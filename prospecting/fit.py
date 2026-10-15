"""Evidence-based purchasing fit. Unknown ownership is never called independent."""
import re
from urllib.parse import urlsplit

# Small, reviewable exclusions grounded in source identity; not fuzzy name guesses.
KNOWN_LARGE = {'ferguson.com': 'major distributor', 'goodmanmfg.com': 'major manufacturer',
               'rotorooter.com': 'national service brand', 'mistersparky.com': 'national franchise brand',
               'temperaturepro.com': 'national franchise brand', 'aireserv.com': 'national franchise brand', 'homedepot.com': 'major retailer',
               'lowes.com': 'major retailer', 'roofingsales.net': 'supplier/distributor'}
LOCAL = re.compile(r'\b(locally owned|locally operated|family owned|family operated|owner operated|independently owned)\b', re.I)
SUPPLIER = re.compile(r'\b(wholesale|distributor|manufacturer|supply store|equipment supplier|(?:plumbing|roofing|electrical|hvac|industrial) supply)\b', re.I)
SOCIAL = {'facebook.com','fb.com','instagram.com','linkedin.com','twitter.com','x.com','youtube.com','tiktok.com','pinterest.com'}
BOOKING = {'calendly.com','acuityscheduling.com','squareup.com','square.site','setmore.com','youcanbook.me','booking.setmore.com','housecallpro.com','jobber.com','getjobber.com','servicetitan.com'}


def host(url):
    try:
        return (urlsplit(url).hostname or '').casefold().removeprefix('www.')
    except ValueError:
        return ''


def under(domain, suffix):
    return domain == suffix or domain.endswith('.' + suffix)


def link_kind(url, text=''):
    domain=host(url)
    if any(under(domain,s) for s in SOCIAL):
        return 'social'
    if any(under(domain,s) for s in BOOKING):
        return 'booking'
    # Match whole words, never the substring in Facebook or a URL slug alone.
    if re.search(r'\b(book(?:ing)?|schedule|appointment)\b', text, re.I):
        return 'booking'
    return 'other'


IDENTITY_HOSTS = {'accounts.google.com','login.microsoftonline.com','login.live.com'}


def identity_page(url):
    return host(url) in IDENTITY_HOSTS


def business_fit(candidate, text=''):
    tags=candidate.get('tags',{})
    site=tags.get('website') or tags.get('contact:website') or ''
    domain=host(site)
    if identity_page(site):
        return {'eligible':False,'score':0,'ownership':'not_public_business_page','reasons':['Website leads to an identity-provider sign-in page, not a publicly auditable business inquiry path.'],'evidence_url':site}
    for suffix,reason in KNOWN_LARGE.items():
        if under(domain,suffix):
            return {'eligible':False,'score':0,'ownership':'known_large_brand','reasons':[f'{domain}: {reason}'],'evidence_url':site}
    if any(under(domain,s) for s in SOCIAL):
        return {'eligible':False,'score':0,'ownership':'social_only','reasons':['No independently auditable business website.'],'evidence_url':site}
    provenance=candidate.get('provenance',{})
    category=provenance.get('category','')
    if SUPPLIER.search(category.replace('_',' ')) or SUPPLIER.search(tags.get('name','')):
        return {'eligible':False,'score':0,'ownership':'supplier','reasons':['Listing identifies a supplier/distributor rather than a service operator.'],'evidence_url':candidate.get('source',site)}
    brand=provenance.get('brand')
    if isinstance(brand,dict) and not (brand.get('wikidata') or (brand.get('names') or {}).get('primary')):
        brand=None
    reasons=['Listed service business inside the configured local research area.']
    # Source statements are evidence, not a corporate-ownership verification.
    match=LOCAL.search(text.replace('-',' '))
    if match:
        reasons.append(f'Website states “{match.group(0)}”; ownership has not been independently verified.')
    if brand:
        reasons.append('A brand affiliation is present; ownership/purchasing autonomy needs review.')
    return {'eligible':True,'score':20 if match and not brand else 8 if brand else 12,
            'ownership':'self_reported_local' if match and not brand else 'affiliated_unknown' if brand else 'unknown',
            'reasons':reasons,'evidence_url':site}
