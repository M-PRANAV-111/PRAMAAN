import io
import re

import pdfplumber
from tests.core_support import CoreApiCase


class ReportTests(CoreApiCase):
    def test_pdf_disclaimer_sources_and_audit(self):
        officer=self.session('officer@aicte.synthetic.in')
        app=self.app_id(officer,'Godavari')
        r=officer.get(f'{self.base}/applications/{app}/report')
        self.assertEqual(r.status_code,200,r.text[:100] if r.status_code!=200 else '')
        self.assertTrue(r.content.startswith(b'%PDF'))
        self.assertIn('attachment; filename="PRAMAAN-',r.headers['Content-Disposition'])
        with pdfplumber.open(io.BytesIO(r.content)) as pdf:
            text='\n'.join(p.extract_text() or '' for p in pdf.pages)
            fonts={char['fontname'] for page in pdf.pages for char in page.chars}
        normalized=' '.join(text.split())
        self.assertIn('Decision support only — not an approval or a rejection. Officials decide.',normalized)
        self.assertIn('SYNTHETIC DEMO DATA',text)
        self.assertIn('Simulated source',text)
        self.assertIn('verify at /audit',text)
        self.assertFalse(re.search(r'\b(APPROVED|REJECTED|FORGED)\b',text,re.I))
        self.assertEqual(fonts,{'Helvetica'})
        with self.sql() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM audit_events WHERE action='report.downloaded' AND application_id=?",(app,)).fetchone()[0],1)

    def test_report_access_and_institution_duplicate_redaction(self):
        officer=self.session('officer@aicte.synthetic.in')
        app=self.app_id(officer,'Godavari')
        other=self.session('nodal@shakti.synthetic.in')
        self.assertEqual(other.get(f'{self.base}/applications/{app}/report').status_code,404)
        inst=self.session('nodal@godavari.synthetic.in')
        r=inst.get(f'{self.base}/applications/{app}/report')
        self.assertEqual(r.status_code,200)
        with pdfplumber.open(io.BytesIO(r.content)) as pdf:
            text='\n'.join(p.extract_text() or '' for p in pdf.pages)
        with self.sql() as c:
            foreign=[r[0] for r in c.execute('SELECT id FROM documents WHERE application_id!=?',(app,))]
        self.assertFalse(any(doc_id in text for doc_id in foreign))
