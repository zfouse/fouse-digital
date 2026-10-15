"""Bounded, evidence-based prospect research. No sending capabilities."""
import argparse
import datetime as dt
import hashlib
import ipaddress
import json
from pathlib import Path
import socket
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

if __package__:
    from .discovery import DiscoveryFailed, validate
    from .providers import discover_businesses
    from .conversion import analyze
    from .contacts import deduplicate, hashes
    from .quality import rank, verified, draft
    from .dashboard import render
    from .history import snapshot
else:
    from discovery import DiscoveryFailed, validate
    from providers import discover_businesses
    from conversion import analyze
    from contacts import deduplicate, hashes
    from quality import rank, verified, draft
    from dashboard import render
    from history import snapshot

AGENT = 'FouseDigitalResearch/1.0 (+https://zfouse.github.io/fouse-digital/)'
BBOX = '38.40,-90.75,38.95,-89.95'
QUERY = f'''[out:json][timeout:45];nwr["craft"~"^(plumber|electrician|hvac|roofer|carpenter|painter|landscaper)$"]["name"]({BBOX});out center tags;'''


def safe_url(url):
    p = urllib.parse.urlsplit(url)
    if p.scheme not in ('http', 'https') or not p.hostname or p.username or p.password or p.port not in (None, 80, 443):
        raise ValueError('Unsupported URL')
    addresses = socket.getaddrinfo(p.hostname, p.port or (443 if p.scheme == 'https' else 80), type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError('Non-public destination')
    return url


class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        safe_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url, data=None, timeout=15):
    safe_url(url)
    req = urllib.request.Request(url, data=data, headers={'User-Agent': AGENT})
    with urllib.request.build_opener(Redirect).open(req, timeout=timeout) as r:
        raw = r.read(1_000_001)
        if len(raw) > 1_000_000:
            raise ValueError('Response too large')
        return r.url, r.headers.get('Content-Type', ''), raw.decode('utf-8', errors='replace')


def identity(url):
    return urllib.parse.urlsplit(url).hostname.lower().removeprefix('www.')


def keys(candidate):
    tags = candidate['tags']
    provider = candidate.get('provider', 'osm')
    values = [('osm:' + candidate['type'] + ':' + str(candidate['id'])) if provider == 'osm' else provider + ':' + str(candidate['id'])]
    website = tags.get('website') or tags.get('contact:website')
    if website:
        values.append('domain:' + identity(website))
    phone = tags.get('phone') or tags.get('contact:phone')
    if phone:
        digits = ''.join(c for c in phone if c.isdigit())
        if len(digits) >= 10:
            values.append('phone:' + digits[-10:])
    for contact in candidate.get('contacts', []):
        if contact.get('kind') == 'phone':
            digits = ''.join(c for c in contact.get('value', '') if c.isdigit())
            if len(digits) >= 10:
                values.append('phone:' + digits[-10:])
    return [hashlib.sha256(v.encode()).hexdigest() for v in values] + hashes(candidate.get('contacts', []) + [{'kind': k, 'value': tags.get(k) or tags.get('contact:' + k) or ''} for k in ('email', 'phone')])


def audit(url, getter=fetch):
    return analyze(url, getter, AGENT)


def run(candidates, state, target=10, auditor=audit):
    today = dt.datetime.now(ZoneInfo('America/Chicago')).date().isoformat()
    seen = set(state.get('seen', []))
    count = state.setdefault('daily', {}).get(today, 0)
    eligible, review_queue, skipped = [], [], []
    evaluated_seen = set(seen)
    deadline = time.monotonic() + 600
    # Rotate the pool daily so unqualified entries cannot permanently hide later records.
    candidates = sorted(candidates, key=lambda c: hashlib.sha256((today + str(c.get('id'))).encode()).hexdigest())
    checked = 0
    for c in candidates:
        if checked >= 150 or time.monotonic() >= deadline:
            break
        if count >= target or len(eligible) >= max(20, 2*(target-count)):
            break
        tags = c.get('tags', {})
        location = c.get('center') or c
        lat, lon = location.get('lat'), location.get('lon')
        if tags.get('craft') not in ('plumber', 'electrician', 'hvac', 'roofer', 'carpenter', 'painter', 'landscaper'):
            continue
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)) or not (38.40 <= lat <= 38.95 and -90.75 <= lon <= -89.95):
            continue
        url = tags.get('website') or tags.get('contact:website')
        if not tags.get('name') or not url:
            continue
        if '://' not in url:
            url = 'https://' + url
        c = dict(c, tags=dict(tags, website=url))
        try:
            ids = keys(c)
            if evaluated_seen.intersection(ids):
                continue
            checked += 1
            result = auditor(url)
            final, findings, contacts = result
            ids += [hashlib.sha256(('domain:' + identity(final)).encode()).hexdigest()]
            if evaluated_seen.intersection(ids):
                continue
            source = c.get('source') or f"https://www.openstreetmap.org/{c['type']}/{c['id']}"
            contacts.extend(c.get('contacts', []))
            for kind in ('email', 'phone'):
                value = tags.get(kind) or tags.get('contact:' + kind)
                if value:
                    contacts.append({'kind': kind, 'value': value, 'source': source})
            contacts = deduplicate(contacts)
            ids += hashes(contacts)
            if evaluated_seen.intersection(ids) or not contacts:
                continue
            lead = {'name': tags['name'], 'category': tags.get('craft'), 'location': c.get('center', {'lat': c.get('lat'), 'lon': c.get('lon')}), 'discovery_source': source, 'provider': c.get('provider', 'osm'), 'provenance': c.get('provenance', {}), 'website': final, 'checked_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'contacts': contacts, 'findings': findings, 'coverage': getattr(result, 'coverage', {})}
            lead['ranking'] = rank(findings, contacts, tags.get('craft'))
            confirmed = sorted(verified(findings), key=lambda f: -f['impact'])
            if not confirmed:
                if findings:
                    review_queue.append(lead)
                continue
            lead['draft'] = draft(tags['name'], confirmed[0], tags.get('craft', 'service'))
            if lead['draft'] is None:
                continue
            lead['_keys'] = ids
            eligible.append(lead)
            evaluated_seen.update(ids)
        except (ValueError, OSError, urllib.error.URLError) as e:
            skipped.append({'source': f"{c.get('type')}/{c.get('id')}", 'reason': type(e).__name__})
    leads = sorted(eligible, key=lambda l: (-l['ranking']['score'], l['name'].casefold()))[:max(0, target-count)]
    for lead in leads:
        seen.update(lead.pop('_keys'))
    count += len(leads)
    review_queue = sorted(review_queue, key=lambda l: (-len(l['findings']), l['name']))[:10]
    state['seen'] = sorted(seen)
    state['daily'][today] = count
    return {'date': today, 'target': target, 'qualified_today': count, 'new_leads': leads, 'review_queue': review_queue, 'audited_sites': checked, 'ranking_scope': 'Highest priorities among websites audited within this run’s budget.', 'shortfall': max(0, target-count), 'skipped': skipped, 'attribution': 'Overture Maps Foundation https://docs.overturemaps.org/attribution/ ; © OpenStreetMap contributors, ODbL https://www.openstreetmap.org/copyright'}, state



def main():
    p = argparse.ArgumentParser()
    p.add_argument('--state', default='state/ledger.json')
    p.add_argument('--output', default='reports')
    p.add_argument('--candidates', help='Offline OSM-format JSON fixture')
    args = p.parse_args()
    state_path = Path(args.state)
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    output = Path(args.output)
    pool = None
    try:
        if args.candidates:
            candidates = validate(Path(args.candidates).read_text())
            discovery = {'status': 'success', 'source': 'fixture', 'attempts': []}
        else:
            candidates, discovery, pool = discover_businesses(QUERY, fetch, state_path.parent / 'pool.json')
    except DiscoveryFailed as e:
        report = {
            'status': 'discovery_failed',
            'date': dt.datetime.now(ZoneInfo('America/Chicago')).date().isoformat(),
            'target': 10, 'qualified_today': None, 'shortfall': None,
            'new_leads': [], 'skipped': [],
            'message': 'Discovery failed. No research completed; existing ledger and prior lead reports preserved.',
            'discovery': {'status': 'failed', 'attempts': e.attempts},
            'attribution': 'Overture Maps Foundation https://docs.overturemaps.org/attribution/ ; © OpenStreetMap contributors, ODbL https://www.openstreetmap.org/copyright',
        }
        output.mkdir(parents=True, exist_ok=True)
        # Separate diagnostic files never overwrite a prior successful review.
        (output / 'diagnostic.json').write_text(json.dumps(report, indent=2))
        (output / 'diagnostic.html').write_text(render(report))
        print(report['message'], file=sys.stderr)
        return 2
    def polite_audit(url):
        time.sleep(1)
        return audit(url)
    report, state = run(candidates, state, auditor=polite_audit)
    report['status'] = 'degraded' if discovery.get('status') == 'degraded' else 'success'
    report['discovery'] = discovery
    output.mkdir(parents=True, exist_ok=True)
    if (output / 'review.json').exists() or (output / 'review.html').exists():
        snapshot(output)
    (output / 'review.json').write_text(json.dumps(report, indent=2, ensure_ascii=False))
    (output / 'review.html').write_text(render(report))
    shutil.copytree(Path(__file__).with_name('licenses'), output / 'licenses', dirs_exist_ok=True)
    for name in ('diagnostic.json', 'diagnostic.html'):
        (output / name).unlink(missing_ok=True)
    snapshot(output, state_path.parent)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = state_path.with_name(state_path.name + '.tmp')
    temporary.write_text(json.dumps(state, indent=2))
    temporary.replace(state_path)
    if pool is not None:
        pool_path = state_path.parent / 'pool.json'
        temp_pool = pool_path.with_suffix('.tmp')
        temp_pool.write_text(json.dumps(pool, indent=2))
        temp_pool.replace(pool_path)
        shutil.copytree(Path(__file__).with_name('licenses'), state_path.parent / 'licenses', dirs_exist_ok=True)
    print(f"Qualified today: {report['qualified_today']}/10; new drafts: {len(report['new_leads'])}; shortfall: {report['shortfall']}")

    return 0


if __name__ == '__main__':
    sys.exit(main())
