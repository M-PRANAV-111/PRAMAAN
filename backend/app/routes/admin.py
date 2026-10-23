"""Staff administration; account activation is independent from application scrutiny."""
import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone

from .. import audit, features, sessions, tokens
from ..api import ApiError, not_found, route
from ..config import get_settings
from ..db import new_id, now_iso, reader, transaction
from ..email import send_email
from ..notify import emit
from ..schemas import (RegistrationOut, AcceptRegistrationRequest, ReasonRequest, AdminUserOut,
                       InvitationRequest, AcceptedOut, SystemOut, Role)
from .accounts import ACCEPTED, institution_out, link_mail
from .system import ready


def registration_out(c, r):
    i = c.execute('SELECT * FROM institutions WHERE id=?',(r['institution_id'],)).fetchone()
    u = c.execute('SELECT * FROM users WHERE id=?',(r['user_id'],)).fetchone()
    decider = c.execute('SELECT name FROM users WHERE id=?',(r['decided_by'],)).fetchone()
    return {'id':r['id'],'institution':institution_out(i),'contact_name':u['name'],'email':u['email'],
            'email_verified':bool(u['email_verified']),'status':r['status'],'created_at':r['created_at'],
            'decided_by_name':decider['name'] if decider else None,'reason':r['reason']}


def user_out(c,u):
    i = c.execute('SELECT name FROM institutions WHERE id=?',(u['institution_id'],)).fetchone()
    return {**{k:u[k] for k in ('id','email','name','role','created_at','last_login_at')},
            'institution_name':i['name'] if i else None,'is_active':bool(u['is_active']),'email_verified':bool(u['email_verified'])}


@route('GET','/api/v1/admin/registrations',summary='List verified registration requests',tag='admin',roles=('ADMIN',),
       response=list[RegistrationOut],query={'status':'Registration status'})
def list_registrations(ctx):
    status = ctx.query.get('status')
    if status and status not in ('PENDING','ACCEPTED','DECLINED'):
        raise ApiError(422,'validation_error','Unknown registration status')
    with transaction() as c:
        rows = c.execute('SELECT r.* FROM registrations r JOIN users u ON u.id=r.user_id WHERE u.email_verified=1'+
                         (' AND r.status=?' if status else '')+' ORDER BY r.created_at', (status,) if status else ()).fetchall()
        audit.record(c,ctx.user,'admin.registrations_viewed','system','registrations')
        return [registration_out(c,r) for r in rows]


def decide_registration(ctx, status, reason):
    with transaction() as c:
        r = c.execute('SELECT * FROM registrations WHERE id=?',(ctx.path['registration_id'],)).fetchone()
        if not r:
            raise not_found('Registration')
        u = c.execute('SELECT * FROM users WHERE id=?',(r['user_id'],)).fetchone()
        if r['status']!='PENDING' or not u['email_verified']:
            raise ApiError(409,'registration_not_pending','Only verified pending registrations can be processed')
        c.execute('UPDATE registrations SET status=?,reason=?,decided_by=?,decided_at=? WHERE id=?',
                  (status,reason,ctx.user.user_id,now_iso(),r['id']))
        c.execute('UPDATE institutions SET status=? WHERE id=?',('ACTIVE' if status=='ACCEPTED' else 'DECLINED',r['institution_id']))
        c.execute('UPDATE users SET is_active=? WHERE id=?',(int(status=='ACCEPTED'),u['id']))
        audit.record(c,ctx.user,'registration.'+status.lower(),'registration',r['id'],
                     {'reason_hash':hashlib.sha256((reason or '').encode()).hexdigest()})
        if status=='ACCEPTED':
            emit(c,to_users=[u['id']],kind='REGISTRATION_ACCEPTED',title='Registration accepted',
                 body='Your institution account is ready.',link='/account')
        result = registration_out(c,c.execute('SELECT * FROM registrations WHERE id=?',(r['id'],)).fetchone())
    send_email(u['email'],'PRAMAAN: Registration '+status.lower(),
               'Your institution registration was '+status.lower()+'.\n'+(reason or '')+'\n'+get_settings().public_base_url+'/login')
    return result


@route('POST','/api/v1/admin/registrations/{registration_id}/accept',summary='Accept a verified registration',tag='admin',
       roles=('ADMIN',),body=AcceptRegistrationRequest,response=RegistrationOut)
def accept_registration(ctx):
    return decide_registration(ctx,'ACCEPTED',ctx.body.note)


@route('POST','/api/v1/admin/registrations/{registration_id}/decline',summary='Decline a registration with a reason',tag='admin',
       roles=('ADMIN',),body=ReasonRequest,response=RegistrationOut)
def decline_registration(ctx):
    return decide_registration(ctx,'DECLINED',ctx.body.reason)


@route('GET','/api/v1/admin/users',summary='List user accounts',tag='admin',roles=('ADMIN',),response=list[AdminUserOut],
       query={'role':'Role','active':'Active accounts'})
def list_users(ctx):
    role,active = ctx.query.get('role'),ctx.query.get('active')
    if (role and role not in Role.__args__) or (active is not None and active not in ('true','false')):
        raise ApiError(422,'validation_error','Invalid role or active filter')
    with transaction() as c:
        rows = c.execute('SELECT * FROM users ORDER BY created_at').fetchall()
        audit.record(c,ctx.user,'admin.users_viewed','system','users')
        return [user_out(c,u) for u in rows if (not role or u['role']==role) and
                (active is None or bool(u['is_active'])==(active=='true'))]


@route('POST','/api/v1/admin/invitations',summary='Invite a staff member',tag='admin',roles=('ADMIN',),
       body=InvitationRequest,response=AcceptedOut,status=202)
def invite_user(ctx):
    b = ctx.body
    raw = None
    with transaction() as c:
        if not c.execute('SELECT 1 FROM users WHERE lower(email)=?',(b.email,)).fetchone():
            uid = new_id('usr')
            c.execute('INSERT INTO users (id,email,name,role,password_hash,is_active,email_verified,created_at) '
                      'VALUES (?,?,?,?,?,0,0,?)',(uid,b.email,b.name,b.role,'!unusable-'+secrets.token_hex(16),now_iso()))
            raw = tokens.issue(c,uid,'INVITATION')
            audit.record(c,ctx.user,'invitation.created','user',uid,{'role':b.role})
        else:
            audit.record(c,ctx.user,'invitation.requested','user','withheld')
    if raw:
        link_mail(b.email,'INVITATION',raw)
    return ACCEPTED


def set_active(ctx,active):
    with transaction() as c:
        u = c.execute('SELECT * FROM users WHERE id=?',(ctx.path['user_id'],)).fetchone()
        if not u:
            raise not_found('User')
        if not active:
            if u['id']==ctx.user.user_id:
                raise ApiError(409,'self_deactivation','You cannot deactivate your own account')
            if u['role']=='ADMIN' and u['is_active'] and c.execute("SELECT COUNT(*) FROM users WHERE role='ADMIN' AND is_active=1").fetchone()[0]<=1:
                raise ApiError(409,'last_admin','The last active administrator cannot be deactivated')
            sessions.revoke(c,u['id'])
            c.execute('UPDATE one_time_tokens SET used_at=? WHERE user_id=? AND used_at IS NULL',(now_iso(),u['id']))
        elif not u['email_verified'] or (u['institution_id'] and not c.execute(
                "SELECT 1 FROM institutions WHERE id=? AND status='ACTIVE'",(u['institution_id'],)).fetchone()):
            raise ApiError(409,'account_not_ready','Complete email verification and registration first')
        c.execute('UPDATE users SET is_active=? WHERE id=?',(int(active),u['id']))
        payload = {} if active else {'reason_hash':hashlib.sha256(ctx.body.reason.encode()).hexdigest()}
        audit.record(c,ctx.user,'user.reactivated' if active else 'user.deactivated','user',u['id'],payload)
        return user_out(c,c.execute('SELECT * FROM users WHERE id=?',(u['id'],)).fetchone())


@route('POST','/api/v1/admin/users/{user_id}/deactivate',summary='Deactivate an account and revoke sessions',tag='admin',
       roles=('ADMIN',),body=ReasonRequest,response=AdminUserOut)
def deactivate_user(ctx):
    return set_active(ctx,False)


@route('POST','/api/v1/admin/users/{user_id}/reactivate',summary='Reactivate an eligible account',tag='admin',roles=('ADMIN',),response=AdminUserOut)
def reactivate_user(ctx):
    return set_active(ctx,True)


@route('GET','/api/v1/admin/system',summary='System health and worker activity',tag='admin',roles=('ADMIN','AUDITOR'),response=SystemOut)
def system_status(ctx):
    checks = json.loads(ready(ctx).body)['checks']
    s = get_settings()
    cutoff = (datetime.now(timezone.utc)-timedelta(days=1)).isoformat(timespec='seconds')
    with transaction() as c:
        counts = {r['state']:r['n'] for r in c.execute('SELECT state,COUNT(*) n FROM jobs GROUP BY state')}
        failed = c.execute("SELECT COUNT(*) FROM jobs WHERE state='FAILED' AND updated_at>?",(cutoff,)).fetchone()[0]
        audit.record(c,ctx.user,'admin.system_viewed','system','health')
    last = s.data_dir/'backups'/'last_success.json'
    try:
        last_ok = json.loads(last.read_text())['at']
    except (OSError, ValueError, KeyError):
        last_ok = None
    return {'checks':checks,'worker':{'threads':s.worker_threads,'queued':counts.get('QUEUED',0),
            'running':counts.get('RUNNING',0),'failed_last_24h':failed},'email_provider':s.email_provider,
            'backups':{'last_ok_at':last_ok,'target':'s3' if s.backup_s3_bucket else 'local'},
            'version':'2026.1','extras':features.system_extras()}
