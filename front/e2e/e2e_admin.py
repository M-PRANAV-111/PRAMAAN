"""J4: real invitation, activation controls and two-administrator rule change."""
from uuid import uuid4
from playwright.sync_api import sync_playwright, expect
from core_support import *

with sync_playwright() as p:
    browser = p.chromium.launch()
    admin = browser.new_page()
    login(admin, 'admin@aicte.synthetic.in')
    admin.goto(base + '/admin/users')
    address = 'invited.' + uuid4().hex[:8] + '@officer.synthetic.in'
    admin.get_by_label('Name', exact=True).fill('Invited Integration Officer')
    admin.get_by_label('Email', exact=True).fill(address)
    admin.get_by_role('button', name='Invite user', exact=True).click()
    expect(admin.get_by_text('Invitation created', exact=True)).to_be_visible()
    officer = browser.new_page()
    officer.goto(mail_link(address, '/accept-invitation'))
    officer.get_by_label('Password (', exact=False).fill(password)
    officer.get_by_label('Confirm password', exact=True).fill(password)
    officer.get_by_role('button', name='Activate account').click()
    expect(officer.get_by_text('Password saved.', exact=False)).to_be_visible()
    login(officer, address)
    check('Invited officer signs into the queue', '/queue' in officer.url)
    admin.reload()
    row = admin.locator('tr').filter(has_text=address)
    row.get_by_label('Deactivation reason').fill('Integration test of account deactivation')
    row.get_by_role('button', name='Deactivate', exact=True).click()
    expect(row.get_by_role('button', name='Reactivate', exact=True)).to_be_visible()
    check('Deactivation revokes the officer session', officer.request.get(base + '/api/v1/auth/me').status == 401)
    row.get_by_role('button', name='Reactivate', exact=True).click()
    expect(row.get_by_role('button', name='Deactivate', exact=True)).to_be_visible()
    login(officer, address)
    check('Reactivated officer signs in', '/queue' in officer.url)
    admin.goto(base + '/rules')
    admin.get_by_label('New value', exact=True).fill('0.85')
    note = 'Integration synthetic rule proposal to verify two-person control'
    admin.get_by_label('Why (cite the Handbook clause or circular)').fill(note)
    admin.get_by_role('button', name='Propose version').click()
    version = admin.locator('li').filter(has_text=note)
    expect(version.get_by_text('Another administrator must activate')).to_be_visible()
    check('Proposing admin cannot activate in UI', version.get_by_role('button', name='Activate', exact=True).count() == 0)
    second = browser.new_page()
    login(second, 'admin2@aicte.synthetic.in')
    second.goto(base + '/rules')
    second.locator('li').filter(has_text=note).get_by_role('button', name='Activate', exact=True).click()
    expect(second.locator('li').filter(has_text=note).get_by_text('Active', exact=True)).to_be_visible()
    check('Second administrator activates the real proposal', True)

    # A1: a real registration, verified by its emailed link, then declined with a recorded reason.
    applicant = browser.new_page()
    applicant_email = 'declined.' + uuid4().hex[:8] + '@institution.synthetic.in'
    institution = 'Declined Integration Institute ' + uuid4().hex[:8]
    applicant.goto(base + '/register')
    for label, value in [('Nodal officer name', 'Declined Nodal Officer'), ('Official email', applicant_email),
                         ('Password', password), ('Confirm password', password), ('Institution name', institution),
                         ('AICTE Permanent ID', '1-DEC-' + uuid4().hex[:6]), ('State', 'Telangana'),
                         ('Trust or society name', 'Declined Synthetic Trust')]:
        applicant.get_by_label(label, exact=True).fill(value)
    applicant.get_by_role('checkbox').check()
    applicant.get_by_role('button', name='Register institution').click()
    expect(applicant.get_by_role('heading', name='Registration received')).to_be_visible()
    applicant.goto(mail_link(applicant_email, '/verify-email'))
    applicant.get_by_role('button', name='Confirm email address').click()
    expect(applicant.get_by_text('Your email is verified.')).to_be_visible()
    admin.goto(base + '/admin/registrations')
    entry = admin.locator('li').filter(has_text=institution)
    entry.get_by_label('Reason', exact=False).fill('Permanent ID does not match the AICTE record for this institution.')
    entry.get_by_role('button', name='Decline', exact=True).click()
    expect(admin.get_by_text('Registration declined', exact=True)).to_be_visible()
    expect(entry.get_by_text('DECLINED', exact=True)).to_be_visible()
    declined = applicant.request.post(base + '/api/v1/auth/login', data={'email': applicant_email, 'password': password},
                                      headers={'X-Requested-With': 'pramaan'})
    check('Declined applicant cannot sign in', declined.status == 401)

    # The System page shows readiness and the worker from the real probes.
    admin.goto(base + '/admin/system')
    expect(admin.get_by_text('Worker:', exact=False)).to_be_visible()
    expect(admin.locator('section').filter(has_text='Readiness & subsystems').get_by_text('ok', exact=True).first).to_be_visible()
    check('System page reflects the readiness probe', admin.request.get(base + '/api/v1/ready').status == 200)
    finish(second, 'e2e-admin')
    browser.close()
