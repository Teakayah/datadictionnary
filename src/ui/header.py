"""UI header and footer components.

Contains the SVG brand constants and the render functions for the
application's global header and footer.

Public API:
    LOGO_MARK_SVG  — inline SVG for the logo mark
    MS_LOGO_SVG    — inline SVG for the Microsoft sign-in button
    render_header() — full navigation header with lang toggle
    render_footer() — standard application footer
"""
from __future__ import annotations

from typing import Optional
import html as _html
import json as _json


import streamlit as st
import streamlit.components.v1 as components

from src.i18n import t, set_locale, get_current_locale

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


def _build_lang_toggle(locale: str) -> str:
    en_active = "dd-lang-active" if locale == "en" else ""
    fr_active = "dd-lang-active" if locale == "fr" else ""

    aria_en = ' aria-current="true"' if locale == "en" else ""
    aria_fr = ' aria-current="true"' if locale == "fr" else ""

    title_en = t("language.switch_to_en")
    title_fr = t("language.switch_to_fr")
    aria_lang = t("nav.aria_language_selector")

    return (
        f'<span class="dd-nav-sep"></span>'
        f'<span class="dd-lang-toggle" aria-label="{aria_lang}">'
        f'<a href="#" data-lang="en" class="dd-lang-opt {en_active}" title="{title_en}"{aria_en}>EN</a>'
        f'<span class="dd-lang-sep">/</span>'
        f'<a href="#" data-lang="fr" class="dd-lang-opt {fr_active}" title="{title_fr}"{aria_fr}>FR</a>'
        f'</span>'
    )


def _render_proxy_buttons(tabs: list[str]) -> None:
    with st.container():
        st.markdown('<div id="dd-proxy-anchor"></div>', unsafe_allow_html=True)
        for tab_id in tabs:
            if st.button(t(f"nav.{tab_id}"), key=f"nav_{tab_id}"):
                st.query_params["tab"] = tab_id
                st.rerun()
        # on_click fires before rerun so render_header() picks up the new locale.
        st.button("LOCALE_EN", key="lang_btn_en", on_click=set_locale, args=("en",))
        st.button("LOCALE_FR", key="lang_btn_fr", on_click=set_locale, args=("fr",))


def _inject_wiring_js(tabs: list[str]) -> None:
    tab_map = {tid: t(f"nav.{tid}") for tid in tabs}
    tab_map_js = _json.dumps(tab_map)
    nav_labels_js = _json.dumps(list(tab_map.values()))

    components.html(f"""
    <div style="display:none;">
    <script>
    (function() {{
        const parentDoc = window.parent.document;
        const NAV_LABELS = {nav_labels_js};
        const TAB_MAP = {tab_map_js};
        const iframeId = Math.random().toString(36);

        function wire() {{
            const allBtns = Array.from(parentDoc.querySelectorAll('button'));

            // 1. The proxy container is already hidden via CSS (visibility:hidden).
            //    Nothing to do here — btn.click() works on visibility:hidden elements.

            // 2. Wire Navigation
            parentDoc.querySelectorAll('a.dd-nav-tab[data-tab], a.dd-logo-link[data-tab]').forEach(link => {{
                if (link._wired === iframeId) return;
                link._wired = iframeId;
                link.addEventListener('click', function(e) {{
                    e.preventDefault();
                    const tabId = this.getAttribute('data-tab');
                    const localizedLabel = TAB_MAP[tabId];
                    const currentBtns = Array.from(parentDoc.querySelectorAll('button'));
                    const btn = currentBtns.find(b => b.textContent.trim() === localizedLabel);
                    if (btn) btn.click();
                }});
            }});

            // 3. Wire Language
            parentDoc.querySelectorAll('a.dd-lang-opt[data-lang]').forEach(link => {{
                if (link._wired === iframeId) return;
                link._wired = iframeId;
                link.addEventListener('click', function(e) {{
                    e.preventDefault();
                    const lang = this.getAttribute('data-lang').toUpperCase();
                    const currentBtns = Array.from(parentDoc.querySelectorAll('button'));
                    const btn = currentBtns.find(b => b.textContent.trim() === 'LOCALE_' + lang);
                    if (btn) btn.click();
                }});
            }});
        }}

        // Initial wire
        setTimeout(wire, 150);

        // Continuous monitoring for Streamlit rerenders
        const observer = new MutationObserver(() => {{ wire(); }});
        observer.observe(parentDoc.body, {{childList: true, subtree: true}});
    }})();
    </script>
    </div>
    """, height=0)


def render_header(
    user_name: Optional[str] = None,
    active_tab: str = "search",
    show_admin: bool = False,
    show_pipelines: bool = False
) -> None:
    """Render the application header with navigation and locale toggle."""
    locale = get_current_locale()


    user_section = ""
    if user_name:
        user_section = (
            f'<span class="dd-nav-sep"></span>'
            f'<span class="dd-nav-user">{_html.escape(user_name)}</span>'
        )

    def link(label: str, tab_id: str) -> str:
        active = "active" if active_tab == tab_id else ""
        aria_curr = ' aria-current="page"' if active_tab == tab_id else ""
        return f'<a href="#" data-tab="{tab_id}" class="dd-nav-tab {active}"{aria_curr}>{label}</a>'

    admin_link = link(t("nav.admin"), "admin") if show_admin else ""
    pipelines_link = link(t("nav.pipelines"), "pipelines") if show_pipelines else ""
    lang_toggle = _build_lang_toggle(locale)
    aria_nav = t("nav.aria_main_navigation")

    st.html(f'''
<div class="dd-header" lang="{locale}">
  <div class="dd-header-inner">
    <a href="#" data-tab="search" class="dd-logo-link">
      {LOGO_MARK_SVG}
      <span class="dd-logo-text">{_html.escape(t("common.app_title"))}</span>
      <span class="dd-pill">{_html.escape(t("common.beta"))}</span>
    </a>
    <nav class="dd-nav" role="navigation" aria-label="{aria_nav}">
      {link(t("nav.search"), "search")}
      {link(t("nav.catalog"), "catalog")}
      {link(t("nav.glossary"), "glossary")}
      {link(t("nav.discovery"), "discovery")}
      {link(t("nav.health"), "health")}
      {pipelines_link}
      {admin_link}
      {lang_toggle}
      {user_section}
    </nav>
  </div>
</div>
''')

    tabs = ["search", "catalog", "glossary", "discovery", "health"]
    if show_pipelines:
        tabs.append("pipelines")
    if show_admin:
        tabs.append("admin")

    _render_proxy_buttons(tabs)
    _inject_wiring_js(tabs)


def render_footer() -> None:
    """Render the standard application footer."""
    st.markdown(f"""
    <div class="dd-footer">
      <div class="dd-footer-inner">
        <span>{_html.escape(t('footer.built_with'))}</span>
        <span>main.data_governance.dictionary_cache</span>
      </div>
    </div>
    """, unsafe_allow_html=True)
