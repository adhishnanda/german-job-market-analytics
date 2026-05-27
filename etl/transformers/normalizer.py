"""Normalise raw job dicts from all sources into a common schema."""
from __future__ import annotations

from typing import Any


def normalize(raw: dict[str, Any], source: str) -> dict[str, Any]:
    """Return a normalised job record.

    title_raw and description_raw must not be modified after this call.
    """
    raise NotImplementedError
