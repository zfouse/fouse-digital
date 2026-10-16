from collections import Counter
import copy
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import urllib.error

from prospecting.run import run
from prospecting.funnel import failure_reason
from prospecting.conversion import AuditResult
from prospecting.browser_verify import Guard,telemetry_endpoint,static_asset_read
from prospecting.geography import overpass_query,matches
from test_prospecting import candidate,fake_audit


class FunnelTests(unittest.TestCase):
    def test_terminal_outcomes_partition_every_screened_candidate(self):
        rows=[candidate(1),candidate(2,craft='shop'),candidate(3,website=''),candidate(4,website='https://ferguson.com'),candidate(5,website='https://timeout.example'),candidate(6,website='https://healthy.example')]
        def audit(url):
            if 'timeout' in url:raise TimeoutError()
            if 'healthy' in url:return url,[],[]
            return fake_audit(url)
        report,_=run(rows,{},auditor=audit)
        funnel=report['funnel']
        self.assertEqual(sum(funnel['outcomes'].values()),report['screened_businesses'])
        self.assertEqual(funnel['outcomes'],{'qualified':1,'unsupported_trade_or_missing_name':1,'missing_website':1,'discovery_fit_excluded':1,'static_timeout':1,'no_source_signals':1})
        self.assertEqual(report['qualification_rates']['qualified_per_100_screened'],16.67)
        self.assertIsNone(report['qualification_rates']['browser_complete_percent'])
        self.assertFalse(any(k.startswith('_') for l in report['new_leads'] for k in l))

    def test_browser_inconclusive_and_budget_are_separate_not_failed_qualification(self):
        rows=[candidate(i,f'https://{i}.example',name=f'Fixture {i}',phone=f'314555{i:04}') for i in range(4)]
        def audit(url):
            return AuditResult(url,[{'code':'viewport','url':url,'status':'potential','observation':'test','evidence':'fixture'}],[{'kind':'phone','value':'3145550100','source':url}],{})
        def browser(result):result.coverage['browser']={'status':'limited'};return result
        report,_=run(rows,{},auditor=audit,browser_verifier=browser,limits={'screened':4,'browser_checks':1,'static_seconds':300,'total_seconds':900})
        self.assertEqual(report['funnel']['outcomes'],{'browser_inconclusive':1,'browser_budget_or_time_not_inspected':3})
        self.assertEqual(report['qualification_rates']['browser_complete_percent'],0)
        self.assertEqual(report['qualification_rates']['browser_attempt_denominator'],1)

    def test_specific_static_failure_reasons(self):
        for code in (403,404,429,503):self.assertEqual(failure_reason(urllib.error.HTTPError('https://x',code,'',{},None)),'static_http_'+str(code))
        self.assertEqual(failure_reason(ValueError('robots disallows audit')),'static_robots_unavailable_or_denied')
        self.assertEqual(failure_reason(ValueError('Website redirects to an identity-provider sign-in page')),'static_identity_redirect')

    def test_only_exact_measured_telemetry_is_separate_and_still_never_sent(self):
        for url in ('https://www.google.com/g/collect?secret=redact','https://csp.secureserver.net/eventbus/web?clientid=redact'):
            events=[]
            route=SimpleNamespace(request=SimpleNamespace(url=url,resource_type='fetch',method='POST'),abort=lambda:events.append('abort'),continue_=lambda:events.append('sent'))
            guard=Guard(lambda u:u,'https://fixture.example',lambda u:True);guard.route(route)
            self.assertEqual(events,['abort']);self.assertEqual(guard.dynamic_blocked,0);self.assertEqual(guard.optional_blocked,1)
            self.assertNotIn('redact',str(guard.diagnostics))
        for url in ('https://google.com.evil.example/g/collect','https://www.google.com/api/book','https://csp.secureserver.net/eventbus/booking'):
            self.assertFalse(telemetry_endpoint(url))

    def test_industry_targeting_filters_discovery_without_changing_default_trades(self):
        region={'country':'US','states':['MO'],'bbox':[-91,38,-90,39],'industries':['plumber']}
        c=candidate();c['geography']={'country':'US','state':'MO'}
        self.assertTrue(matches(c,region));c['tags']['craft']='roofer';self.assertFalse(matches(c,region))
        self.assertIn('^(plumber)$',overpass_query(region))


    def test_discovery_uses_only_explicit_usable_website_and_preserves_cached_bytes(self):
        import tempfile,json
        from pathlib import Path
        from prospecting.overture import normalize
        from prospecting.providers import cached_pool,discover_businesses
        from test_providers import ROW,NOW,candidate as overture_candidate
        row=copy.deepcopy(ROW);row['websites']=['',None,'mailto:info@fixture.example',' https://fixture.example/contact ']
        self.assertEqual(normalize(row,'fixture')['tags']['website'],'https://fixture.example/contact')
        row['websites']=['',None];self.assertIsNone(normalize(row,'fixture'))
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'pool.json';region={'id':'fixture'}
            good=overture_candidate();bad=copy.deepcopy(good);bad['id']='blank';bad['tags']['website']=''
            path.write_text(json.dumps({'schema':1,'fetched_at':NOW.isoformat(),'region':region,'candidates':[good,bad]}));before=path.read_bytes()
            rows,diagnostic,pool=discover_businesses('',lambda:None,path,[],NOW,region)
            self.assertEqual(len(rows),1);self.assertEqual(diagnostic['pool_quality']['missing_website_excluded'],1)
            self.assertEqual(path.read_bytes(),before);self.assertIsNone(pool)

    def test_dashboard_exposes_the_funnel_without_implying_healthy_unchecked_sites(self):
        from prospecting.dashboard import render
        report,_=run([candidate()],{},auditor=lambda u:(u,[],[]))
        html=render(report)
        self.assertIn('Qualification funnel',html)
        self.assertIn('no source signals',html)
        self.assertIn('not a healthy website',html)

    def test_static_asset_fetch_parity_keeps_dynamic_and_interaction_locks(self):
        allowed='https://cdn.fixture.example/assets/static/widget.js?ver=1.2'
        self.assertTrue(static_asset_read('GET',allowed,'fetch'))
        for method,url in [('POST',allowed),('GET','https://cdn.fixture.example/data.json'),('GET',allowed+'&email=test')]:
            self.assertFalse(static_asset_read(method,url,'fetch'))
        for method,url,interacting,expected in [('GET',allowed,False,'read'),('POST',allowed,False,'blocked'),('GET','https://fixture.example/api/widget.js',False,'blocked'),('GET','https://fixture.example/submit.js',False,'blocked'),('GET',allowed,True,'blocked'),('GET','https://fixture.example/data.json',False,'blocked')]:
            events=[];checked=[]
            guard=Guard(lambda u:checked.append(u),'https://fixture.example',lambda u:True);guard.interacting=interacting
            route=SimpleNamespace(request=SimpleNamespace(url=url,resource_type='fetch',method=method),abort=lambda:events.append('blocked'),continue_=lambda:events.append('read'))
            guard.route(route);self.assertEqual(events,[expected]);self.assertEqual(bool(checked),expected=='read')
        guard=Guard(lambda u:(_ for _ in ()).throw(ValueError('private destination')),'https://fixture.example',lambda u:True)
        guard.route(SimpleNamespace(request=SimpleNamespace(url=allowed,resource_type='fetch',method='GET'),abort=lambda:None,continue_=lambda:self.fail('unsafe destination read')))
        self.assertEqual(guard.static_asset_reads,0)
        guard.resource_failure(allowed,'fetch',404);self.assertEqual(guard.essential_failed,1)
