import pytest
import duckdb
from unittest.mock import MagicMock
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
import pytest
import duckdb
from unittest.mock import MagicMock, patch
import pandas as pd
from src.db.duckdb_adapter import _DuckDBCursor, _DuckDBConn, _to_duckdb_sql, _duckdb_available, _run_duckdb_query, _get_shared_duckdb_connection, _clear_shared_duckdb_connection, _ensure_user_data_attached

def test_duckdb_adapter_to_duckdb_sql_empty_params():
    sql = "SELECT 1"
    res_sql, res_params = _to_duckdb_sql(sql, {})
    assert res_sql == sql
    assert res_params == {}

    res_sql, res_params = _to_duckdb_sql(sql, None)
    assert res_sql == sql
    assert res_params == {}

def test_duckdb_adapter_to_duckdb_sql_list_val():
    sql = "SELECT * FROM tbl WHERE id IN %(ids)s"
    params = {"ids": [1, 2, 3]}
    res_sql, res_params = _to_duckdb_sql(sql, params)
    assert res_sql == "SELECT * FROM tbl WHERE id = ANY($ids)"
    assert res_params == {"ids": [1, 2, 3]}

def test_duckdb_available():
    with patch('src.db.duckdb_adapter.DUCKDB_PATH', "some_path"):
        with patch('os.path.exists', return_value=True):
            assert _duckdb_available() == True

    with patch('src.db.duckdb_adapter.DUCKDB_PATH', "some_path"):
        with patch('os.path.exists', return_value=False):
            assert _duckdb_available() == False

    with patch('src.db.duckdb_adapter.DUCKDB_PATH', None):
        with patch('os.path.exists', return_value=True):
            assert _duckdb_available() == False

def test_duckdb_cursor_execute_none_con():
    cursor = _DuckDBCursor(None)
    cursor.execute("SELECT 1")
    assert cursor._rel is None

def test_duckdb_cursor_execute_dict_params():
    con_mock = MagicMock()
    cursor = _DuckDBCursor(con_mock)
    cursor.execute("SELECT %(a)s", {"a": 1})
    con_mock.execute.assert_called_once_with("SELECT $a", {"a": 1})

def test_duckdb_cursor_execute_write():
    con_mock = MagicMock()
    cursor = _DuckDBCursor(con_mock)
    cursor.execute_write("SELECT 1")
    con_mock.execute.assert_called_once_with("SELECT 1")

def test_duckdb_cursor_fetchall():
    con_mock = MagicMock()
    rel_mock = MagicMock()
    rel_mock.fetchall.return_value = [1]
    con_mock.execute.return_value = rel_mock
    cursor = _DuckDBCursor(con_mock)
    cursor.execute("SELECT 1")
    res = cursor.fetchall()
    assert res == [1]

def test_duckdb_cursor_fetchall_none_rel():
    con_mock = MagicMock()
    cursor = _DuckDBCursor(con_mock)
    res = cursor.fetchall()
    assert res == []

def test_duckdb_cursor_fetchall_as_pandas():
    con_mock = MagicMock()
    rel_mock = MagicMock()
    df_mock = pd.DataFrame({'a': [1]})
    rel_mock.df.return_value = df_mock
    con_mock.execute.return_value = rel_mock
    cursor = _DuckDBCursor(con_mock)
    cursor.execute("SELECT 1")
    res = cursor.fetchall_as_pandas()
    assert not res.empty

def test_duckdb_cursor_fetchall_as_pandas_none_rel():
    con_mock = MagicMock()
    cursor = _DuckDBCursor(con_mock)
    res = cursor.fetchall_as_pandas()
    assert res.empty

def test_duckdb_cursor_enter_exit():
    con_mock = MagicMock()
    cursor = _DuckDBCursor(con_mock)
    with cursor as c:
        assert c == cursor

def test_ensure_user_data_attached_read_only_exists():
    con_mock = MagicMock()
    with patch('os.path.exists', return_value=True):
        _ensure_user_data_attached(con_mock, "path", read_only=True)
        con_mock.execute.assert_called_once_with('ATTACH IF NOT EXISTS \'path\' AS "user_data" (READ_ONLY)')

def test_duckdb_conn_cursor():
    con_mock = MagicMock()
    with patch('src.db.duckdb_adapter._get_shared_duckdb_connection', return_value=con_mock):
        conn = _DuckDBConn("fake_path")
        cursor = conn.cursor()
        assert cursor._con == con_mock

def test_duckdb_conn_execute():
    con_mock = MagicMock()
    with patch('src.db.duckdb_adapter._get_shared_duckdb_connection', return_value=con_mock):
        conn = _DuckDBConn("fake_path")
        cursor = conn.execute("SELECT 1", [1])
        assert cursor._con == con_mock
        con_mock.execute.assert_called()

def test_duckdb_conn_enter_exit():
    con_mock = MagicMock()
    with patch('src.db.duckdb_adapter._get_shared_duckdb_connection', return_value=con_mock):
        conn = _DuckDBConn("fake_path")
        with conn as c:
            assert c == conn

def test_duckdb_conn_open():
    con_mock = MagicMock()
    with patch('src.db.duckdb_adapter._get_shared_duckdb_connection', return_value=con_mock):
        conn = _DuckDBConn("fake_path")
        assert conn.open == True

    with patch('src.db.duckdb_adapter._get_shared_duckdb_connection', return_value=None):
        conn = _DuckDBConn("fake_path")
        assert conn.open == False

def test_duckdb_connection_ensure_user_data_attached_no_con():
    with patch('src.db.duckdb_adapter._get_shared_duckdb_connection', return_value=None):
        conn = _DuckDBConn("fake_path")
        conn._ensure_user_data_attached()

def test_duckdb_connection_ensure_user_data_attached_with_con():
    con_mock = MagicMock()
    with patch('src.db.duckdb_adapter._get_shared_duckdb_connection', return_value=con_mock):
        with patch('src.db.duckdb_adapter.USER_DATA_PATH', "some'path\x00"):
            with patch('src.db.duckdb_adapter._ensure_user_data_attached') as mock_ensure:
                conn = _DuckDBConn("fake_path")
                conn._ensure_user_data_attached()
                mock_ensure.assert_called_once_with(con_mock, "some''path", read_only=conn._read_only)

def test_duckdb_connection_ensure_user_data_attached_no_user_data_path():
    con_mock = MagicMock()
    with patch('src.db.duckdb_adapter._get_shared_duckdb_connection', return_value=con_mock):
        with patch('src.db.duckdb_adapter.USER_DATA_PATH', None):
            with patch('src.db.duckdb_adapter._ensure_user_data_attached') as mock_ensure:
                conn = _DuckDBConn("fake_path")
                conn._ensure_user_data_attached()
                mock_ensure.assert_called_once_with(con_mock, "", read_only=conn._read_only)

def test_run_duckdb_query():
    con_mock = MagicMock()
    rel_mock = MagicMock()
    df_mock = pd.DataFrame({'a': [1]})
    rel_mock.df.return_value = df_mock
    con_mock.execute.return_value = rel_mock
    with patch('src.db.duckdb_adapter._get_shared_duckdb_connection', return_value=con_mock):
        res = _run_duckdb_query("SELECT 1")
        assert not res.empty

def test_get_shared_duckdb_connection():
    with patch('src.db.duckdb_adapter._duckdb_available', return_value=True):
        with patch('duckdb.connect') as mock_connect:
            mock_con = MagicMock()
            mock_connect.return_value = mock_con

            _clear_shared_duckdb_connection()
            con1 = _get_shared_duckdb_connection()
            con2 = _get_shared_duckdb_connection()
            assert con1 == con2
            mock_connect.assert_called_once()

            _clear_shared_duckdb_connection()
            with patch.dict('os.environ', {'DUCKDB_READ_ONLY': '1'}):
                con = _get_shared_duckdb_connection()
                assert con is not None

def test_get_shared_duckdb_connection_unavailable():
    with patch('src.db.duckdb_adapter._duckdb_available', return_value=False):
        _clear_shared_duckdb_connection()
        con = _get_shared_duckdb_connection()
        assert con is None

def test_get_shared_duckdb_connection_exception():
    with patch('src.db.duckdb_adapter._duckdb_available', return_value=True):
        with patch('duckdb.connect', side_effect=Exception("Test Exception")):
            _clear_shared_duckdb_connection()
            con = _get_shared_duckdb_connection()
            assert con is None

def test_duckdb_conn_read_only_default():
    with patch.dict('os.environ', {'DUCKDB_READ_ONLY': 'true'}):
        with patch('src.db.duckdb_adapter._get_shared_duckdb_connection', return_value=MagicMock()):
            conn = _DuckDBConn("fake_path")
            assert conn._read_only == True

    with patch.dict('os.environ', {'DUCKDB_READ_ONLY': 'false'}):
        with patch('src.db.duckdb_adapter._get_shared_duckdb_connection', return_value=MagicMock()):
            conn = _DuckDBConn("fake_path")
            assert conn._read_only == False

def test_duckdb_conn_read_only_explicit():
    with patch('src.db.duckdb_adapter._get_shared_duckdb_connection', return_value=MagicMock()):
        conn = _DuckDBConn("fake_path", read_only=True)
        assert conn._read_only == True

def test_run_duckdb_query_with_params():
    con_mock = MagicMock()
    rel_mock = MagicMock()
    df_mock = pd.DataFrame({'a': [1]})
    rel_mock.df.return_value = df_mock
    con_mock.execute.return_value = rel_mock
    with patch('src.db.duckdb_adapter._get_shared_duckdb_connection', return_value=con_mock):
        res = _run_duckdb_query("SELECT %(a)s", {"a": 1})
        assert not res.empty
        con_mock.execute.assert_called_once_with("SELECT $a", {"a": 1})

def test_get_shared_duckdb_connection_double_check():
    import src.db.duckdb_adapter as m
    with patch.object(m, '_duckdb_available', return_value=True):
        m._shared_connection = None

        # Override lock to simulate race condition
        original_lock = m._db_write_lock
        class FakeLock:
            def __enter__(self):
                m._shared_connection = "already_set"
            def __exit__(self, *args):
                pass
        m._db_write_lock = FakeLock()

        try:
            con = m._get_shared_duckdb_connection()
            assert con == "already_set"
        finally:
            m._db_write_lock = original_lock
            m._shared_connection = None

import pytest
import duckdb
from unittest.mock import MagicMock, patch
import pandas as pd
from src.db.duckdb_adapter import _DuckDBCursor, _DuckDBConn, _to_duckdb_sql, _duckdb_available, _run_duckdb_query, _get_shared_duckdb_connection, _clear_shared_duckdb_connection, _ensure_user_data_attached

def test_duckdb_adapter_to_duckdb_sql_empty_params():
    sql = "SELECT 1"
    res_sql, res_params = _to_duckdb_sql(sql, {})
    assert res_sql == sql
    assert res_params == {}

    res_sql, res_params = _to_duckdb_sql(sql, None)
    assert res_sql == sql
    assert res_params == {}

def test_duckdb_adapter_to_duckdb_sql_list_val():
    sql = "SELECT * FROM tbl WHERE id IN %(ids)s"
    params = {"ids": [1, 2, 3]}
    res_sql, res_params = _to_duckdb_sql(sql, params)
    assert res_sql == "SELECT * FROM tbl WHERE id = ANY($ids)"
    assert res_params == {"ids": [1, 2, 3]}

def test_duckdb_available():
    with patch('src.db.duckdb_adapter.DUCKDB_PATH', "some_path"):
        with patch('os.path.exists', return_value=True):
            assert _duckdb_available() == True

    with patch('src.db.duckdb_adapter.DUCKDB_PATH', "some_path"):
        with patch('os.path.exists', return_value=False):
            assert _duckdb_available() == False

    with patch('src.db.duckdb_adapter.DUCKDB_PATH', None):
        with patch('os.path.exists', return_value=True):
            assert _duckdb_available() == False

def test_duckdb_cursor_execute_none_con():
    cursor = _DuckDBCursor(None)
    cursor.execute("SELECT 1")
    assert cursor._rel is None

def test_duckdb_cursor_execute_dict_params():
    con_mock = MagicMock()
    cursor = _DuckDBCursor(con_mock)
    cursor.execute("SELECT %(a)s", {"a": 1})
    con_mock.execute.assert_called_once_with("SELECT $a", {"a": 1})

def test_duckdb_cursor_execute_write():
    con_mock = MagicMock()
    cursor = _DuckDBCursor(con_mock)
    cursor.execute_write("SELECT 1")
    con_mock.execute.assert_called_once_with("SELECT 1")

def test_duckdb_cursor_fetchall():
    con_mock = MagicMock()
    rel_mock = MagicMock()
    rel_mock.fetchall.return_value = [1]
    con_mock.execute.return_value = rel_mock
    cursor = _DuckDBCursor(con_mock)
    cursor.execute("SELECT 1")
    res = cursor.fetchall()
    assert res == [1]

def test_duckdb_cursor_fetchall_none_rel():
    con_mock = MagicMock()
    cursor = _DuckDBCursor(con_mock)
    res = cursor.fetchall()
    assert res == []

def test_duckdb_cursor_fetchall_as_pandas():
    con_mock = MagicMock()
    rel_mock = MagicMock()
    df_mock = pd.DataFrame({'a': [1]})
    rel_mock.df.return_value = df_mock
    con_mock.execute.return_value = rel_mock
    cursor = _DuckDBCursor(con_mock)
    cursor.execute("SELECT 1")
    res = cursor.fetchall_as_pandas()
    assert not res.empty

def test_duckdb_cursor_fetchall_as_pandas_none_rel():
    con_mock = MagicMock()
    cursor = _DuckDBCursor(con_mock)
    res = cursor.fetchall_as_pandas()
    assert res.empty

def test_duckdb_cursor_enter_exit():
    con_mock = MagicMock()
    cursor = _DuckDBCursor(con_mock)
    with cursor as c:
        assert c == cursor

def test_ensure_user_data_attached_read_only_exists():
    con_mock = MagicMock()
    with patch('os.path.exists', return_value=True):
        _ensure_user_data_attached(con_mock, "path", read_only=True)
        con_mock.execute.assert_called_once_with('ATTACH IF NOT EXISTS \'path\' AS "user_data" (READ_ONLY)')

def test_duckdb_conn_cursor():
    con_mock = MagicMock()
    with patch('src.db.duckdb_adapter._get_shared_duckdb_connection', return_value=con_mock):
        conn = _DuckDBConn("fake_path")
        cursor = conn.cursor()
        assert cursor._con == con_mock

def test_duckdb_conn_execute():
    con_mock = MagicMock()
    with patch('src.db.duckdb_adapter._get_shared_duckdb_connection', return_value=con_mock):
        conn = _DuckDBConn("fake_path")
        cursor = conn.execute("SELECT 1", [1])
        assert cursor._con == con_mock
        con_mock.execute.assert_called()

def test_duckdb_conn_enter_exit():
    con_mock = MagicMock()
    with patch('src.db.duckdb_adapter._get_shared_duckdb_connection', return_value=con_mock):
        conn = _DuckDBConn("fake_path")
        with conn as c:
            assert c == conn

def test_duckdb_conn_open():
    con_mock = MagicMock()
    with patch('src.db.duckdb_adapter._get_shared_duckdb_connection', return_value=con_mock):
        conn = _DuckDBConn("fake_path")
        assert conn.open == True

    with patch('src.db.duckdb_adapter._get_shared_duckdb_connection', return_value=None):
        conn = _DuckDBConn("fake_path")
        assert conn.open == False

def test_duckdb_connection_ensure_user_data_attached_no_con():
    with patch('src.db.duckdb_adapter._get_shared_duckdb_connection', return_value=None):
        conn = _DuckDBConn("fake_path")
        conn._ensure_user_data_attached()

def test_duckdb_connection_ensure_user_data_attached_with_con():
    con_mock = MagicMock()
    with patch('src.db.duckdb_adapter._get_shared_duckdb_connection', return_value=con_mock):
        with patch('src.db.duckdb_adapter.USER_DATA_PATH', "some'path\x00"):
            with patch('src.db.duckdb_adapter._ensure_user_data_attached') as mock_ensure:
                conn = _DuckDBConn("fake_path")
                conn._ensure_user_data_attached()
                mock_ensure.assert_called_once_with(con_mock, "some''path", read_only=conn._read_only)

def test_duckdb_connection_ensure_user_data_attached_no_user_data_path():
    con_mock = MagicMock()
    with patch('src.db.duckdb_adapter._get_shared_duckdb_connection', return_value=con_mock):
        with patch('src.db.duckdb_adapter.USER_DATA_PATH', None):
            with patch('src.db.duckdb_adapter._ensure_user_data_attached') as mock_ensure:
                conn = _DuckDBConn("fake_path")
                conn._ensure_user_data_attached()
                mock_ensure.assert_called_once_with(con_mock, "", read_only=conn._read_only)

def test_run_duckdb_query():
    con_mock = MagicMock()
    rel_mock = MagicMock()
    df_mock = pd.DataFrame({'a': [1]})
    rel_mock.df.return_value = df_mock
    con_mock.execute.return_value = rel_mock
    with patch('src.db.duckdb_adapter._get_shared_duckdb_connection', return_value=con_mock):
        res = _run_duckdb_query("SELECT 1")
        assert not res.empty

def test_get_shared_duckdb_connection():
    with patch('src.db.duckdb_adapter._duckdb_available', return_value=True):
        with patch('duckdb.connect') as mock_connect:
            mock_con = MagicMock()
            mock_connect.return_value = mock_con

            _clear_shared_duckdb_connection()
            con1 = _get_shared_duckdb_connection()
            con2 = _get_shared_duckdb_connection()
            assert con1 == con2
            mock_connect.assert_called_once()

            _clear_shared_duckdb_connection()
            with patch.dict('os.environ', {'DUCKDB_READ_ONLY': '1'}):
                con = _get_shared_duckdb_connection()
                assert con is not None

def test_get_shared_duckdb_connection_unavailable():
    with patch('src.db.duckdb_adapter._duckdb_available', return_value=False):
        _clear_shared_duckdb_connection()
        con = _get_shared_duckdb_connection()
        assert con is None

def test_get_shared_duckdb_connection_exception():
    with patch('src.db.duckdb_adapter._duckdb_available', return_value=True):
        with patch('duckdb.connect', side_effect=Exception("Test Exception")):
            _clear_shared_duckdb_connection()
            con = _get_shared_duckdb_connection()
            assert con is None

def test_duckdb_conn_read_only_default():
    with patch.dict('os.environ', {'DUCKDB_READ_ONLY': 'true'}):
        with patch('src.db.duckdb_adapter._get_shared_duckdb_connection', return_value=MagicMock()):
            conn = _DuckDBConn("fake_path")
            assert conn._read_only == True

    with patch.dict('os.environ', {'DUCKDB_READ_ONLY': 'false'}):
        with patch('src.db.duckdb_adapter._get_shared_duckdb_connection', return_value=MagicMock()):
            conn = _DuckDBConn("fake_path")
            assert conn._read_only == False

def test_duckdb_conn_read_only_explicit():
    with patch('src.db.duckdb_adapter._get_shared_duckdb_connection', return_value=MagicMock()):
        conn = _DuckDBConn("fake_path", read_only=True)
        assert conn._read_only == True

def test_run_duckdb_query_with_params():
    con_mock = MagicMock()
    rel_mock = MagicMock()
    df_mock = pd.DataFrame({'a': [1]})
    rel_mock.df.return_value = df_mock
    con_mock.execute.return_value = rel_mock
    with patch('src.db.duckdb_adapter._get_shared_duckdb_connection', return_value=con_mock):
        res = _run_duckdb_query("SELECT %(a)s", {"a": 1})
        assert not res.empty
        con_mock.execute.assert_called_once_with("SELECT $a", {"a": 1})

def test_get_shared_duckdb_connection_double_check():
    import src.db.duckdb_adapter as m
    with patch.object(m, '_duckdb_available', return_value=True):
        m._shared_connection = None

        original_lock = m._db_write_lock
        class FakeLock:
            def __enter__(self):
                m._shared_connection = "already_set"
            def __exit__(self, *args):
                pass
        m._db_write_lock = FakeLock()

        try:
            con = m._get_shared_duckdb_connection()
            assert con == "already_set"
        finally:
            m._db_write_lock = original_lock
            m._shared_connection = None
