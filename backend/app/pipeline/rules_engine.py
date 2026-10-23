"""Rule packs as data, evaluated into proof-carrying results.

A rule's outcome is PASS, FAIL, NOT_EVALUABLE (an input is missing or unreliable — the engine
abstains instead of guessing) or NOT_APPLICABLE (category mismatch). Every result carries a proof:
the rule, its clause, every input with its provenance, and the evaluated values.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, model_validator

from . import safe_expr

LOW_CONFIDENCE = 0.6

RuleType = Literal["require_document", "assert", "consistency", "expiry", "verification"]


class Clause(BaseModel):
    ref: str
    status: Literal["TO_VERIFY", "SOURCE_SEEN", "VERIFIED"] = "TO_VERIFY"
    url: str | None = None


class Rule(BaseModel):
    id: str = Field(pattern=r"^[A-Z0-9_.]+$")
    title: str
    type: RuleType
    severity: Literal["DEFICIENCY", "REVIEW", "INFO"]
    clause: Clause
    remedy: str
    fix_doc_type: str | None = None
    action_owner: Literal["INSTITUTION", "OFFICER"] = "INSTITUTION"
    applies_to: list[str] | None = None
    doc_type: str | None = None
    field: str | None = None
    sources: list[str] | None = None
    inputs: dict[str, str] | None = None
    expr: str | None = None
    params: dict[str, float | int | str] = {}
    on_or_after: str | None = None
    tiebreak: str | None = None  # consistency only: authoritative source used to say which side is likely wrong

    @model_validator(mode="after")
    def _shape(self) -> "Rule":
        need = {
            "require_document": ["doc_type"], "verification": ["doc_type"], "consistency": ["field", "sources"],
            "assert": ["inputs", "expr"], "expiry": ["field", "on_or_after"],
        }[self.type]
        missing = [n for n in need if getattr(self, n) in (None, [], {})]
        if missing:
            raise ValueError(f"rule {self.id}: missing {missing}")
        if self.type == "assert":
            safe_expr.validate(self.expr or "", set(self.inputs or {}) | set(self.params))
        return self

    def reads(self) -> set[str]:
        """Document types this rule depends on — used for targeted re-validation."""
        if self.type in ("require_document", "verification"):
            return {self.doc_type or ""}
        if self.type == "consistency":
            return {s for s in self.sources or [] if ":" not in s}
        refs = list((self.inputs or {}).values()) if self.type == "assert" else [self.field or ""]
        return {r.split(".")[0] for r in refs if r.split(".")[0] not in ("record", "application", "ref")}


class ChecklistItem(BaseModel):
    doc_type: str
    required: bool
    note: str = ""


class RulePack(BaseModel):
    pack: str
    version: str
    title: str
    source: dict[str, str]
    reference_dates: dict[str, str]
    categories: dict[str, dict[str, str]]
    checklist: list[ChecklistItem]
    rules: list[Rule]

    @model_validator(mode="after")
    def _unique(self) -> "RulePack":
        ids = [r.id for r in self.rules]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate rule ids")
        return self

    @classmethod
    def from_yaml(cls, text: str) -> "RulePack":
        return cls.model_validate(yaml.safe_load(text))

    def rule(self, rule_id: str) -> Rule:
        return next(r for r in self.rules if r.id == rule_id)

    def ref(self, name: str) -> Any:
        raw = self.reference_dates[name]
        try:
            return date.fromisoformat(raw)
        except ValueError:
            return raw


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


@dataclass
class EvalContext:
    application: dict[str, Any]
    institution: dict[str, Any]
    record: dict[str, Any] | None
    docs_by_type: dict[str, dict[str, Any]]                # current (non-superseded) document per type
    claims_by_doc: dict[str, dict[str, dict[str, Any]]]    # doc_id -> field -> claim row
    verification_by_doc: dict[str, str | None]              # doc_id -> final ladder status


@dataclass
class RuleResult:
    rule_id: str
    outcome: str
    reason: str | None
    proof: dict[str, Any]
    evidence: list[dict[str, Any]] = field(default_factory=list)


class _Missing(Exception):
    def __init__(self, reason: str, ref: str):
        super().__init__(reason)
        self.reason, self.ref = reason, ref


def _typed(claim: dict[str, Any]) -> Any:
    v, t = claim["value_norm"], claim["value_type"]
    if t == "int":
        return int(v)
    if t == "date":
        return date.fromisoformat(v)
    return v


def _claim_evidence(claim: dict[str, Any], doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "claim_id": claim["id"], "document_id": doc["id"], "doc_type": doc["doc_type"], "document_name": doc["original_name"],
        "field": claim["field"], "value": claim["value_raw"], "normalized": claim["value_norm"], "page": claim["page"],
        "bbox": [claim["x0"], claim["y0"], claim["x1"], claim["y1"]],
        "page_size": [claim["page_width"], claim["page_height"]],
        "extractor": claim["extractor"], "confidence": claim["confidence"],
    }


class Evaluator:
    def __init__(self, pack: RulePack, ctx: EvalContext):
        self.pack, self.ctx = pack, ctx

    # ----- input resolution -----
    def resolve(self, ref: str) -> tuple[Any, dict[str, Any] | None]:
        scope, _, name = ref.partition(".") if "." in ref else ref.partition(":")
        if scope == "ref":
            return self.pack.ref(name), {"source": "rule_pack.reference_dates", "name": name, "value": self.pack.reference_dates[name]}
        if scope == "application":
            return self.ctx.application[name], {"source": "application", "field": name, "value": self.ctx.application[name]}
        if scope == "record":
            if name == "permanent_id":
                v = self.ctx.institution["aicte_permanent_id"]
            elif self.ctx.record is None:
                raise _Missing("record_unavailable", ref)
            else:
                v = self.ctx.record[name]
            return v, {"source": "aicte_records", "field": name, "value": v, "simulated": True}
        doc = self.ctx.docs_by_type.get(scope)
        if doc is None:
            raise _Missing("missing_document", scope)
        claim = self.ctx.claims_by_doc.get(doc["id"], {}).get(name)
        if claim is None or claim["value_norm"] is None:
            raise _Missing("missing_field", ref)
        if claim["confidence"] < LOW_CONFIDENCE:
            raise _Missing("low_confidence", ref)
        return _typed(claim), _claim_evidence(claim, doc)

    # ----- rule types -----
    def run(self, rule: Rule) -> RuleResult:
        base = {"rule": {"id": rule.id, "title": rule.title, "type": rule.type, "pack": self.pack.pack,
                         "version": self.pack.version, "clause": rule.clause.model_dump()}}
        category = self.ctx.application["category"]
        if rule.applies_to and category not in rule.applies_to:
            return RuleResult(rule.id, "NOT_APPLICABLE", None, {**base, "applies_to": rule.applies_to})
        try:
            return getattr(self, "_" + rule.type)(rule, base)
        except _Missing as m:
            return RuleResult(rule.id, "NOT_EVALUABLE", m.reason, {**base, "missing": {"reason": m.reason, "input": m.ref}})

    def _require_document(self, rule: Rule, base: dict[str, Any]) -> RuleResult:
        doc = self.ctx.docs_by_type.get(rule.doc_type or "")
        proof = {**base, "required_doc_type": rule.doc_type, "present_doc_types": sorted(self.ctx.docs_by_type)}
        if doc:
            return RuleResult(rule.id, "PASS", None, proof, [{"document_id": doc["id"], "doc_type": doc["doc_type"],
                                                              "document_name": doc["original_name"]}])
        return RuleResult(rule.id, "FAIL", "missing_document", proof)

    def _assert(self, rule: Rule, base: dict[str, Any]) -> RuleResult:
        values: dict[str, Any] = {}
        inputs: dict[str, Any] = {}
        evidence = []
        for var, ref in (rule.inputs or {}).items():
            v, prov = self.resolve(ref)
            values[var] = v
            inputs[var] = {"ref": ref, "value": v.isoformat() if isinstance(v, date) else v, "provenance": prov}
            if prov and "claim_id" in prov:
                evidence.append(prov)
        values.update(rule.params)
        try:
            ok = bool(safe_expr.evaluate(rule.expr or "", values))
        except (TypeError, ZeroDivisionError) as exc:
            return RuleResult(rule.id, "NOT_EVALUABLE", "evaluation_error",
                              {**base, "inputs": inputs, "expr": rule.expr, "error": str(exc)}, evidence)
        proof = {**base, "inputs": inputs, "params": rule.params, "expr": rule.expr, "result": ok}
        return RuleResult(rule.id, "PASS" if ok else "FAIL", None if ok else "assertion_false", proof, evidence)

    def _consistency(self, rule: Rule, base: dict[str, Any]) -> RuleResult:
        observed: list[dict[str, Any]] = []
        skipped: list[dict[str, str]] = []
        evidence = []
        for src in rule.sources or []:
            ref = src.replace(":", ".") if src.startswith("record:") else f"{src}.{rule.field}"
            try:
                v, prov = self.resolve(ref)
            except _Missing as m:
                skipped.append({"source": src, "reason": m.reason})
                continue
            observed.append({"source": src, "value": str(v).upper(), "provenance": prov})
            if prov and "claim_id" in prov:
                evidence.append(prov)
        proof = {**base, "field": rule.field, "observed": observed, "skipped": skipped}
        if len(observed) < 2:
            reasons = {s["reason"] for s in skipped}
            reason = "missing_document" if reasons <= {"missing_document"} else sorted(reasons - {"missing_document"})[0]
            return RuleResult(rule.id, "NOT_EVALUABLE", reason, proof, evidence)
        distinct = sorted({o["value"] for o in observed})
        if len(distinct) == 1:
            if any(s["reason"] in ("low_confidence", "missing_field") for s in skipped):
                proof["note"] = "Agreeing sources only; some sources could not be read reliably."
            return RuleResult(rule.id, "PASS", None, proof, evidence)
        groups = {d: [o["source"] for o in observed if o["value"] == d] for d in distinct}
        proof["conflict"] = groups
        if rule.tiebreak:
            try:
                tv, tprov = self.resolve(rule.tiebreak.replace(":", "."))
                proof["tiebreak"] = {"source": rule.tiebreak, "value": str(tv).upper(), "provenance": tprov}
            except _Missing:
                pass
        return RuleResult(rule.id, "FAIL", "values_disagree", proof, evidence)

    def _expiry(self, rule: Rule, base: dict[str, Any]) -> RuleResult:
        valid_to, prov = self.resolve(rule.field or "")
        limit, limit_prov = self.resolve(rule.on_or_after or "")
        ok = valid_to >= limit
        proof = {**base, "valid_to": valid_to.isoformat(), "must_be_on_or_after": limit.isoformat(),
                 "reference": limit_prov, "status": "VALID" if ok else "EXPIRED",
                 "note": "Uses the typed validity date; print or issue dates are not used for expiry."}
        return RuleResult(rule.id, "PASS" if ok else "FAIL", None if ok else "expired", proof, [prov] if prov else [])

    def _verification(self, rule: Rule, base: dict[str, Any]) -> RuleResult:
        doc = self.ctx.docs_by_type.get(rule.doc_type or "")
        if doc is None:
            return RuleResult(rule.id, "NOT_EVALUABLE", "missing_document", {**base})
        status = self.ctx.verification_by_doc.get(doc["id"])
        proof = {**base, "document_id": doc["id"], "verification_status": status}
        ev = [{"document_id": doc["id"], "doc_type": doc["doc_type"], "document_name": doc["original_name"]}]
        if status in ("VERIFIED", "EXPIRED"):
            return RuleResult(rule.id, "PASS", None, proof, ev)
        if status == "MISMATCH_DETECTED":
            return RuleResult(rule.id, "FAIL", "source_mismatch", proof, ev)
        return RuleResult(rule.id, "NOT_EVALUABLE", "verification_inconclusive", proof, ev)


def evaluate(pack: RulePack, ctx: EvalContext, only: set[str] | None = None) -> list[RuleResult]:
    ev = Evaluator(pack, ctx)
    return [ev.run(r) for r in pack.rules if only is None or r.id in only]


def rules_reading(pack: RulePack, doc_types: set[str]) -> set[str]:
    return {r.id for r in pack.rules if r.reads() & doc_types}
