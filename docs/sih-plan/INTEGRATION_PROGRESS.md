Last action: 2026-10-27 — merged Part B (`8a8da49`) with AI_TEST_FAULT and the fixture provider ported; added production-refusal, restart and readiness tests (`e763027`); checkpoint green: backend 204 OK, smoke 393/0, browser 19/19.
Next action: claimed A1/A2 browser coverage — extend e2e_password (Account page: change password, sessions, revoke, refresh), e2e_admin (decline, System page), e2e_officer (mark all read, Run full check); then TEST_PLAN.md, DEMO_GUIDE.md, CameraScanner decision, final report.
Known problems: `07_INTEGRATION.md` not found (Questions 1); Docker not installed (A7); CI results cannot be read here (`gh` missing, repository private) so A8's CI step is unobserved; `updateAccount` and `documentHistory` have no UI (decision needed).

# Integration resume status

Every state below comes from a command run on 2026-10-27 unless the row says otherwise. Results are in
[INTEGRATION_MATRIX.md](INTEGRATION_MATRIX.md). This session is **Opus** (Claude Opus 5.5). No other agent activity was
found: `origin` had no `integration/e2e` before this session pushed it, the `../pramaan-astra` worktree is clean at
`9963ed2`, there are no stashes.

States: **Verified** (re-run today and passed) · **Done, unverified** · **Partial** · **Not started** · **Blocked**.
Lanes: Astra owns Part A, Opus owns Part B; Part C is split as in the resume prompt.

Claims (to avoid double work):
- claim: A1 browser coverage (Account page, decline registration) by Opus
- claim: A2 browser coverage (mark all read) by Opus
- claim: A6 production-refusal tests by Opus — done in `e763027`
- claim: `validateApplication` browser coverage by Opus
- claim: failure and retry table by Opus — done

## What the restart found

- `integration/e2e` = `main` (7587110) merged with `astra/core-backend` (9963ed2) in `7512b14`, plus the stopped
  run's **uncommitted** work (53 files: AI skeleton, smoke and e2e runner, Part C scripts, Dockerfile, frontend wiring).
  It had no secrets (only empty placeholders, test sentinels and generated tokens) and was committed unchanged as
  `5db316e wip: …`.
- `opus/ai-verification` (worktree `../pramaan-opus`, 3 commits on `astra/core-backend`) held the Part B implementation
  built to Backend Prompt 2 (194 tests `OK (skipped=3)` today before the merge).
- The uncommitted AI skeleton collided with it and departed from the Part B contract (routing restated the derived
  status; grounding could only re-tag values the template extractor already found; explanations were accepted only
  when identical to the template; an Anthropic adapter no spec asked for). The Opus implementation won in `8a8da49`;
  the skeleton's useful parts were kept or ported (recorded stage history, job notes in the UI, `AI_TEST_FAULT`,
  a recorded fixture provider — the last two refused unless `APP_ENV=test`).

## Questions (safest choice taken, flagged for the report)

1. `07_INTEGRATION.md` was not found in any worktree, in git history or in the two session transcripts. Items below are
   the resume prompt's list; acceptance details were taken from Backend Prompt 2 (Part B), `docs/agent-prompts/INTEGRATION.md`
   and the code. Please add the file to `docs/sih-plan/` if it exists.
2. `updateAccount` and `documentHistory` exist in the API with no UI. Left API-only (smoke-verified) rather than adding
   features; say if either should get a screen.
3. CameraScanner: without a camera it draws a synthetic page and lets the user submit it as a document. Open — see the
   development-only row.

## Items

| Item | Owner | State | Evidence | Next step |
|---|---|---|---|---|
| A1 accounts | Astra (claimed by Opus for browser coverage) | Partial | `tests.test_accounts` (8) inside `Ran 204 tests … OK (skipped=3)`; smoke rows for all account operations as expected; browser e2e_register `3/3`, e2e_password `2/2`. Not reached by a browser run: Account page (change password, sessions, revoke, refresh), Decline in admin | Extend e2e_password and e2e_admin (claimed) |
| A2 notifications | Astra (claimed by Opus for browser coverage) | Partial | `tests.test_notifications` passes; e2e_officer opens the clarification notice. `readAllNotifications` not reached | Add "Mark all as read" to e2e_officer (claimed) |
| A3 timeline and reports | Astra | Verified | `tests.test_tracking`, `tests.test_reports` pass; e2e_application `24/24` incl. `PASS real PDF downloaded`, `PASS download audited in timeline`, `PASS complete real-event timeline` | — |
| A4 clarification loop | Astra | Verified | `tests.test_notifications`, `tests.test_tracking` pass; e2e_officer `3/3` (`PASS Officer sees the real institutional reply`, `PASS Audit chain verifies after the complete clarification loop`) | — |
| A5 search and lists | Astra | Verified | `tests.test_tracking` (search, pagination) passes; e2e_officer `PASS Queue search uses backend query and total header`; tracking_check `16 of 16` after the Queue count fix (`ea36c6c`) | — |
| A6 production configuration (one test per refusal) | Astra (tests added by Opus) | Verified | `python -m unittest tests.test_production_refusals` → `Ran 18 tests … OK` (one test per refusal, incl. `SEED_DEMO_PASSWORD`, synthetic accounts at startup, AI fixture/fault/allow_real, and a real process refusing to start); `tests.test_config` unchanged and passing | — |
| A7 root Dockerfile | Astra | Blocked | `Dockerfile` and `.dockerignore` exist; **not built**: `docker: command not found` | Needs Docker. Its steps (frontend `typecheck` + `build`, backend start with production refusals) are each tested without it |
| A8 smoke.py and its CI step | Astra | Blocked | `python -m scripts.smoke` → `61 operations; 393 assertions passed; 0 failed operations.` (bodies for the two new Part B POSTs added in `8a8da49`). `ci.yml` runs it. The CI run cannot be read: `gh: command not found`, GitHub API `Not Found` (private repository) | Needs `gh auth login` or repository access to read the Actions run for `integration/e2e` |
| B1 stage codes and journey | Opus | Verified | e2e_ai all three variants `PASS affidavit: UI stage history equals the recorded backend stages`, `PASS routing ran as a recorded stage`; fixture `PASS AI extraction ran as a recorded stage`; e2e_application `PASS UI recorded stages equal real job sequence`; `tests.test_jobs` stage codes | — |
| B2 grounded values and suggestions | Opus | Verified | `test_ai_grounding` (13) and `test_ai_test_hooks` (10) in the 204 run; e2e_ai fixture `PASS printed value grounded as a claim with a real page box`, `PASS contradicting value is a suggestion, never a claim`, officer dismissal in the UI → `PASS dismissal clears the suggestion reason from routing`, `PASS dismissal is in the audit trail` | — |
| B3 routing (three outcomes) | Opus | Verified | `test_routing` (25) in the 204 run; e2e_ai (3 variants) `PASS routing outcome is one of the three`, `PASS every routing reason points into this application`, OutcomeCard `data-outcome` equals the API outcome; fixture `PASS an open AI suggestion keeps the case from READY` | — |
| B4 explanations | Opus | Verified | `test_explain` (11) in the 204 run (new numbers, dates, IDs, decision words rejected; template kept). Browser: the template shows in every run; validated AI wording cannot appear in a browser run because no wording is recorded (the fixture says `AI step skipped: no_fixture`) | — |
| B5 AI status | Opus | Verified | smoke `aiStatus 401/403/403/200/200`, `aiKillSwitch 401/403/403/200/403/422`; e2e_ai `PASS server AI status matches the declared variant`, `PASS only the recorded fixture is labelled simulated`, System page shows it; fixture `PASS kill switch turns AI off`, `PASS AI feature flag follows the kill switch`, `PASS kill switch release restores the mode` | — |
| B6 failure injection (`AI_TEST_FAULT`, test-only) | Opus | Verified | `tests.test_ai_test_hooks` (refused outside test incl. a real process; rate_limit, timeout, invalid_json each leave the deterministic result) and `test_production_refusals.AIRefusals`; e2e_ai `rate_limit` `19/19` (`PASS the 429 is recorded as a skip note`, `PASS deterministic result kept`) | — |
| B7 data policy | Opus | Verified | `test_ai_policy` (14) in the 204 run; e2e_ai `PASS an unstamped file causes no provider request` (all variants), `PASS the data policy is recorded as a skip note` (fixture, rate_limit) | — |
| C e2e_register | Astra | Verified | `PASS e2e_register.py`, `3/3 checks passed` | — |
| C e2e_application | Astra | Verified | `PASS e2e_application.py`, `24/24 checks passed` | — |
| C e2e_officer | Astra | Verified | `PASS e2e_officer.py`, `3/3 checks passed` (selector fixed in `ea36c6c`) | Extend for A2 (claimed) |
| C e2e_admin | Astra | Verified | `PASS e2e_admin.py`, `5/5 checks passed` | Extend for A1 decline (claimed) |
| C e2e_password | Astra | Verified | `PASS e2e_password.py`, `2/2 checks passed` | Extend for the Account page (claimed) |
| C e2e_ai | Opus | Verified | rewritten in `8a8da49`: fixture `25/25`, rate_limit `19/19`, none `16/16` | — |
| C e2e_security | Opus | Verified | `PASS e2e_security.py`, `9/9 checks passed` | — |
| C e2e_quality | Opus | Verified | `PASS e2e_quality.py`, `11/11 checks passed` (tab order fixed in `ea36c6c`) | — |
| Failure and retry table | shared (claimed by Opus) | Verified | 15 rows in the matrix, each tied to a test that passed today; two tests added (`test_job_restart`, `test_readiness`) | — |
| Development-only behaviour search | shared | Partial | Searched (mock, fake, dummy, placeholder, lorem, TODO, FIXME, setTimeout). Removed by the stopped run: browser-only registration adapter with a hard-coded password; demo chips now need `meta.features.demo_accounts` (refused in production, tested). Open: CameraScanner synthetic page | Decide the CameraScanner fallback; re-run the search at the end |
| docs/TEST_PLAN.md | shared | Not started | No integration section yet | Next |
| docs/DEMO_GUIDE.md | shared | Not started | Unchanged by the integration | Next |
| Final report | shared | Not started | — | Last |

## Matrix rows

One row per contract operation (61); evidence columns are in
[INTEGRATION_MATRIX.md](INTEGRATION_MATRIX.md#operation-matrix--latest-run).

| Item | Owner | State | Evidence | Next step |
|---|---|---|---|---|
| 48 operations (list in the matrix) | as tagged | Verified | smoke as expected for every caller + a 2xx in a browser run today | — |
| `metrics` | Astra | Verified | smoke `401/200(token)`; token-only by design | — |
| `getAccount`, `revokeSession`, `revokeOtherSessions`, `changePassword`, `refresh` | Astra | Partial | smoke as expected; Account page calls them; no browser run reaches it | A1 (claimed) |
| `declineRegistration` | Astra | Partial | smoke `200` for ADMIN; no browser run declines | A1 (claimed) |
| `readAllNotifications` | Astra | Partial | smoke 200; not reached | A2 (claimed) |
| `validateApplication` | Astra | Partial | smoke 202/202/202/403; "Run full check" not reached | claimed |
| `benchmark` | Astra | Partial | browser runs got the documented 404 on a fresh seed (page explains it, asserted by inventory_check); smoke generated a report and got 200 | Accept as designed |
| `jobNotes` | Opus | Partial | smoke 200/404; the UI reads the same notes from `JobOut.ai_notes`, so no screen calls this endpoint | Keep API-only |
| `updateAccount`, `documentHistory` | Astra | Partial | smoke 200; no UI | Question 2 |
| frontend name `account` | Astra | Partial | not in the contract; guarded by `hasEndpoint`, so inert | Remove the dead alias |
