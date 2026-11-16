# Data sources and licensing

Where the corpus comes from and what you may do with each layer. Read this
before redistributing the database, publishing a derived work, or using the
tool commercially.

[Documentation index](README.md) · On this page:
[At a glance](#at-a-glance) · [e-Legislation](#hong-kong-e-legislation-legislation) ·
[DOJ policy publications](#doj-policy-publications) ·
[Judiciary judgments](#hong-kong-judiciary--legal-reference-system-judgments) ·
[HKLII](#hklii-case-retrieval-and-search) ·
[Bill of Rights and constitutional instruments](#hong-kong-bill-of-rights-and-constitutional-instruments) ·
[Project licenses](#project-licenses) · [Compliance checklist](#practical-compliance-checklist)

## At a glance

| Bucket | Covers | Terms |
|---|---|---|
| Code | `src/`, `tests/`, `scripts/` | Apache-2.0 |
| Skills and docs | `skills/`, `docs/` | CC BY 4.0 |
| Downloaded data | `data/` and the SQLite corpus | DATA.GOV.HK, DOJ, Judiciary, and HKLII terms |

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

## DOJ policy publications

**Source:** Department of Justice, <https://www.doj.gov.hk/> — the Prosecution
Code and the domestic-violence prosecution policy pages.

**Terms:** Government of the Hong Kong SAR public information. The project:

- fetches only the curated Prosecution Code and domestic-violence policy pages,
  plus shallow discovery from their two index pages;
- identifies itself with a project User-Agent and uses a 0.5-second default
  interval;
- caches the pages and paragraphs in the local SQLite corpus;
- does not redistribute the pages or the database.

DOJ publications are **policy material, not legislation or judgments**. Cite
the page title, paragraph number if any, version date and source URL. Do not
present a DOJ policy paragraph as a statutory provision or a judicial
authority. Verify every paragraph against the DOJ source.

## Hong Kong Judiciary — Legal Reference System (judgments)

**Source:** <https://legalref.judiciary.hk/>

**Terms:** the Judiciary permits downloading of judgments for private study and
research. Commercial use requires a written application. There is no official
public API, and hyperlinking to the database requires prior approval. Its
`robots.txt` is `Disallow: /`.

This project does not bundle judgments and does not crawl the LRS. It imports a
corpus the operator is authorised to use, or fetches an explicit citation list
through a permission-gated adapter. Automated bulk access requires written
permission; see
[Permission request template](permission-request-template.md).

**Do not** use the local cache for commercial redistribution, bulk publication,
or a competing database without checking the Judiciary's terms and obtaining
permission where required.

## HKLII (case retrieval and search)

**Source:** <https://www.hklii.hk/>

**Terms:** HKLII is a free public legal information service. Its `robots.txt`
is `Disallow: /api`, and its terms prohibit automated harvesting/re-supply.
The project therefore does **not** crawl HKLII. The JSON endpoints are used
only for an explicit, permitted citation list after written permission:

- `GET /api/simplesearch?searchstring=...`
- `GET /api/getjudgment?lang=en&abbr=hkcfa&year=2021&num=1`
- `GET /api/getcasenoteup?abbr=...&year=...&num=...`

These endpoints are **undocumented** and may change or be withdrawn. They are
not an official Judiciary API. When a permitted citation list is configured,
the client:

- identifies itself with a project User-Agent;
- serializes requests with a 1.5-second minimum interval;
- retries with backoff on transient failures;
- caches responses locally;
- does not crawl, discover cases, or redistribute judgment text.

The `sync_cases` function refuses to run without
`HK_LAW_CASE_PERMISSION_REF` and an explicit citation list. The default MCP
launcher uses live HKLII for case search/read (`HK_LAW_LOCAL_ONLY=0`), subject
to these terms; set `HK_LAW_LOCAL_ONLY=1` for a strictly local MCP. The
repository stores no judgment text.

**Attribution:** cite the neutral citation and link to the HKLII or Judiciary
source. Do not describe HKLII as an official government source.

## Hong Kong Bill of Rights and constitutional instruments

The Bill of Rights Ordinance (Cap. 383) and constitutional instruments are
included in the e-Legislation archives and are subject to the same DATA.GOV.HK
terms.

## Authorised bulk access

If you obtain written permission, record the reference and the permitted
endpoint outside the repository:

```bash
# ~/.config/hk-law-sync.env (mode 0600)
HK_LAW_CASE_PERMISSION_REF="JUD-HKLII-2026-001"
HK_LAW_CASE_SOURCE="hklii"
HK_LAW_CASE_SOURCE_URL="https://permitted.example/path"
HK_LAW_CASE_CITATIONS="/absolute/path/to/authorised-citations.txt"
HK_LAW_CASE_LICENSE="Private research; no redistribution"
```

`hk-law sync --citations ...` fetches only that explicit list. It does not
discover cases. The LRS adapter is not wired until the permission letter
specifies the permitted URL pattern, scope, and rate limit. The written request
template is [here](permission-request-template.md).

## Publishing a remote endpoint

`hk-law serve-http` lets other people query your local corpus. That does not
change the source terms, and it makes **you** the operator of a service.

- **Do not run an open, public endpoint over a corpus that contains judgment
  text you may not redistribute.** The remote surface can return any locally
  imported judgment to any authenticated caller. Keep such deployments private,
  or keep judgments out of the corpus.
- **Prefer `HK_LAW_LOCAL_ONLY=1` for a public deployment.** Live HKLII access is
  intended for individual, rate-limited research. A public multi-user service
  that proxies HKLII at scale needs its own permission and terms review.
- **Keep the rate limiter and the disclaimer.** Do not remove the provenance
  fields or the warning that search snippets are not the provision.
- **Protect the endpoint.** Use an access key and HTTPS, and do not publish the
  SQLite volume. An anonymous endpoint is a deliberate choice, not a default.
- **Logs and queries.** Reverse proxies and application logs may record user
  queries. Treat them as confidential research material.

See [Remote access](remote-access.md) for the deployment controls.

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
- [ ] I did not present a DOJ policy paragraph as legislation or a judgment.
- [ ] I did not crawl the LRS or HKLII without written permission.
- [ ] Any automated case access uses an explicit citation list and a recorded
      permission reference.
- [ ] Imported judgment text stays local and is not redistributed.

## Related

[Architecture](architecture.md) · [Coverage](coverage.md) ·
[Reliability model](reliability.md) · [Documentation index](README.md)
