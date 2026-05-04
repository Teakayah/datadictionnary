## 2025-05-04 - Fix i18n text matching in design system tests
**Learning:** UI strings have been abstracted into localization dictionaries (`locale/en.json`). Tests asserting on text content (like checking for the '§' symbol or checking title case) should parse and search these JSON strings, not raw Python source code (`_read_app_source()`).
**Action:** When updating tests that assert on UI copy, use `locale/en.json` as the source of truth for text instead of attempting to scan for hardcoded string literals in the source.
