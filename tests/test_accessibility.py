"""
WCAG 2.0 accessibility compliance tests.

Scope (testable without a real browser or axe-core):
  1.1 — Language attribute present on the page (Success Criterion 3.1.1)
  1.2 — Form inputs have non-empty labels (SC 1.3.1)
  1.3 — Buttons have non-empty, descriptive labels (SC 4.1.2)
  1.4 — Error messages use semantic st.error, not bare st.write (SC 1.3.3)
  1.5 — Landmark / navigation region present in header HTML (SC 1.3.6)
  1.6 — Heading hierarchy: h1 before h3 (SC 1.3.1)
  1.7 — Language toggle is discoverable and labelled (SC 3.1.2)
  1.8 — Color is not sole means of conveying state (SC 1.4.1)
  1.9 — Admin access denial expressed with st.error (SC 4.1.3)
  1.10 — Search input has a descriptive label or placeholder (SC 1.3.1)
  1.11 — Locale files have identical key sets (no silent fallback to key name)
  1.12 — Main content region has aria-live for dynamic updates (SC 4.1.3)
"""
from __future__ import annotations

import json
import os
import re
import pandas as pd
from streamlit.testing.v1 import AppTest

from tests.conftest import sql_returns

APP_PATH = os.path.join(os.path.dirname(__file__), "..", "app.py")

ADMIN_GROUP    = "admin_group_id"
STANDARD_GROUP = "finance_dept_id"


def _html(at: AppTest) -> str:
    """Extracts raw HTML from AppTest markdown and st.html() nodes in the main container."""
    parts = []
    # 1. Standard markdown
    if hasattr(at, "markdown"):
        parts.extend(m.value for m in at.markdown)
    # 2. Extract st.html injections which are stored as UnknownElement (html)
    for el in getattr(at, "main", []):
        if type(el).__name__ == "UnknownElement" and getattr(el, "type", "") == "html":
            parts.append(getattr(el.proto, "body", ""))
    # Look into elements list too since st.html got changed
    if hasattr(at, "elements"):
        for el in at.elements:
             if type(el).__name__ == "UnknownElement" and getattr(el, "type", "") == "html":
                parts.append(getattr(el.proto, "body", ""))
    return " ".join(parts)


def _signed_in_app(*, groups: list[str] | None = None) -> AppTest:
    at = AppTest.from_file(APP_PATH, default_timeout=15)
    at.session_state["authenticated"] = True
    at.session_state["user_groups"] = groups or [STANDARD_GROUP]
    at.session_state["user_name"]   = "Test User"
    at.session_state["user_email"]  = "test@example.com"
    return at


# ── 1.1  Language attribute ───────────────────────────────────────────────────

class TestLanguageAttribute:
    """SC 3.1.1 — Language of Page."""

    def test_lang_attribute_in_header_html(self):
        """The dd-header element must carry a lang= attribute for screen readers."""
        at = _signed_in_app()
        at.run()
        assert not at.exception, f"Exception: {at.exception}"
        html = _html(at)
        assert re.search(r'lang=["\'](?:en|fr)["\']', html), \
            "No lang= attribute found in rendered header HTML"


# ── 1.2  Form input labels ────────────────────────────────────────────────────

class TestInputLabels:
    """SC 1.3.1 — Info and Relationships: every input must have a visible label."""

    def test_text_inputs_have_labels(self):
        at = _signed_in_app()
        at.run()
        assert not at.exception, f"Exception: {at.exception}"
        for inp in at.text_input:
            assert inp.label and inp.label.strip(), \
                f"st.text_input key={inp.key!r} has no label"

    def test_text_areas_have_labels(self):
        at = _signed_in_app()
        at.run()
        assert not at.exception, f"Exception: {at.exception}"
        for area in at.text_area:
            assert area.label and area.label.strip(), \
                f"st.text_area key={area.key!r} has no label"

    def test_selectboxes_have_labels(self):
        at = _signed_in_app()
        at.run()
        assert not at.exception, f"Exception: {at.exception}"
        for sel in at.selectbox:
            assert sel.label and sel.label.strip(), \
                f"st.selectbox key={sel.key!r} has no label"


# ── 1.3  Button labels ────────────────────────────────────────────────────────

class TestButtonLabels:
    """SC 4.1.2 — Name, Role, Value: buttons must have descriptive text."""

    def test_buttons_have_non_empty_labels(self):
        at = _signed_in_app()
        at.run()
        assert not at.exception, f"Exception: {at.exception}"
        # Exclude the hidden nav/lang proxy buttons (label = tab id or "Lang XX")
        # All visible buttons must still have a label
        for btn in at.button:
            assert btn.label is not None and len(btn.label.strip()) > 0, \
                f"Button key={btn.key!r} has an empty label"


# ── 1.4  Semantic error states ────────────────────────────────────────────────

class TestSemanticErrors:
    """SC 1.3.3 — Sensory Characteristics: errors must not rely on color alone."""

    def test_admin_denial_uses_st_error(self, monkeypatch):
        """Non-admin navigating to /admin must get an st.error, not a bare write."""
        monkeypatch.setenv("ADMIN_GROUPS", ADMIN_GROUP)
        at = _signed_in_app(groups=[STANDARD_GROUP])
        at.query_params["tab"] = "admin"
        at.run()
        assert not at.exception, f"Exception: {at.exception}"
        assert len(at.error) > 0, "Expected at least one st.error for access denied"
        assert any("access" in e.value.lower() for e in at.error), \
            "Access-denied message not found in st.error widgets"


# ── 1.5  Navigation landmark ──────────────────────────────────────────────────

class TestLandmarkRegions:
    """SC 1.3.6 — Identify Purpose: navigation landmarks aid screen-reader users."""

    def test_nav_role_or_class_present(self):
        at = _signed_in_app()
        at.run()
        assert not at.exception, f"Exception: {at.exception}"
        html = _html(at)
        has_nav = (
            "<nav" in html
            or 'role="navigation"' in html
            or "dd-nav" in html
        )
        assert has_nav, "No navigation landmark found in rendered HTML"

    def test_nav_has_aria_label(self):
        at = _signed_in_app()
        at.run()
        assert not at.exception, f"Exception: {at.exception}"
        html = _html(at)
        assert "aria-label" in html, \
            "Navigation element missing aria-label attribute"


# ── 1.6  Heading hierarchy ────────────────────────────────────────────────────

class TestHeadingHierarchy:
    """SC 1.3.1 — Headings must follow a logical order (h1 → h2 → h3)."""

    def test_no_orphaned_h3_without_h1(self):
        at = _signed_in_app()
        at.run()
        assert not at.exception, f"Exception: {at.exception}"
        html = _html(at)
        has_h3 = bool(re.search(r"<h3|^### ", html, re.MULTILINE))
        has_h1 = bool(re.search(r"<h1|^# ", html, re.MULTILINE))
        if has_h3:
            assert has_h1, "h3 heading found without a preceding h1"


# ── 1.7  Language toggle ──────────────────────────────────────────────────────

class TestLanguageToggle:
    """SC 3.1.2 — Language of Parts: user must be able to change the display language."""

    def test_language_toggle_present_in_header(self):
        at = _signed_in_app()
        at.run()
        assert not at.exception, f"Exception: {at.exception}"
        html = _html(at)
        assert "EN" in html and "FR" in html, \
            "Language toggle (EN / FR) not found in rendered header HTML"

    def test_language_toggle_has_title_attribute(self):
        at = _signed_in_app()
        at.run()
        assert not at.exception, f"Exception: {at.exception}"
        html = _html(at)
        # Gemini-designed toggle renders title= on each lang link
        assert "switch_to" in html.lower() or "switch to" in html.lower() \
            or "passer en" in html.lower() or "title=" in html, \
            "Language toggle links missing accessible title attributes"

    def test_locale_switches_to_french(self):
        """Setting session_state.locale='fr' must change visible labels."""
        at = _signed_in_app()
        at.session_state["locale"] = "fr"
        at.run()
        assert not at.exception, f"Exception: {at.exception}"
        html = _html(at)
        # French nav label must appear somewhere in the header
        assert "Recherche" in html or "Glossaire" in html or "Santé" in html, \
            "French locale not applied to navigation labels"

    def test_locale_defaults_to_english(self):
        """Without a locale override the app defaults to English labels."""
        at = _signed_in_app()
        at.run()
        assert not at.exception, f"Exception: {at.exception}"
        html = _html(at)
        assert "Search" in html or "Glossary" in html, \
            "Default English locale not applied to navigation labels"


# ── 1.8  Color not sole indicator ────────────────────────────────────────────

class TestColorNotSoleIndicator:
    """SC 1.4.1 — Status must be conveyed by more than color."""

    def test_active_nav_tab_has_text_class(self):
        """Active navigation tab must use a CSS class, not just inline color."""
        at = _signed_in_app()
        at.run()
        assert not at.exception, f"Exception: {at.exception}"
        html = _html(at)
        # The active class 'active' is added to the current tab link
        assert 'class="dd-nav-tab active"' in html or "dd-nav-tab active" in html, \
            "Active tab not indicated by a CSS class (color-only would fail WCAG 1.4.1)"


# ── 1.9  Search input ────────────────────────────────────────────────────────

class TestSearchInput:
    """SC 1.3.1 — Search input must have a descriptive label."""

    def test_search_tab_has_labelled_input(self):
        """Search tab must have at least one labelled interactive input (text or select)."""
        empty = pd.DataFrame(columns=[
            "full_name", "catalog_name", "schema_name", "table_name",
            "table_description", "table_type", "updated_at",
        ])
        sql_returns(empty)
        at = _signed_in_app()
        at.query_params["tab"] = "search"
        at.run()
        assert not at.exception, f"Exception: {at.exception}"
        # The search tab uses text_input or selectbox depending on the implementation
        all_inputs = list(at.text_input) + list(at.selectbox)
        assert len(all_inputs) > 0, \
            "No interactive inputs (text_input or selectbox) found on the search tab"
        labelled = [
            i for i in all_inputs
            if i.label and i.label.strip()
        ]
        assert len(labelled) > 0, \
            "Search tab has no labelled inputs (WCAG SC 1.3.1)"


# ── 1.11  Locale key parity ───────────────────────────────────────────────────

LOCALE_DIR = os.path.join(os.path.dirname(__file__), "..", "locale")


def _flatten_keys(d: dict, prefix: str = "") -> set[str]:
    """Recursively collect all dotted key paths from a nested dict."""
    keys: set[str] = set()
    for k, v in d.items():
        full = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            keys |= _flatten_keys(v, full)
        else:
            keys.add(full)
    return keys


class TestLocaleParity:
    """Every key in en.json must exist in fr.json and vice versa.

    Missing keys cause silent fallback to the raw key name in the UI, which
    breaks the non-English locale.  SC 3.1.2 — Language of Parts.
    """

    def _load(self, lang: str) -> dict:
        path = os.path.join(LOCALE_DIR, f"{lang}.json")
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def test_fr_has_all_en_keys(self):
        en_keys = _flatten_keys(self._load("en"))
        fr_keys = _flatten_keys(self._load("fr"))
        missing = en_keys - fr_keys
        assert not missing, (
            "Keys present in en.json but missing from fr.json:\n"
            + "\n".join(f"  {k}" for k in sorted(missing))
        )

    def test_en_has_all_fr_keys(self):
        en_keys = _flatten_keys(self._load("en"))
        fr_keys = _flatten_keys(self._load("fr"))
        extra = fr_keys - en_keys
        assert not extra, (
            "Keys present in fr.json but missing from en.json:\n"
            + "\n".join(f"  {k}" for k in sorted(extra))
        )


# ── 1.12  Aria-live on main content ──────────────────────────────────────────

class TestAriaLive:
    """SC 4.1.3 — Status messages must be programmatically determinable.

    The main page container must carry aria-live so that dynamic content
    changes (search results, save confirmations) are announced to screen readers.
    """

    def test_main_content_has_aria_live(self):
        at = _signed_in_app()
        at.run()
        assert not at.exception, f"Exception: {at.exception}"
        html = _html(at)
        assert 'aria-live' in html, \
            "Main content wrapper missing aria-live attribute (WCAG SC 4.1.3)"

    def test_main_content_has_role_main(self):
        at = _signed_in_app()
        at.run()
        assert not at.exception, f"Exception: {at.exception}"
        html = _html(at)
        assert 'role="main"' in html, \
            "Main content wrapper missing role='main' landmark (WCAG SC 1.3.6)"
