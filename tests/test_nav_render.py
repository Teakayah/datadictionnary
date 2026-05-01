"""
Nav render regression tests.

Guards against st.markdown() → st.html() regressions where Streamlit's
markdown processor breaks the nav HTML mid-way, rendering lang-toggle or
user-section spans as raw escaped text inside the dark header background.

Requires a running Streamlit app (ENABLE_MOCK_AUTH=true, DUCKDB_PATH set).
Tests are skipped automatically when the app is not reachable.

Run:
    pytest tests/test_nav_render.py -v
    pytest tests/test_nav_render.py -v -m integration
"""
from __future__ import annotations

import os
from typing import Generator

import pytest
import requests
try:
    from playwright.sync_api import Page, sync_playwright
except ImportError:
    pass

APP_URL = os.getenv("LOAD_TEST_HOST", "http://localhost:8501")
_SEARCH_URL = "/?tab=search&mock_login=true"
_WAIT_MS = 2500


def _server_is_up() -> bool:
    try:
        return requests.get(f"{APP_URL}/healthz", timeout=3).status_code == 200
    except requests.ConnectionError:
        return False


@pytest.fixture(scope="module")
def require_server():
    if not _server_is_up():
        pytest.skip(f"Streamlit app not reachable at {APP_URL}")


@pytest.fixture(scope="module")
def page(require_server) -> Generator[Page, None, None]:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        p = ctx.new_page()
        p.goto(f"{APP_URL}{_SEARCH_URL}", wait_until="networkidle")
        p.wait_for_timeout(_WAIT_MS)
        yield p
        browser.close()


# ── Helpers ────────────────────────────────────────────────────────────────────

def _header_info(page: Page) -> dict:
    return page.evaluate("""() => {
        const h = document.querySelector('.dd-header');
        if (!h) return { found: false };
        const text = h.innerText || '';
        return {
            found: true,
            rawHtmlVisible: text.includes('<span') || text.includes('class=') || text.includes('</'),
            hasLangToggle: !!h.querySelector('a.dd-lang-opt[data-lang]'),
            langEnVisible: (() => {
                const el = h.querySelector('a.dd-lang-opt[data-lang="en"]');
                return el ? window.getComputedStyle(el).visibility : 'missing';
            })(),
            langFrVisible: (() => {
                const el = h.querySelector('a.dd-lang-opt[data-lang="fr"]');
                return el ? window.getComputedStyle(el).visibility : 'missing';
            })(),
            navTabCount: h.querySelectorAll('a.dd-nav-tab').length,
            innerText: text.slice(0, 200),
        };
    }""")


# ── Tests ──────────────────────────────────────────────────────────────────────

@pytest.mark.integration
class TestNavRender:

    @pytest.fixture(autouse=True)
    def _srv(self, require_server):
        pass

    def test_header_present(self, page: Page):
        """.dd-header element must exist in the DOM."""
        info = _header_info(page)
        assert info["found"], ".dd-header not found — header may have failed to render"

    def test_no_raw_html_in_header_text(self, page: Page):
        """Header innerText must not contain raw HTML tags.

        Catches the regression where st.markdown() broke mid-HTML and rendered
        lang-toggle or user-section spans as visible escaped text.
        """
        info = _header_info(page)
        assert not info["rawHtmlVisible"], (
            f"Raw HTML visible as text in nav header.\n"
            f"innerText snippet: {info.get('innerText', '')!r}\n"
            "Likely cause: st.html() was reverted to st.markdown() for the nav."
        )

    def test_lang_toggle_links_present(self, page: Page):
        """Both EN and FR lang links must exist inside .dd-header."""
        info = _header_info(page)
        assert info["hasLangToggle"], (
            "No a.dd-lang-opt[data-lang] found in header — lang toggle not rendered"
        )

    def test_lang_links_visible(self, page: Page):
        """EN and FR links must be visible (not hidden by CSS)."""
        info = _header_info(page)
        assert info["langEnVisible"] == "visible", (
            f"EN lang link not visible: {info['langEnVisible']}"
        )
        assert info["langFrVisible"] == "visible", (
            f"FR lang link not visible: {info['langFrVisible']}"
        )

    def test_nav_tabs_present(self, page: Page):
        """At least 5 nav tab links (Search…Health) must render."""
        info = _header_info(page)
        assert info["navTabCount"] >= 5, (
            f"Only {info['navTabCount']} nav tabs found, expected ≥ 5"
        )

    def test_no_proxy_buttons_visible(self, page: Page):
        """Proxy nav/lang buttons must not be visible to the user.

        These are st.button() widgets the JS uses to trigger reruns; they must
        be hidden (visibility:hidden in the dd-proxy-anchor container).
        """
        proxy_labels = {"Search", "Catalog", "Glossary", "Discovery", "Health",
                        "Rechercher", "Catalogue", "Glossaire", "Découverte", "Santé",
                        "LOCALE_EN", "LOCALE_FR"}
        visible = page.evaluate(f"""() => {{
            const labels = {list(proxy_labels)!r};
            return Array.from(document.querySelectorAll('button'))
                .filter(b => labels.includes(b.textContent.trim()))
                .filter(b => {{
                    const r = b.getBoundingClientRect();
                    return r.height > 0 && window.getComputedStyle(b).visibility !== 'hidden';
                }})
                .map(b => b.textContent.trim());
        }}""")
        assert visible == [], (
            f"Proxy buttons are visible to users: {visible}\n"
            "Check the CSS :has(#dd-proxy-anchor) rule in DESIGN_CSS."
        )

    def test_lang_toggle_switches_locale(self, page: Page):
        """Clicking FR must trigger a rerun that switches the UI to French."""
        page.goto(f"{APP_URL}{_SEARCH_URL}", wait_until="networkidle")
        page.wait_for_timeout(_WAIT_MS)

        before = page.locator(".dd-search-hero h1").text_content()
        page.locator('a.dd-lang-opt[data-lang="fr"]').click()
        page.wait_for_timeout(_WAIT_MS)
        after = page.locator(".dd-search-hero h1").text_content()

        assert before != after, (
            "Language did not switch after clicking FR link — "
            "the lang proxy button wiring may be broken."
        )

        # Switch back to EN to leave page in a clean state
        page.locator('a.dd-lang-opt[data-lang="en"]').click()
        page.wait_for_timeout(_WAIT_MS)
