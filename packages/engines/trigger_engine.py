import logging
import os
from dataclasses import dataclass, field
from typing import Dict, List

import pandas as pd
import yaml

from packages.adapters.base import DataAdapter

logger = logging.getLogger(__name__)


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

        return TriggerResult(
            stock_code=stock_code,
            report_period=report_period,
            status="OK",
            triggers=triggers,
        )
