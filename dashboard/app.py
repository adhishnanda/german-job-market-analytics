"""Streamlit entry point for the German Job Market Analytics dashboard."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd
import streamlit as st

# Ensure project root is on sys.path when launched as `streamlit run dashboard/app.py`
_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

from analytics.aggregations import (
    language_ratio,
    role_by_city,
    skill_demand_weekly,
    source_coverage,
)
from dashboard.charts import (
    language_ratio_chart,
    role_by_city_chart,
    role_donut_chart,
    skill_trend_chart,
    source_coverage_chart,
)

_DB_PATH = _ROOT / "data" / "db" / "jobs.duckdb"

_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:ital,wght@0,400;0,500;0,700;1,400&family=IBM+Plex+Sans:wght@400;600;700&display=swap');

/* Base body font */
html, body, [class*="css"] {
    font-family: 'IBM Plex Sans', 'Helvetica Neue', Arial, sans-serif !important;
}

/* Headings use mono */
h1 {
    font-family: 'IBM Plex Mono', 'Courier New', monospace !important;
    font-weight: 700 !important;
    letter-spacing: -0.03em !important;
}
h2, h3, h4 {
    font-family: 'IBM Plex Mono', 'Courier New', monospace !important;
    font-weight: 600 !important;
    letter-spacing: -0.02em !important;
}

/* KPI metric values — large and mono */
[data-testid="stMetricValue"] {
    font-family: 'IBM Plex Mono', monospace !important;
    font-size: 32px !important;
    font-weight: 700 !important;
    line-height: 1.15 !important;
}
[data-testid="stMetricLabel"] {
    font-family: 'IBM Plex Mono', monospace !important;
    letter-spacing: 0.07em !important;
    font-size: 11px !important;
    text-transform: uppercase !important;
    color: #9a9a9a !important;
    opacity: 1 !important;
}

/* KPI card: thin bottom rule only, no box */
[data-testid="metric-container"] {
    border: none !important;
    border-bottom: 1px solid #2a2a2a !important;
    padding-bottom: 16px !important;
    background: transparent !important;
    border-radius: 0 !important;
}

/* Chart containers: flush with page background, no border */
[data-testid="stPlotlyChart"],
[data-testid="stPlotlyChart"] > div {
    background-color: #111111 !important;
    border: none !important;
    border-radius: 0 !important;
}

/* Vertical spacing between chart rows */
[data-testid="stHorizontalBlock"] {
    margin-top: 1.5rem !important;
    row-gap: 1.5rem !important;
}

/* Sidebar divider */
[data-testid="stSidebar"] hr { border-color: #2a2a2a !important; margin: 12px 0; }

/* Trim top padding on main content area */
[data-testid="stAppViewContainer"] > .main > div:first-child { padding-top: 1.5rem; }
</style>
"""


@st.cache_resource
def _open_db() -> duckdb.DuckDBPyConnection | None:
    """Open jobs.duckdb in read-only mode; returns None if the file is absent."""
    if not _DB_PATH.exists():
        return None
    try:
        return duckdb.connect(str(_DB_PATH), read_only=True)
    except Exception:
        return None


def _sidebar(conn: duckdb.DuckDBPyConnection) -> tuple[date, date, list[str], list[str]]:
    """Render sidebar filters; return (date_from, date_to, cities, roles)."""
    with st.sidebar:
        st.markdown("## Filters")
        st.divider()

        try:
            bounds = conn.execute(
                "SELECT MIN(posted_date), MAX(posted_date) FROM jobs_clean WHERE posted_date IS NOT NULL"
            ).fetchone()
            db_min = bounds[0] if bounds and bounds[0] else date(2024, 1, 1)
            db_max = bounds[1] if bounds and bounds[1] else date.today()
        except Exception:
            db_min, db_max = date(2024, 1, 1), date.today()

        date_range = st.date_input(
            "Posted date range",
            value=(db_min, db_max),
            min_value=db_min,
            max_value=db_max,
            key="date_range",
        )
        if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
            date_from, date_to = date_range[0], date_range[1]
        else:
            date_from = date_to = date_range if isinstance(date_range, date) else db_min

        st.divider()

        try:
            city_rows = conn.execute(
                "SELECT DISTINCT city FROM jobs_clean WHERE city IS NOT NULL ORDER BY city"
            ).fetchall()
            all_cities = [r[0] for r in city_rows]
        except Exception:
            all_cities = []

        selected_cities: list[str] = st.multiselect(
            "City",
            options=all_cities,
            default=[],
            placeholder="All cities",
        )

        st.divider()

        try:
            role_rows = conn.execute(
                "SELECT DISTINCT role_category FROM jobs_clean ORDER BY role_category"
            ).fetchall()
            all_roles = [r[0] for r in role_rows]
        except Exception:
            all_roles = []

        selected_roles: list[str] = st.multiselect(
            "Role category",
            options=all_roles,
            default=[],
            placeholder="All roles",
        )

    return date_from, date_to, selected_cities, selected_roles


def _filter_by_date(df: pd.DataFrame, col: str, from_: date, to_: date) -> pd.DataFrame:
    """Restrict df to rows where col is within [from_, to_]."""
    if df.empty or col not in df.columns:
        return df
    dt_col = pd.to_datetime(df[col])
    mask = (dt_col >= pd.Timestamp(from_)) & (dt_col <= pd.Timestamp(to_))
    return df[mask].copy()


def _filter_city(df: pd.DataFrame, cities: list[str]) -> pd.DataFrame:
    if not cities or "city" not in df.columns:
        return df
    return df[df["city"].isin(cities)].copy()


def _filter_role(df: pd.DataFrame, roles: list[str]) -> pd.DataFrame:
    if not roles or "role_category" not in df.columns:
        return df
    return df[df["role_category"].isin(roles)].copy()


def _kpi_row(rbc_df: pd.DataFrame, conn: duckdb.DuckDBPyConnection) -> None:
    """Render the four top-of-page KPI metrics."""
    total_jobs = int(rbc_df["job_count"].sum()) if not rbc_df.empty else 0
    n_cities = int(rbc_df["city"].nunique()) if not rbc_df.empty else 0
    n_roles = int(rbc_df["role_category"].nunique()) if not rbc_df.empty else 0
    try:
        n_sources = conn.execute(
            "SELECT COUNT(DISTINCT source) FROM jobs_clean"
        ).fetchone()[0]
    except Exception:
        n_sources = 0

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Canonical jobs", f"{total_jobs:,}")
    with c2:
        st.metric("Active sources", int(n_sources))
    with c3:
        st.metric("Cities", n_cities)
    with c4:
        st.metric("Role categories", n_roles)


def main() -> None:
    """Render the dashboard."""
    st.set_page_config(
        page_title="German Job Market Analytics",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(_CSS, unsafe_allow_html=True)

    st.markdown(
        "<div style='border-left:1px solid #00d4ff;padding-left:14px;margin-bottom:4px'>"
        "<h1 style='margin:0'>German Job Market Analytics</h1>"
        "</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<span style='color:#666666;font-size:12px;letter-spacing:0.08em;"
        "font-family:\"IBM Plex Mono\",monospace'>"
        "SKILL DEMAND &nbsp;·&nbsp; COVERAGE &nbsp;·&nbsp; LANGUAGE &nbsp;·&nbsp; ROLES"
        "</span>",
        unsafe_allow_html=True,
    )
    st.markdown("")

    conn = _open_db()
    if conn is None:
        st.warning(
            "Database not found at `data/db/jobs.duckdb`. "
            "Run `python -m etl.pipeline_runner` to populate it first."
        )
        return

    date_from, date_to, cities, roles = _sidebar(conn)

    # ── Load all four aggregations (full, unfiltered) ─────────────────────────
    try:
        skill_df_full = skill_demand_weekly(conn)
        rbc_df_full = role_by_city(conn)
        lang_df_full = language_ratio(conn)
        cov_df_full = source_coverage(conn)
    except Exception as exc:
        st.error(f"Failed to load data from database: {exc}")
        return

    # ── Apply Python-level filters ────────────────────────────────────────────
    skill_df = _filter_by_date(skill_df_full, "week_start", date_from, date_to)
    rbc_df = _filter_city(_filter_role(rbc_df_full, roles), cities)
    cov_df = _filter_by_date(cov_df_full, "snapshot_date", date_from, date_to)
    lang_df = lang_df_full  # no date/city/role dimension in result

    # ── KPI row ───────────────────────────────────────────────────────────────
    _kpi_row(rbc_df, conn)
    st.divider()

    # ── Skill demand — full width ─────────────────────────────────────────────
    st.markdown(
        "<p style='font-family:\"IBM Plex Mono\",monospace;font-size:10px;"
        "letter-spacing:0.15em;text-transform:uppercase;color:#666666;"
        "margin:1.5rem 0 0.25rem 0'>SKILL DEMAND TREND</p>",
        unsafe_allow_html=True,
    )
    st.plotly_chart(skill_trend_chart(skill_df), use_container_width=True)

    # ── Role by city | Role donut ─────────────────────────────────────────────
    st.markdown(
        "<p style='font-family:\"IBM Plex Mono\",monospace;font-size:10px;"
        "letter-spacing:0.15em;text-transform:uppercase;color:#666666;"
        "margin:1.5rem 0 0.25rem 0'>ROLE BREAKDOWN</p>",
        unsafe_allow_html=True,
    )
    col_left, col_right = st.columns(2)
    with col_left:
        st.plotly_chart(role_by_city_chart(rbc_df), use_container_width=True)
    with col_right:
        st.plotly_chart(role_donut_chart(rbc_df), use_container_width=True)

    # ── Source coverage | Language ratio ──────────────────────────────────────
    st.markdown(
        "<p style='font-family:\"IBM Plex Mono\",monospace;font-size:10px;"
        "letter-spacing:0.15em;text-transform:uppercase;color:#666666;"
        "margin:1.5rem 0 0.25rem 0'>COVERAGE &amp; LANGUAGE</p>",
        unsafe_allow_html=True,
    )
    col_cov, col_lang = st.columns(2)
    with col_cov:
        st.plotly_chart(source_coverage_chart(cov_df), use_container_width=True)
    with col_lang:
        st.plotly_chart(language_ratio_chart(lang_df), use_container_width=True)


if __name__ == "__main__":
    main()
