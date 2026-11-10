## 2025-02-18 - Add focus visible styles for keyboard navigation
**Learning:** Only text inputs have an explicit focus indicator in the design system. Links and buttons lack custom focus styles, which harms keyboard navigation accessibility and WCAG compliance.
**Action:** Add global `:focus-visible` styles to `a` and `button` elements in `assets/design.css` to ensure keyboard navigation works correctly while not disrupting mouse users.
