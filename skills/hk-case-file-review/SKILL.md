---
name: hk-case-file-review
description: |
  Review a Hong Kong criminal case file. Use after receiving prosecution
  papers, witness statements, exhibits, video, expert reports, or disclosure.
  Builds an evidence matrix, identifies inconsistencies and legal gaps, and
  produces disclosure and further-inquiry requests.
argument-hint: "[case + charges + materials received]"
legal_frame: hk
last_reviewed: 2026-11
version: 1.0.0
risk_level: high
trigger_phrases:
  - 閱卷
  - 案卷審查
  - 證據分析
  - 文件披露
  - case file review
  - evidence review
  - disclosure
  - 證人陳述
  - 呈堂證物
mcp_tools:
  - search_legislation
  - get_section
  - statute_history
  - search_cases
  - get_case
  - get_case_paragraphs
  - case_graph
  - verify_citation
  - verify_citations
---

# HK Case File Review

> **Not legal advice.** Work from the actual materials. Do not fill gaps with
> assumptions; record every missing item as a further inquiry.

## Step 1 — Build the index

Create a document index with:
- production number / bundle reference;
- date and author;
- document type (witness statement, exhibit, report, video, transcript,
  correspondence, forensic report, medical report, cautioned statement);
- page/paragraph count;
- whether it is served, unused, or missing.

Log the date and time of receipt. Preserve the original files.

## Step 2 — Prosecution case theory

Summarise in one page:
- the charge(s) and elements;
- the prosecution's narrative;
- the evidence said to prove each element;
- the witnesses and their roles;
- the exhibits and what they prove;
- the inferences the prosecution asks the court to draw.

## Step 3 — Evidence matrix

| Element | Prosecution evidence | Source | Weakness | Defence evidence | Status |
|---|---|---|---|---|---|
| ... | ... | statement/exhibit | ... | ... | ... |

For each witness:
- date, duration and conditions of observation;
- lighting, distance, obstruction, duration;
- prior statements and inconsistencies;
- relationship to the accused/complainant;
- motive to lie or favour;
- special needs / vulnerability;
- whether the witness was interviewed under caution or cautioned.

## Step 4 — Identification evidence

If identification is in issue:
- Was there an identification parade or photobook? Verify the procedure and
  whether it was fairly conducted.
- Record the witness's description before and after seeing the defendant.
- Check CCTV quality, time stamps, continuity, and whether the footage has been
  enhanced.
- Consider Turnbull-style warnings and Hong Kong authority; retrieve the
  actual cases, do not rely on the label.

## Step 5 — Admissions, confessions, and interviews

- Was the defendant cautioned? When and by whom?
- Was the interview recorded? Is there a full record or only a summary?
- Was the defendant offered a lawyer, interpreter, or appropriate adult?
- Are there allegations of inducement, threat, oppression, or violence?
- Is the statement signed/initialled? Are corrections initialled?
- Is there a voluntariness challenge or an application to exclude?
- Verify the current admissibility rules in the Criminal Procedure Ordinance
  (Cap. 221) and the Evidence Ordinance (Cap. 8), plus case law.

## Step 6 — Exhibit and continuity

- Chain of custody for drugs, weapons, phones, documents, and forensic samples.
- Seals, labels, signatures, storage, and transfer records.
- CCTV/DVD hash values and copies.
- Photographs and scene sketches.
- Financial records and bank statements.
- Electronic evidence: extraction reports, metadata, device integrity.

## Step 7 — Disclosure and unused material

List:
- statements of witnesses not called;
- interview notes and rough notes;
- CCTV and audio not relied on;
- forensic work sheets and raw data;
- communications between investigators and experts;
- documents that undermine the prosecution case or assist the defence.

Frame requests by reference to the material and why it is relevant; verify the
applicable disclosure principles in HK authority.

## Step 8 — Legal audit

For each charge:
- retrieve the provision and check the elements;
- use `statute_history` to check the provision in force on the date of the
  alleged offence, not only the current text;
- identify elements not evidenced;
- identify defences raised by the evidence;
- check whether the charge is duplicitous or wrongly particularised;
- check limitation, venue, and jurisdiction.

## Output template

```
CASE: [name] | [court] | [case no.]
MATERIALS REVIEWED: [index summary]
PROSECUTION THEORY: [one page]
EVIDENCE MATRIX: [table]
KEY INCONSISTENCIES: [numbered list with source references]
LEGAL GAPS: [element | missing evidence | authority]
DISCLOSURE REQUESTS: [item | relevance | deadline]
FURTHER INQUIRIES: [expert | CCTV | witness | records]
DEFENCE OPPORTUNITIES: [ ]
RISKS: [ ]
NEXT STEPS: [ ]
```

## Red flags

- A statement that is unsigned, undated, or adopted only by a summary.
- A confession without a recorded interview or appropriate adult.
- CCTV with no continuity evidence.
- An expert report that does not disclose the underlying data.
- A charge that depends on a definition not in the served papers.
