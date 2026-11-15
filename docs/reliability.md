# Reliability model

Legal research fails in predictable ways. This document lists the failure modes
the project is designed to catch and the controls it uses.

## Failure modes

| Failure | Example | Control |
|---|---|---|
| Hallucinated citation | "Cap. 221 s.99ZZ" | `verify_citation` / `get_section` returns `not_found` |
| Wrong section/heading | citing s.9J for a different bail rule | `get_section` returns the heading and operative text |
| Stale law | relying on a repealed or amended provision | current-version corpus + `version_date`; repealed sections skipped |
| Wrong paragraph | attributing a holding to the wrong paragraph | `get_case_paragraphs` returns numbered paragraphs |
| Overruled authority | citing a case later reversed | `note_up` + explicit warning; human check required |
| Secondary-source contamination | blog/news summary | only primary legislation/judgments are indexed |
| Silent retrieval failure | HKLII changes its endpoint | error surfaced, not converted into a fake answer |
| Language mismatch | English citation for a Chinese-only text | language field + `lang` parameter |
| Overbroad search | keyword hit without legal relevance | snippet + full-text retrieval + analysis step |
| Version drift | new amendment after download | `version_date` + re-download/ingest procedure |

## Controls

### 1. Citation verification

`verify_citation` accepts:

- `Cap. 221 s.9J`
- `section 9J of Cap. 221`
- `Cap. 221 Sch. 3`
- `[2021] HKCFA 1`

It returns `verified`, `not_found`, `unverified`, `mismatch`, or
`unrecognised`. Case verification uses the local cache when available and
HKLII when `live=True`.

### 2. Provenance on every result

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

### 3. Paragraph-level citations

`get_case_paragraphs` extracts `<a class="para">` anchors from the judgment
HTML. The returned paragraph number is the number in the judgment, not a
position in the local text. Use it in submissions as `[2021] HKCFA 1 at [3]`.

### 4. Explicit uncertainty

Skills require `[UNVERIFIED]` markers when a source cannot be retrieved. A
search snippet or a secondary source cannot be promoted to authority.

### 5. Currency and treatment

- Legislation: `version_date` from the XML; current-version corpus.
- Judgments: `fetched_at`; `note_up` warning.
- The tool never claims to be a citator of record.

### 6. Tests

`tests/` covers:

- citation parsing and normalisation;
- HKeL XML parsing (including repealed sections and schedules);
- ingestion and FTS search;
- get-section and verification;
- judgment HTML paragraph extraction.

Run `.venv/bin/pytest -q`.

## Confidence levels

Use these in research outputs:

- **High:** operative text retrieved from the local corpus; binding authority
  retrieved by paragraph; no contrary authority found; currency checked.
- **Medium:** text retrieved but authority is persuasive/first-instance, or
  subsequent treatment not fully checked.
- **Low:** only a search snippet is available, or the source could not be
  retrieved; label `[UNVERIFIED]` and do not present as settled.

## Audit procedure

1. Sample 10 random sections from the corpus; compare heading and text to the
   e-Legislation website.
2. Sample 5 cached judgments; compare paragraph numbers to the source.
3. Run `verify_citation` on known-good and deliberately wrong citations.
4. Check `corpus_status` for the version date and last ingest time.
5. Re-run `pytest`.

## Known limitations

- HKLII endpoints are unofficial and may change.
- Note-up data is not a citator of record.
- Case law coverage is demand-driven, not exhaustive.
- Chinese search uses trigram matching; very short queries fall back to LIKE.
- The corpus is current-version only; historical research needs another source.
- The skills are practice scaffolds, not legal advice or a substitute for
  supervised legal work.
