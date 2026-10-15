"""Recheck a bounded existing review sample. Isolated output, never production state."""
import argparse
from collections import Counter
import datetime as dt
import json
from pathlib import Path
import time

from .run import audit
from .browser_verify import verify
from .fit import business_fit
from .contacts import deduplicate
from .quality import serviceable,draft


def validate(report, output, limit=6):
    rows=report.get('new_leads',[])+report.get('review_queue',[])
    unique={}
    for row in rows:
        unique.setdefault(row['website'],row)
    results=[];start=time.monotonic()
    def save():
        statuses=Counter(r.get('browser',{}).get('status','not_attempted') for r in results)
        payload={'mode':'isolated_read_only_review_validation','checked_at':dt.datetime.now(dt.timezone.utc).isoformat(),
                 'source_report_date':report.get('date'),'elapsed_seconds':round(time.monotonic()-start,2),
                 'businesses_attempted':len(results),'browser_outcomes':dict(statuses),
                 'verified_draftable_businesses':sum(bool(r.get('draft')) for r in results),
                 'production_state_modified':False,'outreach_sent':False,'results':results}
        output.write_text(json.dumps(payload,indent=2,ensure_ascii=False))
    for lead in list(unique.values())[:limit]:
        row={'name':lead['name'],'website':lead['website'],'source':lead.get('discovery_source'),
             'baseline_browser_status':lead.get('coverage',{}).get('browser',{}).get('status','not_attempted')}
        try:
            time.sleep(1)
            result=audit(lead['website'])
            fit=business_fit({'tags':{'name':lead['name'],'website':result.final},'provenance':lead.get('provenance',{})},result.coverage.get('source_text',''))
            result=verify(result)
            contacts=deduplicate(list(result.contacts)+lead.get('contacts',[]))
            confirmed=serviceable(result.findings)
            row.update(fit=fit,contacts=contacts,findings=result.findings,browser=result.coverage.get('browser',{}))
            if fit['eligible'] and contacts and confirmed:
                row['draft']=draft(lead['name'],max(confirmed,key=lambda f:f['impact']),lead.get('category','service'))
        except (OSError,ValueError) as error:
            row['error']=type(error).__name__+': '+str(error)[:350]
        results.append(row);save()
        print(row['name'],row.get('browser',{}).get('status','audit_unavailable'),'draftable',bool(row.get('draft')),flush=True)
    save()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--limit',type=int,default=6)
    args=parser.parse_args()
    if not 1<=args.limit<=12:parser.error('Sample limit must be 1–12')
    output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True)
    validate(json.loads(Path(args.report).read_text()),output,args.limit)


if __name__=='__main__':main()
