# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

A local-first research stack for Hong Kong criminal law and defence. The Python package `hk-criminal-law-mcp` provides two interfaces over one SQLite corpus:

- an MCP server (`hk_criminal_law_mcp.server`, stdio) exposing citation-aware research tools to Claude Code or any MCP client;
- a CLI (`hk-law`) with the same functionality.

Legislation is indexed locally from official DATA.GOV.HK e-Legislation XML (HKL M 1.0). Case search/read defaults to live HKLII query-time access; set `HK_LAW_LOCAL_ONLY=1` for a strictly local MCP. Judgments can also be imported from an authorised corpus or fetched through a permission-gated citation list. There is no bulk crawler. The project is a retrieval aid, not a citator of record and not legal advice; every provision and judgment must be checked against the official source.

## Commands

Use the project venv (`.venv/`, Python 3.11+; CI uses 3.12).

```bash
make setup                 # python3 -m venv .venv && pip install -e '.[dev]'
make test                  # .venv/bin/pytest -q
.venv/bin/pytest tests/test_search.py::test_get_section -q   # single test
make serve                 # run the MCP server on stdio
make skills                # link skills/*/ into .claude/skills/
```

Corpus build (network required; outputs are git-ignored):

```bash
# Current legislation, English + Traditional Chinese (~1.3 GB of ZIPs)
.venv/bin/hk-law download --data-dir data/raw --dataset current
.venv/bin/hk-law ingest --data-dir data/raw --dataset current --language en
.venv/bin/hk-law ingest --data-dir data/raw --dataset current --language zh-Hant

# Optional historical versions (~2.1 GB, English)
.venv/bin/hk-law download --data-dir data/raw --dataset past --languages en
.venv/bin/hk-law ingest --data-dir data/raw --dataset past --language en

.venv/bin/hk-law stats
```

CLI examples: `hk-law get-section 221 9J`, `search-legislation`, `statute-history 221 9J --as-of 2020-01-01`, `search-cases`, `get-case "[2021] HKCFA 1" --paragraphs 1 3`, `verify`, `verify-text`, `doctrine`, `sentencing`, `authority`, `case-graph`, `stats`.

Installation/multi-project use:

```bash
bash scripts/link_skills.sh   # project-scoped skill discovery via .claude/skills symlinks
bash scripts/install_global.sh  # user-scope MCP server + skills under ~/.claude/skills/hk-criminal-law
```

The project-scoped MCP server in `.mcp.json` is named `hk-criminal-law-local`; the global one is `hk-criminal-law`. `scripts/run_mcp.sh` sets `HK_LAW_DB` to `data/hk_law.db` and `HK_LAW_DATA_DIR` to `data/raw`.

Tests use a temporary SQLite database via the `conn` fixture (`tests/conftest.py`) and are offline — no corpus or network is required. Tests import from `src/` via `sys.path` insertion, so an editable install is not strictly needed to run them.

## Architecture

```text
DATA.GOV.HK HKeL XML ZIPs
        │ download + parse (ingest_legislation.py, legislation_xml.py)
        ▼
data/hk_law.db  (SQLite, WAL)
  legislation_docs/sections + FTS (current)
  legislation_history_docs/sections (past versions, date-keyed)
  cases/case_paragraphs + FTS, case_noteups, case_search_cache
  sync_runs (audit), case_sources (judgment provenance)
        ▲
        ├── search.py     legislation retrieval, ranges, history, verification
        ├── hklii.py      judgment/search/note-up client + local cache + live/local guard
        ├── sync.py       legislation sync, authorised case import, permission-gated citation sync
        ├── research.py   doctrine/sentencing/authority/case-graph packs
        ├── server.py     MCP tool wrappers (thin: open conn, call module, close)
        └── cli.py        hk-law argparse front end
```

- `config.py` — env configuration and the standard disclaimer. Key vars: `HK_LAW_DB`, `HK_LAW_DATA_DIR`, `HK_LAW_HOME`, `HK_LAW_REQUEST_INTERVAL`, endpoint overrides `HK_LAW_HKLII_BASE` / `HK_LAW_ELEGISLATION_BASE` / `HK_LAW_DATA_GOV_BASE`, plus `HK_LAW_LOCAL_ONLY` (launcher default `0`; set `1` for local-only) and the permission-gated case vars `HK_LAW_CASE_PERMISSION_REF` / `HK_LAW_CASE_CITATIONS` / `HK_LAW_CASE_IMPORT_DIR`.
- `db.py` — owns the schema (`SCHEMA`), `connect()` (creates schema, enables WAL/foreign keys, normalises legacy version dates), and `stats()`.
- `legislation_xml.py` — HKL M 1.0 parser. Skips repealed sections/schedules; separates amendment `sourceNote` from operative text; indexes schedules and nested `role="rule"` sections under High Court Orders (the Order becomes part context); deduplicates storage keys with `temporalId`/`~N` suffixes when numbering repeats.
- `ingest_legislation.py` — download map for current (`hkel_c_*`) and past (`hkel_p_*`) archives; auto-detects history archives; upserts per document/language and re-inserts that document's sections and FTS rows (idempotent). `skip_unchanged=True` compares each XML's checksum with the stored document checksum for incremental sync.
- `search.py` — current-corpus FTS (`legislation_fts_en` porter, `legislation_fts_zh` trigram), section/range lookup, historical version listing, and citation verification.
- `hklii.py` — local judgment corpus first, then live HKLII by default when `HK_LAW_LOCAL_ONLY=0` (the launcher default). Set `HK_LAW_LOCAL_ONLY=1` for local-only. The permission-gated citation list lives in `sync.py`; there is no discovery crawler. Search responses cached with `HK_LAW_CACHE_TTL` (default 6 h); imported judgment text retained until re-imported. A process-wide rate limiter enforces 1.5 s between requests with retries/backoff; a live search failure falls back to local results.
- `HK_LAW_LOCAL_ONLY=0` is the launcher default and makes the server tool defaults live (`live_case_default()` is the inverse of `local_only()`); this is query-time HKLII coverage, not a local corpus, and remains subject to HKLII's terms. Bulk sync still requires `HK_LAW_CASE_PERMISSION_REF`.
- `sync.py` — `sync_legislation` (DATA.GOV.HK incremental), `import_cases` (JSONL/CSV/JSON/SQLite/HTML), permission-gated `sync_cases`, and `sync_status`. Records `sync_runs` and `case_sources`. It must refuse automated case access without `HK_LAW_CASE_PERMISSION_REF`.
- `research.py` — composes the above into discovery packs; court levels are ranked by neutral-citation code, not by citator treatment.
- `server.py` — FastMCP/MCPServer tool definitions; each tool opens and closes its own connection and attaches `DISCLAIMER`. It imports both MCP SDK paths (`mcp.server.fastmcp.FastMCP` for 1.x, `mcp.server.mcpserver.MCPServer` for 2.x) — keep both working. `cli.py` mirrors every tool.
- `citations.py` — normalises `Cap. 221 s.9J` / `Cap. 221 Sch. 3` and `[2021] HKCFA 1`; extracts and deduplicates citations from free text.

## Invariants to preserve

- **Never invent a citation or historical text.** `verify_citation` returns `verified` / `not_found` / `unverified` / `mismatch` / `unrecognised`; `verify_citations` applies this to a whole passage. Keep those semantics.
- **`statute_history` must not pass current law off as historical law.** If the requested date is on/after the current version date, or no past archive was ingested, it returns current text with `historical: false` and a warning. Preserve the `historical` flag, warnings, and `next_version_date`.
- FTS5 auxiliary functions (`snippet`, `bm25`) require the literal table name, not an alias — queries spell out `legislation_fts_en`, `legislation_fts_zh`, `cases_fts_en`, `cases_fts_zh`. Chinese queries under 3 characters fall back to `LIKE`.
- Judgments and downloaded archives are **not redistributed**. Do not add bundled judgment text, a prebuilt judgment database, or a crawler. The supported paths are authorised import and the permission-gated citation list; automated HKLII/LRS access requires `HK_LAW_CASE_PERMISSION_REF`. Keep HKLII rate limiting intact; its JSON endpoints are undocumented and may change.
- Downloaded data (`data/`) and `.db` files are git-ignored. The local corpus here is roughly 2.4 GB; never commit it.
- Every result should carry provenance (`source_url`, `version_date`, language, fetch/ingest date) and the disclaimer. Search snippets are explicitly not the provision.
- Version number lives in three places: `pyproject.toml`, `src/hk_criminal_law_mcp/config.py` (`VERSION`), and `.claude-plugin/plugin.json`. Bump all three together.

## Skills

Twelve `SKILL.md` documents under `skills/` implement the defence workflows. `.claude/skills/<name>` contains tracked symlinks to those directories; after adding/renaming a skill, re-run `bash scripts/link_skills.sh` so the symlink is created and committed.

When editing skills: the frontmatter `name` must equal the folder name, `legal_frame` stays `hk`, and no legal proposition may be added without a retrievable Cap./section or neutral citation with paragraph. Skills assume the `hk-criminal-law` MCP server is available.

## Licensing and docs

Code is Apache-2.0; `skills/` and `docs/` are CC BY 4.0; downloaded data is governed by the source terms (DATA.GOV.HK, Hong Kong Judiciary, HKLII). See [docs/data-sources-and-licensing.md](docs/data-sources-and-licensing.md).

Deeper context: [docs/README.md](docs/README.md) (documentation index), [docs/architecture.md](docs/architecture.md) (schema and data flow), [docs/coverage.md](docs/coverage.md) (corpus counts and historical coverage), [docs/reliability.md](docs/reliability.md) (failure modes, verification controls, audit procedure), [README.md](README.md) (full tool/skill tables and limitations).
