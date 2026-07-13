# Smoketest Review: latest-n 20 posts (2026-07-07)

**Source diff:**
```
smoketest_latest_n_20posts.txt      (clean run, this afternoon)
smoketest_latest_n_20posts copy.txt (your inline-annotated copy)
```

**Diff command:**
```bash
diff -u smoketest_latest_n_20posts.txt "smoketest_latest_n_20posts copy.txt"
```

The annotated copy has 18 inline `<<` comments. They're organized below into the three buckets you asked for. **Edit this file as you triage** — strike through items you've handled, add your own notes, regroup as needed. Anything that turns into a real fix should land as a separate commit / plan.

---

## Bucket 1: Fixes to smoketest (renderer / runner behavior)

These are issues with the smoketest *itself* — output formatting, layout, runtime behavior. Fix in `scripts/post_fetch_smoketest.py` or the renderer.

### 1.1 Redundant `post_types=` under brand_mentions
- **Source line:** 43
- **Issue:** `post_types=performance_comparisons` is printed under every brand block, but the same value is already under `post:` as `types=...`. When a single brand carries the post, the per-brand `post_types=` line is redundant.
- **Fix direction:** When the post has exactly 1 brand, drop the `post_types=` line from that brand's block (it's already in `post:`). When the post has multiple brands and one of them has a different `post_type`, keep the per-brand line.
- **File:** `x-monitoring/scripts/post_fetch_smoketest.py` (`_render_sample_posts`)

>> confirm that post_types belongs to post, and not to per-brand (as your wording suggests) -- query actual live db, not memory to answer this

### 1.2 Add `in_reply_to:` rendering for reply posts
- **Source line:** 59-62
- **Issue:** Post 4 (or whichever this is) is a reply (`@bridgemindai @algebraist22 哈哈，确实很容易。`). The smoketest shows the reply text but no signal that it's a reply, and the original replied-to post is missing.
- **Fix direction:** Render a `in_reply_to: @handle/status/<id>` line (or `↳ reply to ...`) when the post has `in_reply_to_user_id` and `quoted_status_id`. Pull from the `posts` table.
- **File:** `x-monitoring/scripts/post_fetch_smoketest.py` (`_render_sample_posts`) + ensure `_load_latest_n_posts` selects `in_reply_to_user_id` and `quoted_status_id`.

### 1.3 `_unattributed_*` synthetic brand block for no-brand posts
- **Source line:** 216-221
- **Issue:** When a post has no monitored brand, the renderer emits `brand_mentions: (none)`. The user wants a synthetic `_unattributed_all` block (with `sentiment=neutral`, `cls_discourse=genuine_hype`, `cn=none`, `us=none`) instead.
- **Note:** This is BOTH a smoketest fix AND a codebase change. The smoketest fix is the rendering; the codebase fix is wiring the classifier through to unattributed posts (see Bucket 2.1). Doing the rendering without the classifier invocation would show fake data.
- **File:** `x-monitoring/scripts/post_fetch_smoketest.py` + `x_monitor/attribution.py` (classifier wiring)

### 1.4 German-source language detection
- **Source line:** 116-117
- **Issue:** A German-language post (`Anthropics neue KI-Modelle: Fable 5, Opus 4.8 und Sonnet 5 im Vergleich`) has `text_en` = source (not translated) and `literal_zh` = source. The user marked both "didn't work" / "didn't work".
- **Note:** This is BOTH a smoketest rendering issue (no signal that translation failed) AND a real codebase bug (the translator isn't running for non-English / non-Chinese sources). The smoketest fix: add a `lang=` line or `translation_status=` marker. The codebase fix: investigate why German doesn't trigger translation. See Bucket 2.2.
- **File:** `x-monitoring/scripts/post_fetch_smoketest.py` (rendering) + `x_monitor/translator.py` (real fix)

---

## Bucket 2: Changes to actual codebase / DB

These need a real fix in the runner, classifier, translator, or schema. Bigger than a renderer tweak.

### 2.1 Rename `_unattributed` to `_unattributed_all` + add `_unattributed_us`, `_unattributed_china`
- **Source line:** 71-79
- **Issue:** The user wants a taxonomy of unattributed buckets so we can see *where* (which side of US-China) an unattributed post falls. Currently the code uses a single `_unattributed` sentinel.
- **Plan:** Migration that renames the existing `_unattributed` brand row to `_unattributed_all` (or adds `_unattributed_all` as new) and inserts two new rows `_unattributed_us` and `_unattributed_china`. The brand-keyword detector doesn't need to match these (they're catch-alls), but the classifier should be able to attach a brand to them so the per-brand row-build loop picks them up.
- **File:** new `x-monitoring/x_monitor/migrations/032_unattributed_taxonomy.sql` (or whatever next free number) + `x_monitor/attribution.py` (synthetic-brand handling)

### 2.2 German-source language detection / translation
- **Source line:** 116-117
- **Issue:** German post has `lang_detected=???` (probably `en` based on the user's frustration — the translator is noop'ing it). Need to investigate:
  1. What `lang_detected` is set to on this post in the DB.
  2. Whether the translator's noop_en path is firing (it shouldn't for German).
  3. Whether the lang detection upstream (TwitterAPI.io response, posts table) is being mis-set to `en`.
- **Plan:** Diagnostic query to check `lang_detected` distribution on the actual offending post. If `lang_detected=en` → bug is upstream (lang detection). If `lang_detected=de` → bug is in translator (it's not handling de). If `lang_detected=null` → bug is in the post-fetch pipeline.
- **File:** likely `x_monitor/translator.py` once root cause is found

### 2.3 Classifier should run for no-brand posts
- **Source line:** 216-221
- **Issue:** Currently `_run_pipeline` skips classification for posts with empty `brand_ids` (line 545-547 of `post_fetch_smoketest.py`). The user wants classification output even for no-brand posts, attached to the `_unattributed_all` block.
- **Plan:** Either (a) invoke the classifier with a synthetic `_unattributed_all` brand for no-brand posts, OR (b) emit a post-level (not brand-level) classification summary for no-brand posts. The user has to decide which. Option (a) keeps the smoketest output uniform.
- **File:** `x-monitoring/scripts/post_fetch_smoketest.py` + `x_monitor/attribution.py`

### 2.4 New discourse value: `nerfing` (moved from 3.1)
- **Source line:** 71-79
- **Issue:** The LLM emitted `nerfing` (model-nerfing accusations). The parser silently dropped it because `nerfing` is not in `_VALID_DISCOURSE`.
- **Plan:** Migration adds the row to `discourse_keys` (a new INSERT OR IGNORE block) AND a code change in `attribution.py` adds `'nerfing'` to `_VALID_DISCOURSE`. Then the prompt legend in `build_pragmatics_full_prompt` needs the entry so the LLM knows to emit it. Three layers in lockstep.
- **Definition (operator-supplied):** posts accusing a model of being deliberately downgraded / cap'd / held back (e.g., "Fable 5 was nerfed vs. Sonnet on purpose"). Sits next to `fud` (which spreads doom) and `distillation_accusation` (which attacks lineage) — `nerfing` is specifically about capability gating.
- **Prompt impact (must-do, not just legend-add):** without a worked example AND an explicit "nerfing ≠ fud, nerfing ≠ general frustration" boundary, the LLM will conflate `nerfing` with `fud` or roll it into `distillation_accusation`. The v13 plan must include:
  1. A new entry in the discourse-legend block (the literal "nerfing = capability gating accusation" sentence).
  2. A worked example (post X labeled `nerfing`, NOT `fud`).
  3. A counter-example (similar post Y labeled `fud`, NOT `nerfing`).
  4. A reference back to whichever rule currently covers negativity-about-capabilities — that rule probably needs tightening to exclude nerfing-shaped content.
- **File:** new `x-monitoring/x_monitor/migrations/033_add_nerfing_discourse.sql` + `x_monitor/attribution.py` (constant + prompt legend + worked example) + `build_pragmatics_full_prompt` (legend + 2 worked examples).
- **Five-layer checklist** (mirror docs/reference/lookup-tables.md "How to add a new value"): migration, `_VALID_*` constant, prompt legend, test fixture, this doc + `docs/reference/lookup-tables.md` — BUT the **prompt legend for an existing value also needs review** for overlap; see prompt impact above.

### 2.5 New discourse value: `analysis` (moved from 3.2)
- **Source line:** 493, 499, 505 (three posts landed on `analysis`)
- **Issue:** The LLM emitted `analysis` (balanced, data-driven, dispassionate comparison) three times. Not in `_VALID_DISCOURSE`.
- **Plan:** Same as 2.4 — migration + `_VALID_DISCOURSE` + prompt legend. Bundle with 2.4 in a single migration if practical.
- **Definition (operator-supplied):** posts that describe themselves — or are functionally — an "analysis" piece: data-driven, multi-model, dispassionate, often with charts/tables/citations. Distinct from `genuine_hype` (positive valence), `fud` (negative valence), and `performance_comparisons` (which is a **post_type** value, not a discourse value — see 3.5). A single post can carry `analysis` discourse + `performance_comparisons` post_type without conflict.
- **Prompt impact (operator-flagged, must-do):** the v13 plan must include a **rewrite of the `genuine_hype` legend and (likely) `advertising-marketing`** so the LLM picks the right bucket. Without this rewrite, the LLM will keep defaulting to `genuine_hype` (or `advertising-marketing`, per 3.4) for posts that are actually `analysis`. Concretely:
  1. **Rewrite `genuine_hype` legend** to make room for `analysis`: make explicit that `genuine_hype` requires **praise without data** (or with data the LLM itself has not enumerated). A post that ranks, benchmarks, compares, or "here are the numbers" is `analysis`, not `genuine_hype`.
  2. **Tighten `advertising-marketing`** (also covered in 3.4) so it excludes "listicle / round-up / comparison" posts (those are `analysis`).
  3. Add the `analysis` legend entry: "data-driven, multi-model, dispassionate comparison. Often has charts/tables/citations. NOT a verdict about which model is best — that comes through sentiment."
  4. Worked examples:
     - Post A: leaderboard screenshot → `analysis` (NOT `genuine_hype`).
     - Post B: "Kimi K2.7 is amazing!" → `genuine_hype` (NOT `analysis`).
     - Post C: "5 best LLMs of 2026, ranked" → `analysis` (NOT `advertising-marketing`).
- **File:** same as 2.4 (combined migration) + `build_pragmatics_full_prompt` (genuine_hype legend rewrite + analysis legend + 3 worked examples).

---

## Bucket 3: Prompt calibrations needed

These need changes to the classifier prompt rules or worked examples. Bundle into a v13 plan (sibling to `2026-07-06-001-feat-v12-classifier-calibration-plan.md`).

### ~~3.1 Add new discourse: `nerfing`~~ moved to **2.4**

### ~~3.2 Add new discourse: `analysis`~~ moved to **2.5**

### 3.3 Tighten `event_announcement` definition
- **Source line:** 135
- **Issue:** The user says: "events (both live and online) have definite end dates." A model release is a release (`buzz_releases` or `event_announcement`), not an event in the conference/livestream sense. Currently the LLM is calling product releases `event_announcement`.
- **Action:** Update the prompt legend for `event_announcement` to be explicit: conferences, meetups, livestreams with bounded duration. Product releases should be `buzz_releases` (if hype) or stay in `event_announcement` only if the LLM considers the launch as a one-time "moment" (e.g. "we just launched K2.7 — live now").

### 3.4 Tighten `advertising-marketing` definition
- **Source line:** 499, 505
- **Issue:** Posts that "mention multiple models and treat them equally" should NOT be `advertising-marketing`. The LLM is misclassifying neutral multi-model comparison posts.
- **Action:** Update the prompt legend: `advertising-marketing` is for posts that promote a specific model with a CTA. Multi-model neutral comparisons should be `analysis` (if it lands in 3.2) or `genuine_hype` (if positive coverage).

### 3.5 Detect both `hands_on_usage` and `performance_comparisons` if appropriate
- **Source line:** 64
- **Issue:** A "I tried it, here's what I found" post was emitted as only `types=hands_on_usage. But given the tone of the post, it is also , `performance_comparisons`, which should be added
- **Action:** Add a worked example distinguishing the two. Rule 12 (or whatever covers `hands_on_usage`) should not exclude others.

### 3.6 Rule 16 may need tightening
- **Source line:** 71-79
- **Issue:** A post critiquing a US vendor product got `us=constructive_criticism`. The user manually overrode this to `const_critic` (= `constructive_critical` row id from `nationalism_keys`) — the operator's judgment is that this is constructive-criticism sentiment, but **not** nationalism sentiment, because the post has no US-China relational framing.
- **Action:** Add a worked example for rule 16 showing: "constructive criticism of a US vendor's product" is NOT nationalism unless the post also frames the US-China relationship. Current rule 16's prompt is too eager to read vendor critique as nationalism.
- **Note:** the LLM misspelled the canonical value (`constructive_criticism` instead of `constructive_critical`) — separate from the over-eagerness issue but worth noting. The parser silently coerced/dropped it (constructive_criticism is not in `_VALID_NATIONALISM`; the canonical key is `constructive_critical`). Worth confirming whether `constructive_criticism` ever reaches the parser or gets pre-normalized in the prompt legend.

### 3.7 YAML filter — would the current YAML catch these posts going forward?
- **Source lines:** 557, 587, 596, 607, 620, 629, 638 (six "our updated yaml should filter this out" comments)
- **Issue:** These six posts were collected by the TwitterAPI search query **before** the YAML filter config was set up; that's why they're in the smoketest. The question is no longer "did the YAML filter fail in the past" (it didn't exist) — it's **"if these same posts arrived today, would the current YAML's search query filter each one out?"**
- **Action:** Forward-looking check, not a retroactive bug fix:
  1. Identify the current YAML config (the most recently edited `data/queries/*.yaml` — check git log on those files).
  2. For each of the 6 posts, take its `text` and run it against the YAML query logic (most likely a substring / regex match against the brand keywords).
  3. Report per-post: "current YAML would have filtered / would NOT have filtered."
  4. For ones the YAML would not filter, flag them as candidates for tightening the query (or accept that they pass through by design).
- **File:** `data/queries/*.yaml` — depends on which YAML the operator is iterating on.

---

## How to triage

Strike through items you've handled (e.g. `~~1.1~~`). When you decide an item is a real fix:

- **Smoketest fixes (1.x):** roll them into a single `feat(x-monitor): smoketest renderer cleanup` commit.
- **Codebase/DB (2.x):** each is its own plan or migration. Most cleanly: 2.1 is a migration; 2.2 needs a diagnostic step first; 2.3 is a small code change in the runner.
- **Prompt calibrations (3.x):** bundle all into a single v13 plan (sibling to `2026-07-06-001-feat-v12-classifier-calibration-plan.md`). The 3.1 and 3.2 entries were moved to **2.4** (`nerfing`) and **2.5** (`analysis`); each carries an explicit "Prompt impact (must-do)" block listing what v13 must rewrite in `build_pragmatics_full_prompt` — for `analysis` that includes a **rewrite** of the `genuine_hype` legend (not just an additive entry) so the LLM routes into the right bucket.

When done triaging, this file can be deleted or archived.
