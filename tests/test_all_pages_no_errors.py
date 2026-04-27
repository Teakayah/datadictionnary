from __future__ import annotations

import os
from streamlit.testing.v1 import AppTest
import pytest
from tests.conftest import sql_returns
import pandas as pd

APP_PATH = os.path.join(os.path.dirname(__file__), "..", "app.py")

def make_tables_df() -> pd.DataFrame:
    return pd.DataFrame({
        "full_name":         ["main.sales.orders", "main.sales.customers"],
        "catalog_name":      ["main", "main"],
        "schema_name":       ["sales", "sales"],
        "table_name":        ["orders", "customers"],
        "table_description": ["All customer orders", "Customer master data"],
        "table_type":        ["TABLE", "TABLE"],
        "updated_at":        [pd.Timestamp("2026-04-22 10:00"), pd.Timestamp("2026-04-21 08:00")],
    })

def make_health_col_stats() -> pd.DataFrame:
    return pd.DataFrame({"total": [10], "with_desc": [7]})

@pytest.fixture
def auth_app(monkeypatch):
    monkeypatch.setenv("DEMO_DATA", "false")
    monkeypatch.setenv("EDITOR_GROUPS", "finance_dept_id,all_employees_id")
    monkeypatch.setenv("ADMIN_GROUPS", "finance_dept_id,all_employees_id")
    at = AppTest.from_file(APP_PATH, default_timeout=15)
    at.session_state["authenticated"] = True
    at.session_state["user_groups"] = ["finance_dept_id", "all_employees_id"]
    at.session_state["user_name"] = "Finance User"
    return at

def test_no_errors_on_search(auth_app):
    sql_returns(make_tables_df())
    auth_app.query_params["tab"] = "search"
    auth_app.run()
    assert not auth_app.exception
    assert not auth_app.error

def test_no_errors_on_catalog(auth_app):
    sql_returns(make_tables_df())
    auth_app.query_params["tab"] = "catalog"
    auth_app.run()
    assert not auth_app.exception
    assert not auth_app.error

def test_no_errors_on_glossary(auth_app):
    sql_returns(make_tables_df())
    auth_app.query_params["tab"] = "glossary"
    auth_app.run()
    assert not auth_app.exception
    assert not auth_app.error

def test_no_errors_on_discovery(auth_app):
    sql_returns(make_tables_df())
    auth_app.query_params["tab"] = "discovery"
    auth_app.run()
    assert not auth_app.exception
    assert not auth_app.error

def test_no_errors_on_health(auth_app):
    sql_returns(make_tables_df(), make_health_col_stats())
    auth_app.query_params["tab"] = "health"
    auth_app.run()
    assert not auth_app.exception
    assert not auth_app.error

def test_no_errors_on_admin(auth_app):
    sql_returns(make_tables_df())
    auth_app.query_params["tab"] = "admin"
    auth_app.run()
    assert not auth_app.exception
    assert not auth_app.error
