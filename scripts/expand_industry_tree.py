"""Expand industry_tree with traditional sectors and update mappings.

Usage:
    python -m scripts.expand_industry_tree
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from packages.domain.database import get_session
from packages.domain.models import IndustryTree, StockIndustryKB

# ── 新增行业树节点 ──
NEW_NODES = [
    # === 金融 (parent_id=5) ===
    # level=2
    {"id": 50, "name": "银行", "parent_id": 5, "level": 2, "sort": 1},
    {"id": 51, "name": "证券", "parent_id": 5, "level": 2, "sort": 2},
    {"id": 52, "name": "保险", "parent_id": 5, "level": 2, "sort": 3},
    {"id": 53, "name": "多元金融", "parent_id": 5, "level": 2, "sort": 4},
    {"id": 54, "name": "房地产", "parent_id": 5, "level": 2, "sort": 5},
    {"id": 55, "name": "建筑建材", "parent_id": 5, "level": 2, "sort": 6},
    # level=3
    {"id": 500, "name": "银行业", "parent_id": 50, "level": 3, "sort": 1},
    {"id": 510, "name": "证券业", "parent_id": 51, "level": 3, "sort": 1},
    {"id": 520, "name": "保险业", "parent_id": 52, "level": 3, "sort": 1},
    {"id": 530, "name": "非银金融", "parent_id": 53, "level": 3, "sort": 1},
    {"id": 540, "name": "房地产开发", "parent_id": 54, "level": 3, "sort": 1},
    {"id": 550, "name": "建筑工程", "parent_id": 55, "level": 3, "sort": 1},
    {"id": 560, "name": "建材", "parent_id": 55, "level": 3, "sort": 2},
    # level=4
    {"id": 5000, "name": "银行", "parent_id": 500, "level": 4, "sort": 1},
    {"id": 5001, "name": "证券", "parent_id": 510, "level": 4, "sort": 1},
    {"id": 5002, "name": "保险", "parent_id": 520, "level": 4, "sort": 1},
    {"id": 5003, "name": "信托", "parent_id": 530, "level": 4, "sort": 1},
    {"id": 5004, "name": "期货", "parent_id": 530, "level": 4, "sort": 2},
    {"id": 5005, "name": "创投", "parent_id": 530, "level": 4, "sort": 3},
    {"id": 5006, "name": "多元金融", "parent_id": 530, "level": 4, "sort": 4},
    {"id": 5400, "name": "房地产开发", "parent_id": 540, "level": 4, "sort": 1},
    {"id": 5401, "name": "物业管理", "parent_id": 540, "level": 4, "sort": 2},
    {"id": 5402, "name": "园区开发", "parent_id": 540, "level": 4, "sort": 3},
    {"id": 5403, "name": "房产服务", "parent_id": 540, "level": 4, "sort": 4},
    {"id": 5404, "name": "全国地产", "parent_id": 540, "level": 4, "sort": 5},
    {"id": 5405, "name": "区域地产", "parent_id": 540, "level": 4, "sort": 6},
    {"id": 5500, "name": "建筑工程", "parent_id": 550, "level": 4, "sort": 1},
    {"id": 5501, "name": "基础建设", "parent_id": 550, "level": 4, "sort": 2},
    {"id": 5502, "name": "专业工程", "parent_id": 550, "level": 4, "sort": 3},
    {"id": 5503, "name": "装修装饰", "parent_id": 550, "level": 4, "sort": 4},
    {"id": 5600, "name": "水泥", "parent_id": 560, "level": 4, "sort": 1},
    {"id": 5601, "name": "玻璃", "parent_id": 560, "level": 4, "sort": 2},
    {"id": 5602, "name": "陶瓷", "parent_id": 560, "level": 4, "sort": 3},
    {"id": 5603, "name": "耐火材料", "parent_id": 560, "level": 4, "sort": 4},
    {"id": 5604, "name": "管材", "parent_id": 560, "level": 4, "sort": 5},
    {"id": 5605, "name": "防水材料", "parent_id": 560, "level": 4, "sort": 6},
    {"id": 5606, "name": "其他建材", "parent_id": 560, "level": 4, "sort": 7},

    # === 消费 (parent_id=3) ===
    # level=2
    {"id": 32, "name": "纺织服饰", "parent_id": 3, "level": 2, "sort": 3},
    {"id": 33, "name": "商贸零售", "parent_id": 3, "level": 2, "sort": 4},
    {"id": 34, "name": "社会服务", "parent_id": 3, "level": 2, "sort": 5},
    {"id": 35, "name": "美容护理", "parent_id": 3, "level": 2, "sort": 6},
    {"id": 36, "name": "农林牧渔", "parent_id": 3, "level": 2, "sort": 7},
    {"id": 37, "name": "轻工制造", "parent_id": 3, "level": 2, "sort": 8},
    # level=3
    {"id": 320, "name": "纺织服装", "parent_id": 32, "level": 3, "sort": 1},
    {"id": 330, "name": "商业贸易", "parent_id": 33, "level": 3, "sort": 1},
    {"id": 340, "name": "旅游酒店", "parent_id": 34, "level": 3, "sort": 1},
    {"id": 350, "name": "美容个护", "parent_id": 35, "level": 3, "sort": 1},
    {"id": 360, "name": "农业", "parent_id": 36, "level": 3, "sort": 1},
    {"id": 370, "name": "轻工", "parent_id": 37, "level": 3, "sort": 1},
    # level=4 - 食品饮料细分
    {"id": 3000, "name": "白酒", "parent_id": 30, "level": 4, "sort": 1},
    {"id": 3001, "name": "食品", "parent_id": 30, "level": 4, "sort": 2},
    {"id": 3002, "name": "乳制品", "parent_id": 30, "level": 4, "sort": 3},
    {"id": 3003, "name": "调味品", "parent_id": 30, "level": 4, "sort": 4},
    {"id": 3004, "name": "啤酒", "parent_id": 30, "level": 4, "sort": 5},
    {"id": 3005, "name": "休闲食品", "parent_id": 30, "level": 4, "sort": 6},
    {"id": 3006, "name": "软饮料", "parent_id": 30, "level": 4, "sort": 7},
    {"id": 3007, "name": "红黄酒", "parent_id": 30, "level": 4, "sort": 8},
    # level=4 - 家电细分
    {"id": 3100, "name": "白色家电", "parent_id": 31, "level": 4, "sort": 1},
    {"id": 3101, "name": "小家电", "parent_id": 31, "level": 4, "sort": 2},
    {"id": 3102, "name": "厨电", "parent_id": 31, "level": 4, "sort": 3},
    {"id": 3103, "name": "黑色家电", "parent_id": 31, "level": 4, "sort": 4},
    {"id": 3104, "name": "智能家居", "parent_id": 31, "level": 4, "sort": 5},
    {"id": 3105, "name": "电器连锁", "parent_id": 31, "level": 4, "sort": 6},
    # level=4 - 纺织服饰
    {"id": 3200, "name": "纺织", "parent_id": 320, "level": 4, "sort": 1},
    {"id": 3201, "name": "服饰", "parent_id": 320, "level": 4, "sort": 2},
    {"id": 3202, "name": "家纺", "parent_id": 320, "level": 4, "sort": 3},
    {"id": 3203, "name": "鞋帽", "parent_id": 320, "level": 4, "sort": 4},
    # level=4 - 商贸零售
    {"id": 3300, "name": "百货", "parent_id": 330, "level": 4, "sort": 1},
    {"id": 3301, "name": "超市", "parent_id": 330, "level": 4, "sort": 2},
    {"id": 3302, "name": "电商", "parent_id": 330, "level": 4, "sort": 3},
    {"id": 3303, "name": "专业连锁", "parent_id": 330, "level": 4, "sort": 4},
    {"id": 3304, "name": "跨境电商", "parent_id": 330, "level": 4, "sort": 5},
    {"id": 3305, "name": "免税", "parent_id": 330, "level": 4, "sort": 6},
    {"id": 3306, "name": "珠宝首饰", "parent_id": 330, "level": 4, "sort": 7},
    {"id": 3307, "name": "商品城", "parent_id": 330, "level": 4, "sort": 8},
    {"id": 3308, "name": "商贸代理", "parent_id": 330, "level": 4, "sort": 9},
    {"id": 3309, "name": "批发业", "parent_id": 330, "level": 4, "sort": 10},
    {"id": 3310, "name": "其他商业", "parent_id": 330, "level": 4, "sort": 11},
    # level=4 - 社会服务
    {"id": 3400, "name": "旅游", "parent_id": 340, "level": 4, "sort": 1},
    {"id": 3401, "name": "酒店餐饮", "parent_id": 340, "level": 4, "sort": 2},
    {"id": 3402, "name": "教育", "parent_id": 340, "level": 4, "sort": 3},
    {"id": 3403, "name": "体育", "parent_id": 340, "level": 4, "sort": 4},
    {"id": 3404, "name": "旅游景点", "parent_id": 340, "level": 4, "sort": 5},
    {"id": 3405, "name": "旅游服务", "parent_id": 340, "level": 4, "sort": 6},
    # level=4 - 美容护理
    {"id": 3500, "name": "化妆品", "parent_id": 350, "level": 4, "sort": 1},
    {"id": 3501, "name": "个人护理", "parent_id": 350, "level": 4, "sort": 2},
    {"id": 3502, "name": "日用化工", "parent_id": 350, "level": 4, "sort": 3},
    # level=4 - 农林牧渔
    {"id": 3600, "name": "种植业", "parent_id": 360, "level": 4, "sort": 1},
    {"id": 3601, "name": "畜牧业", "parent_id": 360, "level": 4, "sort": 2},
    {"id": 3602, "name": "渔业", "parent_id": 360, "level": 4, "sort": 3},
    {"id": 3603, "name": "林业", "parent_id": 360, "level": 4, "sort": 4},
    {"id": 3604, "name": "饲料", "parent_id": 360, "level": 4, "sort": 5},
    {"id": 3605, "name": "农业综合", "parent_id": 360, "level": 4, "sort": 6},
    # level=4 - 轻工制造
    {"id": 3700, "name": "造纸", "parent_id": 370, "level": 4, "sort": 1},
    {"id": 3701, "name": "家居用品", "parent_id": 370, "level": 4, "sort": 2},
    {"id": 3702, "name": "家具", "parent_id": 370, "level": 4, "sort": 3},
    {"id": 3703, "name": "包装印刷", "parent_id": 370, "level": 4, "sort": 4},
    {"id": 3704, "name": "文具", "parent_id": 370, "level": 4, "sort": 5},
    {"id": 3705, "name": "卫浴", "parent_id": 370, "level": 4, "sort": 6},

    # === 能源 (parent_id=6) ===
    # level=2
    {"id": 60, "name": "煤炭", "parent_id": 6, "level": 2, "sort": 1},
    {"id": 61, "name": "石油石化", "parent_id": 6, "level": 2, "sort": 2},
    {"id": 62, "name": "电力", "parent_id": 6, "level": 2, "sort": 3},
    # level=3
    {"id": 600, "name": "煤炭开采", "parent_id": 60, "level": 3, "sort": 1},
    {"id": 610, "name": "石油化工", "parent_id": 61, "level": 3, "sort": 1},
    {"id": 620, "name": "电力生产", "parent_id": 62, "level": 3, "sort": 1},
    # level=4
    {"id": 6000, "name": "煤炭开采", "parent_id": 600, "level": 4, "sort": 1},
    {"id": 6001, "name": "焦炭加工", "parent_id": 600, "level": 4, "sort": 2},
    {"id": 6100, "name": "石油开采", "parent_id": 610, "level": 4, "sort": 1},
    {"id": 6101, "name": "石油加工", "parent_id": 610, "level": 4, "sort": 2},
    {"id": 6102, "name": "石油贸易", "parent_id": 610, "level": 4, "sort": 3},
    {"id": 6103, "name": "天然气", "parent_id": 610, "level": 4, "sort": 4},
    {"id": 6104, "name": "油服工程", "parent_id": 610, "level": 4, "sort": 5},
    {"id": 6200, "name": "火电", "parent_id": 620, "level": 4, "sort": 1},
    {"id": 6201, "name": "水电", "parent_id": 620, "level": 4, "sort": 2},
    {"id": 6202, "name": "风电", "parent_id": 620, "level": 4, "sort": 3},
    {"id": 6203, "name": "核电", "parent_id": 620, "level": 4, "sort": 4},
    {"id": 6204, "name": "光伏", "parent_id": 620, "level": 4, "sort": 5},
    {"id": 6205, "name": "储能", "parent_id": 620, "level": 4, "sort": 6},
    {"id": 6206, "name": "新型电力", "parent_id": 620, "level": 4, "sort": 7},

    # === 原材料 - 制造业 (parent_id=1) ===
    # level=2
    {"id": 14, "name": "化工", "parent_id": 1, "level": 2, "sort": 5},
    {"id": 15, "name": "钢铁", "parent_id": 1, "level": 2, "sort": 6},
    {"id": 16, "name": "有色金属", "parent_id": 1, "level": 2, "sort": 7},
    {"id": 17, "name": "建筑材料", "parent_id": 1, "level": 2, "sort": 8},
    # level=3
    {"id": 140, "name": "基础化工", "parent_id": 14, "level": 3, "sort": 1},
    {"id": 150, "name": "钢铁冶炼", "parent_id": 15, "level": 3, "sort": 1},
    {"id": 160, "name": "有色金属冶炼", "parent_id": 16, "level": 3, "sort": 1},
    {"id": 170, "name": "建材", "parent_id": 17, "level": 3, "sort": 1},
    # level=4 - 化工
    {"id": 1400, "name": "化工原料", "parent_id": 140, "level": 4, "sort": 1},
    {"id": 1401, "name": "农药化肥", "parent_id": 140, "level": 4, "sort": 2},
    {"id": 1402, "name": "塑料", "parent_id": 140, "level": 4, "sort": 3},
    {"id": 1403, "name": "橡胶", "parent_id": 140, "level": 4, "sort": 4},
    {"id": 1404, "name": "化纤", "parent_id": 140, "level": 4, "sort": 5},
    {"id": 1405, "name": "聚氨酯", "parent_id": 140, "level": 4, "sort": 6},
    {"id": 1406, "name": "有机硅", "parent_id": 140, "level": 4, "sort": 7},
    {"id": 1407, "name": "钛白粉", "parent_id": 140, "level": 4, "sort": 8},
    {"id": 1408, "name": "氟化工", "parent_id": 140, "level": 4, "sort": 9},
    {"id": 1409, "name": "氯碱", "parent_id": 140, "level": 4, "sort": 10},
    {"id": 1410, "name": "煤化工", "parent_id": 140, "level": 4, "sort": 11},
    {"id": 1411, "name": "染料涂料", "parent_id": 140, "level": 4, "sort": 12},
    {"id": 1412, "name": "矿物制品", "parent_id": 140, "level": 4, "sort": 13},
    # level=4 - 钢铁
    {"id": 1500, "name": "普钢", "parent_id": 150, "level": 4, "sort": 1},
    {"id": 1501, "name": "特钢", "parent_id": 150, "level": 4, "sort": 2},
    {"id": 1502, "name": "冶钢原料", "parent_id": 150, "level": 4, "sort": 3},
    {"id": 1503, "name": "钢加工", "parent_id": 150, "level": 4, "sort": 4},
    # level=4 - 有色金属
    {"id": 1600, "name": "铜", "parent_id": 160, "level": 4, "sort": 1},
    {"id": 1601, "name": "铝", "parent_id": 160, "level": 4, "sort": 2},
    {"id": 1602, "name": "小金属", "parent_id": 160, "level": 4, "sort": 3},
    {"id": 1603, "name": "黄金", "parent_id": 160, "level": 4, "sort": 4},
    {"id": 1604, "name": "稀土", "parent_id": 160, "level": 4, "sort": 5},
    {"id": 1605, "name": "钨", "parent_id": 160, "level": 4, "sort": 6},
    {"id": 1606, "name": "钴", "parent_id": 160, "level": 4, "sort": 7},
    {"id": 1607, "name": "镍", "parent_id": 160, "level": 4, "sort": 8},
    {"id": 1608, "name": "铅锌", "parent_id": 160, "level": 4, "sort": 9},
    {"id": 1609, "name": "磁材", "parent_id": 160, "level": 4, "sort": 10},
    {"id": 1610, "name": "非金属材料", "parent_id": 160, "level": 4, "sort": 11},
    {"id": 1611, "name": "金属新材料", "parent_id": 160, "level": 4, "sort": 12},
    # level=4 - 建筑材料
    {"id": 1700, "name": "水泥", "parent_id": 170, "level": 4, "sort": 1},
    {"id": 1701, "name": "玻璃", "parent_id": 170, "level": 4, "sort": 2},
    {"id": 1702, "name": "陶瓷", "parent_id": 170, "level": 4, "sort": 3},
    {"id": 1703, "name": "其他建材", "parent_id": 170, "level": 4, "sort": 4},

    # === 公用事业 (新增 level=1: 7) ===
    {"id": 7, "name": "公用事业", "parent_id": 0, "level": 1, "sort": 7},
    # level=2
    {"id": 70, "name": "环保", "parent_id": 7, "level": 2, "sort": 1},
    {"id": 71, "name": "水务", "parent_id": 7, "level": 2, "sort": 2},
    {"id": 72, "name": "燃气供热", "parent_id": 7, "level": 2, "sort": 3},
    {"id": 73, "name": "交通运输", "parent_id": 7, "level": 2, "sort": 4},
    # level=3
    {"id": 700, "name": "环境保护", "parent_id": 70, "level": 3, "sort": 1},
    {"id": 710, "name": "水务", "parent_id": 71, "level": 3, "sort": 1},
    {"id": 720, "name": "燃气", "parent_id": 72, "level": 3, "sort": 1},
    {"id": 730, "name": "交运物流", "parent_id": 73, "level": 3, "sort": 1},
    # level=4
    {"id": 7000, "name": "环境保护", "parent_id": 700, "level": 4, "sort": 1},
    {"id": 7001, "name": "固废处理", "parent_id": 700, "level": 4, "sort": 2},
    {"id": 7002, "name": "污水处理", "parent_id": 700, "level": 4, "sort": 3},
    {"id": 7003, "name": "大气治理", "parent_id": 700, "level": 4, "sort": 4},
    {"id": 7100, "name": "水务", "parent_id": 710, "level": 4, "sort": 1},
    {"id": 7200, "name": "燃气", "parent_id": 720, "level": 4, "sort": 1},
    {"id": 7201, "name": "供热", "parent_id": 720, "level": 4, "sort": 2},
    {"id": 7300, "name": "物流", "parent_id": 730, "level": 4, "sort": 1},
    {"id": 7301, "name": "仓储", "parent_id": 730, "level": 4, "sort": 2},
    {"id": 7302, "name": "港口", "parent_id": 730, "level": 4, "sort": 3},
    {"id": 7303, "name": "航空", "parent_id": 730, "level": 4, "sort": 4},
    {"id": 7304, "name": "铁路", "parent_id": 730, "level": 4, "sort": 5},
    {"id": 7305, "name": "公路", "parent_id": 730, "level": 4, "sort": 6},
    {"id": 7306, "name": "航运", "parent_id": 730, "level": 4, "sort": 7},
    {"id": 7307, "name": "公交", "parent_id": 730, "level": 4, "sort": 8},
    {"id": 7308, "name": "机场", "parent_id": 730, "level": 4, "sort": 9},
    {"id": 7309, "name": "空运", "parent_id": 730, "level": 4, "sort": 10},
    {"id": 7310, "name": "水运", "parent_id": 730, "level": 4, "sort": 11},
    {"id": 7311, "name": "路桥", "parent_id": 730, "level": 4, "sort": 12},
    {"id": 7312, "name": "公共交通", "parent_id": 730, "level": 4, "sort": 13},
    {"id": 7313, "name": "摩托车", "parent_id": 730, "level": 4, "sort": 14},

    # === 综合 (parent_id=1) ===
    {"id": 18, "name": "综合", "parent_id": 1, "level": 2, "sort": 9},
    {"id": 180, "name": "综合类", "parent_id": 18, "level": 3, "sort": 1},
    {"id": 1800, "name": "综合类", "parent_id": 180, "level": 4, "sort": 1},

    # === 缺失的信息技术/医药叶子节点（修复无效映射）===
    # 汽车服务下
    {"id": 1011, "name": "智能网联汽车", "parent_id": 102, "level": 4, "sort": 1},
    # 自动化设备下
    {"id": 1113, "name": "工业自动化", "parent_id": 112, "level": 4, "sort": 4},
    # 集成电路设计下
    {"id": 2002, "name": "GPU与ASIC芯片", "parent_id": 200, "level": 4, "sort": 1},
    # 计算机下
    {"id": 210, "name": "服务器与云计算", "parent_id": 21, "level": 3, "sort": 1},
    {"id": 211, "name": "数据服务与要素", "parent_id": 21, "level": 3, "sort": 2},
    {"id": 212, "name": "人工智能软件", "parent_id": 21, "level": 3, "sort": 3},
    {"id": 213, "name": "企业软件与办公", "parent_id": 21, "level": 3, "sort": 4},
    {"id": 214, "name": "系统集成服务", "parent_id": 21, "level": 3, "sort": 5},
    {"id": 2102, "name": "服务器与云计算", "parent_id": 210, "level": 4, "sort": 1},
    {"id": 2103, "name": "数据服务与要素", "parent_id": 211, "level": 4, "sort": 1},
    {"id": 2104, "name": "人工智能软件", "parent_id": 212, "level": 4, "sort": 1},
    {"id": 2105, "name": "企业软件与办公", "parent_id": 213, "level": 4, "sort": 1},
    {"id": 2106, "name": "系统集成服务", "parent_id": 214, "level": 4, "sort": 1},
    # 传媒（信息技术下新增L2）
    {"id": 23, "name": "传媒", "parent_id": 2, "level": 2, "sort": 4},
    {"id": 220, "name": "传媒娱乐", "parent_id": 23, "level": 3, "sort": 1},
    {"id": 2202, "name": "游戏与数字内容", "parent_id": 220, "level": 4, "sort": 1},
    # 医疗器械下
    {"id": 401, "name": "智能医疗", "parent_id": 40, "level": 3, "sort": 1},
    {"id": 4011, "name": "智能医疗装备", "parent_id": 401, "level": 4, "sort": 1},
    {"id": 4012, "name": "医疗信息化", "parent_id": 401, "level": 4, "sort": 2},
]


def expand_industry_tree():
    """Insert new industry tree nodes and remap unmapped stocks."""
    session = get_session()
    try:
        # 1. Insert new nodes
        inserted = 0
        for node in NEW_NODES:
            existing = session.query(IndustryTree).filter_by(id=node["id"]).first()
            if not existing:
                session.add(IndustryTree(**node))
                inserted += 1
        session.commit()
        print(f"Inserted {inserted} new industry tree nodes")

        # 2. Report current leaf count
        leaf_count = session.query(IndustryTree).filter_by(level=4).count()
        print(f"Total level-4 leaf nodes: {leaf_count}")

    except Exception as e:
        session.rollback()
        print(f"Error: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    expand_industry_tree()
