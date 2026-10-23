from __future__ import annotations

import io

from PIL import Image, ImageOps
from starlette.responses import Response

from .. import audit
from ..api import ApiError, Ctx, not_found, route
from ..config import get_settings
from ..db import loads, new_id, now_iso, reader, transaction
from ..pipeline.doctypes import DOC_TYPES
from ..pipeline.extract import render_page
from ..pipeline.intake import IntakeError, validate_upload
from ..pipeline.orchestrator import create_job, worker
from ..schemas import DocumentEvidence, JobOut, UploadResponse
from ..security import rate_limiter
from ..storage import LocalStorage, safe_display_name
from .common import document_out, job_out, load_application, load_document


@route("POST", "/api/v1/applications/{application_id}/documents",
       summary="Upload a document (multipart: file, doc_type). Replaces the current document of the same type.",
       tag="documents", response=UploadResponse, roles=("INSTITUTION",), multipart=True, status=202)
def upload_document(ctx: Ctx):
    s = get_settings()
    p = ctx.user
    if not rate_limiter.allow(f"upload:{p.user_id}", s.upload_rate_per_minute):
        raise ApiError(429, "rate_limited", "Too many uploads. Wait a minute and try again.")
    doc_type = ctx.form.get("doc_type", "")
    if doc_type not in DOC_TYPES:
        raise ApiError(422, "validation_error", "doc_type is missing or unknown", {"allowed": list(DOC_TYPES)})
    if ctx.file is None:
        raise ApiError(422, "validation_error", "No file was uploaded")
    with reader() as c:
        load_application(c, p, ctx.path["application_id"])  # authorize before touching the file
    try:
        info = validate_upload(ctx.file.data, doc_type, s.max_pdf_pages)
    except IntakeError as e:
        raise ApiError(422, e.code, e.message) from None
    sha = LocalStorage().put(ctx.file.data)
    doc_id = new_id("doc")
    with transaction() as c:
        a = load_application(c, p, ctx.path["application_id"])
        previous = c.execute("SELECT id FROM documents WHERE application_id = ? AND doc_type = ? AND superseded_by IS NULL",
                             (a["id"], doc_type)).fetchall()
        c.execute(
            "INSERT INTO documents (id, application_id, doc_type, original_name, sha256, size_bytes, mime, pages,"
            " uploaded_by, uploaded_at, processing_state) VALUES (?,?,?,?,?,?,?,?,?,?, 'QUEUED')",
            (doc_id, a["id"], doc_type, safe_display_name(ctx.file.filename), sha, len(ctx.file.data), info.mime,
             info.pages, p.user_id, now_iso()))
        for prev in previous:
            c.execute("UPDATE documents SET superseded_by = ? WHERE id = ?", (doc_id, prev["id"]))
        job_id = create_job(c, "PROCESS_DOCUMENT", a["id"], doc_id)
        c.execute("UPDATE applications SET updated_at = ? WHERE id = ?", (now_iso(), a["id"]))
        audit.record(c, p, "document.uploaded", "document", doc_id,
                     {"doc_type": doc_type, "sha256": sha, "size": len(ctx.file.data),
                      "replaces": [r["id"] for r in previous]}, a["id"])
    worker.submit(job_id)
    with reader() as c:
        d = c.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
        j = c.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return {"document": document_out(d), "job": job_out(j)}


@route("GET", "/api/v1/jobs/{job_id}", summary="Processing job status", tag="documents", response=JobOut)
def get_job(ctx: Ctx):
    with reader() as c:
        j = c.execute("SELECT * FROM jobs WHERE id = ?", (ctx.path["job_id"],)).fetchone()
        if j is None:
            raise not_found("Job")
        load_application(c, ctx.user, j["application_id"])
        return job_out(j)


@route("GET", "/api/v1/documents/{document_id}/evidence",
       summary="Extracted claims with positions, verification attempts and integrity indicators",
       tag="evidence", response=DocumentEvidence)
def document_evidence(ctx: Ctx):
    with reader() as c:
        d, _ = load_document(c, ctx.user, ctx.path["document_id"])
        claims = [{"id": r["id"], "document_id": r["document_id"], "field": r["field"], "value_raw": r["value_raw"],
                   "value_norm": r["value_norm"], "value_type": r["value_type"], "page": r["page"],
                   "bbox": [r["x0"], r["y0"], r["x1"], r["y1"]], "page_size": [r["page_width"], r["page_height"]],
                   "extractor": r["extractor"], "confidence": r["confidence"]}
                  for r in c.execute("SELECT * FROM claims WHERE document_id = ? ORDER BY page, y0", (d["id"],))]
        vers = [{**{k: r[k] for k in ("id", "document_id", "tier", "channel", "status", "request_ref", "response_hash",
                                       "created_at")}, "simulated": bool(r["simulated"]), "detail": loads(r["detail_json"], {})}
                for r in c.execute("SELECT * FROM verifications WHERE document_id = ? ORDER BY tier", (d["id"],))]
        integ = [{"kind": r["kind"], "page": r["page"], "bbox": loads(r["bbox_json"]), **loads(r["detail_json"], {})}
                 for r in c.execute("SELECT * FROM integrity_signals WHERE document_id = ?", (d["id"],))]
        return {"document": document_out(d), "claims": claims, "verifications": vers, "integrity": integ,
                "extraction": loads(d["extraction_json"])}


@route("GET", "/api/v1/documents/{document_id}/pages/{page}", summary="Rendered page image (PNG) for the evidence viewer",
       tag="evidence", raw=True, response=None)
def page_image(ctx: Ctx):
    try:
        page = int(ctx.path["page"])
    except ValueError:
        raise not_found("Page") from None
    with reader() as c:
        d, _ = load_document(c, ctx.user, ctx.path["document_id"])
    if page < 1 or page > d["pages"]:
        raise not_found("Page")
    data = LocalStorage().get(d["sha256"])
    if d["mime"] == "application/pdf":
        img = render_page(data, page - 1, dpi=110)
    else:
        with Image.open(io.BytesIO(data)) as im:
            img = ImageOps.exif_transpose(im).convert("RGB")  # re-encode: strips EXIF/GPS metadata
        img.thumbnail((1600, 1600))
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return Response(buf.getvalue(), media_type="image/png",
                    headers={"Cache-Control": "private, max-age=300", "X-Content-Type-Options": "nosniff"})
