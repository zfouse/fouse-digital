import copy
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import re
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from prospecting.fit import business_fit,link_kind
from prospecting.findings import merge_findings,root_key,same_business
from prospecting.browser_verify import inspect,verify,Guard
from prospecting.conversion import analyze,AuditResult
from prospecting.quality import draft,rank
from prospecting.run import run


def business(name='Local Fixture',site='https://fixture.example',id=1):
    return {'provider':'overture','id':id,'type':'place','lat':38.6,'lon':-90.2,
            'tags':{'name':name,'craft':'plumber','website':site,'phone':'3145550100'}}


def defect(url='https://fixture.example/',target='https://fixture.example/contact'):
    return {'code':'broken_cta','status':'verified','verification':'source','impact':50,'evidence_strength':30,
            'url':url,'target':target,'label':'Request quote','observation':'Quote destination returned 404 twice.',
            'evidence':'GET 404,404','action':'Repair the quote link.'}


class FitAndFindingTests(unittest.TestCase):
    def test_oct15_facebook_is_not_a_booking_link(self):
        for url,text in [('https://www.facebook.com/FergusonOfficial','Facebook'),('http://Facebook.com/ARSBuild','Facebook'),('https://www.facebook.com/AAAHomeHVACElectricPlumbing/','Book an appointment')]:
            self.assertEqual(link_kind(url,text),'social')
        self.assertEqual(link_kind('https://calendly.com/local-fixture','Schedule'),'booking')
        self.assertEqual(link_kind('/contact','Book an appointment'),'booking')
        def get(url): return url,'text/html','<a href="https://facebook.com/fixture">Facebook</a>'
        result=analyze('https://fixture.example/',get,'Test')
        self.assertFalse(any(f['code']=='external_booking_review' for f in result.findings))
        self.assertFalse(result.coverage['pages'][0]['booking_links'])

    def test_social_lookalike_domain_is_not_trusted(self):
        self.assertNotEqual(link_kind('https://facebook.com.evil.example/a','Facebook'),'social')
        self.assertNotEqual(link_kind('https://notcalendly.com/a','Read more'),'booking')

    def test_large_distributor_and_national_chains_excluded_before_audits(self):
        for site in ('https://www.ferguson.com/store/mo/st+louis/plumbingpvf-0564','https://rotorooter.com/stlouis','https://goodmanmfg.com','https://temperaturepro.com/'):
            self.assertFalse(business_fit(business(site=site))['eligible'])
        calls=[]
        report,_=run([business(site='https://ferguson.com')],{},auditor=lambda u:calls.append(u))
        self.assertFalse(calls)
        self.assertEqual(len(report['excluded_businesses']),1)

    def test_unknown_ownership_not_invented_and_local_statement_raises_fit(self):
        unknown=business_fit(business())
        local=business_fit(business(),'Family-owned and locally operated since 1980.')
        affiliated=business();affiliated['provenance']={'brand':{'names':{'primary':'A brand'}}}
        self.assertEqual(unknown['ownership'],'unknown')
        self.assertGreater(local['score'],unknown['score'])
        self.assertLess(business_fit(affiliated)['score'],unknown['score'])
        self.assertIn('not been independently verified',' '.join(local['reasons']))

    def test_repeated_pages_aliases_merge_sources_not_evidence_loss(self):
        a={'code':'viewport','url':'http://www.fixture.example/','evidence':'home','status':'potential'}
        b=dict(a,url='https://fixture.example/contact/',evidence='contact')
        c={'code':'viewport','url':'https://other.example/','evidence':'other','status':'potential'}
        merged=merge_findings([a,b,c])
        self.assertEqual(len(merged),2)
        self.assertEqual(len(merged[0]['sources']),2)
        self.assertEqual(len(merged[0]['evidence_records']),2)

    def test_repeat_forms_merge_but_distinct_forms_and_domains_do_not(self):
        a={'code':'form_labels','url':'https://fixture.example/','evidence':'fields=email','signature':'contact/email','status':'potential'}
        b=dict(a,url='https://fixture.example/about')
        c=dict(a,signature='newsletter/email')
        d=dict(a,url='https://other.example/')
        self.assertEqual(len(merge_findings([a,b,c,d])),3)
        # Empty tel URIs must never merge unrelated sites globally.
        tel={'code':'empty_contact_link','url':'https://fixture.example/','target':'tel:','label':'Call','evidence':'tel:'}
        self.assertNotEqual(root_key(tel),root_key(dict(tel,url='https://other.example/')))

    def test_shared_phone_and_parent_site_do_not_erase_different_identities(self):
        a={'provider':'overture','id':1,'name':'Averill Heating','website':'https://parent.example/about/averill','contact_keys':['shared-phone']}
        b=dict(a,id=2,name='Weis Comfort',website='https://parent.example/about/weis')
        self.assertFalse(same_business(a,b))
        self.assertTrue(same_business(a,dict(a,provider='osm',id=3,name='Averill Heating LLC')))

    def test_shared_root_failure_one_draft_retains_related_business(self):
        a=business('Averill','https://parent.example/about/averill',1)
        b=business('Weis','https://parent.example/about/weis',2)
        def audit(url):
            f=dict(defect(url,'https://parent.example/contact'),verification='browser')
            return url,[f],[]
        report,state=run([a,b],{},auditor=audit)
        self.assertEqual(len(report['new_leads']),1)
        self.assertEqual(len(report['new_leads'][0]['related_businesses']),1)
        self.assertEqual({report['new_leads'][0]['name'],report['new_leads'][0]['related_businesses'][0]['name']},{'Averill','Weis'})
        self.assertEqual(len(state['finding_seen']),1)

    def test_different_failures_and_identities_on_parent_domain_survive(self):
        a=business('Averill','https://parent.example/about/averill',1)
        b=business('Weis','https://parent.example/about/weis',2)
        report,_=run([a,b],{},auditor=lambda url:(url,[dict(defect(url,url+'/quote'),verification='browser')],[]))
        self.assertEqual(len(report['new_leads']),2)

    def test_source_status_alone_cannot_create_outreach(self):
        self.assertIsNone(draft('Fixture',defect()))
        report,_=run([business()],{},auditor=lambda u:(u,[defect()],[]))
        self.assertFalse(report['new_leads'])
        self.assertEqual(report['shortfall'],10)

    def test_browser_failure_downgrades_without_changing_evidence_to_fact(self):
        result=AuditResult('https://fixture.example',[defect()],[],{})
        with patch('prospecting.browser_verify.subprocess.run',side_effect=TimeoutError()):
            result=verify(result)
        self.assertEqual(result.findings[0]['status'],'potential')
        self.assertEqual(result.coverage['browser']['status'],'unavailable')
        self.assertIsNone(draft('Fixture',result.findings[0]))

    def test_network_guard_blocks_submission_booking_and_dynamic_requests(self):
        for method,kind,url in [('POST','document','https://fixture.example/'),('GET','fetch','https://fixture.example/'),('GET','image','https://fixture.example/api/book'),('GET','document','https://fixture.example/submit')]:
            route=SimpleNamespace(request=SimpleNamespace(method=method,resource_type=kind,url=url),abort=lambda:events.append('blocked'),continue_=lambda:events.append('allowed'))
            events=[];Guard(lambda u:u,'https://fixture.example/',lambda u:True).route(route)
            self.assertEqual(events,['blocked'])


class ReadOnlyBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise unittest.SkipTest('Install requirements and Chromium')
        cls.calls=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*a):pass
            def do_POST(self):
                cls.calls.append(('POST',self.path));self.send_response(200);self.end_headers()
            def do_GET(self):
                cls.calls.append(('GET',self.path))
                if self.path in ('/missing','/missing.css'):
                    self.send_response(404);self.end_headers();return
                if self.path.startswith('/mobile'):
                    body='<meta name="viewport" content="width=device-width"><a style="display:block;width:650px" href="/contact">Request quote</a>'
                    if self.path in ('/mobile-clipped','/mobile-limited','/mobile-css-missing','/mobile-analytics'):
                        body='<meta name="viewport" content="width=device-width"><style>body{overflow:hidden}a{display:block;margin-left:300px;width:200px;text-align:center}</style><a href="/contact">Request quote</a>'
                    if self.path=='/mobile-offcanvas':body='<style>body{overflow:hidden}a{display:block;margin-left:500px;width:200px}</style><a href=/contact>Request quote</a>'
                    if self.path=='/mobile-css-missing':body+='<link rel=stylesheet href=/missing.css>'
                    if self.path=='/mobile-analytics':body+='<script src=https://www.google-analytics.com/analytics.js></script>'
                    if self.path=='/mobile-limited': body+="<script>fetch('/data-needed-for-widget')</script>"
                elif self.path.startswith('/native'):
                    body='<meta name="viewport" content="width=device-width"><a href="tel:">Call now</a>'
                    if self.path=='/native-hover':body+="<script>document.querySelector('a').addEventListener('mouseenter',e=>e.target.href='tel:3145550100')</script>"
                    if self.path=='/native-delegated':body+="<script>document.addEventListener('click',e=>{e.preventDefault()})</script>"
                elif self.path=='/inert-booking':
                    body='<meta name="viewport" content="width=device-width"><a href="#">Book appointment</a>'
                elif self.path=='/inquiry-clipped':
                    body='<meta name="viewport" content="width=device-width"><style>body{overflow:hidden}button{margin-left:300px;width:220px}</style><form action="/book" method=post><input name=email aria-label=Email><textarea name=message aria-label=Message></textarea><button>Send inquiry</button></form>'
                elif self.path=='/router':
                    body='''<meta name="viewport" content="width=device-width"><a id="client-contact" href="/missing">Request quote</a><script>document.addEventListener('click',e=>{if(e.target.id==='client-contact'){e.preventDefault();let d=document.createElement('div');d.setAttribute('role','dialog');d.innerHTML='<form><input aria-label=Email><button>Send</button></form>';document.body.append(d)}})</script>'''
                else:
                    body='''<meta name="viewport" content="width=device-width"><a href="/missing">Request quote</a>
                    <a href="#modal" onclick="event.preventDefault();let d=document.createElement('div');d.setAttribute('role','dialog');d.innerHTML='<form action=/book method=post><input name=email><button>Submit appointment</button></form>';document.body.append(d);fetch('/api/book',{method:'POST'});">Contact us</a>
                    <form action="/book" method="post"><input name="email"><button>Book appointment</button></form>
                    <a href="https://facebook.com/fixture">Facebook</a>'''
                self.send_response(200);self.send_header('Content-Type','text/html');self.end_headers();self.wfile.write(body.encode())
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.base=f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join()

    def test_visible_dead_link_and_popup_verified_without_form_submission(self):
        url=self.base+'/'
        f=defect(url,self.base+'/missing')
        potential={'code':'cta_fragment','status':'potential','url':url,'evidence':"href='#modal'",'observation':'Fragment requires browser inspection'}
        result=inspect(url,[f,potential],checker=lambda u:u,permission=lambda u:True)
        self.assertTrue(any(f['verification']=='browser' and f['status']=='verified' for f in result['findings']))
        self.assertTrue(any(c.get('result')=='local_dialog_opened' for c in result['coverage']['controls']))
        self.assertFalse(any(f['code']=='cta_fragment' for f in result['findings']))
        self.assertFalse(any(method=='POST' or path.startswith(('/book','/api/')) for method,path in self.calls))
        self.assertEqual(len(result['coverage']['viewports']),2)

    def test_repeated_mobile_contact_clipping_uses_actual_layout(self):
        result=inspect(self.base+'/mobile-clipped',[],checker=lambda u:u,permission=lambda u:True)
        issues=[f for f in result['findings'] if f['code']=='mobile_contact_clipped']
        self.assertEqual(len(issues),1)
        self.assertEqual(issues[0]['status'],'verified')
        self.assertEqual(issues[0]['verification'],'browser')
    def test_working_client_side_popup_dismisses_source_404(self):
        url=self.base+'/router'
        result=inspect(url,[defect(url,self.base+'/missing')],checker=lambda u:u,permission=lambda u:True)
        self.assertFalse(any(f['code']=='broken_cta' for f in result['findings']))
        self.assertTrue(result['coverage']['dismissed'])

    def test_blocked_widget_data_keeps_mobile_observation_potential(self):
        result=inspect(self.base+'/mobile-limited',[],checker=lambda u:u,permission=lambda u:True)
        issues=[f for f in result['findings'] if f['code']=='mobile_contact_clipped']
        self.assertTrue(issues)
        self.assertTrue(all(f['status']=='potential' for f in issues))
        self.assertGreater(result['coverage']['dynamic_requests_blocked'],0)


class RegressionIntegrationTests(unittest.TestCase):
    def test_related_identity_is_retained_when_root_issue_previously_reviewed(self):
        c=business('New related operator','https://parent.example/about/related',2)
        f=dict(defect(c['tags']['website'],'https://parent.example/contact'),verification='browser')
        state={'seen':['historic-key'],'daily':{'2000-01-01':2},'finding_seen':[root_key(f)]}
        report,state=run([c],state,auditor=lambda u:(u,[f],[]))
        self.assertEqual(report['new_leads'],[])
        self.assertEqual(report['related_identities'][0]['entity']['name'],'New related operator')
        self.assertIn('historic-key',state['seen'])
        self.assertEqual(len(state['related_entities']),1)

    def test_potential_findings_shared_by_related_businesses_get_one_review_card(self):
        a=business('Averill','https://parent.example/about/averill',1)
        b=business('Weis','https://parent.example/about/weis',2)
        def inspect_source(url): return url,[{'code':'viewport','status':'potential','url':url,'evidence':'missing','observation':'Mobile viewport needs review'}],[]
        report,_=run([a,b],{},auditor=inspect_source)
        self.assertEqual(len(report['review_queue']),1)
        self.assertEqual(len(report['review_queue'][0]['related_businesses']),1)
        self.assertEqual(len(report['review_queue'][0]['findings'][0]['sources']),2)

    def test_known_chain_removed_from_new_discovery_records(self):
        from prospecting.overture import normalize
        row={'id':'test','names':{'primary':'Ferguson Plumbing Supply'},'websites':['https://ferguson.com'],'bbox':{'xmin':-90.2,'ymin':38.6},'confidence':.95,'taxonomy':{'primary':'plumbing'}}
        self.assertIsNone(normalize(row,'release'))

    def test_browser_confirmation_supersedes_source_duplicate(self):
        source=defect();browser=dict(source,verification='browser',evidence='Chromium HTTP 404')
        merged=merge_findings([source,browser])
        self.assertEqual(len(merged),1)
        self.assertEqual(merged[0]['verification'],'browser')
        self.assertEqual(len(merged[0]['evidence_records']),2)


class ConversionVerificationRegressionTests(unittest.TestCase):
    setUpClass = classmethod(ReadOnlyBrowserTests.setUpClass.__func__)
    tearDownClass = classmethod(ReadOnlyBrowserTests.tearDownClass.__func__)
    def test_wide_box_with_fully_visible_contact_label_is_harmless(self):
        result=inspect(self.base+'/mobile',[],checker=lambda u:u,permission=lambda u:True)
        self.assertFalse(any(f['code']=='mobile_contact_clipped' for f in result['findings']))

    def test_empty_native_phone_is_verified_without_dialing(self):
        source={'code':'empty_contact_link','status':'verified','verification':'source','impact':42,'url':self.base+'/native','target':'tel:','label':'Call now','evidence':'source empty tel'}
        result=inspect(self.base+'/native',[source],checker=lambda u:u,permission=lambda u:True)
        confirmed=[f for f in result['findings'] if f['code']=='empty_contact_link' and f['status']=='verified']
        self.assertEqual(len(confirmed),1)
        self.assertEqual(len(result['findings']),1)
        self.assertIn('"activated": false',confirmed[0]['evidence'])
        self.assertIsNotNone(draft('Fixture',confirmed[0]))

    def test_delegated_click_handler_keeps_empty_phone_unverified(self):
        for path in ('/native-delegated','/native-hover'):
            with self.subTest(path=path):
                result=inspect(self.base+path,[],checker=lambda u:u,permission=lambda u:True)
                self.assertFalse(any(f['status']=='verified' for f in result['findings']))

    def test_hash_booking_stays_potential_without_navigation_or_booking(self):
        before=len(self.calls)
        result=inspect(self.base+'/inert-booking',[],checker=lambda u:u,permission=lambda u:True)
        self.assertTrue(any(f['code']=='inert_contact_control' and f['status']=='potential' for f in result['findings']))
        self.assertTrue(result['coverage']['booking_checks'])
        self.assertFalse(any(draft('Fixture',f) for f in result['findings']))
        self.assertFalse(any(method=='POST' or path.startswith('/book') for method,path in self.calls[before:]))

    def test_inquiry_submit_clipping_without_submission(self):
        before=len(self.calls)
        result=inspect(self.base+'/inquiry-clipped',[],checker=lambda u:u,permission=lambda u:True)
        self.assertTrue(any(f['code']=='mobile_contact_clipped' and f['label']=='Send inquiry' and f['status']=='verified' for f in result['findings']))
        self.assertTrue(result['coverage']['form_checks'][0]['forms'][0]['inquiry'])
        self.assertFalse(any(method=='POST' or path.startswith('/book') for method,path in self.calls[before:]))


    def test_closed_offcanvas_control_is_not_a_mobile_defect(self):
        result=inspect(self.base+'/mobile-offcanvas',[],checker=lambda u:u,permission=lambda u:True)
        self.assertFalse(any(f['status']=='verified' for f in result['findings']))

    def test_failed_stylesheet_keeps_clipping_unverified(self):
        result=inspect(self.base+'/mobile-css-missing',[],checker=lambda u:u,permission=lambda u:True)
        self.assertEqual(result['coverage']['status'],'limited')
        self.assertFalse(any(f['status']=='verified' for f in result['findings']))

    def test_optional_analytics_does_not_invent_a_functional_render_failure(self):
        result=inspect(self.base+'/mobile-analytics',[],checker=lambda u:u,permission=lambda u:True)
        self.assertGreater(result['coverage']['optional_requests_blocked'],0)
        self.assertEqual(result['coverage']['essential_resources_failed'],0)
        self.assertTrue(any(f['status']=='verified' for f in result['findings']))


class PublicBusinessPageTests(unittest.TestCase):
    def test_identity_redirect_is_not_a_complete_business_audit(self):
        def getter(url):
            if url.endswith('/robots.txt'):return url,'text/plain','User-agent: *\nAllow: /'
            return 'https://accounts.google.com/v3/signin/identifier','text/html','<form><input name=email><input type=password></form>'
        with self.assertRaisesRegex(ValueError,'identity-provider'):
            analyze('https://sites.google.com/view/fixture',getter,'Test')
        self.assertFalse(business_fit(business(site='https://accounts.google.com/v3/signin/identifier'))['eligible'])
        self.assertTrue(business_fit(business(site='https://sites.google.com/view/public-fixture'))['eligible'])
