---
name: hk-appeal
description: |
  Hong Kong criminal appeal workflow. Use after conviction or sentence when
  advising on appeal routes, leave, grounds, deadlines, fresh evidence, bail
  pending appeal, and the Court of Appeal/Court of Final Appeal. Produces a
  grounds-of-appeal skeleton with verified authorities.
argument-hint: "[conviction/sentence + court + date + proposed grounds]"
legal_frame: hk
last_reviewed: 2026-11
version: 1.0.0
risk_level: high
trigger_phrases:
  - 上訴
  - 刑事上訴
  - 定罪上訴
  - 判刑上訴
  - appeal
  - leave to appeal
  - 終審法院
  - 上訴理由
mcp_tools:
  - search_legislation
  - get_section
  - search_cases
  - get_case
  - get_case_paragraphs
  - note_up
  - verify_citation
---

# HK Criminal Appeal

> **Not legal advice.** Appeal routes and time limits are strict. Verify the
> current ordinance, practice direction, and court guidance immediately.

## Step 1 — Identify the route

- Magistrates' Court -> Court of First Instance (appeal by way of rehearing or
  case stated — verify which applies).
- District Court / Court of First Instance -> Court of Appeal.
- Court of Appeal -> Court of Final Appeal (leave required).
- Sentence appeals follow the same hierarchy, subject to leave requirements.
- Interlocutory / bail / procedural decisions may have separate routes.

Record:
- the decision and date;
- the court and judge;
- the order made;
- the appeal route and the deadline;
- whether leave is required and from whom;
- whether bail pending appeal is available.

## Step 2 — Obtain the record

- transcript / notes of evidence;
- reasons for verdict / sentencing remarks;
- exhibits and admitted facts;
- judge's directions (jury trials);
- correspondence and disclosure history;
- any reserved judgment.

## Step 3 — Identify grounds

Common grounds (verify each against the record):
1. **Misdirection of law** — wrong legal test, wrong element, wrong burden.
2. **No or insufficient evidence** — a verdict that no reasonable tribunal could
   reach.
3. **Unreasonable verdict** — inconsistent with the evidence.
4. **Wrongful admission/exclusion of evidence** — voluntariness, hearsay,
   identification, expert evidence.
5. **Procedural unfairness** — disclosure, opportunity to respond, bias,
   interpreter, conduct of the trial.
6. **Ineffective representation** — only in exceptional cases; assess carefully.
7. **Fresh evidence** — new evidence not available at trial; explain why it
   could not have been obtained and its likely impact.
8. **Sentence** — wrong in principle, manifestly excessive/inadequate, failure
   to consider relevant matters, parity, totality.
9. **Abuse of process** — delay, manipulation, breach of undertaking.

For each ground, state:
- the error;
- where it appears in the record;
- the legal authority;
- why it matters to the verdict/sentence;
- the prejudice to the defendant.

## Step 4 — Leave and procedure

- Prepare the notice of appeal / application for leave within the deadline.
- Identify whether an extension of time is needed and the test for it.
- Prepare the appeal bundle and chronology.
- Consider whether to apply for bail pending appeal; verify the applicable
  factors and procedure.
- Confirm whether the appeal is against conviction, sentence, or both.

## Step 5 — Authorities

Use `search_cases` and `get_case_paragraphs` for each ground. Prefer CFA and CA
authority. Check subsequent treatment with `note_up`. Do not cite a case for a
proposition that the paragraph does not support.

## Output template

```
MATTER: [name] | [court] | [case no.] | [decision date]
ROUTE: [court] -> [appeal court] | leave required? | deadline
RECORD: [transcript/reasons/exhibits]
GROUNDS:
  1. [error] | [record reference] | [authority] | [prejudice]
  2. ...
FRESH EVIDENCE: [evidence | why not available | likely impact]
SENTENCE APPEAL: [error in principle | manifestly excessive | parity | totality]
BAIL PENDING APPEAL: [available? | factors | application]
NEXT STEPS: [notice | bundle | deadline | counsel]
VERIFICATION: [sources retrieved; anything unverified]
```

## Red flags

- Missing the deadline.
- A ground that repeats the trial argument without identifying an error.
- A fresh-evidence application without an explanation for the delay.
- Citing a sentencing guideline without checking the current range.
- Failing to obtain the full record before settling grounds.
