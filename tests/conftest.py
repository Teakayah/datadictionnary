"""
Pytest configuration for the Data Dictionary test suite.

Before any test module is imported, we inject lightweight stubs for packages
that are not (and need not be) installed in the test environment:

  - databricks / databricks.sql  — would open a real SQL Warehouse
  - msal                         — would initiate Entra ID OAuth
  - dotenv                       — environment loading (not needed in tests)

AppTest runs app.py via exec() in a fresh module namespace (it is NOT
registered as "app" in sys.modules), so the mocks must live at the
dependency level — i.e. in sys.modules["databricks.sql"] — rather than
being patched via patch("app.run_query").
"""

from __future__ import annotations

import sys
import pandas as pd
import requests
import os
import pytest
import streamlit as st
from unittest.mock import MagicMock


# ── AppTest ButtonGroup.value fix ─────────────────────────────────────────────
# Streamlit AppTest's ButtonGroup.value reads session_state and returns whatever
# is stored there. For st.segmented_control with selection_mode="single", the
# stored value is a plain string. ButtonGroup.indices then does
#   [format_func(v) for v in self.value]
# and iterating over a string yields individual characters, causing:
#   ValueError: content: "N" is not in list
# Wrap non-list values in a list so the iteration works correctly.
try:
    from streamlit.testing.v1.element_tree import ButtonGroup as _BG
    _orig_value_fget = _BG.value.fget

    def _patched_value(self):
        v = _orig_value_fget(self)
        if v is None:
            return []
        if not isinstance(v, list):
            return [v]
        return v

    _BG.value = property(_patched_value)
except Exception:
    pass  # if Streamlit internals change, fail loudly in the tests themselves


# ── Test environment — enable mock auth so AppTest runs without Entra ID ──────
import os as _os
_os.environ.setdefault("ENABLE_MOCK_AUTH", "true")
_os.environ.setdefault("ENVIRONMENT", "development")
_os.environ.setdefault("DEMO_DATA", "true")
_os.environ["DUCKDB_PATH"] = ""  # Force empty to ensure hermetic tests
# Required by src.config / src.api.auth at import time so startup validation passes.
_os.environ.setdefault("TENANT_ID", "test-tenant-id")
_os.environ.setdefault("CLIENT_ID", "test-client-id")

# ── Stub missing packages ─────────────────────────────────────────────────────

def _make_stub(name: str) -> MagicMock:
    m = MagicMock()
    m.__name__ = name
    m.__spec__ = None
    return m


# databricks.sql — app.py does: from databricks import sql; sql.connect(...)
_databricks = _make_stub("databricks")
_databricks_sql = _make_stub("databricks.sql")
_databricks.sql = _databricks_sql
sys.modules.setdefault("databricks", _databricks)
sys.modules.setdefault("databricks.sql", _databricks_sql)

# msal — used only in real-auth path; tests run in mock-auth mode
sys.modules.setdefault("msal", _make_stub("msal"))

# dotenv — safe to no-op
_dotenv = _make_stub("dotenv")
_dotenv.load_dotenv = lambda *a, **kw: None
sys.modules.setdefault("dotenv", _dotenv)


# ── SQL cursor helper ─────────────────────────────────────────────────────────
# app.py's run_query() follows this chain:
#   conn = sql.connect(...) → conn.cursor() as cursor → cursor.execute(...);
#   cursor.fetchall_as_pandas()
#
# All calls go through the same MagicMock chain because MagicMock.return_value
# is a fixed attribute (not a new object per call).

def get_db_cursor() -> MagicMock:
    """Return the mock cursor object that run_query() will use."""
    return (
        _databricks_sql.connect.return_value
                       .cursor.return_value
                       .__enter__.return_value
    )


@pytest.fixture(autouse=True)
def reset_sql_mock():
    """Reset the SQL cursor mock before every test.

    This prevents call-history from one test leaking into assertions in
    the next, and sets a safe default return value of an empty DataFrame.
    """
    st.cache_data.clear()
    cursor = get_db_cursor()
    cursor.reset_mock()
    cursor.fetchall_as_pandas.return_value = pd.DataFrame()
    cursor.fetchall_as_pandas.side_effect = None
    cursor.execute.side_effect = None
    yield
    cursor.reset_mock()
    cursor.execute.side_effect = None


def sql_returns(*dataframes: pd.DataFrame, side_effect=None) -> None:
    """Configure the SQL mock to return the given DataFrames in order."""
    cursor = get_db_cursor()
    cursor.reset_mock()
    if side_effect:
        cursor.fetchall_as_pandas.side_effect = side_effect
    else:
        def default_side_effect(*args, **kwargs):
            if hasattr(default_side_effect, "index") and default_side_effect.index < len(dataframes):
                df = dataframes[default_side_effect.index]
                default_side_effect.index += 1
                return df
            return pd.DataFrame()
        default_side_effect.index = 0
        cursor.fetchall_as_pandas.side_effect = default_side_effect
    cursor.fetchall_as_pandas.return_value = None


APP_URL = os.getenv("LOAD_TEST_HOST", "http://localhost:8501")

def _server_is_up() -> bool:
    try:
        return requests.get(f"{APP_URL}/_stcore/health", timeout=3).status_code == 200
    except requests.ConnectionError:
        return False

@pytest.fixture(scope="session")
def require_server():
    """Skip tests if the Streamlit app is not reachable."""
    if not _server_is_up():
        pytest.skip(f"Streamlit app not reachable at {APP_URL}")
