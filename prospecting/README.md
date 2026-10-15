# Daily prospect review

The existing static GitHub Pages website and customer email form are unchanged. Research runs in GitHub Actions, targets **10 qualified St. Louis-area service businesses per Chicago calendar day**, and prepares email drafts only. There is no sending, form submission, SMTP integration, paid query service, new account or API key.

## Discovery strategy

`providers.py` orchestrates independently replaceable providers. Each returns candidate dictionaries and diagnostic metadata. A candidate carries provider/stable ID, coordinates, name, trade, website, sourced contacts and provenance. Add another `(name, callable)` to the provider list; the common audit and ledger paths do not need provider-specific changes.

1. **Recent saved pool:** reuse `pool.json` for seven days, avoiding unnecessary daily data downloads.
2. **Overture Places:** read the latest release from the public STAC catalog. Select only regional GeoParquet shards, project needed fields and filter coordinates, trade and confidence through Apache Arrow. Access is anonymous S3, not an Overpass query. Extraction has a 180-second subprocess deadline and per-request/connect limits. There is no full-planet download, paid SQL service or credential discovery. The STAC index is capped at 5 MB, intersecting files at eight, candidates at 5,000. Current regional query intersects one shard; projected range reads avoid downloading that whole file.
3. **Outage pool:** if refresh fails, reuse a saved pool up to 45 days old, explicitly reporting `discovery.status=degraded` and its original age. A cached listing is a discovery hint; its website is audited again before any draft is generated. Cache reads never reset its age.
4. **Overpass:** only when there is no usable pool and Overture fails, use the existing bounded serial Overpass failover. It now also retries HTTP 500, which caused the fallback failure in the latest live run. Maximum three requests per endpoint, exponential backoff/jitter and Retry-After handling remain in place. Permanent query/auth errors stop that provider. No unlimited retries.

Provider failure never becomes an invented business or a website issue. If all providers fail and the pool is unavailable/expired, the command exits 2, writes separate HTML/JSON diagnostics, and leaves the ledger, pool and prior reports intact. Actions uploads the diagnostic artifact and preserves a failed workflow status. A healthy empty Overpass result is an honest shortfall, not fabricated leads.

`ledger.json` and the pool persist on the existing `prospect-ledger` branch, separately from Pages. Pool changes and ledger changes are pushed in the same commit after report upload succeeds. The ledger retains all existing hashes/counts; OSM keys keep their old format. Provider IDs plus normalized domains and phone numbers deduplicate both within and across providers. Shared domains/phones intentionally suppress additional branches. Writes use temporary files and atomic replacement. Discovery cache never marks a lead as researched.

## Qualification, contacts and truthful audits

A lead needs a named service trade, website, location inside latitude 38.40–38.95 / longitude -90.75–-89.95, public contact information and an observed homepage issue. Overture maps exact taxonomy categories for plumbing, HVAC, electrical, roofing, landscaping, carpentry and painting; confidence must be at least 0.8 and known closed records are excluded. Retail suppliers and unrelated categories are excluded. Coordinates are listing locations, not a claimed service radius.

Contacts are copied from explicit public dataset fields or homepage `mailto:`/`tel:` links and retain their source URLs. The release, original source records, licenses and confidence accompany Overture leads. No guessed email addresses, inferred phone numbers, fabricated contacts or promised deliverability. Directory data can be stale; review source evidence before outreach.

Website audits respect robots rules (unknown robots errors cause a skip; 404 allows inspection), URL safety checks, response-size caps and a one-second pause per audit. Only two source-level observations qualify: the fetched homepage still uses HTTP, or its HTML lacks a `width=device-width` viewport declaration. These are not claims that HTTPS is unavailable or that a site is broken on mobile. JavaScript-rendered metadata and form delivery are not tested. No lost-revenue, speed, broken-form or conversion claims are invented. Review observations in a browser before using a draft.

Reports include the exact observation, evidence URL, timestamp, contacts and personalized draft. They never send. The daily cap remains 10 including reruns. At most 150 unseen websites and ten minutes of audit work are attempted per run; errors are skipped. Candidates rotate deterministically each day so unsuccessful entries cannot permanently block the rest of the pool. Discovery success does not guarantee ten qualified leads; shortfalls remain visible.

## Review and operation

After merge, **Daily prospect review** runs at 13:23 UTC daily (8:23 a.m. Chicago daylight time / 7:23 a.m. standard time). GitHub can delay scheduled runs. No setup secrets are required. Repository rules must permit Actions to update `prospect-ledger`; GitHub lookup failures stop rather than treating the ledger as missing.

Open the completed run, download `prospect-review-<run ID>`, and open `review.html`. `review.json` contains the same data. Failures provide `diagnostic.html/json`. Reports expire after 30 days; download anything you want to retain. Pool/ledger persist independently. Do not delete `prospect-ledger` to fix a transient API outage.

**Visibility:** the repository is public. The pool branch now includes public discovery listings, contacts and provenance, in addition to hashed deduplication data. GitHub Actions reports and drafts should also be treated as accessible, not private. Do not add private customer data or notes. This is not an authenticated CRM or permanent draft archive.

`Prospecting tests` supports an optional manual **read-only live validation** run on a selected branch. It uses isolated scratch state, writes only report artifacts (seven-day retention), and never pushes production ledger/pool changes. This lets a PR be tested on a GitHub-hosted runner before merging.

## Setup, cost and tests

```sh
python3 -m pip install -r prospecting/requirements.txt
python3 -m unittest discover -s tests -v
python3 prospecting/run.py --state /path/to/ledger.json --output /path/to/reports
```

CI uses Python 3.12. Apache Arrow is pinned in `requirements.txt`; the rest uses the standard library. `--candidates /path/to/osm.json` remains available for OSM-format fixtures, but still audits websites. Unit/integration tests use fixtures and local Parquet files, not public endpoints. Tests cover schema normalization, geography/trades/closed-record filtering, source/contact preservation, actual Parquet projection/filtering, provider continuation, subprocess limits, cache freshness/expiration, degraded outage recovery, cross-provider legacy deduplication, report/draft generation, ledger preservation, retries and workflow ledger loading.

Designed for $0 incremental cost: standard public-repository Linux Actions runners, anonymous public datasets, no model calls or paid APIs. Normal days use the saved pool; refresh is weekly. Small reports expire automatically. Account-level artifact storage allowances still apply; no billing settings are changed. Sources remain best-effort, and release schema changes may require maintenance.

See [GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions), [Overture access](https://docs.overturemaps.org/getting-data/cloud-sources/), [Places guide](https://docs.overturemaps.org/guides/places/), and [source evaluation and live results](DISCOVERY-NOTES.md).

Reports retain OpenStreetMap attribution where applicable (ODbL) and Overture source-level licenses. Overture Places is published under CDLA Permissive 2.0 / Apache 2.0 depending on source; preserve its source notices when redistributing. [Overture attribution and licensing](https://docs.overturemaps.org/attribution/), [OpenStreetMap copyright](https://www.openstreetmap.org/copyright).
