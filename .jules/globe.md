## 2024-05-22 - [Concatenation]
**Learning:** String concatenation should not be used when localized strings are involved (e.g. `f"{t('key')}: {_e}"`).
**Action:** Pass the dynamic variables to the translation function `t('key', error=str(_e))` and use placeholders in the translation files.

## 2023-10-27 - [Extraction method]
**Learning:** When extracting placeholder strings, avoid generic regex or direct replacement in shell scripts. Always create a python script that utilizes `json.load()` and `json.dump(..., ensure_ascii=False)` to prevent unicode issues and malformed JSON.
**Action:** Apply Python-based file modifications for string extractions in JSON dictionaries.
