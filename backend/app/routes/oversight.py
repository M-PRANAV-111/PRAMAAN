"""Officer review, rule-pack governance, audit trail, dashboard and benchmark report."""
from __future__ import annotations

import json

import yaml

from .. import audit
from ..api import ApiError, Ctx, not_found, route
from ..config import get_settings
from ..db import loads, new_id, now_iso, reader, transaction
from ..pipeline.findings import ACTIVE_STATES, derive_status
from ..pipeline.rules_engine import RulePack, content_hash
from ..rulepacks import PACK_NAME, active_version, parse
from ..schemas import (AuditEventOut, AuditVerifyOut, DashboardOut, FindingOut, ReviewRequest, RulePackOut,
                       RuleProposalOut, RuleProposalRequest, RulePackVersionOut)
from ..security import OVERSIGHT_ROLES, REVIEWER_ROLES
from .common import finding_out, load_application

_DECISION_STATE = {"CONFIRM": "CONFIRMED", "DISMISS": "DISMISSED", "ESCALATE": "ESCALATED",
                   "REQUEST_CLARIFICATION": "CLARIFICATION_REQUESTED"}


@route("POST", "/api/v1/findings/{finding_id}/review",
       summary="Record an officer decision on a finding (reason required, audited)", tag="findings",
       body=ReviewRequest, response=FindingOut, roles=REVIEWER_ROLES)
def review_finding(ctx: Ctx):
    body: ReviewRequest = ctx.body
    with transaction() as c:
        f = c.execute("SELECT * FROM findings WHERE id = ?", (ctx.path["finding_id"],)).fetchone()
        if f is None:
            raise not_found("Finding")
        a = load_application(c, ctx.user, f["application_id"])
        if f["state"] == "RESOLVED":
            raise ApiError(409, "already_resolved", "This finding was resolved by re-validation")
        new_state = _DECISION_STATE[body.decision]
        c.execute("INSERT INTO reviews (id, finding_id, reviewer_id, decision, reason, created_at) VALUES (?,?,?,?,?,?)",
                  (new_id("rev"), f["id"], ctx.user.user_id, body.decision, body.reason.strip(), now_iso()))
        c.execute("UPDATE findings SET state = ? WHERE id = ?", (new_state, f["id"]))
        sev = [r["severity"] for r in c.execute(
            f"SELECT severity FROM findings WHERE application_id = ? AND state IN ({','.join('?' * len(ACTIVE_STATES))})",
            (a["id"], *ACTIVE_STATES))]
        c.execute("UPDATE applications SET status = ?, updated_at = ? WHERE id = ?", (derive_status(sev), now_iso(), a["id"]))
        audit.record(c, ctx.user, f"finding.{body.decision.lower()}", "finding", f["id"],
                     {"from": f["state"], "to": new_state, "reason_sha256": content_hash(body.reason.strip())}, a["id"])
        if body.decision == 'REQUEST_CLARIFICATION':
            from ..notify import emit
            emit(c,to_institution=a['institution_id'],kind='CLARIFICATION_REQUESTED',title='Clarification requested',
                 body='An officer requested clarification on a finding.',link=f"/applications/{a['id']}",
                 application_id=a['id'],finding_id=f['id'])
        return finding_out(c, c.execute("SELECT * FROM findings WHERE id = ?", (f["id"],)).fetchone(), ctx.user)


# ------------------------------------------------------------------------------------ rule packs
def _version_out(c, r) -> dict:
    def name(uid):
        if not uid:
            return None
        u = c.execute("SELECT name FROM users WHERE id = ?", (uid,)).fetchone()
        return u["name"] if u else None
    return {"id": r["id"], "pack": r["pack"], "version": r["version"], "status": r["status"], "change_note": r["change_note"],
            "content_hash": r["content_hash"], "proposed_by_name": name(r["proposed_by"]),
            "activated_by_name": name(r["activated_by"]), "created_at": r["created_at"], "activated_at": r["activated_at"]}


@route("GET", "/api/v1/rules", summary="Active rule pack with clause references and version history", tag="rules",
       response=RulePackOut)
def get_rules(ctx: Ctx):
    with reader() as c:
        row, pack = active_version(c)
        versions = c.execute("SELECT * FROM rule_pack_versions WHERE pack = ? ORDER BY created_at DESC", (PACK_NAME,)).fetchall()
        rules = []
        for r in pack.rules:
            d = r.model_dump()
            rules.append({k: d.get(k) for k in ("id", "title", "type", "severity", "remedy", "applies_to", "params", "expr",
                                                  "inputs", "field", "sources", "doc_type", "on_or_after")}
                         | {"clause": r.clause.model_dump(), "reads": sorted(r.reads())})
        return {"version": _version_out(c, row), "title": pack.title, "source": pack.source,
                "reference_dates": pack.reference_dates, "categories": pack.categories, "rules": rules,
                "versions": [_version_out(c, v) for v in versions]}


@route("POST", "/api/v1/rules/proposals", summary="Propose a new rule-pack version by changing numeric parameters",
       tag="rules", body=RuleProposalRequest, response=RuleProposalOut, roles=("ADMIN",), status=201)
def propose_rules(ctx: Ctx):
    body: RuleProposalRequest = ctx.body
    with transaction() as c:
        row, pack = active_version(c)
        data = yaml.safe_load(row["content_yaml"])
        diff = []
        by_id = {r["id"]: r for r in data["rules"]}
        for rule_id, params in body.changes.items():
            rule = by_id.get(rule_id)
            if rule is None:
                raise ApiError(422, "unknown_rule", f"Unknown rule {rule_id}")
            for k, v in params.items():
                if k not in (rule.get("params") or {}):
                    raise ApiError(422, "unknown_param", f"Rule {rule_id} has no parameter '{k}'")
                old = rule["params"][k]
                if old != v:
                    rule["params"][k] = int(v) if float(v).is_integer() else v
                    diff.append({"rule_id": rule_id, "param": k, "old": old, "new": rule["params"][k]})
        if not diff:
            raise ApiError(422, "no_change", "The proposal does not change anything")
        major, _, minor = str(data["version"]).partition(".")
        n = 1
        while True:
            candidate = f"{major}.{int(minor or 0) + n}"
            if not c.execute("SELECT 1 FROM rule_pack_versions WHERE pack = ? AND version = ?", (PACK_NAME, candidate)).fetchone():
                break
            n += 1
        data["version"] = candidate
        text = f"# Proposed by {ctx.user.name}: {body.note}\n" + yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
        RulePack.from_yaml(text)  # validates structure and expressions before storing
        vid = new_id("rpv")
        c.execute("INSERT INTO rule_pack_versions (id, pack, version, content_yaml, content_hash, status, change_note,"
                  " proposed_by, created_at) VALUES (?,?,?,?,?, 'PROPOSED', ?, ?, ?)",
                  (vid, PACK_NAME, candidate, text, content_hash(text), body.note, ctx.user.user_id, now_iso()))
        audit.record(c, ctx.user, "rules.proposed", "rule_pack_version", vid, {"version": candidate, "diff": diff})
        return {"version": _version_out(c, c.execute("SELECT * FROM rule_pack_versions WHERE id = ?", (vid,)).fetchone()),
                "diff": diff}


@route("POST", "/api/v1/rules/versions/{version_id}/activate",
       summary="Activate a proposed version (must be a different administrator from the proposer)",
       tag="rules", response=RulePackVersionOut, roles=("ADMIN",))
def activate_rules(ctx: Ctx):
    with transaction() as c:
        v = c.execute("SELECT * FROM rule_pack_versions WHERE id = ?", (ctx.path["version_id"],)).fetchone()
        if v is None:
            raise not_found("Rule pack version")
        if v["status"] != "PROPOSED":
            raise ApiError(409, "not_proposed", "Only proposed versions can be activated")
        if v["proposed_by"] == ctx.user.user_id:
            raise ApiError(403, "four_eyes", "A different administrator must activate this version")
        parse(v["content_yaml"])
        ts = now_iso()
        c.execute("UPDATE rule_pack_versions SET status = 'RETIRED' WHERE pack = ? AND status = 'ACTIVE'", (v["pack"],))
        c.execute("UPDATE rule_pack_versions SET status = 'ACTIVE', activated_by = ?, activated_at = ? WHERE id = ?",
                  (ctx.user.user_id, ts, v["id"]))
        audit.record(c, ctx.user, "rules.activated", "rule_pack_version", v["id"], {"version": v["version"]})
        return _version_out(c, c.execute("SELECT * FROM rule_pack_versions WHERE id = ?", (v["id"],)).fetchone())


# ------------------------------------------------------------------------------------- audit
@route("GET", "/api/v1/audit", summary="Audit events, newest first", tag="audit", response=list[AuditEventOut],
       roles=OVERSIGHT_ROLES, query={"application_id": "Filter by application", "limit": "Max events (≤ 500)"})
def list_audit(ctx: Ctx):
    try:
        limit = max(1, min(500, int(ctx.query.get("limit", "200"))))
    except ValueError:
        limit = 200
    app_id = ctx.query.get("application_id")
    with reader() as c:
        if app_id:
            load_application(c, ctx.user, app_id)
            rows = c.execute("SELECT e.*, u.name FROM audit_events e LEFT JOIN users u ON u.id = e.actor_id"
                             " WHERE e.application_id = ? ORDER BY seq DESC LIMIT ?", (app_id, limit)).fetchall()
        else:
            rows = c.execute("SELECT e.*, u.name FROM audit_events e LEFT JOIN users u ON u.id = e.actor_id"
                             " ORDER BY seq DESC LIMIT ?", (limit,)).fetchall()
    return [{"seq": r["seq"], "ts": r["ts"], "actor_id": r["actor_id"], "actor_role": r["actor_role"],
             "actor_name": r["name"] or ("System" if r["actor_id"] == "system" else None), "action": r["action"],
             "object_type": r["object_type"], "object_id": r["object_id"], "application_id": r["application_id"],
             "payload": loads(r["payload_json"], {}), "hash": r["hash"], "prev_hash": r["prev_hash"]} for r in rows]


@route("GET", "/api/v1/audit/verify", summary="Recompute the hash chain and report the first broken event",
       tag="audit", response=AuditVerifyOut, roles=OVERSIGHT_ROLES)
def verify_audit(ctx: Ctx):
    with reader() as c:
        return audit.verify_chain(c)


# ------------------------------------------------------------------------------------- dashboard
@route("GET", "/api/v1/dashboard", summary="Role-scoped counts computed from stored data", tag="dashboard",
       response=DashboardOut)
def dashboard(ctx: Ctx):
    p = ctx.user
    with reader() as c:
        if p.role == "INSTITUTION":
            where, args = "a.institution_id = ?", (p.institution_id,)
        else:
            where, args = "a.submitted_at IS NOT NULL", ()
        apps = c.execute(f"SELECT a.id, a.status FROM applications a WHERE {where}", args).fetchall()
        ids = [a["id"] for a in apps]
        marks = ",".join("?" * len(ids)) or "''"
        by_status: dict[str, int] = {}
        for a in apps:
            by_status[a["status"]] = by_status.get(a["status"], 0) + 1
        f_rows = c.execute(f"SELECT source_kind, COUNT(*) n FROM findings WHERE application_id IN ({marks}) AND state IN"
                           f" ({','.join('?' * len(ACTIVE_STATES))}) GROUP BY source_kind", (*ids, *ACTIVE_STATES)).fetchall()
        v_rows = c.execute(f"SELECT verification_status s, COUNT(*) n FROM documents WHERE application_id IN ({marks})"
                           " AND superseded_by IS NULL AND verification_status IS NOT NULL GROUP BY verification_status",
                           ids).fetchall()
        reviews = c.execute(f"SELECT COUNT(*) FROM reviews r JOIN findings f ON f.id = r.finding_id"
                            f" WHERE f.application_id IN ({marks})", ids).fetchone()[0]
        simulated = c.execute(f"SELECT 1 FROM verifications WHERE simulated = 1 AND application_id IN ({marks}) LIMIT 1",
                              ids).fetchone() is not None
    return {"role": p.role, "applications": len(apps), "by_status": by_status,
            "open_findings": sum(r["n"] for r in f_rows), "findings_by_source": {r["source_kind"]: r["n"] for r in f_rows},
            "verification_by_status": {r["s"]: r["n"] for r in v_rows}, "reviews_recorded": reviews,
            "simulated_sources_in_use": simulated}


@route("GET", "/api/v1/benchmark", summary="Latest synthetic benchmark report (produced by backend/eval/benchmark.py)",
       tag="dashboard", response=None, roles=OVERSIGHT_ROLES)
def benchmark(ctx: Ctx):
    path = get_settings().data_dir / "benchmark" / "latest.json"
    if not path.exists():
        raise ApiError(404, "no_benchmark", "No benchmark has been run yet. Run: python -m eval.benchmark")
    return json.loads(path.read_text())
