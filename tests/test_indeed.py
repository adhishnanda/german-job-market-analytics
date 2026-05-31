"""Tests for etl/extractors/indeed.py."""

from __future__ import annotations

import csv
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from etl.extractors.indeed import (
    SLEEP_SECONDS,
    _city_from_url,
    _fetch_feed,
    _jk_from_url,
    _parse_entry,
    _save_snapshot,
    fetch_jobs,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entry(
    n: int,
    jk: str | None = None,
    author: str | None = "Acme GmbH",
) -> SimpleNamespace:
    """Return a minimal feedparser-style entry object."""
    jk_val = jk or f"jk{n:04d}"
    return SimpleNamespace(
        id=f"https://de.indeed.com/viewjob?jk={jk_val}",
        title=f"Data Engineer {n}",
        author=author,
        link=f"https://de.indeed.com/viewjob?jk={jk_val}",
        published=f"Mon, {n + 1:02d} May 2026 08:00:00 GMT",
        summary=f"<p>We are looking for Data Engineer {n} with Python skills.</p>",
    )


def _make_entry_no_jk(n: int) -> SimpleNamespace:
    """Return a feedparser entry whose id has no jk parameter."""
    return SimpleNamespace(
        id=f"de.indeed.com/rc/clk?hash=opaque{n}",
        title=f"Analyst {n}",
        author="Corp AG",
        link=f"https://de.indeed.com/rc/clk?hash=opaque{n}",
        published=f"Tue, {n + 1:02d} May 2026 09:00:00 GMT",
        summary="Description text.",
    )


def _make_parsed(
    entries: list[Any],
    status: int = 200,
    bozo: bool = False,
    bozo_exception: Exception | None = None,
) -> dict[str, Any]:
    """Build a mock feedparser result dict."""
    result: dict[str, Any] = {
        "entries": entries,
        "status": status,
        "bozo": bozo,
    }
    if bozo_exception is not None:
        result["bozo_exception"] = bozo_exception
    return result


_FEED_URL = "https://de.indeed.com/rss?q=Data+Engineer&l=Berlin&sort=date"


# ---------------------------------------------------------------------------
# _city_from_url
# ---------------------------------------------------------------------------


class TestCityFromUrl:
    def test_berlin_extracted(self) -> None:
        assert _city_from_url(_FEED_URL) == "Berlin"

    def test_deutschland_extracted(self) -> None:
        url = (
            "https://de.indeed.com/rss?q=Business+Intelligence&l=Deutschland&sort=date"
        )
        assert _city_from_url(url) == "Deutschland"

    def test_missing_l_param_returns_none(self) -> None:
        assert (
            _city_from_url("https://de.indeed.com/rss?q=Data+Engineer&sort=date")
            is None
        )

    def test_url_encoded_spaces_decoded(self) -> None:
        url = "https://de.indeed.com/rss?q=Data+Engineer&l=Frankfurt+am+Main"
        assert _city_from_url(url) == "Frankfurt am Main"


# ---------------------------------------------------------------------------
# _jk_from_url
# ---------------------------------------------------------------------------


class TestJkFromUrl:
    def test_jk_extracted(self) -> None:
        assert _jk_from_url("https://de.indeed.com/viewjob?jk=abc123") == "abc123"

    def test_no_jk_returns_none(self) -> None:
        assert _jk_from_url("https://de.indeed.com/rc/clk?hash=xyz") is None

    def test_empty_string_returns_none(self) -> None:
        assert _jk_from_url("") is None


# ---------------------------------------------------------------------------
# _parse_entry
# ---------------------------------------------------------------------------


class TestParseEntry:
    def test_all_fields_present(self) -> None:
        record = _parse_entry(_make_entry(0), "Berlin")
        assert set(record.keys()) == {
            "source",
            "job_id_raw",
            "title_raw",
            "company_raw",
            "url",
            "posted_at_raw",
            "description_raw",
            "city_raw",
        }

    def test_in_prefix_applied(self) -> None:
        record = _parse_entry(_make_entry(0), "Berlin")
        assert record["job_id_raw"].startswith("IN_")

    def test_jk_used_as_id(self) -> None:
        entry = _make_entry(0, jk="abc123")
        record = _parse_entry(entry, "Berlin")
        assert record["job_id_raw"] == "IN_abc123"

    def test_fallback_to_full_entry_id_when_no_jk(self) -> None:
        entry = _make_entry_no_jk(0)
        record = _parse_entry(entry, "Berlin")
        assert record["job_id_raw"] == f"IN_{entry.id}"

    def test_missing_author_is_none(self) -> None:
        entry = _make_entry(0, author=None)
        record = _parse_entry(entry, "Berlin")
        assert record["company_raw"] is None

    def test_city_raw_passed_through(self) -> None:
        record = _parse_entry(_make_entry(0), "München")
        assert record["city_raw"] == "München"

    def test_city_raw_none_when_not_provided(self) -> None:
        record = _parse_entry(_make_entry(0), None)
        assert record["city_raw"] is None

    def test_source_is_indeed(self) -> None:
        record = _parse_entry(_make_entry(0), "Berlin")
        assert record["source"] == "indeed"

    def test_title_raw_mapped(self) -> None:
        entry = _make_entry(7)
        record = _parse_entry(entry, "Berlin")
        assert record["title_raw"] == entry.title

    def test_posted_at_raw_mapped(self) -> None:
        entry = _make_entry(3)
        record = _parse_entry(entry, "Berlin")
        assert record["posted_at_raw"] == entry.published


# ---------------------------------------------------------------------------
# _fetch_feed
# ---------------------------------------------------------------------------


class TestFetchFeed:
    def test_returns_one_dict_per_entry(self) -> None:
        entries = [_make_entry(i) for i in range(3)]
        with patch(
            "etl.extractors.indeed.feedparser.parse", return_value=_make_parsed(entries)
        ):
            result = _fetch_feed(_FEED_URL)
        assert len(result) == 3

    def test_records_have_correct_structure(self) -> None:
        entries = [_make_entry(0)]
        with patch(
            "etl.extractors.indeed.feedparser.parse", return_value=_make_parsed(entries)
        ):
            result = _fetch_feed(_FEED_URL)
        assert result[0]["source"] == "indeed"
        assert result[0]["city_raw"] == "Berlin"

    def test_empty_entries_returns_empty_list(self) -> None:
        with patch(
            "etl.extractors.indeed.feedparser.parse", return_value=_make_parsed([])
        ):
            result = _fetch_feed(_FEED_URL)
        assert result == []

    def test_http_404_returns_empty_list(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with patch(
            "etl.extractors.indeed.feedparser.parse",
            return_value=_make_parsed([], status=404),
        ):
            with caplog.at_level("ERROR", logger="etl.extractors.indeed"):
                result = _fetch_feed(_FEED_URL)
        assert result == []
        assert "404" in caplog.text

    def test_bozo_with_no_entries_returns_empty_list(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        exc = Exception("malformed feed")
        with patch(
            "etl.extractors.indeed.feedparser.parse",
            return_value=_make_parsed([], bozo=True, bozo_exception=exc),
        ):
            with caplog.at_level("ERROR", logger="etl.extractors.indeed"):
                result = _fetch_feed(_FEED_URL)
        assert result == []
        assert "parse error" in caplog.text.lower()

    def test_feedparser_exception_returns_empty_list(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with patch(
            "etl.extractors.indeed.feedparser.parse",
            side_effect=RuntimeError("network down"),
        ):
            with caplog.at_level("ERROR", logger="etl.extractors.indeed"):
                result = _fetch_feed(_FEED_URL)
        assert result == []
        assert "feedparser raised" in caplog.text

    def test_bozo_true_with_entries_still_returns_records(self) -> None:
        # A feed can be bozo=True (e.g. minor XML warning) yet still yield entries.
        entries = [_make_entry(0)]
        with patch(
            "etl.extractors.indeed.feedparser.parse",
            return_value=_make_parsed(entries, bozo=True),
        ):
            result = _fetch_feed(_FEED_URL)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# fetch_jobs
# ---------------------------------------------------------------------------


class TestFetchJobs:
    def test_flat_list_across_two_feeds(self) -> None:
        feed_a = [_make_entry(i, jk=f"a{i}") for i in range(2)]
        feed_b = [_make_entry(i, jk=f"b{i}") for i in range(2)]
        call_count = 0

        def _mock_parse(url: str) -> dict[str, Any]:
            nonlocal call_count
            entries = feed_a if call_count == 0 else feed_b
            call_count += 1
            return _make_parsed(entries)

        with patch("etl.extractors.indeed.feedparser.parse", side_effect=_mock_parse):
            with patch("etl.extractors.indeed.time.sleep"):
                result = fetch_jobs(["url_a", "url_b"])

        assert len(result) == 4

    def test_sleep_called_between_feeds(self) -> None:
        with patch(
            "etl.extractors.indeed.feedparser.parse",
            return_value=_make_parsed([_make_entry(0)]),
        ):
            with patch("etl.extractors.indeed.time.sleep") as mock_sleep:
                fetch_jobs(["url_1", "url_2", "url_3"])

        assert mock_sleep.call_count == 2
        mock_sleep.assert_called_with(SLEEP_SECONDS)

    def test_no_sleep_before_first_feed(self) -> None:
        with patch(
            "etl.extractors.indeed.feedparser.parse",
            return_value=_make_parsed([]),
        ):
            with patch("etl.extractors.indeed.time.sleep") as mock_sleep:
                fetch_jobs(["url_1"])

        mock_sleep.assert_not_called()

    def test_deduplication_same_jk_in_two_feeds(self) -> None:
        shared_entry = _make_entry(0, jk="shared999")
        unique_entry = _make_entry(1, jk="unique001")

        def _mock_parse(url: str) -> dict[str, Any]:
            if url == "url_a":
                return _make_parsed([shared_entry])
            return _make_parsed([shared_entry, unique_entry])

        with patch("etl.extractors.indeed.feedparser.parse", side_effect=_mock_parse):
            with patch("etl.extractors.indeed.time.sleep"):
                result = fetch_jobs(["url_a", "url_b"])

        assert len(result) == 2
        ids = [r["job_id_raw"] for r in result]
        assert ids.count("IN_shared999") == 1

    def test_failed_feed_does_not_abort_run(self) -> None:
        good_entries = [_make_entry(i) for i in range(3)]

        def _mock_parse(url: str) -> dict[str, Any]:
            if url == "url_bad":
                return _make_parsed([], status=503)
            return _make_parsed(good_entries)

        with patch("etl.extractors.indeed.feedparser.parse", side_effect=_mock_parse):
            with patch("etl.extractors.indeed.time.sleep"):
                result = fetch_jobs(["url_bad", "url_good"])

        assert len(result) == 3

    def test_empty_feeds_list_returns_empty(self) -> None:
        with patch("etl.extractors.indeed.time.sleep") as mock_sleep:
            result = fetch_jobs([])
        assert result == []
        mock_sleep.assert_not_called()

    def test_all_records_have_source_indeed(self) -> None:
        entries = [_make_entry(i) for i in range(5)]
        with patch(
            "etl.extractors.indeed.feedparser.parse", return_value=_make_parsed(entries)
        ):
            with patch("etl.extractors.indeed.time.sleep"):
                result = fetch_jobs(["url_1"])
        assert all(r["source"] == "indeed" for r in result)


# ---------------------------------------------------------------------------
# _save_snapshot
# ---------------------------------------------------------------------------


class TestSaveSnapshot:
    def test_file_created_at_expected_path(self, tmp_path: Path) -> None:
        records = [_parse_entry(_make_entry(0), "Berlin")]
        path = _save_snapshot(records, "2026-05-30", base_dir=tmp_path)
        assert path == tmp_path / "2026-05-30" / "indeed_rss.csv"
        assert path.exists()

    def test_csv_header_contains_all_fields(self, tmp_path: Path) -> None:
        records = [_parse_entry(_make_entry(0), "Berlin")]
        path = _save_snapshot(records, "2026-05-30", base_dir=tmp_path)
        with path.open(encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            assert set(reader.fieldnames or []) == {
                "source",
                "job_id_raw",
                "title_raw",
                "company_raw",
                "url",
                "posted_at_raw",
                "description_raw",
                "city_raw",
            }

    def test_csv_row_count_matches_records(self, tmp_path: Path) -> None:
        records = [_parse_entry(_make_entry(i), "Berlin") for i in range(5)]
        path = _save_snapshot(records, "2026-05-30", base_dir=tmp_path)
        with path.open(encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        assert len(rows) == 5

    def test_empty_records_writes_header_only(self, tmp_path: Path) -> None:
        path = _save_snapshot([], "2026-05-30", base_dir=tmp_path)
        with path.open(encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        assert rows == []

    def test_creates_date_subdirectory(self, tmp_path: Path) -> None:
        _save_snapshot([], "2026-06-15", base_dir=tmp_path)
        assert (tmp_path / "2026-06-15").is_dir()
