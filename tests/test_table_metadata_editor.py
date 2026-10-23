from unittest.mock import patch
from streamlit.testing.v1 import AppTest
import pytest

def test_render_table_metadata_editor():
    def render_editor():
        from src.ui.cards.detail import render_table_metadata_editor
        render_table_metadata_editor("main.public.test_table", "Test Description", "test@example.com")

    # Mock i18n
    with patch("src.ui.cards.detail.t", side_effect=lambda k, **kw: k):
        at = AppTest.from_function(render_editor)
        at.run()

        # invalid email
        at.text_input[0].set_value("invalidemail").run()
        at.button[0].click().run()
        assert at.error[0].value == "detail.invalid_email"

        # valid save
        with patch("src.ui.cards.detail.save_table_metadata") as mock_save:
            at.text_input[0].set_value("valid@example.com").run()
            at.button[0].click().run()
            mock_save.assert_called_once_with(
                "main.public.test_table",
                description="Test Description",
                steward_email="valid@example.com"
            )
            assert len(at.error) == 0

        # cancel
        at.button[1].click().run()

        # exception on save
        with patch("src.ui.cards.detail.save_table_metadata", side_effect=Exception("Save Failed")):
            at.button[0].click().run()
            assert at.error[0].value == "common.error"
