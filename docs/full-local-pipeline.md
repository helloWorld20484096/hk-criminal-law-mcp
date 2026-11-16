# Fully local pipeline

How to keep the corpus current without making the MCP depend on a live legal
database. Read this before configuring the timer or importing judgments.

> [!IMPORTANT]
> This public repository ships **no judgment text** and claims **no permission**
> from the Judiciary or HKLII. If you do not have written permission, use
> `import-cases` only. The HKLII adapter refuses to run without
> `HK_LAW_CASE_PERMISSION_REF` and an explicit citation list; enabling it
> without permission is not authorised.

[Documentation index](README.md) · On this page:
[What is local](#what-is-local) · [Legislation sync](#legislation-sync) ·
[Judgment import](#judgment-import) · [Permission-gated HKLII sync](#permission-gated-hklii-sync) ·
[MCP local-only mode](#mcp-local-only-mode) · [Scheduler](#scheduler) ·
[State and audit](#state-and-audit) · [Known limits](#known-limits)

## What is local

| Layer | Local? | Update path |
|---|---|---|
| Current legislation (EN + ZH) | Yes | DATA.GOV.HK current archives; `hk-law sync` checks ETag/Last-Modified and ingests only changed documents |
| Historical legislation | Yes, when the Past Version archives are downloaded | `hk-law sync --dataset past` or `--dataset both` |
| Legislation FTS (EN/ZH) | Yes | Rebuilt incrementally per changed document |
| Judgment text | Yes, once imported or fetched under permission | `hk-law import-cases` from an authorised corpus, or the permission-gated HKLII citation sync |
| Judgment FTS (EN/ZH) | Yes | Populated by the import/sync |
| Note-up | Cached locally; live only with permission | `hk-law sync --citations ...` with a permission reference |

The MCP server never needs a live legal database to answer a local query. It
reads SQLite. Network access is limited to an explicit sync run.

## Legislation sync

```bash
export HK_LAW_DB="$PWD/data/hk_law.db"
export HK_LAW_DATA_DIR="$PWD/data/raw"

# Check the official archives, download only what changed, ingest only
# documents whose XML checksum changed.
.venv/bin/hk-law sync --dataset current

# Include the Past Version archives (large; slower).
.venv/bin/hk-law sync --dataset both

# Force a full re-download and re-ingest for a known-bad archive.
.venv/bin/hk-law sync --dataset current --force
```

What `sync` does:

1. `HEAD`/conditional `GET` each archive with `If-None-Match` /
   `If-Modified-Since`. If the server supplies no validator, it compares
   `Content-Length`.
2. Downloads a changed ZIP to a `.part` file, then atomically replaces the old
   archive.
3. Calls the existing XML indexer with `skip_unchanged=True`: each document's
   SHA-256 is compared with the stored `legislation_docs.checksum`; unchanged
   documents are skipped.
4. Updates the EN or ZH FTS index for changed sections only.
5. Records the run in `sync_runs` and the archive validators in `meta`.

The archive URLs and ranges are the official DATA.GOV.HK e-Legislation bulk
data mapping already used by `download`. Reuse is subject to the DATA.GOV.HK
terms; attribution is required and the database is not redistributed.

## Judgment import

The importer is the supported path for a corpus you are licensed to use. It is
idempotent: re-importing the same neutral citation updates the case, its
paragraphs, and its FTS row in place.

```bash
.venv/bin/hk-law import-cases \
  --path /path/to/authorised-corpus.jsonl \
  --format jsonl \
  --source "licensed-provider-2026" \
  --license "Private research; no redistribution"
```

Or point `sync` at a drop folder that another authorised process refreshes:

```bash
export HK_LAW_CASE_IMPORT_DIR=/path/to/authorised-export
export HK_LAW_CASE_LICENSE="Private research; no redistribution"
.venv/bin/hk-law sync --dataset current
```

### JSONL

One JSON object per line. The only required field is `citation`; `paragraphs`
is strongly preferred so paragraph-level retrieval works.

```json
{"citation":"[2021] HKCFA 1","title":"HKSAR v Example","court":"Court of Final Appeal","court_code":"HKCFA","year":2021,"number":"1","judgment_date":"2021-01-12","language":"en","source_url":"https://example.invalid/judgment","paragraphs":[{"number":"1","text":"The appeal is allowed."},{"number":"2","text":"Bail conditions must be justified."}],"cited_cases":[]}
```

If `paragraphs` is absent, the importer splits numbered lines; if `text` is
present without numbering, it splits on blank lines and numbers the blocks.
If `html` is present, it uses the existing HKLII-compatible paragraph parser.

### CSV

Header row required:

```text
citation,title,court,court_code,year,number,judgment_date,language,source_url,text
```

### SQLite

A database with a `cases` table and (optionally) `case_paragraphs`:

```text
cases(id, neutral_citation, title, court, court_code, year, num,
      judgment_date, language, source_url, text, ...)
case_paragraphs(case_id, para_no, text)
```

### HTML directory

A folder of `.html` / `.htm` files. The neutral citation is read from a
sibling `.json` sidecar (`{"citation": "[2021] HKCFA 1", ...}`) or from a
filename such as `2021-HKCFA-1.html`. Do not point this at a directory you are
not authorised to ingest.

## Permission-gated HKLII sync

`hk-law sync --citations ...` is a **citation-list fetcher**, not a crawler. It
requires:

| Variable | Purpose |
|---|---|
| `HK_LAW_CASE_PERMISSION_REF` | Written-permission reference (required). The sync refuses to run without it. |
| `HK_LAW_CASE_CITATIONS` | Explicit citation list, one per line. |
| `HK_LAW_CASE_SOURCE` | `hklii` (the only wired HTTP adapter) |
| `HK_LAW_CASE_SOURCE_URL` | The permitted endpoint, recorded in provenance |
| `HK_LAW_CASE_LICENSE` | Your licence/terms note, recorded in `case_sources` |

```bash
export HK_LAW_CASE_PERMISSION_REF="JUD-HKLII-2026-001"
export HK_LAW_CASE_SOURCE="hklii"
export HK_LAW_CASE_SOURCE_URL="https://permitted.example/path"
export HK_LAW_CASE_CITATIONS="/path/to/authorised-citations.txt"
.venv/bin/hk-law sync --dataset current
```

There is no default LRS/HKLII discovery crawler in this build. The reason is
factual, not timidity:

- The Judiciary Legal Reference System publishes `robots.txt` as `Disallow: /`.
- HKLII publishes `robots.txt` as `Disallow: /api`, and its terms prohibit
  automated harvesting/re-supply. Its judgments are HKSAR Government copyright,
  reproduced by permission for private use.
- There is no official public bulk-download API or data.gov.hk judgment-text
  dataset.

A Judiciary LRS adapter needs the permitted URL pattern, scope, and rate limit
from the permission letter before it can be wired. Until then, use an
authorised corpus import or a permitted citation list. See the
[permission request template](permission-request-template.md).

## MCP local-only mode

The project launcher exports `HK_LAW_LOCAL_ONLY=1` by default:

```bash
bash scripts/run_mcp.sh   # sets HK_LAW_LOCAL_ONLY=1 unless you override it
```

In local-only mode:

- `search_cases` searches the local FTS index only.
- `get_case` and `get_case_paragraphs` return local text or a structured
  "not in the local corpus" error; they do not contact HKLII.
- `verify_citation` verifies against the local corpus only.
- `note_up` returns cached data only.
- `corpus_status` and `sync_status` report `local_only`, coverage, last runs,
  and whether a permission reference is configured (never the value itself).

Set `HK_LAW_LOCAL_ONLY=0` only after a permitted source is configured. The MCP
tool parameters still default to local (`live=False`, `allow_live=False`), so a
client must opt in explicitly.

## Scheduler

```bash
bash scripts/install_sync_timer.sh
systemctl --user list-timers hk-law-sync.timer
journalctl --user -u hk-law-sync.service -n 100
```

The installer writes:

- `~/.config/systemd/user/hk-law-sync.service`
- `~/.config/systemd/user/hk-law-sync.timer` (`OnCalendar=daily`,
  `Persistent=true`, 30-minute randomized delay)
- `~/.config/hk-law-sync.env` (mode 0600) for permission-gated variables

Run once manually:

```bash
./scripts/sync.sh
```

If `systemctl` is unavailable, the installer prints a cron equivalent.

## State and audit

| Table / key | Meaning |
|---|---|
| `sync_runs` | One row per run: kind, source, start/finish, status, JSON stats, error |
| `case_sources` | Provenance for each imported/authorised source: licence, permission ref, base URL, timestamps, last count |
| `meta.archive.<file>.etag` / `.last-modified` | HTTP validators used to avoid re-downloading unchanged legislation |
| `meta.legislation_current.last_sync` | Last successful legislation check |
| `meta.legislation_past.last_sync` | Last successful historical check |

`hk-law sync-status` and the MCP `sync_status` tool return the same view:
counts by court, paragraph count, source rows, recent runs, import directory,
citation file, and permission-configured boolean.

## Known limits

- Judgment coverage equals what you imported. There is no hidden live fallback
  in local-only mode.
- The HKLII adapter fetches an explicit citation list; it does not discover
  cases. True incremental discovery requires an authorised feed.
- The LRS adapter is not wired; it needs the permitted URL pattern.
- Re-importing a large corpus rewrites FTS rows for each case. That is correct
  but slower than a differential import; the importer is idempotent, not
  delta-aware.
- The database is local and git-ignored. Do not redistribute judgment text.

## Related

[Permission request template](permission-request-template.md) ·
[Architecture](architecture.md) · [Coverage](coverage.md) ·
[Data sources and licensing](data-sources-and-licensing.md) ·
[Reliability model](reliability.md)
