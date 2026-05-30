"""Extractor for Indeed job postings via RSS feeds (IN_)."""
from __future__ import annotations

import csv
import logging
import time
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import feedparser

logger = logging.getLogger(__name__)

FEEDS: list[str] = [
    "https://de.indeed.com/rss?q=Data+Analyst&l=Berlin&sort=date",
    "https://de.indeed.com/rss?q=Business+Intelligence&l=Deutschland&sort=date",
    "https://de.indeed.com/rss?q=Analytics+Engineer&l=Berlin&sort=date",
    "https://de.indeed.com/rss?q=Data+Engineer&l=Berlin&sort=date",
    "https://de.indeed.com/rss?q=Data+Scientist&l=Berlin&sort=date",
]

SLEEP_SECONDS = 3.0
SNAPSHOT_DIR = Path("data/raw/indeed")

_RAW_FIELDS = [
    "source",
    "job_id_raw",
    "title_raw",
    "company_raw",
    "url",
    "posted_at_raw",
    "description_raw",
    "city_raw",
]


def _city_from_url(feed_url: str) -> str | None:
    """Extract the l= location parameter from an Indeed feed URL."""
    params = parse_qs(urlparse(feed_url).query)
    values = params.get("l")
    return values[0] if values else None


def _jk_from_url(url: str) -> str | None:
    """Extract the jk= job-key parameter from an Indeed job URL."""
    params = parse_qs(urlparse(url).query)
    values = params.get("jk")
    return values[0] if values else None


def _parse_entry(entry: Any, city_raw: str | None) -> dict[str, Any]:
    """Map one feedparser entry to the 8-field raw dict."""
    entry_id: str = getattr(entry, "id", "") or ""
    jk = _jk_from_url(entry_id)
    job_id_raw = f"IN_{jk}" if jk else f"IN_{entry_id}"

    return {
        "source": "indeed",
        "job_id_raw": job_id_raw,
        "title_raw": getattr(entry, "title", "") or "",
        "company_raw": getattr(entry, "author", None) or None,
        "url": getattr(entry, "link", "") or "",
        "posted_at_raw": getattr(entry, "published", None) or None,
        "description_raw": getattr(entry, "summary", None) or None,
        "city_raw": city_raw,
    }


def _fetch_feed(feed_url: str) -> list[dict[str, Any]]:
    """Fetch and parse one Indeed RSS feed; returns [] and logs on failure."""
    try:
        parsed = feedparser.parse(feed_url)
    except Exception as exc:
        logger.error("feedparser raised fetching %r: %s", feed_url, exc)
        return []

    status = parsed.get("status", 200)
    if status not in {200, 301, 302}:
        logger.error("Indeed RSS returned HTTP %d for %r", status, feed_url)
        return []

    entries = parsed.get("entries") or []
    if not entries and parsed.get("bozo"):
        logger.error(
            "Indeed RSS parse error for %r: %s",
            feed_url,
            parsed.get("bozo_exception"),
        )
        return []

    city_raw = _city_from_url(feed_url)
    return [_parse_entry(entry, city_raw) for entry in entries]


def _save_snapshot(
    records: list[dict[str, Any]],
    date_str: str,
    base_dir: Path = SNAPSHOT_DIR,
) -> Path:
    """Write records to a dated CSV snapshot and return the path."""
    out_dir = base_dir / date_str
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "indeed_rss.csv"
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=_RAW_FIELDS)
        writer.writeheader()
        writer.writerows(records)
    return out_path


def fetch_jobs(feeds: list[str] | None = None) -> list[dict[str, Any]]:
    """Fetch all feeds, deduplicate by job_id_raw, and return a flat list.

    Sleeps SLEEP_SECONDS between feeds (not before the first).
    Returns [] when no feeds are provided or all feeds fail.
    """
    if feeds is None:
        feeds = FEEDS

    all_records: list[dict[str, Any]] = []
    seen: set[str] = set()

    for i, feed_url in enumerate(feeds):
        if i > 0:
            time.sleep(SLEEP_SECONDS)

        for record in _fetch_feed(feed_url):
            jid = record["job_id_raw"]
            if jid not in seen:
                seen.add(jid)
                all_records.append(record)

    return all_records


def extract() -> list[dict[str, Any]]:
    """Public entry point: fetch all feeds, save a dated snapshot, return records."""
    records = fetch_jobs()
    date_str = date.today().isoformat()
    path = _save_snapshot(records, date_str)
    logger.info("Saved %d Indeed records to %s", len(records), path)
    return records
