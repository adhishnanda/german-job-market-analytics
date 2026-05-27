"""Identify and drop duplicate job postings across sources."""
from __future__ import annotations

from typing import Any


def deduplicate(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return *jobs* with cross-source duplicates removed."""
    raise NotImplementedError
