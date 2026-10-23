from __future__ import annotations

from starlette.responses import JSONResponse

from .. import audit
from ..api import SESSION_COOKIE, ApiError, Ctx, route
from ..config import get_settings
from ..db import reader, transaction
from ..schemas import LoginRequest, OkOut, SessionOut, UserOut
from ..security import Principal, dummy_verify, issue_token, rate_limiter, verify_password


def _user_out(c, u) -> dict:
    inst = None
    if u["institution_id"]:
        inst = c.execute("SELECT name FROM institutions WHERE id = ?", (u["institution_id"],)).fetchone()
    return {"id": u["id"], "email": u["email"], "name": u["name"], "role": u["role"],
            "institution_id": u["institution_id"], "institution_name": inst["name"] if inst else None}


@route("POST", "/api/v1/auth/login", summary="Sign in and receive a session cookie", tag="auth", body=LoginRequest,
       response=SessionOut, public=True)
def login(ctx: Ctx):
    s = get_settings()
    body: LoginRequest = ctx.body
    if not rate_limiter.allow(f"login:{ctx.client_ip}", s.login_rate_per_minute):
        raise ApiError(429, "rate_limited", "Too many sign-in attempts. Wait a minute and try again.")
    with reader() as c:
        u = c.execute("SELECT * FROM users WHERE email = ? AND is_active = 1", (body.email.strip().lower(),)).fetchone()
        if u is None:
            dummy_verify(body.password)
            ok = False
        else:
            ok = verify_password(body.password, u["password_hash"])
        if not ok:
            with transaction() as w:
                audit.record(w, None, "auth.login_failed", "user", "unknown", {"email_hash_prefix": _h(body.email)})
            raise ApiError(401, "invalid_credentials", "Email or password is incorrect")
        user = _user_out(c, u)
    p = Principal(u["id"], u["role"], u["institution_id"], u["name"], u["email"])
    token, exp = issue_token(p)
    with transaction() as w:
        audit.record(w, p, "auth.login", "user", u["id"], {})
    resp = JSONResponse(SessionOut(user=UserOut(**user), expires_at=exp.isoformat()).model_dump(mode="json"))
    resp.set_cookie(SESSION_COOKIE, token, max_age=s.jwt_ttl_minutes * 60, httponly=True, secure=s.cookie_secure,
                    samesite="strict", path="/")
    return resp


def _h(email: str) -> str:
    import hashlib
    return hashlib.sha256(email.strip().lower().encode()).hexdigest()[:12]


@route("POST", "/api/v1/auth/logout", summary="End the session", tag="auth", response=OkOut)
def logout(ctx: Ctx):
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(SESSION_COOKIE, path="/")
    return resp


@route("GET", "/api/v1/auth/me", summary="Current user", tag="auth", response=UserOut)
def me(ctx: Ctx):
    with reader() as c:
        u = c.execute("SELECT * FROM users WHERE id = ? AND is_active = 1", (ctx.user.user_id,)).fetchone()
        if u is None:
            raise ApiError(401, "unauthenticated", "Account is no longer active")
        return _user_out(c, u)
