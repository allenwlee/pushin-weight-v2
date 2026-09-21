# PushinWeight v2 LLM token cost and scaling report

Date: 2026-09-03

Scope: Consolidation of the model-usage, cost, latency, scaling, and caching
discussion from the 2026-09-02/03 working session. This is an analysis report,
not a production invoice or an implementation plan.

## Executive conclusion

At the conversation's 50-post reference workload, the modeled 15-minute loop
used about **210,400 total tokens**: headlines 57.2%, translation 30.9%, and
classification 11.9%. That was a deliberately conservative full-change
scenario based on the then-checked-out DeepSeek V4 Pro headline route and the
old 30-minute/hourly/6-hour/daily headline cadences. It is not a measurement of
one production loop.

Latest `origin/main` has already changed two decisive inputs: headlines now use
DeepSeek V4 Flash, and the four cadences are hourly/daily/weekly/30-day. Holding
the old token-per-call assumptions constant, the frequency-weighted 50-post
model becomes about **129,400 tokens per 15 minutes**: headlines 30.4%,
translation 50.2%, and classification 19.3%. This is still an all-due-
fingerprints-changed ceiling. Semantic-fingerprint reuse can make actual
headline use much lower.

Post enrichment remains approximately linear in the number of unique posts
successfully processed: about **1,076 output tokens per post** and about 1,768
input-plus-output tokens per post under the representative probes. It stops
being linear at the queue envelope: at most 50 current-cycle and 50 carryover
posts can be claimed per cycle. If incoming unique posts rise from 50 to 150
per cycle, steady-state model service is capped at 100, enrichment tokens rise
about 2x rather than 3x, and backlog grows by roughly 50 posts per cycle.

The largest durable savings do not come from a cheaper model alone. They come
from generating rich commentary only where it is needed, reusing work per
unique post, regenerating only materially changed brand-windows, making the
critic conditional, and serving persisted brand narratives rather than calling
an LLM on page load. Dedicated brand pages strengthen the need for demand-based
prewarming and stale-while-revalidate; they do not justify multiplying LLM
calls by every chart tab.

Hillary's local DeepSeek V4 Flash 0731 MXFP4 proved transport and JSON-schema
compatibility, but it did not meet the production headline bar. Its normal
nine-call synthetic chain took 8m23s, and critic calibration produced three
unsupported false accepts, two invalid controls, and one supported false hold.
It should remain a shadow/offline candidate, not the sole production endpoint.

## Evidence labels and revision basis

Numbers in this report use the following labels:

- **Measured**: observed in a saved provider/evaluation artifact or supplied
  directly by the owner.
- **Code constant**: read from repository source or configuration.
- **Provider-reported**: usage or price returned/published by a provider.
- **Estimate**: derived from measurements with an explicit formula.
- **Scenario**: a hypothetical workload or architecture assumption.
- **Reserved maximum**: a safety budget passed to or reserved around a request;
  it is not actual token consumption.

The authoritative checkout was inspected without changing branches:

| Basis | Revision | Important state |
| --- | --- | --- |
| Checked-out report branch | `b3ec46c0d5ff2ae439e654473504b81aaa5ffc2d` | Translation/classification Flash; headline Pro; old cadences |
| Latest remote main inspected with `git show` | `6f3f332bb18c730fbf47e9bf9be2e44b01f54d23` | Translation/classification/headlines Flash; slower headline cadences |

The checkout is behind `origin/main`, so the report presents the
**conversation baseline** and the **latest-main recalculation** separately.
Commit `c211ce9` changed only headline cadence/staleness. Commit `6f3f332`
changed the headline route and accounting rates from Pro to Flash, and also
advanced the editor/critic prompt versions. No claim is made here about which
revision a currently running external service has deployed; that requires
runtime/deployment verification.

Primary repository evidence:

- `config.yaml` and `git show origin/main:config.yaml`
- `render.yaml`
- `x_monitor/translator.py`
- `x_monitor/attribution.py`
- `x_monitor/config.py`
- `monitor/cycle.py`
- `core/models.py`
- `docs/reference/headline-trend-narratives.md` at `origin/main`
- `docs/analysis/2026-09-03-dsv4-gguf-vs-live-models-report.md`
- Saved historical headline evaluation JSON/Markdown under `docs/analysis/`

## Current role routing

| Role | Checked-out conversation baseline | Latest `origin/main` | Included in the three-role split? |
| --- | --- | --- | --- |
| Translation plus EN/ZH commentary | `deepseek-v4-flash` | `deepseek-v4-flash` | Yes |
| Five-dimension classification | `deepseek-v4-flash` | `deepseek-v4-flash` | Yes |
| Headline rank/editor/critic | `deepseek-v4-pro` | `deepseek-v4-flash` | Yes |
| Relevancy | `claude-haiku-4-5` | `claude-haiku-4-5` | No; no session token sample |
| Signal model | `claude-haiku-4-5` | `claude-haiku-4-5` | No; no session token sample |
| X collection | TwitterAPI.io calls | TwitterAPI.io calls | No; billed in API credits, not LLM tokens |

The headline route is intentionally independent from translator/classifier
routing. Consequently, the earlier statement "headlines use Pro" was accurate
for the checked-out conversation baseline but is stale for latest
`origin/main`.

## Harvest and enrichment shape

Production collection is triggered by one Render cron at `*/15 * * * *`.
Collection is not continuous. Queries run sequentially near the start of the
cycle, so a post may be incidentally caught by a later overlapping query, but
posts published after a brand's query normally wait for the next cycle. The
expected scheduling wait is about 7.5 minutes on average and almost 15 minutes
worst case, before enrichment latency.

Translation and classification can continue after collection within the same
job. That produces between-trigger enrichment activity, not reliable between-
trigger collection. Backlog replay and metric refresh can also run later, but
they mostly process already-known posts.

Source-code constants:

| Item | Value | Type |
| --- | ---: | --- |
| Translation batch size | 20 posts | Code constant |
| Classification batch size | 20 posts | Code constant |
| Per-stage request timeout | 90s | Code constant |
| Per-stage attempt budget | 300s | Code constant |
| Concurrent batch workers requested by cycle | Up to 3 | Code constant |
| Current-cycle claims | 50 posts/cycle | Code/config constant |
| Carryover claims | 50 posts/cycle | Code/config constant |
| Total claim envelope | 100 posts/cycle | Code/config constant |
| Retry attempts in translator | 3 | Code constant |

Normal successful-path enrichment calls for `P` processed posts are:

```text
translation calls    = ceil(P / 20)
classification calls = ceil(P / 20)
total calls           = 2 * ceil(P / 20)
```

Application-side concurrency reduces wall time only when the provider has
parallel capacity. It does not reduce tokens. Hillary was configured with one
llama.cpp slot, so concurrent submissions queued rather than increasing
aggregate throughput.

## Token assumptions per call and per post

These are representative historical probes, not guaranteed production means.
Prompt length, source language, post length, multi-brand attribution, repair,
fallback, and retries all change actual usage.

| Work unit | Input | Output | Total | Evidence type |
| --- | ---: | ---: | ---: | --- |
| Headline rank, representative 5-brand call | 2,022 | 520 | 2,542 | Historical observed call |
| Headline editor, representative 5-brand call | 3,237 | 3,150 | 6,387 | Historical observed call |
| Headline critic, representative 5-brand call | 6,734 | 3,314 | 10,048 | Historical observed call |
| Average call in modeled 40-brand headline graph | unavailable separately | unavailable separately | about 8,800 | Estimate from full graph |
| Translation, representative 20-post batch | about 6,240 | 19,554 | about 25,800 | Historical probe/estimate |
| Classification, representative 20-post batch | about 7,590 | 1,975 | about 9,560 | Historical probe/estimate |

One translation sizing observation counted 7,369 input tokens with the same
19,554-token output. It was used when testing whether Hy-MT fit, whereas the
6,240 figure was the representative input used in the session's frequency-
weighted split. They should not be silently averaged.

Approximate full-batch densities from the representative split are:

| Role | Input/post | Output/post | Total/post |
| --- | ---: | ---: | ---: |
| Translation/commentary | 312 | 978 | 1,290 |
| Classification | 380 | 99 | 478 |
| Combined enrichment | 692 | 1,076 | 1,768 |

The 50- and 100-post scenario tables below linearly interpolate partial
batches. Actual call count still rounds up, and a half-full final call retains
fixed prompt overhead, so real usage need not be perfectly linear.

### Reserved output maximums are not usage

| Call | Reserved `max_tokens`/budget | Representative actual output |
| --- | ---: | ---: |
| Translation, 20 posts | 30,000 | 19,554 |
| Classification, 20 posts | 4,096 | 1,975 |
| Headline rank | 2,400 | 520 in the cited sample |
| Headline editor | 8,000 | 3,150 in the cited sample |
| Headline critic | 9,000 | 3,314 in the cited sample |

Translation uses `min(65,536, max(16,384, 1,500 * posts))`. Classification
uses `min(8,192, max(4,096, 200 * posts))`. Those formulas reserve headroom;
using them as actual token totals would overstate spend.

The representative 5-brand rank/editor/critic rows also do not algebraically
reconcile to the separate 40-brand graph estimate because they come from
different packet/fixture assumptions. They are useful sizing examples, not a
single controlled dataset.

## Conversation-baseline 15-minute token model

Assumptions:

- 50 unique posts enriched per loop;
- 20 posts per translation and classification call, producing three calls of
  each type;
- 40 eligible brands;
- a complete 40-brand headline window is 17 calls: one rank, eight editor, and
  eight critic calls;
- every due window has a changed semantic fingerprint;
- old cadences: 1d/30m, 7d/60m, 30d/360m, 365d/1,440m.

The expected number of due headline windows in one 15-minute interval was:

```text
15/30 + 15/60 + 15/360 + 15/1440 = 0.802083 windows
0.802083 * 17 = 13.6354 headline calls
```

| Workload | Calls/15m | Input | Output | Total | Token share |
| --- | ---: | ---: | ---: | ---: | ---: |
| Headlines | 13.64 amortized | about 77,000 | about 43,400 | **about 120,400** | **57.2%** |
| Translation | 3 | about 16,100 | about 48,900 | **about 65,000** | **30.9%** |
| Classification | 3 | about 20,100 | about 4,900 | **about 25,000** | **11.9%** |
| **Total** | **19.64** | **about 113,200** | **about 97,200** | **about 210,400** | **100%** |

The implied complete 40-brand window is about 150,100 tokens: approximately
96,000 input and 54,100 output. That is about 8,800 tokens averaged across its
17 calls.

Two important variants from the conversation were:

| Scenario | Headlines | Translation | Classification | Total | Split |
| --- | ---: | ---: | ---: | ---: | --- |
| No headline fingerprints changed | 0 | 65,000 | 25,000 | 90,000 | 0% / 72.2% / 27.8% |
| 100 posts, old headline assumptions | 120,400 | 130,000 | 50,000 | 300,400 | 40.1% / 43.3% / 16.7% |

This model was a token-volume allocation, not a dollar allocation. In
particular, Pro and Flash had different unit prices, so applying these token
percentages directly to the bill was only a planning proxy.

## Latest-`origin/main` cadence recalculation

Latest `origin/main` uses these headline settings:

| Window | Cadence | Stale after |
| --- | ---: | ---: |
| 1 day | 60 minutes | 120 minutes |
| 7 days | 1,440 minutes | 2,880 minutes |
| 30 days | 10,080 minutes | 20,160 minutes |
| 365 days | 43,200 minutes | 86,400 minutes |

Other revision-sensitive headline controls are:

| Control | Conversation checkout | Latest `origin/main` | Type |
| --- | ---: | ---: | --- |
| Model | DeepSeek V4 Pro | DeepSeek V4 Flash | Code/config constant |
| Editor/critic prompt | v4 / v4 | v6 / v6 | Code/config constant |
| Provider timeout | 45s | 60s | Code/config constant |
| Work lease | 90s | 900s | Code/config constant |
| Worker concurrency | 1 | 1 | Code/config constant |
| Expected brand cap | 40 | 40 | Code/config constant |
| Per-window call cap | 25 | 25 | Reserved maximum |
| Per-window input cap | 700,000 | 700,000 | Reserved maximum |
| Per-window output cap | 160,000 | 160,000 | Reserved maximum |
| Per-window dollar cap | $1.50 | $1.50 | Reserved maximum |

The configured p95 headline target remains 45s even though latest-main's
transport timeout is 60s. These caps bound a run; they are not expected or
measured consumption.

Its due-window expectation per 15 minutes is:

```text
15/60 + 15/1440 + 15/10080 + 15/43200 = 0.262252 windows
0.262252 * 17 = 4.4583 headline calls
new cadence factor / old cadence factor = 0.326964
```

Holding the conversation's 40-brand token-per-window estimate constant:

| Workload | Calls/15m | Input | Output | Total | Token share |
| --- | ---: | ---: | ---: | ---: | ---: |
| Headlines | 4.46 amortized | about 25,200 | about 14,200 | **about 39,400** | **30.4%** |
| Translation, 50 posts | 3 | about 16,100 | about 48,900 | **about 65,000** | **50.2%** |
| Classification, 50 posts | 3 | about 20,100 | about 4,900 | **about 25,000** | **19.3%** |
| **Total** | **10.46** | **about 61,400** | **about 68,000** | **about 129,400** | **100%** |

At the 100-post processing envelope, the analogous latest-main token model is
about 219,400 tokens: **17.9% headlines, 59.3% translation, and 22.8%
classification**.

Old cadence produced 77 due windows/day and 1,309 full-graph calls/day in the
all-changed ceiling. Latest-main cadence produces about 25.176 due windows/day
and about 428 calls/day, a 67.3% reduction in scheduled headline calls before
semantic-fingerprint skips.

Latest-main configured conservative direct-DeepSeek peak/cache-miss prices are
$0.44/M input and $1.32/M output for Flash. The checked-out Pro accounting
rates were $1.32/M input and $3.96/M output. Each Flash rate is one third of the
corresponding Pro rate. Under identical tokens and full-change behavior, the
combined cadence and model-route factor for headline spend is therefore:

```text
0.326964 cadence factor * 1/3 price factor = 0.108988
```

That is an estimated **89.1% reduction in the modeled headline component**
relative to the old Pro/old-cadence ceiling. It is not an observed invoice
reduction: prompt versions changed, cache-hit/off-peak rates may apply, and
actual fingerprint-change rates are unknown. The 50-post total token estimate
falls 38.5% from 210,400 to 129,400 because model price changes do not change
token count and enrichment is unchanged.

## Owner-supplied spend observations

The owner supplied seven hourly DeepSeek spend samples, in cents:

```text
22, 19, 18, 17, 30, 40, 11
```

Derived transparently:

```text
sum                  = 157 cents
mean                 = 157 / 7 = 22.4286 cents/hour
daily run rate       = $0.224286 * 24 = $5.38286/day
30-day run rate      = $5.38286 * 30 = $161.486/month
observed sample span = 11 to 40 cents/hour
```

The working shorthand was therefore **$5.38/day** and **about $161/month**.
This seven-hour extrapolation is not a monthly forecast with confidence bounds.
The owner described it as Flash spend, while the checked-out configuration at
the time still routed headlines to Pro. Because translation/classification
usage is not persisted per call and the provider samples were not tagged by
worker, the report cannot verify which roles those cents covered. The samples
must not be allocated to workers as though the token percentages were invoice
percentages.

## Headline graph, persistence, and brand-count scaling

For `N` eligible brands, one complete window uses:

```text
headline calls(N) = 1 + 2 * ceil(N / 5)
```

| Eligible brands | Rank | Editor | Critic | Total/window |
| ---: | ---: | ---: | ---: | ---: |
| 20 | 1 | 4 | 4 | 9 |
| 40 | 1 | 8 | 8 | 17 |
| 44 | 1 | 9 | 9 | 19 |
| 100 | 1 | 20 | 20 | 41 |

Latest configuration has `per_brand_expected_max_brands: 40`; snapshot
construction uses that as its brand cap. Adding Grok, OpenAI, Claude, and Gemini
to a fully occupied 40-brand manifest would therefore require an explicit cap
and budget review. Without it, the headline snapshot should fail closed above
the configured cap rather than silently execute the hypothetical 19-call
graph.

Current headline persistence already includes:

- one immutable `TrendNarrativeRun` per cutoff/window;
- a `TrendNarrativeProviderCall` ledger with input/output tokens and latency;
- immutable `BrandTrendNarrative` outcomes and last-good links;
- one `TrendNarrativeVisibleRun` pointer per window;
- one bounded `TrendNarrativeWorkSlot` per window.

Browser reads use PostgreSQL and do not call the provider. However, visibility
and work-slot state are still organized around an atomic all-brand run. Fully
independent on-demand brand generation needs per-brand visible/work-slot state
so MiniMax can advance without waiting for every other brand.

## Three-times post-volume scenario

Adding brands does not by itself make every enrichment call three times larger.
DeepSeek work increases when the new queries produce additional unique,
newly-persisted posts requiring enrichment. Duplicate search results and
engagement-only refreshes do not require fresh translation/classification.
Multi-brand posts may enlarge classifier output somewhat because they emit
results per attributed brand. Repairs, per-post fallback, and retries can make
growth superlinear.

Ignoring the queue envelope, representative enrichment output is:

```text
output tokens ~= 1,076 * unique posts processed
total tokens  ~= 1,768-1,800 * unique posts processed
```

The lower total is the full-batch per-call density; 1,800/post is the rounded
50-post loop assumption, which includes the partially filled third batches.

The actual two-lane claim policy changes the immediate result:

| Incoming/processed situation | Translation calls | Classification calls | Modeled enrichment output | Consequence |
| --- | ---: | ---: | ---: | --- |
| 20 processed | 1 | 1 | about 21,500 | Below caps |
| 50 fresh processed | 3 | 3 | about 53,800 | Fills current-cycle lane |
| 100 processed as 50 current + 50 carryover | 5 | 5 | about 107,600 | Fills total envelope |
| 150 unique arrivals/cycle, steady state | at most 5 | at most 5 | at most about 107,600 served/cycle | About 50 posts/cycle added to backlog |

The first 150-post spike may process only the 50 current-cycle claims if there
is no carryover yet, leaving 100 pending. Once carryover exists, the worker can
serve 50 old plus 50 current per cycle; with 150 continuing to arrive, backlog
grows by about 50 per cycle.

An earlier conversational example said a rise from 20 to 60 could process all
60 in the same loop. Current code's disjoint 50-current/50-carryover policy
corrects that: at most 50 newly created posts are claimed from the current
cycle, and the remaining 10 become carryover. Token growth remains broadly
linear over eventual successful processing, but freshness no longer does.

Using latest-main's 50-post token model, a 50-to-150 arrival increase with the
100-post service ceiling changes modeled provider tokens from about 129,400 to
219,400 per loop if headline brand count and change behavior stay constant.
That is about **1.70x**, not 3x. Enrichment itself is 2x; the amortized headline
component remains about 39,400. The missing work is accumulated backlog, not
free capacity.

If all 150 posts could be processed with no cap, the same fixed-headline model
would be about 309,400 tokens, or 2.39x the 50-post total. If four brands also
raised a permitted 40-brand headline graph from 17 to 19 calls, a rough
call-proportional headline estimate would rise from 39,400 to about 44,000
tokens; packet sizes prevent treating this as exact.

## Hillary local GGUF versus hosted models

The local artifact was:

- `ggml-org/DeepSeek-V4-Flash-0731-GGUF`, MXFP4;
- revision `f559fd6005309e5f6bd650342ee8711ff189b3b8`;
- served as `dsv4-flash-0731-mxfp4` on Hillary;
- about 155 GB decimal/144 GiB on disk;
- 65,536-token runtime context;
- one inference slot, full Metal offload, F16 K/V cache;
- approximately 147 GiB model RSS.

Basic raw JSON and PushinWeight rank/editor/critic schema probes passed at
about 27 output tokens/s. The full saved evaluation reported 37,595 input and
16,010 output tokens across 17 sequential calls, with local billing `$0.00`.
Its `$0.113025` accounted-cost field applied the historical hosted Pro pricing
manifest and is not a local cash charge.

Measured latency:

| Synthetic packet | Rank | Editor | Critic | Complete chain |
| --- | ---: | ---: | ---: | ---: |
| 1 brand | 9.3s | 24.6s | 27.7s | 1m02s |
| 3 brands | 13.5s | 59.3s | 68.1s | 2m21s |
| 5 brands | 23.3s | 2m09s | 2m28s | 5m00s |

Additional local observations:

- 17 calls including eight critic controls: **11m52s**;
- normal nine-call synthetic headline chain: **8m23s**;
- normal-chain output: **11,512 tokens**;
- generation: about **26.5 tokens/s**;
- prompt processing: about **364 tokens/s**;
- slowest call: **2m28s**;
- eight small critic-control calls: **21.8-28.3s each**.

The conversation's stored hosted-Pro comparison summarized a normal chain at
about 1m29s and 9,769 output tokens. A separate closest repository baseline,
`2026-08-27-070446`, used 17 hosted Pro calls, cost $0.068524, reported 17,769
input and 11,381 output tokens, and had 1.653-21.930s latency with 6.458s mean.
These are different fixtures and are not a paired benchmark.

Local quality/calibration failed despite mechanically complete ordinary
outputs:

- three unsupported false accepts: causality, mistranslation, unsafe embedded
  instruction;
- two mechanically invalid control decisions: event conflation and invented
  detail;
- one supported false hold;
- activation flags `calibration_pass=false` and
  `zero_unsupported_publications=false`.

The capacity conclusion was also negative:

- a 40-brand window extrapolated from the five-brand local result was roughly
  38-40 minutes, missing the old 30-minute 1-day cadence;
- a 20-post classifier's 1,975 output tokens require about 75s of generation at
  26.5 tokens/s before prompt/overhead, already near the 90s request timeout;
- three to five classifier batches were estimated at about 4-8 minutes
  sequentially, versus a five-minute stage budget;
- a 19,554-output-token translation batch needs about 12m19s of generation;
- three such translation batches were estimated at about 37 minutes.

Latest-main's slower headline cadence relaxes queue pressure, but it does not
fix the local translator/classifier timeout mismatch or the critic-calibration
failure. Parameter count was not the missing headline property: the needed
capability is evidence-sensitive judgment, especially in the critic.

## Same-shape model-swap estimates discussed

These projections used the $5.38/day owner-supplied run rate and token shares
as a spend-allocation proxy. They are not additive to the later origin/main
cadence/model changes and should be rebased after worker-tagged billing exists.

| Scenario discussed | Estimated saving | Estimated remaining spend | Important caveat |
| --- | ---: | ---: | --- |
| Keep headline Flash; Ling 3.0 Flash translation; free LFM2.5-2.6B classification | 30.6% | $3.74/day; about $112/30d | Free endpoint availability/limit; Ling lacks schema enforcement |
| Ling 3.0 Flash for translation and classification, paid-only | 25.7% | $4.00/day; about $120/30d | Must pass both task evaluations |
| Theoretical cheaper headline replacement too | about 60% | about $2.16/day | No cheaper headline model had passed PushinWeight evaluation |
| Free classification + Mistral Nemo translation + free/local rank/editor + hosted critic | about 62% | about $2.06/day; $61.70/30d | Changes role placement and packet size, not strictly same shape |
| Mistral translation/free classification while all headlines stay hosted | not stated as a percentage | about $3.42/day | Token-share proxy |

The unchanged-shape Ling estimate assumed a 262K context and 32K maximum
output, enough for the current 30K reservation, but no native schema
enforcement. Mistral Nemo was estimated about 79% cheaper than DeepSeek V4
Flash for translation at the observed input/output mix, but its 16,384 maximum
completion does not safely fit the observed 19,554-token 20-post output; the
suggested experiment used 10-post packets.

The 2026-09-03 OpenRouter research snapshot reported:

| Model | Input $/M | Output $/M | Proposed role/constraint |
| --- | ---: | ---: | --- |
| Mistral Nemo | $0.019 | $0.030 | Translation challenger; 10-post packets; formatting but no schema enforcement |
| Hy-MT2 30B A3B | $0.074 | $0.295 | Translation specialist; 8K context/4K output; does not fit current packet |
| Hy-MT2 1.8B | $0.044 | $0.177 | Cheaper, but no enforced structured output in the session research |
| DeepSeek V4 Flash 0731 on OpenRouter | $0.050 | $0.160 | Hosted headline candidate in that catalog snapshot |
| GLM 5.3 Flash | $0.075 | $0.250 | Temporary-price snapshot |
| Qwen3.8 Flash | $0.150 | $0.470 | More expensive than the cited Flash alternatives |
| LFM2.5-2.6B free | $0 | $0 | Classifier candidate; schema support, but shared free-tier risk |
| MiniMax M3 free | $0 | $0 | Rank/draft candidate; JSON formatting, not schema enforcement |

These OpenRouter prices are a point-in-time external catalog snapshot and are
not the same route as the direct-DeepSeek accounting prices in `config.yaml`.
They must be rechecked before a purchasing or routing decision.

Hy-MT 30B could be tried with five-post literal-translation packets. At 50
posts/cycle that is 10 translation calls/cycle, or 960/day over 96 cycles. It
cannot replace the full current translator unchanged because the latter also
produces English and Chinese analyst commentary, pragmatic rendering, language
detection, and optional cultural annotation.

The session's OpenRouter free-tier snapshot described a shared 50-request/day
limit without purchased credit and 1,000/day after at least $10 of purchased
credit. At 50 posts/cycle, current translation plus classification is six calls
per cycle, or 576/day. Classification alone is about 288/day. Under the old
headline cadence, rank plus editor could add 693/day in the all-changed ceiling;
under latest-main cadence, the corresponding estimate is about 227/day. At the
100-post envelope, enrichment alone is 960 calls/day. Every free route therefore
needs validation, rate-limit handling, and a paid fallback.

## Call-shape redesign estimates

The discussion proposed changing scaling from:

```text
full enrichment * every post
+ editor and critic * every brand * every due window
```

to:

```text
cheap work * new unique posts
+ rich work * promoted posts
+ strong headline work * materially changed active brand-windows
```

The proposed levers were:

1. Deduplicate exact and near-duplicate posts before costly work; perform local
   language/brand/importance intake.
2. Translate only missing directions. Preserve bilingual commentary as a
   settled initial-display requirement, but provide an auditable algorithmic
   commentary baseline and reserve richer LLM commentary for feed-visible,
   prefetched, high-engagement, or headline-evidence posts.
3. Cascade classification: compact common labels for all posts, specialist
   axes only when triggered, and strong-model escalation only for ambiguity.
4. Regenerate only materially changed brand-window fingerprints; build long
   windows from persisted aggregates/deltas.
5. Use one strong final writer where possible; validate IDs/numbers/schema in
   code; invoke the semantic critic for risky causal/event/quotation/low-
   coverage cases and audit a random safe sample.
6. Generate for visible/active brands first and retain last-good content for
   unchanged or long-tail brands.

### Explicit selective-work scenarios

The session's reference shape can be parameterized without pretending that
every page view creates work:

```text
new tokens = H * h + T * v + C

H = amortized headline tokens
h = fraction of headline brand-windows that are both hot/demanded and changed
T = current rich translation/commentary synthesis tokens
v = fraction of unique posts ever promoted to rich LLM commentary
C = classification tokens, retained for all processed posts
```

Here `v` counts unique posts that are prefetched/displayed/promoted at least
once, not page views. A cached result reused by 1,000 viewers still counts once.
The formula treats the current combined translation/commentary call as the
selectively invoked rich path; it does not separately measure the minimum cost
of literal translation if that remains on a different LLM for every post.
Classification remains at 100% in all three scenarios.

Using the conversation baseline `H=120.4k`, `T=65k`, and `C=25k` tokens:

| Estimate | `h` | `v` | New tokens/15m | Reduction from 210.4k |
| --- | ---: | ---: | ---: | ---: |
| Conservative | 30% | 50% | **93.62k** | **55.5%** |
| Likely working case | 15% | 25% | **59.31k** | **71.8%** |
| Aggressive | 5% | 10% | **37.52k** | **82.2%** |

Latest-main cadence alone changes the headline term to about `H=39.4k` and the
unchanged 50-post total to about 129.4k. Applying the same selective fractions:

| Estimate | New tokens/15m | Further reduction from 129.4k |
| --- | ---: | ---: |
| Conservative | **69.32k** | **46.4%** |
| Likely working case | **47.16k** | **63.5%** |
| Aggressive | **33.47k** | **74.1%** |

These are sensitivity estimates, not forecasts. The missing empirical inputs
are the actual hot-and-changed fraction `h`, rich-promotion fraction `v`, and
the cost of any cheaper/deterministic baseline used for posts outside `v`.

The planning ranges discussed, assuming rich commentary for roughly 20-30% of
posts and critic escalation for roughly 10-25% of candidates, were:

| Redesign depth | Estimated reduction | Illustrative spend from $5.38/day |
| --- | ---: | ---: |
| Conservative | 35-55% | Not separately calculated in session |
| Selective enrichment/recommended | 65-80% | about $1.10-$1.90/day |
| Top-brand generation plus lazy long tail | 80-90% | Not separately calculated in session |

If only 10% of brand-window combinations are requested, purely demand-shaped
generation was estimated to eliminate about 90% of headline work. Applied to
the old 57.2% headline token share, that is about **51% of total tokens**. This
is a scenario bound, not a forecast: dedicated brand pages mean important
brands must be prewarmed, not truly cold.

## On-demand persistence and dedicated brand pages

A headline request should never mean one generation per user. The durable cache
identity discussed was approximately:

```text
brand + window + facts fingerprint + prompt/model version
```

The first requester reserves one deduplicated job. The bilingual result,
evidence references, verification state, and last-good link persist in
PostgreSQL. A second requester five minutes later receives the saved result at
database latency if the fingerprint is unchanged. If new facts exist, the page
serves last-good immediately while exactly one refresh runs. Locale changes
reuse the same bilingual object.

Brand-dedicated bookmark destinations change the recommendation from cold
on-demand to:

```text
seed once -> prewarm active brands -> stale-while-revalidate -> cold refresh on demand
```

The default brand brief must be ready before navigation. Page load should read
the persisted brief, compare fingerprints, and enqueue a priority refresh only
when stale. Chart tabs such as sentiment, post type, discourse, language, and
nationalism are deterministic database aggregations and should not each create
a full LLM narrative. One cached brand brief can include only materially
important dimension observations; a tab without one can use an algorithmic
caption or a separately cached optional deep insight.

### Durable hot-list recommendation

Use PostgreSQL as the demand-policy source of truth with one row keyed by
`brand + window`. Store a `hot_until` timestamp/TTL rather than only an
`is_hot` boolean, plus last-requested and aggregate-demand timestamps/counters
needed to renew the TTL. Keep explicit reasons—operator pin, user follow, paid
subscription, launch watch—separate from derived recent-demand/popularity
state so an expiry cannot erase an intentional pin and an old page view cannot
masquerade as a subscription.

Redis should hold only short-lived dedupe locks/reservations and queue
coordination, never the sole hot-list truth. Per-brand visible narrative and
per-brand work-slot state should also be separate from demand policy: hotness
decides what to prewarm; visible/work state decides what is safe to serve and
which cutoff owns generation. This separation permits rebuilding Redis without
losing user intent or publication correctness.

The resulting cost unit is one generation per materially changed active
`brand-window-fingerprint`, shared across all employees and page views—not one
generation per page view and not one per chart tab.

## Measurement gaps and recommended instrumentation

The application currently persists input tokens, output tokens, and latency for
headline provider calls, but **does not persist translation/classification
token usage per call**. That is the primary blocker to invoice-grade allocation.

Add a common provider-call ledger for every LLM role with at least:

- provider, endpoint class, exact model, prompt/version, role, and stage;
- cycle/run/request identity and retry/fallback ordinal;
- batch post count, unique-post count, attributed-brand count, and payload
  bytes;
- input, cached-input, output, reasoning, and total tokens when reported;
- reserved max tokens separately from actual tokens;
- time to first token, total latency, timeout, queue wait, and local/provider
  throughput;
- schema-valid, semantically accepted, repaired, retried, rate-limited,
  failed, and fallback outcomes;
- provider price revision and computed actual/estimated dollars.

Also persist per-cycle denominators:

- raw fetched results, unique inserts, posts needing each enrichment stage;
- current/carryover claims, completions, retries, backlog size, and oldest age;
- changed versus unchanged headline fingerprints by window;
- eligible, hot, pinned, subscribed, generated, held, and last-good brands;
- cache hit/miss and provider calls avoided by reuse.

Recommended next measurements:

1. Rebaseline at latest `origin/main` for at least 24 hours with worker-tagged
   provider usage and actual deployed revision recorded.
2. Report p50/p95/p99 tokens and latency per role and batch size, not only one
   representative probe.
3. Measure semantic-fingerprint change rates by brand/window; this determines
   headline cost more than nominal cadence.
4. Measure commentary promotion and critic-escalation rates before using the
   20-30% and 10-25% redesign assumptions.
5. Replay frozen bilingual translation, classifier, writer, and critic cohorts
   against every cheaper route; cost comparisons without quality/fallback rates
   are incomplete.
6. For Hillary, measure sustained concurrent throughput, thermal stability,
   power, queue delay, and restart/failure behavior in addition to tokens/s.

Until this telemetry exists, keep token models, observed spend, reserved
budgets, provider prices, and architectural scenarios in separate columns. The
current numbers are good enough to identify leverage and capacity failure, but
not to reconcile a provider invoice to individual workers.
