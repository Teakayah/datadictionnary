import pytest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest

@pytest.fixture(autouse=True)
def mock_t():
    with patch("src.pages.search.t", side_effect=lambda k, **kw: k) as m:
        yield m

def test_comment_form_open_and_cancel():
    def render_form():
        from src.pages.search import _render_comment_form
        _render_comment_form("table1", "steward1", "key1")

    at = AppTest.from_function(render_form)
    at.run()

    assert not at.exception
    assert len(at.button) == 1
    assert at.button[0].label == "comment.leave_a_comment"

    with patch("streamlit.rerun"):
        # Click to open the form
        at.button[0].click().run()

    # Re-run manually since rerun was mocked
    at.run()

    assert not at.exception

    # Form is open, two buttons (Send and Cancel)
    assert len(at.text_area) == 1
    assert len(at.button) == 2
    assert at.button[0].label == "comment.send"
    assert at.button[1].label == "comment.cancel"

    with patch("streamlit.rerun"):
        # Click cancel
        at.button[1].click().run()

    # Re-run manually since rerun was mocked
    at.run()

    assert not at.exception

    # Form is closed
    assert len(at.button) == 1
    assert at.button[0].label == "comment.leave_a_comment"

def test_comment_form_submit_valid():
    def render_form():
        from src.pages.search import _render_comment_form
        _render_comment_form("table1", "steward1", "key1")

    at = AppTest.from_function(render_form)
    at.run()

    with patch("streamlit.rerun"):
        # Open form
        at.button[0].click().run()
    at.run()

    with patch("src.pages.search.save_comment") as mock_save, \
         patch("streamlit.rerun"):
        # Enter text and submit
        at.text_area[0].input("My comment").run()
        at.button[0].click().run()

        mock_save.assert_called_once_with("TABLE", "table1", "My comment", "steward1", parent_comment_id=None)

    # Trigger run because rerun was mocked
    at.run()

    # Form should be closed after submit
    assert len(at.button) == 1
    assert at.button[0].label == "comment.leave_a_comment"

def test_comment_form_submit_empty():
    def render_form():
        from src.pages.search import _render_comment_form
        _render_comment_form("table1", "steward1", "key1")

    at = AppTest.from_function(render_form)
    at.run()

    with patch("streamlit.rerun"):
        # Open form
        at.button[0].click().run()
    at.run()

    with patch("src.pages.search.save_comment") as mock_save:
        # Enter text and submit
        at.text_area[0].input("   ").run()
        at.button[0].click().run()

        mock_save.assert_not_called()

    # Warning should be displayed and form stays open
    assert len(at.warning) == 1
    assert at.warning[0].value == "comment.empty_error"
    assert len(at.button) == 2
