"""Migrate all stocks from stocks.yml into the structured knowledge base.

Usage:
    python -m scripts.migrate_stocks_to_kb
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from packages.domain.database import init_db, get_session, Transaction
from packages.domain.models import (
    IndustryTree, ConceptTag, StockIndustryKB, StockConceptRel
)
from packages.config.loader import load_stocks


# ── Segment → 4级行业叶子节点 映射 ──
# 每个映射项: (segment_name, leaf_industry_id, [默认概念标签])
SEGMENT_MAPPING = {
    # AI 产业链
    "光模块": (1210, ["光模块", "CPO", "AI算力", "国产替代"]),
    "光模块/CPO": (1210, ["光模块", "CPO", "AI算力", "国产替代"]),
    "服务器": (2102, ["AI算力", "云计算", "数据中心", "国产替代"]),
    "服务器代工": (2102, ["AI算力", "云计算", "数据中心"]),
    "GPU/ASIC芯片": (2002, ["AI算力", "国产替代", "半导体设备"]),
    "数据要素": (2103, ["数据要素", "数字经济", "信创"]),
    "自动驾驶": (1011, ["自动驾驶", "新能源汽车", "智能网联", "华为产业链"]),
    "传媒游戏（AIGC）": (2202, ["大模型", "AIGC", "游戏", "元宇宙"]),
    "AI+医疗": (4012, ["AI医疗", "创新药", "医疗器械", "智慧医疗"]),
    "算法公司": (2104, ["大模型", "人工智能", "信创", "数据要素"]),
    "办公软件": (2105, ["信创", "云计算", "SaaS", "人工智能"]),

    # 机器人产业链
    "减速器": (1100, ["人形机器人", "智能制造", "工业母机", "国产替代"]),
    "伺服电机": (1100, ["人形机器人", "智能制造", "工业母机", "国产替代"]),
    "传感器": (1100, ["人形机器人", "智能制造", "物联网", "国产替代"]),
    "丝杠": (1100, ["人形机器人", "智能制造", "精密制造"]),
    "控制器": (1100, ["人形机器人", "智能制造", "工业自动化", "国产替代"]),
    "整机代工": (1200, ["消费电子", "智能制造", "苹果产业链"]),
    "系统集成": (1113, ["智能制造", "工业自动化", "信创"]),
    "工业制造": (1112, ["工程机械", "智能制造", "一带一路"]),
    "家用服务机器人": (1100, ["人形机器人", "智能家居", "消费电子"]),
    "医疗机器人": (4011, ["医疗器械", "智慧医疗", "机器人"]),
}


# ── 扩展行业树（补充 stocks.yml 中 segment 对应的叶子节点） ──
EXTRA_INDUSTRY_NODES = [
    # 二级 - 信息技术/计算机（已有 21）
    # 三级 - 计算机
    {"id": 210, "name": "计算机", "parent_id": 21, "level": 3, "sort": 1},  # 已有的，确认

    # 四级 - 计算机
    {"id": 2102, "name": "服务器与云计算", "parent_id": 210, "level": 4, "sort": 1},
    {"id": 2103, "name": "数据服务与要素", "parent_id": 210, "level": 4, "sort": 2},
    {"id": 2104, "name": "人工智能软件", "parent_id": 210, "level": 4, "sort": 3},
    {"id": 2105, "name": "企业软件与办公", "parent_id": 210, "level": 4, "sort": 4},
    {"id": 2106, "name": "系统集成服务", "parent_id": 210, "level": 4, "sort": 5},

    # 二级 - 汽车（已有 10）
    # 三级 - 整车（已有 100）
    # 四级 - 整车
    {"id": 1011, "name": "智能网联汽车", "parent_id": 100, "level": 4, "sort": 2},

    # 二级 - 信息技术/传媒
    {"id": 22, "name": "传媒", "parent_id": 2, "level": 2, "sort": 4},
    # 三级 - 传媒
    {"id": 220, "name": "数字内容", "parent_id": 22, "level": 3, "sort": 1},
    # 四级 - 传媒
    {"id": 2202, "name": "游戏与数字内容", "parent_id": 220, "level": 4, "sort": 1},

    # 二级 - 医药生物/医疗器械（已有 40）
    # 三级 - 医疗器械（已有 400）
    # 四级 - 医疗器械
    {"id": 4011, "name": "智能医疗装备", "parent_id": 40, "level": 4, "sort": 3},
    {"id": 4012, "name": "医疗信息化", "parent_id": 40, "level": 4, "sort": 4},

    # 三级 - 专用设备（已有 111）
    # 四级 - 专用设备
    {"id": 1113, "name": "工业自动化", "parent_id": 111, "level": 4, "sort": 4},

    # 二级 - 信息技术/半导体（已有 20）
    # 三级 - 集成电路设计（已有 200）
    # 四级 - 集成电路设计
    {"id": 2002, "name": "GPU与ASIC芯片", "parent_id": 200, "level": 4, "sort": 2},
]


# ── 扩展概念标签 ──
EXTRA_CONCEPT_TAGS = [
    "云计算", "数据中心", "数字经济", "游戏", "元宇宙",
    "智能网联", "AI医疗", "智慧医疗", "物联网",
    "智能家居", "SaaS", "人工智能", "精密制造",
    "工业自动化", "一带一路", "消费电子",
]


def _ensure_extra_industries(session):
    """Add extra industry nodes needed for segment mapping."""
    count = 0
    for node in EXTRA_INDUSTRY_NODES:
        existing = session.query(IndustryTree).filter_by(id=node["id"]).first()
        if not existing:
            session.add(IndustryTree(**node))
            count += 1
    print(f"  Extra industry nodes added: {count}")


def _ensure_extra_concepts(session):
    """Add extra concept tags."""
    count = 0
    for name in EXTRA_CONCEPT_TAGS:
        existing = session.query(ConceptTag).filter_by(name=name).first()
        if not existing:
            session.add(ConceptTag(name=name))
            count += 1
    print(f"  Extra concept tags added: {count}")


def migrate_stocks():
    """Read stocks.yml and migrate all stocks into KB tables."""
    print("Migrating stocks from stocks.yml to knowledge base...")
    init_db()

    stocks = load_stocks()
    print(f"  Total stocks in stocks.yml: {len(stocks)}")

    session = get_session()
    try:
        # Ensure extra industries and concepts exist
        _ensure_extra_industries(session)
        _ensure_extra_concepts(session)
        session.commit()

        # Reload tag map after commit
        tag_map = {t.name: t.id for t in session.query(ConceptTag).all()}

        # Migrate each stock
        inserted = 0
        updated = 0
        skipped = 0

        for s in stocks:
            code = s["code"]
            name = s.get("name", "")
            segment = s.get("segment", "")

            mapping = SEGMENT_MAPPING.get(segment)
            if not mapping:
                print(f"    ⚠️  Unmapped segment '{segment}' for {code}, skipping")
                skipped += 1
                continue

            industry_id, concept_names = mapping

            # Upsert stock KB record
            existing = session.query(StockIndustryKB).filter_by(stock_code=code).first()
            if existing:
                existing.stock_name = name
                existing.std_industry_id = industry_id
                updated += 1
            else:
                session.add(StockIndustryKB(
                    stock_code=code,
                    stock_name=name,
                    std_industry_id=industry_id,
                    business_desc=f"来源环节: {segment}",
                ))
                inserted += 1

            # Upsert concept relations
            session.query(StockConceptRel).filter_by(stock_code=code).delete()
            for cn in concept_names:
                tag_id = tag_map.get(cn)
                if tag_id:
                    session.add(StockConceptRel(
                        stock_code=code,
                        concept_tag_id=tag_id,
                    ))

            # Batch commit every 100 records
            if (inserted + updated) % 100 == 0:
                session.commit()
                print(f"    ... {inserted + updated} processed")

        session.commit()
        print(f"\nMigration complete:")
        print(f"  Inserted: {inserted}")
        print(f"  Updated:  {updated}")
        print(f"  Skipped:  {skipped} (unmapped segment)")

    except Exception as e:
        session.rollback()
        print(f"Error: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    migrate_stocks()
