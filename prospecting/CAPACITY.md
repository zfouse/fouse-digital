# Live capacity measurement — October 15, 2026

Two isolated live samples used anonymous Overture Places and actual public websites with the unchanged read-only Chromium rules. No production ledger, historical report or draft changed. Aggregate measurements are saved in [benchmarks/2026-10-15.json](benchmarks/2026-10-15.json).

| Sample | Source listings | Screened candidates | Websites audited | Browser attempts | Qualified drafts | Discovery | Audit + browser | Total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Chicago metro box, IL/IN | 3,275 | 5 | 3 | 2 | 0 | 13.30 s | 16.43 s | 29.74 s |
| Denver city sample, CO | 562 | 5 | 5 | 2 | 0 | 9.19 s | 97.65 s | 106.84 s |

Actual non-St. Louis service-business discovery succeeded in both regions. The sample is not 3,837 verified prospects: these are source listings awaiting qualification. Four browser attempts yielded one complete inspection, two limited inspections and one 80-second worker timeout; an additional potential record was not browser-tested. No inconclusive signal generated an outreach claim. Report JSON measured 13,150 and 26,585 bytes respectively. Source range-request count/transfer bytes were not instrumented, so no claim of a measured bandwidth cost is made.

At the observed end-to-end audit pace, a purely linear extrapolation gives approximately **27–163 minutes for 500 screenings**, or **55–326 minutes for 1,000**, excluding discovery, installation and upload. This is an illustrative range, not a capacity prediction: ten candidates are a small sample, the browser mix differs by region, and one slow site dominated Denver. The current forty-minute workflow cannot reliably support the requested larger scale. With zero qualified prospects in this tiny sample, there is no defensible throughput estimate for 25–50 qualified daily. Never loosen the evidence standard to meet that number.

The operating profile therefore remains capped at **100 screened / 10 qualified / 12 browser attempts**, with a truthful shortfall. Before increasing it: measure a broader multi-region sample, record actual browser completion/yield and transfer/storage, review elapsed runner time and public-provider budgets, then explicitly adjust the configuration guard and workflow budget. No larger workload is automatically activated from this benchmark.

No paid API, model, browser service or account was used. The repository is public and retains standard Ubuntu Actions runners; [GitHub documents free standard runners for public repositories](https://docs.github.com/en/billing/concepts/product-billing/github-actions). Artifact allowances are shared at account level; this sample cannot establish available storage or guarantee a zero bill after future infrastructure changes. Existing thirty-day report retention and additive Git history remain; no paid tier or billing setting is enabled. Regional pools and immutable history grow over time and should be measured before bulk scaling.

Repeat locally with `python -m prospecting.benchmark --output /tmp/capacity.json`, or use the optional benchmark input on the existing manual test workflow. CI uses Python 3.12 on Linux, so its timing may differ from this macOS/Python 3.9 measurement. All benchmark state is isolated and sending/form submission/booking remain prohibited.
