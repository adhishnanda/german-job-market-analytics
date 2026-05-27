"""Tests for the Bundesagentur extractor."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest
import requests

from etl.extractors.bundesagentur import (
    _fetch_page,
    _save_snapshot,
    fetch_jobs,
)

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_response(data: dict, status_code: int = 200) -> MagicMock:
    """Build a mock requests.Response."""
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    resp.json.return_value = data
    if status_code >= 400:
        resp.raise_for_status.side_effect = requests.HTTPError(response=resp)
    else:
        resp.raise_for_status.return_value = None
    return resp


def _page_payload(jobs: list[dict], total: int) -> dict:
    return {"maxErgebnisse": total, "ergebnisliste": jobs}


def _make_job(n: int) -> dict:
    return {"referenznummer": f"ref{n}", "stellenangebotsTitel": f"Job {n}"}


# ---------------------------------------------------------------------------
# _fetch_page
# ---------------------------------------------------------------------------


class TestFetchPage:
    def test_success_returns_json(self) -> None:
        session = MagicMock(spec=requests.Session)
        payload = _page_payload([_make_job(1)], total=1)
        session.get.return_value = _make_response(payload)

        result = _fetch_page(session, "Data Engineer", "Berlin", 0)

        assert result == payload

    def test_http_error_returns_none(self) -> None:
        session = MagicMock(spec=requests.Session)
        session.get.return_value = _make_response({}, status_code=500)

        result = _fetch_page(session, "Data Engineer", "Berlin", 0)

        assert result is None

    def test_connection_error_returns_none(self) -> None:
        session = MagicMock(spec=requests.Session)
        session.get.side_effect = requests.ConnectionError("network down")

        result = _fetch_page(session, "Data Engineer", "Berlin", 0)

        assert result is None

    def test_timeout_returns_none(self) -> None:
        session = MagicMock(spec=requests.Session)
        session.get.side_effect = requests.Timeout("timed out")

        result = _fetch_page(session, "Data Engineer", "Berlin", 0)

        assert result is None


# ---------------------------------------------------------------------------
# fetch_jobs
# ---------------------------------------------------------------------------


class TestFetchJobs:
    def test_job_ids_prefixed_ba(self) -> None:
        payload = _page_payload([_make_job(1), _make_job(2)], total=2)

        with patch("etl.extractors.bundesagentur._fetch_page", return_value=payload):
            with patch("etl.extractors.bundesagentur.time.sleep"):
                results = fetch_jobs(["Data Engineer"], ["Berlin"])

        assert len(results) == 2
        assert all(r["job_id"].startswith("BA_") for r in results)

    def test_job_id_uses_referenznummer(self) -> None:
        payload = _page_payload([{"referenznummer": "10000-abc123", "stellenangebotsTitel": "Job"}], total=1)

        with patch("etl.extractors.bundesagentur._fetch_page", return_value=payload):
            with patch("etl.extractors.bundesagentur.time.sleep"):
                results = fetch_jobs(["Data Engineer"], ["Berlin"])

        assert results[0]["job_id"] == "BA_10000-abc123"

    def test_empty_results_returns_empty_list(self) -> None:
        payload = _page_payload([], total=0)

        with patch("etl.extractors.bundesagentur._fetch_page", return_value=payload):
            with patch("etl.extractors.bundesagentur.time.sleep"):
                results = fetch_jobs(["Data Engineer"], ["Berlin"])

        assert results == []

    def test_failed_fetch_returns_empty_list(self) -> None:
        with patch("etl.extractors.bundesagentur._fetch_page", return_value=None):
            with patch("etl.extractors.bundesagentur.time.sleep"):
                results = fetch_jobs(["Data Engineer"], ["Berlin"])

        assert results == []

    def test_pagination_stops_when_total_reached(self) -> None:
        jobs = [_make_job(i) for i in range(10)]
        payload = _page_payload(jobs, total=10)

        with patch(
            "etl.extractors.bundesagentur._fetch_page", return_value=payload
        ) as mock_fetch:
            with patch("etl.extractors.bundesagentur.time.sleep"):
                fetch_jobs(["Data Engineer"], ["Berlin"])

        mock_fetch.assert_called_once()

    def test_pagination_fetches_multiple_pages(self) -> None:
        jobs_p1 = [_make_job(i) for i in range(25)]
        jobs_p2 = [_make_job(i) for i in range(25, 50)]
        payload_p1 = _page_payload(jobs_p1, total=50)
        payload_p2 = _page_payload(jobs_p2, total=50)

        with patch(
            "etl.extractors.bundesagentur._fetch_page",
            side_effect=[payload_p1, payload_p2],
        ) as mock_fetch:
            with patch("etl.extractors.bundesagentur.time.sleep"):
                results = fetch_jobs(["Data Engineer"], ["Berlin"])

        assert mock_fetch.call_count == 2
        assert len(results) == 50

    def test_source_fields_added(self) -> None:
        payload = _page_payload([_make_job(1)], total=1)

        with patch("etl.extractors.bundesagentur._fetch_page", return_value=payload):
            with patch("etl.extractors.bundesagentur.time.sleep"):
                results = fetch_jobs(["Data Engineer"], ["Berlin"])

        assert results[0]["source_keyword"] == "Data Engineer"
        assert results[0]["source_city"] == "Berlin"

    def test_sleep_called_between_requests(self) -> None:
        jobs_p1 = [_make_job(i) for i in range(25)]
        jobs_p2 = [_make_job(i) for i in range(25, 50)]
        payload_p1 = _page_payload(jobs_p1, total=50)
        payload_p2 = _page_payload(jobs_p2, total=50)

        with patch(
            "etl.extractors.bundesagentur._fetch_page",
            side_effect=[payload_p1, payload_p2],
        ):
            with patch("etl.extractors.bundesagentur.time.sleep") as mock_sleep:
                fetch_jobs(["Data Engineer"], ["Berlin"])

        # first request has no sleep; second request does
        mock_sleep.assert_called_once_with(2.0)

    def test_no_sleep_before_first_request(self) -> None:
        payload = _page_payload([_make_job(1)], total=1)

        with patch("etl.extractors.bundesagentur._fetch_page", return_value=payload):
            with patch("etl.extractors.bundesagentur.time.sleep") as mock_sleep:
                fetch_jobs(["Data Engineer"], ["Berlin"])

        mock_sleep.assert_not_called()

    def test_multiple_keywords_and_cities(self) -> None:
        payload = _page_payload([_make_job(1)], total=1)

        with patch(
            "etl.extractors.bundesagentur._fetch_page", return_value=payload
        ) as mock_fetch:
            with patch("etl.extractors.bundesagentur.time.sleep"):
                results = fetch_jobs(["Data Engineer", "Data Analyst"], ["Berlin", "Munich"])

        # 2 keywords × 2 cities = 4 requests
        assert mock_fetch.call_count == 4
        assert len(results) == 4


# ---------------------------------------------------------------------------
# _save_snapshot
# ---------------------------------------------------------------------------


class TestSaveSnapshot:
    def test_creates_file_with_correct_content(self, tmp_path: Path) -> None:
        records = [_make_job(1), _make_job(2)]
        path = _save_snapshot(records, "2026-05-28", base_dir=tmp_path)

        assert path.exists()
        saved = json.loads(path.read_text(encoding="utf-8"))
        assert saved == records

    def test_creates_date_subdirectory(self, tmp_path: Path) -> None:
        _save_snapshot([_make_job(1)], "2026-05-28", base_dir=tmp_path)

        assert (tmp_path / "2026-05-28").is_dir()

    def test_returns_path_to_file(self, tmp_path: Path) -> None:
        path = _save_snapshot([_make_job(1)], "2026-05-28", base_dir=tmp_path)

        assert isinstance(path, Path)
        assert path.suffix == ".json"

    def test_empty_records_writes_empty_array(self, tmp_path: Path) -> None:
        path = _save_snapshot([], "2026-05-28", base_dir=tmp_path)

        saved = json.loads(path.read_text(encoding="utf-8"))
        assert saved == []
