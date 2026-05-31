"""End-to-end pipeline runner: extract → normalize → deduplicate → load → report."""
from __future__ import annotations

import logging
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any

from etl.extractors import bundesagentur, indeed, stepstone
from etl.extractors import linkedin as linkedin_ext
from etl.loaders import duckdb_loader
from etl.loaders.duckdb_loader import DEFAULT_DB_PATH
from etl.transformers import deduplicator, normalizer, salary_parser, skill_extractor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

LINKEDIN_SAMPLE = Path("data/raw/linkedin_sample.csv")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize_batch(raw_records: list[dict[str, Any]], source: str) -> list[dict[str, Any]]:
    """Normalize, parse salary, and extract skills for one source batch."""
    out: list[dict[str, Any]] = []
    for raw in raw_records:
        try:
            record = normalizer.normalize(raw, source)
        except Exception as exc:
            raw_id = raw.get("job_id") or raw.get("job_id_raw") or "?"
            logger.warning("Normalize error (%s, id=%s): %s", source, raw_id, exc)
            continue

        sal_raw = record.get("salary_raw")
        if sal_raw:
            smin, smax, scur = salary_parser.parse_salary(sal_raw)
            record["salary_min"] = smin
            record["salary_max"] = smax
            record["salary_currency"] = scur

        record["skills"] = skill_extractor.extract_skills(record.get("description_raw") or "")
        out.append(record)
    return out


def _null_rate(records: list[dict[str, Any]], field: str) -> float:
    """Fraction of records where field is None or empty string."""
    if not records:
        return 0.0
    return sum(1 for r in records if not r.get(field)) / len(records)


# ---------------------------------------------------------------------------
# Summary report
# ---------------------------------------------------------------------------

def _print_summary(
    extracted: dict[str, list[dict[str, Any]]],
    normalized_all: list[dict[str, Any]],
    after_dedup: list[dict[str, Any]],
    loaded: int,
) -> None:
    """Print a full pipeline summary report to stdout."""
    line = "=" * 64

    print(f"\n{line}")
    print("PIPELINE SUMMARY REPORT")
    print(line)

    # --- Extracted per source ---
    print("\n[Extracted per source]")
    total_extracted = 0
    for src, recs in sorted(extracted.items()):
        print(f"  {src:<22s}  {len(recs):>5d}")
        total_extracted += len(recs)
    print(f"  {'TOTAL':<22s}  {total_extracted:>5d}")

    # --- After normalization ---
    by_source_norm: Counter = Counter(r["source"] for r in normalized_all)
    print(f"\n[After normalization]  total={len(normalized_all)}")
    for src in sorted(by_source_norm):
        print(f"  {src:<22s}  {by_source_norm[src]:>5d}")

    # --- After deduplication ---
    dup_count = sum(1 for r in after_dedup if r.get("is_duplicate"))
    canonical_count = len(after_dedup) - dup_count
    dup_pct = dup_count / len(after_dedup) * 100 if after_dedup else 0.0
    print(f"\n[After deduplication]")
    print(f"  {'Total records':<22s}  {len(after_dedup):>5d}")
    print(f"  {'Canonical':<22s}  {canonical_count:>5d}")
    print(f"  {'Duplicates':<22s}  {dup_count:>5d}  ({dup_pct:.1f}%)")

    # --- Duplicate rate per source ---
    print("\n[Duplicate rate per source]")
    src_stats: dict[str, list[int]] = defaultdict(lambda: [0, 0])  # [dups, total]
    for r in after_dedup:
        src = r.get("source", "unknown")
        src_stats[src][1] += 1
        if r.get("is_duplicate"):
            src_stats[src][0] += 1
    for src in sorted(src_stats):
        dups, total = src_stats[src]
        rate = dups / total * 100 if total else 0.0
        print(f"  {src:<22s}  {dups:>3d}/{total:<5d}  ({rate:.1f}%)")

    # --- Loaded ---
    print(f"\n[Loaded to DuckDB]")
    print(f"  Records loaded         : {loaded}")

    # --- Null rates for key fields (canonical records only) ---
    canonical = [r for r in after_dedup if not r.get("is_duplicate")]
    print(f"\n[Null rates — canonical records only]")
    for field in ("salary_min", "city", "posted_date"):
        rate = _null_rate(canonical, field)
        flag = "  *** HIGH ***" if rate > 0.50 else ""
        print(f"  {field:<22s}  {rate * 100:>5.1f}%{flag}")

    # --- Top 10 skills ---
    skill_ctr: Counter = Counter()
    for r in canonical:
        for sk in r.get("skills") or []:
            skill_ctr[sk] += 1
    print("\n[Top 10 skills]")
    for skill, cnt in skill_ctr.most_common(10):
        print(f"  {skill:<32s}  {cnt:>4d}")

    # --- Top 5 companies ---
    company_ctr: Counter = Counter(
        r["company"] for r in canonical if r.get("company")
    )
    print("\n[Top 5 companies by posting count]")
    for company, cnt in company_ctr.most_common(5):
        print(f"  {company:<40s}  {cnt:>4d}")

    print(f"\n{line}\n")


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_pipeline(
    linkedin_csv: Path = LINKEDIN_SAMPLE,
    stepstone_keywords: list[str] | None = None,
    stepstone_max_pages: int = 1,
    db_path: Path = DEFAULT_DB_PATH,
) -> None:
    """Run the full pipeline end-to-end.

    Args:
        linkedin_csv: Path to the LinkedIn sample CSV.
        stepstone_keywords: Stepstone keyword slugs to scrape (default: ["data-analyst"]).
        stepstone_max_pages: Max pages per Stepstone keyword (default: 1 to avoid blocks).
        db_path: Target DuckDB file path.
    """
    if stepstone_keywords is None:
        stepstone_keywords = ["data-analyst"]

    today = date.today().isoformat()
    extracted: dict[str, list[dict[str, Any]]] = {}

    # -----------------------------------------------------------------------
    # 1. Extract
    # -----------------------------------------------------------------------
    print("\n[1/4] Extracting from all sources...")

    print("  bundesagentur (live API)...", end="", flush=True)
    ba_records = bundesagentur.extract()
    extracted["bundesagentur"] = ba_records
    print(f"  {len(ba_records)} records")

    print("  indeed (RSS feeds)...", end="", flush=True)
    indeed_records = indeed.extract()
    extracted["indeed"] = indeed_records
    print(f"  {len(indeed_records)} records")

    print(
        f"  stepstone (keywords={stepstone_keywords}, max_pages={stepstone_max_pages})...",
        end="",
        flush=True,
    )
    ss_records = stepstone.fetch_jobs(
        keywords=stepstone_keywords,
        locations=["berlin"],
        max_pages=stepstone_max_pages,
    )
    if ss_records:
        stepstone._save_snapshot(ss_records, today)
    extracted["stepstone"] = ss_records
    print(f"  {len(ss_records)} records")

    print(f"  linkedin (csv={linkedin_csv})...", end="", flush=True)
    if linkedin_csv.exists():
        li_records = linkedin_ext._read_csv(linkedin_csv)
    else:
        logger.warning("LinkedIn CSV not found: %s", linkedin_csv)
        li_records = []
    extracted["linkedin"] = li_records
    print(f"  {len(li_records)} records")

    # -----------------------------------------------------------------------
    # 2. Normalize
    # -----------------------------------------------------------------------
    print("\n[2/4] Normalizing...")
    all_normalized: list[dict[str, Any]] = []
    for source, records in extracted.items():
        batch = _normalize_batch(records, source)
        all_normalized.extend(batch)
        print(f"  {source:<22s}  {len(batch)} normalized")
    print(f"  {'TOTAL':<22s}  {len(all_normalized)}")

    # -----------------------------------------------------------------------
    # 3. Deduplicate
    # -----------------------------------------------------------------------
    print("\n[3/4] Deduplicating...")
    deduped = deduplicator.deduplicate(all_normalized)
    dup_count = sum(1 for r in deduped if r.get("is_duplicate"))
    canonical_count = len(deduped) - dup_count
    dup_pct = dup_count / len(deduped) * 100 if deduped else 0.0
    print(f"  Total={len(deduped)}  canonical={canonical_count}  duplicates={dup_count} ({dup_pct:.1f}%)")

    # -----------------------------------------------------------------------
    # 4. Load
    # -----------------------------------------------------------------------
    print("\n[4/4] Loading to DuckDB...")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    loaded = duckdb_loader.load(deduped, db_path)
    print(f"  Loaded {loaded} records to {db_path}")

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    _print_summary(extracted, all_normalized, deduped, loaded)


if __name__ == "__main__":
    run_pipeline()
