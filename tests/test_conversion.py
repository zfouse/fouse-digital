import copy
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

from prospecting.contacts import canonical, deduplicate
from prospecting.conversion import analyze
from prospecting.dashboard import render
from prospecting.history import snapshot
from prospecting.quality import draft, rank
from prospecting.run import keys, run, main

HOME = 'https://fixture.example/'


def getter_for(home, destinations=None):
    destinations = destinations or {}
    def get(url):
        if url.endswith('/robots.txt'):
            return url, 'text/plain', 'User-agent: *\nAllow: /'
        if url in destinations:
            response = destinations[url]
            if isinstance(response, int):
                raise urllib.error.HTTPError(url, response, 'Fixture', {}, None)
            return url, 'text/html', response
        return url, 'text/html', home
    return get


def candidate(i, email=None):
    return {'id': i, 'type': 'node', 'lat': 38.6, 'lon': -90.2,
            'tags': {'name': f'Fixture {i}', 'craft': 'plumber', 'website': f'https://example{i}.test', 'email': email or f'office{i}@example.test'}}


def confirmed(url, impact=50):
    return {'code': 'broken_cta', 'status': 'verified', 'verification': 'browser', 'impact': impact, 'evidence_strength': 30,
            'url': url, 'observation': 'The “Request a quote” link returned HTTP 404 on two checks.',
            'label': 'Request a quote', 'target': url+'/quote', 'evidence': 'Two 404 responses'}


class ConversionTests(unittest.TestCase):
    def test_broken_quote_and_booking_links_need_two_confirmations(self):
        for label in ('Request a quote', 'Book an appointment', 'Contact us'):
            with self.subTest(label=label):
                getter = getter_for(f'<a href="/contact">{label}</a>', {HOME+'contact': 404})
                result = analyze(HOME, getter, 'Test')
                issues = [f for f in result.findings if f['status'] == 'verified']
                self.assertEqual(len(issues), 1)
                self.assertEqual(issues[0]['code'], 'broken_cta')
                self.assertIsNone(draft('Fixture Plumbing', issues[0]))
                self.assertIn(label, draft('Fixture Plumbing', dict(issues[0],verification='browser'))['body'])

    def test_flaky_or_blocked_links_are_never_verified(self):
        for status in (403, 429, 500, 502, 503, 504):
            result = analyze(HOME, getter_for('<a href="/quote">Get quote</a>', {HOME+'quote': status}), 'Test')
            self.assertFalse(any(f['status'] == 'verified' for f in result.findings))
        hits = []
        def get(url):
            if url.endswith('robots.txt'):
                return url, 'text/plain', ''
            if url.endswith('/quote'):
                hits.append(url)
                if len(hits) == 1:
                    raise urllib.error.HTTPError(url,404,'',{},None)
            return url, 'text/html', '<a href="/quote">Get quote</a>'
        self.assertFalse(any(f['status']=='verified' for f in analyze(HOME,get,'Test').findings))

    def test_forms_and_mobile_checks_are_potential_not_delivery_claims(self):
        markup = '<style>.form{min-width:800px}</style><form action="http://fixture.example/send"><input name="email"><textarea name="message"></textarea></form><a href="#quote">Get quote</a>'
        result = analyze(HOME, getter_for(markup), 'Test')
        codes = {f['code'] for f in result.findings}
        self.assertTrue({'form_labels','form_submit','form_insecure_action','mobile_width','viewport','cta_fragment'} <= codes)
        self.assertTrue(all(f['status']=='potential' for f in result.findings))
        self.assertTrue(all(draft('Fixture',f) is None for f in result.findings))

    def test_working_contact_form_and_responsive_source_no_problem_invented(self):
        markup = '<meta name="viewport" content="width=device-width"><form><label for="email">Email</label><input id="email" name="email"><button>Request quote</button></form>'
        self.assertEqual(analyze(HOME,getter_for(markup),'Test').findings, [])

    def test_search_forms_do_not_become_inquiry_problems(self):
        result=analyze(HOME,getter_for('<meta name="viewport" content="width=device-width"><form role="search"><input type="search"></form>'),'Test')
        self.assertFalse(any(f['code'].startswith('form_') for f in result.findings))

    def test_empty_phone_link_verified_but_foreign_number_not_false_positive(self):
        result=analyze(HOME,getter_for('<a href="tel:">Call now</a><a href="tel:+442079460000">London</a>'),'Test')
        issues=[f for f in result.findings if f['status']=='verified']
        self.assertEqual(len(issues),1)
        self.assertEqual(issues[0]['code'],'empty_contact_link')
        self.assertEqual(issues[0]['evidence_strength'],24)

    def test_external_booking_and_javascript_ctas_are_never_clicked(self):
        urls=[]
        base=getter_for('<a href="https://booking.example/schedule">Book appointment</a><a href="/delete/appointment">Cancel appointment</a><a href="/quote?confirm=1">Quote</a><a href="#modal">Get quote</a>')
        def get(url): urls.append(url); return base(url)
        result=analyze(HOME,get,'Test')
        self.assertEqual(set(urls),{HOME,HOME+'robots.txt'})
        self.assertIn('external_booking_review',{f['code'] for f in result.findings})
        self.assertFalse(any(f['status']=='verified' for f in result.findings))

    def test_challenge_pages_and_robots_denial_not_outreach_evidence(self):
        with self.assertRaises(ValueError):
            analyze(HOME,getter_for('<title>Just a moment...</title>'),'Test')
        def deny(url): return url,'text/plain','User-agent: *\nDisallow: /'
        with self.assertRaises(ValueError): analyze(HOME,deny,'Test')

    def test_contact_normalization_merges_sources_without_guessing(self):
        contacts=deduplicate([{'kind':'email','value':' Office@Example.COM ','source':'a'}, {'kind':'email','value':'office@example.com','source':'b'}, {'kind':'phone','value':'+1 (314) 555-0100 ext. 4','source':'c'}, {'kind':'phone','value':'314-555-0100','source':'d'}, {'kind':'email','value':'unknown','source':'a'}])
        self.assertEqual(len(contacts),2)
        self.assertEqual(contacts[0]['sources'],['a','b'])
        self.assertEqual(contacts[1]['sources'],['c','d'])
        self.assertIsNone(canonical('email','a@example.com\nBcc:x'))

    def test_email_dedup_across_providers_and_against_new_ledger_hash(self):
        contacts=[{'kind':'email','value':'OFFICE@example.com'}]
        a=candidate(1,'office@example.com')
        b=dict(candidate(2,' Office@Example.com '),provider='overture',type='place')
        b['tags']['name']=a['tags']['name']
        def auditor(url): return url,[confirmed(url)],[]
        report,state=run([a,b],{},auditor=auditor)
        self.assertEqual(len(report['new_leads']),1)
        expected=hashlib.sha256(b'email:office@example.com').hexdigest()
        self.assertIn(expected,state['seen'])
        self.assertTrue(set(keys(a)).intersection(keys(b)))

    def test_technical_only_and_potential_findings_cannot_fill_quota(self):
        potential={'code':'viewport','status':'potential','impact':0,'url':HOME,'observation':'Missing viewport','evidence':'source'}
        report,state=run([candidate(1)],{},auditor=lambda url:(url,[potential],[]))
        self.assertEqual(report['new_leads'],[])
        self.assertEqual(len(report['review_queue']),1)
        self.assertEqual(state['seen'],[])
        self.assertEqual(report['shortfall'],10)

    def test_ranking_selects_best_after_audit_not_first_ten(self):
        rows=[candidate(i) for i in range(15)]
        def auditor(url):
            score=50 if url=='https://example14.test' else 20
            return url,[confirmed(url,score)],[]
        old={'seen':['historical-hash'],'daily':{'2020-01-01':2}}
        report,state=run(rows,copy.deepcopy(old),auditor=auditor)
        self.assertEqual(report['new_leads'][0]['name'],'Fixture 14')
        self.assertEqual(report['audited_sites'],15)
        self.assertEqual(len(report['new_leads']),10)
        self.assertIn('historical-hash',state['seen'])
        self.assertEqual(state['daily']['2020-01-01'],2)
        self.assertNotIn('_keys',report['new_leads'][0])

    def test_dashboard_orders_scores_and_escapes_content_and_bad_urls(self):
        report,_=run([candidate(1),candidate(2)],{},auditor=lambda url:(url,[confirmed(url,50 if '2.' in url else 20)],[]))
        report['new_leads'].reverse()
        result=render(report)
        self.assertLess(result.index('<h2>Fixture 2'),result.index('<h2>Fixture 1'))
        report['new_leads'][0]['name']='</textarea><img onerror=alert(1)>'
        report['new_leads'][0]['website']='javascript:alert(1)'
        result=render(report)
        self.assertNotIn('<img onerror',result)
        self.assertNotIn('href="javascript:',result)
        self.assertIn('Copy message',result)
        self.assertIn('Verified',result)

    def test_history_snapshots_preserve_old_bytes_and_append(self):
        with tempfile.TemporaryDirectory() as root:
            output=Path(root)/'reports'; output.mkdir()
            state=Path(root)/'state'
            (output/'review.json').write_text('old report')
            first=snapshot(output,state)
            (output/'review.json').write_text('new report')
            second=snapshot(output,state)
            self.assertNotEqual(first,second)
            self.assertEqual((state/'history'/f'{first}.json').read_text(),'old report')
            self.assertEqual((state/'history'/f'{second}.json').read_text(),'new report')

    def test_main_preserves_previous_latest_report_and_existing_history(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root); output=root/'reports'; output.mkdir()
            state=root/'state'; state.mkdir()
            (state/'ledger.json').write_text('{"seen":["keep-me"],"daily":{"2000-01-01":3}}')
            (state/'history').mkdir(); (state/'history'/'older.json').write_text('unchanged history')
            (output/'review.json').write_text('previous json bytes')
            (output/'review.html').write_text('previous html bytes')
            with patch('sys.argv',['run','--state',str(state/'ledger.json'),'--output',str(output)]), patch('prospecting.run.discover_businesses',return_value=([],{'status':'success'},None)):
                self.assertEqual(main(),0)
            self.assertTrue(any(p.read_text()=='previous json bytes' for p in (output/'history').glob('*.json')))
            self.assertTrue(any(p.read_text()=='previous html bytes' for p in (output/'history').glob('*.html')))
            self.assertEqual((state/'history'/'older.json').read_text(),'unchanged history')
            self.assertEqual(len(list((state/'history').glob('*.json'))),2)
            ledger=json.loads((state/'ledger.json').read_text())
            self.assertIn('keep-me',ledger['seen'])
            self.assertEqual(ledger['daily']['2000-01-01'],3)

    def test_local_http_integration_never_posts_form_or_books_appointment(self):
        calls=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*a): pass
            def do_POST(self): calls.append(('POST',self.path)); self.send_response(500); self.end_headers()
            def do_GET(self):
                calls.append(('GET',self.path))
                code=404 if self.path=='/quote' else 200
                body='User-agent: *\nAllow: /' if self.path=='/robots.txt' else '<a href="/quote">Get quote</a><form action="/send" method="post"><input name="email"><button>Send</button></form>'
                self.send_response(code); self.send_header('Content-Type','text/html'); self.end_headers(); self.wfile.write(body.encode())
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
        url=f'http://127.0.0.1:{server.server_port}/'
        def get(url):
            with urllib.request.urlopen(url,timeout=2) as response:
                return response.url,response.headers['Content-Type'],response.read().decode()
        try:
            result=analyze(url,get,'Test')
            self.assertTrue(any(f['code']=='broken_cta' and f['status']=='verified' for f in result.findings))
            self.assertEqual(calls.count(('GET','/quote')),2)
            self.assertFalse(any(method=='POST' or path=='/send' for method,path in calls))
        finally:
            server.shutdown(); server.server_close(); thread.join()


class ValuelessAttributeRegressionTests(unittest.TestCase):
    def test_valueless_html_attributes_do_not_abort_business_research(self):
        from prospecting.conversion import Page,analyze
        html='<meta name><a href style aria-label>Contact</a><form action method><input name aria-label><button type>Send</button></form>'
        page=Page(html)
        self.assertEqual(page.links[0]['href'],'')
        self.assertEqual(page.links[0]['text'],'Contact')
        result=analyze('https://fixture.example/',lambda url:(url,'text/html',html),'Test')
        self.assertFalse(any(f.get('status')=='verified' for f in result.findings))
