import re
import os

DOCS_DIR = "/Users/nicolasleclerc/github/datadictionnary/docs"
FILES = [
    "adr-001-duckdb-local-cache.html",
    "adr-002-push-down-sql-auth.html",
    "adr-003-streamlit-not-fastapi.html",
    "adr-004-sidecar-sync-worker.html",
    "adr-005-storage-abstraction.html",
    "adr-006-entra-groups-overage.html",
    "architecture.html",
    "product-overview.html",
    "business-requirements.html",
    "user-guide.html",
    "steward-guide.html",
    "admin-runbook.html",
    "runbook-sync-worker.html",
    "runbook-secret-rotation.html",
    "reference-locale-keys.html",
    "dependencies.html"
]

# Mapping of terms to link targets
LINK_MAPPINGS = [
    (r"Architecture Overview", "architecture.html"),
    (r"Product Overview", "product-overview.html"),
    (r"Business Requirements", "business-requirements.html"),
    (r"User Guide", "user-guide.html"),
    (r"Steward Guide", "steward-guide.html"),
    (r"Admin Runbook", "admin-runbook.html"),
    (r"Sync Worker Runbook", "runbook-sync-worker.html"),
    (r"Secret Rotation Runbook", "runbook-secret-rotation.html"),
    (r"DuckDB local cache", "adr-001-duckdb-local-cache.html"),
    (r"ADR 001", "adr-001-duckdb-local-cache.html"),
    (r"push-down SQL authorization", "adr-002-push-down-sql-auth.html"),
    (r"ADR 002", "adr-002-push-down-sql-auth.html"),
    (r"Streamlit", "adr-003-streamlit-not-fastapi.html"),
    (r"ADR 003", "adr-003-streamlit-not-fastapi.html"),
    (r"Sidecar sync worker", "adr-004-sidecar-sync-worker.html"),
    (r"ADR 004", "adr-004-sidecar-sync-worker.html"),
    (r"storage abstraction", "adr-005-storage-abstraction.html"),
    (r"ADR 005", "adr-005-storage-abstraction.html"),
    (r"Entra groups overage", "adr-006-entra-groups-overage.html"),
    (r"ADR 006", "adr-006-entra-groups-overage.html"),
    (r"Locale Keys", "reference-locale-keys.html"),
    (r"Dependencies", "dependencies.html"),
]

def process_file(filename):
    filepath = os.path.join(DOCS_DIR, filename)
    if not os.path.exists(filepath):
        print(f"Skipping missing file: {filename}")
        return

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Split by sections to apply 1-2 limit per section
    # Using a simple split that captures the section tags
    parts = re.split(r'(<section[^>]*>|</section>)', content)
    
    new_parts = []
    in_section = False
    counts = {} # term -> count in current section

    for part in parts:
        if part.startswith('<section'):
            in_section = True
            counts = {} # Reset counts for new section
            new_parts.append(part)
        elif part == '</section>':
            in_section = False
            new_parts.append(part)
        elif in_section:
            # We are inside a section. Process text nodes carefully.
            # Avoid replacing inside <a>, <code>, <pre>, <h1-6>, etc.
            # We'll split by tags again.
            sub_parts = re.split(r'(<[^>]+>)', part)
            processed_sub_parts = []
            skip_tag_stack = []
            
            for sub_part in sub_parts:
                if sub_part.startswith('<'):
                    tag_name_match = re.match(r'<(/?[a-zA-Z0-9]+)', sub_part)
                    if tag_name_match:
                        tag_name = tag_name_match.group(1).lower()
                        if tag_name in ['a', 'code', 'pre', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                            skip_tag_stack.append(tag_name)
                        elif tag_name.startswith('/') and tag_name[1:] in ['a', 'code', 'pre', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                            if skip_tag_stack and skip_tag_stack[-1] == tag_name[1:]:
                                skip_tag_stack.pop()
                    processed_sub_parts.append(sub_part)
                else:
                    if not skip_tag_stack:
                        # This is a text node and not inside a forbidden tag
                        for pattern, target in LINK_MAPPINGS:
                            if target == filename:
                                continue # Don't link to self
                            
                            # Skip if we already reached limit for this term in this section
                            if counts.get(pattern, 0) >= 2:
                                continue
                            
                            def replace_func(match):
                                term = match.group(0)
                                if counts.get(pattern, 0) < 2:
                                    counts[pattern] = counts.get(pattern, 0) + 1
                                    return f'<a href="{target}">{term}</a>'
                                return term

                            regex = r'\b' + re.escape(pattern) + r'\b'
                            # Case insensitive match
                            sub_part = re.sub(regex, replace_func, sub_part, flags=re.IGNORECASE)
                        processed_sub_parts.append(sub_part)
                    else:
                        processed_sub_parts.append(sub_part)
            new_parts.append("".join(processed_sub_parts))
        else:
            # Outside of section (e.g. header, footer, or sidebar)
            # The instructions say "1-2 occurrences per section". 
            # Non-section areas can also be treated as a "section" for this rule.
            # But the sidebar already has links. Let's only process the main content if possible.
            # Usually main content is in <main> or <article>.
            # For simplicity, I'll treat non-section parts as one section too, 
            # but maybe I should skip them if they are in <aside> or <nav>.
            
            sub_parts = re.split(r'(<aside[^>]*>.*?</aside>|<nav[^>]*>.*?</nav>|<[^>]+>)', part, flags=re.DOTALL)
            processed_sub_parts = []
            for sub_part in sub_parts:
                if sub_part.startswith('<aside') or sub_part.startswith('<nav'):
                    processed_sub_parts.append(sub_part) # Skip sidebar/nav
                elif sub_part.startswith('<'):
                    processed_sub_parts.append(sub_part)
                else:
                    # Apply linking to text outside of sections/aside/nav (like intro/outro)
                    # Use a local counts dict for this part
                    local_counts = {}
                    for pattern, target in LINK_MAPPINGS:
                        if target == filename:
                            continue
                        def replace_func(match):
                            term = match.group(0)
                            if local_counts.get(pattern, 0) < 2:
                                local_counts[pattern] = local_counts.get(pattern, 0) + 1
                                return f'<a href="{target}">{term}</a>'
                            return term
                        regex = r'\b' + re.escape(pattern) + r'\b'
                        sub_part = re.sub(regex, replace_func, sub_part, flags=re.IGNORECASE)
                    processed_sub_parts.append(sub_part)
            new_parts.append("".join(processed_sub_parts))

    final_content = "".join(new_parts)
    if final_content != content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(final_content)
        print(f"Updated {filename}")
    else:
        print(f"No changes for {filename}")

if __name__ == "__main__":
    for f in FILES:
        process_file(f)
