"""Transparent review priorities, not estimated revenue or conversion probabilities."""


def verified(findings):
    return [f for f in findings if f.get('status') == 'verified' and f.get('impact', 0) > 0]


def rank(findings, contacts, category):
    confirmed = verified(findings)
    impact = max((f['impact'] for f in confirmed), default=0)
    strength = max((f.get('evidence_strength', 0) for f in confirmed), default=0)
    fit = (15 if category in ('plumber', 'roofer', 'hvac', 'electrician', 'landscaper', 'painter', 'carpenter') else 0) + (5 if any(c['kind'] == 'email' for c in contacts) else 0)
    total = impact + strength + fit if confirmed else 0
    return {'score': total, 'impact': impact, 'evidence_strength': strength, 'fit': fit,
            'priority': 'High' if total >= 85 else 'Medium' if total >= 65 else 'Browser review',
            'reason': f'Observed customer contact-path impact {impact}/50; evidence {strength}/30; service/contact fit {fit}/20. Potential findings add no points.',
            'limitations': 'Relative priority among audited prospects, not predicted lost leads or revenue.'}


def draft(name, finding, category='service'):
    if finding.get('status') != 'verified':
        return None
    label = finding.get('label', 'contact')
    if finding['code'] == 'broken_cta':
        offer = f'I can help repair the “{label}” link and check the route from your homepage to the inquiry page.'
    elif finding['code'] == 'empty_contact_link':
        offer = 'I can help connect that button to the correct business contact and check the path on a phone.'
    else:
        return None
    service = {'plumber': 'plumbing', 'roofer': 'roofing', 'hvac': 'heating and cooling', 'electrician': 'electrical', 'landscaper': 'landscaping', 'painter': 'painting', 'carpenter': 'carpentry'}.get(category, category)
    return {'subject': f'{name}: your {label[:55]} link',
            'body': f'Hi {name} team,\n\nI’m Zach with Fouse Digital. While reviewing your {service} website at {finding["url"]}, I found a specific contact-path issue: {finding["observation"]}\n\n{offer} Would you like me to send a short lead-path review showing the link and suggested fix?\n\nZach\nFouse Digital\nhttps://zfouse.github.io/fouse-digital/',
            'finding_code': finding['code'], 'evidence_url': finding['url'],
            'status': 'draft — human review required; never sent'}
