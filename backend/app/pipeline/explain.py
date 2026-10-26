"""Plain-language wording of findings. The template explanation stays the default.

When AI is on, ``explain()`` may reword a *rule* finding from its structured proof only (rule title, the values with
their pages, the comparison, source statuses and the remedy; never document text). The wording is used only if it
passes validation: every number, date, identifier and rule ID must appear in the input, no decision vocabulary, one
to three sentences. Otherwise the template is kept. Integrity and duplicate findings are never reworded: their
wording is deliberately cautious and the duplicate proof contains another institution's evidence.
"""
from __future__ import annotations

import hashlib
import logging
import re
import sqlite3
import time
from typing import Any, Callable

from ..ai import policy, store
from ..ai.client import AIClient, kill_switch_engaged, outside_write_lock
from ..ai.config import AIConfig, get_config
from ..ai.types import ExplainRequest
from ..db import dumps, loads, now_iso
from ..storage import LocalStorage
from . import extract
from .doctypes import DOC_TYPES, FIELD_LABELS, IMAGE_DOC_TYPES
from .findings import ACTIVE_STATES

log = logging.getLogger("pramaan.ai")

MAX_CHARS = 600
MAX_CALLS_PER_STEP = 12        # findings beyond this are worded on the next run; the job is never held up by them
STEP_SECONDS = 60.0           # time budget for all wording requests in one step
FORBIDDEN = re.compile(r"\b(approv(?:e|es|ed|ing)|reject\w*|forg(?:e|ed|er|ery|ing)|fake\w*|fraud\w*|guarantee\w*)\b",
                       re.IGNORECASE)
NUMBER_WORDS = frozenset("""two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen
seventeen eighteen nineteen twenty thirty forty fifty sixty seventy eighty ninety hundred thousand lakh crore million
""".split())
MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                      "september", "october", "november", "december"], 1)}
_TOKEN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._/\-]*[A-Za-z0-9])?")
_RULE_ID = re.compile(r"^[A-Z][A-Z0-9_]*(?:\.[A-Z0-9_]+)+$")
_DATE = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$|^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})$")
_KEEP = ("conflict", "valid_to", "must_be_on_or_after", "status", "expr", "verification_status", "missing", "params")


# ----------------------------------------------------------------------------------------- the facts
def _source_label(source: str) -> str:
    return "AICTE records" if source.startswith("record:") else DOC_TYPES.get(source, source)


def facts_for(f: dict[str, Any]) -> dict[str, Any] | None:
    """Structured proof of a rule finding, or None when the finding is not eligible for AI wording."""
    if f["source_kind"] != "RULE" or f["state"] not in ACTIVE_STATES:
        return None
    proof = loads(f["proof_json"], {})
    rule = proof.get("rule") or {}
    facts: dict[str, Any] = {
        "rule_id": rule.get("id"), "rule_title": rule.get("title"), "severity": f["severity"],
        "outcome": proof.get("outcome"), "reason": proof.get("reason"), "remedy": f["remedy"],
        "template_explanation": f["explanation"],
        "values": [{"document": DOC_TYPES.get(e.get("doc_type") or "", e.get("doc_type")),
                    "field": FIELD_LABELS.get(e.get("field") or "", e.get("field")), "value": e.get("value"),
                    "page": e.get("page")}
                   for e in loads(f["evidence_json"], []) if e.get("field")],
    }
    for key in _KEEP:
        if key in proof:
            facts[key] = proof[key]
    if "conflict" in proof:
        facts["conflict"] = {value: [_source_label(s) for s in sources] for value, sources in proof["conflict"].items()}
    if "inputs" in proof:
        facts["inputs"] = {name: item.get("value") for name, item in proof["inputs"].items()}
    if "observed" in proof:
        facts["observed"] = [{"source": _source_label(o["source"]), "value": o["value"]} for o in proof["observed"]]
    return facts


def input_hash(facts: dict[str, Any]) -> str:
    return hashlib.sha256(dumps(facts).encode()).hexdigest()


# ---------------------------------------------------------------------------------------- validation
def _check_tokens(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text) if any(c.isdigit() for c in t) or _RULE_ID.match(t)]


def _allowed(facts_text: str) -> tuple[set[str], set[int]]:
    allowed: set[str] = set()
    months: set[int] = set()
    for token in _TOKEN.findall(facts_text):
        low = token.lower()
        allowed.add(low)
        m = _DATE.match(token)
        if m:
            y, mo, d = (m.group(1), m.group(2), m.group(3)) if m.group(1) else (m.group(6), m.group(5), m.group(4))
            months.add(int(mo))
            allowed |= {y, mo, mo.lstrip("0"), d, d.lstrip("0")}
            # the same date written in another common format is not a new fact
            mo2, d2 = mo.zfill(2), d.zfill(2)
            allowed |= {f"{y}-{mo2}-{d2}", f"{d2}-{mo2}-{y}", f"{d2}/{mo2}/{y}", f"{d2}.{mo2}.{y}"}
        elif re.fullmatch(r"\d{4}-\d{2}", token):  # academic year such as 2026-27
            allowed |= {token[:4], token[5:]}
        elif "-" in token and any(c.isdigit() for c in token):
            allowed |= {p.lower() for p in token.split("-") if p}
    return allowed, months


def validate(text: str, facts: dict[str, Any]) -> tuple[bool, str]:
    """(ok, reason). Nothing in the wording may go beyond what the structured proof says."""
    t = (text or "").strip()
    if not t or len(t) > MAX_CHARS:
        return False, "length"
    sentences = [s for s in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"“(])", t) if s.strip()]
    if not 1 <= len(sentences) <= 3:
        return False, "sentences"
    if FORBIDDEN.search(t):
        return False, "forbidden_word"
    if re.search(r"https?://|www\.|@|[`<>{}]", t):
        return False, "markup_or_link"
    facts_text = dumps(facts)
    allowed, months = _allowed(facts_text)
    facts_words = {w.lower() for w in re.findall(r"[A-Za-z]+", facts_text)}
    for word in re.findall(r"[A-Za-z]+", t):
        low = word.lower()
        if low in NUMBER_WORDS and low not in facts_words:
            return False, "number_word"
        if low in MONTHS and MONTHS[low] not in months:
            return False, "month_not_in_input"
    for token in _check_tokens(t):
        if token.lower() not in allowed:
            return False, "new_fact"
    return True, "ok"


# ------------------------------------------------------------------------------------------- policy
def _application_synthetic(conn: sqlite3.Connection, cfg: AIConfig, application_id: str) -> bool | None:
    """True when every PDF in the application carries the SYNTHETIC stamp; None while documents are still processing.

    Even a rule title such as "Fire safety NOC missing" is information about the application, so wording is requested
    only for applications made entirely of stamped documents (photographs carry no text and contribute no facts).
    """
    if cfg.data_policy == "allow_real":
        return True
    docs = conn.execute("SELECT * FROM documents WHERE application_id=? AND superseded_by IS NULL", (application_id,)).fetchall()
    if any(d["processing_state"] in ("QUEUED", "PROCESSING") for d in docs):
        return None
    from ..ai import ground
    for doc in docs:
        if doc["doc_type"] in IMAGE_DOC_TYPES:
            continue
        if doc["processing_state"] != "DONE":
            return False
        state = store.document_state(conn, doc["id"])
        if state is None or state["synthetic"] is None:
            data = LocalStorage().get(doc["sha256"])
            with outside_write_lock(conn):
                result = extract.extract_pdf(data)
            sent = min(doc["pages"], cfg.max_pages)
            texts = ground.page_texts(result)
            ocr = {line.page for line in result.lines if line.source == "ocr"}
            ok = policy.stamp_status({n: texts.get(n, "") for n in range(1, sent + 1)}, ocr)
            store.set_synthetic(conn, doc["id"], ok)
            state = {"synthetic": ok}
        if not state["synthetic"]:
            return False
    return True


# ---------------------------------------------------------------------------------------------- step
def explain_step(conn: sqlite3.Connection, job_id: str, app: dict[str, Any], stage: Callable[..., None]) -> None:
    cfg = get_config()
    if not cfg.enabled:
        return
    try:
        _explain_all(conn, cfg, job_id, app["id"])
    except Exception as exc:  # noqa: BLE001 — templates remain in place
        from .orchestrator import JobTimeout
        if isinstance(exc, JobTimeout):
            raise
        log.warning("ai_explain failed type=%s", type(exc).__name__)
        store.add_job_note(conn, job_id, "AI step skipped: error")


def _explain_all(conn: sqlite3.Connection, cfg: AIConfig, job_id: str, application_id: str) -> None:
    from .orchestrator import _check_deadline
    if kill_switch_engaged(conn):
        return
    synthetic = _application_synthetic(conn, cfg, application_id)
    if synthetic is None:
        return  # another document is still processing; the last job of the batch will do this
    if not synthetic:
        store.add_job_note(conn, job_id, "AI step skipped: data_policy")
        return
    client = AIClient(conn, cfg, unlock=outside_write_lock)
    accepted = rejected = calls = 0
    started = time.monotonic()
    for row in conn.execute(f"SELECT * FROM findings WHERE application_id=? AND source_kind='RULE' AND state IN "
                            f"({','.join('?' * len(ACTIVE_STATES))}) ORDER BY created_at", (application_id, *ACTIVE_STATES)).fetchall():
        finding = dict(row)
        facts = facts_for(finding)
        if facts is None:
            continue
        digest = input_hash(facts)
        known = conn.execute("SELECT input_hash FROM finding_ai_text WHERE finding_id=?", (finding["id"],)).fetchone()
        if known and known["input_hash"] == digest:
            continue
        if calls >= MAX_CALLS_PER_STEP or time.monotonic() - started > STEP_SECONDS:
            break
        _check_deadline()
        calls += 1
        outcome = client.explain(ExplainRequest(facts), digest)
        if outcome.result is None:
            store.add_job_note(conn, job_id, f"AI step skipped: {outcome.skipped or 'unavailable'}")
            break
        ok, why = validate(outcome.result.text, facts)
        with store.savepoint(conn, "ai_explain_one"):
            conn.execute(
                "INSERT INTO finding_ai_text (finding_id, input_hash, status, language, text, model, reject_reason, created_at)"
                " VALUES (?,?,?,'en',?,?,?,?) ON CONFLICT(finding_id) DO UPDATE SET input_hash=excluded.input_hash,"
                " status=excluded.status, text=excluded.text, model=excluded.model, reject_reason=excluded.reject_reason,"
                " created_at=excluded.created_at",
                (finding["id"], digest, "accepted" if ok else "rejected", outcome.result.text.strip() if ok else None,
                 outcome.model, None if ok else why, now_iso()))
        accepted += ok
        rejected += not ok
    if accepted or rejected:
        store.audit_system(conn, "ai.explanations", "application", application_id,
                           {"accepted": accepted, "rejected": rejected}, application_id)


def apply_stored(conn: sqlite3.Connection, finding: sqlite3.Row | dict[str, Any], out: dict[str, Any]) -> dict[str, Any]:
    """Use a validated AI wording when one exists for exactly this proof; otherwise the template stays."""
    template = {"explanation_source": "template", "ai_assisted": False, **out}
    if not get_config().enabled or kill_switch_engaged(conn):
        return template
    f = dict(finding)
    row = conn.execute("SELECT * FROM finding_ai_text WHERE finding_id=? AND status='accepted'", (f["id"],)).fetchone()
    if row is None:
        return template
    facts = facts_for(f)
    if facts is None or input_hash(facts) != row["input_hash"]:
        return template
    return {**out, "explanation": row["text"], "explanation_source": "ai_checked", "ai_assisted": True}
