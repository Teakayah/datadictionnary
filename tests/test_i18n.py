from unittest.mock import patch
from src.i18n import get_locale


def test_get_locale_valid_fr():
    with patch("src.i18n.st.context") as mock_context:
        mock_context.headers = {
            "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7"
        }
        assert get_locale() == "fr"


def test_get_locale_valid_en():
    with patch("src.i18n.st.context") as mock_context:
        mock_context.headers = {"Accept-Language": "en-US,en;q=0.9"}
        assert get_locale() == "en"


def test_get_locale_error_handling():
    # Simulate an exception when accessing headers
    with patch("src.i18n.st.context") as mock_context:
        mock_context.headers.get.side_effect = Exception("Simulated error")
        assert get_locale() == "en"

    # Simulate a return value that causes an exception during parsing (e.g., None has no attribute 'split')
    with patch("src.i18n.st.context") as mock_context:
        mock_context.headers.get.return_value = None
        assert get_locale() == "en"
