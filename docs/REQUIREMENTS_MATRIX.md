# Requirements Traceability Matrix — PRAMAAN (SIH26261)

**Inputs analysed:** the five team proposals in `docs/source-proposals/` (README1–5), the master execution prompt, and the official sources verified in Phase 1 (`docs/SIH_6_SLIDES.md`, verification log).
**Precedence when sources conflict:** (1) official PS text and AICTE regulations → (2) authorized technical specs → (3) team proposals → (4) marked engineering assumptions.
**Treatment of inputs:** proposals are informational. Nothing in them overrides the PS safeguards.

Legend — Priority: **P0** must work end-to-end in the prototype · **P1** should · **P2** stretch/future. Status column is filled in at delivery (see README "What is implemented").

---

## 1. Confirmed problem-statement requirements and safeguards

The PS text was available only through the team's documents (all five agree on it; README2 §1 lists deliverables, README3 §0 lists safeguards). Public archives do not yet contain SIH26261 — **confirm on the SIH portal**.

| ID | Requirement | Source | Priority | Implementation | Module | Acceptance test |
|---|---|---|---|---|---|---|
| PS-1 | Decision support only; no automated approve/reject | R1 §1, R2 §1, R3 §0, R5 §1 | P0 | No approve/reject endpoint or status exists; derived status vocabulary is limited to scrutiny states | `backend/app/pipeline/findings.py`, API | `test_no_adverse_status_values` scans all enums for approve/reject/forged |
| PS-2 | Category-based checklists and configurable validation rules | R2 §1 | P0 | YAML rule packs per application category, effective-dated, versioned | `backend/rulepacks/`, `pipeline/rules.py` | Rule unit tests: pass / fail / not-evaluable per rule |
| PS-3 | OCR-based classification, extraction, completeness | R2 §1 | P0 | Text-layer extraction with word boxes; Tesseract for image-only pages; keyword classifier; required-document rules | `pipeline/extract.py` | Extraction test on synthetic PDFs (digital + scanned) |
| PS-4 | Cross-document and institutional-record consistency with evidence-linked flags | R2 §1, R3 §5 | P0 | `consistency` rule type over claims + mock AICTE record; finding carries both claims with page/box | `pipeline/rules.py`, `verification.py` | Intake-mismatch test returns both claims with provenance |
| PS-5 | Verification via authorized issuing-authority sources | R2 §1, R5 §3.4 | P0 | Verification ladder with adapters; mocks clearly marked `simulated` | `pipeline/verification.py` | Scripted scenarios give VERIFIED / MISMATCH / SOURCE_UNAVAILABLE / MANUAL_REVIEW |
| PS-6 | Compliance assistance for documentary and infrastructure evidence | R2 §1 | P0/P1 | Repair planner (documentary); duplicate-photo detection (infrastructure) | `pipeline/repair.py`, `dedupe.py` | Repair plan lists required evidence per finding; duplicate photo flagged across institutions |
| PS-7 | Dashboard: status, deficiencies, verification outcomes, pending actions, audit history | R2 §1 | P0 | Institution and officer dashboards, case view, audit page | `front/src/pages/*` | Browser E2E walk-through |
| PS-8 | RBAC, secure document handling, confidentiality, human review before adverse action | R2 §1, R3 §0 | P0 | Server-enforced roles + object-level checks; private storage; officer disposition required with reason | `app/security.py`, `routes/*` | Cross-institution access returns 404; disposition without reason → 422 |
| PS-9 | Explainable, evidence-linked AI output | R2 §1, R5 §3.1 | P0 | Every finding stores a proof JSON (rule, clause, claims, values, result) | `pipeline/findings.py` | Test: every finding has `proof.rule` or `proof.indicator` and ≥1 evidence ref |
| PS-10 | No bypass of access controls; no assumed access to restricted databases | R2 §1, R3 §10.5 | P0 | External adapters off unless configured; mocks labelled | `verification.py`, config | Default config has no external endpoints |
| PS-11 | Demo on synthetic / anonymised data only | R1 §1, R3 §0 | P0 | Synthetic generator; every synthetic PDF stamped "SYNTHETIC — NOT A REAL DOCUMENT" | `backend/synthetic/` | Generated PDFs contain the stamp |
| PS-12 | Explicit verification statuses: VERIFIED, MISMATCH_DETECTED, EXPIRED, VERIFICATION_PENDING, SOURCE_UNAVAILABLE, MANUAL_REVIEW_REQUIRED | R1 §7, R3 §5.2, R5 §3.4 | P0 | Enum shared by backend and frontend contract | `app/schemas.py`, `contracts/` | Contract test: enum identical in generated TS |

## 2. Functional requirements (from proposals)

| ID | Requirement | Source | Priority | Implementation | Module | Acceptance test |
|---|---|---|---|---|---|---|
| F-1 | Claims carry provenance: doc, page, bbox, extractor, confidence | R1, R3 §10.2, R5 §3.1 | P0 | `claims` table columns | `extract.py` | Every claim has page ≥1 and 4-number bbox |
| F-2 | Typed, reprint-aware dates (issue, print, valid_from, valid_to) | R2 §5.3 I3 | P0 | Extractor emits typed date fields; expiry rules reference `valid_to` only | `extract.py`, rulepack | Reprinted letter (print date later) yields no date finding |
| F-3 | Rule proof traces + minimal conflicting set | R2 I1, R3 §10.3 | P0 | Evaluator returns inputs used and evaluated values | `rules.py` | Proof lists exactly the claims referenced by the failing expression |
| F-4 | Text-layer vs rendered-page divergence | R2 I2, R4 §3.5 | P1 | Render page, OCR numeric tokens' regions, compare with text layer | `integrity.py` | Synthetic overlay edit flagged; clean doc not flagged |
| F-5 | PDF structure indicators (incremental updates, date order, producer) | R2 I2, R5 §3.5 | P1 | pikepdf + raw byte scan | `integrity.py` | Incrementally-updated PDF raises indicator |
| F-6 | Abstention: uncertain → MANUAL_REVIEW_REQUIRED | R1, R3 §10.4, R5 §3.5 | P0 | Indicators never produce "forged"; low OCR confidence → NOT_EVALUABLE → manual review | `integrity.py`, `rules.py` | Low-confidence claim leads to NOT_EVALUABLE, not FAIL |
| F-7 | Duplicate-evidence index (exact + perceptual) with legitimate-reuse allow-list | R1, R3 §10.6, R5 §3.7 | P1 | SHA-256 + OpenCV pHash; same-trust institutions exempt | `dedupe.py` | Same photo in two unrelated institutions → finding; same trust → none |
| F-8 | Compliance Repair Planner with grouping and targeted re-validation | R4 §3.4, R5 §3.6 | P0 | Remedy per rule; group by document; re-run rules whose inputs changed | `repair.py`, `orchestrator.py` | After uploading corrected doc, only affected rules re-run; resolved findings marked RESOLVED |
| F-9 | Officer disposition: confirm / dismiss / escalate, reason required, audited | R2 §12.2, R3 §12.2 | P0 | `POST /findings/{id}/review` | `routes/findings.py` | Review recorded in audit chain |
| F-10 | Tamper-evident hash-chained audit log + verifier | R1, R2 I4, R3 §9 | P0 | `audit_events.prev_hash/hash`; `/audit/verify` | `app/audit.py` | Editing one row is detected at that sequence |
| F-11 | Rule-pack versioning with governed change (proposer ≠ activator) | R2 §12.2, R4 §3.2 | P1 | New version from tolerance change; activation by a different admin | `routes/rules.py` | Same-user activation → 403 |
| F-12 | Institution pre-flight / checklist before submission | R1, R4 §3.8 | P1 | Checklist view computed from rule pack + uploaded docs | `routes/applications.py`, front | Missing doc visible before validation run |
| F-13 | Synthetic fault-injection benchmark incl. hard negatives | R1, R4 §3.7, R5 §3.8 | P1 | `backend/eval/benchmark.py` writes measured report | `eval/` | Report JSON produced from an actual run |
| F-14 | Async processing with real progress | Master prompt §8C | P0 | Job table + worker thread; stages reported | `orchestrator.py` | Job moves queued → running → done |
| F-15 | Alerts (missing, expired, pending, anomaly) | R1, R3 | P2 | In-app notification list derived from findings | front | — (deferred) |
| F-16 | Rule-pack diff between versions | R1, R3 §7 | P2 | Version list with changed params shown | `routes/rules.py` | Diff endpoint shows changed params |

## 3. Non-functional requirements

| ID | Requirement | Source | Priority | Implementation | Acceptance test |
|---|---|---|---|---|---|
| NF-1 | Upload safety: type by magic bytes, size/page limits, safe names, parser failures handled | R4 §9, R5 §11 | P0 | `pipeline/intake.py` | Non-PDF renamed `.pdf` rejected; oversize rejected; malformed PDF rejected cleanly |
| NF-2 | Private storage; no direct file URLs | R3 §17 | P0 | Content-addressed store outside web root; page images served only through authorized endpoint | Unauthenticated page request → 401 |
| NF-3 | Secrets via environment; refuse weak secret in production | Master §9 | P0 | `config.py` startup check | Production mode with default secret fails to start |
| NF-4 | Rate limiting on login and upload | Master §9 | P0 | In-memory token bucket (per IP/user) | 11th rapid login attempt → 429 |
| NF-5 | Security headers, strict CORS | Master §13 | P0 | Middleware | Response headers present |
| NF-6 | Logs without sensitive content | Master §9 | P0 | Structured logs with ids only | Code review |
| NF-7 | Prompt-injection resistance (document text is data) | R3 §17 | P0 | No LLM in pipeline; extracted text never executed or used as instructions | Rule evaluator rejects non-whitelisted AST |
| NF-8 | Health and readiness endpoints | Master §13 | P0 | `/healthz`, `/readyz` (DB + storage + tesseract) | E2E check |
| NF-9 | Accessibility and reduced motion | Master §7 | P0 | Semantic HTML, focus rings, `prefers-reduced-motion` | Browser check |

## 4. Integrations

| Integration | Status in prototype | Requires |
|---|---|---|
| AICTE institutional records | Mock table seeded with synthetic institutions (labelled `simulated`) | AICTE authorization and interface spec |
| DigiLocker / API Setu requester | Not connected; adapter slot only | API Setu registration, user consent flow, approved scopes |
| Issuer portals / reference lookup | Mock issuer registry with configurable availability | Issuer agreements |
| Signed QR on certificates | **Real** Ed25519 verification against synthetic issuer keys | Real issuer public keys |
| PDF digital signatures | Presence + ByteRange coverage check | Full chain validation needs pyHanko + CCA trust roots |
| AICTE portal / SSO | Local accounts | AICTE IdP details |

## 5. Contradictions resolved

| Topic | Conflict | Resolution |
|---|---|---|
| Product name | PRAMAAN (R3, R4) vs Sentinel-EoA (R2) vs unnamed (R1, R5) | **PRAMAAN** |
| Frontend | Next.js (R1, R3) vs React+Vite (R2) vs React (R4, R5) | React 19 + TS + Tailwind v4, esbuild (registry access unavailable; see ARCHITECTURE §Constraints) |
| Rule solver | Z3 (R1, R3) vs OR-Tools CP-SAT (R2) vs Python rules (R4, R5) | Safe expression evaluator; solver optional later — none of the P0 rules need SAT |
| Forensics | Conformal + PyTorch ensemble (R3) vs explainable PDF checks first (R2, R5) | Explainable checks first; conformal deferred (no calibration data — guarantee would be meaningless) |
| API prefix | `/api` (R1, R3–R5) vs `/api/v1` (R2) | `/api/v1` (versioned) |
| Rule outcome vocabulary | passed/failed/incomplete/abstained (R4) vs PS document statuses | Two separate enums: rule outcome `PASS/FAIL/NOT_EVALUABLE`; document verification uses the six PS statuses |
| Roles | 5 (R3) vs 6 (R2, R5) | Prototype: INSTITUTION, OFFICER, ADMIN, AUDITOR. Final decisions stay outside the system |
| Handbook name | "APH 2024-27" vs "2024-25 to 2026-27" (R2 §17.2) | Rule packs record the exact title from the AICTE notice; clause numbers marked `TO_VERIFY` until checked |

## 6. Unsafe or infeasible assumptions found (and how they are handled)

| Assumption | Where | Why unsafe / infeasible | Handling |
|---|---|---|---|
| Conformal prediction "bounds the false-flag rate" | R3 §5.1 | Guarantee needs exchangeable calibration data we don't have | Not implemented; slides mention it only as research basis |
| DigiLocker Rule 9A claim | R3 §10.5 | Sourced from a coaching site, not verified | Not used on slides |
| SIH26261 listed on third-party dashboard | R3 §0 | Not an official source; dashboard blocked from this workspace | Marked "confirm on portal" |
| "SIH 2024 winner" for Team ARTH repo | R5 §4 | Self-reported in README | Cited as "per its README" |
| Weighted idea scores (84/71/63, 79.5, 91…) | R2 §5.2, R3 §4.1 | Subjective estimates | Not presented as data |
| Proof-of-Presence random codes in photos | R1 | Needs portal-side issuance | P2 / future |
| Floor-plan area CV and equipment detection | R1, R3 §10.7 | No data; high false-positive risk | Not built |
| Cross-institution duplicate search | R1, R3 | Needs authorized corpus | Prototype runs only over the synthetic corpus |
| DocTamper dataset for training | R3 §10.8 | Non-commercial, university-only licence | Not used |
| Hard-coded credentials in prior-art repo | R3 §3.2 | Security anti-pattern | Demo credentials generated at seed time, printed once, never committed |

## 7. Engineering assumptions (documented, reversible)

1. Two application categories in the MVP: `EOA_EXISTING` (extension of approval, no change) and `EOA_INTAKE_INCREASE`.
2. Document types: EoA letter (previous year), affidavit, fire-safety NOC, building-stability certificate, faculty summary, infrastructure photo. Field layouts follow public EoA letters; values are synthetic.
3. Academic year 2026-27 starts **1 July 2026** for expiry checks — an assumption marked in the rule pack (`reference_dates.academic_year_start`), to be confirmed against the APH calendar.
4. Rule thresholds (e.g., faculty–student ratio) in the pack are **illustrative placeholders** flagged `clause_status: TO_VERIFY`; the UI shows this flag on every finding that uses them.

## 8. Delivery status (21 Oct 2026)

| Requirement group | Status |
|---|---|
| PS-1 … PS-12 | Implemented and tested; PS-5 uses real signed-QR verification plus clearly labelled simulated record/registry sources |
| F-1 … F-14 | Implemented and tested |
| F-15 alerts, F-16 rule-pack diff view | Not built (P2). Version history and proposal diffs exist |
| NF-1 … NF-9 | Implemented; NF-9 accessibility spot-checked only |
| Integrations (DigiLocker, issuer APIs, AICTE portal/SSO) | Not built — need authorization |

Test evidence: `docs/TEST_PLAN.md`.
