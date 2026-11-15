# Coverage

Snapshot: **2026-11-15** (current-version archives plus the English Past
Version archives downloaded that day).

## Corpus counts

| Metric | Count |
|---|---|
| Legislation documents (all languages) | 6,220 |
| — English documents | 3,110 |
| — Traditional Chinese documents | 3,110 |
| Legislation sections/schedules (all languages) | 120,421 |
| — English sections | 60,300 |
| — Traditional Chinese sections | 60,121 |
| Instruments (constitutional/other) | 124 |

The counts are from `hk-law stats`. The database is local and not distributed
with the source repository.

## Historical corpus counts (English Past Version archives)

| Metric | Count |
|---|---|
| Historical document versions | 15,438 |
| Historical sections/schedules | 851,431 |
| Historical date range | 1997-06-30 .. 2026-08-01 |
| Combined current + historical sections | 971,852 |

These counts depend on which Past Version archives/languages were ingested.
Traditional Chinese past versions can be added with
`--dataset past --languages zh-Hant`.

## Core criminal law and procedure

| Cap. | Title | Version date |
|---|---|---|
| 4 | High Court Ordinance | 2023-04-01 |
| 8 | Evidence Ordinance | 2026-05-14 |
| 91 | Legal Aid Ordinance | 2026-03-27 |
| 134 | Dangerous Drugs Ordinance | 2026-06-12 |
| 136 | Mental Health Ordinance | 2026-07-31 |
| 200 | Crimes Ordinance | 2024-03-23 |
| 210 | Theft Ordinance | 2021-06-24 |
| 212 | Offences against the Person Ordinance | 2021-04-22 |
| 221 | Criminal Procedure Ordinance | 2026-05-14 |
| 226 | Juvenile Offenders Ordinance | 2022-07-01 |
| 227 | Magistrates Ordinance | 2026-05-14 |
| 232 | Police Force Ordinance | 2025-08-24 |
| 383 | Hong Kong Bill of Rights Ordinance | 2017-02-15 |

The Basic Law and other constitutional instruments are also indexed (for
example, Cap. A101).

Version dates come from the `dc:date` metadata of each XML document. They are
the date of the current consolidated version, not the date of the original
enactment.

## Included

- Ordinances and subsidiary legislation in the current-version XML archives.
- Historical versions from the official Past Version archives when downloaded
  and ingested (English by default in this snapshot).
- Sections, schedules, Parts, Divisions, and High Court Order rule context.
- English and Traditional Chinese current text.
- Repealed sections are skipped; operative sections are kept.
- Source notes are stored separately from the operative text.
- Point-in-time lookup with `statute_history(cap, section, as_of)`.

## Not included

- Historical versions for ranges/languages whose past archives were not
  ingested.
- Commencement timelines beyond the document/version dates.
- Editorial notes, annotations, or commentary.
- Practice directions, court guides, and sentencing guidelines as separate
  corpora (some may appear in judgments).
- A prebuilt judgment database.
- Reported-case series (HKLR, HKC, etc.) not available through HKLII.
- A citator of record (note-up and authority ranking are research aids only).

## Historical legislation

The Past Version archives are published by the Department of Justice on
DATA.GOV.HK under the same free-reuse terms as the current archives. They are
optional and large.

```bash
# English past versions (~2.1 GB of ZIPs)
.venv/bin/hk-law download --data-dir data/raw --dataset past --languages en
.venv/bin/hk-law ingest --data-dir data/raw --dataset past --language en

# Example: what did Cap. 221 s.9J say on 1 June 2020?
.venv/bin/hk-law statute-history 221 9J --as-of 2020-06-01
.venv/bin/hk-law section-versions 221 9J
```

If a section/date has no ingested historical version, `statute_history`
returns the current text with `historical: false` and an explicit warning. It
never silently presents current text as historical law.

Historical counts are reported by `hk-law stats` as
`legislation_history_docs`, `legislation_history_sections`, and
`legislation_history_date_range`.

## Case law

Judgments are **demand-driven**:

1. `search_cases` queries the local cache and HKLII's public search.
2. `get_case` fetches the full judgment by neutral citation and caches it.
3. `get_case_paragraphs` retrieves numbered paragraphs.
4. `note_up` caches HKLII's note-up payload.
5. `case_graph` returns outgoing cited cases and incoming note-up citations.
6. `authority_ranking` ranks results by court level and cached note-up data.
7. `doctrine_research` combines legislation hits with ranked case leads.

Coverage grows as you use the tool. The initial database contains only the
cases you have fetched. There is no bundled judgment corpus because the
Judiciary/HKLII terms do not permit redistribution here.

## Recommended coverage for a criminal practice

- Core penal statutes: Cap. 200, 210, 212, 134, 227, 221, 226, 136.
- Evidence and procedure: Cap. 8, 221, 227, 4.
- Constitutional: Basic Law, Cap. 383.
- Sentencing: guideline cases in CFA/CA; fetch and cache the key authorities.
- Offence-specific ordinances as they arise (e.g. firearms, public order,
  immigration, customs, securities, national security).

Use `list_ordinances` and `search_legislation` to confirm that a provision is
in the corpus before relying on it.
