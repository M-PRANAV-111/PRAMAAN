from tests.core_support import CoreApiCase


class TrackingTests(CoreApiCase):
    def test_search_pagination_and_unchanged_default_shape(self):
        from app.routes.common import application_summary
        from app.schemas import ApplicationSummary
        officer=self.session('officer@aicte.synthetic.in')
        plain=officer.get(self.base+'/applications')
        # Compare serialization against the original list implementation, including order.
        with self.sql() as c:
            original=[ApplicationSummary.model_validate(application_summary(c,a)).model_dump(mode='json') for a in
                      c.execute('SELECT * FROM applications WHERE submitted_at IS NOT NULL ORDER BY submitted_at DESC')]
        import json
        self.assertEqual(plain.content,json.dumps(original,separators=(',',':'),ensure_ascii=False).encode())
        self.assertEqual(int(plain.headers['X-Total-Count']),len(original))
        search=officer.get(self.base+'/applications',params={'q':'gOdAvArI','limit':1})
        self.assertEqual(len(search.json()),1)
        self.assertEqual(search.headers['X-Total-Count'],'1')
        pid=search.json()[0]['institution']['aicte_permanent_id']
        self.assertEqual(len(officer.get(self.base+'/applications',params={'q':pid.lower()}).json()),1)
        self.assertEqual(officer.get(self.base+'/applications?limit=201').status_code,422)
        self.assertEqual(officer.get(self.base+'/applications?offset=-1').status_code,422)
        self.assertEqual(officer.get(self.base+'/applications?status=UNKNOWN').status_code,422)
        inst=self.session('nodal@shakti.synthetic.in')
        self.assertEqual(inst.get(self.base+'/applications?q=Godavari').json(),[])

    def test_history_versions_timeline_and_visibility(self):
        inst=self.session('nodal@deccan.synthetic.in')
        app=inst.post(self.base+'/applications',json={'category':'EOA_EXISTING','academic_year':'2027-28'}).json()['id']
        ids=[]
        for _ in range(2):
            with (self.demo/'D_Affidavit_2026-27.pdf').open('rb') as file:
                upload=inst.post(f'{self.base}/applications/{app}/documents',data={'doc_type':'affidavit'},files={'file':file})
            self.assertEqual(upload.status_code,202,upload.text)
            ids.append(upload.json()['document']['id'])
            self.assertEqual(self.wait_job(inst,upload.json()['job']['id'])['state'],'DONE')
        history=inst.get(f'{self.base}/applications/{app}/documents/history').json()
        self.assertEqual([d['version'] for d in history],[1,2])
        self.assertTrue(history[0]['superseded'])
        docs=inst.get(f'{self.base}/applications/{app}').json()['documents']
        self.assertEqual([d['id'] for d in docs],[ids[1]])
        events=inst.get(f'{self.base}/applications/{app}/timeline').json()
        self.assertTrue({'APPLICATION_CREATED','DOCUMENT_UPLOADED','PROCESSING_DONE','VALIDATION_RUN','FINDING_RAISED'} <= {e['kind'] for e in events})
        officer=self.session('officer@aicte.synthetic.in')
        other=self.session('nodal@shakti.synthetic.in')
        for suffix in ('timeline','documents/history'):
            self.assertEqual(officer.get(f'{self.base}/applications/{app}/{suffix}').status_code,404)
            self.assertEqual(other.get(f'{self.base}/applications/{app}/{suffix}').status_code,404)
        self.assertEqual(inst.post(f'{self.base}/applications/{app}/submit').status_code,200)
        self.assertEqual(officer.get(f'{self.base}/applications/{app}/timeline').status_code,200)

    def test_clarification_responses_length_role_and_document_ownership(self):
        officer=self.session('officer@aicte.synthetic.in')
        inst=self.session('nodal@godavari.synthetic.in')
        other=self.session('nodal@shakti.synthetic.in')
        app=self.app_id(officer,'Godavari')
        f=officer.get(f'{self.base}/applications/{app}/findings').json()[0]
        path=f"{self.base}/findings/{f['id']}/responses"
        body={'text':'Please check the attached institution evidence.'}
        self.assertEqual(other.post(path,json=body).status_code,404)
        self.assertEqual(officer.post(path,json=body).status_code,403)
        for text in ('short',' '*20,'a'*2001):
            self.assertEqual(inst.post(path,json={'text':text}).status_code,422)
        foreign=other.get(f"{self.base}/applications/{self.app_id(other,'Shakti')}").json()['documents'][0]['id']
        self.assertEqual(inst.post(path,json={**body,'document_id':foreign}).status_code,404)
        own=inst.get(f'{self.base}/applications/{app}').json()['documents'][0]['id']
        self.assertEqual(officer.post(f"{self.base}/findings/{f['id']}/review",json={'decision':'REQUEST_CLARIFICATION','reason':'Please explain the discrepancy in the document.'}).status_code,200)
        reply=inst.post(path,json={**body,'document_id':own})
        self.assertEqual(reply.status_code,200,reply.text)
        findings=officer.get(f'{self.base}/applications/{app}/findings').json()
        self.assertIn(reply.json(),next(x for x in findings if x['id']==f['id'])['responses'])
        kinds={x['kind'] for x in inst.get(f'{self.base}/applications/{app}/timeline').json()}
        self.assertTrue({'CLARIFICATION_REQUESTED','INSTITUTION_REPLIED'} <= kinds)
