import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from collections import Counter
from packages.engines.watchlist_manager import WatchlistManager
from packages.engines.scoring_engine import ScoringEngine
from packages.engines.valuation_engine import ValuationEngine
from packages.config.loader import load_stocks
from packages.domain.database import get_latest_financial, get_session
from packages.domain.models import ScoreResult
from packages.adapters.akshare_adapter import AKShareAdapter
from packages.adapters.mock_adapter import MockAdapter

st.title("📁 关注清单")

wm = WatchlistManager()

# ── 新建组合 ──
with st.expander("➕ 新建关注组合"):
    name = st.text_input("组合名称")
    desc = st.text_area("描述（可选）")
    if st.button("创建"):
        if name:
            wl = wm.create_watchlist(name, desc)
            st.success(f"已创建组合: {name}")
            st.rerun()
        else:
            st.error("请输入组合名称")

# ── 加载数据 ──
wls = wm.list_watchlists()
all_stocks = load_stocks()
stock_map = {s["code"]: s for s in all_stocks}

try:
    adapter = AKShareAdapter()
except Exception:
    adapter = MockAdapter("stock_300308_q1_2024")
scoring = ScoringEngine(adapter=adapter)
valuation = ValuationEngine(adapter=adapter)

if not wls:
    st.info("暂无关注组合，请创建一个")
    st.stop()

# ── 筛选器 ──
filter_cols = st.columns(4)
with filter_cols[0]:
    filter_score = st.toggle("评分 ≥ 4.0")
with filter_cols[1]:
    filter_cheap = st.toggle("估值低估")
with filter_cols[2]:
    filter_segment = st.selectbox("环节筛选", ["全部"] + sorted(list(set(s.get("segment", "") for s in all_stocks if s.get("segment")))))
with filter_cols[3]:
    if st.button("🔄 批量评分", type="primary"):
        st.session_state["refresh_scores"] = True

# ── 组合 Tabs ──
tabs = st.tabs([wl.name for wl in wls])

for i, wl in enumerate(wls):
    with tabs[i]:
        items = wm.get_items(wl.id)

        col1, col2 = st.columns([3, 1])
        with col2:
            if st.button("🗑️ 删除组合", key=f"del_{wl.id}"):
                wm.delete_watchlist(wl.id)
                st.rerun()

        if not items:
            st.info("该组合暂无股票")
        else:
            # 计算每只股票的评分和估值
            rows = []
            segment_counts = Counter()
            for item in items:
                s = stock_map.get(item.stock_code, {})
                seg = s.get("segment", "?")
                segment_counts[seg] += 1

                # Score
                try:
                    score_result = scoring.calculate(
                        stock_code=item.stock_code,
                        segment=seg,
                        report_period="2024Q1",
                    )
                    total_score = score_result.total_score
                except Exception:
                    total_score = None

                # Valuation
                try:
                    val_result = valuation.calculate(
                        stock_code=item.stock_code,
                        segment=seg,
                        report_period="2024Q1",
                    )
                    val_rating = val_result.overall_rating
                except Exception:
                    val_rating = None

                # Crowdedness
                fin = get_latest_financial(item.stock_code)
                fund_pct = fin.fund_hold_pct if fin else None

                # Score change (last 2 records)
                score_change = None
                try:
                    session = get_session()
                    hist = (
                        session.query(ScoreResult)
                        .filter_by(stock_code=item.stock_code)
                        .order_by(ScoreResult.scored_at.desc())
                        .limit(2)
                        .all()
                    )
                    session.close()
                    if len(hist) == 2 and hist[0].total_score is not None and hist[1].total_score is not None:
                        score_change = hist[0].total_score - hist[1].total_score
                except Exception:
                    pass

                rows.append({
                    "股票代码": item.stock_code,
                    "名称": s.get("name", "?"),
                    "环节": seg,
                    "状态": item.status,
                    "评分": total_score,
                    "估值": val_rating,
                    "拥挤度": fund_pct,
                    "变化": score_change,
                })

            df = pd.DataFrame(rows)

            # 应用筛选
            if filter_score:
                df = df[df["评分"] >= 4.0]
            if filter_cheap:
                df = df[df["估值"] == "cheap"]
            if filter_segment != "全部":
                df = df[df["环节"] == filter_segment]

            if df.empty:
                st.info("没有符合筛选条件的股票")
            else:
                # 渲染表格
                display_df = df.copy()
                display_df["评分"] = display_df["评分"].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "N/A")
                display_df["估值"] = display_df["估值"].apply(
                    lambda x: {"cheap": "🟢 低估", "fair": "🟡 合理", "expensive": "🔴 高估"}.get(x, "N/A")
                )
                display_df["拥挤度"] = display_df["拥挤度"].apply(
                    lambda x: f"🔴 {x:.1%}" if pd.notna(x) and x > 0.15 else (f"{x:.1%}" if pd.notna(x) else "N/A")
                )
                display_df["变化"] = display_df["变化"].apply(
                    lambda x: f"📈 +{x:.2f}" if pd.notna(x) and x > 0 else (f"📉 {x:.2f}" if pd.notna(x) and x < 0 else ("➖ 0.00" if pd.notna(x) else "N/A"))
                )
                st.dataframe(display_df, width='stretch', hide_index=True)

            # ── 产业链仓位分布 ──
            st.markdown("---")
            st.subheader("📊 产业链仓位分布")
            if segment_counts:
                segs = list(segment_counts.keys())
                counts = list(segment_counts.values())
                fig = go.Figure(data=[go.Pie(
                    labels=segs,
                    values=counts,
                    hole=0.4,
                    textinfo="label+percent",
                    textfont_size=12,
                )])
                fig.update_layout(
                    margin=dict(t=10, b=10, l=10, r=10),
                    height=250,
                    showlegend=False,
                    paper_bgcolor="rgba(0,0,0,0)",
                )
                st.plotly_chart(fig, width='stretch', key=f"pie_{wl.id}")

            # ── 横向对比雷达图（同环节最多5只）──
            st.markdown("---")
            st.subheader("📈 横向对比")

            # Group by segment, pick segments with ≥2 stocks
            segment_groups = {}
            for _, row in df.iterrows():
                seg = row["环节"]
                if seg not in segment_groups:
                    segment_groups[seg] = []
                segment_groups[seg].append(row["股票代码"])

            valid_segments = {k: v[:5] for k, v in segment_groups.items() if len(v) >= 2}

            if valid_segments:
                compare_seg = st.selectbox("选择环节对比", list(valid_segments.keys()), key=f"cmp_{wl.id}")
                compare_codes = valid_segments[compare_seg]

                # Fetch scores for each
                radar_data = []
                for code in compare_codes:
                    try:
                        sr = scoring.calculate(stock_code=code, segment=compare_seg, report_period="2024Q1")
                        if sr.status == "OK" and sr.breakdown:
                            radar_data.append({
                                "code": code,
                                "name": stock_map.get(code, {}).get("name", code),
                                "breakdown": sr.breakdown,
                            })
                    except Exception:
                        pass

                if len(radar_data) >= 2:
                    fig = go.Figure()
                    colors = ["#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6"]
                    for idx, rd in enumerate(radar_data):
                        metrics = list(rd["breakdown"].keys())
                        scores = [rd["breakdown"][m] for m in metrics if rd["breakdown"][m] is not None]
                        valid_metrics = [m for m in metrics if rd["breakdown"][m] is not None]
                        if len(scores) >= 3:
                            fig.add_trace(go.Scatterpolar(
                                r=scores + [scores[0]],
                                theta=valid_metrics + [valid_metrics[0]],
                                fill='toself',
                                name=rd["name"],
                                line=dict(color=colors[idx % len(colors)]),
                                fillcolor=f'rgba{tuple(list(int(colors[idx % len(colors)][i:i+2], 16) for i in (1, 3, 5)) + [0.1])}',
                            ))
                    fig.update_layout(
                        polar=dict(radialaxis=dict(visible=True, range=[0, 5])),
                        showlegend=True,
                        legend=dict(orientation="h", yanchor="bottom", y=-0.2),
                        margin=dict(t=20, b=40, l=40, r=40),
                        height=350,
                        paper_bgcolor="rgba(0,0,0,0)",
                    )
                    st.plotly_chart(fig, width='stretch', key=f"radar_cmp_{wl.id}")
                else:
                    st.info("对比股票数据不足，无法生成雷达图")
            else:
                st.info("同环节股票不足2只，无法横向对比")

        # ── 添加股票 ──
        st.markdown("---")
        available = [f"{s['code']} {s['name']}" for s in all_stocks]
        selected = st.selectbox("添加股票", available, key=f"add_{wl.id}")
        if st.button("添加", key=f"btn_add_{wl.id}"):
            code = selected.split()[0]
            wm.add_stock(wl.id, code)
            st.rerun()
