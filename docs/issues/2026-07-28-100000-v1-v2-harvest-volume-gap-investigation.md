## v1 vs v2 harvest volume gap — investigation handoff (verify before acting)

### TL;DR

The cursor-fix plan (`2026-07-27-002`) shipped claiming v2 had only two missing channels vs v1 (cursor + quote-tweets), and pegged the post-fix volume target at 1,500–1,900/day. As of 2026-07-28, prod is at 1,350/day (7/27) and 1,600/day pace (7/28 partial). The cursor is alive (c075616 + e22c3a1 landed) and quote-tweets are partial (dc2ccbd). The question of why v2 is **still ~50% of v1's daily volume** is open. Earlier analysis (mine, 2026-07-28) **incorrectly diagnosed this as a missing reply-capture channel** — that diagnosis was wrong. This issue is the handoff to figure out the actual gap before another plan gets written against a faulty model.

### What I checked (so the next agent doesn't redo it)

#### Volume comparison

| Era | Source | Day | Total | Replies | Quotes | Originals |
|---|---|---|---:|---:|---:|---:|
| v1 | `data/x_monitoring.db` | 7/19 | 1,995 | 724 (36%) | 512 (26%) | 759 (38%) |
| v1 | SQLite | 7/20 | 2,256 | 750 (33%) | 469 (21%) | 1,037 (46%) |
| v1 | SQLite | 7/21 | 2,425 | 708 (29%) | 604 (25%) | 1,113 (46%) |
| v2 | Postgres | 7/19 | 1,127 | 724 (64%) | 211 (19%) | 192 (17%) |
| v2 | Postgres | 7/20 | 1,145 | 750 (66%) | 173 (15%) | 222 (19%) |
| v2 | Postgres | 7/21 | 1,143 | 708 (62%) | 175 (15%) | 260 (23%) |
| v2 | Postgres | 7/25 | 1,163 | 457 (39%) | 218 (19%) | 488 (42%) |
| v2 | Postgres | 7/26 | 1,111 | 454 (41%) | 152 (14%) | 505 (45%) |
| v2 | Postgres | 7/27 | 1,350 | 376 (28%) | 544 (40%) | 430 (32%) |
| v2 | Postgres | 7/28 partial | 406 | 115 (28%) | 143 (35%) | 148 (36%) |

Same query used everywhere: `DATE(fetched_at)` bucketed. Reply share is from `in_reply_to_user_id IS NOT NULL`; quote share from `quoted_status_id IS NOT NULL`.

#### Key findings I want verified (not trusted — verify before acting)

1. **The 7/19–7/21 rows in Postgres are the v1 cutover backfill, not v2 harvests.** v1 was still running on those days, so 7/19–7/21 Postgres counts (1,127 / 1,145 / 1,143) reflect v1's tweets imported during cutover. The 64% reply share matches v1's 33% × ~2 ratio only because (a) backfill was timestamped with `fetched_at = cutover_day` even though authored dates were 7/19–7/21, and (b) the backfill exported what was in v1 SQLite — replies and all. **Don't treat 7/19–7/21 Postgres counts as a v2 capability measure.**

2. **v2 IS already capturing replies via the main harvest.** 7/27 shows 28% replies (376/1,350); 7/28 partial 28% (115/406). v1 had 29–36% replies on the same dates. **Reply share is roughly equivalent.** The "missing reply capture channel" hypothesis I floated earlier (now memorialized in `project_pushinweight_v1_harvest_channels_2026-07-28.md`) is **incorrect** — TwitterAPI.io's `from:X` and keyword queries naturally return replies that mention the tracked tokens. No separate capture channel is needed.

3. **The real gap is "originals" — posts that are neither replies nor quotes.** v1 originals: 759/1,037/1,113 per day on 7/19–7/21. v2 originals (post-fix): 430/148 per day. **Originals are 40–55% of v1's volume** even though query/cap/keyword coverage is supposed to be identical. That's where the volume loss is concentrated.

4. **Quote-tweet share has flipped.** v1 was ~25% quotes; v2 post-fix is 35–40% quotes. Probably because the QT port (dc2ccbd) over-samples relative to v1's QT cadence. Not a regression, but worth noting.

#### What I did NOT check (next agent should)

- **Per-brand originals breakdown.** v1 SQLite has `posts_brands` rows; v2 has the same. Compare per brand (deepseek, qwen, glm, minimax, etc.) to see if the original gap is uniform across brands or concentrated in one.
- **Query shape diff between v1 and v2.** v1 SQLite's `search_queries` is empty so we can't directly diff queries, but `x_monitor/run.py` query rendering may differ from `monitor/cycle.py`'s in subtle ways (e.g., `min_faves`, `min_replies`, `lang:` filters, `since:` vs `since_time:`).
- **`fetched_at` semantics.** v1 SQLite's `fetched_at` updates on every `upsert` (re-fetched tweets get a new `fetched_at`), so "1,995/day on 7/19" overcounts unique posts. v2 Postgres may or may not have the same update behavior — needs verification.
- **`X_LENGTH_CAP` was 512 in both.** But v1 may have used different cap on some calls. Verify in `config.yaml` history vs the regression net's pinned values.
- **The Plan 004 in flight (`docs/plans/2026-07-27-004-refactor-posts-raw-denormalize-and-drop-plan.md`).** May be doing something that touches this gap or makes it worse.

### Why this matters

The next person who looks at v1/v2 volume will read the cursor-fix plan's "1,500–1,900/day target" and conclude the fix is working. **It isn't** — v2 is at ~60% of v1 baseline, and the missing channel is NOT reply capture (that was wrong) and NOT quote capture (that's partially working). The missing channel is most likely **originals** — the main sweep is returning fewer unique originals than v1 did. Could be:
- A query shape difference (operators, caps, filters)
- v1's relevance filter (Plan 2026-07-11-001 KTD6 retired it, so this shouldn't be it)
- The cursor chain's `since_time` clamp at 2h when v1's was unbounded (unlikely, but possible if 2h clamps a meaningful fraction of originals)
- A bug in attribution dropping originals

### Recommended next steps

1. **Diff per-brand daily volume** for v1 (7/19–7/21) vs v2 (7/27+). Use:
   ```bash
   sqlite3 data/x_monitoring.db "SELECT pb.brand_id, DATE(p.fetched_at), COUNT(*)
     FROM posts p JOIN posts_brands pb ON p.tweet_id = pb.post_id
     WHERE p.fetched_at >= '2026-07-19' AND p.fetched_at < '2026-07-22'
       AND (p.in_reply_to_user_id IS NULL OR p.in_reply_to_user_id = '')
       AND (p.quoted_status_id IS NULL OR p.quoted_status_id = '')
     GROUP BY pb.brand_id, DATE(p.fetched_at);"
   ```
   Same shape query against `posts_brands` joined to `posts` in Postgres.

2. **Verify query shape parity** by reading `monitor/cycle.py`'s actual query strings (from a `--dry-run` cycle) vs the equivalent `x_monitor/run.py` rendered strings from a v1 dry-run JSON in `data/runs/`.

3. **Check whether `fetched_at` update semantics differ.** If v1's `upsert` rewrites `fetched_at` on dedup hits, the v1 baseline is inflated and the "50% gap" may be a measurement artifact, not a real gap. **This is the highest-leverage single check** — it would falsify the entire investigation in one query if v1's count is deduplicated wrong.

4. **Only after (1)–(3) above produce a coherent diagnosis** should someone write the next plan. Do NOT file `2026-07-28-005-feat-port-reply-capture-channel-plan.md` — that plan would be based on a wrong premise.

### Files referenced

- `docs/plans/2026-07-27-002-fix-v2-harvest-cursor-regression-plan.md` — the plan that set the 1,500–1,900/day target
- `docs/issues/2026-07-27-180000-harvest-cursor-restoration-v1-parity.md` — earlier handoff with cursor context
- `monitor/cycle.py` — v2 main harvest (U1–U6 wired)
- `monitor/quote_tweets.py` — v2 QT channel (dc2ccbd)
- `x_monitor/run.py` — v1 single-file orchestrator (the legacy path)
- `~/.claude/projects/-Users-fuchitalee-development-pushin-weight-v2/memory/project_pushinweight_v1_harvest_channels_2026-07-28.md` — memory note that needs correction on the reply-channel claim

### Acceptance signal

A clean diagnosis that:
- Names the actual missing channel(s) by query/cap/operator diff, not by post-hoc classification of v1 data.
- Quantifies how much each channel contributes (e.g., "originals are 45% short because X").
- Identifies whether the gap is in v2's query rendering, persistence path, or measurement.
- Recommends a minimal targeted fix, scoped against the verification protocol used for the cursor fix.

**Do NOT** start implementation or file a follow-up plan until (1)–(3) above are answered. The repo has had three plans in two weeks against this same volume drop and we're still not sure of the actual gap.


---

## Verified findings (2026-07-28 ~07:15 UTC) — Grok session

### written by Grok 4.3

Checks (1)–(3) from Recommended next steps, plus prod query dump and live cursor/log review after `e22c3a1`.

### (3) `fetched_at` update semantics — **not an inflation artifact**

| Stack | Insert behavior | Daily `COUNT(*)` vs `COUNT(DISTINCT tweet_id)` |
| --- | --- | --- |
| v1 SQLite | `INSERT OR IGNORE` on `posts` — re-fetch does **not** rewrite `fetched_at` | 7/19–21: **equal** (1995/1995, 2256/2256, 2425/2425) |
| v2 Postgres | `fetched_at = auto_now_add=True`; `_upsert_post` does **not** put `fetched_at` in `defaults` | First-insert only; re-fetch updates other fields, not day bucket |

**Conclusion:** The v1 baseline is **not** inflated by re-touch upserts. The gap is not a pure measurement bug.

### (1) Per-brand originals — **gap is real and uneven**

Originals = neither reply nor quote (`in_reply_to_user_id` empty AND `quoted_status_id` empty).

| Brand | v1 avg originals/day (7/19–21) | v2 originals 7/27 | v2 / v1 |
| --- | ---: | ---: | ---: |
| deepseek | 437 | 217 | **50%** |
| qwen | 369 | 85 | **23%** |
| glm | 290 | 162 | **56%** |
| minimax | ~86 | 30 | ~35% |
| llama | ~63 | 72 | **~114%** (OK / better) |

All-posts brand join (same pattern):

| Brand | v1 avg all/day | v2 7/27 all | v2 / v1 |
| --- | ---: | ---: | ---: |
| deepseek | 895 | 509 | 57% |
| qwen | 828 | 327 | **39%** |
| glm | 698 | 475 | 68% |
| llama | 129 | 155 | 120% |

**Call ownership (config.yaml):**

- **B1** (cap 50): minimax, **qwen**, **deepseek**, mistral, stepfun, hunyuan — *highest-volume brands share one 50-result call*
- **B2** (cap 50): doubao, **glm**, sensechat, inclusionai
- **C1** (cap 150 after e22c3a1): mimo, kimi, yi, **llama** — llama recovered

**Zero unattributed posts** on 7/27 (`posts` with no `posts_brands_mentions` = 0). Gap is not “insert then drop attribution.”

### (2) Query shape parity — **prod B/C queries are well-formed**

Render one-off dump (`job-d9k5cae1egvs73ftgd0g`):

- `PRIMARY_BRANDS` loads all 20 brands; deepseek=`[deepseek-r1,深度求索,DeepSeek]`, qwen=`[通义千问,Qwen,Qwen3]`
- B1 query length **414**, starts with `((m2.5 OR 海螺 OR MiniMax OR Hailuo) OR (…Qwen…) OR (…DeepSeek…) OR …)` — **not** the defensive `(empty)` form
- C1/C2 use config-inline brand tokens (same as plan regression net)
- Call A: `(list:2067062923525275922) min_faves:0` (`MIN_FAVES_FOR_LIST_CALL=0`)

Local SQLite has **0** `brand_keywords` rows → local `plan_calls_for_cycle` renders B as `(empty) (…)`; **that is local-only**, not prod.

v1 used the same `is_primary=1` wide-net path (`Store.read_primary_brand_keywords` → `plan_calls`). Primary token sets for deepseek/qwen/glm match v1 SQLite.

### Live harvest health (post e22c3a1)

- Cron every 15m: **completed**, ~16 min windows on **all six** calls including C1
- C1 multi-pass + 150 cap: **cursor advancing** (unstuck)
- B1/B2/B3: **no TRUNCATED** lines in 05:00–07:00 UTC logs; windows ~16 min; cap stays **50**
- 7/28 UTC hourly inserts (through ~06:00): **51–78/hr** → pace **~1.5k–1.6k/day** if sustained
- 7/27 full day: **1350** total, **470** originals, **544** quotes (40% QT share vs v1 ~25%)

### What this means for the “~50% of v1” claim

| Claim | Verdict |
| --- | --- |
| Missing reply channel | **Rejected** (issue was already right): reply share ~28–36% both eras |
| QT dead | **Rejected**: QT live; share **higher** than v1 |
| `fetched_at` double-count | **Rejected** |
| Empty B-query on prod | **Rejected** |
| C1 deadlock | **Fixed** (e22c3a1); llama at/above v1 |
| Originals shortfall | **Confirmed** as main residual gap vs 7/19–21 v1 |
| Uniform brand loss | **Rejected**: **qwen/deepseek (B1) hit hardest**; llama (C1) fine |

**Confound (important):** v1 baselines are **7/19–21**; live v2 is **7/27–28**. v1 itself varied **423–2425/day** in July. Cross-week comparison overstates a pure pipeline regression. Still, **intra-day brand mix** (qwen ≪ deepseek ≪ llama-vs-v1) points at **B1 packing**, not global X silence.

### Residual technical hypotheses (ranked, not yet proven)

1. **B1 capacity / packing (highest technical leverage):** six high-chatter brands share one `max_results=50` call. Even when not truncating in quiet UTC hours, peak windows may still under-sample; multi-pass only runs when truncated. C1 already got 150+walks; **B1/B2 did not**.
2. **Originals vs QT mix:** v2 QT share 35–40% vs v1 ~25% — total can approach plan target while **originals** stay ~45–60% of v1.
3. **Organic week-to-week variance:** part of total gap; does not explain brand unevenness.
4. **Secondary-token-only discovery:** B uses `is_primary=1` only (same as v1 design). Unlikely sole cause (v1 deepseek originals all matched primary tokens in text on sample).
5. **Call A list membership / list volume:** not yet quantified (v1 `source_query_id` all NULL).

### Recommended next actions (still diagnosis → then one small plan)

1. **Peak-hour probe:** force a B1-only cycle at high-traffic hour; log `n_results` / truncated / multi-pass. If truncated often, raise B1/B2 ceiling or split B1 (deepseek|qwen vs others).
2. **Instrument per-call `n_results` / `n_kept` / `n_inserted` into cycle summary logs** (currently easy to miss B1 under-yield).
3. **Same-metric dashboard:** daily originals + per-brand (not only total fetched_at) so QT inflation cannot mask original shortfall.
4. **Do not** open a reply-capture plan. **Do not** treat 1,500/day total alone as “v1 parity” while originals/qwen lag.

### Numbers snapshot (UTC)

```
v1 avg 7/19–21:  total 2225 | originals 1008
v2 7/27:         total 1350 | originals  470 | quotes 544
v2 7/28 pace:    total ~1536| originals ~624  (from ~07:00 partial day)
```

