## 2024-05-22 - [Concatenation]
**Learning:** String concatenation should not be used when localized strings are involved (e.g. `f"{t('key')}: {_e}"`).
**Action:** Pass the dynamic variables to the translation function `t('key', error=str(_e))` and use placeholders in the translation files.

## 2023-10-27 - [Extraction method]
**Learning:** When extracting placeholder strings, avoid generic regex or direct replacement in shell scripts. Always create a python script that utilizes `json.load()` and `json.dump(..., ensure_ascii=False)` to prevent unicode issues and malformed JSON.
**Action:** Apply Python-based file modifications for string extractions in JSON dictionaries.

## 2024-05-19 - Extracted hardcoded pipeline placeholders
**Learning:** Hardcoded placeholders ("1234" and "42") inside `st.text_input` in `src/ui/cards/pipelines.py` bypassed the i18n framework.
**Action:** Always wrap placeholder strings inside `t()` and store in the localization JSON files, even for simple numeric examples, to maintain consistent localization logic across languages like French (where "e.g." translates to "ex.").
