import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

UTC = timezone.utc

with open("locale/en.json", "r") as f:
    en_locale = json.load(f)

# Mock wrapper for `_show_cms_create_dialog` to test the dialog independently
def create_dialog_app():
    from src.ui.cards.cms_admin import _show_cms_create_dialog
    _show_cms_create_dialog()

# Mock wrapper for `_render_admin_cms_section` to test rendering independently
def admin_section_app():
    from src.ui.cards.cms_admin import _render_admin_cms_section
    _render_admin_cms_section()

class TestCmsCreateDialog:
    @patch("src.ui.cards.cms_admin.create_post")
    def test_create_post_success(self, mock_create):
        at = AppTest.from_function(create_dialog_app).run()

        at.text_input[0].set_value("Test Title")
        at.text_area[0].set_value("Test Body")
        # Radio button: "Announcement" (default) is 0
        at.radio[0].set_value(en_locale["cms"]["type_announcement"])

        at.button[0].click().run() # Click "Save"

        mock_create.assert_called_once()
        args = mock_create.call_args[0][0]
        assert args.title == "Test Title"
        assert args.body == "Test Body"
        assert args.post_type == "announcement"

    @patch("src.ui.cards.cms_admin.create_post")
    def test_create_post_missing_title(self, mock_create):
        at = AppTest.from_function(create_dialog_app).run()

        at.text_input[0].set_value("  ") # Empty title

        at.button[0].click().run()

        mock_create.assert_not_called()
        assert at.error[0].value == en_locale["cms"]["error_title_required"]

    @patch("src.ui.cards.cms_admin.create_post")
    def test_create_post_featured_table_missing_ref(self, mock_create):
        at = AppTest.from_function(create_dialog_app).run()

        at.text_input[0].set_value("Test Title")
        at.radio[0].set_value(en_locale["cms"]["type_featured"]) # Changes the UI to show table ref
        at.run()

        # Second text input is now table_ref
        at.text_input[1].set_value("  ")

        at.button[0].click().run()

        mock_create.assert_not_called()
        assert at.error[0].value == en_locale["cms"]["error_table_ref_required"]

class TestAdminCmsSection:
    @patch("src.ui.cards.cms_admin.get_all_posts")
    def test_render_empty_posts(self, mock_get_posts):
        mock_get_posts.return_value = []
        at = AppTest.from_function(admin_section_app).run()

        # Verify the "No posts" placeholder is rendered
        html_contents = [m.value for m in at.markdown]
        assert any(en_locale["cms"]["no_posts"] in val for val in html_contents)

    @patch("src.ui.cards.cms_admin.get_all_posts")
    @patch("src.ui.cards.cms_admin._show_delete_cms_dialog")
    def test_render_with_posts_and_delete(self, mock_show_delete, mock_get_posts):
        now = datetime.now(UTC)
        mock_get_posts.return_value = [
            {
                "post_id": "1",
                "post_type": "guide",
                "title": "Live Guide",
                "body": "Body",
                "created_at": now - timedelta(days=1),
                "expires_at": now + timedelta(days=1),
            },
            {
                "post_id": "2",
                "post_type": "announcement",
                "title": "Expired Post",
                "body": "Body",
                "created_at": now - timedelta(days=5),
                "expires_at": now - timedelta(days=1),
            }
        ]

        at = AppTest.from_function(admin_section_app).run()

        html_contents = [m.value for m in at.markdown]

        # Check titles rendered
        assert any("Live Guide" in val for val in html_contents)
        assert any("Expired Post" in val for val in html_contents)

        # Check for expired styling in output (opacity 0.5)
        assert any("opacity:0.5" in val for val in html_contents)

        # Click the delete button for post_id "1"
        delete_btn = at.button("cms_admin_del_1")
        assert delete_btn is not None
        delete_btn.click().run()

        mock_show_delete.assert_called_once_with("1")

class TestCmsCreateDialogCancel:
    @patch("src.ui.cards.cms_admin.create_post")
    def test_create_post_cancel(self, mock_create):
        at = AppTest.from_function(create_dialog_app).run()

        at.text_input[0].set_value("Test Title")

        # There are two buttons: Save and Cancel. Cancel is the second one.
        cancel_btn = at.button[1]
        assert cancel_btn.label == en_locale["common"]["cancel"]

        cancel_btn.click().run()

        mock_create.assert_not_called()

    @patch("src.ui.cards.cms_admin._show_cms_create_dialog")
    def test_admin_section_new_post_button(self, mock_show_dialog):
        at = AppTest.from_function(admin_section_app).run()

        new_post_btn = at.button("cms_new_post")
        assert new_post_btn is not None

        new_post_btn.click().run()
        mock_show_dialog.assert_called_once()

    @patch("src.ui.cards.cms_admin.get_all_posts")
    def test_render_no_expiry(self, mock_get_posts):
        now = datetime.now(UTC)
        mock_get_posts.return_value = [
            {
                "post_id": "1",
                "post_type": "guide",
                "title": "Never Expires",
                "body": "Body",
                "created_at": now - timedelta(days=1),
                "expires_at": None,
            }
        ]

        at = AppTest.from_function(admin_section_app).run()
        html_contents = [m.value for m in at.markdown]

        assert any(en_locale["cms"]["no_expiry"] in val for val in html_contents)
        # Should not be rendered with opacity 0.5 (not expired)
        assert not any("opacity:0.5" in val for val in html_contents)

def delete_dialog_app():
    from src.ui.cards.cms_admin import _show_delete_cms_dialog
    _show_delete_cms_dialog("123")

class TestCmsDeleteDialog:
    @patch("src.ui.cards.cms_admin.delete_post")
    def test_delete_post_success(self, mock_delete):
        at = AppTest.from_function(delete_dialog_app).run()

        # Confirm prompt is shown
        assert at.markdown[0].value == en_locale["cms"]["confirm_delete_prompt"]

        # Click delete button
        at.button[0].click().run()

        mock_delete.assert_called_once_with("123")

    @patch("src.ui.cards.cms_admin.delete_post")
    def test_delete_post_cancel(self, mock_delete):
        at = AppTest.from_function(delete_dialog_app).run()

        # Click cancel button
        at.button[1].click().run()

        mock_delete.assert_not_called()
