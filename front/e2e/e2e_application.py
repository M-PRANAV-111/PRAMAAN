"""J2: actual upload, processing, PDF, targeted repair and submission UI."""
import os
import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

base, password, out = sys.argv[1:4]
out = Path(out)
out.mkdir(parents=True, exist_ok=True)
demo = Path(os.environ['PRAMAAN_DEMO_DIR'])
checks = []


def check(name, condition):
    checks.append(bool(condition))
    print(('PASS' if condition else 'FAIL'), name, flush=True)
    assert condition, name


with sync_playwright() as p:
    browser = p.chromium.launch()
    context = browser.new_context(accept_downloads=True)
    page = context.new_page()
    page.goto(base+'/login')
    page.get_by_label('Email', exact=True).fill('nodal@deccan.synthetic.in')
    page.get_by_label('Password', exact=True).fill(password)
    page.get_by_role('button', name='Sign in', exact=True).click()
    page.wait_for_url('**/institution')
    page.get_by_role('button', name='Start an application').first.click()
    page.get_by_role('button', name='Create application').click()
    page.wait_for_url('**/applications/**')
    app_id = page.url.split('/applications/')[1].split('?')[0]

    def read(suffix=''):
        r = context.request.get(base+'/api/v1/applications/'+app_id+suffix)
        assert r.ok, r.text()
        return r.json()

    jobs = []
    def upload(kind, name):
        with page.expect_response(lambda r: r.request.method == 'POST' and r.url.endswith('/documents')) as pending:
            page.set_input_files('#up-'+kind, str(demo/name))
        response = pending.value
        check('upload accepted '+kind, response.status == 202)
        job_id = response.json()['job']['id']
        for _ in range(120):
            job = context.request.get(base+'/api/v1/jobs/'+job_id).json()
            if job['state'] in ('DONE', 'FAILED'):
                break
            page.wait_for_timeout(500)
        check('processing completed '+kind, job['state'] == 'DONE')
        jobs.append(job)
        expect(page.locator('#up-'+kind)).to_be_enabled(timeout=15000)
        return job

    for kind, filename in {
        'eoa_letter':'D_EoA_2025-26.pdf', 'affidavit':'D_Affidavit_2026-27.pdf',
        'fire_noc':'D_Fire_NOC_EXPIRED.pdf', 'building_stability':'D_Structural_Stability.pdf',
        'faculty_summary':'D_Faculty_Summary_WRONG_INTAKE.pdf', 'infra_photo':'D_Lab_Photo.png'
    }.items():
        upload(kind, filename)
    page.get_by_text('Recorded processing stages', exact=True).click()
    expect(page.locator('[data-stage-history] li').last).to_have_attribute('data-code', 'DONE', timeout=15000)
    visible = page.locator('[data-stage-history] li').evaluate_all('(els) => els.map(e => e.dataset.code)')
    check('UI recorded stages equal real job sequence', visible == jobs[-1]['stage_history'])
    page.screenshot(path=out/'processing.png', full_page=True)
    findings = read('/findings')
    check('expired NOC finding exists', any(f['rule_id']=='FIRE.VALID' for f in findings))
    page.get_by_role('tab', name='What to fix', exact=True).click()
    check('repair plan comes from application', bool(read('/repair-plan')['institution_actions']))
    with page.expect_download() as pending:
        page.get_by_role('button', name='Download report', exact=True).first.click()
    target = out/'report.pdf'
    pending.value.save_as(target)
    check('real PDF downloaded', target.read_bytes().startswith(b'%PDF'))
    import pdfplumber
    with pdfplumber.open(target) as pdf:
        text = '\n'.join(page.extract_text() or '' for page in pdf.pages)
    check('report identifies visible application', app_id in text and 'Deccan' in text)
    check('report retains decision-support notice', 'Officials decide.' in text)
    check('download audited in timeline', any(e['kind']=='REPORT_DOWNLOADED' for e in read('/timeline')))
    page.get_by_role('tab', name='Documents', exact=True).click()
    upload('fire_noc', 'D_Fire_NOC_RENEWED.pdf')
    run = read('/runs')[0]
    check('only affected rules rerun', 'FIRE.VALID' in run['affected_rules'] and 'INTAKE.CONSISTENT' not in run['affected_rules'])
    page.get_by_role('tab', name='Findings', exact=False).click()
    page.get_by_label('Show resolved findings').check()
    expect(page.get_by_text('Resolved by re-check', exact=True).first).to_be_visible()
    check('renewed NOC resolves finding', any(f['rule_id']=='FIRE.VALID' and f['state']=='RESOLVED' for f in read('/findings?include_resolved=true')))
    page.get_by_role('button', name='Submit to AICTE', exact=True).first.click()
    page.get_by_role('dialog').get_by_role('button', name='Submit to AICTE', exact=True).click()
    expect(page.get_by_text('Submitted to AICTE', exact=False).first).to_be_visible()
    page.get_by_role('tab', name='Activity', exact=True).click()
    expect(page.get_by_role('heading', name='Application timeline')).to_be_visible()
    kinds = {e['kind'] for e in read('/timeline')}
    check('complete real-event timeline', {'APPLICATION_CREATED','DOCUMENT_UPLOADED','PROCESSING_DONE','VALIDATION_RUN','FINDING_RAISED','FINDING_RESOLVED','SUBMITTED','REPORT_DOWNLOADED'} <= kinds)
    page.screenshot(path=out/'timeline.png', full_page=True)
    browser.close()
print(f'{sum(checks)}/{len(checks)} checks passed')
