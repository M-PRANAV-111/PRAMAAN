# Demo guide (about 7 minutes)

All data is synthetic and stamped as such. Simulated sources are labelled on screen — say so out loud when they appear.

## Before you start
```bash
cd backend && python -m synthetic.seed --reset && python -m eval.benchmark
FRONT_DIST=../front/dist uvicorn app.main:app --port 8000
```
Open http://localhost:8000. Credentials are in `backend/var/demo_credentials.txt`. Keep `backend/var/demo_files/` open in a file browser for the live upload.

| Synthetic institution | Scenario |
|---|---|
| Shakti Institute of Technology | Clean bundle; EoA letter is a **reprint** printed months later (hard negative: no date flag) |
| Shakti Women's Engineering College | Same trust as Shakti Institute and shares its lab photo (allowed reuse: no flag) |
| Godavari College of Engineering | Missing structural certificate, expired fire NOC (QR authentic but expired), intake changed in affidavit, overlay edit on faculty count, lab photo copied from Krishna |
| Krishna Institute of Engineering | Fire NOC printed validity differs from its signed QR, structural registry offline, EoA letter intake differs from AICTE records, scanned affidavit read by OCR |
| Deccan Institute of Technology | Your live demo: empty account plus files with an expired NOC and a wrong intake, and corrected replacements |

## Script

**0:00 Frame (start page).** "Every flag carries its proof. AI assists, officials decide." Scroll through the synthetic fire safety NOC (`FNOC/SYN/2024/3310`, Godavari College of Engineering) as it moves from the five-document bundle through upload, handover into the AICTE intake slot, coordinate-linked field reading, embedded text-layer peel, signed-QR verification (`Authentic, expired`), Handbook rules (`FIRE.VALID`), and the five-step proof card.

**0:30 Officer queue** (click **Sign in** in the sticky header to open the sign-in dialog, pick the *Scrutiny officer, Ananya Rao* chip or sign in at `/login`). Deficiencies first. Point out the verification mix bar and the "simulated sources" note.

**1:00 Godavari — overlay edit.** Findings → *Integrity indicator — visible number of regular faculty differs*. The embedded text says 48, the page shows 68, OCR confidence 96%. "We call this an indicator, not forgery. A re-render can do this too."

**1:45 Godavari — cross-document conflict.** Select *Intake is the same in the affidavit and the faculty summary*. The viewer zooms to 300 on the affidavit; click the second evidence item to jump to 240 on the summary. AICTE records hold 240, so the planner points at the affidavit. Record **Ask the institution** with a reason — the decision lands in the audit trail.

**2:30 Krishna — verification ladder.** Documents → *View what was read* on the fire NOC: tier 1 signed QR verifies cryptographically but the printed date differs → MISMATCH. Structural certificate: registry offline → SOURCE_UNAVAILABLE → officer action, never a deficiency. Scanned affidavit: values read by OCR with confidence shown.

**3:30 Live — Deccan.** Sign in as `nodal@deccan…`. Start an application, upload the six `D_*.pdf/png` files (watch real stages: extracting, integrity, verifying, re-validating). Findings: expired fire NOC and wrong intake. *What to fix* lists two actions in order.

**4:45 Repair loop.** Replace the fire NOC with `D_Fire_NOC_RENEWED.pdf`. Activity shows a re-check that evaluated only the rules reading the NOC and resolved one finding. Submit to AICTE.

**5:30 Governance.** Rule pack page: clauses marked *not yet verified* — say why. Sign in as `admin@…`, propose `FACULTY.RATIO max_ratio = 15`; show that the same admin cannot activate it; `admin2@…` can. Runs after that record v2026.2.

**6:15 Audit.** Audit trail → *Verify the chain* → intact. (Optional: in a terminal, `sqlite3 backend/var/pramaan.sqlite3 "UPDATE audit_events SET action='x' WHERE seq=5"` then verify again → broken at #5.)

**6:40 Honest numbers.** Benchmark page: 26/26 planted faults, 2 of 8 look-alikes flagged and why, and the caveat that the generator and extractors were built together.

## Judge questions to expect
- *Why not an LLM?* Non-deterministic and unauditable for regulatory findings; document text could carry prompt injection. Deterministic extraction first; a model could be a validated fallback later.
- *How would you get issuer data?* DigiLocker requester onboarding through API Setu with user consent, and AICTE-authorized interfaces. Until then the adapters are labelled mocks.
- *What if the rules are wrong?* Every rule cites its clause, is unit-tested, needs four-eyes activation, and every run records the version — a wrong rule is traceable and reversible.
- *Does it replace officers?* No. It cannot approve, reject or declare forgery; every adverse outcome needs an officer's recorded reason.
