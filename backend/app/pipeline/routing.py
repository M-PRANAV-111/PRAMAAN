"""Confidence and routing recommendation (step ``after_rules``).

A recommendation, never a decision: it says who should look at the case next and why, from deterministic state
only (rule results, findings, verification attempts, claim confidence). AI output can only make it *more*
cautious (an unconfirmed suggestion on a rule-read field keeps a case out of READY_FOR_SCRUTINY); nothing in a
document or a model answer can move a case towards READY.

Outcomes (no others):
  READY_FOR_SCRUTINY       every required document present; every rule PASS or NOT_APPLICABLE; every verification
                           VERIFIED by a non-simulated source; no open integrity or duplicate indicator; every
                           claim a rule reads is confident and has no unconfirmed AI suggestion.
  CORRECTIONS_REQUIRED     an open DEFICIENCY whose remedy belongs to the institution (from the repair plan).
  OFFICER_REVIEW_REQUIRED  anything else that is uncertain.
Both of the last two can hold; the primary outcome is CORRECTIONS_REQUIRED and every reason is still listed.
"""
from __future__ import annotations

import hashlib
import logging
import sqlite3
from dataclasses import dataclass, field
from typing import Any, Callable

from .. import audit
from ..ai import store
from ..ai.config import get_config
from ..db import dumps, loads, new_id, now_iso
from ..notify import emit
from ..rulepacks import active_version
from .ai_extract import TYPE_MISMATCH_KIND, read_fields_by_type
from .doctypes import DOC_TYPES, FIELD_LABELS
from .findings import ACTIVE_STATES
from .repair import build_plan
from .verification import LADDERS

log = logging.getLogger("pramaan.routing")

POLICY_VERSION = "routing-2026.1"
INSTITUTION_CODES = {"MISSING_DOCUMENT", "DEFICIENCY_OPEN"}

_NE_TEXT = {
    "low_confidence": "a value was read with low confidence",
    "missing_field": "a value could not be found on the document",
    "record_unavailable": "the AICTE record is unavailable",
    "verification_inconclusive": "no automated source could confirm the document",
    "evaluation_error": "the values could not be compared",
}
_VERIFICATION_CODES = {
    "MISMATCH_DETECTED": ("VERIFICATION_MISMATCH", "the issuing source reports different values"),
    "EXPIRED": ("VERIFICATION_EXPIRED", "the issuing source says it has expired"),
    "SOURCE_UNAVAILABLE": ("SOURCE_UNAVAILABLE", "the issuing source did not respond"),
    "MANUAL_REVIEW_REQUIRED": ("MANUAL_REVIEW_REQUIRED", "no automated source could confirm it"),
    "VERIFICATION_PENDING": ("VERIFICATION_PENDING", "verification has not finished"),
}


@dataclass
class Recommendation:
    outcome: str
    reasons: list[dict[str, Any]]
    ai_used: bool
    run_id: str | None
    state_key: str
    queue_flag: str | None
    institution_actions: int = 0
    officer_items: list[dict[str, Any]] = field(default_factory=list)


def _reason(code: str, text: str, finding_id: str | None = None, document_id: str | None = None) -> dict[str, Any]:
    return {"code": code, "text": text, "finding_id": finding_id, "document_id": document_id}


def _ne_reason(proof: dict[str, Any]) -> str:
    if "missing" in proof:
        return proof["missing"].get("reason", "unknown")
    if "skipped" in proof:
        reasons = {s["reason"] for s in proof["skipped"]}
        return "missing_document" if reasons <= {"missing_document"} else sorted(reasons - {"missing_document"})[0]
    if "verification_status" in proof:
        return "verification_inconclusive"
    return "evaluation_error" if "error" in proof else "unknown"


def missing_codes(reasons: list[dict[str, Any]]) -> set[str]:
    return {r["code"] for r in reasons}


def compute(conn: sqlite3.Connection, application_id: str) -> Recommendation:
    cfg = get_config()
    _, pack = active_version(conn)
    docs = [dict(r) for r in conn.execute(
        "SELECT * FROM documents WHERE application_id=? AND superseded_by IS NULL ORDER BY uploaded_at", (application_id,))]
    current = {d["doc_type"]: d for d in docs}
    findings = [dict(r) for r in conn.execute(
        f"SELECT * FROM findings WHERE application_id=? AND state IN ({','.join('?' * len(ACTIVE_STATES))})",
        (application_id, *ACTIVE_STATES))]
    rule_finding = {f["rule_id"]: f for f in findings if f["source_kind"] == "RULE"}
    latest: dict[str, sqlite3.Row] = {}
    for r in conn.execute("SELECT rr.rule_id, rr.outcome, rr.proof_json FROM rule_results rr JOIN validation_runs vr"
                          " ON vr.id=rr.run_id WHERE rr.application_id=? ORDER BY vr.started_at, vr.rowid, rr.rowid",
                          (application_id,)):
        latest[r["rule_id"]] = r
    run = conn.execute("SELECT id FROM validation_runs WHERE application_id=? ORDER BY started_at DESC, rowid DESC LIMIT 1",
                       (application_id,)).fetchone()

    reasons: list[dict[str, Any]] = []
    missing_reported: set[str] = set()

    def missing(doc_type: str, finding_id: str | None = None) -> None:
        if doc_type not in missing_reported:
            missing_reported.add(doc_type)
            reasons.append(_reason("MISSING_DOCUMENT", f"The {DOC_TYPES.get(doc_type, doc_type)} has not been uploaded.",
                                   finding_id))

    # rules: every rule must be PASS or NOT_APPLICABLE
    if run is None:
        reasons.append(_reason("NOT_VALIDATED_YET", "No documents have been checked yet."))
    for rule in pack.rules:
        if rule.type == "verification" or run is None:
            continue  # verification is judged per document below, from the attempts themselves
        res = latest.get(rule.id)
        finding = rule_finding.get(rule.id)
        fid = finding["id"] if finding else None
        if res is None:
            reasons.append(_reason("RULE_NOT_EVALUATED", f"Rule “{rule.title}” has not been evaluated yet.", fid))
        elif res["outcome"] == "FAIL":
            if rule.type == "require_document":
                missing(rule.doc_type or "", fid)
            elif rule.severity == "DEFICIENCY" and rule.action_owner == "INSTITUTION":
                reasons.append(_reason("DEFICIENCY_OPEN", f"{rule.title}: the institution needs to correct this.", fid))
            else:
                reasons.append(_reason("REVIEW_FINDING_OPEN", f"{rule.title}: needs officer review.", fid))
        elif res["outcome"] == "NOT_EVALUABLE":
            why = _ne_reason(loads(res["proof_json"], {}))
            if why != "missing_document":  # a missing document is reported once, above
                reasons.append(_reason("RULE_NOT_EVALUABLE", f"{rule.title} could not be checked automatically "
                                       f"({_NE_TEXT.get(why, 'an input is unavailable')}).", fid))
    for item in pack.checklist:
        if item.required and item.doc_type not in current:
            missing(item.doc_type)

    # integrity, duplicate and document-type indicators that are still open
    for f in findings:
        if f["source_kind"] == "INTEGRITY" and TYPE_MISMATCH_KIND in f["fingerprint"]:
            reasons.append(_reason("DOCUMENT_TYPE_MISMATCH", f["title"], f["id"]))
        elif f["source_kind"] == "INTEGRITY":
            reasons.append(_reason("INTEGRITY_INDICATOR_OPEN", f["title"], f["id"]))
        elif f["source_kind"] == "DUPLICATE":
            reasons.append(_reason("DUPLICATE_INDICATOR_OPEN",
                                   "Possible reuse of evidence from another application is flagged for officer review.",
                                   f["id"]))
        elif f["source_kind"] == "VERIFICATION":
            reasons.append(_reason("REVIEW_FINDING_OPEN", f["title"], f["id"]))

    # processing state and verification, per current document
    for d in docs:
        label = DOC_TYPES.get(d["doc_type"], d["doc_type"])
        if d["processing_state"] == "FAILED":
            reasons.append(_reason("DOCUMENT_PROCESSING_FAILED", f"The {label} could not be processed.", None, d["id"]))
        elif d["processing_state"] != "DONE":
            reasons.append(_reason("PROCESSING_INCOMPLETE", f"The {label} is still being processed.", None, d["id"]))
        elif d["doc_type"] in LADDERS:
            status = d["verification_status"] or "VERIFICATION_PENDING"
            if status == "VERIFIED":
                if _only_simulated(conn, d["id"]):
                    reasons.append(_reason("SIMULATED_SOURCE_ONLY", f"The {label} was confirmed only by a simulated source; "
                                           "an officer must confirm it with the issuer.", None, d["id"]))
            else:
                code, text = _VERIFICATION_CODES.get(status, ("MANUAL_REVIEW_REQUIRED", "it could not be confirmed"))
                reasons.append(_reason(code, f"The {label}: {text}.", None, d["id"]))

    # claim confidence and unconfirmed AI suggestions on the fields the rules read
    readable = read_fields_by_type(pack)
    for d in docs:
        if d["processing_state"] != "DONE":
            continue
        label = DOC_TYPES.get(d["doc_type"], d["doc_type"])
        for c in conn.execute("SELECT field, confidence FROM claims WHERE document_id=?", (d["id"],)):
            if c["field"] in readable.get(d["doc_type"], ()) and c["confidence"] < cfg.routing_min_confidence:
                reasons.append(_reason("LOW_CONFIDENCE_CLAIM", f"{FIELD_LABELS.get(c['field'], c['field']).capitalize()} in the "
                                       f"{label} was read with confidence {c['confidence']:.2f}.", None, d["id"]))
        for s in conn.execute("SELECT field FROM ai_suggestions WHERE document_id=? AND status='OPEN'", (d["id"],)):
            if s["field"] in readable.get(d["doc_type"], ()):
                reasons.append(_reason("AI_SUGGESTION_UNCONFIRMED", f"An AI suggestion for {FIELD_LABELS.get(s['field'], s['field'])}"
                                       f" in the {label} could not be confirmed on the page.", None, d["id"]))

    plan = build_plan([dict(f) for f in findings])
    institution_deficiencies = [a for a in plan["institution_actions"] if a["severity"] == "DEFICIENCY"]
    if run is None and "MISSING_DOCUMENT" in missing_codes(reasons):
        institution_deficiencies = institution_deficiencies or [{"id": "UPLOAD-REQUIRED"}]   # nothing validated: uploads come first
    if institution_deficiencies:
        outcome = "CORRECTIONS_REQUIRED"
    elif reasons:
        outcome = "OFFICER_REVIEW_REQUIRED"
    else:
        outcome = "READY_FOR_SCRUTINY"
        reasons = [_reason("NO_OPEN_ISSUES", "All required documents are present, every rule passed, every verification is "
                           "confirmed by a non-simulated source, and no indicator is open.")]
    key = hashlib.sha256(dumps([outcome, sorted((r["code"], r["finding_id"], r["document_id"]) for r in reasons),
                                [a["id"] for a in institution_deficiencies]]).encode()).hexdigest()
    ai_used = bool(
        conn.execute("SELECT 1 FROM ai_documents a JOIN documents d ON d.id=a.document_id WHERE d.application_id=?"
                     " AND d.superseded_by IS NULL AND a.step_status='RAN' LIMIT 1", (application_id,)).fetchone()
        or conn.execute("SELECT 1 FROM finding_ai_text t JOIN findings f ON f.id=t.finding_id WHERE f.application_id=?"
                        " AND t.status='accepted' LIMIT 1", (application_id,)).fetchone())
    return Recommendation(outcome, reasons, ai_used, run["id"] if run else None, key,
                          None if findings else "NO_OPEN_FINDINGS", len(institution_deficiencies),
                          [r for r in reasons if r["code"] not in INSTITUTION_CODES and r["code"] != "NO_OPEN_ISSUES"])



def _only_simulated(conn: sqlite3.Connection, document_id: str) -> bool:
    """True when the attempt that produced VERIFIED came from a simulated source or a synthetic issuer key."""
    for a in conn.execute("SELECT * FROM verifications WHERE document_id=? AND status='VERIFIED' ORDER BY created_at DESC, rowid DESC",
                          (document_id,)):
        detail = loads(a["detail_json"], {})
        if not a["simulated"] and not detail.get("issuer_key_simulated"):
            return False
    return True


# ------------------------------------------------------------------------------------ the step
def routing_step(conn: sqlite3.Connection, job_id: str, app: dict[str, Any], stage: Callable[..., None]) -> None:
    stage("ROUTING", "Recommending next steps", 95)
    conn.execute("SAVEPOINT routing")
    try:
        _record(conn, job_id, app["id"], app["institution_id"])
    except Exception as exc:  # noqa: BLE001 — a recommendation must never fail the job that produced the findings
        conn.execute("ROLLBACK TO routing")
        log.error("routing_failure type=%s", type(exc).__name__)
        store.add_job_note(conn, job_id, "Routing recommendation skipped: error")
    finally:
        conn.execute("RELEASE routing")


def _record(conn: sqlite3.Connection, job_id: str, application_id: str, institution_id: str) -> None:
    rec = compute(conn, application_id)
    prev = conn.execute("SELECT * FROM routing_recommendations WHERE application_id=? ORDER BY computed_at DESC, rowid DESC"
                        " LIMIT 1", (application_id,)).fetchone()
    changed = prev is None or prev["state_key"] != rec.state_key
    actions: list[dict[str, Any]] = [] if changed else loads(prev["actions_json"], [])
    settled = conn.execute("SELECT 1 FROM jobs WHERE application_id=? AND state IN ('QUEUED','RUNNING') AND id != ? LIMIT 1",
                           (application_id, job_id)).fetchone() is None
    link = f"/applications/{application_id}"

    def logged(kind: str, summary: str, notified: int | None = None) -> None:
        actions.append({"type": kind, "summary": summary, "notified": notified})
        audit.record(conn, None, "routing.action", "application", application_id,
                     {"action": kind, "outcome": rec.outcome, "run_id": rec.run_id, "notified": notified}, application_id)

    if rec.queue_flag and (prev is None or prev["queue_flag"] != rec.queue_flag):
        logged("MARK_NO_OPEN_FINDINGS", "Marked “No open findings” for queue ordering.")
    def already_unread(kind: str) -> bool:
        return conn.execute("SELECT 1 FROM notifications WHERE application_id=? AND kind=? AND finding_id IS NULL"
                            " AND read_at IS NULL LIMIT 1", (application_id, kind)).fetchone() is not None

    if changed and settled:
        if rec.outcome == "CORRECTIONS_REQUIRED":
            if already_unread("CORRECTIONS_REQUIRED"):  # one unread notice at a time, not one per upload
                logged("NOTIFY_INSTITUTION", "The institution already has an unread notice with the repair plan.", 0)
            else:
                n = len(emit(conn, to_institution=institution_id, kind="CORRECTIONS_REQUIRED", title="Corrections needed",
                             body=f"{rec.institution_actions} item(s) need your action. The repair plan lists the steps.",
                             link=link, application_id=application_id))
                logged("NOTIFY_INSTITUTION", "Told the institution which corrections are needed, with the repair plan.", n)
        if rec.officer_items:
            count = len(rec.officer_items)
            if already_unread("OFFICER_NEEDED"):
                logged("ESCALATE_TO_OFFICERS", f"{count} uncertain item(s) are already flagged to officers.", 0)
            else:
                n = len(emit(conn, to_role="OFFICER", kind="OFFICER_NEEDED", title="An item needs officer review",
                             body=rec.officer_items[0]["text"][:200], link=link, application_id=application_id))
                logged("ESCALATE_TO_OFFICERS", f"Escalated {count} uncertain item(s) with their evidence." if n else
                       f"Flagged {count} uncertain item(s) for officers; they are notified once the application is submitted.", n)
    if prev is not None and not changed and prev["run_id"] == rec.run_id:
        return  # nothing new to record for this run
    conn.execute(
        "INSERT INTO routing_recommendations (id, application_id, run_id, outcome, reasons_json, actions_json, ai_used,"
        " policy_version, state_key, queue_flag, computed_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (new_id("rte"), application_id, rec.run_id, rec.outcome, dumps(rec.reasons), dumps(actions), int(rec.ai_used),
         POLICY_VERSION, rec.state_key if settled else rec.state_key + ":pending", rec.queue_flag, now_iso()))


def current(conn: sqlite3.Connection, application_id: str) -> dict[str, Any]:
    """The recommendation for the application's present state (computed live; stored rows are the history)."""
    rec = compute(conn, application_id)
    stored = conn.execute("SELECT * FROM routing_recommendations WHERE application_id=? ORDER BY computed_at DESC, rowid DESC"
                          " LIMIT 1", (application_id,)).fetchone()
    same = stored is not None and stored["state_key"] == rec.state_key
    return {"outcome": rec.outcome, "reasons": rec.reasons,
            "automated_actions": loads(stored["actions_json"], []) if same else [],
            "run_id": rec.run_id, "computed_at": stored["computed_at"] if same else now_iso(),
            "ai_used": rec.ai_used, "policy_version": POLICY_VERSION}
