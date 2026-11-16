# Reliability model

How the project catches the predictable ways legal research fails, and what to
do before relying on a citation. Read this when you are drafting a research
note, checking a citation, or changing verification behaviour.

[Documentation index](README.md) · On this page:
[Quick verification path](#quick-verification-path) ·
[Failure modes](#failure-modes) · [Controls](#controls) ·
[Confidence levels](#confidence-levels) · [Audit procedure](#audit-procedure) ·
[Known limitations](#known-limitations)

## Quick verification path

Before relying on a passage:

```bash
# 1. Verify every citation.
.venv/bin/hk-law verify-text \
  "Cap. 221 s.9J; [2021] HKCFA 1"

# 2. Read the provision.
.venv/bin/hk-law get-section 221 9J

# 3. Read the cited paragraph.
.venv/bin/hk-law get-case \
  "[2021] HKCFA 1" --paragraphs 1 2

# 4. Check later treatment
#    (not a citator).
.venv/bin/hk-law note-up "[2021] HKCFA 1"
```

`verify_citations` — run as `hk-law verify-text` — checks the local cache by
default; use `--live` to fetch uncached judgments from HKLII. A verified
citation exists in the corpus, but that does not establish that it supports
the proposition.

## Failure modes

| Failure and example | Control |
|---|---|
| **Hallucinated citation** — "Cap. 221 s.99ZZ" | `verify_citation` / `get_section` returns `not_found` |
| **Wrong section/heading** — citing s.9J for a different bail rule | `get_section` returns the heading and operative text |
| **Stale law** — relying on a repealed or amended provision | current-version corpus + `version_date`; repealed sections skipped |
| **Wrong paragraph** — attributing a holding to the wrong paragraph | `get_case_paragraphs` returns numbered paragraphs |
| **Overruled authority** — citing a case later reversed | `note_up` + explicit warning; human check required |
| **Secondary-source contamination** — blog/news summary | only primary legislation/judgments are indexed |
| **Silent retrieval failure** — HKLII changes its endpoint | error surfaced, not converted into a fake answer |
| **Language mismatch** — English citation for a Chinese-only text | language field + `lang` parameter |
| **Overbroad search** — keyword hit without legal relevance | snippet + full-text retrieval + analysis step |
| **Version drift** — new amendment after download | `version_date` + re-download/ingest procedure |
| **Current text passed off as historical** — using today's s.9J for a 2020 offence | `statute_history` returns `historical: false` with a warning when no past version is ingested |
| **Missed citation in a passage** — only checking the first citation | `verify_citations` extracts and checks every citation in the text |
| **Invented sentencing number** — quoting a tariff without a source | `sentencing_research` extracts penalty text and labels the result "not a tariff" |
| **Authority rank mistaken for citator** — treating a high score as binding treatment | explicit warning; check note-up and the judgment |

## Controls

### Citation verification

`verify_citation` accepts:

- `Cap. 221 s.9J`
- `section 9J of Cap. 221`
- `Cap. 221 Sch. 3`
- `[2021] HKCFA 1`

It returns `verified`, `not_found`, `unverified`, `mismatch`, or
`unrecognised`. Case verification uses the local cache when available and
HKLII when `live=True`.

`verify_citations` applies the same checks to every citation found in a
passage, deduplicates them, and reports a summary. It is the preferred control
for draft submissions and research memos.

### Provenance on every result

Each legislation result carries:

- Cap. number and section number;
- heading and part/division;
- version date;
- official e-Legislation URL;
- language;
- a note that a snippet is not the full provision.

Each judgment result carries:

- neutral citation;
- court and judgment date;
- HKLII source URL;
- Judiciary document URL when available;
- fetch date and cache status;
- numbered paragraphs.

### Paragraph-level citations

`get_case_paragraphs` extracts `<a class="para">` anchors from the judgment
HTML. The returned paragraph number is the number in the judgment, not a
position in the local text. Use it in submissions as `[2021] HKCFA 1 at [3]`.

### Explicit uncertainty

Skills require `[UNVERIFIED]` markers when a source cannot be retrieved. A
search snippet or a secondary source cannot be promoted to authority.

### Currency and treatment

- Current legislation: `version_date` from the XML.
- Historical legislation: `statute_history` returns the latest official version
  dated on or before the requested date, plus the next version date. If the Past
  Version archive is not ingested, it returns the current text with
  `historical: false` and a warning; it never silently passes current text off
  as historical.
- Judgments: `fetched_at`; `note_up` warning.
- `authority_ranking` is a court-level/cached-note-up heuristic, not a citator.
- The tool never claims to be a citator of record.

### Section ranges

`get_section_range` orders sections by number/letter (9, 9A, 9J, 10) and returns
part/division context. Parts and Orders can restart numbering; the tool warns
and returns all matches rather than guessing which one the user meant.

### Tests

`tests/` covers:

- citation parsing, extraction and deduplication;
- HKeL XML parsing (including repealed sections and schedules);
- ingestion and FTS search;
- get-section, get-section-range and verification;
- historical version selection, fallback and version listing;
- judgment HTML paragraph extraction;
- doctrine, sentencing and authority research packs.

Run `.venv/bin/pytest -q`.

## Confidence levels

Use these in research outputs:

| Level | Meaning |
|---|---|
| **High** | Operative text retrieved from the local corpus; binding authority retrieved by paragraph; no contrary authority found; currency checked. |
| **Medium** | Text retrieved but authority is persuasive/first-instance, or subsequent treatment not fully checked. |
| **Low** | Only a search snippet is available, or the source could not be retrieved; label `[UNVERIFIED]` and do not present as settled. |

## Audit procedure

1. Sample 10 random sections from the corpus; compare heading and text to the
   e-Legislation website.
2. Sample 5 imported judgments; compare paragraph numbers to the source.
3. Run `verify_citation` on known-good and deliberately wrong citations.
4. Check `corpus_status` / `sync_status` for version dates, last sync, and
   judgment-source provenance.
5. Re-run `pytest`.

## Known limitations

- HKLII endpoints are unofficial and may change.
- Note-up data and authority ranking are not a citator of record.
- Case law coverage depends on the authorised corpus you import; it is not
  exhaustive, and there is no built-in LRS/HKLII crawler.
- Chinese search uses trigram matching; very short queries fall back to LIKE.
- Historical coverage depends on which Past Version archives/languages were
  ingested; commencement timelines are not reconstructed.
- `sentencing_research` is not a sentencing tariff or a structured sentencing
  database.
- The skills are practice scaffolds, not legal advice or a substitute for
  supervised legal work.

See [Coverage](coverage.md) for what is indexed and what is missing.

## Related

[Architecture](architecture.md) · [Coverage](coverage.md) ·
[Data sources and licensing](data-sources-and-licensing.md) ·
[Documentation index](README.md)
