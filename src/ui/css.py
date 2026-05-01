"""Design system CSS loader.

Reads assets/design.css and assets/vis_dialog.css at import time and
exposes them as module-level constants plus a render_css() helper.

Public API:
    DESIGN_CSS    — full design-system stylesheet as a plain CSS string
    VIS_WIDE_CSS  — dialog-sizing override block as a ready-to-inject <style> string
    render_css()  — inject DESIGN_CSS + WCAG aria patch into the Streamlit page

Dependencies: pathlib, streamlit (no databricks/msal imports — safe in tests).
"""

from __future__ import annotations

from pathlib import Path
import streamlit as st

_ASSETS = Path(__file__).parent.parent.parent / "assets"

DESIGN_CSS: str = (_ASSETS / "design.css").read_text(encoding="utf-8")
VIS_WIDE_CSS: str = "<style>\n" + (_ASSETS / "vis_dialog.css").read_text(encoding="utf-8") + "\n</style>"


def render_css() -> None:
    """Inject the design-system stylesheet and WCAG aria patch into the page."""
    st.markdown(f"<style>{DESIGN_CSS}</style>", unsafe_allow_html=True)
    # WCAG fix: Streamlit renders st.dataframe sort/filter buttons as
    # div[aria-haspopup] without a role, violating aria-allowed-attr (WCAG 4.1.2).
    # A MutationObserver patches current and future elements as they render.
    _aria_patch = (
        "document.querySelectorAll('div[aria-haspopup]').forEach(function(el){"
        "if(!el.getAttribute('role')){el.setAttribute('role','combobox');}});"
    )
    st.markdown(
        '<img src="x" style="display:none" aria-hidden="true" onerror="'
        "(function(){"
        + _aria_patch
        + "try{new MutationObserver(function(ms){"
        "ms.forEach(function(m){m.addedNodes.forEach(function(n){"
        "if(n.nodeType!==1)return;"
        "if(n.matches&&n.matches('div[aria-haspopup]')&&!n.getAttribute('role'))n.setAttribute('role','combobox');"
        "n.querySelectorAll&&n.querySelectorAll('div[aria-haspopup]').forEach(function(e){"
        "if(!e.getAttribute('role'))e.setAttribute('role','combobox');});"
        "});})"
        "}).observe(document.body,{childList:true,subtree:true});"
        "}catch(e){}"
        "})();"
        '">',
        unsafe_allow_html=True,
    )
