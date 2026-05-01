import streamlit as st
import logging
import html as _html
from src.i18n import t
from src.ui.cards import _dq_grade

def render_catalog_browser(groups, get_authorized_tables_fn):
    st.markdown(f'''
    <div class="dd-search-hero">
      <div class="dd-eyebrow">{t("catalog.eyebrow")}</div>
      <h1>{t("catalog.hero_title")}</h1>
      <p class="lead">{t("catalog.hero_subtitle")}</p>
    </div>
    ''', unsafe_allow_html=True)

    try:
        all_data = get_authorized_tables_fn(groups)
        if all_data is None or all_data.empty or 'catalog_name' not in all_data.columns:
            st.info(t("catalog.no_catalogs"))
            return

        catalogs = sorted(all_data['catalog_name'].unique().tolist())

        # Simple Tree Implementation using Streamlit expanders
        for cat in catalogs:
            with st.expander(f"📁 {cat}", expanded=False):
                cat_data = all_data[all_data['catalog_name'] == cat]
                # Group by schema_name to avoid O(N^2) dataframe filtering
                for sch, sch_data in cat_data.groupby('schema_name'):
                    st.markdown(f'<div style="margin-left: 20px; font-weight: 500; color: var(--ink-60); margin-top: 10px; margin-bottom: 5px;">📂 {sch}</div>', unsafe_allow_html=True)
                    _dq_lookup = dict(zip(sch_data["table_name"], sch_data["dq_score"])) if "dq_score" in sch_data.columns else {}
                    tables = sorted(sch_data['table_name'].unique().tolist())

                    # Columns for tables to make it more compact
                    t_cols = st.columns(3)
                    for i, tbl in enumerate(tables):
                        with t_cols[i % 3]:
                            full_n = f"{cat}.{sch}.{tbl}"
                            _grade, _gcls = _dq_grade(_dq_lookup.get(tbl, ""))
                            # Show grade badge above the button via markdown, then the clickable button
                            st.markdown(
                                f'<div style="display:flex;align-items:center;gap:6px;margin-bottom:2px;">'
                                f'<span class="dd-dq-badge {_gcls}" title="Completeness grade {_grade}">{_grade}</span>'
                                f'<span style="font-family:var(--font-mono);font-size:12px;color:var(--ink-60);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{_html.escape(tbl)}</span>'
                                f'</div>',
                                unsafe_allow_html=True,
                            )
                            if st.button(f"📄 {tbl}", key=f"tree_{full_n}", use_container_width=True):
                                st.query_params["tab"] = "search"
                                st.session_state["dd_search_override"] = tbl
                                st.session_state["dd_nav_select"] = full_n
                                st.rerun()
    except Exception as e:
        logging.error("Error in catalog browser: %s", e)
        st.error(t("catalog.load_error"))
