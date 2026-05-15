"""Tushare-based industry data enrichment adapter.

Fetches concept-board constituents from Tushare and maps them to
industry chain segments defined in config/industries/*.yml.

Requires TUSHARE_TOKEN environment variable or passed directly.
"""

import os
import time
from typing import Dict, List, Optional, Set

import pandas as pd

from packages.config.loader import load_industry, load_stocks


try:
    import tushare as ts
except ImportError:
    ts = None


# Concept name fuzzy mapping: segment keywords -> possible Tushare concept names.
# Based on actual Tushare concept board availability (proven via API test).
# Segments with no matching board are marked with fallback alternatives.
CONCEPT_KEYWORDS: Dict[str, List[str]] = {
    "光模块/CPO": ["光模块", "CPO", "光通信", "光器件", "光纤", "通信设备"],
    "GPU/ASIC芯片": ["芯片", "半导体", "GPU", "ASIC", "集成电路", "AI芯片", "第三代半导体"],
    "服务器": ["服务器", "AI服务器", "算力", "数据中心", "IDC", "云计算", "IT设备"],
    "液冷散热": ["液冷", "散热", "温控", "热管理", "冷却"],
    "大模型厂商": ["大模型", "ChatGPT", "AIGC", "人工智能", "AI", "大语言模型"],
    "数据要素": ["数据要素", "数据确权", "数据交易", "大数据", "数据安全", "数据要素确权"],
    "算法公司": ["算法", "机器视觉", "计算机视觉", "人脸识别", "图像识别"],
    "传媒游戏（AIGC）": ["AIGC", "传媒", "游戏", "短剧", "影视", "网络游戏", "手机游戏"],
    "办公软件": ["办公软件", "SaaS", "云办公", "远程办公", "在线办公"],
    "自动驾驶": ["自动驾驶", "无人驾驶", "智能网联", "车联网", "智能交通", "ADAS"],
    "AI+医疗": ["医疗AI", "智慧医疗", "AI医疗", "数字医疗", "医疗信息化", "互联网医疗"],
    "减速器": ["减速器", "谐波减速器", "RV减速器", "精密减速器", "减速机", "齿轮"],
    "伺服电机": ["伺服电机", "伺服系统", "电机", "伺服", "步进电机", "微特电机"],
    "传感器": ["传感器", "六维力传感器", "机器视觉", "视觉传感器", "激光雷达", "毫米波雷达"],
    "丝杠": ["丝杠", "滚珠丝杠", "行星滚柱丝杠", "精密传动", "传动部件"],
    "整机代工": ["机器人", "工业机器人", "人形机器人", "机器人本体", "机器人制造"],
    "系统集成": ["自动化", "工业自动化", "智能制造", "系统集成", "工厂自动化"],
    "工业制造": ["工业制造", "智能制造", "工业互联网", "工业4.0", "先进制造"],
    "医疗机器人": ["医疗机器人", "手术机器人", "康复机器人", "微创医疗"],
    "家用服务机器人": ["服务机器人", "扫地机器人", "智能家居", "智能家电", "消费机器人"],
}


class TushareIndustryAdapter:
    """Enrich industry chain data via Tushare concept boards."""

    def __init__(self, token: Optional[str] = None):
        if ts is None:
            raise ImportError("tushare not installed; run: pip install tushare")

        self.token = token or os.getenv("TUSHARE_TOKEN")
        if not self.token:
            raise ValueError(
                "Tushare token required. Set TUSHARE_TOKEN env var "
                "or pass token= to constructor."
            )
        self.pro = ts.pro_api(self.token)
        self._concept_cache: Optional[pd.DataFrame] = None

    def _fetch_concept_list(self) -> pd.DataFrame:
        """Fetch all concept boards from Tushare (cached)."""
        if self._concept_cache is not None:
            return self._concept_cache
        df = self.pro.concept()
        self._concept_cache = df
        return df

    def find_concept_codes(self, keywords: List[str]) -> List[str]:
        """Find Tushare concept codes matching any keyword."""
        concepts = self._fetch_concept_list()
        if concepts is None or concepts.empty:
            return []

        matched = set()
        for kw in keywords:
            mask = concepts["name"].str.contains(kw, na=False, case=False)
            matched.update(concepts.loc[mask, "code"].tolist())
        return list(matched)

    def fetch_concept_stocks(self, concept_code: str) -> pd.DataFrame:
        """Fetch constituent stocks for a concept board."""
        try:
            df = self.pro.concept_detail(id=concept_code, fields="ts_code,name")
            time.sleep(0.3)  # Tushare rate limit courtesy
            return df if df is not None else pd.DataFrame()
        except Exception:
            return pd.DataFrame()

    def enrich_segment(
        self, segment_name: str, keywords: Optional[List[str]] = None
    ) -> List[Dict[str, str]]:
        """Fetch and return candidate stocks for a segment.

        Returns list of dicts: [{"code": "300308.SZ", "name": "中际旭创"}, ...]
        """
        kws = keywords or CONCEPT_KEYWORDS.get(segment_name, [segment_name])
        concept_codes = self.find_concept_codes(kws)

        all_stocks: Set[str] = set()
        stock_names: Dict[str, str] = {}

        for cc in concept_codes:
            df = self.fetch_concept_stocks(cc)
            if df.empty:
                continue
            for _, row in df.iterrows():
                code = str(row.get("ts_code", "")).strip()
                name = str(row.get("name", "")).strip()
                if code and len(code.split(".")) == 2:
                    all_stocks.add(code)
                    if name:
                        stock_names[code] = name

        # Also fetch stock_basic to normalize names
        if all_stocks:
            try:
                codes = ",".join(list(all_stocks)[:100])  # Tushare batch limit
                basic = self.pro.stock_basic(ts_code=codes, fields="ts_code,name")
                time.sleep(0.3)
                if basic is not None and not basic.empty:
                    for _, row in basic.iterrows():
                        code = str(row.get("ts_code", "")).strip()
                        name = str(row.get("name", "")).strip()
                        if code and name:
                            stock_names[code] = name
            except Exception:
                pass

        results = []
        for code in sorted(all_stocks):
            results.append({"code": code, "name": stock_names.get(code, "")})
        return results

    def enrich_industry(self, industry_key: str) -> Dict[str, List[Dict[str, str]]]:
        """Enrich all segments in an industry YAML.

        Returns: {segment_name: [stock_dict, ...], ...}
        """
        industry = load_industry(industry_key)
        results: Dict[str, List[Dict[str, str]]] = {}

        for layer_key in ["upstream", "midstream", "downstream"]:
            layer = industry.get(layer_key)
            if not layer:
                continue
            for segment in layer.get("segments", []):
                seg_name = segment["name"]
                stocks = self.enrich_segment(seg_name)
                if stocks:
                    results[seg_name] = stocks

                for sub in segment.get("sub_segments", []):
                    sub_name = sub if isinstance(sub, str) else sub.get("name", "")
                    if sub_name:
                        sub_stocks = self.enrich_segment(sub_name)
                        if sub_stocks:
                            results[sub_name] = sub_stocks

        return results

    def build_stocks_config(self, industry_key: str) -> List[Dict]:
        """Build stocks.yml entries from Tushare concept data.

        Deduplicates across segments and returns standardized entries.
        """
        enriched = self.enrich_industry(industry_key)
        existing = {s["code"] for s in load_stocks()}

        entries = []
        seen = set(existing)

        for seg_name, stocks in enriched.items():
            for s in stocks:
                code = s["code"]
                if code in seen:
                    continue
                seen.add(code)
                entries.append({
                    "code": code,
                    "name": s["name"],
                    "segment": seg_name,
                    "style": "待分类",
                    "market_cap_tier": "待分类",
                })

        return entries
