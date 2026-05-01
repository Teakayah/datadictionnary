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
SCOPE         = ["User.Read", "GroupMember.Read.All", "email"]

# ── Unity Catalog cache location ─────────────────────────────────────────────
CATALOG_CACHE = "data_governance"
SCHEMA_CACHE  = "dictionary_cache"

# ── Data validation ───────────────────────────────────────────────────────────
MAX_BUSINESS_NAME_LEN = 255

# ── DuckDB local cache ────────────────────────────────────────────────────────
DUCKDB_PATH = os.getenv("DUCKDB_PATH", "")
# User data (comments, overrides, audit) lives in a separate persistent file
# that is never swapped by the nightly sync job.
USER_DATA_PATH = (
    DUCKDB_PATH.replace(".duckdb", "_user_data.duckdb")
    if ".duckdb" in DUCKDB_PATH
    else DUCKDB_PATH + "_user_data.duckdb"
) if DUCKDB_PATH else ""

# ── Mock auth department default ─────────────────────────────────────────────
# ENABLE_MOCK_AUTH, ENVIRONMENT, and DEMO_DATA are intentionally NOT defined
# here. They are read inline via os.getenv() in app.py so that test suites
# can temporarily override them per-test without hitting the module-level cache.
MOCK_DEPT = os.getenv("MOCK_DEPT", "Finance")

def is_demo_mode() -> bool:
    """Return True if demo mode is enabled via environment variable."""
    return os.getenv("DEMO_DATA", "false").lower() == "true"
