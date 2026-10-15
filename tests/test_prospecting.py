import unittest
from unittest.mock import patch
import urllib.error
from prospecting.run import audit, run, render, safe_url


def candidate(i=1, website='https://example.com', **tags):
    return {'id': i, 'type': 'node', 'lat': 38.63, 'lon': -90.2, 'tags': {'name': 'Test Plumbing', 'craft': 'plumber', 'website': website, 'phone': '+1 314 555 0100', **tags}}


def fake_audit(url):
    return url, [{'code': 'broken_cta', 'status': 'verified', 'impact': 50, 'evidence_strength': 30, 'label': 'Get a quote', 'url': url, 'observation': 'The quote link returned 404 twice.', 'evidence': 'GET statuses 404,404'}], []


class ProspectingTests(unittest.TestCase):
    def test_source_evidence_and_contacts(self):
        def getter(url):
            if url.endswith('robots.txt'):
                return url, 'text/plain', 'User-agent: *\nAllow: /'
            return url, 'text/html', '<a href="mailto:office@example.com?subject=x">Contact</a>'
        _, findings, contacts = audit('https://example.com', getter)
        self.assertTrue(all(f['status'] == 'potential' for f in findings))
        self.assertEqual(contacts[0]['value'], 'office@example.com')

    def test_healthy_source_no_invented_problem(self):
        def getter(url):
            return url, 'text/html', '<meta name="viewport" content="width=device-width, initial-scale=1">'
        self.assertFalse(any(f['status'] == 'verified' for f in audit('https://example.com', getter)[1]))
        report, _ = run([candidate()], {}, auditor=lambda u: (u, [], []))
        self.assertEqual(report['new_leads'], [])
        self.assertEqual(report['shortfall'], 10)

    def test_robots_and_unknown_errors(self):
        def denied(url):
            return url, 'text/plain', 'User-agent: *\nDisallow: /'
        with self.assertRaises(ValueError):
            audit('https://example.com', denied)
        report, state = run([candidate()], {}, auditor=lambda u: (_ for _ in ()).throw(TimeoutError()))
        self.assertFalse(report['new_leads'])
        self.assertEqual(state['seen'], [])

    def test_domain_phone_and_rerun_dedup(self):
        report, state = run([candidate(), candidate(2, 'https://www.example.com/other'), candidate(3, 'https://different.com')], {}, auditor=fake_audit)
        self.assertEqual(len(report['new_leads']), 1)
        again, _ = run([candidate()], state, auditor=fake_audit)
        self.assertFalse(again['new_leads'])
        self.assertEqual(again['qualified_today'], 1)

    def test_daily_cap(self):
        candidates = [candidate(i, f'https://example{i}.com', phone=f'314555{i:04}') for i in range(20)]
        report, state = run(candidates, {}, auditor=fake_audit)
        self.assertEqual(len(report['new_leads']), 10)
        report, _ = run(candidates, state, auditor=fake_audit)
        self.assertEqual(len(report['new_leads']), 0)

    def test_location_category_and_contact_required(self):
        outside = candidate(2)
        outside['lat'] = 40
        wrong_category = candidate(3, craft='shop')
        no_contact = candidate(4, phone='')
        report, _ = run([outside, wrong_category, no_contact], {}, auditor=fake_audit)
        self.assertEqual(report['new_leads'], [])

    def test_public_url_guard(self):
        with patch('socket.getaddrinfo', return_value=[(2, 1, 6, '', ('127.0.0.1', 80))]):
            with self.assertRaises(ValueError):
                safe_url('http://localhost')
        for url in ['file:///etc/passwd', 'http://user:pass@example.com', 'http://example.com:22']:
            with self.assertRaises(ValueError):
                safe_url(url)

    def test_report_escapes_untrusted_content(self):
        report, _ = run([candidate(name='<script>alert(1)</script>')], {}, auditor=fake_audit)
        self.assertNotIn('<script>alert(1)</script>', render(report))
        self.assertIn('&lt;script&gt;', render(report))
        self.assertIn('never sent', report['new_leads'][0]['draft']['status'])


if __name__ == '__main__':
    unittest.main()
