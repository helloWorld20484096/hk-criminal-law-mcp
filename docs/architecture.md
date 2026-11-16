# Architecture

How HKeL XML becomes a local SQLite corpus, and how the MCP server reads it.
Read this when you are changing the parser, schema, ingestion, retrieval, or
MCP server.

[Documentation index](README.md) · On this page:
[Components](#components) · [Data flow](#data-flow) ·
[SQLite schema](#sqlite-schema) · [Why local-first](#why-local-first) ·
[Operational notes](#operational-notes)

## Components

All modules live under `src/hk_criminal_law_mcp/`.

- **`config.py`** — Environment, endpoints, disclaimer.
- **`db.py`** — SQLite schema, connection, stats.
- **`legislation_xml.py`** — HKeL XML parser and text renderer.
- **`ingest_legislation.py`** — Downloader and current/historical indexers.
- **`citations.py`** — Cap./section and neutral-citation parsing/extraction.
- **`search.py`** — Legislation search, ranges, history, verification.
- **`hklii.py`** — Judgment/search/note-up client and cache; local-only guard.
- **`sync.py`** — Incremental legislation sync, authorised judgment import,
  permission-gated citation sync, and sync status.
- **`research.py`** — Doctrine/sentencing/authority/citation-graph packs.
- **`server.py`** — MCP tools (FastMCP/MCPServer, stdio).
- **`cli.py`** — `hk-law` command line.

The MCP server is a thin layer over SQLite and the HKLII client. It has no
server-side state beyond the SQLite file and the local cache.

## Data flow

### Legislation

1. `download --dataset current` fetches the official current-version ZIPs from
   DATA.GOV.HK. `--dataset past` fetches the Past Version archives;
   `--dataset both` fetches both.
2. `ingest` auto-detects current vs past archives from their filenames and
   routes them to the current or historical indexer. Each XML document is
   parsed with `legislation_xml.parse_document`.
3. Current versions go to `legislation_docs` / `legislation_sections` and the
   FTS indexes. Historical versions go to `legislation_history_docs` /
   `legislation_history_sections`, keyed by `version_date`; they are queried by
   date, not full-text indexed.
4. `search`, `get_section`, `get_section_range`, and `statute_history` read from
   SQLite. No network is required.

The parser:

- reads the HKL M 1.0 namespace;
- extracts `docNumber`, `docType`, `dc:date`, `dc:language`, long title and
  short title;
- skips repealed sections/schedules;
- indexes top-level sections, schedules, and nested `role="rule"` sections
  under High Court Orders (recording the Order as part context);
- strips amendment `sourceNote` elements from the operative text and stores a
  separate `source_note`;
- makes storage keys unique with `temporalId` where section numbers repeat
  across Parts/Orders.

### Judgments

The MCP is **live-first for case search/read**: `search_cases`, `get_case`,
`get_case_paragraphs`, `verify_citation`, `note_up`, and `case_graph` default to
live HKLII when `HK_LAW_LOCAL_ONLY=0` (the launcher default). Set
`HK_LAW_LOCAL_ONLY=1` for a strictly local MCP. Live search failures fall back
to local results with `live_error`.

Judgments enter the local corpus in one of two ways:

1. **Authorised import** — `hk-law import-cases` reads JSONL/CSV/JSON, a SQLite
   `cases` table, or an HTML directory with sidecars. It parses or accepts
   numbered paragraphs and calls `hklii.store_case` in a batch transaction.
2. **Permission-gated citation sync** — `hk-law sync --citations ...` requires
   `HK_LAW_CASE_PERMISSION_REF` and an explicit citation list. It calls
   `api/getjudgment` for each listed citation only. There is no discovery
   crawler; LRS `robots.txt` is `Disallow: /` and HKLII's is `Disallow: /api`.

When live retrieval is permitted, `get_judgment` parses numbered paragraphs
from `<a class="para">` anchors and caches the judgment, paragraphs,
cited-case list, and raw HTML in SQLite. `note_up` caches the payload.
HKLII requests are serialized by a process-wide rate limiter (default 1.5 s
between requests) with retries and backoff.

Search-result caching uses `case_search_cache` with a default 6-hour TTL
(`HK_LAW_CACHE_TTL`). Local judgment text is retained until re-imported or
explicitly refreshed.

### Local sync

1. `hk-law sync --dataset current` issues a HEAD/conditional GET for each
   DATA.GOV.HK archive. Unchanged archives are skipped.
2. Changed ZIPs are downloaded to `.part` and atomically replaced.
3. The XML indexer compares each document's SHA-256 with the stored checksum
   and skips unchanged documents (`skip_unchanged=True`).
4. Changed documents are upserted with their sections and FTS rows.
5. The run is recorded in `sync_runs`; archive validators are stored in `meta`.
6. `hk-law import-cases` or the permission-gated citation sync updates the
   local judgment corpus and `case_sources`.

## SQLite schema

| Table | Purpose |
|---|---|
| `legislation_docs` | one row per Cap./instrument per language (current) |
| `legislation_sections` | citable current sections/schedules with part/division context |
| `legislation_history_docs` | one row per Cap./instrument/language/version date |
| `legislation_history_sections` | historical section text, indexed by Cap/section/date |
| `legislation_fts_en` | FTS5 `porter unicode61` index (current) |
| `legislation_fts_zh` | FTS5 `trigram` index (current) |
| `cases` | cached judgments and metadata |
| `case_paragraphs` | numbered paragraphs |
| `cases_fts_en` / `cases_fts_zh` | judgment full-text indexes |
| `case_noteups` | note-up payload cache |
| `case_search_cache` | search-response cache |
| `sync_runs` | one row per legislation/case sync or import, with JSON stats and error |
| `case_sources` | provenance for imported/authorised judgment sources |
| `meta` | schema/sync metadata, archive ETag/Last-Modified |

FTS5 auxiliary functions (`snippet`, `bm25`) require the real table name, not
a table alias. This is why the queries spell out `legislation_fts_en` etc.

## Why local-first

- **Cost:** no per-query legal-database fee; no repeated page fetches.
- **Reliability:** the corpus is a stable local artifact; a source outage does
  not break retrieval.
- **Auditability:** every section has a source file, checksum, version date,
  and official URL.
- **Token efficiency:** search returns snippets; full text is fetched only when
  needed, and judgments can be requested paragraph-by-paragraph.

## Operational notes

- The database path comes from `HK_LAW_DB`, defaulting to
  `~/.local/share/hk-criminal-law-mcp/hk_law.db`. `scripts/run_mcp.sh` sets it
  to `data/hk_law.db`; a bare `hk-law` invocation with no `HK_LAW_DB` uses the
  home-directory default.
- WAL mode is enabled. Back up the `.db` file after ingest if you want a
  reproducible corpus snapshot.
- Re-running `ingest` is idempotent for a given document/language: it deletes
  and re-inserts that document's sections and FTS rows.
- The downloaded archives and database are git-ignored and are not part of the
  source distribution.
- `scripts/run_mcp.sh` defaults `HK_LAW_LOCAL_ONLY=0` (live HKLII case
  queries); set it to 1 for a local-only MCP. `scripts/sync.sh` performs the
  explicit legislation update.
- `scripts/install_sync_timer.sh` installs `hk-law-sync.service` and
  `hk-law-sync.timer` under `~/.config/systemd/user/`. Permission-gated case
  variables live in `~/.config/hk-law-sync.env` (mode 0600), not in the unit.

## Related

[Coverage](coverage.md) · [Reliability model](reliability.md) ·
[Data sources and licensing](data-sources-and-licensing.md) ·
[Documentation index](README.md)
