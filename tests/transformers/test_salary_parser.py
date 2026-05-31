"""Tests for the salary parser."""

from __future__ import annotations

import pytest

from etl.transformers.salary_parser import parse_salary


class TestParseSalaryNullCases:
    def test_none_returns_none_triple(self) -> None:
        assert parse_salary(None) == (None, None, None)

    def test_empty_string_returns_none_triple(self) -> None:
        assert parse_salary("") == (None, None, None)

    def test_whitespace_only_returns_none_triple(self) -> None:
        assert parse_salary("   ") == (None, None, None)

    def test_garbage_returns_none_triple(self) -> None:
        assert parse_salary("Competitive salary, please enquire") == (None, None, None)


class TestParseSalarySingleValue:
    def test_german_thousands_single(self) -> None:
        sal_min, sal_max, currency = parse_salary("€40.000")
        assert sal_min == sal_max == 40_000.0
        assert currency == "EUR"

    def test_k_suffix_single(self) -> None:
        sal_min, sal_max, currency = parse_salary("€40k")
        assert sal_min == sal_max == 40_000.0
        assert currency == "EUR"

    def test_plain_annual_large(self) -> None:
        sal_min, sal_max, currency = parse_salary("50000 EUR")
        assert sal_min == sal_max == 50_000.0
        assert currency == "EUR"


class TestParseSalaryRanges:
    def test_range_german_em_dash(self) -> None:
        sal_min, sal_max, currency = parse_salary("€40.000 – €80.000")
        assert sal_min == 40_000.0
        assert sal_max == 80_000.0
        assert currency == "EUR"

    def test_range_k_suffix_hyphen(self) -> None:
        sal_min, sal_max, currency = parse_salary("40k-55k EUR")
        assert sal_min == 40_000.0
        assert sal_max == 55_000.0
        assert currency == "EUR"

    def test_range_english_commas(self) -> None:
        sal_min, sal_max, currency = parse_salary("€40,000-€55,000")
        assert sal_min == 40_000.0
        assert sal_max == 55_000.0
        assert currency == "EUR"

    def test_range_pa_annotation(self) -> None:
        sal_min, sal_max, currency = parse_salary("€60.000 – €80.000 p.a.")
        assert sal_min == 60_000.0
        assert sal_max == 80_000.0
        assert currency == "EUR"


class TestParseSalaryMonthlyConversion:
    def test_german_monthly_keyword(self) -> None:
        sal_min, sal_max, currency = parse_salary("3.500€ pro Monat")
        assert sal_min == sal_max == 42_000.0
        assert currency == "EUR"

    def test_english_monthly_keyword(self) -> None:
        sal_min, sal_max, currency = parse_salary("3500 EUR/month")
        assert sal_min == sal_max == 42_000.0
        assert currency == "EUR"

    def test_implicit_monthly_below_threshold(self) -> None:
        # 4000 < 10 000 → treated as monthly → × 12
        sal_min, sal_max, currency = parse_salary("4000 EUR")
        assert sal_min == sal_max == 48_000.0
        assert currency == "EUR"

    def test_annual_keyword_overrides_small_value(self) -> None:
        # 8000 < 10 000, but p.a. says annual — no conversion
        sal_min, sal_max, currency = parse_salary("8000 EUR p.a.")
        assert sal_min == sal_max == 8_000.0
        assert currency == "EUR"


class TestParseSalaryBoundary:
    def test_exactly_10000_treated_as_annual(self) -> None:
        sal_min, sal_max, _ = parse_salary("10000 EUR")
        assert sal_min == sal_max == 10_000.0

    def test_9999_treated_as_monthly(self) -> None:
        sal_min, sal_max, _ = parse_salary("9999 EUR")
        assert sal_min == sal_max == pytest.approx(9999 * 12.0)


class TestParseSalaryCurrency:
    def test_currency_defaults_to_eur_when_absent(self) -> None:
        _, _, currency = parse_salary("50000")
        assert currency == "EUR"

    def test_euro_sign_detected(self) -> None:
        _, _, currency = parse_salary("€50.000")
        assert currency == "EUR"

    def test_usd_detected(self) -> None:
        _, _, currency = parse_salary("$80,000")
        assert currency == "USD"
