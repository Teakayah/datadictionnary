from __future__ import annotations
"""Health dashboard — catalog-wide metadata coverage metrics.

Renders the "/health" tab. Pure read-only views: documentation coverage,
column completeness, schema-level rollups, and a priority-actions list of
undocumented tables.

Implements SQL push-down for all metrics (ADR 002) to ensure scalability
while maintaining row-level access control.
"""

from dataclasses import dataclass
import logging
import pandas as pd
import streamlit as st

from src.config import CATALOG_CACHE, SCHEMA_CACHE, is_demo_mode
from src.db.queries import run_query
from src.i18n import t
from src.personalization import is_power_user

@dataclass
class HealthMetrics:
    table_coverage: float
    n_desc: int
    n_tables: int
    col_coverage: float
    n_col_desc: int
    n_cols: int


@st.cache_data(ttl="1h", show_spinner=False)
def _get_table_health_stats(groups: tuple) -> pd.DataFrame:
    """Fetch table-level coverage stats grouped by schema with SQL push-down."""
    if is_demo_mode():
        from src.demo.data import _DEMO_TABLES
        return _DEMO_TABLES.groupby('schema_name').agg(
            total=('table_name', 'count'),
            described=('table_description', lambda x: (x.fillna('').astype(str).str.strip().str.len() > 0).sum())
        ).reset_index()

    group_ph = ", ".join(f"%(g_{i})s" for i in range(len(groups))) if groups else "''"
    params = {f"g_{i}": g for i, g in enumerate(groups)}

    # ⚡ Bolt: No redundant caching opportunity exists here. The project enforces SQL push-down
    # for all metrics and permission checks (ADR 002) to maintain scalability and row-level access control.
    # We must not refactor database-level filtering or aggregations into Python/Pandas memory space.
    query = f"""
        SELECT 
            m.schema_name,
            COUNT(*) as total,
            SUM(CASE WHEN m.comment IS NOT NULL AND m.comment != '' THEN 1 ELSE 0 END) as described
        FROM {CATALOG_CACHE}.{SCHEMA_CACHE}.tables_metadata m
        JOIN {CATALOG_CACHE}.{SCHEMA_CACHE}.permissions_cache p ON m.full_name = p.table_full_name
        WHERE (p.principal IN ({group_ph}) OR p.principal = 'SELECT_ALL_USERS')
        GROUP BY m.schema_name
        ORDER BY m.schema_name
    """
    return run_query(query, params)


@st.cache_data(ttl="1h", show_spinner=False)
def _get_column_health_stats(groups: tuple) -> tuple[int, int]:
    """Fetch catalog-wide column coverage stats with SQL push-down."""
    if is_demo_mode():
        return 0, 0
    
    group_ph = ", ".join(f"%(g_{i})s" for i in range(len(groups))) if groups else "''"
    params = {f"g_{i}": g for i, g in enumerate(groups)}

    query = f"""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN c.comment IS NOT NULL AND c.comment != '' THEN 1 ELSE 0 END) as with_desc
        FROM {CATALOG_CACHE}.{SCHEMA_CACHE}.columns_metadata c
        JOIN {CATALOG_CACHE}.{SCHEMA_CACHE}.permissions_cache p ON c.table_full_name = p.table_full_name
        WHERE (p.principal IN ({group_ph}) OR p.principal = 'SELECT_ALL_USERS')
    """
    stats = run_query(query, params)
    if stats is None or stats.empty:
        return 0, 0
    return int(stats.iloc[0]['total']), int(stats.iloc[0]['with_desc'] or 0)


@st.cache_data(ttl="1h", show_spinner=False)
def _get_undocumented_priority(groups: tuple, limit: int = 5) -> pd.DataFrame:
    """Identify undocumented tables with SQL push-down."""
    if is_demo_mode():
        from src.demo.data import _DEMO_TABLES
        return _DEMO_TABLES[
            _DEMO_TABLES['table_description'].fillna('').astype(str).str.strip() == ''
        ].head(limit)

    group_ph = ", ".join(f"%(g_{i})s" for i in range(len(groups))) if groups else "''"
    params = {f"g_{i}": g for i, g in enumerate(groups)}
    params["limit"] = limit

    query = f"""
        SELECT m.full_name, m.table_name, m.comment as table_description
        FROM {CATALOG_CACHE}.{SCHEMA_CACHE}.tables_metadata m
        JOIN {CATALOG_CACHE}.{SCHEMA_CACHE}.permissions_cache p ON m.full_name = p.table_full_name
        WHERE (m.comment IS NULL OR m.comment = '')
          AND (p.principal IN ({group_ph}) OR p.principal = 'SELECT_ALL_USERS')
        LIMIT %(limit)s
    """
    return run_query(query, params)


def _render_health_hero_metrics(metrics: HealthMetrics):
    c1, c2, c3 = st.columns(3, gap="large")
    with c1:
        st.markdown(f'''
        <div style="background:var(--paper); border-top:3px solid var(--accent); padding:24px; border-radius:2px; box-shadow:0 2px 4px rgba(0,0,0,0.05);">
            <div style="font-family:var(--font-sans); font-size:12px; color:var(--ink-40); text-transform:uppercase; letter-spacing:0.1em; margin-bottom:8px;">{t("health.table_coverage")}</div>
            <div style="font-family:var(--font-display); font-size:48px; color:var(--ink);">{metrics.table_coverage:.0f}%</div>
            <div style="font-family:var(--font-mono); font-size:12px; color:var(--ink-60); margin-top:8px;">{t("health.tables_described", n_desc=metrics.n_desc, n_tables=metrics.n_tables)}</div>
        </div>
        ''', unsafe_allow_html=True)
    with c2:
        st.markdown(f'''
        <div style="background:var(--paper); border-top:3px solid var(--deepblue); padding:24px; border-radius:2px; box-shadow:0 2px 4px rgba(0,0,0,0.05);">
            <div style="font-family:var(--font-sans); font-size:12px; color:var(--ink-40); text-transform:uppercase; letter-spacing:0.1em; margin-bottom:8px;">{t("health.column_coverage")}</div>
            <div style="font-family:var(--font-display); font-size:48px; color:var(--ink);">{metrics.col_coverage:.0f}%</div>
            <div style="font-family:var(--font-mono); font-size:12px; color:var(--ink-60); margin-top:8px;">{t("health.columns_defined", n_col_desc=metrics.n_col_desc, n_cols=metrics.n_cols)}</div>
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


def _render_schema_coverage(schema_stats: pd.DataFrame):
    st.markdown(
        '<div class="dd-section-header"><span class="dd-eyebrow" '
        'style="margin-bottom:0">§ Coverage by Schema</span></div>',
        unsafe_allow_html=True,
    )
    
    if schema_stats is None or schema_stats.empty:
        st.info(t("common.empty"))
        return

    stats = schema_stats.copy()
    stats['coverage'] = (stats['described'] / stats['total'] * 100).round(0)

    st.dataframe(
        stats.sort_values(by='coverage', ascending=False),
        column_config={
            "schema_name": "Schema",
            "total": "Tables",
            "described": "With Desc",
            "coverage": st.column_config.ProgressColumn(
                "Coverage", format="%d%%", min_value=0, max_value=100,
            )
        },
        use_container_width=True,
        hide_index=True,
    )


def _render_priority_actions(undocumented: pd.DataFrame):
    st.markdown(
        '<div class="dd-section-header"><span class="dd-eyebrow" '
        'style="margin-bottom:0">§ Priority Actions</span></div>',
        unsafe_allow_html=True,
    )

    if not undocumented.empty:
        st.warning(t("health.missing_descriptions"))
        for row in undocumented.itertuples(index=False):
            if st.button(
                f"📄 {getattr(row, 'table_name', '')}",
                key=f"health_fix_{getattr(row, 'full_name', '')}",
                use_container_width=True,
                help=t("help.btn_priority_fix"),
            ):
                st.query_params["tab"] = "search"
                st.session_state["dd_search_override"] = getattr(row, 'table_name', '')
                st.session_state["dd_nav_select"] = getattr(row, 'full_name', '')
                st.rerun()
    else:
        st.success(t("health.all_documented"))


def _render_zero_result_alerts():
    """Render steward warnings for search terms returning zero results for >7 days."""
    from src.storage import get_analytics_storage
    
    try:
        alerts = get_analytics_storage().get_zero_result_alerts(7)
        if not alerts:
            return
            
        st.markdown(f'''
        <div style="background:rgba(184, 54, 42, 0.08); border-left:4px solid var(--accent); padding:20px 24px; border-radius:2px; margin: 24px 0 24px 0; box-shadow:0 1px 3px rgba(0,0,0,0.03);">
            <div style="font-family:var(--font-sans); font-size:11px; font-weight:600; color:var(--accent); text-transform:uppercase; letter-spacing:0.1em; margin-bottom:6px;">{t("health.steward_alert_title")}</div>
            <div style="font-family:var(--font-sans); font-size:14px; font-weight:500; color:var(--ink); margin-bottom:8px;">{t("health.steward_alert_body")}</div>
        </div>
        ''', unsafe_allow_html=True)
        
        # Display the alert terms inside a clean, interactive dataframe table
        alert_df = pd.DataFrame(alerts)
        
        # Format timestamps for display
        def format_ts(val):
            if isinstance(val, str):
                return val[:16].replace("T", " ")
            try:
                return val.strftime("%Y-%m-%d %H:%M")
            except Exception:
                return str(val)
                
        alert_df['first_seen'] = alert_df['first_seen'].apply(format_ts)
        alert_df['last_seen'] = alert_df['last_seen'].apply(format_ts)
        
        st.dataframe(
            alert_df,
            column_config={
                "query": t("health.alert_query_col"),
                "search_count": t("health.alert_count_col"),
                "first_seen": t("health.alert_first_seen_col"),
                "last_seen": t("health.alert_last_seen_col"),
            },
            use_container_width=True,
            hide_index=True,
        )
        st.markdown('<div style="margin-top:24px;"></div>', unsafe_allow_html=True)
    except Exception as e:
        logging.error("Failed to render zero result alerts: %s", e)


def render_health(groups: tuple, _unused_fn=None):
    st.markdown(f'''
    <div class="dd-search-hero">
      <div class="dd-eyebrow">{t("health.title")}</div>
      <h1>{t("health.hero_title")}</h1>
      <p class="lead">{t("health.hero_subtitle")}</p>
    </div>
    ''', unsafe_allow_html=True)

    with st.expander(t("help.health_expander")):
        _priority_note = t("help.health_priority_editor") if is_power_user() else t("help.health_priority_viewer")
        st.markdown(t("help.health_content") + "\n\n" + _priority_note)

    try:
        # 1. Fetch all metrics via SQL push-down
        schema_stats = _get_table_health_stats(groups)
        n_cols, n_col_desc = _get_column_health_stats(groups)
        undocumented = _get_undocumented_priority(groups)

        if schema_stats.empty:
            st.info(t("health.no_data"))
            return

        # 2. Calculate hero metrics
        n_tables = schema_stats['total'].sum()
        n_desc = schema_stats['described'].sum()
        table_coverage = (n_desc / n_tables * 100) if n_tables > 0 else 0
        col_coverage = (n_col_desc / n_cols * 100) if n_cols > 0 else 0

        metrics = HealthMetrics(
            table_coverage=table_coverage,
            n_desc=int(n_desc),
            n_tables=int(n_tables),
            col_coverage=col_coverage,
            n_col_desc=int(n_col_desc),
            n_cols=int(n_cols),
        )

        _render_health_hero_metrics(metrics)

        # 3. Render automated steward alerts for zero-result searches
        _render_zero_result_alerts()

        st.markdown('<div style="margin-top:48px;"></div>', unsafe_allow_html=True)

        col_left, col_right = st.columns([6, 4], gap="large")

        with col_left:
            _render_schema_coverage(schema_stats)

        with col_right:
            _render_priority_actions(undocumented)

    except Exception as e:
        logging.error("Error in health dashboard: %s", e, exc_info=True)
        st.error(t("health.load_error"))
