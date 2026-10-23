"""Real-server integration harness with isolated synthetic databases."""
import email
import email.policy
import os
import re
import secrets
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

import requests
from tests.test_api import ApiTestCase, BACKEND, PASSWORD, _free_port

_template=None


class CoreApiCase(ApiTestCase):
    @classmethod
    def setUpClass(cls):
        global _template
        if _template is None:
            _template=tempfile.TemporaryDirectory()
            env={**os.environ,'DATA_DIR':_template.name,'SEED_DEMO_PASSWORD':PASSWORD,'APP_ENV':'test','EMAIL_PROVIDER':'console'}
            result=subprocess.run([sys.executable,'-m','synthetic.seed'],cwd=BACKEND,env=env,capture_output=True,text=True)
            if result.returncode:
                raise RuntimeError(result.stderr)
        cls.tmp=tempfile.TemporaryDirectory()
        shutil.copytree(_template.name,cls.tmp.name,dirs_exist_ok=True)
        cls.metrics_token=secrets.token_urlsafe(24)
        env={**os.environ,'DATA_DIR':cls.tmp.name,'WORKER_THREADS':'1','LOGIN_RATE_PER_MINUTE':'1000',
             'UPLOAD_RATE_PER_MINUTE':'1000','APP_ENV':'test','TRUST_PROXY':'true','EMAIL_PROVIDER':'console',
             'METRICS_TOKEN':cls.metrics_token,'LOG_FORMAT':'json'}
        port=_free_port()
        cls.base=f'http://127.0.0.1:{port}/api/v1'
        cls.log=open(Path(cls.tmp.name)/'server.log','w',encoding='utf-8')
        cls.proc=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--port',str(port)],cwd=BACKEND,env=env,
                                   stdout=cls.log,stderr=subprocess.STDOUT)
        for _ in range(150):
            try:
                if requests.get(cls.base+'/health',timeout=1).ok:
                    break
            except requests.ConnectionError:
                time.sleep(.1)
        else:
            raise RuntimeError('Test server did not start: '+(Path(cls.tmp.name)/'server.log').read_text())
        cls.db=Path(cls.tmp.name)/'pramaan.sqlite3'
        cls.demo=Path(cls.tmp.name)/'demo_files'

    def setUp(self):
        self.ip='10.'+'.'.join(str(x) for x in secrets.token_bytes(3))
        self.client=requests.Session()
        self.client.headers.update({'X-Requested-With':'pramaan','X-Forwarded-For':self.ip})

    def session(self,email):
        s=requests.Session()
        s.headers.update({'X-Requested-With':'pramaan','X-Forwarded-For':self.ip})
        r=s.post(self.base+'/auth/login',json={'email':email,'password':PASSWORD})
        self.assertEqual(r.status_code,200,r.text)
        return s

    @contextmanager
    def sql(self):
        c=sqlite3.connect(self.db)
        c.row_factory=sqlite3.Row
        try:
            yield c
            c.commit()
        finally:
            c.close()

    def mail_token(self,to,purpose):
        end=time.monotonic()+10
        while time.monotonic()<end:
            for path in sorted((Path(self.tmp.name)/'outbox').glob('*.eml'),key=lambda p:p.stat().st_mtime,reverse=True):
                msg=email.message_from_bytes(path.read_bytes(),policy=email.policy.default)
                if str(msg['To'])==to and purpose.lower() in str(msg['Subject']).lower():
                    body=msg.get_body(preferencelist=('plain',)).get_content()
                    m=re.search(r'token=([A-Za-z0-9_-]+)',body)
                    if m:
                        return m.group(1)
            time.sleep(.05)
        self.fail('Expected token email was not delivered')

    def register_body(self):
        key=secrets.token_hex(6)
        return {'email':f'{key}@example.test','name':'Synthetic contact','password':secrets.token_urlsafe(24),
                'institution':{'aicte_permanent_id':'TEST-'+key,'name':'Synthetic test institute','state':'Test state',
                               'trust_name':'Synthetic trust'},'accept_terms':True}
