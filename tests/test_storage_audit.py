from unittest.mock import patch, MagicMock
import streamlit as st
import pandas as pd

from src.storage.audit_storage import (
    DemoAuditStorage,
    DuckDBAuditStorage,
    FakeAuditStorage,
    DemoBusinessNameOverrideStorage,
    DuckDBBusinessNameOverrideStorage,
    FakeBusinessNameOverrideStorage,
    ColumnOverride
)

def test_demo_audit_storage():
    st.session_state.clear()
    storage = DemoAuditStorage()

    event1 = {"event_id": "1", "event_type": "update"}
    storage.append(event1)

    assert "demo_audit_log" in st.session_state
    log = st.session_state["demo_audit_log"]
    assert len(log) == 1
    assert log[0]["event_id"] == "1"
    assert "created_at" in log[0]

@patch("src.storage.audit_storage._get_write_connection")
def test_duckdb_audit_storage_success(mock_get_conn):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_get_conn.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    storage = DuckDBAuditStorage()
    event = {
        "event_id": "1",
        "event_type": "update",
        "object_type": "table",
        "object_name": "main.sales.orders",
        "actor_email": "test@example.com",
        "old_value": "old",
        "new_value": "new"
    }

    storage.append(event)
    mock_cursor.execute_write.assert_called_once()
    assert "INSERT INTO user_data.audit_log" in mock_cursor.execute_write.call_args[0][0]

@patch("src.storage.audit_storage._get_write_connection")
@patch("src.storage.audit_storage.log")
def test_duckdb_audit_storage_failure(mock_log, mock_get_conn):
    mock_get_conn.side_effect = Exception("DB Error")

    storage = DuckDBAuditStorage()
    storage.append({"event_id": "err_1"})

    mock_log.warning.assert_called_once()
    assert mock_log.warning.call_args[0][1] == "err_1"

def test_fake_audit_storage():
    storage = FakeAuditStorage()
    storage.append({"event_id": "1"})
    assert len(storage.events) == 1

def test_demo_business_name_override_storage():
    st.session_state.clear()
    storage = DemoBusinessNameOverrideStorage()

    override = ColumnOverride(
        table_full_name="main.sales.orders",
        column_name="id",
        business_name="Order ID",
        definition="The unique identifier for an order",
        edited_by="user1",
        status="pending_approval"
    )

    # Test upsert pending
    storage.upsert(override)

    pending = storage.list_pending()
    assert len(pending) == 1
    assert pending[0]["column_name"] == "id"

    # Test get_for_table (should not include pending)
    table_data = storage.get_for_table("main.sales.orders")
    assert "id" not in table_data

    # Test approve
    storage.approve("main.sales.orders", "id")
    pending = storage.list_pending()
    assert len(pending) == 0

    table_data = storage.get_for_table("main.sales.orders")
    assert "id" in table_data
    assert table_data["id"]["business_name"] == "Order ID"

    # Test upsert published
    override.status = "published"
    override.business_name = "Primary Order ID"
    storage.upsert(override)

    table_data = storage.get_for_table("main.sales.orders")
    assert table_data["id"]["business_name"] == "Primary Order ID"

    # Test reject
    storage.upsert(ColumnOverride(
        table_full_name="main.sales.orders",
        column_name="amount",
        business_name="Order Amount",
        definition="",
        edited_by="user2",
        status="pending_approval"
    ))
    assert len(storage.list_pending()) == 1
    storage.reject("main.sales.orders", "amount")
    assert len(storage.list_pending()) == 0
    assert "amount" not in storage.get_for_table("main.sales.orders")


@patch("src.storage.audit_storage.get_db_connection")
def test_duckdb_business_name_override_storage_get_all(mock_get_db):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_get_db.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_cursor.fetchall_as_pandas.return_value = pd.DataFrame({
        "column_name": ["id", "amount"],
        "business_name": ["Order ID", ""],
        "definition": ["The identifier", ""],
        "edited_by": ["user1", "user2"],
        "edited_at": ["2023", "2023"]
    })

    storage = DuckDBBusinessNameOverrideStorage()
    res = storage.get_for_table("main.sales.orders")

    assert "id" in res
    assert res["id"]["business_name"] == "Order ID"
    assert res["id"]["definition"] == "The identifier"

    assert "amount" in res
    assert res["amount"]["business_name"] == ""

@patch("src.storage.audit_storage._get_write_connection")
def test_duckdb_business_name_override_storage_upsert_published(mock_get_conn):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_get_conn.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    storage = DuckDBBusinessNameOverrideStorage()
    override = ColumnOverride(
        table_full_name="main.sales.orders",
        column_name="id",
        business_name="Order ID",
        definition="The ID",
        edited_by="user1",
        status="published"
    )

    storage.upsert(override)
    mock_cursor.execute_write.assert_called_once()
    assert "INSERT INTO user_data.business_name_overrides" in mock_cursor.execute_write.call_args[0][0]

@patch("src.storage.audit_storage._get_write_connection")
def test_duckdb_business_name_override_storage_upsert_pending(mock_get_conn):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_get_conn.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    storage = DuckDBBusinessNameOverrideStorage()
    override = ColumnOverride(
        table_full_name="main.sales.orders",
        column_name="id",
        business_name="Order ID",
        definition="The ID",
        edited_by="user1",
        status="pending_approval"
    )

    storage.upsert(override)
    mock_cursor.execute_write.assert_called_once()
    assert "INSERT INTO user_data.business_name_overrides" in mock_cursor.execute_write.call_args[0][0]

@patch("src.storage.audit_storage.get_db_connection")
def test_duckdb_business_name_override_storage_list_pending(mock_get_db):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_get_db.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_cursor.fetchall_as_pandas.return_value = pd.DataFrame({
        "table_full_name": ["main.sales.orders"],
        "column_name": ["id"],
        "business_name": ["Order ID"],
        "definition": ["The ID"],
        "edited_by": ["user1"],
        "edited_at": [pd.Timestamp("2023-01-01")]
    })

    storage = DuckDBBusinessNameOverrideStorage()
    res = storage.list_pending()
    assert len(res) == 1
    assert res[0]["column_name"] == "id"

@patch("src.storage.audit_storage._get_write_connection")
@patch("src.storage.audit_storage.get_db_connection")
def test_duckdb_business_name_override_storage_approve(mock_get_db, mock_get_conn):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_get_conn.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    mock_read_conn = MagicMock()
    mock_read_cursor = MagicMock()
    mock_get_db.return_value = mock_read_conn
    mock_read_conn.cursor.return_value.__enter__.return_value = mock_read_cursor

    mock_read_cursor.fetchall_as_pandas.return_value = pd.DataFrame({
        "business_name": ["Order ID"],
        "definition": ["The ID"],
        "edited_by": ["user1"]
    })

    storage = DuckDBBusinessNameOverrideStorage()
    storage.approve("main.sales.orders", "id")

    # 3 execute_write calls: BEGIN, COMMENT, DELETE
    assert mock_cursor.execute_write.call_count == 1
    assert "UPDATE user_data.business_name_overrides SET status = 'published'" in mock_cursor.execute_write.call_args[0][0]

@patch("src.storage.audit_storage._get_write_connection")
@patch("src.storage.audit_storage.get_db_connection")
def test_duckdb_business_name_override_storage_approve_not_found(mock_get_db, mock_get_conn):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_get_conn.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    mock_read_conn = MagicMock()
    mock_read_cursor = MagicMock()
    mock_get_db.return_value = mock_read_conn
    mock_read_conn.cursor.return_value.__enter__.return_value = mock_read_cursor

    mock_read_cursor.fetchall_as_pandas.return_value = pd.DataFrame()

    storage = DuckDBBusinessNameOverrideStorage()
    storage.approve("main.sales.orders", "id")

    # Only DELETE is called
    assert mock_cursor.execute_write.call_count == 1
    assert "UPDATE user_data.business_name_overrides SET status = 'published'" in mock_cursor.execute_write.call_args[0][0]

@patch("src.storage.audit_storage._get_write_connection")
def test_duckdb_business_name_override_storage_reject(mock_get_conn):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_get_conn.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    storage = DuckDBBusinessNameOverrideStorage()
    storage.reject("main.sales.orders", "id")

    mock_cursor.execute_write.assert_called_once()
    assert "DELETE FROM user_data.business_name_overrides" in mock_cursor.execute_write.call_args[0][0]



def test_fake_business_name_override_storage():
    storage = FakeBusinessNameOverrideStorage()

    # Test get_columns
    cols = storage.get_columns("main.sales.orders")
    assert isinstance(cols, pd.DataFrame)

    override = ColumnOverride(
        table_full_name="main.sales.orders",
        column_name="id",
        business_name="Order ID",
        definition="The ID",
        edited_by="user1",
        status="pending_approval"
    )

    storage.upsert(override)

    pending = storage.list_pending()
    assert len(pending) == 1
    assert pending[0]["column_name"] == "id"

    storage.approve("main.sales.orders", "id")
    assert len(storage.list_pending()) == 0

    table_data = storage.get_for_table("main.sales.orders")
    assert "id" in table_data
    assert table_data["id"]["business_name"] == "Order ID"

    # Upsert published
    override.status = "published"
    storage.upsert(override)

    # Test reject
    storage.upsert(ColumnOverride(
        table_full_name="main.sales.orders",
        column_name="amount",
        business_name="Order Amount",
        definition="",
        edited_by="user2",
        status="pending_approval"
    ))
    assert len(storage.list_pending()) == 1
    storage.reject("main.sales.orders", "amount")
    assert len(storage.list_pending()) == 0
