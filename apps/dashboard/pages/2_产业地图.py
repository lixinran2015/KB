import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import streamlit as st
import pandas as pd
from packages.config.loader import load_industry, load_stocks, save_stocks
from packages.domain.database import get_session
from packages.domain.models import ScoreResult, StockFinancial, StockIndustryKB, StockConceptRel, ConceptTag

st.set_page_config(page_title="产业地图", layout="wide")

# ── 初始化 session state ──
if "industry_view" not in st.session_state:
    st.session_state.industry_view = "list"  # list | detail | stocks
if "selected_industry_key" not in st.session_state:
    st.session_state.selected_industry_key = None
if "selected_segment" not in st.session_state:
    st.session_state.selected_segment = None
if "selected_layer" not in st.session_state:
    st.session_state.selected_layer = None

# ── 机器人产业链 segment 匹配规则 ──
# 优先级：从上到下，先匹配的先分配
ROBOT_SEGMENT_RULES = [
    # 上游：核心零部件（优先级从高到低，越具体的越靠前）
    ("丝杠", {"concept": ["丝杠"], "desc": ["丝杠", "滚珠丝杠", "行星滚柱丝杠"]}),
    ("减速器", {"concept": ["减速器"], "desc": ["减速器", "谐波减速", "RV减速", "行星减速", "谐波", "精密传动"]}),
    ("控制器", {"concept": ["控制器"], "desc": ["控制器", "数控系统", "运动控制", "PLC", "控制产品", "可编程逻辑控制器"]}),
    ("传感器", {"concept": ["传感器"], "desc": ["传感器", "力传感器", "视觉传感器", "触觉传感器", "机器视觉"]}),
    ("伺服电机", {"concept": ["伺服", "电机电控"], "desc": ["伺服电机", "伺服系统", "伺服驱动", "伺服器"]}),
    # 下游：场景应用
    ("医疗机器人", {"concept": ["医疗机器人"], "desc": ["医疗机器人", "手术机器人", "康复机器人"]}),
    ("家用服务机器人", {"concept": ["服务机器人"], "desc": ["服务机器人", "扫地机器人", "陪伴机器人", "教育机器人"]}),
    ("整机代工", {"concept": ["工业机器人", "人形机器人"], "desc": ["工业机器人", "焊接机器人", "协作机器人", "人形机器人", "机器人整机"]}),
    ("系统集成", {"concept": [], "desc": ["系统集成", "自动化解决方案", "智能制造系统", "智能工厂", "AGV", "AMR", "RGV", "移动机器人"]}),
    ("工业制造", {"concept": ["工业机器人"], "desc": ["工业制造"]}),
]


def load_robot_stocks_from_db():
    """从数据库加载机器人产业链相关股票，按 segment 分组。"""
    session = get_session()
    try:
        # 1. 获取机器人相关概念标签的 stock_codes
        robot_tag_names = [
            "工业机器人", "服务机器人", "医疗机器人", "人形机器人",
            "军用机器人", "机器人材料", "虚拟机器人", "减速器", "传感器", "伺服",
        ]
        robot_tags = session.query(ConceptTag).filter(ConceptTag.name.in_(robot_tag_names)).all()
        robot_tag_ids = [t.id for t in robot_tags]

        stock_codes = []
        if robot_tag_ids:
            stock_codes = [
                r[0] for r in
                session.query(StockConceptRel.stock_code)
                .filter(StockConceptRel.concept_tag_id.in_(robot_tag_ids))
                .distinct()
                .all()
            ]

        # 2. 包含 L3 110 通用机械/机器人 下的所有 L4 子节点
        #    1100 机器人 + 1101 数控机床 + 1102 工控设备 + 1103 仪器仪表
        l3_110_codes = [
            r[0] for r in
            session.query(StockIndustryKB.stock_code)
            .filter(StockIndustryKB.std_industry_id.in_([1100, 1101, 1102, 1103]))
            .all()
        ]

        all_codes = list(set(stock_codes) | set(l3_110_codes))
        if not all_codes:
            return {}

        # 3. 查询完整股票数据
        stocks = session.query(StockIndustryKB).filter(StockIndustryKB.stock_code.in_(all_codes)).all()

        # 4. 按规则分配到 segment
        segment_map = {}
        for stock in stocks:
            concepts = [c.name for c in stock.concepts]
            desc = stock.business_desc or ""

            matched_seg = None
            for seg_name, rules in ROBOT_SEGMENT_RULES:
                # 概念标签匹配
                for c in rules["concept"]:
                    if c in concepts:
                        matched_seg = seg_name
                        break
                if matched_seg:
                    break

                # 业务描述关键词匹配
                for kw in rules["desc"]:
                    if kw in desc:
                        matched_seg = seg_name
                        break
                if matched_seg:
                    break

            if matched_seg:
                segment_map.setdefault(matched_seg, []).append({
                    "code": stock.stock_code,
                    "name": stock.stock_name,
                    "segment": matched_seg,
                    "style": "待分类",
                    "market_cap_tier": "待分类",
                    "source": "db",
                })

        return segment_map
    finally:
        session.close()


# ── 加载全局数据 ──
all_stocks = load_stocks()

# 构建 segment -> stocks 映射（优先用 stocks.yml，再用数据库补充）
segment_stock_map = {}

# 1. 先加载 stocks.yml 中的股票
for s in all_stocks:
    seg = s.get("segment", "")
    if seg:
        segment_stock_map.setdefault(seg, []).append(s)

# 2. 从数据库加载机器人产业链股票并合并
db_segment_map = load_robot_stocks_from_db()
for seg, stocks in db_segment_map.items():
    existing_codes = {s["code"] for s in segment_stock_map.get(seg, [])}
    for s in stocks:
        if s["code"] not in existing_codes:
            segment_stock_map.setdefault(seg, []).append(s)

# 获取最新评分数据
latest_scores = {}
try:
    session = get_session()
    score_rows = (
        session.query(ScoreResult.stock_code, ScoreResult.total_score)
        .distinct(ScoreResult.stock_code)
        .order_by(ScoreResult.stock_code, ScoreResult.scored_at.desc())
        .all()
    )
    latest_scores = {r.stock_code: r.total_score for r in score_rows if r.total_score is not None}
    session.close()
except Exception:
    pass

# 获取最新财务数据（用于画像标签）
latest_financials = {}
try:
    session = get_session()
    fin_rows = (
        session.query(StockFinancial)
        .order_by(StockFinancial.stock_code, StockFinancial.snapshot_date.desc())
        .all()
    )
    seen = set()
    for f in fin_rows:
        if f.stock_code not in seen:
            latest_financials[f.stock_code] = f
            seen.add(f.stock_code)
    session.close()
except Exception:
    pass

# ── 辅助函数 ──
def get_segment_stats(seg_name):
    """返回环节的股票列表、数量、平均评分"""
    stocks = segment_stock_map.get(seg_name, [])
    scores = [latest_scores.get(s["code"]) for s in stocks]
    valid_scores = [s for s in scores if s is not None]
    avg_score = sum(valid_scores) / len(valid_scores) if valid_scores else None
    return stocks, len(stocks), avg_score


def get_stock_tags(stock_code, segment_stocks):
    """计算股票画像标签列表"""
    tags = []
    fin = latest_financials.get(stock_code)
    score = latest_scores.get(stock_code)

    # 龙头：segment内评分最高前2
    segment_scores = [(s["code"], latest_scores.get(s["code"], 0)) for s in segment_stocks]
    segment_scores = sorted([x for x in segment_scores if x[1]], key=lambda x: x[1], reverse=True)
    if segment_scores and stock_code == segment_scores[0][0]:
        tags.append(("👑 龙头", "#f59e0b"))
    elif len(segment_scores) > 1 and stock_code == segment_scores[1][0]:
        tags.append(("🥈 龙二", "#f59e0b"))

    # 中军：评分在 3.0~4.0 之间
    if score and 3.0 <= score < 4.0:
        tags.append(("🛡️ 中军", "#3b82f6"))

    # 业绩增长
    if fin:
        if (fin.revenue_growth and fin.revenue_growth > 0.30) or \
           (fin.net_profit_growth and fin.net_profit_growth > 0.30):
            tags.append(("📈 业绩增长", "#10b981"))
        # 业绩下滑
        elif (fin.revenue_growth is not None and fin.revenue_growth < 0) or \
             (fin.net_profit_growth is not None and fin.net_profit_growth < 0):
            tags.append(("📉 业绩下滑", "#ef4444"))

        # 高毛利优质
        if fin.gross_margin and fin.gross_margin > 0.40:
            tags.append(("💎 高毛利", "#8b5cf6"))

        # 机构重仓
        if fin.fund_hold_pct and fin.fund_hold_pct > 0.10:
            tags.append(("🏦 机构重仓", "#06b6d4"))

    # 高分白马
    if score and score >= 4.5:
        tags.append(("🦄 高分白马", "#10b981"))

    return tags


# ── 获取所有产业配置 ──
INDUSTRIES = [
    {"key": "ai", "name": "人工智能", "icon": "🤖"},
    {"key": "robot", "name": "机器人", "icon": "🔧"},
]

LAYER_COLORS = {
    "upstream": "#3b82f6",
    "midstream": "#10b981",
    "downstream": "#f59e0b",
}
LAYER_LABELS = {"upstream": "上游", "midstream": "中游", "downstream": "下游"}
LAYER_ICONS = {"upstream": "🏔️", "midstream": "⚙️", "downstream": "🚀"}


# ═══════════════════════════════════════════════════════
# 视图 1：产业列表（首页）
# ═══════════════════════════════════════════════════════
if st.session_state.industry_view == "list":
    st.title("🗺️ 产业地图")
    st.caption("选择产业，查看产业链结构与核心标的")

    cols = st.columns(len(INDUSTRIES))
    for i, ind in enumerate(INDUSTRIES):
        with cols[i]:
            industry_data = load_industry(ind["key"])
            # 统计该产业覆盖的股票数
            ind_segments = []
            for layer_key in ["upstream", "midstream", "downstream"]:
                layer = industry_data.get(layer_key)
                if layer:
                    for seg in layer.get("segments", []):
                        ind_segments.append(seg["name"])

            ind_stock_count = sum(
                len(segment_stock_map.get(seg, []))
                for seg in ind_segments
            )
            ind_seg_count = len(ind_segments)

            with st.container(border=True):
                st.markdown(f"### {ind['icon']} {ind['name']}")
                st.caption(f"{ind_seg_count} 个细分环节")
                st.metric("覆盖标的", f"{ind_stock_count} 只")
                if st.button("进入产业", key=f"enter_{ind['key']}", type="primary"):
                    st.session_state.industry_view = "detail"
                    st.session_state.selected_industry_key = ind["key"]
                    st.rerun()


# ═══════════════════════════════════════════════════════
# 视图 2：产业详情（上游/中游/下游 + 细分行业）
# ═══════════════════════════════════════════════════════
elif st.session_state.industry_view == "detail":
    ind_key = st.session_state.selected_industry_key
    industry = load_industry(ind_key)
    ind_name = industry.get("name", ind_key)

    # 面包屑 + 返回按钮
    col1, col2 = st.columns([6, 1])
    with col1:
        st.markdown(f"### 🗺️ 产业地图 ＞ **{ind_name}**")
    with col2:
        if st.button("⬅️ 返回列表", use_container_width=True):
            st.session_state.industry_view = "list"
            st.session_state.selected_segment = None
            st.session_state.selected_layer = None
            st.rerun()

    st.markdown("---")

    # 遍历 上游/中游/下游
    for layer_key in ["upstream", "midstream", "downstream"]:
        layer = industry.get(layer_key)
        if not layer:
            continue

        layer_color = LAYER_COLORS.get(layer_key, "#9ca3af")
        layer_label = LAYER_LABELS.get(layer_key, layer_key)
        layer_icon = LAYER_ICONS.get(layer_key, "")

        # 层级标题栏
        st.markdown(
            f"<h4 style='color:{layer_color};border-left:4px solid {layer_color};padding-left:12px;margin-top:24px'>"
            f"{layer_icon} {layer.get('name', layer_label)}"
            f"</h4>",
            unsafe_allow_html=True,
        )

        segments = layer.get("segments", [])
        if not segments:
            st.info("暂无细分环节数据")
            continue

        # 环节卡片网格（每行3个）
        seg_cols = st.columns(3)
        for idx, segment in enumerate(segments):
            seg_name = segment["name"]
            stocks, stock_count, avg_score = get_segment_stats(seg_name)

            with seg_cols[idx % 3]:
                with st.container(border=True):
                    # 环节名称 + 股票数量
                    st.markdown(f"**{seg_name}**")

                    # 指标行
                    m1, m2 = st.columns(2)
                    with m1:
                        st.caption(f"📌 {stock_count} 只标的")
                    with m2:
                        if avg_score:
                            score_color = "#10b981" if avg_score >= 4.0 else "#f59e0b" if avg_score >= 3.0 else "#9ca3af"
                            st.caption(f"<span style='color:{score_color}'>⭐ 均分 {avg_score:.1f}</span>", unsafe_allow_html=True)
                        else:
                            st.caption("⭐ 暂无评分")

                    # 价值链占比
                    vcp = segment.get("value_chain_pct")
                    if vcp:
                        st.caption(f"价值链占比: {vcp:.0%}")

                    # 描述
                    desc = segment.get("description", "")
                    if desc:
                        st.caption(f"💡 {desc[:40]}{'...' if len(desc) > 40 else ''}")

                    # 进入按钮
                    if st.button("查看标的", key=f"seg_{ind_key}_{layer_key}_{idx}", use_container_width=True):
                        st.session_state.industry_view = "stocks"
                        st.session_state.selected_segment = seg_name
                        st.session_state.selected_layer = layer_key
                        st.rerun()

    # 底部笔记
    st.markdown("---")
    with st.expander("📝 产业笔记"):
        notes_path = Path(__file__).parent.parent.parent.parent / "docs" / f"{ind_key}_notes.md"
        if notes_path.exists():
            notes_content = notes_path.read_text(encoding="utf-8")
        else:
            notes_content = f"""# {ind_name}产业笔记

## 核心观点

## 重点公司跟踪

## 催化剂时间线

## 风险提示
"""
        notes_tabs = st.tabs(["📖 查看", "✏️ 编辑"])
        with notes_tabs[0]:
            st.markdown(notes_content)
        with notes_tabs[1]:
            edited = st.text_area("编辑笔记（Markdown）", notes_content, height=300, label_visibility="collapsed")
            if st.button("💾 保存笔记"):
                notes_path.parent.mkdir(parents=True, exist_ok=True)
                notes_path.write_text(edited, encoding="utf-8")
                st.success("笔记已保存！")


# ═══════════════════════════════════════════════════════
# 视图 3：股票列表（选中环节后的标的详情）
# ═══════════════════════════════════════════════════════
elif st.session_state.industry_view == "stocks":
    ind_key = st.session_state.selected_industry_key
    industry = load_industry(ind_key)
    ind_name = industry.get("name", ind_key)
    seg_name = st.session_state.selected_segment
    layer_key = st.session_state.selected_layer
    layer_label = LAYER_LABELS.get(layer_key, layer_key)

    # 面包屑
    col1, col2 = st.columns([6, 1])
    with col1:
        st.markdown(f"### 🗺️ 产业地图 ＞ {ind_name} ＞ **{layer_label} ＞ {seg_name}**")
    with col2:
        if st.button("⬅️ 返回产业", use_container_width=True):
            st.session_state.industry_view = "detail"
            st.session_state.selected_segment = None
            st.session_state.selected_layer = None
            st.rerun()

    st.markdown("---")

    stocks = segment_stock_map.get(seg_name, [])
    if not stocks:
        st.info("该环节暂无标的")
    else:
        st.caption(f"共 {len(stocks)} 只标的")

        # 排序：有评分的放前面，按评分降序
        stocks_sorted = sorted(
            stocks,
            key=lambda s: (latest_scores.get(s["code"], 0) or 0, s["code"]),
            reverse=True,
        )

        # 每只股票一个卡片
        for s in stocks_sorted:
            code = s["code"]
            name = s.get("name", "")
            score = latest_scores.get(code)
            fin = latest_financials.get(code)
            tags = get_stock_tags(code, stocks)

            with st.container(border=True):
                # 第一行：名称代码 + 评分 + 标签
                c1, c2, c3 = st.columns([2, 1, 3])

                with c1:
                    st.markdown(f"**{name}** `{code}`")

                with c2:
                    if score:
                        score_color = "#10b981" if score >= 4.0 else "#f59e0b" if score >= 3.0 else "#ef4444"
                        st.markdown(f"<span style='color:{score_color};font-size:18px;font-weight:bold'>⭐ {score:.1f}</span>", unsafe_allow_html=True)
                    else:
                        st.caption("暂无评分")

                with c3:
                    if tags:
                        tag_html = " ".join([
                            f"<span style='background:{color};color:white;padding:2px 8px;border-radius:12px;font-size:12px;margin-right:6px'>{label}</span>"
                            for label, color in tags
                        ])
                        st.markdown(tag_html, unsafe_allow_html=True)
                    else:
                        st.caption("暂无标签")

                # 第二行：财务指标（紧凑展示）
                if fin:
                    metrics = []
                    if fin.revenue_growth is not None:
                        metrics.append(f"营收增: {fin.revenue_growth:+.1%}")
                    if fin.net_profit_growth is not None:
                        metrics.append(f"净利增: {fin.net_profit_growth:+.1%}")
                    if fin.gross_margin is not None:
                        metrics.append(f"毛利: {fin.gross_margin:.1%}")
                    if fin.roe is not None:
                        metrics.append(f"ROE: {fin.roe:.1%}")
                    if fin.pe_ttm is not None:
                        metrics.append(f"PE: {fin.pe_ttm:.1f}x")
                    if fin.fund_hold_pct is not None:
                        metrics.append(f"公募: {fin.fund_hold_pct:.1%}")

                    if metrics:
                        st.caption(" ｜ ".join(metrics))

    # Tushare 补充（保持原有功能）
    st.markdown("---")
    with st.expander("🔍 智能补充股票数据（Tushare）"):
        token = os.getenv("TUSHARE_TOKEN")
        if not token:
            st.info("💡 需要 Tushare Token。设置环境变量 `TUSHARE_TOKEN` 后刷新页面。")
        else:
            if st.button("🚀 拉取概念板块成分股", type="primary"):
                with st.spinner("正在从 Tushare 获取数据..."):
                    try:
                        from packages.adapters.tushare_industry_adapter import TushareIndustryAdapter
                        adapter = TushareIndustryAdapter(token=token)
                        results = adapter.enrich_industry(ind_key)
                        st.success(f"找到 {sum(len(v) for v in results.values())} 只股票")
                        for seg_name_t, stocks_t in results.items():
                            st.caption(f"**{seg_name_t}** ({len(stocks_t)}只)")
                    except Exception as e:
                        st.error(f"获取失败: {e}")
