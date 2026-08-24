# Classifier Prompts -- Literal Reference

Last updated: 2026-08-05-20:38:42



The `x_monitor.attribution.classify_pragmatics_full` (per-post) and
`x_monitor.attribution.classify_batch_pragmatics_full` (batched, ~20 posts per call)
pipelines send the LLM a shared system prompt and parse the structured
response against the taxonomy allow-lists. This doc holds **the literal
prompt text and the literal allow-list constants** so the operator can see
exactly what the LLM is told and what the parser will reject.

Companion doc: **`docs/reference/lookup-tables.md`** (the SQL-side
authoritative taxonomy). Anything that disagrees with that doc is a bug.

**Source of truth:** `x_monitor/attribution.py`.

> **Last reviewed:** 2026-08-05 against `attribution.py` at HEAD `27a8cb3`.
> The classifier prompt and taxonomy are the live v2 contract. The
> prompt body at `_PRAGMATICS_FULL_SYSTEM_PROMPT` is the literal source
> text quoted in Section 3a; do not edit the Python constant to make the
> documentation fit it.
>
> **v2 invocation change:** The classification functions still live in
> `x_monitor/attribution.py` (unchanged). The caller changed:
>   - **v1 (dead):** `x_monitor/run.py` called classification inline
>     during the Fetch+Classify loop, persisted via raw SQL.
>   - **v2 (current):** `monitor/cycle.py::CycleRunner` calls the same
>     `x_monitor/attribution.py` functions from the Django management
>     command (`monitor/management/commands/run_cycle.py`) and Celery
>     task (`monitor/tasks.py`). Persists via Django ORM.
>
> **Caveat for operators:** the `lang_detected` cross-reference rule
> (rule 3 in the Cross-reference block) is a cross-prompt artifact of
> the shared `_PRAGMATICS_FULL_SYSTEM_PROMPT` prefix -- the classifier
> does not emit `lang_detected`; the translator does. See Section 3
> (Cross-reference rules note 3) below.

---

## 1. Pipeline shape (one prompt per call, shared by per-post and batch paths)

There are **two prompt builders** in the classifier pipeline, only one of
which is current:

| Builder | Status | Purpose |
|---|---|---|
| `build_signal_prompt`        | **legacy / superseded** by U9 | per-brand `(post_type, sentiment)` -- 4+4 buckets |
| `build_pragmatics_full_prompt` | **current** (U3a + U9 + Section 5.1 merged) | per-post, one brand row per matched brand, FIVE fields per row, plus top-level `unsanctioned_flags`. Shares the same `_PRAGMATICS_FULL_SYSTEM_PROMPT` prefix as `build_batch_pragmatics_full_prompt` so Anthropic's prompt-cache stays warm across call kinds. |

`build_signal_prompt` is preserved for callers that haven't migrated; the
parser `_parse_signal_response` is still wired through `classify_post` for
fallback paths.

The prompts themselves enumerate the taxonomy; the parsers use the
`_VALID_*` allow-lists below to coerce unknown values to a fallback.

**Entry points** (callers in the v2 Django stack):

| Function | File:Line | Invoked by |
|---|---|---|
| `classify_pragmatics_full` (per-post) | `attribution.py:1670` | per-post fallback path within `classify_batch_pragmatics_full` (fail-soft contract); builds prompt via `build_pragmatics_full_prompt`, returns `{by_brand, unsanctioned_flags}` |
| `classify_batch_pragmatics_full` (batched) | `attribution.py:1911` | `monitor/cycle.py::CycleRunner._run_post_fetch`; builds prompt via `build_batch_pragmatics_full_prompt`, 20 posts/batch, returns a list index-aligned with input tweets |

**v2 invocation chain:**

```
Django management command          Celery beat
  monitor/management/commands/       monitor/tasks.py::run_cycle
    run_cycle.py::Command.handle       (scheduled)
         |                                |
         +--- monitor/cycle.py::CycleRunner.run()
                  |
                  +--- _run_post_fetch()
                  |     x_monitor.attribution.classify_batch_pragmatics_full()
                  |     x_monitor.translator.translate_batch_pragmatics()
                  |
                  +--- _attribute_items()
                        x_monitor.attribution.attribute_to_brands()
```

`_run_post_fetch` invokes both `classify_batch_pragmatics_full` and
`translate_batch_pragmatics` after posts enter the durable enrichment queue.

**Model resolution** (`monitor/cycle.py`, `classify_batch_pragmatics_full`):

The production cycle passes `cfg.llm.classifier_model` explicitly to the
classifier, and the committed value is **DeepSeek V4 Flash**
(`deepseek-v4-flash`). **MiniMax-M3.0** is the legacy classifier route. Calls
without explicit config retain the compatibility resolution ladder:

| Priority | Source | Resolved model |
|---|---|---|
| 1 | Production `cfg.llm.classifier_model` | explicit configured model (`deepseek-v4-flash` committed) |
| 2 | `X_MONITOR_CLASSIFIER_MODEL` or `ANTHROPIC_MODEL` | compatibility environment override |
| 3 | classifier base URL contains `minimax.io` | `MiniMax-M3.0` (legacy) |
| 4 | classifier base URL contains `deepseek.com` | `deepseek-v4-flash` |
| 5 | otherwise | `claude-haiku-4-5` (direct Anthropic fallback) |

The DeepSeek path also passes `thinking={"type": "disabled"}` and threads `_max_tokens_for_batch` -- `min(8192, max(4096, 200 * batch_size))` -- so batch_size=20 gets 4096 tokens and batch_size=40 gets 8192.

---

## 2. `build_signal_prompt` (legacy, U9)

**File:** `x_monitor/attribution.py:875-924`.

```python
return (
    "You classify a tweet's relationship to a list of brands.\n\n"
    "Tweet text:\n"
    f"\"\"\"\n{text}\n\"\"\"\n\n"
    f"Brands (in order): {brand_list}\n\n"
    "For each brand, return a (post_type, sentiment) tuple from these "
    "exact sets:\n\n"
    "post_type:\n"
    "  - buzz_releases           (brand announced something new)\n"
    "  - hands_on_usage          (user is using / showing the brand)\n"
    "  - performance_comparisons (benchmark / eval / head-to-head)\n"
    "  - feedback_questions      (user asking how-to / help / complaint)\n\n"
    "sentiment:\n"
    "  - positive                (praise, enthusiasm)\n"
    "  - negative                (criticism, disappointment)\n"
    "  - neutral                 (informational / question)\n"
    "  - mixed                   (multiple valences in one post)\n\n"
    "Rules:\n"
    "1. Return ONLY a JSON object: {\"classifications\": "
    "[{\"brand_id\": str, \"post_type\": str, \"sentiment\": str}, ...]}\n"
    "2. One entry per brand you classify (you may OMIT brands "
    "that don't apply).\n"
    "3. Use the EXACT brand_id strings from the list above.\n"
    "4. If the tweet is off-topic for all brands, return "
    "{\"classifications\": []}.\n"
    "5. No prose, no explanation, no code fences.\n"
)
```

**Taxonomy values listed in this prompt:**
- `post_type` (4): `buzz_releases`, `hands_on_usage`, `performance_comparisons`, `feedback_questions`
- `sentiment` (4): `positive`, `negative`, `neutral`, `mixed`

**Parser fallback** (`_parse_signal_response`, `attribution.py:927-978`):
- Unknown `post_type` -> `hands_on_usage`
- Unknown `sentiment` -> `neutral`
- Hallucinated `brand_id` (not in registry set) -> dropped silently; `brand_id`
  in the response but not in the asked set -> kept with a `logger.debug`
  line (lines 971-975).

---

## 3. `build_pragmatics_full_prompt` (current, U3a + U9 + Section 5.1 merged)

**File:** `x_monitor/attribution.py:1122-1148`. The actual
prompt body lives in the module-level constant
`_PRAGMATICS_FULL_SYSTEM_PROMPT` (`attribution.py:1202-1459`). The
function just concatenates the constant with a per-tweet header and a
"return ONE entry in `results` whose `tweet_id` is `_single_`" suffix.

### 3a. Raw prompt text (literal, as emitted to the LLM)

> **Literal-source note (verified 2026-08-05 against `attribution.py` at HEAD `27a8cb3`):**
> The fenced block below quotes `_PRAGMATICS_FULL_SYSTEM_PROMPT`, the exact
> system-prompt body sent by the classifier. The per-post builder appends the
> tweet text, ordered brand list, and `_single_` result instruction described
> below. The historical transcription differences listed after this note are
> retained as drift history only; they are not part of the current quote.
>
> Historical drift noticed in the prior review:
>
> 1. **Em dashes (`—`, U+2014) → double hyphens (`--`)** throughout the
>    block. Every instance of `--` in this section is a degraded form of
>    the actual em-dash in the source string (the constant uses
>    `—` everywhere: post_types header, sentiment header, the
>    "Comparative mention is NOT negative sentiment" rule, the
>    "What KIND of post" parenthetical, the us_nationalism header, the
>    "same as china_nationalism but applied to the US axis — anti =
>    反美, etc." line, all rule 7-19 body text, and the section 3a
>    "Cross-reference rules (these are HARD — emit consistently)" header).
> 2. **Chinese annotations dropped** from the `discourse_roles` legend:
>    - `dunk_yingyang` — constant has `阴阳怪气 / passive-aggressive dunk`; doc has `yygq / passive-aggressive dunk`.
>    - `self_deprecation` — constant has `自嘲 / self-mockery`; doc has `self-mockery` only.
>    - `cope` — constant has `嘴硬 / stubborn denial`; doc has `stubborn denial` only.
>    - `fud` — constant has `唱衰 / spreading doom`; doc has `spreading doom` only.
>    - `distillation_accusation` — constant has `套壳 / 蒸馏指控`; doc has `distillation accusation` only.
>    - `absurdist_meme` — constant has `抽象整活 / absurdist antics`; doc has `absurdist antics` only.
> 3. **Chinese annotations dropped** from the `china_nationalism` legend:
>    - `mild_pro` — constant has `温和亲华 — subtle positive`; doc has `subtle positive` only.
>    - `pro` — constant has `亲华 — open positive`; doc has `open positive` only.
>    - `constructive_critical` — constant has `建设性批评 — pro-CN criticism`; doc has `pro-CN criticism` only.
>    - `anti` — constant has `反华 — hostile`; doc has `hostile` only.
>    - `us_nationalism` line — constant has `anti = 反美, etc.`; doc dropped the `反美` annotation.
> 4. **Rule 8 (genuine_hype vs CTA) missing Chinese tokens.**
>    Constant lists `'try', 'sign up', 'join', 'get', 'limited-time', 'free access',
>    限时免费, 立即体验, 注册, 点击`. Doc has `'try', 'sign up', 'join', 'get',
>    'limited-time', 'free access', limited-time-free, immediate-experience, register,
>    click'` — the last 5 tokens are garbled ASCII transliterations of the actual
>    Chinese tokens. The doc's spelling is wrong.
> 5. **Rule 17 (trap-language) transcription error.** Constant has
>    `"翻车"`. Doc has `"翻车"` — a romaji-ish garble that does not
>    match either the Chinese character or any accepted romanization.
> 6. **Rule 6 (orthogonality) uses `×` (multiply sign, U+00D7) in the constant**;
>    doc has `x` (lowercase letter). Semantically the same, but the
>    literal-shape fidelity claim is broken.
> 7. **Stale section references.** The constant contains the markers
>    `§2` (pragmatic register cross-reference) and `§4.4` (nationalism
>    scale cross-reference). The current doc has no Section 4.4 — the
>    reference is dead. Also the doc says `Section 2` in the
>    `discourse_roles` legend, but the corresponding section in this
>    version of the doc is Section 4 (allow-lists), not Section 2.
> 8. **`uncategorized` count in the `discourse_roles` legend is
>    ambiguous.** The constant lists 11 bullets (`genuine_hype`, `sarcasm`,
>    `dunk_yingyang`, `self_deprecation`, `cope`, `fud`,
>    `distillation_accusation`, `ai_slop_critique`, `absurdist_meme`,
>    `advertising-marketing`, `uncategorized`). The doc's prose says
>    "10 keys" then lists 11. The "10 keys" claim is correct as the
>    prompt heading (the heading counts keys excluding the
>    `uncategorized` sentinel), but the heading
>    `discourse_roles (10 keys -- pragmatic register, Section 2; ARRAY, max 3):`
>    is ambiguous because the bullet list immediately below contains 11 entries.
> 9. **Cross-prompt artifact (pre-existing flag, not new):** the
>    `lang_detected` cross-reference rule in the prompt is a
>    translator-only emission. The classifier does NOT emit
>    `lang_detected`. The doc already calls this out in the Section
>    introduction (and the existing note in Section 3b cross-reference
>    rule 3) — this is preserved.
>
> Nominal source range: `attribution.py:1202-1459`. The actual emitted
> string is at `attribution.py:1182-1440` (one line beyond the cited
> range — the constant itself ends with `)\n` on line 1440, just before
> `def build_batch_pragmatics_full_prompt` at line 1442). The
> `1182-1439` citation is off by one. See the Last reviewed footer.

Use this section when you need the exact system-prompt body the LLM receives. The per-post user-message suffix is constructed by `build_pragmatics_full_prompt` and is described above the quote.

```
You classify one or more tweets about their relationship to a
list of brands, across FIVE dimensions per brand: post_types
(array), sentiment (scalar), discourse_roles (array),
china_nationalism (scalar), us_nationalism (scalar). You also
emit a top-level `unsanctioned_flags: [str]` per tweet for
marketing_spam / scam / crypto / unauthorized signals.

For each brand in each tweet, return FIVE fields from these
exact sets:

post_types (6 buckets -- what KIND of post; ARRAY, max 3):
  - buzz_releases            (brand announced something new)
  - hands_on_usage           (user is using / showing the brand)
  - performance_comparisons  (benchmark / eval / head-to-head)
  - feedback_questions       (user asking how-to / help / complaint)
  - advertising_marketing    (CTA, promo, wrapper, free-credit pitch)
  - event_announcement       (official event / community meetup)

sentiment (4 values -- the VALENCE; scalar):
  - positive                 (praise, enthusiasm)
  - negative                 (criticism, disappointment)
  - neutral                  (informational / question; also when
the brand is mentioned only as a COMPARISON POINT and not directly
evaluated -- 'X is better than Y' is positive for X, neutral for Y)
  - mixed                    (multiple valences in one post)

discourse_roles (10 keys -- pragmatic register, Section 2; ARRAY, max 3):
  - genuine_hype             (straight praise)
  - sarcasm                  (English verbal irony)
  - dunk_yingyang            (阴阳怪气 / passive-aggressive dunk)
  - self_deprecation         (自嘲 / self-mockery)
  - cope                     (嘴硬 / stubborn denial)
  - fud                      (唱衰 / spreading doom)
  - distillation_accusation  (套壳 / 蒸馏指控)
  - ai_slop_critique         (AI content-garbage accusation)
  - absurdist_meme           (抽象整活 / absurdist antics)
  - advertising-marketing    (salesy, CTA-heavy marketing speak --
NOTE: hyphenated, not underscored)
  - uncategorized            (catch-all when none of the above fit)

unsanctioned_flags (per tweet; ARRAY, top-level -- omit when no
signal applies):
  - marketing_spam           (promotional CTA on a brand -- usually
paired with post_type=advertising_marketing AND
discourse_role=advertising-marketing; includes referral-link
pitches, 'try it now', 'FREE access' wrappers, third-party
aggregator lists with explicit CTAs)
  - scam                     (impersonation of an official brand
account + asks for payment, credentials, or wallet seed)
  - crypto                   (token ticker / airdrop / wallet claim
tied to a brand -- 'claim your $X airdrop', 'swap Y for brand
token', 'join the liquidity pool')
  - unauthorized             (brand appears in a third-party post
without authorization -- giveaway, 'official AI' impersonation,
fake partner announcement)

Cross-reference rules (these are HARD -- emit consistently):
  - If post_type=advertising_marketing OR
discourse_role=advertising-marketing, the post MUST also carry
unsanctioned_flags: ["marketing_spam"]. The marketing signal is
one signal; it shows up in three places.
  - Comparative mention is NOT negative sentiment. When a post
ranks models ('X is better than Y') and does NOT explicitly call
Y bad, emit sentiment=neutral for Y. Only emit
sentiment=negative when the post contains direct evaluative
criticism of the brand (not when it merely ranks another brand
above it).
  - lang_detected is REQUIRED on every tweet. Source-language
English posts emit lang_detected='en' with text_en=source text
and text_zh_cn=Chinese translation. Source-language Chinese
posts emit lang_detected='zh' with text_zh_cn=source text and
text_en=English translation. Other languages: emit lang_detected
with the source language and populate both translation fields.

china_nationalism (6-step scale, Section 4.4; scalar):
  - none                     (no China-nationalism layer)
  - mild_pro                 (温和亲华 — subtle positive)
  - pro                      (亲华 — open positive)
  - constructive_critical   (建设性批评 — pro-CN criticism)
  - anti                     (反华 — hostile)
  - mixed                    (mixed modes in one post)

us_nationalism (6-step scale, same as china_nationalism but
applied to the US axis — anti = 反美, etc.; scalar):
  - none / mild_pro / pro / constructive_critical / anti / mixed

Rules:
1. Return ONLY a JSON object matching this shape:
   {
     "results": [
       {
         "tweet_id": str,
         "classifications": [
           {
             "brand_id": str,
             "post_types": [str],         // ARRAY, max 3
             "sentiment": str,             // scalar
             "discourse_roles": [str],     // ARRAY, max 3
             "china_nationalism": str,     // scalar
             "us_nationalism": str         // scalar
           }, ...
         ],
         "unsanctioned_flags": [str]      // ARRAY, top-level
       }, ...
     ]
   }
2. ONE result per input tweet, IN THE SAME ORDER as the input.
3. Per tweet, RETURN ONE OBJECT PER BRAND LISTED. The brand list
is what the keyword detector found in the text -- if a
brand name appears, you MUST produce an object. Cross-brand
comparison posts ("GLM 5.2 vs Kimi K2.7"), reply chains
where the brand is mentioned, posts sharing screenshots
with the brand name -- ALL count. Only skip a brand if
the post text contains ZERO mention of it (this should be
impossible given how the brand list was derived).
4. Use the EXACT brand_id strings from each tweet's brand list.
5. Most posts have exactly 1 post_type and 1 discourse_role.
Multi-value is allowed when a post legitimately has more than
one (e.g., a benchmark write-up that is also a
`performance_comparisons` AND `feedback_questions` because it
asks 'am I running behind?'). MAXIMUM 3 of each per brand.
6. nationalism is ORTHOGONAL to post_types x sentiment x
discourse_roles -- a single post can be e.g.
([perf_compare, feedback], positive, [genuine_hype], none,
constructive_critical).
7. If a tweet is off-topic for all brands (shouldn't
happen if the brand list is non-empty), return
{"tweet_id": "<id>", "classifications": [],
"unsanctioned_flags": []}.
8. genuine_hype is incompatible with explicit call-to-action.
If the post contains a CTA (URL + verb like 'try', 'sign up',
'join', 'get', 'limited-time', 'free access', 限时免费, 立即体验, 注册, 点击), discount offer, or wrapper/promo language
('one API key', 'OpenAI-compatible gateway', 'free credit no card'),
prefer discourse_role `advertising-marketing` over `genuine_hype`.
If both genuine praise AND a CTA coexist, emit BOTH
discourse_roles values -- let downstream consumers decide.
9. No prose, no explanation, no code fences.

10. sent=neutral for launch announcements with no evaluative
language. A post that says only 'X is generally available',
'Y launched today', 'Z shipped v3.2', or 'W is now in beta'
(without praise/criticism) is INFORMATIONAL. emit sent=neutral
regardless of whether the brand would benefit from the
announcement. Optimistic framing like 'now available for
everyone' is still neutral (vendor announcement voice, not
user praise).
11. sent=positive for long analytical / investment posts
with explicit positive framing. If the post says 'the model
is strategically positive for X's cloud multiple',
'increasingly important as a strategic asset', 'supports the
valuation narrative', or similar investment-grade positive
language, that IS positive sentiment -- do not water it down
to sent=mixed because there are also caveats in the post.
Caveats and positive framing coexist; positive framing wins.
12. sent=neutral for multi-brand state-of-market posts that
are factual updates per brand ('X climbed 20 spots to #138,
'Y price dropped 8.2%', 'Z was degraded for 45 min'). emit
sent=neutral for each brand UNLESS a specific positive/
negative evaluative claim is made about that brand in the
same post.
13. pt=event_announcement for one-line 'X is generally
available / Y launched / Z shipped' posts. NOT hands_on_usage
(the user isn't using the brand -- the brand is announcing).
NOT buzz_releases (that's a brand-side press release; this
rule covers third-party reshares of an announcement too).
14. pt=performance_comparisons for any post mentioning TTFT
(time-to-first-token), latency, benchmark, ranking, '#N
ranking', 'N spots climbed/dropped', 'side-by-side race',
'vs <other model>'. The LLM Drag Race write-up ('races GPT-
4o-mini vs Llama 3.3 70B side-by-side, measure TTFT') is the
canonical example.
15. pt=performance_comparisons OR pt=feedback_questions for
pure analytical commentary (price/perf framing, model
governance framing, 'should I switch?' framing). NOT
hands_on_usage -- the author is analyzing, not using.
16. Nationalism requires explicit US-China relational framing.
Do not infer `china_nationalism` or `us_nationalism` from
generic anti-vendor dunk on a Chinese (or US) brand's product
failure, benchmark miss, or release reception. A post dunking
on Qwen for a benchmark miss is `sentiment=anti-Qwen` and
`nationalism=neutral`, NOT `us_nationalism=anti`. The
nationalism axes measure US-China framing, not anti-vendor
hostility.
17. Trap-language handling. When the post text contains
"trap", "gotcha", "embarrassing", "fumbled", or
"翻车" AND the subject is a Chinese-vendor product failure,
the post's `discourse_roles` should include `dunk_yingyang`
if the tone is passive-aggressive, or `fud` if the tone is
doom-spreading. The post's `us_nationalism` should remain
`none` per rule 16 -- trap-language is surface vocabulary,
not a US-China framing signal.
18. Superlative praise (`fastest`, `best`, `strongest`,
`first to ship`, `most powerful`) describes the brand being
praised, NOT a US-China framing. The post is
`discourse_roles=[genuine_hype]` for the brand being praised
-- NOT `us_nationalism=pro/anti` based on which country the
praised brand is from. 'Qwen is the fastest model' is hype,
not a nationalism statement about China.
19. Qwen-vendor-not-US distinction. Posts critiquing a
Chinese-vendor's product behavior (Qwen, GLM, DeepSeek, Kimi)
do not carry `us_nationalism` valence by default. Even when
the critique is harsh ("Qwen faded", "DeepSeek shipped a
broken model"), the axis measures US-China framing, not
anti-Chinese-vendor sentiment. emit `us_nationalism=none`
unless the post explicitly invokes US-China framing.

Worked examples (reference cases; match these patterns):
  A. 'Kimi K2.7 Code is generally available in GitHub Copilot'
     -> per brand: pt=[event_announcement], sent=neutral,
       discourse_roles=[uncategorized].
  B. 'K2.7 Code climbed 20 spots to #138; Deepseek V4 price
dropped 8.2%'
     -> per brand: pt=[hands_on_usage], sent=neutral for both,
       discourse_roles=[uncategorized]. (factual updates, no
       aggregate judgment.)
  C. 'Alibaba's Qwen franchise is increasingly important as a
strategic cloud and platform asset... strategically positive
for BABA's cloud multiple'
     -> qwen: pt=[performance_comparisons],
       sent=positive, discourse_roles=[genuine_hype].
       other brands mentioned in same post without explicit
       positive framing: sent=neutral.
  D. 'I built LLM Drag Race: races GPT-4o-mini vs Llama 3.3
70B, measure TTFT'
     -> brands present: pt=[performance_comparisons],
       sent=neutral (showcase, no evaluative claim).
  E. 'This changes how GitHub routes coding tasks -- model
picker vs single assistant' (price/perf analytical piece)
     -> pt=[performance_comparisons] OR
       [feedback_questions] (user implicitly asking 'where
does this leave me?'), NOT hands_on_usage.
  F. 'Kimi K2.7 Code makes Copilot a model marketplace'
(rhetorical questions + analytical commentary)
     -> pt=[feedback_questions] (asks 4 rhetorical
performance/pricing questions), NOT hands_on_usage.
  G. 'DeepSeek shipping a benchmark trap -- gotcha benchmarks
that nobody can reproduce' (anti-vendor dunk on Chinese-vendor
product failure)
     -> deepseek: pt=[performance_comparisons], sent=negative,
       discourse_roles=[dunk_yingyang], cn_nationalism=none,
       us_nationalism=none. (per rules 16, 17: dunk tone is
       surface vocabulary, NOT US-China framing.)
  H. 'Qwen is the fastest model I've benchmarked this month,
scored 89% on MMLU'
     -> qwen: pt=[performance_comparisons], sent=positive,
       discourse_roles=[genuine_hype], cn_nationalism=none,
       us_nationalism=none. (per rule 18: superlative praise
       is hype, not a US-China statement.)
  I. 'GLM 5.2 fumbled the launch -- benchmarks collapsed,
everyone noticed' (anti-vendor dunk on Chinese-vendor release)
     -> glm: pt=[buzz_releases], sent=negative,
       discourse_roles=[fud], cn_nationalism=none,
       us_nationalism=none. (per rules 16, 19: harsh critique
       of Chinese-vendor product is anti-vendor sentiment,
       not US-China framing.)
  J. 'Kimi K2.7 is fast but DeepSeek V4 is faster on coding
tasks; the AI race is heating up between US and Chinese
vendors'
     -> kimi + deepseek: pt=[performance_comparisons],
       sent=neutral, discourse_roles=[uncategorized],
       cn_nationalism=mild_pro, us_nationalism=anti. (this
       post DOES invoke US-China framing explicitly -- rule 16
       applies the other way: nationalism fires when the post
       actually names the AI race.)
```

### 3b. Formatted, readable version

Same content as 3a, restructured for human reading. Use this when
triaging classifier misclassifications or planning prompt rewrites.

#### Header
> You classify one or more tweets about their relationship to a list of
> brands, across FIVE dimensions per brand: post_types (array), sentiment
> (scalar), discourse_roles (array), china_nationalism (scalar),
> us_nationalism (scalar). You also emit a top-level
> `unsanctioned_flags: [str]` per tweet for marketing_spam / scam /
> crypto / unauthorized signals.

#### Field-by-field enumeration

| Field | Cardinality | Values |
|---|---|---|
| `post_types`         | ARRAY, max 3 | `buzz_releases`, `hands_on_usage`, `performance_comparisons`, `feedback_questions`, `advertising_marketing`, `event_announcement` |
| `sentiment`          | scalar       | `positive`, `negative`, `neutral`, `mixed` (neutral also when brand is a comparison point only -- "X is better than Y" -> positive for X, neutral for Y) |
| `discourse_roles`    | ARRAY, max 3 | `genuine_hype`, `sarcasm`, `dunk_yingyang`, `self_deprecation`, `cope`, `fud`, `distillation_accusation`, `ai_slop_critique`, `absurdist_meme`, `advertising-marketing` (hyphenated, not underscored), `uncategorized` (11 listed; 10 in `_VALID_DISCOURSE` -- `uncategorized` is a parser sentinel, see Section 4) |
| `china_nationalism`  | scalar       | `none`, `mild_pro`, `pro`, `constructive_critical`, `anti`, `mixed` |
| `us_nationalism`     | scalar       | same six values (anti = anti-US, etc.) |

`unsanctioned_flags` (top-level, ARRAY per tweet) -- `marketing_spam`,
`scam`, `crypto`, `unauthorized`. The prompt legend describes each
flag's trigger (see 3a for full text).

#### Output JSON shape (rule 1)
```json
{
  "results": [
    {
      "tweet_id": "<string>",
      "classifications": [
        {
          "brand_id": "<string>",
          "post_types":         ["<string>", ...],
          "sentiment":          "<string>",
          "discourse_roles":    ["<string>", ...],
          "china_nationalism":  "<string>",
          "us_nationalism":     "<string>"
        },
        ...
      ],
      "unsanctioned_flags": ["marketing_spam", "scam", "crypto", "unauthorized"]
    },
    ...
  ]
}
```

> **Shape note:** the per-post flat shape (`{"classifications": [...],
> "unsanctioned_flags": [...]}`) that appears in earlier revisions of
> this doc is a legacy artifact. The current prompt and the
> `_validate_deepseek_response_shape` validator
> (`attribution.py:1829-1908`) require the `{"results": [...]}` wrapper.
> `classify_pragmatics_full` carries a compat shim (lines 1737-1751)
> that descends into the first `results` entry if the parser saw no
> `classifications` at the top level -- but the prompt itself instructs
> the `results` shape, and the batch path's `classify_batch_pragmatics_full`
> consumes it directly.

#### Cross-reference rules (between `post_type` / `discourse_role` / `unsanctioned_flags` / sentiment)

1. **`advertising_marketing` <-> `marketing_spam`.** If `post_type=advertising_marketing` OR
   `discourse_role=advertising-marketing`, the post MUST also carry
   `unsanctioned_flags: ["marketing_spam"]`. The marketing signal is one
   signal; it shows up in three places.
2. **Comparative mention is NOT negative sentiment.** When a post ranks
   models ("X is better than Y") and does NOT explicitly call Y bad,
   emit `sentiment=neutral` for Y. Only emit `sentiment=negative` when
   the post contains direct evaluative criticism of the brand.
3. **`lang_detected` is REQUIRED on every tweet** -- but **caveat**:
   the classifier does NOT itself emit `lang_detected`. The rule lives
   in the classifier prompt because the translator and classifier share
   the same `_PRAGMATICS_FULL_SYSTEM_PROMPT` prefix (see plan
   2026-07-13-001). The translator (`x_monitor.translator`) emits
   `lang_detected`, `text_en`, `text_zh_cn`; the classifier consumes the
   translated text and emits only the five classification fields plus
   `unsanctioned_flags`. Operators reading this doc should treat the
   `lang_detected` line in the classifier prompt as a no-op for the
   classifier path; the line is enforced by the translator.

#### Structural rules (1-9)

1. **Output shape** -- the JSON above; nothing else.
2. **One result per input tweet, in the same order as the input.**
3. **One object per brand per tweet** -- the brand list came from the
   keyword detector; if the brand name appears in the text, you MUST
   produce an object. Cross-brand comparison, reply chains, screenshot
   shares -- all count. Only skip a brand if there is literally zero
   mention (which shouldn't happen given the detector).
4. **Use exact `brand_id` strings** from the list the prompt gave you.
5. **Most posts have 1 `post_type` and 1 `discourse_role`.**
   Multi-value is allowed when a post legitimately has more than one
   (e.g., a benchmark write-up that is also `feedback_questions` because
   it asks "am I running behind?"). MAXIMUM 3 of each per brand.
6. **Nationalism is orthogonal** to `post_types x sentiment x
   discourse_roles` -- a single post can be e.g. `([perf_compare,
   feedback], positive, [genuine_hype], none, constructive_critical)`.
7. **Off-topic for all brands** -> `{"tweet_id": "<id>", "classifications":
   [], "unsanctioned_flags": []}`. (Shouldn't happen if the brand list
   is non-empty.)
8. **`genuine_hype` is incompatible with explicit call-to-action.** If
   the post has a CTA (`try`, `sign up`, `join`, `get`, `limited-time`,
   `free access`, `limited-time-free`, `immediate-experience`, `register`, `click`), discount offer,
   or wrapper/promo language (`one API key`, `OpenAI-compatible gateway`,
   `free credit no card`), prefer `advertising-marketing` over
   `genuine_hype`. If both genuine praise AND a CTA coexist, emit BOTH --
   let downstream consumers decide.
9. **No prose, no explanation, no code fences** around the JSON.

#### Substantive rules (10-19)

| # | Rule | Trigger -> emit |
|---|---|---|
| 10 | Launch announcements with no evaluative language -> **neutral** | `X is generally available`, `Y launched today`, `Z shipped v3.2`, `W is now in beta` (without praise/criticism) -> INFORMATIONAL. Even optimistic framing like `now available for everyone` is neutral. |
| 11 | Long analytical / investment posts with explicit positive framing -> **positive** | `the model is strategically positive for X's cloud multiple`, `increasingly important as a strategic asset`, `supports the valuation narrative`. Caveats and positive framing coexist -- positive wins. |
| 12 | Multi-brand state-of-market factual updates -> **neutral per brand** | `X climbed 20 spots to #138`, `Y price dropped 8.2%`, `Z was degraded for 45 min`. Neutral unless a specific positive/negative evaluative claim is made about that brand in the same post. |
| 13 | One-line launch posts -> **`event_announcement`**, NOT `hands_on_usage`, NOT `buzz_releases` | The user isn't using the brand (so not `hands_on_usage`); the brand is announcing (so it's `event_announcement`, even for third-party reshares). |
| 14 | TTFT / latency / benchmark / ranking posts -> **`performance_comparisons`** | Mentions of `TTFT`, `latency`, `benchmark`, `ranking`, `#N ranking`, `N spots climbed/dropped`, `side-by-side race`, `vs <other model>`. The LLM Drag Race write-up is the canonical example. |
| 15 | Pure analytical commentary -> **`performance_comparisons` OR `feedback_questions`**, NOT `hands_on_usage` | Price/perf framing, model governance framing, `should I switch?` framing. Author is analyzing, not using. |
| 16 | Nationalism requires explicit US-China relational framing | A post dunking on Qwen for a benchmark miss is `sentiment=anti-Qwen` and `nationalism=neutral`, NOT `us_nationalism=anti`. The nationalism axes measure US-China framing, not anti-vendor hostility. |
| 17 | Trap-language (Chinese-vendor product failure) | When the post contains `trap`, `gotcha`, `embarrassing`, `fumbled`, or `fan-che` AND the subject is a Chinese-vendor product failure -> include `dunk_yingyang` (passive-aggressive) or `fud` (doom-spreading). `us_nationalism=none` per rule 16. |
| 18 | Superlative praise -> `genuine_hype`, NOT a nationalism statement | `fastest`, `best`, `strongest`, `first to ship`, `most powerful` describe the brand being praised. `Qwen is the fastest model` is hype, not `us_nationalism=pro`. |
| 19 | Qwen-vendor-not-US distinction | Posts critiquing Qwen, GLM, DeepSeek, Kimi product behavior do not carry `us_nationalism` valence by default, even when harsh (`Qwen faded`, `DeepSeek shipped a broken model`). `us_nationalism=none` unless the post explicitly invokes US-China framing. |

#### Worked examples (A-J)

| Letter | Post | Per-brand emit |
|---|---|---|
| **A** | "Kimi K2.7 Code is generally available in GitHub Copilot" | `pt=[event_announcement]`, `sent=neutral`, `discourse_roles=[uncategorized]` |
| **B** | "K2.7 Code climbed 20 spots to #138; Deepseek V4 price dropped 8.2%" | per brand: `pt=[hands_on_usage]`, `sent=neutral` for both, `discourse_roles=[uncategorized]` (factual updates, no aggregate judgment) |
| **C** | "Alibaba's Qwen franchise is increasingly important as a strategic cloud and platform asset... strategically positive for BABA's cloud multiple" | `qwen`: `pt=[performance_comparisons]`, `sent=positive`, `discourse_roles=[genuine_hype]`. Other brands in same post without explicit positive framing: `sent=neutral`. |
| **D** | "I built LLM Drag Race: races GPT-4o-mini vs Llama 3.3 70B, measure TTFT" | brands present: `pt=[performance_comparisons]`, `sent=neutral` (showcase, no evaluative claim) |
| **E** | "This changes how GitHub routes coding tasks -- model picker vs single assistant" (price/perf analytical piece) | `pt=[performance_comparisons]` OR `[feedback_questions]` (user implicitly asking "where does this leave me?"), NOT `hands_on_usage` |
| **F** | "Kimi K2.7 Code makes Copilot a model marketplace" (rhetorical questions + analytical commentary) | `pt=[feedback_questions]` (asks 4 rhetorical performance/pricing questions), NOT `hands_on_usage` |
| **G** | "DeepSeek shipping a benchmark trap -- gotcha benchmarks that nobody can reproduce" (anti-vendor dunk on Chinese-vendor product failure) | `deepseek`: `pt=[performance_comparisons]`, `sent=negative`, `discourse_roles=[dunk_yingyang]`, `cn_nationalism=none`, `us_nationalism=none` (per rules 16, 17: dunk tone is surface vocabulary, NOT US-China framing) |
| **H** | "Qwen is the fastest model I've benchmarked this month, scored 89% on MMLU" | `qwen`: `pt=[performance_comparisons]`, `sent=positive`, `discourse_roles=[genuine_hype]`, `cn_nationalism=none`, `us_nationalism=none` (per rule 18: superlative praise is hype, not a US-China statement) |
| **I** | "GLM 5.2 fumbled the launch -- benchmarks collapsed, everyone noticed" (anti-vendor dunk on Chinese-vendor release) | `glm`: `pt=[buzz_releases]`, `sent=negative`, `discourse_roles=[fud]`, `cn_nationalism=none`, `us_nationalism=none` (per rules 16, 19: harsh critique of Chinese-vendor product is anti-vendor sentiment, not US-China framing) |
| **J** | "Kimi K2.7 is fast but DeepSeek V4 is faster on coding tasks; the AI race is heating up between US and Chinese vendors" | `kimi + deepseek`: `pt=[performance_comparisons]`, `sent=neutral`, `discourse_roles=[uncategorized]`, `cn_nationalism=mild_pro`, `us_nationalism=anti` (this post DOES invoke US-China framing explicitly -- rule 16 applies the other way: nationalism fires when the post actually names the AI race) |

---

**Taxonomy values listed in this prompt:**
- `post_types` (6): `buzz_releases`, `hands_on_usage`, `performance_comparisons`, `feedback_questions`, `advertising_marketing`, `event_announcement`
- `sentiment` (4): `positive`, `negative`, `neutral`, `mixed`
- `discourse_roles` (11 listed in prompt: 10 in `_VALID_DISCOURSE` + `uncategorized` runtime sentinel): `genuine_hype`, `sarcasm`, `dunk_yingyang`, `self_deprecation`, `cope`, `fud`, `distillation_accusation`, `ai_slop_critique`, `absurdist_meme`, `advertising-marketing`, `uncategorized`
- `china_nationalism` (6): `none`, `mild_pro`, `pro`, `constructive_critical`, `anti`, `mixed`
- `us_nationalism` (6): `none`, `mild_pro`, `pro`, `constructive_critical`, `anti`, `mixed`
- `unsanctioned_flags` (4): `marketing_spam`, `scam`, `crypto`, `unauthorized`

**Parser fallback** (`_parse_pragmatics_full_response`,
`attribution.py:1473-1559`, and `_parse_pragmatics_full_response_arrays`,
`attribution.py:1569-1667`):
- Unknown `post_type` (or empty `post_types`) -> `hands_on_usage`
- Unknown `sentiment` -> `neutral`
- Unknown `discourse_role` (or empty `discourse_roles`) -> `uncategorized`
- Unknown `china_nationalism` -> `none`
- Unknown `us_nationalism` -> `none`
- `unsanctioned_flags`: unknown values silently dropped via `_parse_unsanctioned_flags` (`attribution.py:1562-1566`)
- Array lengths hard-capped at `_ARRAY_HARD_CAP = 6` (`attribution.py:1119`);
  longer arrays are truncated with a `logger.warning` (defense against
  100-element LLM emissions).
- The per-post path (`classify_pragmatics_full`) calls the array-aware
  parser and reshapes rows back to the legacy `{by_brand: {...},
  unsanctioned_flags: [...]}` shape, taking the first allowed value per
  array field (`attribution.py:1717-1735`).

---

## 4. Allow-lists (`_VALID_*` constants) -- parser-side mirror

**File:** `x_monitor/attribution.py:1091-1114`.

```python
_VALID_DISCOURSE: frozenset[str] = frozenset({
    "genuine_hype", "sarcasm", "dunk_yingyang", "self_deprecation",
    "cope", "fud", "distillation_accusation", "ai_slop_critique",
    "absurdist_meme",
    # U2a: extended by migration 027 + plan 2026-07-03-003.
    # NOTE: hyphenated, not underscored -- see plan KTD7.
    "advertising-marketing",
})
_VALID_NATIONALISM: frozenset[str] = frozenset({
    "none", "mild_pro", "pro", "constructive_critical", "anti", "mixed",
})
_VALID_POST_TYPES = {
    "buzz_releases", "hands_on_usage",
    "performance_comparisons", "feedback_questions",
    # U2a: extended by migration 027 + plan 2026-07-03-003.
    "advertising_marketing", "event_announcement",
}
_VALID_SENTIMENTS = {"positive", "negative", "neutral", "mixed"}

# U2a: top-level unsanctioned flag allow-list. Values outside this set

# are filtered out at the parser (KTD2 / R14).
_VALID_UNSANCTIONED_FLAGS: frozenset[str] = frozenset({
    "marketing_spam", "scam", "crypto", "unauthorized",
})
```

Note that the legacy `build_signal_prompt` parser uses a smaller
4-bucket `valid_post_types` (`_parse_signal_response`,
`attribution.py:947-951`):

```python
valid_post_types = {
    "buzz_releases", "hands_on_usage",
    "performance_comparisons", "feedback_questions",
}
valid_sentiments = {"positive", "negative", "neutral", "mixed"}
```

The migration 027 extensions (`advertising_marketing`,
`event_announcement`, `advertising-marketing`) are **not** valid in this
path; only the full-prompt path accepts them.

`uncategorized` is a parser runtime sentinel for `discourse_role` when
the LLM emits nothing or the array is empty after filtering. It is
**not** in the `discourse_keys` SQL table and is never persisted to
`posts_brands_discourse` (see `docs/reference/lookup-tables.md` Section 3).

---

## 5. Worked examples inside the prompt

The full prompt carries 10 worked examples (A-J). They are reproduced
inline above. Key facts the operator can rely on:

- **A, B, C** are the canonical "factual updates" / "investment framing"
  examples; they all keep nationalism at `none` unless the post
  explicitly invokes US-China framing.
- **D, E, F** are the analytical / showcase / rhetorical-commentary
  examples; rule 13 / 14 / 15 map them to `performance_comparisons` /
  `feedback_questions`, **not** `hands_on_usage`.
- **G, H, I** are the anti-vendor / superlative / harsh-critique examples;
  rules 16 / 17 / 18 / 19 force `cn_nationalism=none` and
  `us_nationalism=none` because the post does not invoke US-China framing.
- **J** is the canonical "AI race between US and Chinese vendors"
  example; this is the **only** worked example where
  `cn_nationalism=mild_pro` and `us_nationalism=anti` is correct.

The boundaries matter: the parser silently coerces nationalism values
not in `_VALID_NATIONALISM`, so if the LLM emits e.g.
`us_nationalism=constructive_criticism` (the misspelling pattern seen in
the 2026-07-07 smoketest review), the parser drops it back to `none`,
which is *probably* the wrong answer for that post and a sign the
prompt legend needs a "constructive_critical" reminder.

---

## 6. Migration impact / drift checklist

When you add a new taxonomy value, three (sometimes four) layers must
move together:

1. **The migration** adds a row to the corresponding `*_keys` SQL table
   (`docs/reference/lookup-tables.md` records which).
2. **The `_VALID_*` constant** in `attribution.py` gains the new value.
3. **The prompt legend** in `_PRAGMATICS_FULL_SYSTEM_PROMPT` (the
   `post_types:`, `discourse_roles:`, etc. blocks) gains the new value
   so the LLM knows to emit it. The constant is at
   `attribution.py:1202-1459`.
4. **(Optional) A worked example** if the new value is in a crowded
   neighborhood (`genuine_hype` vs `analysis`, `fud` vs `nerfing`,
   `advertising-marketing` vs `analysis`) -- without one, the LLM will
   default to whichever bucket its prior in-context exposure leans.

Note that `unsanctioned_flag_keys` may not yet have a SQL table -- the
allow-list at `_VALID_UNSANCTIONED_FLAGS` is enforced in-memory by the
parser. Confirm with `SELECT name FROM sqlite_master WHERE name LIKE
'%unsanctioned%';` before assuming a table exists.

The companion doc **`docs/reference/lookup-tables.md`** carries the same
checklist in its "How to add a new value" section.

---

## 7. File paths

| What | Where |
|---|---|
| `_resolve_signal_model` (env-driven model routing) | `x_monitor/attribution.py:775-821` |
| `_resolve_thinking_default` (DS V4 thinking=disabled) | `attribution.py:825-845` |
| `build_signal_prompt` (legacy) | `attribution.py:875-924` |
| `_parse_signal_response` (legacy parser) | `attribution.py:927-978` |
| `classify_post` (legacy caller) | `attribution.py:1022-1072` |
| `_VALID_DISCOURSE` / `_VALID_NATIONALISM` / `_VALID_POST_TYPES` / `_VALID_SENTIMENTS` / `_VALID_UNSANCTIONED_FLAGS` / `_ARRAY_HARD_CAP` | `attribution.py:1091-1119` |
| `build_pragmatics_full_prompt` (current per-post builder; concatenates `_PRAGMATICS_FULL_SYSTEM_PROMPT`) | `attribution.py:1122-1148` |
| `_max_tokens_for_batch` | `attribution.py:1161-1179` |
| `_PRAGMATICS_FULL_SYSTEM_PROMPT` (the literal prompt body -- most of the rules + worked examples) | `attribution.py:1202-1459` |
| `build_batch_pragmatics_full_prompt` (current batched builder) | `attribution.py:1442-1470` |
| `_parse_pragmatics_full_response` (legacy scalar parser) | `attribution.py:1473-1559` |
| `_parse_unsanctioned_flags` | `attribution.py:1562-1566` |
| `_parse_pragmatics_full_response_arrays` (U2b array parser, current for `classify_pragmatics_full`) | `attribution.py:1569-1667` |
| `classify_pragmatics_full` (per-post caller) | `attribution.py:1670-1758` |
| `_classify_one_batch_to_by_brand` (per-tweet array->scalar collapse) | `attribution.py:1761-1826` |
| `_validate_deepseek_response_shape` (wire-format validator) | `attribution.py:1829-1908` |
| `classify_batch_pragmatics_full` (batched caller) | `attribution.py:1911-2083` |
| `CycleRunner` (v2 cycle orchestrator that calls classifier) | `monitor/cycle.py:403-854` |
| `run_cycle` management command (v2 entry point) | `monitor/management/commands/run_cycle.py` |
| `run_cycle` Celery task (v2 scheduled entry point) | `monitor/tasks.py` |
| Companion doc (SQL taxonomy, operator-visible summary) | `docs/reference/lookup-tables.md` |

---

## 8. v2 invocation diagram

```
                     ┌──────────────────────────────┐
                     │   Django management command   │
                     │   python manage.py run_cycle  │
                     │   --dry-run / --async / ...   │
                     │   run_cycle.py:106-112        │
                     └──────────────┬───────────────┘
                                    │
                     ┌──────────────▼───────────────┐
                     │   Celery beat (scheduled)     │
                     │   monitor/tasks.py:19-39      │
                     │   run_cycle.delay()           │
                     └──────────────┬───────────────┘
                                    │
                     ┌──────────────▼───────────────┐
                     │   CycleRunner.run()           │
                     │   monitor/cycle.py:653        │
                     │                               │
                     │  Step 1: _plan_calls()        │
                     │    x_monitor.query_plan       │
                     │                               │
                     │  Step 2-3: _fetch_tweets()    │
                     │    x_monitor.apify            │
                     │                               │
                     │  Step 4: _attribute_items()   │
                     │    x_monitor.attribution      │
                     │    .attribute_to_brands()     │
                     │                               │
                     │  Step 5: _persist_items()     │
                     │    Django ORM                 │
                     │    (Post, PostBrand,          │
                     │     PostBrandSignal, etc.)    │
                     │                               │
                     │  Step 6: _run_post_fetch()    │
                     │    x_monitor.attribution      │
                     │    .classify_batch_           │
                     │     pragmatics_full()         │
                     │    x_monitor.translator       │
                     │    .translate_batch_          │
                     │     pragmatics()              │
                     └──────────────────────────────┘
```

---
