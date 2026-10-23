"""Account lifecycle, contact data and self-service session management."""
import hashlib

from .. import audit, features, sessions, tokens
from ..api import ApiError, Ctx, not_found, route
from ..config import get_settings
from ..db import new_id, now_iso, reader, transaction
from ..email import send_email
from ..schemas import (AcceptedOut, RegisterRequest, TokenRequest, AcceptInvitationRequest, EmailRequest,
                       PasswordResetRequest, PasswordChangeRequest, OkOut, SessionOut, AccountOut, AccountUpdate,
                       SessionInfoOut)
from ..security import hash_password, verify_password, rate_limiter
from .auth import _user_out, session_response

ACCEPTED = {"ok": True, "message": "If this request can be processed, you will receive an email with next steps."}
features.register("registration")
features.register("password_reset", lambda: get_settings().env != "production" or get_settings().email_provider != "console")


def limit(ctx, purpose, count=5, seconds=3600):
    if not rate_limiter.allow(f"{purpose}:{ctx.client_ip}", count, seconds):
        raise ApiError(429, "rate_limited", "Too many attempts. Please try again later.")


def link_mail(email, purpose, raw):
    paths = {"VERIFY_EMAIL": "/verify-email", "RESET_PASSWORD": "/reset-password", "INVITATION": "/accept-invitation"}
    labels = {"VERIFY_EMAIL": "Verify your email", "RESET_PASSWORD": "Reset your password", "INVITATION": "Accept your invitation"}
    send_email(email, "PRAMAAN: " + labels[purpose],
               f"{labels[purpose]}: {get_settings().public_base_url}{paths[purpose]}?token={raw}\n"
               "If you did not request this, you can ignore this message.")


@route("POST", "/api/v1/auth/register", summary="Register an institution contact", tag="auth", body=RegisterRequest,
       response=AcceptedOut, public=True, status=202)
def register(ctx: Ctx):
    limit(ctx, "register")
    b = ctx.body
    tokens.validate_password(b.password, b.email)
    hashed = hash_password(b.password)  # equal work for new and duplicate accounts
    raw = None
    with transaction() as c:
        existing = c.execute("SELECT id FROM users WHERE lower(email)=?", (b.email,)).fetchone()
        duplicate_pid = c.execute("SELECT id FROM institutions WHERE lower(aicte_permanent_id)=?",
                                  (b.institution.aicte_permanent_id.lower(),)).fetchone()
        if existing or duplicate_pid:
            audit.record(c, None, "registration.requested", "registration", "withheld")
        else:
            iid, uid, rid, ts = new_id('ins'), new_id('usr'), new_id('reg'), now_iso()
            i = b.institution
            c.execute("INSERT INTO institutions (id,aicte_permanent_id,name,state,trust_name,created_at,status,contact_email) "
                      "VALUES (?,?,?,?,?,?,'PENDING',?)", (iid, i.aicte_permanent_id, i.name, i.state, i.trust_name, ts, b.email))
            c.execute("INSERT INTO users (id,email,name,role,institution_id,password_hash,is_active,created_at,email_verified,phone) "
                      "VALUES (?,?,?,'INSTITUTION',?,?,0,?,0,?)", (uid,b.email,b.name,iid,hashed,ts,b.phone))
            c.execute("INSERT INTO registrations (id,institution_id,user_id,status,created_at) VALUES (?,?,?,'PENDING',?)",
                      (rid,iid,uid,ts))
            raw = tokens.issue(c, uid, 'VERIFY_EMAIL')
            audit.record(c, None, 'registration.created', 'registration', rid)
    if raw:
        link_mail(b.email, 'VERIFY_EMAIL', raw)
    elif existing:
        send_email(b.email, 'PRAMAAN: Registration request', 'Someone tried to register with your address. '
                   'Your account has not changed. If this was you, use the sign-in page at ' + get_settings().public_base_url + '/login')
    return ACCEPTED


@route("POST", "/api/v1/auth/verify-email", summary="Verify a registration email", tag="auth", body=TokenRequest,
       response=OkOut, public=True)
def verify_email(ctx):
    limit(ctx, 'verify-email', 10)
    with transaction() as c:
        uid = tokens.consume(c, ctx.body.token, 'VERIFY_EMAIL')
        c.execute("UPDATE users SET email_verified=1 WHERE id=?", (uid,))
        audit.record(c, None, 'account.email_verified', 'user', uid)
    return {'ok': True}


@route("POST", "/api/v1/auth/password/forgot", summary="Request a password reset", tag="auth", body=EmailRequest,
       response=AcceptedOut, public=True, status=202)
def forgot_password(ctx):
    limit(ctx, 'forgot')
    email = ctx.body.email
    key = hashlib.sha256(email.encode()).hexdigest()
    if not rate_limiter.allow('forgot-email:' + key, 3, 3600):
        raise ApiError(429, 'rate_limited', 'Too many attempts. Please try again later.')
    raw = None
    with transaction() as c:
        u = c.execute("SELECT id FROM users WHERE lower(email)=? AND is_active=1", (email,)).fetchone()
        if u:
            raw = tokens.issue(c, u['id'], 'RESET_PASSWORD')
        audit.record(c, None, 'password.reset_requested', 'user', 'withheld')
    if raw:
        link_mail(email, 'RESET_PASSWORD', raw)
    return ACCEPTED


@route("POST", "/api/v1/auth/password/reset", summary="Use a password reset link", tag="auth", body=PasswordResetRequest,
       response=OkOut, public=True)
def reset_password(ctx):
    limit(ctx, 'reset', 10)
    with transaction() as c:
        uid = tokens.consume(c, ctx.body.token, 'RESET_PASSWORD')
        u = c.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
        if not u['is_active']:
            raise ApiError(422, 'invalid_token', 'This link is invalid or has expired. Request a new link.')
        tokens.validate_password(ctx.body.new_password, u['email'])
        c.execute('UPDATE users SET password_hash=? WHERE id=?', (hash_password(ctx.body.new_password), uid))
        sessions.revoke(c, uid)
        audit.record(c, None, 'password.reset', 'user', uid)
    return {'ok': True}


@route("POST", "/api/v1/auth/accept-invitation", summary="Set a password for a staff invitation", tag="auth",
       body=AcceptInvitationRequest, response=OkOut, public=True)
def accept_invitation(ctx):
    limit(ctx, 'accept-invitation', 10)
    with transaction() as c:
        uid = tokens.consume(c, ctx.body.token, 'INVITATION')
        u = c.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
        tokens.validate_password(ctx.body.password, u['email'])
        c.execute('UPDATE users SET password_hash=?,is_active=1,email_verified=1,name=? WHERE id=?',
                  (hash_password(ctx.body.password), ctx.body.name or u['name'], uid))
        audit.record(c, None, 'invitation.accepted', 'user', uid)
    return {'ok': True}


@route("POST", "/api/v1/auth/password/change", summary="Change password and revoke other sessions", tag="auth",
       body=PasswordChangeRequest, response=OkOut)
def change_password(ctx):
    limit(ctx, 'change-password', 10)
    with transaction() as c:
        u = c.execute('SELECT * FROM users WHERE id=?', (ctx.user.user_id,)).fetchone()
        if not verify_password(ctx.body.current_password, u['password_hash']):
            raise ApiError(422, 'invalid_password', 'Current password is incorrect')
        tokens.validate_password(ctx.body.new_password, u['email'])
        c.execute('UPDATE users SET password_hash=? WHERE id=?', (hash_password(ctx.body.new_password), u['id']))
        sessions.revoke(c, u['id'], except_id=ctx.user.session_id)
        c.execute("UPDATE one_time_tokens SET used_at=? WHERE user_id=? AND purpose='RESET_PASSWORD' AND used_at IS NULL",
                  (now_iso(), u['id']))
        audit.record(c, ctx.user, 'password.changed', 'user', u['id'])
    return {'ok': True}


@route("POST", "/api/v1/auth/refresh", summary="Rotate a valid session", tag="auth", response=SessionOut)
def refresh(ctx):
    limit(ctx, 'refresh', 30, 60)
    with transaction() as c:
        changed = c.execute('UPDATE sessions SET revoked_at=? WHERE id=? AND revoked_at IS NULL AND expires_at>?',
                            (now_iso(), ctx.user.session_id, now_iso())).rowcount
        if not changed:
            raise ApiError(401, 'unauthenticated', 'Sign in to continue')
        u = c.execute('SELECT * FROM users WHERE id=? AND is_active=1', (ctx.user.user_id,)).fetchone()
        if not u:
            raise ApiError(401, 'unauthenticated', 'Sign in to continue')
        result = session_response(c, ctx, ctx.user, _user_out(c,u))
        audit.record(c, ctx.user, 'session.refreshed', 'session', ctx.user.session_id)
        return result


def account_out(c, uid):
    u = c.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
    inst = c.execute('SELECT * FROM institutions WHERE id=?', (u['institution_id'],)).fetchone()
    return {'user': _user_out(c,u), 'email_verified': bool(u['email_verified']), 'phone': u['phone'],
            'created_at': u['created_at'], 'last_login_at': u['last_login_at'],
            'institution': institution_out(inst) if inst else None}


def institution_out(i):
    return {k: i[k] for k in ('id','aicte_permanent_id','name','state','trust_name','status','contact_email','address')}


@route('GET', '/api/v1/account', summary='Current account and contacts', tag='accounts', response=AccountOut)
def get_account(ctx):
    with reader() as c:
        return account_out(c, ctx.user.user_id)


@route('PATCH', '/api/v1/account', summary='Update account contacts', tag='accounts', body=AccountUpdate, response=AccountOut)
def update_account(ctx):
    changes = ctx.body.model_dump(exclude_unset=True)
    if changes.get('name', '') is None:
        raise ApiError(422, 'validation_error', 'Name cannot be empty')
    if not ctx.user.is_institution and {'address','contact_email'} & changes.keys():
        raise ApiError(403, 'forbidden', 'Only institution accounts can edit institution contacts')
    with transaction() as c:
        for key in ('name','phone'):
            if key in changes:
                c.execute(f'UPDATE users SET {key}=? WHERE id=?', (changes[key],ctx.user.user_id))
        for key in ('address','contact_email'):
            if key in changes:
                c.execute(f'UPDATE institutions SET {key}=? WHERE id=?', (changes[key],ctx.user.institution_id))
        audit.record(c, ctx.user, 'account.updated', 'user', ctx.user.user_id, {'fields': sorted(changes)})
        return account_out(c,ctx.user.user_id)


@route('GET', '/api/v1/account/sessions', summary='List active sessions', tag='accounts', response=list[SessionInfoOut])
def list_sessions(ctx):
    with reader() as c:
        return [{**{k: r[k] for k in ('id','created_at','last_seen_at','user_agent','ip_hint')},
                 'current': r['id']==ctx.user.session_id} for r in c.execute(
            'SELECT * FROM sessions WHERE user_id=? AND revoked_at IS NULL AND expires_at>? ORDER BY created_at DESC',
            (ctx.user.user_id, now_iso()))]


@route('DELETE', '/api/v1/account/sessions/{session_id}', summary='Revoke an owned session', tag='accounts', response=OkOut)
def revoke_session(ctx):
    with transaction() as c:
        if not c.execute('UPDATE sessions SET revoked_at=? WHERE id=? AND user_id=?',
                         (now_iso(),ctx.path['session_id'],ctx.user.user_id)).rowcount:
            raise not_found('Session')
        audit.record(c,ctx.user,'session.revoked','session',ctx.path['session_id'])
    return {'ok':True}


@route('POST', '/api/v1/account/sessions/revoke-others', summary='Revoke other sessions', tag='accounts', response=OkOut)
def revoke_other_sessions(ctx):
    with transaction() as c:
        sessions.revoke(c,ctx.user.user_id,except_id=ctx.user.session_id)
        audit.record(c,ctx.user,'sessions.revoked_others','user',ctx.user.user_id)
    return {'ok':True}
