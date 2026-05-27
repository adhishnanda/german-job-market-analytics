# German Job Market Analytics — Project Context

## Project overview
Multi-source ETL pipeline collecting job postings from Bundesagentur API,
Indeed RSS, Stepstone (HTML), and LinkedIn (manual CSV). Analyzes skill demand
trends across German data/analytics roles. Final output: live Streamlit dashboard.

## Tech stack
- Python 3.11+ with virtual environment (venv)
- DuckDB for analytical storage
- Apache Airflow for orchestration
- Streamlit for dashboard
- BeautifulSoup4 + feedparser + requests for ingestion
- langdetect for language detection
- pytest for tests
- black + ruff for formatting/linting

## Project structure
etl/extractors/    — one file per source (bundesagentur.py, indeed.py, stepstone.py, linkedin.py)
etl/transformers/  — normalizer.py, skill_extractor.py, salary_parser.py, deduplicator.py
etl/loaders/       — duckdb_loader.py
airflow/dags/      — job_market_pipeline.py
dashboard/         — app.py, charts.py
data/raw/          — NEVER commit contents (in .gitignore)
data/processed/    — NEVER commit contents (in .gitignore)
data/db/           — NEVER commit *.duckdb files (in .gitignore)
tests/             — mirror etl/ structure, prefix test_*.py
docs/              — architecture.md, schema.md, decisions.md

## Coding conventions
- All functions must have docstrings and type hints
- Every extractor saves raw data as dated snapshots before any transformation
- Never modify title_raw or description_raw fields after initial extraction
- Source-prefix all job IDs: BA_, IN_, SS_, LI_
- Sleep between HTTP requests: min 2s (BA), 3s (Indeed), 10–18s random (Stepstone)
- Return empty list (not None) on failed fetches; log the error

## Commands
Run tests:        pytest tests/ -v
Format code:      black . && ruff check .
Start Airflow:    airflow standalone
Run dashboard:    streamlit run dashboard/app.py
Load to DuckDB:   python -m etl.loaders.duckdb_loader

## Git workflow
- Commit after each working module is complete, not after every file
- Commit message format: "feat: add Stepstone extractor with rate limiting"
- Never commit: data/, .env, *.duckdb, __pycache__/
- Branch for each new source: git checkout -b feat/stepstone-extractor

## Git commit rules
- Never add Co-authored-by lines to commit messages
- Never mention Claude, AI, or Anthropic in commit messages
- Commit messages must look like a human developer wrote them

## What NOT to do
- Do not use requests-html or Playwright for Stepstone (gets blocked faster)
- Do not parallelize scrapers — sequential only
- Do not hardcode sleep times — use random.uniform(min, max)
- Do not store raw HTML in DuckDB — store only parsed fields + raw text