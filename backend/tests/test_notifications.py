from tests.core_support import CoreApiCase


class NotificationTests(CoreApiCase):
    def test_deficiency_clarification_reply_and_read_isolation(self):
        officer=self.session('officer@aicte.synthetic.in')
        inst=self.session('nodal@godavari.synthetic.in')
        other=self.session('nodal@shakti.synthetic.in')
        app=self.app_id(officer,'Godavari')
        before=inst.get(self.base+'/notifications').json()
        self.assertTrue(any(n['kind']=='FINDING_RAISED' for n in before))
        fid=officer.get(f'{self.base}/applications/{app}/findings').json()[0]['id']
        officer.post(f'{self.base}/findings/{fid}/review',json={'decision':'REQUEST_CLARIFICATION','reason':'Please clarify the evidence in this finding.'})
        rows=inst.get(self.base+'/notifications?unread=true').json()
        note=next(n for n in rows if n['kind']=='CLARIFICATION_REQUESTED')
        self.assertEqual(other.post(f"{self.base}/notifications/{note['id']}/read").status_code,404)
        self.assertTrue(all(n['application_id']!=app for n in other.get(self.base+'/notifications').json()))
        count=inst.get(self.base+'/notifications/unread-count').json()['count']
        self.assertEqual(inst.post(f"{self.base}/notifications/{note['id']}/read").status_code,200)
        self.assertEqual(inst.get(self.base+'/notifications/unread-count').json()['count'],count-1)
        self.assertEqual(inst.post(f'{self.base}/findings/{fid}/responses',json={'text':'The corrected evidence will be provided shortly.'}).status_code,200)
        self.assertTrue(any(n['kind']=='INSTITUTION_REPLIED' and n['finding_id']==fid for n in officer.get(self.base+'/notifications').json()))
        self.assertEqual(inst.post(self.base+'/notifications/read-all').status_code,200)
        self.assertEqual(inst.get(self.base+'/notifications/unread-count').json(),{'count':0})
        self.assertEqual(inst.get(self.base+'/notifications?unread=true').json(),[])
        self.assertEqual(inst.get(self.base+'/notifications?limit=201').status_code,422)
