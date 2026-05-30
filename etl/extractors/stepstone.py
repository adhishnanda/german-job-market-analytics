"""Extractor for Stepstone job postings via HTML scraping (SS_)."""
from __future__ import annotations

import json
import logging
import random
import re
import time
from datetime import date
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "https://www.stepstone.de/jobs/{keyword}/in-{location}"
SLEEP_MIN = 10.0
SLEEP_MAX = 18.0
MAX_PAGES = 2

KEYWORDS: list[str] = [
    "data-analyst",
    "business-intelligence",
    "analytics-engineer",
    "data-engineer",
    "data-scientist",
]

LOCATIONS: list[str] = ["berlin"]

SNAPSHOT_DIR = Path("data/raw/stepstone")

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7",
}

_UMLAUT_MAP = str.maketrans(
    {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss", "Ä": "ae", "Ö": "oe", "Ü": "ue"}
)


def _to_slug(text: str) -> str:
    """Convert a keyword or location to a Stepstone URL slug (lowercase, hyphens)."""
    text = text.lower().translate(_UMLAUT_MAP)
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def _build_url(keyword_slug: str, location_slug: str, page: int) -> str:
    """Return the Stepstone search URL for a given keyword, location, and page."""
    base = BASE_URL.format(keyword=keyword_slug, location=location_slug)
    if page > 1:
        return f"{base}?page={page}"
    return base


def _parse_cards(html: str, keyword: str, location: str) -> list[dict[str, Any]]:
    """Parse job cards from a Stepstone search results HTML page."""
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.find_all("article", attrs={"data-at": "job-item"})
    records: list[dict[str, Any]] = []
    for card in cards:
        job_id_raw = card.get("data-job-id", "")
        if not job_id_raw:
            continue

        title_tag = card.find("a", attrs={"data-at": "job-item-title"})
        title_raw = title_tag.get_text(strip=True) if title_tag else None
        href = title_tag.get("href", "") if title_tag else ""
        url = (
            f"https://www.stepstone.de{href}"
            if href and not href.startswith("http")
            else href
        )

        company_tag = card.find("span", attrs={"data-at": "job-item-company-name"})
        company = company_tag.get_text(strip=True) if company_tag else None

        location_tag = card.find("span", attrs={"data-at": "job-item-location"})
        location_raw = location_tag.get_text(strip=True) if location_tag else None

        time_tag = card.find("time", attrs={"datetime": True})
        posted_date_raw = time_tag.get("datetime") if time_tag else None

        records.append(
            {
                "source": "stepstone",
                "job_id": f"SS_{job_id_raw}",
                "title_raw": title_raw,
                "company": company,
                "location_raw": location_raw,
                "posted_date_raw": posted_date_raw,
                "url": url,
                "source_keyword": keyword,
                "source_city": location,
            }
        )
    return records


def _fetch_page(session: requests.Session, url: str) -> requests.Response | None:
    """Fetch one Stepstone page; returns the Response or None on connection error."""
    try:
        return session.get(url, headers=_HEADERS, timeout=30)
    except requests.RequestException as exc:
        logger.error("Stepstone request failed (url=%r): %s", url, exc)
        return None


def _save_snapshot(
    records: list[dict[str, Any]],
    date_str: str,
    base_dir: Path = SNAPSHOT_DIR,
) -> Path:
    """Write records to a dated JSON snapshot file and return the path."""
    out_dir = base_dir / date_str
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "stepstone.json"
    out_path.write_text(
        json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return out_path


def fetch_jobs(
    keywords: list[str] | None = None,
    locations: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Fetch up to MAX_PAGES per keyword × location pair.

    Sleeps random.uniform(SLEEP_MIN, SLEEP_MAX) between every page request.
    On 403/429: logs warning and stops all remaining locations for that keyword.
    Returns a flat list of raw dicts; returns [] on complete failure.
    """
    if keywords is None:
        keywords = KEYWORDS
    if locations is None:
        locations = LOCATIONS

    all_records: list[dict[str, Any]] = []
    session = requests.Session()
    request_count = 0

    for keyword in keywords:
        keyword_slug = _to_slug(keyword)
        blocked = False

        for location in locations:
            if blocked:
                break
            location_slug = _to_slug(location)

            for page in range(1, MAX_PAGES + 1):
                if request_count > 0:
                    time.sleep(random.uniform(SLEEP_MIN, SLEEP_MAX))
                request_count += 1

                url = _build_url(keyword_slug, location_slug, page)
                response = _fetch_page(session, url)

                if response is None:
                    break

                if response.status_code in {403, 429}:
                    logger.warning(
                        "Stepstone returned %d for %r — stopping keyword %r",
                        response.status_code,
                        url,
                        keyword,
                    )
                    blocked = True
                    break

                if not response.ok:
                    logger.error(
                        "Stepstone HTTP %d for %r",
                        response.status_code,
                        url,
                    )
                    break

                cards = _parse_cards(response.text, keyword, location)
                all_records.extend(cards)

                if not cards:
                    break

    return all_records


def extract() -> list[dict[str, Any]]:
    """Public entry point: fetch all jobs, save a dated snapshot, and return records."""
    records = fetch_jobs()
    date_str = date.today().isoformat()
    path = _save_snapshot(records, date_str)
    logger.info("Saved %d Stepstone records to %s", len(records), path)
    return records
