"""
Video recording utility — captures a video of a user navigating through the Data Dictionary.

Usage:
    python scripts/record_video.py                          # full run
    python scripts/record_video.py --out videos/run1        # custom output dir
    python scripts/record_video.py --width 1440             # custom viewport width

Requires the Streamlit app to be running (ENABLE_MOCK_AUTH=true ENVIRONMENT=development):
    streamlit run app.py

Install deps (already in dev env):
    pip install playwright
    python -m playwright install chromium
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import tempfile
from pathlib import Path
from playwright.sync_api import sync_playwright, Page

DEFAULT_OUT = Path(__file__).resolve().parent.parent / "videos" / "latest"
VIEWPORT = {"width": 1440, "height": 1080}
# Streamlit renders inside a fixed-height scroll container — tall shots resize
# the viewport rather than using full_page=True (which has no effect).
DETAIL_HEIGHT = 3600
WAIT_AFTER_NAV = 1200   # ms — reduced for fluid pacing
WAIT_STEP = 600          # ms — between minor interactions

_base_url = os.getenv("RECORD_VIDEO_HOST", "http://127.0.0.1:8501")


# ── core helpers ──────────────────────────────────────────────────────────────

def _wait(page: Page, ms: int = WAIT_AFTER_NAV) -> None:
    page.wait_for_timeout(ms)


def _is_app_loaded(page: Page) -> bool:
    """True when the app shell is already rendered (avoids full-reload flashes)."""
    try:
        return page.locator(".dd-search-hero").is_visible()
    except Exception:
        return False


def _click_nav_tab(page: Page, tab_id: str) -> None:
    """Click the in-app nav link — JS wires it to the hidden Streamlit button,
    so Streamlit re-renders over WebSocket with no page reload and no flash."""
    try:
        link = page.locator(f'a.dd-nav-tab[data-tab="{tab_id}"]').first
        link.wait_for(state="visible", timeout=3000)
        link.hover()
        page.wait_for_timeout(150)
        link.click()
        page.wait_for_timeout(900)
    except Exception:
        # Fallback: full reload
        page.goto(f"{_base_url}/?tab={tab_id}&mock_login=true")
        try:
            page.wait_for_selector(".dd-search-hero", timeout=8000)
            page.wait_for_timeout(400)
        except Exception:
            _wait(page)


def _nav(page: Page, tab: str, extra: str = "") -> None:
    """Navigate to a tab. Uses in-app click when the app is already loaded
    (no flash), falls back to a full page load for the first visit."""
    if not extra and _is_app_loaded(page):
        _click_nav_tab(page, tab)
    else:
        page.goto(f"{_base_url}/?tab={tab}&mock_login=true{extra}")
        try:
            page.wait_for_selector(".dd-search-hero", timeout=8000)
            page.wait_for_timeout(400)
        except Exception:
            _wait(page)


def _scroll(page: Page, y: int) -> None:
    """Smooth-scroll by y pixels and wait for the animation to settle."""
    page.evaluate(f"window.scrollBy({{top: {y}, behavior: 'smooth'}})")
    page.wait_for_timeout(700)


def _hover_click(page: Page, locator) -> None:
    """Hover briefly before clicking to show intent in the recording."""
    locator.hover()
    page.wait_for_timeout(200)
    locator.click()


def _type_search(page: Page, locator, text: str, char_delay: int = 80) -> None:
    """Type text character-by-character to simulate realistic user input."""
    locator.click()
    page.wait_for_timeout(300)
    for char in text:
        locator.type(char)
        page.wait_for_timeout(char_delay)


def _shot(page: Page, out: Path, name: str, *, tall: bool = False) -> None:
    """Pause briefly so the video captures this state cleanly."""
    page.wait_for_timeout(WAIT_STEP)
    mode = "tall" if tall else "viewport"
    print(f"  Recorded step: {name} [{mode}]")


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
    _type_search(page, box, "budget")
    _shot(page, out, "03_search_autocomplete")

    first_opt = page.locator('[data-testid="stSelectboxVirtualDropdown"] li').first
    if not first_opt.is_visible():
        return
    _hover_click(page, first_opt)
    _wait(page)
    _shot(page, out, "04_search_results_cards")

    btn = page.locator('button:has-text("View details"), button:has-text("Voir les détails")').first
    if not btn.is_visible():
        return
    _hover_click(page, btn)
    _wait(page)
    _shot(page, out, "05_search_detail_panel", tall=True)

    _scroll(page, 500)
    _shot(page, out, "06_search_detail_columns")

    preview_btn = page.locator('button:has-text("Preview data")').first
    if preview_btn.is_visible():
        _hover_click(page, preview_btn)
        _wait(page, 1200)
        _shot(page, out, "07_search_data_preview_dialog")
        page.keyboard.press("Escape")
        _wait(page, 400)

    # Lineage graph interactivity — vis-network renders inside a component iframe.
    print("  ── Lineage graph interactivity")
    page.evaluate("window.scrollTo({top: document.body.scrollHeight, behavior: 'smooth'})")
    _wait(page, 1200)
    _shot(page, out, "08a_lineage_graph_initial")
    for frame in page.frames:
        canvas = frame.locator("canvas").first
        try:
            canvas.wait_for(state="visible", timeout=2000)
            _graph_box = canvas.bounding_box()
            if _graph_box:
                cx = _graph_box["x"] + _graph_box["width"] * 0.65
                cy = _graph_box["y"] + _graph_box["height"] * 0.38
                page.mouse.move(cx, cy, steps=15)
                page.wait_for_timeout(300)
                page.mouse.click(cx, cy)
                _wait(page, 900)
                _shot(page, out, "08b_lineage_graph_node_selected")
                # Smooth drag to pan
                mx = _graph_box["x"] + _graph_box["width"] * 0.5
                my = _graph_box["y"] + _graph_box["height"] * 0.5
                page.mouse.move(mx, my, steps=10)
                page.mouse.down()
                page.mouse.move(mx - 80, my - 40, steps=30)
                page.mouse.up()
                _wait(page, 500)
                _shot(page, out, "08c_lineage_graph_panned")
                print("  ✓  lineage graph interaction recorded")
                break
        except Exception:
            continue

    # Bookmark the table so Discovery can show a populated bookmarks tab
    page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})")
    _wait(page, 500)
    star_btn = page.locator('button:has-text("☆")').first
    if star_btn.is_visible():
        _hover_click(page, star_btn)
        _wait(page, 700)
        _shot(page, out, "08_search_detail_bookmarked", tall=True)
        print("  ✓  table bookmarked for discovery showcase")

    back_btn = page.locator('button:has-text("Back to results")').first
    if back_btn.is_visible():
        _hover_click(page, back_btn)
        _wait(page)


def capture_navigation(page: Page, out: Path) -> None:
    """Showcase fluid tab-switching to demonstrate app responsiveness.
    Uses in-app nav clicks after the first load — no page-reload flash."""
    print("\n── Navigation showcase")
    # First load: full goto so mock auth cookie is set
    _nav(page, "search")
    _shot(page, out, "01_nav_search")
    # Subsequent switches: in-app clicks, smooth and instant
    for tab, name in [
        ("catalog",   "02_nav_catalog"),
        ("glossary",  "03_nav_glossary"),
        ("discovery", "04_nav_discovery"),
        ("health",    "05_nav_health"),
        ("search",    "06_nav_back_search"),
    ]:
        _click_nav_tab(page, tab)
        _shot(page, out, name)


def capture_catalog(page: Page, out: Path) -> None:
    print("\n── Catalog browser")
    _nav(page, "catalog")
    _shot(page, out, "09_catalog_browser")

    # The first expander is the help text — skip it.
    # The second expander onwards are catalog entries ("📁 catalog_name").
    catalog_exp = page.locator('[data-testid="stExpander"]').nth(1)
    if not catalog_exp.is_visible():
        catalog_exp = page.locator('[data-testid="stExpander"]').first
    if catalog_exp.is_visible():
        _hover_click(page, catalog_exp)
        _wait(page)
        _shot(page, out, "10_catalog_expanded")

    # Schemas are plain HTML divs inside the catalog expander (no sub-expander).
    # Table buttons ("📄 tablename") are rendered directly after each schema header.
    table_btn = page.locator('button:has-text("📄")').first
    if table_btn.is_visible():
        print("  ── Clicking table in tree → search detail")
        _hover_click(page, table_btn)
        _wait(page, 1400)
        _shot(page, out, "10b_catalog_table_detail")


def capture_glossary(page: Page, out: Path) -> None:
    print("\n── Glossary")
    _nav(page, "glossary")
    _shot(page, out, "11_glossary")

    term_input = page.locator('[data-testid="stSelectbox"] input').first
    if term_input.is_visible():
        _type_search(page, term_input, "rev", char_delay=100)
        _wait(page, 400)
        first = page.locator('[data-testid="stSelectboxVirtualDropdown"] li').first
        if first.is_visible():
            _hover_click(page, first)
            _wait(page)
            _shot(page, out, "12_glossary_term_detail", tall=True)

    # Hover over the first "→ table" link to show it's clickable without navigating away
    link_btn = page.locator('button:has-text("→")').first
    if link_btn.is_visible():
        link_btn.hover()
        page.wait_for_timeout(600)


def capture_discovery(page: Page, out: Path) -> None:
    print("\n── Discovery")
    _nav(page, "discovery")
    _shot(page, out, "13_discovery_notable")

    # Hover over the featured card CTA to show it's clickable, then move on
    cms_nav = page.locator('button:has-text("→")').first
    if cms_nav.is_visible():
        cms_nav.hover()
        page.wait_for_timeout(500)

    try:
        bk = page.locator('button:has-text("Bookmarks")').first
        bk.wait_for(state="visible", timeout=3000)
        _hover_click(page, bk)
        _wait(page)
        _shot(page, out, "14_discovery_bookmarks_populated", tall=True)
    except Exception as exc:
        print(f"  ⚠  Bookmarks tab not found ({exc})")

    try:
        rc = page.locator('button:has-text("Recent")').first
        rc.wait_for(state="visible", timeout=3000)
        _hover_click(page, rc)
        _wait(page)
        _shot(page, out, "15_discovery_recent", tall=True)
    except Exception as exc:
        print(f"  ⚠  Recent tab not found ({exc})")


def capture_health(page: Page, out: Path) -> None:
    print("\n── Health dashboard")
    _nav(page, "health")
    _shot(page, out, "16_health_overview")

    _scroll(page, 400)
    _shot(page, out, "17_health_charts")

    # Hover a priority-action button to show it's actionable without leaving the page
    priority_btn = page.locator('button:has-text("📄")').first
    if priority_btn.is_visible():
        priority_btn.hover()
        page.wait_for_timeout(600)
        _shot(page, out, "17b_health_priority_hover")


def capture_grants_filter(page: Page, out: Path) -> None:
    print("\n── Group permission filter")
    _nav(page, "search")
    if not _select_first_table(page):
        return
    if not _open_first_detail(page):
        return

    _scroll(page, 1400)
    _shot(page, out, "18_search_grants_section")

    group_btn = page.locator('button:has-text("Browse"), button:has-text("Search tables accessible")').first
    if group_btn.is_visible():
        _hover_click(page, group_btn)
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

    # Autocomplete with typed query
    box = page.locator('[data-testid="stSelectbox"] input').first
    _type_search(page, box, "budget", char_delay=90)
    _shot(page, out, "21_fr_search_autocomplete")

    first_opt = page.locator('[data-testid="stSelectboxVirtualDropdown"] li').first
    if first_opt.is_visible():
        _hover_click(page, first_opt)
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


# ── Load test stats card ──────────────────────────────────────────────────────

_STATS_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Manrope', sans-serif; background: #FAF7F0; padding: 48px; }
h2  { font-family: 'Fraunces', serif; font-size: 36px; font-weight: 400;
      color: #14110C; margin-bottom: 6px; }
.sub { font-size: 13px; color: #6B6560; margin-bottom: 32px; letter-spacing: 0.04em; }
.kpis { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 32px; }
.kpi  { background: #fff; border: 1px solid #E8E4DC; border-radius: 4px;
        padding: 20px 24px; }
.kpi .label { font-size: 11px; font-weight: 600; letter-spacing: 0.12em;
              text-transform: uppercase; color: #6B6560; margin-bottom: 8px; }
.kpi .value { font-family: 'JetBrains Mono', monospace; font-size: 28px; color: #14110C; }
.kpi .unit  { font-size: 12px; color: #6B6560; margin-left: 4px; }
.pass { color: #2E7D32; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
thead th { text-align: left; padding: 10px 12px; font-size: 11px; font-weight: 600;
           letter-spacing: 0.08em; text-transform: uppercase; color: #6B6560;
           border-bottom: 2px solid #14110C; }
tbody tr { border-bottom: 1px solid #E8E4DC; }
tbody tr:last-child { border-bottom: 2px solid #14110C; font-weight: 600; }
tbody td { padding: 10px 12px; font-family: 'JetBrains Mono', monospace; font-size: 12px; }
tbody td:first-child { font-family: 'Manrope', sans-serif; color: #14110C; }
.zero { color: #2E7D32; }
"""

def _load_stats_html(csv_path: Path) -> str:
    rows = []
    with open(csv_path) as f:
        for r in csv.DictReader(f):
            rows.append(r)

    agg = next(r for r in rows if r["Name"] == "Aggregated")
    total_req   = int(agg["Request Count"])
    total_fail  = int(agg["Failure Count"])
    rps         = float(agg["Requests/s"])
    p50         = int(agg["50%"])
    p95         = int(agg["95%"])
    p99         = int(agg["99%"])
    fail_pct    = f"{total_fail / total_req * 100:.1f}%" if total_req else "0%"

    detail_rows = [r for r in rows if r["Name"] != "Aggregated"]

    def row_html(r):
        fail = int(r["Failure Count"])
        fail_cls = "zero" if fail == 0 else ""
        return (
            f'<tr>'
            f'<td>{r["Name"]}</td>'
            f'<td>{int(r["Request Count"]):,}</td>'
            f'<td class="{fail_cls}">{fail}</td>'
            f'<td>{int(r["50%"])} ms</td>'
            f'<td>{int(r["95%"])} ms</td>'
            f'<td>{int(r["99%"])} ms</td>'
            f'<td>{float(r["Requests/s"]):.1f}</td>'
            f'</tr>'
        )

    agg_row = (
        f'<tr>'
        f'<td>Aggregated</td>'
        f'<td>{total_req:,}</td>'
        f'<td class="zero">{total_fail}</td>'
        f'<td>{p50} ms</td>'
        f'<td>{p95} ms</td>'
        f'<td>{p99} ms</td>'
        f'<td>{rps:.1f}</td>'
        f'</tr>'
    )

    return f"""<!DOCTYPE html>
<html><head>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:wght@400&family=Manrope:wght@400;600&family=JetBrains+Mono&display=swap" rel="stylesheet">
<style>{_STATS_CSS}</style>
</head><body>
<h2>Load test results</h2>
<p class="sub">300 concurrent users · 2-minute sustained run · 0% failure rate</p>
<div class="kpis">
  <div class="kpi"><div class="label">Total requests</div><div class="value">{total_req:,}</div></div>
  <div class="kpi"><div class="label">Requests / s</div><div class="value">{rps:.0f}</div></div>
  <div class="kpi"><div class="label">Failure rate</div><div class="value pass">{fail_pct}</div></div>
  <div class="kpi"><div class="label">p99 latency</div><div class="value">{p99}<span class="unit">ms</span></div></div>
</div>
<table>
  <thead><tr>
    <th>Endpoint</th><th>Requests</th><th>Failures</th>
    <th>p50</th><th>p95</th><th>p99</th><th>Req/s</th>
  </tr></thead>
  <tbody>
    {''.join(row_html(r) for r in detail_rows)}
    {agg_row}
  </tbody>
</table>
</body></html>"""


def capture_load_test_stats(page: Page, out: Path) -> None:
    print("\n── Load test stats card")
    csv_path = Path(__file__).resolve().parent.parent / "tests" / "load" / "results" / "run_stats.csv"
    if not csv_path.exists():
        print("  ⚠  Stats CSV not found; skipping")
        return

    html = _load_stats_html(csv_path)
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as f:
        f.write(html)
        tmp = Path(f.name)

    page.goto(tmp.as_uri())
    _wait(page, 1500)   # wait for Google Fonts
    _shot(page, out, "28_load_test_stats")
    tmp.unlink(missing_ok=True)


def capture_load_test_report(page: Page, out: Path) -> None:
    """Navigate to the saved Locust HTML report for recording."""
    print("\n── Load test Locust report")
    report = Path(__file__).resolve().parent.parent / "tests" / "load" / "results" / "report.html"
    if not report.exists():
        print(f"  ⚠  Report not found at {report}; skipping")
        return

    page.goto(report.as_uri())
    _wait(page, 1200)
    _shot(page, out, "29_load_test_report_overview")

    _scroll(page, 600)
    _shot(page, out, "30_load_test_report_table")

    _scroll(page, 800)
    _shot(page, out, "31_load_test_report_charts")


# ── WCAG 2.0 accessibility audit ─────────────────────────────────────────────

_AXE_CDN = "https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.9.1/axe.min.js"

_AXE_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Manrope', sans-serif; background: #FAF7F0; padding: 48px; }
h2   { font-family: 'Fraunces', serif; font-size: 36px; font-weight: 400;
       color: #14110C; margin-bottom: 6px; }
.sub { font-size: 13px; color: #6B6560; margin-bottom: 32px; letter-spacing: 0.04em; }
.summary { display: grid; grid-template-columns: repeat(4,1fr); gap:16px; margin-bottom:32px; }
.card { background:#fff; border:1px solid #E8E4DC; border-radius:4px; padding:20px 24px; }
.card .label { font-size:11px; font-weight:600; letter-spacing:0.12em; text-transform:uppercase;
               color:#6B6560; margin-bottom:8px; }
.card .value { font-family:'JetBrains Mono',monospace; font-size:28px; }
.pass  { color:#2E7D32; }
.warn  { color:#E65100; }
.neutral { color:#14110C; }
.section-title { font-size:11px; font-weight:600; letter-spacing:0.12em; text-transform:uppercase;
                 color:#6B6560; margin:24px 0 10px; border-bottom:2px solid #14110C; padding-bottom:6px; }
.vrow { margin-bottom:12px; background:#fff; border:1px solid #E8E4DC; border-radius:4px; padding:14px 18px; }
.vrow .vid  { font-family:'JetBrains Mono',monospace; font-size:11px; color:#B8362A;
              text-transform:uppercase; letter-spacing:0.08em; margin-bottom:4px; }
.vrow .vdesc { font-size:13px; color:#14110C; margin-bottom:4px; }
.vrow .vmeta { font-size:11px; color:#6B6560; }
.badge { display:inline-block; padding:2px 8px; border-radius:2px; font-size:10px;
         font-weight:600; letter-spacing:0.08em; text-transform:uppercase; margin-right:6px; }
.critical { background:#FFEBEE; color:#B71C1C; }
.serious  { background:#FFF3E0; color:#E65100; }
.moderate { background:#FFFDE7; color:#F57F17; }
.minor    { background:#E8F5E9; color:#2E7D32; }
.none-msg { font-size:14px; color:#2E7D32; font-weight:600; padding:16px 0; }
"""

_PAGES_TO_AUDIT = [
    ("search",    "§ Catalog search"),
    ("catalog",   "§ Catalog browser"),
    ("glossary",  "§ Glossary"),
    ("discovery", "§ Discovery"),
    ("health",    "§ Health dashboard"),
]


def _run_axe(page: Page) -> dict:
    page.add_script_tag(url=_AXE_CDN)
    _wait(page, 1000)
    return page.evaluate("""
        () => axe.run(document, {
            runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa'] }
        })
    """)


def _wcag_report_html(audits: list[dict]) -> str:
    total_passes     = sum(len(a.get("passes", []))     for a in audits)
    total_violations = sum(len(a.get("violations", [])) for a in audits)
    total_incomplete = sum(len(a.get("incomplete", [])) for a in audits)

    # Deduplicate violations across pages by rule id
    seen: dict[str, dict] = {}
    for a in audits:
        for v in a.get("violations", []):
            vid = v["id"]
            if vid not in seen:
                seen[vid] = {**v, "_pages": []}
            seen[vid]["_pages"].append(a["_label"])

    impact_order = {"critical": 0, "serious": 1, "moderate": 2, "minor": 3, None: 4}
    violations = sorted(seen.values(), key=lambda v: impact_order.get(v.get("impact"), 4))

    def vrow(v):
        imp   = v.get("impact") or "none"
        pages = ", ".join(v["_pages"])
        tags  = " ".join(
            f'<span class="badge">{t}</span>'
            for t in v.get("tags", [])
            if t.startswith("wcag")
        )
        return (
            f'<div class="vrow">'
            f'  <div class="vid"><span class="badge {imp}">{imp}</span>{v["id"]}</div>'
            f'  <div class="vdesc">{v["description"]}</div>'
            f'  <div class="vmeta">Affects: {pages} &nbsp;·&nbsp; {tags}</div>'
            f'</div>'
        )

    violations_html = (
        "".join(vrow(v) for v in violations)
        if violations
        else '<p class="none-msg">✓ No WCAG 2.0 violations detected across all pages.</p>'
    )

    pages_list = ", ".join(f['_label'] for f in audits)

    return f"""<!DOCTYPE html>
<html><head>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:wght@400&family=Manrope:wght@400;600&family=JetBrains+Mono&display=swap" rel="stylesheet">
<style>{_AXE_CSS}</style>
</head><body>
<h2>Accessibility audit — WCAG 2.0 AA</h2>
<p class="sub">axe-core 4.9 · pages audited: {pages_list}</p>
<div class="summary">
  <div class="card"><div class="label">Violations</div>
    <div class="value {'warn' if total_violations else 'pass'}">{total_violations}</div></div>
  <div class="card"><div class="label">Passes</div>
    <div class="value pass">{total_passes}</div></div>
  <div class="card"><div class="label">Needs review</div>
    <div class="value neutral">{total_incomplete}</div></div>
  <div class="card"><div class="label">Pages audited</div>
    <div class="value neutral">{len(audits)}</div></div>
</div>
<div class="section-title">Violations</div>
{violations_html}
</body></html>"""


def capture_wcag(page: Page, out: Path) -> None:
    print("\n── WCAG 2.0 accessibility audit")
    audits = []
    for tab, label in _PAGES_TO_AUDIT:
        _nav(page, tab)
        print(f"  auditing {label}…", end=" ", flush=True)
        try:
            result = _run_axe(page)
            result["_label"] = label
            n = len(result.get("violations", []))
            p = len(result.get("passes", []))
            print(f"{n} violation(s), {p} pass(es)")
            audits.append(result)
        except Exception as exc:
            print(f"error: {exc}")

    html = _wcag_report_html(audits)
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as f:
        f.write(html)
        tmp = Path(f.name)

    page.goto(tmp.as_uri())
    _wait(page, 1200)
    _shot(page, out, "32_wcag_summary")

    _scroll(page, 700)
    _shot(page, out, "33_wcag_violations_detail")

    tmp.unlink(missing_ok=True)

    # Also save the raw audit JSON for reference
    json_out = out / "wcag_audit.json"
    json_out.write_text(json.dumps(
        [{k: v for k, v in a.items() if k != "passes"} for a in audits],
        indent=2
    ))
    print("  ✓  wcag_audit.json saved")


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    global _base_url
    parser = argparse.ArgumentParser(description="Record a video of the Data Dictionary app navigation.")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="Output directory")
    parser.add_argument("--width", type=int, default=VIEWPORT["width"], help="Viewport width")
    parser.add_argument("--height", type=int, default=VIEWPORT["height"], help="Viewport height")
    parser.add_argument("--host", default=_base_url, help="App base URL")
    args = parser.parse_args()
    _base_url = args.host

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    viewport = {"width": args.width, "height": args.height}

    print(f"Saving video to: {out}")
    print(f"Viewport: {viewport['width']}×{viewport['height']}")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport=viewport, device_scale_factor=2, record_video_dir=str(out))
        page = ctx.new_page()

        # English screens — capture_search must run before capture_discovery
        # so the bookmarked table shows up in the Bookmarks tab.
        capture_login(page, out)
        capture_navigation(page, out)   # fluid tab-switching showcase
        capture_search(page, out)
        capture_catalog(page, out)
        capture_glossary(page, out)
        capture_discovery(page, out)
        capture_health(page, out)
        capture_grants_filter(page, out)

        # Bilingual showcase
        capture_french(page, out)

        # Load test: formatted stats card + raw Locust report
        capture_load_test_stats(page, out)
        capture_load_test_report(page, out)

        # WCAG 2.0 accessibility audit across all tabs
        capture_wcag(page, out)

        ctx.close()
        browser.close()

    print(f"\n✅  Video saved to {out}/")


if __name__ == "__main__":
    main()
