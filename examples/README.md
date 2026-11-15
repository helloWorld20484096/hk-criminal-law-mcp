# Optional integrations

These files are **not enabled by default**. They are opt-in examples for
third-party services that require their own account, terms, and OAuth consent.

## HKLawLLM (師爺仔 HKLaw·GPT)

- Public setup/spec page: <https://hklawllm.com/mcp>
- Actual MCP endpoint: `https://hklawllm.com/api/mcp`
- Config: `examples/hklawllm.mcp.json`
- Integration notes: `docs/hklawllm-integration.md`

The service is hosted, independent, and not affiliated with this project. It
requires OAuth and has its own free/paid quotas. Do not send privileged or
client-identifying material without consent and a terms/privacy review.

To use the example in another project, copy `hklawllm.mcp.json` to that
project's `.mcp.json` (or merge the `mcpServers` entry), then authenticate when
your MCP client prompts.

The repository's own `.mcp.json` deliberately does **not** include this server,
so cloning the repo never signs you up to a third-party service.
