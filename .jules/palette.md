## 2026-05-04 - Localized Strings for Icon-Only Buttons
**Learning:** In this application, when replacing exact character matches for bookmark symbols (★/☆) or arrows (→) to improve accessibility on `st.button`s without labels, it's essential to supply the `help` parameter with an appropriate i18n translation key to act as a tooltip/aria-label.
**Action:** Use `help=t("...")` on `st.button` elements that act as icon-only buttons to ensure they have an accessible name available to screen readers.
