"""Run browser checks against a fresh, isolated synthetic server per script.

Usage: python -m scripts.e2e [script.py ...]
Artifacts stay in ignored DATA_DIR; failures propagate as a nonzero exit code.
"""
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time

import requests

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent


def run(name, ai_variant=None):
    data = BACKEND / 'var' / ('integration-' + Path(name).stem + '-' + (ai_variant or 'default') + '-' + secrets.token_hex(4))
    data.mkdir(parents=True)
    password = secrets.token_urlsafe(24)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    base = f'http://127.0.0.1:{port}'
    env = {**os.environ, 'DATA_DIR': str(data), 'DATABASE_PATH': '', 'APP_ENV': 'test',
           'SEED_DEMO_PASSWORD': password, 'EMAIL_PROVIDER': 'console', 'NOTIFY_EMAIL': 'false',
           'BACKUP_SCHEDULE': 'false', 'SENTRY_DSN': '', 'AI_PROVIDER': 'none', 'AI_TEST_FAULT': '',
           'WORKER_THREADS': '1', 'FRONT_DIST': str(ROOT/'front/dist'), 'PUBLIC_BASE_URL': base,
           'SHOW_DEMO_ACCOUNTS': 'true', 'LOGIN_RATE_PER_MINUTE': '1000', 'UPLOAD_RATE_PER_MINUTE': '1000',
           'PRAMAAN_DEMO_DIR': str(data/'demo_files'), 'PRAMAAN_OUTBOX': str(data/'outbox'), 'PYTHONUTF8': '1'}
    seed = subprocess.run([sys.executable, '-m', 'synthetic.seed'], cwd=BACKEND, env=env,
                          capture_output=True)
    if seed.returncode:
        print('FAIL', name, 'seed failed')
        (data/'seed-error.txt').write_bytes(seed.stderr)
        return False
    env.pop('SEED_DEMO_PASSWORD')
    if ai_variant:
        env['AI_PROVIDER'] = 'none' if ai_variant == 'none' else 'fixture'
        env['AI_TEST_FAULT'] = 'rate_limit' if ai_variant == 'rate_limit' else ''
        env['PRAMAAN_AI_VARIANT'] = ai_variant
    with (data/'server.log').open('w', encoding='utf-8') as log:
        server = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app.main:app', '--port', str(port),
                                   '--no-proxy-headers'], cwd=BACKEND, env=env, stdout=log, stderr=log)
        try:
            for _ in range(150):
                try:
                    if requests.get(base+'/api/v1/health', timeout=1).ok:
                        break
                except requests.ConnectionError:
                    time.sleep(.1)
            else:
                print('FAIL', name, 'server startup')
                return False
            args = [base, str(data/'screenshots')] if name == 'journey_check.py' else [base, password, str(data/'screenshots')]
            if name == 'measure_page.py':
                args = [base]
            result = subprocess.run([sys.executable, str(ROOT/'front/e2e'/name), *args],
                                    cwd=ROOT/'front', env=env, capture_output=True, timeout=420)
            (data/'browser.txt').write_bytes(result.stdout + b'\n' + result.stderr)
            output = result.stdout.decode('utf-8', errors='replace')
            ok = result.returncode == 0 and not any(line.startswith('FAIL') for line in output.splitlines())
            print(('PASS' if ok else 'FAIL'), name, 'artifacts:', data, flush=True)
            if not ok:
                print((output + result.stderr.decode('utf-8', errors='replace'))[-6000:])
            return ok
        finally:
            server.terminate()
            server.wait(timeout=20)


def main():
    names = sys.argv[1:] or ['journey_check.py', 'signin_check.py', 'walkthrough.py',
                             'accounts_check.py', 'tracking_check.py', 'processing_check.py',
                             'inventory_check.py', 'a11y_check.py', 'measure_page.py',
                             *[p.name for p in sorted((ROOT/'front/e2e').glob('e2e_*.py'))]]
    outcomes = [run(name, variant) for name in names
                for variant in (('fixture', 'rate_limit', 'none') if name == 'e2e_ai.py' else (None,))]
    print(f'{sum(outcomes)}/{len(outcomes)} browser scripts passed')
    sys.exit(0 if all(outcomes) else 1)


if __name__ == '__main__':
    main()
