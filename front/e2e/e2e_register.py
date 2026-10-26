"""J1: actual registration, verification, administrator acceptance and sign-in."""
from uuid import uuid4
from playwright.sync_api import sync_playwright, expect
from core_support import *

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    address = 'new.' + uuid4().hex[:8] + '@institution.synthetic.in'
    institution = 'Integration Institute ' + uuid4().hex[:8]
    def register():
        page.goto(base + '/register')
        for label, value in [('Nodal officer name', 'Integration Nodal Officer'), ('Official email', address), ('Password', password), ('Confirm password', password), ('Institution name', institution), ('AICTE Permanent ID', '1-INT-' + address.split('.')[1].split('@')[0]), ('State', 'Telangana'), ('Trust or society name', 'Integration Synthetic Trust')]:
            page.get_by_label(label, exact=True).fill(value)
        page.get_by_role('checkbox').check()
        page.get_by_role('button', name='Register institution').click()
        expect(page.get_by_role('heading', name='Registration received')).to_be_visible()
        return page.locator('main').inner_text()
    first = register()
    check('Duplicate registration has identical neutral response', register() == first)
    page.goto(mail_link(address, '/verify-email'))
    page.get_by_role('button', name='Confirm email address').click()
    expect(page.get_by_text('Your email is verified.')).to_be_visible()
    check('Verification link works in UI', True)
    admin = browser.new_page()
    login(admin, 'admin@aicte.synthetic.in')
    admin.goto(base + '/admin/registrations')
    row = admin.locator('li').filter(has_text=institution)
    row.get_by_label('Reason', exact=False).fill('Verified institution registration for integration test')
    row.get_by_role('button', name='Accept', exact=True).click()
    expect(admin.get_by_text('Registration accepted', exact=True)).to_be_visible()
    login(page, address)
    expect(page.get_by_text(institution).first).to_be_visible()
    check('Accepted institution signs in with real account', '/institution' in page.url)
    finish(page, 'e2e-register')
    browser.close()
