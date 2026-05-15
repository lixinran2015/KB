import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st

st.set_page_config(
    page_title="Stock KB",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.sidebar.title("Stock KB")
st.sidebar.markdown("---")
st.sidebar.info("个人股票知识库 v0.1.0")
