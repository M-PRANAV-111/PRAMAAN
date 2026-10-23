"""Readable evidence report using only Helvetica and the PRAMAAN palette."""
import io
import re
from xml.sax.saxutils import escape

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether

from ..db import now_iso

PALETTE = {k:HexColor(v) for k,v in {'paper':'#f2f5f0','ink':'#1d2b4f','deficiency':'#b4232c',
           'review':'#9a6410','verified':'#2e6b4e','processing':'#5b4e9a'}.items()}
DISCLAIMER = 'Decision support only — not an approval or a rejection. Officials decide.'


def render_report(application, findings, verifications, events, audit_head):
    buf = io.BytesIO()
    ink,paper = PALETTE['ink'],PALETTE['paper']
    styles = {name:ParagraphStyle(name,fontName='Helvetica',fontSize=size,leading=size*1.4,textColor=ink,
                                 spaceAfter=space,splitLongWords=True,keepWithNext=keep)
              for name,size,space,keep in [('body',9,5,False),('title',26,16,True),('heading',14,10,True),('small',8,4,False)]}
    def p(text,style='body',color=None):
        text = str(text if text is not None else 'Not recorded')
        # Regulatory inputs may use "approved intake"; the report describes the recorded value.
        text = re.sub(r'\bapproved\b', 'recorded', text, flags=re.IGNORECASE)
        text = text.replace('\x00','').replace('\u2011','-')
        value = escape(text).replace('\n','<br/>')
        if color:
            value = f'<font color="{color}">{value}</font>'
        return Paragraph(value,styles[style])
    story=[]
    def add(label,value):
        story.append(p(f'{label}: {value}'))
    def heading(title):
        story.extend([Spacer(1,10),p(title,'heading')])
    def table(rows,widths):
        t=Table([[p(v,'small') for v in row] for row in rows],colWidths=widths,repeatRows=1,hAlign='LEFT')
        t.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('BACKGROUND',(0,0),(-1,0),paper),
                              ('LINEBELOW',(0,0),(-1,0),1,ink),('LINEBELOW',(0,1),(-1,-1),.3,ink),
                              ('LEFTPADDING',(0,0),(-1,-1),6),('RIGHTPADDING',(0,0),(-1,-1),6),
                              ('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]))
        story.append(t)
    story.append(p('PRAMAAN','title'))
    story.append(p('Verification report','heading'))
    for label,value in [('Application',application['id']),('Institution',application['institution']['name']),
                        ('Permanent ID',application['institution']['aicte_permanent_id']),('Category',application['category_label']),
                        ('Academic year',application['academic_year']),('Status',application['status']),
                        ('Generated at (UTC)',now_iso()),('Rule pack version',application['rule_pack_version'])]:
        add(label,value)
    notice=Table([[p(DISCLAIMER)]],colWidths=[491])
    notice.setStyle(TableStyle([('BOX',(0,0),(-1,-1),1,ink),('BACKGROUND',(0,0),(-1,-1),paper),
                               ('TOPPADDING',(0,0),(-1,-1),12),('BOTTOMPADDING',(0,0),(-1,-1),12)]))
    story.extend([Spacer(1,14),notice])
    if application['institution']['aicte_permanent_id'].upper().startswith('1-SYN-') or '(synthetic)' in application['institution']['name'].lower():
        story.extend([Spacer(1,12),p('SYNTHETIC DEMO DATA','heading','#5b4e9a')])
    heading('Summary')
    for label,value in application['counts'].items():
        add(label.capitalize(),value)
    heading('Checklist and document versions')
    table([['Document','Version','Processing / verification']]+[[item['label'],
           str(item['document']['version']) if item['document'] else 'Missing',
           (item['document']['processing_state']+' / '+str(item['document']['verification_status'] or 'Declaration')) if item['document'] else 'Not uploaded']
           for item in application['checklist']],[235,55,201])
    story.append(PageBreak())
    heading('Active findings')
    active=[f for f in findings if f['state'] in ('OPEN','CONFIRMED','ESCALATED','CLARIFICATION_REQUESTED')]
    if not active:
        story.append(p('No active findings. This does not constitute an official decision.'))
    for f in active:
        block_start=len(story)
        story.append(p(f['title'],'heading','#b4232c' if f['severity']=='DEFICIENCY' else '#9a6410'))
        add('Severity / state',f"{f['severity']} / {f['state']}")
        add('Explanation',f['explanation'])
        rule=f['proof'].get('rule') or {}
        clause=rule.get('clause') or {}
        add('Rule / version',f"{f['rule_id'] or 'Indicator'} / {rule.get('version','Not applicable')}")
        add('Clause / status',f"{clause.get('ref','Not applicable')} / {clause.get('status','Not applicable')}")
        for e in f['evidence']:
            if e.get('other_application') and not e.get('document_id'):
                add('Evidence',e.get('document_name'))
                continue
            add('Evidence document',e.get('document_name') or e.get('document_id'))
            box=[round(float(v),3) for v in e['bbox']] if e.get('bbox') else 'Not recorded'
            add('Page / box coordinates',f"{e.get('page') or 'Not recorded'} / {box}")
            add('Value',e.get('value'))
            add('Extractor / confidence',f"{e.get('extractor') or 'Not recorded'} / {e.get('confidence') if e.get('confidence') is not None else 'Not recorded'}")
        doc_ids={e.get('document_id') for e in f['evidence']}
        for v in verifications:
            if v['document_id'] in doc_ids:
                add('Verification attempt',f"{v['channel']} / {v['status']}" + (' / Simulated source' if v['simulated'] else ''))
                add('Source detail',v['detail'].get('reason','No further detail'))
        add('Remedy',f['remedy'])
        if not f['reviews']:
            add('Officer decision','Not recorded')
        for review in f['reviews']:
            add('Officer decision',f"{review['decision']} — {review['reviewer_name']}")
            add('Reason',review['reason'])
        for reply in f['responses']:
            add('Institution reply',f"{reply['author_name']} — {reply['text']}")
        block=story[block_start:]
        del story[block_start:]
        story.append(KeepTogether(block))
    heading('Resolved and dismissed findings')
    closed=[f for f in findings if f['state'] in ('RESOLVED','DISMISSED')]
    for f in closed:
        add(f['state'],f['title'])
    if not closed:
        story.append(p('None recorded.'))
    heading('Verification sources')
    for v in verifications:
        add(v['document_id'],f"{v['channel']} / {v['status']}"+(' / Simulated source' if v['simulated'] else ''))
    heading('Timeline excerpt (latest 30 events)')
    for event in events[-30:]:
        add(event['at'],event['title']+(' — '+event['detail'] if event['detail'] else ''))
    heading('Audit integrity')
    add('Audit head hash',audit_head)
    story.append(p('verify at /audit'))
    def page(canvas,doc):
        canvas.saveState()
        canvas.setFillColor(paper)
        canvas.rect(0,0,*A4,fill=1,stroke=0)
        canvas.setFillColor(ink)
        canvas.setStrokeColor(ink)
        canvas.setFont('Helvetica',8)
        canvas.drawString(52,28,'PRAMAAN prototype | Decision support only')
        canvas.drawRightString(A4[0]-52,28,str(doc.page))
        canvas.restoreState()
    SimpleDocTemplate(buf,pagesize=A4,rightMargin=52,leftMargin=52,topMargin=45,bottomMargin=48,
                      title='PRAMAAN verification report',author='PRAMAAN prototype').build(story,onFirstPage=page,onLaterPages=page)
    return buf.getvalue()
