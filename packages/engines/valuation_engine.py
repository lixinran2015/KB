import logging
import os
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import pandas as pd
import yaml

from packages.adapters.base import DataAdapter

logger = logging.getLogger(__name__)


@dataclass
class ValuationResult:
    stock_code: str
    report_period: str
    status: str = "OK"
    overall_rating: Optional[str] = None  # cheap / fair / expensive
    breakdown: Dict[str, Optional[str]] = field(default_factory=dict)
    raw_values: Dict[str, float] = field(default_factory=dict)
    missing_metrics: List[str] = field(default_factory=list)
    message: str = ""


def _parse_valuation_threshold(threshold: str, value: float) -> bool:
    """Check if value satisfies threshold like '<30' or '>=50'"""
    threshold = str(threshold).strip()
    if threshold.startswith(">="):
        target = float(threshold[2:])
        return value >= target
    elif threshold.startswith(">"):
        target = float(threshold[1:])
        return value > target
    elif threshold.startswith("<="):
        target = float(threshold[2:])
        return value <= target
    elif threshold.startswith("<"):
        target = float(threshold[1:])
        return value < target
    return False


class ValuationEngine:
    def __init__(self, adapter: DataAdapter = None):
        self.adapter = adapter
        config_dir = os.path.join(os.path.dirname(__file__), "..", "..", "config")
        path = os.path.join(config_dir, "valuation_rules.yml")
        with open(path, "r", encoding="utf-8") as f:
            self.rules = yaml.safe_load(f)

    def get_segment_rules(self, segment: str) -> dict:
        for rule in self.rules.get("valuation_rules", []):
            if rule["segment"] == segment:
                return rule
        for rule in self.rules.get("valuation_rules", []):
            if rule["segment"] == "默认":
                return rule
        raise ValueError(f"No valuation rules found for segment: {segment}")

    def calculate(self, stock_code: str, segment: str, report_period: str) -> ValuationResult:
        df = self.adapter.fetch_with_fallback(stock_code) if self.adapter else pd.DataFrame()
        if df.empty or "data_status" in df.columns:
            return ValuationResult(
                stock_code=stock_code,
                report_period=report_period,
                status="INSUFFICIENT_DATA",
                message="No data available from any source",
            )

        segment_rules = self.get_segment_rules(segment)
        metrics = segment_rules.get("metrics", [])

        col_map = {
            "PE_TTM": "pe_ttm",
            "PB": "pb",
            "PS_TTM": "ps_ttm",
        }

        breakdown: Dict[str, Optional[str]] = {}
        raw_values: Dict[str, float] = {}
        missing_metrics: List[str] = []
        ratings: List[str] = []

        for metric in metrics:
            metric_name = metric["name"]
            col_name = col_map.get(metric_name, metric_name)

            value = df.iloc[0].get(col_name)
            if pd.isna(value) or value is None:
                missing_metrics.append(metric_name)
                breakdown[metric_name] = None
                continue

            raw_values[metric_name] = float(value)

            if _parse_valuation_threshold(metric.get("cheap", ""), float(value)):
                rating = "cheap"
            elif _parse_valuation_threshold(metric.get("fair", ""), float(value)):
                rating = "fair"
            elif _parse_valuation_threshold(metric.get("expensive", ""), float(value)):
                rating = "expensive"
            else:
                rating = "fair"

            breakdown[metric_name] = rating
            ratings.append(rating)

        missing_ratio = len(missing_metrics) / len(metrics) if metrics else 0
        if missing_ratio > 0.5:
            return ValuationResult(
                stock_code=stock_code,
                report_period=report_period,
                status="INSUFFICIENT_DATA",
                missing_metrics=missing_metrics,
                message=f"估值数据缺失率 {missing_ratio:.0%}，无法评估",
            )

        overall = Counter(ratings).most_common(1)[0][0] if ratings else None

        return ValuationResult(
            stock_code=stock_code,
            report_period=report_period,
            status="OK",
            overall_rating=overall,
            breakdown=breakdown,
            raw_values=raw_values,
            missing_metrics=missing_metrics,
        )
