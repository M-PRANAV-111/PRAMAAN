"""J9: tenant isolation, CSRF, rate-limit UI, outbox privacy and built-asset scan."""
import re
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
from core_support import base, password, out, check, login, finish

with sync_playwright() as p:
    browser = p.chromium.launch()
    context = browser.new_context()
    page = context.new_page()
    login(page, 'officer@aicte.synthetic.in')
    apps = context.request.get(base+'/api/v1/applications').json()
    foreign = next(a['id'] for a in apps if 'Godavari' in a['institution']['name'])
    page.get_by_role('button', name='Sign out', exact=True).click()
    login(page, 'nodal@deccan.synthetic.in')
    page.goto(base+'/applications/'+foreign)
    expect(page.get_by_text('This page does not exist', exact=False)).to_be_visible()
    check('foreign institution API returns 404', context.request.get(base+'/api/v1/applications/'+foreign).status == 404)
    response = context.request.post(base+'/api/v1/applications', data={'category':'EOA_EXISTING','academic_year':'2028-29'})
    check('cookie writes require CSRF header', response.status == 403)
    for route in ('/outbox/index.jsonl','/backend/var/outbox/index.jsonl','/api/v1/outbox'):
        response = context.request.get(base+route)
        check('outbox inaccessible '+route, response.status == 404 or 'text/html' in response.headers.get('content-type',''))
        check('no mail content exposed '+route, 'Content-Transfer-Encoding:' not in response.text())
    # Wait for the sign-out to finish: while the session cookie is still attached, a write without the
    # anti-forgery header is (correctly) refused with 403 and never reaches the rate limiter.
    with page.expect_response(lambda r: r.url.endswith('/api/v1/auth/logout')):
        page.get_by_role('button', name='Sign out', exact=True).click()
    page.wait_for_url(lambda url: '/login' in url or url.rstrip('/') == base)
    setup = [context.request.post(base+'/api/v1/auth/password/forgot', data={'email':'unregistered@example.test'},
                                  headers={'X-Requested-With': 'pramaan'}).status for _ in range(5)]
    check('rate-limit setup requests were accepted or limited, never refused', all(s in (202, 429) for s in setup))
    page.goto(base+'/forgot-password')
    page.get_by_label('Email', exact=False).fill('unregistered@example.test')
    page.get_by_role('button', name='Send reset link', exact=False).click()
    expect(page.get_by_text('Too many attempts. Wait a minute.', exact=True)).to_be_visible()
    check('rate limit produces friendly UI', True)
    finish(page, 'security')
    browser.close()

root = Path(__file__).resolve().parents[1]/'dist'
assets = '\n'.join(p.read_text('utf-8', errors='ignore') for p in root.rglob('*.js'))
patterns = [r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----', r'sk-ant-[A-Za-z0-9_-]{20,}',
            r'AKIA[0-9A-Z]{16}', r'pramaan-local-registrations', r'pramaan-session-identity']
for pattern in patterns:
    check('built assets exclude '+pattern, re.search(pattern, assets) is None)
