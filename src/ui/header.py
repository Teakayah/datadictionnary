"""UI header and footer components.

Contains the SVG brand constants and the render functions for the
application's global header and footer.

Public API:
    LOGO_MARK_SVG  — inline SVG for the logo mark
    MS_LOGO_SVG    — inline SVG for the Microsoft sign-in button
    SEARCH_ICON_SVG — inline SVG for the search bar icon
    render_footer() — standard application footer
"""

from __future__ import annotations

import streamlit as st

from src.i18n import t

# ── Logo & icon SVGs (inlined to avoid Streamlit static-file serving issues) ──

LOGO_MARK_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" fill="none" height="30">
  <rect x="4.5" y="6.5" width="55" height="51" rx="1" fill="#FAF7F0" stroke="#14110C" stroke-width="1.5"/>
  <line x1="4.5" y1="19" x2="59.5" y2="19" stroke="#14110C" stroke-width="1.25"/>
  <circle cx="11" cy="12.75" r="2.5" fill="#B8362A"/>
  <line x1="10" y1="28" x2="54" y2="28" stroke="#C9C2B4" stroke-width="1.25"/>
  <line x1="10" y1="36" x2="54" y2="36" stroke="#C9C2B4" stroke-width="1.25"/>
  <line x1="10" y1="44" x2="40" y2="44" stroke="#C9C2B4" stroke-width="1.25"/>
</svg>"""

MS_LOGO_SVG = """<svg width="16" height="16" viewBox="0 0 23 23" fill="none">
  <rect x="1" y="1" width="10" height="10" fill="#F25022"/>
  <rect x="12" y="1" width="10" height="10" fill="#7FBA00"/>
  <rect x="1" y="12" width="10" height="10" fill="#00A4EF"/>
  <rect x="12" y="12" width="10" height="10" fill="#FFB900"/>
</svg>"""

SEARCH_ICON_SVG = """<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#6B645A" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
  <circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>
</svg>"""


def render_footer() -> None:
    """Render the standard application footer."""
    st.markdown(f"""
    <div class="dd-footer">
      <div class="dd-footer-inner">
        <span>{t('footer.built_with')}</span>
        <span>main.data_governance.dictionary_cache</span>
      </div>
    </div>
    """, unsafe_allow_html=True)
