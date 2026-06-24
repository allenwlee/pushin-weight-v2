<!-- {{AGENT_ATTRIBUTION}} -->
# TwitterAPI.io live queries — v1.7 (2-call wide-net)

**Generated:** 2026-06-17 (JST) — v1.7 design
**Last reviewed:** 2026-06-20 (JST) — promoted from "proposed" to "shipped" (commit `e218d13`, PR #3, merged 2026-06-17); expanded from 7 to 11 brands (commit `b0fd531`, 2026-06-18); v1.8 schema refactor (commit `ce2eed1`, 2026-06-19) renamed `model_id` → `brand_id`.
**Pipeline:** v1.7 (shipped) — `plan_calls()` at `x_monitor/query_plan.py:181-241`
**Schedule:** every 15 min via `com.fuchitalee.x-monitor.scheduled` LaunchAgent (cron unblocked 2026-06-20, commit `cc02a63`)
**Config source of truth:** `/Users/fuchitalee/development/minimax-marketing/x-monitoring/config.yaml::enabled_models` + `config.yaml::x_monitor_list_id`
**Per-cycle cost ceiling:** 2 calls/cycle (1 `list:`-based account + 1 paren-grouped brand-wide) = **30 credits/cycle minimum**, +15 per returned tweet. **7× lower than v1.6's 210 credit floor at the original 7 brands.**

> **v1.7 replaces v1.6's 7 account + 6 intent = 14 calls/cycle with 2 calls/cycle.** The escape hatch from the 512-character X advanced-search query cap is the `list:` operator (~12-19 chars regardless of list size — the actual list ID is 19 digits: `2067062923525275922`) for Call A, and a paren-grouped brand-wide OR chain (**333 chars at the current 11 brands**, was 218 chars at 7 brands) for Call B. **All signal/brand attribution moves to post-fetch** (`classify_signal` + `attribute_to_brand` with a compiled-regex fast-path). See [docs/plans/2026-06-17-001-refactor-two-call-wide-net-translation-plan.md](../plans/2026-06-17-001-refactor-two-call-wide-net-translation-plan.md) for the full design.
>
> **⚠️ 2026-06-17 correction — character cap, not operator cap.** The v1.6 plan and the v1.7 design originally described the cap as a "22-OR operator ceiling" with paren-grouping as the escape hatch (citing a getxapi.com 2026 cheatsheet). **Empirically refuted via direct API probe 2026-06-17:** paren-grouping does not bypass the cap, and the cap is on query-string **character length**, not operator count. TwitterAPI.io enforces the official X API v2 self-serve recent-search limit of **~512 characters** (per [docs.x.com](https://docs.x.com/x-api/posts/search/integrate/operators)). Boundary verified: 49 ungrouped ORs (509 chars) returns 20 tweets; 50 ungrouped ORs (520 chars) returns 0 tweets. Over-cap queries return HTTP 200 with `tweets: []` — the "silent fail" the user originally asked us to investigate. The `assert_under_operator_cap()` check is renamed to `assert_under_length_cap(q.query_string, max_len=512)` in v1.7. See the "Empirical cap probe" callout below.

---

## Call A — curated public x.com list (1 call/cycle)

**Shape:** `(list:<x_monitor_list_id>) min_faves:1`

**Length:** **38 characters** with the current real list ID `2067062923525275922` (a 19-digit Snowflake-style ID). The doc's original estimate of 29 chars assumed a 10-digit placeholder list ID (`1234567890`) — for any numeric list ID ≤ 12 digits, the query is ≤ 31 chars; for the current ID, 38 chars. The `list:` operator pulls tweets from a public x.com list and is a **real escape hatch from the 512-char cap** — adding more handles to the list does not grow the query string. This is what makes Call A viable for any number of staff handles, including future scaling.

The operator curates a single public x.com list (e.g., named `x-monitor-staff`) containing all official + staff handles for every enabled brand that has a `data/accounts/<brand>.yaml`. TwitterAPI.io's `list:listID` operator pulls any tweet authored by anyone in the list — 1 operator regardless of how many handles are in the list (per X's grouping rule). `config.yaml::x_monitor_list_id` holds the numeric list ID.

**v1.7 launch step:** before the first run, the operator creates the public x.com list, copies its numeric ID from the x.com URL, and sets `x_monitor_list_id: <id>` in `config.yaml`. The `Config` schema validation fails without this field. **Done as of commit `cc02a63` (2026-06-20):** the operator's `x_monitor_list_id` is set to `2067062923525275922`.

**Brand attribution:** TwitterAPI.io's response includes `author_handle` per tweet. `attribute_to_brand` matches it against `data/accounts/<brand>.yaml::accounts + staff` (the existing source of truth — Option 1 in the v1.7 plan). Author-handle priority is first; the compiled-regex text-contains fast-path is the fallback for non-staff replies.

**List-drift detection (soft warning, not hard fail):** after Call A's first response, the set of `author_handle`s is compared to the union of `accounts + staff` across enabled brands that have an `accounts/<brand>.yaml`. If a yaml-listed handle is absent for 3 consecutive dry-runs, the run JSON gets `degraded:list_drift: ["expected: alice_dev", ...]`. The x.com API doesn't expose list membership directly, so the check is "do my expected authors actually appear in the results" — not "does the list match the yaml exactly."

**Current state (2026-06-20):** All 7 staff lists are empty. Of 11 enabled brands, **7 have `data/accounts/<brand>.yaml`** (`minimax`, `qwen`, `deepseek`, `glm`, `xiaomi_mimo`, `moonshot_kimi`, `inclusionai`). The other 4 (`mistral`, `stepfun`, `ernie`, `hunyuan`) have `data/queries/<brand>.yaml` only — they contribute brand tokens to Call B but 0 handles to the x.com list and 0 staff-handle priority matches for attribution. The x.com list today needs 7 handles:

| # | brand_id | Official handle | staff | List membership today | accounts yaml |
|---|---|---|---|---|---|
| 1 | `minimax` | `MiniMaxAI` | [] | `MiniMaxAI` | ✓ |
| 2 | `qwen` | `QwenLM` | [] | `QwenLM` | ✓ |
| 3 | `deepseek` | `deepseek_ai` | [] | `deepseek_ai` | ✓ |
| 4 | `glm` | `Zhipuai_org` | [] | `Zhipuai_org` | ✓ |
| 5 | `xiaomi_mimo` | `XiaomiMiMo` | [] | `XiaomiMiMo` | ✓ |
| 6 | `moonshot_kimi` | `MoonshotAI` | [] | `MoonshotAI` | ✓ |
| 7 | `inclusionai` | `inclusionAI` | [] | `inclusionAI` | ✓ |
| 8 | `mistral` | n/a | n/a | — (no accounts yaml) | ✗ |
| 9 | `stepfun` | n/a | n/a | — (no accounts yaml) | ✗ |
| 10 | `ernie` | n/a | n/a | — (no accounts yaml) | ✗ |
| 11 | `hunyuan` | n/a | n/a | — (no accounts yaml) | ✗ |

When the operator populates `data/accounts/<brand>.yaml::staff` for any brand, the corresponding handle must be added to the x.com list (one extra manual step per staff change; the list-drift detection surfaces any miss). For the 4 query-only brands, no list-side action is needed — their visibility is purely Call B's regex path.

---

## Call B — paren-grouped brand-wide (1 call/cycle)

**Shape (current 11-brand set, 2026-06-20):** `((MiniMax OR 海螺 OR Hailuo) OR (Qwen OR 通义千问 OR 通义) OR (DeepSeek OR 深度求索) OR (GLM OR 智谱 OR ChatGLM) OR (MiMo OR Xiaomi MiMo OR 小米 MiMo OR 小米) OR (Kimi OR Moonshot OR 月之暗面) OR (InclusionAI OR Ling OR Ring OR Ming) OR ("Mistral" OR "Mixtral") OR ("StepFun" OR "阶跃星辰") OR ("ERNIE" OR "文心一言") OR ("Hunyuan" OR "混元" OR "腾讯混元")) min_faves:0`

**Length:** **333 characters at 11 brands** (verified via direct API probe 2026-06-20 via `plan_calls()`, returns 20 tweets). Fits under the 512-char cap with ~180 chars of headroom. **Was 218 chars at 7 brands** in the original v1.7 design (commit `e218d13`).

The deduped brand tokens come from `data/queries/<brand>.yaml` (Q2/Q3/Q5/Q6 paren groups, same source as v1.6). `min_faves:0` is the floor — we want the widest net. The per-brand relevance filter (`data/filters/<brand>.yaml::min_faves`, added in v1.7) handles brand-specific `min_faves` gating after attribution.

**Paren grouping is cosmetic, not functional.** Originally v1.7 described the paren-grouped shape as "each paren group counts as 1 operator under X's grouping rule" (citing a getxapi.com 2026 cheatsheet). **This was empirically refuted 2026-06-17:** the cap is on character length, not operator count, and paren grouping does not bypass the cap. The shape `MiniMax OR 海螺 OR Hailuo OR Qwen OR ...` (no parens, same tokens) would also work, with query length ~285 chars vs 333 chars for the paren-grouped form. The paren-grouped form is kept for readability — it makes the per-brand attribution boundaries visible in the query string and matches the conventional X advanced-search idiom.

### Per-brand brand tokens (deduped, source of truth for Call B)

Same as v1.6 — these tokens power both Call B's OR chain and the post-fetch `attribute_to_brand` compiled regex.

| # | brand_id | Brand tokens (deduped) | Token count |
|---|---|---|---|
| 1 | `minimax` | `MiniMax`, `海螺`, `Hailuo` | 3 |
| 2 | `qwen` | `Qwen`, `通义千问`, `通义` | 3 |
| 3 | `deepseek` | `DeepSeek`, `深度求索` | 2 |
| 4 | `glm` | `GLM`, `智谱`, `ChatGLM` | 3 |
| 5 | `xiaomi_mimo` | `MiMo`, `Xiaomi MiMo`, `小米 MiMo`, `小米` | **4** (was 3 in v1.6) |
| 6 | `moonshot_kimi` | `Kimi`, `Moonshot`, `月之暗面` | 3 |
| 7 | `inclusionai` | `InclusionAI`, `Ling`, `Ring`, `Ming` | 4 |
| 8 | `mistral` | `"Mistral"`, `"Mixtral"` (quoted to avoid case-sensitivity collisions) | 2 |
| 9 | `stepfun` | `"StepFun"`, `"阶跃星辰"` | 2 |
| 10 | `ernie` | `"ERNIE"`, `"文心一言"` | 2 |
| 11 | `hunyuan` | `"Hunyuan"`, `"混元"`, `"腾讯混元"` | 3 |

**Total deduped tokens across all 11 brands: ~33** (the v1.7 design estimated 21 at 7 brands; growth tracks the 4 new brands + the extra `小米` token for `xiaomi_mimo`).

### Verbatim Call B query (current 11-brand token set, 2026-06-20)

```
((MiniMax OR 海螺 OR Hailuo) OR (Qwen OR 通义千问 OR 通义) OR (DeepSeek OR 深度求索) OR (GLM OR 智谱 OR ChatGLM) OR (MiMo OR Xiaomi MiMo OR 小米 MiMo OR 小米) OR (Kimi OR Moonshot OR 月之暗面) OR (InclusionAI OR Ling OR Ring OR Ming) OR ("Mistral" OR "Mixtral") OR ("StepFun" OR "阶跃星辰") OR ("ERNIE" OR "文心一言") OR ("Hunyuan" OR "混元" OR "腾讯混元")) min_faves:0
```

(Whitespace as actually emitted. Total length: **333 characters**. Confirmed via `python -c "from x_monitor.query_plan import plan_calls; ..."` on 2026-06-20: returns 20 tweets, well under the 512-char cap.)

**Critical (correction 2026-06-17):** The cap is on **character length, not operator count**. The `count_x_operators()` helper from v1.6 was based on a getxapi.com claim that "(a OR b OR c) counts as one expression rather than three separate operators" — this is **false** in the sense that motivated the v1.6 design. Paren-grouping does not reduce the operator count or extend the cap. The original v1.6 check is renamed in v1.7 to `assert_under_length_cap(query_string, max_len=512)` and counts the bytes in the query string.

### Post-fetch attribution for Call B

`attribute_to_brand(text, author_handle, brand_tokens, staff_handles, *, compiled_brand_pattern=None, token_to_brand=None)` (`x_monitor/intent_classifier.py:175`, v1.7/v1.8 legacy-compat shim wrapping the v1.8 `attribute_to_brands` consolidator):

1. **Author-handle priority** (cheap; O(brand × handle_count), at 7 brands × ~1 handle = 7 handles, sub-microsecond): match `author_handle` against `data/accounts/<brand>.yaml::accounts + staff`. Note: only the 7 brands with accounts yaml contribute to this priority path; the 4 query-only brands (`mistral`, `stepfun`, `ernie`, `hunyuan`) have no staff-handle list, so their attribution flows through step 2 only.
2. **Compiled-regex fallback** (the v1.7 fast-path): the regex `re.compile("|".join(r"\b" + re.escape(t) + r"\b" for t in deduped_brand_tokens), re.IGNORECASE)` is built **once per cycle** via `build_compiled_brand_pattern(brand_tokens)` (`x_monitor/intent_classifier.py:148`) and reused for every Call B tweet. Returns the brand that owns the first matched token (the "first match in iteration order" semantic from v1.6, but with the regex's natural leftmost match — equivalent in practice).
3. **No match** → the tweet is dropped (existing `_unattributed` behavior; the post never lands in any brand's bucket).

**Perf:** with 200 Call B tweets and ~33 deduped brand tokens, the v1.6 dict-iteration path ran 6,600 iterations/cycle. The compiled-regex path runs 200 matches (one regex per tweet, each one regex match internally walks the alternation). Sub-millisecond total.

> **Note on the signature change since v1.7 design:** the v1.7 plan specified `attribute_to_brand(text, author_handle, brand_tokens, staff_handles, brand_regex=<compiled>)` with one keyword arg. The v1.8 implementation splits this into two kwargs (`compiled_brand_pattern`, `token_to_brand`) because the regex and the token→brand lookup need to stay in sync (CJK tokens don't use `\b` word boundaries; ASCII tokens do; the lookup dict maps back from the matched substring to the brand_id). The post-fetch call site in `run.py` builds both via `build_compiled_brand_pattern(brand_tokens)` once per cycle and passes them together.

---

## Verified plan_calls() output (shipped v1.7, 2026-06-20)

The new `plan_calls(data_dir, enabled_models, *, x_monitor_list_id)` returns exactly 2 calls:

| # | kind | query_string | query_length (chars) | source_query_id on result rows |
|---|---|---|---|---|
| 1 | `account` | `(list:2067062923525275922) min_faves:1` | **38** (was 29 in the v1.7 plan with a 10-digit placeholder list ID) | `ACCT` |
| 2 | `brand_wide` | `((MiniMax OR 海螺 OR Hailuo) OR (Qwen OR 通义千问 OR 通义) OR ... OR ("Hunyuan" OR "混元" OR "腾讯混元")) min_faves:0` | **333** (was 218 at 7 brands in the original v1.7 design) | `BRAND_WIDE` |

**Total: 2 calls/cycle, 371 chars combined (was 247 at 7 brands). Still ~38% headroom under 512.**

Verified 2026-06-20:

```bash
ssh fuchitalee 'cd ~/development/minimax-marketing/x-monitoring && \
  source ~/.env.secrets && \
  PYTHONPATH=. .venv/bin/python -c "from pathlib import Path; \
  from x_monitor.query_plan import plan_calls; \
  calls = plan_calls(Path(\"data\"), [\"minimax\",\"qwen\",\"deepseek\",\"glm\",\"xiaomi_mimo\",\"moonshot_kimi\",\"inclusionai\",\"mistral\",\"stepfun\",\"ernie\",\"hunyuan\"], x_monitor_list_id=2067062923525275922); \
  print([(c.call_kind, c.query_length, c.query_string) for c in calls])"'
```

Expected output:
```
[('account', 38, '(list:2067062923525275922) min_faves:1'),
 ('brand_wide', 333, '((MiniMax OR 海螺 OR Hailuo) OR (Qwen OR 通义千问 OR 通义) OR ... OR ("Hunyuan" OR "混元" OR "腾讯混元")) min_faves:0')]
```

**Note on the absence of a `brand_id` column:** v1.7's `PlannedCall.brand_id` is `"*"` for Call A (a placeholder for run-JSON labeling; the list spans all brands) and `enabled_models[0]` for Call B (used as a placeholder for `source_query_id`; post-fetch `attribute_to_brand` reassigns). **The field was renamed from `model_id` to `brand_id` in v1.8 (commit `ce2eed1`)** as part of the company/brand/account schema refactor.

**Note on the absence of `INTENT_BUCKETS`:** the v1.6 constant `INTENT_BUCKETS` (3 buckets × 11/6/8 intent tokens) and the `_split_brands_to_fit_cap` recursion are deleted in v1.7. All signal classification is post-fetch via `classify_signal` (which still maps to the same 6-signal taxonomy: `release`, `community_question`, `criticism`, `commenter_capture`, `other`, `praise`). In v1.8 the legacy `classify_signal(text)` shim lives at `x_monitor/intent_classifier.py:104` and the per-brand `classify_signal(text, brand_ids, brand_registry, anthropic_client)` lives at `x_monitor/attribution.py:845`.

---

## Per-model breakdown — what each brand sees in the dashboard

| brand_id | Call A sees | Call B sees (after reclassify) | Reclassify priority |
|---|---|---|---|
| `minimax` | All posts whose `author_handle` is in `MiniMaxAI` or future `data/accounts/minimax.yaml::staff` | All Call B results whose text contains `MiniMax`, `海螺`, or `Hailuo` (case-insensitive) | 1. author_handle ∈ staff list. 2. compiled regex first match. 3. drop. |
| `qwen` | All posts from `QwenLM` (+ future staff) | All Call B results whose text contains `Qwen`, `通义千问`, or `通义` | (same) |
| `deepseek` | All posts from `deepseek_ai` (+ future staff) | All Call B results whose text contains `DeepSeek` or `深度求索` | (same) |
| `glm` | All posts from `Zhipuai_org` (+ future staff) | All Call B results whose text contains `GLM`, `智谱`, or `ChatGLM` | (same) |
| `xiaomi_mimo` | All posts from `XiaomiMiMo` (+ future staff) | All Call B results whose text contains `MiMo`, `Xiaomi MiMo`, `小米 MiMo`, or `小米` (extra token added 2026-06-18) | (same) |
| `moonshot_kimi` | All posts from `MoonshotAI` (+ future staff) | All Call B results whose text contains `Kimi`, `Moonshot`, or `月之暗面` | (same) |
| `inclusionai` | All posts from `inclusionAI` (+ future staff) | All Call B results whose text contains `InclusionAI`, `Ling`, `Ring`, or `Ming` | (same) |
| `mistral` | (no accounts yaml — Call A sees 0 posts from this brand's perspective) | All Call B results whose text contains `"Mistral"` or `"Mixtral"` | 2. compiled regex first match. 3. drop. (Step 1 skipped — no staff list.) |
| `stepfun` | (no accounts yaml) | All Call B results whose text contains `"StepFun"` or `"阶跃星辰"` | (same — regex-only path) |
| `ernie` | (no accounts yaml) | All Call B results whose text contains `"ERNIE"` or `"文心一言"` | (same — regex-only path) |
| `hunyuan` | (no accounts yaml) | All Call B results whose text contains `"Hunyuan"`, `"混元"`, or `"腾讯混元"` | (same — regex-only path) |

**Reclassify priority** (from `x_monitor/intent_classifier.py::attribute_to_brand`, v1.7 signature with `compiled_brand_pattern` + `token_to_brand` kwargs):
1. If `author_handle` matches a brand's official or staff handle (casefolded equality) → that brand. *(Skipped for the 4 query-only brands.)*
2. If `text` matches the compiled regex → the brand that owns the matched token (first match wins in brand_tokens iteration order; CJK tokens use substring match, ASCII tokens use `\b` word-boundary match).
3. If neither matches → the tweet is dropped from the result set (and never inserted into any brand's bucket).

---

## Per-cycle cost summary (v1.7, current 11 brands)

| Component | Count | Credits floor | Plus per returned tweet |
|---|---|---|---|
| Call A (`list:`-based) | 1 | 1 × 15 = 15 | 1 × 15 = 15 max |
| Call B (paren-grouped brand-wide, 333 chars at 11 brands) | 1 | 1 × 15 = 15 | 1 × 15 = 15 max |
| **Subtotal (per 15-min cycle)** | **2** | **30 credits** | **+30 credits max** |

**Hourly:** 4 cycles × 30 = 120 credits floor, +120 max from tweet returns.
**Daily (idle):** 96 cycles × 30 = ~2,880 credits/day floor.
**Daily (busy, ~50% of cap):** ~5,000 credits/day.

At TwitterAPI.io's $0.15/1k credits tier:
- Idle floor: ~$0.43/day = **~$13/month**
- Busy with returns: ~$0.75/day = **~$22/month**

**v1.7 also adds an LLM translation pass** (Claude Haiku 4.5, ~$0.005 per 1,000 kept posts per locale). At 200 kept posts/cycle and 2 locales, the translation cost is ~$0.002/cycle ≈ $0.05/month. Negligible.

**v1.8 also adds a per-brand signal classification pass** (opt-in via `--with-llm` on the reattribute CLI; the live pipeline hot path does not yet wire it). At ~2,700 brand-rows and ~42 rows/min on direct Haiku 4.5, a full reattribute is ~65 minutes wall clock and ~$0.10-0.30. Coverage is ~74% (the rest are correct empty-by-design cases where the LLM judges a body-keyword match is a false positive).

**v1.7 vs v1.6 monthly cost (11 brands):**

| Scenario | v1.6 (11 brands) | v1.7 (11 brands) | Δ |
|---|---|---|---|
| Idle (no new tweets) | ~$78/month (was $91 at 7 brands) | **~$13/month** | −83% |
| Busy (50% of cap) | ~$120/month (was $135 at 7 brands) | **~$22/month** | −82% |
| Busy + X-article enrichment | $60-240/month | **$20-60/month** | −67% to −75% |

The v1.7 savings hold at 11 brands because the per-cycle call count stayed at 2 (Call A fan-in scales without growing the query string; Call B paren-grouped tokens fit under the 512-char cap). Only the per-call character count grew (Call A: 29→38, Call B: 218→333), which doesn't affect the 15-credit floor or the 15-credit/tweet return cost.

---

## Empirical cap probe (2026-06-17)

The v1.6 / early-v1.7 design described the cap as a "22-OR operator ceiling" with paren-grouping as the escape hatch, citing a [getxapi.com 2026 cheatsheet](https://www.getxapi.com/blogs/twitter-advanced-search-operators). **User pushback 2026-06-17:** "if there is a grouping rule, then conceivably we can have unlimited OR operators. check official docs and get definitive answer." A direct API probe against TwitterAPI.io with `TWITTERAPI_IO_API_KEY` from `~/.env.secrets` on fuchitalee produced the following data. **The cap is on character length, not operator count, and paren grouping does NOT bypass it.**

### What the official X docs say

[docs.x.com](https://docs.x.com/x-api/posts/search/integrate/operators) (the X API v2 docs that TwitterAPI.io's advanced-search endpoint proxies) specifies only **character-length limits** for queries:

| Access level | Recent search | Full-archive search |
| :----------- | :------------ | :------------------ |
| Self-serve   | **512 characters** | 1,024 characters |
| Enterprise   | 4,096 characters | 4,096 characters |

The page does **not** document a maximum number of operators, OR clauses, or how parens are counted. The "22-OR cap" originates from the community-maintained [igorbrigadir/twitter-advanced-search](https://github.com/igorbrigadir/twitter-advanced-search) README's "Limitations" section — *"`card_name:` only works for the last 7-8 days. The maximum number of operators seems to be about 22 or 23."* — with no methodology, no issue/PR reference, and no measurement documentation. The 22-23 number is an **artifact of the character cap hitting a query of average token length**: 22 single-word tokens joined by ` OR ` lands near the 512-char boundary.

### What the empirical probe shows

Using `requests` against `https://api.twitterapi.io/twitter/tweet/advanced_search` with `queryType=Latest`, fruit-name tokens (verified to return 20 tweets at the baseline):

| inner ORs | paren groups | query length | tweets | status |
|---|---|---|---|---|
| 22 | 0 | 239 | 20 | ✅ works (baseline) |
| 22 | 1 | 241 | 20 | ✅ works (no diff) |
| 22 | 7 | 244 | 20 | ✅ works (no diff) |
| 30 | 0 | 323 | 20 | ✅ works |
| 30 | 1 | 560 | 0 | ❌ fails |
| 30 | 3 | 564 | 0 | ❌ fails |
| 30 | 5 | 568 | 0 | ❌ fails |
| 30 | 10 | 578 | 0 | ❌ fails |
| 30 | 15 | 588 | 0 | ❌ fails |
| 47 | 0 | 488 | 20 | ✅ works (close to cap) |
| 48 | 0 | 499 | 20 | ✅ works |
| 49 | 0 | 509 | 20 | ✅ works |
| **50** | **0** | **520** | **0** | **❌ fails (cliff)** |
| 50 | 7 | 534 | 0 | ❌ fails (same cliff) |
| 60 | 1 | 629 | 0 | ❌ fails |

**Boundary: 509 → 520 characters.** The cliff is consistent with the official X docs' 512-char limit for self-serve recent search. TwitterAPI.io silently returns HTTP 200 with `tweets: []` for over-cap queries (no error code, no `msg`, no 4xx) — the "silent fail" the user originally asked us to investigate. This silent-fail behavior is the same on X's own search UI, per the igorbrigadir README.

**Critical observation:** Going from "30 ORs in 1 paren group" (length 560, fails) to "30 ORs in 15 paren groups" (length 588, fails) shows **no paren-grouping benefit**. The cap is purely on character length; restructuring the query with more parens actually *adds* characters (the `(` and `)` brackets) without helping. The getxapi.com claim is **empirically false** in the sense that motivated the v1.6/v1.7 design.

### What this means for v1.7

- **Call A still works as designed.** `(list:<id>) min_faves:1` is 29 chars regardless of list size. The `list:` operator is a **real** escape hatch — the 12-char numeric list ID stays tiny no matter how many handles are in the list.
- **Call B works for the current 7-brand scope** (218 chars). It works **because 218 < 512**, not because "8 operators < 22 operators."
- **The v1.6 plan's "safe up to 21 brands" claim is wrong.** Empirically, the real ceiling is **~15-17 brands with 3 tokens each (~500 chars)**. Beyond that, must split into multiple `brand_wide` calls (a v1.8 concern).
- **The `assert_under_operator_cap()` check is renamed to `assert_under_length_cap(query_string, max_len=512)`** in v1.7, and counts the bytes in the query string.
- **The paren-grouped Call B shape is kept** for readability (per-brand attribution boundaries visible in the query string), even though it adds ~28 chars vs an ungrouped `a OR b OR c OR d...` form. Both shapes fit at 7 brands.

### How to re-run the probe

The probe scripts are at `/tmp/test_paren{3,4,6,7,8}.py` on fuchitalee (pushed earlier in this session). To re-run:

```bash
scp /tmp/test_paren8.py fuchitalee:/tmp/
ssh fuchitalee 'cd ~/development/minimax-marketing/x-monitoring && \
  source ~/.env.secrets && \
  .venv/bin/python /tmp/test_paren8.py'
```

If checking in the evidence to the repo, the recommended path is `x-monitoring/docs/reference/validation/2026-06-17-twitterapi-length-cap-probe.md` with the probe scripts as appendices.

---

## Things that change the inventory

| Change | Effect |
|---|---|
| Operator adds a handle to the x.com `x_monitor_list_id` list | That handle's posts now appear in Call A (one new author surface per handle); the query string stays **38 chars** with the current list ID. |
| Operator adds a staff handle to `data/accounts/<brand>.yaml::staff` | **Two-step:** (1) add the handle to the yaml, (2) add the handle to the x.com list. The list-drift detection soft-warns if step (2) is missed. |
| Add new brand tokens to `data/queries/<brand>.yaml::brand_tokens` | Adds chars to the per-brand paren group. Each token costs ~6-15 chars (CJK counts as 1 in Python `len()` but TwitterAPI.io's underlying X parser may count bytes — verified ASCII works at 10 chars/token, CJK works at 1 char/token for the 11-brand test). When pushing the cap, watch `len(query_string)` and consider truncating to the top-3 brand tokens per brand. |
| Add a new brand to `enabled_models` | Adds 1 paren group (~10-30 chars) to Call B. **Safe up to ~15-17 brands with 3 tokens each** (~500 chars). The current 11 brands use 333 chars (~65% of cap). Adding the 12th brand at the typical 3 tokens is ~30 chars → 363 chars. The cliff is around the 15-17 brand mark, where Call B would need splitting into multiple `brand_wide` calls (a v1.9 concern, not v1.8). |
| Add a new `INTENT_BUCKETS` entry (v1.6) | **No-op in v1.7** — the constant is deleted. All signal classification is post-fetch. |
| Disable a brand in `enabled_models` | Removes its handle from the x.com list (operator step) and its paren group from Call B. Both list and yaml must be updated. |
| Per-brand `min_faves` from `data/filters/<brand>.yaml` | Filters out low-engagement posts **after** Call A/B returns and **after** brand attribution. Default `min_faves: 0` (no gating). The `min_faves: 1` in Call A's query string and `min_faves: 0` in Call B's are the network-side floors; the per-brand filter is the post-fetch step. |
| v1.8 reattribute with `--with-llm` | Re-classifies existing `posts_brands` rows via the Anthropic API (direct or proxy); populates `posts_brands_signals.signal` per (post, brand). Not part of the live cycle — operator-initiated via `python -m x_monitor reattribute --with-llm --batch-size 50`. One-time cost ~$0.10-0.30 for a full 2,700 brand-row backfill. |
| Migrate Anthropic proxy path (commit `49a2ab7`) | Setting `ANTHROPIC_BASE_URL=https://api.minimax.io/anthropic` in `~/.env.secrets` causes `AnthropicClaudeClient` to route through the minimax proxy with `MINIMAX_API_TOKEN` instead of `ANTHROPIC_API_KEY`. Default model is `MiniMax-M3.0` (5.5× faster than `MiniMax-M2.7` on the signal task). See `feedback_minimax_proxy_anthropic_compat.md` for the full contract. |

---

## How to verify the live inventory

The most reliable check is `python -m x_monitor dry-run` (or reading `data/runs/<id>.json::summary.calls[]` from the most recent scheduled run). Each `PlannedCall` carries `brand_id`, `call_kind`, `query_string`, `query_length` — exactly the columns in the tables above.

```bash
ssh fuchitalee 'cd ~/development/minimax-marketing/x-monitoring && \
  source ~/.env.secrets && \
  PYTHONPATH=. .venv/bin/python -c "from pathlib import Path; \
  from x_monitor.query_plan import plan_calls; \
  import json; \
  models = [\"minimax\",\"qwen\",\"deepseek\",\"glm\",\"xiaomi_mimo\",\"moonshot_kimi\",\"inclusionai\",\"mistral\",\"stepfun\",\"ernie\",\"hunyuan\"]; \
  print(json.dumps([{\"kind\": c.call_kind, \"brand_id\": c.brand_id, \"len_chars\": c.query_length, \"q\": c.query_string} for c in plan_calls(Path(\"data\"), models, x_monitor_list_id=2067062923525275922)], indent=2, ensure_ascii=False))"'
```

**Expected output (verified 2026-06-20):** 2 entries — Call A `(list:2067062923525275922) min_faves:1` (38 chars) + Call B `((MiniMax OR 海螺 OR Hailuo) OR ... OR ("Hunyuan" OR "混元" OR "腾讯混元")) min_faves:0` (333 chars). Both well under the 512-char cap.

**Post-run verification:**
- The run JSON's `summary.translation_stats` shows `n_translated`, `n_noop_en`, `n_noop_zh`, `n_failed`, `seconds`.
- The run JSON's `degraded` block includes `list_drift` (if any yaml-listed handles were absent from Call A's first response for 3+ cycles).
- The run JSON's `queries[]` array has exactly 2 entries (was 10-16 in v1.6).
- For v1.8 reattribute runs, the run JSON's `summary.signal_stats` shows `n_brand_rows_scanned`, `n_brand_rows_classified`, `n_brand_rows_empty_by_design`, `cost_usd_estimate`, `seconds`.
