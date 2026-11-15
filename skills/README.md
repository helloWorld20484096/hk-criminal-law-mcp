# Defence skills

Practice scaffolds for Hong Kong criminal law and defence. They tell the model
what to retrieve, what to verify, and what to record, rather than asserting
legal rules from memory.

[README](../README.md) · [Documentation index](../docs/README.md) · On this
page: [Common paths](#common-paths) · [Skills](#skills) ·
[Installation](#installation) · [Editing](#editing)

## Common paths

- New arrest, summons, or police contact: `hk-criminal-intake` →
  `hk-bail-application`.
- Charge sheet or indictment: `hk-charge-analysis` → `hk-case-file-review` →
  `hk-defense-strategy`.
- Trial or sentence: `hk-trial-defense` → `hk-sentencing-mitigation`.
- Appeal: `hk-appeal`.
- Research question: `hk-legal-research`.
- Special issues: `hk-juvenile-defense` or `hk-mental-health-criminal`.
- Conduct and ethics: `hk-professional-ethics`.

## Skills

| Skill | When to use |
|---|---|
| `hk-criminal-intake` | First contact after arrest, summons, or police investigation |
| `hk-bail-application` | Police/court bail, review, variation, sureties |
| `hk-charge-analysis` | Charge sheet/indictment; elements, defences, venue |
| `hk-case-file-review` | Prosecution papers, evidence matrix, disclosure |
| `hk-defense-strategy` | Plea vs trial, charge negotiation, decision memo |
| `hk-sentencing-mitigation` | Plea in mitigation, guideline authorities, totality |
| `hk-trial-defense` | Trial plan, cross-examination, closing submissions |
| `hk-appeal` | Conviction/sentence appeal, leave, fresh evidence |
| `hk-legal-research` | Verification-first research protocol |
| `hk-professional-ethics` | Conflicts, confidentiality, candour, media |
| `hk-juvenile-defense` | Young persons, safeguards, forum, sentencing |
| `hk-mental-health-criminal` | Fitness, psychiatric evidence, hospital orders |

## Installation

### Project-scoped

The repository's `.claude/skills/` links to these folders, so Claude Code
discovers them when the project is open:

```bash
bash scripts/link_skills.sh
```

If you copy a skill elsewhere, keep the `SKILL.md` frontmatter intact. The
skills assume the `hk-criminal-law` MCP server is available.

### All projects

```bash
bash scripts/install_global.sh
```

This installs the MCP server at user scope and copies all 12 skills to
`~/.claude/skills/hk-criminal-law` as one skills-dir plugin. See
[README: Use with Claude Code](../README.md#use-with-claude-code) for the
project-scoped and user-scoped server options.

## Editing

- Keep the frontmatter `name` identical to the folder name.
- Keep `legal_frame: hk`.
- Do not add a legal proposition without a source path: either a Cap./section
  retrievable by the MCP, or a neutral citation with a paragraph.
- Add `escalation_triggers` for fact patterns that require a human lawyer.
- Re-run the evaluation checklist in
  [docs/reliability.md](../docs/reliability.md) after changes.
- After adding or renaming a skill folder, run `bash scripts/link_skills.sh` so
  the `.claude/skills/` symlink is created.

## Related

[README](../README.md) · [Documentation index](../docs/README.md) ·
[Reliability model](../docs/reliability.md)
