import os
import secrets
import subprocess
import sys
import time
from unittest.mock import patch

from app.config import get_settings
from app.db import reader, transaction, new_id, now_iso
from app.pipeline import orchestrator as jobs
from app.pipeline.hooks import _steps, register_step, STAGE_CODES
from app.storage import LocalStorage
from synthetic import generator as g
from tests.local_support import LocalDatabaseCase
from tests.core_support import CoreApiCase


class JobTests(LocalDatabaseCase):
    def job(self,kind='VALIDATE'):
        doc_id=None
        if kind=='PROCESS_DOCUMENT':
            data=g.affidavit(g.Inst('Synthetic institute','1-SYN-TEST'),'2026-27',240,60,__import__('datetime').date(2026,1,1))
            sha=LocalStorage().put(data)
            doc_id=new_id('doc')
            with transaction() as c:
                c.execute('INSERT INTO documents (id,application_id,doc_type,original_name,sha256,size_bytes,mime,pages,uploaded_by,uploaded_at) '
                          "VALUES (?,'app','affidavit','synthetic.pdf',?,?,'application/pdf',1,'usr',?)",(doc_id,sha,len(data),now_iso()))
        with transaction() as c:
            return jobs.create_job(c,kind,'app',doc_id)

    def state(self,jid):
        with reader() as c:
            return dict(c.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone())

    def test_transient_retry_and_stage_codes(self):
        jid=self.job()
        original=jobs.run_validation
        calls=[]
        def flaky(*args,**kwargs):
            calls.append(1)
            if len(calls)==1:
                raise OSError('synthetic temporary failure')
            return original(*args,**kwargs)
        with patch.object(jobs,'run_validation',side_effect=flaky),patch.object(jobs.time,'sleep') as sleep:
            jobs.run_job(jid)
        self.assertEqual(self.state(jid)['state'],'DONE')
        self.assertEqual(self.state(jid)['attempts'],2)
        sleep.assert_called_once_with(2)
        with reader() as c:
            self.assertTrue(all(r[0] in STAGE_CODES.values() for r in c.execute('SELECT stage_code FROM job_stage_durations')))
        self.assertEqual(self.state(jid)['stage_code'],'DONE')

    def test_validation_failure_is_not_retried(self):
        jid=self.job()
        with patch.object(jobs,'run_validation',side_effect=ValueError('bad input')) as fn:
            jobs.run_job(jid)
        self.assertEqual(fn.call_count,1)
        state=self.state(jid)
        self.assertEqual((state['state'],state['stage_code'],state['error']),('FAILED','FAILED','ValueError'))
        self.assertTrue(state['error_message'])

    def test_backoff_two_retries_only(self):
        jid=self.job()
        with patch.object(jobs,'run_validation',side_effect=TimeoutError),patch.object(jobs.time,'sleep') as sleep:
            jobs.run_job(jid)
        self.assertEqual([c.args[0] for c in sleep.call_args_list],[2,8])
        self.assertEqual(self.state(jid)['attempts'],3)
        self.assertEqual(self.state(jid)['state'],'FAILED')

    def test_hard_timeout_terminates_child(self):
        jid=self.job()
        get_settings().job_timeout_seconds=.2
        original=subprocess.Popen
        processes=[]
        def launch(*args,**kwargs):
            p=original([sys.executable,'-c','import time; time.sleep(30)'],**kwargs)
            processes.append(p)
            return p
        start=time.monotonic()
        with patch.object(jobs.subprocess,'Popen',side_effect=launch):
            jobs.run_job_supervised(jid)
        self.assertLess(time.monotonic()-start,5)
        self.assertIsNotNone(processes[0].poll())
        self.assertEqual((self.state(jid)['state'],self.state(jid)['error']),('FAILED','timeout'))

    def test_supervised_jobs_start_and_exit_without_blocking_next_job(self):
        get_settings().job_timeout_seconds=15
        for _ in range(2):
            jid=self.job('PROCESS_DOCUMENT')
            jobs.run_job_supervised(jid)
            self.assertEqual(self.state(jid)['state'],'DONE')

    def test_supervised_child_stops_when_parent_pipe_closes(self):
        jid=self.job()
        proc=subprocess.Popen([sys.executable,'-m','app.pipeline.job_runner',jid],
                              stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            proc.stdin.close()
            proc.wait(timeout=10)
            self.assertEqual(proc.returncode,1)
            self.assertEqual(self.state(jid)['state'],'QUEUED')
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()

    def test_hooks_in_order_and_no_hooks_preserve_rules(self):
        jid=self.job('PROCESS_DOCUMENT')
        calls=[]
        saved={k:list(v) for k,v in _steps.items()}
        try:
            for value in _steps.values():
                value.clear()
            def first(c,jid,doc,stage):
                self.assertGreater(c.execute('SELECT COUNT(*) FROM claims WHERE document_id=?',(doc['id'],)).fetchone()[0],0)
                calls.append('fields1')
                stage('AI_EXTRACTION','Optional field checks',45)
            register_step('after_fields',first)
            register_step('after_fields',lambda *args:calls.append('fields2'))
            register_step('after_rules',lambda *args:calls.append('rules'))
            jobs.run_job(jid)
            self.assertEqual(calls,['fields1','fields2','rules'])
            self.assertEqual(self.state(jid)['state'],'DONE')
            with reader() as c:
                before=[(r['rule_id'],r['outcome']) for r in c.execute('SELECT rule_id,outcome FROM rule_results ORDER BY rule_id')]
            for value in _steps.values():
                value.clear()
            jobs.run_job(self.job())
            with reader() as c:
                latest=c.execute('SELECT id FROM validation_runs ORDER BY rowid DESC LIMIT 1').fetchone()[0]
                after=[tuple(r) for r in c.execute('SELECT rule_id,outcome FROM rule_results WHERE run_id=? ORDER BY rule_id',(latest,))]
            self.assertEqual(before,after)
        finally:
            for key,value in saved.items():
                _steps[key][:]=value


class IdempotentUploadTests(CoreApiCase):
    def test_upload_replay_expiry_and_owner_scope(self):
        inst=self.session('nodal@deccan.synthetic.in')
        app=inst.post(self.base+'/applications',json={'category':'EOA_EXISTING','academic_year':'2028-29'}).json()['id']
        key=secrets.token_hex(16)
        def upload():
            with (self.demo/'D_Lab_Photo.png').open('rb') as f:
                return inst.post(f'{self.base}/applications/{app}/documents',headers={'Idempotency-Key':key},
                                 data={'doc_type':'infra_photo'},files={'file':f})
        first=upload()
        self.assertEqual(first.status_code,202,first.text)
        self.assertEqual(upload().content,first.content)
        self.assertEqual(self.wait_job(inst,first.json()['job']['id'])['state'],'DONE')
        self.assertEqual(upload().content,first.content)
        with self.sql() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM documents WHERE application_id=?',(app,)).fetchone()[0],1)
            c.execute("UPDATE idempotency_keys SET created_at='2000-01-01' WHERE key=?",(key,))
        fresh=upload()
        self.assertNotEqual(fresh.json()['document']['id'],first.json()['document']['id'])
        self.assertEqual(fresh.json()['document']['version'],2)
        self.assertEqual(self.wait_job(inst,fresh.json()['job']['id'])['state'],'DONE')
        other=self.session('nodal@shakti.synthetic.in')
        with (self.demo/'D_Lab_Photo.png').open('rb') as f:
            r=other.post(f'{self.base}/applications/{app}/documents',headers={'Idempotency-Key':key},data={'doc_type':'infra_photo'},files={'file':f})
        self.assertEqual(r.status_code,404)
