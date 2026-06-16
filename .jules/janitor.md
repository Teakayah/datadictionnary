## 2024-06-02 - Unused Parameter in `render_health`
**Learning:** I found an unused parameter in `render_health` (`_unused_fn`) which was passed `get_authorized_tables` in `app.py`. This unused parameter is confusing and we can safely remove it from `src/ui/cards/health.py` and `app.py`
**Action:** Remove `_unused_fn` from `render_health`.
## 2026-06-10 - Prop Drilling Removal in UI Components
**Learning:** Functions like `get_authorized_tables` that are needed by deep UI components (like `render_discovery` or `render_catalog_browser`) were being passed down as parameters all the way from `app.py` (prop drilling). This added unnecessary complexity to the function signatures and bloated the top-level app configuration.
**Action:** Removed prop drilling of `get_authorized_tables`. Directly import it into the specific UI components (`src/ui/cards/discovery.py`, `src/pages/catalog.py`) where it is actually used, simplifying `app.py` and making the component signatures cleaner. Tests should be updated to use `@patch` on the specific module's import space instead of passing mock functions.
## 2026-06-16 - NameError in src/i18n.py missing state
**Learning:** In `src/i18n.py`, the `format_number` and `t` functions relied on an implicitly defined `lang` variable, likely expecting it to be in global scope from somewhere else. However, when these functions were imported into places where `lang` wasn't defined, they would crash with `NameError: name 'lang' is not defined`. Streamlit applications might crash when state isn't explicitly extracted inside functions.
**Action:** Extracted `lang` directly from `st.session_state.get("locale", "en")` inside the `format_number` and `t` functions locally to prevent `NameError`.
