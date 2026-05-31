"""Identify and drop duplicate job postings across sources."""

from __future__ import annotations

from datetime import date
from typing import Any

from thefuzz import fuzz

_SOURCE_PRIORITY: dict[str, int] = {
    "bundesagentur": 0,
    "indeed": 1,
    "stepstone": 2,
    "linkedin": 3,
}

_DATE_WINDOW_DAYS = 7
_TITLE_THRESHOLD = 85
_COMPANY_THRESHOLD = 85


def _same_city(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """Return True if both records share the same city (case-insensitive)."""
    city_a = a.get("city")
    city_b = b.get("city")
    if not city_a or not city_b:
        return False
    return city_a.strip().lower() == city_b.strip().lower()


def _similar_company(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """Return True if company names are similar enough to be the same employer."""
    co_a = (a.get("company") or "").strip()
    co_b = (b.get("company") or "").strip()
    if not co_a or not co_b:
        return False
    return fuzz.ratio(co_a.lower(), co_b.lower()) >= _COMPANY_THRESHOLD


def _similar_title(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """Return True if normalized titles are similar enough to be the same role."""
    t_a = (a.get("title_normalized") or "").strip()
    t_b = (b.get("title_normalized") or "").strip()
    return fuzz.ratio(t_a, t_b) >= _TITLE_THRESHOLD


def _within_date_window(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """Return True if posted_dates are within the dedup window."""
    d_a: date | None = a.get("posted_date")
    d_b: date | None = b.get("posted_date")
    if d_a is None or d_b is None:
        return False
    return abs((d_a - d_b).days) <= _DATE_WINDOW_DAYS


def _is_cross_source_match(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """Return True if two records from different sources represent the same job."""
    return (
        _same_city(a, b)
        and _similar_company(a, b)
        and _similar_title(a, b)
        and _within_date_window(a, b)
    )


def deduplicate(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Apply two-pass deduplication; mutates is_duplicate and canonical_id in-place.

    Pass 1: within each source, any repeated job_id is marked as a duplicate of
            the first occurrence.
    Pass 2: across sources, records that share city, company (fuzzy ≥ 85),
            title (fuzzy ≥ 85), and posted_date (within 7 days) are collapsed.
            The higher-priority source record becomes canonical; lower-priority
            records are marked is_duplicate=True with canonical_id set accordingly.
            Priority: bundesagentur > indeed > stepstone > linkedin.
    """
    # Pass 1 — within-source job_id dedup
    seen: dict[tuple[str, str], str] = {}  # (source, job_id) → canonical job_id
    for record in records:
        source: str = record.get("source", "")
        job_id: str = record.get("job_id", "")
        key = (source, job_id)
        if key in seen:
            record["is_duplicate"] = True
            record["canonical_id"] = seen[key]
        else:
            seen[key] = job_id

    # Pass 2 — cross-source fuzzy dedup
    # Sort surviving canonicals by source priority so higher-priority sources
    # are locked in first and become the canonical record when a match is found.
    canonicals = [r for r in records if not r.get("is_duplicate", False)]
    canonicals.sort(key=lambda r: _SOURCE_PRIORITY.get(r.get("source", ""), 99))

    locked: list[dict[str, Any]] = []
    for record in canonicals:
        matched = False
        for candidate in locked:
            if candidate.get("source") != record.get(
                "source"
            ) and _is_cross_source_match(record, candidate):
                record["is_duplicate"] = True
                record["canonical_id"] = candidate["job_id"]
                matched = True
                break
        if not matched:
            locked.append(record)

    return records
