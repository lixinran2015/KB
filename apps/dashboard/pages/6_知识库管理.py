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

        # ── 行业分类树（新版 v2） ──
        st.caption("行业分类树")

        # Pre-compute stock counts for all leaf industries
        from sqlalchemy import func
        stock_counts = {
            row[0]: row[1]
            for row in session.query(
                StockIndustryKB.std_industry_id,
                func.count(StockIndustryKB.stock_code)
            ).filter(StockIndustryKB.std_industry_id.isnot(None))
            .group_by(StockIndustryKB.std_industry_id)
            .all()
        }

        def get_all_leaf_ids(node_id):
            """Recursively get all leaf node IDs under a given node."""
            children = get_children(node_id)
            if not children:
                return [node_id]
            result = []
            for child in children:
                result.extend(get_all_leaf_ids(child.id))
            return result

        def get_node_path(node_id):
            """Return path from root to this node as list of names."""
            path = []
            current = next((i for i in all_industries if i.id == node_id), None)
            while current:
                path.append(current.name)
                current = next((i for i in all_industries if i.id == current.parent_id), None) if current.parent_id else None
            return list(reversed(path))

        def render_leaf_pill(node, parent_name=None):
            """Render a leaf node as a compact pill-style button."""
            leaf_count = stock_counts.get(node.id, 0)
            is_selected = st.session_state.get("kb_selected_industry") == node.id

            # Build label: name + count, with selection indicator
            label = f"{'● ' if is_selected else ''}{node.name} ({leaf_count})"
            btn_type = "primary" if is_selected else "secondary"

            if st.button(
                label,
                key=f"leaf_{node.id}",
                type=btn_type,
                help=parent_name or "点击筛选该行业",
            ):
                st.session_state.kb_selected_industry = node.id
                st.session_state.kb_selected_concept = None
                st.rerun()

        # Render each root as an expander
        roots = get_children(0)
        for root in roots:
            leaf_ids = get_all_leaf_ids(root.id)
            total_stocks = sum(stock_counts.get(lid, 0) for lid in leaf_ids)
            root_label = f"{root.name} ({total_stocks})"

            with st.expander(root_label, expanded=False):
                lvl2_nodes = get_children(root.id)
                if not lvl2_nodes:
                    st.caption("暂无子分类")
                    continue

                for idx2, lvl2 in enumerate(lvl2_nodes):
                    # L2: Section header with top border (except first)
                    lvl2_leaf_ids = get_all_leaf_ids(lvl2.id)
                    lvl2_count = sum(stock_counts.get(lid, 0) for lid in lvl2_leaf_ids)
                    border_style = "border-top: 1px solid #e0e0e0; margin-top: 10px; padding-top: 8px;" if idx2 > 0 else ""
                    st.markdown(
                        f"<div style='{border_style} font-weight: 700; font-size: 1.05em; color: #222;'>"
                        f"{lvl2.name} "
                        f"<span style='color: #999; font-size: 0.8em; font-weight: 400;'>({lvl2_count})</span>"
                        f"</div>",
                        unsafe_allow_html=True
                    )

                    # Collect leaves under this L2
                    lvl3_nodes = get_children(lvl2.id)
                    if not lvl3_nodes:
                        continue

                    # Group leaves by their L3 parent
                    l3_groups = []  # [(l3_node, [leaf_nodes]), ...]
                    orphan_leaves = []  # L3 nodes that are themselves leaves

                    for lvl3 in lvl3_nodes:
                        lvl4_nodes = get_children(lvl3.id)
                        real_leaves = [l4 for l4 in lvl4_nodes if not get_children(l4.id)] if lvl4_nodes else []

                        if real_leaves:
                            l3_groups.append((lvl3, real_leaves))
                        elif not lvl4_nodes:
                            # lvl3 itself is a leaf
                            orphan_leaves.append(lvl3)

                    # Render orphan leaves (L3 that are leaves) first, in a compact grid
                    if orphan_leaves:
                        cols = st.columns(min(2, len(orphan_leaves)))
                        for i, leaf in enumerate(orphan_leaves):
                            with cols[i % len(cols)]:
                                render_leaf_pill(leaf)

                    # Render L3 groups
                    for lvl3, leaves in l3_groups:
                        # L3 sub-header
                        st.markdown(
                            f"<div style='margin: 6px 0 4px 4px; padding: 2px 6px; "
                            f"background: #f5f5f5; border-radius: 4px; display: inline-block; "
                            f"font-size: 0.85em; color: #666;'>"
                            f"{lvl3.name}"
                            f"</div>",
                            unsafe_allow_html=True
                        )

                        # Leaves in a 2-column grid under this L3
                        if leaves:
                            leaf_cols = st.columns(min(2, len(leaves)))
                            for i, leaf in enumerate(leaves):
                                with leaf_cols[i % len(leaf_cols)]:
                                    render_leaf_pill(leaf, parent_name=lvl3.name)

    # ═══════════════════════════════════════════
    # 中栏：个股列表
    # ═══════════════════════════════════════════
    with mid_col:
        st.subheader("📋 个股列表")

        # Determine if any filter is active
        selected_ind_id = st.session_state.get("kb_selected_industry")
        has_concept_filter = selected_concept and selected_concept != "-- 全部 --"
        has_search = search_query.strip() != ""
        has_active_filter = selected_ind_id or has_concept_filter or has_search

        if not has_active_filter:
            st.info("👈 请在左侧选择行业分类、概念标签，或输入搜索关键词")
            st.caption("当前未设置筛选条件，个股列表已隐藏")
        else:
            # Build query
            query = session.query(StockIndustryKB)

            # Apply filters
            filter_desc = []

            # 1. Industry filter
            if selected_ind_id:
                query = query.filter_by(std_industry_id=selected_ind_id)
                ind_name = next((i.name for i in all_industries if i.id == selected_ind_id), "")
                filter_desc.append(f"行业: **{ind_name}**")

            # 2. Concept filter
            if has_concept_filter:
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
            if has_search:
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
            st.caption(" | ".join(filter_desc))
            st.caption(f"共 {len(stocks)} 条记录")

            if not stocks:
                st.warning("未找到符合条件的个股")
            else:
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
