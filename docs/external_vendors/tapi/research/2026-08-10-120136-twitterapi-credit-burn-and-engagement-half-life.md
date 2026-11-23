# TwitterAPI credit burn, quote recheck economics, and engagement half-life

### written by Grok 4.3

**Generated:** 2026-08-10 12:01 JST  
**Repo:** `pushin-weight-v2` on `fuchitalee`  
**Scope:** Why TwitterAPI credits burn faster than expected; whether the cursor window bug is the cause; what the intended quote/repost recheck is for; how to size a cheaper metrics re-poll using engagement half-life from live X probes.

**Primary sources (in-repo):**

- `docs/external_vendors/twitterapi_docs/twitterapi_index.md` — pricing model
- `docs/reference/harvester-cycle-cost-table.md` — expected search cost per cycle
- `docs/reference/twitterapi-io-calls.md` — call inventory (partially stale on QT wiring)
- `docs/operations/cursor-vs-insert-gap-diagnosis.md` — 2h lookback waste (Aug 5–6)
- `monitor/quote_tweets.py`, `monitor/cycle.py`, `x_monitor/apify.py`, `config.yaml`
- TwitterAPI.io dashboard call log (user-provided sample, 2026-08-08 ~10:05–13:35 JST)
- Live X keyword-search age-bucket probes (2026-08-10 ~02:55 UTC)

---

## 1. Executive summary

Credits are burning faster than the harvester cost table predicts mainly because **every 15-minute cycle re-polls a large set of recent official/staff parent posts via `GET /twitter/tweets` (batched tweet-by-ID)** to refresh `quote_count`. That path is billed at **15 credits per returned tweet** — the same rate as new search results — so re-reading ~100–150 IDs every cycle costs more than the main search harvest itself.

In a representative dashboard sample (~100 recent calls on 2026-08-08):

| Endpoint | Share of credits |
|---|---:|
| `/twitter/tweets` (QT metrics refresh) | **~84%** |
| `/twitter/tweet/advanced_search` (main harvest) | **~15%** |
| `/twitter/tweet/quotes` (actual quote bodies) | **~1%** |

This is **not** primarily the old cursor start/end-time problem (wide re-search of the same 2h window). That issue was real on Aug 5–6 and was mitigated by `max_lookback_hours: 0.25`. The dominant ongoing burn is the **intended but unbudgeted quote-tweet channel**, wired into the v2 cycle on **2026-07-27** (`dc2ccbd`), which the cost table never modeled.

**Engagement half-life (from X age-bucket probes, conditioned on posts that get real engagement):** most of a post's like/RT/quote totals land in **hours, not days**. Practical design targets:

| Milestone | General X | LLM / AI X |
|---|---|---|
| ~50% of lifetime engagement | ~1 hour | ~2 hours |
| ~75% | ~4 hours | ~8 hours |
| ~95% | ~18 hours (~1 day) | ~36 hours (~1.5 days) |

A **once-per-post metrics re-poll at T+24h (general) / T+48h (LLM)** can preserve "silent agreement" signal (rising likes/RTs/quotes on parents) at roughly **~2x tweet budget**, unlike re-polling the same parents every 15 minutes for 14 days.

---

## 2. Pricing model (TwitterAPI.io)

From `twitterapi_index.md` (scraped pricing knowledge):

| Rule | Value |
|---|---|
| Tweet-shaped results | **15 credits per returned tweet** |
| Applies to | `advanced_search`, `quotes`, **`/twitter/tweets` (by IDs)**, timelines, mentions, etc. |
| Per-call floor | **15 credits** even for 0–1 results |
| Currency | 100,000 credits = $1 USD |
| Worked examples | 4 tweets → 60; 0–1 → 15 floor; 50 tweets → 750 |

Dashboard rows match the model exactly (e.g. 50 items → 750 credits; 37 → 555; empty → 15).

**Implication:** there is no cheap "metrics-only" price. Refreshing `quoteCount` via `/twitter/tweets` costs the same per ID as fetching a new search hit.

---

## 3. What we thought we would spend (docs)

### 3.1 Harvester cycle cost table

`docs/reference/harvester-cycle-cost-table.md` models **one cycle** as ~7 search-style calls, ~86 results, **~1,290 credits/cycle**:

| Period | Credits (table) | USD |
|---|---:|---:|
| Per cycle | ~1,290 | ~$0.013 |
| Per day (96 cycles) | ~123,984 | ~$1.24 |
| Per month (30d) | ~3.72M | ~$37 |

Notes on that doc:

- It models **only** A / B1–B3 / C1–C3 style search volume.
- It **omits** the quote-tweet channel entirely.
- Call A is described as `/twitter/list/tweets`; live code uses **`advanced_search` with `list:<id>`**.
- The table's "~$18/mo" line is inconsistent with its own math (~$37).
- `daily_ceiling: 333` in `config.yaml` is a **stale placeholder** and is **not enforced**.

### 3.2 Budget guard drift

`x_monitor/run.py` still uses:

- `_CREDITS_PER_ADVANCED_SEARCH_PAGE = 300` (flat page estimate)
- `_BUDGET_HARD_CAP_CREDITS = 2_000_000` (single-run ceiling)

Live pricing is **15/tweet**, not 300/page. The guard does not cap daily spend and does not count `/twitter/tweets` QT refresh.

### 3.3 Call inventory staleness

`docs/reference/twitterapi-io-calls.md` still says quotes / by-IDs are **"NOT currently wired in the v2 cycle."** That is false as of 2026-07-27: `CycleRunner.run()` calls `run_quote_tweet_channel()` after post-fetch.

---

## 4. Dashboard evidence (2026-08-08)

User-provided TwitterAPI dashboard sample (~last 100 calls, ~10:05–13:35 JST):

| Endpoint | Calls | Credits | Items | % credits |
|---|---:|---:|---:|---:|
| `/twitter/tweets` | 34 | 24,945 | 1,663 | **84.0%** |
| `/twitter/tweet/advanced_search` | 51 | 4,500 | 276 | 15.2% |
| `/twitter/tweet/quotes` | 15 | 240 | 7 | 0.8% |
| **Total** | 100 | **29,685** | 1,946 | 100% |

Patterns:

- `/twitter/tweets` appears in **bursts of 2–6 x 50-ID chunks** → ~**2.4 chunks/cycle ≈ ~120 parent IDs** refreshed every 15 minutes.
- `advanced_search` often returns small or empty pages (many **15-credit floors**) — consistent with a **narrow ~15-min search window**, not a 2h re-fetch flood.
- Actual quote-body fetches are rare and cheap in this window (growth gating working).

Rough extrapolation if this mix holds: on the order of **~$2/day** from the sample density — with **search only ~15%**. Absolute daily total needs a full 24h pull from the vendor dashboard API; the **mix** is the load-bearing finding.

---

## 5. Code path that spends the money

### 5.1 Main harvest (minority of credits when healthy)

- Cron: `render.yaml` → `python manage.py run_cycle --scheduled` every 15 minutes.
- Plans A + B1/B2/B3 + C1/C2/C3 via `plan_calls()`.
- Fetches via `TwitterApiClient.run_search` → `GET /twitter/tweet/advanced_search`.
- Default caps: ~50 results/call (C1 raised to 150); `max_lookback_hours: 0.25`; `cursor_overlap_seconds: 60`.

### 5.2 Quote-tweet channel (majority of credits)

Wired in `monitor/cycle.py` after post-fetch:

```
run_quote_tweet_channel(...)
  → capture_official_quote_tweets   # every cycle
  → capture_nonofficial_quote_tweets_daily  # once per UTC day
```

Implementation: `monitor/quote_tweets.py`

**Official regime (every cycle):**

1. Load official/staff parent posts from last **`track_recency_days` (default 14)**.
2. `api.get_tweets_by_ids([...])` → `GET /twitter/tweets`, chunk size **50** → **750 credits per full chunk**.
3. If `quote_count` grew by ≥ **`official_delta` (default 5)**, call `get_quote_tweets` (capped by **`official_call_budget`**, default 20).

**Daily non-official regime (once/UTC day):**

1. Up to **500** non-staff parents from last **`daily_recency_days` (default 7)**.
2. Same by-ID refresh; QT fetch when delta ≥ 1; **`daily_call_budget`** default 50.

**Live DB snapshot (prod shadow, during investigation):**

| Set | Count |
|---|---:|
| Official/staff handles | ~74 |
| Official/staff posts in last 14 days | **~135** |
| Non-official posts last 7 days | ~24,708 (daily pass caps at 500) |

**Steady-state cost of official refresh alone:**

```
ceil(135 / 50) ≈ 3 chunks
≈ (50+50+35) × 15 ≈ 2,025 credits / cycle
× 96 cycles/day ≈ 194,400 credits/day ≈ $1.94/day ≈ $58/month
```

That is **before** search and before daily non-official refresh — and **larger than the entire search budget** in the cost table (~$37/mo).

Client path constants (`x_monitor/apify.py`):

- `TWEETS_BY_IDS_PATH = "/twitter/tweets"`
- `TWEETS_BY_IDS_CHUNK = 50`
- `QUOTES_PATH = "/twitter/tweet/quotes"`

---

## 6. Why recheck exists (product rationale)

Main search (A/B/C) matches **text / list membership**. It cannot see:

1. **Quote with almost no text** (e.g. thumbs-up emoji on "DeepSeek's latest is amazing!") — no brand keywords in the quote body.
2. **Bare repost / pure RT** (no comment) — silent agreement with a post we already care about.

When a parent is first ingested, `quote_count` / `retweet_count` are frozen at insert time. Popular parents age out of the short search window; **later agreement never reappears** unless something re-observes growth.

The recheck design:

1. Re-read current counters on tracked parents.
2. Only if growth clears a threshold, fetch actual quote tweets and attribute/persist them.

On v1 this was a substantial share of stored volume (~24% cited in module docs). On v2 it was **missing until 2026-07-27**, then ported for parity (`dc2ccbd`).

**The feature is intentional and valuable.** The failure mode is **polling frequency x set size x same 15-credit unit price**, not a broken product idea.

---

## 7. Was it broken before, or did something change?

| Period | What happened |
|---|---|
| Pre–2026-07-27 (v2) | QT channel **not wired** into `monitor/cycle.py` → no by-ID recheck spend on v2 |
| 2026-07-27 | QT channel ported and wired; every cycle + daily regimes start spending |
| ~2026-08-04 | 402 credit exhaustion; topup; recovery cohort (high post volume resumes) |
| 2026-08-05–06 | **Cursor / 2h lookback** waste: re-search same wide window, ~989 fetched / 86 inserted in one diagnosed cycle |
| 2026-08-06 | `max_lookback_hours: 0.25` fix (Option A) |
| 2026-08-08 | Dashboard mix shows **QT by-ID still dominating** after lookback fix |

**Answer to "never a concern until 3–4 days":**

- **(A) partly:** on v2 the recheck simply **did not run** for a long stretch.
- **(B) also:** after wiring, **search over-burn** (cursor floor) + recovery volume made the allotment run out fast; once search was tightened, **QT recheck remained** as the large ongoing bill the cost models never counted.

So: not "recheck is broken"; **recheck is working and expensive**, and recent 402s were a **compound** of unmodeled QT spend + temporary search waste + post-topup traffic.

---

## 8. Is it the cursor problem again?

**No — not as the primary credit story after the 0.25h fix.**

### Cursor bug (Aug 5–6) signature

- `max_lookback_hours: 2` clamped floors → every cycle re-searched ~2 hours.
- Cursors often not advancing → same window repeatedly.
- **~989 tweets fetched / 86 inserted** (~9% keep rate).
- Cost lived on **`advanced_search`** (~15k credits/cycle in that diagnosis).

### Current config

```yaml
cycle:
  cursor_overlap_seconds: 60
  max_lookback_hours: 0.25   # one cycle window
```

Live `call_state` rows for main A/B/C calls were advancing through **2026-08-08 04:30 UTC** (near credit cutoff). With the 15-min clamp, even a stale cursor only opens a bounded window.

### Aug 8 dashboard signature

- Credits dominated by **`/twitter/tweets`**, not search.
- Search mostly small/empty pages (floors), not full multi-page 2h dumps.

| Waste mode | Endpoint | Mechanism |
|---|---|---|
| Cursor window bug | `advanced_search` | Same **time window** searched again |
| QT metrics recheck | `/twitter/tweets` | Same **parent IDs** re-read every 15 min for 14 days |

Related economics (pay for returns, not for new DB rows) — **different mechanism**.

---

## 9. "Same posts multiple times?" — yes

Recheck is high relative to new-post fetch because:

1. **Search** only looks at ~**15 minutes** of new activity → tens of new posts/cycle when healthy.
2. **Official recheck** reloads **~100–150 parent IDs from the last 14 days**, every cycle, whether or not anything changed.
3. Billing is **per returned ID**, not per new quote body and not per DB insert.
4. Actual quote bodies are fetched only on growth — cheap in the sample; the **metrics poll** is the bulk.

So yes: **the same parents are re-fetched many times per day for two weeks.** That is why recheck can look ~4x (or more) the initial search bill.

---

## 10. Engagement half-life (X API probes, 2026-08-10)

### 10.1 Method

- Tooling: X advanced keyword search with `since_time` / `until_time` age buckets, `Latest` mode.
- Condition: `min_faves:10` (general) or `min_faves:5` (LLM keyword set) so samples are not pure zeros.
- Metrics: median likes and **likes per hour of age** (velocity) by bucket.
- **Limitation:** single snapshot totals only — no true per-post time series. Young `min_faves` buckets bias toward **fast risers**. Treat percentiles as **operational estimates**.

LLM query family:

```
(chatgpt OR claude OR deepseek OR grok OR qwen OR "language model" OR llm
 OR openai OR anthropic OR llama) lang:en -filter:replies -filter:nativeretweets
```

### 10.2 Observed velocity (conditioned on posts that cleared a floor)

**General X (`min_faves:10`):**

| Age bucket | Median likes (n≈10) | ~Likes / hour of age |
|---|---:|---:|
| 0–1h | ~24 | ~45–50 / h |
| 1–3h | ~18 | ~9 / h |
| 3–6h | ~23 | ~5 / h |
| 6–12h | ~46 | ~5 / h |
| 12–24h | ~49 | ~2.7 / h |
| 24–48h | ~49 | ~1.4 / h |
| 48–72h | ~34* | ~0.6 / h |
| 3–7d | ~55 | ~0.5 / h |

\*Noisy thin sample.

**LLM / AI X (`min_faves:5` + LLM keywords):**

| Age bucket | Median likes | ~Likes / hour |
|---|---:|---:|
| 0–1h | ~11 | ~40+ / h |
| 1–3h | ~14 | ~7 / h |
| 3–6h | ~9 | ~2 / h |
| 6–12h | ~16 | ~1.7 / h |
| 12–24h | ~15 | ~0.8 / h |
| 24–48h | ~23 | ~0.6 / h |
| 48–72h | ~24 | ~0.4 / h |
| 3–7d | ~20 | ~0.2 / h |

### 10.3 Estimated time to share of lifetime engagement

Population: posts that get **meaningful** engagement (not the zero-engagement firehose).

| Milestone | General X | LLM / AI X |
|---|---|---|
| **~50%** | **~45 min – 2 h** (point: **~1 h**) | **~1 – 3 h** (point: **~2 h**) |
| **~75%** | **~3 – 6 h** (point: **~4 h**) | **~6 – 12 h** (point: **~8 h**) |
| **~95%** | **~12 – 24 h** (point: **~18 h / ~1 day**) | **~24 – 48 h** (point: **~36 h / ~1.5 days**) |

**Subject-matter difference:** LLM discourse has a **slightly fatter 1–2 day tail** (model drops, threads, tool demos, delayed RTs). It is **not** a multi-week slow burn for the median post. Multi-day growth is the exception (major launches / mega-virals).

**Caveats:**

1. Not true half-lives (no longitudinal series).
2. `min_faves` selection bias at young ages.
3. n≈10 per bucket — order of magnitude solid; exact minutes not.
4. Views may dribble after likes/RTs plateau; this analysis targets **like/RT/quote counts** (re-poll object).

### 10.4 What this means for re-poll cadence

| Purpose | Suggested re-poll |
|---|---|
| Default general parent | **T + 24 hours** |
| LLM / AI parent | **T + 48 hours** |
| Optional second pass (official / high engagement only) | **T + 72 hours** |
| Full-DB every 15 days forever | **Wrong X** for max attention; cost grows with history |

**Once-per-post metrics re-poll near plateau ≈ +1x tweet cost → total ~2x**, if each post is re-polled O(1) times — not "entire DB every 15 days as it grows."

---

## 11. Options (product + cost)

### A. Keep QT feature, stop uniform full-set every-15-min poll (recommended first step)

| Lever | Change | Effect |
|---|---|---|
| Who | Official-only, or high-engagement parents | Smaller set |
| When hot | Every 1–4 cycles if count rising | Spend on posts that matter |
| When cold | Hourly or daily | Huge cut |
| How long | 14d → 2–3d for most | Smaller set |
| Threshold | Keep delta gating for quote **bodies** | Already helps |

### B. Counts as signal (often enough)

Store rising `quote_count` / `retweet_count` / likes on the parent without expanding every emoji quote into its own row. Fetch quote bodies only on large deltas or strategic parents.

### C. One-shot at first sight + slow recheck

On first ingest of official/high-signal parents: one metrics refresh (and optional first page of quotes), then slow schedule (24–48h), not every cycle.

### D. Search cannot fully replace recheck

| Case | Search alone? |
|---|---|
| Quote text still says brand name | Often yes |
| Quote is only emoji / empty | **No** |
| Pure RT, no comment | **No** |

### E. Doc + budget hygiene

1. Add QT rows to `harvester-cycle-cost-table.md`.
2. Fix "not wired" claims in `twitterapi-io-calls.md`.
3. Align pricing units to **15/tweet**.
4. Enforce a real daily credit ceiling (log `n_results × 15`, floor 15; halt QT and/or search when exceeded).
5. Log estimated credits from `TwitterApiClient._request_log` per cycle.

---

## 12. Recommended target design (credit-aware)

1. **Tier A (official + already high engagement):** metrics refresh every 1–4 cycles for first 48–72h.
2. **Tier B (other tracked parents):** one metrics refresh at **T+24h** (general) / **T+48h** (LLM).
3. **Everyone else:** no by-ID recheck; rely on search if quote text matches brands.
4. **Always:** only pull quote **posts** when count delta clears a bar.
5. **Dashboard split:** report "new search credits" vs "metrics recheck credits" every cycle so this never goes invisible again.

Expected economics if recheck becomes ~1x search instead of ~4x:

| Component | Rough daily credits | Rough $/day |
|---|---:|---:|
| Search (healthy ~15-min windows) | ~30k–125k | ~$0.30–$1.25 |
| Metrics recheck (once near plateau) | ~same order as search if O(1) per post | ~$0.30–$1.25 |
| Quote bodies (gated) | small | small |
| **vs today (official every 15 min x 14d)** | recheck alone ~190k+ | ~$1.90+ before search |

---

## 13. Related files

| Path | Role |
|---|---|
| `docs/external_vendors/twitterapi_docs/twitterapi_index.md` | Pricing + dashboard backend API notes |
| `docs/reference/harvester-cycle-cost-table.md` | Search-only cost model (needs QT rows) |
| `docs/reference/twitterapi-io-calls.md` | Call inventory (stale on QT wiring) |
| `docs/operations/cursor-vs-insert-gap-diagnosis.md` | 2h lookback diagnosis |
| `monitor/quote_tweets.py` | Official + daily QT regimes |
| `monitor/cycle.py` | Cycle orchestration + QT hook |
| `x_monitor/apify.py` | `get_tweets_by_ids`, `get_quote_tweets`, `run_search` |
| `x_monitor/config.py` | `QuoteTweetConfig` defaults |
| `config.yaml` | `cycle.*`, `search.*`, stale `daily_ceiling` |
| `render.yaml` | 15-min harvest cron |
| `tests/posts/2026-08-04-*.md` | Post **cohorts** (content quality), not call-cost reports |

---

## 14. Open follow-ups

1. Pull full 24h `/backend/user/api_calls` (or consumption_summary) for exact day credits by endpoint.
2. Instrument cycle summary with estimated credits: `sum(max(15, n_results * 15))` per path.
3. Implement tiered QT refresh + update cost table and inventory docs in the same PR.
4. Optional: longitudinal probe — store engagement snapshots at T+1h/6h/24h/48h on a sample of ingested posts to replace cross-sectional half-life estimates with in-house curves.

---

## 15. One-line conclusions

- **Burn driver:** re-polling the same official parents every 15 minutes for 14 days via `/twitter/tweets`, billed at 15 credits/ID.
- **Not the main issue now:** cursor start/end (fixed to 15-min lookback).
- **Feature is good; cadence is wrong.**
- **Max attention for typical posts is hours → ~1 day (general) / ~1.5–2 days (LLM), not 15 days.**
- **Once-per-post metrics re-poll near plateau ≈ ~2x tweet budget; every-15-min recheck is not.**
