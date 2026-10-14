import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import urllib.error

from prospecting.discovery import discover, DiscoveryFailed, ENDPOINTS, retry_after
from prospecting.run import main

SUCCESS = ('https://endpoint.test', 'application/json', '{"elements": []}')


def error(code, headers=None):
    return urllib.error.HTTPError('https://endpoint.test', code, 'error', headers or {}, None)


class DiscoveryTests(unittest.TestCase):
    def discover(self, responses):
        getter = Mock(side_effect=responses)
        sleep = Mock()
        result = discover('query', getter, sleeper=sleep, jitter=lambda: 2)
        return result, getter, sleep

    def test_transient_http_codes_retry_then_succeed(self):
        for code in (502, 503, 504, 429):
            with self.subTest(code=code):
                (_, diagnostic), getter, sleep = self.discover([error(code), SUCCESS])
                self.assertEqual(getter.call_count, 2)
                sleep.assert_called_once_with(32)
                self.assertEqual(diagnostic['status'], 'success')
                self.assertEqual(diagnostic['attempts'][0]['reason'], f'HTTP {code}')

    def test_backoff_exponential_with_jitter(self):
        (_, diagnostic), getter, sleep = self.discover([TimeoutError(), urllib.error.URLError('timeout'), SUCCESS])
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [32, 62])
        self.assertEqual(len(diagnostic['attempts']), 3)
        self.assertEqual(getter.call_args.kwargs['timeout'], 60)

    def test_failover_after_three_failures(self):
        (_, diagnostic), getter, sleep = self.discover([error(502), error(503), error(504), SUCCESS])
        self.assertEqual([c.args[0] for c in getter.call_args_list], [ENDPOINTS[0]] * 3 + [ENDPOINTS[1]])
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [32, 62, 32])
        self.assertEqual(diagnostic['endpoint'], ENDPOINTS[1])

    def test_rate_limit_retry_after_seconds_and_date(self):
        (_, _), getter, sleep = self.discover([error(429, {'Retry-After': '90'}), SUCCESS])
        sleep.assert_called_once_with(92)
        now = lambda: dt.datetime(2026, 10, 14, tzinfo=dt.timezone.utc)
        self.assertEqual(retry_after('Wed, 14 Oct 2026 00:01:30 GMT', now), 90)
        self.assertEqual(retry_after('invalid', now), 0)
        self.assertEqual(retry_after('-10', now), 0)

    def test_long_retry_after_abandons_endpoint_without_requery(self):
        (_, _), getter, sleep = self.discover([error(429, {'Retry-After': '3600'}), SUCCESS])
        self.assertEqual([c.args[0] for c in getter.call_args_list], list(ENDPOINTS))
        sleep.assert_called_once_with(32)

    def test_all_endpoints_fail_bounded(self):
        getter = Mock(side_effect=TimeoutError())
        sleep = Mock()
        with self.assertRaises(DiscoveryFailed) as caught:
            discover('query', getter, sleeper=sleep, jitter=lambda: 5)
        self.assertEqual(getter.call_count, 6)
        self.assertEqual(len(caught.exception.attempts), 6)
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [35, 65, 35, 35, 65])

    def test_bad_query_not_retried(self):
        getter = Mock(side_effect=error(400))
        sleep = Mock()
        with self.assertRaises(DiscoveryFailed):
            discover('query', getter, sleeper=sleep)
        self.assertEqual(getter.call_count, 1)
        sleep.assert_not_called()

    def test_invalid_or_partial_responses_failover(self):
        bad = [('<html>bad gateway</html>'), '{"elements": [], "remark":"timed out"}', '{"elements": {}}']
        for text in bad:
            with self.subTest(text=text):
                (_, diagnostic), getter, _ = self.discover([('url', 'text/plain', text)] * 3 + [SUCCESS])
                self.assertEqual(getter.call_count, 4)
                self.assertEqual(diagnostic['endpoint'], ENDPOINTS[1])

    def test_failure_keeps_ledger_and_prior_leads_and_exits_nonzero(self):
        with tempfile.TemporaryDirectory() as root:
            state = Path(root) / 'ledger.json'
            state.write_text('{"seen": ["existing-lead"], "daily": {"2026-10-14": 4}}')
            before = state.read_bytes()
            output = Path(root) / 'reports'
            output.mkdir()
            (output / 'review.json').write_text('prior lead data')
            (output / 'review.html').write_text('prior review')
            with patch('sys.argv', ['run', '--state', str(state), '--output', str(output)]), patch('prospecting.run.discover', side_effect=DiscoveryFailed([{'outcome': 'failure', 'reason': 'HTTP 502'}])), patch('prospecting.run.run') as research:
                self.assertEqual(main(), 2)
                research.assert_not_called()
            self.assertEqual(state.read_bytes(), before)
            self.assertEqual((output / 'review.json').read_text(), 'prior lead data')
            self.assertEqual((output / 'review.html').read_text(), 'prior review')
            report = json.loads((output / 'diagnostic.json').read_text())
            self.assertEqual(report['status'], 'discovery_failed')
            self.assertIsNone(report['qualified_today'])
            self.assertIsNone(report['shortfall'])
            self.assertEqual(report['new_leads'], [])
            self.assertIn('research incomplete', (output / 'diagnostic.html').read_text())

    def test_first_run_failure_does_not_create_ledger(self):
        with tempfile.TemporaryDirectory() as root:
            state = Path(root) / 'state' / 'ledger.json'
            with patch('sys.argv', ['run', '--state', str(state), '--output', root]), patch('prospecting.run.discover', side_effect=DiscoveryFailed([])):
                self.assertEqual(main(), 2)
            self.assertFalse(state.exists())

    def test_success_after_failure_writes_only_real_research(self):
        with tempfile.TemporaryDirectory() as root:
            state = Path(root) / 'ledger.json'
            state.write_text('{"seen": ["existing-lead"], "daily": {}}')
            (Path(root) / 'diagnostic.json').write_text('old failure')
            with patch('sys.argv', ['run', '--state', str(state), '--output', root]), patch('prospecting.run.discover', return_value=([], {'status': 'success', 'attempts': [{'reason': 'HTTP 502'}, {'outcome': 'success'}]})):
                self.assertEqual(main(), 0)
            report = json.loads((Path(root) / 'review.json').read_text())
            self.assertEqual(report['status'], 'success')
            self.assertEqual(report['new_leads'], [])
            self.assertEqual(json.loads(state.read_text())['seen'], ['existing-lead'])
            self.assertFalse(state.with_name('ledger.json.tmp').exists())
            self.assertFalse((Path(root) / 'diagnostic.json').exists())


if __name__ == '__main__':
    unittest.main()
