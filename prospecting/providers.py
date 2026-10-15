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


def valid_candidates(rows, allow_empty=False):
    return (isinstance(rows, list) and (bool(rows) or allow_empty) and len(rows) <= 5000 and all(
        isinstance(c, dict) and c.get('provider') and c.get('id') and
        isinstance(c.get('tags'), dict) and isinstance(c['tags'].get('name'), str) and
        isinstance((c.get('center') or c).get('lat'), (float, int)) and
        isinstance((c.get('center') or c).get('lon'), (float, int))
        for c in rows))


def overture_provider(region=None):
    # A subprocess bounds all network/native reader activity, including DNS and retries.
    with tempfile.TemporaryDirectory() as root:
        output = Path(root) / 'places.json'
        command = [sys.executable, str(Path(__file__).with_name('overture.py')), str(output)]
        if region is not None:
            command.append(json.dumps(region))
        result = subprocess.run(command,
                                timeout=180, capture_output=True, text=True)
        if result.returncode:
            details = json.loads(output.read_text()).get('error', {}) if output.exists() else {}
            raise RuntimeError('Overture extraction: ' + details.get('type', 'worker_failed') + ': ' + details.get('message', 'No worker diagnostic'))
        payload = json.loads(output.read_text())
        return payload['candidates'], {'release': payload['release']}


def cached_pool(path, max_days, now, region=None):
    try:
        pool = json.loads(path.read_text())
        age = (now - dt.datetime.fromisoformat(pool['fetched_at'])).total_seconds()
        if pool['schema'] != SCHEMA or not (0 <= age <= max_days * 86400):
            return None
        if region is not None and pool.get('region') != region:
            return None
        rows = pool['candidates']
        if not valid_candidates(rows, allow_empty=region is not None):
            return None
        return rows, {'source': 'saved_pool', 'age_days': round(age / 86400, 2), 'fetched_at': pool['fetched_at']}
    except (OSError, ValueError, KeyError, TypeError):
        return None


def discover_businesses(query, getter, pool_path, providers=None, now=None, region=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    cached = cached_pool(pool_path, 7, now, region)
    if cached:
        return cached[0], {'status': 'success', **cached[1], 'attempts': []}, None
    if providers is None:
        providers = [('overture', lambda: overture_provider(region))]
    attempts = []
    for name, provider in providers:
        try:
            rows, metadata = provider()
            if not valid_candidates(rows, allow_empty=region is not None):
                raise ValueError('No candidates returned')
            attempts.append({'provider': name, 'outcome': 'success', 'count': len(rows), **metadata})
            pool = {'schema': SCHEMA, 'fetched_at': now.isoformat(), 'candidates': rows, **({'region': region} if region else {})}
            return rows, {'status': 'success', 'source': name, 'attempts': attempts}, pool
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError, ImportError, KeyError, TypeError) as e:
            attempts.append({'provider': name, 'outcome': 'failure', 'reason': type(e).__name__, 'detail': str(e)[:1000]})
    cached = cached_pool(pool_path, 45, now, region)
    if cached:
        attempts.append({'provider': 'saved_pool', 'outcome': 'success', **cached[1]})
        return cached[0], {'status': 'degraded', **cached[1], 'attempts': attempts}, None
    try:
        if region is not None:
            if __package__:
                from .geography import overpass_query, osm_geography
            else:
                from geography import overpass_query, osm_geography
            query = overpass_query(region)
        rows, metadata = discover(query, getter)
        if region is not None:
            rows = [r for c in rows if (r := osm_geography(c, region)) is not None]
        rows = [dict(c, provider='osm') for c in rows]
        attempts.append({'provider': 'overpass', 'outcome': 'success', **metadata})
        pool = {'schema': SCHEMA, 'fetched_at': now.isoformat(), 'candidates': rows, **({'region': region} if region else {})} if rows or region is not None else None
        return rows, {'status': 'success', 'source': 'overpass', 'attempts': attempts}, pool
    except DiscoveryFailed as e:
        attempts.append({'provider': 'overpass', 'outcome': 'failure', 'attempts': e.attempts})
        raise DiscoveryFailed(attempts) from e
