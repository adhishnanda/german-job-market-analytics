"""Normalise raw job dicts from all sources into a common schema."""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any

from langdetect import LangDetectException, detect

logger = logging.getLogger(__name__)

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
    try:
        posted_date: date | None = date.fromisoformat(posted_date_str) if posted_date_str else None
    except ValueError:
        posted_date = None

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


def normalize(raw: dict[str, Any], source: str) -> dict[str, Any]:
    """Return a normalised job record.

    title_raw and description_raw must not be modified after this call.
    """
    if source == "bundesagentur":
        return _normalize_ba(raw)
    raise ValueError(f"Unknown source: {source!r}")
