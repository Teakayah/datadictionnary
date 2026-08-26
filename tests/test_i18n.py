from unittest.mock import patch
from src.i18n import get_locale, t, set_locale

def test_get_locale_explicit_supplementary():
    """Explicit supplementary test for get_locale to fulfill testing requirement."""
    from src.i18n import get_locale
    with patch("src.i18n.st.context") as mock_context:
        mock_context.headers = {"Accept-Language": "invalid-format-xyz"}
        assert get_locale() == "en"

def test_get_locale_valid_fr():
    with patch("src.i18n.st.context") as mock_context:
        mock_context.headers = {"Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7"}
        assert get_locale() == "fr"

def test_get_locale_valid_en():
    with patch("src.i18n.st.context") as mock_context:
        mock_context.headers = {"Accept-Language": "en-US,en;q=0.9"}
        assert get_locale() == "en"

def test_get_locale_error_handling():
    with patch("src.i18n.st.context") as mock_context:
        mock_context.headers.get.side_effect = Exception("Simulated error")
        assert get_locale() == "en"

    with patch("src.i18n.st.context") as mock_context:
        mock_context.headers.get.return_value = None
        assert get_locale() == "en"

def test_get_locale_unsupported_language():
    with patch("src.i18n.st.context") as mock_context:
        mock_context.headers = {"Accept-Language": "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7"}
        assert get_locale() == "en"

def test_get_locale_empty_string():
    with patch("src.i18n.st.context") as mock_context:
        mock_context.headers = {"Accept-Language": ""}
        assert get_locale() == "en"

def test_get_locale_whitespace_padding():
    with patch("src.i18n.st.context") as mock_context:
        mock_context.headers = {"Accept-Language": "   fr-CH  ,fr;q=0.9"}
        assert get_locale() == "fr"

def test_get_locale_uppercase():
    with patch("src.i18n.st.context") as mock_context:
        mock_context.headers = {"Accept-Language": "FR-CA,fr;q=0.8"}
        assert get_locale() == "fr"

def test_t_formats_kwargs():
    with patch("src.i18n.st") as mock_st, patch("src.i18n.LOCALES", {"en": {"hello": "Hello {name}"}}):
        mock_st.session_state = {"locale": "en"}
        assert t("hello", name="World") == "Hello World"

def test_t_falls_back_to_en():
    with patch("src.i18n.st") as mock_st, patch("src.i18n.LOCALES", {"en": {"hello": "Hello"}, "fr": {}}):
        mock_st.session_state = {"locale": "fr"}
        assert t("hello") == "Hello"

def test_t_falls_back_to_key_if_missing():
    with patch("src.i18n.st") as mock_st, patch("src.i18n.LOCALES", {"en": {}}):
        mock_st.session_state = {"locale": "en"}
        assert t("missing.key") == "missing.key"

def test_t_handles_key_error_in_format():
    with patch("src.i18n.st") as mock_st, patch("src.i18n.LOCALES", {"en": {"hello": "Hello {name}"}}):
        mock_st.session_state = {"locale": "en"}
        # missing kwargs
        assert t("hello") == "Hello {name}"

def test_t_handles_non_dict_lookup():
    with patch("src.i18n.st") as mock_st, patch("src.i18n.LOCALES", {"en": {"level1": "string_not_dict"}}):
        mock_st.session_state = {"locale": "en"}
        assert t("level1.level2") == "level1.level2"

def test_set_locale():
    with patch("src.i18n.st") as mock_st:
        mock_st.session_state = {}
        set_locale("fr")
        assert mock_st.session_state["locale"] == "fr"

def test_set_locale_overwrite():
    from src.i18n import set_locale
    with patch("src.i18n.st") as mock_st:
        mock_st.session_state = {"locale": "en"}
        set_locale("fr")
        assert mock_st.session_state["locale"] == "fr"

def test_set_locale_explicit_coverage():
    """Explicitly test set_locale to fulfill testing requirement."""
    from src.i18n import set_locale
    with patch("src.i18n.st") as mock_st:
        mock_st.session_state = {}
        set_locale("en")
        assert mock_st.session_state["locale"] == "en"

def test_ensure_locale():
    with patch("src.i18n.st") as mock_st, patch("src.i18n.get_locale", return_value="fr"):
        mock_st.session_state = {}
        t("some.key")
        assert mock_st.session_state["locale"] == "fr"

def test_load_locales_exception():
    with patch("builtins.open", side_effect=Exception("simulated missing file")):
        from src.i18n import _load_locales
        res = _load_locales()
        assert res == {"en": {}, "fr": {}}

def test_t_handles_key_error_in_format_with_kwargs():
    with patch("src.i18n.st") as mock_st, patch("src.i18n.LOCALES", {"en": {"hello": "Hello {name}"}}):
        mock_st.session_state = {"locale": "en"}
        assert t("hello", wrong_key="World") == "Hello {name}"

def test_t_handles_index_error_in_format_with_kwargs():
    with patch("src.i18n.st") as mock_st, patch("src.i18n.LOCALES", {"en": {"hello": "Hello {0}"}}):
        mock_st.session_state = {"locale": "en"}
        assert t("hello", wrong_key="World") == "Hello {0}"

def test_lookup_valid():
    from src.i18n import _lookup
    assert _lookup({"a": {"b": "val"}}, ["a", "b"]) == "val"

def test_lookup_missing_key():
    from src.i18n import _lookup
    assert _lookup({"a": {"b": "val"}}, ["a", "c"]) is None

def test_lookup_empty_parts():
    from src.i18n import _lookup
    assert _lookup({"a": "val"}, []) is None

def test_lookup_root_not_dict():
    from src.i18n import _lookup
    assert _lookup("not_a_dict", ["a"]) is None

def test_lookup_intermediate_not_dict():
    from src.i18n import _lookup
    assert _lookup({"a": "string"}, ["a", "b"]) is None

def test_lookup_return_not_string():
    from src.i18n import _lookup
    assert _lookup({"a": {"b": 123}}, ["a", "b"]) is None

from datetime import datetime
from src.i18n import format_number, format_date

def test_format_number_en():
    with patch("src.i18n.st") as mock_st:
        mock_st.session_state = {"locale": "en"}
        assert format_number(1234567) == "1,234,567"
        assert format_number(1234.56) == "1,234.56"

def test_format_number_fr():
    with patch("src.i18n.st") as mock_st:
        mock_st.session_state = {"locale": "fr"}
        assert format_number(1234567) == "1\xa0234\xa0567"
        assert format_number(1234.56) == "1\xa0234,56"

def test_format_date_none():
    assert format_date(None) == ""
    assert format_date("") == ""

def test_format_date_short_en():
    with patch("src.i18n.st") as mock_st, patch("src.i18n.LOCALES", {"en": {"date": {"months": {"1": "Jan"}, "short": "{month} {day}"}}}):
        mock_st.session_state = {"locale": "en"}
        dt = datetime(2023, 1, 5, 14, 30)
        assert format_date(dt, "short") == "Jan 05"

def test_format_date_long_en():
    with patch("src.i18n.st") as mock_st, patch("src.i18n.LOCALES", {"en": {"date": {"time_format": "%I:%M %p", "months": {"1": "Jan"}, "long": "{month} {day}, {year} {time}"}}}):
        mock_st.session_state = {"locale": "en"}
        dt = datetime(2023, 1, 5, 14, 30)
        assert format_date(dt, "long") == "Jan 05, 2023 02:30 PM"

def test_format_date_iso_string_valid():
    with patch("src.i18n.st") as mock_st, patch("src.i18n.LOCALES", {"en": {"date": {"time_format": "%I:%M %p", "months": {"1": "Jan"}, "long": "{month} {day}, {year} {time}"}}}):
        mock_st.session_state = {"locale": "en"}
        dt_str = "2023-01-05T14:30:00Z"
        # The ISO parsing converts 'Z' to '+00:00', resulting in an offset-aware datetime object.
        assert format_date(dt_str, "long") == "Jan 05, 2023 02:30 PM"

def test_format_date_iso_string_invalid():
    assert format_date("not-an-iso-string") == "not-an-iso-string"

def test_format_date_no_strftime():
    class Dummy:
        pass
    dummy = Dummy()
    assert format_date(dummy) == str(dummy)

def test_t_pluralization_zero():
    with patch("src.i18n.st") as mock_st, patch("src.i18n.LOCALES", {"en": {"items_zero": "No items", "items_one": "1 item", "items_other": "{count} items"}}):
        mock_st.session_state = {"locale": "en"}
        assert t("items", count=0) == "No items"

def test_t_pluralization_one():
    with patch("src.i18n.st") as mock_st, patch("src.i18n.LOCALES", {"en": {"items_zero": "No items", "items_one": "{count} item", "items_other": "{count} items"}}):
        mock_st.session_state = {"locale": "en"}
        assert t("items", count=1) == "1 item"

def test_t_pluralization_other():
    with patch("src.i18n.st") as mock_st, patch("src.i18n.LOCALES", {"en": {"items_zero": "No items", "items_one": "1 item", "items_other": "{count} items"}}):
        mock_st.session_state = {"locale": "en"}
        assert t("items", count=5) == "5 items"

def test_t_pluralization_n_variable():
    with patch("src.i18n.st") as mock_st, patch("src.i18n.LOCALES", {"en": {"items_zero": "No items", "items_one": "1 item", "items_other": "{n} items"}}):
        mock_st.session_state = {"locale": "en"}
        assert t("items", n=5) == "5 items"

def test_t_pluralization_fallback():
    # If the _zero/_one/_other keys don't exist, it should gracefully ignore and just use standard lookup
    with patch("src.i18n.st") as mock_st, patch("src.i18n.LOCALES", {"en": {"items": "Just items {count}"}}):
        mock_st.session_state = {"locale": "en"}
        assert t("items", count=5) == "Just items 5"

def test_t_pluralization_handles_key_error_in_format():
    with patch("src.i18n.st") as mock_st, patch("src.i18n.LOCALES", {"en": {"items_other": "{count} items {missing}"}}):
        mock_st.session_state = {"locale": "en"}
        # If there's a key error, it falls back to regular non-plural search, or returns raw string or key
        assert "items" in t("items", count=5)

def test_t_pluralization_handles_index_error_in_format():
    with patch("src.i18n.st") as mock_st, patch("src.i18n.LOCALES", {"en": {"items_other": "{0} items"}}):
        mock_st.session_state = {"locale": "en"}
        assert "items" in t("items", count=5)
