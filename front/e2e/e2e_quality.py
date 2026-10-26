"""J10: keyboard login, narrow/reduced-motion views, real empty and recoverable errors."""
from playwright.sync_api import sync_playwright, expect
from core_support import base, password, check, login, finish

with sync_playwright() as p:
    browser = p.chromium.launch()
    context = browser.new_context(viewport={'width':360,'height':800}, reduced_motion='reduce')
    page = context.new_page()
    page.goto(base+'/login')
    # Keyboard traversal reaches the real form without clicking a control.
    for _ in range(40):
        page.keyboard.press('Tab')
        if page.get_by_label('Email', exact=True).evaluate('(el) => el === document.activeElement'):
            break
    check('email reachable by keyboard', page.get_by_label('Email', exact=True).evaluate('(el) => el === document.activeElement'))
    page.keyboard.type('officer@aicte.synthetic.in')
    # The "Show password" toggle sits between the two fields in tab order.
    password_field = page.get_by_label('Password', exact=True)
    for _ in range(5):
        page.keyboard.press('Tab')
        if password_field.evaluate('(el) => el === document.activeElement'):
            break
    check('password reachable by keyboard', password_field.evaluate('(el) => el === document.activeElement'))
    page.keyboard.type(password)
    page.keyboard.press('Enter')
    expect(page.get_by_role('heading', name='Scrutiny queue')).to_be_visible()
    check('keyboard sign-in reaches queue', True)
    search = page.get_by_label('Search by institution name or Permanent ID')
    search.fill('no-such-synthetic-institution')
    expect(page.locator('tbody tr')).to_have_count(0)
    check('empty search has visible result count', page.get_by_text('0 applications', exact=False).count() > 0 or page.get_by_text('No applications', exact=False).count() > 0)
    for url in ('/queue','/account','/notifications','/help'):
        page.goto(base+url)
        expect(page.locator('h1')).to_be_visible()
        check('no horizontal overflow '+url, page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'))
    # Browser offline mode is test-only fault injection, not a fake production API.
    page.goto(base+'/queue')
    context.set_offline(True)
    page.get_by_label('Search by institution name or Permanent ID').fill('network-failure-case')
    expect(page.get_by_text('Cannot reach the PRAMAAN server', exact=False)).to_be_visible()
    expect(page.get_by_role('button', name='Retry', exact=True)).to_be_visible()
    context.set_offline(False)
    page.get_by_role('button', name='Retry', exact=True).click()
    expect(page.get_by_text('Cannot reach the PRAMAAN server', exact=False)).to_have_count(0)
    check('offline error recovers with Retry', True)
    page.goto(base+'/')
    check('reduced motion requested', page.evaluate("matchMedia('(prefers-reduced-motion: reduce)').matches"))
    check('landing fits 360px', page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'))
    finish(page, 'quality')
    browser.close()
