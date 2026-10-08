# BenchLM as a possible benchmark data source

Checked: October 8, 2026, Japan time. Status: **research only**, retained at the owner's request. This records the session's web research; no authenticated API request, account creation or collector integration was performed.

BenchLM merits a small coverage probe as a secondary source. Its strongest potential contribution is access to sourced benchmark rows and retained publisher snapshots. Artificial Analysis remains the research recommendation for the next core performance source because its free API exposes independently conducted evaluations and the project already has a key. This recommendation is not an owner selection or implementation instruction.

## Reputation and scoring

BenchLM says it started in August 2025 and is maintained by Glevd. It assembles public model cards, evaluation leaderboards, papers and announcements rather than conducting its own private evaluations. This makes it an aggregation publication, distinct from the original evaluator. [About BenchLM](https://benchlm.ai/about)

Research found downstream use, including the [RL Research leaderboard](https://www.rlresearch.ai/leaderboard/), which identifies BenchLM model records as a source. That establishes some use, not an independent validation of BenchAlign accuracy. The session did not establish broad adoption by major labs, independently verified audience size, or a mature reliability record. The assessment of its reputation as developing is a judgment from this limited evidence.

Its published methodology distinguishes Supported and Estimated rankings, retains missing tests, identifies score versions and acknowledges estimation failures. Estimated positions can use peer evidence and lineage priors. For longitudinal analysis, a composite score can therefore move when evidence, peers or scoring policy changes without a new evaluation of the target model. Preserve those inputs and versions; never describe such movement automatically as a capability improvement. [Methodology](https://benchlm.ai/methodology)

## Documented collection access

| Plan | Monthly price | Monthly reads | History |
| --- | ---: | ---: | --- |
| Free | $0 | 1,000 | Current data only |
| Data Pro | $49 | 100,000 | Three rolling calendar months by UTC date |
| Research | $249 | 500,000 | All retained eligible history, without an age cap |

Plan prices and allowances: [BenchLM Data](https://benchlm.ai/data).

The documented REST base is `https://data.benchlm.ai/v1`; MCP is `https://data.benchlm.ai/mcp`. Free includes current rankings, admitted source results and catalogs. One successful data page consumes a read; usage and coverage queries are free. Documented rate limits are 10 requests/minute for Free and 60 for paid plans. Catalog presence does not guarantee numeric result coverage. These are documentation findings, not a verified response contract. [Data access](https://benchlm.ai/data/access)

The service reports retained Arena overall snapshots back to August 2024 and source-reported evaluation runs back to January 2025. Those dates are service-wide coverage claims, not promises for our exact DeepSeek, GLM or other tracked products. Historical access is paid; a missing record remains missing. Source evaluation dates must remain separate from archive dates and BenchAlign scoring dates. [History coverage documentation](https://benchlm.ai/data/access#questions)

## Display and redistribution terms

BenchLM distinguishes query/internal-analysis access from permission to publish its owned outputs or compiled feed in a commercial customer-facing product. Paid plans do not include that display or redistribution permission. Website JSON downloads and `benchlm.ai/api/data` exports use CC BY-NC 4.0; commercial use requires a license. Individually licensed publisher measurements retain their own rights, attribution and source notices. Existing quotation/embed permissions should not be generalized to a recurring downloadable feed or our charts. [Data and licensing](https://benchlm.ai/data#commercial-display-or-redistribution-request-a-license), [terms](https://benchlm.ai/terms)

## Fit with the existing collector

If selected later, BenchLM would reuse `data_sources`, `metrics`, `metric_observations`, `metric_values` and the reviewed source-to-product mappings. No provider-specific table is indicated by this research. A BenchLM composite score and an original benchmark score are different definitions; retain the ranking surface, evidence label, scoring version, source publication and exact product variant.

Prefer attributable original-source measurements when comparing performance. An Arena result obtained through BenchLM remains the same underlying evaluation and must not become a second independent signal alongside our direct Arena data. The same applies to other mirrored evaluator rows.

Artificial Analysis's official free API documents independently conducted intelligence evaluations, speed and pricing, stable model/creator identifiers and 1,000 requests/day. Its use is subject to attribution and its own terms; existing credentials do not establish display/forecast/trading permission. [AA API documentation](https://artificialanalysis.ai/api-reference)

## Questions before any future selection

- Do its free coverage queries include our exact tracked products, variants, original benchmarks and required dates?
- Which results add coverage beyond our current sources, rather than repeat the same evidence?
- What do actual response types, identifiers, missing fields, publication times and revision semantics look like?
- Does retained Arena history include the exact no-style-control scoring configuration we use?
- What commercial display, derived forecast and API redistribution scope can be agreed, at what price?

No BenchLM registry row, mappings, measurements, schedule or display has been created. The four selected sources and completed staging endpoint remain unchanged. Related execution plan: [benchmark-download-collector](../plans/2026-10-05-070106-feat-benchmark-download-collector-plan.md).
