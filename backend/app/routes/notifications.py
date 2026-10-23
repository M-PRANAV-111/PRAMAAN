from .. import features
from ..api import ApiError, not_found, route
from ..db import now_iso, reader, transaction
from ..schemas import NotificationOut, CountOut, OkOut

features.register('notifications')


def pagination(query, default=50):
    try:
        limit, offset = int(query.get('limit',default)), int(query.get('offset',0))
        if not 1 <= limit <= 200 or offset < 0:
            raise ValueError
        return limit,offset
    except ValueError:
        raise ApiError(422,'validation_error','Use limit 1–200 and a non-negative offset') from None


@route('GET','/api/v1/notifications',summary='List owned notifications',tag='notifications',response=list[NotificationOut],
       query={'unread':'Only unread','limit':'Up to 200','offset':'Offset'})
def list_notifications(ctx):
    limit,offset = pagination(ctx.query)
    unread = ctx.query.get('unread','false')
    if unread not in ('true','false'):
        raise ApiError(422,'validation_error','unread must be true or false')
    with reader() as c:
        rows = c.execute('SELECT * FROM notifications WHERE user_id=?' + (' AND read_at IS NULL' if unread=='true' else '') +
                         ' ORDER BY created_at DESC,rowid DESC LIMIT ? OFFSET ?', (ctx.user.user_id,limit,offset)).fetchall()
        return [{k:r[k] for k in NotificationOut.model_fields} for r in rows]


@route('GET','/api/v1/notifications/unread-count',summary='Count unread notifications',tag='notifications',response=CountOut)
def unread_count(ctx):
    with reader() as c:
        return {'count':c.execute('SELECT COUNT(*) FROM notifications WHERE user_id=? AND read_at IS NULL',
                                  (ctx.user.user_id,)).fetchone()[0]}


@route('POST','/api/v1/notifications/{notification_id}/read',summary='Mark owned notification read',tag='notifications',response=OkOut)
def read_notification(ctx):
    with transaction() as c:
        if not c.execute('UPDATE notifications SET read_at=COALESCE(read_at,?) WHERE id=? AND user_id=?',
                         (now_iso(),ctx.path['notification_id'],ctx.user.user_id)).rowcount:
            raise not_found('Notification')
    return {'ok':True}


@route('POST','/api/v1/notifications/read-all',summary='Mark all owned notifications read',tag='notifications',response=OkOut)
def read_all_notifications(ctx):
    with transaction() as c:
        c.execute('UPDATE notifications SET read_at=? WHERE user_id=? AND read_at IS NULL',(now_iso(),ctx.user.user_id))
    return {'ok':True}
