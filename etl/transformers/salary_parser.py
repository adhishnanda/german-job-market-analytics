"""Parse salary ranges from free-text job descriptions."""
from __future__ import annotations


def parse_salary(text: str) -> dict[str, float | None]:
    """Return {'min': float|None, 'max': float|None, 'currency': str|None}."""
    raise NotImplementedError
