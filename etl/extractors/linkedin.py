"""Extractor for LinkedIn job postings from manually collected CSV files (LI_)."""
from __future__ import annotations

import csv
import logging
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SNAPSHOT_DIR = Path("data/raw/linkedin")

REQUIRED_COLUMNS: frozenset[str] = frozenset({"job_id_raw", "title_raw"})

_RELATIVE_DATE_RE = re.compile(
    r"^(\d+)\s+(day|week|month|year)s?\s+ago$",
    re.IGNORECASE,
)
_RELATIVE_DAYS = {"day": 1, "week": 7, "month": 30, "year": 365}


def _parse_relative_date(value: str) -> str:
    """Convert a LinkedIn relative date string to an approximate ISO date.

    Returns the original string unchanged when it does not match the pattern.
    Approximation: 1 month = 30 days, 1 year = 365 days (±2 days expected).
    """
    m = _RELATIVE_DATE_RE.match(value.strip())
    if not m:
        return value
    n = int(m.group(1))
    unit = m.group(2).lower()
    return (date.today() - timedelta(days=n * _RELATIVE_DAYS[unit])).isoformat()


_RAW_FIELDS = [
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
]


def _validate_columns(fieldnames: list[str], csv_path: Path) -> None:
    """Raise ValueError listing missing required columns for the given file."""
    missing = REQUIRED_COLUMNS - frozenset(fieldnames)
    if missing:
        raise ValueError(
            f"{csv_path}: missing required columns: {sorted(missing)}"
        )


def _parse_row(
    row: dict[str, str], row_index: int, csv_path: Path
) -> dict[str, Any] | None:
    """Map one CSV row to a raw dict; return None and log a warning for invalid rows."""
    job_id_raw = (row.get("job_id_raw") or "").strip()
    title_raw = (row.get("title_raw") or "").strip()

    if not job_id_raw:
        logger.warning("Skipping row %d in %s: missing job_id_raw", row_index, csv_path)
        return None
    if not title_raw:
        logger.warning("Skipping row %d in %s: missing title_raw", row_index, csv_path)
        return None

    applicant_count: int | None = None
    applicant_count_raw = (row.get("applicant_count") or "").strip()
    if applicant_count_raw:
        try:
            applicant_count = int(applicant_count_raw)
        except ValueError:
            logger.warning(
                "Row %d in %s: non-integer applicant_count %r — setting to None",
                row_index,
                csv_path,
                applicant_count_raw,
            )

    is_remote: bool | None = None
    is_remote_raw = (row.get("is_remote") or "").strip().lower()
    if is_remote_raw in {"true", "yes", "1"}:
        is_remote = True
    elif is_remote_raw in {"false", "no", "0"}:
        is_remote = False

    city_raw = (row.get("city_raw") or "").strip() or "Berlin"

    posted_at_str = (row.get("posted_at_raw") or "").strip()
    posted_at_raw = _parse_relative_date(posted_at_str) if posted_at_str else None

    return {
        "source": "linkedin",
        "job_id_raw": f"LI_{job_id_raw}",
        "title_raw": title_raw,
        "company_raw": (row.get("company_raw") or "").strip() or None,
        "city_raw": city_raw,
        "posted_at_raw": posted_at_raw,
        "description_raw": (row.get("description_raw") or "").strip() or None,
        "url": (row.get("url") or "").strip() or None,
        "employment_type": (row.get("employment_type") or "").strip() or None,
        "applicant_count": applicant_count,
        "is_remote": is_remote,
    }


def _read_csv(csv_path: Path) -> list[dict[str, Any]]:
    """Read one LinkedIn CSV; validate columns, skip invalid rows, return parsed records."""
    records: list[dict[str, Any]] = []
    with csv_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        _validate_columns(list(reader.fieldnames or []), csv_path)
        for row_index, row in enumerate(reader, start=2):  # row 1 is the header
            record = _parse_row(row, row_index, csv_path)
            if record is not None:
                records.append(record)
    return records


def read_csvs(
    date_str: str | None = None,
    base_dir: Path = SNAPSHOT_DIR,
) -> list[dict[str, Any]]:
    """Read all CSV files from the dated LinkedIn snapshot directory.

    Returns [] when no snapshot directory or no CSV files exist for the date.
    Raises ValueError when a CSV is missing required columns.
    """
    if date_str is None:
        date_str = date.today().isoformat()

    snapshot_dir = base_dir / date_str
    if not snapshot_dir.exists():
        logger.info("No LinkedIn snapshot directory for %s — returning []", date_str)
        return []

    csv_files = sorted(snapshot_dir.glob("*.csv"))
    if not csv_files:
        logger.info("No CSV files in %s — returning []", snapshot_dir)
        return []

    all_records: list[dict[str, Any]] = []
    for csv_path in csv_files:
        records = _read_csv(csv_path)
        logger.info("Read %d records from %s", len(records), csv_path)
        all_records.extend(records)

    return all_records


def extract() -> list[dict[str, Any]]:
    """Public entry point: read today's LinkedIn CSVs and return records."""
    records = read_csvs()
    logger.info(
        "Loaded %d LinkedIn records for %s", len(records), date.today().isoformat()
    )
    return records
