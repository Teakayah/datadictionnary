#!/usr/bin/env python3
"""Documentation bundler script.

Compiles individual markdown documentation pages into HTML,
bundles them into a single-file offline SPA (data-dictionary-docs.html)
and a linear print-friendly document (_print.html), and then renders
the high-fidelity A4 PDF (data-dictionary-docs.pdf) using Playwright.
"""

import os
import re
import subprocess
import sys

# Categorized list of documentation pages in sidebar order
PAGES = [
    # Guides
    {"id": "user-guide", "file": "user-guide.html", "title": "User Guide", "category": "Guides"},
    {"id": "steward-guide", "file": "steward-guide.html", "title": "Data Steward Guide", "category": "Guides"},
    {"id": "admin-runbook", "file": "admin-runbook.html", "title": "Admin Runbook", "category": "Guides"},
    # Product
    {"id": "product-overview", "file": "product-overview.html", "title": "Product Overview", "category": "Product"},
    {"id": "business-requirements", "file": "business-requirements.html", "title": "Business Requirements", "category": "Product"},
    # Features
    {"id": "feature-unified-search", "file": "feature-unified-search.html", "title": "Feature: Unified Search", "category": "Features"},
    {"id": "feature-personalization", "file": "feature-personalization.html", "title": "Feature: Personalization", "category": "Features"},
    {"id": "feature-data-quality", "file": "feature-data-quality.html", "title": "Feature: Data Quality", "category": "Features"},
    {"id": "feature-data-preview", "file": "feature-data-preview.html", "title": "Feature: Data Preview", "category": "Features"},
    {"id": "feature-enhanced-lineage", "file": "feature-enhanced-lineage.html", "title": "Feature: Enhanced Lineage", "category": "Features"},
    {"id": "feature-metadata-export", "file": "feature-metadata-export.html", "title": "Feature: Metadata Export", "category": "Features"},
    {"id": "feature-recommendation-engine", "file": "feature-recommendation-engine.html", "title": "Feature: Recommendation Engine", "category": "Features"},
    {"id": "feature-hybrid-search", "file": "feature-hybrid-search.html", "title": "Feature: Hybrid Semantic Search", "category": "Features"},
    {"id": "feature-search-analytics", "file": "feature-search-analytics.html", "title": "Feature: Search Analytics", "category": "Features"},
    # Architecture
    {"id": "architecture", "file": "architecture.html", "title": "Architecture Overview", "category": "Architecture"},
    {"id": "dependencies", "file": "dependencies.html", "title": "Dependencies", "category": "Architecture"},
    {"id": "adr-001-duckdb-local-cache", "file": "adr-001-duckdb-local-cache.html", "title": "ADR 001: DuckDB Local Cache", "category": "Architecture"},
    {"id": "adr-002-push-down-sql-auth", "file": "adr-002-push-down-sql-auth.html", "title": "ADR 002: SQL Auth", "category": "Architecture"},
    {"id": "adr-003-streamlit-not-fastapi", "file": "adr-003-streamlit-not-fastapi.html", "title": "ADR 003: Streamlit Choice", "category": "Architecture"},
    {"id": "adr-004-sidecar-sync-worker", "file": "adr-004-sidecar-sync-worker.html", "title": "ADR 004: Sidecar Sync Worker", "category": "Architecture"},
    {"id": "adr-005-storage-abstraction", "file": "adr-005-storage-abstraction.html", "title": "ADR 005: Storage Abstraction", "category": "Architecture"},
    {"id": "adr-006-entra-groups-overage", "file": "adr-006-entra-groups-overage.html", "title": "ADR 006: Entra Groups Overage", "category": "Architecture"},
    # Operations
    {"id": "runbook-sync-worker", "file": "runbook-sync-worker.html", "title": "Operations: Sync Worker", "category": "Operations"},
    {"id": "runbook-secret-rotation", "file": "runbook-secret-rotation.html", "title": "Operations: Secret Rotation", "category": "Operations"},
    # Reference
    {"id": "reference-locale-keys", "file": "reference-locale-keys.html", "title": "Reference: Locale Keys", "category": "Reference"},
]

PRINT_SPECIFIC_CSS = """
    /* Cover page */
    .cover {
      display: flex;
      flex-direction: column;
      justify-content: center;
      min-height: 80vh;
      padding: 80px 48px;
      page-break-after: always;
      border-bottom: 2px solid var(--ink);
    }
    .cover h1 {
      font-family: var(--font-display);
      font-size: 64px;
      font-weight: 300;
      letter-spacing: -0.02em;
      line-height: 1.05;
      margin-bottom: 24px;
    }
    .cover h1 em { font-style: italic; color: var(--ink-60); }
    .cover .cover-sub {
      font-size: 18px;
      color: var(--ink-60);
      margin-bottom: 48px;
    }
    .cover .cover-meta {
      font-family: var(--font-mono);
      font-size: 12px;
      color: var(--ink-40);
    }

    /* TOC */
    .toc-page {
      padding: 48px;
      page-break-after: always;
    }
    .toc-page h2 {
      font-family: var(--font-display);
      font-size: 32px;
      font-weight: 400;
      margin-bottom: 24px;
    }
    .toc-page ol { padding-left: 20px; line-height: 2; font-size: 14px; }
    .toc-page a { color: var(--ink); text-decoration: none; }

    /* Each doc page */
    .print-page {
      page-break-before: always;
    }
    .print-page article { padding: 48px; }
    .print-page .hero { padding: 32px 0 40px; }

    /* Mermaid */
    .mermaid-wrap {
      background: var(--paper-deep); border: 1px solid var(--ink-10);
      border-radius: 2px; padding: 24px; margin: 20px 0; overflow: visible;
    }
    .mermaid svg { max-width: 100%; }

    /* Hide interactive elements that don't print well */
    details summary { font-weight: 600; cursor: default; }
    details[open] { border: 1px solid var(--ink-10); padding: 12px; margin: 12px 0; }

    @media print {
      .print-page { page-break-before: always; }
      .cover { page-break-after: always; min-height: 0; }
      .toc-page { page-break-after: always; }
      pre, table { page-break-inside: avoid; }
      h2, h3 { page-break-after: avoid; }
    }
"""


def extract_article_content(file_path):
    """Extract inner HTML content of <article class="page">...</article>."""
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    start_tag = '<article class="page">'
    end_tag = '</article>'

    start_idx = content.find(start_tag)
    if start_idx == -1:
        # Fallback to <article> if class is different
        start_tag = '<article>'
        start_idx = content.find(start_tag)

    if start_idx == -1:
        raise ValueError(f"Could not find <article> tag in {file_path}")

    end_idx = content.rfind(end_tag)
    if end_idx == -1:
        raise ValueError(f"Could not find </article> tag in {file_path}")

    article_body = content[start_idx + len(start_tag):end_idx].strip()
    return article_body


def convert_to_spa_links(html):
    """Replace relative file links (e.g. user-guide.html) with SPA data-page attributes."""
    def repl(match):
        filename = match.group(1)
        page_id = filename.replace(".html", "")
        return f'href="#" data-page="{page_id}"'

    return re.sub(r'href="([a-zA-Z0-9_\-\.]+)\.html"', repl, html)


def convert_to_print_links(html):
    """Replace relative file links (e.g. user-guide.html) with internal anchor links (#user-guide)."""
    def repl(match):
        filename = match.group(1)
        page_id = filename.replace(".html", "")
        return f'href="#{page_id}"'

    return re.sub(r'href="([a-zA-Z0-9_\-\.]+)\.html"', repl, html)


def get_spa_sidebar():
    """Extract and convert the sidebar from user-guide.html for SPA use."""
    with open("docs/user-guide.html", "r", encoding="utf-8") as f:
        content = f.read()

    start_tag = '<aside class="sidebar">'
    end_tag = '</aside>'

    start_idx = content.find(start_tag)
    if start_idx == -1:
        raise ValueError("Could not find <aside class=\"sidebar\"> in docs/user-guide.html")
    end_idx = content.find(end_tag)
    if end_idx == -1:
        raise ValueError("Could not find </aside> in docs/user-guide.html")

    sidebar_content = content[start_idx:end_idx + len(end_tag)]

    # Clean active classes (handled dynamically in JS)
    sidebar_content = re.sub(r'class="nav-item active"', 'class="nav-item"', sidebar_content)
    sidebar_content = re.sub(r'class="nav-item\s+active"', 'class="nav-item"', sidebar_content)

    def repl(match):
        filename = match.group(1)
        page_id = filename.replace(".html", "")
        return f'href="#" data-page="{page_id}"'

    sidebar_content = re.sub(r'href="([a-zA-Z0-9_\-\.]+)\.html"', repl, sidebar_content)
    return sidebar_content


def main():
    # 1. Compile all markdown documents to HTML first
    print("Compiling individual documentation pages...")
    subprocess.run([sys.executable, "scripts/md_to_html.py"], check=True)

    # 2. Extract offline resources from the pre-existing docs/_print.html
    print("Extracting offline base64 fonts and mermaid.js...")
    with open("docs/_print.html", "r", encoding="utf-8") as f:
        print_html_content = f.read()

    # Get style tag inner contents
    style_match = re.search(r"<style>(.*?)</style>", print_html_content, re.DOTALL)
    if not style_match:
        raise ValueError("Could not find <style> tag in docs/_print.html")
    style_content = style_match.group(1)

    # Slice style content to get fonts
    last_font_idx = style_content.rfind("@font-face")
    if last_font_idx == -1:
        raise ValueError("Could not find any @font-face in docs/_print.html")
    closing_brace_idx = style_content.find("}", last_font_idx)
    if closing_brace_idx == -1:
        raise ValueError("Could not find closing brace of last @font-face")
    fonts_block = style_content[:closing_brace_idx + 1]

    # Get style.css content
    with open("docs/style.css", "r", encoding="utf-8") as f:
        style_css_content = f.read()

    # Get offline mermaid library (first script tag contents)
    script_matches = re.findall(r"<script>(.*?)</script>", print_html_content, re.DOTALL)
    if not script_matches or len(script_matches) < 2:
        raise ValueError("Could not find inlined mermaid.js library in docs/_print.html")
    mermaid_js_lib = script_matches[0]

    # 3. Assemble the SPA Bundle (docs/data-dictionary-docs.html)
    print("Assembling offline SPA Bundle (data-dictionary-docs.html)...")
    spa_sidebar = get_spa_sidebar()

    spa_style = f"""<style>
{fonts_block}
{style_css_content}

/* ── SPA layer ── */
.doc-page {{ display: none; }}
.doc-page.is-active {{ display: block; }}
.mermaid-wrap {{
  background: var(--paper-deep); border: 1px solid var(--ink-10);
  border-radius: 2px; padding: 24px; margin: 20px 0; overflow-x: auto;
}}
.mermaid-wrap .mermaid {{ min-width: 520px; }}
.mermaid svg {{ max-width: 100%; }}
</style>"""

    spa_pages_html = []
    for p in PAGES:
        file_path = os.path.join("docs", p["file"])
        if not os.path.exists(file_path):
            print(f"Warning: {file_path} not found. Skipping.")
            continue

        article_body = extract_article_content(file_path)
        article_body = convert_to_spa_links(article_body)

        page_html = f"""<div class="doc-page" id="page-{p['id']}" aria-hidden="true">
<article class="page">
{article_body}
</article>
</div>"""
        spa_pages_html.append(page_html)

    spa_body = "\n".join(spa_pages_html)

    spa_router_script = """<script>
(function () {
  var DEFAULT = 'user-guide';

  function showPage(id) {
    var target = document.getElementById('page-' + id);
    if (!target) return;
    // hide all
    document.querySelectorAll('.doc-page').forEach(function (p) {
      p.classList.remove('is-active');
      p.setAttribute('aria-hidden', 'true');
    });
    // show target
    target.classList.add('is-active');
    target.setAttribute('aria-hidden', 'false');
    // update nav active state
    document.querySelectorAll('.nav-item').forEach(function (n) {
      n.classList.remove('active');
    });
    document.querySelectorAll('.nav-item a[data-page="' + id + '"]').forEach(function (a) {
      var navItem = a.closest('.nav-item');
      if (navItem) navItem.classList.add('active');
    });
    // scroll content to top
    var contentEl = document.getElementById('dd-content');
    if (contentEl) contentEl.scrollTop = 0;
    // update hash without triggering hashchange
    history.replaceState(null, '', '#' + id);
    // re-run mermaid on newly visible diagrams (idempotent — already-rendered svgs are skipped)
    if (window.mermaid) {
      try { mermaid.run({ nodes: target.querySelectorAll('.mermaid') }); } catch(e) {}
    }
  }

  // Wire all data-page links (sidebar + cross-page content links)
  document.addEventListener('click', function (e) {
    var a = e.target.closest('a[data-page]');
    if (!a) return;
    e.preventDefault();
    showPage(a.getAttribute('data-page'));
  });

  // Route on load
  var hash = window.location.hash.replace('#', '');
  showPage((hash && document.getElementById('page-' + hash)) ? hash : DEFAULT);
})();
</script>"""

    spa_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Data Dictionary — Documentation</title>
  {spa_style}
</head>
<body>
  {spa_sidebar}
  <main class="content-wrapper" id="dd-content">
    {spa_body}
  </main>
  <script>{mermaid_js_lib}</script>
  <script>
    mermaid.initialize({{
      startOnLoad: true,
      theme: 'base',
      themeVariables: {{
        primaryColor: '#F2EDE1', primaryTextColor: '#14110C', primaryBorderColor: '#C9C2B4',
        lineColor: '#6B645A', secondaryColor: '#E3E9DE', tertiaryColor: '#DDE4EC',
        background: '#FAF7F0', mainBkg: '#F2EDE1', nodeBorder: '#C9C2B4',
        clusterBkg: '#FAF7F0', clusterBorder: '#C9C2B4', titleColor: '#14110C',
        edgeLabelBackground: '#FAF7F0',
        fontFamily: 'Manrope, "Segoe UI", system-ui, sans-serif', fontSize: '13px'
      }}
    }});
  </script>
  {spa_router_script}
</body>
</html>
"""

    with open("docs/data-dictionary-docs.html", "w", encoding="utf-8") as f:
        f.write(spa_html)
    print("✓ SPA Bundle created successfully.")

    # 4. Assemble the Print Document (docs/_print.html)
    print("Assembling linear Print Bundle (_print.html)...")
    print_style = f"""<style>
{fonts_block}
{style_css_content}
{PRINT_SPECIFIC_CSS}
</style>"""

    toc_items = []
    print_pages_html = []
    for p in PAGES:
        file_path = os.path.join("docs", p["file"])
        if not os.path.exists(file_path):
            continue

        toc_items.append(f'<li><a href="#{p["id"]}">{p["title"]}</a></li>')

        article_body = extract_article_content(file_path)
        article_body = convert_to_print_links(article_body)

        page_html = f"""<div class="print-page" id="{p['id']}">
<article class="page">
{article_body}
</article>
</div>"""
        print_pages_html.append(page_html)

    print_body = "\n".join(print_pages_html)
    toc_body = "\n".join(toc_items)

    print_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Data Dictionary — Documentation Reference</title>
  {print_style}
</head>
<body>
  <div class="content-wrapper">
    <!-- Cover Page -->
    <div class="cover">
      <svg viewBox="0 0 260 40" fill="none" xmlns="http://www.w3.org/2000/svg" style="height:40px;margin-bottom:40px">
        <g transform="translate(4,2)">
          <rect x="0.5" y="0.5" width="26" height="26" rx="1" fill="#FAF7F0" stroke="#14110C" stroke-width="1"/>
          <line x1="0.5" y1="7" x2="26.5" y2="7" stroke="#14110C" stroke-width="0.8"/>
          <circle cx="4" cy="3.5" r="1.5" fill="#B8362A"/>
          <line x1="3" y1="13" x2="23" y2="13" stroke="#C9C2B4" stroke-width="0.8"/>
          <line x1="3" y1="17" x2="23" y2="17" stroke="#C9C2B4" stroke-width="0.8"/>
          <line x1="3" y1="21" x2="17" y2="21" stroke="#C9C2B4" stroke-width="0.8"/>
        </g>
        <text x="40" y="25" font-family="Fraunces, serif" font-size="20" font-weight="400" fill="#14110C" letter-spacing="-0.3">Data Dictionary</text>
        <text x="194" y="25" font-family="Fraunces, serif" font-size="20" fill="#B8362A">§</text>
      </svg>
      <h1>Documentation<br><em>reference.</em></h1>
      <p class="cover-sub">User guides · Architecture · ADRs · Runbooks · Locale keys</p>
      <p class="cover-meta">Business Data Dictionary for Databricks Unity Catalog<br>Internal use only</p>
    </div>

    <!-- Table of Contents -->
    <div class="toc-page">
      <h2>Contents</h2>
      <ol>
        {toc_body}
      </ol>
    </div>

    <!-- Page Contents -->
    {print_body}
  </div>

  <script>{mermaid_js_lib}</script>
  <script>
    mermaid.initialize({{
      startOnLoad: true,
      theme: 'base',
      themeVariables: {{
        primaryColor: '#F2EDE1', primaryTextColor: '#14110C', primaryBorderColor: '#C9C2B4',
        lineColor: '#6B645A', secondaryColor: '#E3E9DE', tertiaryColor: '#DDE4EC',
        background: '#FAF7F0', mainBkg: '#F2EDE1', nodeBorder: '#C9C2B4',
        clusterBkg: '#FAF7F0', clusterBorder: '#C9C2B4', titleColor: '#14110C',
        edgeLabelBackground: '#FAF7F0',
        fontFamily: 'Manrope, "Segoe UI", system-ui, sans-serif', fontSize: '13px'
      }}
    }});
  </script>
</body>
</html>
"""

    with open("docs/_print.html", "w", encoding="utf-8") as f:
        f.write(print_html)
    print("✓ Print Bundle created successfully.")

    # 5. Render to PDF via Playwright
    try:
        print("Rendering A4 PDF via Playwright...")
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            abs_path = os.path.abspath("docs/_print.html")
            file_url = f"file://{abs_path}"

            page.goto(file_url)

            # Wait for networks to clear and Mermaid to compile SVGs
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(3000)

            pdf_path = "docs/data-dictionary-docs.pdf"
            page.pdf(
                path=pdf_path,
                format="A4",
                print_background=True,
                margin={
                    "top": "20mm",
                    "bottom": "20mm",
                    "left": "20mm",
                    "right": "20mm"
                }
            )
            browser.close()
        print(f"✓ PDF successfully generated at: {pdf_path}")
    except Exception as e:
        print(f"⚠️ Playwright PDF generation failed: {e}", file=sys.stderr)
        print("Please ensure that browser dependencies are installed ('playwright install').", file=sys.stderr)


if __name__ == "__main__":
    main()
