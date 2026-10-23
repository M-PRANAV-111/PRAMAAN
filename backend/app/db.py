"""SQLite access with a minimal, ordered SQL-migration runner.

Each call to ``connect()`` returns a fresh connection; ``transaction()`` wraps a unit
of work. WAL mode lets the worker thread write while request handlers read.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .config import BACKEND_DIR, get_settings

MIGRATIONS_DIR = BACKEND_DIR / "migrations"
_local = threading.local()


def after_commit(conn, fn):
    """Schedule a side effect only after its transaction commits."""
    callbacks = getattr(_local, "transactions", {}).get(id(conn))
    if callbacks is None:
        raise RuntimeError("after_commit requires a managed transaction")
    callbacks.append(fn)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:20]}"


def connect(path: Path | None = None) -> sqlite3.Connection:
    db_path = path or get_settings().database_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=10, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 10000")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection | None = None) -> Iterator[sqlite3.Connection]:
    own = conn is None
    c = conn or connect()
    c.execute("BEGIN IMMEDIATE")
    if not hasattr(_local, "transactions"):
        _local.transactions = {}
    callbacks = _local.transactions[id(c)] = []
    try:
        yield c
        c.execute("COMMIT")
    except BaseException:
        c.execute("ROLLBACK")
        raise
    finally:
        _local.transactions.pop(id(c), None)
        if own:
            c.close()
    for fn in callbacks:
        fn()


@contextmanager
def reader() -> Iterator[sqlite3.Connection]:
    c = connect()
    try:
        yield c
    finally:
        c.close()


def migrate(path: Path | None = None) -> list[str]:
    """Apply pending ``migrations/NNNN_*.sql`` files in order. Returns applied versions."""
    conn = connect(path)
    applied: list[str] = []
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        done = {r[0] for r in conn.execute("SELECT version FROM schema_migrations")}
        for file in sorted(MIGRATIONS_DIR.glob("*.sql")):
            version = file.stem
            if version in done:
                continue
            sql = file.read_text(encoding="utf-8")
            conn.execute("BEGIN IMMEDIATE")
            try:
                for statement in _split_sql(sql):
                    conn.execute(statement)
                conn.execute("INSERT INTO schema_migrations VALUES (?, ?)", (version, now_iso()))
                conn.execute("COMMIT")
            except BaseException:
                conn.execute("ROLLBACK")
                raise
            applied.append(version)
    finally:
        conn.close()
    return applied


def _split_sql(sql: str) -> list[str]:
    lines = [ln for ln in sql.splitlines() if not ln.strip().startswith("--")]
    return [s.strip() for s in "\n".join(lines).split(";") if s.strip()]


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def loads(value: str | None, default: Any = None) -> Any:
    if value is None:
        return default
    return json.loads(value)


def dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
