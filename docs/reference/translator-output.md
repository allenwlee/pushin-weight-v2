# Translator output columns

x-monitor has two distinct translator stages that write to different
columns. The naming is a bit subtle — `literal_zh` vs `text_zh_cn` —
so this page lists each column, its translator stage, when it's
populated, and an example.

## The two stages

| Stage | Function | Caller | Output columns on `posts` |
|---|---|---|---|
| **Post translator** (lossless with slang) | `translate_batch_pragmatics` | `x-monitor smoketest`, post-fetch pipeline, `x-monitor backfill translate-posts` | `text_en`, `literal_zh`, `text_zh_cn`, `lang_detected`, `discourse_role`, `cn_equivalent`, `annotation` |
| **Registry translator** (formal, named-entity-preserving) | `translate_registry_rows` | `x-monitor translate-registry` | per-registry-table locale columns (e.g. `brands.display_name_en`, `brands.display_name_zh_cn`) |

The two stages emit different columns and use different prompts.
`literal_zh` and `text_zh_cn` look almost the same and both end up on
`posts` — they reflect **two different rendering styles**, not two
different languages.

## Post-translator output (X / Twitter posts)

The post translator handles high-volume, noisy source text. It uses
the §5.1 four-pronged contract (text_en, literal_zh, cn_equivalent,
annotation) and explicitly preserves slang, memes, brand-voice.

| Column | Populated when | Example |
|---|---|---|
| `text_en` | Source is NOT already English and NOT already Simplified Chinese (deterministic noop) | "Anthropics neue KI-Modelle" → "Anthropic's new AI models" |
| `literal_zh` | Source is NOT already Simplified Chinese (deterministic noop) — note that this is the LLM's best-interpretation rendering, NOT a literal word-for-word translation | "GitHub Copilot just dropped Kimi K2.7 like a secret weapon from a sci-fi film" → "GitHub Copilot 刚刚把 Kimi K2.7 像科幻片里的秘密武器一样扔出来" |
| `text_zh_cn` | Same as `literal_zh` (identical column on `posts`; the registry translator uses `text_zh_cn` for its own output naming on different tables) | see above |
| `lang_detected` | Always | "en", "zh-Hans", "de", etc. |
| `discourse_role` | Always | "genuine_hype", "sarcasm", "dunk_yingyang", "uncategorized", etc. |
| `cn_equivalent` | Always; populated for every input | "Kimi K2.7 Code is generally available in GitHub Copilot" → "Kimi K2.7 Code 正式登陆 Copilot，全量开放" |
| `annotation` | Only when the post contains F2/F3 friction (meme origin, named event, brand slur). Otherwise empty. | "GPT-4o-mini 的 CodingPlan 试用贴暴露了 OpenAI 的吞量设计哲学" |

## Registry-translator output (brands, products, etc.)

The registry translator handles lookup-table rows that need a
formal Chinese rendering — brand display names, company bios, etc.
It uses the same model but a different prompt that emphasizes
proper-noun preservation and formal register.

| Column | Populated when | Example |
|---|---|---|
| `brands.display_name_zh_cn` | --locale=zh_cn (or both) | "Moonshot AI" → "月之暗面" |
| `brands.display_name_en` | --locale=en (or both) | already English, noop |
| `accounts.bio_zh_cn` | --locale=zh_cn | "AI researcher, ex-Google Brain" → "AI 研究员，前 Google Brain" |
| etc. | ... | ... |

## Deterministic noop (the "source serves" rule)

When the source is already in the target locale's language, the
server-side translator NULLs the corresponding column. This is
deterministic — based on `lang_detected`, not the LLM's noisy
self-report. Implemented in `x_monitor/translator.py:_is_english_family`
and `_is_simplified_chinese_family`.

| Source language | text_en | literal_zh / text_zh_cn |
|---|---|---|
| `en` family | NULL (source serves) | populated (best-interpretation Chinese) |
| `zh-Hans` family | populated (English rendering of source) | NULL (source serves) |
| Other (de, fr, etc.) | populated (English rendering) | populated (Chinese rendering) |
| Empty / NULL | populated (LLM uses target_locales to choose) | populated |

The noop prevents two bugs:
1. The translator echoing the English source into `text_en` (when
   the source is already English, that's redundant).
2. The translator echoing Chinese source into `text_en` (the v10
   smoketest Post 4 bug — fixed in plan 003 U5).

## Common confusions

- **`literal_zh` is the post translator's output, `text_zh_cn` is
  the registry translator's output naming.** Same column on `posts`
  because both translator stages write there — but on registry
  tables (`brands`, `accounts`, `companies`), only the registry
  translator writes, and the column is called `text_zh_cn` (or
  `<col>_zh_cn`). Don't mix up the call sites.

- **`cn_equivalent` is NOT a translation — it's a "how would Chinese
  netizens on Weibo/Zhihu/Bilibili say this" free rendering.**
  Different purpose from `literal_zh` (which is the best-interpretation
  Chinese rendering of the source).

- **`annotation` is sparsely populated.** Only when the post has
  cultural friction the dashboard reviewer needs to know about (a
  meme origin, a named event, a brand-specific slur). Empty string
  is normal.

## Where the columns live in code

- `translate_batch_pragmatics`: `x_monitor/translator.py:573`
- `translate_registry_rows`: `x_monitor/translator.py:783`
- Server-side noop logic: `x_monitor/translator.py:625-666`
- Column write paths in the post-fetch pipeline: `x_monitor/run.py`
  (`_run_post_fetch` writes to `posts`; `cmd_translate_registry`
  writes to registry tables)
