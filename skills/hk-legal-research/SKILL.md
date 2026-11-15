---
name: hk-legal-research
description: |
  Hong Kong criminal law research protocol. Use when a question requires
  statutes, case law, sentencing authorities, or verification of a citation.
  Enforces primary-source retrieval through the HK Criminal Law MCP and marks
  every unverified proposition.
argument-hint: "[legal issue or citation]"
legal_frame: hk
last_reviewed: 2026-11
version: 1.0.0
risk_level: high
trigger_phrases:
  - 香港法律研究
  - HK legal research
  - 案例检索
  - 法條查詢
  - 判刑參考
  - verify citation
  - 查案例
  - 查法例
mcp_tools:
  - search_legislation
  - get_section
  - get_section_range
  - statute_history
  - list_section_versions
  - search_cases
  - get_case
  - get_case_paragraphs
  - note_up
  - verify_citation
  - verify_citations
  - doctrine_research
  - authority_ranking
  - case_graph
  - corpus_status
---

# HK Legal Research

> **Not legal advice.** This protocol produces research notes for a qualified
> lawyer to review. Never present an unverified citation as authority.

## Non-negotiable rules

1. **No citation from memory.** Every Cap./section and every neutral citation
   must be checked with `verify_citation` or retrieved with `get_section` /
   `get_case`. For a whole passage, use `verify_citations`.
2. **Read the operative text.** A search snippet is not the provision. Retrieve
   the section or paragraph before relying on it.
3. **Record provenance.** Keep the official URL, version date, and retrieval
   date for every source.
4. **Separate ratio from obiter.** State which court, which level, and whether
   the passage is part of the ratio.
5. **Check currency.** If the alleged offence, charge, or hearing date matters,
   retrieve the provision in force on that date with `statute_history`. If no
   historical version is available, say so; never use current text as if it were
   the historical law.
6. **Mark uncertainty.** If a source cannot be retrieved, write
   `[UNVERIFIED — source not retrieved]` and explain what is missing.

## Workflow

1. **Frame the issue.** Identify the legal question, the offence/provision, the
   procedural stage, the relevant date, and the desired outcome.
2. **Legislation first.** Use `search_legislation` with 2–5 precise terms and
   the relevant Cap. filter. Retrieve the full section with `get_section`.
   Use `get_section_range` when a range is needed. If the relevant date is not
   today, use `statute_history`; use `list_section_versions` to see available
   versions.
3. **Cases second.** Use `search_cases` or `doctrine_research` with the
   provision name, offence, and legal concept. Use `authority_ranking` to sort
   leads by court level and cached note-up. Prefer CFA and CA authority; treat
   CFI/DC decisions as persuasive unless binding in the relevant court.
4. **Read the paragraphs.** Use `get_case_paragraphs` for the passages relied
   on. Quote the paragraph number. Do not paraphrase a holding without the
   paragraph.
5. **Check treatment.** Use `note_up` for cases and `case_graph` for outgoing/
   incoming citations. For legislation, check the version date and any
   amendment/source notes.
6. **Verify the draft.** Run `verify_citations` over the final passage to catch
   every citation, including ones added late.
7. **Build the authority table.** Columns: proposition | source | paragraph/
   subsection | court/level | status | verified?
8. **Answer and flag.** Give the answer, the strongest contrary authority, and
   the gaps. End with the verification table.

## Authority hierarchy (Hong Kong)

- CFA judgments bind all courts.
- CA judgments bind the CFI, District Court and Magistrates.
- CFI judgments bind the District Court and Magistrates; they are persuasive on
  other CFI judges.
- District Court decisions are persuasive on Magistrates and other District
  Court judges.
- Magistrates' decisions are persuasive only.
- Pre-1997 Privy Council authority may remain persuasive; verify its status.
- Obiter dicta and first-instance summaries are not binding.

## Output template

```
ISSUE
[one paragraph]

SHORT ANSWER
[answer with confidence: high / medium / low]

LEGISLATION
- Cap. X s.Y — [heading] — [version date] — [official URL]
  Operative text: "[quote]"

AUTHORITIES
- [citation] — [court] — [paragraph] — [proposition]
  Status: binding / persuasive / doubted / overruled

ANALYSIS
[apply the sources to the facts; identify contrary authority]

GAPS / VERIFICATION
- [UNVERIFIED] ...
- [UNVERIFIED] ...

RESEARCH LOG
- query | source | retrieved at | result
```

## Red flags

- A case citation that the MCP cannot retrieve.
- A section number that does not match the heading.
- A judgment that has been reversed or is under appeal.
- Relying on a newspaper summary or a secondary blog.
- Citing an old edition of an ordinance without checking amendments.
