# Known test failures

22 tests currently fail (all pre-existing before the friendly-names feature branch). This document explains the root cause and the minimal fix needed for each group.

Run the suite to verify nothing new has been introduced:

```bash
python -m pytest tests/ -q \
  --ignore=tests/test_load_smoke.py \
  --ignore=tests/test_wcag_axe.py \
  --ignore=tests/test_nav_render.py
```

---

## Group 1 — Admin page: stats and log tests (4 failures)

**Files:** `tests/test_admin.py`

**Tests:**
- `TestAdminPage::test_stats_cards_present`
- `TestAdminPage::test_log_expand_buttons_present`
- `TestAuditLog::test_business_name_change_log_shows_correct_rows`
- `TestAuditLog::test_comment_log_rows`

**Symptom:** `assert "Total tables" in {}` / `assert 'admin_biz_log_expand' in [...]`

**Root cause:** The admin page was refactored from a single-page layout to a three-tab segmented_control:

| Tab index | Label (`t()` key) | Content |
|---|---|---|
| 0 | `admin.tab_ops` | Pending reviews, CMS, pipelines, editing, sync |
| 1 | `admin.tab_insights` | **Stats cards**, search analytics, integrity |
| 2 | `admin.tab_audit` | **Change logs** (biz names, comments) |

The tests run `at.run()` once and check the default tab (index 0 = Ops). Stats (`st.metric`) are on tab 1 and the expand buttons are on tab 2, so neither is visible on the first render.

Additionally, `get_admin_stats()` was refactored to issue a single combined query returning columns `tables, columns, comments, overrides`. The test's `sql_returns(pd.DataFrame({"c": [42]}), ...)` still supplies four separate single-column DataFrames, none of which match the expected column names. The combined query returns a DF with column `c`, the column lookups on `tables`/`columns` raise a `KeyError` which is swallowed by `except Exception`, and the stats dict defaults to all zeros.

**Fix needed:**
1. Add a second `at.run()` after setting `at.session_state["admin_active_tab"]` to the Insights tab label to reach the stats section.
2. Update the Audit tab tests similarly.
3. Update `sql_returns(...)` in `_run_admin` to supply a single DataFrame with columns `tables, columns, comments, overrides` to match the consolidated query.

---

## Group 2 — Admin quality insights tab (1 failure)

**File:** `tests/test_feat_enhancements.py`

**Test:** `test_admin_quality_insights_tab_renders`

**Symptom:** `assert "Operations" in tab_labels` where `tab_labels == []`

**Root cause:** The test uses `at.tabs` (which wraps `st.tabs()`) to discover tab labels:

```python
tab_labels = [tab.label for tab in at.tabs]
assert "Operations" in tab_labels
```

The admin page now uses `st.segmented_control` (not `st.tabs`). Streamlit's AppTest exposes `segmented_control` widgets via `at.button`-adjacent APIs, not `at.tabs`, so `at.tabs` returns an empty list even when the page is rendered correctly.

**Fix needed:** Replace `at.tabs` lookup with inspection of the rendered markdown/HTML or navigate directly via session_state (`at.session_state["admin_active_tab"] = t("admin.tab_insights")`) and add a second `at.run()`.

---

## Group 3 — Analytics storage DuckDB cursor API mismatch (1 failure)

**File:** `tests/test_storage_analytics.py`

**Test:** `test_duckdb_analytics_alerts`

**Symptom:** `AttributeError: 'TestDuckDBConn' object has no attribute 'cursor'`

**Root cause:** The test creates a hand-rolled mock connection class (`TestDuckDBConn`) with only `execute()` and `fetchall_as_pandas()` methods directly on the connection. The production code was later updated to use the cursor pattern:

```python
# production (analytics_storage.py line 88)
with conn.cursor() as cur:
    cur.execute(query)
    df = cur.fetchall_as_pandas()
```

The mock connection has no `cursor()` method, so the call blows up.

**Fix needed:** Add a `cursor()` context manager to `TestDuckDBConn` that returns `self` (or a nested cursor mock with its own `execute` / `fetchall_as_pandas`). Alternatively, replace the hand-rolled class with `FakeAnalyticsStorage` to avoid mocking internals entirely.

---

## Group 4 — Discovery tab: segmented_control session_state injection (14 failures)

**File:** `tests/test_ui_discovery.py`

**Tests:** All `TestDiscoveryTabs` tests except `test_discovery_tabs_render_notable`

**Symptom:**
```
ValueError: content: "M"
 is not in list
```

**Root cause:** Tests navigate between Discovery sub-tabs by pre-setting session_state before the second `at.run()`:

```python
at.session_state["discovery_active_tab"] = "My Bookmarks"
at.run()
```

Streamlit's AppTest framework serializes widget state at `run()` time. For `st.segmented_control`, options are stored internally as proto `content` objects. When AppTest tries to validate the pre-set string `"My Bookmarks"` against the options list, it calls `format_func(v)` which returns `content: "M"` (a truncated proto representation, not the full label string), and the lookup fails with `ValueError`.

This is a Streamlit AppTest limitation: `segmented_control` values cannot be injected via session_state when the control was not yet rendered with that value; only direct widget interaction (`at.segmented_control[0].set_value(...)`) works.

The one passing test (`test_discovery_tabs_render_notable`) works because it never sets `discovery_active_tab` — it stays on the default tab throughout.

**Fix needed:** Replace session_state injection with direct widget interaction:

```python
# Instead of:
at.session_state["discovery_active_tab"] = "My Bookmarks"
at.run()

# Use:
at.segmented_control(key="discovery_active_tab").set_value("My Bookmarks")
at.run()
```

The same pattern applies to all 14 affected tests. Note that this is the identical issue affecting the admin tab tests in Group 1.

---

## Group 5 — Pipeline delete: confirmation dialog not navigable (1 failure)

**File:** `tests/test_ui_pipelines.py`

**Test:** `TestAdminPipelinesSection::test_render_with_pipelines_and_delete`

**Symptom:** `AssertionError: Expected 'delete_pipeline_def' to be called once. Called 0 times.`

**Root cause:** The test clicks a Delete button and asserts `delete_pipeline_def` was called:

```python
at.button(key="delete_pipeline_1").click().run()
mock_delete.assert_called_once_with("1")
```

But the Delete button in `src/ui/cards/pipelines.py` calls `_show_delete_pipeline_dialog(pipeline_id)`, which opens a `@st.dialog` confirmation modal. The actual `delete_pipeline_def()` call is inside that modal's "Confirm" button. Streamlit AppTest does not support dialog interactions — dialogs are not rendered into the `at.button` collection, so the confirm click is never reachable.

**Fix needed:** Either (a) test the dialog function `_show_delete_pipeline_dialog` in isolation with `AppTest.from_function`, or (b) add an `unsafe_bypass_confirmation=True` env flag that skips the dialog in test contexts. Option (a) is preferred as it keeps production code unchanged.

---

## Summary table

| # | File | Count | Root cause category |
|---|---|---|---|
| 1 | `test_admin.py` | 4 | Tab refactor: stats/logs moved to non-default tabs; combined SQL query shape mismatch |
| 2 | `test_feat_enhancements.py` | 1 | `st.tabs` → `st.segmented_control`: `at.tabs` returns empty list |
| 3 | `test_storage_analytics.py` | 1 | Mock connection missing `cursor()` method after API update |
| 4 | `test_ui_discovery.py` | 14 | AppTest can't inject `segmented_control` value via `session_state` |
| 5 | `test_ui_pipelines.py` | 1 | AppTest can't interact with `@st.dialog` confirmation flow |
