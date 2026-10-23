# Security and threat model

PRAMAAN holds institutional records and documents that can affect a regulatory outcome. Security is part of the design, not a later layer. This document lists what is implemented, how it is tested, and what remains.

## Assets
Uploaded documents · extracted values · findings and officer decisions · rule packs · audit trail · session tokens · synthetic issuer private keys (demo only).

## Trust boundaries
Browser ↔ API (untrusted input) · API ↔ worker (same process) · worker ↔ external sources (adapters; none live in this build) · administrators ↔ rule packs (privileged data that changes outcomes).

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
| SSRF / unauthorized external access | No outbound calls; integrations off unless configured and authorized | `config.py` | default config |
| Sensitive data in logs | Access log records method, path, status, timing and a request id only; audit payloads hold ids and hashes (decision reasons are stored in `reviews`, hashed in the audit payload) | `main.py`, `audit.py` | review |
| Error disclosure | Unhandled errors return a generic message; details stay in server logs | `api.py` | review |
| Weak production config | Startup refuses default/short `JWT_SECRET`, insecure cookies or wildcard CORS when `APP_ENV=production` | `config.py` | manual |
| Resource exhaustion | JSON body cap (256 KB), upload cap, page cap, upload rate limit, audit list cap (500) | `api.py`, routes | `test_upload_rejections` |

## Residual risks and next steps
- **Rate limiting is per process.** Use Redis-backed limits behind a load balancer.
- **No malware scanning.** Add ClamAV (or an equivalent government-approved scanner) as an intake step before storage.
- **Encryption at rest** depends on the host volume; use an encrypted volume or object store with server-side encryption.
- **Audit anchoring.** The chain detects edits but a full rewrite by a database administrator would recompute it; anchor the head hash daily to an external, signed record.
- **No MFA / SSO.** Integrate with the AICTE identity provider (OIDC) before real use.
- **Synthetic issuer private keys** are stored in `DATA_DIR` for the demo generator only; real issuer keys are public keys obtained from issuers.
- **Dependency audit.** Run `pip-audit` and `npm audit` in CI once registry access is available.
- **DPDP Act 2023 obligations** (purpose limitation, retention, data-principal rights) must be settled with AICTE before real data is processed.
