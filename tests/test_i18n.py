from unittest.mock import patch
from src.i18n import get_locale, t, set_locale

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
