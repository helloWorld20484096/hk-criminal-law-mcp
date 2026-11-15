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
- **`hklii.py`** — Judgment/search/note-up client and cache.
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

1. `search_cases` queries the local FTS index first.
2. Unless `live=False`, it also calls HKLII's `api/simplesearch`.
3. `get_case` calls `api/getjudgment`, parses numbered paragraphs from
   `<a class="para">` anchors, and caches the judgment, paragraphs, cited-case
   list, and raw HTML in SQLite.
4. `note_up` calls `api/getcasenoteup` and caches the payload.
5. HKLII requests are serialized by a process-wide rate limiter (default
   1.5 s between requests) with retries and backoff.

Search-result caching uses `case_search_cache` with a default 6-hour TTL
(`HK_LAW_CACHE_TTL`). Judgment text is cached indefinitely until refreshed with
`force=True`.

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
| `meta` | reserved for future schema/version metadata |

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

## Related

[Coverage](coverage.md) · [Reliability model](reliability.md) ·
[Data sources and licensing](data-sources-and-licensing.md) ·
[Documentation index](README.md)
