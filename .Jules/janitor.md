## 2024-06-02 - Unused Parameter in `render_health`
**Learning:** I found an unused parameter in `render_health` (`_unused_fn`) which was passed `get_authorized_tables` in `app.py`. This unused parameter is confusing and we can safely remove it from `src/ui/cards/health.py` and `app.py`
**Action:** Remove `_unused_fn` from `render_health`.
