"""Extractor for Stepstone job postings via HTML scraping (SS_)."""

from __future__ import annotations

import json
import logging
import random
import re
import time
from datetime import date, timedelta
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

# German relative-date parsing: "vor X Tagen/Wochen/Monaten/Jahren", "Heute", "Gestern"
_DE_TIMEAGO_RE = re.compile(
    r"vor\s+(\d+)\s+(tage?n?|woche?n?|monat(?:en?)?|jahre?n?)",
    re.IGNORECASE,
)
_DE_TIMEAGO_DAYS: dict[str, int] = {"tag": 1, "woc": 7, "mon": 30, "jah": 365}


def _parse_german_timeago(text: str) -> str | None:
    """Parse a German relative-time string to an approximate ISO date.

    Handles "vor N Tagen/Wochen/Monaten/Jahren", "Heute", "Gestern".
    Returns None for unrecognised patterns.
    Approximation: 1 Monat = 30 days, 1 Jahr = 365 days (±2 days expected).
    """
    if not text:
        return None
    clean = text.strip().lower()
    if clean == "heute":
        return date.today().isoformat()
    if clean == "gestern":
        return (date.today() - timedelta(days=1)).isoformat()
    m = _DE_TIMEAGO_RE.search(clean)
    if m:
        n = int(m.group(1))
        unit_prefix = m.group(2)[:3].lower()
        multiplier = _DE_TIMEAGO_DAYS.get(unit_prefix, 1)
        return (date.today() - timedelta(days=n * multiplier)).isoformat()
    logger.debug("Unrecognised German timeago: %r", text)
    return None


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
    """Parse job cards from a Stepstone search results HTML page.

    Job ID is now in id="job-item-{numeric_id}" (previously data-job-id).
    Posted date comes from the <time> tag's text as a German relative string
    ("vor X Tagen") parsed via _parse_german_timeago.
    """
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.find_all("article", attrs={"data-at": "job-item"})
    records: list[dict[str, Any]] = []
    for card in cards:
        # Job ID is in id="job-item-{numeric_id}"
        card_id: str = card.get("id") or ""
        if card_id.startswith("job-item-"):
            job_id_raw = card_id[len("job-item-") :]
        else:
            job_id_raw = card_id
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

        # Date is a relative German string in <time> tag text; parse to ISO date.
        time_tag = card.find("time")
        timeago_text = time_tag.get_text(strip=True) if time_tag else None
        posted_date_raw = _parse_german_timeago(timeago_text) if timeago_text else None

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
    max_pages: int = MAX_PAGES,
) -> list[dict[str, Any]]:
    """Fetch up to max_pages per keyword × location pair.

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

            for page in range(1, max_pages + 1):
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
