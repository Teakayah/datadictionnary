## 2026-05-04 - Localized Strings for Icon-Only Buttons
**Learning:** In this application, when replacing exact character matches for bookmark symbols (★/☆) or arrows (→) to improve accessibility on `st.button`s without labels, it's essential to supply the `help` parameter with an appropriate i18n translation key to act as a tooltip/aria-label.
**Action:** Use `help=t("...")` on `st.button` elements that act as icon-only buttons to ensure they have an accessible name available to screen readers.

## 2026-05-09 - Added help attribute to Start/Stop pipeline buttons
**Learning:** The "Start" and "Stop" buttons in the pipelines UI were predominantly icon-based (▶ Start, ■ Stop) and lacked tooltips, making them less accessible and intuitive. Added `help` attribute with localized strings to improve UX and accessibility.
**Action:** Always verify that buttons containing symbols or icons as primary indicators have an accessible `help` attribute.
## 2026-05-13 - Highlight Primary Action Buttons
**Learning:** In Streamlit, primary call-to-action buttons like 'Save', 'Send', or 'Submit' should have `type='primary'` to make them clear and consistent across the UI.
**Action:** Always verify that the main actionable button in forms or dialogs has `type='primary'` to improve visual hierarchy and guide users.
