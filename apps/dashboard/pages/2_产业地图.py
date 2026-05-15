import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from packages.config.loader import load_industry, load_stocks, save_stocks

st.set_page_config(page_title="产业地图", layout="wide")

st.title("🗺️ 产业地图")

# ── 产业选择 ──
col_selector, _ = st.columns([1, 3])
with col_selector:
    industry_choice = st.segmented_control(
        "选择产业",
        ["人工智能", "机器人"],
        default="人工智能",
    )
if not industry_choice:
    industry_choice = "人工智能"
industry_key = "ai" if industry_choice == "人工智能" else "robot"
industry = load_industry(industry_key)

# ── 数据准备 ──
all_stocks = load_stocks()
segment_stock_map = {}
for s in all_stocks:
    seg = s.get("segment", "")
    if seg:
        segment_stock_map.setdefault(seg, []).append(s)

# Layer color scheme
LAYER_COLORS = {
    "upstream": "#3b82f6",   # blue
    "midstream": "#10b981",  # green
    "downstream": "#f59e0b", # amber
}
LAYER_LABELS = {"upstream": "上游", "midstream": "中游", "downstream": "下游"}

# ── 构建环节表格数据 ──
table_rows = []
for layer_key in ["upstream", "midstream", "downstream"]:
    layer = industry.get(layer_key)
    if not layer:
        continue
    layer_color = LAYER_COLORS.get(layer_key, "#9ca3af")
    for segment in layer.get("segments", []):
        seg_name = segment["name"]
        stocks = segment_stock_map.get(seg_name, []) or segment.get("key_stocks", [])
        stock_count = len(stocks)
        table_rows.append({
            "层级": LAYER_LABELS.get(layer_key, layer_key),
            "层级色": layer_color,
            "环节": seg_name,
            "价值链占比": segment.get("value_chain_pct"),
            "国产化率": segment.get("localization_rate"),
            "标的数": stock_count,
            "股票列表": ", ".join(
                [f"{s['code']} {s.get('name', '')}".strip() for s in stocks[:3]]
            ) + (" ..." if stock_count > 3 else "") if stocks else "暂无",
        })
        for sub in segment.get("sub_segments", []):
            sub_name = sub if isinstance(sub, str) else sub.get("name", "")
            if sub_name:
                table_rows.append({
                    "层级": LAYER_LABELS.get(layer_key, layer_key),
                    "层级色": layer_color,
                    "环节": f"  └ {sub_name}",
                    "价值链占比": None,
                    "国产化率": None,
                    "标的数": 0,
                    "股票列表": "",
                })

df_segments = pd.DataFrame(table_rows)

# ── 顶部概览指标 ──
st.markdown("---")
metric_cols = st.columns(4)
with metric_cols[0]:
    st.metric("总环节数", len(df_segments))
with metric_cols[1]:
    total_stocks = sum(len(v) for v in segment_stock_map.values())
    st.metric("覆盖标的", total_stocks)
with metric_cols[2]:
    avg_loc = df_segments["国产化率"].mean()
    st.metric("平均国产化率", f"{avg_loc:.0%}" if pd.notna(avg_loc) else "--")
with metric_cols[3]:
    key_seg = df_segments[df_segments["价值链占比"] == df_segments["价值链占比"].max()]["环节"].values
    st.metric("价值最大环节", key_seg[0] if len(key_seg) else "--")

# ── Tushare 数据补充（折叠，不默认展开）──
with st.expander("🔍 智能补充股票数据（Tushare）", expanded=False):
    token = os.getenv("TUSHARE_TOKEN")
    if not token:
        st.info("💡 需要 Tushare Token。设置环境变量 `TUSHARE_TOKEN` 后刷新页面。")
        st.markdown("[去 tushare.pro 注册](https://tushare.pro)")
    else:
        if "tushare_results" not in st.session_state:
            st.session_state.tushare_results = None
        if "tushare_new_entries" not in st.session_state:
            st.session_state.tushare_new_entries = []

        if st.button("🚀 拉取概念板块成分股", type="primary"):
            with st.spinner("正在从 Tushare 获取数据..."):
                try:
                    from packages.adapters.tushare_industry_adapter import TushareIndustryAdapter
                    adapter = TushareIndustryAdapter(token=token)
                    results = adapter.enrich_industry(industry_key)
                    st.session_state.tushare_results = results
                    st.session_state.tushare_new_entries = adapter.build_stocks_config(industry_key)
                except Exception as e:
                    st.error(f"获取失败: {e}")

        if st.session_state.tushare_results is not None:
            results = st.session_state.tushare_results
            total = sum(len(v) for v in results.values())
            st.success(f"找到 {total} 只股票，分布在 {len(results)} 个环节")
            for seg_name, stocks in results.items():
                display = [f"{s['code']} {s['name']}" for s in stocks[:6]]
                st.caption(f"**{seg_name}** ({len(stocks)}只): {'、'.join(display)}")

            new_entries = st.session_state.tushare_new_entries
            if new_entries:
                if st.button("💾 保存到 stocks.yml", type="secondary"):
                    merged = all_stocks + new_entries
                    save_stocks(merged)
                    st.success(f"已保存 {len(new_entries)} 只新股票！刷新页面后查看。")
                    st.session_state.tushare_results = None
                    st.session_state.tushare_new_entries = []
                    st.rerun()
            else:
                st.info("没有新的股票需要保存")

# ── 主体：左侧旭日图 + 右侧环节表格 ──
st.markdown("---")
left_col, right_col = st.columns([3, 2])

# ── 左侧：旭日图 ──
with left_col:
    st.subheader("产业链结构")

    # Build sunburst data with segment names matching the table
    labels = [industry["name"]]
    parents = [""]
    values = [100]
    colors = ["#1f2937"]  # root: dark gray

    for layer_key in ["upstream", "midstream", "downstream"]:
        layer = industry.get(layer_key)
        if not layer:
            continue
        layer_name = layer.get("name", LAYER_LABELS.get(layer_key, layer_key))
        layer_color = LAYER_COLORS.get(layer_key, "#9ca3af")

        labels.append(layer_name)
        parents.append(industry["name"])
        values.append(33)
        colors.append(layer_color)

        for segment in layer.get("segments", []):
            seg_name = segment["name"]
            labels.append(seg_name)
            parents.append(layer_name)
            val = segment.get("value_chain_pct", 0.1)
            values.append(val * 100 if val <= 1 else val)
            colors.append(layer_color)

    fig = go.Figure(go.Sunburst(
        labels=labels,
        parents=parents,
        values=values,
        branchvalues="total",
        marker=dict(colors=colors, line=dict(color="white", width=1)),
        hovertemplate="<b>%{label}</b><br>占比: %{value:.1f}<extra></extra>",
        textinfo="label",
    ))
    fig.update_layout(
        margin=dict(t=10, b=10, l=10, r=10),
        height=500,
        paper_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig, width='stretch', key=f"sunburst_{industry_key}")

    # Legend
    legend_cols = st.columns(3)
    for i, (key, label) in enumerate([("upstream", "上游"), ("midstream", "中游"), ("downstream", "下游")]):
        with legend_cols[i]:
            st.markdown(
                f"<div style='display:flex;align-items:center;gap:8px'>"
                f"<span style='width:12px;height:12px;border-radius:50%;background:{LAYER_COLORS[key]};display:inline-block'></span>"
                f"<span>{label}</span></div>",
                unsafe_allow_html=True,
            )

# ── 右侧：环节详情表格 ──
with right_col:
    st.subheader("环节详情")

    if not df_segments.empty:
        # Build a styled display
        for _, row in df_segments.iterrows():
            with st.container():
                c1, c2, c3 = st.columns([2, 1, 1])
                with c1:
                    color_dot = f"<span style='color:{row['层级色']};font-size:10px'>●</span>"
                    st.markdown(f"{color_dot} **{row['环节']}**", unsafe_allow_html=True)
                with c2:
                    if pd.notna(row["价值链占比"]):
                        st.caption(f"价值链: {row['价值链占比']:.0%}")
                with c3:
                    if pd.notna(row["国产化率"]):
                        st.caption(f"国产化: {row['国产化率']:.0%}")

                if row["股票列表"]:
                    st.caption(f"📌 {row['股票列表']}")
                st.markdown("---")
    else:
        st.info("暂无环节数据")

# ── 底部：产业链笔记（Markdown 编辑区）──
st.markdown("---")
st.subheader("📝 产业笔记")

notes_path = Path(__file__).parent.parent.parent.parent / "docs" / f"{industry_key}_notes.md"
if notes_path.exists():
    notes_content = notes_path.read_text(encoding="utf-8")
else:
    notes_content = f"""# {industry_choice}产业笔记

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
