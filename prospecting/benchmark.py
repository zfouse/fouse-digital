"""Isolated, bounded live capacity measurement. Never writes the production ledger."""
import argparse
import json
from pathlib import Path
import tempfile
import time

from .geography import load_config, fingerprint
from .providers import discover_businesses
from .discovery import DiscoveryFailed
from .run import fetch, audit, run
from .browser_verify import verify


def measure(region, pool_path, screened=5, browser_checks=2):
    start = time.monotonic()
    try:
        rows, diagnostic, pool = discover_businesses('', fetch, pool_path, region=region)
    except DiscoveryFailed as error:
        return {'region': region, 'status': 'discovery_failed', 'elapsed_seconds': round(time.monotonic()-start, 2), 'attempts': error.attempts}
    discovery_seconds = time.monotonic()-start
    def polite(url):
        time.sleep(1)
        return audit(url)
    limits = {'screened': screened, 'browser_checks': browser_checks, 'static_seconds': 120, 'total_seconds': 300}
    report, _ = run(rows, {}, auditor=polite, browser_verifier=verify, limits=limits, region=region)
    return {'region': region, 'status': 'completed', 'discovery': diagnostic,
            'discovery_seconds': round(discovery_seconds, 2), 'discovered_businesses': len(rows),
            'elapsed_seconds': round(time.monotonic()-start, 2), 'report': report,
            'report_bytes': len(json.dumps(report).encode())}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', required=True)
    args = p.parse_args()
    load_config()  # Enforce country and conservative operating profile.
    regions = json.loads(Path(__file__).with_name('regions.example.json').read_text())
    with tempfile.TemporaryDirectory() as root:
        results = [measure(region, Path(root)/(fingerprint(region)+'.json')) for region in regions]
    payload = {'mode': 'isolated_live_benchmark', 'results': results,
               'paid_services': False, 'outreach': 'draft_only',
               'capacity_approved': False, 'limitations': 'Two bounded samples cannot establish nationwide yield or account billing allowance. No production state writes. Larger targets remain disabled.'}
    output = Path(args.output); output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2))
    for result in results:
        report = result.get('report', {})
        print(result['region']['id'], result['status'], result.get('discovered_businesses', 0), 'discovered;', report.get('screened_businesses', 0), 'screened;', len(report.get('new_leads', [])), 'qualified;', result['elapsed_seconds'], 'seconds')


if __name__ == '__main__':
    main()
