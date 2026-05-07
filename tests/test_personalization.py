from unittest.mock import patch, MagicMock
import pandas as pd
import streamlit as st

from src.personalization import (
    _user_oid,
    _pref_upsert,
    _pref_delete,
    _pref_load,
    _sync_prefs_to_session,
)

class TestUserOid:
    def test_user_oid_from_oid(self):
        st.session_state.clear()
        st.session_state["user_oid"] = "123-oid"
        st.session_state["user_email"] = "test@example.com"
        assert _user_oid() == "123-oid"

    def test_user_oid_from_email(self):
        st.session_state.clear()
        st.session_state["user_email"] = "test@example.com"
        assert _user_oid() == "test@example.com"

    def test_user_oid_anonymous(self):
        st.session_state.clear()
        assert _user_oid() == "anonymous"

class TestPrefUpsert:
    @patch("src.personalization._duckdb_available", return_value=False)
    def test_duckdb_unavailable(self, mock_duckdb):
        # Should return early
        assert _pref_upsert("table_1", "bookmark") is None

    @patch("src.personalization._duckdb_available", return_value=True)
    @patch("src.personalization.get_db_connection")
    @patch("src.personalization._user_oid", return_value="123")
    def test_successful_upsert(self, mock_oid, mock_conn, mock_duckdb):
        mock_con_instance = MagicMock()
        mock_conn.return_value = mock_con_instance

        _pref_upsert("table_1", "bookmark")

        mock_con_instance.execute.assert_called_once()
        args, kwargs = mock_con_instance.execute.call_args
        assert "INSERT INTO user_data.user_preferences" in args[0]
        assert args[1] == ["123", "table_1", "bookmark"]

    @patch("src.personalization._duckdb_available", return_value=True)
    @patch("src.personalization.get_db_connection")
    @patch("src.personalization.logging.warning")
    def test_exception_handling(self, mock_logging, mock_conn, mock_duckdb):
        mock_con_instance = MagicMock()
        mock_con_instance.execute.side_effect = Exception("DB error")
        mock_conn.return_value = mock_con_instance

        _pref_upsert("table_1", "bookmark")

        mock_logging.assert_called_once_with("Could not write user preference: %s", mock_con_instance.execute.side_effect)

class TestPrefDelete:
    @patch("src.personalization._duckdb_available", return_value=False)
    def test_duckdb_unavailable(self, mock_duckdb):
        assert _pref_delete("table_1", "bookmark") is None

    @patch("src.personalization._duckdb_available", return_value=True)
    @patch("src.personalization.get_db_connection")
    @patch("src.personalization._user_oid", return_value="123")
    def test_successful_delete(self, mock_oid, mock_conn, mock_duckdb):
        mock_con_instance = MagicMock()
        mock_conn.return_value = mock_con_instance

        _pref_delete("table_1", "bookmark")

        mock_con_instance.execute.assert_called_once()
        args, kwargs = mock_con_instance.execute.call_args
        assert "DELETE FROM user_data.user_preferences" in args[0]
        assert args[1] == ["123", "table_1", "bookmark"]

    @patch("src.personalization._duckdb_available", return_value=True)
    @patch("src.personalization.get_db_connection")
    @patch("src.personalization.logging.warning")
    def test_exception_handling(self, mock_logging, mock_conn, mock_duckdb):
        mock_con_instance = MagicMock()
        mock_con_instance.execute.side_effect = Exception("DB error")
        mock_conn.return_value = mock_con_instance

        _pref_delete("table_1", "bookmark")

        mock_logging.assert_called_once_with("Could not delete user preference: %s", mock_con_instance.execute.side_effect)

class TestPrefLoad:
    @patch("src.personalization._duckdb_available", return_value=False)
    def test_duckdb_unavailable(self, mock_duckdb):
        assert _pref_load("bookmark") == []

    @patch("src.personalization._duckdb_available", return_value=True)
    @patch("src.personalization.get_db_connection")
    @patch("src.personalization._user_oid", return_value="123")
    def test_successful_load(self, mock_oid, mock_conn, mock_duckdb):
        mock_con_instance = MagicMock()
        mock_cursor = MagicMock()
        mock_con_instance.cursor.return_value.__enter__.return_value = mock_cursor
        mock_conn.return_value = mock_con_instance

        df = pd.DataFrame({"table_full_name": ["table_1", "table_2"]})
        mock_cursor.fetchall_as_pandas.return_value = df

        result = _pref_load("bookmark", limit=10)

        assert result == ["table_1", "table_2"]
        mock_cursor.execute.assert_called_once()
        args, kwargs = mock_cursor.execute.call_args
        assert "SELECT table_full_name FROM user_data.user_preferences" in args[0]
        assert args[1] == {"oid": "123", "type": "bookmark", "lim": 10}

    @patch("src.personalization._duckdb_available", return_value=True)
    @patch("src.personalization.get_db_connection")
    def test_empty_result(self, mock_conn, mock_duckdb):
        mock_con_instance = MagicMock()
        mock_cursor = MagicMock()
        mock_con_instance.cursor.return_value.__enter__.return_value = mock_cursor
        mock_conn.return_value = mock_con_instance

        mock_cursor.fetchall_as_pandas.return_value = pd.DataFrame()

        result = _pref_load("bookmark")
        assert result == []

    @patch("src.personalization._duckdb_available", return_value=True)
    @patch("src.personalization.get_db_connection")
    @patch("src.personalization.logging.warning")
    def test_exception_handling(self, mock_logging, mock_conn, mock_duckdb):
        mock_con_instance = MagicMock()
        mock_con_instance.cursor.side_effect = Exception("DB error")
        mock_conn.return_value = mock_con_instance

        result = _pref_load("bookmark")

        assert result == []
        mock_logging.assert_called_once_with("Could not load user preferences: %s", mock_con_instance.cursor.side_effect)

class TestSyncPrefsToSession:
    @patch("src.personalization._pref_load")
    def test_sync_prefs(self, mock_pref_load):
        # Setup mock returns
        def pref_load_side_effect(pref_type, limit=20):
            if pref_type == "bookmark":
                return ["table_1"]
            elif pref_type == "col_bookmark":
                return ["col_1"]
            elif pref_type == "recent":
                return ["table_2", "table_3"]
            return []

        mock_pref_load.side_effect = pref_load_side_effect

        st.session_state.clear()

        _sync_prefs_to_session()

        assert st.session_state.bookmarks == {"table_1"}
        assert st.session_state.col_bookmarks == {"col_1"}
        assert st.session_state.recent_views == ["table_2", "table_3"]
