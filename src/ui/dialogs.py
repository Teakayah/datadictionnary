import streamlit as st
import pandas as pd
import re
import logging
import time
from src.i18n import t
from src.ui.css import VIS_WIDE_CSS
from src.config import CATALOG_CACHE
from src.db.duckdb_adapter import _duckdb_available


@st.dialog(t("detail.edit_table"), width="large")
def render_table_metadata_editor(
    table_full_name: str, current_desc: str, current_steward: str, save_table_metadata
):
    """Editor for table-level metadata (description, steward)."""
    st.markdown(f"**{table_full_name}**")

    new_desc = st.text_area(
        t("detail.table_description"), value=current_desc, height=150
    )
    new_stew = st.text_input(t("detail.steward_email"), value=current_steward)

    c1, c2 = st.columns([1, 1])
    with c1:
        if st.button(t("common.save"), type="primary", use_container_width=True):
            try:
                save_table_metadata(
                    table_full_name, description=new_desc, steward_email=new_stew
                )
                st.success(t("common.saved"))
                time.sleep(0.5)
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")
    with c2:
        if st.button(t("common.cancel"), use_container_width=True):
            st.rerun()


@st.dialog(t("detail.data_sample"), width="large")
def render_data_sample(
    table_full_name: str, get_authorized_tables, DEMO_DATA, run_query
):
    st.markdown(VIS_WIDE_CSS, unsafe_allow_html=True)
    st.markdown(f"**{table_full_name}**")

    # Security: check permission even though UI usually prevents this call
    groups = (
        tuple(st.session_state.get("user_groups", []))
        if st.session_state.get("user_groups")
        else ("none",)
    )
    active_group = st.session_state.get("group_filter")
    query_groups = (active_group,) if active_group else groups
    _auth_df = get_authorized_tables(query_groups)
    _allowed = (
        set(_auth_df["full_name"].tolist())
        if _auth_df is not None and not _auth_df.empty
        else set()
    )
    if table_full_name not in _allowed:
        st.error(t("detail.unauthorized"))
        return

    try:
        if not re.match(
            r"^[a-zA-Z0-9_]+\.[a-zA-Z0-9_]+\.[a-zA-Z0-9_]+$", table_full_name
        ):
            st.error(t("common.error"))
            return
        if DEMO_DATA:
            df = pd.DataFrame({"id": [1, 2, 3], "status": ["NEW", "SHIPPED", "CLOSED"]})
        elif _duckdb_available():
            # DuckDB file is ATTACHed as CATALOG_CACHE; actual row data lives at
            # CATALOG_CACHE.<schema>.<table> — strip the Databricks Unity Catalog prefix.
            _parts = table_full_name.split(".")
            if len(_parts) == 3:
                _, _sch, _tbl = _parts
                _sample_query = (
                    f'SELECT * FROM {CATALOG_CACHE}."{_sch}"."{_tbl}" LIMIT 100'  # nosec B608
                )
                df = run_query(_sample_query)
            else:
                st.info(t("detail.preview_not_available"))
                return
        else:
            query = f"SELECT * FROM {table_full_name} LIMIT 100"  # nosec B608
            df = run_query(query)
        if df is not None and not df.empty:
            # Height is controlled by VIS_WIDE_CSS (calc(95vh - 190px)) so
            # the grid always fills the dialog regardless of viewport size.
            # Pass a generous fixed height so Streamlit allocates enough iframe
            # space; CSS then stretches it to the actual available area.
            st.dataframe(df, use_container_width=True, height=2000)
        else:
            st.info(t("detail.preview_needs_data"))
    except Exception as e:
        logging.error(
            "Error fetching data sample for %s: %s", table_full_name, e, exc_info=True
        )
        st.error(t("detail.preview_error"))
