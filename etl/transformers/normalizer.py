"""Normalise raw job dicts from all sources into a common schema."""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

from langdetect import LangDetectException, detect

logger = logging.getLogger(__name__)


def _parse_posted_date(raw: str | None) -> date | None:
    """Parse a posted-date string in any supported format; None on failure.

    Formats tried in order:
    - YYYY-MM-DD or ISO 8601 with time (BA and Stepstone)
    - DD-MM-YYYY (LinkedIn manual CSV)
    - RFC 2822 (Indeed RSS, e.g. "Mon, 27 May 2026 10:00:00 GMT")

    Logs a warning and returns None when none of the formats match.
    """
    if not raw:
        return None
    # ISO date or ISO 8601 with time: slice first 10 chars gives YYYY-MM-DD
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        pass
    # DD-MM-YYYY (LinkedIn manual)
    try:
        return datetime.strptime(raw[:10], "%d-%m-%Y").date()
    except ValueError:
        pass
    # RFC 2822 (Indeed RSS)
    try:
        return parsedate_to_datetime(raw).date()
    except (TypeError, ValueError):
        pass
    logger.warning("Unrecognised posted_date format: %r", raw)
    return None

_WORK_MODEL_MAP: dict[str, str] = {
    "VOLLSTAENDIG_IM_HOMEOFFICE": "REMOTE",
    "NACH_VEREINBARUNG": "HYBRID",
    "KEIN_HOMEOFFICE": "ONSITE",
}

# Role category taxonomy — ordered, first match wins
_ROLE_TAXONOMY: list[tuple[str, list[str]]] = [
    ("Data Engineering", ["data engineer", "etl", "pipeline", "data platform", "data infrastructure"]),
    ("Analytics Engineering", ["analytics engineer", "dbt", "data modelling", "data modeling"]),
    ("Data Science / ML", ["data scientist", "machine learning", "ml engineer", "deep learning", "nlp", "computer vision"]),
    ("Data Analysis / BI", ["data analyst", "business intelligence", "bi developer", "reporting", "power bi", "tableau"]),
    ("ML Engineering", ["ml engineer", "mlops", "model deployment", "feature engineering"]),
    ("Data Architect", ["data architect", "data mesh", "lakehouse"]),
]

_BA_DETAIL_URL = "https://www.arbeitsagentur.de/jobsuche/jobdetail/{}"


def _map_work_model(homeofficetyp: str | None) -> str:
    """Map BA homeofficetyp value to canonical work_model."""
    if homeofficetyp is None:
        return "UNKNOWN"
    return _WORK_MODEL_MAP.get(homeofficetyp, "UNKNOWN")


def _map_employment_type(vollzeit: bool | None) -> str:
    """Map BA arbeitszeitVollzeit flag to canonical employment_type."""
    if vollzeit is True:
        return "FULL_TIME"
    if vollzeit is False:
        return "PART_TIME"
    return "UNKNOWN"


def _assign_role_category(title_normalized: str) -> str:
    """Return the first matching role category for the normalized title, else 'Other'."""
    for category, keywords in _ROLE_TAXONOMY:
        if any(kw in title_normalized for kw in keywords):
            return category
    return "Other"


def _detect_language(text: str) -> str:
    """Detect language of text; returns 'unknown' when detection fails or text is empty."""
    if not text or not text.strip():
        return "unknown"
    try:
        return detect(text)
    except LangDetectException:
        return "unknown"


def _normalize_ba(raw: dict[str, Any]) -> dict[str, Any]:
    """Map a raw BA search-list record to the canonical jobs_raw schema."""
    lokationen = raw.get("stellenlokationen") or []
    loc = lokationen[0] if lokationen else {}
    adresse = loc.get("adresse") or {}

    title_raw: str = raw.get("stellenangebotsTitel") or ""
    title_normalized = title_raw.lower().strip()
    description_raw: str = raw.get("description_raw") or ""
    referenznummer: str = raw.get("referenznummer") or ""

    posted_date_str = (raw.get("veroeffentlichungszeitraum") or {}).get("von")
    posted_date: date | None = _parse_posted_date(posted_date_str)

    return {
        # Identity and provenance
        "job_id": raw["job_id"],
        "source": "bundesagentur",
        "source_keyword": raw.get("source_keyword"),
        "source_city": raw.get("source_city"),
        "snapshot_date": date.today(),
        "fetched_at": datetime.now(tz=timezone.utc),
        "url": _BA_DETAIL_URL.format(referenznummer) if referenznummer else None,
        # Raw text fields (immutable after extraction)
        "title_raw": title_raw,
        "description_raw": description_raw,
        "salary_raw": raw.get("salary_raw"),
        # Normalised attributes
        "title_normalized": title_normalized,
        "company": raw.get("firma"),
        "city": adresse.get("ort"),
        "region": adresse.get("bundesland"),
        "country": "DE",
        "postal_code": adresse.get("plz"),
        "lat": loc.get("breite"),
        "lon": loc.get("laenge"),
        "posted_date": posted_date,
        "employment_type": _map_employment_type(raw.get("arbeitszeitVollzeit")),
        "work_model": _map_work_model(raw.get("homeofficetyp")),
        "language": _detect_language(description_raw),
        "role_category": _assign_role_category(title_normalized),
        # Downstream fields — populated by later transformers
        "skills": [],
        "salary_min": None,
        "salary_max": None,
        "salary_currency": None,
        "is_duplicate": False,
        "canonical_id": None,
    }


_WORK_MODEL_KEYWORDS: list[tuple[str, str]] = [
    ("REMOTE", [r"\bfully remote\b", r"\b100%\s*remote\b", r"\bremote\b"]),
    ("HYBRID", [r"\bhybrid\b", r"\bteilweise remote\b", r"\bflex(ible)?\s*work\b"]),
    ("ONSITE", [r"\bvor ort\b", r"\bon[\-\s]?site\b", r"\bin[\-\s]?office\b"]),
]

_EMPLOYMENT_KEYWORDS: list[tuple[str, str]] = [
    ("FULL_TIME", [r"\bfull[\-\s]?time\b", r"\bvollzeit\b"]),
    ("PART_TIME", [r"\bpart[\-\s]?time\b", r"\bteilzeit\b"]),
    ("CONTRACT", [r"\bfreelance\b", r"\bcontract\b", r"\bbefristet\b"]),
    ("INTERNSHIP", [r"\bintern\b", r"\bpraktikum\b", r"\bwerkstudent\b"]),
]


def _scan_keywords(text: str, patterns: list[tuple[str, list[str]]]) -> str:
    """Return the first canonical value whose patterns match text, else 'UNKNOWN'."""
    lower = text.lower()
    for canonical, regexes in patterns:
        if any(re.search(rx, lower) for rx in regexes):
            return canonical
    return "UNKNOWN"


def _normalize_indeed(raw: dict[str, Any]) -> dict[str, Any]:
    """Map a raw Indeed RSS dict to the canonical jobs_raw schema."""
    title_raw: str = raw.get("title_raw") or ""
    title_normalized = title_raw.lower().strip()
    description_raw: str = raw.get("description_raw") or ""

    return {
        # Identity and provenance
        "job_id": raw["job_id_raw"],
        "source": "indeed",
        "source_keyword": None,
        "source_city": raw.get("city_raw"),
        "snapshot_date": date.today(),
        "fetched_at": datetime.now(tz=timezone.utc),
        "url": raw.get("url"),
        # Raw text fields (immutable after extraction)
        "title_raw": title_raw,
        "description_raw": description_raw,
        "salary_raw": None,
        # Normalised attributes
        "title_normalized": title_normalized,
        "company": raw.get("company_raw"),
        "city": raw.get("city_raw"),
        "region": None,
        "country": "DE",
        "postal_code": None,
        "lat": None,
        "lon": None,
        "posted_date": _parse_posted_date(raw.get("posted_at_raw")),
        "employment_type": _scan_keywords(description_raw, _EMPLOYMENT_KEYWORDS),
        "work_model": _scan_keywords(description_raw, _WORK_MODEL_KEYWORDS),
        "language": _detect_language(description_raw),
        "role_category": _assign_role_category(title_normalized),
        # Downstream fields — populated by later transformers
        "skills": [],
        "salary_min": None,
        "salary_max": None,
        "salary_currency": None,
        "is_duplicate": False,
        "canonical_id": None,
    }


def _normalize_stepstone(raw: dict[str, Any]) -> dict[str, Any]:
    """Map a raw Stepstone search-list record to the canonical jobs_raw schema."""
    title_raw: str = raw.get("title_raw") or ""
    title_normalized = title_raw.lower().strip()
    description_raw: str = raw.get("description_raw") or ""

    return {
        "job_id": raw["job_id"],
        "source": "stepstone",
        "source_keyword": raw.get("source_keyword"),
        "source_city": raw.get("source_city"),
        "snapshot_date": date.today(),
        "fetched_at": datetime.now(tz=timezone.utc),
        "url": raw.get("url"),
        "title_raw": title_raw,
        "description_raw": description_raw,
        "salary_raw": None,
        "title_normalized": title_normalized,
        "company": raw.get("company"),
        "city": raw.get("location_raw"),
        "region": None,
        "country": "DE",
        "postal_code": None,
        "lat": None,
        "lon": None,
        "posted_date": _parse_posted_date(raw.get("posted_date_raw")),
        "employment_type": _scan_keywords(description_raw, _EMPLOYMENT_KEYWORDS),
        "work_model": _scan_keywords(description_raw, _WORK_MODEL_KEYWORDS),
        "language": _detect_language(description_raw),
        "role_category": _assign_role_category(title_normalized),
        "skills": [],
        "salary_min": None,
        "salary_max": None,
        "salary_currency": None,
        "is_duplicate": False,
        "canonical_id": None,
    }


def _normalize_linkedin(raw: dict[str, Any]) -> dict[str, Any]:
    """Map a raw LinkedIn CSV dict to the canonical jobs_raw schema."""
    title_raw: str = raw.get("title_raw") or ""
    title_normalized = title_raw.lower().strip()
    description_raw: str = raw.get("description_raw") or ""

    is_remote: bool | None = raw.get("is_remote")
    if is_remote is True:
        # LinkedIn badge doesn't distinguish remote vs hybrid; see decisions.md
        work_model = "UNKNOWN"
    elif is_remote is False:
        work_model = "ONSITE"
    else:
        work_model = _scan_keywords(description_raw, _WORK_MODEL_KEYWORDS)

    employment_hint = (raw.get("employment_type") or "") + " " + description_raw
    employment_type = _scan_keywords(employment_hint, _EMPLOYMENT_KEYWORDS)

    return {
        "job_id": raw["job_id_raw"],
        "source": "linkedin",
        "source_keyword": None,
        "source_city": raw.get("city_raw"),
        "snapshot_date": date.today(),
        "fetched_at": datetime.now(tz=timezone.utc),
        "url": raw.get("url"),
        "title_raw": title_raw,
        "description_raw": description_raw,
        "salary_raw": None,
        "title_normalized": title_normalized,
        "company": raw.get("company_raw"),
        "city": raw.get("city_raw"),
        "region": None,
        "country": "DE",
        "postal_code": None,
        "lat": None,
        "lon": None,
        "posted_date": _parse_posted_date(raw.get("posted_at_raw")),
        "employment_type": employment_type,
        "work_model": work_model,
        "language": _detect_language(description_raw),
        "role_category": _assign_role_category(title_normalized),
        "skills": [],
        "salary_min": None,
        "salary_max": None,
        "salary_currency": None,
        "is_duplicate": False,
        "canonical_id": None,
    }


def normalize(raw: dict[str, Any], source: str) -> dict[str, Any]:
    """Return a normalised job record.

    title_raw and description_raw must not be modified after this call.
    """
    if source == "bundesagentur":
        return _normalize_ba(raw)
    if source == "indeed":
        return _normalize_indeed(raw)
    if source == "stepstone":
        return _normalize_stepstone(raw)
    if source == "linkedin":
        return _normalize_linkedin(raw)
    raise ValueError(f"Unknown source: {source!r}")
