"""
Screenshot utility — captures every major feature screen of the Data Dictionary.

Usage:
    python scripts/screenshot.py                          # full run
    python scripts/screenshot.py --out screenshots/run1  # custom output dir
    python scripts/screenshot.py --width 1440            # custom viewport width

Requires the Streamlit app to be running (ENABLE_MOCK_AUTH=true ENVIRONMENT=development):
    streamlit run app.py

Install deps (already in dev env):
    pip install playwright
    python -m playwright install chromium
"""
from __future__ import annotations

import argparse
import time
import os
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright, Page

DEFAULT_OUT = Path(__file__).parent.parent / "screenshots" / "latest"
VIEWPORT = {"width": 1440, "height": 900}
WAIT_AFTER_NAV = 1800   # ms — let Streamlit finish rendering after navigation

# Set at runtime from --host arg; helpers read this module-level var.
_base_url = os.getenv("SCREENSHOT_HOST", "http://127.0.0.1:8501")


def _wait(page: Page, ms: int = WAIT_AFTER_NAV) -> None:
    page.wait_for_timeout(ms)


def _nav(page: Page, tab: str, extra: str = "") -> None:
    """Navigate to a tab, triggering mock auth if needed."""
    page.goto(f"{_base_url}/?tab={tab}&mock_login=true{extra}")
    _wait(page)


def _shot(page: Page, out: Path, name: str) -> None:
    path = out / f"{name}.png"
    page.screenshot(path=str(path), full_page=False)
    print(f"  ✓  {name}.png")


def capture_login(page: Page, out: Path) -> None:
    print("\n── Login page")
    page.goto(_base_url)
    _wait(page)
    _shot(page, out, "01_login")


def capture_search(page: Page, out: Path) -> None:
    print("\n── Search tab")
    _nav(page, "search")
    _shot(page, out, "02_search_empty")

    # Type in the selectbox to trigger autocomplete
    box = page.locator('[data-testid="stSelectbox"] input').first
    box.click()
    _wait(page, 600)
    _shot(page, out, "03_search_autocomplete")

    # Select first option from dropdown
    first_opt = page.locator('[data-testid="stSelectboxVirtualDropdown"] li').first
    if first_opt.is_visible():
        first_opt.click()
        _wait(page)
        _shot(page, out, "04_search_results_cards")

        # Click "View details" on first result card
        btn = page.locator('button:has-text("View details")').first
        if btn.is_visible():
            btn.click()
            _wait(page)
            _shot(page, out, "05_search_detail_panel")

            # Scroll down to show columns section
            page.evaluate("window.scrollBy(0, 400)")
            _wait(page, 600)
            _shot(page, out, "06_search_detail_columns")

            # Data preview dialog
            preview_btn = page.locator('button:has-text("Preview data"), button:has-text("Aperçu")').first
            if preview_btn.is_visible():
                preview_btn.click()
                _wait(page)
                _shot(page, out, "07_search_data_preview_dialog")
                page.keyboard.press("Escape")
                _wait(page, 500)

            # Back to results
            back_btn = page.locator('button:has-text("Back to results"), button:has-text("Retour")').first
            if back_btn.is_visible():
                back_btn.click()
                _wait(page)


def capture_catalog(page: Page, out: Path) -> None:
    print("\n── Catalog browser")
    _nav(page, "catalog")
    _shot(page, out, "08_catalog_browser")

    # Expand first catalog
    exp = page.locator('[data-testid="stExpander"]').first
    if exp.is_visible():
        exp.click()
        _wait(page)
        _shot(page, out, "09_catalog_expanded")


def capture_glossary(page: Page, out: Path) -> None:
    print("\n── Glossary")
    _nav(page, "glossary")
    _shot(page, out, "10_glossary")

    # Click first glossary term
    term = page.locator('[data-testid="stSelectbox"]').first
    if term.is_visible():
        term.click()
        _wait(page, 600)
        first = page.locator('[data-testid="stSelectboxVirtualDropdown"] li').first
        if first.is_visible():
            first.click()
            _wait(page)
            _shot(page, out, "11_glossary_term_detail")


def capture_discovery(page: Page, out: Path) -> None:
    print("\n── Discovery")
    _nav(page, "discovery")
    _shot(page, out, "12_discovery_notable")

    # Switch to bookmarks tab
    bk = page.locator('button:has-text("Bookmarks"), button:has-text("Favoris")').first
    if bk.is_visible():
        bk.click()
        _wait(page)
        _shot(page, out, "13_discovery_bookmarks")

    # Switch to recent tab
    rc = page.locator('button:has-text("Recent"), button:has-text("Récents")').first
    if rc.is_visible():
        rc.click()
        _wait(page)
        _shot(page, out, "14_discovery_recent")


def capture_health(page: Page, out: Path) -> None:
    print("\n── Health dashboard")
    _nav(page, "health")
    _shot(page, out, "15_health_overview")

    # Scroll to see coverage charts
    page.evaluate("window.scrollBy(0, 500)")
    _wait(page, 600)
    _shot(page, out, "16_health_charts")


def capture_grants_filter(page: Page, out: Path) -> None:
    print("\n── Group permission filter")
    _nav(page, "search")
    # Select a table
    box = page.locator('[data-testid="stSelectbox"] input').first
    box.click()
    _wait(page, 500)
    first_opt = page.locator('[data-testid="stSelectboxVirtualDropdown"] li').first
    if first_opt.is_visible():
        first_opt.click()
        _wait(page)
        btn = page.locator('button:has-text("View details")').first
        if btn.is_visible():
            btn.click()
            _wait(page)
            # Scroll to grants section
            page.evaluate("window.scrollBy(0, 1200)")
            _wait(page, 600)
            _shot(page, out, "17_search_grants_section")

            # Click a group filter button
            grant_btn = page.locator('[data-testid="stSidebarContent"] ~ * button[kind="secondary"]').first
            group_btn = page.locator('button:has-text("Browse"), button:has-text("Search tables accessible")').first
            if group_btn.is_visible():
                group_btn.click()
                _wait(page)
                _shot(page, out, "18_group_filter_results")


def capture_language_toggle(page: Page, out: Path) -> None:
    print("\n── Language toggle (FR)")
    _nav(page, "search")
    # Language buttons may be slow to appear — try with explicit wait
    try:
        fr_btn = page.locator('button:has-text("LOCALE_FR")').first
        fr_btn.wait_for(state="visible", timeout=4000)
        fr_btn.click()
        _wait(page)
        _shot(page, out, "19_search_french")
        try:
            en_btn = page.locator('button:has-text("LOCALE_EN")').first
            en_btn.wait_for(state="visible", timeout=3000)
            en_btn.click()
            _wait(page, 500)
        except Exception:
            pass
    except Exception as exc:
        print(f"  ⚠  Language toggle not found ({exc}); skipping screenshot 19")


def main() -> None:
    global _base_url
    parser = argparse.ArgumentParser(description="Screenshot the Data Dictionary app.")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="Output directory")
    parser.add_argument("--width", type=int, default=VIEWPORT["width"], help="Viewport width")
    parser.add_argument("--height", type=int, default=VIEWPORT["height"], help="Viewport height")
    parser.add_argument("--host", default=_base_url, help="App base URL")
    args = parser.parse_args()
    _base_url = args.host

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    viewport = {"width": args.width, "height": args.height}

    print(f"Saving screenshots to: {out}")
    print(f"Viewport: {viewport['width']}×{viewport['height']}")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(
            viewport=viewport,
            device_scale_factor=2,   # retina-quality PNGs
        )
        page = ctx.new_page()

        capture_login(page, out)
        capture_search(page, out)
        capture_catalog(page, out)
        capture_glossary(page, out)
        capture_discovery(page, out)
        capture_health(page, out)
        capture_grants_filter(page, out)
        capture_language_toggle(page, out)

        browser.close()

    files = sorted(out.glob("*.png"))
    print(f"\n✅  {len(files)} screenshots saved to {out}/")


if __name__ == "__main__":
    main()
