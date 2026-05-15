import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import streamlit as st
from packages.adapters.mock_adapter import MockAdapter
from packages.engines.trigger_engine import TriggerEngine, TriggerStateMachine
from packages.engines.watchlist_manager import WatchlistManager
from packages.domain.database import get_session
from packages.domain.models import TriggerEvent

st.title("🔔 触发器中心")

# Technical triggers
st.subheader("📈 技术面触发器")
adapter = MockAdapter("stock_300308_technical")
engine = TriggerEngine(adapter=adapter)
result = engine.check(stock_code="300308.SZ", report_period="2024Q1")

if result.triggers:
    for t in result.triggers:
        col1, col2, col3 = st.columns([1, 2, 1])
        with col1:
            priority_color = "🔴" if t["priority"] == "high" else "🟡"
            st.markdown(f"{priority_color} **{t['name']}**")
        with col2:
            st.caption(t["description"])
        with col3:
            category_labels = {"technical": "🔧 技术", "fundamental": "📊 基本面", "event": "📰 事件"}
            st.caption(category_labels.get(t["category"], t["category"]))
else:
    st.info("暂无技术面触发事件")

st.markdown("---")

# Event triggers
st.subheader("📰 事件触发器")
session = get_session()
events = session.query(TriggerEvent).all()
session.close()

if events:
    for ev in events:
        with st.container():
            col1, col2, col3 = st.columns([2, 1, 1])
            with col1:
                st.markdown(f"**{ev.name}**")
                st.caption(ev.description or "")
            with col2:
                st.caption(f"状态: {ev.status}")
            with col3:
                st.caption(f"影响: {ev.impact_score or 'N/A'}")
else:
    st.info("暂无事件触发器，请在下方添加")

# ── 事件影响地图 ──
wm = WatchlistManager()
wls = wm.list_watchlists()
watchlist_codes = set()
for wl in wls:
    for item in wm.get_items(wl.id):
        watchlist_codes.add(item.stock_code)

if events and watchlist_codes:
    st.markdown("---")
    st.subheader("🗺️ 事件影响地图")
    st.caption("影响关注清单中的股票")

    for ev in events:
        if not ev.related_stocks:
            continue
        related = [s.strip() for s in ev.related_stocks.split(",") if s.strip()]
        affected = [code for code in related if code in watchlist_codes]
        if affected:
            impact_emoji = "🔴" if (ev.impact_score or 5) >= 7 else ("🟡" if (ev.impact_score or 5) >= 4 else "🟢")
            with st.container():
                cols = st.columns([2, 3])
                with cols[0]:
                    st.markdown(f"{impact_emoji} **{ev.name}**")
                with cols[1]:
                    for code in affected:
                        st.markdown(f"  - `{code}`", unsafe_allow_html=True)

st.markdown("---")

# Add event trigger
with st.expander("➕ 添加事件触发器"):
    name = st.text_input("事件名称")
    category = st.selectbox("类别", ["policy", "earnings", "merger", "other"])
    description = st.text_area("描述")
    impact = st.slider("影响评分", 1, 10, 5)
    related = st.text_input("关联标的（逗号分隔）")

    if st.button("保存"):
        if name:
            session = get_session()
            ev = TriggerEvent(
                template_id="manual",
                name=name,
                category=category,
                description=description,
                impact_score=impact,
                related_stocks=related,
                status="watching",
            )
            session.add(ev)
            session.commit()
            session.close()
            st.success(f"已添加事件: {name}")
            st.rerun()
        else:
            st.error("请输入事件名称")

st.markdown("---")

# State machine demo
st.subheader("🔄 状态机演示")
status = st.selectbox("选择初始状态", ["watching", "triggered", "confirmed", "expired"])
sm = TriggerStateMachine(state=status)

col1, col2, col3 = st.columns(3)
with col1:
    if st.button("触发"):
        sm.trigger()
        st.write(f"状态: {sm.state}")
with col2:
    if st.button("确认"):
        sm.confirm()
        st.write(f"状态: {sm.state}")
with col3:
    if st.button("过期"):
        sm.expire()
        st.write(f"状态: {sm.state}")
