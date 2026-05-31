"""Tests for the DuckDB loader."""

from __future__ import annotations

import duckdb
import pytest

from etl.loaders.duckdb_loader import _ensure_schema, load_to_connection


def _minimal_record(job_id: str) -> dict:
    return {
        "job_id": job_id,
        "source": "bundesagentur",
        "source_keyword": "Data Engineer",
        "source_city": "Berlin",
        "snapshot_date": None,
        "fetched_at": None,
        "url": None,
        "title_raw": "Data Engineer",
        "description_raw": "",
        "salary_raw": None,
        "title_normalized": "data engineer",
        "company": "Acme GmbH",
        "city": "Berlin",
        "region": "BERLIN",
        "country": "DE",
        "postal_code": None,
        "lat": None,
        "lon": None,
        "posted_date": None,
        "employment_type": "FULL_TIME",
        "work_model": "ONSITE",
        "language": "de",
        "role_category": "Data Engineering",
        "salary_min": None,
        "salary_max": None,
        "salary_currency": None,
        "skills": [],
        "is_duplicate": False,
        "canonical_id": None,
    }


@pytest.fixture()
def conn() -> duckdb.DuckDBPyConnection:
    c = duckdb.connect(":memory:")
    _ensure_schema(c)
    yield c
    c.close()


class TestLoad:
    def test_inserts_rows(self, conn: duckdb.DuckDBPyConnection) -> None:
        records = [_minimal_record(f"BA_test{i:03d}") for i in range(3)]
        load_to_connection(records, conn)
        count = conn.execute("SELECT count(*) FROM jobs_raw").fetchone()[0]
        assert count == 3

    def test_returns_row_count(self, conn: duckdb.DuckDBPyConnection) -> None:
        records = [_minimal_record(f"BA_test{i:03d}") for i in range(5)]
        result = load_to_connection(records, conn)
        assert result == 5

    def test_upsert_does_not_duplicate(self, conn: duckdb.DuckDBPyConnection) -> None:
        record = _minimal_record("BA_test001")
        load_to_connection([record], conn)
        load_to_connection([record], conn)
        count = conn.execute("SELECT count(*) FROM jobs_raw").fetchone()[0]
        assert count == 1

    def test_empty_list_is_no_op(self, conn: duckdb.DuckDBPyConnection) -> None:
        result = load_to_connection([], conn)
        assert result == 0
