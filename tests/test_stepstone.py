"""Tests for etl/extractors/stepstone.py."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from etl.extractors.stepstone import (
    SLEEP_MIN,
    SLEEP_MAX,
    _build_url,
    _parse_cards,
    _save_snapshot,
    _to_slug,
    fetch_jobs,
)

# ---------------------------------------------------------------------------
# Fixture HTML
# ---------------------------------------------------------------------------

_TWO_CARD_HTML = """
<html><body>
<article data-at="job-item" id="job-item-123456">
  <a data-at="job-item-title" href="/stellenangebot/senior-data-engineer-123456">Senior Data Engineer</a>
  <span data-at="job-item-company-name">TechCorp GmbH</span>
  <span data-at="job-item-location">Berlin</span>
  <time>vor 1 Tagen</time>
</article>
<article data-at="job-item" id="job-item-789012">
  <a data-at="job-item-title" href="/stellenangebot/data-analyst-789012">Data Analyst</a>
  <span data-at="job-item-company-name">Analytics AG</span>
  <span data-at="job-item-location">Berlin, Deutschland</span>
  <time>Gestern</time>
</article>
</body></html>
"""

_EMPTY_PAGE_HTML = """
<html><body>
<div class="no-results">Keine Ergebnisse gefunden.</div>
</body></html>
"""


def _make_response(status_code: int = 200, text: str = _TWO_CARD_HTML) -> MagicMock:
    """Return a mock requests.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    resp.ok = 200 <= status_code < 300
    return resp


def _patched_session(side_effect=None, return_value=None):
    """Context-manager helper: patches requests.Session and returns the mock session."""
    mock_session = MagicMock()
    if side_effect is not None:
        mock_session.get.side_effect = side_effect
    else:
        mock_session.get.return_value = return_value

    patcher = patch("etl.extractors.stepstone.requests.Session", return_value=mock_session)
    return patcher, mock_session


# ---------------------------------------------------------------------------
# _to_slug
# ---------------------------------------------------------------------------


class TestToSlug:
    def test_spaces_become_hyphens(self) -> None:
        assert _to_slug("data engineer") == "data-engineer"

    def test_multiple_spaces_collapse_to_one_hyphen(self) -> None:
        assert _to_slug("data  engineer") == "data-engineer"

    def test_already_hyphenated_unchanged(self) -> None:
        assert _to_slug("data-engineer") == "data-engineer"

    def test_uppercase_lowercased(self) -> None:
        assert _to_slug("Data Engineer") == "data-engineer"

    def test_umlaut_ue(self) -> None:
        assert _to_slug("münchen") == "muenchen"

    def test_umlaut_oe(self) -> None:
        assert _to_slug("köln") == "koeln"

    def test_umlaut_ae(self) -> None:
        assert _to_slug("düsseldorf") == "duesseldorf"

    def test_sharp_s(self) -> None:
        assert _to_slug("straße") == "strasse"

    def test_mixed_spaces_and_umlauts(self) -> None:
        assert _to_slug("Köln Straße") == "koeln-strasse"

    def test_leading_trailing_hyphens_stripped(self) -> None:
        assert _to_slug(" berlin ") == "berlin"


# ---------------------------------------------------------------------------
# _build_url
# ---------------------------------------------------------------------------


class TestBuildUrl:
    def test_page_1_has_no_query_param(self) -> None:
        url = _build_url("data-engineer", "berlin", 1)
        assert url == "https://www.stepstone.de/jobs/data-engineer/in-berlin"
        assert "page" not in url

    def test_page_2_appends_query_param(self) -> None:
        url = _build_url("data-engineer", "berlin", 2)
        assert url.endswith("?page=2")

    def test_keyword_and_location_in_path(self) -> None:
        url = _build_url("analytics-engineer", "hamburg", 1)
        assert "/jobs/analytics-engineer/in-hamburg" in url


# ---------------------------------------------------------------------------
# _parse_cards
# ---------------------------------------------------------------------------


class TestParseCards:
    def test_returns_one_dict_per_card(self) -> None:
        records = _parse_cards(_TWO_CARD_HTML, "data-engineer", "berlin")
        assert len(records) == 2

    def test_job_id_has_ss_prefix(self) -> None:
        records = _parse_cards(_TWO_CARD_HTML, "data-engineer", "berlin")
        assert all(r["job_id"].startswith("SS_") for r in records)

    def test_job_id_values(self) -> None:
        records = _parse_cards(_TWO_CARD_HTML, "data-engineer", "berlin")
        ids = {r["job_id"] for r in records}
        assert ids == {"SS_123456", "SS_789012"}

    def test_title_raw_extracted(self) -> None:
        records = _parse_cards(_TWO_CARD_HTML, "data-engineer", "berlin")
        titles = [r["title_raw"] for r in records]
        assert "Senior Data Engineer" in titles

    def test_company_extracted(self) -> None:
        records = _parse_cards(_TWO_CARD_HTML, "data-engineer", "berlin")
        companies = [r["company"] for r in records]
        assert "TechCorp GmbH" in companies

    def test_location_raw_extracted(self) -> None:
        records = _parse_cards(_TWO_CARD_HTML, "data-engineer", "berlin")
        first = next(r for r in records if r["job_id"] == "SS_123456")
        assert first["location_raw"] == "Berlin"

    def test_posted_date_raw_from_timeago(self) -> None:
        from datetime import date
        from unittest.mock import patch as _patch
        # "vor 1 Tagen" with today=2026-05-31 → 2026-05-30
        with _patch("etl.extractors.stepstone.date") as mock_date:
            mock_date.today.return_value = date(2026, 5, 31)
            records = _parse_cards(_TWO_CARD_HTML, "data-engineer", "berlin")
        first = next(r for r in records if r["job_id"] == "SS_123456")
        assert first["posted_date_raw"] == "2026-05-30"

    def test_relative_href_made_absolute(self) -> None:
        records = _parse_cards(_TWO_CARD_HTML, "data-engineer", "berlin")
        assert all(r["url"].startswith("https://www.stepstone.de") for r in records)

    def test_source_is_stepstone(self) -> None:
        records = _parse_cards(_TWO_CARD_HTML, "data-engineer", "berlin")
        assert all(r["source"] == "stepstone" for r in records)

    def test_source_keyword_attached(self) -> None:
        records = _parse_cards(_TWO_CARD_HTML, "data-engineer", "berlin")
        assert all(r["source_keyword"] == "data-engineer" for r in records)

    def test_source_city_attached(self) -> None:
        records = _parse_cards(_TWO_CARD_HTML, "data-engineer", "berlin")
        assert all(r["source_city"] == "berlin" for r in records)

    def test_empty_page_returns_empty_list(self) -> None:
        assert _parse_cards(_EMPTY_PAGE_HTML, "data-engineer", "berlin") == []

    def test_card_without_id_skipped(self) -> None:
        html = """
        <html><body>
        <article data-at="job-item">
          <a data-at="job-item-title">No ID Card</a>
          <span data-at="job-item-company-name">Corp</span>
        </article>
        </body></html>
        """
        assert _parse_cards(html, "data-engineer", "berlin") == []

    def test_missing_optional_fields_are_none(self) -> None:
        html = """
        <html><body>
        <article data-at="job-item" id="job-item-999">
          <a data-at="job-item-title" href="/job/999">Minimal Job</a>
        </article>
        </body></html>
        """
        records = _parse_cards(html, "data-engineer", "berlin")
        assert len(records) == 1
        assert records[0]["company"] is None
        assert records[0]["location_raw"] is None
        assert records[0]["posted_date_raw"] is None


# ---------------------------------------------------------------------------
# fetch_jobs — 403/429 handling
# ---------------------------------------------------------------------------


class TestFetchJobs403Handling:
    def test_403_stops_keyword_continues_next(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        def _side_effect(url: str, **kwargs: object) -> MagicMock:
            if "data-analyst" in url:
                return _make_response(403)
            return _make_response(200, _TWO_CARD_HTML)

        patcher, _ = _patched_session(side_effect=_side_effect)
        with patcher:
            with patch("etl.extractors.stepstone.time.sleep"):
                with patch("etl.extractors.stepstone.random.uniform", return_value=12.0):
                    with caplog.at_level("WARNING", logger="etl.extractors.stepstone"):
                        result = fetch_jobs(
                            keywords=["data-analyst", "data-engineer"],
                            locations=["berlin"],
                        )

        assert not any(r["source_keyword"] == "data-analyst" for r in result)
        assert any(r["source_keyword"] == "data-engineer" for r in result)
        assert "403" in caplog.text

    def test_429_stops_keyword_and_logs_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        patcher, _ = _patched_session(return_value=_make_response(429))
        with patcher:
            with patch("etl.extractors.stepstone.time.sleep"):
                with patch("etl.extractors.stepstone.random.uniform", return_value=12.0):
                    with caplog.at_level("WARNING", logger="etl.extractors.stepstone"):
                        result = fetch_jobs(keywords=["data-analyst"], locations=["berlin"])

        assert result == []
        assert "429" in caplog.text

    def test_403_does_not_abort_remaining_keywords(self) -> None:
        responses = {
            "data-analyst": _make_response(403),
            "data-engineer": _make_response(200, _TWO_CARD_HTML),
            "data-scientist": _make_response(200, _TWO_CARD_HTML),
        }

        def _side_effect(url: str, **kwargs: object) -> MagicMock:
            for kw, resp in responses.items():
                if kw in url:
                    return resp
            return _make_response(200, _EMPTY_PAGE_HTML)

        patcher, _ = _patched_session(side_effect=_side_effect)
        with patcher:
            with patch("etl.extractors.stepstone.time.sleep"):
                with patch("etl.extractors.stepstone.random.uniform", return_value=12.0):
                    result = fetch_jobs(
                        keywords=["data-analyst", "data-engineer", "data-scientist"],
                        locations=["berlin"],
                    )

        keywords_returned = {r["source_keyword"] for r in result}
        assert "data-engineer" in keywords_returned
        assert "data-scientist" in keywords_returned
        assert "data-analyst" not in keywords_returned


# ---------------------------------------------------------------------------
# fetch_jobs — rate limiting
# ---------------------------------------------------------------------------


class TestRateLimiting:
    def test_uniform_called_with_sleep_min_max(self) -> None:
        patcher, _ = _patched_session(return_value=_make_response(200, _TWO_CARD_HTML))
        with patcher:
            with patch("etl.extractors.stepstone.time.sleep"):
                with patch("etl.extractors.stepstone.random.uniform") as mock_uniform:
                    mock_uniform.return_value = 13.7
                    fetch_jobs(keywords=["data-analyst", "data-engineer"], locations=["berlin"])

        for c in mock_uniform.call_args_list:
            lo, hi = c.args
            assert lo == SLEEP_MIN
            assert hi == SLEEP_MAX

    def test_sleep_receives_uniform_return_value(self) -> None:
        patcher, _ = _patched_session(return_value=_make_response(200, _TWO_CARD_HTML))
        with patcher:
            with patch("etl.extractors.stepstone.time.sleep") as mock_sleep:
                with patch("etl.extractors.stepstone.random.uniform", return_value=14.5):
                    fetch_jobs(keywords=["data-analyst", "data-engineer"], locations=["berlin"])

        for c in mock_sleep.call_args_list:
            assert c.args == (14.5,)

    def test_no_sleep_before_first_request(self) -> None:
        patcher, _ = _patched_session(return_value=_make_response(200, _EMPTY_PAGE_HTML))
        with patcher:
            with patch("etl.extractors.stepstone.time.sleep") as mock_sleep:
                with patch("etl.extractors.stepstone.random.uniform", return_value=12.0):
                    fetch_jobs(keywords=["data-analyst"], locations=["berlin"])

        mock_sleep.assert_not_called()

    def test_sleep_count_matches_requests_minus_one(self) -> None:
        # 2 keywords × 2 pages each = 4 requests → 3 sleeps
        patcher, _ = _patched_session(return_value=_make_response(200, _TWO_CARD_HTML))
        with patcher:
            with patch("etl.extractors.stepstone.time.sleep") as mock_sleep:
                with patch("etl.extractors.stepstone.random.uniform", return_value=12.0):
                    fetch_jobs(keywords=["data-analyst", "data-engineer"], locations=["berlin"])

        assert mock_sleep.call_count == 3


# ---------------------------------------------------------------------------
# fetch_jobs — empty page handling
# ---------------------------------------------------------------------------


class TestEmptyPageHandling:
    def test_empty_first_page_returns_no_records(self) -> None:
        patcher, _ = _patched_session(return_value=_make_response(200, _EMPTY_PAGE_HTML))
        with patcher:
            with patch("etl.extractors.stepstone.time.sleep"):
                with patch("etl.extractors.stepstone.random.uniform", return_value=12.0):
                    result = fetch_jobs(keywords=["data-analyst"], locations=["berlin"])

        assert result == []

    def test_empty_second_page_stops_pagination(self) -> None:
        call_count = 0

        def _side_effect(url: str, **kwargs: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            return _make_response(200, _TWO_CARD_HTML if call_count == 1 else _EMPTY_PAGE_HTML)

        patcher, mock_session = _patched_session(side_effect=_side_effect)
        with patcher:
            with patch("etl.extractors.stepstone.time.sleep"):
                with patch("etl.extractors.stepstone.random.uniform", return_value=12.0):
                    result = fetch_jobs(keywords=["data-analyst"], locations=["berlin"])

        assert len(result) == 2
        assert mock_session.get.call_count == 2


# ---------------------------------------------------------------------------
# _save_snapshot
# ---------------------------------------------------------------------------


class TestSaveSnapshot:
    def test_file_created_at_expected_path(self, tmp_path: Path) -> None:
        path = _save_snapshot([{"job_id": "SS_1"}], "2026-05-30", base_dir=tmp_path)
        assert path == tmp_path / "2026-05-30" / "stepstone.json"
        assert path.exists()

    def test_json_content_matches_records(self, tmp_path: Path) -> None:
        records = [{"job_id": "SS_1", "title_raw": "Engineer"}, {"job_id": "SS_2"}]
        path = _save_snapshot(records, "2026-05-30", base_dir=tmp_path)
        assert json.loads(path.read_text(encoding="utf-8")) == records

    def test_empty_records_writes_empty_json_array(self, tmp_path: Path) -> None:
        path = _save_snapshot([], "2026-05-30", base_dir=tmp_path)
        assert json.loads(path.read_text(encoding="utf-8")) == []

    def test_creates_date_subdirectory(self, tmp_path: Path) -> None:
        _save_snapshot([], "2026-06-15", base_dir=tmp_path)
        assert (tmp_path / "2026-06-15").is_dir()

    def test_non_ascii_preserved(self, tmp_path: Path) -> None:
        records = [{"company": "Müller & Söhne GmbH"}]
        path = _save_snapshot(records, "2026-05-30", base_dir=tmp_path)
        raw = path.read_text(encoding="utf-8")
        assert "Müller" in raw
