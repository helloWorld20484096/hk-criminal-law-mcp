---
name: hk-criminal-intake
description: |
  First response and client intake for a Hong Kong criminal matter. Use when a
  client/relative first reports an arrest, police investigation, summons,
  charge, or upcoming court date. Triages urgency, identifies the forum,
  captures facts and deadlines, and produces an action list.
argument-hint: "[who is affected + what happened + current stage]"
legal_frame: hk
last_reviewed: 2026-11
version: 1.0.0
risk_level: high
trigger_phrases:
  - 被捕
  - 警署
  - 拘捕
  - 刑事調查
  - 收到告票
  - 上庭
  - arrested
  - police station
  - summons
  - criminal charge
  - 保釋
mcp_tools:
  - search_legislation
  - get_section
  - search_cases
  - get_case
  - verify_citation
---

# HK Criminal Intake

> **Not legal advice.** If the person is in custody or has an imminent court
> date, prioritize immediate human legal assistance.

## Urgency triage (first 5 minutes)

Ask and record:

- Is the person **in custody**? Where (police station / ICAC / customs /
  immigration / correctional facility)?
- Has there been an **arrest, caution, interview, search, or charge**?
- Is there a **court date** or **bail reporting condition**?
- Is the person a **child or young person** (check the statutory age
  definitions in the Juvenile Offenders Ordinance, Cap. 226), or an adult with
  a cognitive, mental-health, or language vulnerability?
- Is any **deadline** within 7 days (bail renewal, court appearance, appeal,
  legal aid application)?
- Are there **media**, **immigration**, or **national-security** dimensions?

If any answer is yes, escalate immediately. Do not wait for a full intake.

## Intake fields

1. **Person**: name, age/date of birth, address, language, immigration status,
   school/employment, family contact, vulnerabilities.
2. **Event**: date/time/place; arresting authority; offences mentioned;
   property seized; words used by police; whether cautioned; whether interviewed.
3. **Custody/bail**: location, bail terms, surety, reporting conditions,
   next appearance.
4. **Proceedings**: court, case number, charge sheet, next hearing, prosecutor.
5. **Evidence**: documents received, witness names, CCTV/phone/video, medical
   records, receipts, messages.
6. **Objectives**: immediate release, preserve position, avoid self-
   incrimination, protect employment/family, prepare defence.

## Workflow

1. **Open a matter file** and record the time of instructions.
2. **Conflict check** before discussing the merits.
3. **Explain the limited scope** of the engagement and who is the client.
4. **Identify the offence(s)**: use `search_legislation` and `get_section` to
   retrieve the provision. Do not guess the charge from the police label.
5. **Identify the forum and procedure**: Magistrates' Court, District Court,
   CFI, or appeal court. Verify the relevant ordinance.
6. **Protect deadlines**: diarise every date; confirm court listing.
7. **Evidence preservation**: advise the client to retain phones, messages,
   receipts, medical records, and CCTV contacts; do not delete anything.
8. **Bail assessment**: if in custody, run `hk-bail-application`.
9. **Legal aid / representation**: check eligibility and the application
   deadline; record the client's choice.
10. **Next steps**: written action list with owner and date.

## Do not

- Advise the client to lie, destroy evidence, or contact witnesses improperly.
- Discuss the merits with the complainant or witnesses.
- Promise an outcome or a bail result.
- Assume the police caution/interview rules without checking the current law.
- Discuss privileged information with family members without the client's consent.

## Output template

```
MATTER: [name] | [date/time] | [source of instructions]
URGENCY: [red / amber / green] — [reason]
CUSTODY/BAIL: [details]
CHARGES MENTIONED: [police label] -> [verified provision(s)]
COURT/DATE: [forum] | [date] | [case number]
KEY FACTS: [chronology]
EVIDENCE TO PRESERVE: [list]
IMMEDIATE ACTIONS: [action | owner | deadline]
NEXT APPOINTMENT: [date/time]
ESCALATION: [senior lawyer / counsel / interpreter / medical]
VERIFICATION: [sources retrieved]
```
