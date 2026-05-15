"""L4 leaf node classifier for stocks mapped to L3 parent nodes.

Uses a hybrid approach:
1. business_desc keyword matching (primary signal)
2. concept_tag keyword matching (secondary signal)
3. industry_raw exact match (tertiary signal)

Unmatched stocks remain at L3 for manual review.
"""

import re
import logging
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

from packages.domain.database import Transaction, get_session
from packages.domain.models import StockIndustryKB, IndustryTree, ConceptTag

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
# L4 Classification Rules
# Format: l3_id -> [rule, ...]
# Each rule: {"l4_id": int, "l4_name": str,
#             "desc_keywords": [str],      # business_desc must contain ANY
#             "concept_keywords": [str],   # concept tag must contain ANY
#             "industry_raw": [str]}       # Tushare industry exact match
# Priority: rules are evaluated in order; first match wins.
# ──────────────────────────────────────────────────────────────

L4_RULES: Dict[int, List[dict]] = {
    # ── 30 食品饮料 ──
    30: [
        {"l4_id": 3000, "l4_name": "白酒", "desc_keywords": ["白酒", "茅台酒", "五粮液", "泸州老窖", "汾酒", "洋河", "酱香", "浓香"], "concept_keywords": ["白酒概念"], "industry_raw": ["白酒"]},
        {"l4_id": 3004, "l4_name": "啤酒", "desc_keywords": ["啤酒", "精酿", "青岛啤酒", "雪花"], "concept_keywords": ["啤酒概念"], "industry_raw": ["啤酒"]},
        {"l4_id": 3007, "l4_name": "红黄酒", "desc_keywords": ["葡萄酒", "红酒", "黄酒", "米酒"], "concept_keywords": [], "industry_raw": ["红黄酒"]},
        {"l4_id": 3002, "l4_name": "乳制品", "desc_keywords": ["乳制品", "奶粉", "酸奶", "牛奶", "伊利", "蒙牛", "奶酪"], "concept_keywords": ["乳业"], "industry_raw": ["乳制品"]},
        {"l4_id": 3003, "l4_name": "调味品", "desc_keywords": ["调味品", "酱油", "醋", "味精", "酱料", "蚝油", "火锅底料"], "concept_keywords": [], "industry_raw": ["调味品"]},
        {"l4_id": 3005, "l4_name": "休闲食品", "desc_keywords": ["零食", "坚果", "糖果", "巧克力", "饼干", "膨化食品", "卤味", "鸭脖", "瓜子"], "concept_keywords": [], "industry_raw": ["休闲食品"]},
        {"l4_id": 3006, "l4_name": "软饮料", "desc_keywords": ["饮料", "果汁", "茶饮料", "功能饮料", "矿泉水", "碳酸饮料"], "concept_keywords": [], "industry_raw": ["软饮料"]},
        {"l4_id": 3001, "l4_name": "食品", "desc_keywords": ["食品", "肉制品", "速冻", "罐头", "粮油", "烘焙"], "concept_keywords": ["食品安全"], "industry_raw": ["食品"]},
    ],

    # ── 31 家用电器 ──
    31: [
        {"l4_id": 3100, "l4_name": "白色家电", "desc_keywords": ["空调", "冰箱", "洗衣机", "冷柜", "压缩机", "格力", "美的", "海尔"], "concept_keywords": ["白色家电"], "industry_raw": ["白色家电", "家用电器"]},
        {"l4_id": 3101, "l4_name": "小家电", "desc_keywords": ["小家电", "电饭煲", "吸尘器", "榨汁机", "微波炉", "电吹风", "扫地机器人"], "concept_keywords": ["小家电概念"], "industry_raw": ["小家电"]},
        {"l4_id": 3102, "l4_name": "厨电", "desc_keywords": ["厨电", "油烟机", "燃气灶", "集成灶", "洗碗机", "消毒柜", "烤箱"], "concept_keywords": ["厨电概念"], "industry_raw": ["厨电"]},
        {"l4_id": 3103, "l4_name": "黑色家电", "desc_keywords": ["电视", "彩电", "显示器", "机顶盒", "音箱", "音响", "投影仪"], "concept_keywords": ["黑色家电"], "industry_raw": ["黑色家电"]},
        {"l4_id": 3104, "l4_name": "智能家居", "desc_keywords": ["智能家居", "智能门锁", "智能照明", "全屋智能", "IoT", "物联网家居"], "concept_keywords": ["智能家居"], "industry_raw": ["智能家居"]},
        {"l4_id": 3105, "l4_name": "电器连锁", "desc_keywords": ["家电零售", "电器连锁", "国美", "苏宁", "家电卖场"], "concept_keywords": [], "industry_raw": ["电器连锁"]},
    ],

    # ── 101 汽车零部件 ──
    101: [
        {"l4_id": 1004, "l4_name": "轮胎轮毂", "desc_keywords": ["轮胎", "轮毂", "子午线", "斜交胎", "汽车轮胎"], "concept_keywords": ["胎压监测", "橡胶"], "industry_raw": ["轮胎"]},
        {"l4_id": 1003, "l4_name": "新能源汽车零部件", "desc_keywords": ["新能源", "电池", "电机", "电控", "充电桩", "锂电", "动力电池", "氢燃料", "燃料电池"], "concept_keywords": ["新能源汽车", "锂电池", "充电桩", "燃料电池"], "industry_raw": []},
        {"l4_id": 1002, "l4_name": "汽车电子", "desc_keywords": ["汽车电子", "车载", "车联网", "智能座舱", "ADAS", "传感器", "电控单元", "ECU", "汽车电器"], "concept_keywords": ["汽车电子", "车联网", "无人驾驶", "智能汽车"], "industry_raw": ["汽车电子", "车联网"]},
        {"l4_id": 1000, "l4_name": "底盘与发动机系统", "desc_keywords": ["底盘", "发动机", "传动", "转向", "悬架", "变速箱", "变速器", "制动", "刹车", "离合器", "曲轴", "连杆", "活塞"], "concept_keywords": ["底盘"], "industry_raw": ["汽车配件", "汽车类"]},
        {"l4_id": 1001, "l4_name": "车身及内外饰", "desc_keywords": ["车身", "保险杠", "内饰", "外饰", "座椅", "车灯", "后视镜", "车门", "仪表板", "玻璃", "密封件"], "concept_keywords": ["汽车零部件"], "industry_raw": []},
    ],

    # ── 102 汽车服务 ──
    102: [
        {"l4_id": 1011, "l4_name": "智能网联汽车", "desc_keywords": ["智能网联", "自动驾驶", "无人驾驶", "车联网", "智能交通", "智慧出行", "共享汽车", "网约车"], "concept_keywords": ["无人驾驶", "车联网", "智能汽车", "共享汽车"], "industry_raw": ["汽车服务", "车联网", "无人驾驶", "智能汽车"]},
    ],

    # ── 110 通用设备 ──
    110: [
        {"l4_id": 1100, "l4_name": "机器人", "desc_keywords": ["机器人", "减速器", "伺服", "人形机器人", "工业机器人", "协作机器人", "机械臂", "谐波减速器", "RV减速器"], "concept_keywords": ["机器人概念", "人形机器人", "减速器", "机器视觉"], "industry_raw": ["机器人", "减速器"]},
        {"l4_id": 1101, "l4_name": "数控机床", "desc_keywords": ["机床", "数控", "磨床", "铣床", "车床", "加工中心", "激光切割", "电火花", "精雕"], "concept_keywords": ["工业母机", "数控机床"], "industry_raw": ["数控机床", "机床制造", "磨具磨料"]},
        {"l4_id": 1102, "l4_name": "工控设备", "desc_keywords": ["工控", "PLC", "变频器", "自动化控制", "工业自动化", "DCS", "伺服系统", "运动控制", "工业以太网"], "concept_keywords": ["工业4.0", "工业互联网", "工控安全"], "industry_raw": ["工控设备", "电气自控", "机械基件"]},
        {"l4_id": 1103, "l4_name": "仪器仪表", "desc_keywords": ["仪器仪表", "电表", "水表", "气表", "测量仪器", "检测设备", "传感器", "压力表", "温度计", "流量计", "校验仪", "热像仪", "光谱仪", "色谱仪", "质谱仪", "显微镜", "光学仪器", "分析仪器"], "concept_keywords": ["仪器仪表", "智能表", "传感器", "物联网应用层"], "industry_raw": ["仪器仪表", "电器仪表"]},
    ],

    # ── 111 专用设备 ──
    111: [
        {"l4_id": 1110, "l4_name": "光伏设备", "desc_keywords": ["光伏", "太阳能电池", "硅片", "组件", "逆变器", "PECVD", "丝网印刷", "电池片", "单晶硅", "多晶硅"], "concept_keywords": ["光伏概念", "HJT电池", "TOPCON电池", "钙钛矿电池"], "industry_raw": ["光伏", "太阳能", "电气设备", "电源设备"]},
        {"l4_id": 1111, "l4_name": "锂电设备", "desc_keywords": ["锂电池", "锂电", "电池设备", "涂布", "卷绕", "化成分容", "隔膜", "电解液", "正负极材料", "电芯"], "concept_keywords": ["锂电池", "固态电池", "钠离子电池"], "industry_raw": ["锂电池", "储能", "电池"]},
        {"l4_id": 1112, "l4_name": "工程机械", "desc_keywords": ["工程机械", "挖掘机", "起重机", "混凝土", "泵车", "装载机", "推土机", "压路机", "盾构机", "塔吊"], "concept_keywords": ["工程机械", "一带一路", "基建"], "industry_raw": ["工程机械", "运输设备", "专用机械", "工业机械"]},
        {"l4_id": 1114, "l4_name": "其他专用设备", "desc_keywords": ["机械", "设备", "制造"], "concept_keywords": [], "industry_raw": ["农用机械", "化工机械", "纺织机械", "轻工机械"]},
    ],

    # ── 112 自动化设备 ──
    112: [
        {"l4_id": 1113, "l4_name": "工业自动化", "desc_keywords": ["工业自动化", "自动化设备", "自动化生产线", "智能装备", "智能制造", "MES", "AGV", "立体仓库", "物流自动化"], "concept_keywords": ["工业4.0", "智能制造", "工业互联网"], "industry_raw": ["工业自动化", "自动化设备", "楼宇设备"]},
    ],

    # ── 120 消费电子 ──
    120: [
        {"l4_id": 1200, "l4_name": "智能手机产业链", "desc_keywords": ["手机", "智能手机", "移动终端", "通讯设备", "基带", "射频", "天线", "摄像头模组", "触控屏", "无线充电"], "concept_keywords": ["消费电子", "苹果概念", "华为概念", "小米概念", "5G"], "industry_raw": ["电子制造", "消费电子", "通信设备"]},
        {"l4_id": 1201, "l4_name": "智能穿戴", "desc_keywords": ["智能手表", "智能手环", "可穿戴", "TWS", "无线耳机", "蓝牙耳机", "VR眼镜", "运动追踪"], "concept_keywords": ["智能穿戴", "无线耳机", "苹果概念"], "industry_raw": ["智能穿戴"]},
        {"l4_id": 1202, "l4_name": "AR/VR", "desc_keywords": ["AR", "VR", "增强现实", "虚拟现实", "混合现实", "MR", "头显", "元宇宙", "空间计算"], "concept_keywords": ["元宇宙", "虚拟现实", "增强现实"], "industry_raw": ["AR/VR", "虚拟现实", "增强现实"]},
    ],

    # ── 121 光学光电子 ──
    121: [
        {"l4_id": 1210, "l4_name": "光模块/CPO", "desc_keywords": ["光模块", "光通信", "CPO", "光纤", "光器件", "光芯片", "光引擎", "硅光", "相干光", "800G", "400G", "光电子晶体", "非线性光学晶体", "激光晶体", "光学晶体"], "concept_keywords": ["CPO概念", "光通信", "5G", "数据中心", "激光"], "industry_raw": ["光学光电子", "光电子", "通信设备", "5G"]},
        {"l4_id": 1211, "l4_name": "LED", "desc_keywords": ["LED", "照明", "Mini LED", "Micro LED", "OLED照明", "背光", "显示屏", "灯珠", "外延片", "节能照明"], "concept_keywords": ["MiniLED", "MicroLED", "节能照明"], "industry_raw": ["LED"]},
        {"l4_id": 1212, "l4_name": "面板", "desc_keywords": ["面板", "LCD", "OLED", "显示", "屏幕", "TFT", "AMOLED", "显示屏", "触控面板", "柔性屏", "折叠屏", "液晶", "显示器", "彩电", "显示器件", "显示终端", "模组", "ITO", "导电玻璃", "液晶显示", "显示模块", "触摸屏", "背光模组"], "concept_keywords": ["OLED", "柔性屏", "折叠屏", "超清视频"], "industry_raw": ["面板", "显示器件", "LCD", "OLED", "元器件"]},
        {"l4_id": 1213, "l4_name": "其他光学电子", "desc_keywords": ["电子", "光学", "元器件", "组件", "器件"], "concept_keywords": ["元器件", "集成电路概念"], "industry_raw": ["电信运营"]},
    ],

    # ── 122 电子元件 (半导体材料) ──
    122: [
        {"l4_id": 1220, "l4_name": "被动元件", "desc_keywords": ["电容", "电阻", "电感", "MLCC", "陶瓷电容", "钽电容", "薄膜电容", "片式元件"], "concept_keywords": ["MLCC", "被动元件"], "industry_raw": ["被动元件", "电子元件"]},
        {"l4_id": 1221, "l4_name": "PCB", "desc_keywords": ["PCB", "印制电路板", "电路板", "HDI", "FPC", "柔性电路板", "覆铜板", "CCL", "IC载板"], "concept_keywords": ["PCB概念", "覆铜板"], "industry_raw": ["PCB", "印制电路板"]},
    ],

    # ── 140 基础化工 ──
    140: [
        {"l4_id": 1405, "l4_name": "聚氨酯", "desc_keywords": ["聚氨酯", "MDI", "TDI", "聚醚", "泡沫", "保温材料", "涂料", "鞋底", "弹性体"], "concept_keywords": ["聚氨酯"], "industry_raw": ["聚氨酯"]},
        {"l4_id": 1406, "l4_name": "有机硅", "desc_keywords": ["有机硅", "硅橡胶", "硅油", "气相白炭黑", "硅树脂", "室温硫化硅橡胶"], "concept_keywords": ["有机硅"], "industry_raw": ["有机硅"]},
        {"l4_id": 1407, "l4_name": "钛白粉", "desc_keywords": ["钛白粉", "二氧化钛", "钛精矿", "硫酸法", "氯化法"], "concept_keywords": ["钛白粉"], "industry_raw": ["钛白粉"]},
        {"l4_id": 1408, "l4_name": "氟化工", "desc_keywords": ["氟化工", "氟化", "制冷剂", "PTFE", "PVDF", "含氟", "氟碳", "氟橡胶"], "concept_keywords": ["氟化工"], "industry_raw": ["氟化工"]},
        {"l4_id": 1409, "l4_name": "氯碱", "desc_keywords": ["氯碱", "烧碱", "PVC", "聚氯乙烯", "盐酸", "液氯", "电石"], "concept_keywords": ["PVC"], "industry_raw": ["氯碱"]},
        {"l4_id": 1410, "l4_name": "煤化工", "desc_keywords": ["煤化工", "煤制", "甲醇", "煤焦油", "合成氨", "尿素", "煤制气", "煤制油"], "concept_keywords": ["煤化工"], "industry_raw": ["煤化工"]},
        {"l4_id": 1401, "l4_name": "农药化肥", "desc_keywords": ["农药", "化肥", "杀虫剂", "除草剂", "杀菌剂", "复合肥", "氮肥", "磷肥", "钾肥", "种子处理"], "concept_keywords": ["农药", "化肥", "草甘膦"], "industry_raw": ["农药化肥"]},
        {"l4_id": 1400, "l4_name": "化工原料", "desc_keywords": ["化工原料", "基础化工", "有机化工", "无机化工", "精细化工", "中间体", "化学试剂"], "concept_keywords": ["化工新材料", "新材料概念"], "industry_raw": ["化工原料"]},
        {"l4_id": 1402, "l4_name": "塑料", "desc_keywords": ["塑料", "改性塑料", "工程塑料", "通用塑料", "塑料粒子", "ABS", "PP", "PE", "PC", "尼龙"], "concept_keywords": ["可降解塑料", "新材料概念"], "industry_raw": ["塑料"]},
        {"l4_id": 1403, "l4_name": "橡胶", "desc_keywords": ["橡胶", "合成橡胶", "天然橡胶", "橡胶制品", "橡胶管", "橡胶密封件", "轮胎用橡胶"], "concept_keywords": ["橡胶"], "industry_raw": ["橡胶"]},
        {"l4_id": 1404, "l4_name": "化纤", "desc_keywords": ["化纤", "化学纤维", "涤纶", "锦纶", "腈纶", "氨纶", "粘胶", "聚酯", "纺丝"], "concept_keywords": ["化纤"], "industry_raw": ["化纤"]},
        {"l4_id": 1411, "l4_name": "染料涂料", "desc_keywords": ["染料", "涂料", "油漆", "油墨", "颜料", "色浆", "建筑涂料", "工业涂料"], "concept_keywords": [], "industry_raw": ["染料涂料"]},
        {"l4_id": 1412, "l4_name": "矿物制品", "desc_keywords": ["矿物", "石墨", "碳素", "炭黑", "耐火", "磨料", "超硬材料", "金刚石", "人造金刚石"], "concept_keywords": ["石墨电极", "金刚石", "超硬材料"], "industry_raw": ["矿物制品"]},
    ],

    # ── 150 钢铁冶炼 ──
    150: [
        {"l4_id": 1500, "l4_name": "普钢", "desc_keywords": ["普钢", "普通钢", "螺纹钢", "线材", "热轧", "冷轧", "中厚板", "棒材", "板材"], "concept_keywords": [], "industry_raw": ["普钢"]},
        {"l4_id": 1501, "l4_name": "特钢", "desc_keywords": ["特钢", "特种钢", "合金钢", "不锈钢", "模具钢", "轴承钢", "齿轮钢", "高温合金", "军工钢"], "concept_keywords": ["军工", "高温合金"], "industry_raw": ["特钢", "特种钢", "不锈钢"]},
        {"l4_id": 1502, "l4_name": "冶钢原料", "desc_keywords": ["铁矿石", "铁精粉", "焦炭", "废钢", "钢坯", "球团", "烧结", "锰矿", "铬矿"], "concept_keywords": [], "industry_raw": ["冶钢原料"]},
        {"l4_id": 1503, "l4_name": "钢加工", "desc_keywords": ["钢管", "钢丝", "钢带", "型钢", "钢结构", "钢丝 rope", "金属制品", "冷弯型钢"], "concept_keywords": [], "industry_raw": ["钢加工"]},
    ],

    # ── 160 有色金属冶炼 ──
    160: [
        {"l4_id": 1603, "l4_name": "黄金", "desc_keywords": ["黄金", "金矿", "贵金属", "金银", "冶炼金", "黄金珠宝"], "concept_keywords": ["黄金概念"], "industry_raw": ["黄金"]},
        {"l4_id": 1604, "l4_name": "稀土", "desc_keywords": ["稀土", "永磁", "钕铁硼", "镨钕", "稀土氧化物", "轻稀土", "重稀土", "磁材"], "concept_keywords": ["稀土永磁", "磁悬浮"], "industry_raw": ["稀土", "磁材"]},
        {"l4_id": 1606, "l4_name": "钴", "desc_keywords": ["钴", "钴矿", "钴粉", "钴盐", "三元材料"], "concept_keywords": ["钴", "小金属概念"], "industry_raw": ["钴"]},
        {"l4_id": 1607, "l4_name": "镍", "desc_keywords": ["镍", "镍矿", "镍铁", "硫酸镍", "红土镍矿", "镍钴"], "concept_keywords": ["镍", "小金属概念"], "industry_raw": ["镍"]},
        {"l4_id": 1608, "l4_name": "铅锌", "desc_keywords": ["铅", "锌", "铅锌", "锌精矿", "铅精矿", "锌锭", "铅锭"], "concept_keywords": ["小金属概念", "锌", "铅锌"], "industry_raw": ["铅锌"]},
        {"l4_id": 1605, "l4_name": "钨", "desc_keywords": ["钨", "钨矿", "钨粉", "硬质合金", "钨丝", "APT"], "concept_keywords": ["钨", "小金属概念"], "industry_raw": ["钨"]},
        {"l4_id": 1600, "l4_name": "铜", "desc_keywords": ["铜", "铜矿", "铜精矿", "铜箔", "电解铜", "铜板带", "铜杆", "铜管"], "concept_keywords": ["铜", "小金属概念"], "industry_raw": ["铜"]},
        {"l4_id": 1601, "l4_name": "铝", "desc_keywords": ["铝", "铝土矿", "氧化铝", "电解铝", "铝箔", "铝板带", "铝型材", "铝合金", "再生铝"], "concept_keywords": ["铝", "小金属概念"], "industry_raw": ["铝"]},
        {"l4_id": 1602, "l4_name": "小金属", "desc_keywords": ["锂", "锑", "锡", "钼", "铟", "锗", "镓", "铋", "钒", "钛", "锆", "铌", "钽", "铍"], "concept_keywords": ["小金属概念", "锂矿"], "industry_raw": ["小金属"]},
        {"l4_id": 1609, "l4_name": "磁材", "desc_keywords": ["磁材", "磁性材料", "永磁", "软磁", "铁氧体", "钕铁硼", "磁粉", "磁芯"], "concept_keywords": ["稀土永磁", "磁性材料"], "industry_raw": ["磁材"]},
        {"l4_id": 1610, "l4_name": "非金属材料", "desc_keywords": ["非金属", "石墨", "炭素", "碳纤维", "碳材料", "碳化硅", "氮化硅", "陶瓷材料"], "concept_keywords": ["碳纤维", "石墨烯"], "industry_raw": ["非金属材料"]},
        {"l4_id": 1611, "l4_name": "金属新材料", "desc_keywords": ["金属新材料", "高温合金", "钛合金", "镍基合金", "超导材料", "形状记忆合金", "粉末冶金"], "concept_keywords": ["超导", "高温合金", "钛合金"], "industry_raw": ["金属新材料"]},
    ],

    # ── 170 建材 ──
    170: [
        {"l4_id": 1700, "l4_name": "水泥", "desc_keywords": ["水泥", "熟料", "水泥制品", "混凝土", "商混", "水泥熟料"], "concept_keywords": ["水泥"], "industry_raw": ["水泥"]},
        {"l4_id": 1701, "l4_name": "玻璃", "desc_keywords": ["玻璃", "浮法玻璃", "光伏玻璃", "电子玻璃", "汽车玻璃", "玻璃原片", "节能玻璃"], "concept_keywords": ["玻璃", "光伏玻璃"], "industry_raw": ["玻璃"]},
        {"l4_id": 1702, "l4_name": "陶瓷", "desc_keywords": ["陶瓷", "瓷砖", "卫生陶瓷", "建筑陶瓷", "日用陶瓷", "特种陶瓷", "电子陶瓷"], "concept_keywords": ["陶瓷"], "industry_raw": ["陶瓷"]},
        {"l4_id": 1703, "l4_name": "其他建材", "desc_keywords": ["建材", "石膏板", "管材", "型材", "门窗", "新型建材", "保温材料", "防水材料", "耐火材料"], "concept_keywords": ["建材", "装配式建筑"], "industry_raw": ["其他建材", "耐火材料", "管材", "防水材料"]},
    ],

    # ── 180 综合类 ──
    180: [
        {"l4_id": 1800, "l4_name": "综合类", "desc_keywords": [], "concept_keywords": [], "industry_raw": ["综合类"]},
    ],

    # ── 200 集成电路设计 ──
    200: [
        {"l4_id": 2002, "l4_name": "GPU与ASIC芯片", "desc_keywords": ["GPU", "ASIC", "芯片设计", "集成电路", "AI芯片", "NPU", "SoC", "处理器", "芯片", "半导体设计", "FPGA", "CIS", "图像传感器", "射频芯片", "功率半导体", "模拟芯片", "数字芯片", "MCU", "微控制器", "存储芯片"], "concept_keywords": ["芯片概念", "集成电路", "国产替代", "AI芯片", "GPU", "存储芯片"], "industry_raw": ["半导体", "集成电路", "芯片"]},
    ],

    # ── 201 半导体设备 ──
    201: [
        {"l4_id": 2010, "l4_name": "刻蚀设备", "desc_keywords": ["刻蚀", "蚀刻", "干法刻蚀", "湿法刻蚀", "等离子刻蚀", "反应离子刻蚀"], "concept_keywords": ["半导体设备", "刻蚀设备"], "industry_raw": ["半导体设备"]},
        {"l4_id": 2011, "l4_name": "薄膜沉积", "desc_keywords": ["薄膜沉积", "CVD", "PVD", "ALD", "化学气相沉积", "物理气相沉积", "原子层沉积", "溅射"], "concept_keywords": ["半导体设备", "薄膜沉积"], "industry_raw": ["半导体设备"]},
        {"l4_id": 2012, "l4_name": "量检测设备", "desc_keywords": ["检测", "量测", "检测设备", "光学检测", "电子束检测", "缺陷检测", "膜厚测量", "线宽测量", "SEM", "AOI"], "concept_keywords": ["半导体设备", "检测设备"], "industry_raw": ["半导体设备"]},
    ],

    # ── 202 半导体材料 ──
    202: [
        {"l4_id": 2020, "l4_name": "半导体材料", "desc_keywords": ["硅片", "光刻胶", "电子特气", "CMP材料", "靶材", "封装材料", "引线框架", "基板", "晶圆", "抛光液", "清洗液"], "concept_keywords": ["光刻胶", "半导体材料", "大硅片", "电子特气"], "industry_raw": ["半导体材料"]},
    ],

    # ── 210 服务器与云计算 ──
    210: [
        {"l4_id": 2102, "l4_name": "服务器与云计算", "desc_keywords": ["服务器", "云计算", "数据中心", "IDC", "云存储", "IaaS", "PaaS", "SaaS", "私有云", "公有云", "边缘计算", "超算"], "concept_keywords": ["云计算", "数据中心", "东数西算", "边缘计算"], "industry_raw": ["IT设备", "计算机设备", "服务器", "云计算"]},
    ],

    # ── 211 数据服务与要素 ──
    211: [
        {"l4_id": 2103, "l4_name": "数据服务与要素", "desc_keywords": ["数据", "大数据", "数据分析", "数据服务", "数据要素", "数据交易", "数据治理", "数据安全", "数据中台", "数字孪生", "智慧城市"], "concept_keywords": ["大数据", "数据要素", "数字经济", "智慧城市"], "industry_raw": ["互联网", "大数据", "数据服务"]},
    ],

    # ── 212 人工智能软件 ──
    212: [
        {"l4_id": 2104, "l4_name": "人工智能软件", "desc_keywords": ["人工智能", "AI", "机器学习", "深度学习", "自然语言处理", "NLP", "计算机视觉", "CV", "语音识别", "大模型", "算法", "智能驾驶", "智能安防"], "concept_keywords": ["人工智能", "ChatGPT", "AIGC", "大模型", "机器视觉", "智能驾驶"], "industry_raw": ["人工智能", "AI", "软件服务", "软件开发"]},
    ],

    # ── 213 企业软件与办公 ──
    213: [
        {"l4_id": 2105, "l4_name": "企业软件与办公", "desc_keywords": ["软件", "ERP", "CRM", "OA", "办公软件", "协同办公", "财务软件", "SaaS", "企业管理", "人力资源", "HRM", "供应链管理", "SCM"], "concept_keywords": ["信创", "SaaS", "国产软件", "云办公"], "industry_raw": ["信创", "办公软件", "企业软件", "SaaS"]},
    ],

    # ── 214 系统集成服务 ──
    214: [
        {"l4_id": 2106, "l4_name": "系统集成服务", "desc_keywords": ["系统集成", "IT服务", "运维", "网络安全", "信息安全", "安防", "监控", "智能建筑", "弱电", "综合布线", "数据中心建设"], "concept_keywords": ["网络安全", "信创", "智慧城市", "安防"], "industry_raw": ["IT服务", "系统集成", "网络安全", "安防服务"]},
    ],

    # ── 220 传媒娱乐 ──
    220: [
        {"l4_id": 2202, "l4_name": "游戏与数字内容", "desc_keywords": ["游戏", "网络游戏", "手游", "电竞", "动漫", "影视", "视频", "直播", "短视频", "长视频", "数字内容", "IP", "网络文学", "音乐", "出版", "广告", "营销", "MCN"], "concept_keywords": ["网络游戏", "手游", "电竞", "元宇宙", "短剧", "抖音", "快手"], "industry_raw": ["传媒娱乐", "游戏", "网络游戏", "手游", "影视音像", "广告包装", "元宇宙", "数字内容", "出版业", "文教休闲"]},
    ],

    # ── 320 纺织服装 ──
    320: [
        {"l4_id": 3200, "l4_name": "纺织", "desc_keywords": ["纺织", "纱线", "面料", "坯布", "印染", "织造", "化纤织造", "棉纺", "毛纺", "丝绸", "无纺布"], "concept_keywords": ["纺织"], "industry_raw": ["纺织"]},
        {"l4_id": 3201, "l4_name": "服饰", "desc_keywords": ["服装", "服饰", "男装", "女装", "童装", "运动服", "休闲服", "正装", "品牌服装", "成衣"], "concept_keywords": ["纺织服装", "体育"], "industry_raw": ["服饰", "鞋帽"]},
        {"l4_id": 3202, "l4_name": "家纺", "desc_keywords": ["家纺", "床上用品", "窗帘", "毛巾", "浴巾", "地毯", "家居纺织品"], "concept_keywords": ["家纺"], "industry_raw": ["家纺"]},
        {"l4_id": 3203, "l4_name": "鞋帽", "desc_keywords": ["鞋", "帽", "运动鞋", "皮鞋", "童鞋", "箱包", "皮具", "皮革"], "concept_keywords": ["鞋帽"], "industry_raw": ["鞋帽"]},
    ],

    # ── 330 商业贸易 ──
    330: [
        {"l4_id": 3302, "l4_name": "电商", "desc_keywords": ["电商", "电子商务", "网购", "B2B", "B2C", "C2C", "跨境电商", "平台电商", "直播电商", "社交电商"], "concept_keywords": ["电子商务", "跨境电商", "直播带货"], "industry_raw": ["电商", "跨境电商"]},
        {"l4_id": 3305, "l4_name": "免税", "desc_keywords": ["免税", "离岛免税", "口岸免税", "市内免税", "免税商品", "DFS"], "concept_keywords": ["免税店", "海南自贸区"], "industry_raw": ["免税"]},
        {"l4_id": 3306, "l4_name": "珠宝首饰", "desc_keywords": ["珠宝", "首饰", "黄金饰品", "钻石", "翡翠", "玉石", "银饰", "钟表"], "concept_keywords": ["黄金概念", "珠宝"], "industry_raw": ["珠宝首饰"]},
        {"l4_id": 3300, "l4_name": "百货", "desc_keywords": ["百货", "商场", "购物中心", "综合零售", "商业零售"], "concept_keywords": ["新零售", "百货"], "industry_raw": ["百货"]},
        {"l4_id": 3301, "l4_name": "超市", "desc_keywords": ["超市", "连锁超市", "大卖场", "便利店", "生鲜超市", "仓储超市", "会员店"], "concept_keywords": ["新零售", "社区团购"], "industry_raw": ["超市", "超市连锁"]},
        {"l4_id": 3303, "l4_name": "专业连锁", "desc_keywords": ["连锁", "专业连锁", "家电连锁", "药房连锁", "眼镜连锁", "母婴连锁", "文具连锁"], "concept_keywords": ["连锁"], "industry_raw": ["专业连锁"]},
        {"l4_id": 3307, "l4_name": "商品城", "desc_keywords": ["商品城", "批发市场", "专业市场", "商贸城", "小商品城"], "concept_keywords": [], "industry_raw": ["商品城"]},
        {"l4_id": 3308, "l4_name": "商贸代理", "desc_keywords": ["代理", "贸易", "进出口", "外贸", "经销", "分销", "供应链"], "concept_keywords": ["外贸", "进出口"], "industry_raw": ["商贸代理", "批发业"]},
        {"l4_id": 3309, "l4_name": "批发业", "desc_keywords": ["批发", "大宗商品", "贸易", "经销", "分销"], "concept_keywords": [], "industry_raw": ["批发业"]},
        {"l4_id": 3310, "l4_name": "其他商业", "desc_keywords": ["商业", "零售", "服务", "咨询", "租赁"], "concept_keywords": [], "industry_raw": ["其他商业"]},
    ],

    # ── 340 旅游酒店 ──
    340: [
        {"l4_id": 3401, "l4_name": "酒店餐饮", "desc_keywords": ["酒店", "餐饮", "饭店", "度假村", "快捷酒店", "星级酒店", "连锁酒店", "民宿", "餐饮连锁", "火锅", "快餐"], "concept_keywords": ["酒店", "餐饮", "旅游酒店"], "industry_raw": ["酒店餐饮", "旅游"]},
        {"l4_id": 3400, "l4_name": "旅游", "desc_keywords": ["旅游", "旅行社", "景区", "度假区", "出境游", "入境游", "国内游", "OTA", "在线旅游"], "concept_keywords": ["旅游", "在线旅游"], "industry_raw": ["旅游", "旅游景点", "旅游服务"]},
        {"l4_id": 3402, "l4_name": "教育", "desc_keywords": ["教育", "培训", "K12", "职业教育", "在线教育", "早教", "留学", "民办学校", "教育信息化"], "concept_keywords": ["在线教育", "职业教育"], "industry_raw": ["教育"]},
        {"l4_id": 3403, "l4_name": "体育", "desc_keywords": ["体育", "运动", "健身", "赛事", "体育用品", "体育场馆", "电竞", "彩票"], "concept_keywords": ["体育", "电竞", "彩票"], "industry_raw": ["体育"]},
        {"l4_id": 3404, "l4_name": "旅游景点", "desc_keywords": ["景点", "景区", "主题公园", "游乐园", "动物园", "植物园", "博物馆", "世界遗产", "自然保护"], "concept_keywords": ["旅游", "主题公园"], "industry_raw": ["旅游景点"]},
        {"l4_id": 3405, "l4_name": "旅游服务", "desc_keywords": ["旅游服务", "旅行社", "导游", "旅游交通", "旅游咨询", "旅游规划", "会展", "会议服务"], "concept_keywords": ["旅游", "会展"], "industry_raw": ["旅游服务"]},
    ],

    # ── 350 美容个护 ──
    350: [
        {"l4_id": 3500, "l4_name": "化妆品", "desc_keywords": ["化妆品", "护肤品", "彩妆", "面膜", "洗发水", "沐浴露", "香水", "美妆", "日化"], "concept_keywords": ["化妆品", "医美概念"], "industry_raw": ["化妆品"]},
        {"l4_id": 3501, "l4_name": "个人护理", "desc_keywords": ["个人护理", "口腔护理", "卫生巾", "纸尿裤", "护理用品", "湿巾", "纸巾", "卫生用品"], "concept_keywords": [], "industry_raw": ["个人护理"]},
        {"l4_id": 3502, "l4_name": "日用化工", "desc_keywords": ["日用化工", "洗涤剂", "肥皂", "清洁剂", "消毒", "化工日用品"], "concept_keywords": [], "industry_raw": ["日用化工"]},
    ],

    # ── 360 农业 ──
    360: [
        {"l4_id": 3600, "l4_name": "种植业", "desc_keywords": ["种植", "农作物", "粮食", "蔬菜", "水果", "棉花", "糖料", "花卉", "中药材", "育种", "种子"], "concept_keywords": ["农业种植", "转基因", "乡村振兴"], "industry_raw": ["种植业"]},
        {"l4_id": 3601, "l4_name": "畜牧业", "desc_keywords": ["畜牧", "养殖", "猪", "鸡", "牛", "羊", "禽", "畜", "饲料", "兽药", "疫苗", "肉制品加工"], "concept_keywords": ["猪肉", "养鸡", "养殖", "饲料"], "industry_raw": ["畜牧业", "饲料"]},
        {"l4_id": 3602, "l4_name": "渔业", "desc_keywords": ["渔业", "水产", "养殖", "捕捞", "海鲜", "鱼苗", "虾", "蟹", "贝", "海参"], "concept_keywords": ["水产养殖"], "industry_raw": ["渔业"]},
        {"l4_id": 3603, "l4_name": "林业", "desc_keywords": ["林业", "木材", "森林", "造林", "林产品", "人造板", "木地板", "家具木材"], "concept_keywords": ["林业", "碳中和"], "industry_raw": ["林业"]},
        {"l4_id": 3604, "l4_name": "饲料", "desc_keywords": ["饲料", "饲料加工", "预混料", "浓缩料", "配合饲料", "水产饲料", "畜禽饲料"], "concept_keywords": ["饲料"], "industry_raw": ["饲料"]},
        {"l4_id": 3605, "l4_name": "农业综合", "desc_keywords": ["农业", "综合", "农", "牧", "渔", "多元化农业", "农业服务", "农机"], "concept_keywords": ["农业", "乡村振兴", "农机"], "industry_raw": ["农业综合"]},
    ],

    # ── 370 轻工 ──
    370: [
        {"l4_id": 3700, "l4_name": "造纸", "desc_keywords": ["造纸", "纸浆", "纸张", "纸板", "纸箱", "瓦楞纸", "文化纸", "包装纸", "生活用纸", "特种纸", "废纸回收"], "concept_keywords": ["造纸", "造纸印刷"], "industry_raw": ["造纸"]},
        {"l4_id": 3701, "l4_name": "家居用品", "desc_keywords": ["家居", "家纺", "日用品", "厨房用品", "收纳", "清洁用品", "塑料制品", "陶瓷制品"], "concept_keywords": ["智能家居", "家居用品"], "industry_raw": ["家居用品"]},
        {"l4_id": 3702, "l4_name": "家具", "desc_keywords": ["家具", "办公家具", "民用家具", "定制家具", "软体家具", "实木家具", "板式家具", "橱柜", "衣柜", "沙发", "床垫"], "concept_keywords": ["家具", "定制家居"], "industry_raw": ["家具"]},
        {"l4_id": 3703, "l4_name": "包装印刷", "desc_keywords": ["包装", "印刷", "彩盒", "标签", "烟标", "酒标", "软包装", "硬包装", "印刷电路"], "concept_keywords": ["包装印刷", "烟标"], "industry_raw": ["包装印刷"]},
        {"l4_id": 3704, "l4_name": "文具", "desc_keywords": ["文具", "办公用品", "书写工具", "纸品", "本册", "学生用品", "美术用品"], "concept_keywords": [], "industry_raw": ["文具"]},
        {"l4_id": 3705, "l4_name": "卫浴", "desc_keywords": ["卫浴", "洁具", "水龙头", "淋浴", "马桶", "浴室柜", "五金", "陶瓷卫浴"], "concept_keywords": [], "industry_raw": ["卫浴"]},
    ],

    # ── 401 智能医疗 ──
    401: [
        {"l4_id": 4011, "l4_name": "智能医疗装备", "desc_keywords": ["医疗器械", "医疗设备", "诊断设备", "影像设备", "CT", "MRI", "超声", "内窥镜", "手术机器人", "康复设备", "体外诊断", "IVD", "试剂", "耗材", "高值耗材", "低值耗材", "制药", "药品", "生物制药", "化学药", "中药", "中成药", "创新药", "仿制药", "疫苗", "血制品", "CXO", "CRO", "CDMO", "CMO", "原料药", "制剂"], "concept_keywords": ["医疗器械", "创新药", "生物疫苗", "CXO", "CRO", "新冠检测"], "industry_raw": ["医药", "生物制药", "化学制药", "中成药", "中药", "医疗保健", "医疗器械", "医药商业", "医疗服务", "医美", "创新药", "CXO", "疫苗", "血制品"]},
        {"l4_id": 4012, "l4_name": "医疗信息化", "desc_keywords": ["医疗信息化", "智慧医疗", "HIS", "电子病历", "远程医疗", "互联网医疗", "医保", "医疗大数据", "AI医疗", "医学影像AI"], "concept_keywords": ["智慧医疗", "互联网医疗", "医疗信息化", "DRG/DIP"], "industry_raw": ["医疗信息化", "智慧医疗"]},
    ],

    # ── 500 银行业 ──
    500: [
        {"l4_id": 5000, "l4_name": "银行", "desc_keywords": ["银行", "商业银行", "零售银行", "公司银行", "投资银行", "信用卡", "理财", "资产管理"], "concept_keywords": ["银行"], "industry_raw": ["银行"]},
    ],

    # ── 510 证券业 ──
    510: [
        {"l4_id": 5001, "l4_name": "证券", "desc_keywords": ["证券", "券商", "经纪", "投行", "自营", "资管", "研究", "融资融券"], "concept_keywords": ["证券", "券商"], "industry_raw": ["证券"]},
    ],

    # ── 520 保险业 ──
    520: [
        {"l4_id": 5002, "l4_name": "保险", "desc_keywords": ["保险", "寿险", "财险", "健康险", "养老保险", "再保险", "保险经纪", "保险代理"], "concept_keywords": ["保险", "养老"], "industry_raw": ["保险"]},
    ],

    # ── 530 非银金融 ──
    530: [
        {"l4_id": 5003, "l4_name": "信托", "desc_keywords": ["信托", "信托公司", "家族信托", "慈善信托", "信托计划"], "concept_keywords": ["信托"], "industry_raw": ["信托"]},
        {"l4_id": 5004, "l4_name": "期货", "desc_keywords": ["期货", "期货经纪", "商品期货", "金融期货", "衍生品", "风险管理"], "concept_keywords": ["期货"], "industry_raw": ["期货"]},
        {"l4_id": 5005, "l4_name": "创投", "desc_keywords": ["创投", "风险投资", "VC", "PE", "私募股权", "天使投资", "孵化器", "新三板"], "concept_keywords": ["创投", "新三板", "北交所"], "industry_raw": ["创投"]},
        {"l4_id": 5006, "l4_name": "多元金融", "desc_keywords": ["金融", "租赁", "融资租赁", "金融租赁", "担保", "典当", "小贷", "消费金融", "供应链金融", "支付", "金融科技"], "concept_keywords": ["金融科技", "供应链金融", "支付"], "industry_raw": ["多元金融"]},
    ],

    # ── 540 房地产开发 ──
    540: [
        {"l4_id": 5404, "l4_name": "全国地产", "desc_keywords": ["房地产", "地产开发", "住宅", "商品房", "全国布局", "大型房企", "万科", "保利", "碧桂园", "恒大"], "concept_keywords": ["房地产", "住房租赁"], "industry_raw": ["房地产开发", "全国地产"]},
        {"l4_id": 5405, "l4_name": "区域地产", "desc_keywords": ["地产", "区域", "地方房企", "省内", "本市", "区域性", "中小房企"], "concept_keywords": ["房地产", "地方国资改革"], "industry_raw": ["区域地产", "房地产开发"]},
        {"l4_id": 5401, "l4_name": "物业管理", "desc_keywords": ["物业", "物业管理", "物业服务", "社区服务", "保洁", "保安", "绿化", "维修", "物业收费"], "concept_keywords": ["物业管理", "社区团购"], "industry_raw": ["物业管理"]},
        {"l4_id": 5402, "l4_name": "园区开发", "desc_keywords": ["园区", "开发区", "高新区", "产业园", "科技园", "工业园", "经开区", "保税区", "物流园"], "concept_keywords": ["园区开发", "自贸区"], "industry_raw": ["园区开发"]},
        {"l4_id": 5403, "l4_name": "房产服务", "desc_keywords": ["房产", "中介", "经纪", "代理", "销售", "租赁", "二手房", "房产咨询", "评估", "拍卖"], "concept_keywords": ["房地产", "租售同权"], "industry_raw": ["房产服务"]},
    ],

    # ── 550 建筑工程 ──
    550: [
        {"l4_id": 5500, "l4_name": "建筑工程", "desc_keywords": ["建筑", "房建", "施工", "总承包", "建筑施工", "土建", "钢结构", "装配式建筑", "幕墙", "装饰", "装修", "土木工程"], "concept_keywords": ["装配式建筑", "基建", "一带一路"], "industry_raw": ["建筑工程", "装修装饰"]},
        {"l4_id": 5501, "l4_name": "基础建设", "desc_keywords": ["基建", "道路", "桥梁", "隧道", "铁路", "地铁", "轨道交通", "市政", "水利", "港口", "机场", "公路", "高速公路"], "concept_keywords": ["基建", "一带一路", "高铁", "轨道交通"], "industry_raw": ["基础建设", "专业工程"]},
        {"l4_id": 5502, "l4_name": "专业工程", "desc_keywords": ["专业工程", "石油化工工程", "电力工程", "冶金工程", "矿山工程", "环保工程", "园林工程", "消防工程", "智能化工程"], "concept_keywords": ["专业工程", "环保工程"], "industry_raw": ["专业工程"]},
        {"l4_id": 5503, "l4_name": "装修装饰", "desc_keywords": ["装修", "装饰", "家装", "公装", "室内设计", "软装", "精装", "全装修", "幕墙", "门窗"], "concept_keywords": ["装配式建筑", "精装修"], "industry_raw": ["装修装饰"]},
    ],

    # ── 560 建材 ──
    560: [
        {"l4_id": 5600, "l4_name": "水泥", "desc_keywords": ["水泥", "熟料", "混凝土", "商混", "水泥制品", "水泥熟料"], "concept_keywords": ["水泥"], "industry_raw": ["水泥"]},
        {"l4_id": 5601, "l4_name": "玻璃", "desc_keywords": ["玻璃", "浮法玻璃", "光伏玻璃", "电子玻璃", "汽车玻璃"], "concept_keywords": ["玻璃", "光伏玻璃"], "industry_raw": ["玻璃"]},
        {"l4_id": 5602, "l4_name": "陶瓷", "desc_keywords": ["陶瓷", "瓷砖", "卫生陶瓷", "建筑陶瓷", "日用陶瓷", "特种陶瓷"], "concept_keywords": ["陶瓷"], "industry_raw": ["陶瓷"]},
        {"l4_id": 5603, "l4_name": "耐火材料", "desc_keywords": ["耐火", "耐火材料", "耐火砖", "浇注料", "镁碳砖", "高铝砖", "硅砖", "保温材料"], "concept_keywords": ["耐火材料"], "industry_raw": ["耐火材料"]},
        {"l4_id": 5604, "l4_name": "管材", "desc_keywords": ["管材", "管道", "塑料管", "钢管", "PE管", "PVC管", "排水管", "给水管", "燃气管"], "concept_keywords": [], "industry_raw": ["管材"]},
        {"l4_id": 5605, "l4_name": "防水材料", "desc_keywords": ["防水", "防水材料", "防水卷材", "防水涂料", "密封材料", "堵漏"], "concept_keywords": ["防水材料"], "industry_raw": ["防水材料"]},
        {"l4_id": 5606, "l4_name": "其他建材", "desc_keywords": ["建材", "石膏板", "型材", "门窗", "五金", "新型建材", "保温材料", "装饰材料", "地板", "墙纸"], "concept_keywords": ["建材", "装配式建筑"], "industry_raw": ["其他建材"]},
    ],

    # ── 600 煤炭开采 ──
    600: [
        {"l4_id": 6000, "l4_name": "煤炭开采", "desc_keywords": ["煤炭", "煤矿", "采煤", "动力煤", "焦煤", "无烟煤", "褐煤", "原煤", "洗煤"], "concept_keywords": ["煤炭", "动力煤"], "industry_raw": ["煤炭开采"]},
        {"l4_id": 6001, "l4_name": "焦炭加工", "desc_keywords": ["焦炭", "焦化", "焦炉", "煤化工", "煤焦油", "粗苯", "煤气"], "concept_keywords": ["焦炭", "煤化工"], "industry_raw": ["焦炭加工"]},
    ],

    # ── 610 石油化工 ──
    610: [
        {"l4_id": 6100, "l4_name": "石油开采", "desc_keywords": ["石油", "原油", "油气", "油田", "钻井", "采油", "勘探", "油井", "页岩油"], "concept_keywords": ["油气", "页岩气", "可燃冰"], "industry_raw": ["石油开采"]},
        {"l4_id": 6101, "l4_name": "石油加工", "desc_keywords": ["炼油", "石化", "石油化工", "乙烯", "丙烯", "芳烃", "PTA", "PX", "成品油", "汽油", "柴油", "煤油", "沥青", "润滑油"], "concept_keywords": ["石化", "油改"], "industry_raw": ["石油加工", "石油贸易"]},
        {"l4_id": 6102, "l4_name": "石油贸易", "desc_keywords": ["石油贸易", "油品贸易", "燃料油", "原油贸易", "成品油贸易", "油品销售", "加油站", "油库"], "concept_keywords": ["油品升级", "加油站"], "industry_raw": ["石油贸易"]},
        {"l4_id": 6103, "l4_name": "天然气", "desc_keywords": ["天然气", "LNG", "CNG", "页岩气", "煤层气", "天然气管道", "储气", "城燃"], "concept_keywords": ["天然气", "页岩气", "可燃冰"], "industry_raw": ["天然气"]},
        {"l4_id": 6104, "l4_name": "油服工程", "desc_keywords": ["油服", "油田服务", "钻井服务", "测井", "录井", "固井", "压裂", "完井", "海上油服", "物探"], "concept_keywords": ["油服", "页岩气"], "industry_raw": ["油服工程"]},
    ],

    # ── 620 电力生产 ──
    620: [
        {"l4_id": 6201, "l4_name": "水电", "desc_keywords": ["水电", "水利发电", "水电站", "水力", "抽水蓄能", "水电厂"], "concept_keywords": ["水电", "抽水蓄能"], "industry_raw": ["水电", "水力发电"]},
        {"l4_id": 6202, "l4_name": "风电", "desc_keywords": ["风电", "风力发电", "风机", "风电场", "陆上风电", "海上风电", "风电机组"], "concept_keywords": ["风电", "海上风电"], "industry_raw": ["风电", "风电设备"]},
        {"l4_id": 6203, "l4_name": "核电", "desc_keywords": ["核电", "核电站", "核反应堆", "核燃料", "核岛", "常规岛", "核电机组"], "concept_keywords": ["核电", "核废料处理"], "industry_raw": ["核电"]},
        {"l4_id": 6204, "l4_name": "光伏", "desc_keywords": ["光伏", "太阳能", "光伏发电", "光伏电站", "分布式光伏", "集中式光伏", "光伏组件"], "concept_keywords": ["光伏", "BIPV", "HJT电池"], "industry_raw": ["光伏", "太阳能"]},
        {"l4_id": 6205, "l4_name": "储能", "desc_keywords": ["储能", "电化学储能", "抽水蓄能", "压缩空气储能", "飞轮储能", "储能电池", "储能系统", "储能电站"], "concept_keywords": ["储能", "钠离子电池", "固态电池"], "industry_raw": ["储能"]},
        {"l4_id": 6200, "l4_name": "火电", "desc_keywords": ["火电", "燃煤", "燃气发电", "热电", "生物质发电", "垃圾发电", "余热发电", "燃煤电厂"], "concept_keywords": ["火电", "生物质能", "垃圾发电"], "industry_raw": ["火电", "火力发电"]},
        {"l4_id": 6206, "l4_name": "新型电力", "desc_keywords": ["新型电力", "虚拟电厂", "智能电网", "微电网", "综合能源", "源网荷储", "电力交易", "绿电", "清洁能源"], "concept_keywords": ["智能电网", "虚拟电厂", "绿电"], "industry_raw": ["新型电力"]},
    ],

    # ── 700 环境保护 ──
    700: [
        {"l4_id": 7001, "l4_name": "固废处理", "desc_keywords": ["固废", "垃圾", "焚烧", "填埋", "危废", "污泥", "餐厨垃圾", "建筑垃圾", "再生资源", "回收", "废品回收"], "concept_keywords": ["固废处理", "垃圾分类", "再生资源", "医废处理"], "industry_raw": ["固废处理", "环境保护"]},
        {"l4_id": 7002, "l4_name": "污水处理", "desc_keywords": ["污水", "水处理", "废水", "给排水", "再生水", "中水回用", "膜技术", "反渗透", "MBR", "净水", "自来水"], "concept_keywords": ["污水处理", "膜技术", "净水"], "industry_raw": ["污水处理", "水务"]},
        {"l4_id": 7003, "l4_name": "大气治理", "desc_keywords": ["大气", "烟气", "脱硫", "脱硝", "除尘", "VOCs", "废气", "空气净化", "尾气处理", "碳捕集"], "concept_keywords": ["大气治理", "碳捕集", "脱硫脱硝"], "industry_raw": ["大气治理", "环境保护"]},
        {"l4_id": 7000, "l4_name": "环境保护", "desc_keywords": ["环保", "环境", "生态修复", "土壤修复", "环境监测", "环评", "环保工程", "噪声治理", "辐射防护"], "concept_keywords": ["环保", "碳中和", "土壤修复"], "industry_raw": ["环境保护"]},
    ],

    # ── 710 水务 ──
    710: [
        {"l4_id": 7100, "l4_name": "水务", "desc_keywords": ["水务", "供水", "排水", "污水处理", "自来水", "水厂", "管网", "水资源", "节水"], "concept_keywords": ["水务", "节水"], "industry_raw": ["水务"]},
    ],

    # ── 720 燃气 ──
    720: [
        {"l4_id": 7200, "l4_name": "燃气", "desc_keywords": ["燃气", "天然气", "煤气", "液化气", "城市燃气", "燃气管道", "储气", "加气站", "LNG", "CNG"], "concept_keywords": ["天然气", "燃气"], "industry_raw": ["燃气", "天然气"]},
        {"l4_id": 7201, "l4_name": "供热", "desc_keywords": ["供热", "供暖", "热力", "热电联产", "集中供热", "余热", "锅炉", "换热站", "暖气"], "concept_keywords": ["供热", "热电联产"], "industry_raw": ["供热", "供气供热"]},
    ],

    # ── 730 交运物流 ──
    730: [
        {"l4_id": 7302, "l4_name": "港口", "desc_keywords": ["港口", "码头", "集装箱", "航运", "海港", "河港", "散货", "油港", "邮轮母港"], "concept_keywords": ["港口", "航运", "一带一路"], "industry_raw": ["港口"]},
        {"l4_id": 7303, "l4_name": "航空", "desc_keywords": ["航空", "机场", "民航", "航班", "客货运", "航空公司", "通航", "低空经济", "无人机物流"], "concept_keywords": ["航空", "机场", "低空经济", "无人机"], "industry_raw": ["航空", "机场"]},
        {"l4_id": 7304, "l4_name": "铁路", "desc_keywords": ["铁路", "高铁", "轨道交通", "铁路运输", "机车", "车辆", "轨道", "地铁", "城轨", "动车"], "concept_keywords": ["高铁", "轨道交通", "铁路基建"], "industry_raw": ["铁路"]},
        {"l4_id": 7305, "l4_name": "公路", "desc_keywords": ["公路", "高速公路", "道路运输", "客运", "货运", "物流运输", " trucking", "冷链物流", "快递", "快运"], "concept_keywords": ["高速公路", "快递", "冷链物流"], "industry_raw": ["公路"]},
        {"l4_id": 7306, "l4_name": "航运", "desc_keywords": ["航运", "海运", "远洋", "内河航运", "船舶运输", "油轮", "散货船", "集装箱船", "LNG船", "邮轮"], "concept_keywords": ["航运", "油轮", "LNG运输"], "industry_raw": ["航运", "船舶"]},
        {"l4_id": 7300, "l4_name": "物流", "desc_keywords": ["物流", "仓储", "供应链", "第三方物流", "快递", "快运", "冷链", "危险品物流", "医药物流", "电商物流", "跨境物流"], "concept_keywords": ["物流", "快递", "跨境电商", "冷链物流"], "industry_raw": ["物流", "仓储物流"]},
        {"l4_id": 7301, "l4_name": "仓储", "desc_keywords": ["仓储", "仓库", "冷库", "保税仓", "物流中心", "配送中心", "智能仓储", "自动化立体库"], "concept_keywords": ["智慧物流", "智能仓储"], "industry_raw": ["仓储"]},
        {"l4_id": 7307, "l4_name": "公交", "desc_keywords": ["公交", "公共汽车", "城市公交", " BRT", "客运", "出租车", "网约车"], "concept_keywords": [], "industry_raw": ["公交"]},
        {"l4_id": 7313, "l4_name": "摩托车", "desc_keywords": ["摩托车", "机车", "两轮车", "电动车", "踏板车", "越野摩托车"], "concept_keywords": ["摩托车", "两轮车"], "industry_raw": ["摩托车"]},
        {"l4_id": 7308, "l4_name": "机场", "desc_keywords": ["机场", "空港", "航站楼", "飞行区", "机场运营", "机场服务", "地勤"], "concept_keywords": ["机场", "航空"], "industry_raw": ["机场"]},
        {"l4_id": 7309, "l4_name": "空运", "desc_keywords": ["空运", "航空货运", "航空物流", "货机", "航空快递", "国际空运"], "concept_keywords": ["航空", "空运"], "industry_raw": ["空运"]},
        {"l4_id": 7310, "l4_name": "水运", "desc_keywords": ["水运", "内河运输", "沿海运输", "渡轮", "客船", "游船", "轮渡"], "concept_keywords": ["水运", "内河航运"], "industry_raw": ["水运"]},
        {"l4_id": 7311, "l4_name": "路桥", "desc_keywords": ["路桥", "桥梁", "隧道", "收费公路", "路桥运营", "桥梁工程", "隧道工程"], "concept_keywords": ["路桥", "基建"], "industry_raw": ["路桥"]},
        {"l4_id": 7312, "l4_name": "公共交通", "desc_keywords": ["公共交通", "综合交通", "交通枢纽", "客运站", "交通投资", "交通基建"], "concept_keywords": ["公共交通", "智慧城市"], "industry_raw": ["公共交通"]},
    ],
}


# Generic concept tags that should be ignored for classification
# (they appear on too many stocks to be discriminative)
IGNORED_CONCEPTS = {
    "融资融券", "转融券标的", "融资标的股", "融券标的股",
    "标普道琼斯A股", "深股通", "沪股通", "MSCI概念",
    "地方国资改革", "年报预增", "机构重仓", "证金持股",
    "新股与次新股", "核准制次新股", "股权转让",
    "ST板块", "退市警示", "风险提示",
}


class L4Classifier:
    """Classify stocks from L3 parent nodes to L4 leaf nodes."""

    def __init__(self):
        self.rules = L4_RULES

    def _match_rule(self, stock: StockIndustryKB, concepts: set, rule: dict) -> bool:
        """Check if a stock matches a classification rule."""
        # 1. Tushare industry_raw exact match (strongest signal)
        if stock.industry_raw and stock.industry_raw in rule.get("industry_raw", []):
            return True

        # 2. business_desc keyword match
        if stock.business_desc:
            desc_lower = stock.business_desc.lower()
            for kw in rule.get("desc_keywords", []):
                if kw.lower() in desc_lower:
                    return True

        # 3. concept tag match (filtered)
        for kw in rule.get("concept_keywords", []):
            if kw in concepts:
                return True

        return False

    def classify_stock(self, stock: StockIndustryKB, concepts: List[str]) -> Optional[int]:
        """Classify a single stock to an L4 node.

        Returns the L4 node ID, or None if no match.
        """
        l3_id = stock.std_industry_id
        if l3_id not in self.rules:
            return None

        # Filter out generic concepts
        filtered_concepts = {c for c in concepts if c not in IGNORED_CONCEPTS}

        for rule in self.rules[l3_id]:
            if self._match_rule(stock, filtered_concepts, rule):
                return rule["l4_id"]

        return None

    def classify_l3_stocks(self, l3_id: int, dry_run: bool = False) -> Tuple[int, int, Dict[int, int]]:
        """Classify all stocks under an L3 node to L4 children.

        Returns: (classified_count, unclassified_count, l4_distribution)
        """
        session = get_session()
        try:
            stocks = (
                session.query(StockIndustryKB)
                .filter_by(std_industry_id=l3_id)
                .all()
            )

            # Pre-fetch concept tags for all stocks
            stock_codes = [s.stock_code for s in stocks]
            concept_map = self._fetch_concepts_batch(session, stock_codes)

            classified = 0
            unclassified = 0
            distribution: Dict[int, int] = defaultdict(int)
            updates = []

            for stock in stocks:
                concepts = concept_map.get(stock.stock_code, [])
                l4_id = self.classify_stock(stock, concepts)

                if l4_id:
                    classified += 1
                    distribution[l4_id] += 1
                    if not dry_run:
                        stock.std_industry_id = l4_id
                        updates.append(stock)
                else:
                    unclassified += 1

            if not dry_run and updates:
                session.commit()

            return classified, unclassified, dict(distribution)
        finally:
            session.close()

    def _fetch_concepts_batch(self, session, stock_codes: List[str]) -> Dict[str, List[str]]:
        """Fetch concept tags for a batch of stocks."""
        if not stock_codes:
            return {}

        from sqlalchemy import text
        # Use a simpler query approach
        result = {}
        for code in stock_codes:
            stock = session.query(StockIndustryKB).filter_by(stock_code=code).first()
            if stock and stock.concepts:
                result[code] = [c.name for c in stock.concepts]
            else:
                result[code] = []
        return result

    def run_full_classification(self, dry_run: bool = False, l3_filter: Optional[int] = None) -> Dict:
        """Run classification for all L3 nodes that have L4 children."""
        session = get_session()
        try:
            # Get all L3 nodes that have L4 children
            l3_nodes = (
                session.query(IndustryTree)
                .filter(IndustryTree.level == 3)
                .all()
            )

            l3_with_children = []
            for l3 in l3_nodes:
                has_l4 = session.query(IndustryTree).filter_by(parent_id=l3.id, level=4).first()
                if has_l4:
                    l3_with_children.append(l3)

            if l3_filter:
                l3_with_children = [n for n in l3_with_children if n.id == l3_filter]

            total_classified = 0
            total_unclassified = 0
            results = []

            for l3 in sorted(l3_with_children, key=lambda x: x.id):
                classified, unclassified, distribution = self.classify_l3_stocks(l3.id, dry_run=dry_run)
                total_classified += classified
                total_unclassified += unclassified

                if classified > 0 or unclassified > 0:
                    results.append({
                        "l3_id": l3.id,
                        "l3_name": l3.name,
                        "classified": classified,
                        "unclassified": unclassified,
                        "distribution": distribution,
                    })

                    l4_names = {}
                    for l4_id in distribution:
                        l4 = session.query(IndustryTree).filter_by(id=l4_id).first()
                        if l4:
                            l4_names[l4_id] = l4.name

                    logger.info(
                        f"L3 {l3.id} {l3.name}: "
                        f"classified={classified}, unclassified={unclassified}"
                    )
                    for l4_id, count in sorted(distribution.items()):
                        logger.info(f"  -> L4 {l4_id} {l4_names.get(l4_id, '?')}: {count}")

            return {
                "dry_run": dry_run,
                "total_classified": total_classified,
                "total_unclassified": total_unclassified,
                "results": results,
            }
        finally:
            session.close()
