"""Bounded, evidence-based prospect research. No sending capabilities."""
import argparse
import datetime as dt
import hashlib
import html
from html.parser import HTMLParser
import ipaddress
import json
from pathlib import Path
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from zoneinfo import ZoneInfo

if __package__:
    from .discovery import DiscoveryFailed, validate
    from .providers import discover_businesses
else:
    from discovery import DiscoveryFailed, validate
    from providers import discover_businesses

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


class Page(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.links = []
        self.viewport = False
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'a' and a.get('href'):
            self.links.append(a['href'])
        if tag == 'meta' and a.get('name', '').lower() == 'viewport' and 'width=device-width' in a.get('content', '').lower().replace(' ', ''):
            self.viewport = True


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
    return [hashlib.sha256(v.encode()).hexdigest() for v in values]


def audit(url, getter=fetch):
    """Only observable source findings; never submit forms or infer lost revenue."""
    origin = urllib.parse.urlunsplit(urllib.parse.urlsplit(url)._replace(path='/robots.txt', query='', fragment=''))
    try:
        _, _, robots = getter(origin)
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise ValueError('robots unavailable') from e
        robots = ''
    rp = urllib.robotparser.RobotFileParser()
    rp.parse(robots.splitlines())
    if not rp.can_fetch(AGENT, url):
        raise ValueError('robots disallows audit')
    final, content_type, text = getter(url)
    if 'text/html' not in content_type:
        raise ValueError('Not an HTML page')
    page = Page(text)
    evidence = []
    if urllib.parse.urlsplit(final).scheme == 'http':
        evidence.append({'code': 'http', 'observation': 'The homepage response used HTTP rather than HTTPS.', 'url': final, 'evidence': final})
    # Absence is an observation of this response only, never a broken-site claim.
    if not page.viewport:
        evidence.append({'code': 'viewport', 'observation': 'The fetched homepage HTML did not include a width=device-width viewport declaration.', 'url': final, 'evidence': 'Parsed meta tags in the fetched HTML; JavaScript-rendered tags were not inspected.'})
    contacts = []
    for link in page.links:
        if link.lower().startswith(('mailto:', 'tel:')):
            value = urllib.parse.unquote(link.split(':', 1)[1].split('?', 1)[0]).strip()
            if value and '\n' not in value and '\r' not in value:
                contacts.append({'kind': 'email' if link.lower().startswith('mailto:') else 'phone', 'value': value, 'source': final})
    return final, evidence, contacts


def draft(name, finding):
    return {'subject': f'A homepage observation for {name}', 'body': f"Hi {name} team,\n\nI’m Zach with Fouse Digital. While reviewing {finding['url']}, I observed: {finding['observation']}\n\nThis is a source-level check, so I’d confirm the behavior in a browser before recommending a change. Would you like a free lead-path review?\n\nZach\nFouse Digital\nhttps://zfouse.github.io/fouse-digital/", 'status': 'draft — requires human review; never sent'}


def run(candidates, state, target=10, auditor=audit):
    today = dt.datetime.now(ZoneInfo('America/Chicago')).date().isoformat()
    seen = set(state.get('seen', []))
    count = state.setdefault('daily', {}).get(today, 0)
    leads, skipped = [], []
    deadline = time.monotonic() + 600
    # Rotate the pool daily so unqualified entries cannot permanently hide later records.
    candidates = sorted(candidates, key=lambda c: hashlib.sha256((today + str(c.get('id'))).encode()).hexdigest())
    checked = 0
    for c in candidates:
        if checked >= 150 or time.monotonic() >= deadline:
            break
        if count >= target:
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
            if seen.intersection(ids):
                continue
            checked += 1
            final, findings, contacts = auditor(url)
            ids += [hashlib.sha256(('domain:' + identity(final)).encode()).hexdigest()]
            if seen.intersection(ids):
                continue
            source = c.get('source') or f"https://www.openstreetmap.org/{c['type']}/{c['id']}"
            contacts.extend(c.get('contacts', []))
            for kind in ('email', 'phone'):
                value = tags.get(kind) or tags.get('contact:' + kind)
                if value:
                    contacts.append({'kind': kind, 'value': value, 'source': source})
            if not findings or not contacts:
                continue
            leads.append({'name': tags['name'], 'category': tags.get('craft'), 'location': c.get('center', {'lat': c.get('lat'), 'lon': c.get('lon')}), 'discovery_source': source, 'provider': c.get('provider', 'osm'), 'provenance': c.get('provenance', {}), 'website': final, 'checked_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'contacts': contacts, 'findings': findings, 'draft': draft(tags['name'], findings[0])})
            seen.update(ids)
            count += 1
        except (ValueError, OSError, urllib.error.URLError) as e:
            skipped.append({'source': f"{c.get('type')}/{c.get('id')}", 'reason': type(e).__name__})
    state['seen'] = sorted(seen)
    state['daily'][today] = count
    return {'date': today, 'target': target, 'qualified_today': count, 'new_leads': leads, 'shortfall': max(0, target-count), 'skipped': skipped, 'attribution': 'Overture Maps Foundation https://docs.overturemaps.org/attribution/ ; © OpenStreetMap contributors, ODbL https://www.openstreetmap.org/copyright'}, state


def render(report):
    esc = lambda x: html.escape(str(x))
    if report.get('status') == 'discovery_failed':
        return '<!doctype html><html lang="en"><meta charset="utf-8"><title>Discovery failed</title><h1>Discovery failed — research incomplete</h1><p>' + esc(report['message']) + '</p><pre>' + esc(json.dumps(report['discovery'], indent=2)) + '</pre></html>'
    cards = []
    for lead in report['new_leads']:
        cards.append('<article><h2>' + esc(lead['name']) + '</h2><pre>' + esc(json.dumps(lead, indent=2, ensure_ascii=False)) + '</pre></article>')
    return '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Fouse Digital review</title><style>body{font:16px system-ui;max-width:960px;margin:40px auto;padding:20px}pre{white-space:pre-wrap;overflow-wrap:anywhere}article{border-top:1px solid #aaa;padding:20px 0}</style><h1>Prospect review — ' + esc(report['date']) + '</h1><p>' + esc(report['qualified_today']) + ' qualified today; shortfall: ' + esc(report['shortfall']) + '</p><p>Drafts only. Confirm observations and contacts before outreach.</p>' + ''.join(cards) + '<p>' + esc(report['attribution']) + '</p></html>'


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
    report['status'] = 'success'
    report['discovery'] = discovery
    output.mkdir(parents=True, exist_ok=True)
    (output / 'review.json').write_text(json.dumps(report, indent=2, ensure_ascii=False))
    (output / 'review.html').write_text(render(report))
    for name in ('diagnostic.json', 'diagnostic.html'):
        (output / name).unlink(missing_ok=True)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = state_path.with_name(state_path.name + '.tmp')
    temporary.write_text(json.dumps(state, indent=2))
    temporary.replace(state_path)
    if pool is not None:
        pool_path = state_path.parent / 'pool.json'
        temp_pool = pool_path.with_suffix('.tmp')
        temp_pool.write_text(json.dumps(pool, indent=2))
        temp_pool.replace(pool_path)
    print(f"Qualified today: {report['qualified_today']}/10; new drafts: {len(report['new_leads'])}; shortfall: {report['shortfall']}")

    return 0


if __name__ == '__main__':
    sys.exit(main())
