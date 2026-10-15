# Discovery investigation and validation

These are historical discovery validation results. The current conversion-quality policy in `README.md` is stricter: earlier HTTP/viewport-only leads are not automatically reclassified as verified conversion prospects. Existing historical reports remain unchanged.

## Actual failure at commit 63a8b26

Downloaded the diagnostic artifact and inspected failed step logs for [Daily prospect review run 38678044393](https://github.com/zfouse/fouse-digital/actions/runs/38678044393). The primary `overpass-api.de` returned HTTP 504 three times. The fallback `overpass.private.coffee` returned HTTP 500 on its first attempt, which the earlier retry policy treated as permanent. The process exited 2. Its diagnostic upload worked and the ledger was preserved. This was a provider availability failure, not evidence that no businesses exist. Retrying more Overpass hosts alone would retain the same architectural dependency.

## Alternatives evaluated

| Source | Automated access / cost | Decision |
|---|---|---|
| [Overture Places](https://docs.overturemaps.org/guides/places/) | Official anonymous cloud files and STAC index; designed for programmatic area extraction; open source-level licenses; no account | New primary. Names, websites, coordinates, category, phones/emails and provenance support the existing qualification pipeline. Public object storage avoids Overpass query capacity. |
| Saved local regional pool | Reuse previously retrieved, sourced public records; no network cost | Seven-day normal reuse, 45-day explicit degraded fallback. Re-audit websites and retain original record age. |
| Overpass / OSM | Free public instances, shared query resources; ODbL | Retain as secondary provider with bounded retries including HTTP 500. |
| [City of St. Louis business-license FeatureServer](https://maps8.stlouis-mo.gov/arcgis/rest/services/SLDC/Business_License_2024/FeatureServer/0) | Public query API and useful name/phone/email fields | Evaluated schema directly. No website field, city-only coverage and a 2024 dataset. Not enabled because identifying a website would require additional verified matching. Never invent websites from business names. |
| [Public Nominatim](https://operations.osmfoundation.org/policies/nominatim/) | Policy prohibits systematic POI extraction | Not used for prospect discovery. |
| Commercial map/directory APIs or arbitrary directory scraping | Typically require keys/accounts, billing, or service-specific permission | Not introduced. The two open sources and pool meet this phase without new accounts or credentials. |

Overture's official Python client's current STAC parser expected an older `aws-s3` asset key and fell back to a broad listing in our evaluation. The production adapter instead reads the small official STAC index directly, supports current `aws` and older `aws-s3` keys, explicitly bounds intersecting shards and never silently scans the global dataset. It uses pinned Apache Arrow with anonymous S3 range reads and column/geography/trade filtering.

## Live local results

Using release `2026-09-23.1`, the initial live Overture extraction returned **1,107 real named service-business candidates with websites** inside the configured area (before adding the exact `painting` category mapping). These were discovery candidates, not assumed qualified leads. No fixture or hand-entered business list was used.

The full CLI then independently fetched Overture data, performed live robots/homepage audits, and produced **10 qualified leads and 10 personalized drafts**, shortfall zero. Nine website errors were skipped rather than turned into findings. Examples include AA Quick Plumbing, Roof STL and Gravity Drain Services; each report retains the actual source website and narrowly worded HTML observation. These are observations, not endorsements or verified revenue opportunities. The local live run used isolated state and sent nothing or changed any production ledger.

The subsequent exact painting mapping expands discovery; counts will differ by release/filter changes. All live counts are observed validation results, not a guarantee of sustained daily yield. Source listings and contact details can be stale. HTTP/source viewport checks still require human review before any outreach.

## Automated checks

29 automated tests pass locally, including a real local-Parquet integration test through the production reader, full provider-to-audit-to-draft integration, cache fallback/expiry and existing ledger compatibility. CI installs the same pinned reader and runs these checks on Python 3.12. Optional manual GitHub-hosted live validation uses isolated state and no write permission; see the PR for its result. Production scheduling and ledger writes are exercised only after merge.

## GitHub-hosted live verification

[Read-only validation run 38680199414](https://github.com/zfouse/fouse-digital/actions/runs/38680199414) passed on the PR branch. Its live job completed in **2 minutes 19 seconds**. The downloaded artifact confirms the Overture provider discovered **1,207 candidates** after adding the exact painting category, using release `2026-09-23.1`; **10 qualified leads and 10 drafts** were produced, shortfall zero, with **16 website errors skipped**. No Overpass fallback was required. The scratch ledger/pool were never pushed to production. The validated provider/audit code is unchanged by the subsequent report-health and license-notice additions, which pass the same automated integration suite. Daily production branch persistence remains a post-merge operation.


## Conversion-quality validation

The stricter conversion audit was run live against 150 records from the existing saved discovery pool using isolated scratch state. It found **one verified qualified prospect** and retained ten potential-only records in the browser-inspection queue. West County Gardens’ “Get in Touch” destination returned HTTP 404 on two checks; the draft uses that specific observation. HTTP/viewport-only observations did not fill the remaining daily slots. This is a sampled result, not a promise of ten confirmed conversion defects every day. No forms, quote requests, bookings or outreach were submitted and no production ledger was changed.

45 automated tests pass, including GET-only local HTTP integration, verified/potential separation, normalized contacts, ranking/selection and append-only historical report preservation. Dashboard browser QA at 1440px and 390px passed: business search, copy/fallback, no horizontal overflow and no console errors. Browser QA of the dashboard is separate from the source-only audits of business websites.
