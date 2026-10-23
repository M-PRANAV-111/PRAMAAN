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

## Example: a finding (abridged)

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
