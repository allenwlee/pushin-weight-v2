# Translator output columns

x-monitor has two distinct translator stages that write to different
columns. The naming is a bit subtle — `literal_zh` vs `text_zh_cn` —
so this page lists each column, its translator stage, when it's
populated, and an example.

## The two stages

| Stage | Function | Caller | Output columns on `posts` |
|---|---|---|---|
| **Post translator** (lossless with slang) | `translate_batch_pragmatics` | `x-monitor smoketest`, post-fetch pipeline, `x-monitor backfill translate-posts` | `text_en`, `literal_zh`, `text_zh_cn`, `lang_detected`, `en_equivalent`, `cn_equivalent`, `annotation` |
| **Registry translator** (formal, named-entity-preserving) | `translate_registry_rows` | `x-monitor translate-registry` | per-registry-table locale columns (e.g. `brands.display_name_en`, `brands.display_name_zh_cn`) |

The two stages emit different columns and use different prompts.
`literal_zh` and `text_zh_cn` look almost the same and both end up on
`posts` — they reflect **two different rendering styles**, not two
different languages.

> **Note (plan 2026-07-06-001):** `discourse_role` was removed from the
> post-translator contract. Pragmatic register is now exclusively the
> classifier's per-brand output — see `posts_brands_discourse`,
> populated by `classify_pragmatics_full` (one row per
> `post_id × brand_id × discourse_key × act_id`). The translator
> returns translation + netizen voice + friction annotation only.

## Post-translator output (X / Twitter posts)

The post translator handles high-volume, noisy source text. It uses
the translation-and-commentary contract (`text_en`, `literal_zh`, bilingual
analyst commentary, and optional annotation) and explicitly preserves slang,
memes, and brand voice.

| Column | Populated when | Example |
|---|---|---|
| `text_en` | Always after durable post-fetch persistence. The translator may mark an English-source echo as a noop; the persistence layer stores the source text in that case. | "Anthropics neue KI-Modelle" → "Anthropic's new AI models" |
| `literal_zh` | Source is NOT already Simplified Chinese (deterministic noop) — note that this is the LLM's best-interpretation rendering, NOT a literal word-for-word translation | "GitHub Copilot just dropped Kimi K2.7 like a secret weapon from a sci-fi film" → "GitHub Copilot 刚刚把 Kimi K2.7 像科幻片里的秘密武器一样扔出来" |
| `text_zh_cn` | Always after durable post-fetch persistence. The translator may mark a Simplified-Chinese-source echo as a noop; the persistence layer stores the source text in that case. | see above |
| `lang_detected` | Always; one of `en`, `zh-Hans`, `zh-Hant`, `ja`, `ko`, or `other`. Registered ISO 639-1 language tags outside the named families normalize to `other`; undetermined/private/reserved values remain invalid. | Model `fr`, `ar`, `de`, or `es-MX` → persisted `other` |
| `en_equivalent` → `posts.commentary_en` | Always; non-empty English analyst synthesis, distinct from source and both translations | "The release expands Kimi's reach through Copilot." |
| `cn_equivalent` → `posts.commentary_zh_cn` | Always; non-empty Simplified Chinese analyst synthesis, distinct from source and both translations | "Kimi K2.7 Code 正式登陆 Copilot，触达面又扩大了。" |
| `annotation` | Only when the post contains F2/F3 friction (meme origin, named event, brand slur). Otherwise empty. | "GPT-4o-mini 的 CodingPlan 试用贴暴露了 OpenAI 的吞量设计哲学" |

For pragmatic register (`discourse_role`), see
`posts_brands_discourse` — it's emitted exclusively by
`classify_pragmatics_full` (one row per `post × brand × act`),
populated by Stage 2 of the post-fetch pipeline.

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

## Deterministic noop inside the translator

When the source is already in the target locale's language, the translator
marks that generated field as a noop. This is deterministic—based on
`lang_detected`, not an LLM noop hint. The durable Django post-fetch path then
uses the source text as the persisted target-locale value, so a successful
enrichment row has both `text_en` and `text_zh_cn` populated.

| Source language | text_en | literal_zh / text_zh_cn |
|---|---|---|
| `en` family | source text persisted | populated (best-interpretation Chinese) |
| `zh-Hans` family | populated (English rendering of source) | source text persisted |
| Other (de, fr, etc.) | populated (English rendering) | populated (Chinese rendering) |
| Empty / NULL | populated (LLM uses target_locales to choose) | populated |

The noop prevents the model from inventing a same-language translation while
still allowing persistence completeness to be checked directly from columns.

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

- **`en_equivalent` is also not a translation.** It is an English analyst
  synthesis and persists to `commentary_en`. `cn_equivalent` persists to
  `commentary_zh_cn`. Blank, `N/A`, or copied output is incomplete and the
  durable queue retries it.

- **`annotation` is sparsely populated.** Only when the post has
  cultural friction the dashboard reviewer needs to know about (a
  meme origin, a named event, a brand-specific slur). Empty string
  is normal.

## Where the columns live in code

- `translate_batch_pragmatics`: `x_monitor/translator.py`
- `translate_registry_rows`: `x_monitor/translator.py`
- Translator noop and output validation: `x_monitor/translator.py`
- Durable persistence and retry state: `monitor/cycle.py`
- Column write paths in the post-fetch pipeline: `x_monitor/run.py`
  (`_run_post_fetch` writes to `posts`; `cmd_translate_registry`
  writes to registry tables)
