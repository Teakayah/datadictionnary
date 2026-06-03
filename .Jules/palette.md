## 2024-05-28 - Added Tooltips to Save/Cancel/Send Buttons
**Learning:** Tooltips are a critical accessibility feature for buttons. We noticed `st.button`s across multiple components didn't have `help` properties.
**Action:** Always include a `help` property (which translates to `title`/`aria-label`) for actionable buttons like Save, Cancel, Send Comment, etc., using the translation dictionary to ensure localization.
