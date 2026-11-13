import pytest
import duckdb
from unittest.mock import MagicMock, patch
from src.db.duckdb_adapter import _DuckDBCursor, _to_duckdb_sql

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

def test_duckdb_ensure_user_data_attached_no_con():
    # Calling internal _ensure_user_data_attached with no connection raises exception
    from src.db.duckdb_adapter import _ensure_user_data_attached
    with pytest.raises(Exception):
        _ensure_user_data_attached(None, "fake_path")

def test_duckdb_ensure_user_data_attached_calls_global():
    # Make sure _ensure_user_data_attached attaches the file
    from src.db.duckdb_adapter import _ensure_user_data_attached
    from unittest.mock import MagicMock, call
    mock_con = MagicMock()
    _ensure_user_data_attached(mock_con, "fake_path.duckdb")
    mock_con.execute.assert_has_calls([call('ATTACH IF NOT EXISTS \'fake_path.duckdb\' AS "user_data"')])
def test_to_duckdb_sql_no_params():
    sql, params = _to_duckdb_sql("SELECT * FROM test", {})
    assert sql == "SELECT * FROM test"
    assert params == {}

def test_to_duckdb_sql_in_clause():
    sql = "SELECT * FROM test WHERE id IN %(ids)s"
    params = {"ids": [1, 2, 3]}
    res_sql, res_params = _to_duckdb_sql(sql, params)
    assert res_sql == "SELECT * FROM test WHERE id = ANY($ids)"
    assert res_params == {"ids": [1, 2, 3]}

def test_to_duckdb_sql_pyformat():
    sql = "SELECT * FROM test WHERE id = %(id)s"
    params = {"id": 1}
    res_sql, res_params = _to_duckdb_sql(sql, params)
    assert res_sql == "SELECT * FROM test WHERE id = $id"
    assert res_params == {"id": 1}

def test_to_duckdb_sql_current_timestamp():
    sql = "SELECT current_timestamp()"
    params = {"id": 1}
    res_sql, res_params = _to_duckdb_sql(sql, params)
    assert res_sql == "SELECT current_localtimestamp()"
    assert res_params == {"id": 1}
