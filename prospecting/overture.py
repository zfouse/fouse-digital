"""Read only intersecting Overture GeoParquet files, anonymously via S3."""
import io
import json
from pathlib import Path
import re
import sys
import urllib.request
from urllib.parse import urlsplit

TRADES = {'plumbing': 'plumber', 'roofing': 'roofer', 'hvac_service': 'hvac',
          'electrician': 'electrician', 'landscaping': 'landscaper',
          'carpenter': 'carpenter', 'painting': 'painter'}
CREDIT = 'Overture Maps Foundation; source licenses retained per record. https://docs.overturemaps.org/attribution/'


def website_choices(values):
    result=[]
    if not isinstance(values,(list,tuple)):return result
    for raw in values:
        if not isinstance(raw,str) or not raw.strip() or any(c.isspace() for c in raw.strip()):continue
        value=raw.strip()
        try:
            p=urlsplit(value if '://' in value else 'https://'+value)
            if p.scheme not in ('http','https') or not p.hostname or '.' not in p.hostname.strip('.') or p.username or p.password or p.port not in (None,80,443):continue
        except ValueError:continue
        result.append(value)
    return result


def normalize(row, release, region=None, diagnostics=None):
    def reject(reason):
        if diagnostics is not None:diagnostics[reason]=diagnostics.get(reason,0)+1
        return None
    category = (row.get('taxonomy') or {}).get('primary')
    trade = TRADES.get(category)
    box = row.get('bbox') or {}
    lon, lat = box.get('xmin'), box.get('ymin')
    name = (row.get('names') or {}).get('primary')
    sites = website_choices(row.get('websites'))
    if not trade or not name:return reject('missing_name_or_unsupported_trade')
    if not sites:return reject('missing_website')
    if row.get('operating_status') in ('permanently_closed','temporarily_closed'):return reject('not_operating')
    if not isinstance(lat, (float, int)) or not isinstance(lon, (float, int)) or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return reject('invalid_coordinates')
    if not isinstance(row.get('confidence'), (float, int)) or row['confidence'] < .8 or not row.get('id'):
        return reject('low_confidence_or_missing_id')
    source = f'https://explore.overturemaps.org/?id={row["id"]}'
    contacts = [{'kind': kind, 'value': value, 'source': source}
                for kind, field in (('phone', 'phones'), ('email', 'emails'))
                for value in row.get(field) or [] if isinstance(value, str) and value.strip()]
    result = {'provider': 'overture', 'type': 'place', 'id': row['id'],
            'lat': lat, 'lon': lon, 'source': source,
            'tags': {'name': name, 'website': sites[0], 'craft': trade},
            'contacts': contacts, 'provenance': {'release': release, 'category': category,
            'confidence': row['confidence'], 'brand': row.get('brand'), 'sources': row.get('sources') or [], 'attribution': CREDIT}}
    addresses = [a for a in row.get('addresses', []) or [] if a.get('country') == 'US']
    if region is not None:
        addresses = [a for a in addresses if a.get('region') in region['states'] and
                     (not region.get('localities') or (a.get('locality') or '').casefold() in [v.casefold() for v in region['localities']])]
        if not addresses:
            return reject('country_state_or_locality_unproven')
    if not addresses:
        return reject('country_unproven')
    address = addresses[0]
    result['geography'] = {'country': address.get('country'), 'state': address.get('region'),
                           'city': address.get('locality'), 'source': source}
    if region is not None:
        result['geography'].update(language=region.get('language', 'en'), timezone=region['timezone'], target_id=region['id'])
        if __package__:
            from .geography import matches
        else:
            from geography import matches
        if not matches(result, region):
            return reject('outside_target')
    if __package__:
        from .fit import business_fit
    else:
        from fit import business_fit
    fit=business_fit(result)
    if not fit['eligible']:return reject('commercial_fit_'+fit['ownership'])
    if diagnostics is not None:diagnostics['eligible_records']=diagnostics.get('eligible_records',0)+1
    return result


def read_json(url):
    with urllib.request.urlopen(url, timeout=20) as r:
        return json.loads(r.read(1_000_000))


def load(region=None, diagnostics=None):
    if region is None:
        if __package__:
            from .geography import load_config, select_region
        else:
            from geography import load_config, select_region
        region = select_region(load_config(), {})
    box = region['bbox']
    import pyarrow.compute as pc
    import pyarrow.dataset as ds
    import pyarrow.fs as fs
    import pyarrow.parquet as pq
    catalog = read_json('https://stac.overturemaps.org/catalog.json')
    release = catalog['latest']
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}\.\d+', release):
        raise ValueError('Invalid release')
    with urllib.request.urlopen(f'https://stac.overturemaps.org/{release}/collections.parquet', timeout=20) as r:
        raw = r.read(5_000_001)
    if len(raw) > 5_000_000:
        raise ValueError('Index too large')
    index = pq.read_table(io.BytesIO(raw)).to_pylist()
    paths = []
    for item in index:
        b = item.get('bbox') or {}
        if item.get('collection') != 'place' or item.get('type') != 'Feature':
            continue
        if b['xmin'] <= box[2] and b['xmax'] >= box[0] and b['ymin'] <= box[3] and b['ymax'] >= box[1]:
            assets = item['assets']
            asset = assets.get('aws') or assets.get('aws-s3')
            href = asset['href']
            prefix = 'https://overturemaps-us-west-2.s3.us-west-2.amazonaws.com/'
            if href.startswith(prefix):
                path = 'overturemaps-us-west-2/' + href[len(prefix):]
            elif href.startswith('s3://overturemaps-us-west-2/'):
                path = href[len('s3://'):]
            else:
                raise ValueError('Unrecognized Overture storage asset')
            paths.append(path)
    if not paths or len(paths) > 8:
        raise ValueError('No bounded set of regional shards')
    store = fs.S3FileSystem(anonymous=True, region='us-west-2', connect_timeout=10,
                            request_timeout=30, retry_strategy=fs.AwsStandardS3RetryStrategy(max_attempts=2))
    dataset = ds.dataset(paths, filesystem=store, format='parquet')
    filt = ((pc.field('bbox', 'xmin') >= box[0]) & (pc.field('bbox', 'xmin') <= box[2]) &
            (pc.field('bbox', 'ymin') >= box[1]) & (pc.field('bbox', 'ymin') <= box[3]) &
            pc.field('taxonomy', 'primary').isin([k for k,v in TRADES.items() if not region.get('industries') or v in region['industries']]) & (pc.field('confidence') >= .8))
    columns = ['id', 'names', 'bbox', 'websites', 'emails', 'phones', 'taxonomy', 'confidence', 'sources', 'operating_status']
    if 'addresses' not in dataset.schema.names:
        raise ValueError('Provider schema lacks required country/state address evidence')
    columns.append('addresses')
    if 'brand' in dataset.schema.names:
        columns.append('brand')
    candidates = []
    # Disable speculative parallel reads; predicate/projection pushdown avoids planet downloads.
    for batch in dataset.to_batches(filter=filt, columns=columns, batch_size=2048,
                                    batch_readahead=0, fragment_readahead=0, use_threads=False):
        for row in batch.to_pylist():
            candidate = normalize(row, release, region, diagnostics)
            if candidate:
                candidates.append(candidate)
            if len(candidates) >= 5000:
                return candidates, release
    return candidates, release


if __name__ == '__main__':
    try:
        region = json.loads(sys.argv[2]) if len(sys.argv) > 2 else None
        diagnostics={}
        candidates, release = load(region,diagnostics)
        result = {'candidates': candidates, 'release': release,'normalization':diagnostics}
    except Exception as e:
        # Anonymous/public-data reader: retain bounded error details for actionable diagnostics.
        Path(sys.argv[1]).write_text(json.dumps({'error': {'type': type(e).__name__, 'message': str(e)[:1000]}}))
        sys.exit(1)
    Path(sys.argv[1]).write_text(json.dumps(result))
