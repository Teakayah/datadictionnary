import os
import re

# Mapping of source files to target names
MAPPING = {
    "ARCHITECTURE.md": "architecture.html",
    "docs/PRODUCT_OVERVIEW.md": "product-overview.html",
    "docs/DEPENDENCIES.md": "dependencies.html",
    "docs/business-requirements.md": "business-requirements.html",
    "docs/features/unified-search.md": "feature-unified-search.html",
    "docs/features/personalization.md": "feature-personalization.html",
    "docs/features/data-quality.md": "feature-data-quality.html",
    "docs/features/data-preview.md": "feature-data-preview.html",
    "docs/features/enhanced-lineage.md": "feature-enhanced-lineage.html",
    "docs/features/metadata-export.md": "feature-metadata-export.html",
    "docs/features/recommendation-engine.md": "feature-recommendation-engine.html",
    "docs/features/hybrid-search.md": "feature-hybrid-search.html",
    "docs/features/search-analytics.md": "feature-search-analytics.html",
    "docs/runbooks/sync-worker.md": "runbook-sync-worker.html",
    "docs/runbooks/secret-rotation.md": "runbook-secret-rotation.html",
    "docs/api/locale-keys.md": "reference-locale-keys.html",
    "docs/api/api-reference.md": "reference-api.html",
}

# ADRs
ADR_DIR = "docs/adr"
if os.path.exists(ADR_DIR):
    for f in os.listdir(ADR_DIR):
        if f.endswith(".md"):
            MAPPING[os.path.join(ADR_DIR, f)] = f"adr-{f.replace('.md', '.html')}"

SIDEBAR_HTML = """
<aside class="sidebar">
  <div class="sidebar-header">
    <a href="product-overview.html" style="text-decoration:none; color:inherit;">
      <svg viewBox="0 0 260 40" fill="none" xmlns="http://www.w3.org/2000/svg" style="height:24px">
        <g transform="translate(4,2)">
          <rect x="0.5" y="0.5" width="26" height="26" rx="1" fill="#FAF7F0" stroke="#14110C" stroke-width="1"/>
          <line x1="0.5" y1="7" x2="26.5" y2="7" stroke="#14110C" stroke-width="0.8"/>
          <circle cx="4" cy="3.5" r="1.5" fill="#B8362A"/>
        </g>
        <text x="40" y="25" font-family="Fraunces, serif" font-size="20" font-weight="400" fill="#14110C" letter-spacing="-0.3">Data Dictionary</text>
      </svg>
    </a>
  </div>
  <nav class="nav-section">
    <div class="nav-section-title">Guides</div>
    <ul class="nav-list">
      <li class="nav-item {active_user_guide}"><a href="user-guide.html">User Guide</a></li>
      <li class="nav-item {active_steward_guide}"><a href="steward-guide.html">Steward Guide</a></li>
      <li class="nav-item {active_admin_runbook}"><a href="admin-runbook.html">Admin Runbook</a></li>
    </ul>
  </nav>
  <nav class="nav-section">
    <div class="nav-section-title">Product</div>
    <ul class="nav-list">
      <li class="nav-item {active_product_overview}"><a href="product-overview.html">Product Overview</a></li>
      <li class="nav-item {active_business_requirements}"><a href="business-requirements.html">Business Requirements</a></li>
    </ul>
  </nav>
  <nav class="nav-section">
    <div class="nav-section-title">Features</div>
    <ul class="nav-list">
      <li class="nav-item {active_feature_unified_search}"><a href="feature-unified-search.html">Unified Search</a></li>
      <li class="nav-item {active_feature_personalization}"><a href="feature-personalization.html">Personalization</a></li>
      <li class="nav-item {active_feature_data_quality}"><a href="feature-data-quality.html">Data Quality</a></li>
      <li class="nav-item {active_feature_data_preview}"><a href="feature-data-preview.html">Data Preview</a></li>
      <li class="nav-item {active_feature_enhanced_lineage}"><a href="feature-enhanced-lineage.html">Enhanced Lineage</a></li>
      <li class="nav-item {active_feature_metadata_export}"><a href="feature-metadata-export.html">Metadata Export</a></li>
      <li class="nav-item {active_feature_recommendation_engine}"><a href="feature-recommendation-engine.html">Recommendation Engine</a></li>
      <li class="nav-item {active_feature_hybrid_search}"><a href="feature-hybrid-search.html">Hybrid Semantic Search</a></li>
      <li class="nav-item {active_feature_search_analytics}"><a href="feature-search-analytics.html">Search Analytics</a></li>
    </ul>
  </nav>
  <nav class="nav-section">
    <div class="nav-section-title">Architecture</div>
    <ul class="nav-list">
      <li class="nav-item {active_architecture}"><a href="architecture.html">Architecture Overview</a></li>
      <li class="nav-item {active_dependencies}"><a href="dependencies.html">Dependencies</a></li>
      <li class="nav-item {active_adr_001}"><a href="adr-001-duckdb-local-cache.html">ADR 001: DuckDB Cache</a></li>
      <li class="nav-item {active_adr_002}"><a href="adr-002-push-down-sql-auth.html">ADR 002: SQL Auth</a></li>
      <li class="nav-item {active_adr_003}"><a href="adr-003-streamlit-not-fastapi.html">ADR 003: Streamlit</a></li>
      <li class="nav-item {active_adr_004}"><a href="adr-004-sidecar-sync-worker.html">ADR 004: Sync Worker</a></li>
      <li class="nav-item {active_adr_005}"><a href="adr-005-storage-abstraction.html">ADR 005: Storage Abstraction</a></li>
      <li class="nav-item {active_adr_006}"><a href="adr-006-entra-groups-overage.html">ADR 006: Groups Overage</a></li>
      <li class="nav-item {active_adr_007}"><a href="adr-007-api-mcp-server.html">ADR 007: API &amp; MCP</a></li>
    </ul>
  </nav>
  <nav class="nav-section">
    <div class="nav-section-title">Operations</div>
    <ul class="nav-list">
      <li class="nav-item {active_runbook_sync_worker}"><a href="runbook-sync-worker.html">Sync Worker Runbook</a></li>
      <li class="nav-item {active_runbook_secret_rotation}"><a href="runbook-secret-rotation.html">Secret Rotation Runbook</a></li>
    </ul>
  </nav>
  <nav class="nav-section">
    <div class="nav-section-title">Reference</div>
    <ul class="nav-list">
      <li class="nav-item {active_reference_locale_keys}"><a href="reference-locale-keys.html">Locale Keys</a></li>
      <li class="nav-item {active_reference_api}"><a href="reference-api.html">API &amp; MCP Reference</a></li>
    </ul>
  </nav>
</aside>
"""

def get_sidebar(current_filename):
    actives = {
        "user-guide.html": "active_user_guide",
        "steward-guide.html": "active_steward_guide",
        "admin-runbook.html": "active_admin_runbook",
        "product-overview.html": "active_product_overview",
        "business-requirements.html": "active_business_requirements",
        "feature-unified-search.html": "active_feature_unified_search",
        "feature-personalization.html": "active_feature_personalization",
        "feature-data-quality.html": "active_feature_data_quality",
        "feature-data-preview.html": "active_feature_data_preview",
        "feature-enhanced-lineage.html": "active_feature_enhanced_lineage",
        "feature-metadata-export.html": "active_feature_metadata_export",
        "feature-recommendation-engine.html": "active_feature_recommendation_engine",
        "feature-hybrid-search.html": "active_feature_hybrid_search",
        "feature-search-analytics.html": "active_feature_search_analytics",
        "architecture.html": "active_architecture",
        "dependencies.html": "active_dependencies",
        "adr-001-duckdb-local-cache.html": "active_adr_001",
        "adr-002-push-down-sql-auth.html": "active_adr_002",
        "adr-003-streamlit-not-fastapi.html": "active_adr_003",
        "adr-004-sidecar-sync-worker.html": "active_adr_004",
        "adr-005-storage-abstraction.html": "active_adr_005",
        "adr-006-entra-groups-overage.html": "active_adr_006",
        "adr-007-api-mcp-server.html": "active_adr_007",
        "reference-api.html": "active_reference_api",
        "runbook-sync-worker.html": "active_runbook_sync_worker",
        "runbook-secret-rotation.html": "active_runbook_secret_rotation",
        "reference-locale-keys.html": "active_reference_locale_keys",
    }
    
    ctx = {v: "" for v in actives.values()}
    if current_filename in actives:
        ctx[actives[current_filename]] = "active"
    
    return SIDEBAR_HTML.format(**ctx)

def md_to_html(md_content, filename):
    # 1. Blockquotes/Callouts
    def callout_repl(match):
        content = match.group(1).strip()
        cls = ""
        if any(w in content.upper() for w in ["TIP", "NOTE", "OK"]):
            cls = " ok"
        elif any(w in content.upper() for w in ["WARN", "IMPORTANT"]):
            cls = " warn"
        elif any(w in content.upper() for w in ["DANGER", "ERROR"]):
            cls = " danger"
        return f'<div class="callout{cls}">{content}</div>'
    
    md_content = re.sub(r'^>\s*(.*)', callout_repl, md_content, flags=re.MULTILINE)

    # 2. Diagrams
    def mermaid_repl(match):
        mermaid_content = match.group(1).strip()
        if "graph TD" in mermaid_content and "Identity layer" in mermaid_content:
            return """
<div class="workflow-diagram">
  <div class="wf-step"><span class="wf-label">Entra ID</span><span class="wf-actor">Identity</span></div>
  <div class="wf-arrow">→</div>
  <div class="wf-step accent"><span class="wf-label">Streamlit App</span><span class="wf-actor">Compute/UI</span></div>
  <div class="wf-arrow">→</div>
  <div class="wf-step ok"><span class="wf-label">DuckDB Cache</span><span class="wf-actor">Local Store</span></div>
  <div class="wf-arrow">↔</div>
  <div class="wf-step"><span class="wf-label">Unity Catalog</span><span class="wf-actor">Source of Truth</span></div>
</div>
<details class="ascii-container">
  <summary>View System Architecture (Raw Mermaid)</summary>
<pre>""" + mermaid_content + """</pre>
</details>"""
        return f'<pre class="mermaid"><code>{mermaid_content}</code></pre>'

    md_content = re.sub(r'```mermaid\n(.*?)\n```', mermaid_repl, md_content, flags=re.DOTALL)

    def ascii_diag_repl(match):
        ascii_content = match.group(1).strip()
        if any(c in ascii_content for c in "┌┐└┘├┤┬┴┼═║╒╓╔╕╖╗╘╙╚╛╜╝╞╟╠╡╢╣╤╥╦╧╨╩╪╫╬"):
            if "Streamlit pods" in ascii_content and "Sync worker" in ascii_content:
                return """
<div class="workflow-diagram">
  <div class="wf-step"><span class="wf-label">Streamlit pods</span><span class="wf-actor">Read + Enqueue</span></div>
  <div class="wf-arrow">→</div>
  <div class="wf-step accent"><span class="wf-label">Sync worker</span><span class="wf-actor">Drain + Push</span></div>
  <div class="wf-arrow">→</div>
  <div class="wf-step ok"><span class="wf-label">Databricks</span><span class="wf-actor">Unity Catalog</span></div>
</div>
<details class="ascii-container">
  <summary>View System Flow (Raw ASCII)</summary>
<pre>""" + ascii_content + """</pre>
</details>"""
            return f'<details class="ascii-container"><summary>View Diagram (Raw ASCII)</summary><pre>{ascii_content}</pre></details>'
        return match.group(0)

    md_content = re.sub(r'```\n(.*?)\n```', ascii_diag_repl, md_content, flags=re.DOTALL)

    # 3. Code blocks (Standard)
    md_content = re.sub(r'```python\n(.*?)\n```', r'<pre><code class="language-python">\1</code></pre>', md_content, flags=re.DOTALL)
    md_content = re.sub(r'```bash\n(.*?)\n```', r'<pre><code class="language-bash">\1</code></pre>', md_content, flags=re.DOTALL)
    md_content = re.sub(r'```sql\n(.*?)\n```', r'<pre><code class="language-sql">\1</code></pre>', md_content, flags=re.DOTALL)
    md_content = re.sub(r'```json\n(.*?)\n```', r'<pre><code class="language-json">\1</code></pre>', md_content, flags=re.DOTALL)
    md_content = re.sub(r'```text\n(.*?)\n```', r'<pre><code>\1</code></pre>', md_content, flags=re.DOTALL)

    # 4. Tables
    def table_repl(match):
        table_text = match.group(0)
        rows = table_text.strip().split('\n')
        if len(rows) < 2: return table_text
        header = rows[0].strip('|').split('|')
        body_rows = rows[2:]
        html = '<table class="status-table">\n<thead>\n<tr>'
        for h in header: html += f'<th>{h.strip()}</th>'
        html += '</tr>\n</thead>\n<tbody>\n'
        for r in body_rows:
            html += '<tr>'
            cols = r.strip('|').split('|')
            for c in cols: html += f'<td>{c.strip()}</td>'
            html += '</tr>\n'
        html += '</tbody>\n</table>'
        return html

    md_content = re.sub(r'((?:\|.*\|(?:\n|$))+)', table_repl, md_content)

    # 5. Pre-process sub-headings and rules
    md_content = re.sub(r'^### (.*)', r'<h3>\1</h3>', md_content, flags=re.MULTILINE)
    md_content = re.sub(r'^---', r'<hr>', md_content, flags=re.MULTILINE)

    # 6. Parse into sections and paragraphs
    title_match = re.search(r'^# (.*)', md_content, re.MULTILINE)
    title = title_match.group(1) if title_match else "Documentation"
    md_content = re.sub(r'^# .*', '', md_content, count=1)
    
    parts = re.split(r'^## (.*)', md_content, flags=re.MULTILINE)
    
    def process_block(text):
        # 1. Convert lists (Single lines only for simplicity, prevents over-matching)
        def ol_repl(m):
            items = re.findall(r'^\d+\.\s+(.*)', m.group(0), re.MULTILINE)
            html = '<ol class="steps">\n'
            for i in items:
                html += f'  <li>{i.strip()}</li>\n'
            html += '</ol>'
            return html
            
        def ul_repl(m):
            items = re.findall(r'^[\-\*]\s+(.*)', m.group(0), re.MULTILINE)
            html = '<ul>\n'
            for i in items:
                html += f'  <li>{i.strip()}</li>\n'
            html += '</ul>'
            return html
            
        # Match ordered lists (blocks of lines starting with digits)
        text = re.sub(r'((?:^\d+\.\s+.*(?:\n|$))+)', ol_repl, text, flags=re.MULTILINE)
        # Match unordered lists (blocks of lines starting with bullets)
        text = re.sub(r'((?:^[\-\*]\s+.*(?:\n|$))+)', ul_repl, text, flags=re.MULTILINE)

        # 2. Split remaining text into paragraphs/blocks by \n\n
        blocks = text.split('\n\n')
        res = []
        for b in blocks:
            b = b.strip()
            if not b: continue
            
            if b.startswith(('<', '###', '<hr')):
                res.append(b)
            else:
                res.append(f'<p>{b}</p>')
        return '\n'.join(res)

    html_content = ""
    intro = parts[0].strip()
    if intro:
        intro_html = process_block(intro)
        # Special TOC check
        if "Table of contents" in intro:
            intro_html = intro_html.replace('<ol class="steps">', '<nav class="toc">\n  <ol>').replace('</ol>', '  </ol>\n</nav>')
        html_content = f'<section class="section">\n{intro_html}\n</section>\n'

    for i in range(1, len(parts), 2):
        h2_title = parts[i]
        h2_content = process_block(parts[i+1].strip())
        hid = re.sub(r'[^a-z0-9]+', '-', h2_title.lower()).strip('-')
        if h2_title == "Table of contents":
            h2_content = h2_content.replace('<ol class="steps">', '<nav class="toc">\n  <ol>').replace('</ol>', '  </ol>\n</nav>')
        html_content += f'<section class="section" id="{hid}">\n<h2>{h2_title}</h2>\n{h2_content}\n</section>\n'

    md_content = html_content

    # 7. Inline styles
    md_content = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', md_content)
    md_content = re.sub(r'\*(.*?)\*', r'<em>\1</em>', md_content)
    md_content = re.sub(r'`(.*?)`', r'<code>\1</code>', md_content) # Base code tag fallback

    # 8. Links
    def link_repl(match):
        text, url = match.groups()
        for src, dst in MAPPING.items():
            if url.endswith(os.path.basename(src)): return f'<a href="{dst}">{text}</a>'
        if url.endswith('.md'):
            new_url = os.path.basename(url).replace('.md', '.html')
            if 'adr/' in url: new_url = 'adr-' + new_url
            return f'<a href="{new_url}">{text}</a>'
        return f'<a href="{url}">{text}</a>'
    md_content = re.sub(r'\[(.*?)\]\((.*?)\)', link_repl, md_content)

    def backtick_link_repl(match):
        path = match.group(1)
        if path.endswith('.md'):
            for src, dst in MAPPING.items():
                if os.path.basename(path) == os.path.basename(src):
                    return f'<a href="{dst}"><code>{path}</code></a>'
            new_url = os.path.basename(path).replace('.md', '.html')
            if 'adr/' in path: new_url = 'adr-' + new_url
            return f'<a href="{new_url}"><code>{path}</code></a>'
        return f'<code>{path}</code>'
    md_content = re.sub(r'<code>(.*?)</code>', backtick_link_repl, md_content)

    return title, md_content

def wrap_html(title, content, filename, category):
    sidebar = get_sidebar(filename)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Data Dictionary — {title}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,300;0,9..144,400;0,9..144,500;1,9..144,300&family=Manrope:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="style.css">
</head>
<body>
  {sidebar}
  <main class="content-wrapper">
    <article class="page">
      <header class="site-header">
        <span class="badge">{category}</span>
      </header>
      <section class="hero">
        <div class="eyebrow">{category}</div>
        <h1>{title}</h1>
      </section>
      {content}
      <footer class="site-footer">
        <p>Data Dictionary · Documented by Data Engineering</p>
        <p>Internal Use Only</p>
      </footer>
    </article>
  </main>
</body>
</html>
"""

# Map categories
CATEGORIES = {
    "architecture.html": "Architecture",
    "product-overview.html": "Product",
    "dependencies.html": "Architecture",
    "business-requirements.html": "Product",
    "feature-unified-search.html": "Features",
    "feature-personalization.html": "Features",
    "feature-data-quality.html": "Features",
    "feature-data-preview.html": "Features",
    "feature-enhanced-lineage.html": "Features",
    "feature-metadata-export.html": "Features",
    "feature-recommendation-engine.html": "Features",
    "feature-hybrid-search.html": "Features",
    "feature-search-analytics.html": "Features",
    "runbook-sync-worker.html": "Operations",
    "runbook-secret-rotation.html": "Operations",
    "reference-locale-keys.html": "Reference",
    "reference-api.html": "Reference",
    "user-guide.html": "Guides",
    "steward-guide.html": "Guides",
    "admin-runbook.html": "Guides",
}

import hashlib

DIGEST_DIR = ".digest/docs"

def get_md5(text):
    return hashlib.md5(text.encode('utf-8')).hexdigest()

def should_process(src, dst_name):
    if not os.path.exists(src):
        return False
    
    os.makedirs(DIGEST_DIR, exist_ok=True)
    digest_path = os.path.join(DIGEST_DIR, f"{dst_name}.md5")
    
    with open(src, "r") as f:
        current_md5 = get_md5(f.read())
    
    if os.path.exists(digest_path):
        with open(digest_path, "r") as f:
            old_md5 = f.read().strip()
        if current_md5 == old_md5:
            return False
            
    with open(digest_path, "w") as f:
        f.write(current_md5)
    return True

def process_file(src, dst):
    if not should_process(src, dst):
        print(f"Skipping {src} (no changes).")
        return
        
    print(f"Converting {src} to {dst}...")
    with open(src, 'r') as f:
        content = f.read()
    
    cat = CATEGORIES.get(dst, "Architecture" if "adr-" in dst else "Documentation")
    title, body = md_to_html(content, dst)
    html = wrap_html(title, body, dst, cat)
    
    with open(os.path.join("docs", dst), 'w') as f:
        f.write(html)

def update_existing_html(filename):
    print(f"Updating existing HTML: {filename}...")
    path = os.path.join("docs", filename)
    with open(path, 'r') as f:
        content = f.read()
    
    # Extract title
    title_match = re.search(r'<title>Data Dictionary — (.*?)</title>', content)
    title = title_match.group(1) if title_match else "Documentation"
    
    # Extract main content
    body_match = re.search(r'</header>\s*(?:<section class="hero">.*?</section>\s*)?(.*?)(\s*<footer|\s*<!-- Footer)', content, re.DOTALL)
    
    if not body_match:
        body_match = re.search(r'</section>\s*(.*?)(\s*<footer|\s*<!-- Footer)', content, re.DOTALL)
    if not body_match:
        body_match = re.search(r'</nav>\s*(.*?)(\s*<footer|\s*<!-- Footer)', content, re.DOTALL)

    if not body_match:
        # Fallback 1: Try inside <article> or <main>
        body_match = re.search(r'<(?:article|main)[^>]*>(.*?)</(?:article|main)>', content, re.DOTALL)

    if body_match:
        body = body_match.group(1)
    else:
        # Fallback 2: Try <body> tag
        body_fallback = re.search(r'<body[^>]*>(.*?)</body>', content, re.DOTALL)
        if body_fallback:
            body = body_fallback.group(1)
        else:
            # Final fallback: use the whole content
            body = content

        # Clean up layout tags since we used a broader fallback
        body = re.sub(r'<aside[^>]*>.*?</aside>', '', body, flags=re.DOTALL)
        # Keep TOC, remove other navs
        body = re.sub(r'<nav(?![^>]*class=\"toc\")[^>]*>.*?</nav>', '', body, flags=re.DOTALL)
        body = re.sub(r'<header[^>]*>.*?</header>', '', body, flags=re.DOTALL)
        body = re.sub(r'<footer[^>]*>.*?</footer>', '', body, flags=re.DOTALL)
        body = re.sub(r'<section class="hero">.*?</section>', '', body, flags=re.DOTALL)
        body = re.sub(r'<!DOCTYPE.*?>', '', body, flags=re.DOTALL|re.IGNORECASE)
        body = re.sub(r'<head>.*?</head>', '', body, flags=re.DOTALL|re.IGNORECASE)
        body = re.sub(r'<html.*?>|</html>', '', body, flags=re.DOTALL|re.IGNORECASE)

    # Clean up some old tags if they exist
    body = re.sub(r'<div class="page">', '', body)
    body = re.sub(r'<hr>', '<hr>', body) # Keep hr

    cat = CATEGORIES.get(filename, "Guides")
    html = wrap_html(title, body, filename, cat)
    
    with open(path, 'w') as f:
        f.write(html)

if __name__ == "__main__":
    for src, dst in MAPPING.items():
        if os.path.exists(src):
            process_file(src, dst)
    
    # Update all existing HTML files in docs root to ensure sidebar consistency
    # Skip managed bundle files
    for f in os.listdir("docs"):
        if f.endswith(".html") and f not in ["_print.html", "data-dictionary-docs.html"]:
            update_existing_html(f)
