"""Tests for the deduplicator."""
from __future__ import annotations

from datetime import date

from etl.transformers.deduplicator import _SOURCE_PRIORITY, deduplicate


def _make_record(**overrides: object) -> dict:
    """Return a minimal normalized record suitable for deduplication testing."""
    base: dict = {
        "job_id": "BA_001",
        "source": "bundesagentur",
        "title_normalized": "data engineer",
        "company": "Acme GmbH",
        "city": "Berlin",
        "posted_date": date(2026, 5, 15),
        "is_duplicate": False,
        "canonical_id": None,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Pass 1 — within-source job_id dedup
# ---------------------------------------------------------------------------


class TestPassOneWithinSourceDedup:
    def test_no_duplicates_unchanged(self) -> None:
        r1 = _make_record(job_id="BA_001")
        r2 = _make_record(job_id="BA_002")
        deduplicate([r1, r2])
        assert r1["is_duplicate"] is False
        assert r2["is_duplicate"] is False

    def test_same_job_id_same_source_marks_second_duplicate(self) -> None:
        r1 = _make_record(job_id="BA_001")
        r2 = _make_record(job_id="BA_001")
        deduplicate([r1, r2])
        assert r1["is_duplicate"] is False
        assert r2["is_duplicate"] is True
        assert r2["canonical_id"] == "BA_001"

    def test_first_occurrence_is_always_canonical(self) -> None:
        r1 = _make_record(job_id="BA_001")
        r2 = _make_record(job_id="BA_001")
        r3 = _make_record(job_id="BA_001")
        deduplicate([r1, r2, r3])
        assert r1["is_duplicate"] is False
        assert r2["canonical_id"] == "BA_001"
        assert r3["canonical_id"] == "BA_001"

    def test_pass1_groups_by_source_and_job_id(self) -> None:
        """The same job_id string under two different sources is not a Pass-1 duplicate."""
        r1 = _make_record(job_id="JOB_001", source="bundesagentur", title_normalized="xyz role alpha")
        r2 = _make_record(job_id="JOB_001", source="indeed", title_normalized="completely unrelated")
        deduplicate([r1, r2])
        # Pass 1: different (source, job_id) keys → not a duplicate
        # Pass 2: title too dissimilar → not a duplicate
        assert r1["is_duplicate"] is False
        assert r2["is_duplicate"] is False


# ---------------------------------------------------------------------------
# Pass 2 — cross-source fuzzy dedup
# ---------------------------------------------------------------------------


class TestPassTwoCrossSourceDedup:
    def _matching_pair(self) -> tuple[dict, dict]:
        """Return a BA and Indeed record that match on all four conditions."""
        ba = _make_record(job_id="BA_001", source="bundesagentur")
        indeed = _make_record(job_id="IN_001", source="indeed")
        return ba, indeed

    def test_matching_records_lower_priority_marked_duplicate(self) -> None:
        ba, indeed = self._matching_pair()
        deduplicate([ba, indeed])
        assert ba["is_duplicate"] is False
        assert indeed["is_duplicate"] is True
        assert indeed["canonical_id"] == "BA_001"

    def test_priority_wins_regardless_of_input_order(self) -> None:
        ba, indeed = self._matching_pair()
        deduplicate([indeed, ba])  # Indeed listed first
        assert ba["is_duplicate"] is False
        assert indeed["canonical_id"] == "BA_001"

    def test_title_too_dissimilar_no_dedup(self) -> None:
        ba = _make_record(job_id="BA_001", source="bundesagentur", title_normalized="data engineer")
        indeed = _make_record(job_id="IN_001", source="indeed", title_normalized="product manager")
        deduplicate([ba, indeed])
        assert indeed["is_duplicate"] is False

    def test_date_outside_window_no_dedup(self) -> None:
        ba = _make_record(job_id="BA_001", source="bundesagentur", posted_date=date(2026, 5, 1))
        indeed = _make_record(job_id="IN_001", source="indeed", posted_date=date(2026, 5, 10))  # 9 days
        deduplicate([ba, indeed])
        assert indeed["is_duplicate"] is False

    def test_date_exactly_at_window_boundary_deduped(self) -> None:
        ba = _make_record(job_id="BA_001", source="bundesagentur", posted_date=date(2026, 5, 1))
        indeed = _make_record(job_id="IN_001", source="indeed", posted_date=date(2026, 5, 8))  # 7 days
        deduplicate([ba, indeed])
        assert indeed["is_duplicate"] is True

    def test_different_city_no_dedup(self) -> None:
        ba = _make_record(job_id="BA_001", source="bundesagentur", city="Berlin")
        indeed = _make_record(job_id="IN_001", source="indeed", city="Munich")
        deduplicate([ba, indeed])
        assert indeed["is_duplicate"] is False

    def test_company_too_different_no_dedup(self) -> None:
        ba = _make_record(job_id="BA_001", source="bundesagentur", company="Zalando SE")
        indeed = _make_record(job_id="IN_001", source="indeed", company="Deutsche Bank AG")
        deduplicate([ba, indeed])
        assert indeed["is_duplicate"] is False

    def test_missing_city_skips_cross_source_dedup(self) -> None:
        ba = _make_record(job_id="BA_001", source="bundesagentur", city=None)
        indeed = _make_record(job_id="IN_001", source="indeed", city=None)
        deduplicate([ba, indeed])
        assert indeed["is_duplicate"] is False

    def test_missing_date_skips_cross_source_dedup(self) -> None:
        ba = _make_record(job_id="BA_001", source="bundesagentur", posted_date=None)
        indeed = _make_record(job_id="IN_001", source="indeed", posted_date=None)
        deduplicate([ba, indeed])
        assert indeed["is_duplicate"] is False


# ---------------------------------------------------------------------------
# Source priority
# ---------------------------------------------------------------------------


class TestSourcePriority:
    def test_priority_order_constants(self) -> None:
        assert _SOURCE_PRIORITY["bundesagentur"] < _SOURCE_PRIORITY["indeed"]
        assert _SOURCE_PRIORITY["indeed"] < _SOURCE_PRIORITY["stepstone"]
        assert _SOURCE_PRIORITY["stepstone"] < _SOURCE_PRIORITY["linkedin"]

    def test_linkedin_deduped_against_ba(self) -> None:
        ba = _make_record(job_id="BA_001", source="bundesagentur")
        linkedin = _make_record(job_id="LI_001", source="linkedin")
        deduplicate([linkedin, ba])  # LinkedIn listed first
        assert ba["is_duplicate"] is False
        assert linkedin["is_duplicate"] is True
        assert linkedin["canonical_id"] == "BA_001"

    def test_stepstone_deduped_against_indeed(self) -> None:
        indeed = _make_record(job_id="IN_001", source="indeed")
        stepstone = _make_record(job_id="SS_001", source="stepstone")
        deduplicate([stepstone, indeed])
        assert indeed["is_duplicate"] is False
        assert stepstone["is_duplicate"] is True
        assert stepstone["canonical_id"] == "IN_001"


# ---------------------------------------------------------------------------
# Return value and mutation behaviour
# ---------------------------------------------------------------------------


class TestDeduplicateContract:
    def test_returns_same_list_object(self) -> None:
        records = [_make_record(job_id="BA_001")]
        result = deduplicate(records)
        assert result is records

    def test_non_dedup_fields_untouched(self) -> None:
        r = _make_record(job_id="BA_001", company="Zalando SE", city="Berlin")
        deduplicate([r])
        assert r["company"] == "Zalando SE"
        assert r["city"] == "Berlin"
        assert r["title_normalized"] == "data engineer"

    def test_empty_list_returns_empty_list(self) -> None:
        assert deduplicate([]) == []

    def test_single_record_never_marked_duplicate(self) -> None:
        r = _make_record()
        deduplicate([r])
        assert r["is_duplicate"] is False
        assert r["canonical_id"] is None
