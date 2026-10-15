"""Bounded GET-only conversion-path analysis. Never submit forms or click booking."""
from dataclasses import dataclass
import re
import json
import time
from html.parser import HTMLParser
import urllib.error
import urllib.parse
import urllib.robotparser

if __package__:
    from .contacts import canonical, deduplicate
    from .fit import link_kind, identity_page
    from .findings import merge_findings
else:
    from contacts import canonical, deduplicate
    from fit import link_kind, identity_page
    from findings import merge_findings

CTA = re.compile(r'\b(contact|quote|estimate|book|booking|schedule|appointment|call|request|consultation)\b', re.I)
CHALLENGE = re.compile(r'<title[^>]*>\s*(just a moment|access denied|attention required|verify you are human)', re.I)


class Page(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.links, self.forms, self.ids, self.labels = [], [], set(), set()
        self.text = []
        self.viewport = False
        self.current_link = None
        self.current_form = None
        self.implicit_label = 0
        self.hidden_depth = 0
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        # HTMLParser represents present-but-valueless attributes as None. Browsers
        # treat their string value as empty; preserve key presence for hidden/etc.
        a = {key: value if value is not None else '' for key,value in attrs}
        if tag in ('script', 'style'):
            self.hidden_depth += 1
        if a.get('id'):
            self.ids.add(a['id'])
        if tag == 'meta' and a.get('name', '').lower() == 'viewport':
            self.viewport = 'width=device-width' in a.get('content', '').lower().replace(' ', '')
        if tag == 'a':
            self.current_link = {'href': a.get('href', ''), 'text': a.get('aria-label', ''), 'onclick': a.get('onclick'), 'hidden': 'hidden' in a or 'display:none' in a.get('style', '').replace(' ', '')}
            self.links.append(self.current_link)
        if tag == 'form':
            self.current_form = {'action': a.get('action', ''), 'method': a.get('method', 'get').lower(), 'fields': [], 'submit': False, 'search': a.get('role') == 'search'}
            self.forms.append(self.current_form)
        if tag == 'label':
            self.implicit_label += 1
            if a.get('for'):
                self.labels.add(a['for'])
        if self.current_form and tag in ('input', 'select', 'textarea'):
            a['implicit_label'] = bool(self.implicit_label)
            if a.get('type', '').lower() not in ('hidden', 'submit', 'button', 'reset', 'image'):
                self.current_form['fields'].append(a)
            if a.get('type', '').lower() in ('submit', 'image'):
                self.current_form['submit'] = True
        if self.current_form and tag == 'button' and a.get('type', 'submit') == 'submit':
            self.current_form['submit'] = True

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.hidden_depth = max(0, self.hidden_depth-1)
        if tag == 'a':
            self.current_link = None
        if tag == 'form':
            self.current_form = None
        if tag == 'label':
            self.implicit_label = max(0, self.implicit_label-1)

    def handle_data(self, data):
        if not self.hidden_depth:
            self.text.append(data)
        if self.current_link is not None and not self.hidden_depth:
            self.current_link['text'] += data


@dataclass
class AuditResult:
    final: str
    findings: list
    contacts: list
    coverage: dict

    def __iter__(self):
        return iter((self.final, self.findings, self.contacts))

    def __getitem__(self, index):
        return (self.final, self.findings, self.contacts)[index]


def finding(code, observation, url, evidence, verified=False, impact=0, action='', **extra):
    return {'code': code, 'observation': observation, 'url': url, 'evidence': evidence,
            'status': 'verified' if verified else 'potential',
            'impact': impact, 'evidence_strength': (30 if code == 'broken_cta' else 24) if verified else 8,
            'action': action, 'verification': 'source', **extra}


def analyze(url, getter, agent):
    deadline = time.monotonic() + 45
    robots = {}
    findings, contacts, pages, checks = [], [], [], []
    def get(target):
        if time.monotonic() >= deadline:
            raise TimeoutError('Audit budget reached')
        return getter(target)
    def allowed(target):
        p = urllib.parse.urlsplit(target)
        origin = f'{p.scheme}://{p.netloc}'
        if origin not in robots:
            try:
                _, _, text = get(origin + '/robots.txt')
            except urllib.error.HTTPError as e:
                if e.code != 404:
                    raise ValueError('robots unavailable') from e
                text = ''
            rp = urllib.robotparser.RobotFileParser()
            rp.parse(text.splitlines())
            robots[origin] = rp
        return robots[origin].can_fetch(agent, target)
    def read(target):
        if not allowed(target):
            raise ValueError('robots disallows audit')
        final, kind, text = get(target)
        if urllib.parse.urlsplit(final).hostname != urllib.parse.urlsplit(target).hostname:
            # Redirects can introduce another site's rules; do not inspect its body before permission.
            if not allowed(final):
                raise ValueError('redirect robots disallows audit')
        if identity_page(final):
            raise ValueError('Website redirects to an identity-provider sign-in page; no public business page audited')
        if 'text/html' not in kind or CHALLENGE.search(text):
            raise ValueError('Not an inspectable HTML page')
        return final, text, Page(text)
    final, text, home = read(url)
    origin = urllib.parse.urlsplit(final)
    queue = [(final, text, home)]
    # Inspect up to two contact/booking/quote landing pages, not an unbounded crawl.
    targets = []
    for link in home.links:
        target = urllib.parse.urljoin(final, link['href'])
        p = urllib.parse.urlsplit(target)
        if not link['hidden'] and not link['onclick'] and CTA.search(link['text'] + ' ' + p.path) and p.scheme in ('https', 'http') and p.netloc == origin.netloc and not p.query and not re.search(r'cancel|delete|remove|logout|unsubscribe|confirm|checkout', p.path, re.I) and p.path not in ('', '/'):
            target = urllib.parse.urlunsplit(p._replace(fragment=''))
            if target not in targets:
                targets.append(target)
    # Recheck at most two distinct CTA destinations. Never probe form action URLs.
    for target in targets[:2]:
        statuses = []
        try:
            landed, body, page = read(target)
            queue.append((landed, body, page))
            checks.append({'url': target, 'result': 'loaded'})
        except urllib.error.HTTPError as e:
            statuses.append(e.code)
            if e.code in (404, 410):
                try:
                    read(target)
                except urllib.error.HTTPError as again:
                    statuses.append(again.code)
                except (ValueError, OSError):
                    pass
            if len(statuses) == 2 and statuses[0] == statuses[1] and statuses[0] in (404, 410):
                label = next((l['text'].strip() for l in home.links if urllib.parse.urljoin(final, l['href']).split('#')[0] == target), 'Contact link')
                findings.append(finding('broken_cta', f'The “{label[:100]}” link on the homepage points to a page that returned HTTP {statuses[0]} on two checks.', final,
                    f'href={target}; GET statuses={statuses}', True, 50,
                    'Repair this contact or request destination and confirm the customer path.', target=target, label=label[:100]))
            else:
                checks.append({'url': target, 'result': f'HTTP {e.code}; not verified broken'})
                findings.append(finding('link_unavailable', 'A contact destination could not be reliably checked; browser review is required.', final, f'{target}: HTTP {e.code}', target=target))
        except (ValueError, OSError) as e:
            checks.append({'url': target, 'result': type(e).__name__})
            findings.append(finding('link_unchecked', 'A contact destination needs browser inspection; network or access rules prevented inspection.', final, f'{target}: {type(e).__name__}', target=target))
    for page_url, body, page in queue:
        pages.append({'url': page_url, 'forms': len(page.forms), 'cta_links': sum(bool(CTA.search(l['text'])) for l in page.links), 'booking_links': [l['href'] for l in page.links if link_kind(urllib.parse.urljoin(page_url,l['href']),l['text']) == 'booking']})
        for link in page.links:
            href = link['href'].strip()
            kind = 'email' if href.lower().startswith('mailto:') else 'phone' if href.lower().startswith('tel:') else None
            if kind:
                value = urllib.parse.unquote(href.split(':', 1)[1].split('?', 1)[0])
                if canonical(kind, value):
                    contacts.append({'kind': kind, 'value': value, 'source': page_url})
                elif not link['onclick'] and not link['hidden'] and link['text'].strip():
                    # Verify only an objectively empty URI, not a foreign/international number.
                    if not value.strip():
                        findings.append(finding('empty_contact_link', f'The “{link["text"].strip()[:100]}” link contains an empty {href.split(":")[0]} destination.', page_url,
                            f'anchor text={link["text"].strip()[:100]!r}; href={href!r}', True, 42,
                            'Connect this contact link to the correct public business contact.', label=link['text'].strip()[:100], target=href))
            if CTA.search(link['text']) and href.startswith('#') and href[1:] not in page.ids:
                findings.append(finding('cta_fragment', 'A call-to-action points to a fragment absent from the fetched HTML; JavaScript may supply it.', page_url,
                    f'anchor={link["text"].strip()[:100]!r}; href={href!r}', action='Check this call-to-action in a browser.'))
        for index, form in enumerate(page.forms, 1):
            if form['search'] or any(f.get('type') == 'search' for f in form['fields']):
                continue
            fields = form['fields']
            form_signature=json.dumps({'action':urllib.parse.urljoin(page_url,form['action']) if form['action'] not in ('','#') else 'current_document','method':form['method'],'fields':[(f.get('name'),f.get('type'),f.get('id')) for f in fields]},sort_keys=True)
            if not fields:
                continue
            unlabeled = [f.get('name') or f.get('id') or f.get('type', 'text') for f in fields if not (f.get('aria-label') or f.get('aria-labelledby') or f.get('title') or f.get('implicit_label') or f.get('id') in page.labels)]
            if unlabeled:
                findings.append(finding('form_labels', 'A non-search form has fields without accessible labels in the fetched HTML; rendered behavior needs checking.', page_url,
                    f'form {index}; fields={unlabeled[:8]}', action='Inspect rendered labels and add clear field instructions if confirmed.',signature=form_signature))
            action = urllib.parse.urljoin(page_url, form['action'])
            if page_url.startswith('https:') and action.startswith('http:'):
                findings.append(finding('form_insecure_action', 'An HTTPS page declares an HTTP form destination; JavaScript handling and browser behavior need inspection.', page_url, f'form {index}; action={action}', action='Inspect the inquiry flow without submitting customer information.',signature=form_signature))
            if not form['submit']:
                findings.append(finding('form_submit', 'A non-search form has no native submit control in the fetched HTML; JavaScript may provide one.', page_url,
                    f'form {index}; action={form["action"]!r}', action='Inspect the rendered inquiry flow without submitting it.',signature=form_signature))
            if len(fields) > 8:
                findings.append(finding('long_form', 'A non-search form includes more than eight visible-type fields in source; check whether all are needed for an initial inquiry.', page_url,
                    f'form {index}; field count={len(fields)}', action='Review initial inquiry friction in a browser.',signature=form_signature))
        external_booking = [l['href'] for l in page.links if link_kind(urllib.parse.urljoin(page_url,l['href']),l['text']) == 'booking' and urllib.parse.urlsplit(urllib.parse.urljoin(page_url, l['href'])).netloc != origin.netloc]
        if external_booking:
            findings.append(finding('external_booking_review', 'Appointment booking uses an external service; the booking journey has not been tested.', page_url, f'External booking links={external_booking[:3]}', action='Inspect the booking journey without making an appointment.'))
        if not page.viewport:
            findings.append(finding('viewport', 'No device-width viewport declaration was found in this page’s HTML; mobile layout requires browser inspection.', page_url, 'Parsed meta tags; no rendered layout test.'))
        widths = re.findall(r'(?:min-width|width)\s*:\s*(\d{3,4})px', body, re.I)
        if any(int(w) > 480 for w in widths):
            findings.append(finding('mobile_width', 'Fixed or minimum widths above 480px appear in page source; responsive CSS may override them.', page_url,
                f'width values={sorted(set(widths))[:8]}', action='Check overflow and contact controls at a mobile viewport.'))
    if not any(p['forms'] or p['cta_links'] for p in pages):
        findings.append(finding('cta_missing', 'No contact calls to action or forms were identified in the inspected HTML; menus, images or JavaScript may provide them.', final,
            f'Inspected {len(pages)} page(s); source analysis only.', action='Inspect the rendered contact path on desktop and mobile.'))
    return AuditResult(final, merge_findings(findings), deduplicate(contacts),
                       {'pages': pages, 'link_checks': checks, 'browser_checked': False, 'source_text': ' '.join(home.text)[:100000],
                        'limitations': ['No forms submitted or appointment/quote requests made.', 'No rendered/mobile or form-delivery test.', 'External booking flows and query-string links require browser review.']})
