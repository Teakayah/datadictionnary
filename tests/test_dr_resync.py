from unittest.mock import MagicMock, patch
import pandas as pd
from src.sync.dr_resync import _databricks_query, _get_all_local_max_ts, _merge_into_local, run_dr_resync
import os

def test_databricks_query_missing_creds():
    with patch.dict(os.environ, {"DATABRICKS_HOST": "", "DATABRICKS_HTTP_PATH": "", "DATABRICKS_TOKEN": ""}, clear=True):
        assert _databricks_query("SELECT 1") is None

@patch("src.sync.dr_resync.os.getenv")
def test_databricks_query_with_creds(mock_getenv):
    mock_getenv.side_effect = lambda k, d="": "val" if k in ["DATABRICKS_HOST", "DATABRICKS_HTTP_PATH", "DATABRICKS_TOKEN"] else d
    with patch("databricks.sql.connect") as mock_connect:
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.fetchall_as_pandas.return_value = pd.DataFrame({"col": [1]})

        df = _databricks_query("SELECT 1")
        assert df is not None
        assert df.iloc[0]["col"] == 1
        mock_cur.execute.assert_called_once()

def test_get_all_local_max_ts():
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur

    mock_cur.fetchall.return_value = [("comments", "2023-01-01"), ("audit_log", None)]
    res = _get_all_local_max_ts(mock_conn)
    assert res == {"comments": "2023-01-01", "audit_log": None}
    mock_cur.execute.assert_called_once()

def test_merge_into_local_empty():
    mock_conn = MagicMock()
    _merge_into_local(mock_conn, "comments", pd.DataFrame())
    mock_conn.cursor.assert_not_called()

def test_merge_into_local_fallback_loop():
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    # Ensure it doesn't have _con
    del mock_cur._con
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur

    df = pd.DataFrame({"id": [1, 2], "val": ["a", "b"]})
    _merge_into_local(mock_conn, "comments", df)

    assert mock_cur.execute_write.call_count == 2

def test_merge_into_local_duckdb_native():
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_con = MagicMock()
    mock_con.register = MagicMock()
    mock_con.unregister = MagicMock()
    mock_cur._con = mock_con
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur

    df = pd.DataFrame({"id": [1, 2], "val": ["a", "b"]})
    _merge_into_local(mock_conn, "business_name_overrides", df)

    mock_con.register.assert_called_once()
    mock_con.unregister.assert_called_once()
    mock_cur.execute_write.assert_called_once()
    # Check that verb was REPLACE since it's business_name_overrides
    args, _ = mock_cur.execute_write.call_args
    assert "INSERT OR REPLACE" in args[0]

def test_run_dr_resync_success():
    mock_conn = MagicMock()
    with patch("src.sync.dr_resync._get_all_local_max_ts", return_value={"comments": "2023-01-01"}):
        with patch("src.sync.dr_resync._databricks_query") as mock_query:
            # We have 3 tables in _DR_TABLES
            mock_query.side_effect = [
                pd.DataFrame({"id": [1]}),  # comments
                pd.DataFrame(),             # audit_log (empty)
                pd.DataFrame({"id": [2]})   # business_name_overrides
            ]
            with patch("src.sync.dr_resync._merge_into_local") as mock_merge:
                res = run_dr_resync(mock_conn)
                assert res == "Up-to-date"
                assert mock_merge.call_count == 2

def test_run_dr_resync_skipped():
    mock_conn = MagicMock()
    with patch("src.sync.dr_resync._get_all_local_max_ts", return_value={}):
        with patch("src.sync.dr_resync._databricks_query", return_value=None):
            res = run_dr_resync(mock_conn)
            assert res == "Skipped (no Databricks creds)"

def test_run_dr_resync_error():
    mock_conn = MagicMock()
    with patch("src.sync.dr_resync._get_all_local_max_ts", side_effect=Exception("DB Error")):
        res = run_dr_resync(mock_conn)
        assert res == "Error: DB Error"

def test_run_dr_resync_status_setter():
    mock_conn = MagicMock()
    mock_setter = MagicMock()
    with patch("src.sync.dr_resync._get_all_local_max_ts", side_effect=Exception("DB Error")):
        res = run_dr_resync(mock_conn, status_setter=mock_setter)
        assert res == "Error: DB Error"
        # Should be called with "Checking" and then the error string
        assert mock_setter.call_count == 2
