"""J5: browser reset flow invalidates the old server-side session."""
from playwright.sync_api import sync_playwright, expect
from core_support import *

with sync_playwright() as p:
    browser = p.chromium.launch()
    old = browser.new_page()
    address = 'nodal@deccan.synthetic.in'
    login(old, address)
    page = browser.new_page()
    page.goto(base + '/forgot-password')
    page.get_by_label('Email', exact=True).fill(address)
    page.get_by_role('button', name='Send reset link').click()
    expect(page.get_by_text('If an account exists', exact=False)).to_be_visible()
    page.goto(mail_link(address, '/reset-password'))
    new_password = password + '-Changed!'
    page.get_by_label('Password (', exact=False).fill(new_password)
    page.get_by_label('Confirm password', exact=True).fill(new_password)
    page.get_by_role('button', name='Set password').click()
    expect(page.get_by_text('Password saved.', exact=False)).to_be_visible()
    check('Old session returns 401 after reset', old.request.get(base + '/api/v1/auth/me').status == 401)
    login(page, address, new_password)
    check('New password signs into the real institution', '/institution' in page.url)
    finish(page, 'e2e-password')
    browser.close()
