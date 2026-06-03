## 2026-05-28 - Missing Pipeline Translation Keys
**Learning:** The pipeline UI uses `st.toast(t("pipelines.started"))` but the `"started"` key was entirely missing from `locale/en.json` and `locale/fr.json`.
**Action:** When inspecting hardcoded strings or missing keys, verify all parameters passed to the `t()` translation function exist in all relevant locale dictionaries. Use `grep -rn 't("'` to audit translation keys.
