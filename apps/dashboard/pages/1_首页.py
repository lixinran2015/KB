import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import streamlit as st
from packages.domain.database import init_db
from packages.engines.watchlist_manager import WatchlistManager
from packages.config.loader import load_stocks

st.title("📊 Stock KB 首页")

init_db()

# Dynamic metrics
from packages.domain.database import get_session
from packages.domain.models import StockFinancial, ScoreResult

session = get_session()
try:
    latest_period = session.query(StockFinancial.report_period).distinct().order_by(StockFinancial.report_period.desc()).first()
    latest_period = latest_period[0] if latest_period else "未同步"
    score_count = session.query(ScoreResult).count()
finally:
    session.close()

wm = WatchlistManager()
wls = wm.list_watchlists()

# Data health status
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("财务数据", latest_period, "已同步")
with col2:
    st.metric("股票数量", len(load_stocks()))
with col3:
    st.metric("关注组合", len(wls))
with col4:
    st.metric("评分记录", score_count)

st.markdown("---")

# Run daily update button
if st.button("▶️ 运行日常更新", type="primary"):
    with st.spinner("正在更新..."):
        import subprocess
        result = subprocess.run(
            [sys.executable, "-m", "apps.cli.main", "daily"],
            capture_output=True,
            text=True,
        )
        st.code(result.stdout + result.stderr)
        if result.returncode == 0:
            st.success("更新完成！")
        else:
            st.error("更新失败")

st.markdown("---")

# Watchlists
st.subheader("📁 我的关注清单")

if not wls:
    st.info("暂无关注清单，请在左侧导航栏进入“关注清单”页面创建")
else:
    # Limit display to avoid crowding
    display_wls = wls[:8]
    cols = st.columns(min(len(display_wls), 4))
    for i, wl in enumerate(display_wls):
        with cols[i % 4]:
            items = wm.get_items(wl.id)
            st.metric(wl.name, f"{len(items)}只")
    if len(wls) > 8:
        st.caption(f"... 还有 {len(wls) - 8} 个组合")

st.markdown("---")

# Recent triggers
st.subheader("🔔 最新触发器")
from packages.domain.database import get_session
from packages.domain.models import TriggerEvent
session = get_session()
recent_events = session.query(TriggerEvent).order_by(TriggerEvent.created_at.desc()).limit(5).all()
session.close()

if recent_events:
    for ev in recent_events:
        with st.container():
            col1, col2, col3 = st.columns([2, 1, 1])
            with col1:
                st.markdown(f"**{ev.name}**")
                if ev.description:
                    st.caption(ev.description[:60] + "..." if len(ev.description or "") > 60 else ev.description)
            with col2:
                status_colors = {"watching": "🟡", "triggered": "🔴", "confirmed": "🟢", "expired": "⚪"}
                st.caption(f"{status_colors.get(ev.status, '⚪')} {ev.status}")
            with col3:
                if ev.impact_score:
                    st.caption(f"影响: {'🔥' * min(ev.impact_score, 5)}")
        st.markdown("---")
else:
    st.info("暂无触发事件，请在触发器中心添加或运行 check-triggers")
