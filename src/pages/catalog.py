from __future__ import annotations
import streamlit as st
import logging
import html as _html
from src.i18n import t
from src.ui.cards._shared import _dq_grade

def render_catalog_browser(groups, get_authorized_tables_fn):
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
        all_data = get_authorized_tables_fn(groups)
        if all_data is None or all_data.empty or 'catalog_name' not in all_data.columns:
            st.info(t("catalog.no_catalogs"))
            return

        catalogs = sorted(all_data['catalog_name'].unique().tolist())

        # ⚡ Bolt: Replace inner groupby loop with pre-computed dictionary mapping to prevent O(N^2) performance bottleneck
        _global_dq = {}
        if "dq_score" in all_data.columns:
            # Fix: Use composite key to prevent overriding tables with same name in different schemas
            _global_dq = dict(zip(zip(all_data["catalog_name"], all_data["schema_name"], all_data["table_name"]), all_data["dq_score"]))

        _grouped_tables = all_data.groupby(['catalog_name', 'schema_name'])['table_name'].unique().apply(list).to_dict()

        # ⚡ Bolt: Pre-compute schemas by catalog to avoid expensive DataFrame slicing (O(N^2)) in the render loop below.
        _schemas_by_cat = {}
        for c, s in _grouped_tables.keys():
            if c not in _schemas_by_cat:
                _schemas_by_cat[c] = set()
            _schemas_by_cat[c].add(s)

        # Simple Tree Implementation using Streamlit expanders
        for cat in catalogs:
            with st.expander(f"📁 {cat}", expanded=False):
                schemas = sorted(list(_schemas_by_cat.get(cat, set())))

                for sch in schemas:
                    st.markdown(f"&emsp; :gray[**📂 {sch}**]")
                    tables = sorted(_grouped_tables.get((cat, sch), []))

                    # Columns for tables to make it more compact
                    t_cols = st.columns(3)
                    for i, tbl in enumerate(tables):
                        with t_cols[i % 3]:
                            full_n = f"{cat}.{sch}.{tbl}"
                            _grade, _gcls = _dq_grade(_global_dq.get((cat, sch, tbl), ""))
                            # Show grade badge above the button via markdown, then the clickable button
                            st.html(
                                f'<div style="display:flex;align-items:center;gap:6px;margin-bottom:2px;">'
                                f'<span class="dd-dq-badge {_html.escape(_gcls)}" title="Completeness grade {_html.escape(_grade)}">{_html.escape(_grade)}</span>'
                                f'<span style="font-family:var(--font-mono);font-size:12px;color:var(--ink-60);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{_html.escape(tbl)}</span>'
                                f'</div>'
                            )
                            if st.button(f"📄 {tbl}", key=f"tree_{full_n}", help=t("catalog.tree_help"), use_container_width=True):
                                st.query_params["tab"] = "search"
                                st.session_state["dd_search_override"] = tbl
                                st.session_state["dd_nav_select"] = full_n
                                st.rerun()
    except Exception as e:
        logging.error("Error in catalog browser: %s", e)
        st.error(t("catalog.load_error"))
