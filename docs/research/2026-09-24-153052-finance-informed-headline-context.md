---
artifact_contract: "ce-handoff/v1"
created_at: "2026-09-24T06:30:52Z"
title: "Finance-informed headline context for PushinWeight"
summary: "Research-backed proposals for historical activity baselines, trend phases, and content-grounded headlines; Jev deferred and overlapping 0731 work identified."
keywords: ["headlines", "historical-context", "finance", "relative-volume", "trend-phases", "post-content", "jev-deferred"]
cwd: "/Users/fuchitalee/development/pushin-weight-v2"
resume_focus: "Continue the discussion of finance-inspired headline packet improvements while preserving the product's advantage: posts contain expressed attitudes and reasons, not just a numerical trace."
repository: "allenwlee/pushin-weight-v2"
repo_root_sha: "aff2eb3769a99795697f11c9cadeae825672b5d9"
branch: "feat/combined-rare-type-extra-search"
head: "736ba891b6eb19c7e8542dc32f25393cd2a6c3ef"
worktree_path: "/Users/fuchitalee/development/pushin-weight-v2"
---

# Finance-informed headline context

## Objective, user intent, and authority

The user's latest request was: "let's set aside jev for now. $compound-engineering:ce-handoff the changes to headline using what we learned from finance".

This is a handoff of research and proposed changes, not a record of implemented headline changes. Creating this handoff is the authorized action. There is no new authorization to implement, run paid model experiments, commit, push, migrate, or deploy the proposed feature. Jev is explicitly deferred; do not reopen it as part of this continuation without the user's direction.

The user's preceding product direction was an on-demand headline for a chosen timeframe, brand(s), post country(ies), and post language(s), potentially using prepared text/metadata chunks for frequently viewed brands. Historical comparison is especially important: what is unusual now, and how does the conversation differ from what preceded it? This broad direction is context, not a finalized implementation contract.

After researching financial chart interpretation, the user emphasized that our source posts can contain both expressed attitudes/actions and the authors' stated reasons. The assistant's qualification was that attention, positive sentiment, explicit adoption intent, and reported purchase/use are distinct; a post is not automatically evidence of willingness to buy. Also distinguish a person's explicitly stated reason from an inferred explanation for an aggregate trend.

## Status and scope

- Completed: read-only inspection of the existing headline path; Firecrawl research into financial chart descriptions; discussion of transferable metrics and limitations.
- Not started in this session: implementation, a dedicated finance-inspired implementation plan, threshold calibration, cost/latency measurements, or a quality audit of newly generated headlines.
- The assistant's feature priorities below are proposals. The user requested this handoff but did not individually approve algorithms, thresholds, taxonomy, baseline length, or a release target.
- No application files were edited for this research. Ignored Firecrawl research captures and this temporary handoff were written.
- A separate session is actively implementing headline-provider/batching changes. The captured root code is not a claim about that worktree's latest implementation or the live production configuration.

## Verified current implementation

Repository-relative references below are anchored by the metadata above. Line numbers are capture-time landing points; they can move.

| Reference | What matters |
| --- | --- |
| `monitor/trend_narrative_candidates.py:1608`, `_compact_shape_summary()` | Current shape description uses first/last coarse-bucket counts, net direction and percentage change, the largest adjacent transition, and peak/trough with timestamps. It computes total absolute movement internally but does not expose directional efficiency or an explicit sequence of phases. |
| `monitor/trend_narrative_candidates.py:508`, `build_trend_analysis_snapshot()` | Builds one immutable snapshot under a PostgreSQL repeatable-read, read-only transaction. Existing deterministic facts/evidence preparation is reusable; this is not a greenfield pipeline. |
| `monitor/trend_narrative_candidates.py:1012`, `_assemble_compact_snapshot()` | The dossier already combines quantitative facts, family summaries, shape, corpus phrases, and evidence. Full coarse/fine/metadata series remain private. |
| `monitor/trend_narrative_candidates.py:1139` | Baseline context is the preceding period, with `historic_norm_wording_allowed: False`. Do not claim current packets establish what is usual for an hour/weekday over a longer history. |
| `monitor/trend_narrative_candidates.py:327`, `_provider_dossier()` | Provider projection omits `raw_series`, aggregate inputs, and private provenance. New useful measurements must actually reach the writer, not merely be calculated privately. |
| `monitor/trend_narrative_facts.py:1108`, `_aggregate_episode_rows()` | Existing finer-bucket episode logic uses current-window median activity, minimum post/author counts, and peak-to-baseline thresholds; contiguous qualifying buckets are grouped. This is not a matched hour-of-week historical norm. The compact dossier does not automatically expose every older episode field. Trace the active projection before reusing it. |
| `monitor/trend_narrative_candidates.py:148`, `DOSSIER_EVIDENCE_TARGETS` | Main post-evidence targets are 6/8/10/12 for 1/7/30/365-day windows, with first-party reservations and deduplication. The writer is already reading a bounded sample, not the full raw corpus. |
| `monitor/trend_narrative_candidates.py:2159`, `_fetch_corpus_phrase_signals()` | At most eight prominent two-word phrases per brand; current/prior document prevalence, peer presence, burst bounds, and representative excerpts. Counts use the deduplicated source corpus within resource ceilings, not only selected evidence. Resource overflow marks the family unavailable. Phrase frequency is not semantic reason clustering. |
| `monitor/trend_narrative_generation.py:111` | The editor is explicitly why-first: discussed content leads, measurements provide context. Claims carry fact/evidence IDs; critic instructions cover support, causality, event identity, and proportionality. Trilingual prompts derive from this base. These contracts do not prove every generated headline succeeds. |
| `monitor/trend_narrative_demand.py:151` | Existing demand selection suppresses materially unchanged dossiers; do not describe caching/demand shaping as entirely absent. Actual activation depends on configuration. |
| `monitor/views.py:3594`; `monitor/trend_narrative_projection.py:30` | The headline path receives brand selection and fixed 1/7/30/365-day windows. Country/post-language filters are not passed into the headline projection. Arbitrary filtered headlines need a changed request/evidence contract, not just a new prompt. |
| `monitor/views.py:3227` | Current country filtering uses the author's recorded country, not verified physical location when posting. Preserve that meaning. |
| `docs/reference/headline-trend-narratives.md`; `CONCEPTS.md:185` | Existing narrative contract and vocabulary. Both files have unrelated local edits; source code controls behavior. Some prose is stale relative to newer work. |

Illustrative gap: equal-duration counts `10 -> 20 -> 80 -> 40 -> 15` produce net `increase` and +50% in the current shape field. A useful phase description is "spiked, then mostly subsided; still slightly above the starting level." Peak/trough are already present, but the phase sequence and persistence are not explicit.

## Finance research and proposed adaptations

These sources were searched/scraped with Firecrawl on 2026-09-24. The product documentation establishes what vendors describe, not independent proof of forecasting accuracy or fitness for social-post counts. The proposed transfers below are the assistant's interpretation.

### 1. Matched historical activity: highest proposed priority

- Source: [TradingView Relative Volume at Time](https://www.tradingview.com/support/solutions/43000705489-relative-volume-at-time/).
- Documented mechanism: compare current regular/cumulative volume with historical values at matching time offsets. The page explicitly warns that an unfinished bar depresses the current value.
- Proposed transfer: compare collected-post rates with comparable historical times using the same brand/country/language scope. Expose observed/expected ratio, historical sample size, baseline interval, timezone, and completeness.
- Distinguish preceding-period comparison from usual-for-this-time comparison. Do not invent a historic norm when coverage is insufficient. Baseline duration and same-hour versus same-weekday matching remain undecided.

### 2. Direction, magnitude, and steadiness are separate

- Source: [Interactive Brokers: Linear Regression R-Squared](https://www.interactivebrokers.com/campus/glossary-terms/linear-regression-r-squared/). It distinguishes regression slope/direction from fit/strength.
- Source: [StockCharts: Kaufman's Adaptive Moving Average](https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-overlays/kaufmans-adaptive-moving-average-kama). Its efficiency ratio is absolute endpoint change divided by total absolute adjacent movement; it also discusses persistence filters and longer/shorter trends.
- Proposed transfer: add rate-based direction and fit, plus directional efficiency to distinguish steady buildup from back-and-forth movement. Our shape function already computes the efficiency denominator as `total_movement`.
- Flat/zero denominators need explicit handling. High efficiency is not proof of large, meaningful, or statistically significant change. A spike-and-return can have low efficiency without being repeated random noise; retain phase information.

### 3. Multiple horizons and post-peak context

- Source: [Trading Central Technical Views](https://www.tradingcentral.com/tc-products/tc-technical-views), which describes combining multiple timeframes and recent price data.
- Proposed transfer: independently represent overall-window direction, recent direction, time since peak, drop from peak, and the remaining elevation above baseline.
- Desired distinction: "cooling over the last hour, but still unusually active this week" rather than forcing one direction label onto the whole story. Do not compare unequal-duration raw counts as rates.

### 4. Explicit phases and persistence

- Source: [TrendSpider Automated Chart Pattern Recognition](https://help.trendspider.com/kb/automated-technical-analysis/automated-chart-pattern-recognition). Distinguishes developing/confirmed patterns, invalidation, and stale or played-out formations; it acknowledges subjectivity and changing detection results.
- Proposed social-activity vocabulary: gradual buildup, sudden spike, sustained elevated activity, cooling after a peak, return to usual levels, repeated bursts. No finalized closed taxonomy exists.
- Proposed phase evidence: start/end, rate/magnitude, number of completed buckets, peak, and relevant post IDs. Minimum durations/thresholds remain uncalibrated.
- A possible statistical method is [ruptures change-point detection](https://centre-borelli.github.io/ruptures-docs/). This library documents offline segmentation, not a guaranteed real-time detector. It is a research candidate, not a selected dependency. Latest-phase labels may need to remain provisional; retrospective pivot confirmation must not leak future observations into a real-time claim.

### 5. Calculated evidence into a narrative, not a chart-reading prompt

- Closest product precedent: [Trading Central FIBI Storyteller](https://www.tradingcentral.com/tc-products/fibi-storyteller), described as turning technical signals and multi-timeframe information into narratives.
- Proposed adaptation: code calculates the numbers and bounded shape facts; the existing writer explains the supported story. There is no proposal to purchase a financial platform, add chart-image inference, or transplant bullish/bearish predictions.
- Additional assistant proposal: show participation breadth (distinct authors and source diversity) so repeated posting does not automatically imply broad adoption or organic interest.

## Preserve the product's content advantage

The user redirected attention from shape alone to what the posts say. The current feature is already content-informed and why-first, but does not maintain a systematic historical account of motivations.

Example distinction, not an observed finding:

- Current capability: "Positive discussion increased; selected users praise affordability."
- Stronger future claim: "Affordability is becoming a more common stated reason for adoption, while reliability remains the main stated objection."

The latter needs a defined relationship between expressed action/stance, stated reason, supporting text, and time. Literal two-word phrase counts do not reliably group paraphrases such as "costs less," "half the bill," and "affordable for my workload." Selected examples cannot establish population percentages.

Semantic reason histories were discussed as a potential extension, not approved as part of the minimum finance-shape change. No reason taxonomy or extraction method was chosen. Jev comparisons were subsequently explored and explicitly deferred by the user. Do not make Jev a prerequisite for this work.

Shape can locate an episode, not prove its cause. A user's explicit "I switched because of price" supports that person's stated reason, not necessarily the cause of an aggregate spike. Attention, stance, intent, reported behavior, and verified behavior should remain distinct.

## Proposed verification questions, not completed tests

The assistant's suggested next design discussion could establish the smallest packet change first: historical normalization, phase/persistence, and post-peak/multi-horizon context. Decisions still needed include supported filters/timeframes, available trustworthy history, baseline policy, thresholds, sample sizes, and overlap with the concurrent 0731 branch.

Risk-specific examples for a later authorized plan:

- Equal endpoint change but different paths: steady rise, spike-and-return, repeated bursts.
- Overall rise plus recent decline; ongoing plateau versus return to baseline.
- Normal daily/weekly activity cycle versus genuinely unusual matched-time activity.
- Flat series, zero/low baseline, sparse authors, missing buckets, incomplete final bucket, ingestion delay, backlog/backfill, and changes in collection coverage.
- Filtering and deduplication identical between current and historical periods; multi-brand attribution and counting units explicit.
- Field propagation through snapshot -> provider projection -> writer/critic -> displayed headline; storing a private metric alone is not completion.
- Content explains the topic without converting temporal correlation into proven causation or sentiment into purchase intent.
- Cost/latency and packet size measured against the existing bounded packet. No savings percentage has been established.

Relevant existing tests: `tests/test_trend_narrative_candidates.py` (packet bounds, evidence, phrase counts), `tests/test_trend_narrative_facts.py` (quantitative facts), `tests/test_trend_narrative_generation.py` (prompt/output contracts), `tests/test_trend_narrative_projection.py` (public output), and `tests/test_trend_narrative_demand.py` (material change). These were inspected selectively, not rerun for this research.

## Concurrent work and fragile local state

Capture-time root HEAD is `736ba891b6eb19c7e8542dc32f25393cd2a6c3ef`, branch `feat/combined-rare-type-extra-search`, ahead of its upstream by 21 commits. Root has unrelated tracked edits in `CONCEPTS.md`, `README.md`, several `docs/reference/` files, and vendor/harvester docs, plus untracked vendor directories and a headline plan. Preserve them; do not treat the root branch as a clean main base.

Machine-local overlapping worktree: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/headline-0731-architecture`.

- Branch: `feat/headline-0731-architecture`; captured HEAD `2cfb06b3fd387f8c368ca4b615a8c6c319a83816`.
- Recent commits: `c512c46` strict direct 0731 provider route; `a879474` two-brand review packets; `2cfb06b` budgeting a two-brand graph for three workers.
- Local modifications: `monitor/trend_narrative_evaluation.py`, `tests/test_trend_narrative_evaluation.py`; untracked `scripts/headline_0731_bakeoff.py`, `tests/test_headline_0731_bakeoff.py`, `.pytest-tmp/`.
- This work was observed, not performed or fully reviewed in this session. It overlaps packet/generation concerns. Its qualification, delivery status, and newest state require fresh inspection before any changes.

Machine-local untracked root plan: `/Users/fuchitalee/development/pushin-weight-v2/docs/plans/2026-09-23-142325-feat-headline-0731-architecture-plan.md`. This is separate provider/cost work, not a finance-shape implementation plan; do not overwrite or silently expand it.

Machine-local ignored research cache: `/Users/fuchitalee/development/pushin-weight-v2/.firecrawl/`.

- `search-headline-relative-volume-20260924.json`: matching-time volume calculations and unfinished-bar caveat.
- `search-headline-efficiency-20260924.json`: StockCharts efficiency ratio and persistence filtering.
- `search-headline-regression-20260924.json`: IBKR slope/fit and Fidelity regression documentation.
- `search-headline-automated-patterns-20260924.json`: TrendSpider lifecycle and limitations.
- `search-headline-market-narratives-20260924.json`, `search-headline-storyteller-20260924.json`, `headline-tradingcentral-storyteller-20260924.md`: numerical signals to contextual narratives.
- `search-headline-changepoints-20260924.json`: official ruptures documentation plus other search results. Only primary sources underpin this handoff; community scripts and generic trading pages were not treated as established methods.

These caches are uncommitted and may disappear. Public source URLs above remain the portable pointers. No worktree was committed, stashed, copied, or removed to preserve this handoff.

## Continuation constraints

Current `AGENTS.md` and applicable skills remain authoritative. Fuchitalee is the sole writable authority for PushinWeight. Repo instructions require Ollija annotation before selecting/creating an implementation plan and checking the resulting delivery guide before Git/deployment mutations. No finance-specific plan was selected or created here; this temporary handoff is not one.

Useful skills for a later user-confirmed continuation: `ce-brainstorm` to settle requirements, `ce-plan` only after the requirements/authority are clear, `firecrawl:firecrawl-search` for source refresh, and repo `avoiding-recurring-mistakes` before changes. UI or harvest changes have additional mandatory skills under the repo rules.

The natural resume is to orient from this research, acknowledge the concurrent headline branch and Jev deferral, and confirm the desired next scope with the user. Reading this handoff is not authorization to implement or publish.

This immutable snapshot is stored in OS-managed `/tmp` on fuchitalee, not permanent storage. A receiving session on another host needs this file transferred to a readable location or supplied explicitly.
