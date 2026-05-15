#!/usr/bin/env python3
"""清洗 stocks.yml：基于概念标签保留核心公司，补充遗漏标的。

方案A实现：
1. 为每个 segment 定义核心概念标签（排除通用标签如融资融券、深股通等）
2. 保留 stocks.yml 中至少匹配一个核心标签的股票
3. 从数据库中查询有核心概念标签但不在 stocks.yml 中的股票，补充进来
4. 合并 "光模块" -> "光模块/CPO"
"""

import yaml
from collections import defaultdict
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from packages.domain.database import get_session
from packages.domain.models import StockConceptRel, ConceptTag, StockIndustryKB

# ── Segment -> 核心概念标签映射 ──
# 只包含能精准定义该细分领域的标签，排除融资融券/深股通等通用标签
SEGMENT_TO_CONCEPTS = {
    "服务器": ["云计算", "数据中心", "大数据", "国产软件", "边缘计算", "网络安全"],
    "GPU/ASIC芯片": ["集成电路概念", "第三代半导体", "中芯国际概念", "氮化镓", "AI芯片", "国产替代"],
    "数据要素": ["大数据"],
    "自动驾驶": ["无人驾驶", "车联网", "智能汽车", "新能源整车", "汽车电子"],
    "工业制造": ["工业4.0", "工业互联网", "高端装备"],
    "传媒游戏（AIGC）": ["影视娱乐", "网络游戏", "手机游戏", "动漫", "IP概念", "云游戏", "网络直播"],
    "整机代工": ["工业机器人", "服务机器人"],  # 注意：原segment名与标签有偏差，按标签清洗
    "AI+医疗": ["互联网医疗", "医疗器械概念", "智能医疗", "生物医药"],
    "算法公司": ["机器视觉", "人脸识别", "安防"],
    "家用服务机器人": ["智能家居", "服务机器人", "家用电器"],
    "光模块/CPO": ["光纤", "宽带中国", "光模块", "CPO"],
    "伺服电机": ["电机电控", "节能电机"],
    "传感器": ["传感器"],
    "办公软件": ["云办公", "国产软件", "SAAS"],
    "光模块": ["光模块", "光纤", "CPO"],  # 将被合并到光模块/CPO
}

# Segment 重命名映射
SEGMENT_RENAME = {
    "光模块": "光模块/CPO",
}


def get_tag_name_to_id(session):
    """构建概念标签名 -> id 映射。"""
    tags = session.query(ConceptTag).all()
    return {t.name: t.id for t in tags}


def get_stock_tags(session, stock_code, tag_name_to_id):
    """获取某只股票的所有概念标签名。"""
    rels = session.query(StockConceptRel).filter_by(stock_code=stock_code).all()
    tag_ids = [r.concept_tag_id for r in rels]
    # 反向查名称
    id_to_name = {v: k for k, v in tag_name_to_id.items()}
    return [id_to_name.get(tid) for tid in tag_ids if id_to_name.get(tid)]


def has_core_tag(stock_code, core_tags, tag_name_to_id, stock_tag_cache):
    """检查股票是否有至少一个核心概念标签。"""
    if stock_code not in stock_tag_cache:
        return False
    stock_tags = stock_tag_cache[stock_code]
    return any(tag in stock_tags for tag in core_tags)


def main():
    session = get_session()
    tag_name_to_id = get_tag_name_to_id(session)

    # 读取 stocks.yml
    stocks_path = Path(__file__).parent.parent / "config" / "stocks.yml"
    with open(stocks_path, "r") as f:
        data = yaml.safe_load(f)

    original_stocks = data.get("stocks", [])
    print(f"原始 stocks.yml 共 {len(original_stocks)} 只股票")

    # ── 步骤1：预加载所有 stocks.yml 中股票的概念标签 ──
    all_codes = [s["code"] for s in original_stocks]
    stock_tag_cache = {}
    for code in all_codes:
        stock_tag_cache[code] = get_stock_tags(session, code, tag_name_to_id)

    # ── 步骤2：清洗 - 保留有核心标签的股票 ──
    cleaned_stocks = []
    removed_count = defaultdict(int)
    kept_count = defaultdict(int)

    for s in original_stocks:
        code = s["code"]
        seg = s.get("segment", "")

        # 重命名 segment
        if seg in SEGMENT_RENAME:
            seg = SEGMENT_RENAME[seg]
            s["segment"] = seg

        core_tags = SEGMENT_TO_CONCEPTS.get(seg, [])
        if not core_tags:
            # 未知 segment，保留
            cleaned_stocks.append(s)
            continue

        if has_core_tag(code, core_tags, tag_name_to_id, stock_tag_cache):
            cleaned_stocks.append(s)
            kept_count[seg] += 1
        else:
            removed_count[seg] += 1

    print(f"\n清洗后保留 {len(cleaned_stocks)} 只，移除 {len(original_stocks) - len(cleaned_stocks)} 只")

    # ── 步骤3：从数据库补充遗漏的核心公司 ──
    # 为每个核心标签找到关联的股票，补充到对应 segment
    added_count = defaultdict(int)

    # 反向映射：核心标签 -> 哪些 segment 使用它
    tag_to_segments = defaultdict(list)
    for seg, tags in SEGMENT_TO_CONCEPTS.items():
        for tag in tags:
            tag_to_segments[tag].append(seg)

    # 已存在的股票代码集合
    existing_codes = {s["code"] for s in cleaned_stocks}

    # 查询数据库中所有有概念标签的股票
    id_to_tag_name = {v: k for k, v in tag_name_to_id.items()}
    all_rels = session.query(StockConceptRel).all()
    stock_to_tags = defaultdict(set)
    for rel in all_rels:
        tag_name = id_to_tag_name.get(rel.concept_tag_id)
        if tag_name:
            stock_to_tags[rel.stock_code].add(tag_name)

    # 补充逻辑：对于每个 segment，找到有对应核心标签但不在 stocks.yml 中的股票
    # 每个 segment 最多补充 MAX_SUPPLEMENT 只，避免过于臃肿
    MAX_SUPPLEMENT = 50

    for seg, core_tags in SEGMENT_TO_CONCEPTS.items():
        if seg == "光模块":  # 已合并
            continue

        target_tags = set(core_tags)
        candidates = []
        for code, tags in stock_to_tags.items():
            if code in existing_codes:
                continue
            if target_tags & tags:  # 有交集
                kb = session.query(StockIndustryKB).filter_by(stock_code=code).first()
                if kb:
                    candidates.append((code, kb.stock_name))

        # 限制补充数量
        to_add = candidates[:MAX_SUPPLEMENT]
        for code, name in to_add:
            cleaned_stocks.append({
                "code": code,
                "name": name,
                "segment": seg,
                "style": "待分类",
                "market_cap_tier": "待分类",
            })
            existing_codes.add(code)
            added_count[seg] += 1

    print(f"\n从数据库补充 {sum(added_count.values())} 只股票")

    # ── 步骤4：输出统计 ──
    print("\n=== 各 Segment 统计 ===")
    segment_counts = defaultdict(int)
    for s in cleaned_stocks:
        segment_counts[s["segment"]] += 1

    for seg in sorted(segment_counts.keys(), key=lambda x: segment_counts[x], reverse=True):
        orig = sum(1 for s in original_stocks if s.get("segment") == seg or (seg == "光模块/CPO" and s.get("segment") in ("光模块/CPO", "光模块")))
        rem = removed_count.get(seg, 0)
        add = added_count.get(seg, 0)
        print(f"  {seg}: {orig} -> {segment_counts[seg]} (移除{rem}, 补充{add})")

    # ── 步骤5：写回 stocks.yml ──
    # 去重（按 code+segment）
    seen = set()
    unique_stocks = []
    for s in cleaned_stocks:
        key = (s["code"], s.get("segment", ""))
        if key not in seen:
            seen.add(key)
            unique_stocks.append(s)

    # 排序：先按 segment，再按 code
    unique_stocks.sort(key=lambda s: (s.get("segment", ""), s["code"]))

    with open(stocks_path, "w") as f:
        yaml.dump({"stocks": unique_stocks}, f, allow_unicode=True, sort_keys=False)

    print(f"\n最终 stocks.yml: {len(unique_stocks)} 只股票")
    session.close()


if __name__ == "__main__":
    main()
