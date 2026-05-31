"""Post-load data quality checker for jobs_raw in DuckDB."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import duckdb

from etl.loaders.duckdb_loader import DEFAULT_DB_PATH

logger = logging.getLogger(__name__)

# Thresholds
_NULL_RATE_THRESHOLD = 0.20       # flag if null rate > 20% for a non-salary field
_DUP_RATE_THRESHOLD = 0.30        # flag if global duplicate rate > 30%
_SKILL_COVERAGE_THRESHOLD = 0.50  # flag if < 50% of canonical records have skills
_DATE_WINDOW_DAYS = 90            # flag postings older than 90 days

# Fields checked for null rate (per source); salary_min excluded — expected high
_NULL_CHECK_FIELDS = ["city", "posted_date", "company", "title_normalized"]

_EXPECTED_SOURCES = {"bundesagentur", "indeed", "stepstone", "linkedin"}

_line = "=" * 64


def _ok(msg: str) -> str:
    return f"  OK    {msg}"


def _fail(msg: str) -> str:
    return f"  FAIL  {msg}"


def check(db_path: Path = DEFAULT_DB_PATH) -> bool:
    """Run all data-quality checks against db_path.

    Prints a report to stdout and returns True when every check passes.
    """
    if not db_path.exists():
        print(f"Database not found: {db_path}")
        return False

    conn = duckdb.connect(str(db_path), read_only=True)
    all_pass = True

    print(f"\n{_line}")
    print("DATA QUALITY REPORT")
    print(_line)

    # -----------------------------------------------------------------------
    # 1. Source distribution — flag any expected source with 0 records
    # -----------------------------------------------------------------------
    print("\n[1] Source distribution")
    rows = conn.execute(
        "SELECT source, COUNT(*) FROM jobs_raw GROUP BY source ORDER BY source"
    ).fetchall()
    sources_found: set[str] = set()
    for src, cnt in rows:
        sources_found.add(src)
        print(f"  {src:<22s}  {cnt:>5d} records")

    missing = _EXPECTED_SOURCES - sources_found
    if missing:
        for src in sorted(missing):
            print(_fail(f"No records for source '{src}'"))
        all_pass = False
    else:
        print(_ok("All expected sources present"))

    # -----------------------------------------------------------------------
    # 2. Null rates per field per source — flag if > 20%
    # -----------------------------------------------------------------------
    print(f"\n[2] Null rates per field per source  (threshold {int(_NULL_RATE_THRESHOLD * 100)}%)")
    field_issues = False
    for field in _NULL_CHECK_FIELDS:
        field_rows = conn.execute(
            f"""
            SELECT
                source,
                COUNT(*) AS total,
                SUM(CASE WHEN {field} IS NULL OR CAST({field} AS VARCHAR) = '' THEN 1 ELSE 0 END) AS nulls,
                ROUND(
                    100.0 * SUM(CASE WHEN {field} IS NULL OR CAST({field} AS VARCHAR) = '' THEN 1 ELSE 0 END)
                    / COUNT(*), 1
                ) AS null_pct
            FROM jobs_raw
            GROUP BY source
            ORDER BY source
            """
        ).fetchall()
        print(f"\n  {field}")
        for src, total, nulls, null_pct in field_rows:
            bar = "  *** HIGH ***" if null_pct > _NULL_RATE_THRESHOLD * 100 else ""
            print(f"    {src:<22s}  {null_pct:>5.1f}%{bar}")
            if null_pct > _NULL_RATE_THRESHOLD * 100:
                field_issues = True
                all_pass = False

    if not field_issues:
        print(_ok("All null rates within threshold"))

    # -----------------------------------------------------------------------
    # 3. Date range — flag postings older than 90 days
    # -----------------------------------------------------------------------
    print(f"\n[3] Date range sanity check  (window {_DATE_WINDOW_DAYS} days)")
    row = conn.execute(
        f"""
        SELECT
            MIN(posted_date)  AS oldest,
            MAX(posted_date)  AS newest,
            COUNT(*) FILTER (WHERE posted_date < CURRENT_DATE - INTERVAL '{_DATE_WINDOW_DAYS} days')
                AS old_count,
            COUNT(*) FILTER (WHERE posted_date IS NULL) AS null_date_count
        FROM jobs_raw
        """
    ).fetchone()
    if row:
        oldest, newest, old_count, null_date_count = row
        print(f"  Oldest posting       : {oldest}")
        print(f"  Newest posting       : {newest}")
        print(f"  Null posted_date     : {null_date_count}")
        if old_count > 0:
            print(_fail(f"{old_count} postings older than {_DATE_WINDOW_DAYS} days"))
            all_pass = False
        else:
            print(_ok(f"No postings beyond {_DATE_WINDOW_DAYS}-day window"))

    # -----------------------------------------------------------------------
    # 4. Duplicate rate — flag if > 30%
    # -----------------------------------------------------------------------
    print(f"\n[4] Duplicate rate  (threshold {int(_DUP_RATE_THRESHOLD * 100)}%)")
    row = conn.execute(
        """
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN is_duplicate THEN 1 ELSE 0 END) AS dups,
            ROUND(
                100.0 * SUM(CASE WHEN is_duplicate THEN 1 ELSE 0 END) / COUNT(*), 1
            ) AS dup_pct
        FROM jobs_raw
        """
    ).fetchone()
    if row:
        total, dups, dup_pct = row
        print(f"  Total records        : {total}")
        print(f"  Duplicates           : {dups}")
        print(f"  Duplicate rate       : {dup_pct}%")
        if dup_pct > _DUP_RATE_THRESHOLD * 100:
            print(_fail(f"Duplicate rate {dup_pct}% exceeds threshold {int(_DUP_RATE_THRESHOLD * 100)}%"))
            all_pass = False
        else:
            print(_ok("Duplicate rate within threshold"))

    # -----------------------------------------------------------------------
    # 5. Skill extraction coverage — flag if < 50% of canonical records
    # -----------------------------------------------------------------------
    print(f"\n[5] Skill extraction coverage  (threshold {int(_SKILL_COVERAGE_THRESHOLD * 100)}%)")
    row = conn.execute(
        """
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN len(skills) > 0 THEN 1 ELSE 0 END) AS with_skills,
            ROUND(
                100.0 * SUM(CASE WHEN len(skills) > 0 THEN 1 ELSE 0 END) / COUNT(*), 1
            ) AS coverage_pct
        FROM jobs_raw
        WHERE is_duplicate = FALSE
        """
    ).fetchone()
    if row:
        total, with_skills, coverage_pct = row
        print(f"  Canonical records    : {total}")
        print(f"  With >=1 skill       : {with_skills}")
        print(f"  Coverage             : {coverage_pct}%")
        if coverage_pct < _SKILL_COVERAGE_THRESHOLD * 100:
            print(_fail(f"Coverage {coverage_pct}% below threshold {int(_SKILL_COVERAGE_THRESHOLD * 100)}%"))
            all_pass = False
        else:
            print(_ok("Skill coverage within threshold"))

    conn.close()

    print(f"\n{_line}")
    if all_pass:
        print("RESULT: ALL CHECKS PASSED")
    else:
        print("RESULT: SOME CHECKS FAILED — see above")
    print(f"{_line}\n")

    return all_pass


if __name__ == "__main__":
    passed = check()
    sys.exit(0 if passed else 1)
