"""Extractor for the Bundesagentur für Arbeit jobs API (BA_)."""
from __future__ import annotations

from typing import Any


def fetch_jobs(query: str, location: str, pages: int = 1) -> list[dict[str, Any]]:
    """Fetch job postings from the Bundesagentur API.

    Returns an empty list on failure; never raises.
    """
    raise NotImplementedError
