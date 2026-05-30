"""Load normalised job records into DuckDB."""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path("data/db/jobs.duckdb")

# Canonical column order — must match the CREATE TABLE statement below.
_COLUMNS: list[str] = [
    "job_id",
    "source",
    "source_keyword",
    "source_city",
    "snapshot_date",
    "fetched_at",
    "url",
    "title_raw",
    "description_raw",
    "salary_raw",
    "title_normalized",
    "company",
    "city",
    "region",
    "country",
    "postal_code",
    "lat",
    "lon",
    "posted_date",
    "employment_type",
    "work_model",
    "language",
    "role_category",
    "salary_min",
    "salary_max",
    "salary_currency",
    "skills",
    "is_duplicate",
    "canonical_id",
]

_CREATE_JOBS_RAW = """\
CREATE TABLE IF NOT EXISTS jobs_raw (
    job_id           VARCHAR PRIMARY KEY,
    source           VARCHAR,
    source_keyword   VARCHAR,
    source_city      VARCHAR,
    snapshot_date    DATE,
    fetched_at       TIMESTAMP,
    url              VARCHAR,
    title_raw        VARCHAR,
    description_raw  VARCHAR,
    salary_raw       VARCHAR,
    title_normalized VARCHAR,
    company          VARCHAR,
    city             VARCHAR,
    region           VARCHAR,
    country          VARCHAR,
    postal_code      VARCHAR,
    lat              DOUBLE,
    lon              DOUBLE,
    posted_date      DATE,
    employment_type  VARCHAR,
    work_model       VARCHAR,
    language         VARCHAR,
    role_category    VARCHAR,
    salary_min       DOUBLE,
    salary_max       DOUBLE,
    salary_currency  VARCHAR,
    skills           VARCHAR[],
    is_duplicate     BOOLEAN,
    canonical_id     VARCHAR
)"""

_CREATE_JOBS_CLEAN = """\
CREATE OR REPLACE VIEW jobs_clean AS
SELECT * FROM jobs_raw
WHERE is_duplicate = FALSE"""

_CREATE_SKILLS_EXPLODED = """\
CREATE OR REPLACE VIEW skills_exploded AS
SELECT
    job_id,
    source,
    city,
    role_category,
    posted_date,
    unnest(skills) AS skill
FROM jobs_raw
WHERE is_duplicate = FALSE"""


def _ensure_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Create jobs_raw table and derived views if they do not already exist."""
    conn.execute(_CREATE_JOBS_RAW)
    conn.execute(_CREATE_JOBS_CLEAN)
    conn.execute(_CREATE_SKILLS_EXPLODED)


def get_connection(db_path: Path = DEFAULT_DB_PATH) -> duckdb.DuckDBPyConnection:
    """Open (or create) the DuckDB database and ensure the schema exists.

    The caller is responsible for closing the returned connection.
    """
    conn = duckdb.connect(str(db_path))
    _ensure_schema(conn)
    return conn


def load_to_connection(
    jobs: list[dict[str, Any]],
    conn: duckdb.DuckDBPyConnection,
) -> int:
    """Upsert jobs into jobs_raw; return the row count.

    Deletes any existing rows whose job_id matches the incoming batch, then
    inserts the full batch — achieving idempotent upsert semantics that work
    with the VARCHAR[] skills column.  The caller owns conn and must not
    close it between calls.
    """
    if not jobs:
        return 0

    rows: list[dict[str, Any]] = []
    for job in jobs:
        row = {col: job.get(col) for col in _COLUMNS}
        # DuckDB TIMESTAMP is tz-naive; strip UTC tzinfo (value is already UTC).
        if isinstance(row.get("fetched_at"), datetime) and row["fetched_at"].tzinfo is not None:
            row["fetched_at"] = row["fetched_at"].replace(tzinfo=None)
        rows.append(row)

    df = pd.DataFrame(rows, columns=_COLUMNS)
    col_list = ", ".join(_COLUMNS)

    # INSERT OR REPLACE does not support list columns in DuckDB 1.1.x; and
    # registering a view inside an explicit BEGIN breaks its visibility.
    # Two auto-committed statements on the same in-process connection are
    # effectively serialized, so no external transaction wrapper is needed.
    conn.register("_staging", df)
    conn.execute("DELETE FROM jobs_raw WHERE job_id IN (SELECT job_id FROM _staging)")
    conn.execute(f"INSERT INTO jobs_raw ({col_list}) SELECT {col_list} FROM _staging")

    return len(rows)


def load(
    jobs: list[dict[str, Any]],
    db_path: Path = DEFAULT_DB_PATH,
) -> int:
    """Open db_path, upsert jobs, close, and return the row count."""
    conn = get_connection(db_path)
    try:
        return load_to_connection(jobs, conn)
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit("Run via: python -m etl.loaders.duckdb_loader")
