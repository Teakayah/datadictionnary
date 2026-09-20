from __future__ import annotations

import importlib.util
from pathlib import Path
from subprocess import CompletedProcess

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "auto_ci.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("scripts.auto_ci", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_build_environment_sets_ci_defaults():
    auto_ci = _load_module()

    env = auto_ci.build_environment({})

    assert env["ENABLE_MOCK_AUTH"] == "true"
    assert env["ENVIRONMENT"] == "development"
    assert env["DEMO_DATA"] == "true"
    assert env["TENANT_ID"] == "test-tenant"
    assert env["CLIENT_ID"] == "test-client"
    assert env["DUCKDB_PATH"] == ":memory:"


def test_build_environment_preserves_existing_values():
    auto_ci = _load_module()

    env = auto_ci.build_environment({"ENVIRONMENT": "production", "CLIENT_ID": "custom-client"})

    assert env["ENVIRONMENT"] == "production"
    assert env["CLIENT_ID"] == "custom-client"


def test_docs_are_dirty_only_for_html_changes():
    auto_ci = _load_module()

    assert auto_ci.docs_are_dirty(" M docs/architecture.html")
    assert auto_ci.docs_are_dirty("R  docs/old.html -> docs/new.html")
    assert not auto_ci.docs_are_dirty(" M docs/adr/001-duckdb-local-cache.md")
    assert not auto_ci.docs_are_dirty(" M docs/notes.html.txt")


def test_main_runs_pytest_and_docs_sync(monkeypatch):
    auto_ci = _load_module()
    commands = []

    def fake_run_command(command, **kwargs):
        commands.append((list(command), kwargs))
        if command[:3] == ["git", "status", "--porcelain"]:
            return CompletedProcess(command, 0, stdout="", stderr="")
        return CompletedProcess(command, 0)

    monkeypatch.setattr(auto_ci, "run_command", fake_run_command)

    exit_code = auto_ci.main(["--junit-xml", "test-results.xml"])

    assert exit_code == 0
    assert commands[0][0][:4] == [auto_ci.sys.executable, "-m", "pytest", "tests/"]
    assert "--ignore=tests/load" in commands[0][0]
    assert "--ignore=tests/test_load_smoke.py" in commands[0][0]
    assert "--ignore=tests/test_wcag_axe.py" in commands[0][0]
    assert "--ignore=tests/test_nav_render.py" in commands[0][0]
    assert "--junit-xml=test-results.xml" in commands[0][0]
    assert commands[1][0] == [auto_ci.sys.executable, "scripts/md_to_html.py"]
    assert commands[2][0] == ["git", "status", "--porcelain", "--", "docs"]


def test_check_docs_sync_raises_when_html_is_dirty(monkeypatch):
    auto_ci = _load_module()

    def fake_run_command(command, **kwargs):
        if command[:3] == ["git", "status", "--porcelain"]:
            return CompletedProcess(command, 0, stdout=" M docs/architecture.html\n", stderr="")
        return CompletedProcess(command, 0)

    monkeypatch.setattr(auto_ci, "run_command", fake_run_command)

    with pytest.raises(SystemExit, match="Generated HTML documentation is out of sync"):
        auto_ci.check_docs_sync(env={})
