# October 15 investigation and read-only verification

## Reporting discrepancy

Actual production evidence was read from [Daily prospect review run 38809157557](https://github.com/zfouse/fouse-digital/actions/runs/38809157557), its downloaded review artifact, and a read-only copy of the `prospect-ledger` branch at `b64572a`.

The newest report contains `qualified_today=1`, no new leads/drafts, 100 screened candidates, 89 audits and 12 browser attempts. Three same-day archived reports trace the count to **Ferguson Plumbing Supply**, created in the earlier 15:47 UTC run using source-only evidence. Later runs carried the count forward; they did not newly verify Ferguson. It is also a known excluded distributor under the current fit policy. The legacy ledger contains no new entity records from the latest run.

Reconciliation of the actual three archived JSON reports returns **historical total 1, accepted browser-evidenced carryover 0**. New additive `verified_daily` counts govern the verified quota; the old `daily` total, original report/draft and deduplication hashes are retained. Report fields/dashboard/Actions distinguish carryover, newly qualified prospects, new drafts, current verified daily progress and historical total. Archived carryover is not described as newly live-tested. Unknown/missing historical proof never becomes accepted verification.

## Alaska and rotation

The initial nationwide selector used `sorted(STATES)`, so `AK` was the first abbreviation. The stored ledger confirms cursor 1 and one completed `AK-0` search around Anchorage. This was alphabetic order, not a commercial score or a failed location fallback.

Selection now chooses the least-visited allowed state, with a declared larger-market tie-break order. The real legacy state therefore selects Texas next, honoring Alaska's visit. A completed search advances the state's tile and visit count. Tests cover all 50 states plus D.C., restart/migration, custom state filters and unchanged historical data. Alaska and smaller states remain included; no geographic performance forecast is claimed. Explicit city/metro rotation remains supported, and all business/contact/root deduplication stays global.

## Live review recheck

A bounded exploratory read-only recheck reused all ten public businesses in the October 15 review queue. It used isolated output, fresh static audits and the new up-to-two-page browser checks. The sample ran during development and is not a controlled capacity comparison. Aggregate evidence: [verification review measurements](benchmarks/2026-10-15-verification-review.json).

- 10 businesses attempted; 9 reached browser inspection.
- Business outcomes: 1 complete, 8 limited, 1 static audit connection reset.
- **0/10 businesses produced a supported verified prospect/draft**; 0/9 browser-tested businesses qualified. A complete browser inspection is not a defect or qualification.
- The connection reset, blocked widget data, missing resources and partial render outcomes remain inconclusive. Existing technical/long-form/source-label signals do not fill the quota.
- All observed contact/phone/booking/form checks were read-only. No production state/history was changed. No form was filled/submitted, no phone/email link activated, no appointment/quote request made and no outreach sent.

These observations do not establish improved real-world verified-prospect yield. They demonstrate why apparent technical findings must not be promoted to sales claims. New positive capabilities are separately tested with controlled real Chromium/HTTP fixtures: empty native phone destinations, inert booking controls, actual clipped inquiry submits and visible contact-link failures. Negative fixtures cover delegated/hover-populated controls, client-side popups, off-canvas menus, harmless oversized boxes, failed stylesheets, optional analytics and blocked functional widgets.

## Full revised pipeline validation

An isolated Texas/Houston-area run completed using the same production discovery/audit/browser pipeline and conservative operating limits. Its first attempt exposed a previously unhandled valueless HTML attribute (`style` parsed as `None`) that could abort the entire run. Attribute string values are now normalized to empty strings while retaining attribute presence; a regression test verifies that such public HTML remains source-only evidence and cannot crash research. Production ledger/reports were unaffected by the failed scratch run.

The successful rerun discovered **2,862 source listings**, screened **100 candidates**, attempted **96 static audits** and **12 business browser checks**, and produced **0 supported verified prospects / 0 drafts**. The audit/browser phase took **367.48 seconds**, excluding discovery and final output writes. Aggregate source/result evidence is in [Texas pipeline measurements](benchmarks/2026-10-15-texas-verification.json). Audited-site counts mean attempts, not successful fetches; 26 recorded static attempts ended with network/access/inspection exceptions.

Ten browser slots were limited; two were reported complete but were actually Google sign-in redirects from private Google Sites pages. Those are not successful public business conversion-path inspections. This exposed another quality bug: identity-provider destinations are now rejected before business analysis/browser testing. A subsequent live read-only check of both original hosted-site URLs confirmed the identity-page rejection; [targeted exclusion measurements](benchmarks/2026-10-15-post-validation-exclusions.json) preserve source URLs and outcomes. Public Google Sites pages are still allowed. No authentication was attempted.

The sample also surfaced TemperaturePro's national brand homepage as an unknown-ownership prospect. It is now excluded consistently with existing national franchise filters, grounded in the company's [own franchise description](https://temperaturepro.com/own-a-franchise/) and [national locations list](https://temperaturepro.com/locations/). This does not assert that its franchisees lack local ownership; a national franchise website is outside this pipeline's independent-operator purchasing fit.

The full-run measurements precede these final suitability exclusions, so they are not a claim that the final filters have already produced a higher live qualification rate. All twelve slots produced **zero verified/draftable businesses (0%)**. The code now avoids spending future browser slots on the observed sign-in and known-brand false candidates. A broader suitable-business cohort is needed to establish increased yield. The final automated suite contains **91 passing tests**, including exact behavior for these exclusions.

## Remaining limits

The target remains ten and budgets stay at 100 candidate screenings / 12 business browser attempts, with existing time and rate limits. Each inspected document gets 25 seconds inside the 80-second worker bound. JavaScript-heavy sites requiring blocked APIs, bot challenges, late hydration, inaccessible resources and external booking completion remain limited. Delegated or hover-dependent native link behavior stays potential when it cannot be established safely. No phone ownership, deliverability, form delivery, booking availability or revenue impact is inferred.

Reference behavior: [Playwright trial clicks](https://playwright.dev/python/docs/api/class-locator#locator-click-option-trial) check actionability while skipping activation; [Chromium event-listener inspection](https://chromedevtools.github.io/devtools-protocol/tot/DOMDebugger/#method-getEventListeners) reads handler metadata. Browser instrumentation is distinguished from site handlers and does not justify bypassing real handlers. No paid service, new account, production deployment or sending capability was added.
