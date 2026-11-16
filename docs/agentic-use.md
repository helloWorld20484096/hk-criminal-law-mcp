# Agentic use

The MCP server is designed to be called automatically by agents. Tool
descriptions and the server instructions carry the operating protocol, so an
agent does not need a manually maintained routing table.

## Claude Code

The user-scope server is registered as `hk-criminal-law` and is available in
every project:

```bash
claude mcp get hk-criminal-law
```

The repository also ships a project-scoped server, `hk-criminal-law-local`
(`.mcp.json` and `scripts/run_mcp.sh`). Approve it via `/mcp` if it is pending.

The project includes a research subagent at
`.claude/agents/hk-law-researcher.md`. Invoke it by asking Claude Code to use
`hk-law-researcher`, or run it directly in the agent UI. Its prompt requires the
MCP workflow: corpus check → discovery → primary text → citation verification →
provenance.

The 12 practice skills under `skills/` also assume the MCP and can drive a
workflow from intake through appeal.

## Automatic tool use

Agents discover the tools from the MCP server. The important ones are:

| Stage | Tools |
|---|---|
| Health | `corpus_status`, `sync_status`, `doj_status`, `semantic_status` |
| Discovery | `semantic_search`, `semantic_clusters`, `semantic_neighbors`, `search_legislation`, `search_cases`, `search_doj`, `doctrine_research` |
| Primary text | `get_section`, `get_section_range`, `statute_history`, `list_section_versions`, `get_case`, `get_case_paragraphs`, `get_doj_document`, `list_doj_documents` |
| Verification | `verify_citation`, `verify_citations`, `verify_doj`, `note_up`, `authority_ranking` |
| Research packs | `doctrine_research`, `sentencing_research`, `case_graph` |

The server instructions state the mandatory sequence: verify every citation,
read the operative text, distinguish current from historical law, treat DOJ
policy material as policy rather than legislation or judicial authority, and
label unverified material `[UNVERIFIED]`.

The server defaults to live HKLII for case search/read
(`HK_LAW_LOCAL_ONLY=0`); set `HK_LAW_LOCAL_ONLY=1` for a strictly local MCP.
In local-only mode a missing judgment is a coverage gap, not a negative
finding; report it and do not fabricate a citation. In live mode a HKLII
failure falls back to local results with `live_error`.

## Remote MCP and hosted assistants

`hk-law serve-http` exposes the same tools over Streamable HTTP at `/mcp`, plus
a JSON API (`/api/<tool>`), an OpenAPI schema (`/openapi.json`) and a mobile web
app (`/`). This is the path for ChatGPT, Claude web/mobile, Gemini, DeepSeek
Harness and phones; it is not required for Claude Code.

See [Remote access](remote-access.md) for per-client setup, OAuth, deployment
and security. The short version:

```bash
.venv/bin/hk-law serve-http --access-key "$KEY" --public-url https://your-host
```

Point an MCP client at `https://your-host/mcp` with
`Authorization: Bearer $KEY`, or use OAuth.

## External agents

The server is a standard stdio MCP server. Point any MCP-capable agent host at
the launcher:

```json
{
  "mcpServers": {
    "hk-criminal-law": {
      "command": "/absolute/path/to/repo/scripts/run_mcp.sh",
      "env": {
        "HK_LAW_LOCAL_ONLY": "0",
        "HK_LAW_SEMANTIC_MAP": "/absolute/path/to/repo/semantic_map/dist/data"
      }
    }
  }
}
```

Or launch the installed package directly:

```bash
/path/to/venv/bin/python -m hk_criminal_law_mcp.server
```

For a framework that supports MCP (Claude Agent SDK, LangGraph, CrewAI, etc.),
register the stdio command and let the framework expose the tools. No custom
client is required.

If the agent runs outside this repository, set `HK_LAW_DB` to the corpus and
`HK_LAW_SEMANTIC_MAP` to the atlas data directory. The semantic tools return an
explicit unavailable message, with a build hint, when the atlas has not been
generated.

## Guardrails

- The semantic atlas is a discovery aid; similarity and cluster labels are not
  authority.
- `note_up` and `authority_ranking` are not a citator of record.
- `sentencing_research` is not a sentencing tariff.
- Every provision and judgment must be checked against the official source
  before it is relied on.
- The server is not legal advice.

## Related

[Remote access: ChatGPT, Claude, Gemini, DeepSeek and phones](remote-access.md) ·
[Architecture](architecture.md) · [README](../README.md)
