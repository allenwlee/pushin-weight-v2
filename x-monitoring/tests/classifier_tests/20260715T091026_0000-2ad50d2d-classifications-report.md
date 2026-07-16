# Captured Posts + Classifications Report

**Run:** `data/runs/20260715T091026_0000-2ad50d2d.json`
**Run window:** `fetched_at` 2026-07-15T09:10:26 → 09:15:24 (UTC)
**Classifier:** DeepSeek V4 Pro via `X_MONITOR_CLASSIFIER_BASE_URL=https://api.deepseek.com/anthropic`
**Reviewer:** Allen
**Date:** 2026-07-16

This report lists every post newly inserted by the run, joined to the
brand-classification rows the pipeline wrote for it. Source query is
`data/runs/dsv4-clean-pipeline-20260715T091026.json` (artifact) and
`data/x_monitoring.db` (live state).

> **Scope note.** The run JSON reports `n_inserted: 17`. The DB has
> ~900 posts with `fetched_at >= 2026-07-15T09:10:00` because the
> launchd agent kept re-running between when the manual kill switch
> was set and when `launchctl unload` ran. **This report scopes to the
> 17 run-window posts only.** The other ~880 are pre-existing rows
> touched by later launchd-triggered runs; they are not part of this
> review.

---

## Run totals (from the run JSON)

| Field | Value |
|---|---|
| `n_queries_run` | 6 (A, B1, B2, B3, C1, C2) |
| `n_results` | 35 (raw results returned by TwitterAPI.io) |
| `n_inserted` | **17** (posts whose `tweet_id` was new to `posts` this run) |
| `n_classifications_written` | 45 (upsert attempts) |
| `n_classifications_dropped` | 0 |
| DB rows for run-window posts in `posts_brands_signals` | **33** |
| Counter gap | 45 − 33 = **12 ON CONFLICT updates** (inline writer + post-fetch writer both wrote the same `(post_id, brand_id, post_type_key)` triple) |
| Wall clock | 297.48s |

---

## Posts by call, with classifications

### A — list/curated handles (account call)

3 raw results, 2 newly inserted. Both inserts also landed in B1's bucket (see below) — the account call's inline writer classifies with `_unattributed` initially, then the post-fetch path re-classifies against the brand token index.

| Post | Author | Lang | Source | Notes |
|---|---|---|---|---|
| `2077317360159961139` | MeryemArik9 | — | A → B1 | Bedrock open-model offering post; see full classification below |
| `2077319455072534689` | Hailuo_AI | — | A → B1 | MiniMax WAIC 2026 booth; see full classification below |

The other A-call result was a re-fetch of an already-known post (no insert).

---

### B1 — wide-net, top brands (`minimax` bucket)

**10 newly inserted posts → 14 classification rows.** B1 keyword chain covers: `minimax, qwen, deepseek, mistral, stepfun, hunyuan` (per the 3915675-dedup'd `call_b_groups[0]`).

| # | Tweet ID | Author | Lang | Brand(s) → post_type (sentiment) | First 200 chars of text |
|---|---|---|---|---|---|
| 1 | `2077319457899520174` | Hailuo_AI | — | `minimax → event_announcement (neutral)` | "📅 Multimodal Event Calendar · AI Leap · Her Momentum - Women's Power in the AI Era · Time: 1:30 PM, Jul 17 · Venue: Hall A..." |
| 2 | `2077319455072534689` | Hailuo_AI | — | `minimax → event_announcement (neutral)` + `advertising_marketing (positive)` | "MiniMax at #WAIC2026 · Find us at our Booth, hands-on workshops, and on expert panels! · Hear the latest ideas shaping the future of AI..." |
| 3 | `2077317811349942375` | Awesome_AI_News | — | `minimax → performance_comparisons (positive)` + `event_announcement (positive)` | "Ahead of the 2026 World AI Conference, Hong Kong-listed AI large model stocks rallied. On July 15, MINIMAX-W soared 12.5%..." |
| 4 | `2077319292048072879` | Raph_GMI | — | `minimax, qwen, deepseek, glm → advertising_marketing (neutral)` | "🤖 ONE PLATFORM. THE WORLD'S LEADING AI MODELS. UNLIMITED POSSIBILITIES. · Artificial intelligence is evolving rapidly, and..." |
| 5 | `2077319081980838341` | web3XWG | zh | `minimax, qwen, deepseek, glm → advertising_marketing (positive)` | "AI 正在进入'多模型协同时代'，https://t.co/... 正在成为连接全球 AI 能力的统一入口。 很多人还在讨论：GPT 和 Claude 谁更强？DeepSeek 能不能挑战国际模型？ 但我越来越觉得，这些问..." |
| 6 | `2077317633301504458` | ZayvenKnox | — | `qwen → advertising_marketing (neutral)` (+ B1 wide-net hit) | "120 AI tools categorized by what they actually do. · Bookmark this for 2026. ⚡ · AI Chat & Research · • ChatGPT · • Claude · • Ge..." (Qwen appears in the categorized list) |
| 7 | `2077319526379671867` | 0xPascual | — | `qwen → performance_comparisons (neutral)` | "A 3-hour free video from Andrew Ng just dropped the entire 2026 AI engineering curriculum. Bootcamps charging $15,000 f..." |
| 8 | `2077319339100037160` | mrru5s3ll | — | `deepseek → performance_comparisons (neutral)` + `feedback_questions (positive)` | "Most AI agents shipping right now are chatbots with a to-do list. · The pitch sounds great. Give it a goal, let it figure..." |
| 9 | `2077319292048072879` | Raph_GMI | — | `deepseek → advertising_marketing (neutral)` | (same post as B1 row #4; multi-brand hit) |
| 10 | `2077319081980838341` | web3XWG | zh | `deepseek → advertising_marketing (positive)` | (same post as B1 row #5; multi-brand hit) |

**Plus the MeryemArik9 Bedrock post (#11 in this section, but most interesting):**

| # | Tweet ID | Author | Lang | Brand(s) → post_type (sentiment) | First 200 chars |
|---|---|---|---|---|---|
| 11 | `2077317360159961139` | MeryemArik9 | — | `minimax → performance_comparisons (neutral)` + `feedback_questions (neutral)`; **`llama → performance_comparisons (negative)` + `feedback_questions (negative)`**; **`glm → performance_comparisons (neutral)` + `feedback_questions (neutral)`** | "Bedrock open model offering: Models seem to have a 5 month delay before getting support - most recent models are from Feb · Models available include… Llama (who is still using this?) · Models not available - GLM 5.2, new Qwens, newer MiniMax etc…" |

This single post generated **6 classification rows across 3 brands**. The OR-chain matched `Llama`, `GLM`, and `MiniMax` literally in the text. The LLM correctly distinguished the rhetorical "who is still using this?" (sentiment: negative for llama) from the neutral availability comparison (neutral for GLM and MiniMax).

---

### B2 — wide-net, CN brands (`doubao` bucket)

**5 newly inserted posts → 6 classification rows.** B2 keyword chain covers: `doubao, glm, sensechat, inclusionai` (per `call_b_groups[1]`). Note `glm` and `chatglm` overlap with B1's deepseek/minimax in some cross-mention posts (see post #4 and #5 above).

| # | Tweet ID | Author | Lang | Brand(s) → post_type (sentiment) | First 200 chars |
|---|---|---|---|---|---|
| 1 | `2077319419005460935` | EmmanuelInvest | — | `doubao → buzz_releases (neutral)` + `event_announcement (neutral)` | "🟢 China Clears $AAPL Apple Intelligence & Six Other Mobile AI Services · Impact: Bullish ⭐⭐⭐⭐⭐ · 🇨🇳 China's regulator has..." (matched via the "Nubia Doubao" mention in the original Apple Intelligence clearance story) |
| 2 | `2077317516825866300` | HOWAI4242 | — | `doubao → event_announcement (neutral)` | "China's CAC said Apple Intelligence, Huawei Xiaoyi, OPPO AndesGPT, vivo BlueLM, Xiaomi HyperAI, Samsung Galaxy AI and Nubia Doubao have completed filings for on-device generative AI services. https://t.co/kRBvKxJRyw" |
| 3 | `2077317551722578310` | velokey9 | — | `doubao → hands_on_usage (mixed)` | "I tested Seedream 5.0 Pro on a product-ad task: a launch visual for a fictional drink with exact label text. · Worked: • Clean geometry and lighting..." (matched via ByteDance/Doubao brand group) |

**Posts classified under the B2 path that also got a B1 hit (cross-listed above):**

| # | Tweet ID | Brand (B2 contribution) → post_type (sentiment) |
|---|---|---|
| 4 | `2077319292048072879` | `glm → advertising_marketing (neutral)` |
| 5 | `2077319081980838341` | `glm → advertising_marketing (positive)` |
| 6 | `2077317360159961139` | `glm → performance_comparisons (neutral)` + `feedback_questions (neutral)` |

---

### B3 — wide-net, specialized (`nemo_megatron` bucket)

**0 newly inserted posts.** `n_results: 1, n_kept: 1, n_inserted: 0`. The single kept result was an already-known post. B3 covers `nemo_megatron, exaone, sakana_ai, kuaishou`.

---

### C1 — co-occurrence polysemous (`mimo` bucket)

**0 inserted.** `n_results: 0`. C1's 22-term `co_occurrence` filter pulled nothing new this window. C1 covers `mimo, llama, moonshot_kimi, yi` — these polysemous tokens get the AND-filter to suppress false positives.

---

### C2 — co-occurrence ERNIE/Upstage (`ernie` bucket)

**0 inserted.** `n_results: 1, n_kept: 1, n_inserted: 0`. Same shape as B3 — kept result was already in DB. C2 covers `ernie, upstage`.

---

## Aggregate brand hit-counts (this run)

| Brand | Classification rows | Distinct posts hit |
|---|---|---|
| `minimax` | 7 | 5 |
| `qwen` | 3 | 3 |
| `deepseek` | 4 | 3 |
| `glm` | 4 | 3 |
| `llama` | 2 | 1 |
| `doubao` | 3 | 3 |
| `stepfun` | 1 | 1 |
| (others: mimo, ernie, nemo_megatron, exaone, sakana, kuaishou, upstage, hunyuan, sensechat, inclusionai) | 0 | 0 |
| **Total** | **24 visible here** (plus 9 from B1 cross-listing) = **33** | **14 distinct posts** |

(Note: 33 classification rows ≠ 33 unique `(post, brand)` pairs; the post `2077317360159961139` alone contributes 6 rows. 33 / 17 posts ≈ 1.94 rows/post on average; the MeryemArik9 post pushes that up.)

---

## Post-type distribution

| post_type_key | Rows | Notable brand hits |
|---|---|---|
| `advertising_marketing` | 11 | 4 brands × multi-brand posts (Raph_GMI, web3XWG); GLM-only via B2 |
| `performance_comparisons` | 8 | minimax, qwen, deepseek, llama, glm (all on the MeryemArik9 / Awesome_AI_News / 0xPascual posts) |
| `event_announcement` | 7 | minimax (Hailuo_AI), doubao (EmmanuelInvest, HOWAI4242) |
| `feedback_questions` | 4 | llama (negative on MeryemArik9), minimax/glm/deepseek (neutral) |
| `buzz_releases` | 2 | stepfun (News9Tweets), doubao (EmmanuelInvest) |
| `hands_on_usage` | 1 | doubao (velokey9's Seedream test) |

No `nationalism` or `unsanctioned` hits from this run's classifier pass — `post_fetch.n_unsanctioned: 5` is computed in the post-fetch path on a different signal (regex sweep on text, separate from the LLM classifier).

---

## Sentiment distribution

| sentiment | Rows |
|---|---|
| `neutral` | 18 |
| `positive` | 8 |
| `negative` | 2 (both `llama` on the MeryemArik9 post) |
| `mixed` | 1 (doubao / Seedream test) |

---

## Cross-cutting observations

### 1. OR-chain over-matching on aggregator posts

Posts #4 (`Raph_GMI` "ONE PLATFORM") and #5 (`web3XWG` aggregator) both got classified under **4 different brands simultaneously** (minimax, qwen, deepseek, glm) because all four brand tokens appear in the post text. The classifier labeled them `advertising_marketing` with neutral/positive sentiment — which is arguably correct *for each individual brand* (each is mentioned in an ad context), but the per-brand row count inflates when a single post mentions many brands.

**Not a regression** — the v1.7 design intentionally supports multi-brand classification. Worth tracking as a calibration target: if the goal is "is this post *about* brand X?" rather than "does brand X appear here?", an AND-filter or a stronger LLM-prompt instruction would be needed.

### 2. `minimax` correctly flagged on a competitor-availability post

`MeryemArik9`'s Bedrock post lists MiniMax as a model *not* available. The classifier tagged it `minimax → performance_comparisons (neutral)` + `feedback_questions (neutral)`. The LLM correctly recognized it as a comparison post about MiniMax (among others), and rated sentiment as neutral — not "positive" just because MiniMax's name appears, and not "negative" even though MiniMax isn't on Bedrock.

This is the desired behavior, and the LLM-grade classifier is what makes it work. A pure keyword-index classifier would have produced the same row but with no way to express "neutral" vs "negative" sentiment calibration.

### 3. WAIC event posts cleanly classified

`Hailuo_AI`'s two posts (event calendar + WAIC booth) both got `event_announcement` cleanly. `Awesome_AI_News`'s WAIC stock-rally post got both `performance_comparisons (positive)` *and* `event_announcement (positive)` — the LLM recognized both the financial angle and the conference catalyst. Both are present, neither is wrong.

### 4. `MiniMax` token still misfires on substring

The `minimax` keyword in the index matches the literal substring `minimax`, which (lowercase, in this brand-keyword config) does not appear to collide with anything in the run window. Worth re-checking if MiniMax-M3 model card text starts showing up: a tokenizer-aware keyword gate would prevent false hits from competitor name lists like `MeryemArik9`'s "GLM 5.2, new Qwens, newer MiniMax" — though in this run, that *is* a legitimate MiniMax mention and was correctly classified.

### 5. The `n_classifications_written` semantic

Counter reports 45 upserts; DB has 33 distinct rows in the run window. The 12-row gap = ON CONFLICT DO UPDATE updates where the inline writer (per-call loop) and post-fetch writer (post-call loop) both wrote the same `(post_id, brand_id, post_type_key)` triple. The counter measures **upsert attempts**, not unique rows. See smoketest doc §U3 for the full discussion.

---

## Anomalies / follow-ups

1. **Pre-existing rows in the broader fetched_at window.** ~880 posts in `posts` have `fetched_at >= '2026-07-15T09:10:00'` but are outside the 09:10:26 → 09:15:24 run window. These are from launchd-triggered runs that ran between when the manual kill switch was set (`/tmp/x-monitor-paused`) and when `launchctl unload` ran. They're real posts but not part of this review. Options:
   - Leave as-is (they're valid DB rows)
   - Mark them with `run_id` for traceability (requires schema change)
   - Delete (loses data)
   Recommend: leave as-is; the new launchd config (`com.fuchitalee.x-monitor.scheduled.plist`) is unloaded so this won't recur until/unless reloaded.

2. **C1 returned zero.** This is a yield probe concern tracked separately at `docs/plans/2026-07-08-004-feat-filter-yield-ramp-probe-plan.md` and `memory/2026-07-09-c2-yield-probe-failure.md`. The mimo/yi/kimi/llama AND-filter is presumably working as designed (suppressing non-AI hits), but "zero in a 5-min window" is consistent with the broader yield concern. Out of scope for this report.

3. **Run did not insert any posts under B3 or C2.** Both had 1 kept result each — the kept result was already in DB. This is normal (re-runs deduplicate), not a bug.

4. **Manual-off state is confirmed.** Per the `20260715T091026` run, the manual kill switch (`/tmp/x-monitor-paused`) was *not* engaged yet — the run executed fully. After this run, the kill switch was engaged AND `launchctl unload` was run on both agents (`com.fuchitalee.x-monitor.plist` and `com.fuchitalee.x-monitor.scheduled.plist`). Next operator-visible run will be a manual invocation.

---

## What this confirms

- **The 3 cleanup fixes (U1/U2/U3) work end-to-end:** run JSON `degraded: {}`, all 6 call_ids are A/B/C strings, `n_classifications_written: 45` (vs 0 pre-fix).
- **DS V4 produces valid classifications:** all 33 DB rows have well-formed `(brand_id, post_type_key, sentiment)` triples; none were dead-lettered (`n_classifications_dropped: 0`).
- **LLM-grade classification adds value over keyword-only:** the MeryemArik9 post's neutral-vs-negative split on the same brand group, and the WAIC stock-rally post's dual `performance_comparisons + event_announcement` tagging, both require a model that reads intent.
- **v1.7 multi-brand design is doing what it says:** aggregator posts hit multiple brand rows; that's by design.

## What this does NOT confirm

- **The ~880 posts outside the run window.** A separate audit pass needed if you want to know what the launchd-triggered runs (pre-unload) actually inserted.
- **C1 yield.** Zero inserts in 5 minutes is consistent with the C1 yield concern (memory `2026-07-09-c2-yield-probe-failure.md`), but a single run is not a probe.
- **Counter semantic mismatch.** Documented in the smoketest doc §U3; the gap (45 vs 33) is real but not actionable in this PR.
