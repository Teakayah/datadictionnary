import pytest
import duckdb
from unittest.mock import patch, MagicMock
from src.db.duckdb_adapter import _DuckDBConn, _DuckDBCursor

def test_executemany_duckdb_invalid_input_exception():
    con_mock = MagicMock()
    con_mock.executemany.side_effect = duckdb.InvalidInputException('executemany requires a non-empty list of parameter sets to be provided')
    cursor = _DuckDBCursor(con_mock)
    with pytest.raises(duckdb.InvalidInputException):
        cursor.executemany("SELECT * FROM t WHERE c = %(p)s", [])

def test_executemany_duckdb_invalid_input_exception_no_pyformat():
    con_mock = MagicMock()
    con_mock.executemany.side_effect = duckdb.InvalidInputException('executemany requires a non-empty list of parameter sets to be provided')
    cursor = _DuckDBCursor(con_mock)
    with pytest.raises(duckdb.InvalidInputException):
        cursor.executemany("SELECT * FROM t WHERE c = ?", [])


def test_duckdb_adapter_executemany_valid_dict_conversion():
    con_mock = MagicMock()
    cursor = _DuckDBCursor(con_mock)

    sql = "INSERT INTO test (a, b) VALUES (%(a)s, %(b)s)"
    params = [{"a": 1, "b": 2}, {"a": 3, "b": 4}]

    cursor.executemany(sql, params)

    expected_sql = "INSERT INTO test (a, b) VALUES ($a, $b)"
    expected_params = [{"a": 1, "b": 2}, {"a": 3, "b": 4}]
    con_mock.executemany.assert_called_once_with(expected_sql, expected_params)

def test_duckdb_adapter_executemany_no_con():
    cursor = _DuckDBCursor(None)

    sql = "INSERT INTO test (a) VALUES (?)"
    params = [[1], [2]]
    cursor.executemany(sql, params)
    assert cursor._rel is None

def test_duckdb_adapter_executemany_no_params():
    con_mock = MagicMock()
    cursor = _DuckDBCursor(con_mock)

    sql = "INSERT INTO test (a) VALUES (1)"
    cursor.executemany(sql)
    con_mock.executemany.assert_called_once_with(sql)

def test_duckdb_adapter_executemany_non_dict_params():
    con_mock = MagicMock()
    cursor = _DuckDBCursor(con_mock)

    sql = "INSERT INTO test (a) VALUES (?)"
    params = [[1], [2]]
    cursor.executemany(sql, params)
    con_mock.executemany.assert_called_once_with(sql, params)

def test_duckdb_adapter_executemany_invalid_input_exception():
    con_mock = MagicMock()
    cursor = _DuckDBCursor(con_mock)

    sql = "INSERT INTO test (a, b) VALUES (?, ?)"
    params = []

    con_mock.executemany.side_effect = duckdb.InvalidInputException("executemany requires a non-empty list of parameter sets to be provided")

    with pytest.raises(duckdb.InvalidInputException):
        cursor.executemany(sql, params)

def test_duckdb_adapter_executemany_write():
    con_mock = MagicMock()
    cursor = _DuckDBCursor(con_mock)

    sql = "INSERT INTO test (a) VALUES (1)"
    cursor.executemany_write(sql)
    con_mock.executemany.assert_called_once_with(sql)

@patch("src.db.duckdb_adapter._get_shared_duckdb_connection")
@patch("src.db.duckdb_adapter._ensure_user_data_attached")
def test_ensure_user_data_attached_helper(mock_ensure_attached, mock_get_conn):
    con_mock = MagicMock()
    mock_get_conn.return_value = con_mock

    with patch("src.db.duckdb_adapter.USER_DATA_PATH", "dummy_path"):
        conn = _DuckDBConn("dummy_path")
        conn._ensure_user_data_attached()
        mock_ensure_attached.assert_called_once_with(con_mock, "dummy_path", read_only=conn._read_only)

@patch("src.db.duckdb_adapter._get_shared_duckdb_connection")
@patch("src.db.duckdb_adapter._ensure_user_data_attached")
def test_ensure_user_data_attached_helper_no_con(mock_ensure_attached, mock_get_conn):
    mock_get_conn.return_value = None

    conn = _DuckDBConn("dummy_path")
    conn._ensure_user_data_attached()
    mock_ensure_attached.assert_not_called()

def test_duckdb_conn_execute():
    with patch("src.db.duckdb_adapter._DuckDBCursor") as mock_cursor_class:
        mock_cursor = MagicMock()
        mock_cursor_class.return_value = mock_cursor

        conn = _DuckDBConn("dummy_path")
        res = conn.execute("SELECT 1", {"a": 1})

        mock_cursor.execute.assert_called_once_with("SELECT 1", {"a": 1})
        assert res == mock_cursor


def test_run_duckdb_query():
    with patch("src.db.duckdb_adapter._DuckDBConn") as mock_conn_class:
        mock_conn = MagicMock()
        mock_conn_class.return_value = mock_conn

        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchall_as_pandas.return_value = "pandas_df"

        from src.db.duckdb_adapter import _run_duckdb_query
        res = _run_duckdb_query("SELECT 1")

        mock_cursor.execute.assert_called_once_with("SELECT 1", None)
        assert res == "pandas_df"

def test_duckdb_conn_context_manager():
    conn = _DuckDBConn("dummy_path")
    with conn as c:
        assert c is conn

@patch("src.db.duckdb_adapter._get_shared_duckdb_connection")
def test_duckdb_conn_open(mock_get_conn):
    mock_get_conn.return_value = MagicMock()
    conn = _DuckDBConn("dummy_path")
    assert conn.open is True
