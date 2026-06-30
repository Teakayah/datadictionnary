from unittest.mock import patch, MagicMock
from src.storage.pipeline_storage import (
    DuckDBPipelineDefStorage,
    DuckDBPipelineRunStorage,
    DemoPipelineDefStorage,
    DemoPipelineRunStorage,
    FakePipelineDefStorage,
    FakePipelineRunStorage
)

@patch("src.storage.pipeline_storage.get_db_connection")
def test_duckdb_pipeline_def_list_all(mock_get_db):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_get_db.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    mock_cursor.fetchall.return_value = [
        ("id1", "title1", "desc", "adf", None, "sub", "rg", "factory", "pipe", None, None, None, "u1", "time1")
    ]

    storage = DuckDBPipelineDefStorage()
    res = storage.list_all()

    assert len(res) == 1
    assert res[0]["pipeline_id"] == "id1"
    assert res[0]["title"] == "title1"

@patch("src.storage.pipeline_storage.log")
@patch("src.storage.pipeline_storage.get_db_connection")
def test_duckdb_pipeline_def_list_all_error(mock_get_db, mock_log):
    mock_get_db.side_effect = Exception("DB error")

    storage = DuckDBPipelineDefStorage()
    res = storage.list_all()

    assert len(res) == 0
    mock_log.warning.assert_called_once()

@patch("src.storage.pipeline_storage._get_write_connection")
def test_duckdb_pipeline_def_create(mock_get_conn):
    mock_conn = MagicMock()
    mock_get_conn.return_value = mock_conn

    storage = DuckDBPipelineDefStorage()
    pipeline = {
        "pipeline_id": "id1",
        "title": "t",
        "description": "d",
        "backend": "adf",
        "databricks_job_id": None,
        "adf_subscription_id": "s",
        "adf_resource_group": "rg",
        "adf_factory_name": "f",
        "adf_pipeline_name": "p",
        "ado_organization": None,
        "ado_project": None,
        "ado_pipeline_id": None,
        "created_by": "u",
        "created_at": "t"
    }

    storage.create(pipeline)

    mock_conn.execute.assert_called_once()
    assert "INSERT INTO user_data.pipeline_definitions" in mock_conn.execute.call_args[0][0]


@patch("src.storage.pipeline_storage._get_write_connection")
def test_duckdb_pipeline_def_delete(mock_get_conn):
    mock_conn = MagicMock()
    mock_get_conn.return_value = mock_conn

    storage = DuckDBPipelineDefStorage()
    storage.delete("id1")

    mock_conn.execute.assert_called_once()
    assert "DELETE FROM user_data.pipeline_definitions" in mock_conn.execute.call_args[0][0]
    assert mock_conn.execute.call_args[0][1] == ["id1"]

@patch("src.storage.pipeline_storage.get_db_connection")
def test_duckdb_pipeline_run_get_active(mock_get_db):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_get_db.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    mock_cursor.fetchall.return_value = [
        ("run1", "user1", "time1", "started", "time2")
    ]

    storage = DuckDBPipelineRunStorage()
    res = storage.get_active("pipe1")

    assert res is not None
    assert res["pipeline_id"] == "pipe1"
    assert res["backend_run_id"] == "run1"

@patch("src.storage.pipeline_storage.get_db_connection")
def test_duckdb_pipeline_run_get_active_empty(mock_get_db):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_get_db.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    mock_cursor.fetchall.return_value = []

    storage = DuckDBPipelineRunStorage()
    res = storage.get_active("pipe1")

    assert res is None

@patch("src.storage.pipeline_storage.log")
@patch("src.storage.pipeline_storage.get_db_connection")
def test_duckdb_pipeline_run_get_active_error(mock_get_db, mock_log):
    mock_get_db.side_effect = Exception("DB error")

    storage = DuckDBPipelineRunStorage()
    res = storage.get_active("pipe1")

    assert res is None
    mock_log.warning.assert_called_once()

@patch("src.storage.pipeline_storage._get_write_connection")
def test_duckdb_pipeline_run_upsert(mock_get_conn):
    mock_conn = MagicMock()
    mock_get_conn.return_value = mock_conn

    storage = DuckDBPipelineRunStorage()
    storage.upsert("pipe1", "run1", "user1")

    mock_conn.execute.assert_called_once()
    assert "INSERT INTO user_data.pipeline_runs" in mock_conn.execute.call_args[0][0]

@patch("src.storage.pipeline_storage._get_write_connection")
def test_duckdb_pipeline_run_update_status(mock_get_conn):
    mock_conn = MagicMock()
    mock_get_conn.return_value = mock_conn

    storage = DuckDBPipelineRunStorage()
    storage.update_status("pipe1", "completed")

    mock_conn.execute.assert_called_once()
    assert "UPDATE user_data.pipeline_runs SET status =" in mock_conn.execute.call_args[0][0]

@patch("src.storage.pipeline_storage._get_write_connection")
def test_duckdb_pipeline_run_clear(mock_get_conn):
    mock_conn = MagicMock()
    mock_get_conn.return_value = mock_conn

    storage = DuckDBPipelineRunStorage()
    storage.clear("pipe1")

    mock_conn.execute.assert_called_once()
    assert "DELETE FROM user_data.pipeline_runs" in mock_conn.execute.call_args[0][0]
    assert mock_conn.execute.call_args[0][1] == ["pipe1"]

def test_demo_pipeline_def_storage():
    import streamlit as st
    st.session_state.clear()
    storage = DemoPipelineDefStorage()

    assert storage.list_all() == []

    pipeline = {"pipeline_id": "p1", "title": "t1"}
    storage.create(pipeline)

    res = storage.list_all()
    assert len(res) == 1
    assert res[0]["pipeline_id"] == "p1"

    storage.delete("p1")
    assert storage.list_all() == []

def test_demo_pipeline_run_storage():
    import streamlit as st
    st.session_state.clear()
    storage = DemoPipelineRunStorage()

    assert storage.get_active("p1") is None

    storage.upsert("p1", "r1", "u1")

    active = storage.get_active("p1")
    assert active is not None
    assert active["pipeline_id"] == "p1"
    assert active["backend_run_id"] == "r1"
    assert active["status"] == "started"

    storage.update_status("p1", "completed")
    active = storage.get_active("p1")
    assert active["status"] == "completed"

    storage.update_status("p2", "completed") # Doesn't exist, shouldn't crash

    storage.clear("p1")
    assert storage.get_active("p1") is None

def test_fake_pipeline_def_storage():
    storage = FakePipelineDefStorage()

    assert storage.list_all() == []

    pipeline = {"pipeline_id": "p1", "title": "t1"}
    storage.create(pipeline)

    res = storage.list_all()
    assert len(res) == 1
    assert res[0]["pipeline_id"] == "p1"

    storage.delete("p1")
    assert storage.list_all() == []

def test_fake_pipeline_run_storage():
    storage = FakePipelineRunStorage()

    assert storage.get_active("p1") is None

    storage.upsert("p1", "r1", "u1")

    active = storage.get_active("p1")
    assert active is not None
    assert active["pipeline_id"] == "p1"
    assert active["backend_run_id"] == "r1"
    assert active["status"] == "started"

    storage.update_status("p1", "completed")
    active = storage.get_active("p1")
    assert active["status"] == "completed"

    storage.update_status("p2", "completed") # Doesn't exist, shouldn't crash

    storage.clear("p1")
    assert storage.get_active("p1") is None
