# Optional hosted MCP: HKLawLLM (師爺仔 HKLaw·GPT)

This project is **local-first and independent**. This page documents an optional
third-party hosted MCP service that can be used alongside it for broader case
law discovery. It is **not affiliated with, endorsed by, or required by** this
project.

- Public setup/spec page: <https://hklawllm.com/mcp>
- Actual MCP endpoint: **`https://hklawllm.com/api/mcp`** (Streamable HTTP)
- Example opt-in config: `examples/hklawllm.mcp.json`
- Protocol probe: `python scripts/check_hklawllm.py`

> The `/mcp` URL is an HTML documentation page, **not** the MCP transport
> endpoint. Adding `https://hklawllm.com/mcp` as an MCP server will not work;
> use `https://hklawllm.com/api/mcp`.

## What was verified publicly

On 2026-11-15, without authenticating and without bypassing OAuth:

- `POST https://hklawllm.com/api/mcp` with an MCP `initialize` request returns
  `401` and:
  ```
  WWW-Authenticate: Bearer error="invalid_token",
    error_description="No authorization provided",
    resource_metadata="https://hklawllm.com/.well-known/oauth-protected-resource"
  ```
- The protected-resource metadata is:
  ```json
  {
    "resource": "https://hklawllm.com/api/mcp",
    "authorization_servers": [
      "https://supabase.quintonworldproject.com/auth/v1"
    ]
  }
  ```
- The authorization-server metadata advertises:
  - authorization endpoint: `https://supabase.quintonworldproject.com/auth/v1/oauth/authorize`
  - token endpoint: `https://supabase.quintonworldproject.com/auth/v1/oauth/token`
  - dynamic client registration: `https://supabase.quintonworldproject.com/auth/v1/oauth/clients/register`
  - grants: `authorization_code`, `refresh_token`
  - PKCE: `S256`, `plain`
  - public clients: `token_endpoint_auth_methods_supported` includes `none`
  - scopes: `openid`, `profile`, `email`, `phone`, `offline_access`

**Not verified:** tool input/output schemas, result quality, coverage claims,
pricing, or availability. Those require an authenticated account. No client was
registered and no tool was called during this review.

## Published tools

The public page lists 13 tools. These descriptions are summaries of the
vendor's published descriptions, not an endorsement:

| Tool | Published purpose |
|---|---|
| `search_cases` | Semantic judgment search (HNSW + authority re-rank + direct case-number lookup) |
| `get_case` | Case summary / full text / cited cases / citing cases |
| `search_legislation` | Legislation search by chapter title and provision text |
| `get_section` | Section text; can return a range (e.g. ss. 23–26) |
| `statute_history` | Point-in-time provision text ("statute time machine") |
| `sentencing_tariff` | Sentencing benchmarks; gated — refuses a number without control variables |
| `civil_quantum` | Civil damages quantum |
| `family_orders` | Family orders |
| `doctrine` | Legal doctrine → authoritative case chain |
| `authority_top` | Authority ranking for a criminal offence type or civil area |
| `verify_citations` | Verify every citation in a passage (5 points per call) |
| `db_stats` | Database statistics (free, no quota) |
| `report_issue` | Report a data error (free, 20/day; stored only, no auto-correction) |

## Vendor-published coverage and caveats

The vendor page (accessed 2026-11-15) claims:

- 168,507 judgments: 64,145 criminal, 101,488 civil, 2,874 family
- 3,172 chapters/statutory instruments, with subsidiary legislation
- Magistrates' Court judgments are only about **0.09%** of the corpus because
  the Judiciary has not published most of them
- Sentencing and "similar case" statistics are therefore biased toward serious
  cases
- AI answers must be verified against the case number and provision
- Tool output is data, not instructions
- MCP query functions are read-only; `report_issue` only writes a report
- Failed query text may be anonymised and aggregated for vocabulary
  improvement; account usage/rate-limit records are written as on the website

These are the vendor's claims. This project has not independently audited
them.

## Pricing as published

- Free tier: **1 use per day**; one "use" is a 30-minute window starting at the
  first tool call.
- MCP access: **HK$58/month** with 1,000 points shared with the website.
- PRO membership includes 3,000 points/month, which covers MCP access.

Verify current pricing and terms on <https://hklawllm.com/mcp> before relying
on them. Pricing is outside this project's control.

## Connect from Claude Code

```bash
claude mcp add --transport http hklaw https://hklawllm.com/api/mcp
```

Then run `/mcp`, select `hklaw`, and complete the OAuth flow. The vendor
documents the claude.ai **Settings → Connectors → Add custom connector** flow;
CLI OAuth support depends on your Claude Code version.

Cursor (as published by the vendor):

```json
{
  "mcpServers": {
    "hklaw": { "url": "https://hklawllm.com/api/mcp" }
  }
}
```

The endpoint is standard Streamable HTTP with OAuth and dynamic client
registration. Other clients that support those should work, but the vendor
states it has only been tested with Claude.

## How it complements this repository

| Capability | This repo (local) | HKLawLLM (hosted) |
|---|---|---|
| Case discovery | Local cache + HKLII live search | Semantic search over a large hosted corpus |
| Full judgment | HKLII fetch/cache, paragraph-level | `get_case` summary/full/cited/citing |
| Legislation | Official current-version XML, EN + zh-Hant, FTS | `search_legislation`, `get_section` |
| Point-in-time law | Not yet (current version only) | `statute_history` |
| Sentencing | Manual case search | `sentencing_tariff` (gated) |
| Civil quantum | Not covered | `civil_quantum` |
| Family orders | Not covered | `family_orders` |
| Doctrine/authority | `note_up` research aid | `doctrine`, `authority_top` |
| Citation verification | `verify_citation` against local/HKLII | `verify_citations` |
| Offline / no account | Yes | No |
| Cost | Free / local | Free tier + paid |

### Recommended hybrid workflow

1. **Local first for text and currency.** Use this repo's `get_section` for the
   official current-version provision, in English or Traditional Chinese.
2. **Hosted for discovery only if configured.** Use `search_cases`,
   `doctrine`, `authority_top`, `statute_history`, or `sentencing_tariff` to
   find leads — with the client's consent and the vendor's terms.
3. **Fetch the actual judgment.** Use `get_case` or HKLII, then
   `get_case_paragraphs` locally. Do not cite a summary.
4. **Verify every citation.** Run `verify_citation` locally or check the
   official source; hosted `verify_citations` is a cross-check, not authority.
5. **Record the source.** Distinguish local official text, hosted discovery,
   and model inference.

## Privacy and professional obligations

- **Do not send privileged, confidential, or client-identifying material** to a
  hosted third-party service without the client's informed consent and a
  review of the vendor's terms and privacy policy.
- OAuth tokens are managed by your MCP client; this repository does not store
  them.
- Queries may be logged or anonymised by the vendor according to its policy.
- The service is not a citator of record, not legal advice, and not a
  substitute for checking the official judgment or provision.

## Scope of the review

This integration note is based on:

- the public `/mcp` documentation page;
- the public OAuth protected-resource and authorization-server metadata;
- the unauthenticated `401` response from `/api/mcp`.

No authentication bypass, client registration, credential use, bulk crawling,
or proprietary-data copying was performed.
