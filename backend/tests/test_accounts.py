import hashlib
import secrets
import time

import requests
from tests.core_support import CoreApiCase, PASSWORD


class AccountTests(CoreApiCase):
    def test_registration_verify_accept_login_and_duplicates(self):
        b=self.register_body()
        start=time.perf_counter()
        first=self.client.post(self.base+'/auth/register',json=b)
        first_time=time.perf_counter()-start
        self.assertEqual(first.status_code,202,first.text)
        admin=self.session('admin@aicte.synthetic.in')
        self.assertNotIn(b['email'],[r['email'] for r in admin.get(self.base+'/admin/registrations').json()])
        self.assertEqual(self.client.post(self.base+'/auth/login',json={'email':b['email'],'password':b['password']}).status_code,401)
        raw=self.mail_token(b['email'],'Verify')
        with self.sql() as c:
            token=c.execute('SELECT * FROM one_time_tokens WHERE token_hash=?',(hashlib.sha256(raw.encode()).hexdigest(),)).fetchone()
            self.assertIsNotNone(token)
            self.assertNotIn(raw,str(tuple(token)))
            count=c.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        start=time.perf_counter()
        duplicate=self.client.post(self.base+'/auth/register',json=b)
        duplicate_time=time.perf_counter()-start
        self.assertEqual(duplicate.content,first.content)
        self.assertLess(abs(first_time-duplicate_time),.5)
        other={**b,'email':'another-'+b['email']}
        self.assertEqual(self.client.post(self.base+'/auth/register',json=other).content,first.content)
        with self.sql() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM users').fetchone()[0],count)
        self.assertEqual(self.client.post(self.base+'/auth/verify-email',json={'token':raw}).status_code,200)
        self.assertEqual(self.client.post(self.base+'/auth/verify-email',json={'token':raw}).status_code,422)
        rid=next(r['id'] for r in admin.get(self.base+'/admin/registrations?status=PENDING').json() if r['email']==b['email'])
        self.assertEqual(admin.post(f'{self.base}/admin/registrations/{rid}/accept',json={}).json()['status'],'ACCEPTED')
        self.assertEqual(self.client.post(self.base+'/auth/login',json={'email':b['email'],'password':b['password']}).status_code,200)
        account=self.client.get(self.base+'/account').json()
        self.assertTrue(account['email_verified'])
        self.assertEqual(account['institution']['status'],'ACTIVE')
        changed=self.client.patch(self.base+'/account',json={'name':'Changed contact','phone':'+91 1234','address':'Synthetic address','contact_email':'contact@example.test'})
        self.assertEqual(changed.status_code,200,changed.text)
        self.assertEqual(changed.json()['user']['name'],'Changed contact')
        self.assertEqual(self.client.get(self.base+'/notifications/unread-count').json()['count'],1)

    def test_password_policy_and_registration_rate_limit(self):
        b=self.register_body()
        for password in ['short','password123456',b['email'].split('@')[0]+'-123456789']:
            self.assertEqual(self.client.post(self.base+'/auth/register',json={**b,'password':password}).status_code,422)
        for _ in range(6):
            r=self.client.post(self.base+'/auth/register',json=b)
        self.assertEqual(r.status_code,429)

    def test_reset_generic_expired_wrong_used_and_session_revocation(self):
        email='officer@aicte.synthetic.in'
        signed=self.session(email)
        r=self.client.post(self.base+'/auth/password/forgot',json={'email':email})
        unknown=self.client.post(self.base+'/auth/password/forgot',json={'email':'missing@example.test'})
        self.assertEqual(r.content,unknown.content)
        raw=self.mail_token(email,'Reset')
        new=secrets.token_urlsafe(24)
        self.assertEqual(self.client.post(self.base+'/auth/password/reset',json={'token':secrets.token_urlsafe(32),'new_password':new}).status_code,422)
        with self.sql() as c:
            c.execute("UPDATE one_time_tokens SET expires_at='2000-01-01' WHERE token_hash=?",(hashlib.sha256(raw.encode()).hexdigest(),))
        self.assertEqual(self.client.post(self.base+'/auth/password/reset',json={'token':raw,'new_password':new}).status_code,422)
        self.client.post(self.base+'/auth/password/forgot',json={'email':email})
        # Wait until the second email arrives, rather than reusing the first message.
        end=time.monotonic()+5
        while time.monotonic()<end:
            fresh=self.mail_token(email,'Reset')
            if fresh!=raw:
                break
            time.sleep(.05)
        self.assertNotEqual(fresh,raw)
        self.assertEqual(self.client.post(self.base+'/auth/password/reset',json={'token':fresh,'new_password':new}).status_code,200)
        self.assertEqual(signed.get(self.base+'/auth/me').status_code,401)
        self.assertEqual(self.client.post(self.base+'/auth/password/reset',json={'token':fresh,'new_password':new}).status_code,422)
        self.assertEqual(self.client.post(self.base+'/auth/login',json={'email':email,'password':new}).status_code,200)
        self.assertEqual(self.client.post(self.base+'/auth/password/change',json={'current_password':new,'new_password':PASSWORD}).status_code,200)

    def test_sessions_change_refresh_revoke_logout(self):
        email='auditor@aicte.synthetic.in'
        a,b=self.session(email),self.session(email)
        new=secrets.token_urlsafe(24)
        self.assertEqual(a.post(self.base+'/auth/password/change',json={'current_password':PASSWORD,'new_password':new}).status_code,200)
        self.assertEqual(b.get(self.base+'/account').status_code,401)
        old=a.cookies.get('pramaan_session')
        self.assertEqual(a.post(self.base+'/auth/refresh').status_code,200)
        self.assertNotEqual(old,a.cookies.get('pramaan_session'))
        self.assertEqual(requests.get(self.base+'/account',headers={'Authorization':'Bearer '+old}).status_code,401)
        rows=a.get(self.base+'/account/sessions').json()
        self.assertEqual(len(rows),1)
        self.assertTrue(rows[0]['current'])
        self.assertTrue(rows[0]['ip_hint'].endswith('/24'))
        self.assertLessEqual(len(rows[0]['user_agent']),120)
        self.assertEqual(a.delete(self.base+'/account/sessions/not-owned').status_code,404)
        self.assertEqual(a.post(self.base+'/account/sessions/revoke-others').status_code,200)
        self.assertEqual(a.post(self.base+'/auth/password/change',json={'current_password':new,'new_password':PASSWORD}).status_code,200)
        self.assertEqual(a.delete(self.base+'/account/sessions/'+rows[0]['id']).status_code,200)
        self.assertEqual(a.get(self.base+'/auth/me').status_code,401)
        a=self.session(email)
        token=a.cookies.get('pramaan_session')
        self.assertEqual(a.post(self.base+'/auth/logout').status_code,200)
        self.assertEqual(requests.get(self.base+'/account',headers={'Authorization':'Bearer '+token}).status_code,401)

    def test_invitations_deactivation_guards_and_admin_roles(self):
        admin=self.session('admin@aicte.synthetic.in')
        auditor=self.session('auditor@aicte.synthetic.in')
        b={'email':secrets.token_hex(6)+'@example.test','name':'Synthetic officer','role':'OFFICER'}
        self.assertEqual(auditor.post(self.base+'/admin/invitations',json=b).status_code,403)
        self.assertEqual(admin.post(self.base+'/admin/invitations',json=b).status_code,202)
        raw=self.mail_token(b['email'],'invitation')
        password=secrets.token_urlsafe(24)
        self.assertEqual(self.client.post(self.base+'/auth/accept-invitation',json={'token':raw,'password':password}).status_code,200)
        self.assertEqual(self.client.post(self.base+'/auth/accept-invitation',json={'token':raw,'password':password}).status_code,422)
        self.assertEqual(self.client.post(self.base+'/auth/login',json={'email':b['email'],'password':password}).status_code,200)
        uid=self.client.get(self.base+'/account').json()['user']['id']
        result=admin.post(f'{self.base}/admin/users/{uid}/deactivate',json={'reason':'Synthetic test deactivation'})
        self.assertEqual(result.status_code,200,result.text)
        self.assertFalse(result.json()['is_active'])
        self.assertEqual(self.client.get(self.base+'/account').status_code,401)
        self.assertTrue(admin.post(f'{self.base}/admin/users/{uid}/reactivate').json()['is_active'])
        own=admin.get(self.base+'/account').json()['user']['id']
        self.assertEqual(admin.post(f'{self.base}/admin/users/{own}/deactivate',json={'reason':'Cannot disable own account'}).status_code,409)
        self.assertEqual(auditor.get(self.base+'/admin/users').status_code,403)
        self.assertEqual(auditor.get(self.base+'/admin/system').status_code,200)
        self.assertEqual(admin.get(self.base+'/admin/users?role=BAD').status_code,422)

    def test_decline_requires_reason_preserves_rows(self):
        b=self.register_body()
        self.client.post(self.base+'/auth/register',json=b)
        self.client.post(self.base+'/auth/verify-email',json={'token':self.mail_token(b['email'],'Verify')})
        admin=self.session('admin@aicte.synthetic.in')
        rid=next(r['id'] for r in admin.get(self.base+'/admin/registrations').json() if r['email']==b['email'])
        self.assertEqual(admin.post(f'{self.base}/admin/registrations/{rid}/decline',json={'reason':'   short '}).status_code,422)
        self.assertEqual(admin.post(f'{self.base}/admin/registrations/{rid}/decline',json={'reason':'Please provide a valid institution ID.'}).json()['status'],'DECLINED')
        with self.sql() as c:
            self.assertEqual(c.execute('SELECT is_active FROM users WHERE email=?',(b['email'],)).fetchone()[0],0)

    def test_public_token_limits_and_forgot_email_limit(self):
        for path,body in [('/auth/verify-email',{'token':secrets.token_urlsafe(32)}),
                          ('/auth/accept-invitation',{'token':secrets.token_urlsafe(32),'password':secrets.token_urlsafe(24)}),
                          ('/auth/password/reset',{'token':secrets.token_urlsafe(32),'new_password':secrets.token_urlsafe(24)})]:
            for _ in range(11):
                r=self.client.post(self.base+path,json=body)
            self.assertEqual(r.status_code,429,path)
        for _ in range(4):
            r=self.client.post(self.base+'/auth/password/forgot',json={'email':'limit@example.test'})
        self.assertEqual(r.status_code,429)

    def test_refresh_rate_limit(self):
        account=self.session('nodal@shakti.synthetic.in')
        for _ in range(30):
            self.assertEqual(account.post(self.base+'/auth/refresh').status_code,200)
        self.assertEqual(account.post(self.base+'/auth/refresh').status_code,429)
