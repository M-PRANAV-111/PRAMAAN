"""API contract — the single source of truth for request and response shapes.

``scripts/gen_contract.py`` turns these models (plus the route registry) into
``contracts/openapi.json`` and the TypeScript types used by ``front/``.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Role = Literal["INSTITUTION", "OFFICER", "ADMIN", "AUDITOR"]
Category = Literal["EOA_EXISTING", "EOA_INTAKE_INCREASE"]
ApplicationStatus = Literal["DRAFT", "PROCESSING", "READY_FOR_SCRUTINY", "DEFICIENCIES_FLAGGED", "MANUAL_REVIEW_REQUIRED"]
DocType = Literal["eoa_letter", "affidavit", "fire_noc", "building_stability", "faculty_summary", "infra_photo"]
VerificationStatus = Literal["VERIFIED", "MISMATCH_DETECTED", "EXPIRED", "VERIFICATION_PENDING",
                             "SOURCE_UNAVAILABLE", "MANUAL_REVIEW_REQUIRED"]
RuleOutcome = Literal["PASS", "FAIL", "NOT_EVALUABLE", "NOT_APPLICABLE"]
Severity = Literal["DEFICIENCY", "REVIEW", "INFO"]
FindingState = Literal["OPEN", "CONFIRMED", "DISMISSED", "ESCALATED", "CLARIFICATION_REQUESTED", "RESOLVED"]
FindingSource = Literal["RULE", "INTEGRITY", "DUPLICATE", "VERIFICATION"]
ReviewDecision = Literal["CONFIRM", "DISMISS", "ESCALATE", "REQUEST_CLARIFICATION"]
JobState = Literal["QUEUED", "RUNNING", "DONE", "FAILED"]
ProcessingState = Literal["QUEUED", "PROCESSING", "DONE", "FAILED"]
ActionOwner = Literal["INSTITUTION", "OFFICER"]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------- auth
class LoginRequest(Model):
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=1, max_length=200)


class UserOut(Model):
    id: str
    email: str
    name: str
    role: Role
    institution_id: str | None
    institution_name: str | None


class SessionOut(Model):
    user: UserOut
    expires_at: str


# ---------------------------------------------------------------- applications
class InstitutionOut(Model):
    id: str
    aicte_permanent_id: str
    name: str
    state: str


class FindingCounts(Model):
    active: int
    deficiencies: int
    reviews: int
    resolved: int
    dismissed: int


class JobOut(Model):
    id: str
    kind: Literal["PROCESS_DOCUMENT", "VALIDATE"]
    state: JobState
    stage: str
    progress: int
    error: str | None
    document_id: str | None
    application_id: str


class RunOut(Model):
    id: str
    trigger: str
    rule_pack_version: str
    started_at: str
    finished_at: str | None
    affected_rules: list[str]
    summary: dict[str, Any] | None


class ApplicationCreate(Model):
    category: Category
    academic_year: str = Field(pattern=r"^20\d{2}-\d{2}$")


class ApplicationSummary(Model):
    id: str
    institution: InstitutionOut
    category: Category
    category_label: str
    academic_year: str
    status: ApplicationStatus
    created_at: str
    updated_at: str
    submitted_at: str | None
    counts: FindingCounts
    documents_uploaded: int
    documents_required: int


class DocumentOut(Model):
    id: str
    doc_type: DocType
    doc_type_label: str
    detected_type: str | None
    original_name: str
    sha256: str
    size_bytes: int
    mime: str
    pages: int
    has_text_layer: bool
    uploaded_at: str
    processing_state: ProcessingState
    verification_status: VerificationStatus | None
    superseded: bool


class ChecklistItemOut(Model):
    doc_type: DocType
    label: str
    required: bool
    note: str
    document: DocumentOut | None


class ApplicationDetail(ApplicationSummary):
    checklist: list[ChecklistItemOut]
    documents: list[DocumentOut]
    latest_run: RunOut | None
    active_jobs: list[JobOut]
    rule_pack_version: str


class UploadResponse(Model):
    document: DocumentOut
    job: JobOut


# ---------------------------------------------------------------- evidence & verification
class ClaimOut(Model):
    id: str
    document_id: str
    field: str
    value_raw: str
    value_norm: str | None
    value_type: str
    page: int
    bbox: list[float]
    page_size: list[float]
    extractor: str
    confidence: float


class VerificationOut(Model):
    id: str
    document_id: str
    tier: int
    channel: str
    status: VerificationStatus
    simulated: bool
    request_ref: str | None
    response_hash: str | None
    detail: dict[str, Any]
    created_at: str


class DocumentEvidence(Model):
    document: DocumentOut
    claims: list[ClaimOut]
    verifications: list[VerificationOut]
    integrity: list[dict[str, Any]]
    extraction: dict[str, Any] | None


class EvidenceRef(Model):
    model_config = ConfigDict(extra="allow")
    document_id: str | None = None
    doc_type: str | None = None
    document_name: str | None = None
    claim_id: str | None = None
    field: str | None = None
    value: Any = None
    normalized: str | None = None
    page: int | None = None
    bbox: list[float] | None = None
    page_size: list[float] | None = None
    extractor: str | None = None
    confidence: float | None = None
    other_application: bool | None = None


# ---------------------------------------------------------------- findings
class ReviewOut(Model):
    id: str
    reviewer_name: str
    reviewer_role: Role
    decision: ReviewDecision
    reason: str
    created_at: str


class FindingOut(Model):
    id: str
    application_id: str
    source_kind: FindingSource
    rule_id: str | None
    title: str
    severity: Severity
    state: FindingState
    explanation: str
    remedy: str
    fix_doc_type: str | None
    action_owner: ActionOwner
    advisory: Literal[True]
    clause_status: str | None
    proof: dict[str, Any]
    evidence: list[EvidenceRef]
    created_at: str
    resolved_at: str | None
    reviews: list[ReviewOut]


class ReviewRequest(Model):
    decision: ReviewDecision
    reason: str = Field(min_length=10, max_length=2000)


class RepairAction(Model):
    id: str
    step: int
    owner: ActionOwner
    title: str
    doc_type: str | None
    details: list[str] = []
    resolves: list[str]
    finding_titles: list[str]
    priority: int
    severity: Severity


class RepairPlanOut(Model):
    institution_actions: list[RepairAction]
    officer_actions: list[RepairAction]
    open_findings: int
    note: str


# ---------------------------------------------------------------- rules
class ClauseOut(Model):
    ref: str
    status: str
    url: str | None


class RuleOut(Model):
    id: str
    title: str
    type: str
    severity: Severity
    clause: ClauseOut
    remedy: str
    applies_to: list[str] | None
    params: dict[str, Any]
    expr: str | None
    inputs: dict[str, str] | None
    field: str | None
    sources: list[str] | None
    doc_type: str | None
    on_or_after: str | None
    reads: list[str]


class RulePackVersionOut(Model):
    id: str
    pack: str
    version: str
    status: Literal["PROPOSED", "ACTIVE", "RETIRED"]
    change_note: str
    content_hash: str
    proposed_by_name: str | None
    activated_by_name: str | None
    created_at: str
    activated_at: str | None


class RulePackOut(Model):
    version: RulePackVersionOut
    title: str
    source: dict[str, str]
    reference_dates: dict[str, str]
    categories: dict[str, dict[str, str]]
    rules: list[RuleOut]
    versions: list[RulePackVersionOut]


class RuleProposalRequest(Model):
    changes: dict[str, dict[str, float]] = Field(min_length=1)
    note: str = Field(min_length=10, max_length=500)


class RuleDiffEntry(Model):
    rule_id: str
    param: str
    old: Any
    new: Any


class RuleProposalOut(Model):
    version: RulePackVersionOut
    diff: list[RuleDiffEntry]


# ---------------------------------------------------------------- audit, dashboard, meta
class AuditEventOut(Model):
    seq: int
    ts: str
    actor_id: str | None
    actor_role: str | None
    actor_name: str | None
    action: str
    object_type: str
    object_id: str
    application_id: str | None
    payload: dict[str, Any]
    hash: str
    prev_hash: str


class AuditVerifyOut(Model):
    valid: bool
    events_checked: int
    first_broken_seq: int | None
    problem: str | None
    head_hash: str | None


class DashboardOut(Model):
    role: Role
    applications: int
    by_status: dict[str, int]
    open_findings: int
    findings_by_source: dict[str, int]
    verification_by_status: dict[str, int]
    reviews_recorded: int
    simulated_sources_in_use: bool


class MetaOut(Model):
    doc_types: dict[str, str]
    categories: dict[str, str]
    application_statuses: list[str]
    verification_statuses: list[str]
    default_academic_year: str
    rule_pack_version: str
    max_upload_bytes: int


class HealthOut(Model):
    status: Literal["ok", "degraded"]
    checks: dict[str, str]


class ErrorBody(Model):
    code: str
    message: str
    details: Any = None


class ErrorOut(Model):
    error: ErrorBody


class OkOut(Model):
    ok: Literal[True] = True
