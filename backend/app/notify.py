"""Recipient resolution with the same object visibility as application routes."""
from .config import get_settings
from .db import after_commit, new_id, now_iso
from .email import send_email


def emit(conn, *, to_users=None, to_role=None, to_institution=None, kind, title, body, link,
         application_id=None, finding_id=None):
    if not link.startswith('/') or link.startswith('//') or '\\' in link:
        raise ValueError('Notification links must be local paths')
    app = None
    if application_id:
        app = conn.execute('SELECT * FROM applications WHERE id=?', (application_id,)).fetchone()
        if app is None:
            raise ValueError('Unknown application')
    if finding_id:
        f = conn.execute('SELECT application_id FROM findings WHERE id=?', (finding_id,)).fetchone()
        if not app or not f or f['application_id'] != app['id']:
            raise ValueError('Finding and application must match')
    recipients = set(to_users or ())
    for u in conn.execute('SELECT * FROM users WHERE is_active=1'):
        if u['role'] == to_role or (to_institution is not None and u['institution_id'] == to_institution):
            recipients.add(u['id'])
    ids = []
    for uid in sorted(recipients):
        u = conn.execute('SELECT * FROM users WHERE id=? AND is_active=1', (uid,)).fetchone()
        if not u:
            continue
        if app and ((u['role']=='INSTITUTION' and u['institution_id'] != app['institution_id']) or
                    (u['role']!='INSTITUTION' and not app['submitted_at'])):
            continue
        nid = new_id('ntf')
        conn.execute('INSERT INTO notifications VALUES (?,?,?,?,?,?,?,?,?,NULL)',
                     (nid,uid,kind,title,body,link,application_id,finding_id,now_iso()))
        ids.append(nid)
        if get_settings().notify_email:
            email = u['email']
            # Only a generic notice goes to email; evidence remains behind application authorization.
            after_commit(conn, lambda email=email: send_email(email, 'PRAMAAN: New notification',
                         'An update is available in your account: ' + get_settings().public_base_url + link))
    return ids
