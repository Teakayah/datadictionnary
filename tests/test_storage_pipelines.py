from unittest.mock import patch, MagicMock
import streamlit as st

from src.storage.pipeline_storage import (
    DemoPipelineDefStorage,
    DuckDBPipelineDefStorage,
    FakePipelineDefStorage,
    DemoPipelineRunStorage,
    DuckDBPipelineRunStorage,
    FakePipelineRunStorage
)

def test_demo_pipeline_def_storage():
    st.session_state.clear()
    storage = DemoPipelineDefStorage()

    # Test create
    pipeline = {"pipeline_id": "p1", "title": "Test Pipeline"}
    storage.create(pipeline)
    assert len(storage.list_all()) == 1
    assert storage.list_all()[0]["pipeline_id"] == "p1"

    # Test delete
    storage.delete("p1")
    assert len(storage.list_all()) == 0

@patch("src.storage.pipeline_storage._get_write_connection")
@patch("src.storage.pipeline_storage.get_db_connection")
def test_duckdb_pipeline_def_storage(mock_get_db, mock_get_write):
    # Mock read connection
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_get_db.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    # Mock write connection
    mock_write_conn = MagicMock()
    mock_get_write.return_value = mock_write_conn

    storage = DuckDBPipelineDefStorage()

    # Test list_all
    mock_cursor.fetchall.return_value = [("p1", "Title", "Desc", "databricks", "j1", None, None, None, None, None, None, None, "user", None)]
    pipelines = storage.list_all()
    assert len(pipelines) == 1
    assert pipelines[0]["pipeline_id"] == "p1"
    mock_cursor.execute.assert_called_once()

    # Test create
    pipeline_dict = {
        "pipeline_id": "p2", "title": "T2", "description": "D", "backend": "b",
        "databricks_job_id": None, "adf_subscription_id": None, "adf_resource_group": None,
        "adf_factory_name": None, "adf_pipeline_name": None, "ado_organization": None,
        "ado_project": None, "ado_pipeline_id": None, "created_by": "u", "created_at": None
    }
    storage.create(pipeline_dict)
    mock_write_conn.execute.assert_called_once()
    assert "INSERT INTO user_data.pipeline_definitions" in mock_write_conn.execute.call_args[0][0]

    # Test delete
    mock_write_conn.reset_mock()
    storage.delete("p1")
    mock_write_conn.execute.assert_called_once()
    assert "DELETE FROM user_data.pipeline_definitions" in mock_write_conn.execute.call_args[0][0]

@patch("src.storage.pipeline_storage.get_db_connection")
@patch("src.storage.pipeline_storage.log")
def test_duckdb_pipeline_def_storage_list_error(mock_log, mock_get_db):
    mock_conn = MagicMock()
    mock_get_db.return_value = mock_conn
    mock_conn.cursor.side_effect = Exception("DB Error")

    storage = DuckDBPipelineDefStorage()

    assert storage.list_all() == []
    mock_log.warning.assert_called_once()

def test_fake_pipeline_def_storage():
    storage = FakePipelineDefStorage()

    storage.create({"pipeline_id": "1"})
    assert len(storage.list_all()) == 1

    storage.delete("1")
    assert len(storage.list_all()) == 0

def test_demo_pipeline_run_storage():
    st.session_state.clear()
    storage = DemoPipelineRunStorage()

    storage.upsert("p1", "run1", "user1")
    active = storage.get_active("p1")
    assert active["backend_run_id"] == "run1"
    assert active["status"] == "started"

    storage.update_status("p1", "completed")
    assert storage.get_active("p1")["status"] == "completed"

    storage.clear("p1")
    assert storage.get_active("p1") is None

@patch("src.storage.pipeline_storage._get_write_connection")
@patch("src.storage.pipeline_storage.get_db_connection")
def test_duckdb_pipeline_run_storage(mock_get_db, mock_get_write):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_get_db.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    mock_write_conn = MagicMock()
    mock_get_write.return_value = mock_write_conn

    storage = DuckDBPipelineRunStorage()

    # Test upsert
    storage.upsert("p1", "r1", "user")
    mock_write_conn.execute.assert_called_once()
    assert "INSERT INTO user_data.pipeline_runs" in mock_write_conn.execute.call_args[0][0]

    # Test get_active (exists)
    mock_cursor.fetchall.return_value = [("r1", "user", None, "started", None)]
    run = storage.get_active("p1")
    assert run["backend_run_id"] == "r1"

    # Test get_active (not exists)
    mock_cursor.fetchall.return_value = []
    assert storage.get_active("p2") is None

    # Test update_status
    mock_write_conn.reset_mock()
    storage.update_status("p1", "success")
    mock_write_conn.execute.assert_called_once()
    assert "UPDATE user_data.pipeline_runs SET status =" in mock_write_conn.execute.call_args[0][0]

    # Test clear
    mock_write_conn.reset_mock()
    storage.clear("p1")
    mock_write_conn.execute.assert_called_once()
    assert "DELETE FROM user_data.pipeline_runs" in mock_write_conn.execute.call_args[0][0]

@patch("src.storage.pipeline_storage.get_db_connection")
@patch("src.storage.pipeline_storage.log")
def test_duckdb_pipeline_run_storage_get_error(mock_log, mock_get_db):
    mock_conn = MagicMock()
    mock_get_db.return_value = mock_conn
    mock_conn.cursor.side_effect = Exception("DB Error")

    storage = DuckDBPipelineRunStorage()

    assert storage.get_active("p1") is None
    mock_log.warning.assert_called_once()

def test_fake_pipeline_run_storage():
    storage = FakePipelineRunStorage()

    storage.upsert("p1", "r1", "u")
    assert storage.get_active("p1")["backend_run_id"] == "r1"

    storage.update_status("p1", "failed")
    assert storage.get_active("p1")["status"] == "failed"

    storage.clear("p1")
    assert storage.get_active("p1") is None
