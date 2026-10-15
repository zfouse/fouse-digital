"""Rendered structural checks. Never activate contact schemes or submit controls."""
import json
import re
from urllib.parse import urljoin

if __package__:
    from .fit import link_kind
else:
    from fit import link_kind

CONTACT_PATTERN = r'\b(contact|quote|estimate|call|request|consultation|book|schedule|appointment)\b'
CONTACT = re.compile(CONTACT_PATTERN, re.I)

# Runs on the inspected page only, at each phone width. No event dispatch or input.
SNAPSHOT = r"""() => {
 const forms = [...document.forms].map(f => {
   let fields = [...f.elements].filter(e => /^(INPUT|SELECT|TEXTAREA)$/.test(e.tagName) && !/^(hidden|submit|button|reset|image)$/i.test(e.type||''));
   let names = fields.map(e => [e.name,e.id,e.type,e.autocomplete].join(' ')).join(' ');
   let inquiry = f.getAttribute('role') !== 'search' && !f.querySelector('input[type=search],input[type=password]') && fields.length >= 2 && /email|phone|tel|message|project|service|address/i.test(names) && !/newsletter|subscribe|login|sign.?in/i.test(f.id+' '+f.className);
   let submit = [...f.elements].filter(e => e.tagName === 'BUTTON' ? e.type === 'submit' : /^(submit|image)$/.test(e.type));
   return {inquiry, fields:fields.length, submit_controls:submit.length, disabled_submit:submit.some(e=>e.disabled),
     unlabeled_fields:fields.filter(e=>e.getClientRects().length && !(e.labels?.length || e.getAttribute('aria-label')?.trim() || e.title?.trim() || (e.getAttribute('aria-labelledby')||'').split(' ').some(id=>document.getElementById(id)?.textContent.trim()))).length};
 });
 const controls = [...document.querySelectorAll('a,button,input[type=submit]')].slice(0,250).map((el,i)=>{
   el.setAttribute('data-fouse-research-id',String(i));
   let r=el.getBoundingClientRect(),s=getComputedStyle(el),f=el.form;
   let fi=f?[...document.forms].indexOf(f):-1, inquiry=fi>=0 && forms[fi].inquiry;
   let submit=inquiry && (el.tagName==='BUTTON' && el.type==='submit' || el.type==='submit');
   let text=(el.getAttribute('aria-label')||el.innerText||el.value||'').trim().slice(0,100);
   let clip={left:0,right:innerWidth,top:0,bottom:innerHeight};
   for(let n=el.parentElement;n;n=n.parentElement){let ns=getComputedStyle(n),nr=n.getBoundingClientRect();if(/hidden|clip|scroll|auto/.test(ns.overflowX)){clip.left=Math.max(clip.left,nr.left);clip.right=Math.min(clip.right,nr.right)}}
   let range=document.createRange();range.selectNodeContents(el);let tr=range.getBoundingClientRect();
   let labelClipped=tr.width>0 && (tr.right>clip.right+3 || tr.left<clip.left-3);
   let centerClipped=(r.left+r.right)/2>clip.right || (r.left+r.right)/2<clip.left;
   let canPan=document.documentElement.scrollWidth>innerWidth+2 && !/hidden|clip/.test(getComputedStyle(document.documentElement).overflowX+' '+getComputedStyle(document.body).overflowX);
   return {id:String(i),text,href:el.getAttribute('href')||'',tag:el.tagName,submit,inquiry,disabled:!!el.disabled,
     visible:!el.closest('[hidden],[inert],[aria-hidden="true"]') && !!el.getClientRects().length && r.width>0 && r.height>0 && s.visibility!=='hidden' && s.opacity!=='0',
     top:r.top,bottom:r.bottom,left:r.left,right:r.right,label_clipped:labelClipped,center_clipped:centerClipped,can_pan:canPan};
 });
 return {width:innerWidth,scroll_width:document.documentElement.scrollWidth,forms,controls};
}"""


def has_activation_handlers(page, control_id):
    """Fail closed on any delegated/inline activation handler; CDP reads only."""
    session = page.context.new_cdp_session(page)
    group = 'fouse-contact-check'
    try:
        contexts={};scripts={}
        session.on('Runtime.executionContextCreated',lambda event:contexts.update({event['context']['id']:event['context']}))
        session.on('Debugger.scriptParsed',lambda event:scripts.update({event['scriptId']:event.get('executionContextId')}))
        session.send('Runtime.enable')
        session.send('Debugger.enable')
        def site_listener(listener):
            world=contexts.get(scripts.get(listener.get('scriptId')),{})
            # Chromium's isolated Playwright utility world is not site JavaScript.
            return not (world.get('auxData',{}).get('isDefault') is False and world.get('name','').startswith('__playwright_utility_world'))
        expression = '''(()=>{let e=document.querySelector('[data-fouse-research-id="%s"]');if(!e)return null;let nodes=[...e.querySelectorAll('*')];for(let n=e;n;n=n.parentNode)nodes.push(n);nodes.push(window);return nodes})()''' % int(control_id)
        obj = session.send('Runtime.evaluate', {'expression': expression, 'objectGroup': group})['result'].get('objectId')
        if not obj:
            return True
        props = session.send('Runtime.getProperties', {'objectId': obj, 'ownProperties': True})['result']
        nodes = [p['value']['objectId'] for p in props if p['name'].isdigit() and p.get('value', {}).get('objectId')]
        if len(nodes)>40:
            return True
        for node in nodes:
            listeners = session.send('DOMDebugger.getEventListeners', {'objectId': node})['listeners']
            if any(site_listener(l) and l['type'] in ('mouseenter','mouseover','mousemove','pointerenter','pointerover','pointermove','focus','focusin','click','auxclick','pointerdown','pointerup','touchstart','touchend','mousedown','mouseup','keydown','keypress','keyup') for l in listeners):
                return True
        return False
    except Exception:
        return True
    finally:
        session.send('Runtime.releaseObjectGroup', {'objectGroup': group})
        session.detach()


def mobile_findings(url, snapshots, clean):
    if len(snapshots)!=2:
        return []
    pairs = {}
    for snap in snapshots:
        for c in snap['controls']:
            if link_kind(urljoin(url,c['href']),c['text'])=='social':
                continue
            if not c['visible'] or c['disabled'] or not (CONTACT.search(c['text']) or c['submit']):
                continue
            if c['left']>=snap['width'] or c['right']<=0 or c['top']<0 or c['bottom']>844 or not c['label_clipped']:
                continue
            key=(c['id'], c['text'], c['href'])
            pairs.setdefault(key,[]).append({'width':snap['width'],'left':round(c['left'],1),'right':round(c['right'],1),
                'center_clipped':c['center_clipped'],'can_pan':c['can_pan'],'inquiry_submit':c['submit']})
    result=[]
    for (_,label,href),evidence in pairs.items():
        if len(evidence)!=2:
            continue
        proven=clean and all(m['center_clipped'] and not m['can_pan'] for m in evidence)
        result.append({'code':'mobile_contact_clipped','status':'verified' if proven else 'potential','impact':35 if proven else 0,
            'evidence_strength':27 if proven else 8,'url':url,'target':urljoin(url,href) if href else url,'label':label,'signature':label,
            'observation':f'The “{label}” contact control’s label was clipped at both 375px and 390px; its center was outside the visible, non-pannable area.' if proven else f'The “{label}” contact label was partly clipped at two phone widths; usability needs review.',
            'evidence':json.dumps(evidence),'action':'Repair the responsive contact or inquiry-submit layout and recheck both phone widths.',
            'verification':'browser' if proven else 'browser_limited'})
    return result


def native_contact_findings(page, url, snapshots, clean):
    """Confirm only inert native anchors; never call, email, navigate or book."""
    if not clean or len(snapshots)!=2:
        return []
    first={c['id']:c for c in snapshots[0]['controls']}
    findings=[];candidates=[]
    for c in snapshots[1]['controls']:
        prior=first.get(c['id'],{})
        if not (c['visible'] and prior.get('visible') and c['tag']=='A' and (CONTACT.search(c['text']) or c['href'].lower().startswith(('tel:','mailto:')))):
            continue
        if any(not (0 <= item['top'] and item['bottom'] <= 844 and item['left'] < snap['width'] and item['right'] > 0) for item,snap in ((prior,snapshots[0]),(c,snapshots[1]))):
            continue
        if c['href'] != prior.get('href'):
            continue
        href=c['href'].strip()
        empty_scheme=bool(re.fullmatch(r'(?:tel|mailto):\s*(?:\?.*)?',href,re.I))
        inert_booking=bool(re.search(r'\b(book|schedule|appointment|quote|contact|estimate)\b',c['text'],re.I)) and href in ('','#')
        if not (empty_scheme or inert_booking) or has_activation_handlers(page,c['id']):
            continue
        candidates.append((c,href,empty_scheme))
    # Inspect all site handlers before Playwright's trial-click instrumentation is installed.
    for c,href,empty_scheme in candidates:
        control=page.locator(f'[data-fouse-research-id="{c["id"]}"]')
        try:
            control.click(trial=True,timeout=500)
            if (control.get_attribute('href',timeout=500) or '').strip()!=href:
                continue
        except Exception:
            continue
        code='empty_contact_link' if empty_scheme else 'inert_contact_control'
        destination='an empty '+href.split(':')[0]+' destination' if empty_scheme else 'only the current page/top'
        findings.append({'code':code,'status':'verified','verification':'browser','impact':42,'evidence_strength':30,
            'url':url,'target':href,'label':c['text'],'signature':href+'|'+c['text'] if empty_scheme else c['text'],
            'observation':f'The visible “{c["text"]}” link has {destination} at both phone widths, with no inline or delegated activation handlers found.',
            'evidence':json.dumps({'widths':[s['width'] for s in snapshots],'href':href,'activation_handlers':False,'trial_actionable':True,'activated':False}),
            'action':'Connect the control to the correct public contact or inquiry destination and test its mobile presentation.'})
    return findings
