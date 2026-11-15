---
name: hk-defense-strategy
description: |
  Build and stress-test a Hong Kong criminal defence strategy. Use after the
  case file review, when deciding plea vs trial, charge negotiation, legal
  arguments, evidence strategy, and client advice. Produces a decision memo
  with options, risks, and a client-instruction log.
argument-hint: "[charges + case theory + client objectives]"
legal_frame: hk
last_reviewed: 2026-11
version: 1.0.0
risk_level: high
trigger_phrases:
  - 辯護策略
  - 認罪
  - 不認罪
  - 審訊
  - defence strategy
  - plea
  - trial strategy
  - 抗辯
  - 認罪協商
mcp_tools:
  - search_legislation
  - get_section
  - statute_history
  - search_cases
  - get_case
  - get_case_paragraphs
  - note_up
  - case_graph
  - authority_ranking
  - verify_citation
  - verify_citations
---

# HK Defence Strategy

> **Not legal advice.** The client decides the plea. The lawyer's role is to
> give accurate advice, identify the risks, and record the instructions.

## Step 1 — Confirm the client's instructions

Record:
- the client's account of the facts;
- what the client admits and denies;
- the client's objectives (acquittal, lesser charge, non-custodial sentence,
  speed, minimizing publicity, protecting family/employment);
- the client's willingness to give evidence;
- any language, health, or vulnerability issues;
- whether the client understands the consequences of a conviction (including
  immigration, employment, professional, and travel consequences).

## Step 2 — Assess the prosecution case

For each charge:
- retrieve the provision and elements (`hk-charge-analysis`);
- if the alleged offence date is not today, use `statute_history` to check the
  law in force on that date;
- identify the strongest and weakest elements;
- identify the evidence that proves each element;
- identify evidence that is inadmissible, unreliable, or incomplete;
- identify disclosure gaps.

## Step 3 — Identify defence tracks

Evaluate each track and record its prospects and risks:

1. **No case to answer** — is there evidence on which a reasonable tribunal
   could convict? Identify the precise gap.
2. **Element denial** — which element fails?
3. **Positive defence** — alibi, self-defence, mistake, duress, lawful excuse,
   insanity, automatism. Verify the legal test and the evidential burden.
4. **Exclusion of evidence** — voluntariness, unfairness, illegality, chain of
   custody, expert reliability. Verify the exclusion test.
5. **Abuse of process** — delay, manipulation, breach of undertaking. This is a
   discretionary remedy; assess realistically.
6. **Charge negotiation** — alternative charge, withdrawal of counts, agreed
   facts. Confirm the prosecution's policy and the court's role.
7. **Plea** — plea bargain is limited in Hong Kong; the court retains sentencing
   discretion. Advise on the realistic sentencing range and the guilty-plea
   discount, verified against current authority.

## Step 4 — Evidence strategy

- Defence witnesses: who, what, why credible, availability, risks.
- Expert evidence: need, scope, funding, timing, duties to the court.
- Client evidence: benefits and risks of giving evidence; prepare thoroughly.
- Cross-examination themes: identify the 3–5 themes that matter.
- Admissions: consider formal admissions to narrow issues.
- Alibi: check notice requirements and timing; verify the current procedure.
- Bad character / similar fact / hearsay: verify admissibility and notice.

## Step 5 — Decision memo

```
MATTER:
CHARGES:
CLIENT OBJECTIVES:
PROSECUTION CASE (strengths/weaknesses):
OPTION A — [plea / track] | prospects | risks | sentence range | client view
OPTION B — [trial / track] | prospects | risks | evidence needed | client view
OPTION C — [negotiation / application] | prospects | risks
RECOMMENDATION: [with reasons]
INFORMATION NEEDED: [ ]
DEADLINES: [ ]
CLIENT INSTRUCTIONS: [date | advice given | decision | signed]
```

## Step 6 — Ethical boundaries

- Do not advise the client to give false evidence.
- If the client insists on a account you cannot advance, consider withdrawal
  in accordance with professional rules; seek guidance.
- Do not mislead the court or conceal adverse authority.
- Do not pressure the client into a plea.
- Record the advice and the client's decision contemporaneously.

## Escalation

- Instruct counsel for trial, complex legal arguments, or serious offences.
- Obtain a second opinion on forensic/expert issues.
- Consider an independent psychiatric or psychological assessment where
  vulnerability or fitness is in issue.
