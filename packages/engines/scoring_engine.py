import json
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import pandas as pd
from packages.adapters.base import DataAdapter
from packages.config.loader import load_scoring_rules

logger = logging.getLogger(__name__)

VALIDATION_RULES = {
    "gross_margin": {"min": -1.0, "max": 1.0},
    "net_margin": {"min": -1.0, "max": 1.0},
    "revenue_growth": {"min": -1.0, "max": 10.0},
    "net_profit_growth": {"min": -1.0, "max": 10.0},
    "roe": {"min": -1.0, "max": 1.0},
    "pe_ttm": {"min": 0, "max": 1000},
    "ps_ttm": {"min": 0, "max": 100},
    "pb": {"min": 0, "max": 100},
}


@dataclass
class ScoreResult:
    stock_code: str
    report_period: str
    total_score: Optional[float]
    financial_score: Optional[float]
    status: str = "OK"
    breakdown: Dict = field(default_factory=dict)
    raw_values: Dict = field(default_factory=dict)
    benchmarks: Dict = field(default_factory=dict)
    missing_metrics: List[str] = field(default_factory=list)
    message: str = ""
    qualitative_score: Optional[float] = None


def validate_metric(name: str, value: float) -> tuple[bool, str]:
    rule = VALIDATION_RULES.get(name)
    if rule is None:
        return True, ""
    if not (rule["min"] <= value <= rule["max"]):
        return False, f"{name}={value} out of range [{rule['min']}, {rule['max']}]"
    return True, ""


def parse_threshold(threshold: str, value: float) -> int:
    """Parse threshold string like '>40' and return score 1-5"""
    threshold = str(threshold).strip()
    if threshold.startswith(">="):
        target = float(threshold[2:])
        return 5 if value >= target else 0
    elif threshold.startswith(">"):
        target = float(threshold[1:])
        return 5 if value > target else 0
    elif threshold.startswith("<="):
        target = float(threshold[2:])
        return 5 if value <= target else 0
    elif threshold.startswith("<"):
        target = float(threshold[1:])
        return 5 if value < target else 0
    return 0


class ScoringEngine:
    def __init__(self, adapter: DataAdapter = None):
        self.adapter = adapter
        self.rules = load_scoring_rules()

    def get_segment_rules(self, segment: str) -> dict:
        for rule in self.rules.get("financial_rules", []):
            if rule["segment"] == segment:
                return rule
        # fallback to default
        for rule in self.rules.get("financial_rules", []):
            if rule["segment"] == "默认":
                return rule
        raise ValueError(f"No scoring rules found for segment: {segment}")

    def calculate(self, stock_code: str, segment: str, report_period: str) -> ScoreResult:
        df = self.adapter.fetch_with_fallback(stock_code) if self.adapter else pd.DataFrame()
        if df.empty or "data_status" in df.columns:
            return ScoreResult(
                stock_code=stock_code,
                report_period=report_period,
                total_score=None,
                financial_score=None,
                status="INSUFFICIENT_DATA",
                message="No data available from any source",
            )

        segment_rules = self.get_segment_rules(segment)
        metrics = segment_rules.get("metrics", [])

        valid_metrics = []
        missing_metrics = []
        invalid_metrics = []
        breakdown = {}
        raw_values = {}
        benchmarks = {}

        for metric in metrics:
            metric_name = metric["name"]
            # Map metric name to column name (simplified)
            col_map = {
                "毛利率": "gross_margin",
                "净利率": "net_margin",
                "营收同比增长": "revenue_growth",
                "净利润同比增长": "net_profit_growth",
                "ROE": "roe",
            }
            col_name = col_map.get(metric_name, metric_name)

            value = df.iloc[0].get(col_name)
            if pd.isna(value) or value is None:
                missing_metrics.append(metric_name)
                breakdown[metric_name] = None
                continue

            is_valid, error_msg = validate_metric(col_name, float(value))
            if not is_valid:
                logger.warning(f"Data quality issue for {stock_code}: {error_msg}")
                invalid_metrics.append(metric_name)
                breakdown[metric_name] = None
                continue

            raw_values[metric_name] = float(value)
            weights = metric["weights"]

            # Score based on thresholds: excellent=5, good=4, fair=3, poor=1
            score = 0
            if parse_threshold(weights.get("excellent", ""), float(value)):
                score = 5
            elif parse_threshold(weights.get("good", ""), float(value)):
                score = 4
            elif parse_threshold(weights.get("fair", ""), float(value)):
                score = 3
            elif parse_threshold(weights.get("poor", ""), float(value)):
                score = 1
            else:
                score = 2  # Between fair and poor

            breakdown[metric_name] = score
            benchmarks[metric_name] = weights
            valid_metrics.append({"metric": metric, "score": score})

        # Data quality issue: any invalid metric triggers this status
        if invalid_metrics:
            return ScoreResult(
                stock_code=stock_code,
                report_period=report_period,
                total_score=None,
                financial_score=None,
                status="DATA_QUALITY_ISSUE",
                missing_metrics=missing_metrics + invalid_metrics,
                message=f"Data quality issue detected for: {', '.join(invalid_metrics)}",
            )

        missing_ratio = len(missing_metrics) / len(metrics) if metrics else 0
        if missing_ratio > 0.5:
            return ScoreResult(
                stock_code=stock_code,
                report_period=report_period,
                total_score=None,
                financial_score=None,
                status="INSUFFICIENT_DATA",
                missing_metrics=missing_metrics,
                message=f"数据缺失率 {missing_ratio:.0%}，评分不可靠",
            )

        # Calculate weighted score
        total_weight = sum(m["metric"]["weight"] for m in valid_metrics)
        financial_score = 0
        if total_weight > 0:
            for vm in valid_metrics:
                normalized_weight = vm["metric"]["weight"] / total_weight
                financial_score += vm["score"] * normalized_weight

        # Load qualitative score
        qualitative_score = None
        total_score = round(financial_score, 2)
        try:
            from packages.domain.database import get_session
            from packages.domain.models import QualitativeScore
            session = get_session()
            qs = session.query(QualitativeScore).filter_by(stock_code=stock_code).first()
            session.close()
            if qs:
                qualitative_score = round(
                    (qs.global_ranking + qs.localization_potential + qs.customer_health) / 3 * 0.5, 2
                )
                total_score = round(financial_score * 0.7 + qualitative_score * 0.3, 2)
        except Exception:
            pass

        return ScoreResult(
            stock_code=stock_code,
            report_period=report_period,
            total_score=total_score,
            financial_score=round(financial_score, 2),
            status="OK",
            breakdown=breakdown,
            raw_values=raw_values,
            benchmarks=benchmarks,
            missing_metrics=missing_metrics,
            qualitative_score=qualitative_score,
        )
