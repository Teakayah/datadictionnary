from __future__ import annotations
"""Table-detail modal dialogs.

These are consumed exclusively by the search page's table detail panel
(``src/pages/search.py``). They live in cards/ rather than alongside the
search page because they share visual idioms (and CSS) with the rest of
the cards/ rendering surface, and because callers historically imported
them from ``src.ui.cards``.

- ``render_table_metadata_editor`` — table description + steward editor
- ``render_data_sample``           — top-100-rows preview
"""


import logging
import re

import pandas as pd
import streamlit as st

from src.audit import save_table_metadata
from src.config import CATALOG_CACHE, is_demo_mode
from src.db.duckdb_adapter import _duckdb_available
from src.db.queries import get_authorized_table_names, run_query
from src.i18n import t
from src.ui.css import VIS_WIDE_CSS


@st.dialog(t("detail.edit_table"), width="large")
def render_table_metadata_editor(table_full_name: str, current_desc: str, current_steward: str):
    """Editor for table-level metadata (description, steward)."""
    st.markdown(f"**{table_full_name}**")

    new_desc = st.text_area(
        t("detail.table_description"),
        value=current_desc,
        placeholder=t("detail.table_desc_placeholder"),
        height=150,
    )
    new_stew = st.text_input(
        t("detail.steward_email"), value=current_steward,
        placeholder=t("detail.placeholder_steward"),
    )

    c1, c2 = st.columns([1, 1])
    with c1:
        if st.button(t("common.save"), type="primary", use_container_width=True):
            if new_stew.strip() and "@" not in new_stew:
                st.error(t("detail.invalid_email"))
            else:
                try:
                    save_table_metadata(
                        table_full_name, description=new_desc, steward_email=new_stew,
                    )
                    st.toast(t("common.saved"))
                    st.rerun()
                except Exception as e:
                    logging.error("Save failed for %s: %s", table_full_name, e, exc_info=True)
                    # Security: do not expose internal error details to UI
                    st.error(t("common.error"))
    with c2:
        if st.button(t("common.cancel"), use_container_width=True):
            st.rerun()


@st.dialog(t("detail.data_sample"), width="large")
def render_data_sample(table_full_name: str):
    st.markdown(VIS_WIDE_CSS, unsafe_allow_html=True)
    st.markdown(f"**{table_full_name}**")

    # Defense in depth: re-check authorization even though the UI gate
    # already prevents this dialog from opening for unauthorized tables.
    groups = (
        tuple(st.session_state.get("user_groups", []))
        if st.session_state.get("user_groups") else ("none",)
    )
    active_group = st.session_state.get("group_filter")
    query_groups = (active_group,) if active_group else groups
    _allowed = get_authorized_table_names(query_groups)
    if table_full_name not in _allowed:
        st.error(t("detail.unauthorized"))
        return

    try:
        # Validate Unity Catalog 3-level namespace format before interpolating.
        # Format expects: <catalog>.<schema>.<table>
        # Each part must consist of 1 or more alphanumeric characters, underscores, or hyphens,
        # and be separated by exactly one literal dot.
        if not re.match(r"^[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+$", table_full_name):
            st.error(t("common.error"))
            return
        if is_demo_mode():
            df = pd.DataFrame({"id": [1, 2, 3], "status": ["NEW", "SHIPPED", "CLOSED"]})
        elif _duckdb_available():
            _parts = table_full_name.split(".")
            if len(_parts) == 3:
                _cat, _sch, _tbl = _parts
                _safe_sch = _sch.replace('"', '""')
                _safe_tbl = _tbl.replace('"', '""')
                _sample_query = f'SELECT * FROM {CATALOG_CACHE}."{_safe_sch}"."{_safe_tbl}" LIMIT 100'  # nosec B608
                df = run_query(_sample_query)
            else:
                st.info(t("detail.preview_not_available"))
                return
        else:
            _safe_parts = [p.replace('"', '""') for p in table_full_name.split(".")]
            _safe_table = '"' + '"."'.join(_safe_parts) + '"'
            query = f"SELECT * FROM {_safe_table} LIMIT 100"  # nosec B608
            df = run_query(query)
        if df is not None and not df.empty:
            st.dataframe(df, use_container_width=True, height=2000)
        else:
            st.info(t("detail.preview_needs_data"))
    except Exception as e:
        logging.error(
            "Error fetching data sample for %s: %s", table_full_name, e, exc_info=True,
        )
        st.error(t("detail.preview_error"))
