# Phase 1 prospect research

## Existing deployment and implementation

Inspected October 14, 2026: `main` serves the static site from `/` through the existing GitHub Pages legacy build at https://zfouse.github.io/fouse-digital/. No application backend, database, package dependencies, or custom workflows existed. The customer form prepares email to `fousedigital@gmail.com` in the visitor's email app. This research system uses the same repository and GitHub Actions; it does not change the customer form or site deployment.

Python 3.12 standard library only. No API keys, paid AI services, new accounts, email sending, form submission, or SMTP integration. Personalized drafts use deterministic templates populated with the business name, website and actual observation. They do not require a language-model subscription.

## Qualification and evidence

A lead must have all of:

- An OpenStreetMap name and service trade (plumbing, electrical, HVAC, roofing, carpentry, painting, landscaping).
- Coordinates inside the St. Louis metro research box: latitude 38.40–38.95, longitude -90.75–-89.95. This includes nearby Illinois communities, not a verified service radius.
- A website returning HTML, with robots permission for the homepage audit.
- A public phone or email from OSM tags or a homepage `tel:`/`mailto:` link, with its source. Public listing contact data may be stale; ownership and deliverability are not verified.
- At least one observed homepage issue: response remains HTTP, or fetched HTML lacks a device-width viewport declaration.

Reports include source URLs, UTC check timestamp, exact observation, evidence and draft status. Missing viewport metadata is specifically an HTML-source observation; JavaScript could add it. HTTP observation does not assert HTTPS is unavailable. No claims about lost revenue, broken forms, speed, mobile usability or missing calls to action are inferred. Confirm behavior in a browser before using a draft. The system does not test form delivery or crawl other pages.

Discovery makes one bounded Overpass request per run (45-second server timeout), considers at most 150 candidates, pauses one second per audit, limits each response to 1 MB and each website request to 15 seconds (discovery allows 60 seconds). robots errors other than 404 cause a skip. Network failures never become website findings. URL checks reject credentials, unusual ports and DNS addresses that are not globally routable, including redirected destinations. This is lightweight source inspection, not a browser sandbox; DNS resolution checks are not a guarantee against DNS rebinding.

OpenStreetMap coverage is finite and uneven. The target is 10 **qualified** businesses per Chicago calendar day, not a promise. Shortfalls are recorded without relaxing qualification or inventing issues. OSM identifiers, normalized domains (including redirects) and normalized phone numbers are hashed for deduplication. Multiple branches of one domain or shared phone are intentionally treated as one prospect. Accepted leads remain deduplicated across days; failed or unqualified candidates may be checked again. Daily counts also prevent manual reruns generating more than 10 that day.

## Operation and review

1. Merge the PR. The daily workflow activates on `main`; no secrets or setup accounts are needed. Existing repository rules must allow Actions to create/update `prospect-ledger` with its repository token.
2. Open Actions → **Daily prospect review**. It runs daily at 13:23 UTC (8:23 a.m. Chicago daylight time / 7:23 a.m. standard time); GitHub scheduling can be delayed. **Run workflow** allows a manual run on main.
3. Download `prospect-review-<run ID>` from the completed run, unzip, and open `review.html`. `review.json` contains the same data for later import. Review contacts, sources and observations, then copy any draft you choose to use. Nothing sends an email.
4. Check the run summary for counts/shortfalls and the run status for failures. Discovery errors fail the run and do not alter the ledger. Website errors are recorded as skips without sensitive response bodies.

Reports are uploaded before the ledger is committed, so a report-upload failure cannot mark unseen drafts as processed. A failed ledger push leaves the report available but requires resolving the branch permission/conflict before the next run; those leads may recur. Concurrency serializes scheduled and manual runs. The ledger lives on a separate branch and is not deployed to Pages. Do not delete/reset `prospect-ledger` unless deliberately resetting deduplication. Reports expire after 30 days; download reports you want to retain. The ledger persists independently of artifact expiration. There is no authenticated CRM or long-term draft archive in this static deployment.

**Visibility:** this repository is public. Authenticated GitHub users with repository read access can access Actions artifacts; treat review reports and drafts as accessible, not private. They contain public business contact information only. Do not add private notes or client data. The ledger contains hashes and daily counts only. A private review workspace would require a separate infrastructure decision.

## Cost

Designed for $0 incremental cost: standard Linux Actions runners in this public repository, no dependency installations, no model calls, one public Overpass request per day, and small reports retained for 30 days. GitHub artifact storage has account-level allowances; avoid increasing report sizes/retention and keep the account's paid Actions budget at $0 if needed. No billing settings are changed by this PR.

References: [GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions), [Overpass shared resource guidance](https://dev.overpass-api.de/overpass-doc/en/preface/commons.html). Free public Overpass service can throttle or be unavailable; the workflow fails rather than silently replacing discovery with a paid provider. OSM attribution is embedded in every report: [© OpenStreetMap contributors, ODbL](https://www.openstreetmap.org/copyright).

## Local use and tests

```sh
python3 -m unittest discover -s tests -v
python3 prospecting/run.py --state /path/to/ledger.json --output /path/to/reports
```

Local runs require Python 3.9+ with system timezone data; CI uses 3.12. Keep the same ledger between runs. `--candidates /path/to/osm.json` substitutes an OSM-format discovery response, but still audits websites. Unit tests inject responses and never access the network. Tests cover truthful findings, healthy pages, robots denial, timeouts, location/category/contact qualification, domain/phone/rerun deduplication, daily quota, unsafe URL rejection and HTML escaping.

## Validation in this PR

Eight offline tests pass; whitespace/diff checks pass. Two live discovery attempts on October 14, 2026 returned HTTP 504 from the public Overpass endpoint, including one with a 60-second client timeout. No live leads were fabricated and no ledger was written. Live discovery yield and complete scheduled execution remain unverified until the service responds and the workflow runs on main. This limitation is a reason to review the first run's shortfall, not to assume 10/day is achieved.
