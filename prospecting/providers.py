"""Provider orchestration. Providers return candidates plus diagnostic metadata."""
import datetime as dt
import json
from pathlib import Path
import subprocess
import sys
import tempfile

if __package__:
    from .discovery import DiscoveryFailed, discover
else:
    from discovery import DiscoveryFailed, discover

SCHEMA = 1


def valid_candidates(rows):
    return (isinstance(rows, list) and bool(rows) and len(rows) <= 5000 and all(
        isinstance(c, dict) and c.get('provider') and c.get('id') and
        isinstance(c.get('tags'), dict) and isinstance(c['tags'].get('name'), str) and
        isinstance((c.get('center') or c).get('lat'), (float, int)) and
        isinstance((c.get('center') or c).get('lon'), (float, int))
        for c in rows))


def overture_provider():
    # A subprocess bounds all network/native reader activity, including DNS and retries.
    with tempfile.TemporaryDirectory() as root:
        output = Path(root) / 'places.json'
        result = subprocess.run([sys.executable, str(Path(__file__).with_name('overture.py')), str(output)],
                                timeout=180, capture_output=True, text=True)
        if result.returncode:
            details = json.loads(output.read_text()).get('error', {}) if output.exists() else {}
            raise RuntimeError('Overture extraction: ' + details.get('type', 'worker_failed') + ': ' + details.get('message', 'No worker diagnostic'))
        payload = json.loads(output.read_text())
        return payload['candidates'], {'release': payload['release']}


def cached_pool(path, max_days, now):
    try:
        pool = json.loads(path.read_text())
        age = (now - dt.datetime.fromisoformat(pool['fetched_at'])).total_seconds()
        if pool['schema'] != SCHEMA or not (0 <= age <= max_days * 86400):
            return None
        rows = pool['candidates']
        if not valid_candidates(rows):
            return None
        return rows, {'source': 'saved_pool', 'age_days': round(age / 86400, 2), 'fetched_at': pool['fetched_at']}
    except (OSError, ValueError, KeyError, TypeError):
        return None


def discover_businesses(query, getter, pool_path, providers=None, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    cached = cached_pool(pool_path, 7, now)
    if cached:
        return cached[0], {'status': 'success', **cached[1], 'attempts': []}, None
    if providers is None:
        providers = [('overture', overture_provider)]
    attempts = []
    for name, provider in providers:
        try:
            rows, metadata = provider()
            if not valid_candidates(rows):
                raise ValueError('No candidates returned')
            attempts.append({'provider': name, 'outcome': 'success', 'count': len(rows), **metadata})
            pool = {'schema': SCHEMA, 'fetched_at': now.isoformat(), 'candidates': rows}
            return rows, {'status': 'success', 'source': name, 'attempts': attempts}, pool
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError, ImportError) as e:
            attempts.append({'provider': name, 'outcome': 'failure', 'reason': type(e).__name__, 'detail': str(e)[:1000]})
    cached = cached_pool(pool_path, 45, now)
    if cached:
        attempts.append({'provider': 'saved_pool', 'outcome': 'success', **cached[1]})
        return cached[0], {'status': 'degraded', **cached[1], 'attempts': attempts}, None
    try:
        rows, metadata = discover(query, getter)
        rows = [dict(c, provider='osm') for c in rows]
        attempts.append({'provider': 'overpass', 'outcome': 'success', **metadata})
        pool = {'schema': SCHEMA, 'fetched_at': now.isoformat(), 'candidates': rows} if rows else None
        return rows, {'status': 'success', 'source': 'overpass', 'attempts': attempts}, pool
    except DiscoveryFailed as e:
        attempts.append({'provider': 'overpass', 'outcome': 'failure', 'attempts': e.attempts})
        raise DiscoveryFailed(attempts) from e
