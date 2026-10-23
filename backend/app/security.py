"""Password hashing, session tokens, rate limiting and role definitions."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt

from .config import get_settings

ROLES = ("INSTITUTION", "OFFICER", "ADMIN", "AUDITOR")
REVIEWER_ROLES = ("OFFICER", "ADMIN")
OVERSIGHT_ROLES = ("OFFICER", "ADMIN", "AUDITOR")

# scrypt parameters: N=2^15, r=8, p=1 (~32 MiB, memory-hard). Stored with the hash so they can be raised later.
_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2**15, 8, 1


def hash_password(password: str) -> str:
    if len(password) < 10:
        raise ValueError("Password must be at least 10 characters")
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, maxmem=64 * 1024 * 1024, dklen=32)
    return "scrypt${}${}${}${}${}".format(
        _SCRYPT_N, _SCRYPT_R, _SCRYPT_P, base64.b64encode(salt).decode(), base64.b64encode(dk).decode()
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt_b64, dk_b64 = stored.split("$")
        if algo != "scrypt":
            return False
        expected = base64.b64decode(dk_b64)
        dk = hashlib.scrypt(
            password.encode(), salt=base64.b64decode(salt_b64), n=int(n), r=int(r), p=int(p),
            maxmem=64 * 1024 * 1024, dklen=len(expected),
        )
        return hmac.compare_digest(dk, expected)
    except (ValueError, TypeError):
        return False


# A fixed dummy hash so that unknown e-mail addresses take the same time as wrong passwords.
_DUMMY_HASH: str | None = None


def dummy_verify(password: str) -> None:
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        _DUMMY_HASH = hash_password("timing-equaliser-password")
    verify_password(password, _DUMMY_HASH)


@dataclass(frozen=True)
class Principal:
    user_id: str
    role: str
    institution_id: str | None
    name: str
    email: str

    @property
    def is_institution(self) -> bool:
        return self.role == "INSTITUTION"


def issue_token(p: Principal) -> tuple[str, datetime]:
    s = get_settings()
    exp = datetime.now(timezone.utc) + timedelta(minutes=s.jwt_ttl_minutes)
    payload = {
        "sub": p.user_id, "role": p.role, "inst": p.institution_id, "name": p.name, "email": p.email,
        "exp": exp, "iat": datetime.now(timezone.utc), "iss": "pramaan", "jti": secrets.token_hex(8),
    }
    return jwt.encode(payload, s.jwt_secret, algorithm="HS256"), exp


def decode_token(token: str) -> Principal | None:
    s = get_settings()
    try:
        data = jwt.decode(token, s.jwt_secret, algorithms=["HS256"], issuer="pramaan",
                          options={"require": ["exp", "sub", "role", "iss"]})
    except jwt.PyJWTError:
        return None
    if data.get("role") not in ROLES:
        return None
    return Principal(user_id=data["sub"], role=data["role"], institution_id=data.get("inst"),
                     name=data.get("name", ""), email=data.get("email", ""))


class RateLimiter:
    """Fixed-window limiter keyed by caller identity. In-process; use Redis when running multiple replicas."""

    def __init__(self) -> None:
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, limit: int, window_seconds: float = 60.0) -> bool:
        now = time.monotonic()
        with self._lock:
            hits = [t for t in self._hits.get(key, []) if now - t < window_seconds]
            if len(hits) >= limit:
                self._hits[key] = hits
                return False
            hits.append(now)
            self._hits[key] = hits
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


rate_limiter = RateLimiter()
