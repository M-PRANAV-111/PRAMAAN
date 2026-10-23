# Evidence-First AICTE Compliance Validation System

> **SIH 2026 · Problem Statement:** SIH26261 — AI-Powered Application Validation, Document Authentication and Regulatory Compliance Verification  
> **Status:** Proposal / prototype plan. No implementation, model training, integration, benchmark, or performance result is claimed in this document.  
> **Important:** Confirm the problem-statement ID, exact wording, safeguards, and applicable Approval Process Handbook clauses in the official SIH workspace before submission.

---

## 1. Executive Summary

AICTE approval applications may contain forms, affidavits, certificates, faculty information, intake figures, and infrastructure evidence. Reviewing each document separately can miss contradictions between files, expired evidence, missing requirements, and uncertainty about the issuing source.

This proposal is an **evidence-first compliance validation system** that checks an application against a versioned rulebook and produces findings that an authorized reviewer can inspect. Each finding should show the applicable rule, the extracted claim, the source document and page, the comparison or verification result, and any uncertainty.

The system combines five core capabilities:

1. **Versioned compliance rules** tied to approved source clauses.
2. **Claim–evidence traceability** linking extracted values to documents and page locations.
3. **Cross-document reconciliation** to identify missing, conflicting, and potentially inconsistent facts.
4. **Verification and forensic signals** that help reviewers assess evidence without treating a model score as proof of fraud.
5. **Compliance Repair Planner** that groups related deficiencies and suggests legitimate next steps, then reruns affected checks after corrected evidence is supplied.

The system is decision support only. It must not approve or reject an institution, declare a document fraudulent based only on AI, bypass access controls, or imply access to restricted government systems.

## 2. Problem and Users

### Users
- **Institution applicant:** checks completeness and understands which evidence may be missing.
- **Scrutiny officer:** reviews rule failures and evidence-linked discrepancies.
- **Verification officer:** records authorized issuer or source checks.
- **Senior approver:** makes the final decision through the official process.
- **Policy administrator:** manages proposed rule changes through an approval process.
- **Auditor:** reviews the history of checks, evidence references, and human decisions.

### Problems addressed
- Missing, incomplete, or expired supporting documents.
- Different values for the same fact across forms and certificates.
- Extracted fields that may be wrong because of OCR or poor scan quality.
- Possible file-integrity anomalies requiring closer inspection.
- Unavailable or inconclusive issuer verification.
- Findings that identify a problem but do not explain what evidence is needed next.
- Regulatory rules that need to be updated and tested when the applicable handbook changes.

## 3. Core Innovation

### 3.1 Evidence-linked findings

Represent each validation result as a traceable chain:

`Source clause → versioned rule → extracted claim(s) → evidence location → check result → reviewer action`

For each claim, retain:
- original file identifier and cryptographic hash;
- page number and bounding box or text span, where available;
- extracted and normalized values;
- extraction method and confidence;
- rule and rule version used;
- verification source and timestamp, if any;
- reviewer decision and reason.

A trace proves what the system checked and why it produced a finding; it does **not** prove the underlying claim is true.

### 3.2 Versioned, reviewable rule engine

Store requirements as structured data rather than scattering them through application code. Each rule should include:
- stable rule ID and plain-language description;
- source clause and handbook version;
- effective period and applicability conditions;
- required fields or evidence;
- validation logic, severity, and outcome states;
- unit tests and approval status.

A rule update must be reviewed by an authorized person before activation. The system should be able to identify which prior checks used an earlier rule version and which require re-evaluation.

### 3.3 Cross-document reconciliation

Normalize related values and compare them across an application bundle. Example: a programme intake figure in one form differs from a supporting record.

The system should distinguish:
- confirmed mismatch between extracted values;
- possible OCR or formatting difference;
- missing value or evidence;
- a claim that needs an authoritative source check;
- inconclusive result that requires human review.

Do not silently choose one conflicting value as correct. Show both values and their source locations.

### 3.4 Verification ladder

Use the strongest permitted channel available for each document type, without assuming access to restricted systems:

1. Verify a digital signature or QR/reference identifier when supported.
2. Query an authorized official source or API when access has been granted.
3. Record an issuer-confirmation request and its response when the process permits it.
4. Route to manual verification when a source is unavailable or the result is inconclusive.

Proposed status values:
`VERIFIED`, `MISMATCH_DETECTED`, `EXPIRED`, `VERIFICATION_PENDING`, `SOURCE_UNAVAILABLE`, `MANUAL_REVIEW_REQUIRED`.

The exact status vocabulary must be checked against the official problem statement before implementation. A source being unavailable must never be treated as proof of fraud.

### 3.5 Forensic signals with abstention

Where appropriate, inspect:
- PDF metadata and structural properties;
- discrepancies between embedded text and rendered page content;
- font, image-layer, and layout anomalies;
- duplicate or near-duplicate documents and images;
- OCR confidence and scan quality;
- digital signature or authorized-source verification results.

These are indicators, not conclusive fraud verdicts. Re-scanning, compression, conversion, and legitimate editing workflows can create anomalies. If signals conflict or confidence is inadequate, return `MANUAL_REVIEW_REQUIRED` rather than a categorical accusation.

For a student prototype, begin with explainable PDF and OCR checks. Treat deep-learning forensic models as optional components only after licensing and evaluation.

### 3.6 Compliance Repair Planner — primary product differentiator

Go beyond a list of flags by turning findings into a legitimate resolution plan:

1. Group findings that may share a root cause.
2. Rank actions by rule importance, dependency, and confidence.
3. State the exact missing evidence, clarification, or authorized correction needed.
4. Identify actions that may resolve multiple findings.
5. Allow new evidence to be submitted and rerun only affected checks.
6. Preserve before-and-after results and reviewer decisions.

The first prototype can implement this as a deterministic dependency and prioritization engine. Do not claim it finds a mathematically optimal plan unless that property has been defined and tested. It must never fabricate evidence, alter official records, or guarantee approval.

### 3.7 Duplicate-evidence index

Use file hashes for exact duplicates and perceptual hashes or text similarity for likely near-duplicates in a permitted test corpus. Track document type, context, and provenance.

A match is only a review signal. Official templates, shared campus facilities, and legitimate reuse can explain similarities. Cross-institution checks require authorized access to the relevant corpus and must not expose one institution's documents to another.

### 3.8 Synthetic fault-injection benchmark

Create clearly labelled synthetic application bundles with planted cases:
- missing or expired evidence;
- conflicting fields;
- low-quality scans and OCR errors;
- altered synthetic figures;
- duplicate documents or images;
- legitimate reprints and unusual but valid layouts;
- unavailable issuer source;
- ambiguous cases where the correct outcome is manual review.

Report precision, recall, false-positive rates, extraction accuracy, abstention behaviour, and processing time by issue type. Synthetic data must not be represented as real AICTE submissions.

## 4. Prior-Art Review and Differentiation

This section records a targeted initial review of public repository documentation and official material. It is not an exhaustive source-code audit or proof of global novelty.

| Existing reference | Publicly described capabilities | Implication for this proposal |
|---|---|---|
| [AICTE Document Verification System — Team ARTH](https://github.com/theparthgupta/aicte_doc_verification) | README describes OCR, document comparison, fraud detection, infrastructure analysis, evaluator allocation, and a multi-role portal; identifies the project as an SIH 2024 winner. | AICTE-focused document verification and broad workflow automation are not new by themselves. Differentiate through testable rule provenance, cross-document evidence traces, uncertainty handling, and repair planning. |
| [AICTE Portal Automation](https://github.com/AyonSOMADDAR/AICTE_Portal_Automation) | README describes OCR extraction, summaries, discrepancy reporting, and an approval workflow. | OCR, summaries, and discrepancy dashboards should be treated as baseline capabilities. |
| [Sentinel-AI](https://github.com/sanashk19/Sentinel-AI) | README describes ELA, OCR, a CNN-based tamper score, document validators, and a pipeline combining multiple signals. | Multi-signal forensic scoring is not a sufficient novelty claim. Use forensic results as explainable review signals, not final verdicts. |
| [DocTamper](https://github.com/qcf-568/DocTamper) | Research implementation and dataset for document-image tampered-text detection. Its README states that the dataset is available for non-commercial use under an application process. | Check dataset and model terms before reuse. Do not make this dataset or model a prototype dependency. |
| [ADCD-Net](https://github.com/KAHIMWONG/ADCD-Net) | Document-image forgery localization research; repository README identifies an MIT license. | A candidate forensic baseline, subject to checking all dependencies, data, and weight terms. |
| [AICTE Approval Process Handbook 2024–2027](https://www.aicte.gov.in/sites/default/files/APH%20Final.pdf) | Official handbook covering application, EoA, documentation, and scrutiny procedures. | Applicable clauses and amendments must be checked before rules are encoded. |

### What we can and cannot claim

**Reasonable proposed differentiators to test**
- Every finding has a reproducible path from a rule to specific extracted evidence.
- Cross-document contradictions are presented with source locations rather than only a single risk score.
- The workflow distinguishes mismatches, source unavailability, low confidence, and manual review.
- A repair planner proposes legitimate next steps and records revalidation after correction.
- A benchmark explicitly includes valid hard negatives and measures false alarms.

**Claims we must not make yet**
- That the overall concept is globally novel.
- That no existing project has these features.
- That an AICTE or issuer API is accessible.
- That any forensic model reliably detects real-world forgery.
- That the system achieves a particular accuracy, speed, or reduction in review effort before measurement.
- That a repository's code or data can be reused before its license and terms are checked.

**Next research tasks**
1. Re-check the official SIH problem statement and required deliverables.
2. Read the relevant Approval Process Handbook clauses and amendments in full.
3. Inspect source code, tests, activity, dependencies, and license files for the closest repositories.
4. Search for rule-based compliance systems with evidence provenance and correction planning, not only OCR or tamper detectors.
5. Record repository URLs, access date, inspected files, licenses, and precise feature comparisons.
6. Update this section only when the evidence supports the change.

## 5. Prototype Scope

### P0 — required end-to-end demonstration
- Upload a synthetic application bundle securely.
- Extract text from digital PDFs and run OCR for scanned pages.
- Capture field values, page references, and extraction confidence.
- Validate a small, verified set of rules for completeness, expiry, and cross-document consistency.
- Generate evidence-linked findings.
- Show verification states using mock adapters and at least one local signature/QR check if feasible and properly scoped.
- Provide a reviewer screen to confirm, dismiss, or escalate findings with a reason.
- Produce a basic, deterministic repair plan.
- Record an audit history and rerun affected checks after a correction.
- Include tests and a benchmark summary.

### P1 — only after P0 works
- PDF structural checks and embedded-text versus rendered-page comparison.
- Exact and near-duplicate evidence detection.
- Rule-pack version comparison and regression tests.
- Improved repair-plan grouping and prioritization.
- A metrics page showing false positives and failure cases.

### P2 — optional research extensions
- Deep-learning tamper localization.
- Infrastructure photo or floor-plan assistance.
- Cross-institution duplicate analysis, only with authorized data access.
- Advanced policy-change impact analysis.
- Handbook Q&A assistant.

Do not make live government API access, a trained forensic model, or infrastructure computer vision a dependency for the first demonstration.

## 6. End-to-End Workflow

1. **Secure intake:** validate file type and size, assign an application ID, and calculate a file hash.
2. **Extraction:** parse digital PDF text or run OCR; preserve page and region references.
3. **Claim normalization:** standardize dates, names, counts, and identifiers without losing the original extracted value.
4. **Rule evaluation:** run the approved, versioned rule pack.
5. **Reconciliation:** compare related claims and evidence across documents.
6. **Verification:** perform permitted source/signature checks or mark the source unavailable.
7. **Finding generation:** provide rule, evidence, severity, confidence, and uncertainty.
8. **Repair planning:** suggest legitimate next steps for each finding.
9. **Human review:** an authorized reviewer confirms, dismisses, or requests clarification.
10. **Revalidation:** rerun affected checks when evidence or rules change.
11. **Audit and reporting:** preserve a trace of inputs, rules, outputs, and reviewer actions.

## 7. Illustrative Demo Scenario

Use a synthetic institution and clearly label all files as synthetic.

1. Upload a clean application bundle and open its evidence viewer.
2. Upload a bundle with a missing certificate, an expired certificate, and a conflicting intake value.
3. Click each finding to see the rule, extracted values, page locations, and reason.
4. Show a synthetic PDF anomaly and explain why it is only an indicator.
5. Simulate an unavailable verification source and route the case to manual review.
6. Show the repair plan and submit corrected synthetic evidence.
7. Re-run affected rules and display the before-and-after results.
8. Show benchmark metrics, false positives, and cases the system could not resolve.

The demo must show evidence behind each finding, not only a red/green dashboard.

## 8. Proposed Architecture

```text
Applicant / Reviewer Web Interface
                 |
             FastAPI API
                 |
       Secure Document Intake
                 |
      PDF Parsing + OCR Pipeline
                 |
      Claims + Evidence Store
                 |
       +---------+----------+
       |                    |
 Versioned Rule Engine   Verification Adapters
       |                    |
 Cross-document Checks   Source / Signature Results
       |                    |
       +---------+----------+
                 |
        Evidence-linked Findings
                 |
       Compliance Repair Planner
                 |
      Human Review + Revalidation
                 |
       Audit Log + Reports
                 |
       Synthetic Test Harness
```

### Candidate technology stack

| Layer | Candidate | Reason |
|---|---|---|
| Frontend | React, TypeScript, Tailwind CSS, PDF.js | Reviewer workspace and evidence locations |
| Backend | Python, FastAPI, Pydantic | Typed APIs and clear service boundaries |
| PDF parsing | PyMuPDF or pikepdf | Digital text, metadata, and structure checks |
| OCR | Tesseract or PaddleOCR | Compare extraction quality on the available test set |
| Rule engine | Python with versioned YAML/JSON rules | Reviewable requirements and repeatable checks |
| Database | PostgreSQL | Applications, claims, rules, findings, review actions |
| File storage | Local storage for prototype; approved object storage later | Separate original files from derived data |
| Similarity | SHA-256, perceptual hashes, optional text similarity | Exact and near-duplicate candidates |
| Tests | pytest and synthetic fixtures | Regression tests and measurable error rates |
| Deployment | Docker Compose | Reproducible local demo |

Choose libraries only after checking license compatibility, deployment constraints, and prototype needs. Avoid adding a complex graph database unless the initial relational model proves insufficient.

## 9. Suggested Data Model

- `applications`: application ID, institution reference, status, created time.
- `documents`: file hash, storage reference, type, upload time, access classification.
- `claims`: field name, original value, normalized value, source page/region, extraction confidence.
- `rules`: rule ID, clause reference, version, effective dates, approval state, test references.
- `evaluations`: application ID, rule version, outcome, run ID, timestamp.
- `findings`: category, severity, confidence, explanation, evidence references, review state.
- `repair_actions`: linked findings, requested evidence/action, dependencies, status.
- `verification_events`: channel, source, timestamp, result, response reference.
- `review_events`: reviewer role, decision, reason, timestamp.
- `audit_events`: actor, action, object reference, timestamp, integrity data.
- `benchmark_runs`: dataset version, test configuration, metrics, failure examples.

Minimize personal data. Define access, retention, and deletion policies before using real submissions.

## 10. Proposed API Sketch

These endpoints are design proposals, not implemented APIs.

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/applications` | Create an application workspace |
| `POST` | `/api/applications/{id}/documents` | Upload a document |
| `POST` | `/api/applications/{id}/validate` | Run configured checks |
| `GET` | `/api/applications/{id}/findings` | Retrieve findings and evidence |
| `GET` | `/api/applications/{id}/repair-plan` | Retrieve proposed next steps |
| `POST` | `/api/findings/{id}/review` | Record a reviewer decision |
| `POST` | `/api/applications/{id}/revalidate` | Rerun affected checks |
| `GET` | `/api/rules/versions` | List approved rule versions |
| `POST` | `/api/benchmarks/run` | Run the synthetic test suite |

All endpoints require suitable authentication and authorization. Uploads need file-size limits, safe parser handling, rate limiting, and audit events.

## 11. Security, Privacy, and Responsible Use

- Enforce role-based access and least privilege.
- Encrypt data in transit and at rest in any shared deployment.
- Keep secrets out of source control.
- Defend against oversized files, malicious PDFs, parser abuse, and unsafe file paths.
- Preserve original evidence separately from extracted or transformed data.
- Use only authorized verification channels; never bypass access controls.
- Do not expose one institution's evidence to another.
- Treat forensic results as review indicators, not proof of fraud.
- Provide a correction and appeal route for disputed findings.
- Record human decisions and reasons without unnecessarily duplicating sensitive content.
- Define retention and deletion rules with the responsible authority.

## 12. Evaluation Plan

Build a labelled synthetic benchmark before making performance claims.

| Metric | What to measure |
|---|---|
| Field extraction accuracy | Exact-match accuracy for important fields, separated by digital PDFs and scans |
| Rule-check precision and recall | Correct detection of seeded compliance issues |
| False-positive rate | How often valid evidence is flagged |
| Contradiction detection | Precision and recall for cross-document conflicts |
| Abstention quality | Whether uncertain or unsupported cases are routed to review |
| Repair-plan usefulness | Human assessment of whether recommendations are legitimate and actionable |
| Verification-state accuracy | Correct status for scripted success, mismatch, and unavailable-source scenarios |
| Processing time | Observed end-to-end latency on stated hardware |
| Audit completeness | Whether each finding can be reconstructed from recorded rules and evidence |

Targets may be set after a baseline run. Any target is a goal, not a result. Report the dataset composition, limitations, failure cases, and exact test configuration.

## 13. Six-Week Prototype Roadmap

| Week | Deliverable |
|---|---|
| 1 | Verify official problem statement and handbook clauses; define scope, synthetic cases, and rule schema |
| 2 | Secure upload, PDF parsing/OCR, field extraction, and page references |
| 3 | Versioned rule engine, completeness/expiry checks, cross-document reconciliation, evidence-linked findings |
| 4 | Reviewer workspace, verification mock adapters, basic repair planner, and audit events |
| 5 | PDF integrity indicators, duplicate detection, synthetic fault injection, and regression tests |
| 6 | End-to-end demo, benchmark report, security checks, limitations, and presentation rehearsal |

If time is limited, complete P0 before starting P1.

## 14. Team Workstreams

- **Rules and domain research:** verify handbook clauses and encode testable rules.
- **Document pipeline:** safe file intake, parsing, OCR, field normalization, and evidence locations.
- **Validation and repair planning:** consistency checks, finding logic, and deterministic next-step recommendations.
- **Frontend:** upload, evidence viewer, reviewer queue, findings, and correction workflow.
- **Testing and research:** synthetic data, prior-art tracking, licenses, benchmarks, and failure analysis.
- **Integration and security:** API contracts, role permissions, audit events, and reproducible deployment.

## 15. Definition of Done

- [ ] Official PS ID, wording, safeguards, and relevant handbook clauses verified.
- [ ] Prior-art repositories and license terms recorded.
- [ ] Synthetic dataset and planted faults documented.
- [ ] Core extraction and rule checks implemented.
- [ ] Findings link to the exact rule and source location.
- [ ] Cross-document contradictions are demonstrated.
- [ ] Repair plan suggests legitimate, reviewable next steps.
- [ ] Human review and revalidation work end to end.
- [ ] Unavailable sources and uncertain findings are handled safely.
- [ ] Benchmark includes false positives and failure cases.
- [ ] No unmeasured accuracy, speed, or impact claims remain.
- [ ] Security and data-handling limitations are documented.

## 16. References

1. **AICTE Document Verification System — Team ARTH:** https://github.com/theparthgupta/aicte_doc_verification
2. **AICTE Portal Automation:** https://github.com/AyonSOMADDAR/AICTE_Portal_Automation
3. **Sentinel-AI:** https://github.com/sanashk19/Sentinel-AI
4. **DocTamper:** https://github.com/qcf-568/DocTamper
5. **ADCD-Net:** https://github.com/KAHIMWONG/ADCD-Net
6. **AICTE Approval Process Handbook 2024–2027:** https://www.aicte.gov.in/sites/default/files/APH%20Final.pdf

Check the latest repository content, source files, commit history, dependencies, data terms, and licenses before reuse. These references are starting points, not proof that their full implementations have been independently verified.

---

## Final Value Proposition

**The proposed system does not stop at flagging a possible compliance issue. It shows the applicable rule and supporting evidence, distinguishes mismatches from uncertainty, proposes legitimate corrective steps, and records what changed after revalidation.**

Its success should be judged by whether the prototype can demonstrate those steps accurately and transparently on a documented test set—not by the number of AI models or features listed.
