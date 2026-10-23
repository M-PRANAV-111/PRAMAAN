from __future__ import annotations

from .. import audit
from ..api import ApiError, Ctx, route
from ..db import new_id, now_iso, reader, transaction
from ..pipeline.doctypes import DOC_TYPES
from ..pipeline.findings import ACTIVE_STATES
from ..pipeline.orchestrator import create_job, worker
from ..pipeline.repair import build_plan
from ..rulepacks import active_version
from ..schemas import (ApplicationCreate, ApplicationDetail, ApplicationSummary, FindingOut, JobOut, RepairPlanOut,
                       RunOut, VerificationOut)
from ..security import REVIEWER_ROLES
from ..schemas import ApplicationStatus
from starlette.responses import JSONResponse
from .notifications import pagination
from .common import application_summary, document_out, finding_out, job_out, load_application, run_out


@route("GET", "/api/v1/applications", summary="List applications visible to the caller", tag="applications",
       response=list[ApplicationSummary], query={"status": "Filter by derived status", "q": "Institution name or Permanent ID",
                                               "limit": "Up to 200", "offset": "Pagination offset"})
def list_applications(ctx: Ctx):
    p = ctx.user
    with reader() as c:
        if p.role == "INSTITUTION":
            rows = c.execute("SELECT * FROM applications WHERE institution_id = ? ORDER BY updated_at DESC",
                             (p.institution_id,)).fetchall()
        else:
            rows = c.execute("SELECT * FROM applications WHERE submitted_at IS NOT NULL ORDER BY submitted_at DESC").fetchall()
        out = [application_summary(c, r) for r in rows]
    status = ctx.query.get("status")
    if status and status not in ApplicationStatus.__args__:
        raise ApiError(422, 'validation_error', 'Unknown application status')
    q = ctx.query.get('q','').casefold().strip()
    if len(q)>240:
        raise ApiError(422,'validation_error','Search text must be at most 240 characters')
    out = [a for a in out if (not status or a['status']==status) and (not q or
           q in a['institution']['name'].casefold() or q in a['institution']['aicte_permanent_id'].casefold())]
    total = len(out)
    if ctx.query:
        limit, offset = pagination(ctx.query, 200)
        out = out[offset:offset+limit]
    return JSONResponse([ApplicationSummary.model_validate(a).model_dump(mode='json') for a in out],
                        headers={'X-Total-Count':str(total)})


@route("POST", "/api/v1/applications", summary="Create a draft application", tag="applications",
       body=ApplicationCreate, response=ApplicationSummary, roles=("INSTITUTION",), status=201)
def create_application(ctx: Ctx):
    body: ApplicationCreate = ctx.body
    p = ctx.user
    app_id = new_id("app")
    ts = now_iso()
    with transaction() as c:
        dup = c.execute("SELECT id FROM applications WHERE institution_id = ? AND academic_year = ? AND category = ?",
                        (p.institution_id, body.academic_year, body.category)).fetchone()
        if dup:
            raise ApiError(409, "duplicate_application", "An application for this year and category already exists",
                           {"application_id": dup["id"]})
        c.execute("INSERT INTO applications (id, institution_id, category, academic_year, status, created_by, created_at,"
                  " updated_at) VALUES (?,?,?,?, 'DRAFT', ?, ?, ?)",
                  (app_id, p.institution_id, body.category, body.academic_year, p.user_id, ts, ts))
        audit.record(c, p, "application.created", "application", app_id,
                     {"category": body.category, "academic_year": body.academic_year}, app_id)
        return application_summary(c, c.execute("SELECT * FROM applications WHERE id = ?", (app_id,)).fetchone())


@route("GET", "/api/v1/applications/{application_id}", summary="Application workspace: checklist, documents, latest run",
       tag="applications", response=ApplicationDetail)
def get_application(ctx: Ctx):
    with reader() as c:
        a = load_application(c, ctx.user, ctx.path["application_id"])
        row, pack = active_version(c)
        docs = c.execute("SELECT * FROM documents WHERE application_id = ? ORDER BY uploaded_at DESC", (a["id"],)).fetchall()
        current = {}
        for d in docs:
            if d["superseded_by"] is None and d["doc_type"] not in current:
                current[d["doc_type"]] = document_out(d, c)
        checklist = [{"doc_type": i.doc_type, "label": DOC_TYPES[i.doc_type], "required": i.required, "note": i.note,
                      "document": current.get(i.doc_type)} for i in pack.checklist]
        run = c.execute("SELECT * FROM validation_runs WHERE application_id = ? ORDER BY started_at DESC, rowid DESC LIMIT 1",
                        (a["id"],)).fetchone()
        jobs = c.execute("SELECT * FROM jobs WHERE application_id = ? AND state IN ('QUEUED','RUNNING') ORDER BY created_at",
                         (a["id"],)).fetchall()
        return {**application_summary(c, a), "checklist": checklist, "documents": [document_out(d, c) for d in docs if d['superseded_by'] is None],
                "latest_run": run_out(c, run) if run else None, "active_jobs": [job_out(j) for j in jobs],
                "rule_pack_version": row["version"]}


@route("POST", "/api/v1/applications/{application_id}/submit", summary="Submit the application to AICTE for scrutiny",
       tag="applications", response=ApplicationSummary, roles=("INSTITUTION",))
def submit_application(ctx: Ctx):
    with transaction() as c:
        a = load_application(c, ctx.user, ctx.path["application_id"])
        if a["submitted_at"]:
            raise ApiError(409, "already_submitted", "This application has already been submitted")
        if not c.execute("SELECT 1 FROM validation_runs WHERE application_id = ?", (a["id"],)).fetchone():
            raise ApiError(409, "not_validated", "Upload documents and run the pre-flight check before submitting")
        if c.execute("SELECT 1 FROM jobs WHERE application_id = ? AND state IN ('QUEUED','RUNNING')", (a["id"],)).fetchone():
            raise ApiError(409, "processing", "Wait for document processing to finish before submitting")
        ts = now_iso()
        c.execute("UPDATE applications SET submitted_at = ?, updated_at = ? WHERE id = ?", (ts, ts, a["id"]))
        audit.record(c, ctx.user, "application.submitted", "application", a["id"], {}, a["id"])
        from ..notify import emit
        for f in c.execute("SELECT id,title FROM findings WHERE application_id=? AND action_owner='OFFICER' "
                           "AND state IN ('OPEN','CONFIRMED','ESCALATED','CLARIFICATION_REQUESTED')",(a['id'],)):
            emit(c,to_role='OFFICER',kind='OFFICER_NEEDED',title='An item needs officer review',body=f['title'],
                 link=f"/applications/{a['id']}",application_id=a['id'],finding_id=f['id'])
        return application_summary(c, c.execute("SELECT * FROM applications WHERE id = ?", (a["id"],)).fetchone())


@route("POST", "/api/v1/applications/{application_id}/validate", summary="Queue a full validation run",
       tag="applications", response=JobOut, roles=("INSTITUTION",) + REVIEWER_ROLES, status=202)
def validate_application(ctx: Ctx):
    with transaction() as c:
        a = load_application(c, ctx.user, ctx.path["application_id"])
        job_id = create_job(c, "VALIDATE", a["id"])
        audit.record(c, ctx.user, "validation.requested", "application", a["id"], {"job_id": job_id}, a["id"])
    worker.submit(job_id)
    with reader() as c:
        return job_out(c.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone())


@route("GET", "/api/v1/applications/{application_id}/runs", summary="Validation run history", tag="applications",
       response=list[RunOut])
def list_runs(ctx: Ctx):
    with reader() as c:
        a = load_application(c, ctx.user, ctx.path["application_id"])
        rows = c.execute("SELECT * FROM validation_runs WHERE application_id = ? ORDER BY started_at DESC, rowid DESC LIMIT 50",
                         (a["id"],)).fetchall()
        return [run_out(c, r) for r in rows]


@route("GET", "/api/v1/applications/{application_id}/findings", summary="Findings with proof and evidence",
       tag="findings", response=list[FindingOut], query={"include_resolved": "true to include resolved findings"})
def list_findings(ctx: Ctx):
    include_resolved = ctx.query.get("include_resolved") == "true"
    with reader() as c:
        a = load_application(c, ctx.user, ctx.path["application_id"])
        rows = c.execute("SELECT * FROM findings WHERE application_id = ? ORDER BY CASE severity WHEN 'DEFICIENCY' THEN 0"
                         " WHEN 'REVIEW' THEN 1 ELSE 2 END, created_at", (a["id"],)).fetchall()
        return [finding_out(c, f, ctx.user) for f in rows if include_resolved or f["state"] != "RESOLVED"]


@route("GET", "/api/v1/applications/{application_id}/repair-plan", summary="Grouped, ordered next steps",
       tag="findings", response=RepairPlanOut)
def repair_plan(ctx: Ctx):
    with reader() as c:
        a = load_application(c, ctx.user, ctx.path["application_id"])
        rows = [dict(r) for r in c.execute(
            f"SELECT * FROM findings WHERE application_id = ? AND state IN ({','.join('?' * len(ACTIVE_STATES))})",
            (a["id"], *ACTIVE_STATES))]
    return build_plan(rows)


@route("GET", "/api/v1/applications/{application_id}/verifications", summary="Verification ladder attempts",
       tag="evidence", response=list[VerificationOut])
def list_verifications(ctx: Ctx):
    from ..db import loads
    with reader() as c:
        a = load_application(c, ctx.user, ctx.path["application_id"])
        rows = c.execute("SELECT * FROM verifications WHERE application_id = ? ORDER BY created_at, tier", (a["id"],)).fetchall()
        return [{**{k: r[k] for k in ("id", "document_id", "tier", "channel", "status", "request_ref", "response_hash",
                                       "created_at")}, "simulated": bool(r["simulated"]), "detail": loads(r["detail_json"], {})}
                for r in rows]
