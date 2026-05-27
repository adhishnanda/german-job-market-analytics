"""Load normalised job records into DuckDB."""
from __future__ import annotations

from pathlib import Path
from typing import Any


def load(jobs: list[dict[str, Any]], db_path: Path) -> None:
    """Upsert *jobs* into the DuckDB database at *db_path*."""
    raise NotImplementedError


if __name__ == "__main__":
    raise SystemExit("Run via: python -m etl.loaders.duckdb_loader")
