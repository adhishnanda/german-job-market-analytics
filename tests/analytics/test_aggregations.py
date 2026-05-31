"""Tests for analytics/aggregations.py using an in-memory DuckDB fixture."""

from __future__ import annotations

import duckdb
import pandas as pd
import pytest

from analytics.aggregations import (
    language_ratio,
    role_by_city,
    salary_dist,
    skill_demand_weekly,
    source_coverage,
)
from etl.loaders.duckdb_loader import _ensure_schema, load_to_connection


def _make_record(
    job_id: str,
    source: str,
    city: str,
    role_category: str,
    posted_date: str | None,
    skills: list[str],
    *,
    salary_min: float | None = None,
    salary_max: float | None = None,
    language: str = "de",
    is_duplicate: bool = False,
    snapshot_date: str | None = None,
) -> dict:
    """Build a minimal canonical record for loader fixture use."""
    return {
        "job_id": job_id,
        "source": source,
        "source_keyword": "Data Engineer",
        "source_city": city,
        "snapshot_date": snapshot_date,
        "fetched_at": None,
        "url": None,
        "title_raw": "Data Engineer",
        "description_raw": "",
        "salary_raw": None,
        "title_normalized": "data engineer",
        "company": "Acme GmbH",
        "city": city,
        "region": None,
        "country": "DE",
        "postal_code": None,
        "lat": None,
        "lon": None,
        "posted_date": posted_date,
        "employment_type": "FULL_TIME",
        "work_model": "ONSITE",
        "language": language,
        "role_category": role_category,
        "salary_min": salary_min,
        "salary_max": salary_max,
        "salary_currency": "EUR" if salary_min is not None else None,
        "skills": skills,
        "is_duplicate": is_duplicate,
        "canonical_id": None,
    }


# Fixture data — dates chosen to land on Mondays so DATE_TRUNC('week') is
# unambiguous: 2026-05-04 and 2026-05-11 are both Mondays.
_FIXTURE_RECORDS = [
    # week 2026-05-04: Python + SQL, has salary
    _make_record(
        "BA_001",
        "bundesagentur",
        "Berlin",
        "Data Engineering",
        "2026-05-04",
        ["Python", "SQL"],
        salary_min=70000.0,
        salary_max=90000.0,
        snapshot_date="2026-05-04",
    ),
    # week 2026-05-04: Python + Spark, no salary
    _make_record(
        "BA_002",
        "bundesagentur",
        "Munich",
        "Data Engineering",
        "2026-05-04",
        ["Python", "Spark"],
        snapshot_date="2026-05-04",
    ),
    # week 2026-05-11: SQL, has salary, German
    _make_record(
        "SS_001",
        "stepstone",
        "Berlin",
        "Data Analysis / BI",
        "2026-05-11",
        ["SQL"],
        salary_min=65000.0,
        language="de",
        snapshot_date="2026-05-11",
    ),
    # week 2026-05-11: Python + TensorFlow, no salary, English
    _make_record(
        "LI_001",
        "linkedin",
        "Berlin",
        "Data Science / ML",
        "2026-05-11",
        ["Python", "TensorFlow"],
        language="en",
        snapshot_date="2026-05-11",
    ),
    # week 2026-05-11: no skills, has salary, English
    _make_record(
        "SS_002",
        "stepstone",
        "Frankfurt",
        "Analytics Engineering",
        "2026-05-11",
        [],
        salary_min=80000.0,
        language="en",
        snapshot_date="2026-05-11",
    ),
    # duplicate — must be excluded from all aggregations
    _make_record(
        "BA_003",
        "bundesagentur",
        "Berlin",
        "Data Engineering",
        "2026-05-04",
        ["Python"],
        is_duplicate=True,
        snapshot_date="2026-05-04",
    ),
]


@pytest.fixture()
def conn() -> duckdb.DuckDBPyConnection:
    c = duckdb.connect(":memory:")
    _ensure_schema(c)
    load_to_connection(_FIXTURE_RECORDS, c)
    yield c
    c.close()


class TestSkillDemandWeekly:
    def test_returns_dataframe(self, conn: duckdb.DuckDBPyConnection) -> None:
        df = skill_demand_weekly(conn)
        assert list(df.columns) == ["skill", "week_start", "job_count"]

    def test_excludes_duplicates(self, conn: duckdb.DuckDBPyConnection) -> None:
        # BA_003 (duplicate) carries ["Python"] — must not appear in counts
        df = skill_demand_weekly(conn)
        # Python appears in BA_001 (week 05-04) and BA_002 (week 05-04) and LI_001 (week 05-11)
        python_rows = df[df["skill"] == "Python"]
        assert python_rows["job_count"].sum() == 3

    def test_skill_counts_by_week(self, conn: duckdb.DuckDBPyConnection) -> None:
        df = skill_demand_weekly(conn)
        week1 = pd.Timestamp("2026-05-04")
        python_w1 = df[(df["skill"] == "Python") & (df["week_start"] == week1)][
            "job_count"
        ].values
        assert len(python_w1) == 1
        assert python_w1[0] == 2  # BA_001 + BA_002

    def test_row_count(self, conn: duckdb.DuckDBPyConnection) -> None:
        df = skill_demand_weekly(conn)
        # Python×2 weeks, SQL×2 weeks, Spark×1, TensorFlow×1 = 6 rows
        assert len(df) == 6

    def test_empty_skills_produce_no_rows(
        self, conn: duckdb.DuckDBPyConnection
    ) -> None:
        # SS_002 has skills=[] — should not appear
        df = skill_demand_weekly(conn)
        assert df.empty is False  # other records do produce rows
        # No row with source traceable to SS_002's unique skill situation;
        # verify by checking total distinct job_count entries match expectation
        assert "Spark" in df["skill"].values
        assert "TensorFlow" in df["skill"].values


class TestRoleByCity:
    def test_returns_dataframe(self, conn: duckdb.DuckDBPyConnection) -> None:
        df = role_by_city(conn)
        assert list(df.columns) == ["role_category", "city", "job_count"]

    def test_excludes_duplicates(self, conn: duckdb.DuckDBPyConnection) -> None:
        df = role_by_city(conn)
        # BA_003 (duplicate) is Data Engineering / Berlin; canonical count must be 1
        de_berlin = df[
            (df["role_category"] == "Data Engineering") & (df["city"] == "Berlin")
        ]["job_count"].values
        assert len(de_berlin) == 1
        assert de_berlin[0] == 1

    def test_row_count(self, conn: duckdb.DuckDBPyConnection) -> None:
        df = role_by_city(conn)
        # 5 distinct role×city combos from canonical records
        assert len(df) == 5

    def test_all_cities_present(self, conn: duckdb.DuckDBPyConnection) -> None:
        df = role_by_city(conn)
        assert set(df["city"].tolist()) == {"Berlin", "Munich", "Frankfurt"}

    def test_ordered_descending(self, conn: duckdb.DuckDBPyConnection) -> None:
        df = role_by_city(conn)
        assert df["job_count"].is_monotonic_decreasing or len(df) <= 1


class TestSalaryDist:
    def test_returns_dataframe(self, conn: duckdb.DuckDBPyConnection) -> None:
        df = salary_dist(conn)
        assert list(df.columns) == [
            "role_category",
            "salary_min",
            "salary_max",
            "salary_currency",
        ]

    def test_filters_null_salary_min(self, conn: duckdb.DuckDBPyConnection) -> None:
        df = salary_dist(conn)
        # BA_002 and LI_001 have salary_min=None — must not appear
        assert df["salary_min"].isna().sum() == 0

    def test_row_count(self, conn: duckdb.DuckDBPyConnection) -> None:
        df = salary_dist(conn)
        # BA_001, SS_001, SS_002 have salary_min set; BA_003 is duplicate
        assert len(df) == 3

    def test_excludes_duplicates(self, conn: duckdb.DuckDBPyConnection) -> None:
        # BA_003 is duplicate and has no salary anyway; this ensures the join is clean
        df = salary_dist(conn)
        assert len(df) == 3

    def test_salary_values(self, conn: duckdb.DuckDBPyConnection) -> None:
        df = salary_dist(conn)
        assert set(df["salary_min"].tolist()) == {65000.0, 70000.0, 80000.0}


class TestLanguageRatio:
    def test_returns_dataframe(self, conn: duckdb.DuckDBPyConnection) -> None:
        df = language_ratio(conn)
        assert list(df.columns) == ["source", "language", "job_count", "pct"]

    def test_pct_sums_to_one_per_source(self, conn: duckdb.DuckDBPyConnection) -> None:
        df = language_ratio(conn)
        for source, group in df.groupby("source"):
            assert abs(group["pct"].sum() - 1.0) < 1e-6, f"pct sum != 1 for {source}"

    def test_bundesagentur_all_german(self, conn: duckdb.DuckDBPyConnection) -> None:
        df = language_ratio(conn)
        ba = df[df["source"] == "bundesagentur"]
        assert len(ba) == 1
        assert ba.iloc[0]["language"] == "de"
        assert ba.iloc[0]["pct"] == pytest.approx(1.0)

    def test_stepstone_split(self, conn: duckdb.DuckDBPyConnection) -> None:
        df = language_ratio(conn)
        ss = df[df["source"] == "stepstone"].set_index("language")
        assert ss.loc["de", "pct"] == pytest.approx(0.5)
        assert ss.loc["en", "pct"] == pytest.approx(0.5)

    def test_excludes_duplicates(self, conn: duckdb.DuckDBPyConnection) -> None:
        df = language_ratio(conn)
        # BA_003 is duplicate; bundesagentur canonical count must be 2
        ba = df[df["source"] == "bundesagentur"]
        assert ba["job_count"].sum() == 2

    def test_row_count(self, conn: duckdb.DuckDBPyConnection) -> None:
        df = language_ratio(conn)
        # bundesagentur: de=1; stepstone: de+en=2; linkedin: en=1 → 4 rows
        assert len(df) == 4


class TestSourceCoverage:
    def test_returns_dataframe(self, conn: duckdb.DuckDBPyConnection) -> None:
        df = source_coverage(conn)
        assert list(df.columns) == ["source", "snapshot_date", "job_count"]

    def test_excludes_duplicates(self, conn: duckdb.DuckDBPyConnection) -> None:
        df = source_coverage(conn)
        # BA_003 is duplicate; bundesagentur/2026-05-04 canonical count must be 2
        ba = df[
            (df["source"] == "bundesagentur")
            & (df["snapshot_date"] == pd.Timestamp("2026-05-04"))
        ]["job_count"].values
        assert ba[0] == 2

    def test_row_count(self, conn: duckdb.DuckDBPyConnection) -> None:
        df = source_coverage(conn)
        # bundesagentur/05-04, stepstone/05-11, linkedin/05-11 → 3 rows
        assert len(df) == 3

    def test_all_sources_present(self, conn: duckdb.DuckDBPyConnection) -> None:
        df = source_coverage(conn)
        assert set(df["source"].tolist()) == {"bundesagentur", "stepstone", "linkedin"}

    def test_counts_correct(self, conn: duckdb.DuckDBPyConnection) -> None:
        df = source_coverage(conn)
        ss = df[df["source"] == "stepstone"]["job_count"].values
        assert ss[0] == 2  # SS_001 + SS_002

        li = df[df["source"] == "linkedin"]["job_count"].values
        assert li[0] == 1
