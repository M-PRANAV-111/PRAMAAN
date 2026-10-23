# Evidence-Linked AICTE Compliance Validation System

> **SIH Problem Statement:** SIH26261 — AI-Powered Application Validation, Document Authentication and Regulatory Compliance Verification  
> **Proposed solution:** An evidence-grounded compliance intelligence platform that checks applications, explains every finding, plans legitimate corrections, and continuously tests its own reliability.

**Project status:** Proposal / prototype plan. Features described as proposed are not represented as already implemented. Verify the official SIH problem statement, permitted data sources, and repository licenses before final submission.

---

## 1. Executive Summary

This proposed platform is a decision-support system for validating AICTE approval applications. Instead of treating an application as a collection of PDFs and running isolated OCR or fraud-detection models, it builds a connected view of **requirements, claims, documents, evidence, and verification results**.

The system extracts information from submitted documents, evaluates it against a versioned regulatory rulebook, detects contradictions and suspicious document characteristics, and links each finding to the exact evidence and rule that caused it. Its key differentiator is the **Compliance Repair Planner**: it groups related deficiencies by likely root cause and recommends the smallest legitimate set of corrections or additional evidence that could resolve them. A separate **Adversarial Validation Lab** evaluates the system using synthetic tampered documents and legitimate hard-negative examples.

PRAMAAN AI supports reviewers; it does not make final approval or fraud decisions. Low-confidence, conflicting, or high-impact cases are routed for human review.

## 2. Problem Understanding

Application validation can be difficult when information is distributed across forms, certificates, faculty records, infrastructure documents, declarations, and other supporting files. Potential issues include:

- Required documents or fields are missing.
- The same claim differs across multiple documents.
- A document appears altered, duplicated, incomplete, or inconsistent with its context.
- A rule is applied using the wrong regulatory version or interpretation.
- Reviewers receive a list of flags without a clear explanation of what evidence supports each one.
- Applicants discover deficiencies late and struggle to understand what legitimate evidence is needed next.

A practical system must do more than classify a document as “genuine” or “fake.” It should show what was checked, what was found, why it matters, what remains uncertain, and how a reviewer can verify the result.

## 3. Proposed Innovation

### 3.1 Evidence Graph with Traceable Findings

Represent an application as a graph containing:

- **Requirement nodes:** regulatory clauses and required conditions.
- **Claim nodes:** extracted facts, such as names, dates, counts, qualifications, and facility details.
- **Evidence nodes:** uploaded documents, pages, text spans, tables, and relevant images.
- **Verification nodes:** authorized-source checks and their timestamps.
- **Finding nodes:** missing evidence, contradictions, rule failures, and risk signals.

Edges record relationships such as “supports,” “contradicts,” “derived from,” and “verified by.” Every finding should point back to the applicable rule and its supporting evidence. The graph is an explainability and traceability layer, not proof by itself that a claim is true.

### 3.2 Version-Aware Regulatory Rule Engine

Store regulatory requirements as versioned, reviewable rules rather than burying them in application code. Each rule includes its source, effective period, applicability conditions, required evidence, severity, and test cases.

The engine identifies the relevant rule version for an application and records which rule was executed. When a verified rulebook changes, a **Regulatory Change Impact Analyzer** compares versions and identifies affected checks and previously evaluated applications that may need revalidation. Changes must be reviewed and approved by an authorized person before becoming active.

### 3.3 Cross-Document Contradiction Detection

Normalize extracted facts and compare related claims across forms and supporting documents. For example, a faculty member's name, qualification, role, or experience may differ between a declaration and a supporting record.

The system distinguishes:
- direct contradictions;
- possible formatting or OCR differences;
- values that are missing from one source;
- claims that require external verification.

It presents the compared values, source locations, and confidence rather than silently choosing one value as correct.

### 3.4 Compliance Repair Planner — Main Differentiator

Convert validation results into an actionable, evidence-based resolution plan.

1. Group findings that may share a root cause.
2. Rank them by regulatory importance, dependency, and confidence.
3. Identify the legitimate correction or additional evidence needed for each finding.
4. Recommend a low-effort resolution sequence, showing which actions could address multiple findings.
5. Re-run relevant checks when new evidence is submitted.
6. Preserve the before-and-after findings and reviewer decisions.

The planner never fabricates evidence, changes official documents, or guarantees approval. Recommendations remain subject to the applicable rule and human review.

### 3.5 Document Integrity and Forensic Signals with Abstention

Use multiple independent signals, where technically and legally appropriate:

- PDF metadata and structural anomalies;
- discrepancies between embedded text and rendered page content;
- unusual font, layout, or image-layer inconsistencies;
- duplicate or near-duplicate documents and images;
- OCR confidence and extraction quality;
- authorized-source verification results, when access is available.

These signals are **indicators for review**, not definitive proof of fraud. A scan, reprint, conversion, or ordinary software workflow can create anomalies. If evidence is weak or signals conflict, the system should abstain and request a human decision instead of issuing a categorical accusation.

### 3.6 Evidence Reuse and Provenance Index

Create fingerprints for documents and images to identify exact duplicates and likely near-duplicates across a permitted dataset. Track where an item appeared, its submitted context, and whether reuse is expected or suspicious.

Duplicate detection alone must never imply misconduct. Shared templates, official forms, and legitimately reused evidence should be treated differently from unexplained reuse.

### 3.7 Adversarial Validation Lab

Build a repeatable test suite using synthetic examples and appropriately licensed datasets. Test cases can include missing pages, altered dates, inconsistent names, duplicate images, conflicting values, low-quality scans, and legitimate documents with unusual formatting.

Measure:
- precision and recall by issue type;
- false-positive and false-negative rates;
- OCR and field-extraction accuracy;
- calibration and abstention quality;
- performance across scan quality and document types;
- regression after rule, model, or pipeline changes.

Synthetic data must be clearly labelled and must not be presented as real AICTE submissions. Testing should avoid creating or distributing forged real-world credentials.

### 3.8 Institution Preflight Mode

Provide a pre-submission checklist that lets an institution check whether required fields and supporting evidence appear complete before submission. The mode explains missing or inconsistent items without promising approval and without exposing another institution's data.

## 4. End-to-End Workflow

1. **Secure intake:** accept supported documents, assign an application ID, validate file types and size, and record hashes.
2. **Extraction:** run OCR and document parsing; retain page and field locations plus confidence.
3. **Evidence linking:** map extracted claims to source spans and relevant requirements.
4. **Rule evaluation:** execute the applicable, versioned checks.
5. **Consistency and integrity analysis:** compare related claims and assess document signals.
6. **Finding generation:** produce traceable findings with severity, confidence, evidence, and uncertainty.
7. **Repair planning:** prioritize legitimate actions and missing evidence.
8. **Human review:** let an authorized reviewer confirm, dismiss, or request more information with a recorded reason.
9. **Revalidation:** rerun affected checks when evidence or rules change.
10. **Audit and reporting:** generate a review report and preserve a tamper-evident event history.

## 5. Example Output

**Illustrative scenario — not a real application or an actual AICTE decision**

| Finding | Evidence | Recommended next step |
|---|---|---|
| A required supporting record is missing | Applicable rule and submitted-document inventory | Request the specified record |
| A staff qualification differs between two files | Field values and page references from both files | Ask for clarification or authoritative evidence |
| PDF content has a structural anomaly | File-analysis signal and affected page | Route to manual inspection; do not label it fraudulent |
| A rule version may have changed | Old and new approved rule references | Re-evaluate affected checks after authorized review |

The report should clearly distinguish **failed**, **passed**, **incomplete**, **needs verification**, and **abstained** outcomes.

## 6. System Architecture

```text
Web Interface (Applicant Preflight / Reviewer Workspace)
                         |
                   FastAPI Backend
                         |
        +----------------+----------------+
        |                |                |
 Secure Intake      Rule Engine      Review / Audit API
        |                |                |
 OCR & Parsing     Regulatory Store   Event Ledger
        |
 Claim & Evidence Graph
        |
 +------+------+----------------+
 |             |                |
Consistency  Integrity       Provenance /
Checks       Signals         Duplicate Index
 |             |                |
 +-------------+----------------+
               |
       Findings & Confidence
               |
     Compliance Repair Planner
               |
       Human Review Queue
               |
     Revalidation & Reporting
               |
      Adversarial Test Suite
```

### Suggested technology choices

| Layer | Candidate technologies | Notes |
|---|---|---|
| Frontend | React, TypeScript, Tailwind CSS | Application intake, evidence viewer, reviewer queue, findings and repair plan |
| API | Python, FastAPI, Pydantic | Typed validation endpoints and service boundaries |
| OCR / parsing | Tesseract or PaddleOCR; PyMuPDF; pdfplumber | Benchmark on sample documents before selecting defaults |
| Rules | Python rule modules or a structured JSON/YAML rule schema | Versioning, tests, source references and approval workflow |
| Data | PostgreSQL for structured records; object storage for files | Encrypt files and separate metadata from original evidence |
| Search / similarity | PostgreSQL text search and optional vector/image embeddings | Use only if justified by evaluation and dataset permissions |
| ML / analytics | scikit-learn; optional document anomaly models | Prefer explainable baselines before complex models |
| Testing | pytest, synthetic fixtures, benchmark scripts | Measure accuracy, false alarms and regression |
| Deployment | Docker; approved institutional or cloud environment | Secrets, access controls, backups and retention policies |

These are candidate choices, not fixed requirements. Select components based on available hardware, data permissions, deployment constraints, and benchmark results.

## 7. Proposed Data Model

- `applications`: application identifier, institution reference, status, creation time.
- `documents`: application ID, file hash, storage key, file type, upload time, access classification.
- `extracted_claims`: document ID, field name, normalized value, source page/span, extraction confidence.
- `requirements`: rule ID, source clause, version, effective period, applicability, approval status.
- `evaluations`: application ID, rule version, run ID, outcome, timestamp.
- `findings`: category, severity, confidence, evidence references, explanation, review status.
- `repair_actions`: linked findings, requested evidence/action, dependency, status, reviewer feedback.
- `verification_events`: source, result, timestamp, and permitted response metadata.
- `audit_events`: actor, action, timestamp, object reference, and integrity-chain data.
- `benchmark_runs`: dataset version, test configuration, metrics, and regression results.

Avoid storing unnecessary personal data. Define access, retention, deletion, and audit policies before handling real submissions.

## 8. API Sketch

Proposed endpoints; not implemented unless explicitly stated otherwise.

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/applications` | Create an application workspace |
| `POST` | `/api/applications/{id}/documents` | Upload and register documents |
| `POST` | `/api/applications/{id}/validate` | Run configured checks |
| `GET` | `/api/applications/{id}/findings` | Retrieve findings and evidence references |
| `GET` | `/api/applications/{id}/repair-plan` | Generate or retrieve recommended actions |
| `POST` | `/api/findings/{id}/review` | Record an authorized reviewer decision |
| `POST` | `/api/applications/{id}/revalidate` | Rerun checks after changes |
| `GET` | `/api/rules/versions` | List approved rule versions |
| `POST` | `/api/benchmarks/run` | Run an authorized test suite |

Every endpoint requires authentication and authorization appropriate to the role. Upload and validation endpoints need rate limits, size limits, safe file handling, and audit events.

## 9. Security, Privacy and Responsible AI

- Enforce role-based access and least privilege.
- Encrypt data in transit and at rest; protect secrets outside source control.
- Scan uploads safely and defend against malicious files, path traversal, oversized inputs, and parser abuse.
- Keep original evidence immutable; store derived outputs separately.
- Log access and decisions without unnecessarily duplicating sensitive document contents.
- Use authorized verification sources only; do not scrape restricted systems or bypass access controls.
- Separate system-generated recommendations from final human decisions.
- Provide a correction and appeal path for disputed findings.
- Evaluate error rates and false positives before operational use.
- Define retention and deletion rules with the responsible institution.

## 10. Evaluation Plan

Create a labelled, permissioned test set with separate examples for each issue category. Split data to avoid leakage between development and evaluation, and document the limits of the dataset.

| Metric | What it measures |
|---|---|
| Field extraction accuracy | Correct extraction of important fields |
| Rule-check precision / recall | Reliability of each compliance check |
| False-positive rate | How often valid evidence is incorrectly flagged |
| Contradiction detection F1 | Quality of cross-document inconsistency detection |
| Abstention quality | Whether uncertain cases are safely routed to review |
| Repair-plan usefulness | Reviewer assessment of correctness and actionability |
| Processing time | End-to-end latency per application |
| Audit completeness | Whether each finding can be traced to rules and evidence |

Do not claim accuracy, speed, or impact figures until measured on a documented test set.

## 11. Six-Week Prototype Roadmap

### Week 1 — Scope and rule foundation
- Verify official PS wording and identify a narrow set of requirements.
- Gather permitted sample documents and define a synthetic test set.
- Build the versioned rule schema and application data model.

### Week 2 — Intake and extraction
- Implement secure document upload and basic PDF/text extraction.
- Capture field values, page references, and extraction confidence.
- Add unit tests for parsing and validation.

### Week 3 — Evidence graph and rules
- Link claims, source locations, and rules.
- Implement missing-field and cross-document consistency checks.
- Produce traceable findings.

### Week 4 — Repair planner
- Group related findings and prioritize actions.
- Generate evidence-backed recommendations.
- Add reviewer confirmation, dismissal, and clarification flows.

### Week 5 — Integrity signals and benchmark
- Add carefully scoped file-integrity checks and duplicate detection.
- Build synthetic hard negatives and regression tests.
- Report precision, recall, false positives, and abstention behaviour.

### Week 6 — Demo and hardening
- Test end-to-end flows, role access, file handling, and audit records.
- Prepare a repeatable demo and documented limitations.
- Present results only from tests actually run.

## 12. Demo Plan

Use a clearly labelled synthetic application with:
1. one complete requirement and matching evidence;
2. one missing supporting document;
3. one conflicting field across two documents;
4. one synthetic file-integrity anomaly;
5. a repair plan that requests legitimate evidence;
6. a corrected synthetic submission that triggers revalidation;
7. a benchmark summary showing both detected issues and false positives.

The demonstration should show the evidence behind every result, not just a red/green dashboard.

## 13. Repository and Prior-Art Research Checklist

Before claiming novelty or using external code:

- Verify the current official SIH26261 title, description, constraints, sponsor requirements, and evaluation criteria.
- Inspect relevant GitHub repositories and their recent activity, architecture, actual implemented features, dependencies, and licenses.
- Compare document OCR, tamper detection, duplicate detection, rule engines, and application workflow projects separately.
- Identify what is genuinely different in the proposed solution, especially the evidence-linked repair plan, rule-change impact analysis, and measured abstention.
- Record URLs, commit hashes or release versions, license terms, limitations, and a concise comparison table.
- Do not claim a repository was inspected unless it was actually opened and reviewed.
- Do not claim a feature is novel globally without a sufficiently broad prior-art review.

Potential starting points for research (verify current content and license before use):
- AICTE document-verification repository: https://github.com/theparthgupta/aicte_doc_verification
- Sentinel-AI: https://github.com/sanashk19/Sentinel-AI
- ADCD-Net: https://github.com/KAHIMWONG/ADCD-Net
- DocTamper: https://github.com/qcf-568/DocTamper

These links are starting points, not an assertion that their code or datasets are suitable for reuse. Confirm each repository's contents, license, provenance, and relevance before incorporating anything.

## 14. What Is Actually Implemented?

At this proposal stage, **no implementation, model training, test run, official-source integration, or deployment is claimed**. The architecture, endpoints, data model, roadmap, and demo are plans.

Update this section honestly as work progresses:
- [ ] Official PS verified
- [ ] Prior-art repositories inspected and licences recorded
- [ ] Synthetic dataset prepared
- [ ] Rule engine implemented and tested
- [ ] Evidence-linked findings implemented
- [ ] Repair planner implemented
- [ ] Human review and audit flow tested
- [ ] Benchmark metrics measured
- [ ] Deployment and security checks completed

## 15. Final Value Proposition

**The system does not stop at detecting a possible compliance problem. It connects the finding to evidence and the applicable rule, explains uncertainty, recommends legitimate next steps, verifies the correction, and measures the reliability of its own checks.**

Its strongest proposed differentiator is the closed-loop workflow:

**Detect → Explain → Plan a correction → Human review → Revalidate → Audit.**

The goal is to reduce avoidable review effort while keeping decisions traceable, privacy-conscious, and under authorized human control.


## 16. References, Prior Art and Prototype Resources

This section lists the public starting points used to shape the proposed approach. They are references for learning and comparison—not proof that the proposed system is globally novel, and not a claim that their code has been integrated. Inspect the current repository contents, licence, dependencies, and dataset terms before reuse.

### 16.1 Related GitHub Repositories

| Reference | What to study | How it can help the prototype | Important caution |
|---|---|---|---|
| [AICTE Document Verification System](https://github.com/theparthgupta/aicte_doc_verification) | AICTE-specific workflow, OCR, document comparison, infrastructure checks, reviewer dashboard, and architecture | Use it as the first comparison point for existing AICTE workflows; document which features overlap and where your repair-planning and rule-version approach differs | This project already describes a broad AICTE verification workflow. Do not claim basic AICTE document verification as your unique innovation without a careful comparison |
| [Sentinel-AI — Forensic Document Analysis](https://github.com/sanashk19/Sentinel-AI) | OCR-based checks, image-forensic signals, anomaly summaries, explainability visuals, and API/dashboard structure | Learn how forensic signals might be exposed in a reviewer interface; prototype only a small, testable subset | Treat scores and image anomalies as review signals, not proof of fraud. Inspect model/data provenance and licence |
| [DocTamper](https://github.com/qcf-568/DocTamper) | Research on detecting tampered text in document images, implementation structure, and evaluation approach | Use as a research reference for document-tampering experiments and benchmark design | The repository states that its dataset is restricted to non-commercial use under its terms. Check current dataset and code terms before downloading or using it |
| [ADCD-Net](https://github.com/KAHIMWONG/ADCD-Net) | Document image forgery localization, OCR masks, cross-dataset evaluation, and reproducibility requirements | Study the task and evaluation methodology; do not assume it will run on ordinary laptop hardware without changes | Its documented training setup uses multiple high-end GPUs; for a student prototype, prefer inference-only tests or a lightweight baseline unless suitable compute is available |

### 16.2 Official and Technical References to Verify

- [AICTE official website](https://www.aicte-india.org/) — use official, current handbooks, regulations, circulars, and approval-process documents as the source of regulatory rules.
- [Smart India Hackathon portal](https://www.sih.gov.in/) — confirm the exact SIH26261 problem statement, sponsor expectations, constraints, and submission format before finalizing the proposal.
- [PyMuPDF documentation](https://pymupdf.readthedocs.io/) — PDF text extraction and page-level inspection.
- [Tesseract OCR documentation](https://tesseract-ocr.github.io/) — an OCR option for scanned documents.
- [FastAPI documentation](https://fastapi.tiangolo.com/) — API implementation and validation.
- [pytest documentation](https://docs.pytest.org/) — repeatable automated tests.

**Regulatory rule source of truth:** do not invent AICTE rules or copy rules from an unofficial project. Record the exact official document title, publication/version date, clause/page, effective period, and date checked for every implemented rule. If the official source is unclear, mark the rule as awaiting authorized interpretation.

### 16.3 Suggested Prototype Build Order

Keep the first prototype small enough to finish and demonstrate:

1. **Create a synthetic sample application.** Use fictional names and made-up records; do not upload real personal or institutional documents without permission.
2. **Build a document inventory.** Upload a few PDFs, calculate file hashes, and list required versus supplied files.
3. **Implement 3–5 explicit rules.** Choose only rules you can cite to a verified official source. Store each rule's source, version, applicability, and expected evidence.
4. **Extract a few fields.** Capture values such as names, dates, and counts together with the source page and extraction confidence.
5. **Add cross-document comparison.** Deliberately create one synthetic mismatch and show both source values.
6. **Generate traceable findings.** Each result should show the rule, evidence location, reason, and status such as passed, failed, incomplete, needs verification, or abstained.
7. **Build the Compliance Repair Planner.** Group related findings and recommend a legitimate next action, such as requesting a missing document or clarification.
8. **Add human review and audit history.** Let a reviewer confirm, dismiss, or request more evidence with a reason.
9. **Test the happy path and failure cases.** Include missing files, unreadable scans, OCR mistakes, conflicting values, duplicate files, and uncertain evidence.
10. **Measure results honestly.** Report the number of test cases, rule-check precision/recall where labels are available, false positives, and processing time. Do not invent performance figures.

### 16.4 Recommended SIH Presentation (PPT) Structure

A concise 7-slide presentation can tell the story clearly:

1. **Problem and impact** — describe the manual review challenge using verified facts; cite the official SIH problem statement and official AICTE material.
2. **Current gap and prior art** — show what existing AICTE verification projects and document-forensics research already cover; explain the remaining gap without dismissing existing work.
3. **Proposed solution** — introduce the evidence-linked rule engine, contradiction checks, uncertainty-aware review, and Compliance Repair Planner.
4. **Architecture and workflow** — show intake → extraction → evidence graph → versioned rules → findings → repair plan → human review → revalidation/audit.
5. **Prototype walkthrough** — demonstrate a synthetic application with one missing document, one conflicting field, and a repair recommendation.
6. **Innovation, safety and evaluation** — explain rule-change impact analysis, evidence traceability, abstention, human oversight, and the metrics you will actually measure.
7. **Feasibility, roadmap and references** — present the prototype scope, technology choices, next milestones, and the key sources listed in this README.

For each slide, separate **existing research**, **your proposed design**, and **features actually implemented**. Use screenshots and metrics only from a real prototype or clearly label mockups and planned results.

### 16.5 Prior-Art Comparison Checklist

Before claiming novelty in the PPT or final submission, fill in a comparison using evidence from repository READMEs, code, papers, and official documents.

| Capability | Existing AICTE repository | Document-forensics research | Proposed prototype |
|---|---|---|---|
| AICTE-specific workflow | Inspect and record | Usually not the main focus | Planned |
| Versioned, source-cited regulatory rules | Verify in repository | Usually not the main focus | Planned |
| Cross-document contradiction evidence | Verify implementation | May address image-level manipulation instead | Planned |
| Actionable repair plan linking findings to legitimate next steps | Verify implementation | Usually not the main focus | Proposed differentiator to test |
| Uncertainty / abstention and human review | Verify implementation | Review model limitations and outputs | Planned |
| Regression benchmark for rule and pipeline changes | Verify implementation | Study available benchmarks | Planned |

Do not mark a capability as absent from another project merely because its README does not mention it. Inspect the code or report the status as **not confirmed**.

### 16.6 Attribution and Reuse Notes

- Cite papers, repositories, official regulations, datasets, and third-party models in the project documentation and presentation.
- Follow each repository's software licence and each dataset's separate terms. A public GitHub repository does not automatically mean its data or weights are unrestricted.
- Do not copy credentials, real personal data, or confidential application documents into the repository.
- Keep a `THIRD_PARTY_NOTICES.md` file if code, models, or assets are reused.
- Keep a research log with the URL, date accessed, commit or release inspected, relevant feature, licence, and how it informed the design.
- A reference being listed here means it is a starting point for research; it does not mean its code was copied or integrated.

