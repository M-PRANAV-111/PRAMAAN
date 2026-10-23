# Test plan and results

Every result below was produced by running the commands shown on 22 Oct 2026 in the build workspace (Python 3.13, Node 22, Tesseract 5.5, Chromium headless). Nothing here is estimated.

## Automated suites

| Suite | Command | What it covers | Result |
|---|---|---|---|
| Backend unit | `backend$ python -m unittest tests.test_units` | Safe-expression whitelist (9 attack forms); every rule type incl. PASS/FAIL/NOT_EVALUABLE/NOT_APPLICABLE; reprint-aware dates; low-confidence abstention; consistency conflict proof; verification-state mapping; unsafe rule pack rejected; audit tamper and deletion detection; repair-plan grouping and shared-field linking; content-based upload checks; overlay-edit detection vs clean copy; incremental-save indicator; OCR path with provenance; no adverse-decision vocabulary in any enum | **20 / 20 passed** |
| Backend end-to-end | `backend$ python -m unittest tests.test_api` | Real uvicorn server on a freshly seeded database per class: generic login errors; cookie flags; 401/CSRF; cross-tenant 404 for application, findings and page images; role checks; security headers; clean and hard-negative bundles have no findings; every planted defect found with page/box evidence and "indicator" wording; ladder statuses and `simulated` flags; duplicate redaction for institutions; full institution→officer loop (upload 6 files, repair plan, renewed NOC resolves only its finding via targeted re-run, submit, officer decision needs ≥10-char reason, audit entry); upload rejections (executable, wrong type, unknown doc type, traversal name, 11 MB); four-eyes rule activation and version bump; audit verifier catches a database edit | **14 / 14 passed** |
| Contract drift | `backend$ python -m scripts.gen_contract --check` | Generated OpenAPI + TypeScript match the code | **Passed** (27 operations, 37 schemas) |
| Web type-check | `front$ npm run typecheck` and `front$ npm run typecheck:offline` | Strict TypeScript over all client code and the generated contract (both real `@types/react` and bundled offline shim) | **Passed** (0 errors) |
| Web build | `front$ npm run build` | esbuild code-splitting bundle + `<link rel="modulepreload">` for the start-page chunk + minified Tailwind v4 compile | **Passed** (330.4 KB signed-in JS, 43.1 KB start-page chunk, 46.1 KB minified CSS — all within budgets; first-frame document-visible time under 40 ms RTT improved from **1062.2 ms → 840.1 ms**) |
| Page length & document size | `front$ python e2e/measure_page.py <url>` | Measures whole-page screens (`scrollHeight / innerHeight`), story screens and `[data-part=doc]` width across 1440×900, 1280×720, 1024×768, 390×844 and 360×740 | **Passed** (10.3 / 10.8 / 10.8 / 13.9 / 15.8 whole-page screens; 8.4 / 8.4 / 8.4 / 10.4 / 11.6 story screens; 461 / 374 / 328 / 195 / 180 px document width) |
| Start-page journey & flow checks | `front$ python e2e/journey_check.py <url> <dir>` | Desktop (1440×900), laptop (1280×720), phone (390×844) and `prefers-reduced-motion: reduce`: document & Sign in visible on first screen; scrolling back restores every sampled state exactly (after `data-settled`); scenes advance in order 0 → 8; no horizontal scroll; stage releases after last scene; stage takes no pointer events; resize keeps story near same scene without overflow; medium scroll length (≤ 11 screens desktop/laptop, ≤ 14 phone) and strong document stage presence; header Sign in opens modal `<dialog>`, focuses `#signin-email`, Escape closes and restores focus; reduced motion renders 9 static documents and 0 animated stage; mouse-wheel flow (100 px notch every 70 ms): moving frames improved from **27 / 469 (5.8%)** before to **475 / 491 (96.7%)** after, stop-start stutters reduced from **27** to **4** (≤ 8), median move **56.8 px → 1.0 px**, p95 move **261.3 px → 21.4 px** (< 45 px); scroll p95 frame time **16.7 ms** (< 20 ms target) and longest main-thread task **0 ms** over 50 ms | **48 / 48 passed**; 0 page errors |
| Sign-in checks | `front$ python e2e/signin_check.py <url> <password> <dir>` | First Tab stop is Skip to content, second is Skip to sign in; skip link and header Sign in open modal `<dialog>` without changing URL and focus `#signin-email`; 9 demo-account chips; empty submit sets `aria-invalid` and `aria-describedby="signin-email-error"`; chip fills email, sets `aria-pressed="true"` and focuses password; Show/Hide password toggle; Caps Lock keyup hint (`#signin-caps`); wrong password alert (`role="alert"`) clears and focuses password; Enter signs in to `/queue`; signed-in start page shows "Open your workspace"; `/login?expired=1` shows session notice and `h1#signin-title`; institution chip signs in to `/institution`; mobile 390×844 has no horizontal overflow; `forced-colors: active` keeps visible `1px` borders on dialog and document | **28 / 28 passed**; 0 unexpected console/page errors |
| Browser walkthrough | `front$ python e2e/walkthrough.py <url> <password> <dir>` | Landing; officer sign-in; queue; open case; select integrity and consistency findings; record a decision; evidence dialog; repair plan; audit chain verification; rules; benchmark; institution sign-in; create application; upload six files with live progress; plan; replace NOC; activity; submit; mobile landing | **Passed**; only console errors are the expected 401s from the session probe on signed-out pages |
| Benchmark | `backend$ python -m eval.benchmark` | 34 synthetic bundles through the real pipeline | 26/26 planted faults detected; 2/8 valid look-alikes flagged (legitimate re-saves → indicator); median 2.7 s/bundle |

## Requirement → test traceability (selected)

| Requirement | Test |
|---|---|
| PS-1 no adverse decisions | `test_no_adverse_decision_vocabulary`; DB CHECK `advisory = 1` |
| PS-4 cross-document checks with evidence | `test_consistency_reports_conflicting_sources`, `test_planted_defects_are_found_with_evidence` |
| PS-5/PS-12 verification statuses | `test_verification_states`, `test_verification_ladder_statuses` |
| PS-8 RBAC and confidentiality | `test_institution_cannot_see_other_institution`, `test_role_checks`, duplicate redaction test |
| F-2 reprint-aware dates | `test_reprinted_letter_does_not_trigger_date_rule`, clean Shakti bundle |
| F-6 abstention | `test_low_confidence_input_abstains_instead_of_failing` |
| F-8 targeted re-validation | `test_full_institution_to_officer_loop` (affected rules list, resolved count) |
| F-10 audit chain | `test_tampering_is_detected`, `test_audit_chain_detects_database_tampering` |
| F-11 four eyes | `test_four_eyes_rule_activation` |
| NF-1 upload safety | `test_upload_rejections`, `IntakeTests` |

## Not yet tested
- Docker images and compose (written, not built here).
- Real `@types/react` type-check (CI).
- Accessibility audit with a screen reader (keyboard focus, labels and reduced motion were implemented and spot-checked visually only).
- Load and concurrency beyond a single worker thread.
- Real documents of any kind.


## Start page — independent verification (22 Oct 2026)

### 1. Verification checklist and evidence

| Section & Check | Status | Evidence (22 Oct 2026) |
|---|---|---|
| **1. Static — Repository state** | **PASS** | `git status -s` clean; `0` `*.zip` files; no duplicated project folder; `git diff <initial> HEAD -- front/package.json backend/requirements.txt` returned `0` lines (no added dependencies). |
| **1. Static — Backend unit & API suites** | **PASS** | `python -m unittest tests.test_units` (`20 / 20 passed`); `python -m unittest tests.test_api` (`14 / 14 passed`). |
| **1. Static — Contract drift** | **PASS** | `python -m scripts.gen_contract --check` → `27 operations, 37 schemas verified`. |
| **1. Static — Web type-check & build** | **PASS** | `npm run typecheck` (`0` errors) and `npm run typecheck:offline` (`0` errors); `npm run build` succeeded. |
| **1. Static — Bundle budgets & preloads** | **PASS** | Signed-in JS: `330.35 KB` (`241.14 KB` `app.34b33bc966.js` + `89.21 KB` `chunk-IFUFNL55.js`, budget `≤ 350 KB`); Start-page chunk: `43.15 KB` (`chunk-VWCVTXJT.js`, budget `≤ 45 KB`); CSS: `46.14 KB` (`app.047ae98cef.css`, budget `≤ 50 KB`). `index.html` preloads only `Inter-Regular.woff` and `InterDisplay-Medium.woff`. |
| **3. Browser — `journey_check.py`** | **PASS** | `48 of 48 checks passed`, `page errors: none` across desktop (`1440×900`), laptop (`1280×720`), phone (`390×844`), and `prefers-reduced-motion: reduce`. |
| **3. Browser — `signin_check.py`** | **PASS** | `28 of 28 checks passed`, `console/page errors: none (apart from expected 401s)`. |
| **3. Browser — `walkthrough.py`** | **PASS** | Officer and institution end-to-end flows completed with live uploads, targeted re-validation, audit chain check, and mobile landing. |
| **4. Storyboard — Chapter 0 (Opening)** | **PASS** | Wordmark, lead text, **Sign in** and **Follow a document** visible without scrolling; synthetic NOC on right (top half on phones); header **Sign in** button visible (`docs/screenshots/01-landing.jpg`, `docs/screenshots/14-landing-mobile.jpg`). |
| **4. Storyboard — Chapter 1 (The pile)** | **PASS** | Three `"Pending"` sibling sheets fan out behind the document and fold back before Chapter 2. |
| **4. Storyboard — Chapter 2 (Upload)** | **PASS** | Document sits inside the upload preview well; stage label steps through the 6 real pipeline stage names and ends `"Done — 1 page, 6 values read"`. |
| **4. Storyboard — Chapter 3 (Handover)** | **PASS** | Document leaves the institution tray, arcs across the stage, and drops cleanly into the ink `"PRAMAAN intake"` slot without peeking out or duplicating. |
| **4. Storyboard — Chapter 4 (Reading)** | **PASS** | Scan line sweeps once; non-overlapping labelled bounding boxes appear on `Certificate No.`, `Premises of`, `Permanent Id`, `Date of Issue`, `Valid Upto`, and `Signed QR`. |
| **4. Storyboard — Chapter 5 (Integrity)** | **PASS** | Violet `"EMBEDDED TEXT LAYER"` sheet separates and merges back; copy states indicators are a reason to look closer, never proof of alteration. |
| **4. Storyboard — Chapter 6 (Sources)** | **PASS** | Curves connect document edge to `Signed QR (tier 1)` (`Authentic, expired`), `Issuer registry (tier 3)` (`Simulated source`), `DigiLocker` (`Not connected · needs AICTE authorization`), and `Officer (manual)` with `≥ 35.8 px` right margin (`docs/screenshots/03-landing-pipeline.jpg`). |
| **4. Storyboard — Chapter 7 (Rules)** | **PASS** | Red flag `"Before 01-07-2026"` appears on `Valid Upto` as `FIRE.VALID` lights up; copy states clause references are `"not yet verified"` and `01-07-2026` is a stated assumption. |
| **4. Storyboard — Chapter 8 (The finding)** | **PASS** | Red-tape ribbon appears on the left of the document; proof card shows `Deficiency · advisory`, `FIRE.VALID`, and the 5 numbered steps (`1. Rule applied` – `5. Official decision`); copy states what clears it (`docs/screenshots/02-landing-finding-and-statuses.jpg`). |
| **4. Storyboard — Scene 9 (`#product`)** | **PASS** | Both previews carry `"Synthetic demo preview"` badges; decision controls are inside `aria-disabled="true"` with `0` interactive `<button>` elements; no invented counts. |
| **4. Storyboard — Scene 10 (`#trust`)** | **PASS** | Six verification statuses with meanings, four roles, four explicit limits, and labelled hash-chained audit illustration. |
| **4. Storyboard — Scene 11 (Closing CTA)** | **PASS** | Document shown with red-tape ribbon and expiry flag alongside working **Sign in** button. |
| **5. Honesty audit** | **PASS** | All 27 regex matches in start-page/sign-in files inspected: every match is an explicit negative limit (`"Never approves or rejects"`, `"Never calls a document forged"`), a labelled simulated/unconnected source, a problem-statement status enum, or CSS `%`. Every story fact matches `backend/synthetic/seed.py` (Institution B), `orchestrator.py`, `verification.py`, `rules_engine.py`, and `2026.1.yaml`. |
| **6. Accessibility — Keyboard, SR, Zoom, Forced colors, Reduced motion, Contrast** | **PASS** | Full keyboard sign-in and `PageDown` story progression verified; 1 `h1` + 12 `h2`s + `aria-hidden="true"` stage + `aria-labelledby="signin-title"` dialog; `200%` zoom (`640×400` effective) has `0` horizontal overflow and working dialog; `forced-colors: active` renders `1px solid` borders on `.journey-paper`, `.sheet`, `.btn`, and `dialog.signin-dialog`; `prefers-reduced-motion: reduce` renders `0` animated stage and `9` static stills; all 16 token contrast pairs exceed WCAG AA (`5.33:1` to `13.90:1`). |
| **7. Security & privacy** | **PASS** | `0` hits in `dist/` for seed passwords, `JWT_SECRET`, private keys, or `demo_credentials`; `0` inline `<script>` tags and `0` `dangerouslySetInnerHTML`; `APP_ENV=production` refuses weak `JWT_SECRET`, `COOKIE_SECURE=false`, and `CORS_ORIGINS=*`; `43 / 43` start-page network requests are same-origin (`0` third-party); signed-out `/queue`, `/institution`, and `/applications/app_test` redirect to `/login`. |

### 2. Bundle sizes vs. budgets

| Bundle | File(s) | Measured Size | Budget | Status |
|---|---|---|---|---|
| Signed-in JS (`app.*.js` + static imports) | `app.34b33bc966.js` (`241.14 KB`) + `chunk-IFUFNL55.js` (`89.21 KB`) | **330.35 KB** (`338,275 B`) | `≤ 350 KB` | **PASS** |
| Start-page lazy chunk (`DocumentJourney`) | `chunk-VWCVTXJT.js` | **43.15 KB** (`44,181 B`) | `≤ 45 KB` | **PASS** |
| Compiled CSS | `app.047ae98cef.css` | **46.14 KB** (`47,252 B`) | `≤ 50 KB` | **PASS** |

### 3. Defects found and fixed during verification

1. **Server filesystem path `backend/var/demo_credentials.txt` referenced in `SignInCard.tsx` (`front/src/components/SignInCard.tsx:205`)**
   - **Symptom:** Static security scan for `demo_credentials` in `front/dist/` matched `chunk-DY36I66D.js`.
   - **Cause:** The footnote at the bottom of `SignInCard.tsx` displayed `<code>backend/var/demo_credentials.txt</code>`.
   - **Fix:** Updated `front/src/components/SignInCard.tsx:205` to `"Demo password is printed by the seed script at startup."` Rebuilt `dist/` and verified `0` matches for `demo_credentials`.
2. **`.signin-dialog` border overridden in `forced-colors: active` (`front/src/styles.css:253–268`)**
   - **Symptom:** Under `forced-colors: active`, `getComputedStyle(document.querySelector('dialog.signin-dialog')).borderTopStyle` returned `'none 0px'`.
   - **Cause:** `.signin-dialog { border: 0; }` was placed outside `@layer components`, which in CSS Cascade Layers takes precedence over `@media (forced-colors: active)` inside `@layer components`.
   - **Fix:** Moved `.signin-dialog` rules into `@layer components` above the `@media (forced-colors: active)` block in `front/src/styles.css` and added an automated regression check (`forced-colors: dialog and document have visible borders`) to `front/e2e/signin_check.py`.

### 4. Open issues and recommendations

- **Open issues:** None (`0` blocker, `0` major, `0` minor).
- **Non-defect recommendations:**
  1. In `backend/tests/test_api.py:218`, `GovernanceTests.test_audit_chain_detects_database_tampering` opens a raw `sqlite3.connect(self.db)` without a `with` / `.close()` block, which can cause a harmless `PermissionError` during `TempDirectory.cleanup()` on Windows after all 14 tests pass. Closing that connection explicitly in `test_api.py` would avoid the Windows temp-file lock when backend edits are in scope.

## Core backend — local verification, 23 October 2026

Environment: Windows AMD64, Python 3.13.14, isolated temporary SQLite databases, console email, real Uvicorn servers and headless Chromium. Branch: `astra/core-backend`, worktree `../pramaan-astra`. Remote publication was omitted at the user's request. See [CORE_BACKEND_REPORT.md](CORE_BACKEND_REPORT.md) for the implementation inventory and service limitations.

| Check | Actual result |
|---|---|
| Complete backend suite: `python -m unittest discover -s tests -t .` | **PASS — 68 tests in 110.547s, OK** |
| Contract: `python -m scripts.gen_contract --check` | **PASS — 56 operations, 63 schemas verified** |
| `npm --prefix front run typecheck` | **PASS — TypeScript exited 0** |
| `npm --prefix front run build` | **PASS — signed-in JS 332.3 KB, start-page chunk 43.1 KB, CSS 46.1 KB** |
| `front/e2e/signin_check.py` | **PASS — 28 checks; no console/page errors apart from three expected 401 responses** |
| `front/e2e/journey_check.py` | **PASS — 48/48 checks, page errors: none** |
| Synthetic seed + `front/e2e/walkthrough.py` | **PASS — live officer/institution workflow, uploads, repair, submission, audit and mobile landing** |
| `front/e2e/measure_page.py` | **Completed — measured five viewports (1440×900 through 360×740); informational output, not an assertion suite** |
| PDF report | **PASS — `%PDF`, disclaimer, simulated-source labels, audit event, Helvetica and cross-institution access/redaction assertions; all five rendered sample pages visually inspected** |
| Local backup/restore | **PASS — database/file round trip, newest-14 retention, corruption/traversal rejection and active server/job restore refusal** |
| Synthetic benchmark: `python -m eval.benchmark` | **Completed — 34 bundles, 26/26 planted faults detected; 2/8 hard negatives raised `INTEGRITY:INCREMENTAL_UPDATE`; median 3.42s, p95 3.89s, max 3.92s per bundle** |
| `git diff --check` | **PASS — no whitespace errors** |

The original source contained 20 unit tests and 14 API tests (**34**, not the prompt's stated 36). All remain in the passing suite with their assertions intact. The existing SQLite connection was explicitly closed to resolve the previously documented Windows teardown failure.

New tests exercise registration/verification/acceptance, duplicate responses and timing, password policy, reset token expiry/reuse and session revocation, invitations and administrator guards, rate limits, account updates, notification isolation, query compatibility, versions, timeline/replies, report authorization and redaction, retry backoff and nonretryable errors, hard process termination, consecutive supervised jobs, parent loss, upload replay, inert/ordered hooks, local backup/restore, metrics authentication/log redaction, mocked SMTP/Resend behavior and production configuration refusal. Expected failure-path tests log sanitized `http_503`, timeout and validation error codes.

A final regression run found three jobs stuck at startup after adding parent-death monitoring. The cause was a blocking stdin-pipe read during native-library initialization on Windows. It was replaced with nonblocking pipe-liveness polling; consecutive-job and parent-pipe closure regression checks were added. The complete 68-test run above passed after the fix.

Browser screenshots, text logs, synthetic data and the PDF sample stay under ignored `backend/var/qa` / `backend/var/qa-data-*`; no credentials or generated data are committed. One earlier QA wrapper encountered a Windows console encoding error while printing a successful journey result; the underlying Chromium process completed all 48 checks and its UTF-8 output was preserved. This does not represent an application failure.

Limits: this benchmark is synthetic and is not an accuracy claim for real submissions. The two hard-negative incremental-update findings remain advisory indicators; rule/integrity policy was outside this change. Live SMTP/Resend/S3/Sentry, Docker, a production deployment, multi-instance/load tests and real documents were not tested. The frontend checks cover the existing frontend in this worktree; new frontend screens and unrelated concurrent branch changes are separate workstreams.
