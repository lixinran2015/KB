import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import streamlit as st
import plotly.graph_objects as go
from packages.config.loader import load_industry
from packages.ui.components.industry_tree import build_sunburst_data

st.title("🗺️ 产业地图")

industry_choice = st.selectbox("选择产业", ["人工智能", "机器人"])
industry_key = "ai" if industry_choice == "人工智能" else "robot"
industry = load_industry(industry_key)

labels, parents, values, colors = build_sunburst_data(industry)

fig = go.Figure(go.Sunburst(
    labels=labels,
    parents=parents,
    values=values,
    branchvalues="total",
    marker=dict(colors=colors),
    hovertemplate="<b>%{label}</b><br>占比: %{value:.1f}<extra></extra>",
))

fig.update_layout(
    margin=dict(t=20, b=20, l=20, r=20),
    height=600,
)

st.plotly_chart(fig, use_container_width=True)

# Detail table
st.subheader("📋 环节详情")
for layer_key, layer_name in [("upstream", "上游"), ("midstream", "中游"), ("downstream", "下游")]:
    layer = industry.get(layer_key)
    if not layer:
        continue
    with st.expander(f"{layer_name}: {layer.get('name', '')}"):
        for segment in layer.get("segments", []):
            cols = st.columns([2, 1, 1])
            with cols[0]:
                st.markdown(f"**{segment['name']}**")
            with cols[1]:
                pct = segment.get("value_chain_pct")
                if pct is not None:
                    st.caption(f"价值链占比: {pct:.0%}")
            with cols[2]:
                rate = segment.get("localization_rate")
                if rate is not None:
                    st.caption(f"国产化率: {rate:.0%}")
            stocks = segment.get("key_stocks", [])
            if stocks:
                st.caption(f"关键标的: {', '.join(str(s) for s in stocks)}")
