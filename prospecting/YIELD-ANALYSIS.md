# Qualification yield: October 16, 2026

**The measured bottleneck is trustworthy browser coverage, followed by website accessibility. No sample in this investigation has yet established a higher qualified-lead yield.** The target remains ten supported, commercially eligible prospects per day; zero confirmed problems means zero drafts.

## Evidence and scope

The Texas report referenced in this task is the isolated full-pipeline validation from PR #7, documented in [VERIFICATION-NOTES.md](VERIFICATION-NOTES.md) and [the original aggregate](benchmarks/2026-10-15-texas-verification.json). It discovered 2,862 listings, screened 100 candidates, attempted 96 static audits and 12 browser checks, produced zero verified prospects/drafts, and took 367.48 seconds excluding discovery. Ten browser outcomes were limited; two were sign-in redirects incorrectly labeled complete. PR #7 subsequently rejected identity-provider destinations and TemperaturePro's national franchise site.

The latest scheduled production Actions run remains [38809157557](https://github.com/zfouse/fouse-digital/actions/runs/38809157557), which was **Alaska**, not Texas. Its log/artifact were checked again. The Texas validation and production run must not be conflated.

The old Texas report did not retain a terminal outcome for every candidate. We cannot retrospectively invent its exact rejection funnel. Instead, this investigation rechecked the **same 100 source IDs** (selected using the original date/ID order from the saved Texas pool) under current code/network conditions, in isolated in-memory state. Original history, cache bytes, dedup hashes and production rotation were untouched. All benchmarks used public, read-only requests: no field entry, form submission, call activation, booking or outreach.

## Exact-ID Texas replay funnel

| Stage | Candidates remaining / inspected |
| --- | ---: |
| Screened | 100 |
| Explicit website present | 96 |
| Eligible discovery fit / static audit attempts | 95 |
| Static audit completed | 64 |
| Public contact present and identity unique | 64 |
| Source signal present; eligible for prioritized browser inspection | 60 |
| Browser attempts | 12 |
| Complete browser inspections | 1 |
| Confirmed serviceable problems / new qualified leads / drafts | 0 |

These are replay measurements, not reconstructed October 15 decisions. The complete inspection found no confirmed serviceable problem; it does not prove that every part of that website works. Source-signal absence is not evidence of website health.

Every screened candidate has exactly one terminal outcome:

| Outcome | Count |
| --- | ---: |
| Browser budget/time exhausted before inspection | 48 |
| Browser inconclusive | 11 |
| Browser complete, no confirmed serviceable problem | 1 |
| No source signals to prioritize | 4 |
| Missing website | 4 |
| National franchise / discovery fit excluded | 1 |
| Static DNS failure | 10 |
| Robots unavailable or disallows inspection | 5 |
| TLS failure | 3 |
| Response exceeded existing size limit | 3 |
| Static HTTP 404 | 3 |
| Identity-provider redirect | 3 |
| Static timeout | 2 |
| Static HTTP 400 | 1 |
| Static HTTP 403 | 1 |
| **Total** | **100** |

Thus 31 static attempts failed access/inspection; 48/60 browser-ready candidates were deferred; 11/12 attempts remained inconclusive. **Actual yield: 0 qualified / 100 screened; complete browser rate: 1/12 (8.33%); browser-confirmed problem rate: 0/12.** The audit/browser replay took 394.76 seconds (6.58 minutes per 100, excluding discovery).

The replay diagnostics observed blocked dynamic data on six businesses, JavaScript errors on five, uninspected captcha/booking frames on five, essential resource network failures on four and request-cap exhaustion on two. These categories overlap and include testing restrictions; none is outreach evidence of a business defect.

## Diagnosis and measured changes

1. **Browser coverage is the largest observed loss.** The 12-business cap left 80% of the browser-ready Texas pool uninspected. The broader market capacity experiment completed 26 checks in 346.50 seconds across 45 screenings, including cache lookup and processing. Increase the production cap from 12 to **20**, retaining the 900-second total audit budget, 300-second static budget, 100-screen cap, aggregate daily usage accounting and target ten. This admits more inspection opportunities; it is not proof of more defects. Slow workers may still exhaust time before the cap, and an in-flight bounded worker may finish after the soft deadline.
2. **Discovery admitted unusable website arrays.** The first 45-business sample included five blank websites. Filtered pools removed 201/2,857 Houston records, 144/2,289 Chicago records and 152/2,049 Denver records in memory: 497 unusable website records in total. Screening then had 45/45 explicit usable website values rather than 40/45. Static completion was observed at 29/45 rather than 26/45, but replacements and network variability prevent attributing the entire difference to the filter. Selecting a later valid explicit website entry is supported and tested; no URL/domain/contact is guessed. Fresh source normalization and cached pool exclusions now have separate counters.
3. **Some browser limitations were testing artifacts.** Exact Google `/g/collect` and GoDaddy `/eventbus/web` logging requests were being counted as blocked functional data. They remain aborted, but their classification is now separate. The measured GoDaddy collector is present in its [public client script](https://img1.wsimg.com/tcc/tcc_l.combined.1.0.6.min.js); Google's collector was observed from the site's public [Google tag script](https://www.googletagmanager.com/gtag/js?id=GT-TW5QWTJ5). Unknown APIs, Tag Manager/Facebook code, captcha/booking frames and actual failed functional resources remain conservative limitations. Diagnostics now distinguish methods, dynamic data, essential script errors, forbidden destinations and resource caps, retaining only host/path/resource samples without query strings or credentials.
4. **Static code requested through fetch/XHR was blocked unnecessarily.** The measured Umbrella Roofing site fetches public NitroCDN JavaScript/CSS. Public GET `.js`/`.css` reads now follow the existing script/stylesheet DNS/path/request-cap/interaction restrictions, with only bounded version/cache query parameters. A targeted live recheck allowed 75 such reads, but the site still hit functional/resource/script limitations and remained **limited, unqualified**. A real Chromium fixture verifies that fetch-loaded code repairs an initially empty telephone destination without generating a false defect. Data APIs, POST, unknown parameters, private destinations and interaction-time requests remain blocked.
5. **Suitability and contact absence were not the primary measured cause.** One Texas candidate was excluded as a franchise; all 64 completed audits had public contacts. That does not prove independent ownership, current contact ownership or buying intent: source contacts are provenance-bearing hints, and the current fit rules still retain unknown ownership honestly. Provider coordinates/addresses also do not prove that a linked website serves that market (the Chicago sample's Umbrella Roofing website, for example, advertises Colorado service). No market preference or loosened qualification rule is inferred from zero yield.

Only repeated browser-evidenced defects supported by existing Fouse Digital services qualify. Missing viewport tags, long forms, source-only 404s, absent native submit controls, unknown booking behavior and unverified empty destinations never fill the quota. The small number of safely testable defect classes and blocked functional data limit the addressable yield; this investigation does not establish that the remaining confirmation requirements are arbitrarily restrictive.

## Market/industry benchmark

Three bounded metro boxes (Houston/TX, Chicago/IL, Denver/CO), five service industries (plumbing, HVAC, roofing, electrical, landscaping), three fixed source candidates per cell: **45 screening observations per pass**. Selection uses stable provider IDs and a deterministic hash order within each trade, with URL/name deduplication. The explicit-website fix deliberately replaces unusable records. These are overlapping repeated cohorts, not 180 unique businesses or a statistically representative U.S. sample. Source/network conditions changed between passes; do not treat them as a controlled causal A/B experiment.

| Pass | Screened | Browser attempts | Complete inspections | Qualified / 100 | Wall time | Minutes / 100 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| initial instrumented | 45 | 15 | 2/15 (13.33%) | 0.0 | 259.62s | 9.62 |
| website filtered | 45 | 15 | 1/15 (6.67%) | 0.0 | 246.26s | 9.12 |
| increased coverage | 45 | 26 | 4/26 (15.38%) | 0.0 | 346.5s | 12.83 |
| final static asset fix | 45 | 26 | 4/26 (15.38%) | 0.0 | 344.47s | 12.76 |

Final-code results by market and industry (three candidates screened in each cell):

| Market | Industry | Static completed | Browser attempts | Complete browser inspections | Qualified leads |
| --- | --- | ---: | ---: | ---: | ---: |
| Houston | plumber | 3 | 2 | 1 | 0 |
| Houston | hvac | 1 | 1 | 0 | 0 |
| Houston | roofer | 2 | 2 | 0 | 0 |
| Houston | electrician | 1 | 1 | 0 | 0 |
| Houston | landscaper | 1 | 1 | 0 | 0 |
| Chicago | plumber | 3 | 2 | 1 | 0 |
| Chicago | hvac | 2 | 2 | 0 | 0 |
| Chicago | roofer | 3 | 2 | 0 | 0 |
| Chicago | electrician | 2 | 2 | 0 | 0 |
| Chicago | landscaper | 2 | 2 | 1 | 0 |
| Denver | plumber | 2 | 2 | 0 | 0 |
| Denver | hvac | 2 | 2 | 0 | 0 |
| Denver | roofer | 2 | 2 | 0 | 0 |
| Denver | electrician | 2 | 2 | 1 | 0 |
| Denver | landscaper | 1 | 1 | 0 | 0 |

Final-code terminal outcomes: `browser_inconclusive` **22**, `static_robots_unavailable_or_denied` **5**, `browser_no_confirmed_serviceable_problem` **4**, `static_dns_failure` **4**, `browser_budget_or_time_not_inspected` **2**, `static_response_too_large` **2**, `static_http_404` **2**, `static_http_500` **1**, `static_timeout` **1**, `static_tls_failure` **1**, `no_source_signals` **1**.

The initial pass allowed one browser attempt per cell; coverage and final-code passes allowed two. The initial pass included cold discovery; website-filtered and coverage passes reused cached pools. The final pass used fresh discovery/normalization with the same fixed sampling rule. More attempts, replacement candidates and changing remote behavior prevent causal attribution of complete-inspection percentages to individual code changes.

A complete browser inspection describes the inspected pages under this read-only protocol; it is not form-delivery, booking-availability, phone ownership, independent ownership or sales verification. Inconclusive is never treated as a confirmed defect or as a healthy website. No market or industry yielded evidence justifying quota padding or removing nationwide coverage.

## Cost, repeatability and preservation

Incremental paid API/model/service cost was **$0** on the existing local runtime. The repository is public, and [standard public GitHub Actions runners are currently free](https://docs.github.com/en/billing/concepts/product-billing/github-actions). Account-wide artifact storage allowances were not measured; retained artifacts still consume those allowances. No account, credentials, paid data source, runner upgrade or billing change was introduced. Local wall-clock timings are not a GitHub Linux performance guarantee; discovery cold/cache behavior and remote latency differ, and byte transfer was not instrumented.

The [machine-readable measurements](benchmarks/2026-10-16-qualification-yield.json) include every replay terminal outcome, market/industry cell, denominator and timing scope. Future reports retain candidate traces and explicit rejection reasons rather than dropping all but the ten review-queue entries. Existing archived reports/drafts and ledger schemas remain readable and are not rewritten. Current qualified contacts, normalized contact/identity/root deduplication and the shared nationwide ledger retain their existing rules.

Run `python -m prospecting.yield_benchmark --output /tmp/yield.json --cache /tmp/yield-cache` for the bounded isolated comparison. The tests workflow also exposes a manual `yield_benchmark=true` option with temporary state/cache, read-only permissions, checkpointed reports, a 20-minute outer bound and seven-day artifacts. It skips generic 100-candidate live validation in the same dispatch. The daily production workflow remains automated; this PR does not deploy, merge or trigger a production research run.

Validation: **100 automated tests**, including real local Chromium fixtures, pass. Coverage includes exact funnel partitioning, browser-budget versus inconclusive distinctions, HTTP/access reasons, sourced URL recovery, immutable cache bytes, optional telemetry/lookalikes/query redaction, industry pushdown, capped configurations, preserved reporting/rotation/deduplication/history, and safe static-code reads with submissions/data APIs still blocked.
