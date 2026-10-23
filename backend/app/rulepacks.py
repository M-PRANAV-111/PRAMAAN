"""Loading and versioning rule packs stored in the database."""
from __future__ import annotations

import sqlite3
from functools import lru_cache

from .config import get_settings
from .db import new_id, now_iso
from .pipeline.rules_engine import RulePack, content_hash

PACK_NAME = "aicte-eoa"


@lru_cache(maxsize=16)
def _parse(content_hash_value: str, text: str) -> RulePack:  # noqa: ARG001 — hash is the cache key
    return RulePack.from_yaml(text)


def parse(text: str) -> RulePack:
    return _parse(content_hash(text), text)


def active_version(conn: sqlite3.Connection, pack: str = PACK_NAME) -> tuple[sqlite3.Row, RulePack]:
    row = conn.execute("SELECT * FROM rule_pack_versions WHERE pack = ? AND status = 'ACTIVE'", (pack,)).fetchone()
    if row is None:
        raise LookupError(f"No active rule pack '{pack}'. Run the seed script.")
    return row, parse(row["content_yaml"])


def install_from_files(conn: sqlite3.Connection) -> list[str]:
    """Install packs from rulepacks/<pack>/<version>.yaml that are not in the DB yet; activate the first one."""
    installed = []
    root = get_settings().rulepack_dir
    for path in sorted(root.glob("*/*.yaml")):
        text = path.read_text(encoding="utf-8")
        pack = parse(text)
        exists = conn.execute("SELECT 1 FROM rule_pack_versions WHERE pack = ? AND version = ?",
                              (pack.pack, pack.version)).fetchone()
        if exists:
            continue
        has_active = conn.execute("SELECT 1 FROM rule_pack_versions WHERE pack = ? AND status = 'ACTIVE'",
                                  (pack.pack,)).fetchone()
        conn.execute(
            "INSERT INTO rule_pack_versions (id, pack, version, content_yaml, content_hash, status, change_note, created_at,"
            " activated_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (new_id("rpv"), pack.pack, pack.version, text, content_hash(text), "PROPOSED" if has_active else "ACTIVE",
             f"Installed from {path.name}", now_iso(), None if has_active else now_iso()),
        )
        installed.append(f"{pack.pack}@{pack.version}")
    return installed
