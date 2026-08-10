# Harvester cycle cost & budget table — latest run

### written by Grok 4.3

**Template:** [harvester-cycle-cost-table.md](./harvester-cycle-cost-table.md) (baseline cycle 2026-08-05 16:00 UTC).  
**Source cycle (latest completed):** `20260810T063111_0000-db83da0c`  
**Bucket (wall clock):** 2026-08-10 06:31:07 → 06:37:04 UTC (cron `06:30:27` → success `06:37:04`)  
**Search window:** ~15 min per call (e.g. A `[1786342571, 1786343471]`)  
**Volume (cycle log):** 7 calls planned/run · **87 posts seen** · **51 inserted** · 51 attributed · 350.71s  
**Errors:** 0 fetch errors · metrics_refresh errors=0  
**Pricing source:** [docs/external_vendors/twitterapi/twitterapi_index.md](../external_vendors/twitterapi/twitterapi_index.md) (scraped 2026-08-06 from `https://twitterapi.io/pricing`).  
**Conversion:** 1 USD = 100,000 credits · **15 credits / returned tweet**.

> **Logging limit (same as template):** only truncated walks log `total_items`. For this cycle that is **B1 only** (`total_items=63` after 2 walks).  
> Cycle total `posts seen` is the sum of per-call unique `n_results` (`CycleRunner._posts_seen`).  
> Therefore: **B1 = 63 (exact)** · **A+B2+B3+C1+C2+C3 = 87 − 63 = 24 (exact residual)** · individual non-B1 rows below are **residual-only / not split further**.

---

## Per-call cost (search harvest)

| (a) Call type | (b) TwitterAPI endpoint | (c) # results | (d) cost / result | (e) total cost (credits) | Notes |
|---|---|---:|---:|---:|---|
| **A** | `/twitter/tweet/advanced_search` (`list:<id>…`) | *∈ residual* | 15 | *∈ residual* | List fan-in query via advanced_search (not a separate list timeline path in current client). No truncation log → single walk. |
| **B1** | `/twitter/tweet/advanced_search` (wide-net bare keywords) | **63** | 15 | **945** | **Exact.** `TRUNCATED pass=1/5 n_pass=50` then drained after **2 walks**; `total_items=63`. Dominates the cycle (72% of search results). |
| **B2** | `/twitter/tweet/advanced_search` (handle-only top-presence) | *∈ residual* | 15 | *∈ residual* | No truncation log. |
| **B3** | `/twitter/tweet/advanced_search` (handle-only other) | *∈ residual* | 15 | *∈ residual* | No truncation log. |
| **C1** | `/twitter/tweet/advanced_search` (co-occurrence polyseme set) | *∈ residual* | 15 | *∈ residual* | Cap raised (cap=150 pages=8). Relevancy LLM `KEEP` noise in logs; not a credit line. |
| **C2** | `/twitter/tweet/advanced_search` (ernie/upstage) | *∈ residual* | 15 | *∈ residual* | No truncation log. |
| **C3** | `/twitter/tweet/advanced_search` (doubao/sensechat/kuaishou) | *∈ residual* | 15 | *∈ residual* | No truncation log. |
| **A+B2+B3+C1+C2+C3** | advanced_search (aggregate residual) | **24** | 15 | **360** | **Exact residual** = posts_seen − B1. Per-call split not in logs. |
| **TOTAL search (unique items)** | — | **87** | — | **1,305** | Matches cycle log `posts seen`. |

### B1 walk inflation (billable ≥ unique)

TwitterAPI bills **returned tweets per HTTP response**, not unique IDs after local dedupe.

| B1 walk | Logged | Implied billed (lower bound) |
|---|---|---:|
| Pass 1 | `n_pass=50`, truncated | **50** tweets → **750** cr |
| Pass 2 | drained; unique total 63 | ≥ **13** new → ≥ **195** cr |
| **B1 total** | unique **63** | ≥ **945** cr (equals unique if pass 2 returned only new IDs) |

If pass 2 returned dups already counted in pass 1, billed credits would be **higher** than 945 while unique stays 63. Upper bound for 2× cap-50 pages: 100 × 15 = **1,500** cr (unlikely given drain at 63 unique).

### HTTP call count (search)

| | Count |
|---|---:|
| Planned logical calls | 7 |
| B1 truncation walks | +1 extra search HTTP |
| **Search HTTP invocations (approx)** | **8** |
| Min floor if all empty | 8 × 15 = **120** cr |

Floor is moot: B1 alone returns 50+ on pass 1.

---

## One-shot metrics refresh (new since baseline table)

Continuous QT by-id recheck is **retired** (plan `2026-08-10-002`, commit `c603638`). Replaced by `monitor/metrics_refresh.py` once-per-post after `delay_hours` (default 2.0).

| (a) Call type | (b) Endpoint | (c) # results | (d) cost / result | (e) total cost (credits) | Notes |
|---|---|---:|---:|---:|---|
| **metrics_refresh** | `GET /twitter/tweets` (by-id, chunk 50) | **174** refreshed (due=200, missing=26) | 15 | **~2,610** | `due=200 refreshed=174 missing=26 errors=0`. Client batches `TWEETS_BY_IDS_CHUNK=50` → **4** HTTP chunks for a 200-id due set. Bill ≈ returned tweets × 15 (missing IDs typically not returned → not billed). |
| **quote_tweets channel** | — | 0 | — | **0** | Deprecated no-op on cycle path. |

**Backlog note:** `due=200` hit the `per_cycle_cap` — this cycle is still **draining** the unstamped backlog, not steady-state one-shot volume. Steady-state metrics ≈ inserts from ~2h earlier (~50/cycle), not 174–200.

---

## Cycle total (this run)

| Component | Results (tweet units) | Credits | USD |
|---|---:|---:|---:|
| Search harvest (unique posts seen) | 87 | **1,305** | $0.0131 |
| Metrics refresh (refreshed) | 174 | **~2,610** | $0.0261 |
| QT continuous recheck | 0 | **0** | $0 |
| **TOTAL this cycle** | — | **~3,915** | **~$0.0392** |

| Share | Credits | % of cycle |
|---|---:|---:|
| Search | 1,305 | **33%** |
| Metrics refresh (backlog drain) | 2,610 | **67%** |

Compare to the **2026-08-05 baseline table** (search-only, 86 results → **1,290** cr): search cost is essentially flat (**+15 cr / +1 result**). The new dominant line is one-shot metrics while the backlog is open.

---

## Per-call floor (15 credits minimum)

```
~8 search HTTP × 15 = 120 credits minimum (search path)
~4 by-id HTTP × 15 = 60 credits minimum (metrics path, if empty)
```

Both floors are moot this cycle (large result sets).

---

## Daily / monthly burn at this rate

### A) If every cycle looked like **this** cycle (incl. metrics backlog drain)

| Period | Calculations | Total |
|---|---|---:|
| Per cycle | ~3,915 credits | ~3,915 |
| Per hour (4 cycles) | × 4 | ~15,660 |
| Per day (96 cycles) | × 96 | ~**375,840** |
| Per month (30 d) | × 30 | ~11.28M credits |
| Per month (USD) | × $0.00001 | **~$112.80** |

This is a **temporary upper envelope** while `metrics_refresh` sits at cap (~200 due/cycle).

### B) Steady-state projection (search like this run + one-shot metrics ≈ inserts)

Assumes search stays ~87 seen / cycle and metrics settles to ~51 tweet-units / cycle (one refresh per inserted post, delayed 2h):

| Period | Search | Metrics | Total | USD |
|---|---:|---:|---:|---:|
| Per cycle | 1,305 | ~765 | **~2,070** | ~$0.021 |
| Per day (96) | 125,280 | ~73,440 | **~198,720** | **~$1.99** |
| Per month (30 d) | — | — | ~5.96M | **~$59.60** |

### C) Baseline table (2026-08-05, search-only, no metrics channel)

| Period | Credits | USD |
|---|---:|---:|
| Per cycle | ~1,290 | ~$0.013 |
| Per day | ~123,984 | ~$1.24 |
| Per month | ~3.72M | ~$37.20 |

---

## Comparison vs baseline (2026-08-05 16:00 UTC)

| Metric | Baseline (Aug 5) | Latest (Aug 10 06:31) | Δ |
|---|---:|---:|---:|
| Logical calls | 7 | 7 | 0 |
| Search results (posts seen) | 86 | 87 | +1 |
| Search credits | 1,290 | 1,305 | +15 |
| B1 results | 12 | **63** | **+51** (wide-net now saturates + walks) |
| Inserted | (not in table; 86 fetched) | 51 | — |
| QT continuous by-id | not modeled (was live then) | **0** (no-op) | fixed |
| Metrics one-shot | n/a | **174 → ~2,610 cr** | new |
| Cycle total (modeled) | 1,290 | **~3,915** | metrics backlog |

**B1 regime change:** baseline B1 was quiet (12 hits). This cycle B1 alone is **63** after a truncation walk — the wide-net bare-keyword path is the search cost driver, not C-tier co-occurrence.

---

## Anomalies / ops notes (this run)

1. **B1 truncation every recent cycle** — 05:45, 06:00, 06:15, 06:31, 06:45 all log `TRUNCATED pass=1/5 n_pass=50` then drain in 2 walks (`total_items` 63–97). Extra walk = extra search HTTP + more tweet units.
2. **Per-call `n_results` not logged on ok path** — residual 24 cannot be split to A/B2/B3/C* without code change (log `n_results` / emit `--json` summary from cron).
3. **`source_query_id` NULL on posts** — cannot reconstruct call mix from DB for this cohort.
4. **metrics_refresh at cap** — `due=200` with 174 refreshed is backlog drain; expect credits to fall toward steady-state (B) as `metrics_refreshed_at` fills.
5. **LLM `KEEP` non-JSON** on relevancy path — not TwitterAPI credit burn; noise only.
6. **Budget guard** (`_CREDITS_PER_ADVANCED_SEARCH_PAGE = 300` / stale `daily_ceiling`) still mis-modeled vs live **15 cr/tweet** (carried from baseline doc).

---

## How to re-run this table

```bash
# Latest completed cycle narrative
ssh -T fuchitalee 'set -a; . ~/.env.secrets; set +a
render logs -r crn-d9gv94o4n6ts739tqaug --limit 200 -o text --confirm 2>&1 \
  | grep -E "_fetch_tweets|metrics_refresh|CycleRunner.run:|Cycle 20"'

# Optional: force JSON stats on a manual cycle (spends credits)
# ssh fuchitalee 'cd /Users/fuchitalee/development/pushin-weight-v2 && \
#   .venv/bin/python manage.py run_cycle --json'
```

To get **true per-call rows** next time, either:

1. Log `call_id n_results=…` after every `_fetch_tweets` return (ok path, not only truncated), or  
2. Run cron with JSON summary capture, or  
3. Persist `summary["calls"]` (already has `n_results` / `fetch_n` in memory).

---

## Files

- Template baseline: `docs/reference/harvester-cycle-cost-table.md`
- Pricing: `docs/external_vendors/twitterapi/twitterapi_index.md`
- Credit-burn research: `docs/external_vendors/x_twitter/2026-08-10-120136-twitterapi-credit-burn-and-engagement-half-life.md`
- Fix / one-shot metrics: `docs/plans/2026-08-10-002-fix-once-metrics-refresh-plan.md`, `monitor/metrics_refresh.py` (origin/main)
- Cycle runner: `monitor/cycle.py` (`_fetch_tweets`, `CycleRunner.run`)
- By-id client: `x_monitor/apify.py` (`get_tweets_by_ids`, `TWEETS_BY_IDS_CHUNK=50`)
- Cron: Render `crn-d9gv94o4n6ts739tqaug` (`python manage.py run_cycle`)
