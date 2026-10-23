"""Compliance Repair Planner — deterministic grouping and ordering of next steps.

1. Institution findings that name the document to fix are grouped by that document, so
   "replace the fire NOC" appears once even if three rules flagged it.
2. A conflict that does not single out one document (e.g. affidavit says 300, summary says 240) is
   linked to an existing group when that group already flags the *same field on the same document*
   — the likely shared root cause. Otherwise it becomes its own "resolve the conflict" action.
3. Officer actions (manual verification, integrity review, possible reuse) are listed separately.

The planner never invents evidence and never promises an outcome; it says which evidence would let
the affected rules pass. Ordering: deficiencies before review items, then actions that clear more
findings first.
"""
from __future__ import annotations

from typing import Any

from .doctypes import DOC_TYPES

_WEIGHT = {"DEFICIENCY": 3, "REVIEW": 1, "INFO": 0}
ACTIVE = ("OPEN", "CONFIRMED", "CLARIFICATION_REQUESTED", "ESCALATED")


def _rule_type(f: dict[str, Any]) -> str | None:
    rule = (f.get("proof") or {}).get("rule")
    return rule.get("type") if isinstance(rule, dict) else None


def _fields(f: dict[str, Any]) -> set[tuple[str, str]]:
    return {(e.get("doc_type"), e.get("field")) for e in f.get("evidence") or [] if e.get("field") and e.get("doc_type")}


def _verb(group: list[dict[str, Any]], label: str) -> str:
    types = {_rule_type(f) for f in group}
    if "require_document" in types:
        return f"Upload the {label}"
    if "expiry" in types:
        return f"Upload a renewed {label}"
    return f"Provide a corrected {label}"


def build_plan(findings: list[dict[str, Any]]) -> dict[str, Any]:
    import json
    active = []
    for f in findings:
        if f["state"] not in ACTIVE:
            continue
        f = dict(f)
        f.setdefault("proof", json.loads(f.get("proof_json") or "{}"))
        f.setdefault("evidence", json.loads(f.get("evidence_json") or "[]"))
        active.append(f)

    groups: dict[str, list[dict[str, Any]]] = {}
    linked: dict[str, list[str]] = {}
    unresolved: list[dict[str, Any]] = []
    officer_actions = []
    for f in active:
        if f["action_owner"] != "INSTITUTION":
            officer_actions.append({
                "id": f"OFF-{f['id']}", "owner": "OFFICER", "title": f["remedy"], "doc_type": f["fix_doc_type"],
                "details": [f["explanation"]], "resolves": [f["id"]], "finding_titles": [f["title"]],
                "priority": _WEIGHT[f["severity"]], "severity": f["severity"],
            })
        elif f["fix_doc_type"]:
            groups.setdefault(f["fix_doc_type"], []).append(f)
        else:
            unresolved.append(f)

    standalone = []
    for f in unresolved:
        target = None
        for doc_type, field in sorted(_fields(f)):
            group = groups.get(doc_type)
            if group and any((doc_type, field) in _fields(g) for g in group):
                target = doc_type
                break
        if target:
            groups[target].append(f)
            linked.setdefault(target, []).append(f["title"])
        else:
            standalone.append(f)

    institution_actions = []
    for doc_type, group in groups.items():
        label = DOC_TYPES.get(doc_type, doc_type)
        details = sorted({g["remedy"] for g in group})
        if doc_type in linked:
            details.append("Also likely to clear: " + "; ".join(linked[doc_type]) + " (same field on the same document).")
        institution_actions.append({
            "id": f"INST-{doc_type}", "owner": "INSTITUTION", "title": _verb(group, label), "doc_type": doc_type,
            "details": details, "resolves": [g["id"] for g in group], "finding_titles": [g["title"] for g in group],
            "priority": sum(_WEIGHT[g["severity"]] for g in group),
            "severity": "DEFICIENCY" if any(g["severity"] == "DEFICIENCY" for g in group) else "REVIEW",
        })
    for f in standalone:
        docs = sorted({DOC_TYPES.get(d, d) for d, _ in _fields(f)})
        institution_actions.append({
            "id": f"INST-{f['id']}", "owner": "INSTITUTION",
            "title": "Resolve the conflict between " + " and ".join(docs) if docs else f["remedy"], "doc_type": None,
            "details": [f["explanation"], f["remedy"]], "resolves": [f["id"]], "finding_titles": [f["title"]],
            "priority": _WEIGHT[f["severity"]], "severity": f["severity"],
        })
    institution_actions.sort(key=lambda a: (-(a["severity"] == "DEFICIENCY"), -len(a["resolves"]), -a["priority"], a["title"]))
    officer_actions.sort(key=lambda a: (-a["priority"], a["title"]))
    for i, a in enumerate(institution_actions, 1):
        a["step"] = i
    for i, a in enumerate(officer_actions, 1):
        a["step"] = i
    return {
        "institution_actions": institution_actions,
        "officer_actions": officer_actions,
        "open_findings": len(active),
        "note": "Advisory plan. Uploading a corrected document re-runs only the rules that read it; "
                "outcomes remain subject to official scrutiny.",
    }
