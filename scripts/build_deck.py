"""Build a marketing PowerPoint deck for Business Data Dictionary.

Usage:
    python scripts/build_deck.py
    python scripts/build_deck.py --out docs/pitch.pptx
"""

from __future__ import annotations

import argparse
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

# ── Palette (mirrors design_system/colors_and_type.css) ──────────────────────
PAPER = RGBColor(0xFA, 0xF7, 0xF0)  # --paper
INK = RGBColor(0x14, 0x11, 0x0C)  # --ink
ACCENT = RGBColor(0xB8, 0x36, 0x2A)  # --accent (oxidized red)
INK_40 = RGBColor(0x8A, 0x85, 0x7E)  # --ink-40
PAPER_DEEP = RGBColor(0xF0, 0xEB, 0xE1)  # --paper-deep

# Slide dimensions: widescreen 16:9
W = Inches(13.33)
H = Inches(7.5)

SCREENSHOTS = Path(__file__).parent.parent / "screenshots" / "latest"
OUT_DEFAULT = Path(__file__).parent.parent / "docs" / "pitch.pptx"


# ── Helpers ───────────────────────────────────────────────────────────────────


def _bg(slide, color: RGBColor):
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = color


def _box(
    slide,
    left,
    top,
    width,
    height,
    text="",
    font_size=24,
    bold=False,
    color=None,
    align=PP_ALIGN.LEFT,
    bg=None,
    italic=False,
):
    txBox = slide.shapes.add_textbox(left, top, width, height)
    if bg:
        txBox.fill.solid()
        txBox.fill.fore_color.rgb = bg
    tf = txBox.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    run.font.size = Pt(font_size)
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = color or INK
    return txBox


def _img(slide, path, left, top, width=None, height=None):
    if not Path(path).exists():
        return
    kwargs = {}
    if width:
        kwargs["width"] = width
    if height:
        kwargs["height"] = height
    slide.shapes.add_picture(str(path), left, top, **kwargs)


def _eyebrow(slide, text, top=Inches(0.45)):
    _box(
        slide,
        Inches(0.6),
        top,
        Inches(12),
        Inches(0.35),
        text=f"§ {text}".upper(),
        font_size=9,
        color=INK_40,
        align=PP_ALIGN.LEFT,
    )


def _rule(slide, top):
    """Thin horizontal rule."""
    line = slide.shapes.add_connector(
        1,  # straight
        Inches(0.6),
        top,
        Inches(12.73),
        top,
    )
    line.line.color.rgb = INK_40
    line.line.width = Pt(0.5)


def _stat_block(slide, left, top, value, label, value_size=36):
    _box(
        slide,
        left,
        top,
        Inches(2),
        Inches(0.7),
        text=value,
        font_size=value_size,
        bold=True,
        color=INK,
    )
    _box(
        slide,
        left,
        top + Inches(0.65),
        Inches(2),
        Inches(0.35),
        text=label,
        font_size=10,
        color=INK_40,
    )


def _accent_bar(
    slide, left=Inches(0.6), width=Inches(0.5), top=Inches(1.0), height=Inches(0.06)
):
    bar = slide.shapes.add_shape(1, left, top, width, height)
    bar.fill.solid()
    bar.fill.fore_color.rgb = ACCENT
    bar.line.fill.background()


# ── Slides ────────────────────────────────────────────────────────────────────


def slide_cover(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank
    _bg(slide, PAPER)

    # Left half — editorial hero
    _box(
        slide,
        Inches(0.6),
        Inches(0.5),
        Inches(6),
        Inches(0.4),
        text="§ BUSINESS DATA DICTIONARY",
        font_size=9,
        color=INK_40,
    )
    _box(
        slide,
        Inches(0.6),
        Inches(1.1),
        Inches(6.2),
        Inches(2.8),
        text="A card catalog\nfor your warehouse.",
        font_size=44,
        bold=True,
        color=INK,
    )
    _accent_bar(slide, Inches(0.6), Inches(0.08), Inches(3.75), Inches(0.06))
    _box(
        slide,
        Inches(0.6),
        Inches(3.9),
        Inches(6),
        Inches(1.0),
        text="Search tables, columns, and business terms across Unity Catalog\n— filtered to what each user has permission to see.",
        font_size=14,
        color=INK_40,
    )

    # Stats row
    _stat_block(slide, Inches(0.6), Inches(5.4), "800+", "tables indexed")
    _stat_block(slide, Inches(2.9), Inches(5.4), "4", "schemas")
    _stat_block(
        slide, Inches(5.2), Inches(5.4), "nightly", "sync cadence", value_size=22
    )

    # Right half — login screenshot
    _img(
        slide, SCREENSHOTS / "01_login.png", Inches(6.9), Inches(0.3), width=Inches(6.1)
    )


def slide_problem(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _bg(slide, INK)
    _eyebrow(slide, "The problem", top=Inches(0.5))
    _accent_bar(slide, Inches(0.6), Inches(0.08), Inches(3.75), Inches(0.06))

    _box(
        slide,
        Inches(0.6),
        Inches(1.0),
        Inches(7),
        Inches(1.8),
        text="Data is there.\nNobody can find it.",
        font_size=40,
        bold=True,
        color=PAPER,
    )

    bullets = [
        (
            "Discovery gap",
            "Business users can't browse Unity Catalog — it's a developer tool.",
        ),
        ("Permission fog", "Teams don't know which tables they're allowed to query."),
        (
            "Definition debt",
            "Column names like cust_rev_adj_usd mean nothing without context.",
        ),
        (
            "Stale docs",
            "Wiki pages are always three releases behind the actual schema.",
        ),
    ]
    for i, (title, body) in enumerate(bullets):
        top = Inches(2.6) + Inches(i * 1.1)
        _box(
            slide,
            Inches(0.6),
            top,
            Inches(1.8),
            Inches(0.35),
            text=title,
            font_size=12,
            bold=True,
            color=ACCENT,
        )
        _box(
            slide,
            Inches(2.5),
            top,
            Inches(9.5),
            Inches(0.35),
            text=body,
            font_size=12,
            color=INK_40,
        )


def slide_solution(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _bg(slide, PAPER)
    _eyebrow(slide, "The solution")
    _box(
        slide,
        Inches(0.6),
        Inches(0.9),
        Inches(8),
        Inches(0.9),
        text="One search box. Permission-trimmed results.",
        font_size=32,
        bold=True,
        color=INK,
    )
    _accent_bar(slide, Inches(0.6), Inches(0.08), Inches(5), Inches(0.06))
    _img(
        slide,
        SCREENSHOTS / "04_search_results_cards.png",
        Inches(0.4),
        Inches(1.85),
        width=Inches(12.5),
    )


def slide_detail(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _bg(slide, PAPER)
    _eyebrow(slide, "Table detail panel")
    _box(
        slide,
        Inches(0.6),
        Inches(0.9),
        Inches(9),
        Inches(0.7),
        text="Columns, comments, lineage and grants — in one view.",
        font_size=28,
        bold=True,
        color=INK,
    )
    _img(
        slide,
        SCREENSHOTS / "05_search_detail_panel.png",
        Inches(0.3),
        Inches(1.75),
        width=Inches(12.73),
    )


def slide_data_preview(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _bg(slide, PAPER)
    _eyebrow(slide, "Data preview")
    _box(
        slide,
        Inches(0.6),
        Inches(0.9),
        Inches(9),
        Inches(0.7),
        text="Real rows. Permission-checked. One click.",
        font_size=28,
        bold=True,
        color=INK,
    )
    _accent_bar(slide, Inches(0.6), Inches(0.08), Inches(4.5), Inches(0.06))
    _img(
        slide,
        SCREENSHOTS / "07_search_data_preview_dialog.png",
        Inches(0.3),
        Inches(1.75),
        width=Inches(12.73),
    )


def slide_lineage(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _bg(slide, PAPER)
    _eyebrow(slide, "Lineage & related tables")
    _box(
        slide,
        Inches(0.6),
        Inches(0.9),
        Inches(9),
        Inches(0.7),
        text="Interactive graph. Click any node to explore.",
        font_size=28,
        bold=True,
        color=INK,
    )
    _accent_bar(slide, Inches(0.6), Inches(0.08), Inches(5), Inches(0.06))
    # Two-up: initial graph + node selected state
    _img(
        slide,
        SCREENSHOTS / "08a_lineage_graph_initial.png",
        Inches(0.3),
        Inches(1.75),
        width=Inches(6.3),
    )
    _img(
        slide,
        SCREENSHOTS / "08b_lineage_graph_node_selected.png",
        Inches(6.8),
        Inches(1.75),
        width=Inches(6.3),
    )
    _box(
        slide,
        Inches(0.3),
        Inches(6.9),
        Inches(6.3),
        Inches(0.35),
        text="Initial state — physics-settled layout",
        font_size=9,
        color=INK_40,
        align=PP_ALIGN.CENTER,
    )
    _box(
        slide,
        Inches(6.8),
        Inches(6.9),
        Inches(6.3),
        Inches(0.35),
        text="After clicking a neighbour node",
        font_size=9,
        color=INK_40,
        align=PP_ALIGN.CENTER,
    )


def slide_features(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _bg(slide, PAPER)
    _eyebrow(slide, "Feature set")
    _box(
        slide,
        Inches(0.6),
        Inches(0.9),
        Inches(12),
        Inches(0.6),
        text="Everything a business user needs. Nothing they don't.",
        font_size=26,
        bold=True,
        color=INK,
    )
    _accent_bar(slide, Inches(0.6), Inches(0.08), Inches(6), Inches(0.06))

    features = [
        (
            "§ Catalog search",
            "Full-text search across tables and columns with permission-filtered results.",
        ),
        (
            "§ Glossary",
            "Business term definitions linked to the tables that implement them.",
        ),
        (
            "§ Lineage graph",
            "Multi-hop upstream/downstream lineage, permission-filtered.",
        ),
        ("§ Discovery", "Personalized bookmarks and recently viewed tables."),
        (
            "§ Health dashboard",
            "Completeness grades, DQ scores, and steward assignment per table.",
        ),
        ("§ Bilingual", "Full English / French i18n with live locale switching."),
        (
            "§ Nightly sync",
            "Metadata and permissions sync from Unity Catalog every night.",
        ),
        ("§ Local cache", "DuckDB adapter — zero-latency queries, no network hop."),
    ]
    cols = [Inches(0.6), Inches(6.8)]
    for i, (title, body) in enumerate(features):
        col = cols[i % 2]
        row = i // 2
        top = Inches(1.85) + Inches(row * 1.3)
        bg_rect = slide.shapes.add_shape(1, col, top, Inches(5.9), Inches(1.1))
        bg_rect.fill.solid()
        bg_rect.fill.fore_color.rgb = PAPER_DEEP
        bg_rect.line.fill.background()
        _box(
            slide,
            col + Inches(0.18),
            top + Inches(0.1),
            Inches(5.5),
            Inches(0.35),
            text=title,
            font_size=11,
            bold=True,
            color=ACCENT,
        )
        _box(
            slide,
            col + Inches(0.18),
            top + Inches(0.4),
            Inches(5.5),
            Inches(0.55),
            text=body,
            font_size=11,
            color=INK_40,
        )


def slide_security(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _bg(slide, INK)
    _eyebrow(slide, "Security model", top=Inches(0.5))
    _box(
        slide,
        Inches(0.6),
        Inches(1.0),
        Inches(9),
        Inches(0.9),
        text="Push-down SQL. Users cannot see what they can't query.",
        font_size=30,
        bold=True,
        color=PAPER,
    )

    points = [
        "Permission enforcement happens inside the SQL Warehouse — not in Python.",
        "Every search query JOINs tables_metadata with permissions_cache filtered to the user's Entra groups.",
        "The sentinel SELECT_ALL_USERS acts as a public-access flag — no hardcoded bypass.",
        "Admins are verified against real Entra groups even in development mode.",
        "OAuth 2.0 / OIDC via MSAL with state + nonce CSRF protection and silent token refresh.",
    ]
    for i, pt in enumerate(points):
        top = Inches(2.2) + Inches(i * 0.9)
        _box(
            slide,
            Inches(0.6),
            top,
            Inches(0.3),
            Inches(0.4),
            text="→",
            font_size=14,
            color=ACCENT,
        )
        _box(
            slide,
            Inches(1.0),
            top,
            Inches(11.7),
            Inches(0.55),
            text=pt,
            font_size=13,
            color=INK_40,
        )


def slide_performance(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _bg(slide, PAPER)
    _eyebrow(slide, "Performance — 300 concurrent users, 2-minute run")
    _box(
        slide,
        Inches(0.6),
        Inches(0.9),
        Inches(9),
        Inches(0.7),
        text="Zero failures. Sub-7 ms at p95.",
        font_size=30,
        bold=True,
        color=INK,
    )
    _accent_bar(slide, Inches(0.6), Inches(0.08), Inches(4), Inches(0.06))

    stats = [
        ("14,345", "total requests"),
        ("0 (0%)", "failures"),
        ("121 /s", "throughput"),
        ("2 ms", "p50 latency"),
        ("7 ms", "p95 latency"),
        ("13 ms", "p99 latency"),
    ]
    for i, (val, lbl) in enumerate(stats):
        col = Inches(0.6) + Inches(i % 3 * 4.2)
        top = Inches(2.0) + Inches(i // 3 * 2.0)
        bg = slide.shapes.add_shape(1, col, top, Inches(3.8), Inches(1.6))
        bg.fill.solid()
        bg.fill.fore_color.rgb = PAPER_DEEP
        bg.line.fill.background()
        _box(
            slide,
            col + Inches(0.2),
            top + Inches(0.15),
            Inches(3.4),
            Inches(0.8),
            text=val,
            font_size=36,
            bold=True,
            color=ACCENT if i == 1 else INK,
        )
        _box(
            slide,
            col + Inches(0.2),
            top + Inches(0.9),
            Inches(3.4),
            Inches(0.4),
            text=lbl,
            font_size=11,
            color=INK_40,
        )

    _box(
        slide,
        Inches(0.6),
        Inches(6.3),
        Inches(12),
        Inches(0.5),
        text="800-table DuckDB dataset · HTTP page delivery + DuckDB query layer · MacBook Pro M-series",
        font_size=9,
        color=INK_40,
        italic=True,
    )


def slide_accessibility(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _bg(slide, PAPER)
    _eyebrow(slide, "Accessibility — WCAG 2.0 axe-core audit")
    _box(
        slide,
        Inches(0.6),
        Inches(0.9),
        Inches(9),
        Inches(0.7),
        text="5 of 5 pages: zero violations.",
        font_size=30,
        bold=True,
        color=INK,
    )

    pages = [
        ("§ Catalog search", "0 violations", True),
        ("§ Catalog browser", "0 violations", True),
        ("§ Glossary", "0 violations", True),
        ("§ Discovery", "0 violations", True),
        ("§ Health dashboard", "0 violations", True),
    ]
    for i, (name, result, ok) in enumerate(pages):
        top = Inches(2.0) + Inches(i * 0.9)
        dot = slide.shapes.add_shape(
            1, Inches(0.6), top + Inches(0.1), Inches(0.18), Inches(0.18)
        )
        dot.fill.solid()
        dot.fill.fore_color.rgb = RGBColor(0x2E, 0x7D, 0x32) if ok else ACCENT
        dot.line.fill.background()
        _box(
            slide,
            Inches(1.0),
            top,
            Inches(4.5),
            Inches(0.55),
            text=name,
            font_size=13,
            bold=True,
            color=INK,
        )
        _box(
            slide,
            Inches(5.5),
            top,
            Inches(7.5),
            Inches(0.55),
            text=result,
            font_size=13,
            color=INK_40,
        )




def slide_cta(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _bg(slide, INK)
    _accent_bar(slide, Inches(0.6), Inches(0.08), Inches(13.33 - 1.2), Inches(0.08))

    _box(
        slide,
        Inches(0.6),
        Inches(1.8),
        Inches(12),
        Inches(1.6),
        text="Ready to ship.",
        font_size=56,
        bold=True,
        color=PAPER,
        align=PP_ALIGN.CENTER,
    )
    _box(
        slide,
        Inches(0.6),
        Inches(3.4),
        Inches(12),
        Inches(0.7),
        text="Self-hosted · Databricks Unity Catalog · Microsoft Entra ID",
        font_size=16,
        color=INK_40,
        align=PP_ALIGN.CENTER,
    )
    _box(
        slide,
        Inches(0.6),
        Inches(4.3),
        Inches(12),
        Inches(0.6),
        text="github.com/<org>/data-dictionary",
        font_size=14,
        color=ACCENT,
        align=PP_ALIGN.CENTER,
    )

    _box(
        slide,
        Inches(0.6),
        Inches(6.7),
        Inches(12),
        Inches(0.4),
        text="§ Business Data Dictionary",
        font_size=9,
        color=INK_40,
        align=PP_ALIGN.CENTER,
    )


# ── Main ──────────────────────────────────────────────────────────────────────


def build(out: Path):
    prs = Presentation()
    prs.slide_width = W
    prs.slide_height = H

    slide_cover(prs)
    slide_problem(prs)
    slide_solution(prs)
    slide_detail(prs)
    slide_data_preview(prs)
    slide_lineage(prs)
    slide_features(prs)
    slide_security(prs)
    slide_performance(prs)
    slide_accessibility(prs)
    slide_cta(prs)

    out.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(out))
    print(
        f"✅  Saved {out}  ({out.stat().st_size // 1024} KB,  {len(prs.slides)} slides)"
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT_DEFAULT))
    args = ap.parse_args()
    build(Path(args.out))
