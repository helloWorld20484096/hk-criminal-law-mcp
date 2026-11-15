---
name: hk-trial-defense
description: |
  Prepare and run a Hong Kong criminal trial defence. Use for trial planning,
  opening, examination-in-chief, cross-examination, no-case submissions,
  closing, and post-verdict steps. Produces a trial plan and cross-examination
  matrix tied to the elements and the evidence.
argument-hint: "[charges + trial date + defence theory]"
legal_frame: hk
last_reviewed: 2026-11
version: 1.0.0
risk_level: high
trigger_phrases:
  - 審訊
  - 庭審
  - 盤問
  - 結案陳詞
  - trial
  - cross-examination
  - closing submissions
  - 無需答辯
  - 開庭
mcp_tools:
  - search_legislation
  - get_section
  - search_cases
  - get_case
  - get_case_paragraphs
  - verify_citation
---

# HK Trial Defence

> **Not legal advice.** Trial tactics must be adapted to the forum, the judge,
> the evidence, and the client's instructions.

## Step 1 — Trial plan

- Charges and elements (from `hk-charge-analysis`).
- Prosecution witnesses and exhibits.
- Defence witnesses and exhibits.
- Agreed facts / formal admissions.
- Issues in dispute.
- Legal objections and applications (evidence, disclosure, abuse of process).
- Timetable and estimated length.
- Client's evidence: decide and prepare.

## Step 2 — Opening

Keep it short and accurate:
- identify the real issues;
- state what the evidence will show;
- do not over-promise or attack witnesses before they testify;
- avoid arguments that require evidence not yet admitted.

## Step 3 — Examination-in-chief

- Take the witness through the relevant facts chronologically.
- Use open questions; avoid leading except on formal/matters not in dispute.
- Introduce documents/exhibits properly.
- Do not elicit inadmissible evidence or invite speculation.
- Make notes of concessions and inconsistencies.

## Step 4 — Cross-examination matrix

| Witness | Element/issue | Objective | Key documents | Planned questions | Risk |
|---|---|---|---|---|---|
| ... | ... | ... | ... | ... | ... |

Rules:
- Cross-examination must be relevant and fair.
- Put the defence case to the witness where required.
- Do not ask a question to which you do not know the answer unless the risk is
  deliberate and justified.
- Do not bully, argue, or comment in questions.
- Avoid multiple questions at once.
- Use short, leading, closed questions for concessions.
- Stop when you have the point.

## Step 5 — No-case submission

At the close of the prosecution case:
- identify the element(s) with no or insufficient evidence;
- apply the legal test (verify the current authority);
- do not argue credibility unless the evidence is inherently incredible;
- be prepared for the judge to call on the defence immediately.

## Step 6 — Defence case

- Advise the client on giving evidence and the consequences of not doing so.
- Prepare the client for cross-examination.
- Call witnesses in a logical order.
- Tender defence exhibits through the proper witness.
- Avoid reopening the prosecution case unfairly.

## Step 7 — Closing submissions

Structure:
1. The charge and the burden/standard of proof.
2. The elements and which are disputed.
3. The evidence on each element.
4. The inconsistencies and reliability problems.
5. The defence evidence and why it is credible.
6. The legal authorities.
7. The verdict sought.

Do not misstate evidence. Refer to transcript/page references where available.

## Step 8 — After verdict

- If acquitted: explain costs, release, and records.
- If convicted: move to sentencing preparation (`hk-sentencing-mitigation`).
- Diarise appeal deadlines (`hk-appeal`).
- Explain the verdict and its consequences in plain language.

## Escalation

- Instruct counsel for jury trials, complex expert evidence, or novel legal
  issues.
- Consider a separate application if the trial is unfair or disclosure is
  incomplete.
