# Integration report — `integration/e2e`, 27 October 2026

Written by the Opus session that resumed the stopped integration run. Status per item:
[INTEGRATION_PROGRESS.md](INTEGRATION_PROGRESS.md). Raw results and the operation matrix:
[INTEGRATION_MATRIX.md](INTEGRATION_MATRIX.md). Every result below was produced on 27 October 2026 by the command
shown; nothing is estimated.

## Outcome

The core backend (Astra), the AI layer (Opus) and the frontend now run as one product on `integration/e2e`. On the
final head every check that can run on this machine passes: backend unit and API tests, contract drift, the
contract-wide smoke matrix, frontend typecheck and build, and all 19 browser scripts on fresh seeds. Two deliverables
are blocked by missing tools, not by defects: the Docker image (Docker is not installed) and reading the CI run
(`gh` is not installed and the repository is private). The pull request could not be opened from here for the same
reason; its description is at the end of this report.

## What was found on restart

- 53 files of uncommitted work from the stopped run. No secrets. Committed unchanged as `5db316e`.
- An unmerged branch `opus/ai-verification` (Part B) and, in the uncommitted work, a smaller competing AI skeleton that
  departed from the Part B contract. The Part B implementation was merged (`8a8da49`); the skeleton's useful parts were
  kept or ported, the rest removed (details below).
- A red baseline: 5 of 19 browser scripts failed. All five were fixed at the cause (`ea36c6c`).
- `07_INTEGRATION.md`, which the resume prompt cites, is not in the repository, its history or the session transcripts.
  Items were taken from the resume prompt's list and acceptance details from Backend Prompt 2, `docs/agent-prompts/INTEGRATION.md`
  and the code (flagged as Question 1 in the progress file).

## Changes to existing files, and why

### Made by the stopped run (committed as found in `5db316e`, verified by today's checks)

| File | Change | Why |
|---|---|---|
| `.github/workflows/ci.yml` | Backend job runs the whole test suite and `scripts.smoke`; frontend job installs Python, Tesseract and Chromium and runs `scripts.e2e` | Smoke and browser suites in CI (A8) |
| `.env.example` | `SHOW_DEMO_ACCOUNTS`; an AI block (replaced this session, see below) | Document new settings |
| `backend/app/config.py`, `backend/tests/test_config.py` | `SHOW_DEMO_ACCOUNTS` setting, refused in production, added to the guard test | Demo sign-in chips only outside production |
| `backend/app/routes/system.py` | `/meta` reports `features.demo_accounts` | The UI shows demo chips only when the server allows it |
| `backend/app/routes/common.py`, `backend/app/schemas.py` | `JobOut.stage_history` (recorded stage codes) and `JobOut.ai_notes` | The journey shows the real recorded stages and skip notes (B1) |
| `backend/app/main.py`, `pipeline/hooks.py`, `routes/documents.py` | AI skeleton wiring | Replaced by Part B this session |
| `contracts/*` | Regenerated | Contract follows the code |
| `front/src/lib/session.tsx`, `pages/AuthPages.tsx` | Removed the browser-only registration adapter (it signed every "registered" user in as a seeded account with a hard-coded password); registration, reset and invitation use the real API payloads | Development-only behaviour removed |
| `front/src/components/SignInCard.tsx` | Demo chips only when `meta.features.demo_accounts`; links follow feature flags | Same |
| `front/src/pages/Queue.tsx` | Server-side search, status filter and paging with `X-Total-Count` | A5 against the real API |
| `front/src/lib/query.ts` | Cache cleared when the signed-in identity changes | No data from a previous account after sign-out |
| `front/src/api/client.ts`, `components/ui.tsx` | Response hook for headers; 403/404/429 messages | Real error states |
| `front/src/components/AppShell.tsx`, `lib/features.ts` | Operation names aligned with the contract (`unreadCount`, `systemStatus`, `respondToFinding`) | Calls the real endpoints |
| `front/src/pages/AdminPages.tsx`, `AuthPages.tsx` (Account) | Session list fields, revoke-others, refresh | A1 against the real API |
| `front/src/components/processing/*` | Recorded stage history, notes, real error message, evidence extractor | B1 |
| `front/src/pages/Workspace.tsx` | Contract field names | Same |
| `front/e2e/accounts_check.py`, `processing_check.py`, `walkthrough.py` | Follow the real registration and payloads | Old checks relied on the removed adapter |

New files from the stopped run: `Dockerfile`, `.dockerignore`, `backend/scripts/smoke.py`, `backend/scripts/e2e.py`,
`front/e2e/core_support.py` and the eight `front/e2e/e2e_*.py` scripts.

### Made by this session

| File | Change | Why | Proof the old behaviour still works |
|---|---|---|---|
| `front/src/pages/Queue.tsx` | Status counts and "All (N)" from `/dashboard` | Counting the current page was wrong once paging moved to the server | tracking_check 16 of 16, e2e_officer, e2e_quality |
| `front/e2e/accounts_check.py` | Asserts the honest "Start an application first" state, creates a real application, then checks the scanner button | The seeded demo institution has no application | accounts_check 22 of 22 |
| `front/e2e/inventory_check.py` | Excuses only the documented `no_benchmark` 404 and asserts the page explains it | A fresh seed has no benchmark report; no product defect | inventory_check 99 of 99 |
| `front/e2e/e2e_officer.py` | Radio selector; then mark-all-read and "Run full check" | The radio's name includes its hint; A2 and validate coverage | 5/5 |
| `front/e2e/e2e_quality.py` | Tabs until the password field has focus | The Show-password toggle sits between the fields | 11/11 |
| `backend/app/ai/*`, `routes/ai.py`, `main.py`, `pipeline/hooks.py`, `routes/documents.py`, `routes/common.py` | Merge of `opus/ai-verification`; the skeleton's `app/ai/pipeline.py`, its fixtures, `migrations/0008_ai.sql` and `tests/test_ai.py` removed; job notes now read from the Part B `job_notes` table | Part B wins over the skeleton (contract: three routing outcomes separate from the derived status, page grounding, validated wording) | `Ran 194 tests … OK` on the branch before; the full suite after (below); AI off parity test |
| `backend/app/schemas.py` | Removed the skeleton's duplicate `RoutingOut`/`AIStatusOut` | Part B types live in `schemas_ai.py` | contract check |
| `backend/app/ai/config.py`, `provider.py`, `client.py`, `install.py`, `schemas_ai.py`; new `ai/fixture.py`, `ai/fixtures/extract_affidavit.json` | `AI_PROVIDER=fixture` (recorded hand-authored answers) and `AI_TEST_FAULT` (rate_limit, timeout, invalid_json) wrapped around the real provider chain; refused at startup unless `APP_ENV=test`; status reports `simulated` | B6; lets a real server exercise the AI path with no key | `tests.test_ai_test_hooks` (10), `test_production_refusals.AIRefusals` |
| `backend/tests/test_ai_provider.py` | The exact status-field set now includes `simulated` | Guard stays exact | `StatusApiTests` OK |
| `backend/scripts/smoke.py` | Bodies for `aiKillSwitch` and `reviewAiSuggestion` (fixture SQL only in the temporary database) | The two new Part B POSTs | smoke 0 failed operations |
| `front/src/components/processing/OutcomeCard.tsx` | On `RoutingOut`: three outcomes, reasons linking to the finding or documents tab, AI use, automated actions | B3 | e2e_ai `data-outcome` equals the API outcome |
| `front/src/components/processing/ProcessingJourney.tsx`, `lib/format.ts` | Suggestion wording per reason; AI-grounded values labelled | B2 | e2e_ai fixture |
| `front/src/pages/Workspace.tsx` | Evidence dialog: AI-assisted label; open suggestions with audited Confirm/Dismiss for officers and admins | Part B routing holds a case until an officer reviews suggestions; no UI could do it | e2e_ai fixture: dismissal clears the routing reason, audited |
| `front/src/pages/AdminPages.tsx` | AI status on `AiStatusOut`, simulated label (dusk), provider error in turmeric, audited kill switch | B5 | e2e_ai fixture: kill switch engage and release |
| `backend/app/routes/system.py`, `front/src/components/CameraScanner.tsx` | `features.simulated_camera` only outside production; without it the scanner offers file upload only; with it the viewfinder is labelled simulated | The drawn synthetic page (with the demo institution's details) could be submitted as evidence in production | processing_check 13 of 13 (scanner flow in test); `test_simulated_camera_is_not_offered` |
| `front/e2e/e2e_ai.py` | Rewritten for the Part B contract | B1–B7 in a browser | fixture 25/25, rate_limit 19/19, none 16/16 |
| `front/e2e/e2e_admin.py`, `e2e_password.py` | Decline with reason and System page; Account page sessions, refresh, revoke, change password | A1 coverage | 7/7, 7/7 |
| `.env.example` | AI block now lists the Part B variables (the Anthropic adapter it described was removed) | Accurate settings | — |
| `docs/DEMO_GUIDE.md` | `SHOW_DEMO_ACCOUNTS`, `--reset` warning, routing card, simulated camera, AI status | Matches what runs (seed, benchmark and server checked today) | — |
| New tests | `test_production_refusals` (19, one per refusal), `test_job_restart`, `test_readiness` (4) | A6; failure and retry table rows that had no test | themselves |

The merge also brought Opus's own documented edits to `README.md`, `docs/API_CONTRACT.md`, `ARCHITECTURE.md`,
`PRAMAAN_COMPLETE_PROJECT.md`, `REQUIREMENTS_MATRIX.md`, `SECURITY.md`, `TEST_PLAN.md`, `backend/eval/benchmark.py`,
`backend/scripts/gen_contract.py` and `backend/app/pipeline/integrity.py` (AI text-layer claims get the overlay-edit check).

## Checks on the final head

All on 27 October 2026. Head `35f8a19`; the e2e_security re-run is on `df824ab`, which changes only that script.

| Check | Command | Result |
|---|---|---|
| Contract drift | `cd backend; python -m scripts.gen_contract --check` | PASS — `61 operations, 71 schemas verified` |
| Backend unit and API tests | `cd backend; python -m unittest discover -s tests -t .` | PASS — `Ran 228 tests in 214.125s`, `OK (skipped=3)` (live-provider tests, no key) |
| Smoke matrix | `cd backend; python -m scripts.smoke` | PASS — `61 operations; 393 assertions passed; 0 failed operations.` |
| Frontend typecheck | `cd front; npm run typecheck` | PASS |
| Frontend build | `cd front; npm run build` | PASS — 359.3 KB signed-in JS, 43.5 KB start-page chunk, 49.5 KB CSS |
| Browser suite, fresh seed per script | `cd backend; python -m scripts.e2e` | 18/19 — e2e_security raced its own sign-out (setup requests correctly refused with 403); script fixed |
| e2e_security after the fix | `python -m scripts.e2e e2e_security.py` ×3 | PASS — `3/3 browser scripts passed`, 15 checks each |
| Benchmark | `python -m eval.benchmark` | 26 of 26 planted faults; 2 of 8 look-alikes flagged (incremental-save indicator) — unchanged |
| Demo start | seed, benchmark, server with `SHOW_DEMO_ACCOUNTS=true` | `/api/v1/ready` 200; `/meta`: demo_accounts true, simulated_camera true, routing true, ai false |
| Docker image | `docker build -t pramaan .` | Not run — Docker not installed |
| CI | GitHub Actions on `integration/e2e` | Not observed — `gh` not installed, repository private |

Earlier the same day: resume baseline (backend 78 OK, smoke 375/0, browser 14/19), re-run of the five red scripts
(5/5), Part B checkpoint (backend 204 OK, smoke 393/0, browser 19/19). Operation matrix: 55 of 61 operations verified
(smoke as expected for every caller and a 2xx in a browser run); the other six are listed in the matrix with reasons.

## Not complete, and why

| Item | Reason | What was done instead |
|---|---|---|
| A7 Docker image | Docker is not installed (`docker: command not found`) | Its steps are tested separately: frontend typecheck and build, backend production refusals (including a real process refusing to start) |
| A8 CI run | `gh` not installed; GitHub API answers `Not Found` for the private repository | `scripts.smoke` and `scripts.e2e` pass locally; the CI file runs both |
| Pull request | Needs `gh` or a token | Branch pushed; description below; open it at `https://github.com/M-PRANAV-111/PRAMAAN/compare/main...integration/e2e` |
| Live AI provider | No `GEMINI_API_KEY` / `GROQ_API_KEY`; no live call was ever made | Hand-authored recorded answers under `APP_ENV=test`, labelled simulated; three live tests skip |
| Validated AI wording in a browser | No wording can be recorded once for all findings | Covered by `test_explain` (11) |
| `updateAccount`, `documentHistory`, `getAccount` UI | Not added: would be new features | Smoke-verified API; Question 2 |
| Compose stack, TLS terminator, Postgres/Redis/MinIO outages (`docs/agent-prompts/INTEGRATION.md`) | Needs Docker; this build uses SQLite and local storage | Readiness 503 tests for database, storage and OCR |
| `07_INTEGRATION.md` | Not in the repository | Question 1 |

Smaller observations, left as they were (outside this work, no defect in behaviour): the admin registrations list and
the readiness pill use red tape for "declined" and "degraded", which the palette reserves for deficiencies;
`ProofChain` has a block for `ai_suggestions` on findings that no backend produces (renders nothing); the frontend
names a `account` operation that the contract does not have (inert behind `hasEndpoint`).

## Pull request description

Title: Integrate core backend, AI layer and frontend (integration/e2e)

## Summary
Brings the core backend (accounts, notifications, tracking, reports, operations), the optional AI layer (grounded
extraction, validated wording, three-outcome routing, kill switch, data policy) and the frontend together on one
contract, with smoke and browser suites in CI.

- Preserves the stopped integration run's work (`5db316e`) and fixes the five browser scripts it left red.
- Merges `opus/ai-verification` in place of an uncommitted AI skeleton; ports `AI_TEST_FAULT` and a recorded fixture
  provider onto it, both refused unless `APP_ENV=test`.
- Wires the Part B contract into the UI: routing card, AI status and kill switch, AI-grounded labels, officer review of
  AI suggestions.
- Removes development-only behaviour: the browser-only registration adapter (stopped run) and, in production, the
  camera scanner's drawn synthetic page.
- Adds one test per production refusal, restart-recovery and readiness tests, and eight browser scripts.

Decision support only: nothing approves, rejects or declares forgery; simulated sources and the test fixture are
labelled.

## Test plan (run 2026-10-27)
- [x] `python -m unittest discover -s tests -t .` — 228 tests OK (3 live-provider skips)
- [x] `python -m scripts.gen_contract --check` — 61 operations, 71 schemas
- [x] `python -m scripts.smoke` — 61 operations, 393 assertions, 0 failed
- [x] `npm run typecheck`, `npm run build`
- [x] `python -m scripts.e2e` — 18/19 on the final run; e2e_security fixed, then 3/3
- [ ] `docker build -t pramaan .` — not run (no Docker)
- [ ] CI on this branch — not observed

Details: `docs/sih-plan/INTEGRATION_REPORT.md`, `INTEGRATION_MATRIX.md`, `INTEGRATION_PROGRESS.md`.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
