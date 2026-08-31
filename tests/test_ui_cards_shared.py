from unittest.mock import patch
from src.ui.cards._shared import _dq_grade, _compute_live_completeness

def test_dq_grade():
    assert _dq_grade(95) == ("A", "dq-a")
    assert _dq_grade(80) == ("B", "dq-b")
    assert _dq_grade(65) == ("C", "dq-c")
    assert _dq_grade(30) == ("D", "dq-d")
    assert _dq_grade(0) == ("D", "dq-d")
    assert _dq_grade("invalid") == ("D", "dq-d")
    assert _dq_grade(None) == ("D", "dq-d")

def test_dq_grade_negative():
    assert _dq_grade(-10) == ("D", "dq-d")

def test_compute_live_completeness_success():
    import pandas as pd
    with patch("src.ui.cards._shared._duckdb_available", return_value=True):
        with patch("src.ui.cards._shared.run_query") as mock_run_query:
            mock_run_query.return_value = pd.DataFrame({"total": [10], "defined": [5]})
            assert _compute_live_completeness("cat.sch.tbl") == 50.0

def test_compute_live_completeness_empty():
    import pandas as pd
    with patch("src.ui.cards._shared._duckdb_available", return_value=True):
        with patch("src.ui.cards._shared.run_query") as mock_run_query:
            mock_run_query.return_value = pd.DataFrame()
            assert _compute_live_completeness("cat.sch.tbl") == 0.0

def test_compute_live_completeness_none():
    with patch("src.ui.cards._shared._duckdb_available", return_value=True):
        with patch("src.ui.cards._shared.run_query", return_value=None):
            assert _compute_live_completeness("cat.sch.tbl") == 0.0

def test_compute_live_completeness_exception():
    with patch("src.ui.cards._shared._duckdb_available", return_value=True):
        with patch("src.ui.cards._shared.run_query", side_effect=Exception("DB Error")):
            assert _compute_live_completeness("cat.sch.tbl") == 0.0

def test_compute_live_completeness_duckdb_unavailable():
    import pandas as pd
    with patch("src.ui.cards._shared._duckdb_available", return_value=False):
        with patch("src.ui.cards._shared.run_query") as mock_run_query:
            mock_run_query.return_value = pd.DataFrame({"total": [10], "defined": [8]})
            assert _compute_live_completeness("cat.sch.tbl") == 80.0

def test_compute_live_completeness_zero_total():
    import pandas as pd
    with patch("src.ui.cards._shared._duckdb_available", return_value=True):
        with patch("src.ui.cards._shared.run_query") as mock_run_query:
            mock_run_query.return_value = pd.DataFrame({"total": [0], "defined": [0]})
            assert _compute_live_completeness("cat.sch.tbl") == 0.0

def test_render_empty_state():
    from src.ui.cards._shared import _render_empty_state
    with patch("src.ui.cards._shared.st.markdown") as mock_markdown:
        _render_empty_state("🔍", "No results found")
        mock_markdown.assert_called_once()
        args, kwargs = mock_markdown.call_args
        assert "🔍" in args[0]
        assert "No results found" in args[0]
        assert kwargs.get("unsafe_allow_html") is True
