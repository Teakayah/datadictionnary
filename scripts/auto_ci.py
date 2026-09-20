#!/usr/bin/env python3
"""Run the repository's standard CI checks locally or in automation."""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEST_ENV = {
    "ENABLE_MOCK_AUTH": "true",
    "ENVIRONMENT": "development",
    "DEMO_DATA": "true",
    "TENANT_ID": "test-tenant",
    "CLIENT_ID": "test-client",
    "DUCKDB_PATH": ":memory:",
}
PYTEST_IGNORES = (
    "tests/load",
    "tests/test_load_smoke.py",
    "tests/test_wcag_axe.py",
    "tests/test_nav_render.py",
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the repository's standard CI test and documentation checks.",
    )
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Skip the pytest suite.",
    )
    parser.add_argument(
        "--skip-docs-sync",
        action="store_true",
        help="Skip the generated HTML documentation sync check.",
    )
    parser.add_argument(
        "--junit-xml",
        help="Optional pytest JUnit XML output path.",
    )
    return parser.parse_args(argv)


def build_environment(base_env: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(base_env or os.environ)
    for key, value in DEFAULT_TEST_ENV.items():
        if not env.get(key):
            env[key] = value
    return env


def run_command(
    command: Sequence[str],
    *,
    env: dict[str, str],
    check: bool = True,
    capture_output: bool = False,
    text: bool = False,
) -> subprocess.CompletedProcess[str]:
    print(f"+ {shlex.join(command)}")
    return subprocess.run(
        list(command),
        cwd=REPO_ROOT,
        env=env,
        check=check,
        capture_output=capture_output,
        text=text,
    )


def run_pytest(*, env: dict[str, str], junit_xml: str | None = None) -> None:
    command = [
        sys.executable,
        "-m",
        "pytest",
        "tests/",
        "-q",
        "--tb=short",
    ]
    command.extend(f"--ignore={path}" for path in PYTEST_IGNORES)
    if junit_xml:
        command.append(f"--junit-xml={junit_xml}")
    run_command(command, env=env)


def docs_are_dirty(status_output: str) -> bool:
    for line in status_output.splitlines():
        if not line.strip():
            continue
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1].strip()
        if path.endswith(".html"):
            return True
    return False


def check_docs_sync(*, env: dict[str, str]) -> None:
    run_command([sys.executable, "scripts/md_to_html.py"], env=env)
    status = run_command(
        ["git", "status", "--porcelain", "--untracked-files=all", "--", "docs"],
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    if docs_are_dirty(status.stdout):
        run_command(["git", "diff", "--", "docs"], env=env, check=False)
        raise SystemExit(
            "Generated HTML documentation is out of sync. "
            "Run 'python scripts/md_to_html.py' and commit the resulting docs/*.html changes.",
        )


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    env = build_environment()

    if not args.skip_tests:
        run_pytest(env=env, junit_xml=args.junit_xml)

    if not args.skip_docs_sync:
        check_docs_sync(env=env)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
