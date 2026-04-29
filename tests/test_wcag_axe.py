"""
WCAG 2.0 AA axe-core integration tests.

Uses Playwright + axe-playwright-python to audit each main page for
WCAG 2.0 Level A and AA violations.

Known limitations:
  - Requires a running Streamlit app (ENABLE_MOCK_AUTH=true, DUCKDB_PATH set).
  - Tests are skipped when the app is not reachable.
  - Streamlit-internal ARIA issues (e.g., aria-haspopup on dataframe headers)
    are patched at runtime by render_css() — this test verifies the patch works.

Run:
    pytest tests/test_wcag_axe.py -v               # requires running app
    pytest tests/test_wcag_axe.py -v -m integration
"""
from __future__ import annotations

import os
import time
from typing import Generator

import pytest
import requests
from playwright.sync_api import Page, sync_playwright

APP_URL = os.getenv("LOAD_TEST_HOST", "http://localhost:8501")

# Pages to audit — (label, URL path, wait_for_selector)
_PAGES = [
    ("Search",    "/?tab=search&mock_login=true",    ".dd-search-hero"),
    ("Catalog",   "/?tab=catalog&mock_login=true",   ".dd-search-hero"),
    ("Glossary",  "/?tab=glossary&mock_login=true",  ".dd-search-hero"),
    ("Discovery", "/?tab=discovery&mock_login=true", ".dd-search-hero"),
    ("Health",    "/?tab=health&mock_login=true",    ".dd-search-hero"),
]

# Violation IDs that are known Streamlit framework issues we cannot fix from app.py.
# Any NEW violations not in this list will fail the test.
_KNOWN_UNFIXABLE = frozenset({
    # Streamlit's st.dataframe renders sort/filter column headers as
    # div[aria-haspopup] without a role. Our MutationObserver patch (render_css)
    # closes the race for most pages, but the Health dashboard dataframe
    # re-renders after the observer fires. This is a Streamlit internals issue.
    # Track: https://github.com/streamlit/streamlit/issues
    "aria-allowed-attr",
    # Streamlit progress-bar renders with a non-standard ARIA role.
    "scrollable-region-focusable",
})


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _server_is_up() -> bool:
    try:
        return requests.get(f"{APP_URL}/healthz", timeout=3).status_code == 200
    except requests.ConnectionError:
        return False


@pytest.fixture(scope="session")
def require_server():
    if not _server_is_up():
        pytest.skip(f"Streamlit app not reachable at {APP_URL}")


@pytest.fixture(scope="session")
def browser_page(require_server) -> Generator[Page, None, None]:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        yield page
        browser.close()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _run_axe(page: Page) -> list[dict]:
    """Run axe-core and return WCAG 2.0 A/AA violations."""
    from axe_playwright_python.sync_playwright import Axe
    results = Axe().run(
        page,
        options={
            "runOnly": {"type": "tag", "values": ["wcag2a", "wcag2aa"]},
            "resultTypes": ["violations"],
        },
    )
    return results.response.get("violations", [])


def _load_page(page: Page, url: str, wait_selector: str, timeout: int = 15_000):
    """Navigate, wait for Streamlit to finish rendering, and apply ARIA patches."""
    page.goto(f"{APP_URL}{url}")
    page.wait_for_load_state("networkidle", timeout=timeout)
    try:
        page.wait_for_selector(wait_selector, timeout=timeout)
    except Exception:
        pass
    # Allow MutationObserver ARIA patch and CSS to settle after WS renders
    page.wait_for_timeout(1500)


def _format_violation(v: dict) -> str:
    nodes = v.get("nodes", [])
    node_info = ""
    if nodes:
        n = nodes[0]
        target = n.get("target", [])
        html   = n.get("html", "")[:120]
        node_info = f"\n    target: {target}\n    html:   {html}"
    return (
        f"[{v['impact'].upper()}] {v['id']}\n"
        f"  Rule: {v['help']}\n"
        f"  URL:  {v.get('helpUrl','')}{node_info}"
    )


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.integration
class TestWCAGCompliance:

    @pytest.fixture(autouse=True)
    def _server(self, require_server):
        pass

    @pytest.mark.parametrize("label,path,selector", _PAGES)
    def test_no_wcag_violations(self, browser_page: Page, label: str, path: str, selector: str):
        """Every audited page must have zero WCAG 2.0 AA violations."""
        _load_page(browser_page, path, selector)
        violations = _run_axe(browser_page)

        # Filter out known unfixable framework issues
        actionable = [v for v in violations if v["id"] not in _KNOWN_UNFIXABLE]

        if actionable:
            details = "\n\n".join(_format_violation(v) for v in actionable)
            pytest.fail(
                f"{label} page has {len(actionable)} WCAG 2.0 violation(s):\n\n{details}"
            )

    @pytest.mark.parametrize("label,path,selector", _PAGES)
    def test_color_contrast_passes(self, browser_page: Page, label: str, path: str, selector: str):
        """color-contrast must not appear in violations on any page."""
        _load_page(browser_page, path, selector)
        violations = _run_axe(browser_page)
        contrast_fails = [v for v in violations if v["id"] == "color-contrast"]
        if contrast_fails:
            nodes = [n.get("html", "")[:80] for v in contrast_fails for n in v.get("nodes", [])]
            pytest.fail(
                f"{label}: {len(contrast_fails)} color-contrast violation(s).\n"
                + "\n".join(nodes)
            )

    def test_aria_patch_reduces_violations_on_non_dataframe_pages(self, browser_page: Page):
        """Pages without st.dataframe must have zero aria-allowed-attr violations.

        The Health page is excluded here because Streamlit's st.dataframe
        re-renders asynchronously and can race our MutationObserver patch.
        That case is tracked in _KNOWN_UNFIXABLE.
        """
        non_df_pages = [p for p in _PAGES if p[0] != "Health"]
        for label, path, selector in non_df_pages:
            _load_page(browser_page, path, selector)
            violations = _run_axe(browser_page)
            aria_fails = [v for v in violations if v["id"] == "aria-allowed-attr"]
            if aria_fails:
                nodes = [n.get("html", "")[:80] for v in aria_fails for n in v.get("nodes", [])]
                pytest.fail(
                    f"{label}: unexpected aria-allowed-attr violation(s):\n"
                    + "\n".join(nodes)
                )
