import pandas as pd
from unittest.mock import MagicMock
from src.ui.lineage import _build_lineage_graph, _lineage_vis_html
from streamlit.testing.v1 import AppTest

def test_build_lineage_graph_empty_result():
    mock_run_query = MagicMock(return_value=pd.DataFrame())
    nodes, links = _build_lineage_graph("db.schema.tbl1", "tbl1", ["group1"], mock_run_query, max_depth=1)

    assert len(nodes) == 1
    assert nodes[0]["id"] == "db.schema.tbl1"
    assert nodes[0]["current"] is True
    assert len(links) == 0

def test_build_lineage_graph_with_results():
    data = {
        "table_full_name": ["db.schema.tbl1", "db.schema.tbl1", "db.schema.tbl3"],
        "entity_full_name": ["db.schema.tbl2", "db.schema.tbl3", "db.schema.tbl4"],
        "direction": ["UPSTREAM", "DOWNSTREAM", "DOWNSTREAM"],
        "entity_type": ["TABLE", "TABLE", "TABLE"],
        "depth": [1, 1, 2]
    }
    df = pd.DataFrame(data)
    mock_run_query = MagicMock(return_value=df)

    nodes, links = _build_lineage_graph("db.schema.tbl1", "tbl1", ["group1"], mock_run_query, max_depth=2)

    assert len(nodes) == 4

    node_ids = [n["id"] for n in nodes]
    assert "db.schema.tbl1" in node_ids
    assert "db.schema.tbl2" in node_ids
    assert "db.schema.tbl3" in node_ids
    assert "db.schema.tbl4" in node_ids

    assert {"from": "db.schema.tbl2", "to": "db.schema.tbl1"} in links
    assert {"from": "db.schema.tbl1", "to": "db.schema.tbl3"} in links
    assert {"from": "db.schema.tbl3", "to": "db.schema.tbl4"} in links

def test_build_lineage_graph_with_node_fn_not_in_visited():
    data = {
        "table_full_name": ["db.schema.tbl5"],
        "entity_full_name": ["db.schema.tbl1"], # tbl1 is visited, tbl5 is not
        "direction": ["UPSTREAM"],
        "entity_type": ["TABLE"],
        "depth": [1]
    }
    df = pd.DataFrame(data)
    mock_run_query = MagicMock(return_value=df)

    nodes, links = _build_lineage_graph("db.schema.tbl1", "tbl1", ["group1"], mock_run_query, max_depth=2)

    node_ids = [n["id"] for n in nodes]
    assert "db.schema.tbl5" in node_ids
    assert "db.schema.tbl1" in node_ids

def test_lineage_vis_html():
    nodes = [{"id": "n1", "label": "n1", "current": True, "relationship": "Current"}]
    edges = []

    html = _lineage_vis_html(nodes, edges, height=500, container_id="test_container")
    assert "test_container" in html
    assert "500px" in html
    assert "vis.DataSet" in html
    assert "net.getScale()" in html
    assert "doubleClick" in html
    assert "LINNAV-" in html
    assert "avoidOverlap" in html

def test_render_lineage_fullscreen_apptest():
    def app():
        import streamlit as st
        from src.ui.lineage import render_lineage_fullscreen
        if st.button("Show"):
            render_lineage_fullscreen([{"id": "n1", "label": "n1", "current": True, "relationship": "Current"}], [], "db.schema.tbl1")

    at = AppTest.from_function(app).run()
    at.button[0].click().run()

    assert len(at.markdown) > 0
    found = False
    for m in at.markdown:
        if "db.schema.tbl1" in m.value:
            found = True
            break
    assert found


def test_lineage_v2_component_js_and_render():
    from src.ui.lineage import _LINEAGE_V2_JS, render_lineage_graph

    assert "setTriggerValue" in _LINEAGE_V2_JS
    assert "doubleClick" in _LINEAGE_V2_JS
    assert "avoidOverlap" in _LINEAGE_V2_JS

    def app():
        from src.ui.lineage import render_lineage_graph as _render
        _render(
            [
                {"id": "db.s.a", "label": "a", "current": True, "relationship": "Current"},
                {"id": "db.s.b", "label": "b", "current": False, "relationship": "Same schema"},
            ],
            [{"from": "db.s.a", "to": "db.s.b"}],
            height=350,
            key="test_lin_v2",
        )

    at = AppTest.from_function(app).run()
    assert not at.exception


def test_trigger_lineage_navigation_sets_state_and_reruns():
    from unittest.mock import patch
    from src.ui.lineage import _trigger_lineage_navigation
    import streamlit as st

    class _RerunExc(Exception):
        pass

    with patch.object(st, "rerun", side_effect=_RerunExc):
        # Ignoring None or same table does not rerun
        _trigger_lineage_navigation(None, "db.s.a")
        _trigger_lineage_navigation("db.s.a", "db.s.a")

        st.session_state.pop("dd_search_override", None)
        st.session_state.pop("dd_nav_select", None)
        try:
            _trigger_lineage_navigation("db.s.target_tbl", "db.s.a")
            assert False, "Expected st.rerun()"
        except _RerunExc:
            pass
        assert st.session_state.get("dd_search_override") == "target_tbl"
        assert st.session_state.get("dd_nav_select") == "db.s.target_tbl"
