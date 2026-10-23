# Core backend implementation — 23 October 2026

Implemented in the existing Starlette/SQLite repository on local branch `astra/core-backend`, worktree `../pramaan-astra`. The user subsequently requested that all changes stay local, so no push, pull request, remote merge or deployment is part of this delivery. No project copy or ZIP was produced. The original checkout was left alone.

## Delivered behavior

All requested account, session, notification, tracking, clarification, report and administration operations are implemented. The generated contract has **56 operations and 63 schemas**, including the separately authenticated metrics endpoint. Jobs have stable stage codes, bounded transient retries, plain failure messages, upload idempotency and supervised hard timeouts. Optional SMTP/Resend email, S3 backups, daily local backup scheduling and scrubbed Sentry integration are configured through environment variables. AI hook registration is available and inert by default.

## New files

Paths below are relative to the repository root; grouped paths are individual files.

| Files | Purpose |
|---|---|
| `backend/app/features.py` | Feature flags and admin system extras registration |
| `backend/app/sessions.py`, `backend/app/tokens.py` | Revocable sessions, masked IP metadata, purpose-scoped single-use tokens and password policy |
| `backend/app/data/common_passwords.txt` | 499 distinct local weak-password patterns; no runtime download |
| `backend/app/email.py`, `backend/app/notify.py` | Queued console/SMTP/Resend email and access-checked notification recipients |
| `backend/app/routes/accounts.py`, `backend/app/routes/admin.py` | Registration, verification, recovery, invitations, account/session management and staff administration |
| `backend/app/routes/notifications.py`, `backend/app/routes/tracking.py` | Inbox/read operations, timeline, document history and clarification replies |
| `backend/app/routes/reports.py`, `backend/app/reports/__init__.py`, `backend/app/reports/verification_report.py` | Authorized, audited PDF streaming and Helvetica/palette report generation |
| `backend/app/pipeline/hooks.py`, `backend/app/pipeline/job_runner.py` | Ordered extension points and isolated job execution with parent-death monitoring |
| `backend/app/observability.py` | Redacted structured request logs, protected Prometheus metrics and optional scrubbed Sentry |
| `backend/app/instance_lock.py`, `backend/app/backup_schedule.py`, `backend/scripts/backup.py` | Single-instance/restore locks, UTC schedule, verified local/S3 backup sets and retention |
| `backend/tests/__init__.py`, `backend/tests/core_support.py`, `backend/tests/local_support.py` | Test discovery and isolated real-server/database fixtures |
| `backend/tests/test_contract.py`, `backend/tests/test_accounts.py`, `backend/tests/test_config.py`, `backend/tests/test_email.py` | Contract compatibility, accounts/security policy and mocked provider coverage |
| `backend/tests/test_jobs.py`, `backend/tests/test_notifications.py`, `backend/tests/test_operations.py`, `backend/tests/test_reports.py`, `backend/tests/test_tracking.py` | Worker/retry/timeout/idempotency, access isolation, backup/restore, metrics, PDF and tracking coverage |
| `docs/CORE_BACKEND_REPORT.md` | This implementation inventory and handoff |

`backend/app/routes/core_contract.py` existed only in the first local contract checkpoint. Its temporary handlers have been removed and replaced by the real route modules.

## Reasons for changes to existing files

| Existing file | Necessary change |
|---|---|
| `.env.example` | Document new optional services, account URLs, timeouts and production requirements without credentials |
| `backend/app/api.py` | Delegate authentication to current DB sessions, preserve CSRF/role checks, support raw PDF/text response types and sanitized observability |
| `backend/app/config.py` | Parse new settings, preserve empty-value defaults and reject unsafe production/email/backup combinations |
| `backend/app/db.py` | Run email callbacks only after a successful transaction commit |
| `backend/app/main.py` | Register routes, initialize observability and timing warmup, hold the instance lock, start/stop workers and backup schedule, expose required CORS headers |
| `backend/app/schemas.py` | Add the shared account/tracking/admin models and optional/defaulted document, finding and job fields required by frontend/AI consumers |
| `backend/app/security.py` | Carry JWT `jti` and optional principal session identity while keeping the existing scrypt/JWT implementation |
| `backend/app/routes/auth.py` | Create/revoke stored sessions, update last login and prevent a password-reset/login race |
| `backend/app/routes/applications.py` | Add optional search/filter/pagination and total-count header, preserve the unfiltered list body and emit officer notifications at submission |
| `backend/app/routes/common.py` | Serialize additive fields, stable document versions and clarification responses while preserving evidence redaction |
| `backend/app/routes/documents.py` | Apply user/application-scoped 24-hour upload idempotency atomically with the first response |
| `backend/app/routes/oversight.py` | Emit the clarification notification from the existing audited officer action |
| `backend/app/routes/system.py` | Include registered feature availability in `/meta` |
| `backend/app/pipeline/orchestrator.py` | Add stable stages, retry/deadline supervision, hooks, duration metrics and lifecycle notifications; retain deterministic extraction/rule evaluation |
| `backend/synthetic/seed.py` | Use explicit institution insert columns after additive migrations and refuse production seeding |
| `backend/eval/benchmark.py` | Use explicit institution columns so benchmark fixtures survive the additive schema changes |
| `backend/requirements.txt` | Declare optional-use `boto3` and `sentry-sdk`; no framework migration |
| `backend/scripts/gen_contract.py` | Generate correct PDF/text media types, upload idempotency header, pagination response header and separate metrics authentication |
| `backend/tests/test_api.py` | Close an existing SQLite test connection so Windows temporary-directory cleanup succeeds; no assertion was removed or relaxed |
| `contracts/openapi.json`, `contracts/api.gen.ts` | Regenerate the API contract/types from the actual route registry and models |
| `docs/API_CONTRACT.md` | Explain the new operations, additive fields, stage mapping and extension hooks |
| `docs/SECURITY.md` | Document token/session controls, isolation, redaction, watchdog/restore guarantees and residual limits |
| `docs/DEPLOYMENT.md` | Document settings, production guards, single-instance operation, backup/restore and service limitations |
| `docs/TEST_PLAN.md` | Append dated results from the actual local verification runs |

No frontend source, original audit-chain algorithm, storage implementation, verification adapter or rule-pack logic was changed by this work. The branch includes the pre-existing README-only commit `ef1336c`; that is not a backend implementation edit. The shared `origin/main` reference moved independently during this task; this worktree remains based on that original local baseline and was not merged with unrelated concurrent frontend work.

## Migrations

All migrations are forward-only and run through the existing migrator. Take a backup before upgrade.

| Migration | Change |
|---|---|
| `0002_accounts.sql` | Verified/contact/login fields, active institution defaults, sessions, token hashes, registrations and case-insensitive uniqueness |
| `0003_jobs.sql` | Stage codes, plain error message, attempt count and scoped idempotency keys |
| `0004_notifications.sql` | Notification inbox and indexed unread lookups |
| `0005_responses.sql` | Finding responses and lookup/search indexes |
| `0006_operations.sql` | Persisted job-stage durations |
| `0007_email_metrics.sql` | Sanitized provider failure counts across subprocesses |

Existing users remain verified and institutions active. Existing cookies require a new login because a valid database session is now mandatory.

## New environment variables

- Account links: `PUBLIC_BASE_URL` (local default `http://localhost:8000`; public HTTPS in production).
- Email: `EMAIL_PROVIDER` (`console` by default; production requires `smtp` or `resend`), `EMAIL_FROM`, `SMTP_HOST`, `SMTP_PORT` (587), `SMTP_USER`, `SMTP_PASSWORD`, `RESEND_API_KEY`, `NOTIFY_EMAIL` (false).
- Jobs: `JOB_TIMEOUT_SECONDS` (300). Use existing `WORKER_THREADS>=1` for the supervised hard deadline; synchronous test/benchmark mode has cooperative checks.
- Backups: `BACKUP_SCHEDULE` (false), `BACKUP_HOUR_UTC` (2), `BACKUP_S3_ENDPOINT`, `BACKUP_S3_BUCKET`, `BACKUP_S3_KEY_ID`, `BACKUP_S3_SECRET` (all four together; endpoint HTTPS).
- Operations: `LOG_FORMAT` (`text` or `json`), `METRICS_TOKEN` (empty disables metrics), `SENTRY_DSN` (empty disables reporting), `TRUST_PROXY` (false locally, defaults true on Railway/Fly), `DEMO_ACCOUNTS` (false; forbidden in production).

## Verification

Final command output and browser results are recorded in [TEST_PLAN.md](TEST_PLAN.md). The actual baseline contained **34 tests**, despite the prompt referring to 36. The final suite includes those original tests without weakening their assertions.

The PDF sample was generated from an isolated synthetic application, extracted for required wording and simulated-source labels, rendered with PDFium and visually checked across all five pages. Findings stay together across page breaks. Report display uses “recorded intake” in place of the legacy “approved intake” label; stored source evidence and rule outcomes are unchanged.

The final worker regression exposed a Windows native-library startup deadlock caused by a blocking parent-watch pipe read. The watchdog now polls pipe liveness without a blocking read on Windows. Dedicated checks cover consecutive supervised jobs and exit when the parent pipe closes, in addition to hard timeout termination.

## Handoff to Opus and Argon

- Register ordered steps with `register_step('after_fields', fn)` or `register_step('after_rules', fn)` from `app.pipeline.hooks`. Each receives `(conn, job_id, document_or_application, stage)`; call `stage(code, text, progress)` with a shared `StageCode`. No registered steps means unchanged rule outcomes.
- `after_fields` runs after extracted claims are persisted, before integrity checks. `after_rules` runs after validation and before DONE. Worker subprocesses import `app.main`, so register extensions through the permitted import there as well as their module initialization. Process-local runtime registrations do not propagate from the API process.
- Use `app.features.register` for `ai`/`routing` availability and `register_system_extra` for system diagnostics. The core does not set these features true or fabricate model results.
- Shared AI-facing fields remain defaulted/optional. Core reports and timeline continue to enforce the existing role/object boundaries. Opus owns routing-specific timeline events and AI verification behavior.
- Argon should consume generated `contracts/api.gen.ts`, use `stage_code` for UI logic and preserve human `stage` text. Optional application filters keep the original no-query response body; total results are in `X-Total-Count`. Upload keys are visible ASCII, 1–200 characters, scoped to user/application for 24 hours. A replay returns the initial queued response; poll the returned job ID for live progress.
- Registration decisions are **accept/decline**. Verification allows an administrator to see the pending registration; acceptance is still required before institution login. Refresh rotates and invalidates the previous session. Console email links use the configured frontend origin; the frontend agent owns their screens.
- Metrics use a separate `METRICS_TOKEN` Bearer secret, never an ordinary user JWT. Raw PDF/text types and the metrics scheme are explicitly represented in OpenAPI.

## Deferred and operational limits

- Remote pushes, PRs and merges were omitted following the user's explicit local-only instruction.
- AI extraction, AI verification, routing and new frontend account/tracking/admin screens belong to the other workstreams; the contracts and hooks are delivered here.
- Live SMTP/Resend delivery, S3 upload and Sentry transport need deployment credentials and were not exercised live. Provider behavior is mocked in tests; local console delivery and local backup/restore are exercised end to end.
- Docker images, a production deployment, multi-instance load, real documents and a real screen-reader audit were not validated in this environment.
- Email dispatch and rate limits are in-memory. Mail can be lost on process death; the daily scheduler does not catch up days while stopped. Validity-ending notifications are evaluated when a document is processed, not by a separate daily expiry scanner.
- Backups retain the latest 14 completed sets. Restore refuses active server/job locks and verifies manifest hashes and database integrity. Manifests are not signed; encryption and bucket retention/permissions remain deployment responsibilities. Extra unreferenced immutable files may remain after restore.
- The requested `docs/sih-plan/02_ANALYSIS_AND_RESEARCH.md` was absent in the starting worktree. Existing architecture, API, security, rule-pack, source and test files supplied the implementation context.
