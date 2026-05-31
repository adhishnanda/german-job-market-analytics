"""Tests for etl/extractors/linkedin.py."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import pytest

from etl.extractors.linkedin import (
    REQUIRED_COLUMNS,
    _parse_relative_date,
    _parse_row,
    _read_csv,
    _validate_columns,
    read_csvs,
)

_FULL_ROW: dict[str, str] = {
    "job_id_raw": "3892741056",
    "title_raw": "Senior Data Analyst (f/m/d)",
    "company_raw": "Zalando SE",
    "city_raw": "Berlin",
    "posted_at_raw": "2026-05-28",
    "description_raw": "We are looking for a Senior Data Analyst...",
    "url": "https://www.linkedin.com/jobs/view/3892741056/",
    "employment_type": "FULL_TIME",
    "applicant_count": "47",
    "is_remote": "false",
}


def _write_csv(
    path: Path,
    rows: list[dict[str, Any]],
    fieldnames: list[str] | None = None,
) -> None:
    """Write rows to a CSV file; infers fieldnames from first row if not supplied."""
    if fieldnames is None:
        fieldnames = list(rows[0].keys()) if rows else []
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _make_snap(base: Path, date_str: str = "2026-05-30") -> Path:
    """Create and return a dated subdirectory for snapshot files."""
    d = base / date_str
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# _validate_columns
# ---------------------------------------------------------------------------


class TestValidateColumns:
    def test_all_required_present_does_not_raise(self, tmp_path: Path) -> None:
        _validate_columns(["job_id_raw", "title_raw", "company_raw"], tmp_path / "f.csv")

    def test_missing_job_id_raw_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="job_id_raw"):
            _validate_columns(["title_raw", "company_raw"], tmp_path / "f.csv")

    def test_missing_title_raw_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="title_raw"):
            _validate_columns(["job_id_raw", "company_raw"], tmp_path / "f.csv")

    def test_missing_both_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="missing required columns"):
            _validate_columns(["company_raw"], tmp_path / "f.csv")

    def test_extra_columns_are_accepted(self, tmp_path: Path) -> None:
        _validate_columns(["job_id_raw", "title_raw", "extra_col"], tmp_path / "f.csv")

    def test_required_columns_constant_contains_expected_keys(self) -> None:
        assert REQUIRED_COLUMNS == {"job_id_raw", "title_raw"}


# ---------------------------------------------------------------------------
# _parse_row
# ---------------------------------------------------------------------------


class TestParseRow:
    def test_all_fields_present_in_output(self) -> None:
        record = _parse_row(_FULL_ROW, 2, Path("f.csv"))
        assert record is not None
        assert set(record.keys()) == {
            "source",
            "job_id_raw",
            "title_raw",
            "company_raw",
            "city_raw",
            "posted_at_raw",
            "description_raw",
            "url",
            "employment_type",
            "applicant_count",
            "is_remote",
        }

    def test_li_prefix_applied(self) -> None:
        record = _parse_row(_FULL_ROW, 2, Path("f.csv"))
        assert record is not None
        assert record["job_id_raw"] == "LI_3892741056"

    def test_source_is_linkedin(self) -> None:
        record = _parse_row(_FULL_ROW, 2, Path("f.csv"))
        assert record is not None
        assert record["source"] == "linkedin"

    def test_missing_job_id_returns_none_and_warns(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        row = {**_FULL_ROW, "job_id_raw": ""}
        with caplog.at_level("WARNING", logger="etl.extractors.linkedin"):
            result = _parse_row(row, 2, Path("f.csv"))
        assert result is None
        assert "job_id_raw" in caplog.text

    def test_missing_title_returns_none_and_warns(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        row = {**_FULL_ROW, "title_raw": ""}
        with caplog.at_level("WARNING", logger="etl.extractors.linkedin"):
            result = _parse_row(row, 3, Path("f.csv"))
        assert result is None
        assert "title_raw" in caplog.text

    def test_is_remote_false_parsed(self) -> None:
        record = _parse_row({**_FULL_ROW, "is_remote": "false"}, 2, Path("f.csv"))
        assert record is not None
        assert record["is_remote"] is False

    def test_is_remote_true_parsed(self) -> None:
        record = _parse_row({**_FULL_ROW, "is_remote": "true"}, 2, Path("f.csv"))
        assert record is not None
        assert record["is_remote"] is True

    def test_is_remote_yes_parsed_as_true(self) -> None:
        record = _parse_row({**_FULL_ROW, "is_remote": "yes"}, 2, Path("f.csv"))
        assert record is not None
        assert record["is_remote"] is True

    def test_is_remote_empty_is_none(self) -> None:
        record = _parse_row({**_FULL_ROW, "is_remote": ""}, 2, Path("f.csv"))
        assert record is not None
        assert record["is_remote"] is None

    def test_applicant_count_parsed_as_int(self) -> None:
        record = _parse_row(_FULL_ROW, 2, Path("f.csv"))
        assert record is not None
        assert record["applicant_count"] == 47

    def test_applicant_count_empty_is_none(self) -> None:
        record = _parse_row({**_FULL_ROW, "applicant_count": ""}, 2, Path("f.csv"))
        assert record is not None
        assert record["applicant_count"] is None

    def test_applicant_count_non_integer_warns_and_is_none(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        row = {**_FULL_ROW, "applicant_count": "many"}
        with caplog.at_level("WARNING", logger="etl.extractors.linkedin"):
            record = _parse_row(row, 2, Path("f.csv"))
        assert record is not None
        assert record["applicant_count"] is None
        assert "non-integer" in caplog.text

    def test_optional_fields_none_when_blank(self) -> None:
        row = {**_FULL_ROW, "company_raw": "", "city_raw": "", "url": ""}
        record = _parse_row(row, 2, Path("f.csv"))
        assert record is not None
        assert record["company_raw"] is None
        assert record["city_raw"] == "Berlin"  # auto-filled when blank
        assert record["url"] is None

    def test_title_raw_preserved(self) -> None:
        record = _parse_row(_FULL_ROW, 2, Path("f.csv"))
        assert record is not None
        assert record["title_raw"] == "Senior Data Analyst (f/m/d)"

    def test_whitespace_stripped_from_job_id(self) -> None:
        row = {**_FULL_ROW, "job_id_raw": "  9999  "}
        record = _parse_row(row, 2, Path("f.csv"))
        assert record is not None
        assert record["job_id_raw"] == "LI_9999"


# ---------------------------------------------------------------------------
# _read_csv
# ---------------------------------------------------------------------------


class TestReadCsv:
    def test_reads_two_rows(self, tmp_path: Path) -> None:
        csv_path = tmp_path / "listings.csv"
        rows = [_FULL_ROW, {**_FULL_ROW, "job_id_raw": "9999", "title_raw": "BI Analyst"}]
        _write_csv(csv_path, rows)
        records = _read_csv(csv_path)
        assert len(records) == 2

    def test_li_prefix_applied_in_file_read(self, tmp_path: Path) -> None:
        csv_path = tmp_path / "listings.csv"
        _write_csv(csv_path, [_FULL_ROW])
        records = _read_csv(csv_path)
        assert records[0]["job_id_raw"] == "LI_3892741056"

    def test_missing_required_column_raises_value_error(self, tmp_path: Path) -> None:
        csv_path = tmp_path / "bad.csv"
        _write_csv(
            csv_path,
            [{"company_raw": "X", "city_raw": "Berlin"}],
            fieldnames=["company_raw", "city_raw"],
        )
        with pytest.raises(ValueError, match="missing required columns"):
            _read_csv(csv_path)

    def test_row_missing_job_id_skipped_and_warns(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        csv_path = tmp_path / "listings.csv"
        rows = [_FULL_ROW, {**_FULL_ROW, "job_id_raw": ""}]
        _write_csv(csv_path, rows)
        with caplog.at_level("WARNING", logger="etl.extractors.linkedin"):
            records = _read_csv(csv_path)
        assert len(records) == 1
        assert "job_id_raw" in caplog.text

    def test_row_missing_title_skipped_and_warns(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        csv_path = tmp_path / "listings.csv"
        rows = [_FULL_ROW, {**_FULL_ROW, "job_id_raw": "8888", "title_raw": ""}]
        _write_csv(csv_path, rows)
        with caplog.at_level("WARNING", logger="etl.extractors.linkedin"):
            records = _read_csv(csv_path)
        assert len(records) == 1
        assert "title_raw" in caplog.text

    def test_all_valid_rows_returned(self, tmp_path: Path) -> None:
        csv_path = tmp_path / "listings.csv"
        rows = [
            _FULL_ROW,
            {**_FULL_ROW, "job_id_raw": "1111", "title_raw": "Data Engineer"},
            {**_FULL_ROW, "job_id_raw": "2222", "title_raw": "ML Engineer"},
        ]
        _write_csv(csv_path, rows)
        records = _read_csv(csv_path)
        assert len(records) == 3


# ---------------------------------------------------------------------------
# read_csvs
# ---------------------------------------------------------------------------


class TestReadCsvs:
    def test_returns_empty_list_when_no_directory(self, tmp_path: Path) -> None:
        result = read_csvs(date_str="2026-05-30", base_dir=tmp_path)
        assert result == []

    def test_returns_empty_list_when_directory_has_no_csvs(self, tmp_path: Path) -> None:
        _make_snap(tmp_path)
        result = read_csvs(date_str="2026-05-30", base_dir=tmp_path)
        assert result == []

    def test_reads_single_csv(self, tmp_path: Path) -> None:
        snap = _make_snap(tmp_path)
        _write_csv(snap / "batch1.csv", [_FULL_ROW])
        records = read_csvs(date_str="2026-05-30", base_dir=tmp_path)
        assert len(records) == 1

    def test_reads_multiple_csv_files(self, tmp_path: Path) -> None:
        snap = _make_snap(tmp_path)
        _write_csv(snap / "batch1.csv", [_FULL_ROW])
        _write_csv(
            snap / "batch2.csv",
            [{**_FULL_ROW, "job_id_raw": "9999", "title_raw": "BI Dev"}],
        )
        records = read_csvs(date_str="2026-05-30", base_dir=tmp_path)
        assert len(records) == 2

    def test_li_prefix_applied_end_to_end(self, tmp_path: Path) -> None:
        snap = _make_snap(tmp_path)
        _write_csv(snap / "listings.csv", [_FULL_ROW])
        records = read_csvs(date_str="2026-05-30", base_dir=tmp_path)
        assert records[0]["job_id_raw"] == "LI_3892741056"

    def test_all_records_have_source_linkedin(self, tmp_path: Path) -> None:
        snap = _make_snap(tmp_path)
        rows = [_FULL_ROW, {**_FULL_ROW, "job_id_raw": "1111", "title_raw": "Data Scientist"}]
        _write_csv(snap / "listings.csv", rows)
        records = read_csvs(date_str="2026-05-30", base_dir=tmp_path)
        assert all(r["source"] == "linkedin" for r in records)

    def test_invalid_csv_raises_value_error(self, tmp_path: Path) -> None:
        snap = _make_snap(tmp_path)
        _write_csv(snap / "bad.csv", [{"company_raw": "X"}], fieldnames=["company_raw"])
        with pytest.raises(ValueError, match="missing required columns"):
            read_csvs(date_str="2026-05-30", base_dir=tmp_path)

    def test_skipped_rows_do_not_abort_file(self, tmp_path: Path) -> None:
        snap = _make_snap(tmp_path)
        rows = [
            _FULL_ROW,
            {**_FULL_ROW, "job_id_raw": "", "title_raw": "No ID row"},
            {**_FULL_ROW, "job_id_raw": "2222", "title_raw": "Good record"},
        ]
        _write_csv(snap / "listings.csv", rows)
        records = read_csvs(date_str="2026-05-30", base_dir=tmp_path)
        assert len(records) == 2

    def test_non_csv_files_ignored(self, tmp_path: Path) -> None:
        snap = _make_snap(tmp_path)
        (snap / "notes.txt").write_text("ignore me", encoding="utf-8")
        _write_csv(snap / "listings.csv", [_FULL_ROW])
        records = read_csvs(date_str="2026-05-30", base_dir=tmp_path)
        assert len(records) == 1

    def test_uses_todays_date_when_date_str_not_given(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import etl.extractors.linkedin as li_mod
        from datetime import date as _date

        class _FakeDate(_date):
            @classmethod
            def today(cls) -> "_FakeDate":  # type: ignore[override]
                return cls(2026, 5, 30)

        monkeypatch.setattr(li_mod, "date", _FakeDate)
        snap = tmp_path / "2026-05-30"
        snap.mkdir()
        _write_csv(snap / "listings.csv", [_FULL_ROW])
        records = read_csvs(base_dir=tmp_path)
        assert len(records) == 1


# ---------------------------------------------------------------------------
# _parse_relative_date
# ---------------------------------------------------------------------------


class TestParseRelativeDate:
    def test_days_ago(self) -> None:
        import etl.extractors.linkedin as li_mod
        from datetime import date as _date

        class _FakeDate(_date):
            @classmethod
            def today(cls) -> "_FakeDate":  # type: ignore[override]
                return cls(2026, 5, 30)

        original = li_mod.date
        li_mod.date = _FakeDate  # type: ignore[assignment]
        try:
            assert _parse_relative_date("3 days ago") == "2026-05-27"
        finally:
            li_mod.date = original

    def test_weeks_ago(self) -> None:
        import etl.extractors.linkedin as li_mod
        from datetime import date as _date

        class _FakeDate(_date):
            @classmethod
            def today(cls) -> "_FakeDate":  # type: ignore[override]
                return cls(2026, 5, 30)

        original = li_mod.date
        li_mod.date = _FakeDate  # type: ignore[assignment]
        try:
            assert _parse_relative_date("2 weeks ago") == "2026-05-16"
        finally:
            li_mod.date = original

    def test_months_ago(self) -> None:
        import etl.extractors.linkedin as li_mod
        from datetime import date as _date

        class _FakeDate(_date):
            @classmethod
            def today(cls) -> "_FakeDate":  # type: ignore[override]
                return cls(2026, 5, 30)

        original = li_mod.date
        li_mod.date = _FakeDate  # type: ignore[assignment]
        try:
            assert _parse_relative_date("1 month ago") == "2026-04-30"
        finally:
            li_mod.date = original

    def test_singular_forms_accepted(self) -> None:
        import etl.extractors.linkedin as li_mod
        from datetime import date as _date

        class _FakeDate(_date):
            @classmethod
            def today(cls) -> "_FakeDate":  # type: ignore[override]
                return cls(2026, 5, 30)

        original = li_mod.date
        li_mod.date = _FakeDate  # type: ignore[assignment]
        try:
            assert _parse_relative_date("1 day ago") == "2026-05-29"
            assert _parse_relative_date("1 week ago") == "2026-05-23"
        finally:
            li_mod.date = original

    def test_iso_date_returned_unchanged(self) -> None:
        assert _parse_relative_date("2026-05-28") == "2026-05-28"

    def test_unrecognised_string_returned_unchanged(self) -> None:
        assert _parse_relative_date("last quarter") == "last quarter"

    def test_case_insensitive(self) -> None:
        import etl.extractors.linkedin as li_mod
        from datetime import date as _date

        class _FakeDate(_date):
            @classmethod
            def today(cls) -> "_FakeDate":  # type: ignore[override]
                return cls(2026, 5, 30)

        original = li_mod.date
        li_mod.date = _FakeDate  # type: ignore[assignment]
        try:
            assert _parse_relative_date("3 Days Ago") == "2026-05-27"
        finally:
            li_mod.date = original


# ---------------------------------------------------------------------------
# city_raw auto-fill (via _parse_row)
# ---------------------------------------------------------------------------


class TestCityAutoFill:
    def test_blank_city_defaults_to_berlin(self) -> None:
        row = {**_FULL_ROW, "city_raw": ""}
        record = _parse_row(row, 2, Path("f.csv"))
        assert record is not None
        assert record["city_raw"] == "Berlin"

    def test_missing_city_key_defaults_to_berlin(self) -> None:
        row = {k: v for k, v in _FULL_ROW.items() if k != "city_raw"}
        record = _parse_row(row, 2, Path("f.csv"))
        assert record is not None
        assert record["city_raw"] == "Berlin"

    def test_explicit_city_preserved(self) -> None:
        row = {**_FULL_ROW, "city_raw": "Munich"}
        record = _parse_row(row, 2, Path("f.csv"))
        assert record is not None
        assert record["city_raw"] == "Munich"

    def test_whitespace_only_city_defaults_to_berlin(self) -> None:
        row = {**_FULL_ROW, "city_raw": "   "}
        record = _parse_row(row, 2, Path("f.csv"))
        assert record is not None
        assert record["city_raw"] == "Berlin"


# ---------------------------------------------------------------------------
# posted_at_raw relative-date conversion (via _parse_row)
# ---------------------------------------------------------------------------


class TestPostedAtRawConversion:
    def _patched_parse_row(
        self, row: dict[str, str], fake_today: str
    ) -> dict | None:
        import etl.extractors.linkedin as li_mod
        from datetime import date as _date

        y, m, d = (int(x) for x in fake_today.split("-"))

        class _FakeDate(_date):
            @classmethod
            def today(cls) -> "_FakeDate":  # type: ignore[override]
                return cls(y, m, d)

        original = li_mod.date
        li_mod.date = _FakeDate  # type: ignore[assignment]
        try:
            return _parse_row(row, 2, Path("f.csv"))
        finally:
            li_mod.date = original

    def test_relative_date_converted(self) -> None:
        row = {**_FULL_ROW, "posted_at_raw": "2 weeks ago"}
        record = self._patched_parse_row(row, "2026-05-30")
        assert record is not None
        assert record["posted_at_raw"] == "2026-05-16"

    def test_iso_date_preserved(self) -> None:
        row = {**_FULL_ROW, "posted_at_raw": "2026-05-28"}
        record = _parse_row(row, 2, Path("f.csv"))
        assert record is not None
        assert record["posted_at_raw"] == "2026-05-28"

    def test_empty_posted_at_is_none(self) -> None:
        row = {**_FULL_ROW, "posted_at_raw": ""}
        record = _parse_row(row, 2, Path("f.csv"))
        assert record is not None
        assert record["posted_at_raw"] is None
