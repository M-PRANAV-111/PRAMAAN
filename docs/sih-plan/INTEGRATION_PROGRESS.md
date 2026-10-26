Last action: 2026-10-27 — re-baselined (backend 78 OK, smoke 375/0, contract OK, browser 14/19), fixed the 5 red browser scripts (re-run 5/5), wrote this file.
Next action: Part B — merge `opus/ai-verification` into `integration/e2e`, replacing the uncommitted AI skeleton; port `AI_TEST_FAULT` and the test-only fixture provider onto it; rewire OutcomeCard, ProcessingJourney, AdminPages and e2e_ai to the Part B contract.
Known problems: `07_INTEGRATION.md` is not in the repository or any transcript (see Questions); Docker is not installed (A7 Blocked); two competing AI implementations exist until the merge lands; `gh` is not installed, so CI runs are read from the GitHub API only.

# Integration resume status

Every state below comes from a command run on 2026-10-27 unless the row says otherwise. Results are in
[INTEGRATION_MATRIX.md](INTEGRATION_MATRIX.md). This session is **Opus** (Claude Opus 5.5). No other agent activity was
found: `origin` has no `integration/e2e`, the `../pramaan-astra` worktree is clean at `9963ed2`, there are no stashes.

States: **Verified** (re-run today and passed) · **Done, unverified** · **Partial** · **Not started** · **Blocked**.
Lanes: Astra owns Part A, Opus owns Part B; Part C is split as in the resume prompt.

## What the restart found

- `integration/e2e` = `main` (7587110) merged with `astra/core-backend` (9963ed2) in `7512b14`, plus the stopped
  run's **uncommitted** work (53 files: AI skeleton, smoke and e2e runner, Part C scripts, Dockerfile, frontend wiring).
  It had no secrets (only empty placeholders, test sentinels and generated tokens) and was committed unchanged as
  `5db316e wip: …`.
- `opus/ai-verification` (worktree `../pramaan-opus`, 3 commits on `astra/core-backend`, not merged) holds the Part B
  implementation built to Backend Prompt 2: 194 tests, `OK (skipped=3)` today.
- The uncommitted AI skeleton collides with it (same `app/ai` package and `ai_suggestions` table) and departs from the
  Part B contract: its routing restates the application's derived status, grounding can only re-tag values the template
  extractor already found, explanations are accepted only when identical to the template, and it adds an Anthropic
  adapter that no spec asked for. Decision: the Opus implementation wins; the skeleton's useful parts (recorded stage
  history, job notes in the UI, `AI_TEST_FAULT`, test-only fixture provider) are ported onto it.

## Questions (safest choice taken, flagged for the report)

1. `07_INTEGRATION.md` was not found in any worktree, in git history or in the two session transcripts. Items below are
   the resume prompt's list; acceptance details were taken from Backend Prompt 2 (Part B), `docs/agent-prompts/INTEGRATION.md`
   and the code. Please add the file to `docs/sih-plan/` if it exists.
2. The "failure and retry table" has no document yet; its rows are inferred from the job, email and AI tests.

## Items

| Item | Owner | State | Evidence | Next step |
|---|---|---|---|---|
| A1 accounts | Astra | Partial | Works: `tests.test_accounts` (8) in the full run `Ran 78 tests … OK`; smoke rows register, verifyEmail, login, forgotPassword, resetPassword, acceptInvitation, changePassword, listSessions, revokeSession all as expected; browser e2e_register `3/3`, e2e_password `2/2`. Not shown: the Account page (change password, sessions, refresh, revoke) and Decline in admin are not reached by any browser run; `updateAccount` has no UI | Extend e2e_password with change-password and session revoke; e2e_admin with decline |
| A2 notifications | Astra | Partial | `tests.test_notifications` passes; smoke 200 for every role; e2e_officer opens the clarification notice (listNotifications, readNotification, unreadCount hit). `readAllNotifications` is not reached by any browser run | Add "Mark all read" to a browser script |
| A3 timeline and reports | Astra | Verified | `tests.test_tracking`, `tests.test_reports` pass; e2e_application `24/24` incl. `PASS real PDF downloaded`, `PASS download audited in timeline`, `PASS complete real-event timeline` | — (documentHistory UI is a matrix row) |
| A4 clarification loop | Astra | Verified | `tests.test_notifications` (clarification reply) and `tests.test_tracking` (responses) pass; e2e_officer re-run `3/3`: `PASS Officer sees the real institutional reply`, `PASS Audit chain verifies after the complete clarification loop` | — |
| A5 search and lists | Astra | Verified | `tests.test_tracking` (search, pagination) passes; e2e_officer `PASS Queue search uses backend query and total header`; tracking_check re-run `16 of 16` after the Queue count fix | — |
| A6 production configuration (one test per refusal) | Astra | Partial | `tests.test_config.test_production_guards` refuses console email, HTTP base URL, DEMO_ACCOUNTS, SHOW_DEMO_ACCOUNTS, COOKIE_SECURE=false, short JWT, wildcard CORS (sub-tests, passing). Missing: a set `SEED_DEMO_PASSWORD` is never asserted to be refused; empty `PUBLIC_BASE_URL`; AI refusals (`allow_real` without confirmation, fixture/fault outside test) live in the skeleton or the unmerged branch | Add the missing refusal tests after the AI merge |
| A7 root Dockerfile | Astra | Blocked | `Dockerfile` and `.dockerignore` exist; **not built**: `docker: command not found` | Needs Docker. Everything else in the image (frontend build, backend start with `APP_ENV=production` refusals) is tested without it |
| A8 smoke.py and its CI step | Astra | Partial | `python -m scripts.smoke` → `58 operations; 375 assertions passed; 0 failed operations.`; `ci.yml` runs it in the backend job. No CI run observed yet | Push and read the run from the GitHub API |
| B1 stage codes and journey | Opus | Partial | Works on the skeleton: e2e_application `PASS UI recorded stages equal real job sequence`; e2e_ai stage-history checks pass; `tests.test_jobs` stage codes pass. The Part B stage texts ("AI-assisted extraction", "Recommending next steps") are only on the unmerged branch | Merge, then re-run e2e_application and e2e_ai |
| B2 grounded values and suggestions | Opus | Partial | Skeleton: re-tags values the template extractor already found, so it cannot add a value. Opus branch: `test_ai_grounding` (13) in `194 … OK` today | Merge |
| B3 routing (three outcomes) | Opus | Partial | Skeleton returns the derived status (DEFICIENCIES_FLAGGED…), which Backend Prompt 2 §5 says routing must not replace. Opus branch: READY_FOR_SCRUTINY / CORRECTIONS_REQUIRED / OFFICER_REVIEW_REQUIRED, `test_routing` (25) passing today | Merge; rewire OutcomeCard |
| B4 explanations | Opus | Partial | Skeleton accepts only text identical to the template. Opus branch: validated wording, `test_explain` (11) passing today | Merge |
| B5 AI status | Opus | Partial | Skeleton status endpoint is in smoke (`aiStatus 401/403/403/200/403`); AdminPages renders it but no browser run opens it. Opus branch adds the kill switch and AUDITOR read access | Merge; add a browser check of the System page |
| B6 failure injection (`AI_TEST_FAULT`, test-only) | Opus | Partial | Skeleton only: refused outside `APP_ENV=test` (`tests.test_ai`), e2e_ai `rate_limit` variant `8/8`. The Opus client has no fault injection | Port onto the Opus provider chain with refusal tests |
| B7 data policy | Opus | Partial | Skeleton allows any file containing the word SYNTHETIC; e2e_ai `PASS Unstamped evidence skips external AI`. Opus branch requires the stamp line on every page sent, `test_ai_policy` (14) passing today | Merge |
| C e2e_register | Astra | Verified | `python -m scripts.e2e` → `PASS e2e_register.py`, `3/3 checks passed` | — |
| C e2e_application | Astra | Verified | `PASS e2e_application.py`, `24/24 checks passed` | — |
| C e2e_officer | Astra | Verified | Baseline FAIL (selector); re-run `PASS e2e_officer.py`, `3/3 checks passed` | — |
| C e2e_admin | Astra | Verified | `PASS e2e_admin.py`, `5/5 checks passed` | Extend for decline (A1) and System page (B5) |
| C e2e_password | Astra | Verified | `PASS e2e_password.py`, `2/2 checks passed` | Extend for Account page (A1) |
| C e2e_ai | Opus | Partial | Passes 9/9, 8/8, 7/7 against the skeleton only | Rewrite for the Part B contract after the merge |
| C e2e_security | Opus | Verified | `PASS e2e_security.py`, `9/9 checks passed` | — |
| C e2e_quality | Opus | Verified | Baseline FAIL (tab order); re-run `PASS e2e_quality.py`, `11/11 checks passed` | — |
| Failure and retry table | shared (Astra jobs/email, Opus AI) | Not started | No table exists. Behaviour is tested: `tests.test_jobs` (retry, no retry on validation, backoff, hard timeout), `tests.test_email` (provider retries), Opus `test_ai_provider`/`test_ai_robustness` (429 fallback chain) | Write the table with one test per row |
| Development-only behaviour search | shared | Partial | Searched today (mock, fake, dummy, placeholder, lorem, TODO, FIXME, setTimeout). Removed by the stopped run: browser-only registration adapter with a hard-coded password; demo-account chips now need `meta.features.demo_accounts` (refused in production). Open: CameraScanner draws a synthetic page and submits it when no camera is present | Decide on the CameraScanner fallback; re-run the search at the end |
| docs/TEST_PLAN.md | shared | Not started | No integration section yet | After Part B |
| docs/DEMO_GUIDE.md | shared | Not started | Unchanged by the integration | After Part B |
| Final report | shared | Not started | — | Last |

## Matrix rows

One row per contract operation; the evidence columns (smoke cells and browser hits) are in
[INTEGRATION_MATRIX.md](INTEGRATION_MATRIX.md#operation-matrix--generated-2026-10-27-from-the-baseline-runs).

| Item | Owner | State | Evidence | Next step |
|---|---|---|---|---|
| 42 operations (list in the matrix) | as tagged | Verified | smoke as expected for every caller + a 2xx in a browser run today | — |
| `metrics` | Astra | Verified | smoke `401/200(token)`; token-only, no UI by design | — |
| `getAccount`, `listSessions`, `revokeSession`, `revokeOtherSessions`, `changePassword`, `refresh` | Astra | Partial | smoke as expected; Account page calls them; no browser run reaches it | A1 next step |
| `declineRegistration` | Astra | Partial | smoke `200` for ADMIN; no browser run declines | A1 next step |
| `readAllNotifications` | Astra | Partial | smoke 200; not reached | A2 next step |
| `validateApplication` | Astra | Partial | smoke 202/202/202/403; UI button not reached | Add to e2e_officer or e2e_application |
| `systemStatus`, `aiStatus`, `ready` | Astra / Opus | Partial | smoke as expected; System page not reached | B5 next step |
| `benchmark` | Astra | Partial | browser runs got the documented 404 (no report on a fresh seed); smoke generated a real report and got 200 | Accept as designed, or seed a report in one browser run |
| `updateAccount` | Astra | Partial | smoke 200; no UI calls it | Decide: add to Account page or leave API-only |
| `documentHistory` | Astra | Partial | smoke 200 / foreign 404; no UI calls it | Decide: show in Documents tab or leave API-only |
| frontend name `account` | Astra | Partial | not in the contract; guarded by `hasEndpoint`, so inert | Remove the dead alias |
