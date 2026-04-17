# Data Dictionary — Design System

A refined, editorial design system for **Business Data Dictionary**, an enterprise-grade frontend for navigating Databricks Unity Catalog metadata. The brand blends the rigor of a scientific reference with the restraint of modern editorial design: a data product that reads like a well-made book.

---

## Product Context

**Business Data Dictionary** is an internal tool that bridges the gap between data engineering and business users. It provides a searchable, digestible, and permission-aware view of an organization's data assets stored in Databricks Unity Catalog.

**Core components**
- **Frontend:** Streamlit web app (`app.py`) — search interface + Entra ID sign-in
- **Metadata cache:** A dedicated Unity Catalog schema populated by a nightly sync job
- **Sync job:** `scripts/sync_metadata.py` extracts catalogs, schemas, tables, and permission grants via the Databricks SDK

**Users**
- *Business users* — analysts, PMs, ops teams. Non-technical. Need to find data by plain-English terms.
- *Data stewards* — own tables and descriptions. Read-heavy with occasional edits.
- *Data engineers* — verify sync health, troubleshoot missing assets.

**Surfaces we design for**
1. **Application** — the Streamlit app itself (search, results, table detail, auth).
2. **Corporate / marketing site** — public-facing page introducing the product to prospective enterprise users. The original brief was *"Corporate website to could use a touch of modern."*

---

## Sources

- **Local codebase:** `datadictionnary/` — Streamlit app + sync scripts (read via `local_ls` / `local_read`).
- **GitHub mirror:** `Teakayah/datadictionnary` (default branch `main`) — same code, same structure.
- **No existing Figma, brand book, or visual assets.** The system below is designed from scratch to match the tool's purpose (a catalog) and the company's request (modern, corporate).

> Because no visual reference was provided, every visual decision below is a deliberate original choice. Treat this as v1 — the user should confirm direction before production adoption.

---

## Brand Positioning

**Name:** Data Dictionary (codename *datadictionnary*)
**One-liner:** *A card catalog for your warehouse.*
**Tagline candidates:** *Know what you have.* · *Metadata, made legible.* · *The reference desk for your data.*

**Personality**
- Editorial, precise, quietly confident
- Library-science calm, not Silicon Valley loud
- Respects the reader's intelligence
- Corporate but never sterile — warm paper, ink, a single accent of oxidized red

**Metaphor anchor: the card catalog.** The drawer, the index tab, the typed slip, the Dewey number. Every UI decision gets tested against: *does this feel like a well-kept reference library?*

---

## Content Fundamentals

**Voice: editorial-technical.** Write like a reference librarian — factual, declarative, respectful of the reader's time. Never breathless, never self-congratulating.

- **Person.** Address the reader as *you*. Refer to the product by name (*Data Dictionary*) or *the catalog*. Avoid first-person plural (*we*) except in narrative contexts like changelogs.
- **Casing.** **Sentence case** for every headline, button, menu label, and tab. Never title case. Full uppercase reserved for short eyebrow labels (e.g. `CATALOG · SALES`) and single-letter indices.
- **Tone.** Calm, specific, short. Use the active voice. Prefer verbs over gerunds: *Search the catalog* not *Searching the catalog*.
- **Punctuation.** Oxford comma. Em dashes with spaces around them — like this. No exclamation marks in product UI. Periods at the end of descriptions and empty states; no periods on buttons or labels.
- **Numbers.** Spell out one through nine; use digits for 10+. Always use digits for counts, IDs, and dates (`2,341 tables`, `Updated Apr 14`).
- **Emoji & decoration.** None in product UI. The metaphor is a printed reference work, not a chat app.
- **Technical terms.** Use Unity Catalog vocabulary accurately: *catalog*, *schema*, *table*, *grant*. Don't soften to *folders* or *databases*.

**Examples**

| Do | Don't |
|---|---|
| Search the catalog | 🔍 Let's find your data! |
| 2,341 tables across 18 schemas | Tons of tables ready to explore |
| No matches for "customer_ltv" | Oops — we couldn't find anything 😕 |
| Updated nightly from Unity Catalog | Freshly synced with Databricks |
| Sign in with Entra ID | Log in to continue |
| Empty — this schema has no tables yet. | Nothing here yet! |

**Microcopy patterns**
- Buttons: verb-first, two words max. *Search*, *Sign in*, *View table*, *Request access*.
- Placeholders: a real query. *e.g. customer_lifetime_value*
- Empty states: state the fact, then offer one action. *No grants match this filter. Clear filters.*

---

## Visual Foundations

### The system in one sentence
Warm off-white paper, near-black ink, a single confident accent of **oxidized red** (`#B8362A`), a serif display face paired with a geometric sans and a monospace for identifiers, generous margins, hairline rules instead of boxes, and almost no motion.

### Color
Split into three explicit groups:

- **Paper & ink** — a warm neutral scale, not pure white/black. `#FAF7F0` (paper) through `#14110C` (ink).
- **Accent** — a single oxidized red, `#B8362A`. Used for one thing per screen: the selected row, the primary button, the index letter. Never decorative.
- **Semantic** — forest green, ochre, deep blue for success / warning / info. Desaturated so they read as ink-on-paper, not iOS alerts.

Imagery vibe: high-contrast monochrome photography, archival scans, taxonomic illustrations. Never stock-photo warmth or glossy gradients.

### Typography
- **Display serif:** *Fraunces* — a characterful literary serif with optical sizing. Used at 48px+ for hero headlines and section titles. Weight 400, slight negative tracking at display sizes.
- **Body sans:** *GT Walsheim* (sub: *Manrope* on Google Fonts) — a geometric humanist sans. 16px body, 14px UI, 12px metadata labels.
- **Monospace:** *JetBrains Mono* — every table name, column name, SQL identifier, and numeric count. This is how the catalog signals "this is a real thing in the warehouse."

> **Font substitution note.** *Fraunces* is on Google Fonts (licensed). *GT Walsheim* is commercial — we ship **Manrope** as the nearest Google Fonts substitute. If you have GT Walsheim licenses, drop the `.woff2` files into `fonts/` and update `colors_and_type.css`.

Type scale: 12 · 13 · 14 · 16 · 18 · 24 · 32 · 48 · 72 · 104. Line-height 1.5 for body, 1.1 for display.

### Spacing & layout
- 8pt base grid. Tokens: 4, 8, 12, 16, 24, 32, 48, 64, 96, 128.
- Column grid: **12 columns**, 32px gutter, max content width **1200px**, page margin 48px on desktop.
- Asymmetric layouts are encouraged. Large left-justified headlines with narrow right-hand metadata gutter. Full-bleed hairlines above section starts.
- Section headers sit on their own line, separated from content by a 1px ink rule and 48px of air.

### Backgrounds & atmosphere
- Default surface is **paper** (`#FAF7F0`). Subtle paper-grain noise at 2% opacity — optional, can be toggled off.
- No gradients, ever, except a near-invisible vignette (3% ink at the corners of full-bleed hero sections).
- **No full-bleed hero photography** in the app. The marketing site may use one archival-feeling photograph per page.
- Repeating patterns are limited to one: a hairline dot grid used behind taxonomies and empty states.

### Motion
- Philosophy: *almost none.* The brand is calm reading material.
- Transitions: 120ms for hover, 180ms for state changes, 240ms for page enters. Easing `cubic-bezier(0.2, 0, 0, 1)` (a gentle out-expo).
- No bounce. No spring. No parallax.
- Exceptions: the index-letter selector on the marketing page may tick through letters with a deliberate typewriter rhythm (60ms per letter).

### Hover, focus, press
- **Hover:** ink deepens 6% OR paper lightens 4%. Never scale, never shadow change.
- **Focus:** 2px oxidized-red outline offset 3px. No outline hide.
- **Press:** 1px translate-Y, ink deepens to full.
- **Disabled:** 40% opacity, no pointer.

### Borders, rules, shadows
- **Rules over boxes.** 1px hairlines in `--ink-20` divide sections. Cards have a single top rule, not a full border.
- **Corner radius:** 2px for inputs and buttons. 0px for cards and tables. The only rounded element is the single pill-shaped "beta" badge on the marketing site.
- **Shadows:** one shadow token only — `0 1px 0 0 var(--ink-10)` (a hairline bottom). No drop shadows, no glows, no elevation tiers.
- **Transparency / blur:** used exactly once — the sticky header uses `backdrop-filter: blur(8px)` over a 92% paper background.

### Imagery
- Archival-feeling, monochrome or duotone.
- Warm (paper-tinted), never cool.
- Scientific plates, technical diagrams, typographic specimens are all on-brand.
- We do not ship any generic stock photos.

### Iconography
See **ICONOGRAPHY** below.

---

## Iconography

- **Primary icon set:** **Lucide** via CDN. Lucide's 1.5px-stroke, rounded-linecap geometry pairs cleanly with the humanist sans and feels like plate illustrations rather than app chrome.
- **Stroke width:** locked at **1.5px**. Do not mix weights.
- **Default icon color:** current ink (`--ink-80`). Accent red only when the icon represents the active / selected state.
- **Sizes:** 14px (inline), 16px (UI), 20px (buttons), 24px (section headers). No icons larger than 24px in product UI.
- **Pairing:** when an icon sits next to text, the icon's optical size should match the text's x-height, not its cap height.

**Substitution flag.** The codebase ships no icons of its own (Streamlit uses emoji characters like `📖` and `🔍`). We've replaced those emoji with Lucide equivalents (`book-open`, `search`). If the team prefers to keep Streamlit emoji for the MVP, that's documented as a deliberate exception.

**Emoji.** Not used in product or marketing UI. The `📖` and `🔍` that appear in the Streamlit source will be removed at the first visual pass.

**Unicode as icons.** Permitted for a small set of typographic marks only: `§` (section), `¶` (paragraph), `†` (footnote), `·` (bullet). These appear as decorative index marks in the marketing page.

Assets live in `assets/`. See `assets/README.md` for the catalog.

---

## Index

Root files:
- `README.md` — this document
- `SKILL.md` — Agent Skill manifest (use this from Claude Code)
- `colors_and_type.css` — CSS variables for the full token system
- `fonts/` — webfonts (Fraunces, Manrope, JetBrains Mono via Google Fonts; drop GT Walsheim `.woff2` here)
- `assets/` — logos, marks, and illustrative imagery
- `preview/` — small HTML cards that populate the Design System tab
- `ui_kits/` — full-product recreations
  - `ui_kits/app/` — the Streamlit data dictionary interface
  - `ui_kits/marketing/` — the modern corporate website

Open `ui_kits/app/index.html` and `ui_kits/marketing/index.html` to see the system in use.
