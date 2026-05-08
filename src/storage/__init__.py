"""Storage abstraction — collapses the demo / DuckDB / Databricks branching
that used to be duplicated across src/cms.py, src/pipelines.py,
src/personalization.py, and src/audit.py.

Each entity has a Protocol (e.g. ``CMSStorage``) and one or more concrete
backends. The factory at the bottom of this file picks a backend based on
runtime env (demo mode, DuckDB availability) on every call — no caching,
so tests can flip the env between calls without surprising behaviour.

Test-only helpers (``FakeCMSStorage``) ship in the storage module too so
downstream consumers don't need to redefine in-memory fakes.

Migration order (from TODO.md #4):
  1. CMS                  — done in commit feat/storage-cms
  2. Pipelines            — open
  3. Preferences + site_settings — open
  4. Audit + business name overrides — open
"""

from __future__ import annotations

from src.config import is_demo_mode
from src.db.duckdb_adapter import _duckdb_available
from src.storage.cms_storage import (  # noqa: F401
    CMSStorage,
    DemoCMSStorage,
    DuckDBCMSStorage,
    FakeCMSStorage,
)


def get_cms_storage() -> CMSStorage:
    """Pick a CMS backend based on runtime env.

    Demo mode and missing DuckDB both fall back to session-state storage —
    DuckDB is the only persistent backend today. (CMS posts have always
    been session-only when DuckDB is absent; this preserves that.)

    Not cached: re-evaluating ``is_demo_mode()`` and ``_duckdb_available()``
    on every call costs ~microseconds and keeps tests honest. Tests can
    inject a ``FakeCMSStorage`` via ``mock.patch('src.cms.get_cms_storage')``.
    """
    if is_demo_mode() or not _duckdb_available():
        return DemoCMSStorage()
    return DuckDBCMSStorage()
