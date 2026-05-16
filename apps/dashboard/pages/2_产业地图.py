import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import streamlit as st
import pandas as pd
from packages.config.loader import load_all_industries, load_industry, load_stocks, save_industry, save_stocks
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
INDUSTRIES = load_all_industries()
# 如果没有配置文件，显示默认的两个产业
if not INDUSTRIES:
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

    st.divider()
    if st.button("➕ 添加产业", key="btn_add_industry", type="secondary"):
        st.session_state.industry_view = "add_industry"
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


# ═══════════════════════════════════════════════════════
# 视图 4：添加产业（自动生成 + DeepSeek 核对）
# ═══════════════════════════════════════════════════════
elif st.session_state.industry_view == "add_industry":
    st.title("➕ 添加产业")
    st.caption("输入产业名称，系统自动分析股票数据并生成产业链地图")

    # 返回按钮
    if st.button("⬅️ 返回列表", use_container_width=True):
        st.session_state.industry_view = "list"
        # 清除生成状态
        for key in ["gen_industry_name", "gen_structure", "gen_stocks", "gen_verify_result", "gen_stocks_entries"]:
            if key in st.session_state:
                del st.session_state[key]
        st.rerun()

    st.markdown("---")

    # ── 输入阶段 ──
    industry_name = st.text_input("产业名称", placeholder="例如：新能源、半导体、生物医药")

    col1, col2 = st.columns([1, 4])
    with col1:
        generate_btn = st.button("🚀 自动生成产业地图", type="primary", use_container_width=True)

    # ── 生成阶段 ──
    if generate_btn and industry_name:
        from packages.adapters.industry_generator import IndustryGenerator

        gen = IndustryGenerator()
        try:
            with st.spinner("正在分析股票数据..."):
                stocks = gen.collect_stocks(industry_name)
                if not stocks:
                    st.warning(f"未找到与「{industry_name}」相关的股票，请尝试其他名称。")
                else:
                    st.success(f"找到 {len(stocks)} 只相关股票")
                    structure = gen.auto_structure(stocks, industry_name=industry_name)

                    # 保存到 session state
                    st.session_state.gen_industry_name = industry_name
                    st.session_state.gen_structure = structure
                    st.session_state.gen_stocks = stocks

                    # DeepSeek 核对
                    with st.spinner("正在请 DeepSeek AI 核对..."):
                        verify_result = gen.verify_with_deepseek(industry_name, structure)
                        st.session_state.gen_verify_result = verify_result

                    # 生成 stocks.yml 条目
                    config, stocks_entries = gen.generate_config(industry_name, structure, stocks)
                    st.session_state.gen_stocks_entries = stocks_entries
                    st.session_state.gen_config = config

                    st.rerun()
        finally:
            gen.close()

    # ── 展示阶段 ──
    if "gen_structure" in st.session_state and st.session_state.gen_structure:
        industry_name = st.session_state.gen_industry_name
        structure = st.session_state.gen_structure
        verify_result = st.session_state.get("gen_verify_result")
        stocks_entries = st.session_state.get("gen_stocks_entries", [])
        config = st.session_state.get("gen_config", {})

        st.markdown(f"### 📊 自动生成结果：{industry_name}")

        # AI 评分
        if verify_result:
            score = verify_result.get("overall_score", 0)
            score_color = "#10b981" if score >= 7 else "#f59e0b" if score >= 5 else "#ef4444"
            st.markdown(
                f"**DeepSeek AI 评分：** <span style='color:{score_color};font-size:24px;font-weight:bold'>{score}/10</span>",
                unsafe_allow_html=True,
            )

            # Issues
            issues = verify_result.get("issues", [])
            if issues:
                with st.expander("📋 AI 评估详情"):
                    for issue in issues:
                        severity = issue.get("severity", "medium")
                        icon = "🔴" if severity == "high" else "🟡" if severity == "medium" else "🟢"
                        st.markdown(f"{icon} **{issue.get('description', '')}**")
                        st.caption(f"💡 建议：{issue.get('suggestion', '')}")

        # 结构对比
        st.markdown("#### 产业结构")
        col_orig, col_improved = st.columns(2)

        with col_orig:
            st.markdown("**🤖 原始结构**")
            for layer_key in ["upstream", "midstream", "downstream"]:
                layer = structure.get(layer_key, {})
                if layer.get("segments"):
                    layer_label = {"upstream": "上游", "midstream": "中游", "downstream": "下游"}.get(layer_key, layer_key)
                    st.markdown(f"**{layer_label}：** {layer.get('name', layer_label)}")
                    for seg in layer["segments"]:
                        st.caption(f"  • {seg['name']} — {seg.get('description', '')}")

        with col_improved:
            st.markdown("**🧠 AI 建议结构**")
            if verify_result and verify_result.get("improved_structure"):
                improved = verify_result["improved_structure"]
                for layer_key in ["upstream", "midstream", "downstream"]:
                    layer = improved.get(layer_key, {})
                    if layer.get("segments"):
                        layer_label = {"upstream": "上游", "midstream": "中游", "downstream": "下游"}.get(layer_key, layer_key)
                        st.markdown(f"**{layer_label}：** {layer.get('name', layer_label)}")
                        for seg in layer["segments"]:
                            st.caption(f"  • {seg['name']} — {seg.get('description', '')}")
            else:
                st.caption("AI 未提供改进建议")

        # 股票预览
        st.markdown("---")
        st.markdown(f"**📈 预计写入 {len(stocks_entries)} 只股票到 stocks.yml**")
        with st.expander("预览股票列表"):
            preview_df = pd.DataFrame([
                {"代码": s["code"], "名称": s["name"], "环节": s["segment"]}
                for s in stocks_entries[:50]
            ])
            st.dataframe(preview_df, use_container_width=True)
            if len(stocks_entries) > 50:
                st.caption(f"... 共 {len(stocks_entries)} 只，显示前 50 只")

        # 选择采用的结构
        st.markdown("---")
        st.markdown("### ✅ 确认保存")

        use_structure = st.radio(
            "选择采用的结构",
            ["原始结构", "AI 建议结构"] if (verify_result and verify_result.get("improved_structure")) else ["原始结构"],
            horizontal=True,
        )

        # 检查是否已存在
        industry_dir = Path(__file__).parent.parent.parent.parent / "config" / "industries"
        existing_file = industry_dir / f"{industry_name}.yml"
        if existing_file.exists():
            st.warning(f"⚠️ 产业「{industry_name}」已存在，保存将覆盖原有配置。")

        if st.button("💾 确认并保存", type="primary"):
            # 确定最终结构
            final_structure = structure
            if use_structure == "AI 建议结构" and verify_result:
                final_structure = verify_result.get("improved_structure", structure)

            # ── 同步 segment 名称映射（按层级独立） ──
            # 如果 AI 建议结构修改了 segment 名称，需要同步更新 stocks_entries 中的 segment 字段
            # 否则产业地图页面按 AI segment 名称查找 stocks.yml 会找不到股票
            # 使用 (layer, segment_name) 作为 key 避免跨层级覆盖
            rename_map = {}
            if use_structure == "AI 建议结构" and verify_result:
                for layer in ["upstream", "midstream", "downstream"]:
                    orig_segs = [s["name"] for s in structure.get(layer, {}).get("segments", [])]
                    ai_segs = [s["name"] for s in final_structure.get(layer, {}).get("segments", [])]
                    for i in range(min(len(orig_segs), len(ai_segs))):
                        if orig_segs[i] != ai_segs[i]:
                            rename_map[(layer, orig_segs[i])] = ai_segs[i]

            # 应用映射到 stocks_entries
            synced_entries = []
            for entry in stocks_entries:
                new_entry = dict(entry)
                layer = new_entry.pop("_layer", "")
                key = (layer, new_entry["segment"])
                if key in rename_map:
                    new_entry["segment"] = rename_map[key]
                synced_entries.append(new_entry)

            # 组装最终配置
            final_config = {
                "name": industry_name,
                "upstream": final_structure.get("upstream", {"name": "上游", "segments": []}),
                "midstream": final_structure.get("midstream", {"name": "中游", "segments": []}),
                "downstream": final_structure.get("downstream", {"name": "下游", "segments": []}),
            }

            try:
                # 1. 保存产业配置文件
                save_industry(industry_name, final_config)

                # 2. 追加股票到 stocks.yml
                existing_stocks = load_stocks()
                existing_codes = {s["code"] for s in existing_stocks}
                new_entries = [s for s in synced_entries if s["code"] not in existing_codes]
                all_stocks = existing_stocks + new_entries
                save_stocks(all_stocks)

                st.success(f"✅ 产业「{industry_name}」已保存！")
                st.info(f"📁 配置文件：config/industries/{industry_name}.yml")
                st.info(f"📈 新增 {len(new_entries)} 只股票到 stocks.yml")

                # 3. 清除 session state 并返回列表
                for key in ["gen_industry_name", "gen_structure", "gen_stocks", "gen_verify_result", "gen_stocks_entries", "gen_config"]:
                    if key in st.session_state:
                        del st.session_state[key]

                st.session_state.industry_view = "list"
                st.rerun()

            except Exception as e:
                st.error(f"保存失败：{e}")
