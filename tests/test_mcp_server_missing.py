import pytest
from src.mcp_server.server import list_tables
import asyncio
from unittest.mock import patch
import pandas as pd
import json

@pytest.mark.anyio
async def test_list_tables_schema_only(monkeypatch):
    """
    Test that the list_tables function properly filters by schema alone,
    hitting the previously uncovered 'elif schema:' branch in src.mcp_server.server.py.
    """
    # Arrange
    monkeypatch.setenv("DUCKDB_PATH", ":memory:")

    mock_df = pd.DataFrame([
        {"catalog_name": "main", "schema_name": "sales", "table_name": "customers"},
        {"catalog_name": "main", "schema_name": "finance", "table_name": "accounts"}
    ])

    with patch("src.api.queries.get_authorized_tables", return_value=mock_df):
        with patch("src.mcp_server.server.redis_cache.get", return_value=None):
            with patch("src.mcp_server.server.redis_cache.set", return_value=None):
                with patch("src.mcp_server.server._require_user") as mock_user:
                    class DummyUser:
                        groups = ["users"]
                    mock_user.return_value = DummyUser()

                    # Act
                    res = await list_tables(schema="sales")
                    data = json.loads(res)

                    # Assert
                    assert isinstance(data, list)
                    assert len(data) == 1
                    assert data[0]["table_name"] == "customers"
                    assert data[0]["schema_name"] == "sales"
