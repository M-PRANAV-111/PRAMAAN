# Integration matrix

Every result below was produced by a command run on the date shown. A row without a dated command is not a result.

## Resume baseline — 2026-10-27

Branch `integration/e2e` at `5db316e` (the stopped run's uncommitted work, committed unchanged as `wip:`). `origin/main`
had not moved (still `7587110`), so no rebase was needed. Windows 11, Python 3.13.14, Node 22.19.0, Chromium 1248
(Playwright), Tesseract installed. Docker is **not installed** on this machine.

| Check | Command | Result today |
|---|---|---|
| Backend unit and API tests | `cd backend; python -m unittest discover -s tests -t .` | **PASS** — `Ran 78 tests in 95.749s` / `OK` |
| Contract drift | `cd backend; python -m scripts.gen_contract --check` | **PASS** — `58 operations, 66 schemas verified` |
| Contract smoke matrix | `cd backend; python -m scripts.smoke` | **PASS** — `58 operations; 375 assertions passed; 0 failed operations.` |
| Frontend typecheck | `cd front; npm run typecheck` | **PASS** — exit 0 |
| Frontend build | `cd front; npm run build` | **PASS** — `signed-in JS 353.5 KB, start-page chunk 43.5 KB, css 49.4 KB` |
| Browser suite, each script on its own fresh seed (`SEED_DEMO_PASSWORD` generated, `EMAIL_PROVIDER=console`, `APP_ENV=test`) | `cd backend; python -m scripts.e2e` | **FAIL** — `14/19 browser scripts passed` |
| Docker image | `docker build -t pramaan .` | **Not run** — `docker: command not found` |

Browser scripts, one line each (counts are the script's own output):

| Script | Result | First failing line |
|---|---|---|
| journey_check.py | PASS — 48 of 48 | — |
| signin_check.py | PASS — 28 checks | — |
| walkthrough.py | PASS — exit 0 (no per-check output) | — |
| accounts_check.py | **FAIL — 20 of 21** | `FAIL  Applicant Dashboard switches to Upload / Scan section` |
| tracking_check.py | **FAIL** — exception at line 89 | `Locator.click: Timeout 30000ms exceeded … get_by_role("group", name="Filter by status").get_by_role("button", name="All (")` |
| processing_check.py | PASS — 13 of 13 | — |
| inventory_check.py | **FAIL — 92 of 93** | `FAIL  zero unhandled page or unexpected console errors across all routes [desktop/officer: console: Failed to load resource: … 404 (Not Found) …]` |
| a11y_check.py | PASS — 10 of 10 | — |
| measure_page.py | PASS — exit 0 (informational) | — |
| e2e_admin.py | PASS — 5/5 | — |
| e2e_ai.py (fixture) | PASS — 9/9 | — (ran against the uncommitted AI skeleton, see the progress file) |
| e2e_ai.py (rate_limit) | PASS — 8/8 | — (same) |
| e2e_ai.py (none) | PASS — 7/7 | — (same) |
| e2e_application.py | PASS — 24/24 | — |
| e2e_officer.py | **FAIL** — exception at line 33 after 2 passes | `Locator.check: Timeout 30000ms exceeded … get_by_role("radio", name="Confirm", exact=True)` |
| e2e_password.py | PASS — 2/2 | — |
| e2e_quality.py | **FAIL** — exception at line 20 after 1 pass | `AssertionError: Locator expected to be visible … get_by_role("heading", name="Scrutiny queue")` |
| e2e_register.py | PASS — 3/3 | — |
| e2e_security.py | PASS — 9/9 | — |

Separately, the unmerged branch `opus/ai-verification` (worktree `../pramaan-opus`, 3 commits on top of
`astra/core-backend`) was tested today: `python -m unittest discover -s tests -t .` → `Ran 194 tests in 217.717s` /
`OK (skipped=3)`. The 3 skips are the opt-in live-provider tests (no API key on this machine).

### Causes of the red baseline

| Script | Cause | Fix |
|---|---|---|
| accounts_check.py | The seeded live-demo institution (Deccan) has no application, so the Upload / Scan section correctly shows "Start an application first". The old check passed only through the removed browser-only registration adapter. | The script now asserts that empty state, creates a real application through the UI, and then checks the scan control. |
| tracking_check.py | The stopped run moved queue search and paging to the server but then computed status counts from the current page and dropped the total from "All". | `Queue.tsx`: status counts and the "All (N)" total come from `GET /api/v1/dashboard`, which uses the same visibility scope as the list. |
| inventory_check.py | A fresh seed has no benchmark report; `GET /api/v1/benchmark` answers its documented 404 (`no_benchmark`) and Chromium logs it as a failed resource. The page itself shows "No benchmark has been run yet". No product defect. | The script excuses only that one request (by URL, only when no report exists) and now asserts the empty-state text. |
| e2e_officer.py | The radio's accessible name is its label plus hint ("Confirm The finding stands …"), so an exact match on "Confirm" can never succeed. | Selector matches names starting with "Confirm". |
| e2e_quality.py | Tab order is Email → "Show password" → Password; the script pressed Tab once and typed the password into the toggle. | The script tabs until the password field has focus (still keyboard only). |

Re-run after the fixes (commit `ea36c6c`), 2026-10-27, each on a fresh seed:
`python -m scripts.e2e accounts_check.py tracking_check.py inventory_check.py e2e_officer.py e2e_quality.py` →
`5/5 browser scripts passed` (accounts_check 22 of 22, tracking_check 16 of 16, inventory_check 99 of 99,
e2e_officer 3/3, e2e_quality 11/11).

## Failure and retry table — 2026-10-27

Each row names the behaviour the code implements and the test that exercises it. "Result" is from the runs listed
in [INTEGRATION_PROGRESS.md](INTEGRATION_PROGRESS.md) on this date.

| Failure | What happens | Where | Test | Result |
|---|---|---|---|---|
| Transient I/O error or timeout inside a job | Retried, at most 3 attempts, waiting 2 s then 8 s, never past the job deadline | `pipeline/orchestrator.py` `run_job` | `test_jobs.test_transient_retry_and_stage_codes`, `test_jobs.test_backoff_two_retries_only` | PASS |
| Non-transient error (bad input, rule error) | Not retried; job FAILED with an error code | same | `test_jobs.test_validation_failure_is_not_retried` | PASS |
| Job runs past `JOB_TIMEOUT_SECONDS` | Child process terminated; job FAILED `timeout` | supervised worker | `test_jobs.test_hard_timeout_terminates_child`, `test_jobs.test_supervised_child_stops_when_parent_pipe_closes` | PASS |
| Worker stopped mid-job (crash or restart) | Jobs left RUNNING are re-queued at start ("Re-queued after restart") and finish once | `Worker.start` | `test_job_restart.test_interrupted_job_is_requeued_and_finishes` (added today) | PASS |
| Client retries an upload | Replay inside the window returns the same job; expired or foreign replay refused | `routes/documents.py` | `test_jobs.test_upload_replay_expiry_and_owner_scope` | PASS |
| Email provider error | 3 attempts, 2 s then 8 s; failure metric carries a sanitised code only | `email.py` `_loop` | `test_email.test_provider_retries_and_sanitized_failure_metric` | PASS |
| AI provider 429, 5xx or timeout | Primary → secondary model → fallback provider → none; at most 3 requests with growing back-off; INFO job note; deterministic result unchanged | `ai/client.py` | `test_ai_provider.test_429_goes_to_secondary_then_fallback_then_none`, `test_at_most_three_attempts`, `test_ai_pipeline` (server errors, timeouts), `test_ai_test_hooks.FaultInjectionTests`, browser `e2e_ai` `rate_limit` | PASS |
| AI answer breaks the schema | Treated as a failed request, falls through; note `schema_violation` | `ai/client.py`, adapters | `test_ai_provider.test_a_response_that_fails_validation_falls_through`, `test_ai_test_hooks.test_invalid_json` | PASS |
| AI key missing | Not counted as an attempt; note `no_api_key` | `ai/client.py` | `test_ai_provider.test_missing_key_is_not_an_attempt` | PASS |
| AI daily request or page budget used up | No request; `budget_exhausted` recorded and shown in status | `ai/client.py` | `test_ai_provider.test_budget_exhaustion_uses_none_and_is_recorded`, `test_page_budget` | PASS |
| One AI request hangs | Bounded by the call deadline | `ai/client.py` | `test_ai_robustness.test_each_request_is_bounded_by_the_call_deadline` | PASS |
| AI step raises | Contained; job finishes with the deterministic result and a note | `pipeline/ai_extract.py` | `test_ai_pipeline.test_a_crash_inside_the_step_is_contained` | PASS |
| Database, storage or OCR unavailable | `/api/v1/ready` answers 503 and names the failing check | `routes/system.py` | `test_readiness` (4 tests, added today) | PASS |
| Browser loses the network | Error with a Retry button; Retry recovers | `components/ui.tsx` `ErrorBox` | browser `e2e_quality` `PASS offline error recovers with Retry` | PASS |
| Too many sign-in or reset attempts | 429 shown as "Too many attempts. Wait a minute." | `api/client.ts` | browser `e2e_security` `PASS rate limit produces friendly UI` | PASS |

Not covered here: Postgres, Redis and MinIO outages from `docs/agent-prompts/INTEGRATION.md` do not apply (this
build uses SQLite and local storage); a compose-stack outage test needs Docker, which is not installed.

## Final checks — 2026-10-27

Head `35f8a19` for every row except the e2e_security re-run, which is `df824ab` (only `front/e2e/e2e_security.py`
changed between them).

| Check | Command | Result |
|---|---|---|
| Contract drift | `cd backend; python -m scripts.gen_contract --check` | **PASS** — `61 operations, 71 schemas verified` |
| Backend unit and API tests | `cd backend; python -m unittest discover -s tests -t .` | **PASS** — `Ran 228 tests in 214.125s` / `OK (skipped=3)`; the 3 skips are the opt-in live-provider tests (no key) |
| Contract smoke matrix | `cd backend; python -m scripts.smoke` | **PASS** — `61 operations; 393 assertions passed; 0 failed operations.` |
| Frontend typecheck | `cd front; npm run typecheck` | **PASS** — exit 0 |
| Frontend build | `cd front; npm run build` | **PASS** — `signed-in JS 359.3 KB, start-page chunk 43.5 KB, css 49.5 KB` |
| Browser suite on fresh seeds | `cd backend; python -m scripts.e2e` | **18/19** — every script passed except e2e_security (`waiting for get_by_text("Too many attempts. Wait a minute.")`): its setup requests raced the sign-out and were correctly refused with 403. Script fixed in `df824ab` |
| e2e_security after the fix | `python -m scripts.e2e e2e_security.py e2e_security.py e2e_security.py` | **PASS** — `3/3 browser scripts passed`, each 15 PASS, 0 FAIL |
| Docker image | `docker build -t pramaan .` | **Not run** — Docker not installed |

Per script on the final run: journey_check 48 of 48 · signin_check 28 PASS · walkthrough exit 0 · accounts_check 22 of 22 ·
tracking_check 16 of 16 · processing_check 13 of 13 · inventory_check 99 of 99 · a11y_check 10 of 10 · measure_page
exit 0 · e2e_admin 7/7 · e2e_ai fixture 25/25, rate_limit 19/19, none 16/16 · e2e_application 24/24 · e2e_officer 5/5 ·
e2e_password 7/7 · e2e_quality 11/11 · e2e_register 3/3 · e2e_security 15 PASS (after the fix).

## Operation matrix — final run

Generated 2026-10-27 from `contracts/openapi.json`, the frontend call sites, the final smoke output and the server logs
of the final browser runs (with the passing e2e_security re-run in place of the raced one).

How it is built: every operation in the contract; the frontend files that name it; the smoke result per caller (`OUT`
= signed out, then each role, then the invalid-input and foreign-owner probes); and the requests the server logged
during the browser runs (status: scripts). A row is **Verified** when smoke passed and a browser run reached it with
a 2xx. "Browser runs" counts requests made by the UI and the scripts' own API reads alike. At the resume baseline the
counts were Verified 42, Partial (UI not exercised) 13, Partial (no UI) 2, API only 1, over 58 operations.

| Operation | Method and path | UI call sites | Smoke today (OUT / INST / OFF / ADMIN / AUD / invalid / foreign) | Browser runs today (status: scripts) | State |
|---|---|---|---|---|---|
| `getAccount` | `GET /api/v1/account` | components/AppShell.tsx, lib/features.ts | 401 / 200 / 200 / 200 / 200 / n/a / n/a | not hit | Partial (UI not exercised by a browser run) |
| `listSessions` | `GET /api/v1/account/sessions` | pages/AuthPages.tsx | 401 / 200 / 200 / 200 / 200 / n/a / n/a | 200: e2e_password, e2e_quality | Verified |
| `revokeOtherSessions` | `POST /api/v1/account/sessions/revoke-others` | pages/AuthPages.tsx | 401 / 200 / 200 / 200 / 200 / n/a / n/a | 200: e2e_password | Verified |
| `revokeSession` | `DELETE /api/v1/account/sessions/{session_id}` | pages/AuthPages.tsx | 401 / 200 / 200 / 200 / 200 / n/a / 404 | 200: e2e_password | Verified |
| `updateAccount` | `PATCH /api/v1/account` | not called by UI | 401 / 200 / 200 / 200 / 200 / 422 / n/a | not hit | Partial (no UI) |
| `acceptRegistration` | `POST /api/v1/admin/registrations/{registration_id}/accept` | pages/AdminPages.tsx | 401 / 403 / 403 / 200 / 403 / 422 / n/a | 200: e2e_register | Verified |
| `deactivateUser` | `POST /api/v1/admin/users/{user_id}/deactivate` | pages/AdminPages.tsx | 401 / 403 / 403 / 200 / 403 / 422 / n/a | 200: e2e_admin | Verified |
| `declineRegistration` | `POST /api/v1/admin/registrations/{registration_id}/decline` | pages/AdminPages.tsx | 401 / 403 / 403 / 200 / 403 / 422 / n/a | 200: e2e_admin | Verified |
| `inviteUser` | `POST /api/v1/admin/invitations` | pages/AdminPages.tsx | 401 / 403 / 403 / 202 / 403 / 422 / n/a | 202: e2e_admin | Verified |
| `listRegistrations` | `GET /api/v1/admin/registrations` | components/AppShell.tsx, lib/features.ts, pages/AdminPages.tsx | 401 / 403 / 403 / 200 / 403 / 422 / n/a | 200: e2e_admin, e2e_register | Verified |
| `listUsers` | `GET /api/v1/admin/users` | components/AppShell.tsx, lib/features.ts, pages/AdminPages.tsx | 401 / 403 / 403 / 200 / 403 / 422 / n/a | 200: e2e_admin | Verified |
| `reactivateUser` | `POST /api/v1/admin/users/{user_id}/reactivate` | pages/AdminPages.tsx | 401 / 403 / 403 / 200 / 403 / n/a / n/a | 200: e2e_admin | Verified |
| `systemStatus` | `GET /api/v1/admin/system` | components/AppShell.tsx, lib/features.ts, pages/AdminPages.tsx | 401 / 403 / 403 / 200 / 200 / n/a / n/a | 200: e2e_admin, e2e_ai[fixture], e2e_ai[none], e2e_ai[rate_limit] | Verified |
| `aiKillSwitch` | `POST /api/v1/ai/kill-switch` | pages/AdminPages.tsx | 401 / 403 / 403 / 200 / 403 / 422 / n/a | 200: e2e_ai[fixture] | Verified |
| `aiStatus` | `GET /api/v1/ai/status` | components/AppShell.tsx, lib/features.ts, pages/AdminPages.tsx | 401 / 403 / 403 / 200 / 200 / n/a / n/a | 200: e2e_admin, e2e_ai[fixture], e2e_ai[none], e2e_ai[rate_limit] | Verified |
| `createApplication` | `POST /api/v1/applications` | pages/InstitutionHome.tsx | 401 / 201 / 403 / 403 / 403 / 422 / n/a | 201: accounts_check, e2e_ai[fixture], e2e_ai[none], e2e_ai[rate_limit], e2e_application, walkthrough; 403: e2e_security | Verified |
| `getApplication` | `GET /api/v1/applications/{application_id}` | main.tsx, pages/InstitutionHome.tsx, pages/Workspace.tsx | 401 / 200 / 200 / 200 / 200 / n/a / 404 | 200: a11y_check, accounts_check, e2e_ai[fixture], e2e_ai[none], e2e_ai[rate_limit], e2e_application, e2e_officer, inventory_check, processing_check, signin_check, tracking_check, walkthrough; 404: e2e_security | Verified |
| `listApplications` | `GET /api/v1/applications` | main.tsx, pages/InstitutionHome.tsx, pages/Queue.tsx | 401 / 200 / 200 / 200 / 200 / 422 / n/a | 200: a11y_check, accounts_check, e2e_admin, e2e_ai[fixture], e2e_ai[none], e2e_ai[rate_limit], e2e_application, e2e_officer, e2e_password, e2e_quality, e2e_register, e2e_security, inventory_check, processing_check, signin_check, tracking_check, walkthrough | Verified |
| `listRuns` | `GET /api/v1/applications/{application_id}/runs` | pages/Workspace.tsx | 401 / 200 / 200 / 200 / 200 / n/a / 404 | 200: e2e_application, inventory_check, tracking_check, walkthrough | Verified |
| `submitApplication` | `POST /api/v1/applications/{application_id}/submit` | pages/Workspace.tsx | 401 / 200 / 403 / 403 / 403 / n/a / 404 | 200: e2e_ai[fixture], e2e_application, walkthrough | Verified |
| `validateApplication` | `POST /api/v1/applications/{application_id}/validate` | pages/Workspace.tsx | 401 / 202 / 202 / 202 / 403 / n/a / 404 | 202: e2e_officer | Verified |
| `listAudit` | `GET /api/v1/audit` | main.tsx, pages/Oversight.tsx, pages/Workspace.tsx | 401 / 403 / 200 / 200 / 200 / n/a / n/a | 200: accounts_check, e2e_ai[fixture], e2e_officer, inventory_check, walkthrough | Verified |
| `verifyAudit` | `GET /api/v1/audit/verify` | pages/Oversight.tsx | 401 / 403 / 200 / 200 / 200 / n/a / n/a | 200: e2e_officer, walkthrough | Verified |
| `acceptInvitation` | `POST /api/v1/auth/accept-invitation` | pages/AuthPages.tsx | 200 / 200 / 200 / 200 / 200 / 422 / n/a | 200: e2e_admin | Verified |
| `changePassword` | `POST /api/v1/auth/password/change` | components/AppShell.tsx, pages/AuthPages.tsx | 401 / 200 / 200 / 200 / 200 / 422 / n/a | 200: e2e_password | Verified |
| `forgotPassword` | `POST /api/v1/auth/password/forgot` | lib/features.ts, pages/AuthPages.tsx | 202 / 202 / 202 / 202 / 202 / 422 / n/a | 202: e2e_password, e2e_security; 429: e2e_security | Verified |
| `login` | `POST /api/v1/auth/login` | api/client.ts, lib/session.tsx | 200 / 200 / 200 / 200 / 200 / 422 / n/a | 200: a11y_check, accounts_check, e2e_admin, e2e_ai[fixture], e2e_ai[none], e2e_ai[rate_limit], e2e_application, e2e_officer, e2e_password, e2e_quality, e2e_register, e2e_security, inventory_check, processing_check, signin_check, tracking_check, walkthrough; 401: e2e_admin, signin_check | Verified |
| `logout` | `POST /api/v1/auth/logout` | lib/session.tsx | 401 / 200 / 200 / 200 / 200 / n/a / n/a | 200: a11y_check, accounts_check, e2e_security, signin_check, tracking_check, walkthrough | Verified |
| `me` | `GET /api/v1/auth/me` | api/client.ts, lib/session.tsx | 401 / 200 / 200 / 200 / 200 / n/a / n/a | 200: a11y_check, accounts_check, e2e_admin, e2e_ai[fixture], e2e_ai[none], e2e_ai[rate_limit], e2e_officer, e2e_password, e2e_quality, e2e_register, e2e_security, inventory_check, signin_check, walkthrough; 401: a11y_check, accounts_check, e2e_admin, e2e_ai[fixture], e2e_ai[none], e2e_ai[rate_limit], e2e_application, e2e_officer, e2e_password, e2e_quality, e2e_register, e2e_security, inventory_check, journey_check, measure_page, processing_check, signin_check, tracking_check, walkthrough | Verified |
| `refresh` | `POST /api/v1/auth/refresh` | lib/session.tsx | 401 / 200 / 200 / 200 / 200 / n/a / n/a | 200: e2e_password | Verified |
| `register` | `POST /api/v1/auth/register` | lib/features.ts, pages/AuthPages.tsx | 202 / 202 / 202 / 202 / 202 / 422 / n/a | 202: e2e_admin, e2e_register | Verified |
| `resetPassword` | `POST /api/v1/auth/password/reset` | pages/AuthPages.tsx | 200 / 200 / 200 / 200 / 200 / 422 / n/a | 200: e2e_password | Verified |
| `verifyEmail` | `POST /api/v1/auth/verify-email` | pages/AuthPages.tsx | 200 / 200 / 200 / 200 / 200 / 422 / n/a | 200: e2e_admin, e2e_register | Verified |
| `benchmark` | `GET /api/v1/benchmark` | main.tsx, pages/Oversight.tsx | 401 / 403 / 200 / 200 / 200 / n/a / n/a | 404: inventory_check, walkthrough | Partial (UI not exercised by a browser run) |
| `dashboard` | `GET /api/v1/dashboard` | main.tsx, pages/Queue.tsx | 401 / 200 / 200 / 200 / 200 / n/a / n/a | 200: a11y_check, accounts_check, e2e_admin, e2e_ai[fixture], e2e_ai[none], e2e_ai[rate_limit], e2e_officer, e2e_password, e2e_quality, e2e_register, e2e_security, inventory_check, signin_check, tracking_check, walkthrough | Verified |
| `getJob` | `GET /api/v1/jobs/{job_id}` | components/UploadSlot.tsx, components/processing/useJobProgress.ts | 401 / 200 / 200 / 200 / 200 / n/a / 404 | 200: e2e_ai[fixture], e2e_ai[none], e2e_ai[rate_limit], e2e_application, e2e_officer, processing_check, walkthrough | Verified |
| `jobNotes` | `GET /api/v1/jobs/{job_id}/notes` | not called by UI | 401 / 200 / 200 / 200 / 200 / n/a / 404 | not hit | Partial (no UI) |
| `uploadDocument` | `POST /api/v1/applications/{application_id}/documents` | api/client.ts | 401 / 202 / 403 / 403 / 403 / 422 / 404 | 202: e2e_ai[fixture], e2e_ai[none], e2e_ai[rate_limit], e2e_application, processing_check, walkthrough | Verified |
| `documentEvidence` | `GET /api/v1/documents/{document_id}/evidence` | components/processing/ProcessingJourney.tsx, pages/Workspace.tsx | 401 / 200 / 200 / 200 / 200 / n/a / 404 | 200: a11y_check, e2e_ai[fixture], e2e_ai[none], e2e_ai[rate_limit], e2e_application, processing_check, walkthrough | Verified |
| `listVerifications` | `GET /api/v1/applications/{application_id}/verifications` | components/processing/ProcessingJourney.tsx, main.tsx, pages/Workspace.tsx | 401 / 200 / 200 / 200 / 200 / n/a / 404 | 200: a11y_check, e2e_ai[fixture], e2e_ai[none], e2e_ai[rate_limit], e2e_application, e2e_officer, inventory_check, processing_check, signin_check, tracking_check, walkthrough | Verified |
| `pageImage` | `GET /api/v1/documents/{document_id}/pages/{page}` | api/client.ts | 401 / 200 / 200 / 200 / 200 / n/a / 404 | 200: a11y_check, e2e_ai[fixture], e2e_ai[none], e2e_ai[rate_limit], e2e_application, e2e_officer, inventory_check, processing_check, signin_check, tracking_check, walkthrough | Verified |
| `reviewAiSuggestion` | `POST /api/v1/documents/{document_id}/ai-suggestions/review` | pages/Workspace.tsx | 401 / 403 / 200 / 200 / 403 / 422 / n/a | 200: e2e_ai[fixture] | Verified |
| `applicationRouting` | `GET /api/v1/applications/{application_id}/routing` | components/processing/OutcomeCard.tsx, lib/features.ts | 401 / 200 / 200 / 200 / 200 / n/a / 404 | 200: e2e_ai[fixture], e2e_ai[none], e2e_ai[rate_limit], e2e_application, e2e_officer, processing_check, walkthrough | Verified |
| `listFindings` | `GET /api/v1/applications/{application_id}/findings` | main.tsx, pages/InstitutionHome.tsx, pages/Workspace.tsx | 401 / 200 / 200 / 200 / 200 / n/a / 404 | 200: a11y_check, e2e_ai[fixture], e2e_ai[none], e2e_ai[rate_limit], e2e_application, e2e_officer, inventory_check, processing_check, signin_check, tracking_check, walkthrough | Verified |
| `repairPlan` | `GET /api/v1/applications/{application_id}/repair-plan` | pages/InstitutionHome.tsx, pages/Workspace.tsx | 401 / 200 / 200 / 200 / 200 / n/a / 404 | 200: e2e_application, inventory_check, walkthrough | Verified |
| `reviewFinding` | `POST /api/v1/findings/{finding_id}/review` | pages/Workspace.tsx | 401 / 403 / 200 / 200 / 403 / 422 / n/a | 200: e2e_officer, walkthrough | Verified |
| `listNotifications` | `GET /api/v1/notifications` | lib/features.ts, pages/AdminPages.tsx | 401 / 200 / 200 / 200 / 200 / 422 / n/a | 200: e2e_officer, e2e_quality | Verified |
| `readAllNotifications` | `POST /api/v1/notifications/read-all` | pages/AdminPages.tsx | 401 / 200 / 200 / 200 / 200 / n/a / n/a | 200: e2e_officer | Verified |
| `readNotification` | `POST /api/v1/notifications/{notification_id}/read` | pages/AdminPages.tsx | 401 / 200 / 200 / 200 / 200 / n/a / 404 | 200: e2e_officer | Verified |
| `unreadCount` | `GET /api/v1/notifications/unread-count` | components/AppShell.tsx | 401 / 200 / 200 / 200 / 200 / n/a / n/a | 200: a11y_check, accounts_check, e2e_admin, e2e_ai[fixture], e2e_ai[none], e2e_ai[rate_limit], e2e_application, e2e_officer, e2e_password, e2e_quality, e2e_register, e2e_security, inventory_check, processing_check, signin_check, tracking_check, walkthrough | Verified |
| `applicationReport` | `GET /api/v1/applications/{application_id}/report` | lib/features.ts, pages/Workspace.tsx | 401 / 200 / 200 / 200 / 200 / n/a / 404 | 200: e2e_application | Verified |
| `activateRules` | `POST /api/v1/rules/versions/{version_id}/activate` | pages/Oversight.tsx | 401 / 403 / 403 / 200 / 403 / n/a / n/a | 200: e2e_admin | Verified |
| `getRules` | `GET /api/v1/rules` | main.tsx, pages/Oversight.tsx | 401 / 200 / 200 / 200 / 200 / n/a / n/a | 200: accounts_check, e2e_admin, inventory_check, walkthrough | Verified |
| `proposeRules` | `POST /api/v1/rules/proposals` | pages/Oversight.tsx | 401 / 403 / 403 / 201 / 403 / 422 / n/a | 201: e2e_admin | Verified |
| `health` | `GET /api/v1/health` | pages/AdminPages.tsx | 200 / 200 / 200 / 200 / 200 / n/a / n/a | 200: a11y_check, accounts_check, e2e_admin, e2e_ai[fixture], e2e_ai[none], e2e_ai[rate_limit], e2e_application, e2e_officer, e2e_password, e2e_quality, e2e_register, e2e_security, inventory_check, journey_check, measure_page, processing_check, signin_check, tracking_check, walkthrough | Verified |
| `meta` | `GET /api/v1/meta` | lib/features.ts, pages/InstitutionHome.tsx, pages/Landing.tsx | 200 / 200 / 200 / 200 / 200 / n/a / n/a | 200: a11y_check, accounts_check, e2e_admin, e2e_ai[fixture], e2e_ai[none], e2e_ai[rate_limit], e2e_application, e2e_officer, e2e_password, e2e_quality, e2e_register, e2e_security, inventory_check, journey_check, measure_page, processing_check, signin_check, tracking_check, walkthrough | Verified |
| `metrics` | `GET /api/v1/metrics` | not called by UI | 401/200(token) / 401/200(token) / 401/200(token) / 401/200(token) / 401/200(token) / n/a / n/a | not hit | Verified (API only) |
| `ready` | `GET /api/v1/ready` | components/processing/OutcomeCard.tsx, pages/AdminPages.tsx | 200 / 200 / 200 / 200 / 200 / n/a / n/a | 200: e2e_admin, e2e_ai[fixture], e2e_ai[none], e2e_ai[rate_limit] | Verified |
| `applicationTimeline` | `GET /api/v1/applications/{application_id}/timeline` | lib/features.ts, pages/Workspace.tsx | 401 / 200 / 200 / 200 / 200 / n/a / 404 | 200: e2e_application, inventory_check, tracking_check, walkthrough | Verified |
| `documentHistory` | `GET /api/v1/applications/{application_id}/documents/history` | not called by UI | 401 / 200 / 200 / 200 / 200 / n/a / 404 | not hit | Partial (no UI) |
| `respondToFinding` | `POST /api/v1/findings/{finding_id}/responses` | lib/features.ts, pages/Workspace.tsx | 401 / 200 / 403 / 403 / 403 / 422 / 404 | 200: e2e_officer | Verified |

State counts: Partial (UI not exercised by a browser run): 2, Partial (no UI): 3, Verified: 55, Verified (API only): 1

Frontend names not in the contract (guarded by hasEndpoint, so they render nothing): `account`
