"""End-to-end integration test: BA fetch → normalize → deduplicate → load."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import duckdb
import pytest

from etl.extractors.bundesagentur import fetch_jobs
from etl.loaders.duckdb_loader import _ensure_schema, load_to_connection
from etl.transformers.deduplicator import deduplicate
from etl.transformers.normalizer import normalize
from etl.transformers.salary_parser import parse_salary
from etl.transformers.skill_extractor import extract_skills


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ba_raw(
    n: int,
    keyword: str = "Data Engineer",
    city: str = "Berlin",
) -> dict[str, Any]:
    """Return a minimal valid BA search-list record for record index n."""
    return {
        "job_id": f"BA_ref{n:04d}",
        "referenznummer": f"ref{n:04d}",
        "stellenangebotsTitel": f"Data Engineer {n}",
        "firma": f"Company {n}",
        "stellenlokationen": [
            {
                "adresse": {
                    "ort": city,
                    "bundesland": "BERLIN",
                    "plz": f"1000{n % 10}",
                },
                "breite": 52.5 + n * 0.01,
                "laenge": 13.4 + n * 0.01,
            }
        ],
        "veroeffentlichungszeitraum": {"von": "2026-05-01"},
        "arbeitszeitVollzeit": True,
        "homeofficetyp": "KEIN_HOMEOFFICE",
        "source_keyword": keyword,
        "source_city": city,
        "description_raw": f"We need a Data Engineer {n} with Python and SQL skills.",
        "salary_raw": None,
    }


def _run_pipeline(raw_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize → enrich salary and skills → deduplicate."""
    normalized = [normalize(r, "bundesagentur") for r in raw_records]
    for record in normalized:
        sal_min, sal_max, sal_curr = parse_salary(record.get("salary_raw"))
        record["salary_min"] = sal_min
        record["salary_max"] = sal_max
        record["salary_currency"] = sal_curr
        record["skills"] = extract_skills(record.get("description_raw") or "")
    return deduplicate(normalized)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mem_conn() -> duckdb.DuckDBPyConnection:
    """In-memory DuckDB connection with schema initialized."""
    conn = duckdb.connect(":memory:")
    _ensure_schema(conn)
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------


class TestFullPipeline:
    def test_ten_records_load_correctly(
        self, mem_conn: duckdb.DuckDBPyConnection
    ) -> None:
        ba_raw = [_make_ba_raw(i) for i in range(10)]
        payload = {"ergebnisliste": ba_raw, "maxErgebnisse": 10}

        with patch("etl.extractors.bundesagentur._fetch_page", return_value=payload):
            with patch("etl.extractors.bundesagentur.time.sleep"):
                fetched = fetch_jobs(["Data Engineer"], ["Berlin"])

        records = _run_pipeline(fetched)
        load_to_connection(records, mem_conn)

        count = mem_conn.execute("SELECT count(*) FROM jobs_raw").fetchone()[0]
        assert count == 10

    def test_all_records_non_duplicate(
        self, mem_conn: duckdb.DuckDBPyConnection
    ) -> None:
        records = _run_pipeline([_make_ba_raw(i) for i in range(10)])
        load_to_connection(records, mem_conn)

        clean_count = mem_conn.execute("SELECT count(*) FROM jobs_clean").fetchone()[0]
        assert clean_count == 10

    def test_upsert_is_idempotent(self, mem_conn: duckdb.DuckDBPyConnection) -> None:
        records = _run_pipeline([_make_ba_raw(i) for i in range(10)])
        load_to_connection(records, mem_conn)
        load_to_connection(records, mem_conn)

        count = mem_conn.execute("SELECT count(*) FROM jobs_raw").fetchone()[0]
        assert count == 10

    def test_load_returns_row_count(self, mem_conn: duckdb.DuckDBPyConnection) -> None:
        records = _run_pipeline([_make_ba_raw(i) for i in range(5)])
        result = load_to_connection(records, mem_conn)
        assert result == 5

    def test_empty_jobs_list_is_a_no_op(
        self, mem_conn: duckdb.DuckDBPyConnection
    ) -> None:
        result = load_to_connection([], mem_conn)
        assert result == 0
        count = mem_conn.execute("SELECT count(*) FROM jobs_raw").fetchone()[0]
        assert count == 0


# ---------------------------------------------------------------------------
# jobs_clean view
# ---------------------------------------------------------------------------


class TestJobsCleanView:
    def test_excludes_duplicate_records(
        self, mem_conn: duckdb.DuckDBPyConnection
    ) -> None:
        records = _run_pipeline([_make_ba_raw(i) for i in range(5)])
        records[3]["is_duplicate"] = True
        records[3]["canonical_id"] = records[0]["job_id"]
        records[4]["is_duplicate"] = True
        records[4]["canonical_id"] = records[0]["job_id"]

        load_to_connection(records, mem_conn)

        raw_count = mem_conn.execute("SELECT count(*) FROM jobs_raw").fetchone()[0]
        clean_count = mem_conn.execute("SELECT count(*) FROM jobs_clean").fetchone()[0]
        assert raw_count == 5
        assert clean_count == 3

    def test_all_clean_records_have_is_duplicate_false(
        self, mem_conn: duckdb.DuckDBPyConnection
    ) -> None:
        records = _run_pipeline([_make_ba_raw(i) for i in range(4)])
        records[2]["is_duplicate"] = True
        records[2]["canonical_id"] = records[0]["job_id"]
        load_to_connection(records, mem_conn)

        duplicates_in_clean = mem_conn.execute(
            "SELECT count(*) FROM jobs_clean WHERE is_duplicate = TRUE"
        ).fetchone()[0]
        assert duplicates_in_clean == 0


# ---------------------------------------------------------------------------
# skills_exploded view
# ---------------------------------------------------------------------------


class TestSkillsExplodedView:
    def test_one_row_per_skill(self, mem_conn: duckdb.DuckDBPyConnection) -> None:
        records = _run_pipeline([_make_ba_raw(i) for i in range(3)])
        for record in records:
            record["skills"] = ["Python", "SQL"]
        load_to_connection(records, mem_conn)

        count = mem_conn.execute("SELECT count(*) FROM skills_exploded").fetchone()[0]
        assert count == 6  # 3 records × 2 skills each

    def test_empty_skills_produce_no_rows(
        self, mem_conn: duckdb.DuckDBPyConnection
    ) -> None:
        records = _run_pipeline([_make_ba_raw(i) for i in range(3)])
        for record in records:
            record["skills"] = []
        load_to_connection(records, mem_conn)

        count = mem_conn.execute("SELECT count(*) FROM skills_exploded").fetchone()[0]
        assert count == 0

    def test_column_names(self, mem_conn: duckdb.DuckDBPyConnection) -> None:
        records = _run_pipeline([_make_ba_raw(0)])
        records[0]["skills"] = ["Python"]
        load_to_connection(records, mem_conn)

        result = mem_conn.execute("SELECT * FROM skills_exploded LIMIT 1")
        col_names = [desc[0] for desc in result.description]
        assert col_names == [
            "job_id",
            "source",
            "city",
            "role_category",
            "posted_date",
            "skill",
        ]

    def test_excludes_duplicate_records(
        self, mem_conn: duckdb.DuckDBPyConnection
    ) -> None:
        records = _run_pipeline([_make_ba_raw(i) for i in range(4)])
        for record in records:
            record["skills"] = ["Python"]
        records[3]["is_duplicate"] = True
        records[3]["canonical_id"] = records[0]["job_id"]
        load_to_connection(records, mem_conn)

        count = mem_conn.execute("SELECT count(*) FROM skills_exploded").fetchone()[0]
        assert count == 3  # duplicate record excluded from view
