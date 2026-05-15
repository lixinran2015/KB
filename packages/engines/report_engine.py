import os
import re
from datetime import datetime
from typing import Optional

import jinja2

from packages.adapters.mock_adapter import MockAdapter
from packages.config.loader import load_stocks
from packages.engines.scoring_engine import ScoringEngine
from packages.engines.trigger_engine import TriggerEngine
from packages.engines.valuation_engine import ValuationEngine

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "docs", "_templates")


class ReportEngine:
    def __init__(self):
        self.env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(TEMPLATES_DIR),
            autoescape=False,
        )

    def generate(
        self,
        stock_code: str,
        segment: str,
        report_period: str,
        output_path: Optional[str] = None,
    ) -> str:
        stocks = load_stocks()
        stock = next(
            (s for s in stocks if s["code"] == stock_code),
            {"code": stock_code, "name": "未知"},
        )

        adapter = MockAdapter("stock_300308_q1_2024")
        scoring = ScoringEngine(adapter=adapter).calculate(
            stock_code, segment, report_period
        )
        valuation = ValuationEngine(adapter=adapter).calculate(
            stock_code, segment, report_period
        )
        triggers = TriggerEngine(adapter=adapter).check(stock_code, report_period)

        template = self.env.get_template("stock_report.j2")
        md = template.render(
            stock=stock,
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
            report_period=report_period,
            score_breakdown=scoring.breakdown,
            raw_values=scoring.raw_values,
            total_score=scoring.total_score,
            status=scoring.status,
            valuation_breakdown=valuation.breakdown,
            valuation_raw=valuation.raw_values,
            overall_valuation=valuation.overall_rating,
            triggers=triggers.triggers,
        )

        if output_path and os.path.exists(output_path):
            md = self._preserve_manual_slots(output_path, md)

        if output_path:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(md)

        return md

    def _preserve_manual_slots(self, existing_path: str, new_md: str) -> str:
        with open(existing_path, "r", encoding="utf-8") as f:
            old_md = f.read()

        pattern = r"<!-- MANUAL_SLOT:(\w+) -->(.*?)<!-- END_MANUAL_SLOT -->"
        old_slots = dict(re.findall(pattern, old_md, re.DOTALL))

        def replacer(match):
            slot_name = match.group(1)
            if slot_name in old_slots:
                return f"<!-- MANUAL_SLOT:{slot_name} -->{old_slots[slot_name]}<!-- END_MANUAL_SLOT -->"
            return match.group(0)

        return re.sub(pattern, replacer, new_md, flags=re.DOTALL)
