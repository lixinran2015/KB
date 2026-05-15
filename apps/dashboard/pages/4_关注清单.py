import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import streamlit as st
from packages.engines.watchlist_manager import WatchlistManager
from packages.config.loader import load_stocks

st.title("📁 关注清单")

wm = WatchlistManager()

# Create new watchlist
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

# List watchlists
wls = wm.list_watchlists()

if not wls:
    st.info("暂无关注组合，请创建一个")
else:
    tabs = st.tabs([wl.name for wl in wls])
    stocks = load_stocks()
    stock_map = {s["code"]: s for s in stocks}

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
                data = []
                for item in items:
                    s = stock_map.get(item.stock_code, {})
                    data.append({
                        "股票代码": item.stock_code,
                        "名称": s.get("name", "?"),
                        "环节": s.get("segment", "?"),
                        "状态": item.status,
                    })
                st.dataframe(data, use_container_width=True)

            # Add stock
            available = [f"{s['code']} {s['name']}" for s in stocks]
            selected = st.selectbox("添加股票", available, key=f"add_{wl.id}")
            if st.button("添加", key=f"btn_add_{wl.id}"):
                code = selected.split()[0]
                wm.add_stock(wl.id, code)
                st.rerun()
