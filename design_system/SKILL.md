---
name: data-dictionary-design
description: Use this skill to generate well-branded interfaces and assets for Data Dictionary (a Business Data Dictionary for Databricks Unity Catalog), either for production or throwaway prototypes/mocks/etc. Contains essential design guidelines, colors, type, fonts, assets, and UI kit components for prototyping.
user-invocable: true
---

Read the README.md file within this skill, and explore the other available files.

Key starting points:
- `README.md` — brand positioning, content fundamentals, visual foundations, iconography
- `colors_and_type.css` — all design tokens (CSS variables); include this on every page
- `assets/` — logos and the card-catalog mark
- `ui_kits/app/` — internal Streamlit app (search + detail)
- `ui_kits/marketing/` — modern corporate site
- `preview/` — small specimen cards for the design system tab

If creating visual artifacts (slides, mocks, throwaway prototypes, etc), copy assets out and create static HTML files for the user to view. If working on production code, you can copy assets and read the rules here to become an expert in designing with this brand.

Visual shorthand: warm paper (`#FAF7F0`), near-black ink (`#14110C`), ONE accent of oxidized red (`#B8362A`). Fraunces serif display + Manrope body + JetBrains Mono for identifiers. Hairlines over boxes, 0–2px radii, almost no motion, no emoji. The metaphor is a card catalog.

If the user invokes this skill without any other guidance, ask them what they want to build or design, ask some questions, and act as an expert designer who outputs HTML artifacts _or_ production code, depending on the need.
