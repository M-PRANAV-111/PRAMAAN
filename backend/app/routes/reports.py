import io
from datetime import datetime, timezone

from starlette.responses import StreamingResponse

from .. import audit, features
from ..api import route
from ..db import transaction
from ..reports.verification_report import render_report
from .applications import get_application, list_verifications
from .common import finding_out, load_application
from .tracking import timeline

features.register('reports')


@route('GET','/api/v1/applications/{application_id}/report',summary='Download the verification report',tag='reports',raw='application/pdf')
def application_report(ctx):
    # A single read snapshot covers findings, history and the captured audit head.
    with transaction() as c:
        app=load_application(c,ctx.user,ctx.path['application_id'])
        detail=get_application(ctx)
        findings=[finding_out(c,f,ctx.user) for f in c.execute('SELECT * FROM findings WHERE application_id=? ORDER BY created_at,rowid',(app['id'],))]
        for finding in findings:
            for evidence in finding['evidence']:
                # Fill provenance only from this application's actual stored claim.
                field=evidence.get('field') or finding['proof'].get('detail',{}).get('field')
                claim=c.execute('SELECT * FROM claims WHERE document_id=? AND application_id=? AND field=?',
                                (evidence.get('document_id'),app['id'],field)).fetchone()
                if claim:
                    for key,value in [('value',claim['value_raw']),('extractor',claim['extractor']),('confidence',claim['confidence'])]:
                        if evidence.get(key) is None:
                            evidence[key]=value
        verifications=list_verifications(ctx)
        events=timeline(c,ctx.user,app['id'])
        audit.record(c,ctx.user,'report.downloaded','application',app['id'],{},app['id'])
        head=c.execute('SELECT hash FROM audit_events ORDER BY seq DESC LIMIT 1').fetchone()[0]
        pdf=render_report(detail,findings,verifications,events,head)
    name=f"PRAMAAN-{app['id']}-{datetime.now(timezone.utc).date().isoformat()}.pdf"
    return StreamingResponse(io.BytesIO(pdf),media_type='application/pdf',headers={'Content-Disposition':f'attachment; filename="{name}"'})
