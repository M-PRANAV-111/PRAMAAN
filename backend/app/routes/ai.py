"""AI status, the runtime kill switch, routing recommendations and job notes."""
from __future__ import annotations

import hashlib

from .. import audit
from ..ai import store
from ..ai.client import build_status, set_state
from ..api import Ctx, not_found, route
from ..db import reader, transaction
from ..pipeline import routing
from ..schemas_ai import AiStatusOut, JobNoteOut, KillSwitchRequest, RoutingOut
from .common import load_application


@route("GET", "/api/v1/ai/status", summary="AI layer status: provider, models, budget, errors (never a key)", tag="ai",
       response=AiStatusOut, roles=("ADMIN", "AUDITOR"))
def ai_status(ctx: Ctx):
    with reader() as c:
        return build_status(c)


@route("POST", "/api/v1/ai/kill-switch", summary="Engage or release the runtime AI kill switch", tag="ai",
       body=KillSwitchRequest, response=AiStatusOut, roles=("ADMIN",))
def ai_kill_switch(ctx: Ctx):
    body: KillSwitchRequest = ctx.body
    with transaction() as c:
        set_state(c, "kill_switch", "1" if body.engaged else "0")
        audit.record(c, ctx.user, "ai.kill_switch", "system", "ai",
                     {"engaged": body.engaged, "reason_hash": hashlib.sha256(body.reason.encode()).hexdigest()})
        return build_status(c)


@route("GET", "/api/v1/applications/{application_id}/routing", summary="Routing recommendation with reasons", tag="findings",
       response=RoutingOut)
def application_routing(ctx: Ctx):
    with reader() as c:
        a = load_application(c, ctx.user, ctx.path["application_id"])
        return routing.current(c, a["id"])


@route("GET", "/api/v1/jobs/{job_id}/notes", summary="INFO notes recorded on a processing job (e.g. an AI step that was skipped)",
       tag="documents", response=list[JobNoteOut])
def job_notes(ctx: Ctx):
    with reader() as c:
        j = c.execute("SELECT application_id FROM jobs WHERE id = ?", (ctx.path["job_id"],)).fetchone()
        if j is None:
            raise not_found("Job")
        load_application(c, ctx.user, j["application_id"])
        return store.job_notes(c, ctx.path["job_id"])
