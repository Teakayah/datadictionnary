from __future__ import annotations

import pytest
from src.config import is_demo_mode


@pytest.mark.parametrize("env_val,expected", [
    ("true", True),
    ("TRUE", True),
    ("True", True),
    ("false", False),
    ("FALSE", False),
    ("False", False),
    ("0", False),
    ("1", False),
    ("", False),
    ("anything_else", False)
])
def test_is_demo_mode(monkeypatch, env_val: str, expected: bool):
    """Test that is_demo_mode correctly parses the DEMO_DATA environment variable."""
    monkeypatch.setenv("DEMO_DATA", env_val)
    assert is_demo_mode() is expected


def test_is_demo_mode_unset(monkeypatch):
    """Test that is_demo_mode defaults to False when DEMO_DATA is unset."""
    monkeypatch.delenv("DEMO_DATA", raising=False)
    assert is_demo_mode() is False


def test_is_demo_mode_mixed_case(monkeypatch):
    """Test that is_demo_mode correctly parses mixed case environment variables."""
    monkeypatch.setenv("DEMO_DATA", "tRuE")
    assert is_demo_mode() is True
    monkeypatch.setenv("DEMO_DATA", "FaLsE")
    assert is_demo_mode() is False
