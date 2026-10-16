import copy
import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from prospecting.geography import load_config, select_region, advance, fingerprint, matches, tiles, STATES, overpass_query
from prospecting.overture import normalize
from prospecting.providers import discover_businesses
from prospecting.discovery import DiscoveryFailed
from prospecting.run import run, main
from prospecting.dashboard import render
from test_providers import ROW
from test_prospecting import fake_audit

REGION = {'id':'denver','name':'Denver','kind':'city','country':'US','states':['CO'], 'bbox':[-105.12,39.6,-104.6,39.95], 'timezone':'America/Denver','language':'en','localities':['Denver']}


def denver():
    row = copy.deepcopy(ROW)
    row['bbox'] = {'xmin':-104.99,'ymin':39.74}
    row['addresses'] = [{'country':'US','region':'CO','locality':'Denver'}]
    return normalize(row, 'test-release', REGION)


class GeographyTests(unittest.TestCase):
    def test_all_states_and_dc_rotate_durably_without_resetting_ledger(self):
        config = load_config(); state = {'seen':['historic'], 'daily':{'2026-01-01':3}}
        visited = []
        for _ in range(51):
            region = select_region(config, state); visited.append(region['states'][0]); advance(state, region, config)
            state = json.loads(json.dumps(state))
        self.assertEqual(set(visited), set(STATES)); self.assertEqual(len(set(visited)), 51)
        self.assertEqual(state['seen'], ['historic']); self.assertEqual(state['daily']['2026-01-01'], 3)
        self.assertTrue(select_region(config,state)['id'].endswith('-1'))
        for code in STATES:
            self.assertTrue(all(0 < b[2]-b[0] <= 2 and 0 < b[3]-b[1] <= 2 for b in tiles(code)))

    def test_international_and_unbenchmarked_large_profiles_are_blocked(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'config.json'
            for country,limits in [('CA',{}),('GB',{}),('US',{'screened':500}),('US',{'qualified':25}),('US',{'screened':0}),('US',{'browser_checks':21})]:
                config=load_config(); config['country']=country; config['countries'][country]['enabled']=True;config['limits'].update(limits)
                path.write_text(json.dumps(config))
                with self.assertRaises(ValueError): load_config(path)

    def test_state_city_and_metro_configuration(self):
        config=load_config();config['targeting']['states']=['CO','NY']
        state={};self.assertEqual(select_region(config,state)['states'],['CO'])
        advance(state,select_region(config,state),config);self.assertEqual(select_region(config,state)['states'],['NY'])
        config['targeting']['regions']=[REGION,dict(REGION,id='metro',kind='metro',states=['CO','WY'],localities=[])]
        state={};self.assertEqual(select_region(config,state),REGION)
        advance(state,REGION,config);self.assertEqual(select_region(config,state)['kind'],'metro')

    def test_source_country_state_and_city_required_no_cross_border_guessing(self):
        candidate=denver();self.assertTrue(matches(candidate,REGION));
        self.assertFalse(matches(dict(candidate,geography={'country':'US','state':'CO','city':None}),REGION));self.assertEqual(candidate['geography']['state'],'CO')
        for addresses in ([],[{'country':'CA','region':'CO','locality':'Denver'}],[{'country':'US','region':'WY','locality':'Denver'}],[{'country':'US','region':'CO','locality':'Aurora'}]):
            row=copy.deepcopy(ROW);row['bbox']={'xmin':-104.99,'ymin':39.74};row['addresses']=addresses
            self.assertIsNone(normalize(row,'release',REGION))

    def test_scoped_cache_cannot_leak_across_regions_empty_results_are_completed(self):
        now=dt.datetime.now(dt.timezone.utc)
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'pool.json'
            path.write_text(json.dumps({'schema':1,'fetched_at':now.isoformat(),'region':dict(REGION,id='other'), 'candidates':[denver()]}))
            provider=Mock(return_value=([],{}))
            rows,diagnostic,pool=discover_businesses('',Mock(),path,[('test',provider)],now,REGION)
            provider.assert_called_once();self.assertEqual(rows,[]);self.assertEqual(pool['region'],REGION)
            path.write_text(json.dumps(pool));provider.reset_mock()
            rows,_,_=discover_businesses('',Mock(),path,[('test',provider)],now,REGION)
            provider.assert_not_called();self.assertEqual(rows,[])
            self.assertNotEqual(fingerprint(REGION),fingerprint(dict(REGION,localities=[])))

    def test_overpass_fallback_requires_explicit_country_state_and_retains_bounded_query(self):
        osm={'type':'node','id':2,'lat':39.74,'lon':-104.99,'tags':{'name':'Fixture','website':'https://fixture.example','addr:country':'US','addr:state':'CO','addr:city':'Denver'}}
        with tempfile.TemporaryDirectory() as root,patch('prospecting.providers.discover',return_value=([osm,dict(osm,tags={'name':'Unknown'})],{})) as discovery:
            rows,_,_=discover_businesses('',Mock(),Path(root)/'pool', [('bad',Mock(side_effect=TimeoutError()))],region=REGION)
            self.assertEqual(len(rows),1);self.assertEqual(rows[0]['geography']['country'],'US')
            self.assertIn('["addr:country"="US"]',discovery.call_args.args[0]);self.assertIn('[timeout:45]',overpass_query(REGION))

    def test_global_dedup_and_configurable_caps_and_dashboard(self):
        rows=[dict(denver(),id=str(i)) for i in range(6)]
        limits={'screened':2,'browser_checks':1,'static_seconds':300,'total_seconds':900}
        report,state=run(rows,{},target=3,auditor=fake_audit,limits=limits,region=REGION)
        self.assertEqual(report['screened_businesses'],2);self.assertEqual(len(report['new_leads']),1)
        duplicate=dict(denver(),id='new-provider-id')
        again,_=run([duplicate],state,target=3,auditor=fake_audit,region=REGION)
        self.assertEqual(again['new_leads'],[])
        exhausted,_=run(rows,state,target=3,auditor=fake_audit,limits=limits,region=REGION)
        self.assertEqual(exhausted['screened_businesses'],0)
        html=render(report);self.assertIn('verified daily total / 3',html);self.assertIn('CO',html);self.assertIn('Commercial suitability',html)

    def test_discovery_failure_preserves_rotation_ledger_and_legacy_pool(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'ledger.json';path.write_text('{"seen":["historic"],"geo_rotation":{"cursor":4}}')
            legacy=Path(root)/'pool.json';legacy.write_text('legacy pool bytes');before=path.read_bytes()
            with patch('sys.argv',['run','--state',str(path),'--output',str(Path(root)/'reports')]),patch('prospecting.run.discover_businesses',side_effect=DiscoveryFailed([{'reason':'fixture timeout'}])):
                self.assertEqual(main(),2)
            self.assertEqual(path.read_bytes(),before);self.assertEqual(legacy.read_text(),'legacy pool bytes')
            self.assertTrue((Path(root)/'reports/diagnostic.json').exists())

    def test_real_parquet_discovery_outside_st_louis(self):
        import io
        import pyarrow as pa
        import pyarrow.dataset as ds
        import pyarrow.fs as fs
        import pyarrow.parquet as pq
        from prospecting.overture import load
        row=copy.deepcopy(ROW);row['bbox']={'xmin':-104.99,'xmax':-104.99,'ymin':39.74,'ymax':39.74}
        row['addresses']=[{'country':'US','region':'CO','locality':'Denver'}]
        foreign=dict(row,id='foreign',addresses=[{'country':'CA','region':'CO','locality':'Denver'}])
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'fixture.parquet';pq.write_table(pa.Table.from_pylist([row,ROW,foreign]),path)
            index=pa.Table.from_pylist([{'type':'Feature','collection':'place','bbox':{'xmin':-106.,'xmax':-104.,'ymin':39.,'ymax':40.},'assets':{'aws':{'href':'https://overturemaps-us-west-2.s3.us-west-2.amazonaws.com/release/fixture.parquet'}}}])
            buffer=io.BytesIO();pq.write_table(index,buffer);reader=ds.dataset
            with patch('prospecting.overture.read_json',return_value={'latest':'2026-09-23.1'}),patch('prospecting.overture.urllib.request.urlopen',return_value=io.BytesIO(buffer.getvalue())),patch.object(fs,'S3FileSystem',return_value=fs.LocalFileSystem()),patch.object(ds,'dataset',side_effect=lambda *a,**k:reader(path)):
                rows,_=load(REGION)
            self.assertEqual(len(rows),1);self.assertEqual(rows[0]['geography']['state'],'CO')
            self.assertEqual(rows[0]['contacts'][0]['value'],'3145550100')  # source value retained, never geographically guessed
            with patch('prospecting.overture.read_json',return_value={'latest':'2026-09-23.1'}),patch('prospecting.overture.urllib.request.urlopen',return_value=io.BytesIO(buffer.getvalue())),patch.object(fs,'S3FileSystem',return_value=fs.LocalFileSystem()),patch.object(ds,'dataset',side_effect=lambda *a,**k:reader(path)):
                diagnostics={};filtered,_=load(dict(REGION,industries=['roofer']),diagnostics)
            self.assertEqual(filtered,[])
            self.assertEqual(diagnostics,{})  # category pushdown avoids unnecessary row normalization
