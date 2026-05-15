import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import streamlit as st
import pandas as pd
from packages.config.loader import load_stocks
from packages.domain.database import get_session
from packages.domain.models import QualitativeScore
from packages.engines.scoring_engine import ScoringEngine
from packages.engines.watchlist_manager import WatchlistManager
from packages.adapters.akshare_adapter import AKShareAdapter
from packages.adapters.mock_adapter import MockAdapter

st.title("📋 个股档案")

stocks = load_stocks()
stock_options = {f"{s['code']} {s['name']}": s for s in stocks}

selected = st.selectbox("选择股票", list(stock_options.keys()))
stock = stock_options[selected]

# Score — use AKShare if available, fall back to mock for testing
try:
    adapter = AKShareAdapter()
except Exception:
    adapter = MockAdapter("stock_300308_q1_2024")
engine = ScoringEngine(adapter=adapter)

with st.spinner("计算评分..."):
    result = engine.calculate(
        stock_code=stock["code"],
        segment=stock["segment"],
        report_period="2024Q1",
    )

col1, col2, col3 = st.columns([1, 1, 1])
with col1:
    st.metric("综合评分", result.total_score or "N/A")
with col2:
    st.metric("环节", stock["segment"])
with col3:
    st.metric("风格", stock["style"])

if result.status == "OK":
    st.success(f"✅ 评分正常")

    # Breakdown
    st.subheader("📊 分项评分")
    breakdown_data = []
    for name, score in result.breakdown.items():
        if score is not None:
            raw = result.raw_values.get(name, "N/A")
            breakdown_data.append({"指标": name, "得分": score, "原始值": raw})

    if breakdown_data:
        df = pd.DataFrame(breakdown_data)
        st.dataframe(df, width='stretch')

    # Qualitative score
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
                st.dataframe(pd.DataFrame(qual_data), width='stretch')

    # Action recommendation
    st.subheader("💡 建议行动")
    if result.total_score >= 4.5:
        st.info("基本面优秀，建议关注")
    elif result.total_score >= 4.0:
        st.info("基本面良好，可进一步研究")
    elif result.total_score >= 3.0:
        st.warning("基本面一般，谨慎对待")
    else:
        st.error("基本面较弱，建议回避")

else:
    st.warning(f"⚠️ {result.message}")

# Add to watchlist
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
