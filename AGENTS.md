# Agent instructions

This repository ships a local-first Hong Kong criminal-law MCP server. Agents
must use it for Hong Kong legal research rather than answering from memory.

## Start the server

The user-scope server is normally registered as `hk-criminal-law`:

```bash
claude mcp get hk-criminal-law
```

The project-scoped server is `hk-criminal-law-local` (approve it via `/mcp` in
Claude Code if it is pending). Manual launch:

```bash
bash scripts/run_mcp.sh
```

The server reads `HK_LAW_DB` and, when built, `HK_LAW_SEMANTIC_MAP`
(`semantic_map/dist/data`). The launcher defaults to `HK_LAW_LOCAL_ONLY=0`:
case search/read uses live HKLII by default; set `HK_LAW_LOCAL_ONLY=1` for a
strictly local MCP.

## Agent protocol

1. Call `corpus_status` (and `sync_status` for freshness/provenance).
2. For prosecution policy and discretion, call `doj_status`, search with
   `search_doj`, read with `get_doj_document`, and check policy citations with
   `verify_doj`. DOJ material is policy, not legislation or judicial authority.
3. Discover with `semantic_search`, `semantic_clusters`, `semantic_neighbors`,
   `search_legislation`, `search_cases`, and `doctrine_research`. `search_cases`
   uses local FTS plus live HKLII by default; in local-only mode a missing
   judgment is a coverage gap, not proof it does not exist. Do not fabricate a
   citation.
4. Read primary text with `get_section`, `statute_history`,
   `get_case`, and `get_case_paragraphs`.
5. Run `verify_citations` (and `verify_doj` for DOJ policy citations) over every
   citation before relying on it.
6. Use `statute_history` for the law in force on a date.
7. Label anything you cannot retrieve `[UNVERIFIED]`.
8. Cite judgments by paragraph, and include provenance and confidence.

Do not treat semantic proximity, cluster labels, or authority-ranking scores as
authority. The server is a retrieval aid, not legal advice and not a citator of
record.

See `docs/agentic-use.md` for Claude Code, subagent, and external-framework
integration.

## Remote surface

`hk-law serve-http` exposes the same tools over Streamable HTTP at `/mcp`, a
JSON API at `/api/<tool>`, OpenAPI at `/openapi.json`, a mobile web app at
`/`, and a one-click setup page at `/connect`. Remote deployments require an
operator access key (or an explicit anonymous/open mode), may hide `sync_doj`,
and redact operator paths/permission references from status results. See
`docs/remote-access.md`.
