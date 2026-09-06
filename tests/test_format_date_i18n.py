import pytest
from src.i18n import format_date

def test_format_date_with_iso_string(monkeypatch):
    monkeypatch.setenv("STREAMLIT_SERVER_LOCALE", "en")

    # Valid ISO string
    assert format_date("2023-10-27T10:00:00Z") == "Oct 27, 2023 10:00 AM UTC"

    # Invalid string (falls back to returning the string directly)
    assert format_date("Not a date") == "Not a date"

    # Non-datetime object
    assert format_date(12345) == "12345"
