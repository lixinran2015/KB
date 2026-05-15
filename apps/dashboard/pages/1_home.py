import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import streamlit as st
from packages.domain.database import init_db
from packages.engines.watchlist_manager import WatchlistManager
from packages.config.loader import load_stocks

st.title("📊 Stock KB 首页")

init_db()

# Data health status
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("财务数据", "2024Q1", "已同步")
with col2:
    st.metric("股票数量", len(load_stocks()))
with col3:
    st.metric("关注组合", 0)
with col4:
    st.metric("缓存命中", "--")

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
wm = WatchlistManager()
wls = wm.list_watchlists()

if not wls:
    st.info("暂无关注清单，请在左侧导航栏进入“关注清单”页面创建")
else:
    cols = st.columns(len(wls))
    for i, wl in enumerate(wls):
        with cols[i]:
            items = wm.get_items(wl.id)
            st.metric(wl.name, f"{len(items)}只")

st.markdown("---")

# Recent triggers
st.subheader("🔔 最新触发器")
st.info("触发器功能即将上线")
