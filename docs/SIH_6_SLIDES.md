# PRAMAAN — SIH 2026 Idea Presentation (6 slides)

Ready-to-paste content for the official SIH 2026 idea-submission template (Title · Idea/Proposed Solution · Technical Approach · Feasibility & Viability · Impact & Benefits · Research & References). The template allows at most six slides and asks for points, diagrams and infographics rather than paragraphs.

> **Before uploading**
> - **PS ID / title / theme** are taken from the team's problem-statement document. Public first-lot archives of SIH 2026 statements end at SIH26226 (22 Aug 2026 snapshot), so SIH26261 could not be re-checked from a public source. Confirm the exact wording and deadline in the official SIH portal.
> - **Team ID / Team Name** are placeholders.
> - **No numbers on these slides are results.** Anything measurable is listed as a KPI to be measured.

---

## SLIDE 1 — TITLE PAGE

**SMART INDIA HACKATHON 2026**

- **Problem Statement ID:** SIH26261
- **Problem Statement Title:** AI-Powered Application Validation, Document Authentication and Regulatory Compliance Verification
- **Theme:** Smart Automation
- **PS Category:** Software
- **Organization:** All India Council for Technical Education (AICTE) — Regulation Bureau
- **Team ID:** `<TEAM_ID>`
- **Team Name:** `<TEAM_NAME as registered on portal>`

**Project:** **PRAMAAN** *(प्रमाण — "proof / evidence")*
**Tagline:** *Every flag carries its proof. AI assists — officials decide.*

**Visual arrangement**
- Left 60%: the template fields above.
- Right 40%: PRAMAAN wordmark; beneath it a thin five-node "proof chain" motif: `Clause → Rule → Claim → Evidence → Source`.
- One accent colour only (deep indigo on white, saffron for the chain nodes).

**Presenter note (15 s)**
"PRAMAAN means proof. Our system never gives an officer a bare score; every flag comes with the rule, the exact evidence and the source check behind it, and the official makes the decision."

---

## SLIDE 2 — IDEA TITLE: PRAMAAN — Proof-Carrying Validation for AICTE Approvals

### The problem
- An approval / Extension-of-Approval (EoA) file combines affidavits, certificates, NOCs, faculty and intake data, and infrastructure evidence.
- Scrutiny checks files one at a time, so **missing / expired items, cross-document contradictions and doubtful documents surface late**.
- Confirmation from issuing authorities is slow; reasons for a query are hard to trace and vary between reviewers.
- **Consequence:** repeated query–resubmission cycles, delayed decisions, uneven scrutiny.

### Our solution (end to end)
`Upload → Classify & extract (page + box provenance) → Evaluate versioned Handbook rules → Reconcile across documents & AICTE records → Verify at source → Evidence-linked findings → Officer review → Repair plan → Targeted re-validation → Audit`

**Key features:** category checklists · OCR/extraction with confidence · completeness & expiry checks · cross-document consistency · verification with the six PS statuses · document-integrity indicators · institution & officer dashboards · RBAC + tamper-evident audit trail.

### What makes it different (3 differentiators)
1. **Proof-carrying findings** — every flag is a replayable chain: *Handbook clause → versioned rule → extracted claims (document, page, box) → result → reviewer action*. Rules live in effective-dated rule packs, not in code, so a Handbook change is a reviewed data change.
2. **Honest uncertainty via a Verification Ladder** — strongest available check first: source/cryptographic → official lookup → integrity indicator → human. When evidence is weak, the system **abstains** (`MANUAL_REVIEW_REQUIRED`) instead of guessing. Reprint-aware date logic; text-layer vs rendered-page check for machine-generated PDFs. Output is always "indicator", never "forged".
3. **Closed-loop Repair Planner + Institution Pre-flight** — groups deficiencies by root cause, names the exact evidence that resolves each one, re-runs **only the affected rules** after correction, and keeps a before/after trail.

**By design, PRAMAAN does not:** approve or reject, declare forgery, or access restricted databases.

**Visual arrangement**
- Left column: 3 problem icons (late discovery · contradictions · slow source checks).
- Centre: horizontal pipeline strip (the flow above).
- Right column: 3 differentiator cards, plus one small "example proof" card:
  `Rule FIRE.VALID (APH 2024-27) · Fire NOC, p.1 · valid_to 31-03-2026 < AY start 01-07-2026 → EXPIRED`.

**Presenter note (60 s)**
"Existing tools score a single document. AICTE's real problem is a bundle of documents that must agree with each other and with AICTE's own records. PRAMAAN turns the Handbook into versioned rules, links every extracted value to its page, and produces findings an officer can check in seconds. When it can't be sure, it says so and routes the case to a human. And it tells the institution exactly what to fix."

---

## SLIDE 3 — TECHNICAL APPROACH

### Technologies (and why)
| Layer | Choice | Why |
|---|---|---|
| Frontend | React 19 + TypeScript, Tailwind CSS v4, Zod (esbuild bundle) | Typed, accessible dashboards; evidence viewer with box overlays on page images |
| API | Python ASGI — Starlette + Pydantic; OpenAPI contract generated from the same models | Python document/ML ecosystem; one schema source drives the typed frontend client |
| Data | Relational store for claims, rules, findings, audit (SQLite in prototype → PostgreSQL in deployment) · private content-addressed file store · background worker queue | One source of truth; originals kept immutable and private |
| Document intelligence | pdfplumber (text layer + word coordinates) · pypdfium2 (page rendering) · Tesseract OCR for scans · template + regex extractors | Deterministic, auditable extraction first; every value keeps page, box and confidence |
| Rules | YAML rule packs + safe expression evaluator (no `eval`) | Officials can read rules; each run emits a proof trace |
| Verification | Pluggable adapters: signed-QR check (Ed25519), AICTE-record lookup, issuer registry; DigiLocker/issuer APIs **only after authorization** (labelled mocks now) | Separates cryptographic/source proof from visual suspicion |
| Integrity | PDF structure (pikepdf: incremental updates, metadata), text-layer vs OCR divergence, SHA-256 + perceptual-hash duplicate index | Cheap, explainable indicators; no large training set needed |
| Security | scrypt password hashing, short-lived JWT, server-side RBAC + object-level checks, hash-chained audit log, local processing only | Sensitive records never leave the deployment |
| Deployment | Docker Compose; on-premise / government cloud ready | Reproducible; no paid services |

### Workflow (recreate as a flowchart)
```
[Institution uploads PDF]
   → [Intake: type & size check · SHA-256 · private storage · audit entry]
   → [Classify document type] → [Extract claims: text layer / OCR → {value, page, box, confidence}]
   → ┌ [Rule engine: versioned Handbook pack]        ┐
     ├ [Cross-document + AICTE-record reconciliation] ┤
     ├ [Verification Ladder → 6 PS statuses]          ┤
     └ [Integrity indicators + duplicate index]       ┘
   → [Findings, each with its proof chain] → [Repair plan]
   → [Officer: confirm / dismiss / escalate + reason]
   → [Re-validate affected rules] → [Report + hash-chained audit log]
```

### Methodology
1. Encode 2–3 application categories from the APH 2024-27 into a rule pack, each rule citing its clause.
2. Build one working vertical slice: sign in → upload → extract → validate → evidence-linked findings → review.
3. Add verification ladder, integrity indicators, repair planner.
4. Measure on a synthetic fault-injection benchmark (planted defects **and** valid hard negatives).

**Visual arrangement:** layered architecture (UI → API → pipeline → data), with the flowchart above as the centrepiece; tech logos in a thin band at the bottom.

**Presenter note (60 s)**
"The core path is deterministic: rules are data, extraction is template-first, and every claim keeps its coordinates. Machine learning is used only where it adds signal, and never as the sole basis for a flag. External sources plug in through adapters; today they are clearly labelled mocks, and real integrations need AICTE authorization."

---

## SLIDE 4 — FEASIBILITY AND VIABILITY

### Feasibility analysis
- **Technical:** open-source stack; deterministic path runs on a CPU laptop; no model training or live government API is on the critical path.
- **Operational:** fits AICTE's existing online approval portal as a decision-support layer; officers keep the final say; AICTE's own EoA letters already direct readers to verify course details on the AICTE website — our ladder formalises that lookup.
- **Economic:** no licence fees; on-premise deployment; rules updated as data, not code releases.
- **Scalability:** stateless API + worker queue; documents processed asynchronously; scales horizontally.

### Buildable now vs needs authorization
| Buildable now (prototype) | Needs AICTE / issuer authorization |
|---|---|
| Full pipeline on synthetic application bundles | Real application data and institutional records |
| Rule packs for selected categories | Official sign-off on every encoded rule |
| PDF signature & QR checks, integrity indicators | DigiLocker requester access via API Setu onboarding |
| Mock issuer adapters with explicit statuses | Issuer APIs / portal integrations |
| Dashboards, audit, repair planner | Integration with the AICTE portal and SSO |

### Challenges & risks → mitigation
| Risk | Mitigation |
|---|---|
| Rule mis-encoding | Clause citation per rule, unit tests per rule, official review before activation |
| False alarms on legitimate scans / reprints | Abstention, "indicator" wording, reprint-aware dates, hard-negative test set |
| AI-forged edits evade pixel forensics | Prefer source / cryptographic verification; forensics never the sole basis |
| No issuer API access | `SOURCE_UNAVAILABLE` status → manual queue; never treated as fraud |
| Privacy of institutional records | RBAC, private storage, local processing, DPDP-aligned minimisation |
| Over-scoping | P0/P1/P2 priorities; vertical slice first |

**Visual arrangement:** four feasibility tiles (Technical · Operational · Economic · Scalable) on top; two tables below.

**Presenter note (45 s)**
"Everything on the left column we can demonstrate end to end with synthetic data. The right column needs AICTE's authorization, so the design treats those sources as optional adapters and reports honestly when they are unavailable."

---

## SLIDE 5 — IMPACT AND BENEFITS

### Who benefits and how
- **AICTE officers:** deficiencies surface before scrutiny starts; each flag shows its rule and evidence; less repetitive cross-checking; consistent outcomes across reviewers.
- **Institutions:** pre-flight check before submission; a precise "what to fix" list; fewer query cycles.
- **AICTE / governance:** traceable, explainable decisions; rule changes versioned and auditable; tamper-evident history; cross-institution evidence reuse becomes visible (only AICTE holds the full corpus).
- **Society & economy:** faster, fairer approvals for technical education; less paperwork and travel for clarifications; stronger trust in approved institutions.

### Principles we will not compromise
Advisory only · human decision on every adverse outcome · no forgery verdicts · evidence for every flag · privacy by default.

### Measured on the working prototype (synthetic data, 21 Oct 2026)
- **26 of 26** planted faults detected across 13 fault types; **2 of 8** valid look-alike bundles still flagged (legitimate PDF re-saves raise an integrity *indicator*, by design).
- **2.7 s** median to check a 5–6 document bundle on a CPU.
- Caveat for the slide: synthetic documents built alongside the extractors — not real-world accuracy.

### Proposed evaluation KPIs for a pilot (to be measured — no figures claimed)
| KPI | How we will measure |
|---|---|
| Findings with complete proof chain | % of findings linked to rule + page/box + source (design target: all) |
| Detection on seeded defects | Precision / recall per defect type on the synthetic benchmark |
| False alarms | False-positive rate on valid hard negatives (reprints, re-scans) |
| Abstention quality | Share of uncertain cases correctly routed to manual review |
| Reviewer effort | Minutes per bundle, assisted vs manual (small time-and-motion study) |
| Query cycles | Clarification rounds per application (pilot data from AICTE) |

**Visual arrangement:** three stakeholder columns with icons; KPI table as a strip at the bottom labelled "To be measured".

**Presenter note (45 s)**
"The prototype numbers are real but synthetic, and we say so. We are not claiming speed-ups we haven't measured. What we can guarantee by design is that every flag is traceable. The KPIs on this slide are how we will prove the rest, first on our synthetic benchmark and then in a pilot."

---

## SLIDE 6 — RESEARCH AND REFERENCES

### Official & regulatory
- [SIH 2026 problem statements (official portal)](https://sih.gov.in/sih2026PS) — source of SIH26261; confirm wording here.
- [AICTE Approval Process Handbook 2024-27](https://aicte.gov.in/sites/default/files/APH%20Final.pdf) — the rules our rule packs encode.
- [AICTE public notice, approval process 2026-27 (hosted by BTEUP)](https://bteup.ac.in/PDFFILES/NEWS_639005651817728160.pdf) — portal timeline; APH 2024-25 to 2026-27 applies.
- [Sample AICTE EoA letter 2026-27 (CUSAT)](https://soe.cusat.ac.in/assets/files/aicte_eoa_letters/EOA_Report_2026-2027.pdf) — real field structure (Permanent ID, Application ID, intake tables, print date) used for synthetic templates.
- [DigiLocker onboarding FAQ](https://www.digilocker.gov.in/assets/FAQ%20DL%20EL_onboarding.pdf) and [API Setu](https://api.apisetu.gov.in) — requester registration and consent flow; basis for our "authorized adapter only" design.
- [Controller of Certifying Authorities — digital signatures](https://cca.gov.in/digital_signature.html) — India's legal framework for verifiable digital signatures.
- [Digital Personal Data Protection Act 2023 (Digital India)](https://digitalindia.gov.in/dpdp) — privacy obligations for institutional and personal data.

### Academic research
- [Qu et al., *Towards Robust Tampered Text Detection in Document Image*, CVPR 2023 (DocTamper)](https://openaccess.thecvf.com/content/CVPR2023/html/Qu_Towards_Robust_Tampered_Text_Detection_in_Document_Image_New_Dataset_CVPR_2023_paper.html) — leading tampered-text benchmark; dataset is non-commercial only.
- [Wong et al., *ADCD-Net*, ICCV 2025](https://openaccess.thecvf.com/content/ICCV2025/papers/Wong_ADCD-Net_Robust_Document_Image_Forgery_Localization_via_Adaptive_DCT_Feature_ICCV_2025_paper.pdf) — recent document forgery localization; optional signal provider.
- [Wu et al., *AIForge-Doc*, arXiv 2026](https://arxiv.org/abs/2602.20569) — DocTamper's detector drops from 0.98 AUC in-distribution to 0.563 on AI-forged documents; why we prefer source verification and abstention.
- [Angelopoulos & Bates, *A Gentle Introduction to Conformal Prediction*](https://arxiv.org/abs/2107.07511) — statistical basis for abstaining instead of guessing.

### Implementation references
- [PyMuPDF](https://pymupdf.readthedocs.io/) — text layer with coordinates and page rendering.
- [pyHanko](https://pyhanko.readthedocs.io/) — PDF signature validation.
- [Tesseract OCR](https://tesseract-ocr.github.io/tessdoc/) — offline OCR for scans.
- [FastAPI](https://fastapi.tiangolo.com/) · [Next.js](https://nextjs.org/docs) · [PostgreSQL](https://www.postgresql.org/docs/) — core stack.
- [OWASP ASVS](https://owasp.org/ASVS/) — security verification checklist.

### Prior art we build beyond
- [AICTE Document Verification — Team ARTH](https://github.com/theparthgupta/aicte_doc_verification) — README states SIH 2024 winner; OCR, comparison, fraud detection, multi-role portal. No rule versioning, abstention or issuer verification described.
- [AICTE Portal Automation](https://github.com/AyonSOMADDAR/AICTE_Portal_Automation) — OCR extraction and discrepancy reports.
- [Sentinel-AI](https://github.com/sanashk19/Sentinel-AI) — multi-signal tamper scoring for ID documents (single score).

### Third-party commentary (context only)
- [SIH 2026 PS archive (first lot)](https://github.com/Rugved-dev18/SIH-2026-official-Software-Problem-Statements) — unofficial snapshot; used to check PS numbering.

**Visual arrangement:** four labelled boxes (Official · Academic · Implementation · Prior art), small font, links as short titles.

**Presenter note (20 s)**
"Our rules come from the official Handbook, our design limits come from DigiLocker's and CCA's frameworks, and our honesty about forensics comes from 2026 research showing that detectors fail on AI-forged documents."

---

## Verification log for this deck (21 Oct 2026)

| Item | Status |
|---|---|
| SIH 2026 template structure (6 slides, headings) | Verified against multiple copies of the 2026 template |
| SIH26261 ID / title / theme | **Not verifiable publicly**; from team PS document — confirm on portal |
| APH 2024-27 is current for 2026-27 approvals | Verified (AICTE notice; EoA 2026-27 letters cite APH 2024-27, chapter VI) |
| EoA letter structure | Verified on a public 2026-27 EoA letter |
| DigiLocker requester onboarding needs API Setu registration and user consent | Verified (DigiLocker FAQ) |
| AIForge-Doc figures | Verified (arXiv abstract) |
| DocTamper dataset non-commercial | Verified (repository README) |
| Team ARTH repo features / SIH 2024 winner claim | Verified as stated in its README (claim not independently confirmed) |
| Prototype metrics on Slide 5 | Measured by `backend/eval/benchmark.py`; report in `backend/var/benchmark/latest.json` |
