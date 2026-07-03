# Post-fetch pipeline architecture

This document describes the per-post transformations that run inside
`RunPipeline.execute` AFTER the TwitterAPI.io fetch. The pipeline was
streamlined in 2026-07-02 per
`docs/plans/2026-07-02-002-feat-streamlined-post-fetch-pipeline-plan.md`.

## Call sequence

```
RunPipeline.execute
  │
  ├──> TwitterApiClient.run_search         (unchanged — fetch + paginate)
  │
  ├──> _attribute_call_items               (U2: unchanged)
  │       per kept tweet: classify_post(text, brand_ids, registry, client)
  │       writes: posts_brands_signals (post_type + sentiment)
  │
  ├──> _run_post_fetch  (NEW — U3 + U4)    (called once per cycle, after insert)
  │       on the kept set:
  │         1. translate_batch(kept, target_locales, client)
  │            writes: posts.text_en / text_zh_cn / lang_detected
  │            applies F0–F3 friction judge to per-post annotation
  │
  │         2. classify_pragmatics_full(kept, brands, registry, client)
  │            writes: posts_brands_signals (post_type + sentiment)  [mirrors classify_post]
  │                    posts_brands_discourse (discourse_role + china_nat + us_nat)
  │
  └──> phase_timings_sec += {classify, translate, discourse}
```

The merged `classify_pragmatics_full` call returns all four prongs
(post_type, sentiment, discourse_role, china_nationalism,
us_nationalism) for every (tweet × attributed_brand) row in one
structured LLM response. This is the KTD1 architecture choice — see
Plan2 §4 Key Technical Decisions for the timing rationale.

The `classify_post` path remains for the quote-tweet ingestion path
(`_ingest_quote_tweets`), which doesn't have the brand registry
available. It writes only `(post_type, sentiment)` to
`posts_brands_signals` — the same columns that `classify_pragmatics_full`
writes — so the two paths converge at the storage layer.

## Per-post data flow

```
kept_tweet
  │
  ├──> translate_batch (one call per 20-post batch)
  │      │
  │      ├──> posts.text_en
  │      ├──> posts.text_zh_cn
  │      └──> posts.lang_detected
  │
  └──> classify_pragmatics_full (one call per 20-post batch)
         │
         ├──> posts_brands_signals  (post_type, sentiment)  [existing — migration 022 shape]
         └──> posts_brands_discourse (discourse_role, china_nationalism, us_nationalism)
                                                                  [new — migration 025 shape]
```

Failures at any stage are non-fatal per the v1.7 contract. A row
that fails the LLM call stays NULL on the affected columns and the
cycle continues.

## Hot-loop time budget

| Stage                  | Per kept post | At 200 kept posts | Notes                              |
|------------------------|---------------|-------------------|------------------------------------|
| Fetch + attribute      | 0.05 s        | 10 s              | Variable per TwitterAPI.io latency |
| classify_pragmatics_full | 0.03 s      | 6 s               | 20-post batches × 10 calls         |
| translate_batch        | 0.03 s        | 6 s               | Same                               |
| Bulk store writes      | 0.005 s       | 1 s               | INSERT OR IGNORE                   |
| **Subtotal**           | **0.115 s**   | **23 s**          |                                    |
| **Cycle target**       |               | **< 90 s**        | **~67 s headroom for retries**     |

The smoketest runner (`scripts/post_fetch_smoketest.py`) prints
per-stage wall-clock and asserts the cycle stays under the 90s
ceiling when invoked with `--strict-budget`.

## Storage shape

### Existing tables (unchanged)

- `posts` — already has `text_en`, `text_zh_cn`, `lang_detected`
  (migration 003) and the INTEGER id PK `posts.id` (migration 020).
- `posts_brands_signals` — `(post_id INTEGER, brand_id INTEGER,
  post_type INTEGER, sentiment INTEGER)`. Migration 022 promoted
  `post_type` and `sentiment` to NOT NULL INTEGER FKs.
- `post_type_keys` + `sentiment_keys` — seeded by migration 019.

### New tables (migration 025)

- `discourse_keys` — 9-way pragmatic-register vocabulary
  (genuine_hype, sarcasm, dunk_yingyang, self_deprecation, cope,
  fud, distillation_accusation, ai_slop_critique, absurdist_meme).
  INTENTIONALLY TIGHT: no `other` bucket. Unknown keys coerce to
  `uncategorized` at the brief renderer (KTD5).
- `nationalism_keys` — 6-step scale shared across both axes
  (none, mild_pro, pro, constructive_critical, anti, mixed).
- `discourse_labels` + `nationalism_labels` — i18n label tables
  keyed on `(key, lang)` with en + zh_cn seeded.
- `posts_brands_discourse` — composite-PK `(post_id INTEGER,
  brand_id INTEGER, discourse_key INTEGER, act_id INTEGER)`.
  `china_nationalism` + `us_nationalism` FKs are nullable during
  the backfill window. Three brand-scoped indexes mirror
  `pushin_weight/core/models.py::PostBrandDiscourse`.

### Why the two nationalism axes share one enum

Per research §4.4, the US and China axes have different data shapes
on X but share the same 6-step bucket vocabulary. The renderer
expands the key by axis context: `china_nationalism::anti` →
"反华"; `us_nationalism::anti` → "反美". Per-axis label tables
are deferred (matches pushin_weight Q2-deferred decision).

## Why classify_post stayed put (U2)

`classify_post` is the pre-existing per-brand `(post_type, sentiment)`
classifier shipped at the U9 / migration 019 boundary. It writes
to `posts_brands_signals` exactly as `classify_pragmatics_full`
does, so the two paths converge at the storage layer. The
post-fetch pipeline replaces its inline calls with
`classify_pragmatics_full` to also emit the `discourse_role` and
the two `*_nationalism` prongs.

`classify_post` continues to be called from `_ingest_quote_tweets`
and `_attribute_call_items` for the brand-attribution pre-classify
path that doesn't have the discourse / nationalism prongs in scope.

## Fail-soft contract

A single post's translation, classification, or discourse/nationalism
failure never aborts the cycle. Carried from
`x_monitor/translator.py:25-27` and item 6b of the source plan.

Per-stage counters surface in the cycle summary:

- `n_classified` — kept posts where `classify_pragmatics_full` returned rows
- `n_translated` — kept posts with `text_en` / `text_zh_cn` populated
- `n_discourse` — kept posts with at least one `posts_brands_discourse` row
- `n_nationalism` — kept posts with both `china_nationalism` and
  `us_nationalism` populated (not NULL)
- `phase_timings_sec` — per-stage wall-clock from the cycle run

The smoketest runner prints all of these and surfaces the error
count per stage.

## See also

- `docs/plans/2026-07-02-002-feat-streamlined-post-fetch-pipeline-plan.md`
  — the originating plan
- `docs/research/2026-06-26-v2-x-cn-pragmatics-translation-prompts-en.md`
  — research backing the F0–F3 friction levels and the 9-way
  `discourse_role` taxonomy
- `x_monitor/store.py::Store.bulk_insert_post_brand_discourse` —
  the bulk write API
- `x_monitor/store.py::Store.get_post_brand_discourse_for_post` —
  the per-post read API (TEXT-keyed join-back)
- `scripts/post_fetch_smoketest.py` — the one-cycle smoketest runner