from __future__ import annotations
"""Process-local DuckDB connection for the sidecar sync daemon.

The Streamlit app uses a Streamlit-cached singleton (src.db.duckdb_adapter
._get_shared_duckdb_connection). The daemon runs outside Streamlit and
needs its own connection. This module provides a thin wrapper that
mirrors enough of _DuckDBConn that src.sync.push and src.sync.dr_resync
can be called with either.
"""


import logging
from pathlib import Path

import duckdb

from src.config import CATALOG_CACHE, DUCKDB_PATH, USER_DATA_PATH
from src.db.duckdb_adapter import _DuckDBCursor, _initialize_schema

log = logging.getLogger(__name__)


class DaemonConn:
    """Connection-like wrapper around a process-local DuckDB connection.

    The connection is in-memory; the catalog cache and user_data files are
    ATTACH'd. Catalog is read-only — DR resync only writes to user_data.
    """

    def __init__(self) -> None:
        if not USER_DATA_PATH:
            raise RuntimeError(
                "USER_DATA_PATH (derived from DUCKDB_PATH) is empty — "
                "set DUCKDB_PATH in the environment before starting the daemon."
            )
        self._con = duckdb.connect(":memory:")

        import uuid

        # Securely quote paths using random dollar-quotes, stripping null-bytes that truncate parsing
        q_token = f"q_{uuid.uuid4().hex}"
        safe_duckdb_path = DUCKDB_PATH.replace('\x00', '') if DUCKDB_PATH else ""
        safe_user_data_path = USER_DATA_PATH.replace('\x00', '') if USER_DATA_PATH else ""
        safe_catalog_cache = CATALOG_CACHE.replace('"', '""')

        if DUCKDB_PATH and Path(DUCKDB_PATH).exists():
            self._con.execute(
                f'ATTACH ${q_token}${safe_duckdb_path}${q_token}$ AS "{safe_catalog_cache}" (READ_ONLY)'  # nosec B608
            )
        else:
            log.info(
                "Catalog file %s missing — daemon will run without DR resync from cache.",
                DUCKDB_PATH,
            )
        self._con.execute(f'ATTACH IF NOT EXISTS ${q_token}${safe_user_data_path}${q_token}$ AS "user_data"')  # nosec B608
        _initialize_schema(self._con)

    def cursor(self) -> _DuckDBCursor:
        return _DuckDBCursor(self._con)

    def execute(self, sql: str, params=None) -> _DuckDBCursor:
        cur = _DuckDBCursor(self._con)
        cur.execute(sql, params)
        return cur

    def close(self) -> None:
        try:
            self._con.close()
        except Exception:
            pass

    def __enter__(self) -> "DaemonConn":
        return self

    def __exit__(self, *_) -> None:
        # Owner is the daemon main loop — don't close here.
        pass

    @property
    def open(self) -> bool:
        return self._con is not None
