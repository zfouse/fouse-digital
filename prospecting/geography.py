"""Offline geographic configuration; only explicitly sourced U.S. addresses qualify."""
import hashlib
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo

STATES = json.loads(Path(__file__).with_name('us-states.json').read_text())['states']
ZONES = {**dict.fromkeys('AK'.split(), 'America/Anchorage'), **dict.fromkeys('HI'.split(), 'Pacific/Honolulu'), **dict.fromkeys('CA NV WA OR'.split(), 'America/Los_Angeles'), **dict.fromkeys('AZ'.split(), 'America/Phoenix'), **dict.fromkeys('CO UT NM WY MT ID'.split(), 'America/Denver'), **dict.fromkeys('CT DE FL GA IN KY MA MD ME MI NC NH NJ NY OH PA RI SC VA VT WV DC'.split(), 'America/New_York')}
DEFAULT_CONFIG = Path(__file__).with_name('targeting.json')


def load_config(path=DEFAULT_CONFIG):
    config = json.loads(Path(path).read_text())
    country = config['countries'][config['country']]
    if config['country'] != 'US' or not country['enabled']:
        raise ValueError('International discovery is disabled pending policy and language review')
    ZoneInfo(config['ledger_timezone'])
    for key, maximum in [('screened', 1000), ('qualified', 50), ('browser_checks', 100), ('static_seconds', 1800), ('total_seconds', 2100)]:
        value = config['limits'][key]
        if type(value) is not int or not 1 <= value <= maximum:
            raise ValueError('Invalid bounded limit: ' + key)
    # A checked-in profile cannot silently activate unbenchmarked bulk research.
    if config['limits']['screened'] > 100 or config['limits']['qualified'] > 10 or config['limits']['browser_checks'] > 12:
        raise ValueError('Larger targets require a reviewed capacity benchmark and explicit code/config change')
    states = config['targeting'].get('states', []) or list(STATES)
    if not states or any(s not in STATES for s in states):
        raise ValueError('Unknown U.S. state')
    for region in config['targeting'].get('regions', []):
        validate_region(region)
    return config


def validate_region(region):
    box = region['bbox']
    if (region.get('country') != 'US' or len(box) != 4 or
        not all(isinstance(x, (int, float)) and math.isfinite(x) for x in box) or
        not (-180 <= box[0] < box[2] <= 180 and -90 <= box[1] < box[3] <= 90) or
        box[2]-box[0] > 2 or box[3]-box[1] > 2 or
        not region.get('states') or any(s not in STATES for s in region['states']) or
        region.get('kind') not in ('city', 'metro', 'state')):
        raise ValueError('Invalid bounded U.S. geographic target')
    ZoneInfo(region['timezone'])
    if not region.get('id') or not region.get('name') or region.get('language') != 'en':
        raise ValueError('Target needs a stable ID, name and supported draft language en')
    if not isinstance(region.get('localities', []), list) or any(not isinstance(v, str) for v in region.get('localities', [])):
        raise ValueError('Localities must be a list of source address names')


def fingerprint(region):
    # Includes filters, so two regions sharing a box cannot share incompatible caches.
    return hashlib.sha256(json.dumps(region, sort_keys=True).encode()).hexdigest()[:24]


# Search anchors are approximate metro centers, not legal boundaries or business locations.
# Country/state inclusion always comes from provider addresses.
ANCHORS = dict(zip('AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY'.split(),
    [(-86.80,33.52),(-149.90,61.22),(-112.07,33.45),(-92.29,34.75),(-118.24,34.05),(-104.99,39.74),(-72.68,41.76),(-75.55,39.74),(-77.04,38.91),(-80.19,25.76),(-84.39,33.75),(-157.86,21.31),(-116.20,43.62),(-87.63,41.88),(-86.16,39.77),(-93.62,41.59),(-97.34,37.69),(-85.76,38.25),(-90.07,29.95),(-70.26,43.66),(-76.61,39.29),(-71.06,42.36),(-83.05,42.33),(-93.27,44.98),(-90.18,32.30),(-94.58,39.10),(-108.50,45.78),(-95.94,41.26),(-115.14,36.17),(-71.46,42.99),(-74.17,40.74),(-106.65,35.08),(-74.01,40.71),(-80.84,35.23),(-96.79,46.88),(-82.99,39.96),(-97.52,35.47),(-122.68,45.52),(-75.17,39.95),(-71.41,41.82),(-80.84,34.00),(-96.73,43.55),(-86.78,36.16),(-95.37,29.76),(-111.89,40.76),(-73.21,44.48),(-77.44,37.54),(-122.33,47.61),(-81.63,38.35),(-87.91,43.04),(-104.82,41.14)]))


def tiles(state):
    boxes = [STATES[state]['bbox']]
    if state == 'AK':
        boxes = [[-180, 51, -130, 72], [172, 51, 180, 54]]
    result = []
    for west, south, east, north in boxes:
        # Stable, bounded two-degree tiles; real address region/country filters exclude neighbors.
        for y in range(math.floor(south), math.ceil(north), 2):
            for x in range(math.floor(west), math.ceil(east), 2):
                result.append([x, y, min(x+2, east), min(y+2, north)])
    lon, lat = ANCHORS[state]
    anchor = [round(lon-.4, 4), round(lat-.3, 4), round(lon+.4, 4), round(lat+.3, 4)]
    return [anchor] + sorted(result, key=lambda b: ((b[0]+b[2])/2-lon)**2 + ((b[1]+b[3])/2-lat)**2)


def select_region(config, state):
    targeting = config['targeting']
    rotation = state.get('geo_rotation', {})
    regions = targeting.get('regions', [])
    if regions:
        region = dict(regions[rotation.get('cursor', 0) % len(regions)])
    else:
        states = targeting.get('states', []) or sorted(STATES)
        code = states[rotation.get('cursor', 0) % len(states)]
        grid = tiles(code)
        tile = rotation.get('tiles', {}).get(code, 0) % len(grid)
        region = {'id': f'{code}-{tile}', 'name': STATES[code]['name'], 'country': 'US',
                  'kind': 'state', 'states': [code], 'bbox': grid[tile],
                  'timezone': ZONES.get(code, 'America/Chicago'), 'language': 'en'}
    validate_region(region)
    return region


def advance(state, region, config):
    rotation = state.setdefault('geo_rotation', {})
    rotation['cursor'] = rotation.get('cursor', 0)+1
    if not config['targeting'].get('regions'):
        code = region['states'][0]
        counters = rotation.setdefault('tiles', {})
        counters[code] = counters.get(code, 0)+1
    rotation['last_completed'] = region


def matches(candidate, region):
    geo = candidate.get('geography', {})
    loc = candidate.get('center') or candidate
    west, south, east, north = region['bbox']
    return (geo.get('country') == 'US' and geo.get('state') in region['states'] and
            (not region.get('localities') or (geo.get('city') or '').casefold() in [x.casefold() for x in region['localities']]) and
            west <= loc.get('lon', -999) <= east and south <= loc.get('lat', -999) <= north)


def overpass_query(region):
    west, south, east, north = region['bbox']
    states = '|'.join(region['states'])  # validated against the offline state catalog
    return f'[out:json][timeout:45];nwr["craft"~"^(plumber|electrician|hvac|roofer|carpenter|painter|landscaper)$"]["name"]["addr:country"="US"]["addr:state"~"^({states})$"]({south},{west},{north},{east});out center tags;'


def osm_geography(candidate, region):
    tags = candidate.get('tags', {})
    result = dict(candidate, geography={'country': tags.get('addr:country'), 'state': tags.get('addr:state'),
                 'city': tags.get('addr:city'), 'source': f"https://www.openstreetmap.org/{candidate['type']}/{candidate['id']}",
                 'timezone': region['timezone'], 'language': region.get('language', 'en'), 'target_id': region['id']})
    return result if matches(result, region) else None
