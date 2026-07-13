# U3 evidence report review notes

Source: `tests/classifier_tests/20260713T040301_0000-bbf72b83-u3-evidence.md`
Reviewer: Allen
Date: 2026-07-13

The "tweet #N" in Allen's review comments maps 1:1 to the "#### #N"
entry in the report (the script numbers tweets globally across all
6 calls). The same `tweet_id` can appear at multiple #N (e.g. #5
and #13 share `2076516742621503588`).

---

## #1 — Table name and "signals is deprecated"

**Confirmed:** the table is `posts_brands_signals` (plural `posts`,
plural `brands`, plural `signals`). Schema:

```sql
CREATE TABLE posts_brands_signals (
    post_id       TEXT NOT NULL,
    brand_id      TEXT NOT NULL,
    post_type_key TEXT NOT NULL,
    sentiment     TEXT,
    PRIMARY KEY (post_id, brand_id, post_type_key),
    FOREIGN KEY (post_id)       REFERENCES posts(tweet_id)       ON DELETE CASCADE,
    FOREIGN KEY (brand_id)      REFERENCES brands(nickname)      ON DELETE SET NULL,
    FOREIGN KEY (post_type_key) REFERENCES post_type_keys(key)   ON DELETE RESTRICT,
    FOREIGN KEY (sentiment)     REFERENCES sentiment_keys(key)   ON DELETE RESTRICT,
    CHECK (brand_id <> '_unattributed')
);
```

`sentiment` is a **column on this table** (FK to `sentiment_keys.key`),
not a separate table. `sentiment_keys` has 4 rows: `positive` (id 1),
`negative` (id 2), `neutral` (id 3), `mixed` (id 4).

**No matches** in the codebase for `post_brands_sentiments` (singular
`post`, missing final `s`) or any `signals is deprecated` note.
`posts_brands_sentiments` (with the `s`) was the v1.6 name;
`posts_brands_signals` is the v1.7 canonical name and is the active
table. No deprecation work pending.

---

## #2 — Tweet #2 (tweet_id `2076517824500294086`, INSERTED IN DB)

- **Author:** @NyamaQuarter · `lang: en`
- **Post id:** 7540
- **Text:** "✅ Top AI LLM Models for Every Task. Ask Gemini 3.1 Pro
  FREE now 👉 [link]. → Writing & Research: Grok 4.3, GLM 5.1,
  GPT-5.5, Claude 4.6, Gemini 3.1 Pro, Perplexity → Social Content:
  Grok 4, GPT o3, DeepSeek → Academic / STEM: Claude Opus 4.7,
  MiniMax M2.7 [link]"
- **Brand edges (3):** `deepseek` (0.333), `glm` (0.333),
  `minimax` (0.333)
- **Signals (3):** all `advertising_marketing` / `neutral`
- **Discourse (3):** role=`advertising-marketing` (id 10), act_id=1,
  both nationalisms `none` (id 1)
- **Unsanctioned flags:** `[]` (empty)

**Reviewer corrections vs current classification:**

| Field | DB value | Reviewer assertion | Verdict |
|---|---|---|---|
| `lang_detected` | `NULL` | "is not null (global)" | **Bug (global).** NULL even though `lang: en` is set on the tweet by the Twitter API. Same bug on every tweet in the report. Plan 2026-07-13-002 U1 candidate. |
| `text_zh_cn` | `''` | "should be populated (global)" | **Bug (global).** Empty for an English-source post. The classifier should always populate `text_zh_cn` (Chinese translation) and `text_en` (source text or English translation). For source-language English, `text_en` should be the source text itself and `text_zh_cn` the Chinese translation. Currently both are empty. |
| Unsanctioned flag | `[]` | "positive (due to direct call to action)" | **Agree — should be flagged.** This is exactly the kind of promotional CTA `marketing_spam` was designed for: aggregator list with "Ask Gemini 3.1 Pro **FREE** now 👉" CTA. The brand edges + signals are correct (3 brands genuinely named, post is advertising), but the unsanctioned flag is missing. **False negative** in the LLM's output. Plan 2026-07-13-002 U1 target. |
| `posts_brands.weight` | `0.333…` each | "weights may be outdated; I thought for each brand mention we are just counting once (for calculation of UI)" | **Architecture question, not a bug.** `posts_brands.weight` is a per-post × per-brand `1/N` uniform split (3 brands → 1/3 each). It's a legacy read path; brand presence is binary in the UI rendering layer. The `1/N` split only makes sense for fractional attribution; it's a poor fit here. Plan candidate for U5: drop the column, replace with a `presence` boolean, or use a more meaningful formula (TF-IDF, mention count, text position). |

**Discourse check:** the `advertising-marketing` role (id 10) is a
valid key in the `discourse_keys` lookup table — that's why the
discourse insert succeeded for this post. This is a *different*
failure mode from the KTD5 dead-letter path that hits tweets
#8 / #11 / #12 (where the LLM emitted a key not in the lookup table).

---

## #3 — Tweet #3 (tweet_id `2076517522514321766`, INSERTED IN DB)

- **Author:** @Colosteve2000 · `lang: en`
- **Post id:** 7559
- **Text:** "I got to use more S tier frontier model than every
  before. I made my website's more efficient. I worked on some new
  agentic software (to reduce token usage and prompt usage) I
  researched Quantum computers. 5.6 Sol is the best model i have
  ever used. Better than 5.5 Better than Opus 4.8, Better than GLM 5.2"
- **DB state:** 1 brand edge (`glm`, weight 1.0); signal
  `glm / hands_on_usage / negative`; discourse
  `glm / dunk_yingyang (id 3) / both nationalism none`.
- **Reviewer assertion:** "sentiment is actually positive, because
  it's being compared to frontier models."

**Verdict: confirmed — current `negative` and `dunk_yingyang` are
wrong.** The tweet is an enthusiastic comparison: the author is
positive about 5.6 Sol and uses GLM 5.2 as a comparison point
("Better than GLM 5.2"). This is not dunking on GLM; it's ranking
frontier models. The correct sentiment for the GLM edge is
`neutral` (mentioned as a comparison, not evaluated negatively) and
the correct discourse role is something like a `performance_ranking`
or `genuine_review` (not `dunk_yingyang`, which is a hostile
dismissal). The `hands_on_usage` post_type is also wrong — this
is more like `performance_comparisons` (the author is comparing
multiple frontier models).

**Fix candidate for U1:** add a "comparative mention ≠ negative"
rule to the sentiment prompt (same root cause as #10).

---

## #4 — Tweet #4 (tweet_id `2076517375407792635`, INSERTED IN DB)

- **Author:** @GlbGPT (or some GLM-aggregator account)
- **Post id:** 7560
- **Text:** "🎉 BREAKING NEWS: GLM 5.1 IS COMING TO @GlbGPT! Try it 👉
  [link]. Stronger multilingual ability → smoother communication
  across languages 🌍. Advanced coding + reasoning → solve tasks
  with better structure and accuracy 💻. Efficient AI workflow →
  write, analyze, summarize, and create faster than ever 🚀"
- **DB state:** 1 brand edge (`glm`, weight 1.0); signal
  `glm / buzz_releases / positive`; discourse
  `glm / advertising-marketing (id 10) / both nationalism none`;
  unsanctioned `[]`.
- **Reviewer assertion:** "unsanctioned flag = positive (due to
  direct call to action)"

**Verdict: confirmed — should be flagged.** This is a 3rd-party
service (@GlbGPT) promoting GLM 5.1 availability on their platform
with an explicit "Try it 👉" CTA. Same shape as tweet #9 (the
AINFT/TRON promo that the classifier correctly caught with
`marketing_spam`) and tweet #2 (the "Ask Gemini FREE now" list).
The brand edge + signal + discourse classification are all correct
(`advertising_marketing` + `advertising-marketing` discourse
role), but the unsanctioned flag is missing. False negative in
the LLM's output. Plan 2026-07-13-002 U1 target (same root cause
as #2 and #9).

---

## #5 — Tweet #5 (tweet_id `2076516742621503588`, INSERTED IN DB)

- **Author:** @preferredev_ (also appears at #13 and #20 — same
  tweet, different raw fetch)
- **Post id:** 7533
- **Text:** "@RoundtableSpace probably built on another open source
  model like GLM, Deepseek, or Kimi"
- **DB state:** 2 brand edges (deepseek, glm), no kimi (kimi
  was added by the co-occurrence C1 path? — actually no, the
  brand edge list has only deepseek + glm, kimi is in the text
  but the brand edge was not written). Signals
  `deepseek/feedback_questions/neutral`,
  `glm/feedback_questions/neutral`. Discourse: empty (KTD5
  dead-letter, no rows).
- **Reviewer note:** "model = kimi, but this is already addressed
  in our next plan"

**Verdict: acknowledged, no action this review.** The reviewer is
noting that `kimi` is the polysemous brand that gets conflated with
the footballer or F1 driver (and with `moonshot_kimi` as a model name).
Plan 2026-07-13-002 U4 drops `moonshot_kimi` from B1/B2 (and C1
covers it via co-occurrence). The current tweet's text mentions
"kimi" by name as a model, but the brand edge list has only
deepseek + glm — kimi was *not* attributed, which is the bug
class that the next plan addresses. (Note: this is *opposite* of
the false-positive direction — the LLM is failing to attribute
kimi when it should, possibly because the C1 co-occurrence path
didn't fire on this minimal tweet.)

---

## #6 — Tweet #6 (tweet_id `2076516018575569297`, DUPLICATE)

- **Author:** @huangtang12 · `lang: zh`
- **Prior-run post id:** 7507, `fetched_at 2026-07-13T03:56:37`
- **Text:** "今天发现国家超算平台有个羊毛可以薅：TokenPlan 首月
  9.9 元。支持GLM-5.2、GLM-5、GLM-5.1、MiniMax-M3、MiniMax-M2.7、
  MiniMax-M2.5、DeepSeek-V4-Flash、DeepSeek-V3.2、Kimi-K2.7-Code、
  Kimi-K2.6、Kimi-K2.5、MiMo-V2.5-Pro 抢购页面：[link]。如果你还
  没有听说过或者注册过这个平台,先用我的邀请链接注册一下，可以
  领1000万Token量包+200卡时算力 [link]。麻烦的一点是需要大陆手
  机号以及实名认证。不过实名后会送400元额度。"
- **DB state:** 4 brand edges (deepseek, glm, minimax, mimo) at
  0.25 each (uniform 1/4 split); signals all
  `advertising_marketing/neutral`; discourse all
  `advertising-marketing (id 10) / both nationalism none`;
  unsanctioned `[]`.
- **Reviewer assertion:** "text_en = should be populated"

**Verdict: confirmed — `text_en` should be populated.** This is a
**Chinese-source post** (lang: zh), so the correct population is:
- `text_zh_cn` = the source text (should remain empty--agent to confirm)
- `text_en` = the English translation (currently empty — bug)

Currently both are empty. The classifier pipeline is not writing
the translation back. Plan 2026-07-13-002 U1 candidate (same root
cause as #2 / the global pipeline bug).

**Cross-tweet note:** this tweet also appears at #14 and #21
(same `tweet_id`, three different raw fetches — the tweet was
returned by 3 different call files: doubao, mimo, minimax).
All three should show the same DB state, and they do. The
classification is consistent.

**Side note (not in scope of #6 review):** the tweet IS a referral-
link promo ("领1000万Token量包+200卡时算力" = "get 10M tokens +
200 GPU-hours") and the reviewer didn't flag it. The classifier
correctly classified it as `advertising_marketing` with
`advertising-marketing` discourse role. The unsanctioned flag is
missing — should probably be `marketing_spam` for the referral-link
component — but that's the same U1 fix as #2 / #4 / #9.

---

## #7 — Tweet #7 (tweet_id `2076511514396131408`, DUPLICATE)

- **Author:** @schwepervezence · `lang: en`
- **Prior-run post id:** 7508
- **Text:** "Basically that meme about model cycles is real again.
  OOS is the worst shit ever (again). Can't believe I bought into
  the hype behind GLM :/. It's great btw, if you run it yourself.
  I imagine."
- **DB state:** 1 brand edge (`glm`, weight 1.0); signal
  `glm / hands_on_usage / negative`; discourse
  `glm / dunk_yingyang (id 3) / both nationalism none`.
- **Reviewer assertions:** none directly (skipped in the list).

**Reviewer's own read:** current classification looks correct. The
post literally says "the hype behind GLM" was disappointing and
"if you run it yourself" — that's a `dunk_yingyang` (hostile
dismissal) discourse role, `negative` sentiment, `hands_on_usage`
post_type. The current classification is correct as-is. No
correction from this review.

---

## #8 — Tweet #8 (tweet_id `2076515460296937968`, DUPLICATE)

- **Author:** @so_sthbryan · `lang: en`
- **Prior-run post id:** 7470
- **Text:** "China is moving to wall off its top open source AI
  models from foreign users. DeepSeek, Qwen, GLM face new outbound
  restrictions soon. The open source AI stack is about to get a
  Chinese firewall. The countries holding the weights now hold
  the leverage."
- **DB state:** 3 brand edges (deepseek, glm, qwen) at 0.333 each;
  signals all `event_announcement/negative`; discourse: empty
  (KTD5 dead-letter); unsanctioned `[]`.
- **Reviewer assertions:** "explain failure of discourse rows.
  should have us and cn nationalism both neutral"

**Verdict on discourse failure:** the LLM emitted a `discourse_key`
value that does not match any row in the `discourse_keys` lookup
table, so the FK insert into `posts_brands_discourse` failed and
the row was captured by the KTD5 dead-letter path. The dead-letter
JSONL is at `data/runs/2026-07-13/enum_dead_letter.jsonl`. The
report's "no discourse rows — `discours_key` likely fell through
to the KTD5 `uncategorized-sentinel` and was dead-lettered"
footnote refers to this exact failure. Plan 2026-07-13-002 U2 owns
the disposition path (right now the dead-letter file just
accumulates and is never read).

**Verdict on nationalism:** the LLM did not get a chance to emit
`china_nationalism` / `us_nationalism` for this post because the
discourse step itself failed before reaching the nationalism
sub-prompt. So there's nothing to correct here — the FKs are NULL
because the row never got that far. For posts that DO have
discourse rows, the FK targets are `nationalism_keys` with values
`none` (1), `mild_pro` (2), `pro` (3), `constructive_critical` (4),
`anti` (5), `mixed` (6). For this post (a neutral policy
journalism report), the correct values when the discourse step
does succeed would be `china_nationalism=none` (the post
describes outbound restrictions neutrally) and `us_nationalism=none`
(the post does not take a US-side stance). The fix is on the
discourse-key side (the LLM is emitting a value the lookup table
doesn't have), not on the nationalism side.

**Signals — additional reviewer observation:** the current
`negative` sentiment on all 3 brand edges may also be wrong
(consistent with #3 / #10). The post is reporting a policy event
("China is moving to wall off its top open source AI models from
foreign users") — it's a neutral report of a restrictive event.
`negative` is debatable; `neutral` (event announcement without
valence judgment) is more accurate. Plan 2026-07-13-002 U1
candidate.

---

## #9 — Tweet #9 (tweet_id `2076515287466131557`, DUPLICATE)

- **Author:** @Azardweb4 · `lang: en`
- **Prior-run post id:** 7471
- **Text:** A 3rd-party service (AINFT) promoting their Web3
  integration: "Expanded AI model support with GPT-5.5-Instant,
  DeepSeek-V3.2, MiniMax-M2.7, and GLM-5.1 across Web Chat and
  API" and "@AINFTcom @justinsuntron #TRONEcoStar".
- **DB state:** 3 brand edges (deepseek, glm, minimax) at 0.333
  each; signals all `buzz_releases/neutral`; discourse all
  `advertising-marketing (id 10) / both nationalism none`;
  unsanctioned `["marketing_spam"]` (already set).
- **Reviewer assertion:** "unsanctioned flag = positive; this post
  is promoting a 3rd party service/product"

**Verdict: confirmed — DB already has `marketing_spam` correctly
set.** The classifier correctly caught this as `marketing_spam`
(3rd-party product announcement name-dropping 3 of our watched
brands). No change needed; this is a good detection that should
be the template for #2 / #4 / #6's missing flags. The reviewer
might want stricter treatment in a future plan (e.g. propagate
the flag to every brand edge, not just the post-level row), but
that's a U2 candidate for plan 2026-07-13-002, not a fix for
this review.

---

## #10 — Tweet #10 (tweet_id `2076512230431220198`, DUPLICATE)

- **Author:** @Suparious · `lang: en`
- **Prior-run post id:** 7426
- **Text:** "MiniMax-M3 has been the most creative model I've used,
  compared to Claude, GPT, GLM and DeepSeek. Whenever I'm asking
  design questions, MiniMax gives me the best solutions."
- **DB state:** 3 brand edges (deepseek, glm, minimax) at 0.333
  each; signals
  `deepseek / performance_comparisons / negative`,
  `glm / performance_comparisons / negative`,
  `minimax / hands_on_usage / positive`; 1 discourse row
  `minimax / genuine_hype (id 1) / both nationalism none`.
- **Reviewer assertion:** "glm, deepseek = sentiment is neutral
  (article says minimax is better, but doesn't directly disparage
  the other 2)"

**Verdict: confirmed — current `negative` is wrong on deepseek
and glm.** The tweet explicitly compares models but does not
call GLM or DeepSeek bad; it says MiniMax is *better*, not that
the others are *bad*. The correct sentiment for the GLM and
DeepSeek edges is `neutral` (they are mentioned as comparison
points, not evaluated negatively). The `minimax` edge correctly
reads `positive` and the discourse role `genuine_hype` is also
correct. The `negative` on `deepseek` / `glm` is an over-reach
by the LLM. This is a sentiment prompt issue (plan
2026-07-13-002 U1 candidate — add a "comparative mention ≠
negative" rule to the sentiment prompt, same root cause as #3).

**Additional structural note:** the post_type differs across
brand edges in the same post — `performance_comparisons` for
deepseek/glm (correct — they are the comparison subjects) and
`hands_on_usage` for minimax (the focus brand). This is
internally consistent and not a bug.

---

## #11 — Tweet #11 (tweet_id `2076511705534734637`, DUPLICATE)

- **Author:** @TheEastFrontier · `lang: en`
- **Prior-run post id:** 7501
- **Text:** "Chinese tech giants Stepfun, ByteDance, and WeChat
  drive the AI agent phone revolution, challenging traditional
  smartphone paradigms despite memory and pricing hurdles."
- **DB state:** 1 brand edge (`stepfun`, weight 1.0); signal
  `stepfun / buzz_releases / neutral`; discourse: empty
  (KTD5 dead-letter); unsanctioned `[]`.
- **Reviewer note:** "slightly edge case: bytedance and wechat are
  being referenced, but not their LLM but their chatbot brands
  (but not by name). we will need to build this for next version."

**Verdict: acknowledged.** Current attribution correctly avoids
`doubao` (ByteDance's LLM) and `hunyuan` (Tencent/WeChat) because
the post doesn't name those products — only the parent companies.
A future version needs an **alias / parent-company → LLM brand**
mapping (e.g. `ByteDance` → `doubao`, `Tencent` / `WeChat` →
`hunyuan`, `Alibaba` → `qwen`, `Baidu` → `ernie`, etc.) so that a
parent-company mention can attribute the LLM brand with a
lower-confidence weight. This is non-trivial schema work and
should be a separate plan post-2026-07-13-002. The classifier is
correctly conservative: only `stepfun` (named explicitly) gets
attributed. No change for this review.

**Side note (not in review):** the discourse is also dead-lettered
for this post — same KTD5 path as #8. Same U2 plan candidate.

---

## #12 — Tweet #12 (tweet_id `2076507830635712626`, DUPLICATE)

- **Author:** @OMGTheMess · `lang: en`
- **Prior-run post id:** 7457
- **Text:** A "clean, copyable list of major Chinese AI models
  (LLMs and notable systems)" enumerating 15 brands with model
  variants (Qwen, DeepSeek, ERNIE, GLM, Yi, Doubao, Kimi, Hunyuan,
  Aquila, InternLM, TeleChat, Spark, Baichuan, SenseChat, Yang).
- **DB state:** 8 brand edges (deepseek, ernie, glm, hunyuan,
  qwen, doubao, yi, sensechat) at 0.125 each; signals all
  `buzz_releases/neutral`; discourse: empty (KTD5 dead-letter).
- **Reviewer assertion:** "confirm `discours_key` is a misspelling
  in this doc and not in codebase"

**Verdict: confirmed typo, report-only.** The doc uses
`discours_key` (missing the `e`) in 10 places (lines 236, 330,
423, 474, 498, 581, 629, 662, 720, 880), all in the "no discourse
rows" footnote.

The codebase uses the correct spelling `discourse_key` everywhere
(verified in `x_monitor/store.py:1698, 1712, 1722, 1737, 1749,
1755, 1760, 1765` and elsewhere). The DB column is `discourse_key`
(correct, with `e`). The report-only typo originated in the build
script's emit code in
`scripts/build_u3_evidence_live_run.py`.

**Fix:** replace the typo in the report and in the script's emit
function. Trivial single-character fix; fold into the next
evidence-report regeneration or amend the recent commit
`6d871e5`.

---

## #13 — Tweet #13 (tweet_id `2076516742621503588`, INSERTED IN DB)

- **Author:** @preferredev_ (same as #5)
- **Post id:** 7533 (same as #5)
- **Text:** "@RoundtableSpace probably built on another open source
  model like GLM, Deepseek, or Kimi"
- **DB state:** same as #5.

**Reviewer comment:** empty (no question or assertion).

This entry is the second raw fetch of the same tweet_id as #5
(appearing again in the `mimo_brand_wide_acct.json` call file).
Classification is consistent across all three occurrences (#5,
#13, #20). No review action.

---

## Cross-cutting findings

1. **Global pipeline bugs (affect every tweet):**
   - `lang_detected` is NULL on all 36 report entries, even when
     `lang: en` or `lang: zh` is set on the tweet by the Twitter API.
   - `text_en` and `text_zh_cn` are both empty on all 36 entries
     (verified: text_en=NO for every row, text_zh_cn=NO for every
     row, lang_detected=NULL for every row).
   - These two bugs together mean the classifier is not writing
     back the language detection + translation pair. Plan
     2026-07-13-002 U1 (prompt + closed-DB bug fold) target.

2. **Unsanctioned flag false negatives:** tweets #2, #4, and #6
   all have legitimate `marketing_spam` cases the LLM is missing.
   #9 has the same shape but was correctly caught — the difference
   is what the U1 prompt fix needs to address. Three confirmed
   false negatives in this report; same root cause.

3. **Sentiment over-reach (comparative mention ≠ negative):**
   tweets #3, #8, and #10 all have `negative` sentiment on a brand
   that is mentioned only as a comparison point, not disparaged.
   The LLM is over-flagging "worse than" as negative. Same
   prompt-level fix candidate.

4. **Discourse KTD5 dead-letter:** tweets #5, #8, #11, #12 all
   have empty `posts_brands_discourse` tables because the LLM
   emitted a `discourse_key` value not in the lookup table. The
   dead-letter JSONL is at
   `data/runs/2026-07-13/enum_dead_letter.jsonl`. Plan
   2026-07-13-002 U2 owns the disposition path (currently just
   accumulates, never read).

5. **Polysemous brand collisions (already in next plan):**
   - `kimi` (#5): missed-attribution, not in C1's coverage
   - `yi` (#15, not in this review's list — see doc entry #15
     where "Yoon Cho-Yi" actress gets `yi` LLM brand): false
     positive on Korean drama
   - `bytedance` / `wechat` (#11): parent-company → LLM brand
     mapping needed (future plan)

---

## Summary of action items for plan 2026-07-13-002

- **U1 (prompt + closed-DB bug fold):**
  - Fix the global `lang_detected` / `text_en` / `text_zh_cn`
    pipeline gap (affects all 36 entries in this report).
  - Add `unsanctioned_flags` trigger definitions for
    `marketing_spam` so the LLM catches the 3 missed CTAs in
    this report (#2, #4, #6).
  - Add a "comparative mention ≠ negative" rule to the sentiment
    prompt (#3, #8, #10).
- **U2 (discourse dead-letter disposition):** the KTD5 path
  currently just appends to `enum_dead_letter.jsonl`. Add a
  periodic job that either (a) extends `discourse_keys` from
  the dead-letter file with a label and replays, or (b) flags
  the dead-letter as "unrecognized LLM output" for human review.
- **U3 (post-U1 measurement):** re-run the smoketest, verify
  the three fixes above move the needle on the disputed tweets
  in this review.
- **U4 (drop 6 B/C dupe brands from `call_b_groups`):** already
  in plan; #3 / #5 / #15 confirm the polysemous collisions.
- **U5 (open slot) — candidates surfaced by this review:**
  - **#1 table-name legacy:** archive the `posts_brands.weight`
    column or replace with a `presence` boolean (current `weight`
    is a `1/N` uniform split, legacy read path).
  - **#3 brand-yaml negative-keywords:** add a per-brand
    negative-keyword list to suppress drama / celebrity /
    common-name false positives (e.g. `yi` → block "Cho-Yi",
    "MyBiasMyBoss"; `kimi` → block given-name contexts).
  - **#11 parent-company → LLM alias mapping:** schema-level
    work to attribute `ByteDance` / `Tencent` / `Alibaba` etc.
    mentions to their respective LLM brands at lower confidence.
  - **#12 `discours_key` typo fix** in the report + emit script.
