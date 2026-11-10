import pytest
import duckdb
from src.db.duckdb_adapter import _DuckDBCursor
from unittest.mock import patch, MagicMock

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

def test_duckdb_adapter_execute_write():
    from src.db.duckdb_adapter import _DuckDBCursor
    con_mock = MagicMock()
    cursor = _DuckDBCursor(con_mock)

    sql = "INSERT INTO test (a) VALUES (1)"
    cursor.execute_write(sql)
    con_mock.execute.assert_called_once_with(sql)

def test_duckdb_adapter_context_manager():
    from src.db.duckdb_adapter import _DuckDBConn
    con_mock = MagicMock()
    with patch('src.db.duckdb_adapter._get_shared_duckdb_connection', return_value=con_mock):
        db = _DuckDBConn(':memory:')
        with db as ctx:
            assert ctx is db

def test_duckdb_adapter_ensure_user_data_attached_no_con():
    from src.db.duckdb_adapter import _DuckDBConn
    with patch('src.db.duckdb_adapter._get_shared_duckdb_connection', return_value=None):
        db = _DuckDBConn(':memory:')
        # Verify it returns early without error
        db._ensure_user_data_attached()

def test_duckdb_adapter_ensure_user_data_attached():
    from src.db.duckdb_adapter import _DuckDBConn
    con_mock = MagicMock()
    with patch('src.db.duckdb_adapter._get_shared_duckdb_connection', return_value=con_mock):
        db = _DuckDBConn(':memory:', read_only=False)
        with patch('src.db.duckdb_adapter.USER_DATA_PATH', 'test_path'):
            with patch('src.db.duckdb_adapter._ensure_user_data_attached') as mock_ensure:
                db._ensure_user_data_attached()
                mock_ensure.assert_called_once_with(con_mock, 'test_path', read_only=False)