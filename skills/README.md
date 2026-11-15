# Defence skills

These are Claude Code skill documents (`SKILL.md`) for Hong Kong criminal law
and defence. They are deliberately process-heavy: they tell the model what to
retrieve, what to verify, and what to record, rather than asserting legal rules
from memory.

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

Project-scoped: the repository's `.claude/skills/` links to these folders, so
Claude Code discovers them when the project is open.

If you copy a skill elsewhere, keep the `SKILL.md` frontmatter intact. The
skills assume the `hk-criminal-law` MCP server is available.

## Editing

- Keep the frontmatter `name` identical to the folder name.
- Keep `legal_frame: hk`.
- Do not add a legal proposition without a source path: either a Cap./section
  retrievable by the MCP, or a neutral citation with a paragraph.
- Add `escalation_triggers` for fact patterns that require a human lawyer.
- Re-run the evaluation checklist in `docs/reliability.md` after changes.
