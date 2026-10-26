"""AI-assisted extraction, grounded in the page (step ``after_fields``), and the document-type check.

What it may change: it can add or replace a *claim*, but only for a value it finds printed on the page as that
field, with the real bounding box, extractor ``ai+text`` / ``ai+ocr`` and the match score as confidence. Everything
else becomes a visible suggestion that no rule reads. A deterministic claim with confidence >= 0.95 is never
overwritten. Any failure leaves the deterministic result intact and adds an INFO note to the job.

The step is handed a connection inside the pipeline's write transaction. Slow work (re-reading scanned pages, the
provider round-trips) runs with that write lock released, and everything it writes afterwards is one savepoint.
"""
from __future__ import annotations

import io
import logging
import sqlite3
from typing import Any, Callable

import pdfplumber
from pypdf import PdfReader, PdfWriter

from .. import audit
from ..ai import ground, policy, store
from ..ai.client import AIClient, kill_switch_engaged, outside_write_lock
from ..ai.config import AIConfig, get_config
from ..ai.types import AIError, ClassifyRequest, ExtractRequest, FieldInfo
from ..db import dumps, loads, new_id, now_iso
from ..rulepacks import active_version
from ..storage import LocalStorage
from . import extract
from .doctypes import DOC_TYPES, FIELD_LABELS, IMAGE_DOC_TYPES, TEMPLATES
from .findings import from_integrity
from .rules_engine import RulePack

log = logging.getLogger("pramaan.ai")

CONFIDENT_CLAIM = 0.95          # a deterministic claim at or above this is never overwritten
CLASSIFY_CONFIDENCE = 0.80      # a mismatch needs a confident, quoted model answer
TYPE_MISMATCH_KIND = "AI_TYPE_MISMATCH"
_STATE_AFTER_REVIEW = {"CONFIRM": "CONFIRMED", "DISMISS": "DISMISSED", "ESCALATE": "ESCALATED",
                       "REQUEST_CLARIFICATION": "CLARIFICATION_REQUESTED"}


# ------------------------------------------------------------------------------------ what the rules read
def rule_fields(pack: RulePack, doc_type: str) -> list[FieldInfo]:
    """Fields of ``doc_type`` that some rule reads, in template order, with their value types."""
    wanted: set[str] = set()
    for rule in pack.rules:
        if rule.type == "assert":
            for ref in (rule.inputs or {}).values():
                scope, _, name = ref.partition(".")
                if scope == doc_type:
                    wanted.add(name)
        elif rule.type == "consistency" and doc_type in (rule.sources or []) and rule.field:
            wanted.add(rule.field)
        elif rule.type == "expiry" and rule.field:
            scope, _, name = rule.field.partition(".")
            if scope == doc_type:
                wanted.add(name)
    return [FieldInfo(spec.field, FIELD_LABELS.get(spec.field, spec.field), spec.value_type)
            for spec in TEMPLATES.get(doc_type, []) if spec.field in wanted]


def read_fields_by_type(pack: RulePack) -> dict[str, set[str]]:
    return {t: {f.name for f in rule_fields(pack, t)} for t in TEMPLATES}


# ------------------------------------------------------------------------------------------ small helpers
def _text_layers(data: bytes) -> tuple[list[bool], list[str]]:
    """Per page: does it have a text layer, and what does it say? (No OCR: this is the cheap first look.)"""
    layers, texts = [], []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            layers.append(sum(len(w["text"]) for w in page.extract_words()) >= extract.MIN_TEXT_CHARS)
            texts.append(page.extract_text() or "")
    return layers, texts


def _first_pages(data: bytes, count: int) -> bytes:
    reader = PdfReader(io.BytesIO(data))
    if len(reader.pages) <= count:
        return data
    writer = PdfWriter()
    for page in reader.pages[:count]:
        writer.add_page(page)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def _skip(conn: sqlite3.Connection, job_id: str, doc: dict[str, Any], reason: str, synthetic: bool | None = None) -> None:
    store.set_document_state(conn, doc["id"], "SKIPPED", reason=reason, synthetic=synthetic)
    store.add_job_note(conn, job_id, f"AI step skipped: {reason}")
    store.audit_system(conn, "ai.step_skipped", "document", doc["id"], {"reason": reason}, doc["application_id"])
    log.info("ai_step skipped reason=%s", reason)


# ---------------------------------------------------------------------------------------------- the step
def ai_extract_step(conn: sqlite3.Connection, job_id: str, doc: dict[str, Any], stage: Callable[[str, str, int], None]) -> None:
    cfg = get_config()
    if not cfg.enabled or doc["doc_type"] in IMAGE_DOC_TYPES:
        return
    try:
        _run(conn, cfg, job_id, doc, stage)
    except Exception as exc:  # noqa: BLE001 — the deterministic result must survive any AI failure
        from .orchestrator import JobTimeout
        if isinstance(exc, JobTimeout):
            raise
        code = exc.code if isinstance(exc, AIError) else "error"
        log.warning("ai_step failed code=%s type=%s", code, type(exc).__name__)
        _skip(conn, job_id, doc, code)


def _run(conn: sqlite3.Connection, cfg: AIConfig, job_id: str, doc: dict[str, Any], stage: Callable[[str, str, int], None]) -> None:
    _, pack = active_version(conn)
    fields = rule_fields(pack, doc["doc_type"])
    claims = {r["field"]: dict(r) for r in conn.execute("SELECT * FROM claims WHERE document_id=?", (doc["id"],))}
    data = LocalStorage().get(doc["sha256"])
    sent = min(doc["pages"], cfg.max_pages)

    layers, layer_texts = _text_layers(data)
    ocr_path = not all(layers)
    targets = {f.name for f in fields if f.name not in claims or claims[f.name]["value_norm"] is None
               or claims[f.name]["confidence"] < cfg.trigger_confidence}
    if ocr_path:
        targets = {f.name for f in fields}
    classification_uncertain = (not ocr_path) and extract.classify("\n".join(layer_texts))[0] != doc["doc_type"]
    if not targets and not classification_uncertain:
        # Nothing needs the model. Remember whether the pages carry the stamp (so wording can be requested later
        # without re-reading the file) and drop suggestions left over from an earlier run.
        stamped = policy.stamp_status({n: t for n, t in enumerate(layer_texts[:sent], 1)})
        store.set_document_state(conn, doc["id"], "NOT_NEEDED", synthetic=stamped)
        store.replace_suggestions(conn, doc["id"], doc["application_id"], [])
        return

    stage("AI_EXTRACTION", "AI-assisted extraction", 47)
    if kill_switch_engaged(conn):
        return _skip(conn, job_id, doc, "kill_switch")

    with outside_write_lock(conn):  # re-reading scanned pages (OCR) is slow and needs no database
        result = extract.extract_pdf(data)
    classification_uncertain = classification_uncertain or (ocr_path and result.detected_type != doc["doc_type"])
    pages = ground.pages_from(result)
    texts = {n: t for n, t in ground.page_texts(result).items() if n <= sent}
    ocr_pages = {n for n, p in pages.items() if p.source == "ocr"}
    sent_texts = {n: texts.get(n, "") for n in range(1, sent + 1)}
    stamped = policy.stamp_status(sent_texts, ocr_pages)           # the truth about the file, whatever the policy allows
    decision = policy.decide(cfg, sent_texts, ocr_pages)
    if not decision.allowed:
        return _skip(conn, job_id, doc, decision.reason or "data_policy", synthetic=stamped)

    pdf_bytes = _first_pages(data, sent)
    client = AIClient(conn, cfg, unlock=outside_write_lock)
    proposals = None
    extract_outcome = classify_outcome = None
    if targets:
        request = ExtractRequest(doc["doc_type"], DOC_TYPES[doc["doc_type"]], fields, pdf_bytes, list(range(1, sent + 1)), texts)
        extract_outcome = client.extract(request, doc["sha256"], sent)
        if extract_outcome.result is None:
            return _skip(conn, job_id, doc, extract_outcome.skipped or "unavailable", synthetic=stamped)
        proposals = extract_outcome.result.fields
    if classification_uncertain:
        request_c = ClassifyRequest(doc["doc_type"], dict(DOC_TYPES), pdf_bytes, list(range(1, sent + 1)), texts)
        classify_outcome = client.classify(request_c, doc["sha256"], sent)
        if classify_outcome.result is None and not targets:
            return _skip(conn, job_id, doc, classify_outcome.skipped or "unavailable", synthetic=stamped)

    outcomes = [o for o in (extract_outcome, classify_outcome) if o is not None and o.result is not None]
    provider, model = outcomes[0].provider, outcomes[0].model
    with store.savepoint(conn, "ai_apply"):
        created = replaced = suggested = 0
        classification = None
        if proposals is not None:
            created, replaced, suggested = _integrate(conn, doc, fields, targets, proposals, pages, claims, extract_outcome.model,
                                                      cfg.trigger_confidence)
        if classify_outcome is not None and classify_outcome.result is not None:
            classification = _classification(doc, classify_outcome.result, pages, classify_outcome.model)
        store.set_document_state(conn, doc["id"], "RAN", synthetic=stamped, provider=provider, model=model,
                                 cache_hit=all(o.cache_hit for o in outcomes), classification=classification)
        store.audit_system(conn, "ai.extraction", "document", doc["id"],
                           {"provider": provider, "model": model, "cache_hit": all(o.cache_hit for o in outcomes),
                            "claims_created": created, "claims_replaced": replaced, "suggestions": suggested,
                            "ocr_path": ocr_path, "classified": classification is not None}, doc["application_id"])


# ------------------------------------------------------------------------------------------- integration
def _integrate(conn: sqlite3.Connection, doc: dict[str, Any], fields: list[FieldInfo], targets: set[str],
               proposals: dict[str, Any], pages: dict[int, ground.PageData], claims: dict[str, dict[str, Any]],
               model: str, trigger_confidence: float = 0.80) -> tuple[int, int, int]:
    created = replaced = 0
    suggestions: list[dict[str, Any]] = []

    def suggest(info: FieldInfo, proposal: Any, reason: str) -> None:
        suggestions.append({"field": info.name, "value": proposal.value.strip(), "page": proposal.page,
                            "quote": proposal.quote, "reason": reason, "model": model})

    for info in fields:
        proposal = proposals.get(info.name)
        if info.name not in targets or proposal is None or not (proposal.value or "").strip():
            continue
        existing = claims.get(info.name)
        wanted = ground.canon(proposal.value, info.value_type)
        if existing and existing["confidence"] >= CONFIDENT_CLAIM:
            # The claim stands. A disagreement is worth showing only if it is a plausible value of that field;
            # free text from a model (or from an injected sentence) is not put in front of people.
            if wanted is not None and wanted != existing["value_norm"]:
                suggest(info, proposal, "conflicts_with_page")
            continue
        grounding = ground.ground(info.name, info.value_type, proposal.value, proposal.page, proposal.quote, pages)
        claim = grounding.claim
        if claim is None:
            suggest(info, proposal, grounding.reason or "not_found_on_page")
            continue
        if existing and existing["value_norm"] is not None:
            if existing["value_norm"] != claim.value_norm:
                if existing["confidence"] >= trigger_confidence:
                    suggest(info, proposal, "conflicts_with_page")
                    continue
            elif existing["confidence"] >= claim.confidence:
                continue  # same value, nothing to improve
        if existing:
            conn.execute("DELETE FROM claims WHERE document_id=? AND field=?", (doc["id"], info.name))
            replaced += 1
        else:
            created += 1
        conn.execute(
            "INSERT INTO claims (id,document_id,application_id,field,value_raw,value_norm,value_type,page,x0,y0,x1,y1,"
            "page_width,page_height,extractor,confidence) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (new_id("clm"), doc["id"], doc["application_id"], claim.field, claim.value_raw, claim.value_norm,
             claim.value_type, claim.page, *claim.bbox, claim.page_width, claim.page_height, claim.extractor,
             claim.confidence))
    store.replace_suggestions(conn, doc["id"], doc["application_id"], suggestions)
    return created, replaced, len(suggestions)


def _classification(doc: dict[str, Any], result: Any, pages: dict[int, ground.PageData], model: str) -> dict[str, Any]:
    quote = result.evidence_quote
    located = any(ground._quote_span(p, quote) for p in pages.values()) if quote else False
    ai_type = result.document_type
    mismatch = bool(ai_type and ai_type != doc["doc_type"] and result.confidence >= CLASSIFY_CONFIDENCE and located)
    return {"expected": doc["doc_type"], "ai_type": ai_type, "confidence": round(result.confidence, 3),
            "quote": store.clean_text(quote, 300) if located else None, "quote_found": located, "mismatch": mismatch,
            "model": model}


# ---------------------------------------------------------------- document-type finding (after_rules)
def classification_sync_step(conn: sqlite3.Connection, job_id: str, app: dict[str, Any], stage: Callable[..., None]) -> None:
    """Keep one REVIEW finding per confident, quoted AI type mismatch. Never a deficiency on its own."""
    if not get_config().enabled:
        return
    try:
        with store.savepoint(conn, "ai_classification"):
            _sync_classification(conn, app["id"])
    except Exception as exc:  # noqa: BLE001
        log.warning("ai_classification_sync failed type=%s", type(exc).__name__)


def _sync_classification(conn: sqlite3.Connection, application_id: str) -> None:
    run = conn.execute("SELECT id FROM validation_runs WHERE application_id=? ORDER BY started_at DESC, rowid DESC LIMIT 1",
                       (application_id,)).fetchone()
    if run is None:
        return
    docs = [dict(r) for r in conn.execute(
        "SELECT d.*, a.classification_json FROM documents d JOIN ai_documents a ON a.document_id=d.id"
        " WHERE d.application_id=? AND d.superseded_by IS NULL AND d.processing_state='DONE'", (application_id,))]
    for doc in docs:
        info = loads(doc["classification_json"]) or {}
        if not info.get("mismatch"):
            continue
        expected = DOC_TYPES.get(doc["doc_type"], doc["doc_type"])
        seen = DOC_TYPES.get(info.get("ai_type") or "", "a different document")
        detail = {"field": "", "expected": doc["doc_type"], "ai_type": info.get("ai_type"), "confidence": info["confidence"],
                  "evidence_quote": info.get("quote"), "model": info.get("model"), "ai_assisted": True}
        if not conn.execute("SELECT 1 FROM integrity_signals WHERE document_id=? AND kind=?",
                            (doc["id"], TYPE_MISMATCH_KIND)).fetchone():
            conn.execute("INSERT INTO integrity_signals (id, document_id, kind, detail_json, page, bbox_json, created_at)"
                         " VALUES (?,?,?,?,NULL,NULL,?)",
                         (new_id("sig"), doc["id"], TYPE_MISMATCH_KIND,
                          dumps({"title": f"Uploaded file may not be a {expected}", **detail}), now_iso()))
        draft = from_integrity({"kind": TYPE_MISMATCH_KIND, "title": f"Uploaded file may not be a {expected}",
                                "detail": detail, "page": None, "bbox": None, "page_size": None}, doc)
        explanation = (f"The file uploaded as {expected} reads like {seen} (AI check, confidence "
                       f"{info['confidence']:.2f}): “{info.get('quote')}”. This is an indicator for the officer "
                       "to check, not a conclusion about the document.")
        row = conn.execute("SELECT id FROM findings WHERE application_id=? AND fingerprint=? AND state != 'RESOLVED'",
                           (application_id, draft.fingerprint)).fetchone()
        if row:
            conn.execute("UPDATE findings SET explanation=? WHERE id=?", (explanation, row["id"]))
            continue
        # Reprocessing a document clears its signals, so the validation run that just finished resolved the finding.
        # Bring that same finding back (in the state the officer had left it) instead of raising a second one.
        revived = conn.execute("SELECT id FROM findings WHERE application_id=? AND fingerprint=? AND state='RESOLVED'"
                               " AND resolved_by_run=? ORDER BY created_at DESC, rowid DESC LIMIT 1",
                               (application_id, draft.fingerprint, run["id"])).fetchone()
        if revived:
            last = conn.execute("SELECT decision FROM reviews WHERE finding_id=? ORDER BY created_at DESC, rowid DESC LIMIT 1",
                                (revived["id"],)).fetchone()
            conn.execute("UPDATE findings SET state=?, resolved_at=NULL, resolved_by_run=NULL, explanation=? WHERE id=?",
                         (_STATE_AFTER_REVIEW.get(last["decision"] if last else "", "OPEN"), explanation, revived["id"]))
            continue
        fid = new_id("fnd")
        conn.execute(
            "INSERT INTO findings (id, application_id, run_id, fingerprint, source_kind, rule_id, title, severity, state,"
            " explanation, remedy, fix_doc_type, action_owner, proof_json, evidence_json, advisory, created_at)"
            " VALUES (?,?,?,?,?,?,?,?, 'OPEN', ?,?,?,?,?,?, 1, ?)",
            (fid, application_id, run["id"], draft.fingerprint, draft.source_kind, None,
             draft.title.replace("Integrity indicator — ", ""), draft.severity, explanation, draft.remedy,
             draft.fix_doc_type, draft.action_owner, dumps(draft.proof), dumps(draft.evidence), now_iso()))
        audit.record(conn, None, "finding.raised", "finding", fid, {"source": "ai_classification"}, application_id)
        from ..notify import emit
        emit(conn, to_role="OFFICER", kind="OFFICER_NEEDED", title="An item needs officer review", body=draft.title,
             link=f"/applications/{application_id}", application_id=application_id, finding_id=fid)
