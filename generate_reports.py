"""
generate_reports.py — Business Data Dictionary presentation generator.

Produces a branded PowerPoint from screenshots/latest/*.png.

Usage:
    python generate_reports.py
    python generate_reports.py --src screenshots/latest --out reports/walkthrough.pptx

Layout per slide (10" × 7.5"):
    ┌─────────────────────────────────────────────────────────┐
    │  ■ Data Dictionary          [slide title]    [nn / NN]  │ 0.62"  header (#14110C)
    ├─────────────────────────────────────────────────────────┤ 0.025" rule  (#B8362A)
    │                                                         │
    │                    [screenshot]                         │  6.1"  content
    │                                                         │
    ├─────────────────────────────────────────────────────────┤ 0.015" rule  (#2C2A27)
    │  [section name]                    Data Dictionary · date│ 0.38"  footer (#FAF7F0)
    └─────────────────────────────────────────────────────────┘
"""
from __future__ import annotations

import argparse
import os
import re
from datetime import date
from pathlib import Path

from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

# ── Design tokens (mirror design_system/colors_and_type.css) ─────────────────

INK     = RGBColor(0x14, 0x11, 0x0C)   # --ink
PAPER   = RGBColor(0xFA, 0xF7, 0xF0)   # --paper
ACCENT  = RGBColor(0xB8, 0x36, 0x2A)   # --accent (oxidized red)
MUTED   = RGBColor(0x6B, 0x65, 0x5C)   # --ink-muted
RULE    = RGBColor(0x2C, 0x2A, 0x27)   # subtle dark rule

# Slide geometry (inches) — 10 × 7.5 standard
W  = Inches(10)
H  = Inches(7.5)
HDR_H  = Inches(0.62)      # header height
RULE_H = Inches(0.025)     # accent rule under header
FTR_RULE_H = Inches(0.015) # footer rule
FTR_H  = Inches(0.38)      # footer height
PAD    = Inches(0.22)      # horizontal padding inside header/footer
IMG_PAD = Inches(0.18)     # padding around screenshot

CONTENT_TOP = HDR_H + RULE_H
CONTENT_BOT = H - FTR_H - FTR_RULE_H
CONTENT_H   = CONTENT_BOT - CONTENT_TOP

# Fonts — use Fraunces/Manrope if viewer has them, else fall back gracefully
FONT_DISPLAY = "Fraunces"
FONT_BODY    = "Manrope"
FONT_MONO    = "JetBrains Mono"


# ── Section grouping ──────────────────────────────────────────────────────────

def _section_for(num: int) -> str:
    if num == 0:
        return "Introduction"
    if num <= 19:
        return "English UI"
    if num <= 27:
        return "French UI"
    return "Load test & WCAG"


def _human_title(filename: str) -> str:
    """'20_fr_search_empty.png' → 'FR · Search empty'"""
    stem = Path(filename).stem
    stem = re.sub(r"^\d+_", "", stem)          # strip leading number
    if stem.startswith("fr_"):
        stem = "FR · " + stem[3:]
    stem = stem.replace("_", " ")
    # Capitalize only the first word
    return stem[0].upper() + stem[1:] if stem else filename


def _file_num(filename: str) -> int:
    m = re.match(r"^(\d+)", filename)
    return int(m.group(1)) if m else 999


# ── python-pptx helpers ───────────────────────────────────────────────────────

def _blank_slide(prs: Presentation) -> object:
    return prs.slides.add_slide(prs.slide_layouts[6])  # blank layout


def _rect(slide, left, top, width, height, fill: RGBColor):
    shape = slide.shapes.add_shape(
        1,  # MSO_SHAPE_TYPE.RECTANGLE
        left, top, width, height,
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill
    shape.line.fill.background()   # no border
    return shape


def _textbox(slide, left, top, width, height,
             text: str, size: float, color: RGBColor,
             bold=False, align=PP_ALIGN.LEFT, font=FONT_BODY, italic=False):
    txb = slide.shapes.add_textbox(left, top, width, height)
    tf  = txb.text_frame
    tf.word_wrap = False
    p   = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    run.font.size = Pt(size)
    run.font.color.rgb = color
    run.font.bold  = bold
    run.font.italic = italic
    run.font.name  = font
    return txb


# ── Slide builders ────────────────────────────────────────────────────────────

def _add_header_footer(slide, title: str, section: str,
                       page_num: int, total: int, today: str):
    """Add branded header bar + accent rule + footer rule + footer to a slide."""

    # ── Header background ────────────────────────────────────────────────────
    _rect(slide, 0, 0, W, HDR_H, INK)

    # Logo mark: small square in accent colour
    mark_size = Inches(0.28)
    mark_top  = (HDR_H - mark_size) / 2
    mark_left = PAD
    _rect(slide, mark_left, mark_top, mark_size, mark_size, ACCENT)

    # Product name next to mark
    name_left = mark_left + mark_size + Inches(0.12)
    _textbox(
        slide, name_left, 0, Inches(2.8), HDR_H,
        "Data Dictionary", 11,
        RGBColor(0xFF, 0xFF, 0xFF), bold=True,
        font=FONT_DISPLAY,
        align=PP_ALIGN.LEFT,
    )

    # Slide title (centre)
    _textbox(
        slide, Inches(3.2), 0, Inches(4.4), HDR_H,
        title, 11,
        RGBColor(0xCC, 0xC8, 0xC2),
        align=PP_ALIGN.CENTER,
        font=FONT_BODY,
    )

    # Page number (right)
    _textbox(
        slide, W - Inches(1.6), 0, Inches(1.4), HDR_H,
        f"{page_num} / {total}", 9.5,
        RGBColor(0x88, 0x82, 0x7A),
        align=PP_ALIGN.RIGHT,
        font=FONT_MONO,
    )

    # ── Accent rule under header ──────────────────────────────────────────────
    _rect(slide, 0, HDR_H, W, RULE_H, ACCENT)

    # ── Footer rule ───────────────────────────────────────────────────────────
    ftr_rule_top = H - FTR_H - FTR_RULE_H
    _rect(slide, 0, ftr_rule_top, W, FTR_RULE_H, RULE)

    # ── Footer background ────────────────────────────────────────────────────
    ftr_top = H - FTR_H
    _rect(slide, 0, ftr_top, W, FTR_H, PAPER)

    # Footer left: section name
    _textbox(
        slide, PAD, ftr_top, Inches(5), FTR_H,
        section, 8.5,
        MUTED, align=PP_ALIGN.LEFT,
        font=FONT_BODY, italic=True,
    )

    # Footer right: product · date
    _textbox(
        slide, W - Inches(3.4), ftr_top, Inches(3.2), FTR_H,
        f"Data Dictionary  ·  {today}", 8.5,
        MUTED, align=PP_ALIGN.RIGHT,
        font=FONT_BODY,
    )


def _add_screenshot(slide, img_path: str):
    """Fit the screenshot into the content zone, centred, preserving aspect ratio."""
    with Image.open(img_path) as pil:
        img_w, img_h = pil.size

    aspect = img_w / img_h

    avail_w = W - 2 * IMG_PAD
    avail_h = CONTENT_H - 2 * IMG_PAD

    if aspect > (avail_w / avail_h):
        disp_w = avail_w
        disp_h = avail_w / aspect
    else:
        disp_h = avail_h
        disp_w = avail_h * aspect

    left = (W - disp_w) / 2
    top  = CONTENT_TOP + (CONTENT_H - disp_h) / 2

    slide.shapes.add_picture(img_path, left, top, width=disp_w, height=disp_h)


def _add_title_slide(prs: Presentation, today: str):
    slide = _blank_slide(prs)

    # Full bleed ink background
    _rect(slide, 0, 0, W, H, INK)

    # Accent bar — left edge
    _rect(slide, 0, 0, Inches(0.18), H, ACCENT)

    # Logo mark (large, centred vertically in upper half)
    mark = Inches(0.7)
    _rect(slide, Inches(0.55), Inches(1.9), mark, mark, ACCENT)

    # Product name
    _textbox(
        slide, Inches(0.55), Inches(2.75), Inches(8), Inches(1.5),
        "Data Dictionary", 40,
        RGBColor(0xFF, 0xFF, 0xFF), bold=True,
        font=FONT_DISPLAY,
    )

    # Subtitle
    _textbox(
        slide, Inches(0.55), Inches(3.9), Inches(8), Inches(0.8),
        "Product walkthrough", 18,
        RGBColor(0xCC, 0xC8, 0xC2),
        font=FONT_BODY,
    )

    # Date
    _textbox(
        slide, Inches(0.55), Inches(6.6), Inches(6), Inches(0.6),
        today, 11,
        RGBColor(0x6B, 0x65, 0x5C),
        font=FONT_MONO,
    )


def _add_section_slide(prs: Presentation, section: str,
                       description: str, today: str):
    slide = _blank_slide(prs)
    _rect(slide, 0, 0, W, H, PAPER)

    # Left accent strip
    _rect(slide, 0, 0, Inches(0.22), H, ACCENT)

    # Section label (eyebrow)
    _textbox(
        slide, Inches(0.55), Inches(2.6), Inches(9), Inches(0.55),
        "§ " + section.upper(), 11,
        ACCENT, bold=True,
        font=FONT_BODY,
    )

    # Section title
    _textbox(
        slide, Inches(0.55), Inches(3.1), Inches(9), Inches(1.2),
        section, 36,
        INK, bold=True,
        font=FONT_DISPLAY,
    )

    # Description
    if description:
        _textbox(
            slide, Inches(0.55), Inches(4.35), Inches(7.5), Inches(0.7),
            description, 13,
            MUTED,
            font=FONT_BODY,
        )

    # Bottom rule + date
    _rect(slide, Inches(0.55), Inches(6.85), Inches(9.1), Inches(0.02), MUTED)
    _textbox(
        slide, Inches(0.55), Inches(6.95), Inches(9), Inches(0.4),
        f"Data Dictionary  ·  {today}", 9,
        MUTED,
        font=FONT_BODY, italic=True,
    )


# ── Section metadata ──────────────────────────────────────────────────────────

_SECTION_DESCRIPTIONS = {
    "English UI":        "Core product screens — search, catalog browser, glossary, and data health.",
    "French UI":         "Full bilingual experience — all key flows in Canadian French.",
    "Load test & WCAG":  "Performance under 300 concurrent users and WCAG 2.0 accessibility audit results.",
}


# ── Main ──────────────────────────────────────────────────────────────────────

def generate_pptx(image_dir: str, output_file: str):
    today = date.today().strftime("%B %d, %Y")
    images = sorted(
        [f for f in os.listdir(image_dir) if f.endswith(".png")],
        key=_file_num,
    )

    if not images:
        print(f"No PNG files found in {image_dir}")
        return

    prs = Presentation()
    prs.slide_width  = W
    prs.slide_height = H

    # Title slide
    _add_title_slide(prs, today)

    # Group images by section, inserting dividers when section changes
    content_count = len(images)
    current_section = None

    for idx, img in enumerate(images, start=1):
        section = _section_for(_file_num(img))

        if section != current_section:
            _add_section_slide(
                prs, section,
                _SECTION_DESCRIPTIONS.get(section, ""),
                today,
            )
            current_section = section

        slide = _blank_slide(prs)
        _rect(slide, 0, 0, W, H, PAPER)  # warm paper background

        _add_header_footer(
            slide,
            title=_human_title(img),
            section=section,
            page_num=idx,
            total=content_count,
            today=today,
        )
        _add_screenshot(slide, os.path.join(image_dir, img))

    prs.save(output_file)
    print(f"PowerPoint saved: {output_file}  ({content_count} screenshots, {len(prs.slides)} slides total)")


def generate_html(image_dir: str, output_file: str):
    images = sorted(
        [f for f in os.listdir(image_dir) if f.endswith(".png")],
        key=_file_num,
    )
    rows = "".join(
        f'<div class="card"><img src="{os.path.join(image_dir, img)}" alt="{img}">'
        f'<p>{_human_title(img)}</p></div>'
        for img in images
    )
    html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>Screenshot Gallery</title>
<style>
  body {{ font-family: Manrope, sans-serif; margin: 20px; background: #FAF7F0; color: #14110C; }}
  h1   {{ text-align: center; font-family: Fraunces, Georgia, serif; }}
  .gallery {{ display: flex; flex-wrap: wrap; gap: 20px; justify-content: center; }}
  .card {{ background: white; padding: 10px; border-radius: 6px;
           box-shadow: 0 2px 8px rgba(0,0,0,.08); width: 300px; }}
  .card img {{ width: 100%; height: auto; border-radius: 3px; }}
  .card p {{ margin: 8px 0 0; font-size: .85em; color: #6B655C; }}
</style></head>
<body>
<h1>§ Data Dictionary</h1>
<div class="gallery">{rows}</div>
</body></html>"""
    with open(output_file, "w") as f:
        f.write(html)
    print(f"HTML gallery saved: {output_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", default="screenshots/latest")
    parser.add_argument("--out", default="reports/walkthrough.pptx")
    parser.add_argument("--html", default="reports/gallery.html")
    args = parser.parse_args()

    os.makedirs(Path(args.out).parent, exist_ok=True)

    if not os.path.exists(args.src):
        print(f"Source directory not found: {args.src}")
    else:
        generate_html(args.src, args.html)
        generate_pptx(args.src, args.out)
