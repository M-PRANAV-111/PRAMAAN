"""Real browser helpers. Mail is read only from the test server's local outbox."""
import email.policy
import os
import re
import sys
import time
from email.parser import BytesParser
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import expect

base, password, out = sys.argv[1].rstrip('/'), sys.argv[2], Path(sys.argv[3])
out.mkdir(parents=True, exist_ok=True)
outbox = Path(os.environ.get('PRAMAAN_OUTBOX', str(Path(__file__).resolve().parents[2] / 'backend/var/outbox')))
results = []

def check(name, condition):
    results.append(bool(condition))
    print(('PASS ' if condition else 'FAIL ') + name)
    assert condition, name

def login(page, address, pw=None):
    page.goto(base + '/login')
    page.get_by_label('Email', exact=True).fill(address)
    page.get_by_label('Password', exact=True).fill(pw or password)
    page.get_by_role('button', name='Sign in', exact=True).click()
    page.wait_for_url(lambda url: '/login' not in url)

def mail_link(address, path):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        for file in sorted(outbox.glob('*.eml'), key=lambda p: p.stat().st_mtime, reverse=True):
            msg = BytesParser(policy=email.policy.default).parsebytes(file.read_bytes())
            if address not in str(msg['To']):
                continue
            body = msg.get_body(preferencelist=('plain',)).get_content()
            for url in re.findall(r'https?://\S+', body):
                parsed = urlsplit(url)
                if parsed.path == path:
                    return base + parsed.path + '?' + parsed.query
        time.sleep(.1)
    raise AssertionError('Expected email link did not arrive')

def finish(page, name):
    page.screenshot(path=out / (name + '.png'), full_page=True)
    print(f'{len(results)}/{len(results)} checks passed')
