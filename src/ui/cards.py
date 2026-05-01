import streamlit as st
import pandas as pd
import html as _html
from src.i18n import t
from src.db.duckdb_adapter import _duckdb_available
from src.config import CATALOG_CACHE, SCHEMA_CACHE

_DQ_GRADES = [
    (90, "A", "dq-a"),
    (75, "B", "dq-b"),
    (60, "C", "dq-c"),
    (0, "D", "dq-d"),
]


def _dq_grade(score_str) -> tuple:
    """Return (letter, css_class) from a dq_score string or number."""
    try:
        score = float(score_str or 0)
    except (ValueError, TypeError):
        score = 0
    for threshold, letter, cls in _DQ_GRADES:
        if score >= threshold:
            return letter, cls
    return "D", "dq-d"


def _compute_live_completeness(table_full_name: str, run_query) -> float:
    """Live column-definition coverage: (metadata comment OR user override) / total cols."""
    bno_tbl = (
        "user_data.business_name_overrides"
        if _duckdb_available()
        else f"{CATALOG_CACHE}.{SCHEMA_CACHE}.business_name_overrides"
    )
    q = (
        "SELECT COUNT(*) AS total, "
        "COUNT(CASE WHEN (cm.comment IS NOT NULL AND cm.comment != '') "
        "           OR  (bno.definition IS NOT NULL AND bno.definition != '') "
        "           THEN 1 END) AS defined "
        "FROM {0}.{1}.columns_metadata cm "
        "LEFT JOIN {2} bno "
        "  ON cm.table_full_name = bno.table_full_name AND cm.column_name = bno.column_name "
        "WHERE cm.table_full_name = %(fn)s"
    ).format(CATALOG_CACHE, SCHEMA_CACHE, bno_tbl)
    try:
        result = run_query(q, {"fn": table_full_name})
        if result is None or result.empty:
            return 0.0
        total = int(result.iloc[0]["total"] or 0)
        defined = int(result.iloc[0]["defined"] or 0)
        return (defined / total * 100) if total > 0 else 0.0
    except Exception:
        return 0.0


def _render_table_card(row: "pd.Series", key_prefix: str, _pref_upsert, _pref_delete) -> None:
    """Discovery card: table name is clickable, star toggles bookmark."""
    _ts = row.get("updated_at")
    _time_str = (
        _ts.strftime(t("discovery.date_format"))
        if isinstance(_ts, pd.Timestamp)
        else (str(_ts) if _ts else "")
    )
    _full = str(row.get("full_name", ""))
    _tname = str(row.get("table_name", ""))
    _is_bk = _full in st.session_state.get("bookmarks", set())

    st.markdown(
        f"""
    <div style="background:var(--paper); border:1px solid var(--ink-10); padding:16px 20px 4px; margin-bottom:4px; border-radius:2px;">
        <div style="display:flex; justify-content:space-between; align-items:baseline; margin-bottom:4px;">
            <div style="font-family:var(--font-mono); font-size:12px; color:var(--ink-40); text-transform:uppercase; letter-spacing:0.1em;">{_html.escape(str(row.get("catalog_name", "")))} · {_html.escape(str(row.get("schema_name", "")))}</div>
            <div style="font-family:var(--font-mono); font-size:11px; color:var(--accent);">{t("discovery.updated")} {_time_str}</div>
        </div>
        <p style="font-family:var(--font-sans); font-size:13px; color:var(--ink-60); line-height:1.5; margin:4px 0 8px;">{_html.escape(str(row.get("table_description", "")))}</p>
    </div>
    """,
        unsafe_allow_html=True,
    )

    # Table name button (navigates to detail) + star bookmark — flush below the card
    _c_name, _c_star = st.columns([11, 1], gap="small")
    with _c_name:
        if st.button(
            f"→ {_tname}",
            key=f"{key_prefix}_open_{_full}",
            use_container_width=True,
            type="secondary",
        ):
            st.query_params["tab"] = "search"
            st.session_state["dd_search_override"] = _tname
            st.session_state["dd_nav_select"] = _full
            st.rerun()
    with _c_star:
        if st.button(
            "★" if _is_bk else "☆",
            key=f"{key_prefix}_bk_{_full}",
            use_container_width=True,
        ):
            if _is_bk:
                st.session_state.get("bookmarks", set()).discard(_full)
                _pref_delete(_full, "bookmark")
            else:
                st.session_state.get("bookmarks", set()).add(_full)
                _pref_upsert(_full, "bookmark")
            st.rerun()
    st.markdown("<div style='margin-bottom:12px'></div>", unsafe_allow_html=True)
