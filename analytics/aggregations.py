"""SQL aggregations over jobs_clean for the dashboard."""

from __future__ import annotations

import duckdb
import pandas as pd


def skill_demand_weekly(conn: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Return weekly skill demand counts from canonical records.

    Queries the skills_exploded view (already filters is_duplicate=FALSE).
    Columns: skill (VARCHAR), week_start (DATE), job_count (BIGINT).
    Rows with a NULL posted_date are excluded.
    """
    return conn.execute(
        """
        SELECT
            skill,
            DATE_TRUNC('week', posted_date)::DATE AS week_start,
            COUNT(*) AS job_count
        FROM skills_exploded
        WHERE posted_date IS NOT NULL
        GROUP BY skill, week_start
        ORDER BY week_start, skill
        """
    ).df()


def role_by_city(conn: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Return canonical job counts grouped by role_category and city.

    Columns: role_category (VARCHAR), city (VARCHAR), job_count (BIGINT).
    Records with a NULL city are excluded.
    """
    return conn.execute(
        """
        SELECT
            role_category,
            city,
            COUNT(*) AS job_count
        FROM jobs_clean
        WHERE city IS NOT NULL
        GROUP BY role_category, city
        ORDER BY job_count DESC
        """
    ).df()


def salary_dist(conn: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Return salary data for canonical records that have a known salary_min.

    Columns: role_category (VARCHAR), salary_min (DOUBLE),
             salary_max (DOUBLE), salary_currency (VARCHAR).
    """
    return conn.execute(
        """
        SELECT
            role_category,
            salary_min,
            salary_max,
            salary_currency
        FROM jobs_clean
        WHERE salary_min IS NOT NULL
        ORDER BY role_category, salary_min
        """
    ).df()


def language_ratio(conn: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Return language distribution per source as counts and percentages.

    Columns: source (VARCHAR), language (VARCHAR),
             job_count (BIGINT), pct (DOUBLE).
    pct = count / total canonical records for that source, rounded to 4dp.
    """
    return conn.execute(
        """
        WITH base AS (
            SELECT source, language, COUNT(*) AS job_count
            FROM jobs_clean
            GROUP BY source, language
        ),
        totals AS (
            SELECT source, SUM(job_count) AS total
            FROM base
            GROUP BY source
        )
        SELECT
            b.source,
            b.language,
            b.job_count,
            ROUND(b.job_count * 1.0 / t.total, 4) AS pct
        FROM base b
        JOIN totals t ON b.source = t.source
        ORDER BY b.source, b.language
        """
    ).df()


def source_coverage(conn: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Return per-source, per-snapshot-date canonical record counts.

    Columns: source (VARCHAR), snapshot_date (DATE), job_count (BIGINT).
    """
    return conn.execute(
        """
        SELECT
            source,
            snapshot_date,
            COUNT(*) AS job_count
        FROM jobs_clean
        GROUP BY source, snapshot_date
        ORDER BY snapshot_date, source
        """
    ).df()
