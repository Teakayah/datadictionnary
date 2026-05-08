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
from src.storage.pipeline_storage import (  # noqa: F401
    DemoPipelineDefStorage,
    DemoPipelineRunStorage,
    DuckDBPipelineDefStorage,
    DuckDBPipelineRunStorage,
    FakePipelineDefStorage,
    FakePipelineRunStorage,
    PipelineDefStorage,
    PipelineRunStorage,
)


def _use_demo_backend() -> bool:
    """Single source of truth for the demo/duckdb routing decision.

    Demo mode and missing DuckDB both fall back to session-state storage —
    DuckDB is the only persistent backend today.
    """
    return is_demo_mode() or not _duckdb_available()


def get_cms_storage() -> CMSStorage:
    """Pick a CMS backend based on runtime env.

    Not cached: re-evaluating ``is_demo_mode()`` and ``_duckdb_available()``
    on every call costs ~microseconds and keeps tests honest. Tests can
    inject a ``FakeCMSStorage`` via ``mock.patch('src.cms.get_cms_storage')``.
    """
    return DemoCMSStorage() if _use_demo_backend() else DuckDBCMSStorage()


def get_pipeline_def_storage() -> PipelineDefStorage:
    """Pick a pipeline-definitions backend based on runtime env."""
    return (
        DemoPipelineDefStorage() if _use_demo_backend()
        else DuckDBPipelineDefStorage()
    )


def get_pipeline_run_storage() -> PipelineRunStorage:
    """Pick a pipeline-runs backend based on runtime env."""
    return (
        DemoPipelineRunStorage() if _use_demo_backend()
        else DuckDBPipelineRunStorage()
    )
