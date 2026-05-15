"""Initialize structured knowledge base data.

Usage:
    python -m scripts.init_kb_data
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from packages.domain.database import init_db, get_session
from packages.domain.models import IndustryTree, ConceptTag, StockIndustryKB, StockConceptRel


# ── 行业分类树（4级） ──
INDUSTRY_TREE_DATA = [
    # 一级
    {"id": 1, "name": "制造业", "parent_id": 0, "level": 1, "sort": 1},
    {"id": 2, "name": "信息技术", "parent_id": 0, "level": 1, "sort": 2},
    {"id": 3, "name": "消费", "parent_id": 0, "level": 1, "sort": 3},
    {"id": 4, "name": "医药生物", "parent_id": 0, "level": 1, "sort": 4},
    {"id": 5, "name": "金融", "parent_id": 0, "level": 1, "sort": 5},
    {"id": 6, "name": "能源", "parent_id": 0, "level": 1, "sort": 6},

    # 二级 - 制造业
    {"id": 10, "name": "汽车", "parent_id": 1, "level": 2, "sort": 1},
    {"id": 11, "name": "机械设备", "parent_id": 1, "level": 2, "sort": 2},
    {"id": 12, "name": "电子", "parent_id": 1, "level": 2, "sort": 3},
    {"id": 13, "name": "电力设备", "parent_id": 1, "level": 2, "sort": 4},

    # 二级 - 信息技术
    {"id": 20, "name": "半导体", "parent_id": 2, "level": 2, "sort": 1},
    {"id": 21, "name": "计算机", "parent_id": 2, "level": 2, "sort": 2},
    {"id": 22, "name": "通信", "parent_id": 2, "level": 2, "sort": 3},

    # 二级 - 消费
    {"id": 30, "name": "食品饮料", "parent_id": 3, "level": 2, "sort": 1},
    {"id": 31, "name": "家用电器", "parent_id": 3, "level": 2, "sort": 2},

    # 二级 - 医药生物
    {"id": 40, "name": "医疗器械", "parent_id": 4, "level": 2, "sort": 1},
    {"id": 41, "name": "化学制药", "parent_id": 4, "level": 2, "sort": 2},

    # 三级 - 汽车
    {"id": 100, "name": "整车", "parent_id": 10, "level": 3, "sort": 1},
    {"id": 101, "name": "汽车零部件", "parent_id": 10, "level": 3, "sort": 2},
    {"id": 102, "name": "汽车服务", "parent_id": 10, "level": 3, "sort": 3},

    # 三级 - 机械设备
    {"id": 110, "name": "通用设备", "parent_id": 11, "level": 3, "sort": 1},
    {"id": 111, "name": "专用设备", "parent_id": 11, "level": 3, "sort": 2},
    {"id": 112, "name": "自动化设备", "parent_id": 11, "level": 3, "sort": 3},

    # 三级 - 电子
    {"id": 120, "name": "消费电子", "parent_id": 12, "level": 3, "sort": 1},
    {"id": 121, "name": "光学光电子", "parent_id": 12, "level": 3, "sort": 2},
    {"id": 122, "name": "元件", "parent_id": 12, "level": 3, "sort": 3},

    # 三级 - 半导体
    {"id": 200, "name": "集成电路设计", "parent_id": 20, "level": 3, "sort": 1},
    {"id": 201, "name": "半导体设备", "parent_id": 20, "level": 3, "sort": 2},
    {"id": 202, "name": "半导体材料", "parent_id": 20, "level": 3, "sort": 3},

    # 四级 - 汽车零部件
    {"id": 1000, "name": "底盘与发动机系统", "parent_id": 101, "level": 4, "sort": 1},
    {"id": 1001, "name": "车身及内外饰", "parent_id": 101, "level": 4, "sort": 2},
    {"id": 1002, "name": "汽车电子", "parent_id": 101, "level": 4, "sort": 3},
    {"id": 1003, "name": "新能源汽车零部件", "parent_id": 101, "level": 4, "sort": 4},
    {"id": 1004, "name": "轮胎轮毂", "parent_id": 101, "level": 4, "sort": 5},

    # 四级 - 通用设备
    {"id": 1100, "name": "机器人", "parent_id": 110, "level": 4, "sort": 1},
    {"id": 1101, "name": "数控机床", "parent_id": 110, "level": 4, "sort": 2},
    {"id": 1102, "name": "工控设备", "parent_id": 110, "level": 4, "sort": 3},

    # 四级 - 专用设备
    {"id": 1110, "name": "光伏设备", "parent_id": 111, "level": 4, "sort": 1},
    {"id": 1111, "name": "锂电设备", "parent_id": 111, "level": 4, "sort": 2},
    {"id": 1112, "name": "工程机械", "parent_id": 111, "level": 4, "sort": 3},

    # 四级 - 消费电子
    {"id": 1200, "name": "智能手机产业链", "parent_id": 120, "level": 4, "sort": 1},
    {"id": 1201, "name": "智能穿戴", "parent_id": 120, "level": 4, "sort": 2},
    {"id": 1202, "name": "AR/VR", "parent_id": 120, "level": 4, "sort": 3},

    # 四级 - 光学光电子
    {"id": 1210, "name": "光模块/CPO", "parent_id": 121, "level": 4, "sort": 1},
    {"id": 1211, "name": "LED", "parent_id": 121, "level": 4, "sort": 2},
    {"id": 1212, "name": "面板", "parent_id": 121, "level": 4, "sort": 3},

    # 四级 - 半导体设备
    {"id": 2010, "name": "刻蚀设备", "parent_id": 201, "level": 4, "sort": 1},
    {"id": 2011, "name": "薄膜沉积", "parent_id": 201, "level": 4, "sort": 2},
    {"id": 2012, "name": "量检测设备", "parent_id": 201, "level": 4, "sort": 3},
]


# ── 概念标签池 ──
CONCEPT_TAGS = [
    "人形机器人",
    "新能源汽车",
    "汽车零部件",
    "军工",
    "低空经济",
    "固态电池",
    "光模块",
    "CPO",
    "AI算力",
    "大模型",
    "半导体设备",
    "国产替代",
    "卫星互联网",
    "商业航天",
    "数据要素",
    "信创",
    "智能制造",
    "工业母机",
    "氢能源",
    "储能",
    "海上风电",
    "创新药",
    "CXO",
    "脑机接口",
    "消费电子",
    "苹果产业链",
    "华为产业链",
    "小米汽车",
    "特斯拉产业链",
    "比亚迪产业链",
]


# ── 示范数据：万向钱潮 ──
DEMO_STOCKS = [
    {
        "stock_code": "000559.SZ",
        "stock_name": "万向钱潮",
        "std_industry_id": 1000,  # 底盘与发动机系统
        "business_desc": "主营万向节、传动轴、汽车底盘、精密轴承、新能源汽车部件、机器人传动件等",
        "concepts": ["汽车零部件", "新能源汽车", "人形机器人", "军工", "低空经济"],
    }
]


def _seed_industry_tree(session):
    """Upsert industry tree nodes."""
    for node in INDUSTRY_TREE_DATA:
        existing = session.query(IndustryTree).filter_by(id=node["id"]).first()
        if existing:
            existing.name = node["name"]
            existing.parent_id = node["parent_id"]
            existing.level = node["level"]
            existing.sort = node["sort"]
        else:
            session.add(IndustryTree(**node))
    print(f"  Industry tree: {len(INDUSTRY_TREE_DATA)} nodes")


def _seed_concept_tags(session):
    """Upsert concept tags (unique by name)."""
    count = 0
    for name in CONCEPT_TAGS:
        existing = session.query(ConceptTag).filter_by(name=name).first()
        if not existing:
            session.add(ConceptTag(name=name))
            count += 1
    print(f"  Concept tags: {count} new, {len(CONCEPT_TAGS)} total")


def _seed_demo_stocks(session):
    """Insert demo stock data (万向钱潮)."""
    for demo in DEMO_STOCKS:
        # Upsert stock KB record
        existing = session.query(StockIndustryKB).filter_by(stock_code=demo["stock_code"]).first()
        if existing:
            existing.stock_name = demo["stock_name"]
            existing.std_industry_id = demo["std_industry_id"]
            existing.business_desc = demo["business_desc"]
        else:
            session.add(StockIndustryKB(
                stock_code=demo["stock_code"],
                stock_name=demo["stock_name"],
                std_industry_id=demo["std_industry_id"],
                business_desc=demo["business_desc"],
            ))

        # Build concept name -> id mapping
        tag_map = {t.name: t.id for t in session.query(ConceptTag).all()}

        # Clear old relations and re-insert
        session.query(StockConceptRel).filter_by(stock_code=demo["stock_code"]).delete()
        for concept_name in demo["concepts"]:
            tag_id = tag_map.get(concept_name)
            if tag_id:
                session.add(StockConceptRel(
                    stock_code=demo["stock_code"],
                    concept_tag_id=tag_id,
                ))

    print(f"  Demo stocks: {len(DEMO_STOCKS)} (万向钱潮)")


def init_kb():
    """Initialize knowledge base: create tables + seed data."""
    print("Initializing knowledge base...")
    init_db()
    session = get_session()
    try:
        _seed_industry_tree(session)
        _seed_concept_tags(session)
        _seed_demo_stocks(session)
        session.commit()
        print("Knowledge base initialized successfully.")
    except Exception as e:
        session.rollback()
        print(f"Error: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    init_kb()
