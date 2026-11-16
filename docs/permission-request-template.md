# Permission request template — automated judgment access

Use this when asking the Hong Kong Judiciary (Legal Reference System) or HKLII
for permission to retrieve judgments into a **private, local research corpus**.
It is a starting point, not legal advice. Adapt the scope to your practice and
send it through the contact route the source publishes.

## Why a permission is needed

- **Judiciary LRS:** `https://legalref.judiciary.hk/robots.txt` is
  `Disallow: /`. The Judiciary permits downloading judgments for private study
  and research; commercial use requires a written application.
- **HKLII:** `https://www.hklii.hk/robots.txt` is `Disallow: /api`. HKLII's
  terms prohibit automated harvesting/re-supply; judgment text is HKSAR
  Government copyright reproduced by permission for private use.
- **No official bulk API:** no public bulk-download endpoint or data.gov.hk
  judgment-text dataset was found. A permission-gated feed is the compliant
  route.

Do not configure `HK_LAW_CASE_PERMISSION_REF` until you have a written
permission whose scope covers the endpoint you will use.

## Email / letter template

> **Subject:** Request for permission to retrieve judgments for private legal
> research (automated, rate-limited, local-only)
>
> Dear [Judiciary / HKLII contact],
>
> I am [name], [role] at [organisation]. I maintain a private, non-commercial
> legal-research corpus for [purpose: e.g. preparing defences in Hong Kong
> criminal cases / academic research]. I would like permission to retrieve
> judgments on an automated but strictly limited basis.
>
> **What I propose to access**
>
> - Source: [Judiciary Legal Reference System / HKLII]
> - Courts: [HKCFA, HKCA, HKCFI, HKDC, HKMC — or the specific list]
> - Years: [e.g. 1997–present, or 2020–present]
> - Languages: [English / Traditional Chinese]
> - Fields: [neutral citation, case title, court, judgment date, paragraph
>   text, cited cases; note-up only if separately permitted]
> - Endpoint / URL pattern: [the exact permitted endpoint or pattern]
>
> **How I will access it**
>
> - One request at a time, with a minimum interval of [e.g. 2 seconds] and no
>   parallel connections.
> - Identifiable User-Agent: `[tool/version (+contact)]`.
> - Refresh: [daily incremental / weekly]; initial backfill: [scope and
>   estimated volume].
> - Off-peak window: [e.g. 01:00–06:00 HKT], if required.
> - I will stop immediately on a 429/403 or on your request.
>
> **What I will do with the data**
>
> - Store it only on a local, access-controlled machine; no public server, no
>   API resale, no redistribution, no competing database.
> - Retain it for [period] and delete it on request or on termination of
>   permission.
> - Attribute every citation to the neutral citation and the official/HKLII
>   URL; display a "not the official text" disclaimer.
> - Keep an audit log of sync runs and source provenance.
>
> **What I am asking you to confirm in writing**
>
> 1. That automated retrieval is permitted for the stated private,
>    non-commercial purpose.
> 2. The permitted endpoint(s) or URL pattern.
> 3. The permitted courts, years, languages, and fields.
> 4. The required rate limit, concurrency, and access window.
> 5. Whether note-up data is included.
> 6. Any attribution, retention, deletion, or security conditions.
> 7. A permission reference I can record in my configuration.
>
> I am happy to provide any further information or to adjust the scope. Thank
> you for considering this request.
>
> Yours sincerely,
> [Name, contact details, organisation, date]

## What to do with the reply

Record the written permission reference in the environment, never in the
database or source tree:

```bash
# ~/.config/hk-law-sync.env   (mode 0600)
HK_LAW_CASE_PERMISSION_REF="JUD-HKLII-2026-001"
HK_LAW_CASE_SOURCE="hklii"
HK_LAW_CASE_SOURCE_URL="https://permitted.example/path"
HK_LAW_CASE_CITATIONS="/absolute/path/to/authorised-citations.txt"
HK_LAW_CASE_LICENSE="Private research; no redistribution"
```

Then run:

```bash
.venv/bin/hk-law sync --dataset current
.venv/bin/hk-law sync-status
```

The sync records the reference and source URL in `case_sources`, and refuses
to run if the reference is missing. It fetches only the explicit citation list;
it does not discover or crawl cases.

## If permission is refused or delayed

Use an authorised corpus import instead:

```bash
.venv/bin/hk-law import-cases \
  --path /path/to/licensed-export.jsonl \
  --source "licensed-provider" \
  --license "Private research; no redistribution"
```

The MCP remains fully local; `search_cases`, `get_case`, and
`get_case_paragraphs` work against the imported corpus. See
[Fully local pipeline](full-local-pipeline.md).

## Scope checklist

- [ ] Purpose is private study/research, not commercial republication.
- [ ] Courts, years, languages, and fields are explicitly listed.
- [ ] Endpoint/URL pattern is explicitly permitted.
- [ ] Rate limit and concurrency are agreed in writing.
- [ ] Note-up is either included or explicitly excluded.
- [ ] Attribution and disclaimer requirements are recorded.
- [ ] Retention, deletion, and security conditions are recorded.
- [ ] Permission reference is stored outside the repository (mode 0600).
- [ ] No redistribution, resale, or public API.
