"""Serial, bounded discovery against independently operated public instances."""
import datetime as dt
from email.utils import parsedate_to_datetime
import json
import random
import time
import urllib.error
import urllib.parse

ENDPOINTS = (
    'https://overpass-api.de/api/interpreter',
    'https://overpass.private.coffee/api/interpreter',
)
ATTEMPTS = 3
MAX_WAIT = 120
RETRYABLE = {429, 500, 502, 503, 504}


class DiscoveryFailed(Exception):
    def __init__(self, attempts):
        super().__init__('Discovery unavailable; ledger preserved')
        self.attempts = attempts


def retry_after(value, now):
    """Return the server's minimum delay, accepting seconds or an HTTP date."""
    if not value:
        return 0
    try:
        return max(0, int(value))
    except ValueError:
        try:
            date = parsedate_to_datetime(value)
            if date.tzinfo is None:
                date = date.replace(tzinfo=dt.timezone.utc)
            return max(0, (date - now()).total_seconds())
        except (ValueError, TypeError, OverflowError):
            return 0


def validate(text):
    response = json.loads(text)
    if not isinstance(response, dict) or response.get('remark') or not isinstance(response.get('elements'), list):
        raise ValueError('Incomplete or invalid Overpass response')
    for c in response['elements']:
        if not isinstance(c, dict) or c.get('type') not in ('node', 'way', 'relation') or not isinstance(c.get('id'), int) or not isinstance(c.get('tags', {}), dict):
            raise ValueError('Invalid Overpass element')
    return response['elements']


def discover(query, getter, sleeper=time.sleep, jitter=lambda: random.uniform(0, 5),
             now=lambda: dt.datetime.now(dt.timezone.utc), endpoints=ENDPOINTS):
    attempts = []
    data = urllib.parse.urlencode({'data': query}).encode()
    for endpoint_index, endpoint in enumerate(endpoints):
        if endpoint_index:
            sleeper(30 + jitter())
        for attempt in range(1, ATTEMPTS + 1):
            record = {'endpoint': endpoint, 'attempt': attempt, 'at': now().isoformat()}
            server_wait = 0
            try:
                _, _, text = getter(endpoint, data=data, timeout=60)
                elements = validate(text)
                attempts.append(dict(record, outcome='success'))
                return elements, {'status': 'success', 'endpoint': endpoint, 'attempts': attempts}
            except urllib.error.HTTPError as e:
                reason = f'HTTP {e.code}'
                retryable = e.code in RETRYABLE
                server_wait = retry_after(e.headers.get('Retry-After') if e.headers else None, now)
                if e.fp is not None:
                    e.close()
            except (urllib.error.URLError, OSError) as e:
                reason = type(e).__name__
                retryable = True
            except (ValueError, TypeError):
                # HTTP 200 can still contain an Overpass timeout remark/HTML error.
                reason = 'invalid_or_incomplete_response'
                retryable = True
            record.update(outcome='failure', reason=reason)
            attempts.append(record)
            if not retryable:
                # A bad query/auth failure should not be sprayed at other services.
                raise DiscoveryFailed(attempts)
            if attempt == ATTEMPTS or server_wait > MAX_WAIT:
                if server_wait > MAX_WAIT:
                    record['retry_after_exceeds_wait_limit'] = True
                break
            delay = max(30 * 2 ** (attempt - 1), server_wait) + jitter()
            record['backoff_seconds'] = delay
            sleeper(delay)
    raise DiscoveryFailed(attempts)
