# Coverage

Snapshot: **2026-11-15** (corpus built from the DATA.GOV.HK current-version
archives downloaded that day).

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
- Sections, schedules, Parts, Divisions, and High Court Order rule context.
- English and Traditional Chinese text.
- Repealed sections are skipped; operative sections are kept.
- Source notes are stored separately from the operative text.

## Not included

- Historical versions or point-in-time legislation.
- Commencement timelines beyond the document date.
- Editorial notes, annotations, or commentary.
- Practice directions, court guides, and sentencing guidelines as separate
  corpora (some may appear in judgments).
- A prebuilt judgment database.
- Reported-case series (HKLR, HKC, etc.) not available through HKLII.
- A citator of record (note-up is a research aid only).

## Case law

Judgments are **demand-driven**:

1. `search_cases` queries the local cache and HKLII's public search.
2. `get_case` fetches the full judgment by neutral citation and caches it.
3. `get_case_paragraphs` retrieves numbered paragraphs.
4. `note_up` caches HKLII's note-up payload.

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
