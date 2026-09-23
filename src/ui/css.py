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
import streamlit.components.v1 as components

_ASSETS = Path(__file__).parent.parent.parent / "assets"

DESIGN_CSS: str = (_ASSETS / "design.css").read_text(encoding="utf-8")
VIS_WIDE_CSS: str = "<style>\n" + (_ASSETS / "vis_dialog.css").read_text(encoding="utf-8") + "\n</style>"


def render_css() -> None:
    """Inject the design-system stylesheet and WCAG aria patch into the page.

    The aria patch fixes two Streamlit framework violations on ``st.dataframe``
    sort/filter buttons (WCAG 4.1.2):
      1. ``aria-allowed-attr`` — ``div[aria-haspopup]`` rendered without ``role``.
      2. ``aria-input-field-name`` — ``role="combobox"`` without an accessible name.

    The patch runs in three layers, all targeting ``window.parent.document``
    from a 0-height components.html iframe (Streamlit's React frontend rejects
    string event handlers like ``<img onerror>``):
      1. **One-shot** sweep on first paint.
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
        "doc.querySelectorAll('div[aria-haspopup]').forEach(function(el){"
        "if(!el.getAttribute('role')){el.setAttribute('role','combobox');}"
        "if(!el.getAttribute('aria-label')){"
        "var hdr=el.closest('[role=\"columnheader\"]')||el.parentElement;"
        "var txt=hdr?(hdr.innerText||hdr.textContent||'').split('\\n')[0].trim():'';"
        "el.setAttribute('aria-label',txt||'Column options');}});"
        "doc.querySelectorAll('button').forEach(function(btn){"
        "var tt=btn.closest('[data-testid=\"stTooltipHoverTarget\"]');"
        "if(tt&&tt.getAttribute('title')){btn.setAttribute('aria-label',tt.getAttribute('title'));}"
        "});"
    )

    _patch_el = (
        "function _p(el){"
        "if(!el.getAttribute('role')){el.setAttribute('role','combobox');}"
        "if(!el.getAttribute('aria-label')){"
        "var hdr=el.closest('[role=\"columnheader\"]')||el.parentElement;"
        "var txt=hdr?(hdr.innerText||hdr.textContent||'').split('\\n')[0].trim():'';"
        "el.setAttribute('aria-label',txt||'Column options');}}"
        "function _pBtn(btn){"
        "var tt=btn.closest('[data-testid=\"stTooltipHoverTarget\"]');"
        "if(tt&&tt.getAttribute('title')){btn.setAttribute('aria-label',tt.getAttribute('title'));}}"
    )
    _observer_js = (
        _patch_el
        + "try{new (win.MutationObserver)(function(ms){"
        "ms.forEach(function(m){"
        "if(m.type==='attributes'&&m.target&&m.target.nodeType===1){"
        "if(m.target.hasAttribute('aria-haspopup')){_p(m.target);}"
        "if(m.target.tagName==='BUTTON'){_pBtn(m.target);}"
        "if(m.target.getAttribute('data-testid')==='stTooltipHoverTarget'){var b=m.target.querySelector('button');if(b)_pBtn(b);}}"
        "m.addedNodes&&m.addedNodes.forEach(function(n){"
        "if(n.nodeType!==1)return;"
        "if(n.matches&&n.matches('div[aria-haspopup]'))_p(n);"
        "n.querySelectorAll&&n.querySelectorAll('div[aria-haspopup]').forEach(_p);"
        "if(n.matches&&n.matches('button'))_pBtn(n);"
        "n.querySelectorAll&&n.querySelectorAll('button').forEach(_pBtn);"
        "});})"
        "}).observe(doc.body,{childList:true,subtree:true,"
        "attributes:true,attributeFilter:['aria-haspopup','title']});"
        "}catch(e){}"
    )
    _polling_js = (
        "var ticks=0;var iv=win.setInterval(function(){"
        + _patch_now
        + "if(++ticks>=20)win.clearInterval(iv);},250);"
    )

    components.html(
        "<script>(function(){"
        "var win=window.parent;if(!win)return;"
        "var doc=win.document;if(!doc||!doc.body)return;"
        + _patch_now
        + _observer_js
        + _polling_js
        + "})();</script>",
        height=0,
    )
