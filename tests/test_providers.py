import copy
import datetime as dt
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from prospecting.discovery import DiscoveryFailed
from prospecting.overture import normalize
from prospecting.providers import discover_businesses, overture_provider
from prospecting.run import main, run, render

ROW = {'id': 'fixture-id', 'names': {'primary': 'Fixture Plumbing'}, 'websites': ['https://fixture.example'],
       'bbox': {'xmin': -90.2, 'xmax': -90.2, 'ymin': 38.6, 'ymax': 38.6}, 'phones': ['3145550100'],
       'emails': ['test@fixture.example'], 'taxonomy': {'primary': 'plumbing'}, 'confidence': .95,
       'operating_status': 'open', 'sources': [{'dataset': 'Fixture', 'license': 'CDLA-Permissive-2.0'}]}
NOW = dt.datetime(2026, 10, 14, tzinfo=dt.timezone.utc)


def candidate():
    return normalize(copy.deepcopy(ROW), '2026-09-23.1')


def pool(path, days):
    path.write_text(json.dumps({'schema': 1, 'fetched_at': (NOW-dt.timedelta(days=days)).isoformat(), 'candidates': [candidate()]}))


class ProviderIntegrationTests(unittest.TestCase):
    def test_normalization_never_fills_missing_contacts_or_accepts_closed_places(self):
        row = copy.deepcopy(ROW)
        row.update(phones=[], emails=[])
        self.assertEqual(normalize(row, 'release')['contacts'], [])
        for changed in ({'operating_status': 'permanently_closed'}, {'confidence': .5}, {'websites': []}, {'bbox': {'xmin': 0, 'ymin': 0}}, {'taxonomy': {'primary': 'paint_store'}}):
            row = dict(ROW, **changed)
            self.assertIsNone(normalize(row, 'release'))

    def test_provider_to_audit_to_draft_preserves_source_and_legacy_dedup(self):
        with tempfile.TemporaryDirectory() as root:
            provider = Mock(return_value=([candidate()], {'release': 'release'}))
            rows, diagnostic, saved = discover_businesses('q', Mock(), Path(root)/'pool.json', [('test', provider)], NOW)
            def auditor(url):
                return url, [{'code': 'broken_cta', 'status': 'verified', 'impact': 50, 'evidence_strength': 30, 'label': 'Contact', 'url': url, 'observation': 'Fixture observation', 'evidence': 'Fixture HTML'}], []
            # Legacy OSM lead with same phone prevents a duplicate from Overture on another domain.
            legacy = {'type': 'node', 'id': 1, 'tags': {'name': 'Fixture', 'craft': 'plumber', 'website': 'https://legacy.example', 'phone': '3145550100'}, 'lat': 38.6, 'lon': -90.2}
            report, state = run([legacy], {}, auditor=auditor)
            report, _ = run(rows, state, auditor=auditor)
            self.assertEqual(report['new_leads'], [])
            report, _ = run(rows, {}, auditor=auditor)
            lead = report['new_leads'][0]
            self.assertEqual(lead['contacts'][0]['value'], '3145550100')
            self.assertEqual(lead['contacts'][0]['source'], candidate()['source'])
            self.assertEqual(lead['provenance']['release'], '2026-09-23.1')
            self.assertIn('Fixture observation', lead['draft']['body'])
            self.assertIn('never sent', lead['draft']['status'])
            self.assertEqual(saved['candidates'], rows)

    def test_fresh_cache_avoids_every_network_provider(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)/'pool.json'; pool(path, 3)
            provider, getter = Mock(), Mock()
            rows, diagnostic, saved = discover_businesses('q', getter, path, [('test', provider)], NOW)
            provider.assert_not_called(); getter.assert_not_called()
            self.assertEqual(len(rows), 1)
            self.assertEqual(diagnostic['source'], 'saved_pool')
            self.assertIsNone(saved)

    def test_stale_cache_is_explicit_degraded_fallback_and_keeps_original_age(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)/'pool.json'; pool(path, 20)
            before = path.read_bytes()
            rows, diagnostic, saved = discover_businesses('q', Mock(), path, [('overture', Mock(side_effect=TimeoutError()))], NOW)
            self.assertEqual(diagnostic['status'], 'degraded')
            self.assertEqual(diagnostic['age_days'], 20)
            report, _ = run([], {})
            report['discovery'] = diagnostic
            self.assertIn('(degraded)', render(report))
            self.assertIn('20.0 days', render(report))
            self.assertIsNone(saved)
            self.assertEqual(path.read_bytes(), before)

    def test_expired_pool_falls_back_to_overpass_and_retains_ledger_compatibility(self):
        osm = {'type': 'node', 'id': 4, 'lat': 38.6, 'lon': -90.2, 'tags': {'name': 'Fixture'}}
        with tempfile.TemporaryDirectory() as root, patch('prospecting.providers.discover', return_value=([osm], {'attempts': []})):
            path = Path(root)/'pool.json'; pool(path, 46)
            rows, diagnostic, saved = discover_businesses('q', Mock(), path, [('overture', Mock(side_effect=RuntimeError()))], NOW)
            self.assertEqual(rows[0]['provider'], 'osm')
            self.assertEqual(diagnostic['source'], 'overpass')

    def test_total_failure_retains_cache_and_reports_both_providers(self):
        with tempfile.TemporaryDirectory() as root, patch('prospecting.providers.discover', side_effect=DiscoveryFailed([{'reason': 'HTTP 500'}])):
            path = Path(root)/'pool.json'; pool(path, 50)
            before = path.read_bytes()
            with self.assertRaises(DiscoveryFailed) as caught:
                discover_businesses('q', Mock(), path, [('overture', Mock(side_effect=RuntimeError()))], NOW)
            self.assertEqual([a['provider'] for a in caught.exception.attempts], ['overture', 'overpass'])
            self.assertEqual(path.read_bytes(), before)

    def test_modular_provider_failure_continues_and_subprocess_has_hard_deadline(self):
        with tempfile.TemporaryDirectory() as root:
            _, diagnostic, _ = discover_businesses('q', Mock(), Path(root)/'none', [('broken', Mock(side_effect=ValueError())), ('next', lambda: ([candidate()], {}))], NOW)
            self.assertEqual(diagnostic['source'], 'next')
        with patch('prospecting.providers.subprocess.run', side_effect=subprocess.TimeoutExpired('reader',180)) as child:
            with self.assertRaises(subprocess.TimeoutExpired):
                overture_provider()
            self.assertEqual(child.call_args.kwargs['timeout'], 180)

    def test_main_persists_pool_without_erasing_existing_ledger(self):
        with tempfile.TemporaryDirectory() as root:
            state = Path(root)/'ledger.json'
            state.write_text('{"seen": ["old-record"], "daily": {}}')
            saved = {'schema': 1, 'fetched_at': NOW.isoformat(), 'candidates': [candidate()]}
            with patch('sys.argv', ['run', '--state', str(state), '--output', str(Path(root)/'reports')]), patch('prospecting.run.discover_businesses', return_value=([candidate()], {'status': 'success'}, saved)), patch('prospecting.run.audit', return_value=('https://fixture.example', [], [])), patch('prospecting.run.time.sleep'):
                self.assertEqual(main(), 0)
            self.assertEqual(json.loads(state.read_text())['seen'], ['old-record'])
            self.assertEqual(json.loads((Path(root)/'pool.json').read_text()), saved)
            self.assertTrue((Path(root)/'licenses/CDLA-Permissive-2.0.txt').exists())
            self.assertTrue((Path(root)/'reports/licenses/Apache-2.0.txt').exists())

    def test_real_parquet_reader_filters_region_trade_status_and_contact_values(self):
        try:
            import pyarrow as pa
            import pyarrow.dataset as ds
            import pyarrow.fs as fs
            import pyarrow.parquet as pq
        except ImportError:
            self.skipTest('Install prospecting/requirements.txt')
        from prospecting.overture import load
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)/'region.parquet'
            outside = dict(ROW, id='outside', bbox={'xmin': 0., 'xmax': 0., 'ymin': 0., 'ymax': 0.})
            closed = dict(ROW, id='closed', operating_status='permanently_closed')
            pq.write_table(pa.Table.from_pylist([ROW, outside, closed]), path)
            index = pa.Table.from_pylist([{'type': 'Feature', 'collection': 'place', 'bbox': {'xmin': -91., 'xmax': -89., 'ymin': 38., 'ymax': 39.}, 'assets': {'aws': {'href': 'https://overturemaps-us-west-2.s3.us-west-2.amazonaws.com/release/fixture.parquet'}}}])
            buffer = io.BytesIO(); pq.write_table(index, buffer)
            actual_dataset = ds.dataset
            with patch('prospecting.overture.read_json', return_value={'latest': '2026-09-23.1'}), patch('prospecting.overture.urllib.request.urlopen', return_value=io.BytesIO(buffer.getvalue())), patch.object(fs, 'S3FileSystem', return_value=fs.LocalFileSystem()), patch.object(ds, 'dataset', side_effect=lambda *a, **kw: actual_dataset(path)):
                rows, release = load()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]['id'], 'fixture-id')
            self.assertEqual(rows[0]['contacts'][1]['value'], 'test@fixture.example')
