from __future__ import annotations
"""Table detail cards and sections.

Includes the schema/columns viewer, business name editor, comments
section, and data preview (local-only for prototype).
"""


import logging

import pandas as pd
import streamlit as st

from src.audit import save_table_metadata, save_table_business_name
import src.auth
from src.storage import get_table_business_name_override_storage
from src.config import CATALOG_CACHE, is_demo_mode
from src.db.duckdb_adapter import _duckdb_available
from src.db.queries import (
    get_authorized_table_names,
    run_query,
)
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
        placeholder=t("detail.steward_email_placeholder"),
    )

    c1, c2 = st.columns([1, 1])
    with c1:
        if st.button(t("common.save"), help=t("help.btn_common_save"), type="primary", use_container_width=True, key="save_table_meta"):
            if new_stew.strip() and "@" not in new_stew:
                st.error(t("detail.invalid_email"))
            else:
                try:
                    with st.spinner(t("common.saving")):
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
        if st.button(t("common.cancel"), help=t("help.btn_common_cancel"), use_container_width=True):
            st.rerun()


@st.dialog(t("editor.title"), width="large")
def render_business_name_editor(table_full_name: str, column_name: str, current_val: str, current_def: str):
    """Dialog to edit business name and definition for a column."""
    st.markdown(f"**{table_full_name}** · `{column_name}`")
    new_name = st.text_input(
        t("table.business_name"),
        value=current_val,
        placeholder=t("table.business_name_placeholder"),
        key="edit_biz_name",
    )
    new_def = st.text_area(
        t("table.description"),
        value=current_def,
        placeholder=t("table.description_placeholder"),
        height=150,
        key="edit_biz_def",
    )

    c1, c2 = st.columns(2)
    with c1:
        if st.button(t("common.save"), type="primary", use_container_width=True, key="save_biz_edit"):
            with st.spinner(t("common.saving")):
                try:
                    from src.db.queries import _get_write_connection
                    import secrets

                    conn = _get_write_connection()
                    with conn.cursor() as cur:
                        actor = st.session_state.get("user_email", "unknown")
                        # 1. Update the local override table
                        cur.execute_write(
                            "INSERT OR REPLACE INTO user_data.business_name_overrides "
                            "(table_full_name, column_name, business_name, definition, edited_by, edited_at, status) "
                            "VALUES (%(t)s, %(c)s, %(n)s, %(d)s, %(u)s, current_timestamp, 'pending')",
                            {
                                "t": table_full_name,
                                "c": column_name,
                                "n": new_name.strip(),
                                "d": new_def.strip(),
                                "u": actor,
                            },
                        )
                        # 2. Queue for background sync to Databricks
                        payload = {
                            "column_name": column_name,
                            "business_name": new_name.strip(),
                            "definition": new_def.strip(),
                        }
                        import json
                        cur.execute_write(
                            "INSERT INTO user_data.pending_sync "
                            "(sync_id, sync_type, table_full_name, payload_json, queued_by, queued_at) "
                            "VALUES (%(id)s, 'COLUMN_DEF', %(t)s, %(p)s, %(u)s, current_timestamp)",
                            {
                                "id": secrets.token_hex(8),
                                "t": table_full_name,
                                "p": json.dumps(payload),
                                "u": actor,
                            },
                        )
                        # 3. Log audit event
                        cur.execute_write(
                            "INSERT INTO user_data.audit_log "
                            "(event_id, event_type, object_type, object_name, actor_email, old_value, new_value, created_at) "
                            "VALUES (%(id)s, 'business_name_change', 'COLUMN', %(obj)s, %(u)s, %(old)s, %(new)s, current_timestamp)",
                            {
                                "id": secrets.token_hex(8),
                                "obj": f"{table_full_name}.{column_name}",
                                "u": actor,
                                "old": current_val,
                                "new": new_name.strip(),
                            },
                        )

                    st.toast(t("common.saved"))
                    st.rerun()
                except Exception as e:
                    logging.error("Failed to save business name override: %s", e, exc_info=True)
                    # Security: do not expose internal error details to UI
                    st.error(t("common.error"))
    with c2:
        if st.button(t("common.cancel"), help=t("help.btn_common_cancel"), use_container_width=True):
            st.rerun()


@st.dialog(t("detail.edit_friendly_name"), width="large")
def render_table_business_name_editor(
    table_full_name: str,
    current_name_en: str = "",
    current_name_fr: str = "",
    current_def_en: str = "",
    current_def_fr: str = "",
):
    """Editor for the bilingual table-level friendly name + definition.

    Editors (non-admin power users) submit pending proposals; admins publish
    immediately. The sidecar handles the write-back to the configured UC
    reference table once a proposal is approved.
    """
    st.markdown(f"**{table_full_name}**")

    # Hand-roll defaults from the override store when the caller didn't pass
    # them (e.g. opening the dialog for a table that already has a pending
    # proposal). The store returns the published value; an editor proposing
    # on top of that will create a new pending row.
    if not any([current_name_en, current_name_fr, current_def_en, current_def_fr]):
        try:
            override = get_table_business_name_override_storage().get_for_table(table_full_name)
            current_name_en = override.get("business_name_en", "")
            current_name_fr = override.get("business_name_fr", "")
            current_def_en  = override.get("business_definition_en", "")
            current_def_fr  = override.get("business_definition_fr", "")
        except Exception as exc:
            logging.warning("Could not load existing friendly name for %s: %s", table_full_name, exc)

    if not src.auth.is_admin():
        st.info(t("detail.friendly_name_pending_notice"))

    new_name_en = st.text_input(t("detail.friendly_name_en"), value=current_name_en)
    new_name_fr = st.text_input(t("detail.friendly_name_fr"), value=current_name_fr)
    new_def_en  = st.text_area(t("detail.friendly_definition_en"), value=current_def_en, height=120)
    new_def_fr  = st.text_area(t("detail.friendly_definition_fr"), value=current_def_fr, height=120)

    c1, c2 = st.columns([1, 1])
    with c1:
        if st.button(t("common.save"), type="primary", use_container_width=True):
            with st.spinner(t("common.saving")):
                try:
                    save_table_business_name(
                        table_full_name,
                        new_name_en.strip(), new_name_fr.strip(),
                        new_def_en.strip(),  new_def_fr.strip(),
                    )
                    st.toast(t("common.saved"))
                    st.rerun()
                except PermissionError:
                    st.error(t("detail.unauthorized"))
                except ValueError as e:
                    logging.error("Validation error for %s: %s", table_full_name, e, exc_info=True)
                    st.error(t("common.error"))
                except Exception as e:
                    logging.error("Friendly-name save failed for %s: %s", table_full_name, e, exc_info=True)
                    st.error(t("common.error"))
    with c2:
        if st.button(t("common.cancel"), help=t("help.btn_common_cancel"), use_container_width=True):
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
        if is_demo_mode():
            df = pd.DataFrame({"id": [1, 2, 3], "status": ["NEW", "SHIPPED", "CLOSED"]})
        elif _duckdb_available():
            _parts = table_full_name.split(".")
            _duckdb_parts = _parts[1:] if len(_parts) == 3 else _parts
            _duckdb_table = f"{CATALOG_CACHE}." + ".".join(_duckdb_parts)
            _sample_query = "SELECT * FROM query_table(%(t)s) LIMIT 100"
            df = run_query(_sample_query, {"t": _duckdb_table})
        else:
            # Fallback for Databricks SQL where table_full_name is in format cat.sch.tbl
            _parts = table_full_name.split(".")
            query_parts = []
            params = {}
            for i, p in enumerate(_parts):
                query_parts.append(f"IDENTIFIER(%(p{i})s)")
                params[f"p{i}"] = p
            _safe_table_name = ".".join(query_parts)
            query = "".join(["SELECT * FROM ", _safe_table_name, " LIMIT 100"])
            df = run_query(query, params)
        if df is not None and not df.empty:
            st.dataframe(df, use_container_width=True, height=2000)
        else:
            st.info(t("detail.preview_needs_data"))
    except Exception as e:
        logging.error(
            "Error fetching data sample for %s: %s", table_full_name, e, exc_info=True,
        )
        st.error(t("detail.preview_error"))
