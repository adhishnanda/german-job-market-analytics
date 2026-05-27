"""Extractor for Indeed Germany RSS feeds (IN_)."""
from __future__ import annotations

from typing import Any


def fetch_jobs(query: str, location: str) -> list[dict[str, Any]]:
    """Fetch job postings from Indeed RSS.

    Returns an empty list on failure; never raises.
    """
    raise NotImplementedError
