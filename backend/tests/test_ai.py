import io
import os
from datetime import date
from unittest.mock import patch

from reportlab.pdfgen import canvas
from app.ai import client, pipeline
from app.config import reset_settings_cache
from app.db import transaction, reader, now_iso, new_id
from app.pipeline import extract, orchestrator
from app.routes.common import job_out
from app.storage import LocalStorage
from synthetic import generator as g
from tests.local_support import LocalDatabaseCase


class AITests(LocalDatabaseCase):
    def setUp(self):
        super().setUp()
        self.ai_env=patch.dict(os.environ, {'AI_PROVIDER':'fixture','AI_TEST_FAULT':'','AI_DAILY_CALL_BUDGET':'50'})
        self.ai_env.start()
        self.addCleanup(self.ai_env.stop)

    def job(self, stamp=True):
        if stamp:
            data=g.affidavit(g.Inst('Synthetic institute','1-SYN-TEST'),'2026-27',120,60,date(2026,1,1))
        else:
            stream=io.BytesIO()
            pdf=canvas.Canvas(stream)
            pdf.drawString(50,750,'AFFIDAVIT Total intake sought: 120')
            pdf.save()
            data=stream.getvalue()
        sha=LocalStorage().put(data)
        did=new_id('doc')
        with transaction() as c:
            c.execute("INSERT INTO documents(id,application_id,doc_type,original_name,sha256,size_bytes,mime,pages,uploaded_by,uploaded_at) VALUES (?,'app','affidavit','synthetic.pdf',?,?,'application/pdf',1,'usr',?)",(did,sha,len(data),now_iso()))
            jid=orchestrator.create_job(c,'PROCESS_DOCUMENT','app',did)
        return jid,did

    def outcomes(self):
        with reader() as c:
            rid=c.execute('SELECT id FROM validation_runs ORDER BY rowid DESC LIMIT 1').fetchone()[0]
            return [tuple(r) for r in c.execute('SELECT rule_id,outcome FROM rule_results WHERE run_id=? ORDER BY rule_id',(rid,))]

    def test_fixture_grounding_suggestions_and_real_stages(self):
        jid,did=self.job()
        orchestrator.run_job(jid)
        with reader() as c:
            job=job_out(c.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone())
            self.assertEqual(job['state'],'DONE',job)
            self.assertIn('AI_EXTRACTION',job['stage_history'])
            self.assertIn('ROUTING',job['stage_history'])
            row=c.execute("SELECT * FROM claims WHERE document_id=? AND field='total_intake'",(did,)).fetchone()
            self.assertEqual((row['value_norm'],row['extractor']),('120','ai+text'))
            self.assertGreater(row['x1'],row['x0'])
            self.assertEqual(c.execute('SELECT value FROM ai_suggestions WHERE document_id=?',(did,)).fetchone()[0],'999999')
            self.assertFalse(c.execute("SELECT 1 FROM claims WHERE value_norm='999999'").fetchone())
            self.assertTrue(c.execute("SELECT 1 FROM audit_events WHERE action='routing.updated'").fetchone())

    def test_faults_fallback_preserves_deterministic_findings(self):
        for fault in ('rate_limit','timeout','invalid_json'):
            jid,did=self.job()
            with patch.dict(os.environ,{'AI_TEST_FAULT':fault}):
                orchestrator.run_job(jid)
            orchestrator.run_validation('app',trigger='test-full-baseline')
            before=self.outcomes()
            with reader() as c:
                job=job_out(c.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone())
                self.assertEqual(job['state'],'DONE')
                self.assertIn('AI step skipped: '+fault,job['ai_notes'])
            with patch.dict(os.environ,{'AI_PROVIDER':'none'}):
                with transaction() as c:
                    validate=orchestrator.create_job(c,'VALIDATE','app')
                orchestrator.run_job(validate)
            self.assertEqual(before,self.outcomes())

    def test_data_policy_makes_no_provider_call(self):
        jid,_=self.job(False)
        with patch.object(client.requests,'post') as external,patch.object(pipeline,'complete') as complete:
            orchestrator.run_job(jid)
        external.assert_not_called()
        complete.assert_not_called()
        with reader() as c:
            job=job_out(c.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone())
            self.assertEqual(job['state'],'DONE')
            self.assertIn('AI step skipped: data_policy',job['ai_notes'])
            self.assertNotIn('AI_EXTRACTION',job['stage_history'])

    def test_faults_and_fixtures_refused_outside_test(self):
        for provider,fault in [('fixture',''),('none','timeout')]:
            with patch.dict(os.environ,{'APP_ENV':'development','AI_PROVIDER':provider,'AI_TEST_FAULT':fault}):
                reset_settings_cache()
                with self.assertRaises(ValueError):
                    client.settings()
        reset_settings_cache()

    def test_wrong_field_page_and_low_confidence_cannot_ground(self):
        line=extract.Line(1,[extract.Word('Total intake sought: 120',10,20,200,30)],600,800,'text-layer')
        result=extract.ExtractionResult(lines=[line])
        self.assertIsNotNone(pipeline.ground(result,'affidavit',{'field':'total_intake','value':'120','page':1}))
        for candidate in [{'field':'faculty_count','value':'120','page':1},{'field':'total_intake','value':'120','page':2},{'field':'total_intake','value':'999','page':1}]:
            self.assertIsNone(pipeline.ground(result,'affidavit',candidate))
        line.words[0].conf=.2
        self.assertIsNone(pipeline.ground(result,'affidavit',{'field':'total_intake','value':'120','page':1}))

    def test_budget_and_status_never_expose_key(self):
        jid,_=self.job()
        with patch.dict(os.environ,{'AI_DAILY_CALL_BUDGET':'1','ANTHROPIC_API_KEY':'secret-sentinel'}):
            with transaction() as c:
                client.complete(c,jid,'extraction',{})
                with self.assertRaisesRegex(client.AIUnavailable,'budget'):
                    client.complete(c,jid,'extraction',{})
            status=pipeline.status()
            self.assertEqual(status['usage'],1)
            self.assertTrue(status['fallback_active'])
            self.assertNotIn('secret-sentinel',str(status))

    def test_provider_transport_is_bounded_and_errors_are_sanitized(self):
        jid,_=self.job()
        with patch.dict(os.environ,{'AI_PROVIDER':'anthropic','AI_MODEL':'configured-model','ANTHROPIC_API_KEY':'secret-sentinel'}):
            with transaction() as c, patch.object(client.requests,'post') as post:
                post.return_value.status_code=429
                post.return_value.text='secret-sentinel provider internals'
                with self.assertRaisesRegex(client.AIUnavailable,'^rate_limit$'):
                    client.complete(c,jid,'extraction',{'document':'synthetic text'})
                args,kwargs=post.call_args
                self.assertEqual(args[0],'https://api.anthropic.com/v1/messages')
                self.assertEqual(kwargs['timeout'],(5,20))
                self.assertFalse(kwargs['allow_redirects'])
            self.assertEqual(pipeline.status()['last_error'],'rate_limit')
            self.assertNotIn('secret-sentinel',str(pipeline.status()))

    def test_malformed_provider_values_cannot_change_claims(self):
        jid,did=self.job()
        with patch.object(pipeline,'complete',return_value={'claims':[{'field':'total_intake','value':'999999','page':1}]}):
            orchestrator.run_job(jid)
        with reader() as c:
            self.assertEqual(c.execute("SELECT value_norm FROM claims WHERE document_id=? AND field='total_intake'",(did,)).fetchone()[0],'120')
            self.assertEqual(c.execute('SELECT value FROM ai_suggestions WHERE document_id=?',(did,)).fetchone()[0],'999999')

    def test_unsupported_explanations_remain_template(self):
        jid,did=self.job()
        original=pipeline.complete
        def reply(c,jid,task,payload):
            if task=='explanation':
                return {'explanation':'Invented conclusion without evidence'}
            return original(c,jid,task,payload)
        with patch.object(pipeline,'complete',side_effect=reply):
            orchestrator.run_job(jid)
        with reader() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM ai_explanations').fetchone()[0],0)
            self.assertFalse(c.execute("SELECT 1 FROM findings WHERE explanation LIKE '%Invented conclusion%'").fetchone())

    def test_three_routing_outcomes(self):
        jid,did=self.job()
        orchestrator.run_job(jid)
        with transaction() as c:
            c.execute("UPDATE findings SET state='RESOLVED' WHERE application_id='app'")
            c.execute("UPDATE documents SET verification_status='VERIFIED',processing_state='DONE' WHERE id=?",(did,))
            self.assertEqual(pipeline.routing(c,'app')['outcome'],'READY_FOR_SCRUTINY')
            c.execute("UPDATE documents SET verification_status='SOURCE_UNAVAILABLE' WHERE id=?",(did,))
            self.assertEqual(pipeline.routing(c,'app')['outcome'],'MANUAL_REVIEW_REQUIRED')
            c.execute("UPDATE findings SET state='OPEN' WHERE application_id='app' AND severity='DEFICIENCY'")
            result=pipeline.routing(c,'app')
            self.assertEqual(result['outcome'],'DEFICIENCIES_FLAGGED')
            self.assertTrue(all(r['link'].startswith('/applications/app') for r in result['reasons']))
