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

## 2026-05-29 — Normalizer and skill extractor (Day 3)

### Role taxonomy: ordered list, first match wins
`_ROLE_TAXONOMY` in `normalizer.py` is a `list[tuple]`, not a dict, so match
order is deterministic and explicit. A title like "ML Engineer" would satisfy
both the "Data Science / ML" bucket (which contains "ml engineer") and the
"ML Engineering" bucket. By placing "Data Science / ML" above "ML Engineering"
in the list the intent is clear: a bare "ML Engineer" title defaults to the
broader science/ML grouping. The order can be changed without touching the
matching logic.
Trade-off: "ML Engineering" as a separate bucket is currently hard to reach
because "ml engineer" is caught by "Data Science / ML" first. This is
intentional for now — the bucket exists to catch compound titles like
"MLOps / ML Engineering" where "ml engineer" appears alongside "mlops".

### Role category falls through to "Other"
The normalizer returns "Other" rather than `None` when no taxonomy keyword
matches. A string value is easier to filter and group in SQL (`WHERE
role_category = 'Other'`) than a `NULL` which requires `IS NULL` handling.

### Skill matching: regex `\b` word boundaries, case-insensitive, compiled at import
Each entry in `SKILL_MAP` compiles its patterns into a single `re.Pattern`
with `re.IGNORECASE` at module load time (`_COMPILED`). Advantages:
- Compilation cost paid once, not per record.
- `\b` prevents substring false-positives (e.g. "Scala" matching inside
  "Rescala" or "R" matching every word containing the letter).
- Aliases (e.g. `GCP` → `Google Cloud Platform`) are handled by listing
  multiple patterns under one canonical key; the canonical name is what goes
  into the `skills` array.
No fuzzy matching was used — the false-positive rate on job descriptions
outweighs the small recall gain from approximate matching.

### Skill deduplication: dict key insertion order, not set
`extract_skills` accumulates matches in a `dict[str, None]` rather than a
`set`. Both deduplicate, but `dict` preserves the SKILL_MAP iteration order,
giving a stable, predictable output order in the `skills` array. This makes
snapshot diffs readable and tests deterministic without requiring a sort.

### `skills` initialized as `[]` in normalizer, filled separately
The normalizer sets `skills: []` and does not call `extract_skills`. The
two steps are intentionally decoupled: the skill dictionary can be expanded
and re-run over stored normalized records without re-fetching or re-parsing
raw data. The caller (pipeline or loader) is responsible for wiring the two
steps together.

### `language` defaults to `"unknown"`, never raises
`_detect_language` catches `LangDetectException` and returns `"unknown"`
rather than propagating. Short descriptions (< ~20 chars), empty strings, and
purely numeric text all fail detection; silently returning `"unknown"` keeps
the record usable. `NULL` was avoided for the same reason as role_category —
string comparisons are simpler in SQL aggregations.

### Enum fields return `"UNKNOWN"`, not `None`, on missing data
`_map_work_model` and `_map_employment_type` return the string `"UNKNOWN"`
when the source field is absent or unrecognised. This keeps `work_model` and
`employment_type` non-null in every record, which simplifies GROUP BY and
filter queries in the dashboard layer.
