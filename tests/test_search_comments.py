import pytest
from streamlit.testing.v1 import AppTest

def run_comment_form():
    import streamlit as st
    from src.pages.search import _render_comment_form
    _render_comment_form("main.sales.orders", "test@example.com", "main.sales.orders")

def test_comment_form_empty_error(monkeypatch):
    """Submitting an empty comment should show a warning message."""
    at = AppTest.from_function(run_comment_form)
    at.run()

    btn = next(b for b in at.button if b.label == "Leave a comment")
    btn.click().run()

    send_btn = next(b for b in at.button if b.label == "Send")
    send_btn.click().run()

    assert any("comment" in w.value.lower() or "empty" in w.value.lower() or "Please enter a comment" in w.value for w in at.warning)

def test_comment_form_cancel():
    """Clicking cancel should close the form."""
    at = AppTest.from_function(run_comment_form)
    at.run()

    btn = next(b for b in at.button if b.label == "Leave a comment")
    btn.click().run()

    cancel_btn = next(b for b in at.button if b.label == "Cancel")
    cancel_btn.click().run()

    assert any(b.label == "Leave a comment" for b in at.button)

def test_comment_form_save(monkeypatch):
    """Submitting a valid comment should call save_comment and close the form."""
    from unittest.mock import MagicMock
    mock_save = MagicMock()
    monkeypatch.setattr("src.pages.search.save_comment", mock_save)

    at = AppTest.from_function(run_comment_form)
    at.run()

    btn = next(b for b in at.button if b.label == "Leave a comment")
    btn.click().run()

    text_area = at.text_area[0]
    text_area.set_value("This is a great table!").run()

    send_btn = next(b for b in at.button if b.label == "Send")
    send_btn.click().run()

    mock_save.assert_called_once_with(
        "TABLE", "main.sales.orders", "This is a great table!", "test@example.com", parent_comment_id=None
    )
    assert any(b.label == "Leave a comment" for b in at.button)

def run_reply_form():
    import streamlit as st
    from src.pages.search import _render_comment_form
    _render_comment_form("main.sales.orders", "test@example.com", "main.sales.orders_123", "123")

def test_comment_form_reply(monkeypatch):
    """The reply form should use the correct labels and pass parent_comment_id."""
    from unittest.mock import MagicMock
    mock_save = MagicMock()
    monkeypatch.setattr("src.pages.search.save_comment", mock_save)

    at = AppTest.from_function(run_reply_form)
    at.run()

    btn = next(b for b in at.button if b.label == "Reply")
    btn.click().run()

    text_area = at.text_area[0]
    text_area.set_value("This is a reply!").run()

    send_btn = next(b for b in at.button if b.label == "Send")
    send_btn.click().run()

    mock_save.assert_called_once_with(
        "TABLE", "main.sales.orders", "This is a reply!", "test@example.com", parent_comment_id="123"
    )
    assert any(b.label == "Reply" for b in at.button)

def run_comment_form_no_steward():
    import streamlit as st
    from src.pages.search import _render_comment_form
    _render_comment_form("main.sales.orders", "", "main.sales.orders")

def test_comment_form_no_steward():
    """If no steward is configured, the form should show a warning message."""
    at = AppTest.from_function(run_comment_form_no_steward)
    at.run()

    btn = next(b for b in at.button if b.label == "Leave a comment")
    btn.click().run()

    html = "\n".join([m.value for m in at.markdown])
    assert "dd-comment-no-steward" in html
