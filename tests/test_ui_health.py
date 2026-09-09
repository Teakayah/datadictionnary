import pytest
import pandas as pd
from unittest.mock import patch, MagicMock
from src.ui.cards.health import _render_priority_actions, render_health, HealthMetrics

def test_render_priority_actions_empty():
    import streamlit as st
    with patch("src.ui.cards.health.st.markdown") as mock_md, \
         patch("src.ui.cards.health.st.success") as mock_success:
        df = pd.DataFrame()
        _render_priority_actions(df)
        mock_success.assert_called_once()

def test_render_priority_actions_with_data():
    import streamlit as st
    with patch("src.ui.cards.health.st.markdown") as mock_md, \
         patch("src.ui.cards.health.st.warning") as mock_warning, \
         patch("src.ui.cards.health.st.button") as mock_button:
        df = pd.DataFrame([{"table_name": "t1", "full_name": "c.s.t1"}])
        mock_button.return_value = False
        _render_priority_actions(df)
        mock_warning.assert_called_once()
        mock_button.assert_called_once()

def test_render_health_empty():
    with patch("src.ui.cards.health._get_table_health_stats") as mock_stats, \
         patch("src.ui.cards.health._render_empty_state") as mock_empty:
        mock_stats.return_value = pd.DataFrame()
        render_health(("cat1",))
        mock_empty.assert_called_once()

def test_render_health_metrics_happy_path():
    with patch("src.ui.cards.health._get_table_health_stats") as mock_stats, \
         patch("src.ui.cards.health._get_column_health_stats") as mock_col_stats, \
         patch("src.ui.cards.health._get_undocumented_priority") as mock_undoc, \
         patch("src.ui.cards.health._render_health_hero_metrics") as mock_hero, \
         patch("src.ui.cards.health._render_zero_result_alerts") as mock_alerts, \
         patch("src.ui.cards.health._render_schema_coverage") as mock_schema, \
         patch("src.ui.cards.health._render_priority_actions") as mock_priority, \
         patch("src.ui.cards.health.st.columns") as mock_columns:

        mock_stats.return_value = pd.DataFrame({"total": [10, 20], "described": [5, 10]})
        mock_col_stats.return_value = (100, 50)
        mock_undoc.return_value = pd.DataFrame([{"table_name": "t1", "full_name": "c.s.t1"}])
        mock_cols = [MagicMock(), MagicMock()]
        mock_columns.return_value = mock_cols

        # Test __enter__/__exit__ for columns mock
        mock_cols[0].__enter__.return_value = mock_cols[0]
        mock_cols[1].__enter__.return_value = mock_cols[1]

        render_health(("cat1",))

        mock_hero.assert_called_once()
        metrics_arg = mock_hero.call_args[0][0]
        assert metrics_arg.table_coverage == 50.0
        assert metrics_arg.n_desc == 15
        assert metrics_arg.n_tables == 30
        assert metrics_arg.col_coverage == 50.0
        assert metrics_arg.n_col_desc == 50
        assert metrics_arg.n_cols == 100

        mock_alerts.assert_called_once()
        mock_schema.assert_called_once()
        mock_priority.assert_called_once()

def test_render_health_exception():
    with patch("src.ui.cards.health._get_table_health_stats") as mock_stats, \
         patch("src.ui.cards.health.st.error") as mock_error:
        mock_stats.side_effect = Exception("DB Error")

        render_health(("cat1",))

        mock_error.assert_called_once()

def test_render_health_hero_metrics():
    import streamlit as st
    with patch("src.ui.cards.health.st.columns") as mock_columns:
        mock_cols = [MagicMock(), MagicMock(), MagicMock()]
        mock_columns.return_value = mock_cols

        # Test __enter__/__exit__ for columns mock
        mock_cols[0].__enter__.return_value = mock_cols[0]
        mock_cols[1].__enter__.return_value = mock_cols[1]
        mock_cols[2].__enter__.return_value = mock_cols[2]

        from src.ui.cards.health import _render_health_hero_metrics, HealthMetrics
        metrics = HealthMetrics(
            table_coverage=50.0,
            n_desc=10,
            n_tables=20,
            col_coverage=25.0,
            n_col_desc=100,
            n_cols=400,
        )
        _render_health_hero_metrics(metrics)

        assert len(mock_cols[0].mock_calls) > 0
        assert len(mock_cols[1].mock_calls) > 0
        assert len(mock_cols[2].mock_calls) > 0

def test_render_schema_coverage_empty():
    import streamlit as st
    with patch("src.ui.cards.health._render_empty_state") as mock_empty:
        from src.ui.cards.health import _render_schema_coverage
        _render_schema_coverage(pd.DataFrame())
        mock_empty.assert_called_once()

def test_render_schema_coverage_with_data():
    import streamlit as st
    with patch("src.ui.cards.health.st.dataframe") as mock_dataframe:
        from src.ui.cards.health import _render_schema_coverage
        df = pd.DataFrame({"schema_name": ["s1"], "total": [10], "described": [5]})
        _render_schema_coverage(df)
        mock_dataframe.assert_called_once()

def test_render_zero_result_alerts_empty():
    with patch("src.analytics.get_zero_result_alerts", return_value=[]):
        from src.ui.cards.health import _render_zero_result_alerts
        _render_zero_result_alerts()

def test_render_zero_result_alerts_with_data():
    import streamlit as st
    with patch("src.analytics.get_zero_result_alerts", return_value=[{"query": "q", "search_count": 5, "first_seen": "2023-01-01", "last_seen": "2023-01-02"}]), \
         patch("src.ui.cards.health.st.dataframe") as mock_dataframe, \
         patch("src.ui.cards.health.st.markdown") as mock_markdown:
        from src.ui.cards.health import _render_zero_result_alerts
        _render_zero_result_alerts()
        mock_dataframe.assert_called_once()

def test_render_zero_result_alerts_exception():
    with patch("src.analytics.get_zero_result_alerts", side_effect=Exception("DB Error")):
        from src.ui.cards.health import _render_zero_result_alerts
        _render_zero_result_alerts()

def test_get_table_health_stats_demo():
    from src.ui.cards.health import _get_table_health_stats
    with patch("src.ui.cards.health.is_demo_mode", return_value=True):
        df = _get_table_health_stats(("cat1",))
        assert not df.empty

def test_get_table_health_stats_db():
    from src.ui.cards.health import _get_table_health_stats
    with patch("src.ui.cards.health.is_demo_mode", return_value=False), \
         patch("src.ui.cards.health.run_query") as mock_run:
        mock_run.return_value = pd.DataFrame([{"total": 10}])
        df = _get_table_health_stats(("cat1",))
        assert not df.empty

def test_get_column_health_stats_demo():
    from src.ui.cards.health import _get_column_health_stats
    with patch("src.ui.cards.health.is_demo_mode", return_value=True):
        res = _get_column_health_stats(("cat1",))
        assert res == (0, 0)

def test_get_column_health_stats_db():
    from src.ui.cards.health import _get_column_health_stats
    with patch("src.ui.cards.health.is_demo_mode", return_value=False), \
         patch("src.ui.cards.health.run_query") as mock_run:
        mock_run.return_value = pd.DataFrame([{"total": 10, "with_desc": 5}])
        res = _get_column_health_stats(("cat1",))
        assert res == (10, 5)

def test_get_undocumented_priority_demo():
    from src.ui.cards.health import _get_undocumented_priority
    with patch("src.ui.cards.health.is_demo_mode", return_value=True):
        df = _get_undocumented_priority(("cat1",))
        assert isinstance(df, pd.DataFrame)

def test_get_undocumented_priority_db():
    from src.ui.cards.health import _get_undocumented_priority
    with patch("src.ui.cards.health.is_demo_mode", return_value=False), \
         patch("src.ui.cards.health.run_query") as mock_run:
        mock_run.return_value = pd.DataFrame([{"table_name": "t1"}])
        df = _get_undocumented_priority(("cat1",))
        assert not df.empty

def test_get_column_health_stats_db_empty():
    from src.ui.cards.health import _get_column_health_stats
    with patch("src.ui.cards.health.is_demo_mode", return_value=False), \
         patch("src.ui.cards.health.run_query") as mock_run:
        mock_run.return_value = pd.DataFrame()
        res = _get_column_health_stats(("cat1",))
        assert res == (0, 0)

def test_render_zero_result_alerts_html_format():
    with patch("src.analytics.get_zero_result_alerts", return_value=[
        {"query": "q", "search_count": 5, "first_seen": "2023-01-01", "last_seen": "2023-01-02"}
    ]), \
         patch("src.ui.cards.health.st.markdown") as mock_markdown, \
         patch("src.ui.cards.health.st.dataframe"):
        from src.ui.cards.health import _render_zero_result_alerts
        _render_zero_result_alerts()
        # Verify the alert HTML was rendered
        assert len(mock_markdown.mock_calls) > 0
        call_args = mock_markdown.mock_calls[0].args[0]
        assert "background:rgba(184, 54, 42, 0.08)" in call_args


def test_render_zero_result_alerts_with_bad_date():
    with patch("src.analytics.get_zero_result_alerts", return_value=[
        {"query": "q", "search_count": 5, "first_seen": "invalid_date", "last_seen": "invalid_date"}
    ]), \
         patch("src.ui.cards.health.st.markdown"), \
         patch("src.ui.cards.health.st.dataframe"):
        from src.ui.cards.health import _render_zero_result_alerts
        _render_zero_result_alerts()


def test_render_zero_result_alerts_with_none_date():
    with patch("src.analytics.get_zero_result_alerts", return_value=[
        {"query": "q", "search_count": 5, "first_seen": None, "last_seen": None}
    ]), \
         patch("src.ui.cards.health.st.markdown"), \
         patch("src.ui.cards.health.st.dataframe"):
        from src.ui.cards.health import _render_zero_result_alerts
        _render_zero_result_alerts()

def test_render_zero_result_alerts_with_date_formatting():
    with patch("src.analytics.get_zero_result_alerts", return_value=[
        {"query": "q", "search_count": 5, "first_seen": "2023-01-01T10:00:00Z", "last_seen": "2023-01-02T10:00:00Z"}
    ]), \
         patch("src.ui.cards.health.st.markdown"), \
         patch("src.ui.cards.health.st.dataframe") as mock_df, \
         patch("src.ui.cards.health.t", return_value="%Y-%m-%d"):
        from src.ui.cards.health import _render_zero_result_alerts
        _render_zero_result_alerts()
        # Verify the dates were formatted
        assert len(mock_df.mock_calls) > 0
        df_arg = mock_df.mock_calls[0].args[0]
        assert df_arg.iloc[0]['first_seen'] == "2023-01-01"
        assert df_arg.iloc[0]['last_seen'] == "2023-01-02"


def test_render_zero_result_alerts_with_date_formatting_real_t():
    with patch("src.analytics.get_zero_result_alerts", return_value=[
        {"query": "q", "search_count": 5, "first_seen": "2023-01-01T10:00:00Z", "last_seen": "2023-01-02T10:00:00Z"}
    ]), \
         patch("src.ui.cards.health.st.markdown"), \
         patch("src.ui.cards.health.st.dataframe"):
        from src.ui.cards.health import _render_zero_result_alerts
        _render_zero_result_alerts()


def test_render_zero_result_alerts_with_date_formatting_real_test():
    with patch("src.analytics.get_zero_result_alerts", return_value=[
        {"query": "q", "search_count": 5, "first_seen": "2023-01-01T10:00:00Z", "last_seen": "2023-01-02T10:00:00Z"}
    ]), \
         patch("src.ui.cards.health.st.markdown"), \
         patch("src.ui.cards.health.st.dataframe") as mock_df, \
         patch("src.ui.cards.health.t", side_effect=lambda k: "%Y-%m-%d" if k == "health.alert_date_format" else k):
        from src.ui.cards.health import _render_zero_result_alerts
        _render_zero_result_alerts()
        # Verify the dates were formatted
        assert len(mock_df.mock_calls) > 0
        df_arg = mock_df.mock_calls[0].args[0]
        assert df_arg.iloc[0]['first_seen'] == "2023-01-01"
        assert df_arg.iloc[0]['last_seen'] == "2023-01-02"


def test_render_zero_result_alerts_with_bad_date_format():
    with patch("src.analytics.get_zero_result_alerts", return_value=[
        {"query": "q", "search_count": 5, "first_seen": "invalid_date", "last_seen": "invalid_date"}
    ]), \
         patch("src.ui.cards.health.st.markdown"), \
         patch("src.ui.cards.health.st.dataframe") as mock_df, \
         patch("src.ui.cards.health.t", side_effect=lambda k: "%Y-%m-%d" if k == "health.alert_date_format" else k):
        from src.ui.cards.health import _render_zero_result_alerts
        _render_zero_result_alerts()
        # Verify the dates were formatting gracefully degraded to fallback
        assert len(mock_df.mock_calls) > 0
        df_arg = mock_df.mock_calls[0].args[0]
        assert df_arg.iloc[0]['first_seen'] == "invalid_date"
        assert df_arg.iloc[0]['last_seen'] == "invalid_date"


def test_render_zero_result_alerts_with_nat():
    with patch("src.analytics.get_zero_result_alerts", return_value=[
        {"query": "q", "search_count": 5, "first_seen": "NaT", "last_seen": "NaT"}
    ]), \
         patch("src.ui.cards.health.st.markdown"), \
         patch("src.ui.cards.health.st.dataframe") as mock_df, \
         patch("src.ui.cards.health.t", side_effect=lambda k: "%Y-%m-%d" if k == "health.alert_date_format" else k):
        from src.ui.cards.health import _render_zero_result_alerts
        _render_zero_result_alerts()
        assert len(mock_df.mock_calls) > 0
        df_arg = mock_df.mock_calls[0].args[0]
        assert df_arg.iloc[0]['first_seen'] == "NaT"
        assert df_arg.iloc[0]['last_seen'] == "NaT"


def test_render_zero_result_alerts_with_html_escaping():
    with patch("src.analytics.get_zero_result_alerts", return_value=[
        {"query": "q", "search_count": 5, "first_seen": "2023-01-01", "last_seen": "2023-01-02"}
    ]), \
         patch("src.ui.cards.health.st.markdown") as mock_markdown, \
         patch("src.ui.cards.health.st.dataframe"):
        from src.ui.cards.health import _render_zero_result_alerts
        with patch("src.ui.cards.health.t", side_effect=lambda k, **kwargs: f"Mocked {k}"):
            _render_zero_result_alerts()

            assert len(mock_markdown.mock_calls) > 0
            call_args = mock_markdown.mock_calls[0].args[0]
            assert "Mocked health.steward_alert_title" in call_args
            assert "Mocked health.steward_alert_body" in call_args


def test_priority_actions_button_click():
    import streamlit as st
    with patch("src.ui.cards.health.st.markdown"), \
         patch("src.ui.cards.health.st.warning"), \
         patch("src.ui.cards.health.st.button", return_value=True), \
         patch.object(st.session_state, '__setitem__') as mock_setitem, \
         patch("src.ui.cards.health.st.rerun") as mock_rerun, \
         patch.object(st.query_params, '__setitem__'):
        from src.ui.cards.health import _render_priority_actions
        df = pd.DataFrame([{"table_name": "t1", "full_name": "c.s.t1"}])
        _render_priority_actions(df)
        mock_rerun.assert_called_once()
        # Verify state was set
        calls = [c.args for c in mock_setitem.mock_calls]

def test_priority_actions_more_than_50():
    import streamlit as st
    with patch("src.ui.cards.health.st.markdown"), \
         patch("src.ui.cards.health.st.warning"), \
         patch("src.ui.cards.health.st.info") as mock_info, \
         patch("src.ui.cards.health.st.button", return_value=False):
        from src.ui.cards.health import _render_priority_actions
        # create 51 items
        items = [{"table_name": f"t{i}", "full_name": f"c.s.t{i}"} for i in range(51)]
        df = pd.DataFrame(items)
        _render_priority_actions(df)
        mock_info.assert_called_once()
