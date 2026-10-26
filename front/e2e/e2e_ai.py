"""Real UI upload and evidence checks for fixture, fallback and disabled AI servers.

Run with scripts.e2e; mode is read from the server's admin status, never assumed.
The provider fixtures are deliberately recorded synthetic examples, not live AI.
"""
import io
import json
import sys
import time
from datetime import date
from pathlib import Path

from playwright.sync_api import sync_playwright, expect
from reportlab.pdfgen import canvas

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'backend'))
from synthetic import generator as g

base,password,out=sys.argv[1],sys.argv[2],Path(sys.argv[3])
out.mkdir(parents=True,exist_ok=True)
results=[]


def check(name, condition):
    results.append(bool(condition))
    print(('PASS' if condition else 'FAIL'),name,flush=True)


with sync_playwright() as pw:
    browser=pw.chromium.launch()
    context=browser.new_context(viewport={'width':1440,'height':1000})
    page=context.new_page()
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(base+'/login')
    page.get_by_label('Email').fill('nodal@deccan.synthetic.in')
    page.get_by_label('Password').fill(password)
    page.get_by_role('button',name='Sign in',exact=True).click()
    page.wait_for_url(lambda url:'/login' not in url)
    page.get_by_role('button',name='Start an application').first.click()
    page.get_by_role('button',name='Create application',exact=True).click()
    page.wait_for_url('**/applications/**')
    application=page.url.split('/applications/')[1].split('?')[0]
    api=base+'/api/v1'
    data=g.affidavit(g.Inst('Deccan Institute of Technology (Synthetic)','1-SYN-TEST'),'2026-27',120,60,date(2026,1,1))
    source=out/'synthetic-grounding.pdf'
    source.write_bytes(data)

    def upload(path):
        with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/documents'),timeout=60000) as response:
            page.set_input_files('#up-affidavit',str(path))
        payload=response.value.json()
        jid=payload['job']['id']
        for _ in range(180):
            job=context.request.get(api+'/jobs/'+jid).json()
            if job['state'] in ('DONE','FAILED'):
                break
            page.wait_for_timeout(500)
        check('UI upload finishes a real backend job',job['state']=='DONE')
        journey=page.get_by_role('region',name='Document verification journey')
        expect(journey).to_have_attribute('data-stage-code','DONE',timeout=10000)
        stage_list=journey.locator('[data-stage-history] [data-code]')
        expect(stage_list).to_have_count(len(job['stage_history']))
        observed=stage_list.evaluate_all('(nodes)=>nodes.map(n=>n.dataset.code)')
        check('UI stage history exactly matches recorded backend stages',observed==job['stage_history'])
        return job,payload['document']['id'],journey

    job,did,journey=upload(source)
    evidence=context.request.get(api+'/documents/'+did+'/evidence').json()
    if 'AI_EXTRACTION' in job['stage_history'] and not job['ai_notes']:
        expect(journey.get_by_text('AI-assisted',exact=False)).to_be_visible()
        expect(journey.get_by_text('AI suggestion — not found on the page, not used:',exact=False)).to_be_visible()
        grounded=[c for c in evidence['claims'] if c['extractor'] in ('ai+text','ai+ocr')]
        check('Grounded claims have actual page boxes',bool(grounded) and all(c['bbox'][2]>c['bbox'][0] and c['bbox'][3]>c['bbox'][1] for c in grounded))
        check('Unsupported suggestion is excluded from rule claims',any(s['value']=='999999' for s in evidence['ai_suggestions']) and all(c['value_norm']!='999999' for c in evidence['claims']))
    elif job['ai_notes']:
        expect(journey.get_by_text('AI step skipped: rate_limit',exact=True)).to_be_visible()
        check('Fallback keeps deterministic extraction',all(not c['extractor'].startswith('ai+') for c in evidence['claims']))
    else:
        check('Disabled AI has no AI extraction stage','AI_EXTRACTION' not in job['stage_history'])
        expect(journey.get_by_text('AI-assisted',exact=False)).to_have_count(0)
    routing=context.request.get(api+'/applications/'+application+'/routing').json()
    check('Routing reasons point to application evidence',bool(routing['reasons']) and all(r['link'].startswith('/applications/'+application) for r in routing['reasons']))
    expect(journey.locator('[data-outcome-card] a').first).to_be_visible()
    findings=context.request.get(api+'/applications/'+application+'/findings').json()
    signature=sorted((f['rule_id'],f['severity'],f['title'],f['explanation']) for f in findings if f['source_kind']=='RULE')
    (out/'findings-signature.json').write_text(json.dumps(signature),encoding='utf-8')
    (out/'stages.json').write_text(json.dumps({'backend':job['stage_history'],'ui':journey.locator('[data-stage-history] [data-code]').evaluate_all('(nodes)=>nodes.map(n=>n.dataset.code)')}),encoding='utf-8')
    page.screenshot(path=out/'ai-journey.png',full_page=True)

    unstamped=out/'unstamped.pdf'
    buf=io.BytesIO()
    pdf=canvas.Canvas(buf)
    pdf.drawString(50,750,'AFFIDAVIT Total intake sought: 120')
    pdf.save()
    unstamped.write_bytes(buf.getvalue())
    policy,_,journey=upload(unstamped)
    if 'AI_EXTRACTION' in job['stage_history']:
        expect(journey.get_by_text('AI step skipped: data_policy',exact=True)).to_be_visible()
        check('Unstamped evidence skips external AI','AI_EXTRACTION' not in policy['stage_history'])
    check('No browser execution errors',not errors)
    page.screenshot(path=out/'data-policy.png',full_page=True)
    browser.close()

print(f'{sum(results)}/{len(results)} AI checks passed')
sys.exit(0 if all(results) else 1)
