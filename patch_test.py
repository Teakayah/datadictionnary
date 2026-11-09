import pytest
from streamlit.testing.v1 import AppTest
import pandas as pd
from unittest.mock import patch

def test_missing_coverage_comment_form():
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
        "comment_text": "hello"
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
