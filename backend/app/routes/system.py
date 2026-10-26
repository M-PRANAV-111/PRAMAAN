from __future__ import annotations

import shutil

from starlette.responses import JSONResponse

from ..api import Ctx, route
from ..features import snapshot
from ..config import get_settings
from ..db import reader
from ..pipeline.doctypes import DOC_TYPES
from ..rulepacks import active_version
from ..schemas import ApplicationStatus, HealthOut, MetaOut, VerificationStatus
from ..storage import LocalStorage


@route("GET", "/api/v1/health", summary="Liveness probe", tag="system", response=HealthOut, public=True)
def health(ctx: Ctx):
    return {"status": "ok", "checks": {"process": "ok"}}


@route("GET", "/api/v1/ready", summary="Readiness probe (database, rule pack, storage, OCR)", tag="system",
       response=HealthOut, public=True)
def ready(ctx: Ctx):
    checks: dict[str, str] = {}
    try:
        with reader() as c:
            c.execute("SELECT 1").fetchone()
            row, _ = active_version(c)
            checks["database"] = "ok"
            checks["rule_pack"] = f"ok ({row['version']})"
    except Exception as exc:  # report, don't crash the probe
        checks["database"] = f"error: {type(exc).__name__}"
    try:
        LocalStorage()
        checks["storage"] = "ok"
    except OSError:
        checks["storage"] = "error"
    tess = get_settings().tesseract_cmd or shutil.which("tesseract")
    checks["ocr"] = "ok" if tess else "unavailable (scanned pages cannot be read)"
    status = "ok" if all(v.startswith("ok") for v in checks.values()) else "degraded"
    body = HealthOut(status=status, checks=checks).model_dump()
    return JSONResponse(body, status_code=200 if status == "ok" else 503)


@route("GET", "/api/v1/meta", summary="Enumerations and configuration the UI needs", tag="system", response=MetaOut,
       public=True)
def meta(ctx: Ctx):
    with reader() as c:
        row, pack = active_version(c)
    return {
        "features": {**snapshot(), "demo_accounts": get_settings().show_demo_accounts and get_settings().env != 'production',
                     # The camera scanner's drawn synthetic page is a development/test stand-in, never offered in production.
                     "simulated_camera": get_settings().env != "production"},
        "doc_types": DOC_TYPES,
        "categories": {k: v.get("label", k) for k, v in pack.categories.items()},
        "application_statuses": list(ApplicationStatus.__args__),
        "verification_statuses": list(VerificationStatus.__args__),
        "default_academic_year": "2026-27",
        "rule_pack_version": row["version"],
        "max_upload_bytes": get_settings().max_upload_bytes,
    }
