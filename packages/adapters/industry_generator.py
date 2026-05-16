"""Auto-generate industry chain configurations from existing stock data.

Given an industry name, this module:
1. Collects relevant stocks from the database (concept tags + business descriptions)
2. Auto-classifies them into upstream/midstream/downstream layers
3. Clusters segments within each layer by concept tags
4. Verifies the generated structure with DeepSeek AI
5. Produces a YAML-compatible industry config dict
"""

import json
import logging
import os
from collections import Counter, defaultdict
from typing import Dict, List, Optional, Tuple

from packages.adapters.l4_classifier import IGNORED_CONCEPTS
from packages.domain.database import get_session
from packages.domain.models import ConceptTag, StockConceptRel, StockIndustryKB

logger = logging.getLogger(__name__)

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


# ── Heuristic keywords for auto-layer classification ──
LAYER_KEYWORDS = {
    "upstream": [
        "材料", "矿产", "资源", "设备", "零部件", "原材料", "硅片", "光刻胶",
        "锂矿", "钴", "镍", "稀土", "化工", "钢材", "金属", "矿石",
    ],
    "midstream": [
        "制造", "生产", "组装", "电池", "组件", "芯片", "模组", "设计",
        "晶圆", "封装", "测试", "加工", "代工", "集成", "核心",
    ],
    "downstream": [
        "应用", "终端", "服务", "运营", "销售", "整车", "电站", "消费",
        "零售", "品牌", "渠道", "物流", "解决方案", "平台",
    ],
}

VERIFY_PROMPT_TEMPLATE = """\
你是一位资深产业链分析师。请评估以下自动生成的产业结构，并给出专业建议。

产业名称：{industry_name}

自动生成的产业结构：
{structure_yaml}

请从以下维度评估：
1. 上下游划分是否合理？是否有 segment 应该被移动到其他层级？
2. segment 名称是否专业准确？是否有更好的命名？
3. 是否有遗漏的重要 segment？
4. 每个层级的命名（如"核心零部件"）是否恰当？

请以 JSON 格式返回，不要包含任何 markdown 代码块标记：
{{
  "overall_score": 8,
  "issues": [
    {{"severity": "high", "description": "...", "suggestion": "..."}}
  ],
  "improved_structure": {{
    "upstream": {{"name": "...", "segments": [{{"name": "...", "description": "..."}}]}},
    "midstream": {{"name": "...", "segments": [{{"name": "...", "description": "..."}}]}},
    "downstream": {{"name": "...", "segments": [{{"name": "...", "description": "..."}}]}}
  }}
}}
"""


class IndustryGenerator:
    """Generate industry chain configs from stock data."""

    def __init__(self, api_key: Optional[str] = None):
        self.session = get_session()
        self.client = None
        self.model = "deepseek-chat"
        if OpenAI is not None:
            key = api_key or os.getenv("DEEPSEEK_API_KEY")
            if key:
                try:
                    self.client = OpenAI(api_key=key, base_url="https://api.deepseek.com/v1")
                except Exception as e:
                    logger.warning(f"Failed to initialize DeepSeek client: {e}")

    def _tag_name_to_id(self) -> Dict[str, int]:
        """Build concept tag name -> id mapping."""
        tags = self.session.query(ConceptTag).all()
        return {t.name: t.id for t in tags}

    def collect_stocks(self, industry_name: str) -> List[StockIndustryKB]:
        """Collect stocks related to the given industry name.

        Strategy:
        1. Exact match on concept tag name
        2. Keyword match in business_desc
        3. Keyword match in industry_raw
        """
        tag_map = self._tag_name_to_id()
        matched_codes = set()

        # 1. Exact concept tag match
        if industry_name in tag_map:
            tag_id = tag_map[industry_name]
            codes = [
                r[0] for r in
                self.session.query(StockConceptRel.stock_code)
                .filter_by(concept_tag_id=tag_id)
                .all()
            ]
            matched_codes.update(codes)
            logger.info(f"Concept tag '{industry_name}' matched {len(codes)} stocks")

        # 2. business_desc keyword match
        desc_matches = (
            self.session.query(StockIndustryKB)
            .filter(StockIndustryKB.business_desc.like(f"%{industry_name}%"))
            .all()
        )
        for s in desc_matches:
            matched_codes.add(s.stock_code)
        logger.info(f"business_desc keyword matched {len(desc_matches)} stocks")

        # 3. industry_raw keyword match
        raw_matches = (
            self.session.query(StockIndustryKB)
            .filter(StockIndustryKB.industry_raw.like(f"%{industry_name}%"))
            .all()
        )
        for s in raw_matches:
            matched_codes.add(s.stock_code)
        logger.info(f"industry_raw keyword matched {len(raw_matches)} stocks")

        if not matched_codes:
            return []

        stocks = (
            self.session.query(StockIndustryKB)
            .filter(StockIndustryKB.stock_code.in_(list(matched_codes)))
            .all()
        )
        return stocks

    def _classify_layer(self, stock: StockIndustryKB, concepts: List[str]) -> str:
        """Classify a stock into upstream/midstream/downstream."""
        scores = {"upstream": 0, "midstream": 0, "downstream": 0}

        # Score from business_desc
        desc = (stock.business_desc or "").lower()
        for layer, keywords in LAYER_KEYWORDS.items():
            for kw in keywords:
                if kw in desc:
                    scores[layer] += 1

        # Score from concept tags
        for c in concepts:
            c_lower = c.lower()
            for layer, keywords in LAYER_KEYWORDS.items():
                for kw in keywords:
                    if kw in c_lower:
                        scores[layer] += 1

        # Score from industry_raw
        raw = (stock.industry_raw or "").lower()
        for layer, keywords in LAYER_KEYWORDS.items():
            for kw in keywords:
                if kw in raw:
                    scores[layer] += 1

        # Default to midstream on tie
        best = max(scores, key=lambda k: (scores[k], k != "midstream"))
        return best

    def _cluster_segments(self, stocks: List[StockIndustryKB], industry_name: str = "") -> List[Dict]:
        """Cluster stocks into segments based on concept tags."""
        # Collect all concept tags for these stocks
        tag_counter = Counter()
        stock_tags = {}

        for stock in stocks:
            tags = [c.name for c in stock.concepts if c.name not in IGNORED_CONCEPTS]
            stock_tags[stock.stock_code] = tags
            for t in tags:
                tag_counter[t] += 1

        # Tags that are too generic or equal to the industry name itself
        # should not be used as segment names
        excluded_tags = {industry_name, "概念"}

        # Use top concept tags as segment names (min 3 stocks per segment)
        segments = []
        assigned = set()

        for tag, count in tag_counter.most_common():
            if count < 3:
                continue
            if tag in excluded_tags:
                continue
            # Skip tags that contain the industry name (too generic)
            if industry_name and industry_name in tag and tag != industry_name:
                continue
            seg_stocks = [
                s for s in stocks
                if tag in stock_tags.get(s.stock_code, [])
                and s.stock_code not in assigned
            ]
            if len(seg_stocks) >= 3:
                segments.append({
                    "name": tag,
                    "stocks": seg_stocks,
                })
                for s in seg_stocks:
                    assigned.add(s.stock_code)

        # Remaining stocks go to "其他"
        remaining = [s for s in stocks if s.stock_code not in assigned]
        if remaining:
            segments.append({
                "name": "其他",
                "stocks": remaining,
            })

        return segments

    def auto_structure(self, stocks: List[StockIndustryKB], industry_name: str = "") -> Dict:
        """Auto-generate upstream/midstream/downstream structure.

        Returns a dict compatible with industry YAML schema.
        """
        if not stocks:
            return {}

        # Build stock -> tags mapping
        stock_tags = {}
        for s in stocks:
            stock_tags[s.stock_code] = [c.name for c in s.concepts]

        # Classify each stock into a layer
        layer_stocks = {"upstream": [], "midstream": [], "downstream": []}
        for s in stocks:
            layer = self._classify_layer(s, stock_tags.get(s.stock_code, []))
            layer_stocks[layer].append(s)

        # Layer display names (auto-generated)
        layer_names = {
            "upstream": "上游",
            "midstream": "中游",
            "downstream": "下游",
        }

        structure = {"name": "", "upstream": {}, "midstream": {}, "downstream": {}}

        for layer in ["upstream", "midstream", "downstream"]:
            segs = self._cluster_segments(layer_stocks[layer], industry_name=industry_name)
            structure[layer] = {
                "name": layer_names[layer],
                "segments": [
                    {
                        "name": seg["name"],
                        "description": f"{len(seg['stocks'])} 只相关标的",
                    }
                    for seg in segs
                ],
            }

        return structure

    def verify_with_deepseek(self, industry_name: str, structure: Dict) -> Optional[Dict]:
        """Send the generated structure to DeepSeek for verification.

        Returns a dict with overall_score, issues, and improved_structure,
        or None if the API call fails.
        """
        if self.client is None:
            logger.warning("OpenAI client not available, skipping DeepSeek verification")
            return None

        import yaml
        structure_yaml = yaml.dump(structure, allow_unicode=True, sort_keys=False)

        prompt = VERIFY_PROMPT_TEMPLATE.format(
            industry_name=industry_name,
            structure_yaml=structure_yaml,
        )

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是一位资深产业链分析师，精通A股各行业产业链结构。"},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=2000,
                temperature=0.3,
            )
            content = response.choices[0].message.content.strip()
            # Remove markdown code block markers if present
            if content.startswith("```"):
                content = content.split("\n", 1)[1]
            if content.endswith("```"):
                content = content.rsplit("\n", 1)[0]
            if content.startswith("json"):
                content = content.split("\n", 1)[1]
            return json.loads(content)
        except Exception as e:
            logger.warning(f"DeepSeek verification failed: {e}")
            return None

    def generate_config(
        self,
        industry_name: str,
        structure: Dict,
        stocks: List[StockIndustryKB],
    ) -> Tuple[Dict, List[Dict]]:
        """Generate final industry config and stocks.yml entries.

        Returns:
            (industry_config_dict, stocks_entries)
        """
        config = {
            "name": industry_name,
            "upstream": structure.get("upstream", {"name": "上游", "segments": []}),
            "midstream": structure.get("midstream", {"name": "中游", "segments": []}),
            "downstream": structure.get("downstream", {"name": "下游", "segments": []}),
        }

        # Build segment -> stock mapping for stocks.yml entries
        stock_tags = {}
        for s in stocks:
            stock_tags[s.stock_code] = [c.name for c in s.concepts]

        layer_stocks = {"upstream": [], "midstream": [], "downstream": []}
        for s in stocks:
            layer = self._classify_layer(s, stock_tags.get(s.stock_code, []))
            layer_stocks[layer].append(s)

        # Cluster per layer and record layer info for each segment
        layer_segments: Dict[str, List[Dict]] = {}
        segment_map: Dict[str, List[StockIndustryKB]] = {}
        layer_segment_map: Dict[str, str] = {}
        for layer in ["upstream", "midstream", "downstream"]:
            segs = self._cluster_segments(layer_stocks[layer], industry_name=industry_name)
            layer_segments[layer] = segs
            for seg in segs:
                name = seg["name"]
                if name not in segment_map:
                    segment_map[name] = []
                segment_map[name].extend(seg["stocks"])
                layer_segment_map[name] = layer

        stocks_entries = []
        for seg_name, seg_stocks in segment_map.items():
            layer = layer_segment_map.get(seg_name, "")
            for s in seg_stocks:
                stocks_entries.append({
                    "code": s.stock_code,
                    "name": s.stock_name,
                    "segment": seg_name,
                    "style": "待分类",
                    "market_cap_tier": "待分类",
                    "_layer": layer,
                })

        return config, stocks_entries

    def close(self):
        self.session.close()
