# API contract

The contract is generated from code, so it cannot drift from what the server does:

- `backend/app/schemas.py` — Pydantic models for every request and response.
- `backend/app/api.py` — the route registry (`@route(...)`) that validates bodies, enforces roles and serializes responses.
- `python -m scripts.gen_contract` writes **`contracts/openapi.json`** (OpenAPI 3.1) and **`contracts/api.gen.ts`** (TypeScript types, enum value lists and the endpoint table the web client calls through). `--check` fails CI if either file is stale.

## Conventions

| Topic | Rule |
|---|---|
| Base path | `/api/v1` |
| Auth | `pramaan_session` cookie (HttpOnly, SameSite=Strict) set by `POST /auth/login`; `Authorization: Bearer <jwt>` also accepted for API clients |
| CSRF | Every non-GET request made with the cookie must send `X-Requested-With: pramaan` |
| Errors | Always `{"error": {"code", "message", "details"}}` with a meaningful HTTP status (401, 403, 404, 409, 413, 422, 429, 500) |
| Object access | Institutions see only their own applications; officers, admins and auditors see submitted applications. Cross-tenant ids return 404, not 403 |
| Advisory flag | Every finding has `advisory: true`; no endpoint can approve, reject or declare forgery |
| Statuses | Verification: `VERIFIED`, `MISMATCH_DETECTED`, `EXPIRED`, `VERIFICATION_PENDING`, `SOURCE_UNAVAILABLE`, `MANUAL_REVIEW_REQUIRED`. Rule outcome: `PASS`, `FAIL`, `NOT_EVALUABLE`, `NOT_APPLICABLE`. Application (derived): `DRAFT`, `PROCESSING`, `READY_FOR_SCRUTINY`, `DEFICIENCIES_FLAGGED`, `MANUAL_REVIEW_REQUIRED` |
| Async work | Uploads and full checks return a `JobOut`; poll `GET /jobs/{job_id}` for `stage` and `progress` |

## Endpoints

| Method | Path | Purpose | Roles | Body | Success |
|---|---|---|---|---|---|
| `GET` | `/api/v1/applications` | List applications visible to the caller | any authenticated | — | 200 `ApplicationSummary[]` |
| `POST` | `/api/v1/applications` | Create a draft application | INSTITUTION | ApplicationCreate | 201 `ApplicationSummary` |
| `GET` | `/api/v1/applications/{application_id}` | Application workspace: checklist, documents, latest run | any authenticated | — | 200 `ApplicationDetail` |
| `POST` | `/api/v1/applications/{application_id}/submit` | Submit the application to AICTE for scrutiny | INSTITUTION | — | 200 `ApplicationSummary` |
| `POST` | `/api/v1/applications/{application_id}/validate` | Queue a full validation run | INSTITUTION, OFFICER, ADMIN | — | 202 `JobOut` |
| `GET` | `/api/v1/applications/{application_id}/runs` | Validation run history | any authenticated | — | 200 `RunOut[]` |
| `GET` | `/api/v1/applications/{application_id}/findings` | Findings with proof and evidence | any authenticated | — | 200 `FindingOut[]` |
| `GET` | `/api/v1/applications/{application_id}/repair-plan` | Grouped, ordered next steps | any authenticated | — | 200 `RepairPlanOut` |
| `GET` | `/api/v1/applications/{application_id}/verifications` | Verification ladder attempts | any authenticated | — | 200 `VerificationOut[]` |
| `POST` | `/api/v1/auth/login` | Sign in and receive a session cookie | public | LoginRequest | 200 `SessionOut` |
| `POST` | `/api/v1/auth/logout` | End the session | any authenticated | — | 200 `OkOut` |
| `GET` | `/api/v1/auth/me` | Current user | any authenticated | — | 200 `UserOut` |
| `POST` | `/api/v1/applications/{application_id}/documents` | Upload a document (multipart: file, doc_type). Replaces the current document of the same type. | INSTITUTION | multipart: file, doc_type | 202 `UploadResponse` |
| `GET` | `/api/v1/jobs/{job_id}` | Processing job status | any authenticated | — | 200 `JobOut` |
| `GET` | `/api/v1/documents/{document_id}/evidence` | Extracted claims with positions, verification attempts and integrity indicators | any authenticated | — | 200 `DocumentEvidence` |
| `GET` | `/api/v1/documents/{document_id}/pages/{page}` | Rendered page image (PNG) for the evidence viewer | any authenticated | — | 200 `PNG` |
| `POST` | `/api/v1/findings/{finding_id}/review` | Record an officer decision on a finding (reason required, audited) | OFFICER, ADMIN | ReviewRequest | 200 `FindingOut` |
| `GET` | `/api/v1/rules` | Active rule pack with clause references and version history | any authenticated | — | 200 `RulePackOut` |
| `POST` | `/api/v1/rules/proposals` | Propose a new rule-pack version by changing numeric parameters | ADMIN | RuleProposalRequest | 201 `RuleProposalOut` |
| `POST` | `/api/v1/rules/versions/{version_id}/activate` | Activate a proposed version (must be a different administrator from the proposer) | ADMIN | — | 200 `RulePackVersionOut` |
| `GET` | `/api/v1/audit` | Audit events, newest first | OFFICER, ADMIN, AUDITOR | — | 200 `AuditEventOut[]` |
| `GET` | `/api/v1/audit/verify` | Recompute the hash chain and report the first broken event | OFFICER, ADMIN, AUDITOR | — | 200 `AuditVerifyOut` |
| `GET` | `/api/v1/dashboard` | Role-scoped counts computed from stored data | any authenticated | — | 200 `DashboardOut` |
| `GET` | `/api/v1/benchmark` | Latest synthetic benchmark report (produced by backend/eval/benchmark.py) | OFFICER, ADMIN, AUDITOR | — | 200 `object` |
| `GET` | `/api/v1/health` | Liveness probe | public | — | 200 `HealthOut` |
| `GET` | `/api/v1/ready` | Readiness probe (database, rule pack, storage, OCR) | public | — | 200 `HealthOut` |
| `GET` | `/api/v1/meta` | Enumerations and configuration the UI needs | public | — | 200 `MetaOut` |

## Core backend extension (23 October 2026)

The generated contract now contains 56 operations and 63 schemas. Existing fields remain; the shared additions have defaults: `MetaOut.features`, `JobOut.stage_code/error_message`, `DocumentOut.version`, `FindingOut.responses/explanation_source/ai_assisted`, and `DocumentEvidence.ai_suggestions`.

| Method | Path (under `/api/v1`) | Body → response | Access |
|---|---|---|---|
| POST | `/auth/register` | `RegisterRequest` → 202 `AcceptedOut` | Public, 5/hour/IP |
| POST | `/auth/verify-email` | `TokenRequest` → `OkOut` | Public, 10/hour/IP |
| POST | `/auth/accept-invitation` | `AcceptInvitationRequest` → `OkOut` | Public, 10/hour/IP |
| POST | `/auth/password/forgot` | `EmailRequest` → 202 `AcceptedOut` | Public, 5/hour/IP and 3/hour/email hash |
| POST | `/auth/password/reset` | `PasswordResetRequest` → `OkOut` | Public, 10/hour/IP |
| POST | `/auth/password/change` | `PasswordChangeRequest` → `OkOut` | Authenticated, current password required |
| POST | `/auth/refresh` | No body → `SessionOut` | Authenticated, 30/minute/IP |
| GET / PATCH | `/account` | No body / `AccountUpdate` → `AccountOut` | Own account |
| GET | `/account/sessions` | → `SessionInfoOut[]` | Own active sessions |
| DELETE | `/account/sessions/{session_id}` | → `OkOut` | Own session; unknown/foreign → 404 |
| POST | `/account/sessions/revoke-others` | → `OkOut` | Own sessions |
| GET | `/notifications` | `unread`, `limit`, `offset` → `NotificationOut[]` | Own notifications |
| GET | `/notifications/unread-count` | → `CountOut` | Own notifications |
| POST | `/notifications/{notification_id}/read` | → `OkOut` | Owner |
| POST | `/notifications/read-all` | → `OkOut` | Own notifications |
| GET | `/applications/{application_id}/timeline` | → `TimelineEventOut[]` | Existing application visibility |
| GET | `/applications/{application_id}/report` | → `application/pdf` attachment | Existing application visibility; audited |
| GET | `/applications/{application_id}/documents/history` | → `DocumentOut[]` including superseded | Existing application visibility |
| POST | `/findings/{finding_id}/responses` | `ResponseRequest` → `ResponseOut` | INSTITUTION, own application; attachment must belong to it |
| GET | `/admin/registrations` | `status` → `RegistrationOut[]` | ADMIN; email-verified requests only |
| POST | `/admin/registrations/{registration_id}/accept` | `AcceptRegistrationRequest` → `RegistrationOut` | ADMIN |
| POST | `/admin/registrations/{registration_id}/decline` | `ReasonRequest` → `RegistrationOut` | ADMIN; reason at least 10 trimmed characters |
| GET | `/admin/users` | `role`, `active` → `AdminUserOut[]` | ADMIN |
| POST | `/admin/invitations` | `InvitationRequest` → 202 `AcceptedOut` | ADMIN; OFFICER, ADMIN or AUDITOR only |
| POST | `/admin/users/{user_id}/deactivate` | `ReasonRequest` → `AdminUserOut` | ADMIN; self/last-admin guards |
| POST | `/admin/users/{user_id}/reactivate` | → `AdminUserOut` | ADMIN; verified and registration eligible |
| GET | `/admin/system` | → `SystemOut` | ADMIN, AUDITOR |
| GET | `/metrics` | → Prometheus text | Separate `Authorization: Bearer <METRICS_TOKEN>`; 404 when disabled |

`GET /applications` accepts case-insensitive `q` (institution name or Permanent ID), an `ApplicationStatus` in `status`, `limit` (1–200), and non-negative `offset`. `X-Total-Count` reports the count after filters, before pagination. With no parameters, the JSON bytes and ordering match the original list implementation. With parameters, the default limit is 200. Invalid filters return 422.

Document versions use `(uploaded_at, rowid)` ordering within `(application_id, doc_type)`; rowid breaks same-second upload ties. The workspace lists current documents; the history endpoint includes every version. Replies are visible to the institution that owns the application and to authorized oversight users.

Upload requests may include `Idempotency-Key` (1–200 visible ASCII characters). The key is scoped to the authenticated user and application for 24 hours. Replays return the original 202 JSON bytes, even after processing finishes; poll its job to see current state. Concurrent duplicate keys cannot create two document rows. The same key with different content still returns the first response.

Stage codes are `QUEUED`, `READING`, `FINGERPRINTING`, `EXTRACTING_TEXT`, `EXTRACTING_FIELDS`, `AI_EXTRACTION`, `INTEGRITY`, `VERIFYING`, `RULES`, `ROUTING`, `DONE`, `FAILED`. Existing stage text is preserved. `error` remains a code; `error_message` is safe, plain-language guidance.

Feature registration: `app.features.register(name, bool_or_callable)`. Implemented core flags are `registration`, `password_reset`, `notifications`, `timeline`, `reports`, and `clarifications`. AI and routing flags are owned by their extension; no AI integration is claimed by the core backend.

### Extension hooks

Import `register_step` from `app.pipeline.orchestrator` (also available in `app.pipeline.hooks`). `register_step("after_fields", fn)` runs after claims are persisted and before integrity/source checks; `register_step("after_rules", fn)` runs after rule evaluation and reconciliation. Each function receives `(conn, job_id, document_or_application, stage)` inside a write transaction. Use `stage(code, text, progress)` with the provided connection; do not open a nested write transaction. Register steps at module import through the AI route/feature import in `main.py` so supervised subprocesses load them too. Registration order is preserved, and empty registries preserve deterministic outcomes.

`app.features.register_system_extra("ai", callable)` adds an entry to `SystemOut.extras`. The callable returns JSON-compatible data and must omit secrets. Core migrations occupy `0002`–`0007`; AI migrations remain `0050`–`0099`.

### Finding example

```json
{
  "id": "fnd_…", "source_kind": "RULE", "rule_id": "INTAKE.CONSISTENT", "severity": "REVIEW", "state": "OPEN",
  "title": "Intake is the same in the affidavit and the faculty summary",
  "explanation": "The total intake differs: 240 in Faculty & student strength summary; 300 in Affidavit (EoA format).",
  "remedy": "Correct the document with the wrong intake and re-upload it.",
  "fix_doc_type": "affidavit", "action_owner": "INSTITUTION", "advisory": true, "clause_status": "TO_VERIFY",
  "proof": {
    "rule": {"id": "INTAKE.CONSISTENT", "type": "consistency", "pack": "aicte-eoa", "version": "2026.1",
             "clause": {"ref": "Internal consistency of declarations", "status": "TO_VERIFY"}},
    "conflict": {"240": ["faculty_summary"], "300": ["affidavit"]},
    "tiebreak": {"source": "record:approved_intake", "value": "240"},
    "outcome": "FAIL"
  },
  "evidence": [
    {"document_id": "doc_…", "doc_type": "affidavit", "field": "total_intake", "value": "300", "page": 1,
     "bbox": [142.2, 171.4, 160.6, 182.6], "page_size": [595.3, 841.9], "extractor": "text-layer+template", "confidence": 0.98}
  ]
}
```
