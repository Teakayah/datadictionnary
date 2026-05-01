import streamlit as st
import pandas as pd
from src.i18n import t
import html as _html
_DQ_GRADES = [
    (90, "A", "dq-a"),
    (75, "B", "dq-b"),
    (60, "C", "dq-c"),
    (0,  "D", "dq-d"),
]


def _render_table_card(row: "pd.Series", key_prefix: str, _pref_delete_fn, _pref_upsert_fn) -> None:
    """Discovery card: table name is clickable, star toggles bookmark."""
    _ts = row.get("updated_at")
    _time_str = _ts.strftime(t("discovery.date_format")) if isinstance(_ts, pd.Timestamp) else (str(_ts) if _ts else "")
    _full      = str(row.get("full_name", ""))
    _tname     = str(row.get("table_name", ""))
    _is_bk     = _full in st.session_state.get("bookmarks", set())

    st.markdown(f'''
    <div style="background:var(--paper); border:1px solid var(--ink-10); padding:16px 20px 4px; margin-bottom:4px; border-radius:2px;">
        <div style="display:flex; justify-content:space-between; align-items:baseline; margin-bottom:4px;">
            <div style="font-family:var(--font-mono); font-size:12px; color:var(--ink-40); text-transform:uppercase; letter-spacing:0.1em;">{_html.escape(str(row.get("catalog_name","")))} · {_html.escape(str(row.get("schema_name","")))}</div>
            <div style="font-family:var(--font-mono); font-size:11px; color:var(--accent);">{t("discovery.updated")} {_time_str}</div>
        </div>
        <p style="font-family:var(--font-sans); font-size:13px; color:var(--ink-60); line-height:1.5; margin:4px 0 8px;">{_html.escape(str(row.get("table_description","")))}</p>
    </div>
    ''', unsafe_allow_html=True)

    # Table name button (navigates to detail) + star bookmark — flush below the card
    _c_name, _c_star = st.columns([11, 1], gap="small")
    with _c_name:
        if st.button(f"→ {_tname}", key=f"{key_prefix}_open_{_full}", use_container_width=True, type="secondary"):
            st.query_params["tab"] = "search"
            st.session_state["dd_search_override"] = _tname
            st.session_state["dd_nav_select"] = _full
            st.rerun()
    with _c_star:
        if st.button("★" if _is_bk else "☆", key=f"{key_prefix}_bk_{_full}", use_container_width=True):
            if _is_bk:
                st.session_state.get("bookmarks", set()).discard(_full)
                _pref_delete_fn(_full, "bookmark")
            else:
                st.session_state.get("bookmarks", set()).add(_full)
                _pref_upsert_fn(_full, "bookmark")
            st.rerun()
    st.markdown("<div style='margin-bottom:12px'></div>", unsafe_allow_html=True)


def render_discovery(groups):
    st.markdown(f'''
    <div class="dd-search-hero">
      <div class="dd-eyebrow">{t("discovery.title")}</div>
      <h1>{t("discovery.hero_title")}</h1>
      <p class="lead">{t("discovery.hero_subtitle")}</p>
    </div>
    ''', unsafe_allow_html=True)

    _disc_tab_labels = [
        t("personalization.tab_notable"),
        t("personalization.tab_bookmarks"),
        t("personalization.tab_recent"),
    ]

    # Initialize the key in session state to avoid changing 'default' parameter
    if "discovery_active_tab" not in st.session_state:
        _disc_idx = st.session_state.get("_disc_tab_idx", 0)
        st.session_state["discovery_active_tab"] = _disc_tab_labels[_disc_idx] if 0 <= _disc_idx < len(_disc_tab_labels) else _disc_tab_labels[0]

    _disc_active = st.segmented_control(
        "discovery_tabs",
        options=_disc_tab_labels,
        key="discovery_active_tab",
        label_visibility="collapsed",
        selection_mode="single",
    )

    # Prevent deselecting all tabs (forces at least one to be active)
    if _disc_active is None:
        _disc_active = _disc_tab_labels[st.session_state.get("_disc_tab_idx", 0)]

    # Keep index in sync so the next rerun (e.g. locale switch) restores correctly
    if _disc_active in _disc_tab_labels:
        st.session_state["_disc_tab_idx"] = _disc_tab_labels.index(_disc_active)

    # ── New & Notable ────────────────────────────────────────────────────────────
    if _disc_active == _disc_tab_labels[0]:
        st.markdown(f'<div class="dd-section-header"><span class="dd-eyebrow" style="margin-bottom:0;color:#14110C">{t("personalization.tab_notable")}</span></div>', unsafe_allow_html=True)
        primary_group = st.session_state.get("group_filter")
        if not primary_group and groups:
            primary_group = groups[0]

        if primary_group:
            st.info(t("discovery.group_highlights", group=primary_group))
            try:
                all_authorized = get_authorized_tables((primary_group,))
                if not all_authorized.empty and "updated_at" in all_authorized.columns:
                    recent_tables = all_authorized.sort_values(by="updated_at", ascending=False).head(10)
                    for _, row in recent_tables.iterrows():
                        _render_table_card(row, "notable")
                else:
                    st.info(t("discovery.no_updates"))
            except Exception as e:
                logging.error("Error in discovery tab: %s", e)
                st.error(t("discovery.load_error"))
        else:
            st.warning(t("discovery.sign_in_prompt"))

    # ── My Bookmarks ─────────────────────────────────────────────────────────────
    elif _disc_active == _disc_tab_labels[1]:
        st.markdown(f'<div class="dd-section-header"><span class="dd-eyebrow" style="margin-bottom:0;color:#14110C">{t("personalization.tab_bookmarks")}</span></div>', unsafe_allow_html=True)
        bookmarks = st.session_state.get("bookmarks", set())
        if not bookmarks:
            st.info(t("personalization.no_bookmarks"))
        else:
            try:
                all_tables = get_authorized_tables(groups)
                bk_df = all_tables[all_tables["full_name"].isin(bookmarks)]
                if bk_df.empty:
                    st.info(t("personalization.no_bookmarks"))
                else:
                    for _, row in bk_df.iterrows():
                        _render_table_card(row, "bk")
            except Exception as e:
                logging.error("Error loading bookmarks: %s", e)
                st.error(t("discovery.load_error"))

        # ── Bookmarked columns ────────────────────────────────────────────────
        col_bookmarks = st.session_state.get("col_bookmarks", set())
        st.markdown(f'<div class="dd-section-header" style="margin-top:32px"><span class="dd-eyebrow" style="margin-bottom:0;color:#14110C">{t("personalization.bookmarked_columns")}</span></div>', unsafe_allow_html=True)
        if not col_bookmarks:
            st.info(t("personalization.no_col_bookmarks"))
        else:
            _col_bk_auth_fns = set(get_authorized_tables(groups)["full_name"].tolist()) if groups else set()
            for _bk_id in sorted(col_bookmarks):
                if "::" not in _bk_id:
                    continue
                _bk_table, _bk_col = _bk_id.split("::", 1)
                if _bk_table not in _col_bk_auth_fns:
                    continue  # column's parent table no longer authorized — hide silently
                _bk_tbl_parts = _bk_table.split(".")
                _bk_tbl_label = _bk_tbl_parts[-1] if _bk_tbl_parts else _bk_table
                _bk_path = " · ".join(_bk_tbl_parts[:-1]) if len(_bk_tbl_parts) > 1 else ""
                _c_col, _c_star = st.columns([11, 1], gap="small")
                with _c_col:
                    st.markdown(
                        f'<div style="background:var(--paper);border:1px solid var(--ink-10);padding:10px 16px;border-radius:2px;margin-bottom:4px;">'
                        f'<div style="font-family:var(--font-mono);font-size:11px;color:var(--ink-40);margin-bottom:4px;">{_html.escape(_bk_path)} · {_html.escape(_bk_tbl_label)}</div>'
                        f'<div style="font-family:var(--font-mono);font-size:14px;color:var(--ink);">{_html.escape(_bk_col)}</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                    if st.button(f"→ {_bk_tbl_label}", key=f"colbk_open_{_bk_id}", use_container_width=True, type="secondary"):
                        st.query_params["tab"] = "search"
                        st.session_state["dd_search_override"] = _bk_tbl_label
                        st.session_state["dd_nav_select"] = _bk_table
                        st.rerun()
                with _c_star:
                    if st.button("★", key=f"colbk_rm_{_bk_id}", use_container_width=True):
                        st.session_state.col_bookmarks.discard(_bk_id)
                        _pref_delete_fn(_bk_id, "col_bookmark")
                        st.rerun()

    # ── Recently Viewed ──────────────────────────────────────────────────────────
    elif _disc_active == _disc_tab_labels[2]:
        st.markdown(f'<div class="dd-section-header"><span class="dd-eyebrow" style="margin-bottom:0;color:#14110C">{t("personalization.tab_recent")}</span></div>', unsafe_allow_html=True)
        recent_views = st.session_state.get("recent_views", [])
        if not recent_views:
            st.info(t("personalization.no_recent"))
        else:
            try:
                all_tables = get_authorized_tables(groups)
                # Preserve recency order
                rv_df = all_tables[all_tables["full_name"].isin(recent_views)].copy()
                rv_df["_order"] = rv_df["full_name"].map({fn: i for i, fn in enumerate(recent_views)})
                rv_df = rv_df.sort_values("_order").drop(columns=["_order"])
                if rv_df.empty:
                    st.info(t("personalization.no_recent"))
                else:
                    for _, row in rv_df.iterrows():
                        _render_table_card(row, "rv")
            except Exception as e:
                logging.error("Error loading recent views: %s", e)
                st.error(t("discovery.load_error"))

def render_health(groups):
    st.markdown(f'''
    <div class="dd-search-hero">
      <div class="dd-eyebrow">{t("health.title")}</div>
      <h1>{t("health.hero_title")}</h1>
      <p class="lead">{t("health.hero_subtitle")}</p>
    </div>
    ''', unsafe_allow_html=True)

    try:
        all_data = get_authorized_tables(groups)
        if all_data.empty:
            st.info(t("health.no_data"))
            return

        # 1. Calculation Logic
        n_tables = len(all_data)
        n_desc = (all_data['table_description'].str.strip().str.len() > 0).sum()
        table_coverage = (n_desc / n_tables * 100) if n_tables > 0 else 0

        # For columns, we need to query the cache (or use mock)
        if DEMO_DATA:
            # Aggregate columns from _DEMO_COLUMNS
            all_cols_list = []
            for df in _DEMO_COLUMNS.values():
                all_cols_list.append(df)
            all_cols_df = pd.concat(all_cols_list)
            n_cols = len(all_cols_df)
            n_col_desc = all_cols_df['comment'].apply(lambda x: len(str(x).strip()) > 0).sum()
        else:
            cols_stats_query = f"SELECT count(*) as total, count(comment) as with_desc FROM {CATALOG_CACHE}.{SCHEMA_CACHE}.columns_metadata"
            stats = run_query(cols_stats_query)
            n_cols = stats.iloc[0]['total']
            n_col_desc = stats.iloc[0]['with_desc']

        col_coverage = (n_col_desc / n_cols * 100) if n_cols > 0 else 0

        # 2. Hero Metrics
        c1, c2, c3 = st.columns(3, gap="large")
        with c1:
            st.markdown(f'''
            <div style="background:var(--paper); border-top:3px solid var(--accent); padding:24px; border-radius:2px; box-shadow:0 2px 4px rgba(0,0,0,0.05);">
                <div style="font-family:var(--font-sans); font-size:12px; color:var(--ink-40); text-transform:uppercase; letter-spacing:0.1em; margin-bottom:8px;">{t("health.table_coverage")}</div>
                <div style="font-family:var(--font-display); font-size:48px; color:var(--ink);">{table_coverage:.0f}%</div>
                <div style="font-family:var(--font-mono); font-size:12px; color:var(--ink-60); margin-top:8px;">{t("health.tables_described", n_desc=n_desc, n_tables=n_tables)}</div>
            </div>
            ''', unsafe_allow_html=True)
        with c2:
            st.markdown(f'''
            <div style="background:var(--paper); border-top:3px solid var(--deepblue); padding:24px; border-radius:2px; box-shadow:0 2px 4px rgba(0,0,0,0.05);">
                <div style="font-family:var(--font-sans); font-size:12px; color:var(--ink-40); text-transform:uppercase; letter-spacing:0.1em; margin-bottom:8px;">{t("health.column_coverage")}</div>
                <div style="font-family:var(--font-display); font-size:48px; color:var(--ink);">{col_coverage:.0f}%</div>
                <div style="font-family:var(--font-mono); font-size:12px; color:var(--ink-60); margin-top:8px;">{t("health.columns_defined", n_col_desc=n_col_desc, n_cols=n_cols)}</div>
            </div>
            ''', unsafe_allow_html=True)
        with c3:
            st.markdown(f'''
            <div style="background:var(--paper); border-top:3px solid var(--ochre); padding:24px; border-radius:2px; box-shadow:0 2px 4px rgba(0,0,0,0.05);">
                <div style="font-family:var(--font-sans); font-size:12px; color:var(--ink-40); text-transform:uppercase; letter-spacing:0.1em; margin-bottom:8px;">{t("health.freshness_index")}</div>
                <div style="font-family:var(--font-display); font-size:48px; color:var(--ink);">A</div>
                <div style="font-family:var(--font-mono); font-size:12px; color:var(--ink-60); margin-top:8px;">{t("health.last_sync")}</div>
            </div>
            ''', unsafe_allow_html=True)

        st.markdown('<div style="margin-top:48px;"></div>', unsafe_allow_html=True)

        # 3. Bottom breakdown
        col_left, col_right = st.columns([6, 4], gap="large")

        with col_left:
            st.markdown('<div class="dd-section-header"><span class="dd-eyebrow" style="margin-bottom:0">§ Coverage by Schema</span></div>', unsafe_allow_html=True)
            schema_stats = all_data.groupby('schema_name').agg(
                total=('table_name', 'count'),
                described=('table_description', lambda x: x.apply(lambda y: len(str(y).strip()) > 0).sum())
            ).reset_index()
            schema_stats['coverage'] = (schema_stats['described'] / schema_stats['total'] * 100).round(0)

            st.dataframe(
                schema_stats.sort_values(by='coverage', ascending=False),
                column_config={
                    "schema_name": "Schema",
                    "total": "Tables",
                    "described": "With Desc",
                    "coverage": st.column_config.ProgressColumn("Coverage", format="%d%%", min_value=0, max_value=100)
                },
                use_container_width=True,
                hide_index=True
            )

        with col_right:
            st.markdown('<div class="dd-section-header"><span class="dd-eyebrow" style="margin-bottom:0">§ Priority Actions</span></div>', unsafe_allow_html=True)
            undocumented = all_data[all_data['table_description'].apply(lambda x: len(str(x).strip()) == 0)].head(5)

            if not undocumented.empty:
                st.warning(t("health.missing_descriptions"))
                for _, row in undocumented.iterrows():
                    if st.button(f"📄 {row['table_name']}", key=f"health_fix_{row['full_name']}", use_container_width=True):
                        st.query_params["tab"] = "search"
                        st.session_state["dd_search_override"] = row["table_name"]
                        st.session_state["dd_nav_select"] = row["full_name"]
                        st.rerun()
            else:
                st.success(t("health.all_documented"))

    except Exception as e:
        logging.error("Error in health dashboard: %s", e)
        st.error(t("health.load_error"))



# ── Admin page ─────────────────────────────────────────────────────────────────

def get_admin_stats() -> dict:
    """Return four catalog-wide counts for the admin dashboard."""
    if DEMO_DATA:
        return {
            "tables":    len(_DEMO_TABLES),
            "columns":   sum(len(df) for df in _DEMO_COLUMNS.values()),
            "comments":  sum(len(v) for v in st.session_state.get("demo_comments", {}).values()),
            "overrides": sum(len(v) for v in st.session_state.get("demo_business_names", {}).values()),
        }
    try:
        _ud = _duckdb_available()
        comments_tbl  = "user_data.comments"                if _ud else f"{CATALOG_CACHE}.{SCHEMA_CACHE}.comments"
        overrides_tbl = "user_data.business_name_overrides" if _ud else f"{CATALOG_CACHE}.{SCHEMA_CACHE}.business_name_overrides"
        tables_tbl    = f"{CATALOG_CACHE}.{SCHEMA_CACHE}.tables_metadata"
        columns_tbl   = f"{CATALOG_CACHE}.{SCHEMA_CACHE}.columns_metadata"
        tables_cnt    = run_query(f"SELECT COUNT(*) AS c FROM {tables_tbl}").iloc[0]["c"]
        columns_cnt   = run_query(f"SELECT COUNT(*) AS c FROM {columns_tbl}").iloc[0]["c"]
        comments_cnt  = run_query(f"SELECT COUNT(*) AS c FROM {comments_tbl}").iloc[0]["c"]
        overrides_cnt = run_query(f"SELECT COUNT(*) AS c FROM {overrides_tbl}").iloc[0]["c"]
        return {"tables": tables_cnt, "columns": columns_cnt, "comments": comments_cnt, "overrides": overrides_cnt}
    except Exception as e:
        logging.warning("Failed to fetch admin stats: %s", e)
        return {"tables": 0, "columns": 0, "comments": 0, "overrides": 0}


def get_business_name_change_log() -> pd.DataFrame:
    """Return the last 200 business name change events for the admin log."""
    if DEMO_DATA:
        logs = [l for l in st.session_state.get("demo_audit_log", []) if l["event_type"] == "business_name_change"]
        if not logs:
            return pd.DataFrame(columns=["event_id", "object_name", "old_value", "new_value", "actor_email", "created_at"])
        return pd.DataFrame(logs).sort_values("created_at", ascending=False).head(200)
    audit_tbl = "user_data.audit_log" if _duckdb_available() else f"{CATALOG_CACHE}.{SCHEMA_CACHE}.audit_log"
    return run_query(
        f"SELECT event_id, object_name, old_value, new_value, actor_email, created_at "
        f"FROM {audit_tbl} "
        f"WHERE event_type = 'business_name_change' "
        f"ORDER BY created_at DESC LIMIT 200"
    )


def get_comment_log() -> pd.DataFrame:
    """Return the last 200 comment/reply events for the admin log."""
    if DEMO_DATA:
        logs = [l for l in st.session_state.get("demo_audit_log", [])
                if l["event_type"] in ("comment_added", "comment_reply")]
        if not logs:
            return pd.DataFrame(columns=["event_id", "object_name", "comment_preview", "actor_email", "created_at"])
        df = pd.DataFrame(logs).rename(columns={"new_value": "comment_preview"})
        return df.sort_values("created_at", ascending=False).head(200)
    audit_tbl = "user_data.audit_log" if _duckdb_available() else f"{CATALOG_CACHE}.{SCHEMA_CACHE}.audit_log"
    return run_query(
        f"SELECT event_id, object_name, new_value AS comment_preview, actor_email, created_at "
        f"FROM {audit_tbl} "
        f"WHERE event_type IN ('comment_added', 'comment_reply') "
        f"ORDER BY created_at DESC LIMIT 200"
    )


def get_sync_queue_stats() -> dict:
    """Return counts of pending_sync items by status."""
    if not _duckdb_available():
        return {}
    try:
        conn = _get_write_connection()
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT status, COUNT(*) FROM user_data.pending_sync GROUP BY status"
            )
            rows = cursor.fetchall()
            stats = {row[0]: row[1] for row in rows}
            # Ensure all statuses are present
            for s in ("pending", "processing", "done", "failed"):
                stats.setdefault(s, 0)
            return stats
    except Exception:
        return {"pending": 0, "processing": 0, "done": 0, "failed": 0}


def render_admin_page():
    if not is_admin():
        st.error(t("admin.access_denied"))
        st.stop()

    st.markdown(f'''
    <div class="dd-search-hero">
      <div class="dd-eyebrow">{t("admin.title")}</div>
      <h1>Administration.</h1>
      <p class="lead">{t("admin.subtitle")}</p>
    </div>
    ''', unsafe_allow_html=True)

    stats = get_admin_stats()
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric(t("admin.stats_tables"), f"{stats.get('tables', 0):,}")
    with c2:
        st.metric(t("admin.stats_columns"), f"{stats.get('columns', 0):,}")
    with c3:
        st.metric(t("admin.stats_comments"), f"{stats.get('comments', 0):,}")
    with c4:
        st.metric(t("admin.stats_overrides"), f"{stats.get('overrides', 0):,}")

    # --- § Synchronization status ---
    st.markdown(f'<div class="dd-section-header" style="margin-top:32px;"><span class="dd-eyebrow">§ {t("admin.sync_title")}</span></div>', unsafe_allow_html=True)

    sync_stats = get_sync_queue_stats()
    total_jobs = sum(sync_stats.values())
    done_jobs = sync_stats.get("done", 0)
    pct_complete = (done_jobs / total_jobs * 100) if total_jobs > 0 else 100.0

    sc1, sc2 = st.columns([7, 3], gap="large")
    with sc1:
        st.progress(pct_complete / 100.0, text=f"{pct_complete:.1f}% synced with Databricks")

        # Detailed breakdown
        bc1, bc2, bc3, bc4 = st.columns(4)
        bc1.caption(f"Pending: {sync_stats.get('pending', 0)}")
        bc2.caption(f"Processing: {sync_stats.get('processing', 0)}")
        bc3.caption(f"Done: {sync_stats.get('done', 0)}")
        bc4.caption(f"Failed: {sync_stats.get('failed', 0)}")

    with sc2:
        # Current Mode & DR Status
        is_idle = (time.time() - _get_last_ui_activity()) > 300
        mode_label = "Idle (High Throughput)" if is_idle else "Active (Low Impact)"
        mode_color = "var(--deepblue)" if is_idle else "var(--accent-ink)" # Deep blue vs Accent red

        st.markdown(
            f'<div style="background:var(--paper-deep); padding:12px; border-radius:4px; border-left:4px solid {mode_color};">'
            f'<div style="font-family:var(--font-mono); font-size:10px; color:var(--ink-40); text-transform:uppercase;">Sync Mode</div>'
            f'<div style="font-family:var(--font-sans); font-size:14px; font-weight:600; color:var(--ink);">{mode_label}</div>'
            f'<div style="margin-top:12px; font-family:var(--font-mono); font-size:10px; color:var(--ink-40); text-transform:uppercase;">Self-Healing (DR)</div>'
            f'<div style="font-family:var(--font-sans); font-size:13px; color:var(--ink-60);">{_get_dr_resync_status()}</div>'
            f'</div>',
            unsafe_allow_html=True
        )

    st.markdown('<div style="margin-top:32px;"></div>', unsafe_allow_html=True)

    with st.expander(t("admin.biz_log_title"), expanded=True):
        biz_log = get_business_name_change_log()
        st.dataframe(
            biz_log,
            column_config={
                "object_name": st.column_config.TextColumn("Object"),
                "old_value":   st.column_config.TextColumn("Old name"),
                "new_value":   st.column_config.TextColumn("New name"),
                "actor_email": st.column_config.TextColumn("Changed by"),
                "created_at":  st.column_config.TextColumn("Changed at"),
            },
            hide_index=True,
            use_container_width=True,
        )

    with st.expander(t("admin.comment_log_title"), expanded=True):
        comment_log = get_comment_log()
        st.dataframe(
            comment_log,
            column_config={
                "object_name":      st.column_config.TextColumn("Object"),
                "comment_preview":  st.column_config.TextColumn("Comment preview"),
                "actor_email":      st.column_config.TextColumn("Author"),
                "created_at":       st.column_config.TextColumn("Posted at"),
            },
            hide_index=True,
            use_container_width=True,
        )


# ── Global State for Background Workers ──────────────────────────────────────
_worker_state_lock = threading.Lock()
_LAST_UI_ACTIVITY = time.time()
_DR_RESYNC_STATUS = "Idle" # Idle, Checking, Syncing, Up-to-date, Error
_DR_RESYNC_PROGRESS = 0.0

def _get_last_ui_activity():
    with _worker_state_lock:
        return _LAST_UI_ACTIVITY

def _get_dr_resync_status():
    with _worker_state_lock:
        return _DR_RESYNC_STATUS

def _set_dr_resync_status(status):
    global _DR_RESYNC_STATUS
    with _worker_state_lock:
        _DR_RESYNC_STATUS = status

def _set_dr_resync_progress(progress):
    global _DR_RESYNC_PROGRESS
    with _worker_state_lock:
        _DR_RESYNC_PROGRESS = progress

def _mark_ui_activity():
    global _LAST_UI_ACTIVITY
    with _worker_state_lock:
        _LAST_UI_ACTIVITY = time.time()


def _run_dr_resync():
    """Background task to pull missing records from Databricks to DuckDB."""
    if not _duckdb_available():
        return

    _set_dr_resync_status("Checking")
    try:
        conn = _get_write_connection()
        # 1. Check for newest records in Databricks vs Local
        # We check comments, audit_log, and overrides
        tables_to_check = [
            ("comments", "created_at", "comment_id"),
            ("audit_log", "created_at", "event_id"),
            ("business_name_overrides", "edited_at", "table_full_name, column_name")
        ]

        for tbl, ts_col, pk in tables_to_check:
            # Get max local timestamp
            with conn.cursor() as cursor:
                cursor.execute(f"SELECT MAX({ts_col}) FROM user_data.{tbl}")
                local_max = cursor.fetchall()[0][0]

            # Query Databricks for any records AFTER local_max
            # Note: run_query handles the Databricks connection
            remote_q = f"SELECT * FROM {CATALOG_CACHE}.{SCHEMA_CACHE}.{tbl}"
            params = {}
            if local_max:
                remote_q += f" WHERE {ts_col} > %(local_max)s"
                params["local_max"] = local_max

            delta_df = run_query(remote_q, params)
            if delta_df is not None and not delta_df.empty:
                _set_dr_resync_status(f"Syncing {tbl}")
                # Merge into DuckDB
                with conn.cursor() as cursor:
                    for _, row in delta_df.iterrows():
                        # Simple append for logs/comments (guaranteed unique IDs)
                        if tbl in ("comments", "audit_log"):
                            cols = ", ".join(delta_df.columns)
                            placeholders = ", ".join([f"%({c})s" for c in delta_df.columns])
                            cursor.execute_write(
                                f"INSERT OR IGNORE INTO user_data.{tbl} ({cols}) VALUES ({placeholders})",
                                row.to_dict()
                            )
                        else:
                            # Merge for overrides
                            cursor.execute_write(
                                f"INSERT OR REPLACE INTO user_data.{tbl} ({', '.join(delta_df.columns)}) "
                                f"VALUES ({', '.join([f'%({c})s' for c in delta_df.columns])})",
                                row.to_dict()
                            )

        _set_dr_resync_status("Up-to-date")
        _set_dr_resync_progress(100.0)
    except Exception as e:
        logging.error("DR Resync failed: %s", e)
        _set_dr_resync_status(f"Error: {str(e)[:50]}")



# ── App entry point ────────────────────────────────────────────────────────────
render_css()
_mark_ui_activity()

# Start the Databricks write-back worker (singleton daemon thread, no-ops in pure local mode).
if _duckdb_available():
    _start_sync_worker_thread()

# Capture viewport height once per session; returns None on first render (before JS runs).
if "viewport_height" not in st.session_state:
    _vh = streamlit_js_eval(js_expressions="window.innerHeight", key="_dd_vh")
    if _vh:
        st.session_state["viewport_height"] = int(_vh)
else:
    # Keep the component alive so it runs on browsers that re-register after reload
    streamlit_js_eval(js_expressions="window.innerHeight", key="_dd_vh")

# ── Auth gate ─────────────────────────────────────────────────────────────────
if ENABLE_MOCK_AUTH and ENVIRONMENT == "development":
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    # Personalization state — seed from DuckDB, fall back to empty
    if "bookmarks" not in st.session_state:
        st.session_state.bookmarks = set()
    if "col_bookmarks" not in st.session_state:
        st.session_state.col_bookmarks = set()
    if "recent_views" not in st.session_state:
        st.session_state.recent_views = []
    if not st.session_state.get("_prefs_loaded"):
        _sync_prefs_to_session()
        st.session_state["_prefs_loaded"] = True

    # Auto-login from a URL param — used by screenshot scripts and load tests
    # that navigate directly to a URL without an existing session.
    # Only fires when the user is NOT already authenticated so that a nav click
    # (which re-adds mock_login=true to the URL) cannot overwrite the session.
    if st.query_params.get("mock_login") == "true" and not st.session_state.authenticated:
        _ql_dept = st.query_params.get("mock_dept", MOCK_DEPT).lower()
        _dept_group_map = {
            "finance":  (["finance_group",  "SELECT_ALL_USERS"], "Finance User",  "finance.user@research-org.ca"),
            "research": (["research_group", "SELECT_ALL_USERS"], "Research User", "research.user@research-org.ca"),
            "hr":       (["hr_group",       "SELECT_ALL_USERS"], "HR User",       "hr.user@research-org.ca"),
            "it":       (["it_group",       "SELECT_ALL_USERS"], "IT User",       "it.user@research-org.ca"),
        }
        if _ql_dept in _dept_group_map:
            _ql_groups, _ql_name, _ql_email = _dept_group_map[_ql_dept]
        else:
            # Default: all groups (admin view — used by screenshot script & load tests)
            _ql_groups = ["finance_group", "research_group", "hr_group", "it_group",
                          "SELECT_ALL_USERS", "finance_dept_id", "all_employees_id"]
            _ql_name, _ql_email = "Admin User", "admin@research-org.ca"
        st.session_state.authenticated = True
        st.session_state.user_groups   = _ql_groups
        st.session_state.user_name     = _ql_name
        st.session_state.user_email    = _ql_email
    if not st.session_state.get("authenticated"):
        # Slim logo-only header for the sign-in page — avoids nav JS wiring on unauthenticated renders
        st.html(f'''
<div class="dd-header">
  <div class="dd-header-inner">
    <span class="dd-logo-link">
      {LOGO_MARK_SVG}
      <span class="dd-logo-text">Data Dictionary</span>
      <span class="dd-pill">Beta</span>
    </span>
  </div>
</div>
''')
        st.markdown('<div class="dd-page" role="main" aria-live="polite">', unsafe_allow_html=True)
        render_signin_page(mock=True)
        st.markdown("</div>", unsafe_allow_html=True)
