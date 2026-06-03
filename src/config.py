from __future__ import annotations
"""Configuration constants for the Data Dictionary application.

This module owns all environment-variable reads and compile-time constants.
No other module should call os.getenv() for these values — import from here.
Only stdlib (os) is imported so this module is safe to import in the test
environment where databricks, msal, and dotenv are stubbed.
"""

import os

# ── Entra ID / MSAL OAuth ────────────────────────────────────────────────────
TENANT_ID     = os.getenv("TENANT_ID")
CLIENT_ID     = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
AUTHORITY     = f"https://login.microsoftonline.com/{TENANT_ID}"
REDIRECT_URI  = os.getenv("REDIRECT_URI")
# User.Read is required by src.auth_graph.fetch_member_groups,
# which is called when the ID token has a groups overage (>~150 groups).
# Without this scope, users in many groups would see zero tables.
SCOPE         = ["User.Read", "email"]

# ── Unity Catalog cache location ─────────────────────────────────────────────
CATALOG_CACHE = "data_governance"
SCHEMA_CACHE  = "dictionary_cache"

# ── Data validation ───────────────────────────────────────────────────────────
MAX_BUSINESS_NAME_LEN = 255   # column business name — short label
MAX_DEFINITION_LEN    = 2000  # column/table definition — paragraph-length

# ── DuckDB local cache ────────────────────────────────────────────────────────
DUCKDB_PATH = os.getenv("DUCKDB_PATH", "")
# User data (comments, overrides, audit) lives in a separate persistent file
# that is never swapped by the nightly sync job.
USER_DATA_PATH = (
    DUCKDB_PATH.replace(".duckdb", "_user_data.duckdb")
    if ".duckdb" in DUCKDB_PATH
    else DUCKDB_PATH + "_user_data.duckdb"
) if DUCKDB_PATH else ""

# ── Pipeline execution service principal ─────────────────────────────────────
PIPELINE_SP_TENANT_ID     = os.getenv("PIPELINE_SP_TENANT_ID", "")
PIPELINE_SP_CLIENT_ID     = os.getenv("PIPELINE_SP_CLIENT_ID", "")
PIPELINE_SP_CLIENT_SECRET = os.getenv("PIPELINE_SP_CLIENT_SECRET", "")
DATABRICKS_HOST_URL       = os.getenv("DATABRICKS_HOST", "")

# ── Mock auth department default ─────────────────────────────────────────────
# ENABLE_MOCK_AUTH, ENVIRONMENT, and DEMO_DATA are intentionally NOT defined
# here. They are read inline via os.getenv() in app.py so that test suites
# can temporarily override them per-test without hitting the module-level cache.
MOCK_DEPT = os.getenv("MOCK_DEPT", "Finance")

# ── Semantic Search ──────────────────────────────────────────────────────────
ENABLE_SEMANTIC_SEARCH = os.getenv("ENABLE_SEMANTIC_SEARCH", "false").lower() == "true"
DATABRICKS_EMBEDDING_ENDPOINT = os.getenv("DATABRICKS_EMBEDDING_ENDPOINT", "")

# ── API / MCP server ─────────────────────────────────────────────────────────
# Override API_AUDIENCE when the API has its own app registration separate from
# the Streamlit app; defaults to CLIENT_ID (same app registration).
API_AUDIENCE = os.getenv("API_AUDIENCE", CLIENT_ID or "")
REDIS_URL = os.getenv("REDIS_URL", "")


def is_demo_mode() -> bool:
    """Return True if demo mode is enabled via environment variable."""
    return os.getenv("DEMO_DATA", "false").lower() == "true"
