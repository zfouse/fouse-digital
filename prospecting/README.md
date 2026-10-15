# Daily prospect review

The existing static GitHub Pages website and customer email form are unchanged. Research runs in GitHub Actions, rotates nationwide across all 50 U.S. states and D.C., initially targeting **up to 100 screened candidates and 10 qualified service businesses per Chicago calendar day**, and prepares email drafts only. There is no sending, form submission, SMTP integration, paid query service, new account or API key.

## Discovery strategy

`providers.py` orchestrates independently replaceable providers. Each returns candidate dictionaries and diagnostic metadata. A candidate carries provider/stable ID, coordinates, name, trade, website, sourced contacts and provenance. Add another `(name, callable)` to the provider list; the common audit and ledger paths do not need provider-specific changes.

1. **Recent saved pool:** reuse the matching `pools/<geographic-fingerprint>.json` for seven days, avoiding unnecessary daily data downloads.
2. **Overture Places:** read the latest release from the public STAC catalog. Select only regional GeoParquet shards, project needed fields and filter coordinates, trade and confidence through Apache Arrow. Access is anonymous S3, not an Overpass query. Extraction has a 180-second subprocess deadline and per-request/connect limits. There is no full-planet download, paid SQL service or credential discovery. The STAC index is capped at 5 MB, intersecting files at eight, candidates at 5,000. The number of intersecting shards depends on the selected region; projected range reads avoid downloading that whole file.
3. **Outage pool:** if refresh fails, reuse a saved pool up to 45 days old, explicitly reporting `discovery.status=degraded` and its original age. A cached listing is a discovery hint; its website is audited again before any draft is generated. Cache reads never reset its age.
4. **Overpass:** only when there is no usable pool and Overture fails, use the existing bounded serial Overpass failover. It now also retries HTTP 500, which caused the fallback failure in the latest live run. Maximum three requests per endpoint, exponential backoff/jitter and Retry-After handling remain in place. Permanent query/auth errors stop that provider. No unlimited retries.

Provider failure never becomes an invented business or a website issue. If all providers fail and the pool is unavailable/expired, the command exits 2, writes separate HTML/JSON diagnostics, and leaves the ledger, pool and prior reports intact. Actions uploads the diagnostic artifact and preserves a failed workflow status. A healthy empty Overpass result is an honest shortfall, not fabricated leads.

`ledger.json` and regional pools persist on the existing `prospect-ledger` branch, separately from Pages. Pool changes and ledger changes are pushed in the same commit after report upload succeeds. The ledger retains all existing hashes/counts; OSM keys keep their old format. Provider IDs plus normalized domains and phone numbers deduplicate both within and across providers. Matching named identities are deduplicated globally; shared contacts alone do not erase distinct businesses. Writes use temporary files and atomic replacement. Discovery cache never marks a lead as researched.

## Qualification and conversion-path audits

Discovery reuses the existing providers with configurable U.S. geography; service-trade and evidence standards remain in place. A qualified outreach prospect now requires a public contact and a **verified actionable contact-path defect**. HTTP and viewport declarations alone do not qualify a business. This stricter standard can produce fewer than ten leads; the daily target remains ten without filling shortfalls with weak claims.

`conversion.py` inspects the homepage and at most two distinct same-origin contact, appointment, booking or quote destinations. It checks public HTML for inquiry forms, accessible field labels, native submit controls, form length, mixed-content form destinations, contact CTAs, booking links, empty phone/email destinations, missing anchor targets, viewport declarations and fixed-width hints. Search forms are excluded from inquiry-form warnings. External booking services, query-string destinations, destructive-looking URLs and JavaScript click handlers are not followed. Forms are never submitted, form action URLs are never probed, and no appointment or quote request is made.

Every finding has a status, evidence, URL, proposed action, impact and evidence-strength score. The October 15 browser rules below supersede source-only qualification:

- **Source evidence awaiting browser confirmation:** a contact/quote/booking CTA destination returns the same HTTP 404/410 on two GET checks; or an explicitly labeled phone/email link has an objectively empty destination. These alone no longer qualify. An actual browser contact-link click and matching failure are required, or repeatable rendered contact-control clipping. A failed URL check verifies the response at that time, not that all customers are blocked. Source-only link visibility and JavaScript interception are not proven. Inline JavaScript/explicitly hidden links are excluded from these checks.
- **Potential — browser inspection needed:** missing source labels/submit controls, long forms, HTTP form actions, missing fragment targets, external booking journeys, possible mobile width/viewport problems, missing source CTAs or destinations that time out/deny access. JavaScript, responsive CSS, accessible names or menus may resolve these observations in a browser. These do not generate drafts, qualify a lead, or add ranking points.

Network errors, rate limits and server 5xx responses never become verified broken links. Robots rules, URL safety checks, response-size limits and a one-second per-business pause remain. Each business has a 45-second check budget (a currently active request can finish afterward). The newer two-phase audit budget and limits are described under October 15 corrections below. Daily deterministic rotation prevents the same early records monopolizing research.

`quality.py` ranks eligible prospects **after** auditing the bounded sample, then selects the strongest available slots up to the existing daily cap. Current score components are displayed: contact-path impact /45, evidence strength /30, business fit /20 and actionable remediation /5. Repeated dead CTA responses have stronger evidence than an empty source URI. Known supported service trades and a public email improve fit; independence, budget and willingness to buy are unknown. Scores are relative review priorities, never revenue forecasts, conversion probabilities or claims of lost leads. Potential signals add zero points.

`contacts.py` deduplicates explicit email addresses (trim/case normalization) and North American phone numbers (country prefix, punctuation and extension normalization), merging all source URLs. It does not guess emails, strip email plus-addresses, or infer identities. Invalid contacts are excluded from outreach contact lists; an international phone is not labeled broken merely because it falls outside the local normalization rules. Canonical email/phone hashes supplement the existing provider/domain/phone ledger hashes. Existing ledger keys and daily counts are retained. Older ledger entries without email hashes cannot retrospectively reveal addresses that were never stored; existing domain/phone protection still applies.

Drafts contain the business name/trade, actual page/link wording, verified observation and a matching fix (repair the inquiry destination or connect the contact control). They never include unverified mobile/form-delivery claims, sales outcomes, generic HTTP pitches or messages for potential-only records. No AI API or sending functionality is introduced.

## Review dashboard and history

`review.html` is a standalone offline dashboard: highest-priority prospects first, component scores and rationale, source-linked findings with status badges, public contacts and merged provenance, page/form/CTA/booking coverage, and readable subject/message fields with a local copy button. Business-name filtering works locally. A separate expandable browser-inspection queue holds up to ten potential-only records with **no drafts** and no qualified ledger entries. Form delivery remains untested; bounded Chromium control/mobile observations are labeled per prospect. The dashboard itself works at desktop and mobile widths.

Historical reports are never edited to apply the new scoring policy. Before a local latest report is replaced, its exact bytes are copied to an append-only history snapshot. Every new successful report also gets a timestamp/UUID snapshot in both the output artifact and the existing ledger branch’s `history/` directory. The workflow commits history alongside the existing ledger/pool after upload succeeds. Prior ledger files, pool records and any existing history remain intact. Earlier Actions artifacts keep their existing retention; already expired artifacts cannot be recovered by this change. The new branch history persists beyond artifact expiration. All reports and histories remain public-access material; do not add private client notes.

## Review and operation

After merge, **Daily prospect review** runs at 13:23 UTC daily (8:23 a.m. Chicago daylight time / 7:23 a.m. standard time). GitHub can delay scheduled runs. No setup secrets are required. Repository rules must permit Actions to update `prospect-ledger`; GitHub lookup failures stop rather than treating the ledger as missing.

Open the completed run, download `prospect-review-<run ID>`, and open `review.html`. `review.json` contains the same data. Failures provide `diagnostic.html/json`. Actions artifacts expire after 30 days; new report snapshots also persist in the ledger branch history. Earlier artifacts remain unchanged. Do not delete `prospect-ledger` to fix a transient API outage.

**Visibility:** the repository is public. The pool branch now includes public discovery listings, contacts and provenance, in addition to hashed deduplication data. GitHub Actions reports and drafts should also be treated as accessible, not private. Do not add private customer data or notes. This is not an authenticated CRM or permanent draft archive.

`Prospecting tests` supports an optional manual **read-only live validation** run on a selected branch. It uses isolated scratch state, writes only report artifacts (seven-day retention), and never pushes production ledger/pool changes. This lets a PR be tested on a GitHub-hosted runner before merging.

## Setup, cost and tests

```sh
python3 -m pip install -r prospecting/requirements.txt
python3 -m unittest discover -s tests -v
python3 prospecting/run.py --state /path/to/ledger.json --output /path/to/reports
```

CI uses Python 3.12. Apache Arrow is pinned in `requirements.txt`; the rest uses the standard library. `--candidates /path/to/osm.json` remains available for OSM-format fixtures, but still audits websites. Unit/integration tests use fixtures, a local HTTP server and local Parquet files, not public endpoints. Tests cover schema normalization, geography/trades/closed-record filtering, source/contact preservation, actual Parquet projection/filtering, provider continuation, subprocess limits, cache freshness/expiration, degraded outage recovery, cross-provider legacy deduplication, report/draft generation, verified-versus-potential qualification, GET-only form/link safety, ranking and daily selection, normalized email/phone deduplication, history preservation, dashboard escaping, ledger preservation, retries and workflow ledger loading.

Designed for $0 incremental cost: standard public-repository Linux Actions runners, anonymous public datasets, no model calls or paid APIs. Each selected region has its own seven-day cache. Default state rotation usually visits a different region each day, so most days perform a fresh bounded regional read. Small reports expire automatically. Account-level artifact storage allowances still apply; no billing settings are changed. Sources remain best-effort, and release schema changes may require maintenance.

See [GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions), [Overture access](https://docs.overturemaps.org/getting-data/cloud-sources/), [Places guide](https://docs.overturemaps.org/guides/places/), and [source evaluation and live results](DISCOVERY-NOTES.md).

Reports retain OpenStreetMap attribution where applicable (ODbL) and Overture source-level licenses. Overture Places is published under CDLA Permissive 2.0 / Apache 2.0 depending on source; Full CDLA/Apache license texts and a notice are included in the pool branch and successful report artifacts; preserve those notices when redistributing. [Overture attribution and licensing](https://docs.overturemaps.org/attribution/), [OpenStreetMap copyright](https://www.openstreetmap.org/copyright).

## October 15 review corrections: local fit and browser verification

The October 15 artifact contained Facebook links labeled as booking services, repeated evidence from shared websites, and a major distributor in the qualified list. Current qualification corrects those issues:

- `fit.py` filters a small, reviewable set of known national brands/distributors and clear supplier listings, both in newly normalized Overture records and at runtime for the existing pool. Local service geography alone is not ownership proof. A website statement such as “family owned” improves fit but is labeled **self-reported**, not independently verified. Unknown ownership remains explicitly unknown; brand affiliation lowers fit. Exclusions are visible with reasons. Examples of identity evidence: [Ferguson corporate information](https://www.ferguson.com/content/corporate-information/who-we-are/) and [Mister Sparky franchise information](https://mistersparkyfranchise.com/).
- Social domains are classified before booking links. Facebook/Instagram/etc. never become booking findings, even with booking wording. Booking text uses whole words and known provider domains, not substrings such as “book” inside “Facebook.”
- Repeated evidence is grouped by a stable issue/destination signature, with all page URLs and evidence records preserved. HTTP/HTTPS, `www`, trailing-slash and tracking aliases collapse evidence copies. Different forms, unrelated domains and distinct business identities remain separate. Shared contacts or a parent domain alone no longer prove that two named businesses are the same. Matching provider IDs or matching normalized name plus an explicit contact are required for identity merging.
- Related operators sharing one confirmed root issue receive one prioritized outreach draft; their separate IDs/names/websites remain recorded. A related identity whose root issue was already reviewed is retained in report/ledger relationship metadata, without another draft. Canonical contacts remain deduplicated inside each identity; common switchboards do not erase separate businesses.

### Automated Chromium checks

Actions installs pinned Playwright and Chromium; no accounts, keys, paid browser service or deployed infrastructure are required. Static inspection examines at most 100 candidates or five minutes; a second phase prioritizes at most 12 sites for browser checks within a 15-minute total audit budget. A browser worker is bounded to 60 seconds of checks / 80 seconds process time. The daily job has a 40-minute outer bound to accommodate discovery failover and browser installation. The target remains ten, with truthful shortfalls.

Chromium checks visible contact controls using trial clicks; it reads contact destinations and tests local JavaScript dialog openers without entering data. It measures contact-control position at both 375px and 390px. A source dead-link finding must have an actionable visible browser link and a matching Chromium HTTP 404/410 before it can drive outreach. Mobile contact clipping qualifies only when repeated at both widths and essential resources/dynamic-data blocking do not make the render inconclusive. General page overflow alone never qualifies. Working JavaScript dialogs and labeled/native rendered forms can dismiss corresponding source-only concerns; healthy mobile measurements can dismiss viewport/width hints for the inspected page.

Booking links are inspected for browser visibility/actionability; booking completion, available slots and delivery are never attempted or asserted. Empty contact URIs remain source-only potential issues unless a functional failure is independently confirmed. No timeout, blocked resource, absent popup response or browser startup failure becomes a factual defect. A browser dead-link claim requires an actual read-only contact-link click; direct GETs cannot overrule a working client-side popup/router. Browser failure downgrades source-only verified statuses to potential; it never falls back to technical-only outreach.

Safety controls are layered: fresh unauthenticated contexts; service workers, WebSockets, beacon/dynamic requests, downloads and arbitrary popups blocked; only permitted public document reads; robots checks; GET/HEAD only; form submission events and native submit methods disabled; no field entry; buttons inside or associated with forms excluded. Actual clicks are limited to local UI openers, with the network locked for the remainder of those interactions. Booking/quote submissions, authentication and destructive-looking requests are blocked. Sites needing blocked APIs remain inconclusive rather than failed. URL/DNS checks are the existing lightweight public-destination guard, not a general hostile-code sandbox guarantee.

Only `status=verified` **and** `verification=browser` findings qualify or appear in factual outreach. New scoring components are impact /45, evidence strength /30, business fit /20 and a concrete remediation /5. These are review priorities, not predicted revenue or conversion probabilities. Historical scores/drafts are not recalculated.

### Compatibility and preservation

Existing `seen` hashes, daily counts, append-only reports, drafts and pool remain intact. New `entities`, `finding_seen` and `related_entities` metadata are additive. Legacy provider IDs remain authoritative; legacy domain-only evidence is conservative for root pages with unknown identity, without discarding distinct named paths. The old ledger cannot reveal names/emails it never stored; no missing identity is invented. No history cleanup or retroactive rewrite occurs. Browser results and fit explanations appear in the dashboard; related identities remain visible under the representative finding.

Run tests after installing dependencies and Chromium:

```sh
python3 -m pip install -r prospecting/requirements.txt
python3 -m playwright install --with-deps chromium
python3 -m unittest discover -s tests -v
```

The suite includes real local Chromium/HTTP fixtures that assert popup operation, repeated mobile clipping, visible dead-link confirmation, and absence of any form or booking submission. Regression fixtures cover the October 15 Facebook/Ferguson examples, duplicate forms/pages, shared-site identities, preserved historical roots, unknown ownership, and browser-unavailable downgrades. Public network services are not required by the deterministic test suite. Optional live validation in Actions uses isolated scratch state with read-only repository permissions.

## Nationwide targeting and rotation

`targeting.json` is the operating configuration; `--config /path/config.json` overrides it. An empty `targeting.states` means all 50 states plus D.C. Restrict it with state abbreviations, for example `["CO", "IL", "NY"]`. Rotation visits one state per completed run, starting with a bounded search box around an approximate population center, then moves to a different two-degree tile on that state's next visit. Census 2025 state extents are bundled in `us-states.json`; no runtime geocoding, account, or credentials are needed. Alaska includes both sides of the date line. Search boxes are operational sampling areas, not municipal/metro boundaries.

For cities and metro areas, copy entries from `regions.example.json` into `targeting.regions`. Explicit regions replace state-grid rotation and rotate in listed order. Each has a stable ID, country, name, kind (`city`/`metro`), bounding box `[west,south,east,north]` no larger than two degrees per side, allowed states, IANA research timezone and language. Optional `localities` matches source address city names, case-insensitively; metro samples normally omit that filter to include suburbs. A cross-state metro lists all applicable states. Target timezones are research defaults; multi-zone states are not assigned an asserted business-local timezone.

The shared `geo_rotation` ledger records the completed cursor and per-state tile positions. Discovery failure preserves it with all lead data and produces separate diagnostics. Successful empty searches advance with an explicit shortfall. Manual successful reruns also advance; the existing workflow concurrency prevents concurrent ledger updates. Daily `daily_usage` limits screening and browser attempts across reruns, and existing daily qualification counts remain global. Sampling is bounded and cannot guarantee ten qualified prospects in every region. Tiles may contain rural/water areas; no weak findings fill the shortfall.

A candidate needs source-provided `country=US` and a matching state. City filters also require a sourced locality. Coordinates alone never assign a country/state. Overture projects its address fields; Overpass fallback requires explicit `addr:country`, `addr:state` and (when configured) `addr:city`. This strict address requirement can lower coverage. The old unscoped `pool.json` remains untouched and is never reused for a different geography. Regional caches include their complete filter configuration and cannot leak across targets. All provider IDs, contact normalization, entity/root-cause deduplication and historical evidence remain in one global ledger with unchanged key formats. International records cannot enter the production path.

The dashboard shows state, industry, verified problem and commercial suitability totals for **new prospects in this run**, together with the target and actual screening/audit/browser counts. Its search matches business, city/state, industry, finding code and ownership evidence. Existing historical reports/drafts remain unchanged. Unknown ownership remains unknown; listings or self-reported claims do not prove independence.

## Limits, measured capacity and future countries

`limits.screened`, `qualified`, `browser_checks`, `static_seconds` and `total_seconds` are configurable. Current defaults remain 100/10/12 with five-minute static and fifteen-minute total audit budgets; network/process requests already in progress may finish afterward. The existing forty-minute job bound, provider retry/backoff/rate limits, per-business pause, robots checks and read-only browser safety remain. `screened` counts candidate eligibility examinations, not successful website audits, and `browser_verified_sites` counts attempts, including inconclusive/unavailable checks. These are reported separately from qualified prospects.

The planned 500–1,000/25–50 profile is recorded **disabled**. Configuration validation rejects larger screening/qualification/browser caps until a reviewed benchmark and explicit code/config change increase the guard. Core limits are parameterized; no weakened verification or paid infrastructure is hidden in an increased target. See [measured live capacity](CAPACITY.md). Run an isolated bounded benchmark with:

```sh
python -m prospecting.benchmark --output /tmp/capacity.json
```

The benchmark uses temporary caches and an empty in-memory ledger, screens five candidates in each of two public-data regions and permits two browser attempts per region. It never writes production state or sends anything. A manual CI dispatch can include the same benchmark, preserving it as an artifact.

Country entries include enablement, language, research timezone and outreach restrictions. Only U.S. discovery is allowed by code, even if a future country's configuration is accidentally enabled. Canada/U.K. entries are disabled placeholders, with compliance and language review required before implementation and activation. Current contact normalization and draft language support remain U.S./English; adding a country also requires address normalization, telephone rules, geographic catalog, translation, source-policy review and applicable consent/legal-basis/suppression rules. Templates are not legal clearance.

U.S. outreach remains draft-only and requires review before any sending implementation. The stored policy calls for truthful headers/subjects, sender postal address, opt-out/suppression handling and federal/state review. The existing draft text is **not send-ready compliance certification**. [FTC CAN-SPAM guidance](https://www.ftc.gov/business-guidance/resources/can-spam-act-compliance-guide-business) applies to commercial email, including B2B. No automatic sending capability is added.

Geographic source: [Census 2025 cartographic state boundaries](https://www.census.gov/geographies/mapping-files/2025/geo/carto-boundary-file.html). Address interpretation follows the [Overture Places guide](https://docs.overturemaps.org/guides/places/). Standard public Linux runners and anonymous public datasets retain the intended zero incremental service cost; account artifact allowances and provider availability are external constraints. No billing settings change.
