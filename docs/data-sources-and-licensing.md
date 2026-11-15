# Data sources and licensing

Where the corpus comes from and what you may do with each layer. Read this
before redistributing the database, publishing a derived work, or using the
tool commercially.

[Documentation index](README.md) · On this page:
[At a glance](#at-a-glance) · [e-Legislation](#hong-kong-e-legislation-legislation) ·
[Judiciary judgments](#hong-kong-judiciary--legal-reference-system-judgments) ·
[HKLII](#hklii-case-retrieval-and-search) ·
[Bill of Rights and constitutional instruments](#hong-kong-bill-of-rights-and-constitutional-instruments) ·
[Project licenses](#project-licenses) · [Compliance checklist](#practical-compliance-checklist)

## At a glance

| Bucket | Covers | Terms |
|---|---|---|
| Code | `src/`, `tests/`, `scripts/` | Apache-2.0 |
| Skills and docs | `skills/`, `docs/` | CC BY 4.0 |
| Downloaded data | `data/` and the SQLite corpus | DATA.GOV.HK, Judiciary, and HKLII terms |

This project distinguishes **code**, **skills/docs**, and **downloaded data**.
They have different licenses and different obligations.

## Hong Kong e-Legislation (legislation)

**Source:** Department of Justice, Hong Kong e-Legislation, XML bulk archives
published on DATA.GOV.HK:

- Current version:
  <https://data.gov.hk/en-data/dataset/hk-doj-hkel-legislation-current>
  — files `hkel_c_leg_cap_*`, `hkel_c_instruments_*`
- Past versions:
  <https://data.gov.hk/en-data/dataset/hk-doj-hkel-legislation-past>
  — files `hkel_p_leg_cap_*`, `hkel_p_instruments_*`
- Languages: English, Traditional Chinese, Simplified Chinese
- Format: ZIP containing HKL M 1.0 XML

**Terms:** DATA.GOV.HK terms of use. The data is free to reuse with
attribution. This project:

- downloads the archives at the user's direction;
- stores them under `data/raw/` (git-ignored);
- indexes them into a local SQLite database (git-ignored);
- does not redistribute the archives or the database.

**Attribution in outputs:** include the Cap. number, section, version date, and
the e-Legislation URL. Do not present the local copy as the official text.

**Currency:** the current archives are the version in force at the time of
download. The Past Version archives are official historical versions; when
ingested, `statute_history` returns the latest official version dated on or
before the requested date. Coverage depends on which past archives/languages
were ingested. Commencement timelines are not reconstructed.

## Hong Kong Judiciary — Legal Reference System (judgments)

**Source:** <https://legalref.judiciary.hk/>

**Terms:** the Judiciary permits downloading of judgments for private study and
research. Commercial use requires a written application. There is no official
public API, and hyperlinking to the database requires prior approval.

This project does not bundle judgments. It fetches a judgment only when the
user requests a specific neutral citation, caches it locally, and stores the
Judiciary's document URL when HKLII provides one.

**Do not** use the local cache for commercial redistribution, bulk publication,
or a competing database without checking the Judiciary's terms and obtaining
permission where required.

## HKLII (case retrieval and search)

**Source:** <https://www.hklii.hk/>

**Terms:** HKLII is a free public legal information service. The project uses
the same JSON endpoints as HKLII's web client:

- `GET /api/simplesearch?searchstring=...`
- `GET /api/getjudgment?lang=en&abbr=hkcfa&year=2021&num=1`
- `GET /api/getcasenoteup?abbr=...&year=...&num=...`

These endpoints are **undocumented** and may change or be withdrawn. They are
not an official Judiciary API. The client:

- identifies itself with a project User-Agent;
- serializes requests with a 1.5-second minimum interval;
- retries with backoff on transient failures;
- caches responses locally;
- does not bulk-crawl or redistribute judgment text.

**Attribution:** cite the neutral citation and link to the HKLII or Judiciary
source. Do not describe HKLII as an official government source.

## Hong Kong Bill of Rights and constitutional instruments

The Bill of Rights Ordinance (Cap. 383) and constitutional instruments are
included in the e-Legislation archives and are subject to the same DATA.GOV.HK
terms.

## Project licenses

- **Code** (`src/`, `tests/`, `scripts/`): Apache License 2.0 — see `LICENSE`.
- **Skills and documentation** (`skills/`, `docs/`): CC BY 4.0 — see
  `LICENSE-SKILLS`.
- **Downloaded data**: not covered by the project licenses; governed by the
  source terms above.

## Practical compliance checklist

- [ ] I downloaded legislation from DATA.GOV.HK, not a secondary site.
- [ ] I attributed the Cap./section and source URL in my output.
- [ ] I did not redistribute the bulk archives or the SQLite database.
- [ ] I checked the Judiciary/HKLII terms before commercial use.
- [ ] I did not present the local copy as the official text.
- [ ] I did not bulk-crawl HKLII or bypass its rate limits.

## Related

[Architecture](architecture.md) · [Coverage](coverage.md) ·
[Reliability model](reliability.md) · [Documentation index](README.md)
