import pytest
import duckdb
from unittest.mock import patch, MagicMock
from src.db.duckdb_adapter import _DuckDBCursor

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
def test_duckdb_adapter_executemany_invalid_input():
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_conn.executemany.side_effect = duckdb.InvalidInputException("executemany with no parameters")
    from src.db.duckdb_adapter import _DuckDBCursor
    import pytest
    with _DuckDBCursor(mock_conn) as cursor:
        with pytest.raises(duckdb.InvalidInputException):
            cursor.executemany("SELECT 1", [])

def test_duckdb_adapter_executemany_question_mark_params():
    mock_conn = MagicMock()

    from src.db.duckdb_adapter import _DuckDBCursor
    with _DuckDBCursor(mock_conn) as cursor:
        cursor.executemany("SELECT ?", [(1,), (2,)])

    mock_conn.executemany.assert_called_with("SELECT ?", [(1,), (2,)])
