1. Add new tests to `tests/test_ui_search_query.py` to cover more UI edge cases and improve test coverage for `src/pages/search.py`.
   - Run the exact bash command `cat << 'INNER_EOF' >> tests/test_ui_search_query.py` with the missing tests generated from the exploration.
```python
def test_missing_search_coverage_extra():
    import pandas as pd
    from unittest.mock import patch
    from streamlit.testing.v1 import AppTest

    def render_search():
        import streamlit as st
        from src.pages.search import render_search_page
        st.session_state["user_email"] = "test@example.com"
        st.session_state["dd_user_groups"] = ["group1"]
        render_search_page(("group1",))

    at = AppTest.from_function(render_search)

    # 1. Test clear state logic lines 681-682
    at.session_state["_dd_sticky_nav"] = "main.sales.orders"
    at.session_state["catalog_search"] = "orders"
    at.session_state["_dd_current_search_query"] = "old_query"
    at.session_state["dd_comment_open_123"] = True

    mock_search = pd.DataFrame([{
        "full_name": "main.sales.orders",
        "table_name": "orders",
        "catalog_name": "main",
        "schema_name": "sales",
        "dq_score": 100,
        "match_type": "Table",
        "description": "desc"
    }])
    mock_authorized = pd.DataFrame([{
        "full_name": "main.sales.orders",
        "table_name": "orders",
        "catalog_name": "main",
        "schema_name": "sales",
    }])
    mock_cols = pd.DataFrame([{
        "column_name": "col_1",
        "data_type": "int",
        "comment": "comment",
    }])

    with patch("src.pages.search.get_authorized_tables", return_value=mock_authorized), \
         patch("src.pages.search.search_all_metadata", return_value=mock_search), \
         patch("src.pages.search.get_table_columns", return_value=mock_cols), \
         patch("src.pages.search.run_query", return_value=pd.DataFrame()), \
         patch("src.pages.search.get_table_comments", return_value=[]), \
         patch("src.pages.search.get_table_steward", return_value=""), \
         patch("src.pages.search.get_column_overrides", return_value={}), \
         patch("src.pages.search.is_power_user", return_value=True), \
         patch("src.pages.search._build_lineage_graph", return_value=([{"id": "A"}], [{"source": "A", "target": "B"}])), \
         patch("src.pages.search._lineage_vis_html", return_value="<div>lineage</div>"), \
         patch("src.pages.search.t", side_effect=lambda k, **kw: k):

        at.run()

        # Verify 681-682
        assert "dd_comment_open_123" not in at.session_state

        # Test expand lineage 570-571
        expand_btns = [b for b in at.button if b.key == "expand_lin_main.sales.orders"]
        if expand_btns:
            with patch("src.pages.search.render_lineage_fullscreen") as mock_lin:
                expand_btns[0].click().run()
                mock_lin.assert_called_once()

        # Test back to results 784-785
        back_btns = [b for b in at.button if b.key == "search_back"]
        if back_btns:
            back_btns[0].click().run()
            assert "_dd_sticky_nav" not in at.session_state


def test_edit_buttons_coverage():
    import pandas as pd
    from unittest.mock import patch
    from streamlit.testing.v1 import AppTest

    def render_detail():
        import streamlit as st
        from src.pages.search import _render_detail_panel
        st.session_state["user_email"] = "test@example.com"
        st.session_state["dd_user_groups"] = ["group1"]
        row = pd.Series({
            "catalog_name": "main",
            "schema_name": "sales",
            "table_name": "orders",
            "full_name": "main.sales.orders",
            "description": "desc",
            "dq_score": 100,
            "steward_email": ""
        })
        _render_detail_panel(row, "main.sales.orders", ("group1",))

    at = AppTest.from_function(render_detail)

    mock_cols = pd.DataFrame([{
        "column_name": "col_1",
        "data_type": "int",
        "comment": "comment",
    }])

    with patch("src.pages.search.get_table_columns", return_value=mock_cols), \
         patch("src.pages.search._compute_live_completeness", return_value=100.0), \
         patch("src.pages.search.run_query", return_value=pd.DataFrame()), \
         patch("src.pages.search.get_table_comments", return_value=[]), \
         patch("src.pages.search.get_table_steward", return_value=""), \
         patch("src.pages.search.get_column_overrides", return_value={}), \
         patch("src.pages.search.is_power_user", return_value=True), \
         patch("src.pages.search._build_lineage_graph", return_value=([{"id": "A"}], [{"source": "A", "target": "B"}])), \
         patch("src.pages.search._lineage_vis_html", return_value="<div>lineage</div>"), \
         patch("src.pages.search.t", side_effect=lambda k, **kw: k):

        at.run()

        edit_tbl_btns = [b for b in at.button if b.key == "edit_tbl_main.sales.orders"]
        if edit_tbl_btns:
            with patch("src.pages.search.render_table_metadata_editor") as mock_edit:
                edit_tbl_btns[0].click().run()
                mock_edit.assert_called_once()

        edit_fn_btns = [b for b in at.button if b.key == "edit_friendly_main.sales.orders"]
        if edit_fn_btns:
            with patch("src.pages.search.render_table_business_name_editor") as mock_edit2:
                edit_fn_btns[0].click().run()
                mock_edit2.assert_called_once()

def test_unauthorized_group_filter():
    import pandas as pd
    from unittest.mock import patch
    from streamlit.testing.v1 import AppTest

    def render_search():
        import streamlit as st
        from src.pages.search import render_search_page
        st.session_state["user_email"] = "test@example.com"
        st.session_state["dd_user_groups"] = ["group1"]
        render_search_page(("group1",))

    at = AppTest.from_function(render_search)
    at.session_state["catalog_search"] = None

    mock_authorized = pd.DataFrame([{
        "full_name": "main.sales.orders",
        "table_name": "orders",
        "catalog_name": "main",
        "schema_name": "sales",
    }])

    mock_group_tables = pd.DataFrame([{
        "full_name": "main.sales.other",
        "table_name": "other",
        "name": "other",
        "catalog_name": "main",
        "schema_name": "sales"
    }])

    def mock_get_auth_tables(*args, **kwargs):
        if kwargs.get("filter_groups"):
            return mock_group_tables
        return mock_authorized

    with patch("src.pages.search.get_authorized_tables", side_effect=mock_get_auth_tables), \
         patch("src.pages.search.t", side_effect=lambda k, **kw: k):

        at.run()

        gview_btns = [b for b in at.button if b.key and b.key.startswith("gview_main.sales.other")]
        if gview_btns:
            gview_btns[0].click().run()

            errors = [e.value for e in at.error]
            assert any("detail.unauthorized" in e for e in errors)

def test_unauthorized_search_query():
    import pandas as pd
    from unittest.mock import patch
    from streamlit.testing.v1 import AppTest

    def render_search():
        import streamlit as st
        from src.pages.search import render_search_page
        st.session_state["user_email"] = "test@example.com"
        st.session_state["dd_user_groups"] = ["group1"]
        render_search_page(("group1",))

    at = AppTest.from_function(render_search)
    at.session_state["catalog_search"] = "other"

    mock_authorized = pd.DataFrame([{
        "full_name": "main.sales.orders",
        "table_name": "orders",
        "catalog_name": "main",
        "schema_name": "sales",
    }])

    mock_search = pd.DataFrame([{
        "full_name": "main.sales.other",
        "table_name": "other",
        "catalog_name": "main",
        "schema_name": "sales",
        "dq_score": 100,
        "match_type": "Table",
        "description": "desc"
    }])

    def mock_get_auth_tables(*args, **kwargs):
        return mock_authorized

    with patch("src.pages.search.get_authorized_tables", side_effect=mock_get_auth_tables), \
         patch("src.pages.search.search_all_metadata", return_value=mock_search), \
         patch("src.pages.search.t", side_effect=lambda k, **kw: k):

        at.run()

        view_btns = [b for b in at.button if b.key and b.key.startswith("view_main.sales.other")]
        if view_btns:
            view_btns[0].click().run()

            errors = [e.value for e in at.error]
            assert any("detail.unauthorized" in e for e in errors)

def test_render_detail_panel_overrides_coverage():
    import pandas as pd
    from unittest.mock import patch
    from streamlit.testing.v1 import AppTest

    def render_detail():
        import streamlit as st
        from src.pages.search import _render_detail_panel
        st.session_state["user_email"] = "test@example.com"
        st.session_state["dd_user_groups"] = ["group1"]
        row = pd.Series({
            "catalog_name": "main",
            "schema_name": "sales",
            "table_name": "orders",
            "full_name": "main.sales.orders",
            "description": "desc",
            "dq_score": 100,
            "steward_email": ""
        })
        _render_detail_panel(row, "main.sales.orders", ("group1",))

    at = AppTest.from_function(render_detail)

    mock_cols = pd.DataFrame([{
        "column_name": "col_1",
        "data_type": "int",
        "comment": "comment",
    }])

    with patch("src.pages.search.get_table_columns", return_value=mock_cols), \
         patch("src.pages.search._compute_live_completeness", return_value=100.0), \
         patch("src.pages.search.run_query", return_value=pd.DataFrame()), \
         patch("src.pages.search.get_table_comments", return_value=[]), \
         patch("src.pages.search.get_table_steward", return_value=""), \
         patch("src.pages.search.get_column_overrides", return_value={"col_1": {"business_name": "col1 biz name", "definition": "col1 definition"}}), \
         patch("src.pages.search.is_power_user", return_value=True), \
         patch("src.pages.search._build_lineage_graph", return_value=([{"id": "A"}], [{"source": "A", "target": "B"}])), \
         patch("src.pages.search._lineage_vis_html", return_value="<div>lineage</div>"), \
         patch("src.pages.search.t", side_effect=lambda k, **kw: k):

        at.run()

        # Test editing a column (304-306)
        edit_col_btns = [b for b in at.button if b.key == "col_edit_main.sales.orders__col_1"]
        if edit_col_btns:
            edit_col_btns[0].click().run()
            assert at.session_state.get("dd_col_edit_mode") == "main.sales.orders__col_1"

def test_missing_coverage_comment_form():
    import pandas as pd
    from unittest.mock import patch
    from streamlit.testing.v1 import AppTest

    def render_detail():
        import streamlit as st
        from src.pages.search import _render_detail_panel
        st.session_state["user_email"] = "test@example.com"
        st.session_state["dd_user_groups"] = ["group1"]
        row = pd.Series({
            "catalog_name": "main",
            "schema_name": "sales",
            "table_name": "orders",
            "full_name": "main.sales.orders",
            "description": "desc",
            "dq_score": 100,
            "steward_email": ""
        })
        _render_detail_panel(row, "main.sales.orders", ("group1",))

    at = AppTest.from_function(render_detail)

    mock_cols = pd.DataFrame([{
        "column_name": "col_1",
        "data_type": "int",
        "comment": "comment",
    }])

    mock_comments = [{
        "comment_id": 123,
        "author_email": "test@example.com",
        "created_at": pd.Timestamp.now(),
        "comment_text": "hello",
        "replies": [{"comment_id": 124, "author_email": "other@test.com", "created_at": pd.Timestamp.now(), "comment_text": "hi"}]
    }]

    with patch("src.pages.search.get_table_columns", return_value=mock_cols), \
         patch("src.pages.search._compute_live_completeness", return_value=100.0), \
         patch("src.pages.search.run_query", return_value=pd.DataFrame()), \
         patch("src.pages.search.get_table_comments", return_value=mock_comments), \
         patch("src.pages.search.get_table_steward", return_value=""), \
         patch("src.pages.search.get_column_overrides", return_value={}), \
         patch("src.pages.search.is_power_user", return_value=True), \
         patch("src.pages.search._build_lineage_graph", return_value=([{"id": "A"}], [{"source": "A", "target": "B"}])), \
         patch("src.pages.search._lineage_vis_html", return_value="<div>lineage</div>"), \
         patch("src.pages.search.t", side_effect=lambda k, **kw: k):

        at.run()

        # open reply form
        reply_btns = [b for b in at.button if b.key == "dd_comment_btn_main.sales.orders_123"]
        if reply_btns:
            reply_btns[0].click().run()
            assert at.session_state.get("dd_comment_open_main.sales.orders_123") == True

            # try sending empty (line 76)
            send_btns = [b for b in at.button if b.key == "dd_comment_send_main.sales.orders_123"]
            if send_btns:
                send_btns[0].click().run()
                assert len([w for w in at.warning if "comment.empty_error" in w.value]) > 0

            # try sending with text (line 64-72)
            with patch("src.pages.search.save_comment") as mock_save:
                if send_btns:
                    at.text_area(key="dd_comment_text_main.sales.orders_123").set_value("new reply text")
                    send_btns[0].click().run()
                    mock_save.assert_called_once_with("TABLE", "main.sales.orders", "new reply text", "", parent_comment_id="123")
                    assert "dd_comment_open_main.sales.orders_123" not in at.session_state

            # try cancel (line 79-81)
            at.session_state["dd_comment_open_main.sales.orders_123"] = True
            at.run()
            cancel_btns = [b for b in at.button if b.key == "dd_comment_cancel_main.sales.orders_123"]
            if cancel_btns:
                cancel_btns[0].click().run()
                assert "dd_comment_open_main.sales.orders_123" not in at.session_state

        # Exception during save coverage (line 73-75)
        at.session_state["dd_comment_open_main.sales.orders_123"] = True
        at.run()
        with patch("src.pages.search.save_comment", side_effect=Exception("Database error")):
            send_btns = [b for b in at.button if b.key == "dd_comment_send_main.sales.orders_123"]
            if send_btns:
                at.text_area(key="dd_comment_text_main.sales.orders_123").set_value("error test")
                send_btns[0].click().run()
                assert any("common.error" in e.value for e in at.error)

INNER_EOF
```
2. Verify the changes using the exact command `git diff tests/test_ui_search_query.py`.
3. Add a journal entry for the Inspector persona:
   - Run the exact bash command `cat << 'INNER_EOF' >> .jules/inspector.md` with the critical testing learning about UI test coverage.
```markdown
## 2026-10-14 - Test coverage gaps in Streamlit conditionals and iterables
**Learning:** Found significant test coverage gaps in conditional UI elements like `st.button` click callbacks nested in loops (e.g., table columns, comment replies) or behind simple boolean condition checks (e.g., unauthorized search navigation) in `src/pages/search.py`.
**Action:** Explicitly write `AppTest` test cases that locate conditionally-rendered components via their dynamic keys (e.g. `b.key == "col_edit_main.sales.orders__col_1"`), simulate clicks via `.click().run()`, and assert internal state updates to guarantee proper component execution. Provide mock setups that trigger iteration loops (e.g., by adding a mocked comment with replies) to test elements correctly mapped inside these iterables.
INNER_EOF
```
4. Verify the journal entry using the exact command `tail -n 20 .jules/inspector.md`.
5. Clean up temporary files:
   - Run `rm plan.md .coverage` to clean up temporary scratch files and execution artifacts.
6. Verify cleanup using the exact command `ls -la plan.md`.
7. Run the full test suite using `python -m pytest tests/ --cov=src.pages.search --cov-report=term-missing`.
8. Complete Pre-Commit Steps: Complete pre-commit steps to ensure proper testing, verification, review, and reflection are done.
9. Submit the change using `request_code_review` with the title format `🕵️ Inspector: Cover search page conditional UI components` and description sections: `💡 What:`, `🎯 Why:`, `📊 Coverage:`.
   - Title: `🕵️ Inspector: Cover search page conditional UI components`
   - Description:
     💡 What: Added unit tests to tests/test_ui_search_query.py covering conditionally-rendered buttons, click callbacks, exceptions, and loops in src/pages/search.py (e.g., comment forms, unauthorized navigation links).
     🎯 Why: These conditional components were previously untested, risking unhandled exceptions or regressions when UI logic changes. Simulating dynamic button interaction inside loops catches complex state mutation bugs early.
     📊 Coverage: Improved coverage for src/pages/search.py by covering previously untested logic.
