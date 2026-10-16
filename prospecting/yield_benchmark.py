"""Bounded market/industry funnel benchmark; scratch state only, draft-only."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import time

from .geography import ANCHORS,fingerprint,validate_region
from .providers import discover_businesses
from .discovery import DiscoveryFailed
from .run import fetch,audit,run
from .browser_verify import verify
from .findings import canonical_url,normalized_name

TRADES=['plumber','hvac','roofer','electrician','landscaper']
MARKETS=[('TX','Houston'),('IL','Chicago'),('CO','Denver')]


def sample(rows,trade,count=3):
    selected=[];seen=set()
    ordered=sorted(rows,key=lambda c:hashlib.sha256(('yield-v1'+str(c['id'])).encode()).hexdigest())
    for row in ordered:
        if row['tags'].get('craft')!=trade:continue
        key=(canonical_url(row['tags'].get('website','')),normalized_name(row['tags']['name']))
        if key in seen:continue
        seen.add(key);selected.append(row)
        if len(selected)>=count:break
    return selected


def benchmark(output,cache,phase='improved',browser_checks=2):
    started=time.monotonic();results=[];discoveries=[]
    def save():
        total_screened=sum(r.get('report',{}).get('screened_businesses',0) for r in results)
        qualified=sum(len(r.get('report',{}).get('new_leads',[])) for r in results)
        attempts=sum(r.get('report',{}).get('browser_attempts',r.get('report',{}).get('browser_verified_sites',0)) for r in results)
        statuses=Counter(o['status'] for r in results for o in r.get('report',{}).get('browser_outcomes',[]))
        elapsed=time.monotonic()-started
        payload={'phase':phase,'sample_design':f'3 fixed candidates per industry; 5 trades × 3 bounded U.S. markets. Each cell permits {browser_checks} prioritized browser attempts; uninspected candidates stay unverified.',
                 'screened':total_screened,'qualified':qualified,'qualified_per_100_screened':round(100*qualified/total_screened,2) if total_screened else None,
                 'browser_attempts':attempts,'browser_outcomes':dict(statuses),'browser_complete_percent':round(100*statuses['complete']/attempts,2) if attempts else None,
                 'elapsed_seconds':round(elapsed,2),'processing_minutes_per_100_screened':round(elapsed/60*100/total_screened,2) if total_screened else None,
                 'cost':{'incremental_paid_services_usd':0,'assumption':'Existing local runtime or standard public-repository Ubuntu Actions runner; no paid API/model. Shared artifact allowance and source bandwidth not priced or instrumented.'},
                 'production_state_modified':False,'outreach_sent':False,'discoveries':discoveries,'results':results}
        output.write_text(json.dumps(payload,indent=2,ensure_ascii=False))
    for code,name in MARKETS:
        lon,lat=ANCHORS[code]
        region={'id':name.lower()+'-yield','name':name+' bounded metro sample','kind':'metro','country':'US','states':[code],
                'bbox':[round(lon-.4,4),round(lat-.3,4),round(lon+.4,4),round(lat+.3,4)],'timezone':'America/Denver' if code=='CO' else 'America/Chicago','language':'en'}
        validate_region(region);path=cache/(fingerprint(region)+'.json');t=time.monotonic()
        try:
            rows,diagnostic,pool=discover_businesses('',fetch,path,region=region)
            if pool:path.write_text(json.dumps(pool))
            discoveries.append({'market':name,'seconds':round(time.monotonic()-t,2),'candidate_count':len(rows),'diagnostic':diagnostic})
        except DiscoveryFailed as error:
            discoveries.append({'market':name,'status':'discovery_failed','attempts':error.attempts});save();continue
        for trade in TRADES:
            selected=sample(rows,trade)
            t=time.monotonic()
            def polite(url):time.sleep(1);return audit(url)
            report,_=run(selected,{},auditor=polite,browser_verifier=verify,region=region,
                         limits={'screened':3,'browser_checks':browser_checks,'static_seconds':90,'total_seconds':160})
            results.append({'market':name,'industry':trade,'sample_size':len(selected),'elapsed_seconds':round(time.monotonic()-t,2),'report':report})
            save();print(phase,name,trade,report['screened_businesses'],'screened',len(report['new_leads']),'qualified',flush=True)
    save()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True);parser.add_argument('--cache',required=True);parser.add_argument('--phase',default='improved')
    parser.add_argument('--browser-checks',type=int,choices=[1,2],default=2)
    args=parser.parse_args();output=Path(args.output);cache=Path(args.cache);output.parent.mkdir(parents=True,exist_ok=True);cache.mkdir(parents=True,exist_ok=True)
    benchmark(output,cache,args.phase,args.browser_checks)


if __name__=='__main__':main()
