# App UI kit — Business Data Dictionary (Streamlit)

High-fidelity recreation of the internal Streamlit app. Not the production implementation — it's a clickable mock that shows the visual system in action.

## Flows covered
1. **Sign in** — Entra ID mock sign-in screen with supporting marketing sidebar.
2. **Catalog search** — main search field, scope checkboxes, result rows with selection state, hover states.
3. **Table detail** — right-hand panel showing columns, grants, and freshness for a selected row.

## Components
| File | Purpose |
|---|---|
| `AppShell.jsx` | Sticky header, nav, footer. |
| `SignIn.jsx` | Landing + Entra ID sign-in. |
| `SearchBar.jsx` | Primary search with ⌘K affordance. |
| `ResultsList.jsx` | Selectable table rows with match highlighting and tags. |
| `TableDetail.jsx` | Right panel — columns, grants, freshness. |
| `Icon.jsx` | Lucide-style icons inlined at 1.5px stroke. |

Open `index.html` to see them composed.
