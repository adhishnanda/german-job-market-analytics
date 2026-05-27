# German Job Market Analytics

Multi-source ETL pipeline and dashboard for analysing skill demand trends in
German data and analytics roles.

## Sources

| Source | Prefix | Method |
|---|---|---|
| Bundesagentur für Arbeit | `BA_` | REST API |
| Indeed Germany | `IN_` | RSS feed |
| Stepstone | `SS_` | HTML scraping |
| LinkedIn | `LI_` | Manual CSV export |

## Tech stack

- **Storage** — DuckDB
- **Orchestration** — Apache Airflow
- **Dashboard** — Streamlit
- **Ingestion** — requests, feedparser, BeautifulSoup4

## Setup

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env           # fill in any required credentials
```

## Running

```bash
# Run the full test suite
pytest tests/ -v

# Format and lint
black . && ruff check .

# Start the Airflow scheduler (first-time setup)
airflow standalone

# Load processed data into DuckDB
python -m etl.loaders.duckdb_loader

# Launch the dashboard
streamlit run dashboard/app.py
```

## Project layout

```
etl/
  extractors/      # one file per source
  transformers/    # normalizer, skill extractor, salary parser, deduplicator
  loaders/         # duckdb_loader
airflow/dags/      # Airflow DAG definition
dashboard/         # Streamlit app
data/
  raw/             # dated snapshots (gitignored)
  processed/       # cleaned records (gitignored)
  db/              # *.duckdb files (gitignored)
tests/             # mirrors etl/ structure
docs/              # architecture, schema, decisions
```

## Contributing

See `docs/decisions.md` for architectural decisions and `docs/architecture.md`
for the system overview.
