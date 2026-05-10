from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from src.sync.worker import (
    read_dr_resync_status,
    read_worker_heartbeat,
    _read_setting,
    DR_STATUS_KEY,
    WORKER_HEARTBEAT_KEY,
)

@patch("src.sync.worker._duckdb_available", return_value=True)
@patch("src.db.queries.get_db_connection")
def test_read_setting_success(mock_get_db, mock_duckdb):
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_get_db.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur

    # Simulate a row being returned
    mock_cur.fetchall.return_value = [("SuccessValue",)]

    assert _read_setting("test_key", "default") == "SuccessValue"
    mock_cur.execute.assert_called_once_with(
        "SELECT value FROM user_data.site_settings WHERE key = %(k)s",
        {"k": "test_key"}
    )

@patch("src.sync.worker._duckdb_available", return_value=True)
@patch("src.db.queries.get_db_connection")
def test_read_setting_not_found(mock_get_db, mock_duckdb):
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_get_db.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur

    # Simulate no row returned
    mock_cur.fetchall.return_value = []

    assert _read_setting("test_key", "default") == "default"

@patch("src.sync.worker._duckdb_available", return_value=False)
def test_read_setting_duckdb_unavailable(mock_duckdb):
    assert _read_setting("test_key", "default") == "default"

@patch("src.sync.worker._duckdb_available", return_value=True)
@patch("src.db.queries.get_db_connection")
def test_read_setting_exception(mock_get_db, mock_duckdb):
    mock_get_db.side_effect = Exception("DB error")
    assert _read_setting("test_key", "default") == "default"

@patch("src.sync.worker._read_setting")
def test_read_dr_resync_status(mock_read_setting):
    mock_read_setting.return_value = "Running"
    assert read_dr_resync_status() == "Running"
    mock_read_setting.assert_called_once_with(DR_STATUS_KEY, default="Idle")

@patch("src.sync.worker._read_setting")
def test_read_dr_resync_status_default(mock_read_setting):
    mock_read_setting.return_value = "Idle"
    assert read_dr_resync_status() == "Idle"
    mock_read_setting.assert_called_once_with(DR_STATUS_KEY, default="Idle")

@patch("src.sync.worker._read_setting")
def test_read_worker_heartbeat(mock_read_setting):
    mock_read_setting.return_value = "2023-10-01T12:00:00Z"
    assert read_worker_heartbeat() == "2023-10-01T12:00:00Z"
    mock_read_setting.assert_called_once_with(WORKER_HEARTBEAT_KEY, default="")
