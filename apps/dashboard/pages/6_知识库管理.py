import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import streamlit as st
import pandas as pd
from packages.domain.database import init_db, get_session
from packages.domain.models import (
    IndustryTree, ConceptTag, StockIndustryKB, StockConceptRel
)

st.set_page_config(page_title="知识库管理", layout="wide")

st.title("📚 结构化知识库管理")

init_db()

session = get_session()

try:
    # ── 加载全局数据 ──
    all_industries = session.query(IndustryTree).order_by(IndustryTree.sort).all()
    all_tags = session.query(ConceptTag).order_by(ConceptTag.name).all()
    tag_map = {t.id: t.name for t in all_tags}
    tag_name_to_id = {t.name: t.id for t in all_tags}

    # 构建行业树结构
    industry_by_parent = {}
    for ind in all_industries:
        industry_by_parent.setdefault(ind.parent_id, []).append(ind)

    def get_children(parent_id):
        return industry_by_parent.get(parent_id, [])

    def get_industry_path(ind_id):
        """Return [root, ..., leaf] path names for a leaf industry ID."""
        path = []
        current = next((i for i in all_industries if i.id == ind_id), None)
        while current:
            path.append(current.name)
            current = next((i for i in all_industries if i.id == current.parent_id), None) if current.parent_id else None
        return " → ".join(reversed(path))

    def get_leaf_industries():
        """Return all level=4 industries."""
        return [i for i in all_industries if i.level == 4]

    # ── 页面布局：左中右三栏 ──
    left_col, mid_col, right_col = st.columns([2, 3, 3])

    # ═══════════════════════════════════════════
    # 左栏：行业树 + 概念筛选 + 搜索
    # ═══════════════════════════════════════════
    with left_col:
        st.subheader("🔍 导航")

        # 搜索框
        search_query = st.text_input("搜索（代码/名称/行业/概念）", "", placeholder="输入关键词...")

        st.markdown("---")

        # 按概念筛选
        st.caption("按概念筛选")
        selected_concept = st.selectbox(
            "选择概念标签",
            ["-- 全部 --"] + [t.name for t in all_tags],
            label_visibility="collapsed",
        )

        st.markdown("---")

        # 行业树
        st.caption("行业分类树")

        # Use session_state to track expanded nodes
        if "kb_expanded" not in st.session_state:
            st.session_state.kb_expanded = set()

        def render_tree_node(node, indent=0):
            """Recursively render industry tree node with expand/collapse."""
            children = get_children(node.id)
            has_children = len(children) > 0

            cols = st.columns([1, 6])
            with cols[0]:
                if has_children:
                    is_expanded = node.id in st.session_state.kb_expanded
                    icon = "▼" if is_expanded else "▶"
                    if st.button(icon, key=f"toggle_{node.id}"):
                        if is_expanded:
                            st.session_state.kb_expanded.discard(node.id)
                        else:
                            st.session_state.kb_expanded.add(node.id)
                        st.rerun()
                else:
                    st.write("•")
            with cols[1]:
                label = f"{'　' * indent}**{node.name}**"
                if not has_children:
                    # Leaf node - clickable to filter
                    if st.button(label, key=f"ind_{node.id}"):
                        st.session_state.kb_selected_industry = node.id
                        st.session_state.kb_selected_concept = None
                        st.rerun()
                else:
                    st.markdown(label)

            # Render children if expanded
            if has_children and node.id in st.session_state.kb_expanded:
                for child in children:
                    render_tree_node(child, indent + 1)

        # Render root nodes (parent_id=0)
        roots = get_children(0)
        for root in roots:
            render_tree_node(root)

    # ═══════════════════════════════════════════
    # 中栏：个股列表
    # ═══════════════════════════════════════════
    with mid_col:
        st.subheader("📋 个股列表")

        # Build query
        query = session.query(StockIndustryKB)

        # Apply filters
        filter_desc = []

        # 1. Industry filter
        selected_ind_id = st.session_state.get("kb_selected_industry")
        if selected_ind_id:
            query = query.filter_by(std_industry_id=selected_ind_id)
            ind_name = next((i.name for i in all_industries if i.id == selected_ind_id), "")
            filter_desc.append(f"行业: **{ind_name}**")

        # 2. Concept filter
        if selected_concept and selected_concept != "-- 全部 --":
            concept_id = tag_name_to_id.get(selected_concept)
            if concept_id:
                # Get stock codes related to this concept
                rel_codes = [
                    r.stock_code for r in
                    session.query(StockConceptRel).filter_by(concept_tag_id=concept_id).all()
                ]
                query = query.filter(StockIndustryKB.stock_code.in_(rel_codes))
                filter_desc.append(f"概念: **{selected_concept}**")

        # 3. Search filter
        if search_query.strip():
            q = search_query.strip()
            # Search across code, name, industry name, concept name
            matched_concept_ids = [
                t.id for t in all_tags if q in t.name
            ]
            matched_industry_ids = [
                i.id for i in all_industries if q in i.name
            ]

            concept_stock_codes = []
            if matched_concept_ids:
                concept_stock_codes = [
                    r.stock_code for r in
                    session.query(StockConceptRel)
                    .filter(StockConceptRel.concept_tag_id.in_(matched_concept_ids))
                    .all()
                ]

            query = query.filter(
                (StockIndustryKB.stock_code.contains(q)) |
                (StockIndustryKB.stock_name.contains(q)) |
                (StockIndustryKB.std_industry_id.in_(matched_industry_ids)) |
                (StockIndustryKB.stock_code.in_(concept_stock_codes))
            )
            filter_desc.append(f"搜索: **{q}**")

        stocks = query.all()

        # Show filter info
        if filter_desc:
            st.caption(" | ".join(filter_desc))
        else:
            st.caption("显示全部")

        st.caption(f"共 {len(stocks)} 条记录")

        # Display stock cards
        for s in stocks:
            with st.container(border=True):
                c1, c2 = st.columns([3, 1])
                with c1:
                    st.markdown(f"**{s.stock_name}** `{s.stock_code}`")
                    path = get_industry_path(s.std_industry_id)
                    st.caption(f"🏭 {path}")
                    if s.business_desc:
                        st.caption(f"📝 {s.business_desc[:60]}{'...' if len(s.business_desc) > 60 else ''}")
                    # Show concepts
                    rel_tags = session.query(StockConceptRel).filter_by(stock_code=s.stock_code).all()
                    if rel_tags:
                        tag_names = [tag_map.get(r.concept_tag_id, "?") for r in rel_tags]
                        st.caption("🏷️ " + " · ".join(tag_names))
                with c2:
                    if st.button("编辑", key=f"edit_{s.stock_code}"):
                        st.session_state.kb_editing_stock = s.stock_code
                        st.rerun()

    # ═══════════════════════════════════════════
    # 右栏：个股编辑
    # ═══════════════════════════════════════════
    with right_col:
        st.subheader("✏️ 个股编辑")

        editing_code = st.session_state.get("kb_editing_stock")
        if not editing_code:
            st.info("在左侧列表点击「编辑」按钮选择要编辑的个股")
        else:
            stock_kb = session.query(StockIndustryKB).filter_by(stock_code=editing_code).first()
            if not stock_kb:
                st.error(f"未找到股票: {editing_code}")
                st.session_state.kb_editing_stock = None
            else:
                st.markdown(f"### {stock_kb.stock_name} `{stock_kb.stock_code}`")

                # 1. 修改所属行业（下拉选末级行业）
                leaf_inds = get_leaf_industries()
                leaf_options = {f"{i.name} (ID:{i.id})": i.id for i in leaf_inds}
                current_leaf_label = next(
                    (k for k, v in leaf_options.items() if v == stock_kb.std_industry_id),
                    list(leaf_options.keys())[0] if leaf_options else None
                )
                new_ind_label = st.selectbox(
                    "所属行业（末级）",
                    list(leaf_options.keys()),
                    index=list(leaf_options.keys()).index(current_leaf_label) if current_leaf_label else 0,
                )
                new_ind_id = leaf_options[new_ind_label]

                # 2. 业务简介
                new_desc = st.text_area(
                    "业务简介",
                    stock_kb.business_desc or "",
                    height=100,
                )

                # 3. 概念标签（多选）
                current_rels = session.query(StockConceptRel).filter_by(stock_code=editing_code).all()
                current_tag_ids = {r.concept_tag_id for r in current_rels}
                tag_options = {t.name: t.id for t in all_tags}
                selected_tag_names = st.multiselect(
                    "概念标签",
                    list(tag_options.keys()),
                    default=[name for name, tid in tag_options.items() if tid in current_tag_ids],
                )

                col1, col2 = st.columns(2)
                with col1:
                    if st.button("💾 保存", type="primary"):
                        stock_kb.std_industry_id = new_ind_id
                        stock_kb.business_desc = new_desc

                        # Update concept relations
                        session.query(StockConceptRel).filter_by(stock_code=editing_code).delete()
                        for tag_name in selected_tag_names:
                            tag_id = tag_options[tag_name]
                            session.add(StockConceptRel(
                                stock_code=editing_code,
                                concept_tag_id=tag_id,
                            ))
                        session.commit()
                        st.success("保存成功！")
                        st.rerun()

                with col2:
                    if st.button("取消"):
                        st.session_state.kb_editing_stock = None
                        st.rerun()

finally:
    session.close()
