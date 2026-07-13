---
title: Smoketest review actions — renderer cleanup, codebase/DB fixes, v13 prompt calibration
date: 2026-07-08
type: feat
status: ready
product_contract_source: ce-plan-bootstrap
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
execution: code
---

# Context

Triaging review of the smoketest run (`x-monitoring/tests/classifier_tests/smoketest_latest_n_20posts.txt` vs the operator-annotated copy) surfaced 14 findings across 3 buckets:

- **Bucket 1:** 4 smoketest-renderer / runner-side issues.
- **Bucket 2:** 5 codebase/DB changes (incl. 2 new discourse values requiring migration + parser + prompt legend).
- **Bucket 3:** 5 prompt calibration issues for the next classifier calibration pass (v13, sibling of `2026-07-06-001-feat-v12-classifier-calibration-plan.md`).

The triaging scratchpad (`x-monitoring/tests/classifier_tests/2026-07-07-latest-n-20posts-review.md`) is reorganized into 3 sibling implementation units in this plan; the scratchpad can be archived when all units land.

**Important DB-fact (verified live, 2026-07-08):** `posts_brands_signals.PRIMARY KEY (post_id, brand_id, post_type_key)` — **`post_type_key` is stored per `(post_id, brand_id)`**, NOT per `post_id`. The 1.1 wording in the triaging doc ("when a single brand carries the post, the per-brand `post_types=` line is redundant") is **incorrect at the schema layer**. The renderer should keep the per-brand `post_types=` block as the source of truth and decide whether the `post:`-level `types=` is a redundant roll-up or a deliberate operator-visible summary. U1 captures the resolution.

# Files to modify

| Path | Change |
|---|---|
| `x-monitoring/scripts/post_fetch_smoketest.py` | U1: renderer cleanup (1.1, 1.2, 1.4-signal). |
| `x-monitoring/x_monitor/store.py` | U1: `_load_latest_n_posts` includes `in_reply_to_user_id`, `quoted_status_id`. |
| `x-monitoring/tests/test_post_fetch_smoketest_latest_n.py` | U1: renderer regression tests. |
| `x-monitoring/x_monitor/migrations/033_unattributed_taxonomy.sql` | U2 (2.1): rename `_unattributed` to `_unattributed_all`, add `_unattributed_us`, `_unattributed_china`. |
| `x-monitoring/x_monitor/migrations/034_add_nerfing_and_analysis_discourse.sql` | U2 (2.4+2.5): two new discourse rows. |
| `x-monitoring/tests/test_migration_033_unattributed_taxonomy.py` | U2: row-count and idempotency for migrations 033 + 034. |
| `x-monitor/attribution.py` | U2: `_VALID_DISCOURSE` gains `nerfing` and `analysis`; 2.3 wires the classifier for no-brand posts. |
| `x-monitor/translator.py` | U2 (2.2 root cause) — once diagnostic identifies upstream, post-fetch pipeline, or translator itself. |
| `x-monitoring/x_monitor/prompts/build_pragmatics_full_prompt.py` | U3: v13 prompt rewrite (3.3, 3.4, 3.5, 3.6 + 2.4 / 2.5 legend additions). |
| `x-monitoring/tests/classifier_tests/v13_fixture.jsonl` | U3: regression fixture covering new worked examples. |
| `x-monitoring/docs/reference/lookup-tables.md` | U2: add `nerfing`, `analysis` rows to `discourse_keys` table. |

# Implementation

## U1. Smoketest renderer cleanup (Bucket 1)

**Goal.** Tighten the smoketest output so it (a) reflects the per-brand nature of `post_type_key` correctly per the live schema, (b) shows reply/quoted-post context, and (c) annotates translation failures. This is one commit, all renderer-side — the Bucket 1 items are deliberately small.

**Requirements.** Schema is verified live — `posts_brands_signals.PRIMARY KEY (post_id, brand_id, post_type_key)` confirms `post_type_key` is per `(post_id, brand_id)`. The renderer must therefore:

1. The `post:` block carries **no `types=` line under any condition**. `post_type` lives only under `brand_mentions: <brand>` (per-brand, per the schema).
2. Always emit per-brand `post_types=` blocks (matches `posts_brands_signals.PRIMARY KEY (post_id, brand_id, post_type_key)`).
3. For zero-brand posts (pre-U2), render `post: brand_mentions: (none)` with no `types=` and no per-brand block. After U2 lands, the synthetic `_unattributed_all` block fills this slot.
4. Render an `in_reply_to:` line when `in_reply_to_user_id` / `quoted_status_id` are populated.
5. Render a `lang=` and `translation_status=` line on every post so a silent translator no-op on German / French / Korean is visible in smoketest artifacts.

**Dependencies.** None.

**Files.**
- `x-monitoring/scripts/post_fetch_smoketest.py` (`_render_sample_posts`, `_load_latest_n_posts`).
- `x-monitoring/x_monitor/store.py` (`Store.read_recent_posts` — extend the SELECT to include `in_reply_to_user_id`, `quoted_status_id`, `quoted_text` if available).
- `x-monitoring/tests/test_post_fetch_smoketest_latest_n.py` — extend existing 8-test file; add new tests for renderer output (test files next to existing ones, not a new file).

**Approach.**

**1.1 (`post_types` belongs to brands, not the post parent):** the schema confirms it — `posts_brands_signals.PRIMARY KEY (post_id, brand_id, post_type_key)` (verified live 2026-07-08) — `post_type` is stored per `(post_id, brand_id)`, NOT per `post_id`. The renderer therefore:

- **Always** emits the per-brand `post_types=` block (matches schema).
- **Never** emits a `types=` line under the `post:` parent. There is no "post-level post_type" in the data; what the operator sees came from the per-brand row.
- The triaging scratchpad's 1.1 wording ("when a single brand carries the post, the per-brand `post_types=` line is redundant") was inverted at the source. The redundancy the operator actually saw was the `post: types=` roll-up, which this change deletes entirely.

Edge case (no detected brands, pre-U2): emit `post: brand_mentions: (none)` with no `types=` line and no per-brand block. After U2 / 2.3 lands, this slot is filled by the synthetic `_unattributed_all` brand block, which carries the `post_types=` per-brand the schema requires.

**1.2 (in_reply_to):** if `in_reply_to_user_id` is set, look up the corresponding `author_handle` and tweet_id in the `accounts` + `posts` tables (a new `Store.get_post_handle(tweet_id)` lookup) and render:

```
in_reply_to: @<handle>/status/<tweet_id>
```

If the replied-to post is in our `posts` table but the account isn't, render with just the tweet_id. If `quoted_status_id` is set, render a similar `quote: @<handle>/status/<tweet_id>` line below `in_reply_to:`.

**1.3 (synthetic `_unattributed_*` block):** do NOT implement in U1 — that's a classifier-wiring change (covered by 2.3) plus a migration (2.1). Without both, the renderer would emit fabricated data. Strike 1.3 from this unit; it lands together with 2.1 + 2.3.

**1.4 (language/translation visibility):** always render:

```
lang:         <lang_detected>
translation:  <ok|skipped:noop|skipped:unknown-lang|failed>
```

The `translation` field reads from the translator's return shape (today `_run_pipeline` returns `text_en` / `literal_zh` — extend with a `translation_status` field that's either `ok`, `skipped:noop`, `skipped:unknown-lang:<code>`, or `failed`). U1 surfaces the signal; U2 (2.2) fixes the underlying bug for German / French / Korean.

**Patterns to follow.** The v12 calibration's hierarchical renderer pattern (`post:` group + per-brand block under `brand_mentions:`). Look at `scripts/post_fetch_smoketest.py:_render_sample_posts` (around line 284) before changing the layout.

**Test scenarios.**

| Category | Test |
|---|---|
| Happy path | Single-brand post: `post:` block has NO `types=` line; only the per-brand block carries `post_types=...`. |
| Happy path | Multi-brand post: each per-brand block carries its own `post_types=`; the `post:` block never carries `types=` regardless of overlap. |
| Happy path | Reply post with `in_reply_to_user_id` populated renders `in_reply_to: @<handle>/status/<id>`. |
| Happy path | Quoted post with `quoted_status_id` populated renders `quote: @<handle>/status/<id>`. |
| Happy path | English-source post renders `lang: en` and `translation: ok`. |
| Edge case | German-source post renders `lang: de` and `translation: skipped:unknown-lang:de` so the failure is visible. (The fix to the underlying translator is U2.2; U1 only surfaces the signal.) |
| Edge case | `author_handle=NULL` post renders the URL with `(no handle)` placeholder — preserves the v12 fallback. |
| Edge case | Zero-brand post renders `post: brand_mentions: (none)` with **no** `types=` line and **no** per-brand block. (Pre-U2 behavior — U2 fills this with the synthetic `_unattributed_all` block.) |
| Error path | `in_reply_to_user_id` points at an unknown / deleted post — render `in_reply_to: <unknown>/status/<id>` and continue; do NOT raise. |

**Verification.** Existing `tests/test_post_fetch_smoketest_latest_n.py` (8 tests) still pass; the new renderer tests pass; a manual `--source=latest-n --latest=5` run shows `lang=`, `translation=`, and `in_reply_to=` lines in the output.

---

## U2. Codebase / DB fixes (Bucket 2)

**Goal.** Land the 5 codebase/DB changes: the unattributed taxonomy (2.1), a diagnostic step + fix for the German-translation bug (2.2), classifier wiring for no-brand posts (2.3), and the two new discourse values `nerfing` + `analysis` (2.4 + 2.5). U3 will share the prompt-rewrite work for 2.4 / 2.5 — U2 only lands the data + parser side; U3 lands the prompt side.

**Requirements.**

- 2.1: a single migration that consolidates the `_unattributed` sentinel into three categorical rows.
- 2.2: root-cause the German failure before patching.
- 2.3: classifier runs even for `brand_ids == []`, with the result attached to a synthetic `_unattributed_all` brand row.
- 2.4 + 2.5: two new discourse rows; `_VALID_DISCOURSE` gained. **The prompt legends are U3 — see U3's "2.4 / 2.5 prompt impact" block for the prompt-side work.**

**Dependencies.** U1 unblocks 2.4 / 2.5's testing but isn't a strict prerequisite.

**Files.**
- `x-monitoring/x_monitor/migrations/033_unattributed_taxonomy.sql` — NEW.
- `x-monitoring/x_monitor/migrations/034_add_nerfing_and_analysis_discourse.sql` — NEW.
- `x-monitor/attribution.py` — `_VALID_DISCOURSE` add 2 values; no-brand classifier invocation.
- `x-monitor/translator.py` — patch 2.2 root cause.
- `x-monitor/store.py` — store-side helpers for the no-brand classifier attachment (if option (a) below is chosen).
- `x-monitoring/tests/test_migration_033_unattributed_taxonomy.py` — NEW (covers both 033 + 034).
- `docs/reference/lookup-tables.md` — add `nerfing`, `analysis` rows.

**Approach.**

**2.1 (unattributed taxonomy):** migration that

1. If the existing `_unattributed` brand nickname exists, rename it to `_unattributed_all` (UPDATE; PKs are surrogate INTEGER ids, so child FK refs are preserved).
2. INSERT OR IGNORE two new brand rows: `_unattributed_us`, `_unattributed_china`.
3. Brand-keyword detector (`compile_keyword_index`) does NOT need to match these — they are synthetic. They do appear in the `brands` table so the brand-attribution layer can attach the no-brand classification to them (per 2.3).

**2.2 (German translation diagnostic):**

Step 1 — diagnostic query:

```sql
-- on the offending German post (tweet_id from the source diff)
SELECT tweet_id, lang_detected, text_en, literal_zh
  FROM posts
 WHERE text LIKE 'Anthropics neue KI-Modelle%'
 LIMIT 5;
```

Step 2 — read three branches:
- `lang_detected = 'de'` and `text_en = text` → translator is no-op'ing on `de`. Fix is in `x_monitor/translator.py` to handle `de` (and likely `fr`, `ko`, `ja` too — small set).
- `lang_detected = 'en'` → upstream lang detection bug in the post-fetch pipeline (TwitterAPI.io response is being mis-keyed). Fix is in `x_monitor/store.py` or `x_monitor/api_response.py` (whichever writes the lang field).
- `lang_detected IS NULL` → pipeline never sets lang for non-CN / non-EN sources. Fix is `x_monitor/api_response.py`.

Step 3 — once the branch is identified, ship the fix as a small follow-up patch in the same U2 commit. The diagnostic step is **blocking** for the fix; without it the fix is guesswork.

**2.3 (classifier wiring for no-brand posts):**

The user can pick option (a) or (b); the doc leaves this open. **Recommendation: option (a).** `_run_pipeline` always invokes the classifier; the per-brand loop attaches the classifier output to a synthetic `_unattributed_all` brand row. This keeps the smoketest output uniform (per-brand block format) and matches the Bucket 1 / Bucket 2 split — 1.3 (the renderer) just renders the synthetic block; the data side is 2.3. The doc and tests treat them as one user-facing feature.

**2.4 + 2.5 (discourse values):** single migration 034 that adds two rows to `discourse_keys`:

| key       | display_name      | definition (used in `role_labels`)                                                          |
|-----------|-------------------|---------------------------------------------------------------------------------------------|
| `nerfing` | nerfing accusation | "post accuses a model of being deliberately cap'd, downgraded, or held back"                |
| `analysis`| analysis           | "data-driven, multi-model, dispassionate comparison; often has charts/tables/citations"    |

`_VALID_DISCOURSE` in `attribution.py` gains the two entries; the parser side accepts them. Prompt-side additions are deferred to U3 (the v13 calibration) but the parser change makes the smoketest artifact display them correctly even before the prompt rewrite.

**Test scenarios.**

| Category | Test |
|---|---|
| Happy path | Migration 033 lands: `_unattributed_all` row exists (renamed from `_unattributed` if pre-existing); `_unattributed_us` and `_unattributed_china` rows present. |
| Happy path | Migration 034 adds 2 rows to `discourse_keys`; `_VALID_DISCOURSE` accepts them; parser does not drop them. |
| Happy path | No-brand post runs `_run_pipeline`; the rendered output carries a `_unattributed_all` brand block with non-empty classification. |
| Edge case | Pre-existing `_unattributed` brand is gone after 033 (renamed); child `brands_companies` rows reference the renamed brand's id (FK still valid because the id didn't change). |
| Edge case | 2.2 diagnostic: each branch of the diagnostic (`lang_detected=de|en|NULL`) is exercised by a synthetic post; the chosen branch is patched and verified to translate / lang-detect correctly afterward. |
| Error path | Re-apply 033: idempotent (rename is a no-op after first apply; INSERT OR IGNORE no-ops for the two new rows). |
| Error path | A pre-existing post with `lang_detected=de` and untranslated `text_en` renders `translation: skipped:unknown-lang:de` after the U1 renderer fix; after the 2.2 patch, it renders `translation: ok`. |

**Verification.** Migration-ledger version reaches 33 + 34. Both new test files green. Manual: a fresh `--source=latest-n --latest=20` run after U1 + U2 show clean per-brand attribution, no `_unattributed_*` orphans, and German / French / Korean posts translated cleanly.

---

## U3. v13 prompt calibration (Bucket 3 + 2.4 / 2.5 prompt impact)

**Goal.** Bundle all Bucket 3 prompt calibrations + the prompt-impact blocks from 2.4 / 2.5 into a single v13 calibration plan, sibling of `2026-07-06-001-feat-v12-classifier-calibration-plan.md`. This is the v13 sibling that the existing triaging doc identifies as the home for 3.x items.

**Requirements.**

3.3 — tighten `event_announcement` so it's bounded-duration events (conferences, meetups, livestreams), not model releases.

3.4 — tighten `advertising-marketing` so multi-model listicles are NOT labeled as `advertising-marketing`. They should be `analysis` (which lands in U2 as a discourse value).

3.5 — `hands_on_usage` and `performance_comparisons` should both fire if appropriate. Rule 12 is too eager to keep `performance_comparisons` off the post_type list when the operator wants both.

3.6 — Rule 16 (nationalism) should NOT fire on plain vendor critique unless the post frames a US-China relationship. Worked example required.

3.7 — verify current `data/queries/*.yaml` would catch the 6 historical no-brand-posts going forward (forward-looking check, not a retroactive fix).

2.4 prompt impact (`nerfing`) — add legend entry + worked example + counter-example vs. `fud` / `distillation_accusation`.

2.5 prompt impact (`analysis`) — add legend entry, **rewrite** `genuine_hype` so the LLM picks the right bucket, tighten `advertising-marketing` (per 3.4), and add 3 worked examples (leaderboard → analysis, "amazing!" → genuine_hype, listicle → analysis).

**Dependencies.** U2 lands `_VALID_DISCOURSE` first; U3 ships the matching prompt legend. U2 + U3 land on different commits but the same release.

**Files.**
- `x_monitor/prompts/build_pragmatics_full_prompt.py` (the actual prompt builder).
- `x_monitor/attribution.py` — Rule 12 + Rule 16 prompt-text mutations (if the rules live next to attribution rather than the prompt builder).
- `x-monitoring/tests/classifier_tests/v13_fixture.jsonl` — regression fixture.
- `data/queries/*.yaml` — 3.7 verification, no edits unless an obvious gap surfaces.

**Approach.** Write a fixture of ~10 synthetic posts covering each new worked example and counter-example (one per rule tightening, plus the 3 `analysis` / `genuine_hype` / `advertising-marketing` examples from 2.5). Update `build_pragmatics_full_prompt.py` to:

1. Add `nerfing` and `analysis` to the discourse legend with the wording from 2.4 / 2.5.
2. Rewrite the `genuine_hype` legend with the "praise WITHOUT data" rule.
3. Tighten `advertising-marketing` legend per 2.5 / 3.4.
4. Tighten `event_announcement` legend per 3.3.
5. Tighten Rule 12 (hands_on_usage vs performance_comparisons) per 3.5.
6. Tighten Rule 16 (nationalism scope) per 3.6.

**Test scenarios.**

| Category | Test |
|---|---|
| Happy path | Fixture post A ("Fable 5 was nerfed vs. Sonnet on purpose") classifies as `nerfing`, not `fud`. |
| Happy path | Fixture post B (leaderboard + reasoning) classifies as `analysis`, not `genuine_hype`. |
| Happy path | Fixture post C ("5 best LLMs of 2026, ranked") classifies as `analysis`, not `advertising-marketing`. |
| Happy path | Fixture post D (concrete product release "we shipped 2.4") classifies as `buzz_releases`, not `event_announcement`. |
| Happy path | Fixture post E ("I tried both, here's my comparison") classifies as `hands_on_usage` + `performance_comparisons` (not just one). |
| Happy path | Fixture post F (vendor critique, no US-China framing) classifies `us=none`, not `constructive_critical`. |
| Edge case | Fixture post G (vendor critique WITH US-China framing) classifies `us=constructive_critical` (the boundary case the worked example teaches). |
| Forward-looking check (3.7) | For each of the 6 historical no-brand-posts, the current YAML query would catch them — report written to `tests/classifier_tests/2026-07-08-yaml-coverage-check.md`. |

**Verification.**

- All v12 calibration rules 16-19 still hold (regression check via existing `/tmp/v12_fixture.jsonl` and the new v13 fixture).
- `tests/test_v13_prompt_calibration.py` passes the worked-example coverage.
- A `--source=latest-n --latest=20` run after U1 + U2 + U3 shows: zero silently-dropped `nerfing` / `analysis` discourse values, fewer `event_announcement` / `advertising-marketing` misclassifications on a manual eyeball pass.

---

## Definition of Done

- [ ] U1 renderer cleanup landed; 1.1 respects per-brand schema, 1.2 renders reply/quote context, 1.4 shows translation status. 1.3 deferred to U2.
- [ ] U2 changes landed:
  - Migration 033 (`_unattributed` → `_unattributed_all` + 2 new rows) applied to live DB.
  - Migration 034 (discourse `nerfing`, `analysis`) applied to live DB.
  - 2.2 German-translation diagnostic run; root-cause identified; patch landed and tested.
  - 2.3 classifier runs for no-brand posts; output attached to `_unattributed_all`.
- [ ] U3 v13 prompt calibration landed; new fixture passes.
- [ ] All three units' tests green.
- [ ] The triaging scratchpad (`x-monitoring/tests/classifier_tests/2026-07-07-latest-n-20posts-review.md`) archived or deleted.

## Scope Boundaries

### Out of scope (deferred)
- Backfilling historical posts that were silently dropped by the parser before this plan (e.g. the 6 no-brand posts from 3.7). The plan is forward-looking; backfills are follow-up work.
- Adding `Llama` / `Mixtral` / `Mistral` as new brand rows. Already covered by migration 029 (commit c7b877f).
- Any other classifier-prompt rewrites that are not enumerated in 2.4 / 2.5 / 3.x.

### Explicit non-goals
- This plan does not redesign the brand-attribution layer; it only adds the unattributed taxonomy and makes the no-brand path emit classification.
- This plan does not change the translator's output shape beyond what 2.2's root-cause fix requires.
- This plan does not gate the v13 prompt calibration on a model-side change.

## Open Questions

1. **2.3 option (a) vs. (b)** — confirmed in the body of U2 as option (a) (synthetic `_unattributed_all` brand row). Operator can flip to (b) before U2 lands.
2. **2.2 which branch** — German-source post diagnostic must run first. The plan allocates this as a blocking-step before the fix; this is runtime discovery, not a planning-time decision.
3. **3.7 YAML file** — the operator has not identified which YAML is "the updated one." U3's verification step enumerates YAMLs by mtime / git log and asks the operator to confirm.

## Commits

This plan lands as **3 commits**, one per unit, in order U1 → U2 → U3. Each commit is independently testable.

```
feat(x-monitor): smoketest renderer cleanup — per-brand post_types, reply/quote context, translation status
feat(x-monitor): unattributed taxonomy + new discourse values + German-translation fix + no-brand classifier wiring
feat(x-monitor): v13 prompt calibration — nerfing/analysis legend, rewrite genuine_hype, tighten rules 12/16
```
