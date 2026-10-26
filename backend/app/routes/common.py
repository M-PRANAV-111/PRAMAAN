"""Shared authorization checks and row → contract serializers."""
from __future__ import annotations

import sqlite3
from typing import Any

from ..api import ApiError, not_found
from ..db import loads
from ..pipeline.doctypes import DOC_TYPES
from ..pipeline.orchestrator import application_status_counts
from ..rulepacks import active_version
from ..security import OVERSIGHT_ROLES, Principal


def load_application(c: sqlite3.Connection, p: Principal, application_id: str) -> sqlite3.Row:
    """Object-level authorization. Institutions see only their own; oversight roles see submitted applications."""
    row = c.execute("SELECT * FROM applications WHERE id = ?", (application_id,)).fetchone()
    if row is None:
        raise not_found("Application")
    if p.role == "INSTITUTION":
        if row["institution_id"] != p.institution_id:
            raise not_found("Application")
    elif p.role in OVERSIGHT_ROLES:
        if row["submitted_at"] is None:
            raise not_found("Application")
    else:
        raise ApiError(403, "forbidden", "Not allowed")
    return row


def load_document(c: sqlite3.Connection, p: Principal, document_id: str) -> tuple[sqlite3.Row, sqlite3.Row]:
    doc = c.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
    if doc is None:
        raise not_found("Document")
    app = load_application(c, p, doc["application_id"])
    return doc, app


def document_out(d: sqlite3.Row | dict[str, Any], c: sqlite3.Connection | None = None) -> dict[str, Any]:
    if c is None:
        from ..db import reader
        with reader() as conn:
            return document_out(d, conn)
    version = c.execute('SELECT COUNT(*) FROM documents WHERE application_id=? AND doc_type=? AND '
                        '(uploaded_at < ? OR (uploaded_at = ? AND rowid <= (SELECT rowid FROM documents WHERE id=?)))',
                        (d['application_id'], d['doc_type'], d['uploaded_at'], d['uploaded_at'], d['id'])).fetchone()[0]
    return {
        "version": max(1, version),
        "id": d["id"], "doc_type": d["doc_type"], "doc_type_label": DOC_TYPES.get(d["doc_type"], d["doc_type"]),
        "detected_type": d["detected_type"], "original_name": d["original_name"], "sha256": d["sha256"],
        "size_bytes": d["size_bytes"], "mime": d["mime"], "pages": d["pages"], "has_text_layer": bool(d["has_text_layer"]),
        "uploaded_at": d["uploaded_at"], "processing_state": d["processing_state"],
        "verification_status": d["verification_status"], "superseded": d["superseded_by"] is not None,
    }


def job_out(j: sqlite3.Row) -> dict[str, Any]:
    from ..pipeline.hooks import STAGE_CODES
    from ..db import reader
    with reader() as c:
        history = [r['stage_code'] for r in c.execute('SELECT stage_code FROM job_stage_durations WHERE job_id=? ORDER BY rowid',(j['id'],))]
        notes = [r['text'] for r in c.execute('SELECT text FROM job_notes WHERE job_id=? ORDER BY created_at, rowid', (j['id'],))]
    code = j['stage_code'] or STAGE_CODES.get(j['stage'])
    if code and (not history or history[-1] != code):
        history.append(code)
    return {**{k: j[k] for k in ("id", "kind", "state", "stage", "progress", "error", "document_id", "application_id")},
            "stage_code": code, "error_message": j['error_message'], 'stage_history':history, 'ai_notes':notes}


def application_summary(c: sqlite3.Connection, a: sqlite3.Row) -> dict[str, Any]:
    inst = c.execute("SELECT * FROM institutions WHERE id = ?", (a["institution_id"],)).fetchone()
    _, pack = active_version(c)
    required = [i.doc_type for i in pack.checklist if i.required]
    uploaded = {r["doc_type"] for r in c.execute(
        "SELECT doc_type FROM documents WHERE application_id = ? AND superseded_by IS NULL", (a["id"],))}
    running = c.execute("SELECT 1 FROM jobs WHERE application_id = ? AND state IN ('QUEUED','RUNNING') LIMIT 1",
                        (a["id"],)).fetchone()
    return {
        "id": a["id"],
        "institution": {"id": inst["id"], "aicte_permanent_id": inst["aicte_permanent_id"], "name": inst["name"],
                        "state": inst["state"]},
        "category": a["category"], "category_label": pack.categories.get(a["category"], {}).get("label", a["category"]),
        "academic_year": a["academic_year"], "status": "PROCESSING" if running else a["status"],
        "created_at": a["created_at"], "updated_at": a["updated_at"], "submitted_at": a["submitted_at"],
        "counts": application_status_counts(c, a["id"]),
        "documents_uploaded": len(uploaded & set(required)), "documents_required": len(required),
    }


def run_out(c: sqlite3.Connection, r: sqlite3.Row) -> dict[str, Any]:
    v = c.execute("SELECT version FROM rule_pack_versions WHERE id = ?", (r["rule_pack_version_id"],)).fetchone()
    return {"id": r["id"], "trigger": r["trigger"], "rule_pack_version": v["version"] if v else "?",
            "started_at": r["started_at"], "finished_at": r["finished_at"],
            "affected_rules": loads(r["affected_rules_json"], []), "summary": loads(r["summary_json"])}


def finding_out(c: sqlite3.Connection, f: sqlite3.Row, p: Principal) -> dict[str, Any]:
    proof = loads(f["proof_json"], {})
    evidence = loads(f["evidence_json"], [])
    if p.role == "INSTITUTION" and f["source_kind"] == "DUPLICATE":
        # Never reveal another institution's evidence to an institution user.
        proof = {k: v for k, v in proof.items() if not k.startswith("matched_")}
        evidence = [e if not e.get("other_application") else
                    {"document_name": "Evidence in another application (withheld)", "other_application": True}
                    for e in evidence]
    reviews = [{"id": r["id"], "reviewer_name": r["name"], "reviewer_role": r["role"], "decision": r["decision"],
                "reason": r["reason"], "created_at": r["created_at"]}
               for r in c.execute("SELECT rv.*, u.name, u.role FROM reviews rv JOIN users u ON u.id = rv.reviewer_id"
                                  " WHERE rv.finding_id = ? ORDER BY rv.created_at", (f["id"],))]
    clause_status = (proof.get("rule") or {}).get("clause", {}).get("status") if isinstance(proof.get("rule"), dict) else None
    from ..pipeline.explain import apply_stored  # validated AI wording when one exists; the template otherwise
    return apply_stored(c, f, {
        "id": f["id"], "application_id": f["application_id"], "source_kind": f["source_kind"], "rule_id": f["rule_id"],
        "title": f["title"], "severity": f["severity"], "state": f["state"], "explanation": f["explanation"],
        "remedy": f["remedy"], "fix_doc_type": f["fix_doc_type"], "action_owner": f["action_owner"], "advisory": True,
        "clause_status": clause_status, "proof": proof, "evidence": evidence, "created_at": f["created_at"],
        "resolved_at": f["resolved_at"], "reviews": reviews,
        "responses": response_rows(c, f['id']),
    })


def response_rows(c, finding_id):
    return [{k:r[k] for k in ('id','author_name','text','document_id','created_at')} for r in c.execute(
        'SELECT r.*,u.name author_name FROM finding_responses r JOIN users u ON u.id=r.author_id '
        'WHERE finding_id=? ORDER BY r.created_at,r.rowid',(finding_id,))]
