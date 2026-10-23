"""Low-cardinality metrics and logs that exclude URLs, tokens and document content."""
import hashlib
import hmac
import json
import logging
import threading
from collections import Counter

from starlette.responses import Response

from .api import ApiError, route
from .config import get_settings
from .db import reader

_requests = Counter()
_lock = threading.Lock()
access = logging.getLogger('pramaan.access')


def record_request(request, response, rid, milliseconds):
    template = getattr(request.state,'route_template','unmatched')
    uid = getattr(request.state,'user_id',None)
    uid_hash = hmac.new(get_settings().jwt_secret.encode(),uid.encode(),hashlib.sha256).hexdigest()[:16] if uid else None
    with _lock:
        _requests[(request.method,template,response.status_code)] += 1
    data={'request_id':rid,'method':request.method,'route':template,'status':response.status_code,
          'ms':round(milliseconds,2),'user_id_hash':uid_hash}
    if get_settings().log_format=='json':
        access.info(json.dumps(data,separators=(',',':')))
    else:
        access.info('request id=%s method=%s route=%s status=%s ms=%.1f user=%s',
                    rid,request.method,template,response.status_code,milliseconds,uid_hash)


@route('GET','/api/v1/metrics',summary='Prometheus metrics protected by a separate token',tag='system',public=True,
       raw='text/plain')
def metrics(ctx):
    expected = get_settings().metrics_token
    if not expected:
        raise ApiError(404,'not_found','Metrics are disabled')
    actual = ctx.request.headers.get('authorization','')
    if not hmac.compare_digest(actual,'Bearer '+expected):
        raise ApiError(401,'unauthenticated','Metrics token required')
    lines=['# TYPE pramaan_requests_total counter']
    with _lock:
        for (method,path,status),count in sorted(_requests.items()):
            lines.append(f'pramaan_requests_total{{method="{method}",route="{path}",status="{status}"}} {count}')
    with reader() as c:
        depth=c.execute("SELECT COUNT(*) FROM jobs WHERE state='QUEUED'").fetchone()[0]
        stages=c.execute('SELECT stage_code,SUM(seconds) total,COUNT(*) n FROM job_stage_durations GROUP BY stage_code').fetchall()
        failures=c.execute('SELECT COUNT(*) FROM email_failures').fetchone()[0]
    lines+=['# TYPE pramaan_queue_depth gauge',f'pramaan_queue_depth {depth}',
            '# TYPE pramaan_email_failures_total counter',f'pramaan_email_failures_total {failures}',
            '# TYPE pramaan_job_stage_seconds summary']
    for r in stages:
        lines += [f'pramaan_job_stage_seconds_sum{{stage_code="{r["stage_code"]}"}} {r["total"]}',
                  f'pramaan_job_stage_seconds_count{{stage_code="{r["stage_code"]}"}} {r["n"]}']
    return Response('\n'.join(lines)+'\n',media_type='text/plain; version=0.0.4')


def scrub_event(event,hint):
    # Never send request data, cookies, breadcrumbs, user details, locals or exception messages.
    for key in ('request','user','breadcrumbs','extra','contexts'):
        event.pop(key,None)
    for value in event.get('exception',{}).get('values',[]):
        value['value']=value.get('type','Exception')
        for frame in value.get('stacktrace',{}).get('frames',[]):
            frame.pop('vars',None)
    return event


def configure():
    # Uvicorn's stock access logger includes query strings, which can contain one-time tokens.
    logging.getLogger('uvicorn.access').disabled=True
    if not access.handlers:
        handler=logging.StreamHandler()
        handler.setFormatter(logging.Formatter('%(message)s'))
        access.addHandler(handler)
        access.propagate=False
    access.setLevel(logging.INFO)
    if get_settings().sentry_dsn:
        import sentry_sdk
        sentry_sdk.init(dsn=get_settings().sentry_dsn,send_default_pii=False,before_send=scrub_event,
                        include_local_variables=False,default_integrations=False)
