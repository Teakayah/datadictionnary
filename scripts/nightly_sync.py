#!/usr/bin/env python3
"""
Databricks write-back worker.

Reads pending column-definition sync jobs from user_data DuckDB and applies
them to Databricks Unity Catalog via ALTER TABLE … ALTER COLUMN … COMMENT.

Run once (CI / post-deploy flush):
    python scripts/sync_worker.py

Run as a long-lived daemon:
    python scripts/sync_worker.py --daemon
    python scripts/sync_worker.py --daemon --poll 30
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import threading
import time
from pathlib import Path

import duckdb
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("sync_worker")

# ── Config ─────────────────────────────────────────────────────────────────────

DUCKDB_PATH = os.getenv("DUCKDB_PATH", "")
USER_DATA_PATH = (
    DUCKDB_PATH.replace(".duckdb", "_user_data.duckdb")
    if ".duckdb" in DUCKDB_PATH
    else DUCKDB_PATH + "_user_data.duckdb"
) if DUCKDB_PATH else ""

MAX_ATTEMPTS  = 3
BATCH_SIZE    = 20
_write_lock   = threading.Lock()


# ── DB helpers ─────────────────────────────────────────────────────────────────

def _open_user_data() -> duckdb.DuckDBPyConnection:
    if not USER_DATA_PATH:
        sys.exit("DUCKDB_PATH is not set.")
    if not Path(USER_DATA_PATH).exists():
        sys.exit(
            f"User-data file not found: {USER_DATA_PATH!r}\n"
            "Start the Streamlit app first so the file is initialised."
        )
    return duckdb.connect(USER_DATA_PATH)


# ── Databricks push ─────────────────────────────────────────────────────────────

def _push(table_full_name: str, column_name: str, definition: str) -> None:
    """ALTER TABLE … ALTER COLUMN … COMMENT on Databricks."""
    host      = os.getenv("DATABRICKS_HOST", "").strip()
    http_path = os.getenv("DATABRICKS_HTTP_PATH", "").strip()
    token     = os.getenv("DATABRICKS_TOKEN", "").strip()

    if not (host and http_path and token):
        raise RuntimeError(
            "Set DATABRICKS_HOST, DATABRICKS_HTTP_PATH and DATABRICKS_TOKEN "
            "to enable write-back."
        )

    parts = table_full_name.split(".")
    if len(parts) != 3:
        raise ValueError(f"Expected catalog.schema.table, got {table_full_name!r}")
    cat, sch, tbl = [p.replace("`", "``") for p in parts]
    col = column_name.replace("`", "``")

    alter_sql = (
        f"ALTER TABLE `{cat}`.`{sch}`.`{tbl}` "
        f"ALTER COLUMN `{col}` SET COMMENT %(comment)s"
    )

    import databricks.sql as dbsql

    with dbsql.connect(
        server_hostname=host,
        http_path=http_path,
        access_token=token,
    ) as conn:
        with conn.cursor() as cur:
            cur.execute(alter_sql, {"comment": definition or ""})

    log.info("✓  %s . %s", table_full_name, column_name)


# ── Queue processing ────────────────────────────────────────────────────────────

def process_batch(con: duckdb.DuckDBPyConnection) -> int:
    """Process one batch of pending items. Returns the number attempted."""
    rows = con.execute(
        "SELECT sync_id, table_full_name, column_name, definition, attempts "
        "FROM pending_sync "
        "WHERE status = 'pending' AND attempts < ? "
        "ORDER BY queued_at "
        "LIMIT ?",
        [MAX_ATTEMPTS, BATCH_SIZE],
    ).fetchall()

    attempted = 0
    for sync_id, table_fn, col_name, definition, attempts in rows:
        new_attempts = attempts + 1
        with _write_lock:
            con.execute(
                "UPDATE pending_sync SET status='processing', attempts=? WHERE sync_id=?",
                [new_attempts, sync_id],
            )
        try:
            _push(table_fn, col_name, definition or "")
            with _write_lock:
                con.execute(
                    "UPDATE pending_sync "
                    "SET status='done', completed_at=current_localtimestamp(), last_error=NULL "
                    "WHERE sync_id=?",
                    [sync_id],
                )
        except Exception as exc:
            err = str(exc)[:500]
            new_status = "failed" if new_attempts >= MAX_ATTEMPTS else "pending"
            with _write_lock:
                con.execute(
                    "UPDATE pending_sync SET status=?, last_error=? WHERE sync_id=?",
                    [new_status, err, sync_id],
                )
            log.warning(
                "✗  %s . %s  (attempt %d/%d): %s",
                table_fn, col_name, new_attempts, MAX_ATTEMPTS, err,
            )
        attempted += 1

    return attempted


def queue_stats(con: duckdb.DuckDBPyConnection) -> dict:
    row = con.execute(
        "SELECT "
        "  COUNT(*) FILTER (WHERE status='pending')    AS pending, "
        "  COUNT(*) FILTER (WHERE status='processing') AS processing, "
        "  COUNT(*) FILTER (WHERE status='done')       AS done, "
        "  COUNT(*) FILTER (WHERE status='failed')     AS failed "
        "FROM pending_sync"
    ).fetchone()
    return dict(zip(["pending", "processing", "done", "failed"], row or [0, 0, 0, 0]))


# ── Entry points ────────────────────────────────────────────────────────────────

def run_once() -> None:
    con = _open_user_data()
    stats = queue_stats(con)
    log.info("Queue state before run: %s", stats)
    n = process_batch(con)
    log.info("Processed %d item(s).", n)
    con.close()


def run_daemon(poll_interval: int) -> None:
    log.info(
        "Sync worker starting — poll every %ds, max %d attempts per item.",
        poll_interval, MAX_ATTEMPTS,
    )
    con = _open_user_data()
    while True:
        try:
            n = process_batch(con)
            if n:
                log.info("Pushed %d column definition(s) to Databricks.", n)
        except Exception as exc:
            log.error("Worker loop error: %s", exc, exc_info=True)
            try:
                con.close()
            except Exception:
                pass
            time.sleep(5)
            con = _open_user_data()
        time.sleep(poll_interval)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Databricks write-back sync worker")
    parser.add_argument("--daemon", action="store_true", help="Run continuously")
    parser.add_argument(
        "--poll", type=int, default=15,
        help="Poll interval in seconds when running as daemon (default: 15)",
    )
    args = parser.parse_args()

    if args.daemon:
        run_daemon(args.poll)
    else:
        run_once()
