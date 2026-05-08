1. **Optimize `_merge_into_local` in `src/sync/dr_resync.py`**:
   - Edit `src/sync/dr_resync.py` to modify `_merge_into_local`.
   - Replace the slow `df.to_dict("records")` loop with DuckDB's native DataFrame insertion logic.
   - Specifically, implement it as:
     ```python
     verb = "INSERT OR IGNORE" if table in ("comments", "audit_log") else "INSERT OR REPLACE"
     sql = f"{verb} INTO user_data.{table} SELECT * FROM _dr_tmp_df"
     with local_conn.cursor() as cur:
         if hasattr(cur, '_con') and hasattr(cur._con, 'register'):
             cur._con.register("_dr_tmp_df", df)
             cur.execute_write(sql)
             cur._con.unregister("_dr_tmp_df")
         else:
             cols = ", ".join(df.columns)
             placeholders = ", ".join(f"%({c})s" for c in df.columns)
             sql_fallback = f"{verb} INTO user_data.{table} ({cols}) VALUES ({placeholders})"
             for row in df.to_dict("records"):
                 cur.execute_write(sql_fallback, row)
     ```
   - This ensures we eliminate the N+1 problem by leveraging DuckDB's native fast dataframes loading capabilities while still providing a mocked fallback mechanism if the custom cursor doesn't expose the underlying connection or register method.

2. **Testing**:
   - Run the full test suite using: `python -m pytest tests/ -q --ignore=tests/test_load_smoke.py --ignore=tests/test_wcag_axe.py --ignore=tests/test_nav_render.py` to ensure logic is correct and no regressions are introduced.

3. **Pre-commit**:
   - Complete pre-commit steps to ensure proper testing, verification, review, and reflection are done.
