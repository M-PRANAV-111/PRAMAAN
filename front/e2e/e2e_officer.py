"""J3: search, clarification round trip, officer decision and audit verification."""
import re
from playwright.sync_api import sync_playwright, expect
from core_support import *

with sync_playwright() as p:
    browser = p.chromium.launch()
    officer = browser.new_page()
    login(officer, 'officer@aicte.synthetic.in')
    with officer.expect_response(lambda r: '/applications?' in r.url and 'q=Godavari' in r.url) as searched:
        officer.get_by_role('searchbox').fill('Godavari')
    check('Queue search uses backend query and total header', searched.value.status == 200 and searched.value.headers.get('x-total-count') == '1')
    officer.get_by_role('link', name='Godavari College of Engineering (Synthetic)').click()
    officer.wait_for_url('**/applications/**')
    case_url = officer.url.split('?')[0]
    officer.get_by_role('button', name='Intake is the same in the affidavit').click()
    officer.get_by_role('radio', name='Ask the institution').check()
    officer.get_by_label('Reason (recorded with your name)').fill('Please explain the difference between affidavit intake and recorded intake.')
    officer.get_by_role('button', name='Record decision').click()
    expect(officer.get_by_text('Decision recorded in the audit trail')).to_be_visible()
    institution = browser.new_page()
    login(institution, 'nodal@godavari.synthetic.in')
    institution.goto(base + '/notifications')
    notice = institution.locator('li').filter(has_text='clarification').first
    expect(notice).to_be_visible()
    notice.get_by_role('button', name='Open', exact=True).click()
    institution.get_by_role('button', name='Intake is the same in the affidavit').click()
    reply = 'The affidavit includes a proposed intake; the recorded intake remains unchanged.'
    institution.get_by_label('Your reply to the scrutiny officer', exact=False).fill(reply)
    institution.get_by_role('button', name='Send clarification reply').click()
    expect(institution.get_by_text('Clarification reply recorded')).to_be_visible()
    officer.reload()
    officer.get_by_role('button', name='Intake is the same in the affidavit').click()
    expect(officer.get_by_text(reply, exact=True)).to_be_visible()
    check('Officer sees the real institutional reply', True)
    officer.get_by_role('radio', name=re.compile(r'^Confirm\b')).check()  # label text = option + its hint
    officer.get_by_label('Reason (recorded with your name)').fill('Institution response explains the mismatch; the finding stands for scrutiny.')
    officer.get_by_role('button', name='Record decision').click()
    expect(officer.get_by_text('Decision recorded in the audit trail')).to_be_visible()
    # A2: the institution clears its notifications in one action.
    institution.goto(base + '/notifications')
    institution.get_by_role('button', name='Mark all as read', exact=True).click()
    expect(institution.get_by_text('All marked as read', exact=True)).to_be_visible()
    check('Mark all as read leaves no unread notification',
          institution.request.get(base + '/api/v1/notifications/unread-count').json()['count'] == 0)
    # The officer re-runs the full check on the submitted case; it is a real validation job.
    officer.goto(case_url)
    with officer.expect_response(lambda r: r.url.endswith('/validate') and r.request.method == 'POST') as queued:
        officer.get_by_role('button', name='Run full check', exact=True).click()
    expect(officer.get_by_text('Full check queued', exact=True)).to_be_visible()
    job_id = queued.value.json()['id']
    for _ in range(240):
        job = officer.request.get(base + '/api/v1/jobs/' + job_id).json()
        if job['state'] in ('DONE', 'FAILED'):
            break
        officer.wait_for_timeout(500)
    check('Run full check completes a real validation job', job['state'] == 'DONE' and 'RULES' in job['stage_history'])
    officer.goto(base + '/audit')
    officer.get_by_role('button', name='Verify the chain').click()
    expect(officer.get_by_text('Chain intact.')).to_be_visible()
    check('Audit chain verifies after the complete clarification loop', True)
    finish(officer, 'e2e-officer')
    browser.close()
