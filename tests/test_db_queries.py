"""Tests for src/db/queries.py."""

from __future__ import annotations
import pandas as pd
from unittest.mock import patch
from src.db.queries import _fetch_metadata_for_fns

def test_fetch_metadata_for_fns_empty():
    df = _fetch_metadata_for_fns([], ("group1",))
    assert df.empty

@patch("src.db.queries.run_query")
def test_fetch_metadata_for_fns_with_groups(mock_run_query):
    mock_run_query.return_value = pd.DataFrame([{"full_name": "c.s.t"}])

    df = _fetch_metadata_for_fns(["c.s.t"], ("group1", "group2"))

    assert not df.empty
    mock_run_query.assert_called_once()
    sql, params = mock_run_query.call_args[0]

    assert "%(group_0)s" in sql
    assert "%(group_1)s" in sql
    assert "SELECT unnest(%(fns)s)" in sql
    assert params["fns"] == ["c.s.t"]
    assert params["group_0"] == "group1"
    assert params["group_1"] == "group2"

@patch("src.db.queries.run_query")
def test_fetch_metadata_for_fns_no_groups(mock_run_query):
    mock_run_query.return_value = pd.DataFrame([{"full_name": "c.s.t"}])

    df = _fetch_metadata_for_fns(["c.s.t"], ())

    assert not df.empty
    mock_run_query.assert_called_once()
    sql, params = mock_run_query.call_args[0]

    assert "''" in sql # group placeholders fallback
    assert "SELECT unnest(%(fns)s)" in sql
    assert params["fns"] == ["c.s.t"]
    assert "group_0" not in params
