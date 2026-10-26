"""Part B in a real browser against a real seeded server: AI status, grounded values, suggestions and their
officer review, routing with reasons, injected failures and the data policy.

Run through ``python -m scripts.e2e``, which starts one fresh server per variant and declares it in
PRAMAAN_AI_VARIANT; the script cross-checks the declaration against the server's own AI status.

  fixture     AI_PROVIDER=fixture: hand-authored recorded answers (APP_ENV=test only), labelled simulated
  rate_limit  the same provider with AI_TEST_FAULT=rate_limit: every provider request fails with HTTP 429
  none        AI off

The uploaded documents are synthetic and stamped as such, except one deliberately unstamped file that the data
policy must keep away from any provider.
"""
import io
import os
import sys
from datetime import date
from pathlib import Path

from playwright.sync_api import expect, sync_playwright
from reportlab.pdfgen import canvas

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))
from synthetic import generator as g  # noqa: E402
from synthetic import variants as v  # noqa: E402

base, password, out = sys.argv[1].rstrip('/'), sys.argv[2], Path(sys.argv[3])
out.mkdir(parents=True, exist_ok=True)
variant = os.environ.get('PRAMAAN_AI_VARIANT', 'none')
api = base + '/api/v1'
OUTCOMES = ('READY_FOR_SCRUTINY', 'CORRECTIONS_REQUIRED', 'OFFICER_REVIEW_REQUIRED')
INST = g.Inst('Deccan Institute of Technology (Synthetic)', '1-SYN-7742-0004')
results = []
errors = []


def check(name, condition):
    results.append(bool(condition))
    print(('PASS' if condition else 'FAIL'), name, flush=True)


def sign_in(context, email):
    page = context.new_page()
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.goto(base + '/login')
    page.get_by_label('Email', exact=True).fill(email)
    page.get_by_label('Password', exact=True).fill(password)
    page.get_by_role('button', name='Sign in', exact=True).click()
    page.wait_for_url(lambda url: '/login' not in url)
    return page


def unstamped_noc():
    """A fire NOC without the SYNTHETIC stamp line: under the default policy it must never reach a provider."""
    buf = io.BytesIO()
    pdf = canvas.Canvas(buf)
    pdf.drawString(50, 760, 'FIRE SAFETY NO OBJECTION CERTIFICATE')
    pdf.drawString(50, 730, 'Valid Upto: 31-03-2027')
    pdf.save()
    return buf.getvalue()


with sync_playwright() as pw:
    browser = pw.chromium.launch()

    # ------------------------------------------------------------ AI status, shown to an administrator (B5)
    admin_ctx = browser.new_context(viewport={'width': 1440, 'height': 1000})
    admin = sign_in(admin_ctx, 'admin@aicte.synthetic.in')
    status = admin_ctx.request.get(api + '/ai/status').json()
    check('server AI status matches the declared variant', status['provider'] == ('none' if variant == 'none' else 'fixture'))
    check('AI status carries no key field', not [k for k in status if 'key' in k.lower()])
    check('only the recorded fixture is labelled simulated', status.get('simulated') is (variant != 'none'))
    admin.goto(base + '/admin/system')
    panel = admin.locator('[data-ai-status]')
    expect(panel).to_contain_text(status['provider'])
    if status.get('simulated'):
        expect(panel.get_by_text('Simulated — recorded test answers', exact=True)).to_be_visible()
    admin.screenshot(path=out / 'ai-status.png', full_page=True)

    # ------------------------------------------------------------ institution uploads through the UI
    ctx = browser.new_context(viewport={'width': 1440, 'height': 1000})
    page = sign_in(ctx, 'nodal@deccan.synthetic.in')
    page.get_by_role('button', name='Start an application').first.click()
    page.get_by_role('button', name='Create application', exact=True).click()
    page.wait_for_url('**/applications/**')
    application = page.url.split('/applications/')[1].split('?')[0]

    def upload(slot, path):
        with page.expect_response(lambda r: r.request.method == 'POST' and r.url.endswith('/documents'), timeout=60000) as resp:
            page.set_input_files('#up-' + slot, str(path))
        payload = resp.value.json()
        for _ in range(240):
            job = ctx.request.get(api + '/jobs/' + payload['job']['id']).json()
            if job['state'] in ('DONE', 'FAILED'):
                break
            page.wait_for_timeout(500)
        check(f'{slot}: UI upload finishes a real backend job', job['state'] == 'DONE')
        journey = page.get_by_role('region', name='Document verification journey')
        expect(journey).to_have_attribute('data-stage-code', 'DONE', timeout=15000)
        stages = journey.locator('[data-stage-history] [data-code]')
        expect(stages).to_have_count(len(job['stage_history']))
        check(f'{slot}: UI stage history equals the recorded backend stages',
              stages.evaluate_all('(nodes) => nodes.map(n => n.dataset.code)') == job['stage_history'])
        return job, payload['document']['id'], journey

    # The template extractor reads none of this two-column form, so every rule-read field is an AI target.
    table = out / 'two-column-affidavit.pdf'
    table.write_bytes(v.affidavit_variant('two_column', INST, '2026-27', 120, 60, date(2026, 1, 7)))
    job, affidavit, journey = upload('affidavit', table)
    history = job['stage_history']
    evidence = ctx.request.get(api + '/documents/' + affidavit + '/evidence').json()
    ai_claims = [c for c in evidence['claims'] if c['extractor'] in ('ai+text', 'ai+ocr')]
    check('routing ran as a recorded stage', 'ROUTING' in history)
    if variant == 'fixture':
        check('AI extraction ran as a recorded stage', 'AI_EXTRACTION' in history)
        # Extraction answered; only the finding-wording step has no recording, and it says so.
        check('extraction answered; only the unrecorded wording step is noted', job['ai_notes'] == ['AI step skipped: no_fixture'])
        expect(journey.get_by_text('AI-assisted analysis', exact=False)).to_be_visible()
        intake = [c for c in ai_claims if c['field'] == 'total_intake']
        check('printed value grounded as a claim with a real page box',
              len(intake) == 1 and intake[0]['value_norm'] == '120'
              and intake[0]['bbox'][2] > intake[0]['bbox'][0] and intake[0]['bbox'][3] > intake[0]['bbox'][1])
        check('contradicting value is a suggestion, never a claim',
              [(s['field'], s['value'], s['reason']) for s in evidence['ai_suggestions']] == [('faculty_count', '999999', 'conflicts_with_page')]
              and all(c['value_norm'] != '999999' for c in evidence['claims']))
        expect(journey.locator('[data-ai-suggestion="faculty_count"]')).to_contain_text('differs from what the page shows')
    elif variant == 'rate_limit':
        check('AI extraction stage was entered', 'AI_EXTRACTION' in history)
        check('the 429 is recorded as a skip note', job['ai_notes'] == ['AI step skipped: rate_limited'])
        expect(journey.get_by_text('AI step skipped: rate_limited', exact=True)).to_be_visible()
        check('deterministic result kept: no AI claim or suggestion', not ai_claims and not evidence['ai_suggestions'])
        after = admin_ctx.request.get(api + '/ai/status').json()
        check('status reports the failure and the fallback', after['last_error_code'] == 'rate_limited' and after['fallback_active'])
    else:
        check('AI off: no AI stage, note, claim or suggestion',
              'AI_EXTRACTION' not in history and not job['ai_notes'] and not ai_claims and not evidence['ai_suggestions'])
    page.screenshot(path=out / 'ai-journey.png', full_page=True)

    # ------------------------------------------------------------ data policy (B7)
    requests_before = admin_ctx.request.get(api + '/ai/status').json()['requests_today']
    noc = out / 'unstamped-noc.pdf'
    noc.write_bytes(unstamped_noc())
    policy_job, _, journey = upload('fire_noc', noc)
    requests_after = admin_ctx.request.get(api + '/ai/status').json()['requests_today']
    check('an unstamped file causes no provider request', requests_after == requests_before)
    if variant != 'none':
        check('the data policy is recorded as a skip note', policy_job['ai_notes'] == ['AI step skipped: data_policy'])
        expect(journey.get_by_text('AI step skipped: data_policy', exact=True)).to_be_visible()
    else:
        check('AI off: the unstamped file has no AI stage', 'AI_EXTRACTION' not in policy_job['stage_history'])

    # ------------------------------------------------------------ routing recommendation (B3)
    detail = ctx.request.get(api + '/applications/' + application).json()
    documents = {d['id'] for d in detail['documents']}
    findings = {f['id'] for f in ctx.request.get(api + '/applications/' + application + '/findings').json()}
    routing = ctx.request.get(api + '/applications/' + application + '/routing').json()
    codes = [r['code'] for r in routing['reasons']]
    check('routing outcome is one of the three', routing['outcome'] in OUTCOMES)
    check('every routing reason points into this application', bool(routing['reasons']) and all(
        (r.get('finding_id') is None or r['finding_id'] in findings) and (r.get('document_id') is None or r['document_id'] in documents)
        for r in routing['reasons']))
    check('routing reports AI use only when the provider answered', routing['ai_used'] is (variant == 'fixture'))
    check('an open AI suggestion keeps the case from READY',
          (routing['outcome'] != 'READY_FOR_SCRUTINY' and 'AI_SUGGESTION_UNCONFIRMED' in codes) if variant == 'fixture'
          else 'AI_SUGGESTION_UNCONFIRMED' not in codes)
    card = page.locator('[data-outcome-card]').last
    expect(card).to_have_attribute('data-outcome', routing['outcome'])
    if variant == 'fixture':
        expect(card.locator('[data-reason-code="AI_SUGGESTION_UNCONFIRMED"]')).to_be_visible()

    # ------------------------------------------------------------ officer reviews the suggestion (B2)
    if variant == 'fixture':
        page.get_by_role('button', name='Submit to AICTE', exact=True).first.click()
        page.get_by_role('dialog').get_by_role('button', name='Submit to AICTE', exact=True).click()
        expect(page.get_by_text('Submitted to AICTE', exact=False).first).to_be_visible()
        officer_ctx = browser.new_context(viewport={'width': 1440, 'height': 1000})
        officer = sign_in(officer_ctx, 'officer@aicte.synthetic.in')
        officer.goto(base + '/applications/' + application + '?tab=documents')
        officer.locator('li').filter(has_text='two-column-affidavit.pdf').get_by_role('button', name='View what was read').click()
        dialog = officer.get_by_role('dialog')
        suggestions = dialog.locator('[data-ai-suggestions]')
        expect(suggestions).to_contain_text('999999')
        expect(dialog.get_by_text('AI-assisted, matched on the text layer', exact=False).first).to_be_visible()
        suggestions.get_by_label('Reason for', exact=False).fill('The page shows 60 regular faculty; the suggested value is not on it.')
        suggestions.get_by_role('button', name='Dismiss suggestion', exact=True).click()
        expect(officer.get_by_text('Suggestion dismissed in the audit trail', exact=True)).to_be_visible()
        expect(dialog.locator('[data-ai-suggestions]')).to_have_count(0)
        officer.screenshot(path=out / 'suggestion-dismissed.png', full_page=True)
        after = officer_ctx.request.get(api + '/applications/' + application + '/routing').json()
        check('dismissal clears the suggestion reason from routing', 'AI_SUGGESTION_UNCONFIRMED' not in [r['code'] for r in after['reasons']])
        check('reviewed suggestion drops out of the evidence',
              officer_ctx.request.get(api + '/documents/' + affidavit + '/evidence').json()['ai_suggestions'] == [])
        audit = officer_ctx.request.get(api + '/audit?application_id=' + application + '&limit=500').json()
        check('dismissal is in the audit trail', any(e['action'] == 'ai.suggestion_dismiss' for e in audit))

        # The administrator's kill switch turns AI off at runtime and back on; both changes need a reason.
        admin.goto(base + '/admin/system')
        admin.get_by_label('Reason (recorded in the audit trail)').fill('Integration test: pausing AI assistance briefly.')
        admin.get_by_role('button', name='Engage the AI kill switch', exact=True).click()
        expect(admin.get_by_text('AI kill switch engaged', exact=True)).to_be_visible()
        engaged = admin_ctx.request.get(api + '/ai/status').json()
        check('kill switch turns AI off', engaged['kill_switch'] is True and engaged['mode'] == 'off')
        check('AI feature flag follows the kill switch', admin_ctx.request.get(api + '/meta').json()['features'].get('ai') is False)
        admin.get_by_label('Reason (recorded in the audit trail)').fill('Integration test: resuming AI assistance.')
        admin.get_by_role('button', name='Release the AI kill switch', exact=True).click()
        expect(admin.get_by_text('AI kill switch released', exact=True)).to_be_visible()
        check('kill switch release restores the mode', admin_ctx.request.get(api + '/ai/status').json()['mode'] == 'synthetic_only')

    check('no browser execution errors', not errors)
    browser.close()

print(f'{sum(results)}/{len(results)} AI checks passed')
sys.exit(0 if all(results) else 1)
