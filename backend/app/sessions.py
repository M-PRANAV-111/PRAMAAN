"""Server-side session checks and privacy-preserving client metadata."""
import ipaddress
import secrets
from datetime import datetime, timedelta, timezone

from .db import now_iso, reader, transaction


def client_ip(request):
    from .config import get_settings
    raw = request.client.host if request.client else "unknown"
    if get_settings().trust_proxy:
        raw = request.headers.get("x-forwarded-for", raw).split(",")[0].strip()
    try:
        return str(ipaddress.ip_address(raw))
    except ValueError:
        return "unknown"


def ip_hint(ip):
    try:
        addr = ipaddress.ip_address(ip)
        return str(ipaddress.ip_network(f"{addr}/{24 if addr.version == 4 else 48}", strict=False))
    except ValueError:
        return "unknown"


def create(conn, user_id, expires_at, user_agent="", ip="unknown", session_id=None):
    sid = session_id or secrets.token_urlsafe(24)
    ts = now_iso()
    conn.execute("INSERT INTO sessions VALUES (?,?,?,?,?,NULL,?,?)",
                 (sid, user_id, ts, ts, expires_at, user_agent[:120], ip_hint(ip)))
    return sid


def authenticate(token):
    from .security import Principal, decode_token
    p = decode_token(token)
    if p is None or not p.session_id:
        return None
    ts = now_iso()
    with reader() as c:
        row = c.execute("SELECT u.*, s.last_seen_at FROM sessions s JOIN users u ON u.id=s.user_id "
                        "WHERE s.id=? AND s.user_id=? AND s.revoked_at IS NULL AND s.expires_at>? "
                        "AND u.is_active=1 AND u.email_verified=1", (p.session_id, p.user_id, ts)).fetchone()
    if row is None:
        return None
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(timespec="seconds")
    if row['last_seen_at'] < cutoff:
        with transaction() as c:
            c.execute("UPDATE sessions SET last_seen_at=? WHERE id=? AND last_seen_at<? AND revoked_at IS NULL",
                      (ts, p.session_id, cutoff))
    return Principal(row['id'], row['role'], row['institution_id'], row['name'], row['email'], p.session_id)


def revoke(conn, user_id, *, except_id=None):
    conn.execute("UPDATE sessions SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL AND id != ?",
                 (now_iso(), user_id, except_id or ""))
