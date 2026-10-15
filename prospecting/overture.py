"""Read only intersecting Overture GeoParquet files, anonymously via S3."""
import io
import json
from pathlib import Path
import re
import sys
import urllib.request

TRADES = {'plumbing': 'plumber', 'roofing': 'roofer', 'hvac_service': 'hvac',
          'electrician': 'electrician', 'landscaping': 'landscaper',
          'carpenter': 'carpenter', 'painting': 'painter'}
BBOX = (-90.75, 38.4, -89.95, 38.95)
CREDIT = 'Overture Maps Foundation; source licenses retained per record. https://docs.overturemaps.org/attribution/'


def normalize(row, release):
    category = (row.get('taxonomy') or {}).get('primary')
    trade = TRADES.get(category)
    box = row.get('bbox') or {}
    lon, lat = box.get('xmin'), box.get('ymin')
    name = (row.get('names') or {}).get('primary')
    sites = row.get('websites') or []
    if not trade or not name or not sites or row.get('operating_status') in ('permanently_closed', 'temporarily_closed'):
        return None
    if not isinstance(lat, (float, int)) or not isinstance(lon, (float, int)) or not (38.4 <= lat <= 38.95 and -90.75 <= lon <= -89.95):
        return None
    if not isinstance(row.get('confidence'), (float, int)) or row['confidence'] < .8 or not row.get('id'):
        return None
    source = f'https://explore.overturemaps.org/?id={row["id"]}'
    contacts = [{'kind': kind, 'value': value, 'source': source}
                for kind, field in (('phone', 'phones'), ('email', 'emails'))
                for value in row.get(field) or [] if isinstance(value, str) and value.strip()]
    result = {'provider': 'overture', 'type': 'place', 'id': row['id'],
            'lat': lat, 'lon': lon, 'source': source,
            'tags': {'name': name, 'website': sites[0], 'craft': trade},
            'contacts': contacts, 'provenance': {'release': release, 'category': category,
            'confidence': row['confidence'], 'brand': row.get('brand'), 'sources': row.get('sources') or [], 'attribution': CREDIT}}
    if __package__:
        from .fit import business_fit
    else:
        from fit import business_fit
    return result if business_fit(result)['eligible'] else None


def read_json(url):
    with urllib.request.urlopen(url, timeout=20) as r:
        return json.loads(r.read(1_000_000))


def load():
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
        if b['xmin'] <= BBOX[2] and b['xmax'] >= BBOX[0] and b['ymin'] <= BBOX[3] and b['ymax'] >= BBOX[1]:
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
    filt = ((pc.field('bbox', 'xmin') >= BBOX[0]) & (pc.field('bbox', 'xmin') <= BBOX[2]) &
            (pc.field('bbox', 'ymin') >= BBOX[1]) & (pc.field('bbox', 'ymin') <= BBOX[3]) &
            pc.field('taxonomy', 'primary').isin(list(TRADES)) & (pc.field('confidence') >= .8))
    columns = ['id', 'names', 'bbox', 'websites', 'emails', 'phones', 'taxonomy', 'confidence', 'sources', 'operating_status']
    if 'brand' in dataset.schema.names:
        columns.append('brand')
    candidates = []
    # Disable speculative parallel reads; predicate/projection pushdown avoids planet downloads.
    for batch in dataset.to_batches(filter=filt, columns=columns, batch_size=2048,
                                    batch_readahead=0, fragment_readahead=0, use_threads=False):
        for row in batch.to_pylist():
            candidate = normalize(row, release)
            if candidate:
                candidates.append(candidate)
            if len(candidates) >= 5000:
                return candidates, release
    return candidates, release


if __name__ == '__main__':
    try:
        candidates, release = load()
        result = {'candidates': candidates, 'release': release}
    except Exception as e:
        # Anonymous/public-data reader: retain bounded error details for actionable diagnostics.
        Path(sys.argv[1]).write_text(json.dumps({'error': {'type': type(e).__name__, 'message': str(e)[:1000]}}))
        sys.exit(1)
    Path(sys.argv[1]).write_text(json.dumps(result))
