# Documentation

How the corpus is built, what it covers, how to verify a result, and the terms
that apply to the data.

> [!NOTE]
> New here? Start with the [README quick start](../README.md#quick-start), then
> come back for the reference detail.

## Read by task

| Task | Document |
|---|---|
| Understand the modules, data flow, and SQLite schema | [Architecture](architecture.md) |
| Check what is indexed, which Cap. numbers are covered, and what is missing | [Coverage](coverage.md) |
| Verify a citation or understand the reliability controls | [Reliability model](reliability.md) |
| Check source terms, attribution, and reuse rules | [Data sources and licensing](data-sources-and-licensing.md) |
| Install, edit, or write a defence skill | [Defence skills](../skills/README.md) |
| Run the server, CLI, or tools | [README: Quick start](../README.md#quick-start) · [MCP tools](../README.md#mcp-tools) |

## Reference

| Document | Answers |
|---|---|
| [Architecture](architecture.md) | How HKeL XML becomes SQLite sections; how judgments are fetched and cached; why the design is local-first. |
| [Coverage](coverage.md) | Corpus counts, core criminal Cap. numbers, historical coverage, case-law coverage, and known gaps. |
| [Reliability model](reliability.md) | Failure modes, verification statuses, provenance, confidence levels, and the audit procedure. |
| [Data sources and licensing](data-sources-and-licensing.md) | DATA.GOV.HK, Judiciary, and HKLII terms; project licenses; compliance checklist. |
| [Defence skills](../skills/README.md) | The 12 workflows, installation, and editing rules. |

## Documentation conventions

- Start each document with the question it answers and who it is for.
- Use relative links so the docs work on GitHub and in a local checkout.
- Tag code fences (`bash`, `json`, `text`) and keep commands runnable from the
  repository root.
- Label snapshots and counts with their date; do not present local counts as
  permanent corpus facts.
- End reference documents with links to the adjacent documents.

## Related

[README](../README.md) · [Architecture](architecture.md) ·
[Coverage](coverage.md) · [Reliability](reliability.md) ·
[Data sources](data-sources-and-licensing.md) · [Skills](../skills/README.md)
