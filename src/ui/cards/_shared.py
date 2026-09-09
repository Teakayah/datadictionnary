"""Helpers shared across cards/ submodules.

Contents:
- ``_DQ_GRADES`` / ``_dq_grade``  — DQ score → letter grade + CSS class.
  Used by discovery cards (banner colour) and the search-page table card.
- ``_compute_live_completeness``  — column-definition coverage percentage.
  Used by the search page hero metric and (future) admin reports.
- ``_POST_COLOR``                  — CMS post-type → accent colour.
  Used by ``render_cms_banner`` (discovery) and the admin CMS section.
"""
from __future__ import annotations


from src.config import CATALOG_CACHE, SCHEMA_CACHE
from src.db.duckdb_adapter import _duckdb_available
from src.db.queries import run_query
import streamlit as st

def _render_empty_state(icon: str, text: str) -> None:
    """Renders a consistent empty state placeholder for UI components.

    Args:
        icon: An emoji or character string to display prominently as the icon.
        text: The descriptive message to display below the icon.
    """
    st.markdown(
        f'<div style="padding: 24px; text-align: center; background: var(--paper-deep); border: 1px dashed var(--ink-20); border-radius: 4px;">'
        f'<div style="font-size: 24px; color: var(--ink-40); margin-bottom: 8px;" aria-hidden="true">{icon}</div>'
        f'<div style="font-family: var(--font-sans); font-size: 14px; color: var(--ink-60);">{text}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

_DQ_GRADES = [
    (90, "A", "dq-a"),
    (75, "B", "dq-b"),
    (60, "C", "dq-c"),
    (0,  "D", "dq-d"),
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


def _compute_live_completeness(table_full_name: str) -> float:
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


_POST_COLOR = {
    "announcement":  "var(--accent)",
    "featured_table": "var(--deepblue)",
    "guide":         "var(--forest)",
}
