"""Turn rule results, integrity indicators and duplicate matches into advisory findings."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from .doctypes import DOC_TYPES, FIELD_LABELS
from .rules_engine import Rule, RuleResult

# States that still need attention (count towards the derived application status).
ACTIVE_STATES = ("OPEN", "CONFIRMED", "ESCALATED", "CLARIFICATION_REQUESTED")

_NE_REMEDY = {
    "low_confidence": "The value could not be read reliably. Ask for a clearer copy or confirm it manually.",
    "missing_field": "The expected field was not found on the document. Check that the right document was uploaded.",
    "record_unavailable": "The AICTE record needed for this check is unavailable. Check the record manually.",
    "verification_inconclusive": None,  # use the rule's own remedy
    "evaluation_error": "The rule could not be evaluated on the extracted values. Check them manually.",
}


@dataclass
class FindingDraft:
    fingerprint: str
    source_kind: str
    rule_id: str | None
    title: str
    severity: str
    explanation: str
    remedy: str
    fix_doc_type: str | None
    action_owner: str
    proof: dict[str, Any]
    evidence: list[dict[str, Any]] = field(default_factory=list)
    scope_doc_types: set[str] = field(default_factory=set)


def _fmt(v: Any) -> str:
    if isinstance(v, date):
        return v.strftime("%d-%m-%Y")
    return str(v)


def _explain(rule: Rule, res: RuleResult) -> str:
    p = res.proof
    if rule.type == "require_document":
        return f"No {DOC_TYPES.get(rule.doc_type or '', rule.doc_type)} was found in this application."
    if rule.type == "consistency":
        def src(s: str) -> str:
            return "AICTE records" if s.startswith("record:") else DOC_TYPES.get(s, s)
        parts = [f"{val} in {', '.join(src(s) for s in srcs)}" for val, srcs in p.get("conflict", {}).items()]
        what = FIELD_LABELS.get(rule.field or "", rule.field or "value")
        return f"The {what} differs: " + "; ".join(parts) + "."
    if rule.type == "expiry":
        return (f"Valid up to {_fmt(date.fromisoformat(p['valid_to']))}, which is before "
                f"{_fmt(date.fromisoformat(p['must_be_on_or_after']))} (start of the academic year).")
    if rule.type == "assert":
        vals = ", ".join(f"{k} = {v['value']}" for k, v in p.get("inputs", {}).items())
        params = ", ".join(f"{k} = {v}" for k, v in (p.get("params") or {}).items())
        return f"Condition `{rule.expr}` is false with {vals}" + (f" ({params})" if params else "") + "."
    if rule.type == "verification":
        return "The issuing source reports values that differ from the uploaded document."
    return rule.title


def from_rule(rule: Rule, res: RuleResult) -> FindingDraft | None:
    if res.outcome in ("PASS", "NOT_APPLICABLE"):
        return None
    if res.outcome == "NOT_EVALUABLE":
        if res.reason == "missing_document":
            return None  # the completeness rule already reports the missing document
        remedy = _NE_REMEDY.get(res.reason or "") or rule.remedy
        missing = res.proof.get("missing", {})
        what = missing.get("input", "")
        explanation = {
            "low_confidence": f"Input '{what}' was extracted with low confidence, so the rule abstained.",
            "missing_field": f"Input '{what}' could not be found on the document, so the rule abstained.",
            "verification_inconclusive": "No automated source could confirm this document "
                                         f"(status: {res.proof.get('verification_status')}). Manual confirmation needed.",
            "record_unavailable": "The AICTE record needed for this rule is unavailable, so the rule abstained.",
        }.get(res.reason or "", "The rule could not be evaluated, so it abstained.")
        return FindingDraft(
            fingerprint=f"RULE:{rule.id}", source_kind="RULE", rule_id=rule.id,
            title=f"Manual check needed — {rule.title}", severity="REVIEW", explanation=explanation, remedy=remedy,
            fix_doc_type=rule.fix_doc_type, action_owner="OFFICER",
            proof={**res.proof, "outcome": res.outcome, "reason": res.reason}, evidence=res.evidence,
            scope_doc_types=rule.reads(),
        )
    fix_doc_type = rule.fix_doc_type
    if rule.type == "consistency" and fix_doc_type is None:
        fix_doc_type = _suspect_source(res.proof.get("conflict", {}), (res.proof.get("tiebreak") or {}).get("value"))
    return FindingDraft(
        fingerprint=f"RULE:{rule.id}", source_kind="RULE", rule_id=rule.id, title=rule.title, severity=rule.severity,
        explanation=_explain(rule, res), remedy=rule.remedy, fix_doc_type=fix_doc_type,
        action_owner=rule.action_owner, proof={**res.proof, "outcome": res.outcome, "reason": res.reason},
        evidence=res.evidence, scope_doc_types=rule.reads(),
    )


def _suspect_source(conflict: dict[str, list[str]], tiebreak: str | None = None) -> str | None:
    """The document most likely to be wrong: the one disagreeing with AICTE records (in the conflict or
    as the rule's tie-break source), else a strict minority. Returns None when nothing singles one out
    (the planner then links by shared field)."""
    record_value = next((v for v, srcs in conflict.items() if any(s.startswith("record:") for s in srcs)), None)
    if record_value is None and tiebreak in conflict:
        record_value = tiebreak
    if record_value is not None:
        suspects = [s for v, srcs in conflict.items() if v != record_value for s in srcs if not s.startswith("record:")]
    else:
        sizes = sorted(((len(srcs), v) for v, srcs in conflict.items()), reverse=True)
        if len(sizes) < 2 or sizes[0][0] == sizes[1][0]:
            return None
        suspects = [s for v, srcs in conflict.items() if v != sizes[0][1] for s in srcs]
    return suspects[0] if len(suspects) == 1 else None


def from_integrity(signal: dict[str, Any], doc: dict[str, Any]) -> FindingDraft:
    detail = signal["detail"]
    field_name = detail.get("field", "")
    evidence = [{"document_id": doc["id"], "doc_type": doc["doc_type"], "document_name": doc["original_name"],
                 "page": signal.get("page"), "bbox": signal.get("bbox"), "page_size": signal.get("page_size")}]
    return FindingDraft(
        fingerprint=f"INTEGRITY:{signal['kind']}:{doc['doc_type']}:{field_name}", source_kind="INTEGRITY", rule_id=None,
        title=f"Integrity indicator — {signal['title']}", severity="REVIEW",
        explanation=f"{signal['title']} in {DOC_TYPES.get(doc['doc_type'], doc['doc_type'])}. "
                    "This is an indicator that requires verification, not a finding of forgery.",
        remedy="Compare with the issuer's copy or an authenticated source before any adverse action.",
        fix_doc_type=doc["doc_type"], action_owner="OFFICER",
        proof={"indicator": signal["kind"], "detail": detail, "document_id": doc["id"],
               "wording": "indicator requiring verification"},
        evidence=evidence, scope_doc_types={doc["doc_type"]},
    )


def from_duplicate(doc: dict[str, Any], match: dict[str, Any], method: str, distance: int | None) -> FindingDraft:
    return FindingDraft(
        fingerprint=f"DUPLICATE:{doc['doc_type']}:{match['id']}", source_kind="DUPLICATE", rule_id=None,
        title="Possible reuse of evidence from another application", severity="REVIEW",
        explanation=("This file matches evidence submitted in another institution's application "
                     f"({'identical file' if method == 'sha256' else f'perceptual match, distance {distance}/64'}). "
                     "Shared facilities or templates can explain this; it needs review, not a conclusion."),
        remedy="Ask the institution for original, dated evidence or schedule an inspection.",
        fix_doc_type=doc["doc_type"], action_owner="OFFICER",
        proof={"method": method, "hamming_distance": distance, "document_id": doc["id"],
               "matched_document_id": match["id"], "matched_application_id": match["application_id"],
               "matched_institution_id": match["institution_id"]},
        evidence=[{"document_id": doc["id"], "doc_type": doc["doc_type"], "document_name": doc["original_name"]},
                  {"document_id": match["id"], "doc_type": match["doc_type"], "document_name": match["original_name"],
                   "other_application": True}],
        scope_doc_types={doc["doc_type"]},
    )


def derive_status(active_severities: list[str]) -> str:
    if "DEFICIENCY" in active_severities:
        return "DEFICIENCIES_FLAGGED"
    if "REVIEW" in active_severities:
        return "MANUAL_REVIEW_REQUIRED"
    return "READY_FOR_SCRUTINY"
