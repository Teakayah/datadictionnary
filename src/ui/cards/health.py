"""Health dashboard — catalog-wide metadata coverage metrics.

Renders the "/health" tab. Pure read-only views: documentation coverage,
column completeness, schema-level rollups, and a priority-actions list of
undocumented tables.
"""

from __future__ import annotations

import logging

import streamlit as st

from src.config import CATALOG_CACHE, SCHEMA_CACHE, is_demo_mode
from src.db.queries import run_query
from src.i18n import t


def _calculate_health_metrics(all_data):
    n_tables = len(all_data)
    n_desc = (all_data['table_description'].str.strip().str.len() > 0).sum()
    table_coverage = (n_desc / n_tables * 100) if n_tables > 0 else 0

    if is_demo_mode():
        n_cols = 0
        n_col_desc = 0
    else:
        cols_stats_query = (
            f"SELECT count(*) as total, count(comment) as with_desc "
            f"FROM {CATALOG_CACHE}.{SCHEMA_CACHE}.columns_metadata"
        )
        stats = run_query(cols_stats_query)
        n_cols = stats.iloc[0]['total']
        n_col_desc = stats.iloc[0]['with_desc']

    col_coverage = (n_col_desc / n_cols * 100) if n_cols > 0 else 0
    return table_coverage, n_desc, n_tables, col_coverage, n_col_desc, n_cols


def _render_health_hero_metrics(table_coverage, n_desc, n_tables, col_coverage, n_col_desc, n_cols):
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


def _render_schema_coverage(all_data):
    st.markdown(
        '<div class="dd-section-header"><span class="dd-eyebrow" '
        'style="margin-bottom:0">§ Coverage by Schema</span></div>',
        unsafe_allow_html=True,
    )
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
            "coverage": st.column_config.ProgressColumn(
                "Coverage", format="%d%%", min_value=0, max_value=100,
            )
        },
        use_container_width=True,
        hide_index=True,
    )


def _render_priority_actions(all_data):
    st.markdown(
        '<div class="dd-section-header"><span class="dd-eyebrow" '
        'style="margin-bottom:0">§ Priority Actions</span></div>',
        unsafe_allow_html=True,
    )
    undocumented = all_data[
        all_data['table_description'].apply(lambda x: len(str(x).strip()) == 0)
    ].head(5)

    if not undocumented.empty:
        st.warning(t("health.missing_descriptions"))
        for row in undocumented.itertuples(index=False):
            if st.button(
                f"📄 {getattr(row, 'table_name', '')}",
                key=f"health_fix_{getattr(row, 'full_name', '')}",
                use_container_width=True,
            ):
                st.query_params["tab"] = "search"
                st.session_state["dd_search_override"] = getattr(row, 'table_name', '')
                st.session_state["dd_nav_select"] = getattr(row, 'full_name', '')
                st.rerun()
    else:
        st.success(t("health.all_documented"))


def render_health(groups, get_authorized_tables_fn):
    st.markdown(f'''
    <div class="dd-search-hero">
      <div class="dd-eyebrow">{t("health.title")}</div>
      <h1>{t("health.hero_title")}</h1>
      <p class="lead">{t("health.hero_subtitle")}</p>
    </div>
    ''', unsafe_allow_html=True)

    try:
        all_data = get_authorized_tables_fn(groups)
        if all_data.empty:
            st.info(t("health.no_data"))
            return

        (table_coverage, n_desc, n_tables,
         col_coverage, n_col_desc, n_cols) = _calculate_health_metrics(all_data)

        _render_health_hero_metrics(
            table_coverage, n_desc, n_tables, col_coverage, n_col_desc, n_cols,
        )

        st.markdown('<div style="margin-top:48px;"></div>', unsafe_allow_html=True)

        col_left, col_right = st.columns([6, 4], gap="large")

        with col_left:
            _render_schema_coverage(all_data)

        with col_right:
            _render_priority_actions(all_data)

    except Exception as e:
        logging.error("Error in health dashboard: %s", e)
        st.error(t("health.load_error"))
