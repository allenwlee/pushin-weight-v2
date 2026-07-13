# Classifier Prompts — Literal Reference

The `x_monitor.classify_pragmatics_full` pipeline sends an LLM one prompt
per post and parses the structured response against the taxonomy
allow-lists. This doc holds **the literal prompt text and the literal
allow-list constants** so the operator can see exactly what the LLM is
told and what the parser will reject.

Companion doc: **`docs/reference/lookup-tables.md`** (the SQL-side
authoritative taxonomy). Anything that disagrees with that doc is a bug.

**Source of truth:** `x-monitoring/x_monitor/attribution.py`.

---

## 1. Pipeline shape (one prompt per post)

There are **two prompt builders** in the classifier pipeline, only one of
which is current:

| Builder | Status | Purpose |
|---|---|---|
| `build_signal_prompt`        | **legacy / superseded** by U9 | per-brand `(post_type, sentiment)` — 4+4 buckets |
| `build_pragmatics_full_prompt` | **current** (U3a + U9 + §5.1 merged) | per-brand `post_types` × `sentiment` × `discourse_roles` × `china_nationalism` × `us_nationalism`, plus a top-level `unsanctioned_flags` array |

`build_signal_prompt` is preserved for callers that haven't migrated; the
parser `_parse_signal_response` is still wired through `classify_post` for
fallback paths.

The prompts themselves enumerate the taxonomy; the parsers use the
`_VALID_*` allow-lists below to coerce unknown values to a fallback.

---

## 2. `build_signal_prompt` (legacy, U9)

**File:** `x-monitoring/x_monitor/attribution.py:810-859`.

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

**Parser fallback** (U9 / `_parse_signal_response`):
- Unknown `post_type` → `hands_on_usage`
- Unknown `sentiment` → `neutral`
- Hallucinated `brand_id` (not in asked-set) → dropped with a `logger.debug` line.

---

## 3. `build_pragmatics_full_prompt` (current, U3a + U9 + §5.1 merged)

**File:** `x-monitoring/x_monitor/attribution.py:1028-1260`.

### 3a. Raw prompt text (literal, as emitted to the LLM)

Verbatim from `attribution.py:1041-1260`. Use this when you need to see exactly what string the LLM receives (e.g. for debugging LLM misclassifications or copying the prompt into a one-off Claude session).

```python
return (
    "You classify a tweet's relationship to a list of brands, "
    "across FIVE dimensions.\n\n"
    "Tweet text:\n"
    f"\"\"\"\n{text}\n\"\"\"\n\n"
    f"Brands (in order): {brand_list}\n\n"
    "For each brand, return FIVE fields from these exact sets:\n\n"
    "post_types (6 buckets — what KIND of post; ARRAY, max 3):\n"
    "  - buzz_releases            (brand announced something new)\n"
    "  - hands_on_usage           (user is using / showing the brand)\n"
    "  - performance_comparisons  (benchmark / eval / head-to-head)\n"
    "  - feedback_questions       (user asking how-to / help / complaint)\n"
    "  - advertising_marketing   (CTA, promo, wrapper, free-credit pitch)\n"
    "  - event_announcement      (official event / community meetup)\n\n"
    "sentiment (4 values — the VALENCE; scalar):\n"
    "  - positive                 (praise, enthusiasm)\n"
    "  - negative                 (criticism, disappointment)\n"
    "  - neutral                  (informational / question)\n"
    "  - mixed                    (multiple valences in one post)\n\n"
    "discourse_roles (10 keys — pragmatic register, §2; ARRAY, max 3):\n"
    "  - genuine_hype             (straight praise)\n"
    "  - sarcasm                  (English verbal irony)\n"
    "  - dunk_yingyang            (阴阳怪气 / passive-aggressive dunk)\n"
    "  - self_deprecation         (自嘲 / self-mockery)\n"
    "  - cope                     (嘴硬 / stubborn denial)\n"
    "  - fud                      (唱衰 / spreading doom)\n"
    "  - distillation_accusation  (套壳 / 蒸馏指控)\n"
    "  - ai_slop_critique         (AI content-garbage accusation)\n"
    "  - absurdist_meme           (抽象整活 / absurdist antics)\n"
    "  - advertising-marketing    (salesy, CTA-heavy marketing speak — "
    "NOTE: hyphenated, not underscored)\n\n"
    "china_nationalism (6-step scale, §4.4; scalar):\n"
    "  - none                     (no China-nationalism layer)\n"
    "  - mild_pro                 (温和亲华 — subtle positive)\n"
    "  - pro                      (亲华 — open positive)\n"
    "  - constructive_critical   (建设性批评 — pro-CN criticism)\n"
    "  - anti                     (反华 — hostile)\n"
    "  - mixed                    (mixed modes in one post)\n\n"
    "us_nationalism (6-step scale, same as china_nationalism but\n"
    "applied to the US axis — anti = 反美, etc.; scalar):\n"
    "  - none / mild_pro / pro / constructive_critical / anti / mixed\n\n"
    "Rules:\n"
    "1. Return ONLY a JSON object matching this shape:\n"
    "   {\n"
    "     \"classifications\": [\n"
    "       {\n"
    "         \"brand_id\": str,\n"
    "         \"post_types\": [str],         // ARRAY, max 3\n"
    "         \"sentiment\": str,             // scalar\n"
    "         \"discourse_roles\": [str],     // ARRAY, max 3\n"
    "         \"china_nationalism\": str,     // scalar\n"
    "         \"us_nationalism\": str         // scalar\n"
    "       }, ...\n"
    "     ],\n"
    "     \"unsanctioned_flags\": [str]       // ARRAY, top-level\n"
    "   }\n"
    "2. RETURN ONE OBJECT PER BRAND LISTED. The brand list "
    "is what the keyword detector found in the text — if a "
    "brand name appears, you MUST produce an object. Cross-brand "
    "comparison posts (\"GLM 5.2 vs Kimi K2.7\"), reply chains "
    "where the brand is mentioned, posts sharing screenshots "
    "with the brand name — ALL count. Only skip a brand if "
    "the post text contains ZERO mention of it (this should be "
    "impossible given how the brand list was derived).\n"
    "3. Use the EXACT brand_id strings from the list above.\n"
    "4. Most posts have exactly 1 post_type and 1 discourse_role. "
    "Multi-value is allowed when a post legitimately has more than "
    "one (e.g., a benchmark write-up that is also a "
    "`performance_comparisons` AND `feedback_questions` because it "
    "asks 'am I running behind?'). MAXIMUM 3 of each per brand.\n"
    "5. nationalism is ORTHOGONAL to post_types × sentiment × "
    "discourse_roles — a single post can be e.g. "
    "([perf_compare, feedback], positive, [genuine_hype], none, "
    "constructive_critical).\n"
    "6. If the tweet is off-topic for all brands (shouldn't "
    "happen if the brand list is non-empty), return "
    "{\"classifications\": []}.\n"
    "7. genuine_hype is incompatible with explicit call-to-action. "
    "If the post contains a CTA (URL + verb like 'try', 'sign up', "
    "'join', 'get', 'limited-time', 'free access', 限时免费, 立即体验, "
    "注册, 点击), discount offer, or wrapper/promo language "
    "('one API key', 'OpenAI-compatible gateway', 'free credit no card'), "
    "prefer discourse_role `advertising-marketing` over `genuine_hype`. "
    "If both genuine praise AND a CTA coexist, emit BOTH "
    "discourse_roles values — let downstream consumers decide.\n"
    "8. At the JSON root (outside `classifications`), emit "
    "`unsanctioned_flags: [str]`. Allowed values: "
    "`marketing_spam`, `scam`, `crypto`, `unauthorized`. Empty "
    "array if none apply. Use this for promotional/crypto/scam/"
    "unauthorized brand use that the post_type and discourse_role "
    "taxonomies don't fully capture.\n"
    "9. No prose, no explanation, no code fences.\n"
    "\n"
    "10. sent=neutral for launch announcements with no evaluative "
    "language. A post that says only 'X is generally available', "
    "'Y launched today', 'Z shipped v3.2', or 'W is now in beta' "
    "(without praise/criticism) is INFORMATIONAL. emit sent=neutral "
    "regardless of whether the brand would benefit from the "
    "announcement. Optimistic framing like 'now available for "
    "everyone' is still neutral (vendor announcement voice, not "
    "user praise).\n"
    "11. sent=positive for long analytical / investment posts "
    "with explicit positive framing. If the post says 'the model "
    "is strategically positive for X's cloud multiple', "
    "'increasingly important as a strategic asset', 'supports the "
    "valuation narrative', or similar investment-grade positive "
    "language, that IS positive sentiment — do not water it down "
    "to sent=mixed because there are also caveats in the post. "
    "Caveats and positive framing coexist; positive framing wins.\n"
    "12. sent=neutral for multi-brand state-of-market posts that "
    "are factual updates per brand ('X climbed 20 spots to #138, "
    "'Y price dropped 8.2%', 'Z was degraded for 45 min'). emit "
    "sent=neutral for each brand UNLESS a specific positive/"
    "negative evaluative claim is made about that brand in the "
    "same post.\n"
    "13. pt=event_announcement for one-line 'X is generally "
    "available / Y launched / Z shipped' posts. NOT hands_on_usage "
    "(the user isn't using the brand — the brand is announcing). "
    "NOT buzz_releases (that's a brand-side press release; this "
    "rule covers third-party reshares of an announcement too).\n"
    "14. pt=performance_comparisons for any post mentioning TTFT "
    "(time-to-first-token), latency, benchmark, ranking, '#N "
    "ranking', 'N spots climbed/dropped', 'side-by-side race', "
    "'vs <other model>'. The LLM Drag Race write-up ('races GPT-"
    "4o-mini vs Llama 3.3 70B side-by-side, measure TTFT') is the "
    "canonical example.\n"
    "15. pt=performance_comparisons OR pt=feedback_questions for "
    "pure analytical commentary (price/perf framing, model "
    "governance framing, 'should I switch?' framing). NOT "
    "hands_on_usage — the author is analyzing, not using.\n"
    "16. Nationalism requires explicit US-China relational framing. "
    "Do not infer `china_nationalism` or `us_nationalism` from "
    "generic anti-vendor dunk on a Chinese (or US) brand's product "
    "failure, benchmark miss, or release reception. A post dunking "
    "on Qwen for a benchmark miss is `sentiment=anti-Qwen` and "
    "`nationalism=neutral`, NOT `us_nationalism=anti`. The "
    "nationalism axes measure US-China framing, not anti-vendor "
    "hostility.\n"
    "17. Trap-language handling. When the post text contains "
    "\"trap\", \"gotcha\", \"embarrassing\", \"fumbled\", or "
    "\"翻车\" AND the subject is a Chinese-vendor product failure, "
    "the post's `discourse_roles` should include `dunk_yingyang` "
    "if the tone is passive-aggressive, or `fud` if the tone is "
    "doom-spreading. The post's `us_nationalism` should remain "
    "`none` per rule 16 — trap-language is surface vocabulary, "
    "not a US-China framing signal.\n"
    "18. Superlative praise (`fastest`, `best`, `strongest`, "
    "`first to ship`, `most powerful`) describes the brand being "
    "praised, NOT a US-China framing. The post is "
    "`discourse_roles=[genuine_hype]` for the brand being praised "
    "— NOT `us_nationalism=pro/anti` based on which country the "
    "praised brand is from. 'Qwen is the fastest model' is hype, "
    "not a nationalism statement about China.\n"
    "19. Qwen-vendor-not-US distinction. Posts critiquing a "
    "Chinese-vendor's product behavior (Qwen, GLM, DeepSeek, Kimi) "
    "do not carry `us_nationalism` valence by default. Even when "
    "the critique is harsh (\"Qwen faded\", \"DeepSeek shipped a "
    "broken model\"), the axis measures US-China framing, not "
    "anti-Chinese-vendor sentiment. emit `us_nationalism=none` "
    "unless the post explicitly invokes US-China framing.\n"
    "\n"
    "Worked examples (reference cases; match these patterns):\n"
    "  A. 'Kimi K2.7 Code is generally available in GitHub Copilot'\n"
    "     → per brand: pt=[event_announcement], sent=neutral,\n"
    "       discourse_roles=[uncategorized].\n"
    "  B. 'K2.7 Code climbed 20 spots to #138; Deepseek V4 price "
    "dropped 8.2%'\n"
    "     → per brand: pt=[hands_on_usage], sent=neutral for both,\n"
    "       discourse_roles=[uncategorized]. (factual updates, no\n"
    "       aggregate judgment.)\n"
    "  C. 'Alibaba's Qwen franchise is increasingly important as a\n"
    "strategic cloud and platform asset... strategically positive "
    "for BABA's cloud multiple'\n"
    "     → qwen: pt=[performance_comparisons],\n"
    "       sent=positive, discourse_roles=[genuine_hype].\n"
    "       other brands mentioned in same post without explicit\n"
    "       positive framing: sent=neutral.\n"
    "  D. 'I built LLM Drag Race: races GPT-4o-mini vs Llama 3.3 "
    "70B, measure TTFT'\n"
    "     → brands present: pt=[performance_comparisons],\n"
    "       sent=neutral (showcase, no evaluative claim).\n"
    "  E. 'This changes how GitHub routes coding tasks — model "
    "picker vs single assistant' (price/perf analytical piece)\n"
    "     → pt=[performance_comparisons] OR\n"
    "       [feedback_questions] (user implicitly asking 'where "
    "does this leave me?'), NOT hands_on_usage.\n"
    "  F. 'Kimi K2.7 Code makes Copilot a model marketplace' "
    "(rhetorical questions + analytical commentary)\n"
    "     → pt=[feedback_questions] (asks 4 rhetorical "
    "performance/pricing questions), NOT hands_on_usage.\n"
    "  G. 'DeepSeek shipping a benchmark trap — gotcha benchmarks "
    "that nobody can reproduce' (anti-vendor dunk on Chinese-vendor "
    "product failure)\n"
    "     → deepseek: pt=[performance_comparisons], sent=negative,\n"
    "       discourse_roles=[dunk_yingyang], cn_nationalism=none,\n"
    "       us_nationalism=none. (per rules 16, 17: dunk tone is\n"
    "       surface vocabulary, NOT US-China framing.)\n"
    "  H. 'Qwen is the fastest model I've benchmarked this month, "
    "scored 89% on MMLU'\n"
    "     → qwen: pt=[performance_comparisons], sent=positive,\n"
    "       discourse_roles=[genuine_hype], cn_nationalism=none,\n"
    "       us_nationalism=none. (per rule 18: superlative praise\n"
    "       is hype, not a US-China statement.)\n"
    "  I. 'GLM 5.2 fumbled the launch — benchmarks collapsed, "
    "everyone noticed' (anti-vendor dunk on Chinese-vendor release)\n"
    "     → glm: pt=[buzz_releases], sent=negative,\n"
    "       discourse_roles=[fud], cn_nationalism=none,\n"
    "       us_nationalism=none. (per rules 16, 19: harsh critique\n"
    "       of Chinese-vendor product is anti-vendor sentiment,\n"
    "       not US-China framing.)\n"
    "  J. 'Kimi K2.7 is fast but DeepSeek V4 is faster on coding "
    "tasks; the AI race is heating up between US and Chinese "
    "vendors'\n"
    "     → kimi + deepseek: pt=[performance_comparisons],\n"
    "       sent=neutral, discourse_roles=[uncategorized],\n"
    "       cn_nationalism=mild_pro, us_nationalism=anti. (this\n"
    "       post DOES invoke US-China framing explicitly — rule 16\n"
    "       applies the other way: nationalism fires when the post\n"
    "       actually names the AI race.)\n"
)
```

### 3b. Formatted, readable version

Same content as 3a, restructured for human reading. Use this when triaging classifier misclassifications or planning prompt rewrites.

#### Header
> You classify a tweet's relationship to a list of brands, across FIVE dimensions.
> Tweet text: `<text>`
> Brands (in order): `<brand_id_1>, <brand_id_2>, …`

#### Field-by-field enumeration

| Field | Cardinality | Values |
|---|---|---|
| `post_types`         | ARRAY, max 3 | `buzz_releases`, `hands_on_usage`, `performance_comparisons`, `feedback_questions`, `advertising_marketing`, `event_announcement` |
| `sentiment`          | scalar       | `positive`, `negative`, `neutral`, `mixed` |
| `discourse_roles`    | ARRAY, max 3 | `genuine_hype`, `sarcasm`, `dunk_yingyang`, `self_deprecation`, `cope`, `fud`, `distillation_accusation`, `ai_slop_critique`, `absurdist_meme`, `advertising-marketing` (hyphenated, not underscored) |
| `china_nationalism`  | scalar       | `none`, `mild_pro`, `pro`, `constructive_critical`, `anti`, `mixed` |
| `us_nationalism`     | scalar       | same six values (anti = 反美, etc.) |

#### Output JSON shape (rule 1)
```json
{
  "classifications": [
    {
      "brand_id": "<string>",
      "post_types":         ["<string>", ...],   // ARRAY, max 3
      "sentiment":          "<string>",
      "discourse_roles":    ["<string>", ...],   // ARRAY, max 3
      "china_nationalism":  "<string>",
      "us_nationalism":     "<string>"
    },
    ...
  ],
  "unsanctioned_flags": ["marketing_spam", "scam", "crypto", "unauthorized"]
}
```

#### Structural rules (1–9)

1. **Output shape** — the JSON above; nothing else.
2. **One object per brand** — the brand list came from the keyword detector; if the brand name appears in the text, you MUST produce an object. Cross-brand comparison, reply chains, screenshot shares — all count. Only skip a brand if there is literally zero mention (which shouldn't happen given the detector).
3. **Use exact `brand_id` strings** from the list the prompt gave you.
4. **Most posts have 1 `post_type` and 1 `discourse_role`.** Multi-value is allowed when a post legitimately has more than one (e.g., a benchmark write-up that is also `feedback_questions` because it asks "am I running behind?"). MAXIMUM 3 of each per brand.
5. **Nationalism is orthogonal** to `post_types × sentiment × discourse_roles` — a single post can be e.g. `([perf_compare, feedback], positive, [genuine_hype], none, constructive_critical)`.
6. **Off-topic for all brands** → `{"classifications": []}`. (Shouldn't happen if the brand list is non-empty.)
7. **`genuine_hype` is incompatible with explicit call-to-action.** If the post has a CTA (`try`, `sign up`, `join`, `get`, `limited-time`, `free access`, `限时免费`, `立即体验`, `注册`, `点击`), discount offer, or wrapper/promo language (`one API key`, `OpenAI-compatible gateway`, `free credit no card`), prefer `advertising-marketing` over `genuine_hype`. If both genuine praise AND a CTA coexist, emit BOTH — let downstream consumers decide.
8. **Top-level `unsanctioned_flags`** (outside `classifications`) — for marketing spam, scam, crypto, unauthorized brand use that `post_type` / `discourse_role` don't capture. Empty array if none apply.
9. **No prose, no explanation, no code fences** around the JSON.

#### Substantive rules (10–19)

| # | Rule | Trigger → emit |
|---|---|---|
| 10 | Launch announcements with no evaluative language → **neutral** | `X is generally available`, `Y launched today`, `Z shipped v3.2`, `W is now in beta` (without praise/criticism) → INFORMATIONAL. Even optimistic framing like `now available for everyone` is neutral. |
| 11 | Long analytical / investment posts with explicit positive framing → **positive** | `the model is strategically positive for X's cloud multiple`, `increasingly important as a strategic asset`, `supports the valuation narrative`. Caveats and positive framing coexist — positive wins. |
| 12 | Multi-brand state-of-market factual updates → **neutral per brand** | `X climbed 20 spots to #138`, `Y price dropped 8.2%`, `Z was degraded for 45 min`. Neutral unless a specific positive/negative evaluative claim is made about that brand in the same post. |
| 13 | One-line launch posts → **`event_announcement`**, NOT `hands_on_usage`, NOT `buzz_releases` | The user isn't using the brand (so not `hands_on_usage`); the brand is announcing (so it's `event_announcement`, even for third-party reshares). |
| 14 | TTFT / latency / benchmark / ranking posts → **`performance_comparisons`** | Mentions of `TTFT`, `latency`, `benchmark`, `ranking`, `#N ranking`, `N spots climbed/dropped`, `side-by-side race`, `vs <other model>`. The LLM Drag Race write-up is the canonical example. |
| 15 | Pure analytical commentary → **`performance_comparisons` OR `feedback_questions`**, NOT `hands_on_usage` | Price/perf framing, model governance framing, `should I switch?` framing. Author is analyzing, not using. |
| 16 | Nationalism requires explicit US-China relational framing | A post dunking on Qwen for a benchmark miss is `sentiment=anti-Qwen` and `nationalism=neutral`, NOT `us_nationalism=anti`. The nationalism axes measure US-China framing, not anti-vendor hostility. |
| 17 | Trap-language (Chinese-vendor product failure) | When the post contains `trap`, `gotcha`, `embarrassing`, `fumbled`, or `翻车` AND the subject is a Chinese-vendor product failure → include `dunk_yingyang` (passive-aggressive) or `fud` (doom-spreading). `us_nationalism=none` per rule 16. |
| 18 | Superlative praise → `genuine_hype`, NOT a nationalism statement | `fastest`, `best`, `strongest`, `first to ship`, `most powerful` describe the brand being praised. `Qwen is the fastest model` is hype, not `us_nationalism=pro`. |
| 19 | Qwen-vendor-not-US distinction | Posts critiquing Qwen, GLM, DeepSeek, Kimi product behavior do not carry `us_nationalism` valence by default, even when harsh (`Qwen faded`, `DeepSeek shipped a broken model`). `us_nationalism=none` unless the post explicitly invokes US-China framing. |

#### Worked examples (A–J)

| Letter | Post | Per-brand emit |
|---|---|---|
| **A** | "Kimi K2.7 Code is generally available in GitHub Copilot" | `pt=[event_announcement]`, `sent=neutral`, `discourse_roles=[uncategorized]` |
| **B** | "K2.7 Code climbed 20 spots to #138; Deepseek V4 price dropped 8.2%" | per brand: `pt=[hands_on_usage]`, `sent=neutral` for both, `discourse_roles=[uncategorized]` (factual updates, no aggregate judgment) |
| **C** | "Alibaba's Qwen franchise is increasingly important as a strategic cloud and platform asset... strategically positive for BABA's cloud multiple" | `qwen`: `pt=[performance_comparisons]`, `sent=positive`, `discourse_roles=[genuine_hype]`. Other brands in same post without explicit positive framing: `sent=neutral`. |
| **D** | "I built LLM Drag Race: races GPT-4o-mini vs Llama 3.3 70B, measure TTFT" | brands present: `pt=[performance_comparisons]`, `sent=neutral` (showcase, no evaluative claim) |
| **E** | "This changes how GitHub routes coding tasks — model picker vs single assistant" (price/perf analytical piece) | `pt=[performance_comparisons]` OR `[feedback_questions]` (user implicitly asking "where does this leave me?"), NOT `hands_on_usage` |
| **F** | "Kimi K2.7 Code makes Copilot a model marketplace" (rhetorical questions + analytical commentary) | `pt=[feedback_questions]` (asks 4 rhetorical performance/pricing questions), NOT `hands_on_usage` |
| **G** | "DeepSeek shipping a benchmark trap — gotcha benchmarks that nobody can reproduce" (anti-vendor dunk on Chinese-vendor product failure) | `deepseek`: `pt=[performance_comparisons]`, `sent=negative`, `discourse_roles=[dunk_yingyang]`, `cn_nationalism=none`, `us_nationalism=none` (per rules 16, 17: dunk tone is surface vocabulary, NOT US-China framing) |
| **H** | "Qwen is the fastest model I've benchmarked this month, scored 89% on MMLU" | `qwen`: `pt=[performance_comparisons]`, `sent=positive`, `discourse_roles=[genuine_hype]`, `cn_nationalism=none`, `us_nationalism=none` (per rule 18: superlative praise is hype, not a US-China statement) |
| **I** | "GLM 5.2 fumbled the launch — benchmarks collapsed, everyone noticed" (anti-vendor dunk on Chinese-vendor release) | `glm`: `pt=[buzz_releases]`, `sent=negative`, `discourse_roles=[fud]`, `cn_nationalism=none`, `us_nationalism=none` (per rules 16, 19: harsh critique of Chinese-vendor product is anti-vendor sentiment, not US-China framing) |
| **J** | "Kimi K2.7 is fast but DeepSeek V4 is faster on coding tasks; the AI race is heating up between US and Chinese vendors" | `kimi + deepseek`: `pt=[performance_comparisons]`, `sent=neutral`, `discourse_roles=[uncategorized]`, `cn_nationalism=mild_pro`, `us_nationalism=anti` (this post DOES invoke US-China framing explicitly — rule 16 applies the other way: nationalism fires when the post actually names the AI race) |

---

**Taxonomy values listed in this prompt:**
- `post_types` (6): `buzz_releases`, `hands_on_usage`, `performance_comparisons`, `feedback_questions`, `advertising_marketing`, `event_announcement`
- `sentiment` (4): `positive`, `negative`, `neutral`, `mixed`
- `discourse_roles` (10): `genuine_hype`, `sarcasm`, `dunk_yingyang`, `self_deprecation`, `cope`, `fud`, `distillation_accusation`, `ai_slop_critique`, `absurdist_meme`, `advertising-marketing`
- `china_nationalism` (6): `none`, `mild_pro`, `pro`, `constructive_critical`, `anti`, `mixed`
- `us_nationalism` (6): `none`, `mild_pro`, `pro`, `constructive_critical`, `anti`, `mixed`
- `unsanctioned_flags` (4): `marketing_spam`, `scam`, `crypto`, `unauthorized`

**Parser fallback** (`_parse_pragmatics_full_response`):
- Unknown `post_type` → `hands_on_usage`
- Unknown `sentiment` → `neutral`
- Unknown `discourse_role` (the prompt's array form, scalar branch) → `uncategorized`
- Unknown `china_nationalism` → `none`
- Unknown `us_nationalism` → `none`
- `unsanctioned_flags`: unknown values silently dropped via `_parse_unsanctioned_flags`

---

## 4. Allow-lists (`_VALID_*` constants) — parser-side mirror

**File:** `x-monitoring/x_monitor/attribution.py:997-1020`.

```python
_VALID_DISCOURSE: frozenset[str] = frozenset({
    "genuine_hype", "sarcasm", "dunk_yingyang", "self_deprecation",
    "cope", "fud", "distillation_accusation", "ai_slop_critique",
    "absurdist_meme",
    # U2a: extended by migration 027 + plan 2026-07-03-003.
    # NOTE: hyphenated, not underscored — see plan KTD7.
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
4-bucket `valid_post_types` (`_parse_signal_response`):

```python
valid_post_types = {
    "buzz_releases", "hands_on_usage",
    "performance_comparisons", "feedback_questions",
}
valid_sentiments = {"positive", "negative", "neutral", "mixed"}
```

(`attribution.py:882-886`)

That's the parser-side mirror of the legacy prompt — the migration 027
extensions (`advertising_marketing`, `event_announcement`, `advertising-marketing`)
are **not** valid in this path; only the full-prompt path accepts them.

---

## 5. Worked examples inside the prompt

The full prompt carries 10 worked examples (A–J). They are reproduced
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
3. **The prompt legend** in `build_pragmatics_full_prompt` (the
   `post_types:`, `discourse_roles:`, etc. blocks) gains the new value
   so the LLM knows to emit it.
4. **(Optional) A worked example** if the new value is in a crowded
   neighborhood (`genuine_hype` vs `analysis`, `fud` vs `nerfing`,
   `advertising-marketing` vs `analysis`) — without one, the LLM will
   default to whichever bucket its prior in-context exposure leans.

The companion doc **`docs/reference/lookup-tables.md`** carries the same
checklist in its "How to add a new value" section.

---

## 7. File paths

| What | Where |
|---|---|
| Prompt builders (`build_signal_prompt`, `build_pragmatics_full_prompt`) | `x-monitoring/x_monitor/attribution.py:810` and `:1028` |
| Parser fallbacks (`_parse_signal_response`, `_parse_pragmatics_full_response`) | `x-monitoring/x_monitor/attribution.py:862` and `:1263` |
| Allow-list constants (`_VALID_*`) | `x-monitoring/x_monitor/attribution.py:997-1020` |
| Companion doc (SQL taxonomy, operator-visible summary) | `docs/reference/lookup-tables.md` |
