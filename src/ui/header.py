import streamlit as st
import html as _html
from src.i18n import t, _ensure_locale

LOGO_MARK_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" fill="none" height="30">
  <rect x="4.5" y="6.5" width="55" height="51" rx="1" fill="#FAF7F0" stroke="#14110C" stroke-width="1.5"/>
  <line x1="4.5" y1="19" x2="59.5" y2="19" stroke="#14110C" stroke-width="1.25"/>
  <circle cx="11" cy="12.75" r="2.5" fill="#B8362A"/>
  <line x1="10" y1="28" x2="54" y2="28" stroke="#C9C2B4" stroke-width="1.25"/>
  <line x1="10" y1="36" x2="54" y2="36" stroke="#C9C2B4" stroke-width="1.25"/>
  <line x1="10" y1="44" x2="40" y2="44" stroke="#C9C2B4" stroke-width="1.25"/>
</svg>"""


def render_header(
    user_name: str | None = None, active_tab: str = "search", show_admin: bool = False
):
    _ensure_locale()
    locale = st.session_state.get("locale", "en")

    user_section = ""
    if user_name:
        user_section = f'<span class="dd-nav-sep"></span><span class="dd-nav-user">{_html.escape(user_name)}</span>'

    def link(label, tab_id):
        active = "active" if active_tab == tab_id else ""
        return (
            f'<a href="#" data-tab="{tab_id}" class="dd-nav-tab {active}">{label}</a>'
        )

    admin_link = link(t("nav.admin"), "admin") if show_admin else ""

    en_active = "dd-lang-active" if locale == "en" else ""
    fr_active = "dd-lang-active" if locale == "fr" else ""
    title_en = t("language.switch_to_en")
    title_fr = t("language.switch_to_fr")
    lang_toggle = f'<span class="dd-nav-sep"></span><span class="dd-lang-toggle" aria-label="Language selector"><a href="#" data-lang="en" class="dd-lang-opt {en_active}" title="{title_en}">EN</a><span class="dd-lang-sep">/</span><a href="#" data-lang="fr" class="dd-lang-opt {fr_active}" title="{title_fr}">FR</a></span>'

    st.html(f'''
<div class="dd-header" lang="{locale}">
  <div class="dd-header-inner">
    <a href="#" data-tab="search" class="dd-logo-link">
      {LOGO_MARK_SVG}
      <span class="dd-logo-text">Data Dictionary</span>
      <span class="dd-pill">Beta</span>
    </a>
    <nav class="dd-nav" role="navigation" aria-label="Main navigation">
      {link(t("nav.search"), "search")}
      {link(t("nav.catalog"), "catalog")}
      {link(t("nav.glossary"), "glossary")}
      {link(t("nav.discovery"), "discovery")}
      {link(t("nav.health"), "health")}
      {admin_link}
      {lang_toggle}
      {user_section}
    </nav>
  </div>
</div>
''')

    # Hidden Streamlit nav/lang proxy buttons — JS clicks these; the container is
    # hidden immediately via CSS :has(#dd-proxy-anchor) so they never flash.
    import json as _json
    import streamlit.components.v1 as components

    _tabs = ["search", "catalog", "glossary", "discovery", "health"]
    if show_admin:
        _tabs.append("admin")

    with st.container():
        st.markdown('<div id="dd-proxy-anchor"></div>', unsafe_allow_html=True)
        for tab_id in _tabs:
            if st.button(t(f"nav.{tab_id}"), key=f"nav_{tab_id}"):
                st.query_params["tab"] = tab_id
                st.rerun()
        # on_click fires before rerun so render_header() picks up the new locale.
        from src.i18n import set_locale

        st.button("LOCALE_EN", key="lang_btn_en", on_click=set_locale, args=("en",))
        st.button("LOCALE_FR", key="lang_btn_fr", on_click=set_locale, args=("fr",))

    # Zero-height iframe: wires nav clicks → hidden Streamlit buttons,
    # and wires language toggle clicks → hidden lang proxy buttons.
    _tab_map = {tid: t(f"nav.{tid}") for tid in _tabs}
    _tab_map_js = _json.dumps(_tab_map)
    _nav_labels_js = _json.dumps(list(_tab_map.values()))

    components.html(
        f"""
    <div style="display:none;">
    <script>
    (function() {{
        const parentDoc = window.parent.document;
        const NAV_LABELS = {_nav_labels_js};
        const TAB_MAP = {_tab_map_js};
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
    """,
        height=0,
    )


def render_footer():
    st.markdown(
        f"""
    <div class="dd-footer">
      <div class="dd-footer-inner">
        <span>{t("footer.built_with")}</span>
        <span>main.data_governance.dictionary_cache</span>
      </div>
    </div>
    """,
        unsafe_allow_html=True,
    )
