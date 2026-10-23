ROLE
You are the backend and integration lead for PRAMAAN, our Smart India Hackathon 2026 project for SIH26261 (AICTE application validation, document authentication and regulatory compliance verification). This pass has three goals: prove that everything in the backend works, remove made-up data (keeping only the login details), and make the whole site fast and responsive without changing how it looks. You may edit backend/, contracts/ (only through the generator), the docs, and front/ for performance only.

Run this pass on the repository as it is now, before any stack migration (docs/agent-prompts/BACKEND.md). A clean, verified codebase is easier to migrate.

READ FIRST
README.md, docs/PRAMAAN_COMPLETE_PROJECT.md, docs/ARCHITECTURE.md, docs/API_CONTRACT.md, docs/TEST_PLAN.md, docs/DEMO_GUIDE.md, backend/synthetic/seed.py, backend/app/pipeline/verification.py, backend/app/pipeline/orchestrator.py, backend/app/routes/, front/src/lib/query.ts, front/src/lib/router.tsx, front/src/main.tsx.

The web client was just redesigned (layout language from format.obys.agency: block-letter wordmark, label strip, shaped sheets on an ink canvas; colours ink #1d2b4f, paper #f2f5f0, red tape #b4232c, turmeric #9a6410, leaf, dusk). Do not change colours, fonts, the wordmark, the strip or the layout.

────────────────────────────────────────
PART 1 — PROVE THE BACKEND WORKS
────────────────────────────────────────
1. Baseline, and report the real output of each:
     cd backend && pip install -r requirements.txt
     python -m unittest tests.test_units tests.test_api -v
     python -m scripts.gen_contract --check
     python -m synthetic.seed --reset && python -m eval.benchmark
     cd ../front && npm install && npm run typecheck && npm run build
2. Write backend/scripts/smoke.py and run it against a live server (uvicorn on a free port, fresh temporary DATA_DIR). It must call every one of the 27 operations in contracts/openapi.json as each role (institution, officer, admin, auditor, signed out) and assert the expected status: success for allowed roles, 401 signed out, 403 for the wrong role, 404 for another institution's objects, 422 for bad input. Print a pass/fail table. Add it to CI.
3. Walk every pipeline stage with real files and confirm the stored result: intake rejects (wrong type, oversize, encrypted, malformed), text-layer extraction, OCR on a scanned page, each rule type (PASS, FAIL, NOT_EVALUABLE, NOT_APPLICABLE), every verification status the ladder can produce, integrity indicators (overlay edit, incremental save), duplicate detection with the same-trust allow-list, repair plan grouping, targeted re-validation after a corrected upload, officer review with reason, four-eyes rule activation, audit chain verify and tamper detection, health and readiness (including 503 when OCR or the database is missing).
4. Fix every defect you find. For each one record: symptom, cause, fix, test that now covers it.

────────────────────────────────────────
PART 2 — REMOVE MADE-UP DATA, KEEP ONLY LOGIN DETAILS
────────────────────────────────────────
Keep:
- Demo user accounts (email, name, role, password handling exactly as now: random or SEED_DEMO_PASSWORD, written once to var/demo_credentials.txt, never committed).
- For each institution account, the institution record it belongs to (name, Permanent ID, state, trust). A login needs it; these names keep their "(Synthetic)" suffix.
- The rule pack (it is configuration, not data) and the database schema.

Remove from the default seed and from the running app:
- Pre-created applications, documents, claims, findings, validation runs, reviews and jobs.
- Simulated AICTE records (aicte_records rows), synthetic issuers, issuer_registry rows and var/synthetic_issuer_keys.json.
- Pre-generated files in var/demo_files.
- Any hard-coded institution names, counts, example values or screenshots in the frontend, README or docs that present made-up data as if it were real. (The landing page has already been cleaned; check it anyway.)

Behaviour after removal:
- `python -m synthetic.seed --reset` creates only the accounts and their institutions, then prints the credentials.
- With no source configured, the verification ladder must never say VERIFIED. The AICTE-record and issuer-registry tiers return SOURCE_UNAVAILABLE with the reason "No authorized source connected". The signed-QR tier with no registered issuer key returns MANUAL_REVIEW_REQUIRED ("Issuer key not registered"). Rules that need AICTE records become NOT_EVALUABLE (record_unavailable) and go to an officer.
- Simulated sources become an explicit opt-in for demos: `python -m synthetic.simulated_sources --enable` (and `--disable`) inserts or removes clearly labelled simulated AICTE records and issuer keys for the existing demo institutions. Every result they produce keeps simulated: true and the "Simulated source" label. Default is off.
- Demo files become something a person uploads by hand: `python -m synthetic.make_demo_files <output_dir>` writes the SYNTHETIC-stamped PDFs and PNGs (clean set, set with planted problems, corrected replacements, a scanned copy). Nothing is inserted into the database.
- The benchmark keeps using its own temporary database and never writes to the main one. The Benchmark page shows its empty state until a run exists.
- Tests no longer depend on seeded scenarios. Build fixtures inside the tests (factory helpers that create institutions, users and applications in a temporary database, and upload generated files through the API). Keep the intent of every existing assertion. Add tests: a fresh seed has zero applications, documents, findings, aicte_records, issuers and registry rows; with no sources the ladder never returns VERIFIED; with simulated sources enabled every such result has simulated: true; disabling them removes the rows.
- Empty states: with a fresh seed, sign in as each role and open every page (institution home, application workspace tabs, queue, rule pack, audit trail, benchmark). Each shows a clear empty state with the next step. No blank screens, console errors (other than the expected 401 before sign-in) or broken layouts.
- Docs: update README, docs/DEMO_GUIDE.md (the demo now starts empty: generate the demo files, optionally enable simulated sources, upload as an institution, review as an officer), docs/TEST_PLAN.md and docs/PRAMAAN_COMPLETE_PROJECT.md sections 16, 18, 19 and 21. Replace screenshots that show pre-seeded applications with ones taken from the new flow.

────────────────────────────────────────
PART 3 — MAKE IT FAST, KEEP THE LOOK
────────────────────────────────────────
Measure first, change second, measure again. Put before and after numbers in docs/TEST_PLAN.md.

Backend
- Page images: cache rendered PNGs on disk keyed by (sha256, page, dpi). Documents are content-addressed, so serve them with `Cache-Control: private, max-age=31536000, immutable` and an ETag. Target under 20 ms for a cached page.
- Render each PDF page once per processing job and share it between QR decoding, the OCR fallback and the visible-text checks. Batch the visible-text OCR crops into one Tesseract call per page instead of one subprocess per value. Report median processing time per document type (5 runs each) before and after.
- Remove N+1 queries in list endpoints (application_summary currently runs several queries per application). Create a test-only load fixture of 200 synthetic applications in a temporary database and measure p50 and p95 for GET /applications, /applications/{id}, /applications/{id}/findings and /dashboard. Target p95 under 150 ms on a laptop.
- Optional: signed-out visitors currently get a 401 from /auth/me, which shows as console noise. If you add a session endpoint that returns 200 with "user": null, regenerate the contract and update front/src/lib/session.tsx in the same commit.

Frontend (performance only)
- The data layer was just rewritten: per-key subscriptions (a poll on one query does not re-render the page), unchanged responses keep the old object, background refetch, prefetch on link hover (front/src/main.tsx), tab switches keep the scroll position, quick View Transitions between pages. Verify each behaviour with an automated test.
- Measure with Playwright plus PerformanceObserver ("longtask" and "event" entries): finding switch, tab switch, route change, review submit, and upload progress updates. Target: every interaction paints within 100 ms and no long task over 50 ms during them. Record the numbers.
- Budgets: JavaScript at most 350 KB minified (about 337 KB now, React included), CSS at most 50 KB, only the two above-the-fold fonts preloaded. Fail the build if a budget is exceeded.
- Respect prefers-reduced-motion everywhere. Do not add animation libraries. Do not change colours, fonts, the block wordmark, the label strip or the layout.

────────────────────────────────────────
RULES
────────────────────────────────────────
- Never report a check as passing unless you ran it. Paste a summary of the real output into docs/TEST_PLAN.md with the date.
- PRAMAAN is decision support. No endpoint, enum or message may approve, reject, or call a document forged, fake or fraudulent. Keep test_no_adverse_decision_vocabulary passing.
- Synthetic data only. No real institution, person or document anywhere in the repo, the database or the screenshots.
- Do not weaken a test, a safeguard or a security setting to get a green build. If something cannot be fixed, list it as a known defect with the reason.
- Do not change rule logic, thresholds or clause references. Rules marked TO_VERIFY stay that way until a person checks them against the Approval Process Handbook.
- Change the API only in backend/app/schemas.py and the routes, then regenerate contracts/ (python -m scripts.gen_contract). Never hand-edit contracts/.

FINAL REPORT
1. Part 1: the smoke table, defects found and fixed, test counts.
2. Part 2: exactly what was removed, what remains (accounts and their institutions), the new demo flow, and proof that a fresh seed is empty apart from accounts.
3. Part 3: before and after numbers for every measurement, and the budgets.
4. Anything not done, with the reason, and what still needs AICTE authorization or real credentials.
