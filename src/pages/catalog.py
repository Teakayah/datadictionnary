"""Catalog Browser UI rendering logic.

Provides the main explorer interface for navigating catalogs, schemas, and tables.
"""
from __future__ import annotations
import streamlit as st
import logging
import html as _html
from src.i18n import t
from src.ui.cards._shared import _dq_grade, _render_empty_state
from src.db.queries import get_authorized_tables

def render_catalog_browser(groups: list[str]) -> None:
    """Renders the catalog browser UI.

    Displays a searchable tree-like structure of catalogs and schemas containing tables
    that the current user is authorized to view.

    Args:
        groups: A list of Entra ID group IDs the current user belongs to.
    """
    st.html(f'''
    <div class="dd-search-hero">
      <div class="dd-eyebrow">{_html.escape(t("catalog.eyebrow"))}</div>
      <h1>{_html.escape(t("catalog.hero_title"))}</h1>
      <p class="lead">{_html.escape(t("catalog.hero_subtitle"))}</p>
    </div>
    ''')

    with st.expander(t("help.catalog_expander")):
        st.markdown(t("help.catalog_content"))

    try:
        all_data = get_authorized_tables(groups)
        if all_data is None or all_data.empty or 'catalog_name' not in all_data.columns:
            _render_empty_state("📁", t("catalog.no_catalogs"))
            return

        catalogs = sorted(all_data['catalog_name'].unique())

        # ⚡ Bolt: Replace inner groupby loop with pre-computed dictionary mapping to prevent O(N^2) performance bottleneck
        _global_dq = {}
        if "dq_score" in all_data.columns:
            # Fix: Use composite key to prevent overriding tables with same name in different schemas
            _global_dq = dict(zip(zip(all_data["catalog_name"], all_data["schema_name"], all_data["table_name"]), all_data["dq_score"]))

        # ⚡ Bolt: Prefer agg(list) over apply(list) for faster list aggregation in pandas groupby
        _grouped_tables = all_data.drop_duplicates(subset=['catalog_name', 'schema_name', 'table_name']).groupby(['catalog_name', 'schema_name'])['table_name'].agg(list).to_dict()

        # ⚡ Bolt: Pre-compute schemas by catalog to avoid expensive DataFrame slicing (O(N^2)) in the render loop below.
        _schemas_by_cat = {}
        for c, s in _grouped_tables:
            if c not in _schemas_by_cat:
                _schemas_by_cat[c] = set()
            _schemas_by_cat[c].add(s)

        # Simple Tree Implementation using Streamlit expanders
        for cat in catalogs:
            with st.expander(t("common.folder_link", name=cat), expanded=False):
                schemas = sorted(_schemas_by_cat.get(cat, set()))

                for sch in schemas:
                    st.html(f'<div style="margin-left: 20px; font-weight: 500; color: var(--ink-60); margin-top: 10px; margin-bottom: 5px;">{_html.escape(t("common.open_folder_link", name=str(sch)))}</div>')
                    all_tables_in_sch = sorted(_grouped_tables.get((cat, sch), []))

                    # ⚡ Bolt: Apply hard cap to prevent main-thread blocking on large schemas
                    tables = all_tables_in_sch[:50]
                    is_truncated = len(all_tables_in_sch) > 50

                    # Columns for tables to make it more compact
                    t_cols = st.columns(3)
                    for i, tbl in enumerate(tables):
                        with t_cols[i % 3]:
                            full_n = f"{cat}.{sch}.{tbl}"
                            _grade, _gcls = _dq_grade(_global_dq.get((cat, sch, tbl), ""))
                            # Show grade badge above the button via markdown, then the clickable button
                            st.html(
                                f'<div style="display:flex;align-items:center;gap:6px;margin-bottom:2px;">'
                                f'<span class="dd-dq-badge {_html.escape(_gcls)}" title="{_html.escape(t("catalog.completeness_grade", grade=_grade))}">{_html.escape(_grade)}</span>'
                                f'<span style="font-family:var(--font-mono);font-size:12px;color:var(--ink-60);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{_html.escape(tbl)}</span>'
                                f'</div>'
                            )
                            if st.button(t("common.file_link", name=tbl), key=f"tree_{full_n}", help=t("catalog.tree_help"), use_container_width=True):
                                st.query_params["tab"] = "search"
                                st.session_state["dd_search_override"] = tbl
                                st.session_state["dd_nav_select"] = full_n
                                st.rerun()
                    if is_truncated:
                        st.markdown(f"<div style='margin-left: 20px; font-size: 12px; color: var(--ink-40); margin-top: 8px;'>{_html.escape(t('catalog.more_tables', count=len(all_tables_in_sch) - 50))}</div>", unsafe_allow_html=True)
    except Exception as e:
        logging.error("Error in catalog browser: %s", e)
        st.error(t("catalog.load_error"))
