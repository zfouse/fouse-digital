"""Append-only report snapshots; never rewrite or prune previous reports."""
import datetime as dt
from pathlib import Path
import shutil
import uuid


def snapshot(output, ledger_dir=None):
    key = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '-' + uuid.uuid4().hex[:8]
    destinations = [Path(output) / 'history']
    if ledger_dir is not None:
        destinations.append(Path(ledger_dir) / 'history')
    for directory in set(destinations):
        directory.mkdir(parents=True, exist_ok=True)
        for extension in ('json', 'html'):
            source = Path(output) / ('review.' + extension)
            if source.exists():
                # UUID/timestamp name and exclusive creation protect old bytes even on reruns.
                with (directory / (key + '.' + extension)).open('xb') as out:
                    out.write(source.read_bytes())
    return key
