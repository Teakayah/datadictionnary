import pytest
import duckdb
from unittest.mock import MagicMock
from src.db.duckdb_adapter import _DuckDBCursor, _DuckDBConn
from unittest.mock import patch

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

def test_duckdb_adapter_initialization_with_env_readonly(monkeypatch):
    monkeypatch.setenv("DUCKDB_READ_ONLY", "1")
    monkeypatch.setattr("src.db.duckdb_adapter._get_shared_duckdb_connection", MagicMock(return_value=None))

    # Act
    adapter = _DuckDBConn(":memory:")

    # Assert
    assert adapter._read_only is True

def test_duckdb_adapter_initialization_without_env_readonly(monkeypatch):
    monkeypatch.delenv("DUCKDB_READ_ONLY", raising=False)
    monkeypatch.setattr("src.db.duckdb_adapter._get_shared_duckdb_connection", MagicMock(return_value=None))

    # Act
    adapter = _DuckDBConn(":memory:")

    # Assert
    assert adapter._read_only is False

@patch('src.db.duckdb_adapter._ensure_user_data_attached')
def test_duckdb_adapter_ensure_user_data_attached_called_with_safe_path(mock_ensure, monkeypatch):
    import src.db.duckdb_adapter
    safe_path = "dummy" + chr(0) + "'test.db"
    monkeypatch.setattr(src.db.duckdb_adapter, "USER_DATA_PATH", safe_path)
    monkeypatch.setattr("src.db.duckdb_adapter._get_shared_duckdb_connection", MagicMock(return_value="mock_con"))

    adapter = _DuckDBConn(":memory:")

    # Act
    adapter._ensure_user_data_attached()

    # Assert
    mock_ensure.assert_called_once_with("mock_con", "dummy''test.db", read_only=adapter._read_only)

@patch('src.db.duckdb_adapter._ensure_user_data_attached')
def test_duckdb_adapter_ensure_user_data_attached_no_con(mock_ensure, monkeypatch):
    monkeypatch.setattr("src.db.duckdb_adapter._get_shared_duckdb_connection", MagicMock(return_value=None))

    adapter = _DuckDBConn(":memory:")

    # Act
    adapter._ensure_user_data_attached()

    # Assert
    mock_ensure.assert_not_called()
