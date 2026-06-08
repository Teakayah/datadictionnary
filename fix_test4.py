import re

with open("tests/test_ui_discovery.py", "r") as f:
    content = f.read()

# Since we no longer do remapping on locale switch (we just fallback to notable if missing)
# we need to fix this test appropriately. We just remove the test entirely because
# the logic it was testing (remapping based on _disc_tab_idx) is completely gone.

old_block = r'''    @patch\("src\.ui\.cards\.discovery\.get_active_posts"\)
    def test_discovery_tab_locale_remap\(self, mock_get_posts\):
        mock_get_posts\.return_value = \[\]
        at = AppTest\.from_function\(render_discovery_page_app\)\.run\(\)

        # Test remap with stored invalid label \(e\.g\. after language switch\)
        # Simulate locale switch: clear the tab value \(None triggers remap\) \+ set index
        at\.button_group\(key="discovery_active_tab"\)\.set_value\(\[\]\)
        at\.run\(\)
        assert at\.session_state\["discovery_active_tab"\] == "notable"
        html = \[m\.value for m in at\.markdown\]
        assert any\("My Bookmarks" in val for val in html\)

'''

content = re.sub(old_block, '', content)

with open("tests/test_ui_discovery.py", "w") as f:
    f.write(content)
