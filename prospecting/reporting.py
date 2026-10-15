"""Reconcile archived evidence without deleting historical counts or lead keys."""
import datetime as dt
import json
from pathlib import Path

if __package__:
    from .quality import verified, draft
    from .fit import business_fit
    from .findings import same_business, root_key
    from .contacts import hashes
else:
    from quality import verified, draft
    from fit import business_fit
    from findings import same_business, root_key
    from contacts import hashes


def carryover(state, state_dir, today):
    if today in state.get('verified_daily', {}):
        return state['verified_daily'][today], {'basis':'verified_daily ledger','legacy_total':state.get('daily',{}).get(today,0)}
    accepted=[];reports=0;roots=set()
    day=dt.date.fromisoformat(today)
    files=[]
    for date in (day,day+dt.timedelta(days=1)):
        files.extend((Path(state_dir)/'history').glob(date.strftime('%Y%m%d')+'*.json'))
    for path in sorted(files):
        try:
            report=json.loads(path.read_text())
        except (OSError,ValueError):
            continue
        if report.get('date')!=today:
            continue
        reports+=1
        for lead in report.get('new_leads',[]):
            confirmed=verified(lead.get('findings',[]))
            fit=business_fit({'tags':{'name':lead.get('name',''),'website':lead.get('website','')},'provenance':lead.get('provenance',{})})
            record=lead.get('entity') or {'provider':lead.get('provider'),'id':lead.get('discovery_source'),'name':lead.get('name'),'website':lead.get('website'),'contact_keys':hashes(lead.get('contacts',[]))}
            current_roots={f.get('root_cause_id') or root_key(f) for f in confirmed}
            if (not (current_roots-roots) or not fit['eligible'] or not lead.get('contacts') or not any(draft(lead.get('name',''),f,lead.get('category','service')) for f in confirmed) or
                    any(same_business(record,old) for old in accepted)):
                continue
            accepted.append(record);roots.update(current_roots)
    return len(accepted), {'basis':'archived browser evidence; not a live re-verification','reports_read':reports,
                           'legacy_total':state.get('daily',{}).get(today,0),'accepted_carryover':len(accepted),
                           'note':'Source-only, commercially excluded or unproven historical records remain in history and deduplication, but do not fill the verified-prospect quota.'}
