"""Single-use purpose-scoped tokens. Raw tokens never enter the database."""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .db import new_id, now_iso

LIFETIMES = {"VERIFY_EMAIL": 24 * 60, "RESET_PASSWORD": 30, "INVITATION": 72 * 60}


def issue(conn, user_id, purpose):
    raw = secrets.token_urlsafe(32)
    conn.execute("UPDATE one_time_tokens SET used_at=? WHERE user_id=? AND purpose=? AND used_at IS NULL",
                 (now_iso(), user_id, purpose))
    conn.execute("INSERT INTO one_time_tokens VALUES (?,?,?,?,?,NULL,?)",
                 (new_id("tok"), user_id, purpose, hashlib.sha256(raw.encode()).hexdigest(),
                  (datetime.now(timezone.utc) + timedelta(minutes=LIFETIMES[purpose])).isoformat(timespec="seconds"), now_iso()))
    return raw


def consume(conn, raw, purpose):
    from .api import ApiError
    row = conn.execute("SELECT * FROM one_time_tokens WHERE token_hash=? AND purpose=? AND used_at IS NULL AND expires_at>?",
                       (hashlib.sha256(raw.encode()).hexdigest(), purpose, now_iso())).fetchone()
    if row is None:
        raise ApiError(422, "invalid_token", "This link is invalid or has expired. Request a new link.")
    conn.execute("UPDATE one_time_tokens SET used_at=? WHERE id=?", (now_iso(), row['id']))
    return row['user_id']


def validate_password(password, email):
    from .api import ApiError
    common = set((Path(__file__).parent / "data/common_passwords.txt").read_text(encoding="utf-8").splitlines())
    local = email.partition("@")[0].casefold()
    if not 12 <= len(password) <= 200 or password.casefold() in common or (local and local in password.casefold()):
        raise ApiError(422, "weak_password", "Use 12–200 characters, avoid common passwords and your email name.")
