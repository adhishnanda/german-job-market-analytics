# Architecture Decisions

## 2026-05-27 — Initial scaffold

### Dependency pinning strategy
All packages in `requirements.txt` are pinned to exact versions (`==`).
Reason: scraping projects are brittle — a minor feedparser or bs4 bump can
silently change parsing behaviour and corrupt the historical dataset.
Trade-off: manual version bumps required; accepted given the small team size.

### Chart libraries: Plotly + Altair both included
Both `plotly` and `altair` are listed as dependencies because Streamlit has
native support for both and they cover complementary use cases (Plotly for
interactive drill-down, Altair for declarative layered charts). Whichever
works best for a given chart will be used; the other can be dropped later
without breaking anything.

### DuckDB as the only storage layer
No separate Postgres or SQLite. DuckDB handles all analytical queries
directly on `.duckdb` files stored in `data/db/`. This keeps the stack
self-contained — no server to run — and DuckDB's columnar engine is
well-suited to the aggregation-heavy dashboard queries.

### `data/` directories gitignored but scaffolded with `.gitkeep`
The `.gitkeep` files themselves are gitignored (parent dirs are in
`.gitignore`) so `data/raw/`, `data/processed/`, and `data/db/` will not
exist on a fresh clone. Fresh-clone setup step: `mkdir -p data/{raw,processed,db}`.
This will be added to README setup instructions when the first extractor lands.

### Stub pattern: `raise NotImplementedError`
Skeleton functions raise `NotImplementedError` rather than returning empty
lists. Empty-list stubs would let tests pass silently on unimplemented code;
`NotImplementedError` makes the gap obvious and forces the test to be skipped
explicitly (`pytest.skip`) until the real implementation exists.

## 2026-05-28 — Bundesagentur API (Day 2 live testing)

### BA API version: v6, not v4
During live connection testing the v4 endpoint (`/pc/v4/jobs`) returned 403 for
all requests. Investigation via the Angular app's `config/config.js` revealed
the active endpoint is `/pc/v6/jobs`.

### API key: `jobboerse-jobsuche`
The key embedded in the BA Jobsuche SPA is `jobboerse-jobsuche` (previously
`jobboerse-jobsuche-ui` in older versions of the app). Passed as `X-API-Key`
header. No OAuth Bearer token is required for the public search endpoint.

### v6 pagination is 1-indexed
The `page` query parameter in v6 starts at 1 (not 0). Sending `page=0` returns
a 400 with `"must be greater than or equal to 1"`. The extractor initialises
each keyword × city loop at `page = 1`.

### v6 response field names differ from v4
| v4 field | v6 field |
|---|---|
| `stellenangebote` | `ergebnisliste` |
| `hashId` | `referenznummer` |

`maxErgebnisse` is unchanged. The extractor and tests were updated to use the v6
field names; the `BA_` prefix uses `referenznummer` as the raw ID.

### Browser User-Agent required
The API gateway applies a WAF rule that varies on `User-Agent`. A browser-like
string (`Mozilla/5.0 … AppleWebKit/537.36`) passes through; a Python or curl
default does not. The `_HEADERS` dict in the extractor uses a Chrome UA.

### Airflow DAG: `@daily`, `catchup=False`
The DAG is set to run once per day with no historical backfill. Bundesagentur
and Indeed data is near-real-time; backfilling old dates would produce
incomplete snapshots anyway. This can be revisited once a stable historical
baseline exists.
