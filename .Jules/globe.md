## 2024-05-22 - [Concatenation]
**Learning:** String concatenation should not be used when localized strings are involved (e.g. `f"{t('key')}: {_e}"`).
**Action:** Pass the dynamic variables to the translation function `t('key', error=str(_e))` and use placeholders in the translation files.
