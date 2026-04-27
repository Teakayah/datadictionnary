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
import os
from pathlib import Path
from playwright.sync_api import sync_playwright, Page

DEFAULT_OUT = Path(__file__).resolve().parent.parent / "screenshots" / "latest"
VIEWPORT = {"width": 1440, "height": 1080}
# Streamlit renders inside a fixed-height scroll container — tall shots resize
# the viewport rather than using full_page=True (which has no effect).
DETAIL_HEIGHT = 3600
WAIT_AFTER_NAV = 2000   # ms

_base_url = os.getenv("SCREENSHOT_HOST", "http://127.0.0.1:8501")


# ── core helpers ──────────────────────────────────────────────────────────────

def _wait(page: Page, ms: int = WAIT_AFTER_NAV) -> None:
    page.wait_for_timeout(ms)


def _nav(page: Page, tab: str, extra: str = "") -> None:
    page.goto(f"{_base_url}/?tab={tab}&mock_login=true{extra}")
    _wait(page)


def _shot(page: Page, out: Path, name: str, *, tall: bool = False) -> None:
    path = out / f"{name}.png"
    if tall:
        w = page.viewport_size["width"]
        page.set_viewport_size({"width": w, "height": DETAIL_HEIGHT})
        _wait(page, 600)
        page.screenshot(path=str(path), full_page=False)
        page.set_viewport_size({"width": w, "height": VIEWPORT["height"]})
    else:
        page.screenshot(path=str(path), full_page=False)
    mode = f"tall" if tall else "viewport"
    print(f"  ✓  {name}.png  [{mode}]")


def _switch_locale(page: Page, locale: str) -> bool:
    """Force-click the hidden Streamlit locale proxy button (LOCALE_EN / LOCALE_FR)."""
    clicked = page.evaluate(f"""
        () => {{
            for (const btn of document.querySelectorAll('button')) {{
                if (btn.textContent.trim() === 'LOCALE_{locale.upper()}') {{
                    btn.click();
                    return true;
                }}
            }}
            return false;
        }}
    """)
    if clicked:
        _wait(page)
    return bool(clicked)


def _select_first_table(page: Page) -> bool:
    box = page.locator('[data-testid="stSelectbox"] input').first
    box.click()
    _wait(page, 700)
    first_opt = page.locator('[data-testid="stSelectboxVirtualDropdown"] li').first
    if not first_opt.is_visible():
        return False
    first_opt.click()
    _wait(page)
    return True


def _open_first_detail(page: Page) -> bool:
    btn = page.locator('button:has-text("View details"), button:has-text("Voir les détails")').first
    if not btn.is_visible():
        return False
    btn.click()
    _wait(page)
    return True


# ── English capture functions ─────────────────────────────────────────────────

def capture_login(page: Page, out: Path) -> None:
    print("\n── Login page")
    page.goto(_base_url)
    _wait(page)
    _shot(page, out, "01_login")


def capture_search(page: Page, out: Path) -> None:
    print("\n── Search tab")
    _nav(page, "search")
    _shot(page, out, "02_search_empty")

    box = page.locator('[data-testid="stSelectbox"] input').first
    box.click()
    _wait(page, 700)
    _shot(page, out, "03_search_autocomplete")

    first_opt = page.locator('[data-testid="stSelectboxVirtualDropdown"] li').first
    if not first_opt.is_visible():
        return
    first_opt.click()
    _wait(page)
    _shot(page, out, "04_search_results_cards")

    if not _open_first_detail(page):
        return
    _shot(page, out, "05_search_detail_panel", tall=True)

    page.evaluate("window.scrollBy(0, 500)")
    _wait(page, 500)
    _shot(page, out, "06_search_detail_columns")

    preview_btn = page.locator('button:has-text("Preview data")').first
    if preview_btn.is_visible():
        preview_btn.click()
        _wait(page)
        _shot(page, out, "07_search_data_preview_dialog")
        page.keyboard.press("Escape")
        _wait(page, 500)

    # Bookmark the table so Discovery can show a populated bookmarks tab
    page.evaluate("window.scrollTo(0, 0)")
    _wait(page, 400)
    star_btn = page.locator('button:has-text("☆")').first
    if star_btn.is_visible():
        star_btn.click()
        _wait(page, 800)
        _shot(page, out, "08_search_detail_bookmarked", tall=True)
        print("  ✓  table bookmarked for discovery showcase")

    back_btn = page.locator('button:has-text("Back to results")').first
    if back_btn.is_visible():
        back_btn.click()
        _wait(page)


def capture_catalog(page: Page, out: Path) -> None:
    print("\n── Catalog browser")
    _nav(page, "catalog")
    _shot(page, out, "09_catalog_browser")

    exp = page.locator('[data-testid="stExpander"]').first
    if exp.is_visible():
        exp.click()
        _wait(page)
        _shot(page, out, "10_catalog_expanded")


def capture_glossary(page: Page, out: Path) -> None:
    print("\n── Glossary")
    _nav(page, "glossary")
    _shot(page, out, "11_glossary")

    term = page.locator('[data-testid="stSelectbox"]').first
    if term.is_visible():
        term.click()
        _wait(page, 600)
        first = page.locator('[data-testid="stSelectboxVirtualDropdown"] li').first
        if first.is_visible():
            first.click()
            _wait(page)
            _shot(page, out, "12_glossary_term_detail", tall=True)


def capture_discovery(page: Page, out: Path) -> None:
    print("\n── Discovery")
    _nav(page, "discovery")
    _shot(page, out, "13_discovery_notable")

    try:
        bk = page.locator('button:has-text("Bookmarks")').first
        bk.wait_for(state="visible", timeout=3000)
        bk.click()
        _wait(page)
        _shot(page, out, "14_discovery_bookmarks_populated", tall=True)
    except Exception as exc:
        print(f"  ⚠  Bookmarks tab not found ({exc})")

    try:
        rc = page.locator('button:has-text("Recent")').first
        rc.wait_for(state="visible", timeout=3000)
        rc.click()
        _wait(page)
        _shot(page, out, "15_discovery_recent", tall=True)
    except Exception as exc:
        print(f"  ⚠  Recent tab not found ({exc})")


def capture_health(page: Page, out: Path) -> None:
    print("\n── Health dashboard")
    _nav(page, "health")
    _shot(page, out, "16_health_overview")

    page.evaluate("window.scrollBy(0, 500)")
    _wait(page, 600)
    _shot(page, out, "17_health_charts")


def capture_grants_filter(page: Page, out: Path) -> None:
    print("\n── Group permission filter")
    _nav(page, "search")
    if not _select_first_table(page):
        return
    if not _open_first_detail(page):
        return

    page.evaluate("window.scrollBy(0, 1400)")
    _wait(page, 600)
    _shot(page, out, "18_search_grants_section")

    group_btn = page.locator('button:has-text("Browse"), button:has-text("Search tables accessible")').first
    if group_btn.is_visible():
        group_btn.click()
        _wait(page)
        _shot(page, out, "19_group_filter_results", tall=True)


# ── French (bilingual) section ────────────────────────────────────────────────

def capture_french(page: Page, out: Path) -> None:
    """Switch UI to French and capture key screens to showcase bilingual support."""
    print("\n── French / bilingual section")
    _nav(page, "search")

    if not _switch_locale(page, "FR"):
        print("  ⚠  Could not switch to French — skipping bilingual section")
        return
    print("  ✓  locale switched to FR")

    # Search empty state in French
    _shot(page, out, "20_fr_search_empty")

    # Autocomplete
    box = page.locator('[data-testid="stSelectbox"] input').first
    box.click()
    _wait(page, 700)
    _shot(page, out, "21_fr_search_autocomplete")

    first_opt = page.locator('[data-testid="stSelectboxVirtualDropdown"] li').first
    if first_opt.is_visible():
        first_opt.click()
        _wait(page)
        _shot(page, out, "22_fr_search_results_cards")

        if _open_first_detail(page):
            _shot(page, out, "23_fr_search_detail_panel", tall=True)

    # Catalog in French
    _nav(page, "catalog")
    if not _switch_locale(page, "FR"):
        _switch_locale(page, "FR")   # locale may reset on nav — retry
    _shot(page, out, "24_fr_catalog")

    # Discovery in French
    _nav(page, "discovery")
    _switch_locale(page, "FR")
    _shot(page, out, "25_fr_discovery")

    try:
        bk = page.locator('button:has-text("Favoris")').first
        bk.wait_for(state="visible", timeout=3000)
        bk.click()
        _wait(page)
        _shot(page, out, "26_fr_discovery_bookmarks", tall=True)
    except Exception:
        pass

    # Glossary in French
    _nav(page, "glossary")
    _switch_locale(page, "FR")
    _shot(page, out, "27_fr_glossary")

    # Restore English for any subsequent captures
    _switch_locale(page, "EN")
    print("  ✓  locale restored to EN")


# ── Load test report ──────────────────────────────────────────────────────────

def capture_load_test_report(page: Page, out: Path) -> None:
    """Screenshot the saved Locust HTML report."""
    print("\n── Load test report")
    report = Path(__file__).resolve().parent.parent / "tests" / "load" / "results" / "report.html"
    if not report.exists():
        print(f"  ⚠  Report not found at {report}; skipping")
        return

    page.goto(report.as_uri())
    _wait(page, 1500)
    _shot(page, out, "28_load_test_overview")

    # Scroll down to the stats table
    page.evaluate("window.scrollBy(0, 600)")
    _wait(page, 400)
    _shot(page, out, "29_load_test_stats_table")

    # Scroll further to charts if present
    page.evaluate("window.scrollBy(0, 800)")
    _wait(page, 400)
    _shot(page, out, "30_load_test_charts")


# ── main ──────────────────────────────────────────────────────────────────────

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
        ctx = browser.new_context(viewport=viewport, device_scale_factor=2)
        page = ctx.new_page()

        # English screens — capture_search must run before capture_discovery
        # so the bookmarked table shows up in the Bookmarks tab.
        capture_login(page, out)
        capture_search(page, out)
        capture_catalog(page, out)
        capture_glossary(page, out)
        capture_discovery(page, out)
        capture_health(page, out)
        capture_grants_filter(page, out)

        # Bilingual showcase
        capture_french(page, out)

        # Load test report (opens a local HTML file, no app needed)
        capture_load_test_report(page, out)

        browser.close()

    files = sorted(out.glob("*.png"))
    print(f"\n✅  {len(files)} screenshots saved to {out}/")


if __name__ == "__main__":
    main()
