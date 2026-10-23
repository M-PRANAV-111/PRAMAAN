"""Background processing: document pipeline, validation runs and finding reconciliation."""
from __future__ import annotations

import io
import json
import logging
import queue
import sqlite3
import threading
import time
import subprocess
import sys
from datetime import date, timedelta, datetime, timezone
from typing import Any

from PIL import Image

from .. import audit
from ..config import get_settings
from ..db import dumps, loads, new_id, now_iso, reader, transaction
from ..rulepacks import active_version
from ..storage import LocalStorage
from . import dedupe, extract, integrity, verification
from .doctypes import DOC_TYPES, IMAGE_DOC_TYPES
from .findings import ACTIVE_STATES, FindingDraft, derive_status, from_duplicate, from_integrity, from_rule
from .rules_engine import EvalContext, evaluate, rules_reading
from .hooks import STAGE_CODES, register_step, run_steps

log = logging.getLogger("pramaan.pipeline")
_execution = threading.local()


class JobTimeout(TimeoutError):
    pass


def _check_deadline():
    if time.monotonic() > getattr(_execution, 'deadline', float('inf')):
        raise JobTimeout()


# --------------------------------------------------------------------------------------- jobs
def create_job(conn: sqlite3.Connection, kind: str, application_id: str, document_id: str | None = None) -> str:
    job_id = new_id("job")
    ts = now_iso()
    conn.execute(
        "INSERT INTO jobs (id, application_id, document_id, kind, state, stage, progress, created_at, updated_at, stage_code)"
        " VALUES (?,?,?,?, 'QUEUED', 'Queued', 0, ?, ?, 'QUEUED')",
        (job_id, application_id, document_id, kind, ts, ts),
    )
    return job_id


def _stage(job_id: str, stage: str, progress: int, state: str = "RUNNING", error: str | None = None,
           code: str | None = None, error_message: str | None = None, conn=None) -> None:
    if state != 'FAILED':
        _check_deadline()
    code = code or STAGE_CODES.get(stage)
    from ..schemas import StageCode
    if code not in StageCode.__args__:
        raise ValueError('Unknown stage code')
    def update(c):
        previous = getattr(_execution,'stage_started',None)
        if previous and previous[0] == job_id:
            c.execute('INSERT INTO job_stage_durations (job_id,stage_code,seconds) VALUES (?,?,?)',
                      (job_id,previous[1],max(0,time.monotonic()-previous[2])))
        else:
            old=c.execute('SELECT stage_code,updated_at FROM jobs WHERE id=?',(job_id,)).fetchone()
            if old and old['stage_code']:
                c.execute('INSERT INTO job_stage_durations (job_id,stage_code,seconds) VALUES (?,?,?)',
                          (job_id,old['stage_code'],max(0,(datetime.now(timezone.utc)-datetime.fromisoformat(old['updated_at'])).total_seconds())))
        _execution.stage_started=(job_id,code,time.monotonic()) if state=='RUNNING' else None
        c.execute("UPDATE jobs SET stage=?,progress=?,state=?,error=?,updated_at=?,stage_code=?,error_message=? WHERE id=?",
                  (stage, progress, state, error, now_iso(), code, error_message, job_id))
    if conn is not None:
        update(conn)
        return
    with transaction() as c:
        update(c)


class Worker:
    def __init__(self) -> None:
        self._q: "queue.Queue[str]" = queue.Queue()
        self._threads: list[threading.Thread] = []
        self._started = False

    def start(self) -> None:
        n = get_settings().worker_threads
        if self._started or n <= 0:
            return
        self._started = True
        for i in range(n):
            t = threading.Thread(target=self._loop, name=f"pramaan-worker-{i}", daemon=True)
            t.start()
            self._threads.append(t)
        with transaction() as c:  # resume jobs interrupted by a restart
            pending = [r["id"] for r in c.execute("SELECT id FROM jobs WHERE state IN ('QUEUED','RUNNING') ORDER BY created_at")]
            c.execute("UPDATE jobs SET state = 'QUEUED', stage = 'Re-queued after restart', stage_code='QUEUED' WHERE state = 'RUNNING'")
        for job_id in pending:
            self._q.put(job_id)

    def submit(self, job_id: str) -> None:
        if get_settings().worker_threads <= 0:
            run_job(job_id)  # synchronous mode (tests, benchmark)
        else:
            self._q.put(job_id)

    def _loop(self) -> None:
        while True:
            job_id = self._q.get()
            if job_id is None:
                self._q.task_done()
                return
            try:
                run_job_supervised(job_id)
            except Exception:  # run_job records the failure; never let the worker die
                log.error("worker_failure code=unexpected")
            finally:
                self._q.task_done()

    def stop(self):
        for _ in self._threads:
            self._q.put(None)
        for thread in self._threads:
            thread.join()
        self._threads.clear()
        self._started=False

    def drain(self, timeout: float = 120.0) -> None:
        """Test helper: wait until all queued jobs are processed."""
        import time
        end = time.time() + timeout
        while self._q.unfinished_tasks and time.time() < end:
            time.sleep(0.05)


worker = Worker()


def run_job(job_id: str) -> None:
    with reader() as c:
        job = c.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if job is None or job['state'] in ('DONE','FAILED'):
        return
    _execution.deadline = time.monotonic() + get_settings().job_timeout_seconds
    try:
        for attempt in range(3):
            with transaction() as c:
                c.execute('UPDATE jobs SET attempts=? WHERE id=?',(attempt+1,job_id))
            try:
                _check_deadline()
                if job['kind']=='PROCESS_DOCUMENT':
                    process_document(job_id,job['document_id'],job['application_id'])
                else:
                    _stage(job_id,'Evaluating rule pack',40)
                    run_validation(job['application_id'],trigger='manual')
                _check_deadline()
                with transaction() as c:
                    app = dict(c.execute('SELECT * FROM applications WHERE id=?',(job['application_id'],)).fetchone())
                    run_steps('after_rules',c,job_id,app,lambda code,text,progress: _stage(job_id,text,progress,code=code,conn=c))
                    _check_deadline()
                _stage(job_id,'Done',100,state='DONE')
                return
            except (OSError, TimeoutError) as exc:
                if isinstance(exc,JobTimeout) or attempt==2:
                    raise
                delay = (2,8)[attempt]
                if time.monotonic()+delay >= _execution.deadline:
                    raise JobTimeout() from None
                time.sleep(delay)
    except Exception as exc:
        fail_job(job_id, 'timeout' if isinstance(exc,JobTimeout) else type(exc).__name__)
    finally:
        _execution.deadline = float('inf')


def fail_job(job_id, code):
    messages = {'timeout':'Processing took too long. Try again or upload a smaller document.',
                'OSError':'The stored file could not be read. Please try again.',
                'TimeoutError':'A processing service did not respond. Please try again.',
                'PasswordError':'This PDF is password-protected. Upload a copy without a password.'}
    message = messages.get(code,'This document could not be processed. Check the file and try again.')
    from ..notify import emit
    with transaction() as c:
        job = c.execute('SELECT * FROM jobs WHERE id=?',(job_id,)).fetchone()
        if not job or job['state'] in ('DONE','FAILED'):
            return
        _stage(job_id,'Failed',100,state='FAILED',error=code,error_message=message,conn=c)
        if job['document_id']:
            c.execute("UPDATE documents SET processing_state='FAILED' WHERE id=?",(job['document_id'],))
        app = c.execute('SELECT institution_id FROM applications WHERE id=?',(job['application_id'],)).fetchone()
        audit.record(c,None,'job.failed','job',job_id,{'code':code},job['application_id'])
        emit(c,to_institution=app['institution_id'],kind='PROCESSING_FAILED',title='Processing failed',body=message,
             link=f"/applications/{job['application_id']}",application_id=job['application_id'])
    log.warning('job_failure code=%s',code)


def run_job_supervised(job_id):
    from ..config import BACKEND_DIR
    proc = subprocess.Popen([sys.executable,'-m','app.pipeline.job_runner',job_id],cwd=BACKEND_DIR,
                            stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        proc.wait(timeout=get_settings().job_timeout_seconds)
        if proc.returncode:
            fail_job(job_id,'worker_exit')
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        fail_job(job_id,'timeout')
    finally:
        if proc.stdin:
            proc.stdin.close()
        (get_settings().data_dir/('.job-'+job_id+'.lock')).unlink(missing_ok=True)


# ------------------------------------------------------------------------------ document pipeline
def _app_context(c: sqlite3.Connection, application_id: str) -> tuple[dict, dict, dict | None]:
    app = dict(c.execute("SELECT * FROM applications WHERE id = ?", (application_id,)).fetchone())
    inst = dict(c.execute("SELECT * FROM institutions WHERE id = ?", (app["institution_id"],)).fetchone())
    rec = c.execute("SELECT * FROM aicte_records WHERE institution_id = ?", (inst["id"],)).fetchone()
    return app, inst, dict(rec) if rec else None


def process_document(job_id: str, document_id: str, application_id: str) -> None:
    storage = LocalStorage()
    with reader() as c:
        doc = dict(c.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone())
    with transaction() as c:
        c.execute("UPDATE documents SET processing_state = 'PROCESSING' WHERE id = ?", (document_id,))
    _stage(job_id, "Reading file", 10)
    data = storage.get(doc["sha256"])
    claims: list[extract.ExtractedClaim] = []
    signals: list[integrity.Indicator] = []
    summary: dict[str, Any] = {}
    phash = None

    if doc["doc_type"] in IMAGE_DOC_TYPES:
        _stage(job_id, "Fingerprinting photograph", 40)
        phash = dedupe.phash_image(data)
        with Image.open(io.BytesIO(data)) as im:
            summary["image_size"] = list(im.size)
    else:
        _stage(job_id, "Extracting text and layout", 25)
        result = extract.extract_pdf(data)
        summary.update({"has_text_layer": result.has_text_layer, "used_ocr": result.used_ocr,
                        "detected_type": result.detected_type, "classification_scores": result.classification_scores})
        _stage(job_id, "Extracting fields", 40)
        claims = extract.extract_claims(result, doc["doc_type"])
        with transaction() as c:
            _save_claims(c,document_id,application_id,claims)
            run_steps('after_fields',c,job_id,doc,lambda code,text,progress: _stage(job_id,text,progress,code=code,conn=c))
            _check_deadline()
            claims = [extract.ExtractedClaim(r['field'],r['value_raw'],r['value_norm'],r['value_type'],r['page'],
                      (r['x0'],r['y0'],r['x1'],r['y1']),r['page_width'],r['page_height'],r['extractor'],r['confidence'])
                      for r in c.execute('SELECT * FROM claims WHERE document_id=?',(document_id,))]
        if result.detected_type and result.detected_type != doc["doc_type"]:
            signals.append(integrity.Indicator(
                "DECLARED_TYPE_MISMATCH",
                f"Content looks like a {DOC_TYPES[result.detected_type]} but was uploaded as {DOC_TYPES[doc['doc_type']]}",
                {"declared": doc["doc_type"], "detected": result.detected_type, "scores": result.classification_scores},
            ))
        _stage(job_id, "Checking document integrity", 55)
        s_ind, facts = integrity.structure_indicators(data)
        v_ind, checks = integrity.visible_text_indicators(data, claims)
        signals += s_ind + v_ind
        summary.update({"structure": facts, "visible_text_checks": checks})

    _stage(job_id, "Verifying with sources", 70)
    with reader() as c:
        app, inst, rec = _app_context(c, application_id)
        _, pack = active_version(c)
        ctx = verification.LadderContext(
            conn=c, doc_type=doc["doc_type"], pdf_bytes=None if doc["doc_type"] in IMAGE_DOC_TYPES else data,
            claims={cl.field: cl.value_norm for cl in claims}, institution=inst, record=rec,
            academic_year_start=pack.ref("academic_year_start"),
        )
        final_status, attempts = verification.run_ladder(ctx)

    with transaction() as c:
        _check_deadline()
        ts = now_iso()
        if doc['doc_type'] in IMAGE_DOC_TYPES:
            _save_claims(c,document_id,application_id,claims)
        c.execute('DELETE FROM integrity_signals WHERE document_id=?',(document_id,))
        c.execute('DELETE FROM verifications WHERE document_id=?',(document_id,))
        for s in signals:
            page_size = None
            if s.page is not None:
                match = next((cl for cl in claims if cl.page == s.page), None)
                page_size = [match.page_width, match.page_height] if match else None
            c.execute("INSERT INTO integrity_signals (id, document_id, kind, detail_json, page, bbox_json, created_at)"
                      " VALUES (?,?,?,?,?,?,?)",
                      (new_id("sig"), document_id, s.kind, dumps({"title": s.title, **s.detail, "page_size": page_size}),
                       s.page, dumps(list(s.bbox)) if s.bbox else None, ts))
        for a in attempts:
            c.execute(
                "INSERT INTO verifications (id, document_id, application_id, tier, channel, status, simulated, request_ref,"
                " response_hash, detail_json, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (new_id("ver"), document_id, application_id, a.tier, a.channel, a.status, int(a.simulated), a.request_ref,
                 a.response_hash, dumps(a.detail), ts),
            )
            audit.record(c, None, "verification.attempt", "document", document_id,
                         {"tier": a.tier, "channel": a.channel, "status": a.status, "simulated": a.simulated,
                          "response_hash": a.response_hash}, application_id)
        c.execute("UPDATE documents SET processing_state = 'DONE', has_text_layer = ?, detected_type = ?, phash = ?,"
                  " verification_status = ?, extraction_json = ? WHERE id = ?",
                  (int(bool(summary.get("has_text_layer"))), summary.get("detected_type"), phash, final_status,
                   dumps(summary), document_id))
        audit.record(c, None, "document.processed", "document", document_id,
                     {"claims": len(claims), "indicators": [s.kind for s in signals], "verification": final_status},
                     application_id)
        from ..notify import emit
        today = datetime.now(timezone.utc).date()
        for cl in claims:
            if cl.field == 'valid_to' and cl.value_norm:
                try:
                    expiry = date.fromisoformat(cl.value_norm)
                except ValueError:
                    continue
                if today <= expiry <= today+timedelta(days=60) and not c.execute(
                        "SELECT 1 FROM notifications WHERE kind='VALIDITY_ENDING' AND application_id=? AND body=?",
                        (application_id,document_id)).fetchone():
                    emit(c,to_institution=inst['id'],kind='VALIDITY_ENDING',title='Document validity ending within 60 days',
                         body=document_id,link=f'/applications/{application_id}',application_id=application_id)

    _stage(job_id, "Re-validating affected rules", 85)
    with reader() as c:
        has_run = c.execute("SELECT 1 FROM validation_runs WHERE application_id = ? LIMIT 1", (application_id,)).fetchone()
    if has_run:
        run_validation(application_id, trigger=f"document:{doc['doc_type']}", changed_doc_types={doc["doc_type"]})
    else:
        run_validation(application_id, trigger="first-upload")


# ------------------------------------------------------------------------------- validation
def _save_claims(c, document_id, application_id, claims):
    c.execute('DELETE FROM claims WHERE document_id=?',(document_id,))
    for cl in claims:
        c.execute('INSERT INTO claims (id,document_id,application_id,field,value_raw,value_norm,value_type,page,'
                  'x0,y0,x1,y1,page_width,page_height,extractor,confidence) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                  (new_id('clm'),document_id,application_id,cl.field,cl.value_raw,cl.value_norm,cl.value_type,cl.page,
                   *cl.bbox,cl.page_width,cl.page_height,cl.extractor,cl.confidence))


def _load_eval_context(c: sqlite3.Connection, application_id: str) -> tuple[EvalContext, dict[str, dict]]:
    app, inst, rec = _app_context(c, application_id)
    docs = [dict(r) for r in c.execute(
        "SELECT * FROM documents WHERE application_id = ? AND superseded_by IS NULL AND processing_state = 'DONE'"
        " ORDER BY uploaded_at", (application_id,))]
    docs_by_type = {d["doc_type"]: d for d in docs}  # latest upload of each type wins
    claims_by_doc: dict[str, dict[str, dict]] = {}
    for d in docs_by_type.values():
        claims_by_doc[d["id"]] = {r["field"]: dict(r) for r in c.execute("SELECT * FROM claims WHERE document_id = ?", (d["id"],))}
    ver = {d["id"]: d["verification_status"] for d in docs_by_type.values()}
    return EvalContext(app, inst, rec, docs_by_type, claims_by_doc, ver), docs_by_type


def _duplicate_drafts(c: sqlite3.Connection, doc: dict, inst: dict) -> list[FindingDraft]:
    drafts = []
    others = c.execute(
        "SELECT d.*, a.institution_id, i.trust_name FROM documents d JOIN applications a ON a.id = d.application_id"
        " JOIN institutions i ON i.id = a.institution_id"
        " WHERE a.institution_id != ? AND d.superseded_by IS NULL AND d.processing_state = 'DONE'", (inst["id"],)).fetchall()
    for o in others:
        if o["trust_name"] == inst["trust_name"]:
            continue  # same trust / shared campus: legitimate reuse allow-list
        if o["sha256"] == doc["sha256"]:
            drafts.append(from_duplicate(doc, dict(o), "sha256", None))
        elif doc["phash"] and o["phash"]:
            dist = dedupe.hamming(doc["phash"], o["phash"])
            if dist <= dedupe.PHASH_MAX_DISTANCE:
                drafts.append(from_duplicate(doc, dict(o), "phash", dist))
    return drafts


def run_validation(application_id: str, trigger: str, changed_doc_types: set[str] | None = None,
                   propagate: bool = True) -> str:
    with reader() as c:
        pack_row, pack = active_version(c)
        ctx, docs_by_type = _load_eval_context(c, application_id)
        scope_rules = {r.id for r in pack.rules} if changed_doc_types is None else rules_reading(pack, changed_doc_types)
        # Completeness rules read the document inventory, which every upload changes.
        scope_rules |= {r.id for r in pack.rules if r.type == "require_document"}
        scope_types = set(DOC_TYPES) if changed_doc_types is None else changed_doc_types
        results = evaluate(pack, ctx, only=scope_rules)
        drafts: list[FindingDraft] = []
        matched_apps: dict[str, set[str]] = {}
        for res in results:
            d = from_rule(pack.rule(res.rule_id), res)
            if d:
                drafts.append(d)
        for doc_type, doc in docs_by_type.items():
            if doc_type not in scope_types:
                continue
            for s in c.execute("SELECT * FROM integrity_signals WHERE document_id = ?", (doc["id"],)):
                detail = loads(s["detail_json"], {})
                drafts.append(from_integrity({"kind": s["kind"], "title": detail.pop("title", s["kind"]),
                                              "detail": detail, "page": s["page"],
                                              "bbox": loads(s["bbox_json"]), "page_size": detail.get("page_size")}, doc))
            dup = _duplicate_drafts(c, doc, ctx.institution)
            for d in dup:
                matched_apps.setdefault(d.proof["matched_application_id"], set()).add(doc_type)
            drafts.extend(dup)

    run_id = new_id("run")
    ts = now_iso()
    with transaction() as c:
        _check_deadline()
        c.execute("INSERT INTO validation_runs (id, application_id, rule_pack_version_id, trigger, affected_rules_json,"
                  " started_at) VALUES (?,?,?,?,?,?)",
                  (run_id, application_id, pack_row["id"], trigger, dumps(sorted(scope_rules)), ts))
        for res in results:
            c.execute("INSERT INTO rule_results (id, run_id, application_id, rule_id, outcome, proof_json) VALUES (?,?,?,?,?,?)",
                      (new_id("rr"), run_id, application_id, res.rule_id, res.outcome, dumps(res.proof)))
        stats = _reconcile(c, application_id, run_id, drafts, scope_rules, scope_types, changed_doc_types is None)
        severities = [r["severity"] for r in c.execute(
            f"SELECT severity FROM findings WHERE application_id = ? AND state IN ({','.join('?' * len(ACTIVE_STATES))})",
            (application_id, *ACTIVE_STATES))]
        status = derive_status(severities)
        outcomes = {o: sum(1 for r in results if r.outcome == o) for o in ("PASS", "FAIL", "NOT_EVALUABLE", "NOT_APPLICABLE")}
        summary = {**stats, "outcomes": outcomes, "status_after": status, "rules_evaluated": len(results)}
        c.execute("UPDATE validation_runs SET finished_at = ?, summary_json = ? WHERE id = ?", (now_iso(), dumps(summary), run_id))
        c.execute("UPDATE applications SET status = ?, updated_at = ? WHERE id = ?", (status, now_iso(), application_id))
        audit.record(c, None, "validation.run", "application", application_id,
                     {"run_id": run_id, "trigger": trigger, "rule_pack_version": pack.version, "rules": len(results),
                      "created": stats["created"], "resolved": stats["resolved"], "status": status}, application_id)
    if propagate:
        # A match is symmetric: let the other application see it too (without bouncing back).
        for other_app, types in matched_apps.items():
            if other_app != application_id:
                run_validation(other_app, trigger=f"duplicate-match:{application_id}", changed_doc_types=types,
                               propagate=False)
    return run_id


def _reconcile(c: sqlite3.Connection, application_id: str, run_id: str, drafts: list[FindingDraft],
               scope_rules: set[str], scope_types: set[str], full: bool) -> dict[str, int]:
    existing = [dict(r) for r in c.execute("SELECT * FROM findings WHERE application_id = ? AND state != 'RESOLVED'",
                                           (application_id,))]
    by_fp = {f["fingerprint"]: f for f in existing}
    new_fps = {d.fingerprint for d in drafts}
    created = updated = resolved = 0
    ts = now_iso()
    for d in drafts:
        old = by_fp.get(d.fingerprint)
        if old:
            c.execute("UPDATE findings SET proof_json = ?, evidence_json = ?, explanation = ?, run_id = ? WHERE id = ?",
                      (dumps(d.proof), dumps(d.evidence), d.explanation, run_id, old["id"]))
            updated += 1
            continue
        fid = new_id("fnd")
        c.execute(
            "INSERT INTO findings (id, application_id, run_id, fingerprint, source_kind, rule_id, title, severity, state,"
            " explanation, remedy, fix_doc_type, action_owner, proof_json, evidence_json, advisory, created_at)"
            " VALUES (?,?,?,?,?,?,?,?, 'OPEN', ?,?,?,?,?,?, 1, ?)",
            (fid, application_id, run_id, d.fingerprint, d.source_kind, d.rule_id, d.title, d.severity, d.explanation,
             d.remedy, d.fix_doc_type, d.action_owner, dumps(d.proof), dumps(d.evidence), ts))
        created += 1
        audit.record(c,None,'finding.raised','finding',fid,{},application_id)
        from ..notify import emit
        inst = c.execute('SELECT institution_id FROM applications WHERE id=?',(application_id,)).fetchone()[0]
        if d.severity == 'DEFICIENCY':
            emit(c,to_institution=inst,kind='FINDING_RAISED',title='New deficiency',body=d.title,
                 link=f'/applications/{application_id}',application_id=application_id,finding_id=fid)
        if d.action_owner == 'OFFICER':
            emit(c,to_role='OFFICER',kind='OFFICER_NEEDED',title='An item needs officer review',body=d.title,
                 link=f'/applications/{application_id}',application_id=application_id,finding_id=fid)
    for f in existing:
        if f["fingerprint"] in new_fps:
            continue
        in_scope = full or (f["rule_id"] in scope_rules if f["source_kind"] == "RULE"
                            else (f["fix_doc_type"] in scope_types))
        if in_scope:
            c.execute("UPDATE findings SET state = 'RESOLVED', resolved_at = ?, resolved_by_run = ? WHERE id = ?",
                      (ts, run_id, f["id"]))
            resolved += 1
            audit.record(c,None,'finding.resolved','finding',f['id'],{},application_id)
    return {"created": created, "updated": updated, "resolved": resolved}


def application_status_counts(c: sqlite3.Connection, application_id: str) -> dict[str, Any]:
    rows = c.execute("SELECT severity, state, COUNT(*) n FROM findings WHERE application_id = ? GROUP BY severity, state",
                     (application_id,)).fetchall()
    out: dict[str, Any] = {"active": 0, "deficiencies": 0, "reviews": 0, "resolved": 0, "dismissed": 0}
    for r in rows:
        if r["state"] in ACTIVE_STATES:
            out["active"] += r["n"]
            out["deficiencies" if r["severity"] == "DEFICIENCY" else "reviews"] += r["n"]
        elif r["state"] == "RESOLVED":
            out["resolved"] += r["n"]
        elif r["state"] == "DISMISSED":
            out["dismissed"] += r["n"]
    return out


def date_or_none(v: str | None) -> date | None:
    return date.fromisoformat(v) if v else None


__all__ = ["worker", "create_job", "run_validation", "process_document", "application_status_counts", "json"]
