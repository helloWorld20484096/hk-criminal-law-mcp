# HK Criminal Law MCP

A local-first, open-source research stack for **Hong Kong criminal law and
defence**. It indexes the official current-version Hong Kong legislation XML
(from DATA.GOV.HK) into SQLite, retrieves judgments by neutral citation from
HKLII on demand, and exposes the corpus to Claude Code (or any MCP client)
through a small set of citation-aware tools.

> **Not legal advice.** This is a research aid. Every provision and judgment
> must be checked against the official source before it is relied on. Hong Kong
> criminal law changes; check commencement, amendments and subsequent judicial
> treatment.

## Why this exists

Generic legal chatbots hallucinate citations and cannot tell you whether a
provision is current. This project takes the opposite approach:

- **Primary sources, locally indexed.** Legislation comes from the Department
  of Justice's official e-Legislation XML bulk data, not a scraped secondary
  site.
- **Verification is a tool, not a promise.** `verify_citation` checks a Cap./
  section or neutral citation against the corpus/HKLII before it is used.
- **Judgments are fetched and cached, not bundled.** The repository never
  redistributes judgment text; the user's local cache does.
- **Paragraph-level retrieval.** `get_case` returns numbered paragraphs, so a
  submission can cite `[2021] HKCFA 1 at [3]` rather than a vague page.
- **Bilingual by design.** English and Traditional Chinese legislation share
  the same citation structure.

## Status

This is a working MVP, not a complete citator.

| Layer | Status |
|---|---|
| English current legislation (Caps. 1–300, 301–600, 601+, instruments) | Indexed locally |
| Traditional Chinese current legislation | Indexed locally |
| Historical legislation (DATA.GOV.HK Past Version archives) | Indexed locally when downloaded; point-in-time `statute_history` |
| Judgments | Fetched on demand from HKLII and cached; local full-text search grows with use |
| Citation verification | Single citation + batch passage verification (`verify_citations`) |
| Research packs | Doctrine leads, sentencing context, authority ranking, case citation graph |
| Defence workflows | 12 skills under `skills/` |

The **current** corpus is always available. Point-in-time text requires the
official Past Version archives; if they have not been ingested,
`statute_history` returns the current text with an explicit warning rather than
pretending it is historical.

## Architecture

```
DATA.GOV.HK (DoJ e-Legislation XML: current + past versions)
        │  download + parse
        ▼
   SQLite (data/hk_law.db)
   ├── legislation_docs / legislation_sections
   ├── legislation_history_docs / legislation_history_sections
   ├── legislation_fts_en / legislation_fts_zh
   ├── cases / case_paragraphs
   └── cases_fts_en / cases_fts_zh
        ▲
        │  MCP tools (stdio)
        │
   hk-criminal-law MCP  ──►  Claude Code / any MCP client
        │
        └── HKLII JSON endpoints (judgments, search, note-up) ──► local cache
```

The MCP server has no cloud dependency. Network access is only needed to
download legislation or fetch a judgment that is not already cached.

## Quick start

Requires Python 3.11+ and network access to DATA.GOV.HK for the initial
download.

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'

# Official current-version legislation (English + Traditional Chinese).
# This downloads roughly 1.3 GB of ZIPs and indexes ~120k sections.
.venv/bin/hk-law download --data-dir data/raw --dataset current
.venv/bin/hk-law ingest --data-dir data/raw --dataset current --language en
.venv/bin/hk-law ingest --data-dir data/raw --dataset current --language zh-Hant

# Optional: official past versions for point-in-time statute_history.
# English past archives are roughly 2.1 GB.
.venv/bin/hk-law download --data-dir data/raw --dataset past --languages en
.venv/bin/hk-law ingest --data-dir data/raw --dataset past --language en

.venv/bin/hk-law stats
```

If you already have archives, point `ingest` at them:

```bash
.venv/bin/hk-law ingest --zip data/raw/hkel_c_leg_cap_1_cap_300_en.zip --language en
```

### Prebuilt corpus (release assets)

The [v0.1.0 data release](https://github.com/helloWorld20484096/hk-criminal-law-mcp/releases/tag/v0.1.0)
contains a cleaned SQLite corpus (legislation only, no judgment text) and the
eight official DATA.GOV.HK archives:

```bash
curl -LO https://github.com/helloWorld20484096/hk-criminal-law-mcp/releases/download/v0.1.0/hk_law_public.db.gz
curl -LO https://github.com/helloWorld20484096/hk-criminal-law-mcp/releases/download/v0.1.0/SHA256SUMS
sha256sum -c SHA256SUMS --ignore-missing
gunzip hk_law_public.db.gz
export HK_LAW_DB="$PWD/hk_law_public.db"
.venv/bin/hk-law stats
```

The release database is built from the current-version e-Legislation XML as at
2026-11-15. It contains no judgments, consistent with the source-data terms
described in `docs/data-sources-and-licensing.md`. It is current-version only;
for point-in-time text, download the Past Version archives and ingest them into
the same database:

```bash
.venv/bin/hk-law download --data-dir data/raw --dataset past --languages en
.venv/bin/hk-law ingest --data-dir data/raw --dataset past --language en
```

### Use with Claude Code

The repository ships a project-scoped `.mcp.json` and `scripts/run_mcp.sh`:

```json
{
  "mcpServers": {
    "hk-criminal-law-local": {
      "command": "bash",
      "args": ["scripts/run_mcp.sh"]
    }
  }
}
```

Open the project in Claude Code and approve `hk-criminal-law-local`. The 12
skills under `skills/` are written for this server; `scripts/link_skills.sh`
links them into `.claude/skills/` for project-scoped discovery.

For **user-scope** availability in every project:

```bash
bash scripts/install_global.sh
```

This creates a dedicated venv under `~/.local/share/hk-criminal-law-mcp`,
installs the package there, links the local corpus, copies all 12 skills to
`~/.claude/skills/hk-criminal-law` as one skills-dir plugin, and adds the MCP
server at user scope under the name `hk-criminal-law`.

The repository's project-scoped server is named `hk-criminal-law-local` so it
does not collide with the global `hk-criminal-law` registration. Both expose
the same tools.

Manual equivalent:

```bash
claude mcp add --scope user hk-criminal-law \
  -e HK_LAW_DB="$PWD/data/hk_law.db" \
  -- "$PWD/.venv/bin/python" -m hk_criminal_law_mcp.server
```

The MCP server is now global; the skills remain project-scoped unless you copy
or link them into `~/.claude/skills/`.

### Use from the CLI

```bash
.venv/bin/hk-law get-section 221 9J
.venv/bin/hk-law get-section-range 221 9A 9J
.venv/bin/hk-law search-legislation "bail conditions" --cap 221
.venv/bin/hk-law statute-history 221 9J --as-of 2020-01-01
.venv/bin/hk-law search-cases "bail conditions" --court HKCFA
.venv/bin/hk-law get-case "[2021] HKCFA 1" --paragraphs 1 3
.venv/bin/hk-law verify "Cap. 221 s.9J"
.venv/bin/hk-law verify-text "Cap. 221 s.9J; [2021] HKCFA 1"
.venv/bin/hk-law doctrine "bail conditions"
.venv/bin/hk-law sentencing 210 9
.venv/bin/hk-law authority "bail conditions" --live
.venv/bin/hk-law case-graph "[2021] HKCFA 1"
```

## MCP tools

| Tool | Purpose |
|---|---|
| `search_legislation` | Full-text search over the indexed HKeL corpus (EN/ZH) |
| `get_section` | One section/schedule, with heading, part, version date, URL |
| `get_section_range` | All sections in a range, e.g. Cap. 221 ss. 9A–9J |
| `statute_history` | Point-in-time provision text from the Past Version archives |
| `list_section_versions` | Every historical version date available for a section |
| `list_ordinances` | Browse indexed ordinances/regulations |
| `search_cases` | Local judgment cache first, then HKLII's public search |
| `get_case` | Fetch/cache a judgment by neutral citation; truncate safely |
| `get_case_paragraphs` | Return specific numbered paragraphs |
| `note_up` | HKLII note-up data (research aid, not a citator of record) |
| `verify_citation` | Verify a legislation or case citation |
| `verify_citations` | Extract and verify every citation in a passage |
| `doctrine_research` | Legislation + ranked case leads for an issue |
| `sentencing_research` | Penalty text + sentencing case leads (not a tariff) |
| `authority_ranking` | Rank case results by court level and cached note-up |
| `case_graph` | Outgoing and incoming citations for a case |
| `corpus_status` | Counts, coverage, and last ingest/fetch times |

Every response carries provenance (`source_url`, `version_date`, language) and
a disclaimer. Search responses say explicitly that a snippet is not the
provision.

## Defence skills

| Skill | Use |
|---|---|
| `hk-criminal-intake` | First response, arrest/police station, deadlines |
| `hk-bail-application` | Bail, review, sureties, conditions |
| `hk-charge-analysis` | Elements grid, defences, venue/penalty |
| `hk-case-file-review` | Evidence matrix, disclosure, inconsistencies |
| `hk-defense-strategy` | Plea vs trial, charge negotiation, decision memo |
| `hk-sentencing-mitigation` | Guideline authorities, mitigation, totality |
| `hk-trial-defense` | Trial plan, cross-examination, closing |
| `hk-appeal` | Routes, leave, grounds, fresh evidence, bail pending appeal |
| `hk-legal-research` | Verification-first research protocol |
| `hk-professional-ethics` | Conflicts, confidentiality, candour, media |
| `hk-juvenile-defense` | Age, safeguards, forum, sentencing |
| `hk-mental-health-criminal` | Fitness, psychiatric evidence, hospital orders |

Each skill instructs the model to retrieve the current provision and the
paragraph it relies on. None of them authorises citation from memory.

## Data sources and licensing

- **Legislation:** Hong Kong e-Legislation current-version XML, published by
  the Department of Justice on [DATA.GOV.HK](https://data.gov.hk/en-data/dataset/hk-doj-hkel-legislation-current).
  Free reuse with attribution under the DATA.GOV.HK terms. See
  `docs/data-sources-and-licensing.md`.
- **Judgments:** HKLII's public judgment/search endpoints are used on demand.
  The Judiciary's Legal Reference System permits downloading for private study
  and research; commercial reuse requires permission. This project does not
  redistribute judgment text or a prebuilt judgment database.
- **No warranty:** the HKLII JSON endpoints are undocumented and may change.

Code is Apache-2.0. Skills and documentation are CC BY 4.0. Downloaded data is
not covered by those licenses.

## Reliability model

1. **Local corpus is authoritative for retrieval, not for legal conclusions.**
2. **Every citation is verified** with `verify_citation` or retrieved in full;
   `verify_citations` checks a whole passage at once.
3. **Judgments are cited by paragraph**, not by page or summary.
4. **Currency is explicit:** current or historical legislation version date;
   judgment fetch date; note-up warning.
5. **Point-in-time text is never inferred.** If the Past Version archive is not
   ingested, `statute_history` returns the current text with an explicit warning.
6. **Unverified material is labelled** `[UNVERIFIED]` and cannot be presented
   as authority.

See `docs/reliability.md` for the failure modes this model is designed to catch.

## Limitations

- Current-version legislation is always available. Point-in-time text requires
  the official Past Version archives to be downloaded and ingested; coverage
  depends on which ranges/languages were ingested. Commencement timelines are
  not reconstructed.
- Case law coverage is demand-driven. Bulk judgment import is a roadmap item.
- HKLII endpoints are unofficial; a change or block is possible.
- Note-up and authority ranking are not a citator of record. Check the
  Judiciary's LRS and the judgment itself.
- `sentencing_research` extracts penalty language and case leads; it is **not**
  a sentencing tariff or a structured sentencing database.
- Chinese search uses a trigram index; very short queries fall back to LIKE.
- The skills are practice scaffolds, not a substitute for supervised legal
  work.

## Roadmap

- Bulk judgment import + incremental refresh.
- Citator-style treatment graph (cited/citing, positive/negative).
- Historical Chinese point-in-time coverage and commencement timelines.
- PDF/DOCX export with citation tables.
- Offence-specific sentencing datasets.
- Evaluation suite with gold-standard questions and citation checks.

## Contributing

Good contributions: parser fixes, additional official data sources, offence/
procedure skills with verified citations, tests for known hard cases, and
reliability improvements. Please do not add unverified legal assertions or
copied judgment text.

## License

Apache-2.0 for code; CC BY 4.0 for skills and docs. See `LICENSE` and
`LICENSE-SKILLS`.
