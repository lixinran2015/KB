import logging
import os
from dataclasses import dataclass, field
from typing import Dict, List

import pandas as pd
import yaml

from packages.adapters.base import DataAdapter

logger = logging.getLogger(__name__)


class TriggerStateMachine:
    VALID_TRANSITIONS = {
        "watching": ["triggered"],
        "triggered": ["confirmed", "expired"],
        "confirmed": [],
        "expired": [],
    }

    def __init__(self, state: str = "watching"):
        self.state = state

    def trigger(self):
        if "triggered" in self.VALID_TRANSITIONS.get(self.state, []):
            self.state = "triggered"

    def confirm(self):
        if "confirmed" in self.VALID_TRANSITIONS.get(self.state, []):
            self.state = "confirmed"

    def expire(self):
        if "expired" in self.VALID_TRANSITIONS.get(self.state, []):
            self.state = "expired"


@dataclass
class TriggerResult:
    stock_code: str
    report_period: str
    status: str = "OK"
    triggers: List[Dict] = field(default_factory=list)
    message: str = ""


class TriggerEngine:
    def __init__(self, adapter: DataAdapter = None):
        self.adapter = adapter
        config_dir = os.path.join(os.path.dirname(__file__), "..", "..", "config")
        path = os.path.join(config_dir, "triggers.yml")
        with open(path, "r", encoding="utf-8") as f:
            self.rules = yaml.safe_load(f)

    def check(self, stock_code: str, report_period: str) -> TriggerResult:
        df = self.adapter.fetch_with_fallback(stock_code) if self.adapter else pd.DataFrame()
        if df.empty or "data_status" in df.columns:
            return TriggerResult(
                stock_code=stock_code,
                report_period=report_period,
                status="INSUFFICIENT_DATA",
                message="No data available from any source",
            )

        row = df.iloc[0]
        triggers: List[Dict] = []

        # Check for insufficient technical data
        required_cols = ["volume", "ma_volume_20", "close", "ma_250"]
        available_cols = [c for c in required_cols if c in df.columns and pd.notna(row.get(c))]
        if not available_cols:
            return TriggerResult(
                stock_code=stock_code,
                report_period=report_period,
                status="INSUFFICIENT_DATA",
                message="No technical data available",
            )

        # Volume spike: volume > ma_volume_20 * 2
        volume = row.get("volume")
        ma_volume_20 = row.get("ma_volume_20")
        if pd.notna(volume) and pd.notna(ma_volume_20):
            if float(volume) > float(ma_volume_20) * 2:
                triggers.append({
                    "id": "volume_spike",
                    "name": "成交量倍量",
                    "category": "technical",
                    "priority": "high",
                    "description": f"成交量 {float(volume):,.0f} > 20日均量 {float(ma_volume_20):,.0f} × 2",
                })

        # Break year line: close > ma_250
        close = row.get("close")
        ma_250 = row.get("ma_250")
        if pd.notna(close) and pd.notna(ma_250):
            if float(close) > float(ma_250):
                triggers.append({
                    "id": "break_year_line",
                    "name": "突破年线",
                    "category": "technical",
                    "priority": "medium",
                    "description": f"收盘价 {float(close):.2f} > 250日均线 {float(ma_250):.2f}",
                })

        # Sector strength: check if stock's segment is in top 3 by momentum
        segment = row.get("segment")
        if segment and self._check_sector_strength(segment):
            triggers.append({
                "id": "sector_strength_top3",
                "name": "板块强度前三",
                "category": "sector",
                "priority": "medium",
                "description": f"所在板块 '{segment}' 涨幅排名进入前三",
            })

        return TriggerResult(
            stock_code=stock_code,
            report_period=report_period,
            status="OK",
            triggers=triggers,
        )

    def _check_sector_strength(self, segment: str) -> bool:
        """Check if segment is in top 3 by momentum."""
        try:
            import akshare as ak
            # Fetch concept board spot data to determine relative strength
            df = ak.stock_board_concept_spot_em()
            if df.empty or "相关板块" not in df.columns:
                return False
            # Map our segment names to concept board names heuristically
            segment_keywords = {
                "光模块": ["光模块", "CPO", "光通信"],
                "GPU/ASIC芯片": ["芯片", "半导体", "GPU"],
                "服务器": ["服务器", "算力", "数据中心"],
                "机器人": ["机器人", "人形机器人"],
                "减速器": ["减速器", "机器人"],
            }
            keywords = segment_keywords.get(segment, [segment])
            for kw in keywords:
                mask = df["相关板块"].astype(str).str.contains(kw, na=False, case=False)
                matched = df[mask]
                if not matched.empty:
                    # Check if any matched board is in top 3 by 涨跌幅
                    df_sorted = df.sort_values("涨跌幅", ascending=False).head(3)
                    if not matched.merge(df_sorted, on="相关板块").empty:
                        return True
            return False
        except Exception:
            return False
