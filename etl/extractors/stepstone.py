"""Extractor for Stepstone job listings via HTML scraping (SS_)."""
from __future__ import annotations

from typing import Any


def fetch_jobs(query: str, location: str) -> list[dict[str, Any]]:
    """Scrape job postings from Stepstone.

    Uses random sleep of 10–18 s between requests.
    Returns an empty list on failure; never raises.
    """
    raise NotImplementedError
