from __future__ import annotations
"""Design system CSS loader.

Reads assets/design.css and assets/vis_dialog.css at import time and
exposes them as module-level constants plus a render_css() helper.

Public API:
    DESIGN_CSS    — full design-system stylesheet as a plain CSS string
    VIS_WIDE_CSS  — dialog-sizing override block as a ready-to-inject <style> string
    render_css()  — inject DESIGN_CSS + WCAG aria patch into the Streamlit page

Dependencies: pathlib, streamlit (no databricks/msal imports — safe in tests).
"""


from pathlib import Path
import streamlit as st

_ASSETS = Path(__file__).parent.parent.parent / "assets"

DESIGN_CSS: str = (_ASSETS / "design.css").read_text(encoding="utf-8")
VIS_WIDE_CSS: str = "<style>\n" + (_ASSETS / "vis_dialog.css").read_text(encoding="utf-8") + "\n</style>"


def render_css() -> None:
    """Inject the design-system stylesheet and WCAG aria patch into the page.

    The aria patch fixes a Streamlit framework violation: ``st.dataframe``
    sort/filter buttons render as ``div[aria-haspopup]`` without a ``role``
    attribute, which axe-core flags as ``aria-allowed-attr`` (WCAG 4.1.2).

    The patch runs in three layers:
      1. **One-shot** sweep on first paint via the ``onerror`` trick.
      2. **MutationObserver** on ``childList + subtree + attributes`` — catches
         both newly-added nodes (typical case) AND existing nodes whose
         ``aria-haspopup`` attribute appears asynchronously after Streamlit's
         dataframe re-renders (the Health-page race we previously marked
         unfixable).
      3. **Polling fallback** at 250 ms intervals for the first 5 s — defence
         in depth for DOM operations that bypass MutationObserver's
         ``attributes`` watch (rare, but cheap insurance).
    """
    st.markdown(f"<style>{DESIGN_CSS}</style>", unsafe_allow_html=True)

    _patch_now = (
        "document.querySelectorAll('div[aria-haspopup]').forEach(function(el){"
        "if(!el.getAttribute('role')){el.setAttribute('role','combobox');}});"
    )

    # Layer 2 — MutationObserver. childList catches added nodes; attributes
    # (with attributeFilter) catches existing nodes that gain aria-haspopup
    # later, which is what Streamlit's st.dataframe re-renders look like.
    _observer_js = (
        "try{new MutationObserver(function(ms){"
        "ms.forEach(function(m){"
        "if(m.type==='attributes'&&m.target&&m.target.nodeType===1){"
        "if(m.target.hasAttribute('aria-haspopup')&&!m.target.getAttribute('role')){"
        "m.target.setAttribute('role','combobox');}}"
        "m.addedNodes&&m.addedNodes.forEach(function(n){"
        "if(n.nodeType!==1)return;"
        "if(n.matches&&n.matches('div[aria-haspopup]')&&!n.getAttribute('role'))"
        "n.setAttribute('role','combobox');"
        "n.querySelectorAll&&n.querySelectorAll('div[aria-haspopup]').forEach(function(e){"
        "if(!e.getAttribute('role'))e.setAttribute('role','combobox');});"
        "});})"
        "}).observe(document.body,{childList:true,subtree:true,"
        "attributes:true,attributeFilter:['aria-haspopup']});"
        "}catch(e){}"
    )
    # Layer 3 — 5 s polling fallback (20 ticks at 250 ms) for DOM operations
    # that bypass MutationObserver's attribute watch (rare).
    _polling_js = (
        "var ticks=0;var iv=setInterval(function(){"
        + _patch_now
        + "if(++ticks>=20)clearInterval(iv);},250);"
    )

    st.markdown(
        '<img src="x" style="display:none" aria-hidden="true" onerror="'
        "(function(){"
        + _patch_now      # Layer 1 — one-shot sweep
        + _observer_js    # Layer 2 — MutationObserver
        + _polling_js     # Layer 3 — polling fallback
        + "})();"
        '">',
        unsafe_allow_html=True,
    )
