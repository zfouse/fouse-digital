"""Read-only Chromium verification, isolated and bounded. No submission or booking."""
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit, urljoin

if __package__:
    from .fit import link_kind
    from .findings import canonical_url, merge_findings
else:
    from fit import link_kind
    from findings import canonical_url, merge_findings

CONTACT = re.compile(r'\b(contact|quote|estimate|call|request|consultation|book|schedule|appointment)\b',re.I)
UNSAFE = re.compile(r'(?:cancel|delete|remove|logout|unsubscribe|confirm|checkout|submit|send|payment|purchase|reserve|complete)',re.I)


def safe_document(url):
    p=urlsplit(url)
    return p.scheme in ('http','https') and not p.query and not UNSAFE.search(p.path)


class Guard:
    def __init__(self, checker, homepage, permission):
        self.checker=checker;self.permission=permission
        self.documents={canonical_url(homepage)}
        self.interacting=False;self.click_navigation_target=None;self.blocked=0;self.dynamic_blocked=0;self.essential_failed=0;self.requests=0
        self.checked=set()

    def route(self, route):
        req=route.request
        self.requests+=1
        resource=req.resource_type
        parsed=urlsplit(req.url)
        reject=(bool(UNSAFE.search(parsed.path)) or '/api/' in parsed.path.lower() or bool(re.search(r'(?:email|phone|date|slot|reserve|confirm|submit|send|book)=',parsed.query,re.I)) or (self.interacting and not (resource=='document' and canonical_url(req.url)==self.click_navigation_target)) or self.requests>120 or req.method not in ('GET','HEAD') or
                resource in ('xhr','fetch','eventsource','websocket','beacon','ping','cspreport','other'))
        if reject:
            self.blocked+=1
            if resource in ('xhr','fetch'): self.dynamic_blocked+=1
            route.abort();return
        try:
            self.checker(req.url)
            if resource=='document':
                if canonical_url(req.url) not in self.documents or not self.permission(req.url):
                    raise ValueError('Navigation not permitted')
            route.continue_()
        except (ValueError,OSError):
            self.blocked+=1;route.abort()


def inspect(url, source_findings, checker=None, permission=None):
    from playwright.sync_api import sync_playwright, Error
    if checker is None:
        if __package__:
            from .run import safe_url, fetch, AGENT
        else:
            from run import safe_url, fetch, AGENT
        import urllib.robotparser
        import urllib.error
        checker=safe_url
        robots={}
        def permission(target):
            p=urlsplit(target);origin=f'{p.scheme}://{p.netloc}'
            if origin not in robots:
                try: _,_,text=fetch(origin+'/robots.txt',timeout=5)
                except urllib.error.HTTPError as e:
                    if e.code!=404: return False
                    text=''
                parser=urllib.robotparser.RobotFileParser();parser.parse(text.splitlines());robots[origin]=parser
            return robots[origin].can_fetch(AGENT,target)
    permission=permission or (lambda target:False)
    checker(url)
    if not permission(url): raise ValueError('Robots disallows browser verification')
    deadline=time.monotonic()+60
    def remaining(maximum=12000):
        return max(1,min(maximum,int((deadline-time.monotonic())*1000)))
    guard=Guard(checker,url,permission)
    findings=[dict(f,status='potential',impact=0,evidence_strength=8,verification='awaiting_browser') if f.get('status')=='verified' else dict(f) for f in source_findings]
    coverage={'status':'complete','browser_checked':True,'viewports':[],'controls':[],'booking_checks':[],'dismissed':[],
              'limitations':['No forms filled/submitted or bookings made.','Dynamic data requests and popup-triggered network requests blocked.','Booking availability and form delivery remain untested.']}
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        context=browser.new_context(viewport={'width':1280,'height':900},service_workers='block',accept_downloads=False)
        context.route('**/*',guard.route)
        context.route_web_socket('**/*',lambda ws:ws.close())
        context.add_init_script("""document.addEventListener('submit', e=>{e.preventDefault();e.stopImmediatePropagation()},true);
        HTMLFormElement.prototype.submit=function(){throw new Error('Research: submission blocked')};
        HTMLFormElement.prototype.requestSubmit=function(){throw new Error('Research: submission blocked')};
        navigator.sendBeacon=()=>false;window.open=()=>null;""")
        page=context.new_page()
        context.on('page',lambda popup:popup.close() if popup.opener() else None)
        context.on('requestfailed',lambda req:setattr(guard,'essential_failed',guard.essential_failed+int(req.resource_type in ('script','stylesheet'))))
        try:
            response=page.goto(url,wait_until='domcontentloaded',timeout=remaining())
            if not response or response.status>=400 or re.search(r'just a moment|access denied|verify you are human',page.title(),re.I):
                raise ValueError('Browser reached error/challenge page')
            page.wait_for_timeout(min(400,remaining(400)))
            # Only controls outside forms; trial clicks test actionability without navigation.
            controls=page.locator('a,button').all()[:250]
            visible=[]
            for control in controls:
                if time.monotonic()>=deadline: break
                try:
                    data=control.evaluate("""el=>({text:(el.getAttribute('aria-label')||el.innerText||'').trim().slice(0,100),href:el.getAttribute('href')||'',tag:el.tagName,type:el.getAttribute('type')||'',form:!!el.closest('form')||!!el.getAttribute('form'),hidden:!!el.closest('[hidden],[inert],[aria-hidden="true"]'),id:el.id})""")
                    if data['hidden'] or data['form'] or not CONTACT.search(data['text']) or not control.is_visible(): continue
                    if link_kind(data['href'],data['text'])=='social': continue
                    if data['tag']=='BUTTON' and data['type'].lower()!='button': continue
                    try:
                        control.click(trial=True,timeout=remaining(700))
                        data['actionable']=True
                    except Error:
                        data['actionable']=False
                    data['link_kind']=link_kind(urljoin(url,data['href']),data['text'])
                    if data['link_kind']=='booking':
                        coverage['booking_checks'].append({'text':data['text'],'url':urljoin(url,data['href']),'actionable':data['actionable'],'completion_tested':False})
                    visible.append((control,data))
                    coverage['controls'].append({k:v for k,v in data.items() if k!='form'})
                except Error: continue
                if len(visible)>=10: break
            # Verify source dead-link evidence through browser navigation in a separate controlled page.
            for f in findings:
                if f['code']!='broken_cta' or time.monotonic()>=deadline: continue
                target=f.get('target','')
                match=next((d for _,d in visible if d['actionable'] and canonical_url(urljoin(url,d['href']))==canonical_url(target)),None)
                if not match or not safe_document(target): continue
                guard.documents.add(canonical_url(target))
                # Reopen the source page and perform the real contact-link click, not a direct
                # destination GET that could misclassify a working client-side router/popup.
                check=None
                try:
                    check=context.new_page()
                    check.goto(url,wait_until='domcontentloaded',timeout=remaining())
                    check.wait_for_timeout(min(300,remaining(300)))
                    anchors=check.locator('a').all()[:250]
                    clicked=next((a for a in anchors if canonical_url(urljoin(url,a.get_attribute('href') or ''))==canonical_url(target) and a.is_visible()),None)
                    if clicked is None: continue
                    before=check.locator('[role=dialog]:visible,dialog:visible,form:visible').count()
                    guard.interacting=True;guard.click_navigation_target=canonical_url(target)
                    try:
                        with check.expect_navigation(wait_until='domcontentloaded',timeout=remaining(2000)) as navigation:
                            clicked.click(timeout=remaining(1000))
                        r=navigation.value
                        status=r.status if r else None
                    except Error:
                        status=None
                    after=check.locator('[role=dialog]:visible,dialog:visible,form:visible').count()
                    if status in (404,410) and not guard.essential_failed and not guard.dynamic_blocked:
                        f.update(status='verified',impact=50,evidence_strength=30,verification='browser',
                            observation=f'Clicking the visible “{match["text"]}” contact link led to HTTP {status} in Chromium after two matching source checks.',
                            evidence=f['evidence']+f'; actual browser click HTTP {status}; actionable visible link')
                    elif (status and status<400) or (status is None and after>before):
                        f['status']='dismissed';coverage['dismissed'].append(f)
                    coverage['controls'].append({'text':match['text'],'result':'contact_navigation_checked' if status else 'local_response_or_inconclusive','http_status':status})
                except Error:pass
                finally:
                    if check: check.close()
                    guard.interacting=False;guard.click_navigation_target=None
            # Render at two phone widths. Repeated overflow alone is potential unless a contact control is clipped.
            clipped={}
            for width in (375,390):
                if time.monotonic()>=deadline: break
                page.set_viewport_size({'width':width,'height':844});page.wait_for_timeout(min(200,remaining(200)))
                metrics=page.evaluate("""()=>({width:innerWidth,scroll:document.documentElement.scrollWidth,controls:[...document.querySelectorAll('a,button')].filter(el=>!el.closest('form,[hidden],[inert],[aria-hidden="true"]')).map(el=>{let r=el.getBoundingClientRect(),s=getComputedStyle(el);return {text:(el.getAttribute('aria-label')||el.innerText||'').trim().slice(0,100),href:el.getAttribute('href')||'',left:r.left,right:r.right,top:r.top,bottom:r.bottom,width:r.width,visible:s.display!=='none'&&s.visibility!=='hidden'&&s.opacity!=='0'}})})""")
                coverage['viewports'].append({'width':width,'scroll_width':metrics['scroll']})
                for c in metrics['controls']:
                    if c['visible'] and c['width']>0 and c['top']>=0 and c['top']<844 and c['left']>=0 and c['right']>width+16 and CONTACT.search(c['text']) and link_kind(c['href'],c['text'])!='social':
                        key=(c['text'],c['href']);clipped.setdefault(key,[]).append({'width':width,'right':round(c['right'],1)})
            for (label,target),measurements in clipped.items():
                if len(measurements)!=2: continue
                proven=not guard.dynamic_blocked and not guard.essential_failed
                findings.append({'code':'mobile_contact_clipped','status':'verified' if proven else 'potential','impact':35 if proven else 0,'evidence_strength':27 if proven else 8,
                    'url':url,'target':urljoin(url,target) if target else url,'label':label,'signature':label,
                    'observation':f'The “{label}” contact control extended beyond the viewport at both 375px and 390px in Chromium.',
                    'evidence':json.dumps(measurements),'action':'Adjust the contact control’s responsive layout and recheck both phone widths.','verification':'browser' if proven else 'browser_limited'})
            rendered_forms=page.locator('form:visible').evaluate_all("""forms=>forms.filter(f=>f.getAttribute('role')!=='search'&&!f.querySelector('input[type=search]')).map(f=>({labeled:[...f.querySelectorAll('input:not([type=hidden]):not([type=submit]):not([type=button]),select,textarea')].filter(e=>e.getBoundingClientRect().width>0).every(e=>(e.labels&&e.labels.length)||e.getAttribute('aria-label')||e.title||(e.getAttribute('aria-labelledby')||'').split(' ').some(id=>document.getElementById(id)?.textContent.trim())),submit:!!f.querySelector('button:not([type=button]):not([type=reset]),input[type=submit],input[type=image]')}))""")
            if rendered_forms and not guard.dynamic_blocked and not guard.essential_failed:
                for f in findings:
                    if canonical_url(f.get('url',''))!=canonical_url(url): continue
                    if (f['code']=='form_labels' and all(x['labeled'] for x in rendered_forms)) or (f['code']=='form_submit' and all(x['submit'] for x in rendered_forms)):
                        f['status']='dismissed';coverage['dismissed'].append(f)
            if len(coverage['viewports'])==2 and all(v['scroll_width']<=v['width']+2 for v in coverage['viewports']) and not guard.dynamic_blocked and not guard.essential_failed:
                for f in findings:
                    if f['code'] in ('viewport','mobile_width') and canonical_url(f.get('url',''))==canonical_url(url):
                        f['status']='dismissed';coverage['dismissed'].append(f)
            # Actual clicks are restricted to local UI openers, with *all* network blocked during the action.
            page.set_viewport_size({'width':1280,'height':900})
            for control,data in visible[:3]:
                if time.monotonic()>=deadline: break
                if not data['actionable'] or data['form'] or not (data['tag']=='BUTTON' or data['href'].startswith('#')): continue
                guard.interacting=True
                try:
                    before=page.locator('[role=dialog]:visible,dialog:visible,form:visible').count()
                    control.click(timeout=remaining(1000));page.wait_for_timeout(min(150,remaining(150)))
                    after=page.locator('[role=dialog]:visible,dialog:visible,form:visible').count()
                    coverage['controls'].append({'text':data['text'],'result':'local_dialog_opened' if after>before else 'no_conclusive_local_response','network_blocked':True})
                    if after>before:
                        for f in findings:
                            if f['code']=='cta_fragment' and data['href'] in f['evidence']:
                                f['status']='dismissed';coverage['dismissed'].append(f)
                except Error:
                    coverage['controls'].append({'text':data['text'],'result':'inconclusive','network_blocked':True})
                finally:guard.interacting=True  # Keep the network locked until this context closes.
            coverage['blocked_requests']=guard.blocked
            coverage['dynamic_requests_blocked']=guard.dynamic_blocked
            coverage['essential_resources_failed']=guard.essential_failed
        finally:
            context.close();browser.close()
    return {'findings':merge_findings([f for f in findings if f['status']!='dismissed']), 'coverage':coverage}


def verify(result):
    with tempfile.TemporaryDirectory() as root:
        inp=Path(root)/'input.json';out=Path(root)/'output.json'
        inp.write_text(json.dumps({'url':result.final,'findings':result.findings}))
        try:
            child=subprocess.run([sys.executable,str(Path(__file__).resolve()),str(inp),str(out)],timeout=80,capture_output=True,text=True)
            payload=json.loads(out.read_text()) if out.exists() else {}
            if child.returncode or 'findings' not in payload:
                raise RuntimeError(payload.get('error','Browser worker failed'))
            result.findings=payload['findings'];result.coverage['browser']=payload['coverage'];result.coverage['browser_checked']=True
            result.coverage['limitations']=payload['coverage']['limitations']
        except (OSError,ValueError,RuntimeError,subprocess.SubprocessError) as e:
            result.findings=[dict(f,status='potential',impact=0,evidence_strength=8,verification='browser_unavailable') if f.get('status')=='verified' else f for f in result.findings]
            result.coverage['browser']={'status':'unavailable','reason':str(e)[:500]}
    return result


if __name__=='__main__':
    try:
        request=json.loads(Path(sys.argv[1]).read_text())
        payload=inspect(request['url'],request['findings'])
        Path(sys.argv[2]).write_text(json.dumps(payload))
    except Exception as e:
        Path(sys.argv[2]).write_text(json.dumps({'error':type(e).__name__+': '+str(e)[:500]}));sys.exit(1)
