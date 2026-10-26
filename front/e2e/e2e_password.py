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

    # A1 Account page: three sessions of one officer (each new_page is its own browser context).
    officer = 'officer@aicte.synthetic.in'
    me, second, third = browser.new_page(), browser.new_page(), browser.new_page()
    for p_ in (me, second, third):
        login(p_, officer)
    signed_in = lambda p_: p_.request.get(base + '/api/v1/auth/me').status == 200
    me.goto(base + '/account')
    sessions = me.locator('section').filter(has_text='Active sessions').locator('li')
    expect(sessions).to_have_count(3)
    with me.expect_response(lambda r: r.url.endswith('/api/v1/auth/refresh') and r.request.method == 'POST') as refreshed:
        me.get_by_role('button', name='Refresh this session', exact=True).click()
    expect(me.get_by_text('Session refreshed', exact=True)).to_be_visible()
    check('Refresh this session renews the real session', refreshed.value.status == 200 and signed_in(me))
    sessions.get_by_role('button', name='Revoke', exact=True).first.click()
    expect(sessions).to_have_count(2)
    check('Revoke ends exactly one other session', [signed_in(second), signed_in(third)].count(False) == 1 and signed_in(me))
    me.get_by_role('button', name='Revoke other sessions', exact=True).click()
    expect(me.get_by_text('Other sessions revoked', exact=True)).to_be_visible()
    expect(sessions).to_have_count(1)
    check('Revoke other sessions keeps only this one', not signed_in(second) and not signed_in(third) and signed_in(me))
    officer_password = password + '-Rotated-2!'  # the policy refuses passwords containing the email name
    me.get_by_label('Current password', exact=True).fill(password)
    me.get_by_label('New password', exact=False).fill(officer_password)
    me.get_by_role('button', name='Update password', exact=True).click()
    expect(me.get_by_text('Password updated', exact=True)).to_be_visible()
    check('Changing the password keeps the current session', signed_in(me))
    fresh = browser.new_page()
    login(fresh, officer, officer_password)
    check('The changed password signs in', '/queue' in fresh.url)
    finish(page, 'e2e-password')
    browser.close()
