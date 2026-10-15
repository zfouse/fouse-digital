import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from zoneinfo import ZoneInfo

from prospecting.reporting import carryover
from prospecting.geography import load_config,select_region,advance,STATES
from prospecting.run import run
from prospecting.dashboard import render
from test_prospecting import candidate,fake_audit


class ReportingAndRotationTests(unittest.TestCase):
    def test_oct15_source_only_distributor_never_fills_verified_quota(self):
        today=dt.datetime.now(ZoneInfo('America/Chicago')).date().isoformat()
        state={'daily':{today:1},'seen':['historic']}
        with tempfile.TemporaryDirectory() as root:
            folder=Path(root)/'history';folder.mkdir()
            file=folder/(today.replace('-','')+'T155557.json')
            file.write_text(json.dumps({'date':today,'new_leads':[{'name':'Ferguson Plumbing Supply','website':'https://ferguson.com','contacts':[{'kind':'phone','value':'3145550100'}],'findings':[{'code':'empty_contact_link','status':'verified','impact':42}]}]}))
            before=file.read_bytes();prior,reason=carryover(state,root,today)
            self.assertEqual(prior,0);self.assertEqual(reason['legacy_total'],1)
            report,state=run([],state,prior_qualified=prior)
            self.assertEqual(report['qualified_today'],0);self.assertEqual(report['newly_qualified'],0);self.assertEqual(report['new_drafts'],0)
            self.assertEqual(report['historical_daily_total'],1);self.assertEqual(report['shortfall'],10)
            self.assertEqual(state['daily'][today],1);self.assertEqual(state['verified_daily'][today],0)
            self.assertEqual(state['seen'],['historic']);self.assertEqual(file.read_bytes(),before)
            self.assertIn('Historical ledger total: 1',render(report))

    def test_prior_browser_confirmed_prospects_carry_once_and_drafts_are_per_run(self):
        today=dt.datetime.now(ZoneInfo('America/Chicago')).date().isoformat()
        report,_=run([candidate()],{},auditor=fake_audit)
        state={'daily':{today:1}}
        with tempfile.TemporaryDirectory() as root:
            folder=Path(root)/'history';folder.mkdir()
            for n in (1,2):(folder/(today.replace('-','')+f'T00000{n}.json')).write_text(json.dumps(report))
            prior,_=carryover(state,root,today);self.assertEqual(prior,1)
            again,state=run([],state,prior_qualified=prior)
            self.assertEqual(again['qualified_today'],1);self.assertEqual(again['new_drafts'],0)
            self.assertEqual(carryover(state,root,today)[0],1)

    def test_alaska_cursor_migrates_without_repeating_or_excluding_alaska(self):
        config=load_config();state={'geo_rotation':{'cursor':1,'tiles':{'AK':1}},'seen':['historic']}
        self.assertEqual(select_region(config,state)['states'],['TX'])
        visited=['AK']
        for _ in range(50):
            region=select_region(config,state);visited.append(region['states'][0]);advance(state,region,config)
        self.assertIn('AK',visited);self.assertEqual(set(visited),set(STATES))
        self.assertEqual(state['seen'],['historic'])
        self.assertNotEqual(select_region(config,state)['id'],'TX-0')

    def test_unsupported_stronger_issue_does_not_hide_a_serviceable_fix(self):
        def audit(url):
            _,findings,contacts=fake_audit(url)
            return url,findings+[dict(findings[0],code='unknown_unfixable',impact=100,target=url+'/other')],contacts
        report,_=run([candidate()],{},auditor=audit)
        self.assertEqual(len(report['new_leads']),1)
        self.assertEqual(report['new_leads'][0]['draft']['finding_code'],'broken_cta')

    def test_contact_page_is_checked_and_partial_browser_failure_preserves_other_evidence(self):
        from prospecting.browser_verify import inspect_pages
        home='https://fixture.example/';contact=home+'contact';external='https://elsewhere.example/book'
        request={'url':home,'pages':[home,contact,external],'findings':[{'code':'empty_contact_link','url':contact,'status':'verified','verification':'source','impact':42}]}
        calls=[]
        def inspector(url,findings,**kwargs):
            calls.append(url)
            if url==home:raise TimeoutError('fixture timeout')
            return {'findings':[dict(findings[0],verification='browser')],'coverage':{'status':'complete','limitations':[]}}
        result=inspect_pages(request,inspector)
        self.assertEqual(calls,[contact,home]);self.assertEqual(result['coverage']['status'],'limited')
        self.assertEqual(result['findings'][0]['verification'],'browser')
        self.assertNotIn(external,calls)


    def test_core_run_reuses_verified_daily_ledger_without_reviving_legacy_count(self):
        today=dt.datetime.now(ZoneInfo('America/Chicago')).date().isoformat()
        state={'daily':{today:1},'verified_daily':{today:0}}
        report,state=run([candidate()],state,auditor=fake_audit)
        self.assertEqual(report['qualified_today'],1)
        self.assertEqual(state['daily'][today],2)
        self.assertEqual(state['verified_daily'][today],1)
        again,_=run([],state,auditor=fake_audit)
        self.assertEqual(again['qualified_today'],1)
