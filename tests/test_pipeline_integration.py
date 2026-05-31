"""Cross-source pipeline integration test: 4 sources → normalize → deduplicate → load."""
from __future__ import annotations

from datetime import date
from typing import Any

import duckdb
import pytest

from etl.loaders.duckdb_loader import _ensure_schema, load_to_connection
from etl.transformers.deduplicator import deduplicate
from etl.transformers.normalizer import normalize
from etl.transformers.salary_parser import parse_salary
from etl.transformers.skill_extractor import extract_skills


# ---------------------------------------------------------------------------
# Raw fixture helpers — one minimal record per source
# ---------------------------------------------------------------------------


def _ba_raw() -> dict[str, Any]:
    """Minimal BA search-list record as produced by the extractor."""
    return {
        "job_id": "BA_ref0001",
        "referenznummer": "ref0001",
        "stellenangebotsTitel": "Data Engineer",
        "firma": "BA Company GmbH",
        "stellenlokationen": [{
            "adresse": {"ort": "Berlin", "bundesland": "BERLIN", "plz": "10247"},
            "breite": 52.5,
            "laenge": 13.4,
        }],
        "veroeffentlichungszeitraum": {"von": "2026-05-15"},
        "arbeitszeitVollzeit": True,
        "homeofficetyp": "KEIN_HOMEOFFICE",
        "source_keyword": "Data Engineer",
        "source_city": "Berlin",
        "description_raw": "We need a Data Engineer with Python and SQL skills.",
        "salary_raw": None,
    }


def _indeed_raw() -> dict[str, Any]:
    """Minimal Indeed RSS record as produced by the extractor."""
    return {
        "source": "indeed",
        "job_id_raw": "IN_abc123",
        "title_raw": "Analytics Engineer",
        "company_raw": "Indeed Corp",
        "url": "https://de.indeed.com/viewjob?jk=abc123",
        "posted_at_raw": "Mon, 13 May 2026 08:00:00 GMT",
        "description_raw": "Looking for an analytics engineer with dbt skills.",
        "city_raw": "Berlin",
    }


def _stepstone_raw() -> dict[str, Any]:
    """Minimal Stepstone search-list record as produced by the extractor."""
    return {
        "source": "stepstone",
        "job_id": "SS_99001",
        "title_raw": "Data Scientist",
        "company": "SS GmbH",
        "location_raw": "Berlin",
        "posted_date_raw": "2026-05-10T09:30:00",
        "url": "https://www.stepstone.de/job/data-scientist/99001",
        "source_keyword": "data-scientist",
        "source_city": "berlin",
    }


def _linkedin_raw() -> dict[str, Any]:
    """Minimal LinkedIn CSV record as produced by the extractor (DD-MM-YYYY date)."""
    return {
        "source": "linkedin",
        "job_id_raw": "LI_li001",
        "title_raw": "Data Analyst",
        "company_raw": "LI GmbH",
        "city_raw": "Berlin",
        "posted_at_raw": "30-05-2026",  # DD-MM-YYYY format from LinkedIn UI
        "description_raw": "Seeking a data analyst with SQL and Tableau skills.",
        "url": "https://www.linkedin.com/jobs/view/li001",
        "employment_type": "Full-time",
        "applicant_count": 45,
        "is_remote": False,
    }


# ---------------------------------------------------------------------------
# Pipeline runner
# ---------------------------------------------------------------------------


def _run_pipeline(raw_pairs: list[tuple[dict[str, Any], str]]) -> list[dict[str, Any]]:
    """Normalize → enrich salary and skills → deduplicate."""
    normalized = [normalize(raw, source) for raw, source in raw_pairs]
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


@pytest.fixture()
def four_source_records() -> list[dict[str, Any]]:
    """Processed records for all 4 sources with no intentional cross-source duplicates."""
    return _run_pipeline([
        (_ba_raw(), "bundesagentur"),
        (_indeed_raw(), "indeed"),
        (_stepstone_raw(), "stepstone"),
        (_linkedin_raw(), "linkedin"),
    ])


# ---------------------------------------------------------------------------
# Cross-source pipeline: basic row/source assertions
# ---------------------------------------------------------------------------


class TestCrossSourcePipelineLoad:
    def test_total_row_count_is_four(
        self,
        mem_conn: duckdb.DuckDBPyConnection,
        four_source_records: list[dict[str, Any]],
    ) -> None:
        load_to_connection(four_source_records, mem_conn)
        count = mem_conn.execute("SELECT count(*) FROM jobs_raw").fetchone()[0]
        assert count == 4

    def test_all_four_sources_present(
        self,
        mem_conn: duckdb.DuckDBPyConnection,
        four_source_records: list[dict[str, Any]],
    ) -> None:
        load_to_connection(four_source_records, mem_conn)
        sources = {
            row[0]
            for row in mem_conn.execute("SELECT DISTINCT source FROM jobs_raw").fetchall()
        }
        assert sources == {"bundesagentur", "indeed", "stepstone", "linkedin"}

    def test_no_null_job_ids(
        self,
        mem_conn: duckdb.DuckDBPyConnection,
        four_source_records: list[dict[str, Any]],
    ) -> None:
        load_to_connection(four_source_records, mem_conn)
        null_count = mem_conn.execute(
            "SELECT count(*) FROM jobs_raw WHERE job_id IS NULL"
        ).fetchone()[0]
        assert null_count == 0

    def test_jobs_clean_matches_raw_when_no_duplicates(
        self,
        mem_conn: duckdb.DuckDBPyConnection,
        four_source_records: list[dict[str, Any]],
    ) -> None:
        load_to_connection(four_source_records, mem_conn)
        raw_count = mem_conn.execute("SELECT count(*) FROM jobs_raw").fetchone()[0]
        clean_count = mem_conn.execute("SELECT count(*) FROM jobs_clean").fetchone()[0]
        assert clean_count == raw_count


# ---------------------------------------------------------------------------
# skills_exploded: at least one skill row per source that has descriptions
# ---------------------------------------------------------------------------


class TestSkillsExplodedCrossSource:
    def test_bundesagentur_has_skill_rows(
        self,
        mem_conn: duckdb.DuckDBPyConnection,
        four_source_records: list[dict[str, Any]],
    ) -> None:
        load_to_connection(four_source_records, mem_conn)
        count = mem_conn.execute(
            "SELECT count(*) FROM skills_exploded WHERE source = 'bundesagentur'"
        ).fetchone()[0]
        assert count >= 1

    def test_indeed_has_skill_rows(
        self,
        mem_conn: duckdb.DuckDBPyConnection,
        four_source_records: list[dict[str, Any]],
    ) -> None:
        load_to_connection(four_source_records, mem_conn)
        count = mem_conn.execute(
            "SELECT count(*) FROM skills_exploded WHERE source = 'indeed'"
        ).fetchone()[0]
        assert count >= 1

    def test_linkedin_has_skill_rows(
        self,
        mem_conn: duckdb.DuckDBPyConnection,
        four_source_records: list[dict[str, Any]],
    ) -> None:
        load_to_connection(four_source_records, mem_conn)
        count = mem_conn.execute(
            "SELECT count(*) FROM skills_exploded WHERE source = 'linkedin'"
        ).fetchone()[0]
        assert count >= 1


# ---------------------------------------------------------------------------
# LinkedIn DD-MM-YYYY date handling
# ---------------------------------------------------------------------------


class TestLinkedInDateStorage:
    def test_dd_mm_yyyy_stored_as_iso_date(
        self, mem_conn: duckdb.DuckDBPyConnection
    ) -> None:
        records = _run_pipeline([(_linkedin_raw(), "linkedin")])
        load_to_connection(records, mem_conn)
        result = mem_conn.execute(
            "SELECT posted_date FROM jobs_raw WHERE source = 'linkedin'"
        ).fetchone()
        assert result is not None
        assert result[0] == date(2026, 5, 30)

    def test_iso_date_in_linkedin_record_stored_correctly(
        self, mem_conn: duckdb.DuckDBPyConnection
    ) -> None:
        raw = _linkedin_raw()
        raw["posted_at_raw"] = "2026-05-20"
        records = _run_pipeline([(raw, "linkedin")])
        load_to_connection(records, mem_conn)
        result = mem_conn.execute(
            "SELECT posted_date FROM jobs_raw WHERE source = 'linkedin'"
        ).fetchone()
        assert result[0] == date(2026, 5, 20)


# ---------------------------------------------------------------------------
# Cross-source deduplication: BA wins over LinkedIn for same role
# ---------------------------------------------------------------------------


class TestCrossSourceDedup:
    def test_lower_priority_source_marked_duplicate(
        self, mem_conn: duckdb.DuckDBPyConnection
    ) -> None:
        ba = normalize(_ba_raw(), "bundesagentur")
        ba["skills"] = extract_skills(ba.get("description_raw") or "")

        li_raw = _linkedin_raw()
        li_raw["title_raw"] = "Data Engineer"       # match BA title
        li_raw["company_raw"] = "BA Company GmbH"   # match BA company
        li_raw["posted_at_raw"] = "2026-05-15"       # match BA posted_date
        li = normalize(li_raw, "linkedin")
        li["skills"] = extract_skills(li.get("description_raw") or "")

        deduped = deduplicate([ba, li])
        load_to_connection(deduped, mem_conn)

        raw_count = mem_conn.execute("SELECT count(*) FROM jobs_raw").fetchone()[0]
        clean_count = mem_conn.execute("SELECT count(*) FROM jobs_clean").fetchone()[0]
        assert raw_count == 2       # both stored
        assert clean_count == 1     # only BA is canonical

    def test_ba_record_is_canonical_not_linkedin(
        self, mem_conn: duckdb.DuckDBPyConnection
    ) -> None:
        ba = normalize(_ba_raw(), "bundesagentur")
        ba["skills"] = extract_skills(ba.get("description_raw") or "")

        li_raw = _linkedin_raw()
        li_raw["title_raw"] = "Data Engineer"
        li_raw["company_raw"] = "BA Company GmbH"
        li_raw["posted_at_raw"] = "2026-05-15"
        li = normalize(li_raw, "linkedin")
        li["skills"] = extract_skills(li.get("description_raw") or "")

        deduped = deduplicate([ba, li])
        load_to_connection(deduped, mem_conn)

        canonical = mem_conn.execute(
            "SELECT source FROM jobs_clean"
        ).fetchone()[0]
        assert canonical == "bundesagentur"
