# Security and threat model

PRAMAAN holds institutional records and documents that can affect a regulatory outcome. Security is part of the design, not a later layer. This document lists what is implemented, how it is tested, and what remains.

## Assets
Uploaded documents · extracted values · findings and officer decisions · rule packs · audit trail · session tokens · synthetic issuer private keys (demo only).

## Trust boundaries
Browser ↔ API (untrusted input) · API ↔ supervised worker subprocess · worker ↔ external sources (verification adapters; none live in this build) · configured email/backup/error services · administrators ↔ rule packs (privileged data that changes outcomes).

## Threats and controls

| Threat | Control implemented | Where | Tested by |
|---|---|---|---|
| Account takeover by password guessing | scrypt (N=2^15) hashes; identical error and timing for unknown e-mail vs wrong password; 10 attempts/min/IP | `security.py`, `routes/auth.py` | `test_login_rejects_bad_password_generically` |
| Session theft via XSS | Token only in `HttpOnly; SameSite=Strict` cookie, 30-min expiry; strict CSP (`script-src 'self'`); React escapes output; no `dangerouslySetInnerHTML` | `routes/auth.py`, `main.py` | `test_session_cookie_flags`, `test_security_headers` |
| CSRF | SameSite=Strict + mandatory `X-Requested-With: pramaan` on non-GET cookie requests | `api.py` | `test_unauthenticated_and_csrf` |
| Broken access control / IDOR | Role check per route **and** object-level check on every application, document, job, finding; cross-tenant ids return 404 | `routes/common.py` | `test_institution_cannot_see_other_institution`, `test_role_checks` |
| Leaking another institution's evidence through duplicate findings | Institution view strips matched ids and names | `routes/common.finding_out` | `test_institution_sees_duplicate_without_other_institution_details` |
| Malicious or malformed uploads | Type by magic bytes, not extension; size cap read in bounded chunks; page cap; encrypted/malformed PDFs rejected; decompression-bomb pixel limit; images re-encoded (EXIF stripped) before display | `pipeline/intake.py`, `routes/documents.py` | `test_upload_rejections`, `IntakeTests` |
| Path traversal | Files stored by SHA-256; user names are display-only and sanitized | `storage.py` | traversal-named upload in `test_upload_rejections` |
| Code injection through rule packs | Expressions parsed with `ast` and walked against a whitelist; no attribute access, subscripts, lambdas, comprehensions, `**` or `eval`; packs validated before activation | `pipeline/safe_expr.py`, `rules_engine.py` | `SafeExpressionTests`, `test_rule_pack_rejects_unsafe_expression` |
| Prompt injection inside documents | No language model anywhere in the pipeline; document text is matched by fixed patterns and never executed or used as instructions | design | review |
| Unilateral rule changes | Proposals create a version; activation by a different administrator (four eyes); both audited | `routes/oversight.py` | `test_four_eyes_rule_activation` |
| Tampering with history | Hash-chained audit log; verifier reports the first broken entry | `audit.py` | `test_tampering_is_detected`, `test_audit_chain_detects_database_tampering` |
| Over-trusting automation | Findings are `advisory`; database CHECK forbids `advisory = 0`; no approve/reject/forged vocabulary exists in any enum; decisions need a reason ≥ 10 characters | `schemas.py`, migration | `test_no_adverse_decision_vocabulary` |
| SSRF / unauthorized external access | Verification integrations remain off; configured email and backup destinations are operator controlled; Resend uses a fixed HTTPS endpoint with no redirects | `config.py`, `email.py`, `scripts/backup.py` | configuration and mocked provider tests |
| Sensitive data in logs | Access log records route template, status, timing, request id and an HMAC user hash; bodies and query values are excluded; decision reasons are stored in `reviews`, hashed in audit payloads | `observability.py`, `audit.py` | operational redaction tests |
| Error disclosure | Unhandled errors return a generic message; logs contain sanitized codes and optional Sentry events are scrubbed | `api.py`, `observability.py` | operational redaction tests |
| Weak production config | Startup refuses default/short `JWT_SECRET`, insecure cookies or wildcard CORS when `APP_ENV=production` | `config.py` | manual |
| Resource exhaustion | JSON body cap (256 KB), upload cap, page cap, upload rate limit, audit list cap (500) | `api.py`, routes | `test_upload_rejections` |

## Accounts and operational controls added 23 October 2026

- Authentication now requires both a valid JWT and an unrevoked, unexpired database session. Role, active state and profile are read from the current user row on every request. Logout and deactivation revoke sessions, reset revokes all, password change revokes other sessions, and refresh atomically consumes the old session. Login rechecks the password hash under its write lock to prevent a reset/login race. Existing cookies without a stored session require a new sign-in after upgrade.
- Session metadata stores only IPv4 /24 or IPv6 /48 prefixes and at most 120 user-agent characters. Last-seen writes occur at most once per minute. Proxy headers are ignored unless `TRUST_PROXY=true`; restrict direct ingress to the trusted proxy when enabling it. Run Uvicorn with `--no-proxy-headers` so the application setting is the single source of proxy trust.
- Tokens use 32 random bytes and purpose-scoped SHA-256 hashes. Verification expires after 24 hours, resets after 30 minutes, invitations after 72 hours. Consumption and account changes are one transaction; expired, incorrect and reused tokens have the same failure. New tokens invalidate previous unused tokens of the same purpose.
- New passwords require 12–200 characters, exclude the email local part and a bundled list of 499 distinct weak patterns. Existing scrypt hashes continue to work. Duplicate email/Permanent ID registration and forgot-password requests have generic 202 bodies. Registration performs the expensive password hash before duplicate checks; provider I/O runs off the request thread. A startup warmup prevents the first unknown-email login from paying an extra dummy-hash cost.
- Public account flows, refresh, login and uploads are rate limited. Limits are in-memory and **single instance**, reset on process restart, and must be moved to shared storage for replicas. Email keys are hashed. The application does not expose whether a forgot-password email was sent.
- Institution users cannot activate themselves: verified registrations still require administrative acceptance. Declining retains the account and institution and emails the reason. Reactivation cannot bypass verification or pending/declined registration. Staff invitations create inactive users with unusable passwords. Deactivation cannot target the acting administrator or the last active administrator.
- Notification recipient resolution enforces institution ownership and submitted-application visibility for staff, including explicit recipient IDs. Clarification attachments must belong to the same application. Reports reuse sanitized finding serializers; cross-institution duplicate details remain withheld from institutions. Same-second timeline entries preserve audit sequence.
- SMTP requires STARTTLS; Resend uses a fixed HTTPS endpoint, a 20-second timeout and no redirects. Providers retry twice. Console `.eml` files intentionally contain development tokens and live only under private, ignored `DATA_DIR/outbox`; they are never application logs. Production refuses console email. Restrict outbox ACLs on Windows and remove local data before sharing a workspace.
- JSON request logs contain request ID, method, route template, status, elapsed milliseconds and an HMAC-derived user ID hash. Uvicorn's query-bearing access log is disabled. No request bodies, document text, token values or provider response bodies are logged. Optional Sentry disables default PII/integrations and scrubs request/user/breadcrumb/local-variable data and exception messages.
- Metrics require their own constant-time-checked Bearer token and are off when unset. Queue counts and stage duration aggregates come from SQLite, including supervised worker processes. Email failure metrics store only provider, sanitized error code and timestamp.
- Worker threads supervise isolated processing subprocesses. A hard timeout terminates and waits for the subprocess before marking failure, preventing late database writes. Retryable I/O/timeouts get 2s/8s backoff; validation failures are not retried. The synchronous test/benchmark mode checks deadlines between stages; use `WORKER_THREADS>=1` for the hard deadline.
- Upload idempotency keys are scoped by user/application and stored atomically with the first response. Authorization runs before cache lookup. Backups use SQLite's online backup API and archive the immutable content-addressed store. SHA-256 manifests and SQLite integrity checks are verified before restore; archive traversal, links and paths escaping the store are refused. An OS-held instance lock blocks restore while the server is active.

Remaining operational limits: the email dispatch queue is in-memory (a crash can lose queued mail; users can request another reset, and operators can inspect provider logs); SMTP/Resend/S3 live delivery and Sentry transport need deployment credentials and were not exercised against live services. Backup manifests are integrity checks, not signatures. Encrypt backup storage and restrict its credentials. Retained extra content-addressed files are harmless to restore consistency but still require an explicit retention policy.

## Residual risks from the original prototype
- **Rate limiting is per process.** Use Redis-backed limits behind a load balancer.
- **No malware scanning.** Add ClamAV (or an equivalent government-approved scanner) as an intake step before storage.
- **Encryption at rest** depends on the host volume; use an encrypted volume or object store with server-side encryption.
- **Audit anchoring.** The chain detects edits but a full rewrite by a database administrator would recompute it; anchor the head hash daily to an external, signed record.
- **No MFA / SSO.** Integrate with the AICTE identity provider (OIDC) before real use.
- **Synthetic issuer private keys** are stored in `DATA_DIR` for the demo generator only; real issuer keys are public keys obtained from issuers.
- **Dependency audit.** Run `pip-audit` and `npm audit` in CI once registry access is available.
- **DPDP Act 2023 obligations** (purpose limitation, retention, data-principal rights) must be settled with AICTE before real data is processed.
