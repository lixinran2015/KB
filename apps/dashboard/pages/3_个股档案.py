import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import streamlit as st
from datetime import datetime, timedelta
import pandas as pd
import plotly.graph_objects as go
from packages.config.loader import load_stocks
from packages.domain.database import get_session, get_latest_financial
from packages.domain.models import QualitativeScore, ScoreResult
from packages.engines.scoring_engine import ScoringEngine
from packages.engines.valuation_engine import ValuationEngine
from packages.engines.watchlist_manager import WatchlistManager
from packages.adapters.akshare_adapter import AKShareAdapter
from packages.adapters.mock_adapter import MockAdapter

st.title("📋 个股档案")

stocks = load_stocks()
stock_options = {f"{s['code']} {s['name']}": s for s in stocks}

selected = st.selectbox("选择股票", list(stock_options.keys()))
stock = stock_options[selected]

# Score + Valuation — use AKShare if available, fall back to mock for testing
try:
    adapter = AKShareAdapter()
except Exception:
    adapter = MockAdapter("stock_300308_q1_2024")

scoring = ScoringEngine(adapter=adapter)
valuation = ValuationEngine(adapter=adapter)

with st.spinner("计算评分与估值..."):
    result = scoring.calculate(
        stock_code=stock["code"],
        segment=stock["segment"],
        report_period="2024Q1",
    )
    val_result = valuation.calculate(
        stock_code=stock["code"],
        segment=stock["segment"],
        report_period="2024Q1",
    )

# ── 顶部信息栏 ──
col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
with col1:
    st.metric("综合评分", result.total_score or "N/A")
with col2:
    st.metric("环节", stock["segment"])
with col3:
    st.metric("风格", stock["style"])
with col4:
    st.metric("估值评级", val_result.overall_rating or "N/A")

# Crowdedness warning
fin = get_latest_financial(stock["code"])
if fin and fin.fund_hold_pct and fin.fund_hold_pct > 0.15:
    st.error(f"🔴 拥挤度警告：公募基金持仓 {fin.fund_hold_pct:.1%}，超过 15% 阈值")

if result.status == "OK":
    st.success(f"✅ 评分正常")

    # ── 雷达图 + 估值矩阵 左右布局 ──
    st.markdown("---")
    left, right = st.columns([3, 2])

    with left:
        st.subheader("📊 财务评分雷达")
        radar_metrics = []
        radar_scores = []
        for name, score in result.breakdown.items():
            if score is not None:
                radar_metrics.append(name)
                radar_scores.append(float(score))

        if len(radar_metrics) >= 3:
            fig = go.Figure(data=go.Scatterpolar(
                r=radar_scores + [radar_scores[0]],
                theta=radar_metrics + [radar_metrics[0]],
                fill='toself',
                fillcolor='rgba(59, 130, 246, 0.2)',
                line=dict(color='#3b82f6', width=2),
                name=stock["name"],
            ))
            fig.update_layout(
                polar=dict(
                    radialaxis=dict(visible=True, range=[0, 5], tickfont=dict(size=10)),
                    angularaxis=dict(tickfont=dict(size=12)),
                ),
                showlegend=False,
                margin=dict(t=20, b=20, l=40, r=40),
                height=350,
                paper_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig, width='stretch', key=f"radar_{stock['code']}")
        else:
            st.info("数据不足，无法生成雷达图")

    with right:
        st.subheader("📈 估值矩阵")
        val_data = []
        for metric, rating in val_result.ratings.items():
            if rating is not None:
                emoji = {"cheap": "🟢", "fair": "🟡", "expensive": "🔴"}.get(rating, "⚪")
                val_data.append({"指标": metric.upper(), "评级": f"{emoji} {rating}", "原始值": val_result.raw_values.get(metric, "N/A")})
        if val_data:
            st.dataframe(pd.DataFrame(val_data), width='stretch', hide_index=True)
        else:
            st.info("暂无估值数据")

    # ── 决策框架：评分 + 估值 → 行动建议 ──
    st.markdown("---")
    st.subheader("💡 决策建议")

    total = result.total_score or 0
    val_rating = val_result.overall_rating or "unknown"

    if total >= 4.5 and val_rating == "cheap":
        st.success("🟢 **强烈关注** — 基本面优秀且估值偏低，可考虑建仓")
        st.caption("典型场景：业绩超预期 + 市场情绪低迷导致估值压缩")
    elif total >= 4.0 and val_rating == "expensive":
        st.warning("🟡 **观望** — 基本面优秀但估值偏高，建议等回调")
        st.caption("典型场景：业绩好但股价已充分反映，等PE回到合理区间再介入")
    elif total >= 4.0 and val_rating == "fair":
        st.info("🟡 **关注** — 基本面优秀，估值合理，等催化剂")
        st.caption("典型场景：基本面扎实，但缺乏短期催化，可纳入观察")
    elif total >= 3.0:
        st.warning("🟠 **谨慎** — 基本面一般，暂不核心关注")
    else:
        st.error("🔴 **回避** — 基本面较弱，建议回避")

    # 同环节排名
    st.caption(f"环节排名: {stock['segment']} | 综合评分: {total}")

    # ── 分项评分表格 ──
    st.markdown("---")
    st.subheader("📋 分项评分明细")
    breakdown_data = []
    for name, score in result.breakdown.items():
        if score is not None:
            raw = result.raw_values.get(name, "N/A")
            breakdown_data.append({"指标": name, "得分": score, "原始值": raw})

    if breakdown_data:
        df = pd.DataFrame(breakdown_data)
        st.dataframe(df, width='stretch')

    # ── 定性评分 ──
    if result.qualitative_score is not None:
        st.subheader("🎯 定性评分")
        st.metric("定性评分", result.qualitative_score)

        session = get_session()
        qs = session.query(QualitativeScore).filter_by(stock_code=stock["code"]).first()
        session.close()
        if qs:
            qual_data = []
            if qs.global_ranking is not None:
                qual_data.append({"指标": "全球排名", "得分": qs.global_ranking})
            if qs.localization_potential is not None:
                qual_data.append({"指标": "国产替代潜力", "得分": qs.localization_potential})
            if qs.customer_health is not None:
                qual_data.append({"指标": "客户健康度", "得分": qs.customer_health})
            if qs.tam_usd_billion is not None:
                qual_data.append({"指标": "TAM (十亿美元)", "数值": qs.tam_usd_billion})
            if qs.current_penetration is not None:
                qual_data.append({"指标": "当前渗透率", "数值": f"{qs.current_penetration:.0%}"})
            if qual_data:
                st.dataframe(pd.DataFrame(qual_data), width='stretch', hide_index=True)

            # Stale data warning
            if qs.last_updated:
                try:
                    updated = datetime.strptime(str(qs.last_updated), "%Y-%m-%d")
                    days_old = (datetime.now() - updated).days
                    if days_old > 90:
                        st.warning(f"⚠️ 定性评分已 {days_old} 天未更新，建议复核")
                except ValueError:
                    pass

    # ── 历史评分趋势 ──
    st.markdown("---")
    st.subheader("📈 历史评分趋势")
    session = get_session()
    try:
        history = (
            session.query(ScoreResult)
            .filter_by(stock_code=stock["code"])
            .order_by(ScoreResult.scored_at.asc())
            .limit(20)
            .all()
        )
    finally:
        session.close()

    if history:
        hist_df = pd.DataFrame([{
            "时间": h.scored_at.strftime("%m-%d %H:%M") if h.scored_at else "",
            "综合评分": h.total_score,
            "财务评分": h.financial_score,
        } for h in history if h.total_score is not None])
        if not hist_df.empty:
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=hist_df["时间"], y=hist_df["综合评分"],
                mode='lines+markers', name='综合评分',
                line=dict(color='#3b82f6', width=2),
            ))
            fig.add_trace(go.Scatter(
                x=hist_df["时间"], y=hist_df["财务评分"],
                mode='lines+markers', name='财务评分',
                line=dict(color='#10b981', width=2),
            ))
            fig.update_layout(
                margin=dict(t=10, b=10, l=10, r=10),
                height=250,
                paper_bgcolor="rgba(0,0,0,0)",
                legend=dict(orientation="h", yanchor="bottom", y=-0.3),
                xaxis=dict(showgrid=False),
                yaxis=dict(showgrid=True, gridcolor='rgba(128,128,128,0.1)', range=[0, 5]),
            )
            st.plotly_chart(fig, width='stretch', key=f"history_{stock['code']}")
        else:
            st.info("暂无历史评分数据")
    else:
        st.info("暂无历史评分数据")

else:
    st.warning(f"⚠️ {result.message}")

# ── 加入关注清单 ──
st.markdown("---")
wm = WatchlistManager()
wls = wm.list_watchlists()

if wls:
    col1, col2 = st.columns([1, 2])
    with col1:
        wl_name = st.selectbox("选择组合", [w.name for w in wls])
    with col2:
        if st.button("➕ 加入关注清单"):
            wl = next(w for w in wls if w.name == wl_name)
            wm.add_stock(wl.id, stock["code"], status="watching")
            st.success(f"已加入 {wl_name}")
else:
    st.info("暂无关注清单，请先创建")
