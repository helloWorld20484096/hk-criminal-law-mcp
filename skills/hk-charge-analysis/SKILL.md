---
name: hk-charge-analysis
description: |
  Analyse a Hong Kong criminal charge element by element. Use when reviewing a
  charge sheet, summons, indictment, or proposed charge. Identifies the offence
  provision, extracts actus reus and mens rea, maps available defences, checks
  venue/penalty/limitation, and produces an elements grid with verified sources.
argument-hint: "[charge + provision + facts]"
legal_frame: hk
last_reviewed: 2026-11
version: 1.0.0
risk_level: high
trigger_phrases:
  - 控罪分析
  - 控罪元素
  - 罪名
  - charge analysis
  - elements of offence
  - 告票
  - 公訴書
  - indictment
  - 罪名成立
mcp_tools:
  - search_legislation
  - get_section
  - statute_history
  - search_cases
  - get_case
  - get_case_paragraphs
  - verify_citation
  - verify_citations
---

# HK Charge Analysis

> **Not legal advice.** Always retrieve the current offence provision and
> check the penalty, venue, and any statutory defences before advising.

## Step 1 — Read the charge precisely

Record:
- the offence label used by the prosecution;
- the ordinance and section;
- the particulars (date, place, victim, property, amount, conduct);
- whether the charge is joint, alternative, or duplicitous;
- the court and mode of trial;
- the maximum penalty and any mandatory minimum.

## Step 2 — Retrieve the provision

Use `search_legislation` and `get_section`. If the alleged offence date is not
today, also use `statute_history` to retrieve the provision in force on that
date. Capture:
- the heading and subsection structure;
- definitions in the interpretation section;
- any reverse burden or statutory presumption;
- any statutory defence or exception;
- penalty and venue provisions;
- related offences and alternative charges.

Do not rely on the offence label alone. The same label can appear in several
ordinances with different elements and penalties.

## Step 3 — Extract the elements

For each element, state:
- the act or omission (actus reus);
- the mental element (mens rea), including knowledge, intention, recklessness,
  dishonesty, or negligence;
- any circumstance element (e.g. property belonging to another, lack of
  consent, public place, official capacity);
- any consequence element;
- who must prove it and to what standard;
- the source (Cap./section/subsection).

Use this grid:

| # | Element | Type | Source | Prosecution evidence | Defence response | Status |
|---|---|---|---|---|---|---|
| 1 | ... | actus reus | Cap. X s.Y(1) | ... | ... | disputed/admitted |
| 2 | ... | mens rea | Cap. X s.Y(1) | ... | ... | ... |

## Step 4 — Identify available defences

Consider and verify:
- denial / alibi;
- mistake of fact;
- lack of the required mental element;
- lawful authority or excuse;
- self-defence / prevention of crime (verify the applicable ordinance and
  common-law test);
- duress / necessity;
- automatism / involuntary intoxication;
- insanity / diminished responsibility (verify the Mental Health Ordinance,
  Cap. 136, and the relevant common-law tests);
- limitation periods;
- abuse of process / delay;
- entrapment (as a discretionary stay, not a substantive defence);
- statutory defences in the offence provision.

## Step 5 — Procedural checks

- Is the court the correct venue?
- Is the charge duplicitous or bad for duplicity?
- Is there a time limit for prosecution?
- Is the charge properly particularised?
- Are there alternatives that should be preferred or added?
- Is joinder/severance an issue?
- Is the offence a "specified offence" or subject to special sentencing rules?
- Are there reporting restrictions or anonymity orders?

## Step 6 — Case law

Use `search_cases` for the offence and each disputed element. Retrieve the
paragraphs that define the element. Prefer CFA/CA authority. Check whether a
later case doubts or distinguishes the authority (`note_up`).

## Output template

```
CHARGE: [label] — Cap. [X] s.[Y]
COURT/VENUE: [ ]
MAXIMUM PENALTY: [ ]
ELEMENTS GRID: [table]
DEFENCES: [defence | source | evidence needed | viability]
PROCEDURAL ISSUES: [ ]
AUTHORITIES: [citation | paragraph | proposition | status]
EVIDENCE GAPS: [ ]
RECOMMENDED NEXT STEPS: [ ]
VERIFICATION: [sources retrieved; anything unverified]
```

## Red flags

- The prosecution has not identified the subsection.
- The particulars do not match the elements.
- The mental element is assumed rather than pleaded/evidenced.
- A "strict liability" assertion without checking the provision and case law.
- A penalty stated without checking the current version.
