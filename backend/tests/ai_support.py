"""Shared helpers for the AI-layer tests. CI never calls a live API: the single network seam
(``app.ai.http.post_json``) is replaced by a fake that answers in the documented Gemini/Groq response shapes.

The JSON files under ``tests/fixtures/ai`` are hand-authored model outputs wrapped in those shapes (see the README
there); they are not recordings of a live service.
"""
from __future__ import annotations

import json
import os
import re
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Callable
from unittest.mock import patch

from app.ai import prompts
from app.ai.types import AIError
from app.config import reset_settings_cache
from app.db import new_id, now_iso, reader, transaction
from app.security import Principal
from tests.local_support import LocalDatabaseCase

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "ai"
PID = "1-SYN-TEST"   # the permanent id of the institution that LocalDatabaseCase creates


def fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def gemini_body(output: dict[str, Any], tokens: tuple[int, int] = (1200, 140), status: str = "completed") -> dict[str, Any]:
    """A response in the shape documented for POST /v1beta/interactions."""
    return {"id": "interaction-test", "status": status, "model": "test",
            "steps": [{"type": "model_output", "content": [{"type": "text", "text": json.dumps(output)}]}],
            "usage": {"total_input_tokens": tokens[0], "total_output_tokens": tokens[1]}}


def groq_body(output: dict[str, Any]) -> dict[str, Any]:
    return {"choices": [{"message": {"content": json.dumps(output)}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 900, "completion_tokens": 90}}


def task_of(url: str, payload: dict[str, Any]) -> str:
    system = payload.get("system_instruction") or (payload.get("messages") or [{}])[0].get("content", "")
    for task, text in (("extract", prompts.EXTRACT_SYSTEM), ("classify", prompts.CLASSIFY_SYSTEM),
                       ("explain", prompts.EXPLAIN_SYSTEM)):
        if system == text:
            return task
    raise AssertionError("unknown task")


@dataclass
class Call:
    url: str
    task: str
    payload: dict[str, Any]
    headers: dict[str, str]


@dataclass
class FakeTransport:
    """Replaces ``app.ai.http.post_json``. ``responder(call) -> body | AIError``; every call is recorded."""
    responder: Callable[[Call], Any]
    calls: list[Call] = field(default_factory=list)

    def __call__(self, url: str, headers: dict[str, str], payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        call = Call(url, task_of(url, payload), payload, headers)
        self.calls.append(call)
        out = self.responder(call)
        if isinstance(out, Exception):
            raise out
        return out

    def of(self, task: str) -> list[Call]:
        return [c for c in self.calls if c.task == task]


def facts_in(call: Call) -> dict[str, Any]:
    """The facts object of an explain call (from either provider shape)."""
    payload = call.payload
    text = payload["input"][-1]["text"] if "input" in payload else payload["messages"][-1]["content"]
    return json.loads(re.search(r"<facts>\n(.*)\n</facts>", text, re.S).group(1))


class AICase(LocalDatabaseCase):
    """A fresh database with AI switched on (Gemini, a fake key), no fallback, and the network seam patched."""
    env_extra: dict[str, str] = {}

    def setUp(self):
        super().setUp()
        env = {"AI_PROVIDER": "gemini", "GEMINI_API_KEY": "test-key-not-real", "GROQ_API_KEY": "",
               "AI_FALLBACK_PROVIDER": "none", "AI_DATA_POLICY": "synthetic_only", "AI_PAID_TIER_CONFIRMED": "",
               "AI_DAILY_REQUEST_BUDGET": "200", "AI_DAILY_PAGE_BUDGET": "1000", **self.env_extra}
        self._ai_env = patch.dict(os.environ, env)
        self._ai_env.start()
        reset_settings_cache()
        self.addCleanup(self._ai_env.stop)
        self.transport: FakeTransport | None = None
        self.principal = Principal("usr", "INSTITUTION", "ins", "Test contact", "contact@example.test")
        with transaction() as c:  # a second institution user is not needed; add one officer for escalations
            c.execute("INSERT INTO users (id,email,name,role,institution_id,password_hash,created_at)"
                      " VALUES ('off','officer@example.test','Officer','OFFICER',NULL,'!x',?)", (now_iso(),))

    @contextmanager
    def network(self, responder: Callable[[Call], Any]):
        transport = FakeTransport(responder)
        self.transport = transport
        with patch("app.ai.http.post_json", transport):
            yield transport

    # --------------------------------------------------------------------------------- pipeline
    def upload(self, doc_type: str, name: str, data: bytes, app: str = "app") -> str:
        from synthetic.seed import upload
        return upload(self.principal, app, doc_type, name, data)

    def second_application(self, app_id: str = "app2") -> str:
        """Another application of the same institution (a different year), for with/without-AI comparisons."""
        with transaction() as c:
            ts = now_iso()
            c.execute("INSERT INTO applications (id,institution_id,category,academic_year,status,created_by,created_at,updated_at,"
                      "submitted_at) VALUES (?,'ins','EOA_EXISTING','2026-27','DRAFT','usr',?,?,?)", (app_id, ts, ts, ts))
        return app_id

    def claims(self, doc_id: str) -> dict[str, dict[str, Any]]:
        with reader() as c:
            return {r["field"]: dict(r) for r in c.execute("SELECT * FROM claims WHERE document_id=?", (doc_id,))}

    def suggestions(self, doc_id: str) -> list[dict[str, Any]]:
        with reader() as c:
            return [dict(r) for r in c.execute("SELECT * FROM ai_suggestions WHERE document_id=? ORDER BY field", (doc_id,))]

    def last_job_notes(self) -> list[str]:
        with reader() as c:
            return [r["text"] for r in c.execute("SELECT text FROM job_notes ORDER BY created_at, rowid")]

    def audit_actions(self) -> list[str]:
        with reader() as c:
            return [r["action"] for r in c.execute("SELECT action FROM audit_events ORDER BY seq")]


def iso(d: date) -> str:
    return d.isoformat()


def ensure_core_template() -> None:
    """Seed the shared synthetic database (once) with AI switched off, so seeding never reaches a provider."""
    import subprocess
    import sys
    import tempfile
    import tests.core_support as cs
    from tests.test_api import BACKEND, PASSWORD
    if cs._template is None:
        cs._template = tempfile.TemporaryDirectory()
        env = {**os.environ, "DATA_DIR": cs._template.name, "SEED_DEMO_PASSWORD": PASSWORD, "APP_ENV": "test",
               "EMAIL_PROVIDER": "console", "AI_PROVIDER": "none"}
        result = subprocess.run([sys.executable, "-m", "synthetic.seed"], cwd=BACKEND, env=env, capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(result.stderr)
