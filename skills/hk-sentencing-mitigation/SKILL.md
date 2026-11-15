---
name: hk-sentencing-mitigation
description: |
  Prepare a Hong Kong plea in mitigation and sentencing submission. Use after
  conviction or a guilty plea. Identifies the statutory maximum, guideline
  authorities, aggravating and mitigating factors, totality, and sentence
  options. Produces a structured mitigation outline with verified citations.
argument-hint: "[offence + conviction basis + personal circumstances]"
legal_frame: hk
last_reviewed: 2026-11
version: 1.0.0
risk_level: high
trigger_phrases:
  - 求情
  - 判刑
  - 量刑
  - 輕判
  - sentencing
  - mitigation
  - plea in mitigation
  - 判刑上訴
  - 社會服務令
mcp_tools:
  - search_legislation
  - get_section
  - search_cases
  - get_case
  - get_case_paragraphs
  - verify_citation
---

# HK Sentencing Mitigation

> **Not legal advice.** Sentence levels are fact-specific. Retrieve the current
> maximum, any statutory minimum, and the leading guideline authorities.

## Step 1 — Establish the sentencing framework

- Offence provision and maximum penalty (`get_section`).
- Any statutory minimum, mandatory sentence, or prescribed sentencing option.
- The court's sentencing powers and any relevant ordinance.
- Whether the offence is a "specified offence" or subject to a guideline.
- Whether the defendant is a juvenile/young person (verify the Juvenile
  Offenders Ordinance, Cap. 226, and related provisions).
- Whether a psychiatric/medical disposal is available (Mental Health Ordinance,
  Cap. 136).

## Step 2 — Identify guideline authorities

Use `search_cases` with the offence name, "sentencing", "guideline", "tariff",
and the relevant court. Retrieve the key paragraphs. Record:
- the guideline case and court;
- the starting point / range;
- aggravating and mitigating factors identified by the court;
- whether the guideline has been updated or distinguished.

Do not state a sentence range without a verified source.

## Step 3 — Aggravating factors

Consider, with evidence:
- premeditation, planning, sophistication;
- violence, weapon, vulnerable victim;
- breach of trust;
- multiple victims / repeated conduct;
- financial loss and restitution;
- offence committed on bail or while subject to a court order;
- criminal record and previous similar offences;
- gang/organised crime involvement;
- abuse of position;
- vulnerable victim / domestic context;
- public interest considerations;
- any statutory aggravating factor.

## Step 4 — Mitigating factors

Consider, with evidence:
- guilty plea and its timing (verify the current discount practice);
- remorse and insight;
- cooperation with authorities;
- restitution / compensation;
- young age / immaturity;
- mental health, cognitive impairment, addiction;
- physical health / terminal illness;
- family hardship, sole carer, dependants;
- employment, education, community service, stable history;
- delay and its effect;
- time on remand;
- conditions in custody;
- prospect of rehabilitation;
- support network and treatment plan.

## Step 5 — Sentence options

- Immediate imprisonment.
- Suspended sentence (verify availability and length limits).
- Community service order (verify eligibility and hours).
- Probation order (verify eligibility and conditions).
- Reformative / training centre (young persons).
- Fine / costs / compensation order.
- Hospital order / psychiatric disposal.
- Conditional discharge / bind-over.
- Combination orders where permitted.

## Step 6 — Mitigation outline

```
IN THE [COURT] OF THE HONG KONG SPECIAL ADMINISTRATIVE REGION
CASE NO.:
HKSAR v [NAME]

PLEA IN MITIGATION

A. The offence and plea
B. Personal background and circumstances
C. The offence circumstances (without minimizing)
D. Remorse, insight and rehabilitation
E. Positive factors: employment, family, community, treatment
F. Time in custody / remand
G. Authorities and sentencing range
H. Proposed sentence / order
I. Conclusion
```

Attach:
- antecedent statement and corrections;
- plea mitigation letters;
- employment/school records;
- medical/psychiatric/psychological reports;
- treatment or rehabilitation plan;
- compensation/restitution evidence;
- family/dependant evidence.

## Step 7 — Check totality and parity

- If multiple offences, apply the totality principle; identify the overall
  criminality and avoid double counting.
- Compare co-defendants and ensure parity where appropriate.
- Consider concurrent vs consecutive sentences and the statutory limits.
- Record the proposed structure and the arithmetic.

## Step 8 — After sentence

- Explain the sentence and its consequences to the client.
- Diarise appeal/review deadlines.
- If the sentence is arguably wrong in principle or manifestly excessive,
  refer to `hk-appeal`.
- Explain licence, supervision, and breach consequences.

## Red flags

- Citing a guideline case without checking the current range.
- Treating a first-instance sentencing decision as a guideline.
- Double counting the same fact as aggravating and as an element of the offence.
- Promising a suspended sentence or community service.
- Ignoring immigration, professional, or employment consequences.
