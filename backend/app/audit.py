"""Append-only, hash-chained audit log.

Each event stores ``hash = SHA-256(prev_hash | seq | ts | actor | action | object | payload_hash)``.
Changing, deleting or reordering any row breaks every later hash, which ``verify_chain`` reports.
Payloads hold identifiers and decisions only — never document contents.
"""
from __future__ import annotations

import hashlib
import sqlite3
from typing import Any

from .db import dumps, now_iso
from .security import Principal

GENESIS = "0" * 64


def _event_hash(prev_hash: str, seq: int, ts: str, actor_id: str, action: str, object_type: str,
                object_id: str, payload_hash: str) -> str:
    material = "|".join([prev_hash, str(seq), ts, actor_id, action, object_type, object_id, payload_hash])
    return hashlib.sha256(material.encode()).hexdigest()


def record(conn: sqlite3.Connection, actor: Principal | None, action: str, object_type: str, object_id: str,
           payload: dict[str, Any] | None = None, application_id: str | None = None) -> int:
    """Append an event. Must be called inside an open write transaction."""
    payload = payload or {}
    payload_json = dumps(payload)
    payload_hash = hashlib.sha256(payload_json.encode()).hexdigest()
    last = conn.execute("SELECT seq, hash FROM audit_events ORDER BY seq DESC LIMIT 1").fetchone()
    prev_hash = last["hash"] if last else GENESIS
    seq = (last["seq"] + 1) if last else 1
    ts = now_iso()
    actor_id = actor.user_id if actor else "system"
    h = _event_hash(prev_hash, seq, ts, actor_id, action, object_type, object_id, payload_hash)
    conn.execute(
        "INSERT INTO audit_events (seq, ts, actor_id, actor_role, action, object_type, object_id, application_id,"
        " payload_json, payload_hash, prev_hash, hash) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (seq, ts, actor_id, actor.role if actor else "SYSTEM", action, object_type, object_id, application_id,
         payload_json, payload_hash, prev_hash, h),
    )
    return seq


def verify_chain(conn: sqlite3.Connection) -> dict[str, Any]:
    prev = GENESIS
    expected_seq = 1
    count = 0
    for row in conn.execute("SELECT * FROM audit_events ORDER BY seq"):
        count += 1
        problem = None
        if row["seq"] != expected_seq:
            problem = "sequence gap (event deleted or reordered)"
        elif row["prev_hash"] != prev:
            problem = "previous-hash link broken"
        elif hashlib.sha256(row["payload_json"].encode()).hexdigest() != row["payload_hash"]:
            problem = "payload altered"
        else:
            h = _event_hash(prev, row["seq"], row["ts"], row["actor_id"], row["action"], row["object_type"],
                            row["object_id"], row["payload_hash"])
            if h != row["hash"]:
                problem = "event fields altered"
        if problem:
            return {"valid": False, "events_checked": count, "first_broken_seq": row["seq"], "problem": problem,
                    "head_hash": None}
        prev = row["hash"]
        expected_seq += 1
    return {"valid": True, "events_checked": count, "first_broken_seq": None, "problem": None, "head_hash": prev}
