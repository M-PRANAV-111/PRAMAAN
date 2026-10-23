"""Role-scoped history and institution replies with explicit evidence ownership."""
from .. import audit, features
from ..api import ApiError, not_found, route
from ..db import new_id, now_iso, reader, transaction
from ..notify import emit
from ..schemas import TimelineEventOut, DocumentOut, ResponseRequest, ResponseOut
from .common import document_out, load_application, response_rows

features.register('timeline')
features.register('clarifications')
EVENTS = {
    'application.created':('APPLICATION_CREATED','Application created'),
    'document.uploaded':('DOCUMENT_UPLOADED','Document uploaded'),
    'document.processed':('PROCESSING_DONE','Document processing completed'),
    'job.failed':('PROCESSING_FAILED','Processing needs attention'),
    'validation.run':('VALIDATION_RUN','Validation run completed'),
    'finding.raised':('FINDING_RAISED','Finding raised'),
    'finding.resolved':('FINDING_RESOLVED','Finding resolved'),
    'finding.confirm':('OFFICER_DECISION','Officer recorded a decision'),
    'finding.dismiss':('OFFICER_DECISION','Officer recorded a decision'),
    'finding.escalate':('OFFICER_DECISION','Officer recorded a decision'),
    'finding.request_clarification':('CLARIFICATION_REQUESTED','Clarification requested'),
    'finding.response':('INSTITUTION_REPLIED','Institution replied'),
    'application.submitted':('SUBMITTED','Application submitted'),
    'report.downloaded':('REPORT_DOWNLOADED','Verification report downloaded'),
    'routing.updated':('ROUTING_UPDATED','Review routing updated'),
}


def timeline(c, p, app_id):
    load_application(c,p,app_id)
    out = []
    for e in c.execute('SELECT e.*,u.name FROM audit_events e LEFT JOIN users u ON u.id=e.actor_id '
                       'WHERE e.application_id=? ORDER BY e.ts,e.seq',(app_id,)):
        if e['action'] not in EVENTS:
            continue
        kind,title = EVENTS[e['action']]
        # Assignment details are an oversight concern; institutions get no staff-only routing data.
        if p.is_institution and kind=='ROUTING_UPDATED':
            continue
        detail = ''
        if e['object_type']=='finding':
            f = c.execute('SELECT title FROM findings WHERE id=? AND application_id=?',(e['object_id'],app_id)).fetchone()
            detail = f['title'] if f else ''
        elif e['object_type']=='document':
            d = c.execute('SELECT original_name FROM documents WHERE id=? AND application_id=?',(e['object_id'],app_id)).fetchone()
            detail = d['original_name'] if d else ''
        out.append({'id':f"audit_{e['seq']}",'at':e['ts'],'kind':kind,'title':title,'detail':detail,
                    'actor_name':e['name'] or ('System' if e['actor_id']=='system' else None),
                    'actor_role':e['actor_role'],'link':f'/applications/{app_id}'})
    # Older databases predate finding audit events. Include real historical rows without inventing actors.
    existing = {(r['action'],r['object_id']) for r in c.execute('SELECT action,object_id FROM audit_events WHERE application_id=?',(app_id,))}
    for f in c.execute('SELECT * FROM findings WHERE application_id=?',(app_id,)):
        for action,at in [('finding.raised',f['created_at']),('finding.resolved',f['resolved_at'])]:
            if at and (action,f['id']) not in existing:
                kind,title=EVENTS[action]
                out.append({'id':f"{kind}_{f['id']}",'at':at,'kind':kind,'title':title,'detail':f['title'],
                            'actor_name':'System','actor_role':'SYSTEM','link':f'/applications/{app_id}'})
    return sorted(out,key=lambda e:e['at'])  # stable: preserve numeric audit sequence for same-second events


@route('GET','/api/v1/applications/{application_id}/timeline',summary='Application activity visible to the caller',
       tag='tracking',response=list[TimelineEventOut])
def application_timeline(ctx):
    with reader() as c:
        return timeline(c,ctx.user,ctx.path['application_id'])


@route('GET','/api/v1/applications/{application_id}/documents/history',summary='All document versions',tag='tracking',response=list[DocumentOut])
def document_history(ctx):
    with reader() as c:
        a=load_application(c,ctx.user,ctx.path['application_id'])
        return [document_out(d,c) for d in c.execute('SELECT * FROM documents WHERE application_id=? ORDER BY uploaded_at,rowid',(a['id'],))]


@route('POST','/api/v1/findings/{finding_id}/responses',summary='Reply to a finding with optional supporting evidence',
       tag='tracking',roles=('INSTITUTION',),body=ResponseRequest,response=ResponseOut)
def respond_to_finding(ctx):
    with transaction() as c:
        f=c.execute('SELECT * FROM findings WHERE id=?',(ctx.path['finding_id'],)).fetchone()
        if not f:
            raise not_found('Finding')
        a=load_application(c,ctx.user,f['application_id'])
        if ctx.body.document_id and not c.execute('SELECT 1 FROM documents WHERE id=? AND application_id=?',
                                                 (ctx.body.document_id,a['id'])).fetchone():
            raise not_found('Document')
        rid=new_id('rsp')
        c.execute('INSERT INTO finding_responses VALUES (?,?,?,?,?,?)',
                  (rid,f['id'],ctx.user.user_id,ctx.body.text,ctx.body.document_id,now_iso()))
        audit.record(c,ctx.user,'finding.response','finding',f['id'],{'response_id':rid,'document_id':ctx.body.document_id},a['id'])
        recipients=[r[0] for r in c.execute("SELECT DISTINCT reviewer_id FROM reviews WHERE finding_id=? AND decision='REQUEST_CLARIFICATION'",(f['id'],))]
        emit(c,to_users=recipients,kind='INSTITUTION_REPLIED',title='Institution replied',body='A clarification response is available.',
             link=f"/applications/{a['id']}",application_id=a['id'],finding_id=f['id'])
        return next(r for r in response_rows(c,f['id']) if r['id']==rid)
