import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import streamlit as st
import plotly.graph_objects as go
from packages.config.loader import load_industry, load_stocks, save_stocks
from packages.ui.components.industry_tree import build_sunburst_data

st.title("🗺️ 产业地图")

industry_choice = st.selectbox("选择产业", ["人工智能", "机器人"])
industry_key = "ai" if industry_choice == "人工智能" else "robot"
industry = load_industry(industry_key)

# Build a lookup: segment_name -> list of stock dicts from stocks.yml
all_stocks = load_stocks()
segment_stock_map = {}
for s in all_stocks:
    seg = s.get("segment", "")
    if seg:
        segment_stock_map.setdefault(seg, []).append(s)

# Smart enrichment from Tushare
with st.expander("🔍 智能补充股票数据（Tushare）"):
    token = os.getenv("TUSHARE_TOKEN")
    if not token:
        st.info("💡 需要 Tushare Token 才能智能补充。设置环境变量 `TUSHARE_TOKEN` 后刷新页面。")
        st.markdown("[去 tushare.pro 注册获取 Token](https://tushare.pro)")
    else:
        if st.button("🚀 拉取概念板块成分股", type="primary"):
            with st.spinner("正在从 Tushare 获取数据..."):
                try:
                    from packages.adapters.tushare_industry_adapter import TushareIndustryAdapter
                    adapter = TushareIndustryAdapter(token=token)
                    results = adapter.enrich_industry(industry_key)

                    total = sum(len(v) for v in results.values())
                    st.success(f"找到 {total} 只股票，分布在 {len(results)} 个环节")

                    for seg_name, stocks in results.items():
                        with st.container():
                            st.markdown(f"**{seg_name}** ({len(stocks)}只)")
                            codes = [s['code'] for s in stocks[:8]]
                            names = [s['name'] for s in stocks[:8]]
                            display = [f"{c} {n}" for c, n in zip(codes, names)]
                            st.caption("、".join(display))
                            if len(stocks) > 8:
                                st.caption(f"... 还有 {len(stocks) - 8} 只")

                    # Offer to persist
                    new_entries = adapter.build_stocks_config(industry_key)
                    if new_entries:
                        st.divider()
                        st.write(f"**{len(new_entries)} 只新股票可保存到股票库**")
                        if st.button("💾 保存到 stocks.yml", type="secondary"):
                            merged = all_stocks + new_entries
                            save_stocks(merged)
                            st.success(f"已保存 {len(new_entries)} 只新股票！刷新页面后可在各环节查看。")
                            st.balloons()
                except Exception as e:
                    st.error(f"获取失败: {e}")
                    st.info("可能是网络问题或 Tushare 接口限制，请稍后再试。")

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
            # Show stocks from stocks.yml first, fallback to key_stocks in industry YAML
            seg_name = segment["name"]
            stocks_from_db = segment_stock_map.get(seg_name, [])
            yaml_stocks = segment.get("key_stocks", [])

            if stocks_from_db:
                display = [f"{s['code']} {s['name']}" for s in stocks_from_db]
                st.caption(f"📌 标的: {', '.join(display)}")
            elif yaml_stocks:
                st.caption(f"📌 标的: {', '.join(str(s) for s in yaml_stocks)}")
            else:
                st.caption("⚠️ 暂无标的")
