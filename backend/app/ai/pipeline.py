"""Conservative AI grounding and deterministic routing extension.

Values are accepted only with an exact visible field/value match; provider coordinates
and confidence are never trusted. Unsupported suggestions live outside the claims table.
"""
import re

from .. import audit, features
from ..db import dumps, loads, new_id, now_iso, reader
from ..pipeline import extract
from ..pipeline.doctypes import TEMPLATES
from ..pipeline.findings import ACTIVE_STATES, derive_status
from ..pipeline.hooks import register_step
from ..storage import LocalStorage
from .client import AIUnavailable, complete, settings


def note(c, job_id, reason):
    c.execute('INSERT OR IGNORE INTO ai_job_notes VALUES (?,?)', (job_id, reason))


def ground(result, doc_type, candidate):
    """Return only a verified, typed claim whose actual words identify the field."""
    if (not isinstance(candidate, dict) or not isinstance(candidate.get('value'), str)
            or type(candidate.get('page')) is not int):
        return None
    value = candidate['value']
    for spec in TEMPLATES.get(doc_type, []):
        if spec.field != candidate.get('field'):
            continue
        for line in result.lines:
            if line.page != candidate.get('page'):
                continue
            match = spec.pattern.search(line.text)
            if not match or match.group('v') != value:
                continue
            normalized = extract.normalize(value, spec.value_type)
            if normalized is None:
                return None
            bbox, confidence = extract._span_bbox(line, match.start('v'), match.end('v'))
            if confidence < 0.8:
                return None
            return extract.ExtractedClaim(spec.field, value, normalized, spec.value_type, line.page, bbox,
                line.page_width, line.page_height, 'ai+text' if line.source == 'text-layer' else 'ai+ocr',
                min(0.98, confidence))
    return None


def has_stamp(result):
    return any(re.search(r'\bSYNTHETIC\b', line.text) for line in result.lines)


def after_fields(c, job_id, doc, stage):
    s = settings()
    c.execute('DELETE FROM ai_suggestions WHERE document_id=?', (doc['id'],))
    if s.provider == 'none':
        return
    result = extract.extract_pdf(LocalStorage().get(doc['sha256']))
    if not has_stamp(result):
        note(c, job_id, 'data_policy')
        return
    stage('AI_EXTRACTION', 'AI-assisted extraction with page grounding', 47)
    try:
        response = complete(c, job_id, 'extraction', {
            'task': 'Extract only these fields. Return {"claims":[{"field":str,"value":exact visible text,"page":integer}]}.',
            'fields': [s.field for s in TEMPLATES.get(doc['doc_type'], [])],
            'pages': [{'page': line.page, 'text': line.text} for line in result.lines][:1000]})
        candidates = response.get('claims')
        if not isinstance(candidates, list) or len(candidates) > 100:
            raise AIUnavailable('invalid_json')
        for candidate in candidates:
            if not isinstance(candidate, dict) or not isinstance(candidate.get('field'), str) or not isinstance(candidate.get('value'), str):
                raise AIUnavailable('invalid_json')
        accepted = set()
        for candidate in candidates:
            claim = ground(result, doc['doc_type'], candidate)
            old = c.execute('SELECT * FROM claims WHERE document_id=? AND field=?', (doc['id'],candidate['field'])).fetchone()
            if claim and (not old or old['value_norm'] == claim.value_norm):
                if claim.field in accepted:
                    continue
                accepted.add(claim.field)
                # Preserve the deterministic value and confidence if already extracted.
                if old:
                    c.execute('UPDATE claims SET extractor=? WHERE id=?', (claim.extractor, old['id']))
                else:
                    c.execute('INSERT INTO claims (id,document_id,application_id,field,value_raw,value_norm,value_type,page,x0,y0,x1,y1,page_width,page_height,extractor,confidence) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                        (new_id('clm'),doc['id'],doc['application_id'],claim.field,claim.value_raw,claim.value_norm,claim.value_type,claim.page,*claim.bbox,claim.page_width,claim.page_height,claim.extractor,claim.confidence))
            else:
                page = candidate.get('page')
                c.execute('INSERT INTO ai_suggestions(document_id,field,value,page,reason,model) VALUES (?,?,?,?,?,?)',
                    (doc['id'],candidate['field'][:100],candidate['value'][:1000], page if type(page) is int and page > 0 else None,
                     'conflicts_with_page' if claim else 'not_found_on_page',s.model))
        audit.record(c,None,'ai.extraction','document',doc['id'],{'grounded_fields':sorted(accepted),'simulated':s.provider=='fixture'},doc['application_id'])
    except AIUnavailable as exc:
        note(c, job_id, str(exc))


def routing(c, application_id):
    findings = c.execute("SELECT * FROM findings WHERE application_id=? AND state IN ('OPEN','CONFIRMED','ESCALATED','CLARIFICATION_REQUESTED') ORDER BY id", (application_id,)).fetchall()
    reasons = [{'text': f['title'], 'finding_id': f['id'], 'document_id': None,
                'link': f"/applications/{application_id}?finding={f['id']}"} for f in findings if f['severity'] != 'INFO']
    severities = [f['severity'] for f in findings]
    docs = c.execute('SELECT * FROM documents WHERE application_id=? AND superseded_by IS NULL ORDER BY id', (application_id,)).fetchall()
    for d in docs:
        if d['processing_state'] != 'DONE' or d['verification_status'] not in ('VERIFIED',):
            severities.append('REVIEW')
            reasons.append({'text': f"{d['original_name']}: source or processing needs review", 'finding_id':None,
                            'document_id':d['id'],'link':f"/applications/{application_id}?document={d['id']}"})
    if not docs or not c.execute('SELECT 1 FROM validation_runs WHERE application_id=? LIMIT 1',(application_id,)).fetchone():
        severities.append('REVIEW')
        reasons.append({'text':'A completed validation and document evidence are required', 'finding_id':None,'document_id':None,'link':f'/applications/{application_id}'})
    if not reasons:
        reasons = [{'text': 'No open findings; source evidence is available', 'finding_id':None,'document_id':d['id'],
                    'link':f"/applications/{application_id}?document={d['id']}"} for d in docs]
    return {'outcome': derive_status(severities), 'reasons': reasons, 'advisory':True}


def after_rules(c, job_id, app, stage):
    stage('ROUTING', 'Routing for evidence-based scrutiny', 94)
    result = routing(c, app['id'])
    previous = c.execute('SELECT * FROM application_routing WHERE application_id=?',(app['id'],)).fetchone()
    encoded = dumps(result['reasons'])
    if not previous or previous['outcome'] != result['outcome'] or previous['reasons_json'] != encoded:
        c.execute('INSERT OR REPLACE INTO application_routing VALUES (?,?,?,?)',(app['id'],result['outcome'],encoded,now_iso()))
        audit.record(c,None,'routing.updated','application',app['id'],{'outcome':result['outcome']},app['id'])
    # Explanation assistance never transmits foreign-institution evidence. All current
    # PDF inputs must be stamped before the provider sees any derived finding text.
    s = settings()
    if s.provider == 'none' or c.execute('SELECT 1 FROM ai_job_notes WHERE job_id=?',(job_id,)).fetchone():
        return
    documents = c.execute("SELECT * FROM documents WHERE application_id=? AND superseded_by IS NULL",(app['id'],)).fetchall()
    if not documents or any(d['mime'] != 'application/pdf' or not has_stamp(extract.extract_pdf(LocalStorage().get(d['sha256']))) for d in documents):
        note(c,job_id,'data_policy')
        return
    for f in c.execute("SELECT * FROM findings WHERE application_id=? AND source_kind='RULE' AND state='OPEN'",(app['id'],)).fetchall():
        try:
            response = complete(c,job_id,'explanation',{'task':'Return JSON {"explanation":string} using exactly the supported explanation. Do not add claims or decisions.', 'supported_explanation':f['explanation']})
            # Exact evidence-bound entailment. Novel factual language is left as template.
            text = response.get('explanation')
            if text == f['explanation']:
                c.execute('INSERT OR REPLACE INTO ai_explanations VALUES (?,?,?,?)',(f['id'],f['explanation'],text,s.model))
        except AIUnavailable as exc:
            note(c,job_id,str(exc))
            break


def status():
    s = settings()
    with reader() as c:
        usage = c.execute('SELECT COUNT(*) FROM ai_calls WHERE created_at>=?',(now_iso()[:10],)).fetchone()[0]
        last = c.execute("SELECT status FROM ai_calls ORDER BY id DESC LIMIT 1").fetchone()
    error = last['status'] if last and last['status'] not in ('ok','started') else None
    return {'provider':s.provider,'model':s.model or None,'mode':'simulated' if s.provider=='fixture' else 'disabled' if s.provider=='none' else 'synthetic_only',
            'usage':usage,'budget':s.budget,'last_error':error,'fallback_active':s.provider=='none' or bool(error) or usage>=s.budget}


settings()  # Fail closed on prohibited fixture/fault configuration at startup.
register_step('after_fields', after_fields)
register_step('after_rules', after_rules)
features.register('ai',lambda: settings().provider!='none')
features.register('routing')
features.register_system_extra('ai',status)
