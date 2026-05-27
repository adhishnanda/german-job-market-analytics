"""Extractor for the Bundesagentur für Arbeit jobs API (BA_)."""
from __future__ import annotations

import json
import logging
import time
from datetime import date
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v6/jobs"
PAGE_SIZE = 25
SLEEP_SECONDS = 2.0

KEYWORDS: list[str] = [
    "Data Engineer",
    "Data Analyst",
    "Data Scientist",
    "Analytics Engineer",
    "BI Engineer",
    "Machine Learning Engineer",
]

CITIES: list[str] = [
    "Berlin",
    "Munich",
    "Hamburg",
    "Frankfurt",
    "Cologne",
    "Stuttgart",
    "Düsseldorf",
    "Leipzig",
]

SNAPSHOT_DIR = Path("data/raw/bundesagentur")

_HEADERS = {
    "X-API-Key": "jobboerse-jobsuche",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}


def _build_params(keyword: str, city: str, page: int) -> dict[str, Any]:
    """Build query parameters for a single BA API request (page is 1-indexed)."""
    return {
        "was": keyword,
        "wo": city,
        "page": page,
        "size": PAGE_SIZE,
    }


def _fetch_page(
    session: requests.Session,
    keyword: str,
    city: str,
    page: int,
) -> dict[str, Any] | None:
    """Fetch one page of results; returns None and logs on any error."""
    params = _build_params(keyword, city, page)
    try:
        response = session.get(BASE_URL, params=params, headers=_HEADERS, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        logger.error(
            "BA fetch failed (keyword=%r, city=%r, page=%d): %s",
            keyword,
            city,
            page,
            exc,
        )
        return None


def _save_snapshot(
    records: list[dict[str, Any]],
    date_str: str,
    base_dir: Path = SNAPSHOT_DIR,
) -> Path:
    """Write records to a dated JSON snapshot file and return the path."""
    out_dir = base_dir / date_str
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "jobs.json"
    out_path.write_text(
        json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return out_path


def fetch_jobs(
    keywords: list[str] | None = None,
    cities: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Fetch all jobs for every keyword × city pair with pagination.

    Sleeps SLEEP_SECONDS between every request (skips sleep before the first).
    Returns a flat list of raw dicts with job_id prefixed BA_; returns [] on failure.
    """
    if keywords is None:
        keywords = KEYWORDS
    if cities is None:
        cities = CITIES

    all_records: list[dict[str, Any]] = []
    session = requests.Session()
    request_count = 0

    for keyword in keywords:
        for city in cities:
            page = 1  # v6 API is 1-indexed
            fetched = 0
            total: int | None = None

            while True:
                if request_count > 0:
                    time.sleep(SLEEP_SECONDS)
                request_count += 1

                data = _fetch_page(session, keyword, city, page)
                if data is None:
                    break

                if total is None:
                    total = data.get("maxErgebnisse", 0)

                postings: list[dict[str, Any]] = data.get("ergebnisliste") or []
                for posting in postings:
                    raw_id = posting.get(
                        "referenznummer", f"{keyword}_{city}_{page}_{len(all_records)}"
                    )
                    posting["job_id"] = f"BA_{raw_id}"
                    posting["source_keyword"] = keyword
                    posting["source_city"] = city
                    all_records.append(posting)

                fetched += len(postings)
                if total is not None and fetched >= total:
                    break
                if not postings:
                    break

                page += 1

    return all_records


def extract() -> list[dict[str, Any]]:
    """Public entry point: fetch all jobs, save a dated snapshot, and return records."""
    records = fetch_jobs()
    date_str = date.today().isoformat()
    path = _save_snapshot(records, date_str)
    logger.info("Saved %d records to %s", len(records), path)
    return records
