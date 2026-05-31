"""Tests for the normalizer transformer."""

from __future__ import annotations

from datetime import date, datetime
from unittest.mock import patch

import pytest

from etl.transformers.normalizer import (
    _assign_role_category,
    _map_employment_type,
    _map_work_model,
    _parse_posted_date,
    normalize,
)

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

_CANONICAL_FIELDS = {
    "job_id",
    "source",
    "source_keyword",
    "source_city",
    "snapshot_date",
    "fetched_at",
    "url",
    "title_raw",
    "description_raw",
    "salary_raw",
    "title_normalized",
    "company",
    "city",
    "region",
    "country",
    "postal_code",
    "lat",
    "lon",
    "posted_date",
    "employment_type",
    "work_model",
    "language",
    "role_category",
    "skills",
    "salary_min",
    "salary_max",
    "salary_currency",
    "is_duplicate",
    "canonical_id",
}


def _make_ba_raw(**overrides: object) -> dict:
    """Return a minimal valid raw BA dict (as produced by the extractor)."""
    raw: dict = {
        "job_id": "BA_10000-abc123",
        "referenznummer": "10000-abc123",
        "stellenangebotsTitel": "Senior Data Engineer (w/m/d)",
        "firma": "Zalando SE",
        "stellenlokationen": [
            {
                "adresse": {
                    "ort": "Berlin",
                    "bundesland": "BERLIN",
                    "plz": "10247",
                },
                "breite": 52.5145,
                "laenge": 13.4655,
            }
        ],
        "veroeffentlichungszeitraum": {"von": "2026-05-11"},
        "arbeitszeitVollzeit": True,
        "homeofficetyp": "VOLLSTAENDIG_IM_HOMEOFFICE",
        "source_keyword": "Data Engineer",
        "source_city": "Berlin",
    }
    raw.update(overrides)
    return raw


# ---------------------------------------------------------------------------
# _map_work_model
# ---------------------------------------------------------------------------


class TestMapWorkModel:
    def test_remote(self) -> None:
        assert _map_work_model("VOLLSTAENDIG_IM_HOMEOFFICE") == "REMOTE"

    def test_hybrid(self) -> None:
        assert _map_work_model("NACH_VEREINBARUNG") == "HYBRID"

    def test_onsite(self) -> None:
        assert _map_work_model("KEIN_HOMEOFFICE") == "ONSITE"

    def test_none_returns_unknown(self) -> None:
        assert _map_work_model(None) == "UNKNOWN"

    def test_unrecognised_returns_unknown(self) -> None:
        assert _map_work_model("SOMETHING_NEW") == "UNKNOWN"


# ---------------------------------------------------------------------------
# _map_employment_type
# ---------------------------------------------------------------------------


class TestMapEmploymentType:
    def test_true_returns_full_time(self) -> None:
        assert _map_employment_type(True) == "FULL_TIME"

    def test_false_returns_part_time(self) -> None:
        assert _map_employment_type(False) == "PART_TIME"

    def test_none_returns_unknown(self) -> None:
        assert _map_employment_type(None) == "UNKNOWN"


# ---------------------------------------------------------------------------
# _assign_role_category
# ---------------------------------------------------------------------------


class TestAssignRoleCategory:
    def test_data_engineering(self) -> None:
        assert _assign_role_category("senior data engineer") == "Data Engineering"

    def test_analytics_engineering(self) -> None:
        assert (
            _assign_role_category("analytics engineer dbt") == "Analytics Engineering"
        )

    def test_data_science(self) -> None:
        assert (
            _assign_role_category("data scientist machine learning")
            == "Data Science / ML"
        )

    def test_data_analysis(self) -> None:
        assert _assign_role_category("data analyst power bi") == "Data Analysis / BI"

    def test_ml_engineering(self) -> None:
        assert _assign_role_category("mlops engineer") == "ML Engineering"

    def test_data_architect(self) -> None:
        assert _assign_role_category("senior data architect") == "Data Architect"

    def test_unmatched_returns_other(self) -> None:
        assert _assign_role_category("project manager scrum") == "Other"

    def test_taxonomy_precedence_data_engineering_before_analytics(self) -> None:
        # "data engineer" matches Data Engineering before Analytics Engineering
        assert _assign_role_category("analytics data engineer") == "Data Engineering"


# ---------------------------------------------------------------------------
# normalize — field mapping
# ---------------------------------------------------------------------------


class TestNormalizeBaFields:
    def test_job_id_preserved(self) -> None:
        result = normalize(_make_ba_raw(), "bundesagentur")
        assert result["job_id"] == "BA_10000-abc123"

    def test_source_set(self) -> None:
        result = normalize(_make_ba_raw(), "bundesagentur")
        assert result["source"] == "bundesagentur"

    def test_title_raw_preserved(self) -> None:
        result = normalize(_make_ba_raw(), "bundesagentur")
        assert result["title_raw"] == "Senior Data Engineer (w/m/d)"

    def test_title_normalized_lowercased_and_stripped(self) -> None:
        result = normalize(
            _make_ba_raw(stellenangebotsTitel="  Senior Data Engineer  "),
            "bundesagentur",
        )
        assert result["title_normalized"] == "senior data engineer"

    def test_company_mapped(self) -> None:
        result = normalize(_make_ba_raw(), "bundesagentur")
        assert result["company"] == "Zalando SE"

    def test_city_from_lokationen(self) -> None:
        result = normalize(_make_ba_raw(), "bundesagentur")
        assert result["city"] == "Berlin"

    def test_region_from_lokationen(self) -> None:
        result = normalize(_make_ba_raw(), "bundesagentur")
        assert result["region"] == "BERLIN"

    def test_postal_code_from_lokationen(self) -> None:
        result = normalize(_make_ba_raw(), "bundesagentur")
        assert result["postal_code"] == "10247"

    def test_lat_lon_from_lokationen(self) -> None:
        result = normalize(_make_ba_raw(), "bundesagentur")
        assert result["lat"] == pytest.approx(52.5145)
        assert result["lon"] == pytest.approx(13.4655)

    def test_missing_lokationen_gives_none_location_fields(self) -> None:
        result = normalize(_make_ba_raw(stellenlokationen=[]), "bundesagentur")
        assert result["city"] is None
        assert result["region"] is None
        assert result["postal_code"] is None
        assert result["lat"] is None
        assert result["lon"] is None

    def test_country_always_de(self) -> None:
        result = normalize(_make_ba_raw(), "bundesagentur")
        assert result["country"] == "DE"

    def test_posted_date_parsed(self) -> None:
        result = normalize(_make_ba_raw(), "bundesagentur")
        assert result["posted_date"] == date(2026, 5, 11)

    def test_posted_date_missing_gives_none(self) -> None:
        result = normalize(_make_ba_raw(veroeffentlichungszeitraum={}), "bundesagentur")
        assert result["posted_date"] is None

    def test_work_model_mapped(self) -> None:
        result = normalize(
            _make_ba_raw(homeofficetyp="NACH_VEREINBARUNG"), "bundesagentur"
        )
        assert result["work_model"] == "HYBRID"

    def test_employment_type_mapped(self) -> None:
        result = normalize(_make_ba_raw(arbeitszeitVollzeit=False), "bundesagentur")
        assert result["employment_type"] == "PART_TIME"

    def test_role_category_assigned(self) -> None:
        result = normalize(
            _make_ba_raw(stellenangebotsTitel="Data Engineer"), "bundesagentur"
        )
        assert result["role_category"] == "Data Engineering"

    def test_url_constructed_from_referenznummer(self) -> None:
        result = normalize(_make_ba_raw(), "bundesagentur")
        assert "10000-abc123" in result["url"]
        assert result["url"].startswith("https://")

    def test_url_none_when_referenznummer_missing(self) -> None:
        raw = _make_ba_raw()
        del raw["referenznummer"]
        result = normalize(raw, "bundesagentur")
        assert result["url"] is None

    def test_source_keyword_and_city_preserved(self) -> None:
        result = normalize(_make_ba_raw(), "bundesagentur")
        assert result["source_keyword"] == "Data Engineer"
        assert result["source_city"] == "Berlin"

    def test_snapshot_date_is_today(self) -> None:
        result = normalize(_make_ba_raw(), "bundesagentur")
        assert result["snapshot_date"] == date.today()

    def test_fetched_at_is_datetime(self) -> None:
        result = normalize(_make_ba_raw(), "bundesagentur")
        assert isinstance(result["fetched_at"], datetime)

    def test_description_raw_defaults_to_empty(self) -> None:
        result = normalize(_make_ba_raw(), "bundesagentur")
        assert result["description_raw"] == ""

    def test_description_raw_preserved_when_present(self) -> None:
        result = normalize(
            _make_ba_raw(description_raw="We need Python skills."), "bundesagentur"
        )
        assert result["description_raw"] == "We need Python skills."


# ---------------------------------------------------------------------------
# normalize — language detection
# ---------------------------------------------------------------------------


class TestNormalizeLanguage:
    def test_language_detected_english(self) -> None:
        with patch("etl.transformers.normalizer.detect", return_value="en"):
            result = normalize(
                _make_ba_raw(description_raw="We are looking for a skilled engineer."),
                "bundesagentur",
            )
        assert result["language"] == "en"

    def test_language_detected_german(self) -> None:
        with patch("etl.transformers.normalizer.detect", return_value="de"):
            result = normalize(
                _make_ba_raw(description_raw="Wir suchen einen erfahrenen Ingenieur."),
                "bundesagentur",
            )
        assert result["language"] == "de"

    def test_language_unknown_when_description_empty(self) -> None:
        result = normalize(_make_ba_raw(description_raw=""), "bundesagentur")
        assert result["language"] == "unknown"


# ---------------------------------------------------------------------------
# normalize — downstream field defaults
# ---------------------------------------------------------------------------


class TestNormalizeDownstreamDefaults:
    def test_skills_initialised_empty(self) -> None:
        result = normalize(_make_ba_raw(), "bundesagentur")
        assert result["skills"] == []

    def test_salary_fields_none(self) -> None:
        result = normalize(_make_ba_raw(), "bundesagentur")
        assert result["salary_min"] is None
        assert result["salary_max"] is None
        assert result["salary_currency"] is None

    def test_is_duplicate_false(self) -> None:
        result = normalize(_make_ba_raw(), "bundesagentur")
        assert result["is_duplicate"] is False

    def test_canonical_id_none(self) -> None:
        result = normalize(_make_ba_raw(), "bundesagentur")
        assert result["canonical_id"] is None

    def test_all_canonical_fields_present(self) -> None:
        result = normalize(_make_ba_raw(), "bundesagentur")
        assert _CANONICAL_FIELDS == set(result.keys())


# ---------------------------------------------------------------------------
# normalize — unknown source
# ---------------------------------------------------------------------------


class TestNormalizeUnknownSource:
    def test_unknown_source_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Unknown source"):
            normalize(_make_ba_raw(), "twitter")


# ---------------------------------------------------------------------------
# _parse_posted_date — all four supported formats
# ---------------------------------------------------------------------------


class TestParsePostedDate:
    def test_iso_date_yyyy_mm_dd(self) -> None:
        assert _parse_posted_date("2026-05-11") == date(2026, 5, 11)

    def test_iso_datetime_with_time_component(self) -> None:
        assert _parse_posted_date("2026-05-30T10:00:00") == date(2026, 5, 30)

    def test_dd_mm_yyyy_linkedin_manual(self) -> None:
        assert _parse_posted_date("30-05-2026") == date(2026, 5, 30)

    def test_rfc2822_indeed_rss(self) -> None:
        assert _parse_posted_date("Mon, 27 May 2026 10:00:00 GMT") == date(2026, 5, 27)

    def test_none_input_returns_none(self) -> None:
        assert _parse_posted_date(None) is None

    def test_empty_string_returns_none(self) -> None:
        assert _parse_posted_date("") is None

    def test_unrecognised_format_returns_none(self) -> None:
        assert _parse_posted_date("last quarter") is None


# ---------------------------------------------------------------------------
# normalize — Stepstone and LinkedIn dispatch
# ---------------------------------------------------------------------------


def _make_stepstone_raw(**overrides: object) -> dict:
    """Return a minimal valid raw Stepstone dict (as produced by the extractor)."""
    raw: dict = {
        "job_id": "SS_99001",
        "title_raw": "Data Scientist",
        "company": "SS GmbH",
        "location_raw": "Berlin",
        "posted_date_raw": "2026-05-10T09:30:00",
        "url": "https://www.stepstone.de/job/99001",
        "source_keyword": "data-scientist",
        "source_city": "berlin",
    }
    raw.update(overrides)
    return raw


def _make_linkedin_raw(**overrides: object) -> dict:
    """Return a minimal valid raw LinkedIn dict (as produced by the extractor)."""
    raw: dict = {
        "source": "linkedin",
        "job_id_raw": "LI_li001",
        "title_raw": "Data Analyst",
        "company_raw": "LI GmbH",
        "city_raw": "Berlin",
        "posted_at_raw": "30-05-2026",
        "description_raw": "Seeking a data analyst with SQL skills.",
        "url": "https://www.linkedin.com/jobs/view/li001",
        "employment_type": "Full-time",
        "applicant_count": 45,
        "is_remote": False,
    }
    raw.update(overrides)
    return raw


class TestNormalizeStepstoneFields:
    def test_job_id_preserved(self) -> None:
        result = normalize(_make_stepstone_raw(), "stepstone")
        assert result["job_id"] == "SS_99001"

    def test_source_set(self) -> None:
        result = normalize(_make_stepstone_raw(), "stepstone")
        assert result["source"] == "stepstone"

    def test_city_from_location_raw(self) -> None:
        result = normalize(_make_stepstone_raw(), "stepstone")
        assert result["city"] == "Berlin"

    def test_posted_date_parsed_from_iso_datetime(self) -> None:
        result = normalize(_make_stepstone_raw(), "stepstone")
        assert result["posted_date"] == date(2026, 5, 10)

    def test_all_canonical_fields_present(self) -> None:
        result = normalize(_make_stepstone_raw(), "stepstone")
        assert _CANONICAL_FIELDS == set(result.keys())

    def test_company_mapped(self) -> None:
        result = normalize(_make_stepstone_raw(), "stepstone")
        assert result["company"] == "SS GmbH"


class TestNormalizeLinkedInFields:
    def test_job_id_from_job_id_raw(self) -> None:
        result = normalize(_make_linkedin_raw(), "linkedin")
        assert result["job_id"] == "LI_li001"

    def test_source_set(self) -> None:
        result = normalize(_make_linkedin_raw(), "linkedin")
        assert result["source"] == "linkedin"

    def test_city_from_city_raw(self) -> None:
        result = normalize(_make_linkedin_raw(), "linkedin")
        assert result["city"] == "Berlin"

    def test_dd_mm_yyyy_posted_date_parsed(self) -> None:
        result = normalize(_make_linkedin_raw(), "linkedin")
        assert result["posted_date"] == date(2026, 5, 30)

    def test_is_remote_false_maps_to_onsite(self) -> None:
        result = normalize(_make_linkedin_raw(is_remote=False), "linkedin")
        assert result["work_model"] == "ONSITE"

    def test_is_remote_true_maps_to_unknown(self) -> None:
        result = normalize(_make_linkedin_raw(is_remote=True), "linkedin")
        assert result["work_model"] == "UNKNOWN"

    def test_employment_type_full_time(self) -> None:
        result = normalize(_make_linkedin_raw(employment_type="Full-time"), "linkedin")
        assert result["employment_type"] == "FULL_TIME"

    def test_all_canonical_fields_present(self) -> None:
        result = normalize(_make_linkedin_raw(), "linkedin")
        assert _CANONICAL_FIELDS == set(result.keys())
