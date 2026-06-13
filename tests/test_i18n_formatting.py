import pytest
from datetime import datetime
from unittest.mock import patch
from src.i18n import format_number, format_date, t

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

def test_format_date_empty():
    assert format_date(None) == ""
    assert format_date("") == ""

def test_format_date_short():
    with patch("src.i18n.st") as mock_st, patch("src.i18n.t") as mock_t:
        mock_st.session_state = {"locale": "en"}
        # Mock t() to return its arguments nicely so we can check it
        mock_t.side_effect = lambda key, **kwargs: f"{key} " + " ".join([f"{k}={v}" for k, v in kwargs.items()])

        dt = datetime(2023, 5, 10, 14, 30)
        res = format_date(dt, format_type="short")
        # first it will call t("date.months.5")
        # then it will call t("date.short", day="10", month="...")
        assert "date.short" in res

def test_format_date_long():
    with patch("src.i18n.st") as mock_st, patch("src.i18n.t") as mock_t:
        mock_st.session_state = {"locale": "en"}
        # Mock t() to return its arguments nicely so we can check it
        mock_t.side_effect = lambda key, **kwargs: f"{key} " + " ".join([f"{k}={v}" for k, v in kwargs.items()])

        dt = datetime(2023, 5, 10, 14, 30)
        res = format_date(dt, format_type="long")
        # first it will call t("date.months.5")
        # then it will call t("date.long", day="10", month="...", year=2023, time="14:30")
        assert "date.long" in res

def test_t_pluralization():
    with patch("src.i18n.st") as mock_st, patch("src.i18n.LOCALES", {"en": {"items_zero": "No items", "items_one": "One item", "items_other": "{count} items"}}):
        mock_st.session_state = {"locale": "en"}
        assert t("items", count=0) == "No items"
        assert t("items", count=1) == "One item"
        assert t("items", count=5) == "5 items"

        # Test fallback when suffix not found
        assert t("missing", count=2) == "missing"

def test_t_pluralization_format_error():
    with patch("src.i18n.st") as mock_st, patch("src.i18n.LOCALES", {"en": {"items_other": "{count} items {missing}"}}):
        mock_st.session_state = {"locale": "en"}
        # This will trigger KeyError inside the pluralization format block and fallback to regular key block
        assert t("items", count=5) == "items"
