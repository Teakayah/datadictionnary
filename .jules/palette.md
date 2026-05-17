## 2026-05-04 - Localized Strings for Icon-Only Buttons
**Learning:** In this application, when replacing exact character matches for bookmark symbols (★/☆) or arrows (→) to improve accessibility on `st.button`s without labels, it's essential to supply the `help` parameter with an appropriate i18n translation key to act as a tooltip/aria-label.
**Action:** Use `help=t("...")` on `st.button` elements that act as icon-only buttons to ensure they have an accessible name available to screen readers.

## 2026-05-09 - Added help attribute to Start/Stop pipeline buttons
**Learning:** The "Start" and "Stop" buttons in the pipelines UI were predominantly icon-based (▶ Start, ■ Stop) and lacked tooltips, making them less accessible and intuitive. Added `help` attribute with localized strings to improve UX and accessibility.
**Action:** Always verify that buttons containing symbols or icons as primary indicators have an accessible `help` attribute.

## 2024-05-17 - Use primary styling for CTA buttons
**Learning:** Found multiple places in the app where primary actions are missing the `type="primary"` visual hierarchy, particularly "Start pipeline" and "Leave a comment". Users notice the lack of visual cues for primary calls to action. Streamlit's `st.button` supports `type="primary"` to draw attention to the main action.
**Action:** Adding `type="primary"` to primary actions, such as `t("pipelines.start")` and `t("comment.leave_a_comment")`.
