# Project Progress

## Week 1 — Foundation

### Day 1 — 2026-05-27
- [x] Scaffold project directory structure
- [x] Create requirements.txt
- [x] Create .gitignore
- [x] Create skeleton README.md
- [x] Initialize Git and make first commit (`b97487c`)
- [x] Create GitHub remote and push

### Day 2 — 2026-05-28
- [x] Test Bundesagentur API connection manually
- [x] Build etl/extractors/bundesagentur.py
- [x] Write tests/test_bundesagentur.py
- [x] Run tests and fix failures
- [x] Commit and push

### Day 3 — 2026-05-29
- [x] Build etl/transformers/normalizer.py
- [x] Build etl/transformers/skill_extractor.py
- [x] Write tests for both transformers
- [x] Run tests and fix failures
- [x] Commit and push (`7309872`)

### Day 4 — 2026-05-30
- [x] Build etl/transformers/salary_parser.py
- [x] Build etl/transformers/deduplicator.py
- [x] Write tests for both
- [x] Commit and push

### Day 5 — 2026-05-31
- [x] Build etl/loaders/duckdb_loader.py
- [x] Create jobs_raw table schema in DuckDB
- [x] Create jobs_clean view
- [x] Create skills_exploded view
- [x] Write tests with in-memory DuckDB
- [x] End-to-end test: BA extract → normalize → load
- [x] Commit and push

## Week 2 — Additional Sources

### Day 6 — 2026-05-30
- [x] Build etl/extractors/indeed.py (RSS route)
- [x] Test Indeed RSS parsing
- [x] Normalize Indeed records through existing transformer
- [x] Recreate .venv with Python 3.11; revert duckdb/pandas version bumps
- [x] Fix loader upsert for DuckDB 1.1.3 list-column compatibility
- [x] Commit and push

### Day 7 — 2026-05-30
- [x] Build etl/extractors/stepstone.py
- [x] Write tests/test_stepstone.py (41 tests)
- [x] Verify rate limiting, 403/429 handling, slug conversion
- [x] Commit and push

### Day 8
- [x] Create docs/linkedin_manual_template.csv
- [x] Build etl/extractors/linkedin.py (CSV reader)
- [x] Write tests/test_linkedin.py (37 tests)
- [x] Collect first 20 LinkedIn listings manually
- [x] Commit and push

### Day 9 — 2026-05-31
- [x] Validate linkedin_sample.csv: 20 rows, no missing job_id or title, all applicant_counts valid integers
- [x] Add city_raw auto-fill to "Berlin" when field is empty or missing (LinkedIn extractor)
- [x] Add _parse_relative_date: converts "N days/weeks/months/years ago" to approximate ISO date
- [x] Log four LinkedIn data-quality decisions in docs/decisions.md
- [x] Add _parse_posted_date to normalizer: handles YYYY-MM-DD, ISO 8601 with time, DD-MM-YYYY, RFC 2822
- [x] Add _normalize_stepstone and _normalize_linkedin to normalizer; update dispatch
- [x] Add 7 _parse_posted_date tests + Stepstone/LinkedIn normalizer tests (80 total in test_normalizer.py)
- [x] Build tests/test_pipeline_integration.py: 4-source fixture → normalize → deduplicate → load, 12 assertions
- [x] Commit and push

### Day 10 — 2026-05-31
- [x] Build etl/pipeline_runner.py (4-stage runner: extract → normalize → dedup → load + summary report)
- [x] Build etl/data_quality.py (5 checks: source dist, null rates, date range, dup rate, skill coverage)
- [x] Fix Stepstone _parse_cards: job ID moved to id="job-item-{n}", date now German timeago text
- [x] Add _parse_german_timeago to stepstone.py for "vor N Tagen/Wochen/..." patterns
- [x] Add max_pages parameter to stepstone.fetch_jobs for limited dry-run
- [x] Fix LinkedIn CSV encoding: try utf-8-sig → cp1252 fallback
- [x] Fix loader: drop_duplicates by job_id before INSERT (BA returns same job across keyword×city combos)
- [x] Full pipeline dry run: BA=853, Indeed=0 (blocked), Stepstone=25, LinkedIn=20 → 898 records → 543 in DB
- [x] Data quality run: Indeed blocked (flag), 63 old BA posts (expected), skill coverage 3.5% (structural)
- [x] Log all Day 10 findings in docs/decisions.md
- [x] Commit and push

## Week 3 — Airflow and Dashboard

### Day 11 — 2026-05-31
- [x] Install apache-airflow-providers-standard (FileSensor); Airflow upgraded 2.9.3 → 3.2.2
- [x] Build airflow/dags/job_market_pipeline.py: 6 tasks, @daily, FileSensor for LinkedIn CSV
- [x] Write tests/test_dag_loads.py: 9 tests verifying DAG structure offline
- [x] Update requirements.txt to pin apache-airflow==3.2.2 + providers-standard==1.13.1
- [x] Commit and push

### Day 12
- [ ] Build analytics/aggregations.py (skill counts, role counts, salary dist)
- [ ] Write and test core SQL queries in DuckDB
- [ ] Commit and push

### Day 13
- [ ] Build dashboard/app.py — Streamlit skeleton + DuckDB connection
- [ ] Add skill demand over time chart
- [ ] Add role count by city chart
- [ ] Commit and push

### Day 14
- [ ] Add salary distribution by role chart
- [ ] Add source coverage comparison chart
- [ ] Add English vs German ratio chart
- [ ] Add sidebar filters (date, city, role category)
- [ ] Commit and push

## Week 4 — Polish and Deploy

### Day 15
- [ ] Deploy Streamlit app to Streamlit Cloud
- [ ] Test live deployment
- [ ] Add live demo link to README.md
- [ ] Commit and push

### Day 16
- [ ] Write full README.md with screenshots and methodology
- [ ] Add architecture diagram to docs/architecture.md
- [ ] Add data quality notes and coverage gaps disclosure
- [ ] Commit and push

### Day 17
- [ ] Write LinkedIn post draft
- [ ] Take dashboard screenshots for LinkedIn
- [ ] Final code review and cleanup
- [ ] Tag v1.0.0 release on GitHub

### Day 18 (buffer)
- [ ] Fix anything broken from real-world data
- [ ] Add GitHub Actions workflow for scheduled BA refresh
- [ ] Final push

## Notes
<!-- Add decisions, blockers, or observations here as you go -->