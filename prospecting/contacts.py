"""Normalize explicit contacts without guessing identities or destinations."""
import hashlib
import re
import urllib.parse


def canonical(kind, value):
    value = urllib.parse.unquote(str(value)).strip()
    if any(c in value for c in '\r\n\x00'):
        return None
    if kind == 'email':
        value = value.split('?', 1)[0].strip().casefold()
        return value if re.fullmatch(r'[^\s@,;]+@[^\s@,;]+\.[^\s@,;]+', value) else None
    if kind == 'phone':
        base = re.split(r'(?:ext\.?|extension|\bx\b|;ext=)', value, flags=re.I)[0]
        digits = re.sub(r'\D', '', base)
        if len(digits) == 11 and digits.startswith('1'):
            digits = digits[1:]
        return digits if len(digits) == 10 else None
    return None


def deduplicate(contacts):
    found = {}
    for c in contacts:
        key = canonical(c.get('kind'), c.get('value', ''))
        if not key:
            continue
        identity = (c['kind'], key)
        if identity not in found:
            found[identity] = dict(c, normalized=key, sources=[])
        sources = found[identity]['sources']
        for source in [c.get('source')] + c.get('sources', []):
            if source and source not in sources:
                sources.append(source)
    return list(found.values())


def hashes(contacts):
    return [hashlib.sha256((c['kind'] + ':' + c['normalized']).encode()).hexdigest()
            for c in deduplicate(contacts)]
