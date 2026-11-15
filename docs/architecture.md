# Architecture

## Components

```
src/hk_criminal_law_mcp/
├── config.py              environment, endpoints, disclaimer
├── db.py                  SQLite schema, connection, stats
├── legislation_xml.py     HKeL XML parser and text renderer
├── ingest_legislation.py  downloader and indexer
├── citations.py           Cap./section and neutral-citation parsing
├── search.py              legislation search, get-section, verification
├── hklii.py               judgment/search/note-up client + cache
├── server.py              MCP tools (FastMCP, stdio)
└── cli.py                 hk-law command line
```

The MCP server is a thin layer over SQLite and the HKLII client. It has no
server-side state beyond the SQLite file and the local cache.

## Data flow

### Legislation

1. `download` fetches the official current-version ZIPs from DATA.GOV.HK.
2. `ingest` opens each ZIP, parses every XML document with
   `legislation_xml.parse_document`, and writes documents, sections, and FTS
   rows in one transaction per archive.
3. `search` and `get_section` read from SQLite. No network is required.

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
| `legislation_docs` | one row per Cap./instrument per language |
| `legislation_sections` | citable sections/schedules with part/division context |
| `legislation_fts_en` | FTS5 `porter unicode61` index |
| `legislation_fts_zh` | FTS5 `trigram` index |
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

- The default database path is `HK_LAW_DB` or
  `~/.local/share/hk-criminal-law-mcp/hk_law.db`. The project launcher sets it
  to `data/hk_law.db`.
- WAL mode is enabled. Back up the `.db` file after ingest if you want a
  reproducible corpus snapshot.
- Re-running `ingest` is idempotent for a given document/language: it deletes
  and re-inserts that document's sections and FTS rows.
- The downloaded archives and database are git-ignored and are not part of the
  source distribution.
