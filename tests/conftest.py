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
import pytest
import streamlit as st
from unittest.mock import MagicMock
import types

# Streamlit's @st.cache_resource with a generator yield returns the generator in test bare mode.
# We must mock st.cache_resource to correctly unwrap the generator in our tests.
original_cache_resource = st.cache_resource
def mock_cache_resource(*args, **kwargs):
    # Determine if the call is a decorator with arguments (e.g. @cache_resource(ttl=...))
    # or without arguments (e.g. @cache_resource)
    is_called_with_args = not (len(args) == 1 and callable(args[0]) and len(kwargs) == 0)

    def decorator(func):
        if is_called_with_args:
            cached_func = original_cache_resource(*args, **kwargs)(func)
        else:
            cached_func = original_cache_resource(func)

        def wrapper(*f_args, **f_kwargs):
            # In test mode, because of clear(), we might be calling the underlying function
            # and caching its generator object. The issue is that the SAME generator is
            # returned multiple times across test steps, and `next(res)` raises StopIteration
            # because the generator was already consumed.
            # To fix this, we should NOT execute the cached_func generator.
            # Instead, we just execute the original `func` if it's returning a generator
            # or recreate it. Streamlit handles this internally by storing the yielded value,
            # but our test stub relies on the original cache.
            # We bypass the streamilt cache entirely for generators to avoid StopIteration!
            res = func(*f_args, **f_kwargs)
            if isinstance(res, types.GeneratorType):
                return next(res)
            # If not a generator, we just return the cached_func result
            return cached_func(*f_args, **f_kwargs)
        return wrapper

    if not is_called_with_args:
        return decorator(args[0])
    return decorator

mock_cache_resource.clear = original_cache_resource.clear
st.cache_resource = mock_cache_resource


# ── Test environment — enable mock auth so AppTest runs without Entra ID ──────
import os as _os
_os.environ.setdefault("ENABLE_MOCK_AUTH", "true")

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
#   sql.connect(...) as conn → conn.cursor() as cursor → cursor.execute(...);
#   cursor.fetchall_as_pandas()
#
# All calls go through the same MagicMock chain because MagicMock.return_value
# is a fixed attribute (not a new object per call).

def get_db_cursor() -> MagicMock:
    """Return the mock cursor object that run_query() will use."""
    # When using @st.cache_resource with a yield, the mock generator
    # returned by get_database_connection() needs to be stepped or mocked correctly
    # because st.cache_resource returns the yielded value in normal Streamlit flow,
    # but in test mode it returns the generator or we can just mock st.cache_resource
    # Let's bypass cache_resource completely in test or intercept it.
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
    original_cache_resource.clear()
    cursor = get_db_cursor()
    cursor.reset_mock()
    cursor.fetchall_as_pandas.return_value = pd.DataFrame()
    cursor.fetchall_as_pandas.side_effect = None
    yield
    cursor.reset_mock()


def sql_returns(*dataframes: pd.DataFrame) -> None:
    """Configure the SQL mock to return the given DataFrames in order.

    Call this at the top of any test that needs run_query() to return data.
    If only one DataFrame is passed, it is returned for every query.
    If multiple are passed, they are consumed in order (first call → first df,
    second call → second df, etc.).
    """
    cursor = get_db_cursor()
    cursor.reset_mock()
    if len(dataframes) == 1:
        cursor.fetchall_as_pandas.return_value = dataframes[0]
        cursor.fetchall_as_pandas.side_effect = None
    else:
        cursor.fetchall_as_pandas.side_effect = list(dataframes)
        cursor.fetchall_as_pandas.return_value = None
