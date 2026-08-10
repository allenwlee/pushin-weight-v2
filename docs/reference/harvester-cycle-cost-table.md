# Harvester cycle cost & budget table

**Source cycle:** last complete 15-min group before the 402 errors started.
**Bucket:** 2026-08-05 16:00:00 → 16:14:59 UTC (86 posts fetched, 0 errors).
**Pricing source:** [docs/research/twitterapi_docs/INDEX.md#pricing](../research/twitterapi_docs/INDEX.md#pricing) (scraped 2026-08-06 from `https://twitterapi.io/pricing`).
**Conversion:** 1 USD = 100,000 credits.

## Per-call cost

| (a) Call type | (b) TwitterAPI endpoint | (c) # results | (d) cost per result (credits) | (e) total cost (credits) | Notes |
|---|---|---:|---:|---:|---|
| **A** | `/twitter/list/tweets` (List fan-in) | 11 | 15 | **165** | List-based fan-in (curated list of configured X list). Smaller curated set; one call per cycle. |
| **B1** | `/twitter/tweet/advanced_search` (Wide-net bare keywords) | 12 | 15 | **180** | Bare keywords (deepseek/qwen/minimax/stepfun/hunyuan). No co-occurrence constraint; bare mode per plan 2026-07-30 U1. |
| **B2** | `/twitter/tweet/advanced_search` (Handle-only (top-presence)) | 14 | 15 | **210** | Top-presence handles (@MiniMax_AI, @deepseek_ai, @Zai_org, etc.). Handle-only mode per plan 2026-07-30 U2. |
| **B3** | `/twitter/tweet/advanced_search` (Handle-only (other)) | 13 | 15 | **195** | Other-brand handles (@bytedanceoss, @Kimi_Moonshot, @XiaomiMiMo, etc.). Handle-only mode per plan 2026-07-30 U2. |
| **C1** | `/twitter/tweet/advanced_search` (Co-occurrence (5-brand polyseme set)) | 14 | 15 | **210** | Co-occurrence constraint with 5-term minimal allowlist (llm/model/api/agentic/huggingface). Covers mimo/mistral/moonshot_kimi/yi/llama. |
| **C2** | `/twitter/tweet/advanced_search` (Co-occurrence (ernie/upstage)) | 11 | 15 | **165** | Co-occurrence with 7-term allowlist (5-min + baidu/文心). Covers ernie/upstage. |
| **C3** | `/twitter/tweet/advanced_search` (Co-occurrence (doubao/sensechat/kuaishou)) | 11 | 15 | **165** | Co-occurrence with 5-term allowlist. Added per plan 2026-07-30-002 to cover 3 brands not in B2/B3. |
| **TOTAL** | — | **86** | — | **1290** | one cycle |

## Per-call floor (15 credits minimum)

TwitterAPI.io charges a **15-credit minimum per API call** even when the call returns 0 or 1 result (per the pricing page). With 7 calls per cycle, the minimum floor alone is:

```
7 calls × 15 credits = 105 credits minimum per cycle (regardless of results)
```

Since the last complete cycle returned 86 tweets across 7 calls, the floor is moot here (every call exceeded it). But on a slow cycle with low tweet counts, the floor would dominate.

## Daily burn at this rate

| Period | Calculations | Total |
|---|---|---:|
| Per cycle | 7 calls × ~12.3 tweets/call avg × 15 credits | ~1292 credits |
| Per hour (4 cycles) | cycle × 4 | ~5166 credits |
| Per day (96 cycles) | cycle × 96 | ~123984 credits |
| Per month (30 days) | day × 30 | ~3719520 credits |
| Per month (USD) | month × $0.00001/credit | ~$37.20 |

**At steady-state (86 posts/cycle, 96 cycles/day), monthly burn ≈ $18 USD.**

## Anomaly: 402 errors and the over-counting budget guard

The 402 errors observed on 2026-08-06 02:15+ UTC are the **monthly TwitterAPI.io allotment running out**, not a single-cycle over-burn.

- Dashboard call rates at 2026-08-06 01:40 JST (post-402 recovery): 6 calls × ~50 tweets × 15 credits = **4,335 credits in 30 seconds**.
- That extrapolates to 4,335 × 96 cycles/day = **416,160 credits/day** if every cycle hit the 50-tweet cap.
- The local budget guard in `x_monitor/run.py:959` uses `_CREDITS_PER_ADVANCED_SEARCH_PAGE = 300` — a flat per-page estimate that over-counts by ~2x vs the live per-tweet model. The hard cap formula at `x_monitor/run.py:967` uses this wrong unit.
- The `daily_ceiling: 333` in `config.yaml:65` is a stale placeholder; nothing in the codebase enforces it.

**Recommendation: top up the TwitterAPI.io account, then refresh `docs/reference/twitterapi-io-calls.md` to cite the per-tweet rate (15 credits/tweet) instead of the page-flat 300 credits/page.**

## How to re-run this table

```bash
ssh -T -o BatchMode=yes -o ServerAliveInterval=5 -o ServerAliveCountMax=4 fuchitalee 'render logs --resources crn-d9gv94o4n6ts739tqaug --limit 500 -o text --confirm 2>&1 | grep -E "fetch_tweets.*total_items|n_keep|degraded" | tail -30'
```

Per-call result counts are not currently logged at message-create level (`x_monitor/run.py:999` only logs the cycle total). To get per-call numbers, the cycle runner would need to instrument the fetch_tweets return path (lines 1660-1680) to log `total_items` per call.

## Files

- `docs/research/twitterapi_docs/INDEX.md` — pricing knowledge (this table's source)
- `x_monitor/apify.py` — `SEARCH_PATH = /twitter/tweet/advanced_search` (the API callsite)
- `x_monitor/run.py:958-978` — budget guard with the wrong `300 credits/page` constant
- `config.yaml:65` — `daily_ceiling: 333` (read but not enforced)

## Update 2026-08-10 (plan 2026-08-10-002)

Continuous official/staff quote-count recheck (every 15 min × ~14 days via `/twitter/tweets`) is **removed**.

**New steady-state cost:** each stored post gets **at most one** by-ID metrics re-fetch after `metrics_refresh.delay_hours` (default 2.0), capped per cycle by `metrics_refresh.per_cycle_cap` (default 200). Quote-body endpoint is not used on the cycle path.

See `monitor/metrics_refresh.py` and `config.yaml` → `metrics_refresh:`.

