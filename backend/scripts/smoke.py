"""Contract-wide smoke against a disposable, real seeded server (never a supplied URL).

Run from backend: python -m scripts.smoke
Public operations do not require a session. Metrics requires its own token. A
real synthetic benchmark is generated before exercising its download endpoint.
422 is checked for JSON/multipart bodies and validated query parameters; it is
not invented for operations that accept no input. Fixture SQL is confined to the
temporary test database, and production handlers/processing are never mocked.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import subprocess
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.core_support import CoreApiCase, PASSWORD

ROLES = {
    'INSTITUTION': 'nodal@godavari.synthetic.in',
    'OFFICER': 'officer@aicte.synthetic.in',
    'ADMIN': 'admin@aicte.synthetic.in',
    'AUDITOR': 'auditor@aicte.synthetic.in',
}
QUERY_BAD = {'listApplications': {'limit': '-1'}, 'listNotifications': {'unread': 'bad'},
             'listUsers': {'role': 'bad'}, 'listRegistrations': {'status': 'bad'}}


class Smoke(CoreApiCase):
    def check(self, response, expected, label):
        self.assertEqual(response.status_code, expected, f'{label}: expected {expected}, got {response.status_code}: {response.text[:200]}')
        self.checks += 1

    def fresh(self, role=None):
        self.ip = '10.' + '.'.join(str(x) for x in secrets.token_bytes(3))
        if role:
            return self.session(ROLES[role])
        s = requests.Session()
        s.headers.update({'X-Requested-With': 'pramaan', 'X-Forwarded-For': self.ip})
        return s

    def registration(self, verify=True):
        s = self.fresh()
        body = self.register_body()
        self.check(s.post(self.base+'/auth/register', json=body), 202, 'fixture registration')
        raw = self.mail_token(body['email'], 'Verify')
        if verify:
            self.check(s.post(self.base+'/auth/verify-email', json={'token': raw}), 200, 'fixture verification')
        with self.sql() as c:
            rid = c.execute('SELECT r.id FROM registrations r JOIN users u ON u.id=r.user_id WHERE u.email=?', (body['email'],)).fetchone()[0]
        return body, raw, rid

    def invitation(self):
        email = secrets.token_hex(12)+'@example.test'
        self.check(self.fresh('ADMIN').post(self.base+'/admin/invitations', json={'email':email, 'name':'Synthetic smoke officer', 'role':'OFFICER'}), 202, 'fixture invitation')
        return email, self.mail_token(email, 'invitation')

    def proposal(self, actor):
        rule = next(r for r in actor.get(self.base+'/rules').json()['rules'] if r.get('params'))
        key, value = next((k,v) for k,v in rule['params'].items() if isinstance(v,(int,float)))
        return {'changes': {rule['id']: {key: value+1}}, 'note': 'Synthetic smoke governance change'}

    def prepare(self, op, role, actor):
        ids = dict(self.ids)
        body = None
        files = None
        if op == 'login':
            body = {'email': ROLES.get(role, ROLES['OFFICER']), 'password': PASSWORD}
        elif op == 'register': body = self.register_body()
        elif op == 'verifyEmail': body = {'token': self.registration(False)[1]}
        elif op == 'forgotPassword': body = {'email': secrets.token_hex(10)+'@example.test'}
        elif op == 'resetPassword':
            registered, _, rid = self.registration()
            self.check(self.fresh('ADMIN').post(f'{self.base}/admin/registrations/{rid}/accept', json={}),200,'fixture accept registration')
            self.check(self.fresh().post(self.base+'/auth/password/forgot', json={'email':registered['email']}),202,'fixture forgot')
            body = {'token': self.mail_token(registered['email'], 'Reset'), 'new_password': secrets.token_urlsafe(24)}
        elif op == 'acceptInvitation': body = {'token': self.invitation()[1], 'password': secrets.token_urlsafe(24)}
        elif op == 'changePassword': body = {'current_password': PASSWORD, 'new_password': PASSWORD}
        elif op == 'updateAccount': body = {'name':'Synthetic smoke contact'}
        elif op == 'createApplication': body = {'category':'EOA_EXISTING', 'academic_year':'2027-28'}
        elif op == 'submitApplication':
            created = actor.post(self.base+'/applications', json={'category':'EOA_EXISTING','academic_year':'2028-29'})
            self.check(created,201,'fixture draft')
            a = created.json()['id']
            j = actor.post(f'{self.base}/applications/{a}/validate').json()['id']
            result = self.wait_job(actor,j)
            self.assertEqual(result['state'],'DONE',str(result))
            ids['application_id'] = a
        elif op == 'uploadDocument':
            body = {'doc_type':'affidavit'}
            files = {'file': ('synthetic.pdf', (self.demo/'D_Affidavit_2026-27.pdf').read_bytes(), 'application/pdf')}
        elif op == 'reviewFinding': body = {'decision':'REQUEST_CLARIFICATION', 'reason':'Synthetic smoke requests document clarification.'}
        elif op == 'respondToFinding': body = {'text':'Synthetic smoke institution clarification response.'}
        elif op == 'proposeRules': body = self.proposal(actor)
        elif op == 'activateRules':
            other = self.session('admin2@aicte.synthetic.in')
            r = other.post(self.base+'/rules/proposals',json=self.proposal(other))
            self.check(r,201,'fixture rule proposal')
            ids['version_id'] = r.json()['version']['id']
        elif op in ('acceptRegistration','declineRegistration'):
            ids['registration_id'] = self.registration()[2]
            body = {} if op == 'acceptRegistration' else {'reason':'Synthetic smoke registration needs corrected details.'}
        elif op == 'inviteUser': body = {'email':secrets.token_hex(12)+'@example.test','name':'Synthetic invite','role':'OFFICER'}
        elif op in ('deactivateUser','reactivateUser'):
            email, token = self.invitation()
            self.check(self.fresh().post(self.base+'/auth/accept-invitation',json={'token':token,'password':secrets.token_urlsafe(24)}),200,'fixture accept invitation')
            ids['user_id'] = next(u['id'] for u in actor.get(self.base+'/admin/users').json() if u['email']==email)
            body = {'reason':'Synthetic smoke account lifecycle check.'}
            if op == 'reactivateUser': self.check(actor.post(f"{self.base}/admin/users/{ids['user_id']}/deactivate",json=body),200,'fixture deactivate')
        elif op == 'revokeSession': ids['session_id'] = actor.get(self.base+'/account/sessions').json()[0]['id']
        elif op == 'readNotification':
            uid = actor.get(self.base+'/auth/me').json()['id']
            ids['notification_id'] = 'ntf_smoke_'+secrets.token_hex(8)
            with self.sql() as c:
                c.execute("INSERT INTO notifications (id,user_id,kind,title,body,link,created_at) VALUES (?,?,'SMOKE','Synthetic smoke','Synthetic fixture','/account','2026-01-01')", (ids['notification_id'],uid))
        return ids, body, files

    def request(self, actor, method, path, ids, body=None, files=None, **kwargs):
        path = re.sub(r'\{([^}]+)\}', lambda m: str(ids.get(m[1], 'missing-smoke-object')), path)
        if files:
            return actor.request(method,self.base.removesuffix('/api/v1')+path,data=body,files=files,timeout=60,**kwargs)
        return actor.request(method,self.base.removesuffix('/api/v1')+path,json=body,timeout=60,**kwargs)

    def run_matrix(self):
        self.checks = 0
        admin = self.fresh('ADMIN')
        aid = self.app_id(admin,'Godavari')
        detail = admin.get(f'{self.base}/applications/{aid}').json()
        job = admin.post(f'{self.base}/applications/{aid}/validate').json()['id']
        self.assertEqual(self.wait_job(admin,job)['state'],'DONE')
        finding = admin.get(f'{self.base}/applications/{aid}/findings').json()[0]['id']
        self.ids = {'application_id':aid,'document_id':detail['documents'][0]['id'],'finding_id':finding,'job_id':job,'page':1}
        print('Generating actual synthetic benchmark for download smoke...', flush=True)
        subprocess.run([sys.executable,'-m','eval.benchmark','--repeats','1','--out',str(Path(self.tmp.name)/'benchmark/latest.json')],
                       cwd=Path(__file__).resolve().parents[1],check=True,stdout=subprocess.DEVNULL,timeout=300)
        contract = json.loads((Path(__file__).resolve().parents[2]/'contracts/openapi.json').read_text(encoding='utf-8'))
        print('Operation | OUT | INSTITUTION | OFFICER | ADMIN | AUDITOR | invalid | foreign')
        failures = []
        operations = 0
        for path, methods in contract['paths'].items():
            for method, spec in methods.items():
                operations += 1
                op = spec['operationId']
                cells = []
                try:
                    public = spec.get('security') == []
                    metrics = op == 'metrics'
                    allowed = spec.get('x-roles', ['any authenticated'])
                    for role in (None,*ROLES):
                        actor = self.fresh(role)
                        permitted = public or (role and ('any authenticated' in allowed or role in allowed))
                        if metrics:
                            self.check(self.request(actor,method,path,self.ids),401,op+' separate token')
                            self.check(self.request(actor,method,path,self.ids,headers={'Authorization':'Bearer '+self.metrics_token}),200,op+' token')
                            cells.append('401/200(token)')
                        elif not permitted:
                            status = 401 if role is None else 403
                            self.check(self.request(actor,method,path,self.ids),status,op+' '+str(role))
                            cells.append(str(status))
                        else:
                            ids,body,files = self.prepare(op,role,actor)
                            expected = next(int(s) for s in spec['responses'] if s.isdigit() and int(s)<300)
                            response = self.request(actor,method,path,ids,body,files)
                            self.check(response,expected,op+' '+str(role))
                            cells.append(str(expected))
                            if op in ('uploadDocument','validateApplication'):
                                jid = response.json()['job']['id'] if op=='uploadDocument' else response.json()['id']
                                result = self.wait_job(actor,jid)
                                self.assertEqual(result['state'],'DONE',str(result))
                    valid_role = next((r for r in ROLES if 'any authenticated' in allowed or r in allowed), 'ADMIN')
                    actor = self.fresh(valid_role)
                    if 'requestBody' in spec:
                        self.check(self.request(actor,method,path,self.ids,[]),422,op+' invalid body')
                        cells.append('422')
                    elif op in QUERY_BAD:
                        self.check(self.request(actor,method,path,self.ids,params=QUERY_BAD[op]),422,op+' invalid query')
                        cells.append('422')
                    else: cells.append('n/a')
                    scoped = any('{'+k+'}' in path for k in ('application_id','document_id','job_id','finding_id'))
                    if scoped and ('any authenticated' in allowed or 'INSTITUTION' in allowed):
                        other = self.session('nodal@shakti.synthetic.in')
                        body = {'text':'Synthetic foreign ownership check.'} if op=='respondToFinding' else None
                        # Upload checks ownership before requiring a file.
                        self.check(self.request(other,method,path,self.ids,body),404,op+' foreign institution')
                        cells.append('404')
                    elif op in ('readNotification','revokeSession'):
                        other = self.session('nodal@shakti.synthetic.in')
                        self.check(self.request(other,method,path,ids),404,op+' foreign owner')
                        cells.append('404')
                    else: cells.append('n/a')
                except Exception as exc:
                    failures.append(f'{op}: {exc}')
                    cells.append('FAIL')
                print(op+' | '+' | '.join(cells), flush=True)
        print(f'{operations} operations; {self.checks} assertions passed; {len(failures)} failed operations.')
        print('Public routes permit signed-out callers; metrics uses a separate token; n/a means no applicable input/ownership check.')
        for failure in failures: print('FAIL '+failure)
        return bool(failures)


def main():
    # Never inherit a developer's live database, provider or telemetry settings.
    os.environ.update({'APP_ENV':'test','DATABASE_PATH':'','EMAIL_PROVIDER':'console',
                       'AI_PROVIDER':'none','AI_TEST_FAULT':'','SENTRY_DSN':'',
                       'BACKUP_SCHEDULE':'false','NOTIFY_EMAIL':'false',
                       'PUBLIC_BASE_URL':'http://localhost:8000','COOKIE_SECURE':'false'})
    case = Smoke()
    case.setUpClass()
    try:
        case.setUp()
        return int(case.run_matrix())
    finally:
        case.tearDownClass()


if __name__ == '__main__':
    raise SystemExit(main())
