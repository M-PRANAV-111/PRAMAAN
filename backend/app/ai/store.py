"""Small persistence helpers shared by the AI pipeline steps. All of them use the caller's connection."""
from __future__ import annotations

import sqlite3
from typing import Any

from .. import audit
from ..db import dumps, loads, new_id, now_iso


def add_job_note(conn: sqlite3.Connection, job_id: str, text: str) -> None:
    if conn.execute("SELECT 1 FROM job_notes WHERE job_id=? AND text=?", (job_id, text)).fetchone():
        return  # several AI steps can skip for the same reason; say it once per job
    conn.execute("INSERT INTO job_notes (id, job_id, level, text, created_at) VALUES (?,?,'INFO',?,?)",
                 (new_id("note"), job_id, text, now_iso()))


def job_notes(conn: sqlite3.Connection, job_id: str) -> list[dict[str, Any]]:
    return [{"id": r["id"], "level": r["level"], "text": r["text"], "created_at": r["created_at"]}
            for r in conn.execute("SELECT * FROM job_notes WHERE job_id=? ORDER BY created_at, rowid", (job_id,))]


def set_document_state(conn: sqlite3.Connection, document_id: str, status: str, *, reason: str | None = None,
                       synthetic: bool | None = None, provider: str | None = None, model: str | None = None,
                       cache_hit: bool = False, classification: dict[str, Any] | None = None) -> None:
    previous = conn.execute("SELECT synthetic, classification_json FROM ai_documents WHERE document_id=?",
                            (document_id,)).fetchone()
    if synthetic is None and previous is not None:
        synthetic = None if previous["synthetic"] is None else bool(previous["synthetic"])
    conn.execute(
        "INSERT INTO ai_documents (document_id, synthetic, step_status, skip_reason, provider, model, cache_hit,"
        " classification_json, updated_at) VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(document_id) DO UPDATE SET"
        " synthetic=excluded.synthetic, step_status=excluded.step_status, skip_reason=excluded.skip_reason,"
        " provider=excluded.provider, model=excluded.model, cache_hit=excluded.cache_hit,"
        " classification_json=excluded.classification_json, updated_at=excluded.updated_at",
        (document_id, None if synthetic is None else int(synthetic), status, reason, provider, model, int(cache_hit),
         dumps(classification) if classification is not None else None, now_iso()))


def set_synthetic(conn: sqlite3.Connection, document_id: str, synthetic: bool) -> None:
    """Record the stamp check only, leaving whatever else is known about the document untouched."""
    conn.execute("INSERT INTO ai_documents (document_id, synthetic, step_status, updated_at) VALUES (?,?, 'NOT_NEEDED', ?)"
                 " ON CONFLICT(document_id) DO UPDATE SET synthetic=excluded.synthetic, updated_at=excluded.updated_at",
                 (document_id, int(synthetic), now_iso()))


def document_state(conn: sqlite3.Connection, document_id: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM ai_documents WHERE document_id=?", (document_id,)).fetchone()
    if row is None:
        return None
    return {"synthetic": None if row["synthetic"] is None else bool(row["synthetic"]), "status": row["step_status"],
            "reason": row["skip_reason"], "provider": row["provider"], "model": row["model"],
            "cache_hit": bool(row["cache_hit"]), "classification": loads(row["classification_json"])}


def replace_suggestions(conn: sqlite3.Connection, document_id: str, application_id: str,
                        items: list[dict[str, Any]]) -> None:
    conn.execute("DELETE FROM ai_suggestions WHERE document_id=?", (document_id,))
    for s in items:
        conn.execute(
            "INSERT INTO ai_suggestions (id, document_id, application_id, field, value, page, quote, reason, model, status,"
            " created_at) VALUES (?,?,?,?,?,?,?,?,?, 'OPEN', ?)",
            (new_id("sug"), document_id, application_id, s["field"], s["value"], s.get("page"), s.get("quote"),
             s["reason"], s["model"], now_iso()))


def suggestions_for(conn: sqlite3.Connection, document_id: str) -> list[dict[str, Any]]:
    """Rows shaped like ``AiSuggestionOut`` (the quote stays in the database)."""
    return [{"field": r["field"], "value": r["value"], "page": r["page"], "reason": r["reason"], "model": r["model"]}
            for r in conn.execute("SELECT * FROM ai_suggestions WHERE document_id=? ORDER BY field, rowid", (document_id,))]


def audit_system(conn: sqlite3.Connection, action: str, object_type: str, object_id: str,
                 payload: dict[str, Any], application_id: str | None = None) -> None:
    """Audit events carry identifiers, counts and codes only; never document text, prompts or outputs."""
    audit.record(conn, None, action, object_type, object_id, payload, application_id)
