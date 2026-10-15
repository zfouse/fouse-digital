"""Bounded, evidence-based prospect research. No sending capabilities."""
import argparse
import datetime as dt
import hashlib
import ipaddress
import json
import copy
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
    from .geography import load_config, select_region, fingerprint, advance, matches
    from .discovery import DiscoveryFailed, validate
    from .providers import discover_businesses
    from .conversion import analyze
    from .contacts import deduplicate, hashes
    from .quality import rank, verified, draft
    from .dashboard import render
    from .history import snapshot
    from .fit import business_fit
    from .findings import canonical_url, merge_findings, same_business
    from .browser_verify import verify as verify_browser
else:
    from geography import load_config, select_region, fingerprint, advance, matches
    from discovery import DiscoveryFailed, validate
    from providers import discover_businesses
    from conversion import analyze
    from contacts import deduplicate, hashes
    from quality import rank, verified, draft
    from dashboard import render
    from history import snapshot
    from fit import business_fit
    from findings import canonical_url, merge_findings, same_business
    from browser_verify import verify as verify_browser

AGENT = 'FouseDigitalResearch/1.0 (+https://zfouse.github.io/fouse-digital/)'
QUERY = ''  # Geographic production discovery uses scoped Overture address filters.


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


def run(candidates, state, target=10, auditor=audit, browser_verifier=None, limits=None, region=None, ledger_timezone='America/Chicago'):
    limits = limits or {'screened': 100, 'browser_checks': 12, 'static_seconds': 300, 'total_seconds': 900}
    today = dt.datetime.now(ZoneInfo(ledger_timezone)).date().isoformat()
    seen = set(state.get('seen', []))
    count = state.get('daily', {}).get(today, 0)
    usage = state.get('daily_usage', {}).get(today, {})
    screen_budget = max(0, limits['screened']-usage.get('screened', 0))
    browser_budget = max(0, limits['browser_checks']-usage.get('browser_checks', 0))
    previous_entities = state.get('entities', [])
    previous_findings = set(state.get('finding_seen', []))
    pool, skipped, excluded = [], [], []
    audit_cache = {}
    started = time.monotonic()
    # Reserve browser time after the static sample instead of verifying the first sites encountered.
    candidates = sorted(candidates, key=lambda c: hashlib.sha256((today + str(c.get('id'))).encode()).hexdigest())
    checked = 0
    screened = 0
    for c in candidates:
        if count >= target or screened >= screen_budget or time.monotonic()-started >= limits['static_seconds']:
            break
        screened += 1
        if region is not None and not matches(c, region):
            continue
        tags=c.get('tags', {})
        location=c.get('center') or c
        lat,lon=location.get('lat'),location.get('lon')
        if tags.get('craft') not in ('plumber','electrician','hvac','roofer','carpenter','painter','landscaper') or not tags.get('name'):
            continue
        if not isinstance(lat,(float,int)) or not isinstance(lon,(float,int)) or not (-90<=lat<=90 and -180<=lon<=180):
            continue
        url=tags.get('website') or tags.get('contact:website')
        if not url: continue
        if '://' not in url: url='https://'+url
        c=dict(c,tags=dict(tags,website=url))
        fit=business_fit(c)
        if not fit['eligible']:
            excluded.append({'name':tags['name'],'website':url,'fit':fit});continue
        provider=c.get('provider','osm')
        provider_string=('osm:'+c['type']+':'+str(c['id'])) if provider=='osm' else provider+':'+str(c['id'])
        provider_key=hashlib.sha256(provider_string.encode()).hexdigest()
        if provider_key in seen: continue
        record={'provider':provider,'id':c['id'],'name':tags['name'],'website':url,'geography':c.get('geography',{}),'source':c.get('source') or f"https://www.openstreetmap.org/{c['type']}/{c['id']}"}
        try:
            cached=audit_cache.get(canonical_url(url))
            if cached is None:
                checked+=1
                result=auditor(url)
                audit_cache[canonical_url(url)]=copy.deepcopy(result)
            else:
                result=copy.deepcopy(cached)
            final,findings,contacts=result
            fit=business_fit(dict(c,tags=dict(c['tags'],website=final)),getattr(result,'coverage',{}).get('source_text',''))
            if not fit['eligible']: excluded.append({'name':tags['name'],'website':final,'fit':fit});continue
            contacts=list(contacts)+c.get('contacts',[])
            for kind in ('email','phone'):
                value=tags.get(kind) or tags.get('contact:'+kind)
                if value: contacts.append({'kind':kind,'value':value,'source':record['source']})
            contacts=deduplicate(contacts)
            record['contact_keys']=hashes(contacts)
            if not contacts or any(same_business(record,old) for old in previous_entities): continue
            # Legacy IDs/domains stay intact. Domain-only legacy suppression applies only to root pages,
            # not named, distinct business paths on a shared operator website.
            legacy_domain=hashlib.sha256(('domain:'+identity(final)).encode()).hexdigest()
            if not previous_entities and legacy_domain in seen and urllib.parse.urlsplit(url).path in ('','/'):
                skipped.append({'source':record['source'],'reason':'legacy_domain_seen_identity_unknown'});continue
            findings=merge_findings(findings)
            if not findings: continue
            lead={'name':tags['name'],'category':tags['craft'],'location':{'lat':lat,'lon':lon}, 'geography':c.get('geography',{}),
                  'discovery_source':record['source'],'provider':provider,'provenance':c.get('provenance',{}),
                  'website':final,'checked_at':dt.datetime.now(dt.timezone.utc).isoformat(),'contacts':contacts,
                  'findings':findings,'coverage':getattr(result,'coverage',{}),'fit':fit,'entity':record,
                  '_result':result,'_keys':keys(c)+hashes(contacts),'related_businesses':[]}
            duplicate=next((existing for existing in pool if same_business(existing['entity'],record)),None)
            if duplicate:
                duplicate['related_businesses'].append(record)
                duplicate['contacts']=deduplicate(duplicate['contacts']+contacts)
                duplicate['findings']=merge_findings(duplicate['findings']+findings)
                continue
            pool.append(lead)
        except (ValueError,OSError,urllib.error.URLError) as e:
            skipped.append({'source':record['source'],'reason':type(e).__name__})
    weights={'broken_cta':60,'empty_contact_link':40,'cta_fragment':20,'mobile_width':12,'form_submit':12,'form_labels':8}
    pool.sort(key=lambda lead:-(lead['fit']['score']+max((weights.get(f['code'],0) for f in lead['findings']),default=0)))
    verified_count=0
    for lead in pool:
        result=lead.pop('_result')
        if browser_verifier and verified_count<browser_budget and time.monotonic()-started<limits['total_seconds']:
            result.findings=lead['findings']
            result=browser_verifier(result)
            lead['findings']=merge_findings(result.findings)
            lead['coverage']=result.coverage
            verified_count+=1
        else:
            lead['findings']=[dict(f,status='potential',impact=0,evidence_strength=8) if f.get('verification')!='browser' else f for f in lead['findings']]
        lead['coverage'].pop('source_text',None)
        lead['ranking']=rank(lead['findings'],lead['contacts'],lead['category'],lead['fit'])
    eligible=sorted((l for l in pool if verified(l['findings'])),key=lambda l:(-l['ranking']['score'],l['name']))
    leads=[];related_identities=[];used_roots=set(previous_findings)
    for lead in eligible:
        confirmed=[f for f in verified(lead['findings']) if f['root_cause_id'] not in used_roots]
        if not confirmed:
            primary=next((p for p in leads if set(f['root_cause_id'] for f in verified(p['findings'])).intersection(f['root_cause_id'] for f in verified(lead['findings']))),None)
            if primary: primary['related_businesses'].append(lead['entity'])
            else: related_identities.append({'entity':lead['entity'],'reason':'Same finding already reviewed for a related business.','root_cause_ids':[f['root_cause_id'] for f in verified(lead['findings'])]})
            continue
        if len(leads)>=max(0,target-count): continue
        strongest=max(confirmed,key=lambda f:f['impact'])
        lead['draft']=draft(lead['name'],strongest,lead['category'])
        if not lead['draft']: continue
        leads.append(lead)
        used_roots.update(f['root_cause_id'] for f in confirmed)
        seen.update(lead['_keys'])
    review_queue=[]
    for lead in (l for l in pool if not verified(l['findings']) and l['findings']):
        roots=set(f['root_cause_id'] for f in lead['findings'])
        related=next((q for q in review_queue if roots.intersection(f['root_cause_id'] for f in q['findings'])),None)
        if related:
            related['related_businesses'].append(lead['entity'])
            related['findings']=merge_findings(related['findings']+lead['findings'])
        elif len(review_queue)<10:
            review_queue.append(lead)
    for lead in pool:
        lead.pop('_keys',None)
    state.setdefault('daily_usage', {})[today] = {'screened': usage.get('screened', 0)+screened, 'browser_checks': usage.get('browser_checks', 0)+verified_count}
    state['seen']=sorted(seen)
    state.setdefault('daily',{})[today]=count+len(leads)
    state['entities']=previous_entities+[l['entity'] for l in leads]
    state['finding_seen']=sorted(used_roots)
    relationships=state.get('related_entities',[])
    for relation in related_identities:
        if relation not in relationships: relationships.append(relation)
    state['related_entities']=relationships
    return {'date':today,'target':target,'qualified_today':count+len(leads),'new_leads':leads,
            'daily_usage':state['daily_usage'][today],'screened_businesses':screened,'elapsed_seconds':round(time.monotonic()-started,2),'geographic_target':region,'limits':limits,
            'review_queue':review_queue,'audited_sites':checked,'browser_verified_sites':verified_count,
            'related_identities':related_identities,'excluded_businesses':excluded[:30],'shortfall':max(0,target-count-len(leads)), 'skipped':skipped,
            'ranking_scope':'Local-fit candidates and browser-confirmed problems in the bounded audited sample.',
            'attribution':'Overture Maps Foundation https://docs.overturemaps.org/attribution/ ; © OpenStreetMap contributors, ODbL https://www.openstreetmap.org/copyright'},state


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--config', help='Geographic targeting and bounded daily limits JSON')
    p.add_argument('--state', default='state/ledger.json')
    p.add_argument('--output', default='reports')
    p.add_argument('--candidates', help='Offline OSM-format JSON fixture')
    args = p.parse_args()
    config = load_config(args.config) if args.config else load_config()
    state_path = Path(args.state)
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    output = Path(args.output)
    region = select_region(config, state)
    pool_path = state_path.parent / 'pools' / (fingerprint(region) + '.json')
    pool = None
    try:
        if args.candidates:
            candidates = validate(Path(args.candidates).read_text())
            discovery = {'status': 'success', 'source': 'fixture', 'attempts': []}
        else:
            candidates, discovery, pool = discover_businesses(QUERY, fetch, pool_path, region=region)
    except DiscoveryFailed as e:
        report = {
            'status': 'discovery_failed',
            'date': dt.datetime.now(ZoneInfo(config['ledger_timezone'])).date().isoformat(),
            'target': config['limits']['qualified'], 'geographic_target': region, 'qualified_today': None, 'shortfall': None,
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
    report, state = run(candidates, state, target=config['limits']['qualified'], auditor=polite_audit, browser_verifier=verify_browser,
                        limits=config['limits'], region=None if args.candidates else region, ledger_timezone=config['ledger_timezone'])
    report['country_policy'] = config['countries']['US']
    report['discovered_businesses'] = len(candidates)
    if not args.candidates:
        advance(state, region, config)
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
        pool_path.parent.mkdir(parents=True, exist_ok=True)
        temp_pool = pool_path.with_suffix('.tmp')
        temp_pool.write_text(json.dumps(pool, indent=2))
        temp_pool.replace(pool_path)
        shutil.copytree(Path(__file__).with_name('licenses'), state_path.parent / 'licenses', dirs_exist_ok=True)
    print(f"Qualified today: {report['qualified_today']}/{report['target']}; new drafts: {len(report['new_leads'])}; shortfall: {report['shortfall']}")

    return 0


if __name__ == '__main__':
    sys.exit(main())
