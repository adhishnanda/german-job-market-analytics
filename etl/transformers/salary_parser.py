"""Parse salary ranges from raw salary strings (German and English formats)."""
from __future__ import annotations

import re

_CURRENCY_RE = re.compile(r"€|EUR\b|\$|USD\b|GBP\b|£", re.IGNORECASE)

_ANNUAL_RE = re.compile(
    r"\b(?:pro\s+Jahr|jährlich|per\s+year|annually?|p\.?\s*a\.?|per\s+annum)\b",
    re.IGNORECASE,
)
_MONTHLY_RE = re.compile(
    r"\b(?:pro\s+Monat|monatlich|per\s+month|monthly|/month|p\.?\s*m\.?)\b",
    re.IGNORECASE,
)

# Matches German/English thousands-separated numbers (40.000, 40,000) and plain
# integers, each with an optional 1-2 digit decimal part and optional k/K suffix.
_TOKEN_RE = re.compile(
    r"(\d{1,3}(?:[.,]\d{3})+(?:[.,]\d{1,2})?"  # thousands format
    r"|\d+(?:[.,]\d{1,2})?)"                    # plain integer or decimal
    r"([kK])?",
    re.IGNORECASE,
)

_MIN_SALARY = 500.0
_MAX_SALARY = 500_000.0
_MONTHLY_THRESHOLD = 10_000.0


def _detect_currency(text: str) -> str:
    """Return the currency code found in text, defaulting to 'EUR'."""
    m = _CURRENCY_RE.search(text)
    if not m:
        return "EUR"
    symbol = m.group(0).upper()
    if symbol in ("€", "EUR"):
        return "EUR"
    if symbol in ("$", "USD"):
        return "USD"
    if symbol in ("£", "GBP"):
        return "GBP"
    return "EUR"


def _parse_number(token: str) -> float | None:
    """Parse a numeric token into a float, handling German/English formats and k suffix."""
    token = token.strip()
    if not token:
        return None

    multiplier = 1.0
    if token[-1:].lower() == "k":
        multiplier = 1_000.0
        token = token[:-1]

    # German full format: 40.000,50 or 1.234.567,89
    m = re.fullmatch(r"(\d{1,3}(?:\.\d{3})+),(\d{1,2})", token)
    if m:
        return float(m.group(1).replace(".", "") + "." + m.group(2)) * multiplier

    # German thousands only: 40.000 or 1.234.567
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", token):
        return float(token.replace(".", "")) * multiplier

    # English full format: 40,000.50
    m = re.fullmatch(r"(\d{1,3}(?:,\d{3})+)\.(\d{1,2})", token)
    if m:
        return float(m.group(1).replace(",", "") + "." + m.group(2)) * multiplier

    # English thousands only: 40,000
    if re.fullmatch(r"\d{1,3}(?:,\d{3})+", token):
        return float(token.replace(",", "")) * multiplier

    # German decimal comma: 3,5 or 40,50 (no dots present)
    if re.search(r",\d{1,2}$", token) and "." not in token:
        return float(token.replace(",", ".")) * multiplier

    try:
        return float(token) * multiplier
    except ValueError:
        return None


def _extract_values(text: str) -> list[float]:
    """Return up to two salary-like numeric values found in text."""
    values: list[float] = []
    for m in _TOKEN_RE.finditer(text):
        raw = m.group(1) + (m.group(2) or "")
        val = _parse_number(raw)
        if val is not None and _MIN_SALARY <= val <= _MAX_SALARY:
            values.append(val)
    return values[:2]


def parse_salary(salary_raw: str | None) -> tuple[float | None, float | None, str | None]:
    """Parse a raw salary string into (salary_min, salary_max, currency).

    Returns (None, None, None) when no parseable salary is found.
    Monthly figures (explicit keyword or value < 10 000) are converted to annual (× 12).
    Explicit annual keywords (p.a., pro Jahr, …) override the implicit heuristic.
    Single values produce salary_min == salary_max.
    """
    if not salary_raw or not salary_raw.strip():
        return None, None, None

    text = salary_raw.strip()
    currency = _detect_currency(text)
    values = _extract_values(text)

    if not values:
        return None, None, None

    if _ANNUAL_RE.search(text):
        pass  # explicit annual — no conversion regardless of magnitude
    elif _MONTHLY_RE.search(text) or all(v < _MONTHLY_THRESHOLD for v in values):
        values = [v * 12.0 for v in values]

    sal_min = values[0]
    sal_max = values[1] if len(values) > 1 else values[0]
    return sal_min, sal_max, currency
