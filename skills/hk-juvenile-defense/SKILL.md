---
name: hk-juvenile-defense
description: |
  Hong Kong juvenile criminal defence workflow. Use when the accused is a
  child or young person (verify the statutory age definitions in the Juvenile
  Offenders Ordinance, Cap. 226). Covers age ascertainment, parental/guardian involvement,
  appropriate adult safeguards, bail, court forum, sentencing options, privacy,
  and education/welfare considerations.
argument-hint: "[age + allegation + current stage]"
legal_frame: hk
last_reviewed: 2026-11
version: 1.0.0
risk_level: high
trigger_phrases:
  - 少年犯
  - 未成年
  - 兒童
  - 青少年
  - juvenile
  - young person
  - 兒童法庭
  - 感化令
  - 教導所
mcp_tools:
  - search_legislation
  - get_section
  - search_cases
  - get_case
  - get_case_paragraphs
  - verify_citation
---

# HK Juvenile Defence

> **Not legal advice.** Age determines forum, safeguards, and sentencing
> powers. Verify the exact age and the current statutory definitions.

## Step 1 — Establish age and status

- Date of birth and age at the date of the alleged offence and at each
  procedural step.
- Whether the person is a "child" or "young person" under the Juvenile
  Offenders Ordinance (Cap. 226) — retrieve the definitions.
- Immigration status, school status, family/guardian situation.
- Any care/protection order, social worker involvement, or special educational
  needs.

## Step 2 — Safeguards

Verify the current requirements for:
- notification of a parent/guardian;
- an appropriate adult during interview and proceedings;
- legal representation and legal aid;
- privacy/reporting restrictions;
- separate court facilities and procedures;
- interpreter and communication needs;
- vulnerability and fitness to participate.

If a safeguard was not observed, record it as a potential procedural issue and
investigate the remedy.

## Step 3 — Bail

Apply `hk-bail-application`, with additional attention to:
- suitable residence and supervision;
- parental/guardian surety or undertaking;
- school/employment engagement;
- curfew, reporting, and non-contact conditions;
- welfare reports and social worker support;
- availability of bail accommodation;
- the impact of custody on education and mental health.

## Step 4 — Forum and procedure

- Identify whether the case is in the Juvenile Court, Magistrates' Court,
  District Court, or CFI.
- Check the transfer/committal rules and the court's sentencing powers.
- Verify whether reporting restrictions apply and whether any exception is
  sought.
- Prepare the client and family for the hearing; explain the process.

## Step 5 — Sentencing and disposals

Verify availability and eligibility for:
- absolute/conditional discharge;
- fine;
- probation order;
- community service order;
- reformative training centre;
- training centre;
- detention centre;
- youth prison;
- hospital order (Mental Health Ordinance, Cap. 136);
- other welfare-based disposals.

Obtain:
- school reports;
- welfare/social investigation reports;
- psychological/psychiatric reports;
- family and community support evidence;
- apology/restitution evidence where appropriate.

## Step 6 — Output template

```
YOUNG PERSON: [initials] | DOB | age at offence | age now
ALLEGATION: [charge | Cap./section]
STAGE: [police / juvenile court / other]
SAFEGUARDS: [parent notified? appropriate adult? legal representation?]
BAIL: [status | proposed conditions | surety]
FORUM: [court | transfer issues]
VULNERABILITIES: [education | mental health | care | language]
SENTENCING OPTIONS: [option | eligibility | evidence needed]
PROCEDURAL ISSUES: [ ]
NEXT STEPS: [ ]
```

## Escalation

- Instruct counsel experienced in juvenile work.
- Obtain an independent psychological/psychiatric assessment where needed.
- Involve a social worker or youth advocacy service with consent.
- Consider whether a care/protection referral is appropriate.
