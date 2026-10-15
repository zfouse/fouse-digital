"""Collapse repeated evidence, retaining every source and business identity."""
import hashlib
import json
import re
from urllib.parse import urlsplit,urlunsplit,parse_qsl,urlencode,urljoin


def canonical_url(url):
    try:
        p=urlsplit(str(url))
        hostname=(p.hostname or '').casefold().removeprefix('www.')
        port=f':{p.port}' if p.port and p.port not in (80,443) else ''
        query=urlencode(sorted((k,v) for k,v in parse_qsl(p.query) if not k.lower().startswith(('utm_','fbclid','gclid','y_source'))))
        # HTTP/HTTPS and www aliases identify the same evidence destination, not all sibling businesses.
        return urlunsplit(('',hostname+port,p.path.rstrip('/') or '/',query,''))
    except ValueError:
        return str(url)


def root_key(f):
    code=f['code']
    if code in ('broken_cta','browser_broken_cta'):
        code='broken_cta'
    target=urljoin(f.get('url',''),f.get('target') or f.get('url',''))
    signature=f.get('signature','')
    if urlsplit(target).scheme not in ('http','https'):
        signature=signature or (f.get('target','')+'|'+f.get('label',''))
        target=f.get('url','')
    if code in ('viewport','mobile_width','mobile_overflow','mobile_contact_clipped','external_booking_review','empty_contact_link'):
        target='//' + (urlsplit(f.get('url','')).hostname or '').removeprefix('www.')
    if code in ('form_labels','form_submit','long_form','form_insecure_action'):
        if signature:
            target='//' + (urlsplit(f.get('url','')).hostname or '').removeprefix('www.')
        else:
            signature=re.sub(r'^form \d+;\s*','',f.get('evidence',''))
    return hashlib.sha256(json.dumps([code,canonical_url(target),signature],sort_keys=True).encode()).hexdigest()


def merge_findings(findings):
    result={}
    for source in findings:
        f=dict(source)
        key=root_key(f)
        f['root_cause_id']=key
        sources=list(f.get('sources',[]))
        if f.get('url') and f['url'] not in sources:
            sources.append(f['url'])
        evidence=list(f.get('evidence_records',[])) or [{'url':f.get('url'), 'evidence':f.get('evidence')}]
        if key not in result:
            f['sources']=sources;f['evidence_records']=evidence;result[key]=f
            continue
        existing=result[key]
        merged_sources=list(dict.fromkeys(existing['sources']+sources))
        records=existing['evidence_records']+[r for r in evidence if r not in existing['evidence_records']]
        if f.get('status')=='verified' and (existing.get('status')!='verified' or (f.get('verification')=='browser' and existing.get('verification')!='browser')):
            result[key]=f;existing=f
        existing['sources']=merged_sources;existing['evidence_records']=records
    return list(result.values())


def normalized_name(name):
    return ' '.join(re.sub(r'\b(llc|inc|incorporated|company|co)\b','',re.sub(r'[^a-z0-9 ]',' ',name.casefold())).split())


def same_business(a,b):
    # Shared phone, parent domain or booking service alone is not identity proof.
    if a.get('provider') and a.get('id') is not None and a.get('provider')==b.get('provider') and a.get('id')==b.get('id'):
        return True
    return normalized_name(a['name'])==normalized_name(b['name']) and bool(a.get('contact_keys') and set(a['contact_keys']).intersection(b.get('contact_keys',[])))
