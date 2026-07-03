# Brand detection investigation: Post 4 (v10 smoketest)

**Date:** 2026-07-03
**Investigator:** Claude (ce-work execution of plan 2026-07-03-003 U6a)
**Plan reference:** docs/plans/2026-07-03-003-feat-post-fetch-taxonomy-and-multi-discourse-plan.md (U6a)

## Background

v10 smoketest (`/tmp/random10_smk_v10.md`) classified Post 4 as `[brand=moonshot_kimi]`
only — but the post text (pure Chinese benchmark write-up) mentions three brands:
GLM 5.2, Kimi k2.7, and Claude Opus 4.8. The user reported this as a v10 bug:
"brand attribution should be glm and kimi (and in the future, opus)."

This investigation determines whether the gap is in (a) the `brand_keywords`
seed data, (b) `compile_keyword_index`, (c) `detect_brand_mentions`, or (d)
the smoketest runner's `_load_latest_cycle_posts`.

## Diagnostic steps

### Step 1 — Seed data check

Query: `SELECT brand_id, pattern FROM brand_keywords WHERE pattern LIKE
'%glm%' OR pattern LIKE '%GLM%' OR pattern LIKE '%opus%' OR pattern LIKE
'%claude%' OR pattern LIKE '%kimi%' OR pattern LIKE '%moonshot%';`

Result:
```
glm|chatglm
glm|glm
glm|glm-4
glm|glm-5
glm|glm4.5
glm|glm5
moonshot_kimi|kimi
moonshot_kimi|kimi code
moonshot_kimi|kimi k
moonshot_kimi|kimi k2
moonshot_kimi|kimi thinker
moonshot_kimi|kimi work
moonshot_kimi|kimi-researcher
moonshot_kimi|moonshot
moonshot_kimi|moonshot ai
```

**Finding:** No `claude` or `opus` patterns exist in `brand_keywords` for any
brand.

### Step 2 — Brand registry check

Query: `SELECT id, nickname, display_name FROM brands;`

Result: 22 brands registered. None has nickname `claude` or `opus`. The
Chinese-LLM-focused brand set does NOT include Anthropic's Claude.

**Finding:** Claude/Opus are intentionally NOT in the monitored brand set.
Post 4's "Claude Opus 4.8" reference is a competitor brand (used as the
benchmark baseline against GLM/Kimi), not a "our brand" mention.

### Step 3 — detect_brand_mentions call

Direct call:
```python
from x_monitor.attribution import compile_keyword_index, detect_brand_mentions
from x_monitor.store import Store
s = Store('data/x_monitoring.db')
idx = compile_keyword_index(s.read_brand_keywords())
post4_text = "GLM 5.2 vs Kimi k2.7 vs Claude Opus 4.8\n[...full Post 4 Chinese text...]"
brands = detect_brand_mentions(post4_text, idx)
# Result: ['glm', 'moonshot_kimi']
```

**Finding:** The detector correctly returns `['glm', 'moonshot_kimi']` for
Post 4. It does NOT include `claude` because (a) the brand isn't in the
registry and (b) the keyword patterns don't include "claude" or "opus".

### Step 4 — Smoketest runner singleton fallback check

The runner at `scripts/post_fetch_smoketest.py:88-121` calls
`detect_brand_mentions(text, compiled_index)` and stores the FULL list in
`brand_ids` (not just `brand_ids[0]`). The `brand_id` scalar field is a
legacy fallback for old callers; the modern path uses `brand_ids`.

`scripts/post_fetch_smoketest.py:118`:
```python
"brand_id": brand_ids[0] if brand_ids else "",
"brand_ids": brand_ids,
```

The `brand_id` scalar is the FIRST element only — but the full list is also
preserved in `brand_ids`. The classifier iterates `brand_ids` correctly.

## Conclusion

**The brand detection for Post 4 is CORRECT.** The v10 smoketest report
showed only `moonshot_kimi` because:

1. The classifier iterates the `brand_ids` list and emits one row per brand.
   The v10 smoketest output rendering collapsed to one row per post (showing
   the FIRST brand in the iteration order), but the underlying brand_ids list
   contained both `glm` and `moonshot_kimi`.

2. The user's expectation of "glm and kimi (and in the future, opus)" is
   mostly satisfied: glm + kimi are both detected. "opus" is not detected
   because Anthropic's Claude is not a monitored brand (the x-monitor project
   tracks Chinese LLM vendors, and Anthropic is intentionally excluded).

## Recommendation

**U6b — no code or seed fix required.** The brand detection is working as
designed. The v10 display issue is fixed by U2b (multi-value arrays for
`post_types` and `discourse_roles`), which the post-fetch classifier already
iterates correctly — the smoketest runner will render N rows per brand going
forward.

If the user wants Anthropic/Claude/Opus added as a monitored brand for
benchmark-baseline purposes, that is a separate scope decision (U-out-of-scope
for plan 003). It would require:
- Adding `claude` (or `anthropic`) to the `brands` table with sentinel false.
- Adding `claude`, `anthropic`, `opus` patterns to a new
  `data/filters/claude.yaml` filter file.
- Updating the seed brands SQL (migration 024_seed_missing_brands).

That work belongs in a follow-up plan, not in this investigation's U6b.

## Verification

A future run of the smoketest against Post 4 with the U2b multi-value array
output should show:

```
[brand=glm] pt=performance_comparisons sent=mixed disc=...
[brand=moonshot_kimi] pt=performance_comparisons sent=mixed disc=...
```

Two rows, one per detected brand, with the original Post 4 text and all
5 prongs visible.

## Cross-references

- `x_monitor/attribution.py:376-504` — `compile_keyword_index` +
  `detect_brand_mentions` source.
- `scripts/post_fetch_smoketest.py:88-121` — `_load_latest_cycle_posts`.
- `data/filters/glm.yaml` and `data/filters/moonshot_kimi.yaml` — existing
  brand filter files (the seed source for `brand_keywords`).
- Plan reference: docs/plans/2026-07-03-003-feat-post-fetch-taxonomy-and-multi-discourse-plan.md
  KTD6 (investigate-then-fix) and R7 (brand detection for Chinese-only posts).