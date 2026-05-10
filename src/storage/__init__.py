from __future__ import annotations
from typing import Any, Callable, Optional, Protocol, runtime_checkable
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
from src.storage.preference_storage import (  # noqa: F401
    DemoPreferenceStorage,
    DemoSiteSettingStorage,
    DuckDBPreferenceStorage,
    DuckDBSiteSettingStorage,
    FakePreferenceStorage,
    FakeSiteSettingStorage,
    PreferenceStorage,
    SiteSettingStorage,
)
from src.storage.audit_storage import (  # noqa: F401
    AuditStorage,
    BusinessNameOverrideStorage,
    DemoAuditStorage,
    DemoBusinessNameOverrideStorage,
    DuckDBAuditStorage,
    DuckDBBusinessNameOverrideStorage,
    FakeAuditStorage,
    FakeBusinessNameOverrideStorage,
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


def get_preference_storage() -> PreferenceStorage:
    """Pick a user-preferences backend based on runtime env.

    Demo mode falls back to a no-op backend — preferences are kept only
    in ``st.session_state`` (handled by ``src.personalization``).
    """
    return (
        DemoPreferenceStorage() if _use_demo_backend()
        else DuckDBPreferenceStorage()
    )


def get_site_setting_storage() -> SiteSettingStorage:
    """Pick a site-settings backend based on runtime env.

    Demo mode falls back to a no-op backend — global toggles only persist
    via the in-process session cache.
    """
    return (
        DemoSiteSettingStorage() if _use_demo_backend()
        else DuckDBSiteSettingStorage()
    )


def get_audit_storage() -> AuditStorage:
    """Pick an audit-log backend based on runtime env.

    Demo → session-state; otherwise DuckDB (``user_data.audit_log``).
    Direct Databricks writes were removed in TODO #7 — the sidecar daemon
    pushes audit events via ``enqueue_sync`` instead.
    """
    return DemoAuditStorage() if _use_demo_backend() else DuckDBAuditStorage()


def get_business_name_override_storage() -> BusinessNameOverrideStorage:
    """Pick a business-name-overrides backend (demo / DuckDB)."""
    return (
        DemoBusinessNameOverrideStorage() if _use_demo_backend()
        else DuckDBBusinessNameOverrideStorage()
    )
