"""Plug the AI layer and routing into the pipeline through Astra's extension points; nothing else is patched.

* ``register_step("after_fields", ...)``  grounded AI-assisted extraction
* ``register_step("after_rules", ...)``   document-type finding, validated wording, routing recommendation
* ``features.register``                   ``routing`` (always on) and ``ai`` (on when a provider is configured)
* ``features.register_system_extra``      an ``ai`` entry in ``SystemOut.extras``

Imported by ``app.main`` (so API workers and job subprocesses both register the steps). An unsafe configuration
(for example ``AI_DATA_POLICY=allow_real`` without ``AI_PAID_TIER_CONFIRMED=true``) raises here, at startup.
"""
from __future__ import annotations

from typing import Any

from .. import features
from ..db import reader
from ..pipeline.ai_extract import ai_extract_step, classification_sync_step
from ..pipeline.explain import explain_step
from ..pipeline.hooks import register_step
from ..pipeline.routing import routing_step
from .client import build_status, kill_switch_engaged
from .config import get_config, validate_startup


def _ai_enabled() -> bool:
    if not get_config().enabled:
        return False
    try:
        with reader() as c:
            return not kill_switch_engaged(c)
    except Exception:  # noqa: BLE001 — a probe must never fail because of the database
        return False


def _extras() -> dict[str, Any]:
    with reader() as c:
        s = build_status(c)
    return {k: s[k] for k in ("provider", "mode", "kill_switch", "requests_today", "fallback_active", "last_error_code")}


def install() -> None:
    validate_startup()
    register_step("after_fields", ai_extract_step)
    register_step("after_rules", classification_sync_step)
    register_step("after_rules", explain_step)
    register_step("after_rules", routing_step)
    features.register("routing", True)
    features.register("ai", _ai_enabled)
    features.register_system_extra("ai", _extras)
