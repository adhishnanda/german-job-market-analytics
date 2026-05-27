"""Loader for manually exported LinkedIn job CSV files (LI_)."""
from __future__ import annotations

from pathlib import Path
from typing import Any


def load_csv(path: Path) -> list[dict[str, Any]]:
    """Read a LinkedIn CSV export and return normalised job dicts.

    Returns an empty list on failure; never raises.
    """
    raise NotImplementedError
