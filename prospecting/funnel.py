"""Per-candidate, mutually exclusive outcomes plus explicitly nonexclusive stage counts."""
from collections import Counter
import socket
import ssl
import urllib.error
from urllib.parse import urlsplit


def failure_reason(error):
    if isinstance(error, urllib.error.HTTPError):return 'static_http_'+str(error.code)
    if isinstance(error, socket.gaierror):return 'static_dns_failure'
    if isinstance(error, (TimeoutError,socket.timeout)):return 'static_timeout'
    if isinstance(error, ssl.SSLError):return 'static_tls_failure'
    if isinstance(error, urllib.error.URLError):
        return failure_reason(error.reason) if isinstance(error.reason,Exception) else 'static_network_failure'
    message=str(error).lower()
    for text,reason in [('identity-provider','static_identity_redirect'),('robots','static_robots_unavailable_or_denied'),('budget','static_time_budget'),('not an inspectable','static_non_html_or_challenge'),('response too large','static_response_too_large'),('non-public','static_unsafe_destination')]:
        if text in message:return reason
    return 'static_inspection_rejected' if isinstance(error,ValueError) else 'static_network_failure'


class Funnel:
    def __init__(self):self.rows=[]
    def start(self,candidate):
        row={'provider':candidate.get('provider','osm'),'id':candidate.get('id'),'name':candidate.get('tags',{}).get('name'),
             'industry':candidate.get('tags',{}).get('craft'),'stages':['screened'],'outcome':None}
        website=candidate.get('tags',{}).get('website') or candidate.get('tags',{}).get('contact:website') or ''
        try:
            parsed=urlsplit(website if '://' in website else 'https://'+website)
            row['website_host']=parsed.hostname;row['website_path']=parsed.path[:160]
        except ValueError:
            row['website_host']=None
        self.rows.append(row);return row
    def reached(self,row,stage):
        if stage not in row['stages']:row['stages'].append(stage)
    def finish(self,row,reason,detail=None):
        row['outcome']=reason
        if detail:row['detail']=detail
    def report(self):
        if any(r['outcome'] is None for r in self.rows):raise RuntimeError('Incomplete qualification funnel')
        return {'screened':len(self.rows),'stages':dict(Counter(s for r in self.rows for s in r['stages'])),
                'outcomes':dict(Counter(r['outcome'] for r in self.rows)),
                'definitions':'Outcomes partition screened candidates exactly once. Stage counts are nonexclusive events, not a single linear chain; limited browsers can confirm an independently inspected page.',
                'candidates':self.rows}


def rates(report):
    attempts=report.get('browser_attempts',0)
    complete=sum(r['status']=='complete' for r in report.get('browser_outcomes',[]))
    return {'qualified_per_100_screened':round(100*len(report.get('new_leads',[]))/report['screened_businesses'],2) if report.get('screened_businesses') else None,
            'browser_complete_percent':round(100*complete/attempts,2) if attempts else None,
            'browser_confirmed_problem_percent':round(100*report.get('sites_with_confirmed_problems',0)/attempts,2) if attempts else None,
            'browser_attempt_denominator':attempts,'screened_denominator':report.get('screened_businesses',0)}
