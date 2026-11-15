---
name: hk-bail-application
description: |
  Hong Kong bail application and review workflow. Use for police bail, bail in
  the Magistrates' Court, District Court or Court of First Instance, review of
  refusal/conditions, variation, sureties, and bail pending appeal. Produces a
  structured application and evidence checklist grounded in the current
  provisions and authorities.
argument-hint: "[stage + charge + custody history + grounds]"
legal_frame: hk
last_reviewed: 2026-11
version: 1.0.0
risk_level: high
trigger_phrases:
  - 保釋
  - 申請保釋
  - 保釋覆核
  - 保釋條件
  - 人事擔保
  - bail application
  - bail review
  - bail conditions
  - surety
  - 還押
mcp_tools:
  - search_legislation
  - get_section
  - search_cases
  - get_case
  - get_case_paragraphs
  - verify_citation
---

# HK Bail Application

> **Not legal advice.** Bail law is fact-sensitive and changes through case
> law. Retrieve the current provisions and leading authorities before advising.

## Step 1 — Identify the stage

- Police bail after arrest / release from custody.
- Bail in the Magistrates' Court.
- Bail in the District Court or Court of First Instance.
- Review of a refusal or condition (for example, the review mechanism in the
  Criminal Procedure Ordinance (Cap. 221), Part IA — verify the exact section
  and current text with `get_section`).
- Bail pending appeal or pending retrial.
- Breach / revocation / arrest for breach.

Record the decision-maker, the date, the reasons given, and the next available
review route. Verify time limits with the current ordinance and court practice.

## Step 2 — Gather the material

- Charge(s) and maximum penalty (use `search_legislation`).
- Prosecution case summary and evidence served.
- Custody history: date of arrest, first appearance, previous applications.
- Personal circumstances: age, residence, family, employment, education,
  community ties, health, immigration status.
- Criminal record/antecedents, if available.
- Proposed surety: identity, relationship, financial capacity, willingness,
  prior convictions, understanding of the obligations.
- Proposed conditions: reporting, curfew, residence, surrender of travel
  documents, non-contact, electronic monitoring (if available).
- Any vulnerability: juvenile, mental health, cognitive impairment, pregnancy,
  serious medical need, language barrier.

## Step 3 — Build the bail argument

Address each risk factor with evidence, not assertion:

| Risk | Prosecution concern | Defence response | Evidence |
|---|---|---|---|
| Flight | ties, means, travel documents | residence, family, employment, surrender | documents, surety |
| Reoffending | record, alleged conduct | stable history, conditions, treatment | record, medical |
| Interference | witnesses, complainant | non-contact, residence, reporting | undertakings |
| Delay | likely trial date | prejudice of custody, preparation | court dates |
| Strength of case | prosecution evidence | weaknesses, legal issues | case file |

Also address:
- Presumption of innocence and the right to liberty (verify Basic Law and Bill
  of Rights provisions with `get_section`; Bill of Rights Ordinance is Cap. 383).
- The court's duty to consider bail and the statutory factors in the current
  provision.
- Whether conditions are necessary and proportionate; propose the least
  restrictive package.
- Surety suitability and the amount; explain the surety's obligations.
- Any special rules for juveniles, national-security cases, or specific
  offences — verify, do not assume.

## Step 4 — Authorities

Use `search_cases` with terms such as the offence, "bail", "flight risk",
"conditions", "surety", and the relevant court. Retrieve the key paragraphs
with `get_case_paragraphs`. Prefer CFA and CA authority. Record:
- citation, court, paragraph, proposition, binding status, subsequent treatment.

Do not cite a bail case from a search snippet alone.

## Step 5 — Draft the application

```
IN THE [COURT] OF THE HONG KONG SPECIAL ADMINISTRATIVE REGION
CASE NO.: [ ]
BETWEEN: HKSAR v [NAME]

APPLICATION FOR BAIL / REVIEW OF BAIL

A. Introduction and procedural history
B. The charge and applicable penalty
C. Personal circumstances and community ties
D. The proposed surety and conditions
E. Response to the prosecution's objections
F. Legal principles and authorities
G. Conclusion and order sought
```

Attach:
- surety statement / identity and financial documents;
- residence proof, employment letter, school letter;
- medical/psychiatric reports;
- proposed conditions schedule;
- chronology of custody.

## Step 6 — Hearing preparation

- Confirm the prosecutor's objections and any updated evidence.
- Prepare a one-page chronology and a conditions table for the bench.
- Have the surety present or contactable.
- Prepare fallback conditions if the court is concerned about a specific risk.
- Record the outcome, reasons, and next review date.

## Escalation

Escalate to senior counsel if:
- the charge is very serious or carries a life sentence;
- national-security legislation is engaged;
- a juvenile or vulnerable adult is in custody;
- bail has been refused twice;
- there is a medical or humanitarian emergency.
