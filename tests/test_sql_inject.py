import os
import duckdb
from unittest.mock import patch

def test_sql_inject(tmp_path):
    # Test path with single quotes
    evil_path = str(tmp_path / "evil'path.duckdb")

    # ensure directory exists
    os.makedirs(os.path.dirname(evil_path), exist_ok=True)

    # write empty duckdb file
    duckdb.connect(evil_path).close()

    with patch.dict(os.environ, {"DUCKDB_PATH": evil_path}):
        import src.config as config
        import importlib
        importlib.reload(config)

        # Test the module again
        import src.db.duckdb_adapter as adapter
        importlib.reload(adapter)

        con = adapter._get_shared_duckdb_connection()
        # Should now be None due to ValueError caught and logged in duckdb_adapter
        assert con is None

        # Test daemon_db (with a separate mock so we don't conflict the user_data detachment)
    with patch.dict(os.environ, {"DUCKDB_PATH": str(tmp_path / "evil'path2.duckdb")}):
        import src.config as config
        importlib.reload(config)
        import src.sync.daemon_db as daemon_db
        importlib.reload(daemon_db)

        # create the file
        duckdb.connect(str(tmp_path / "evil'path2.duckdb")).close()

        import pytest
        with pytest.raises(ValueError, match="DUCKDB_PATH contains invalid characters for SQL ATTACH"):
            con2 = daemon_db.DaemonConn()
