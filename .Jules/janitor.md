## 2024-06-02 - Unused Parameter in `render_health`
**Learning:** I found an unused parameter in `render_health` (`_unused_fn`) which was passed `get_authorized_tables` in `app.py`. This unused parameter is confusing and we can safely remove it from `src/ui/cards/health.py` and `app.py`
**Action:** Remove `_unused_fn` from `render_health`.
## 2026-06-03 - Vulture False Positives in APIs and UI
**Learning:** When performing tech debt cleanup using static analysis tools like `vulture`, they will frequently produce false positives for FastAPI route endpoints, Pydantic model fields, standard library methods like `do_GET`, and Streamlit UI pages that are imported dynamically or used as entry points.
**Action:** Never blindly remove components flagged by static analysis without globally searching for their usage, especially in web and UI frameworks.
