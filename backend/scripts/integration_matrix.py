"""Build the operation matrix from evidence: contract, frontend call sites, smoke output, browser-run server logs.

Usage (from the repository root):
    python backend/scripts/integration_matrix.py . smoke-output.txt backend/var/integration-*  > matrix.md
smoke-output.txt is the saved stdout of ``python -m scripts.smoke``; each run folder is a ``scripts.e2e`` artifacts
folder holding server.log (one line per request with route and status). Nothing is assumed: an operation is
"Verified" only when smoke passed for every caller and a browser run reached it with a 2xx.
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

repo, smoke_file = Path(sys.argv[1]), Path(sys.argv[2])
run_dirs = [Path(p) for p in sys.argv[3:]]
request_line = re.compile(r'method=([A-Z]+) route=(\S+) status=(\d+)')
hits = defaultdict(lambda: defaultdict(set))   # (METHOD, route) -> status -> {script}
for d in run_dirs:
    log = d / 'server.log'
    if not log.exists():
        continue
    script = re.sub(r'^integration-|-(default|fixture|rate_limit|none)-[0-9a-f]{8}$', '', d.name)
    variant = re.search(r'-(fixture|rate_limit|none)-[0-9a-f]{8}$', d.name)
    if variant:
        script += f'[{variant.group(1)}]'
    for m in request_line.finditer(log.read_text(encoding='utf-8', errors='replace')):
        hits[(m.group(1), m.group(2))][m.group(3)].add(script)
spec = json.loads((repo / 'contracts/openapi.json').read_text(encoding='utf-8'))
ops = {}
for path, item in spec['paths'].items():
    for method, op in item.items():
        if isinstance(op, dict) and 'operationId' in op:
            ops[op['operationId']] = (method.upper(), path, op.get('tags', [''])[0])

call = re.compile(r'(?:api|callEndpoint|hasEndpoint|urlFor)(?:<[^>]*>)?\(\s*"([A-Za-z]+)"')
literal = re.compile(r'endpoint="([A-Za-z]+)"')
uses = {}
for f in sorted((repo / 'front/src').rglob('*.ts*')):
    if f.name == 'api.gen.ts':
        continue
    text = f.read_text(encoding='utf-8')
    rel = f.relative_to(repo / 'front/src').as_posix()
    for m in list(call.finditer(text)) + list(literal.finditer(text)):
        uses.setdefault(m.group(1), set()).add(rel)
    # Names passed through ternaries or variables, e.g. accept ? "acceptRegistration" : "declineRegistration".
    for name in ops:
        if f'"{name}"' in text:
            uses.setdefault(name, set()).add(rel)

smoke = {}
header = None
for line in smoke_file.read_text(encoding='utf-8', errors='replace').splitlines():
    parts = [p.strip() for p in line.split('|')]
    if parts[0] == 'Operation':
        header = parts
    elif header and len(parts) == len(header) and parts[0] in ops:
        smoke[parts[0]] = parts[1:]

# API-only by design (reasons in INTEGRATION_PROGRESS.md): token-only metrics; the UI reads the profile from `me`,
# notes from JobOut.ai_notes and versions from the application detail; profile edits have no screen (Question 2).
API_ONLY = {'metrics', 'getAccount', 'updateAccount', 'documentHistory', 'jobNotes'}


def state(name, ui, browser_ok):
    smoke_ok = name in smoke and 'FAIL' not in smoke[name]
    if not smoke_ok:
        return 'Partial' if name in smoke else 'Done, unverified'
    if not ui or name in API_ONLY:
        return 'Verified (API only)' if name in API_ONLY else 'Partial (no UI)'
    return 'Verified' if browser_ok else 'Partial (UI not exercised by a browser run)'


summary = defaultdict(int)
print('| Operation | Method and path | UI call sites | Smoke today (OUT / INST / OFF / ADMIN / AUD / invalid / foreign) | Browser runs today (status: scripts) | State |')
print('|---|---|---|---|---|---|')
for name in sorted(ops, key=lambda n: (ops[n][2], n)):
    method, path, _ = ops[name]
    ui_files = sorted(uses.get(name, []))
    ui = ', '.join(ui_files) or 'not called by UI'
    cells = ' / '.join(smoke[name]) if name in smoke else 'not in smoke output'
    seen = hits.get((method, path), {})
    browser = '; '.join(f'{status}: {", ".join(sorted(s))}' for status, s in sorted(seen.items())) or 'not hit'
    browser_ok = any(status.startswith('2') for status in seen)
    st = state(name, ui_files, browser_ok)
    summary[st] += 1
    print(f'| `{name}` | `{method} {path}` | {ui} | {cells} | {browser} | {st} |')
print()
print('State counts: ' + ', '.join(f'{k}: {v}' for k, v in sorted(summary.items())))
unknown = sorted(set(uses) - set(ops))
print()
print('Frontend names not in the contract (guarded by hasEndpoint, so they render nothing): ' + (', '.join(f'`{u}`' for u in unknown) or 'none'))
