---
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ce-plan-bootstrap
title: Post-fetch smoketest quality pass + classifier prompt tuning
type: feat
date: 2026-07-04
status: ready
origin:
  - 2026-07-03 end-to-end smoketest runs at /tmp/smoketest_e2e_run.txt and /tmp/smoketest_e2e_full.txt
  - Plan at docs/plans/2026-07-03-003-feat-post-fetch-taxonomy-and-multi-discourse-plan.md (already shipped migrations 027 + 028 + classifier rewrite; the present plan picks up renderer / prompt / live-API / infra leftovers surfaced by e2e runs)
  - Plan2 at docs/plans/2026-07-02-002-feat-streamlined-post-fetch-pipeline-plan.md (U7 smoketest runner; renderer is what gets fixed here)
deepened: 2026-07-04
---

# Post-fetch smoketest quality pass + classifier prompt tuning

## Goal Capsule

Close seven renderer / prompt / infrastructure gaps surfaced by the first two end-to-end smoketest runs (2026-07-03): the renderer conflates two independent "discourse" fields, hardcodes `disc=uncategorized` for per-brand rows, and omits the post URL; the classifier defaults to `pt=hands_on_usage` and over-rates `sent=positive` for launch announcements and analytical posts; the smoketest's `--source=latest-cycle` ingests posts that have no monitored-brand attribution; the smoketest cannot exercise the live TwitterAPI.io fetch path; and the second e2e run lost all 10 translations to a transient proxy failure that the pipeline surfaced correctly but the report cannot diagnose. The output is one shipped `x-monitor smoketest` that produces URL-anchored, source-of-truth-honest output against either DB-resident or live-API posts, plus a more discriminative classifier prompt, plus a `translation_failure_breakdown` field on the report.

Primary actor: DevRel / marketing triage, plus the LaunchAgent operational gate.
Desired outcome: every smoketest run produces a report where the URL, translator-output, classifier-output, and timing breakdowns are individually verifiable, and where the classifier's per-brand label is what the LLM actually said — not a hardcoded placeholder.

Open blockers: none. All work is in `x-monitoring/`.

## Problem Frame

The two e2e smoketest runs (against the live `data/x_monitoring.db`, 10 posts each, real LLM calls via the minimax proxy) surfaced seven discrete issues. Each is small in isolation, but together they make the smoketest report noisy and the classifier systematically conservative:

1. **Smoketest renderer conflates two discourse fields.** The "discourse:" header is the translator's `discourse_role` (post-level pragmatic-axes output). The `disc=...` field on the `[brand=...]` line is *not* the same thing — it is a hardcoded `uncategorized` placeholder because the in-memory classifier payload from the smoketest path doesn't include `discourse_roles` in the rendered line. Looking at a row like `discourse: genuine_hype` followed by `[brand=moonshot_kimi] pt=hands_on_usage sent=positive disc=uncategorized`, the second "discourse" is meaningless.

2. **The sample header shows the tweet_id but not the URL.** Every post in the report is a real X / Twitter post; a reviewer triaging the sample has to copy-paste the tweet_id into x.com manually. Three seconds of avoidable friction per post.

3. **The classifier over-rates `sent=positive` for launch announcements and analytical posts.** Two specific failures from the e2e runs:
   - Post 5 ("Kimi K2.7 Code is generally available in GitHub Copilot" — 55 chars, one-line announcement) → `sent=positive` is generous; the post is informational.
   - Post 10 (long NVFP4 / Alibaba investment thesis) → `qwen sent=mixed` under-weights the explicit bullish framing; "the model is therefore strategically positive for BABA's cloud multiple" is a positive sentiment claim.
   - Post 6 (multi-brand state-of-the-market: "Kimi K2.7 Code climbed 20 spots to #138, Deepseek V4 Flash price dropped 8.2%") → `kimi sent=positive` (climbing) but `deepseek sent=neutral` (price drop) is asymmetric.

4. **The classifier defaults to `pt=hands_on_usage` for nearly every post.** Specific misses:
   - Post 5 (one-line launch announcement) should be `event_announcement` (new post_type added in migration 027, currently underused).
   - Post 8 ("LLM Drag Race" TTFT benchmark) should be `performance_comparisons`.
   - Post 1 (price/perf analytical piece) could legitimately be `feedback_questions` (four rhetorical questions) or `performance_comparisons`.
   The prompt's `event_announcement` and `advertising_marketing` entries are not getting the LLM's attention.

5. **The smoketest pulls unfiltered posts.** `--source=latest-cycle` is `ORDER BY fetched_at DESC LIMIT N` with no brand filter. Posts 7, 8, 9 in the second e2e run had no monitored-brand attribution; they got translated (wasting LLM quota) and then the classifier was skipped because `brand_ids=[]`. User selected **filter out no-brand posts** as the desired behavior — not the `no_brand` pseudo-brand path. The fix is in `_load_latest_cycle_posts`: skip posts with empty `brand_ids`.

6. **The smoketest cannot exercise the live TwitterAPI.io fetch path.** The two existing sources (`latest-cycle`, `fixture`) cover post-fetch stages but not the fetch stage itself. `TwitterApiClient.run_search()` is only reachable via `x-monitor run` (the main loop). There is no way to smoke-test "fetch → translate → classify" end-to-end without first running a full main loop and waiting for the fetch to populate the DB. A new `--source=api-query` should call `apify.run_search(query, max_results=N)` directly and feed the result into the same `_run_pipeline()` that `latest-cycle` uses.

7. **The second e2e run lost 10/10 translations to a transient proxy failure** (the first run's same input succeeded 10/10). The pipeline correctly surfaced the failures — `n_failed_translate=10`, an `=== ERRORS ===` block, and no rows written to the DB. But the report doesn't tell the user *why* the LLM call failed: no exception class, no retry-count, no proxy-status hint. The same code path that succeeded in run #1 failed 3 times in a row in run #2 (`_MAX_RETRIES=3` per `translator.py:160-182`). Diagnosing this from the report alone is impossible.

### Origin traceability

The seven issues are all surfaced in the same two artifacts:
- `/tmp/smoketest_e2e_run.txt` (first run, sample=5, 10/10 translations succeeded)
- `/tmp/smoketest_e2e_full.txt` (second run, sample=10, 10/10 translations failed)
- Live DB inspection at `data/x_monitoring.db` (migrations 027 + 028 confirmed applied; `posts_brands_signals` schema verified to be the new TEXT-natural-key layout).

## Requirements

**R1.** The smoketest renderer must surface the actual classifier `discourse_roles` per brand row, not a hardcoded `uncategorized` placeholder. The `discourse:` header at the top of each post block must be relabeled to make its source unambiguous (recommended: `trans_disc:` for the translator's `discourse_role` vs `cls_disc=` for the classifier's per-brand `discourse_roles`). The class-disc field must be omitted from the per-brand line when the in-memory classifier payload doesn't include it (no silent placeholder).

**R2.** Each post block in `=== SAMPLE POSTS ===` must include the full X / Twitter URL `https://x.com/<author_handle>/status/<tweet_id>`. `author_handle` is read from `posts.author_handle` (verified column exists in the live DB).

**R3.** Tighten the classifier prompt's sentiment rules so that:
- Launch announcements with no evaluative language (e.g., "X is generally available", "X launched today", "X shipped v3.2") → `sent=neutral`.
- Long analytical / investment posts with explicit positive framing ("strategically positive for BABA", "increasingly important as a strategic asset", "supports the multiple") → `sent=positive`.
- Multi-brand state-of-market posts that mix factual updates per brand → `sent=neutral` for each brand unless a specific positive/negative claim is made.
- Promotional posts with CTAs (the existing R8 rule from the 003 plan) → `sent=positive` *or* `sent=neutral` (marketer intent), not `sent=negative` — promotions aren't criticism.

**R4.** Tighten the classifier prompt's post-type disambiguation rules so that `event_announcement` is the default for one-line "X is generally available / Y launched" posts, and `performance_comparisons` is the default for any post mentioning TTFT / latency / benchmark / ranking / "vs" comparisons. Add a worked example in the prompt showing a launch announcement → `event_announcement` and a benchmark post → `performance_comparisons`.

**R5.** The smoketest's `--source=latest-cycle` must filter out posts with no monitored-brand attribution *before* they enter the pipeline. Filter applied in `_load_latest_cycle_posts` (scripts/post_fetch_smoketest.py:75-121). Posts with empty `brand_ids` after `detect_brand_mentions` are skipped. Report the count of skipped posts in the report header (e.g., `posts_with_no_brand_skipped: 3`).

**R6.** Add a new `--source=api-query` to the smoketest that calls `TwitterApiClient.run_search(query, max_results=N)` directly and feeds the result into `_run_pipeline()`. New args: `--query <advanced-search-string>`, `--since <YYYY-MM-DD>`, `--max-pages <int>`. The `TwitterApiClient` is constructed the same way `__main__.py:51` constructs it for the main loop. The new source is opt-in; default stays `--source=latest-cycle` so CI doesn't accidentally hit the live API. Document the live-API quota cost in the help text.

**R7.** The smoketest report must include a `translation_failure_breakdown` section when `n_failed_translate > 0`, showing per-tweet the exception class, retry count, and last error message. The `translate_batch_pragmatics` function in `x_monitor/translator.py` already raises the last exception after retries exhaust — that exception's `repr` (or its first 200 chars) needs to flow through to the report. This requires `translate_batch_pragmatics` to optionally return a `(rows, errors)` tuple, OR for the smoketest to wrap the call and capture exceptions per-tweet. The latter is simpler and avoids breaking the public API.

**R8.** (Informational, no code change) Document the `literal_zh` vs `text_zh_cn` distinction. `literal_zh` is the post-translator's "lossless with slang" output for X / Twitter posts; `text_zh_cn` is the registry-translator's "formal / named-entity-preserving" output used for brands, products, and other lookup tables. Both columns live in `posts` and are populated by different translator code paths. Add a comment in `x_monitor/translator.py` around the column naming and a short note in `docs/reference/translator-output.md` (new file).

## Key Technical Decisions

**KTD1. Renderer fix is "wire the actual classifier output through" + "rename for clarity" — not "remove the field."** The smoketest in-memory `classification_rows` is built in `_run_pipeline` (scripts/post_fetch_smoketest.py:325-328) by reading `cls["by_brand"]` and dropping every key except `brand_id` + `**prongs`. The `prongs` dict from `classify_pragmatics_full` contains `post_types`, `sentiment`, `discourse_roles`, `china_nationalism`, `us_nationalism`. The renderer at scripts/post_fetch_smoketest.py:187-201 just doesn't read `discourse_roles`. The fix is two lines: read `prongs.get("discourse_roles")` and emit it; relabel the post-level header from `discourse:` to `trans_disc:`. No data model change, no DB migration.

**KTD2. URL construction is a renderer concern, not a data model concern.** The `posts` table already has `author_handle` (verified in the live DB). The renderer reads it from the post dict that `_load_latest_cycle_posts` already returns. The `--source=api-query` path needs to thread `author_handle` through too — `apify.run_search` returns tweet objects that include `author_handle` (or `user.screen_name`); the smoketest adapter maps it once at the top of `_load_api_posts`. Format: `https://x.com/<handle>/status/<tweet_id>` (no trailing slash; verified against x.com canonical URL pattern).

**KTD3. Prompt tuning is in `build_pragmatics_full_prompt`, not a new prompt.** The existing prompt is the right place — it's already the merge point for the §5.1 contract, the R8 CTA rule, and the U9 multi-discourse rule. The new rules go in as additional bullets under "Rules:" (numbered 10, 11, 12 — extending the existing 1-9). One prompt file, one test file (`tests/test_classify_pragmatics_full_prompt.py`), no new fixtures needed because the existing tests cover the structure.

**KTD4. No-brand filter is a `_load_latest_cycle_posts` change, not a `--source` change.** The user picked "filter out no-brand posts" over the `no_brand` pseudo-brand path. The filter is a single early-return in `_load_latest_cycle_posts` after `detect_brand_mentions` returns. The skipped-post count is added to the report header so users know why `posts_seen: 7` when the DB has 10 rows. The `--source=api-query` path also gets the filter for free (same brand-keyword machinery), but `--source=fixture` stays as-is (the fixture author controls attribution).

**KTD5. Live API source is opt-in and runs in the same `_run_pipeline`.** The new `_load_api_posts(query, since, max_pages, max_results)` helper calls `TwitterApiClient.run_search(...)`, applies `detect_brand_mentions` to filter to brand-attributed posts (R5 logic), and returns the same shape `_load_latest_cycle_posts` returns. The existing `_run_pipeline` is unchanged. CLI wiring is in `x_monitor/__main__.py:cmd_smoketest` — read the new `--query`, `--since`, `--max-pages` args, dispatch to `_load_api_posts` when `args.source == "api-query"`. The `TwitterApiClient` is constructed with the same env-var fallback that `__main__.py:51` uses (so tests can monkeypatch `AnthropicClaudeClient` and the LLM path works; the API path needs a separate fake — see KTD6).

**KTD6. Live API source needs a fake for tests.** The existing `tests/test_post_fetch_smoketest.py` and `test_post_fetch_smoketest_latest_cycle.py` use `FakeClaudeClient` for the LLM; the API path needs a `FakeTwitterApiClient` that returns canned tweet objects. New fixture file: `tests/fixtures/api_query_fixture.jsonl` with 3 tweets (one multi-brand, one single-brand, one no-brand). The fake's `run_search` method returns the canned list — no network, no rate limit. This keeps the test fast and deterministic.

**KTD7. Translation failure breakdown is captured by the smoketest, not by the translator.** `translate_batch_pragmatics` keeps its current signature: it returns rows, with `translation_failed=True` for failures. The smoketest wraps the call in a try/except per batch (the current code already has this at scripts/post_fetch_smoketest.py:291-298) and adds per-tweet error capture: if the entire LLM call raises (not just per-row parse failure), attribute the exception to every tweet in the batch and emit `last_error_class` + `last_error_msg` fields. The rows still come back with `translation_failed=True`; the breakdown is a parallel structure (`translation_errors: {tweet_id: {class, msg, retries}}`) that the report prints when non-empty. The translator's `_call_with_retry` is the source of truth for retry counts (currently `_MAX_RETRIES=3`); the smoketest reads `_MAX_RETRIES` from the module at import time.

**KTD8. The `literal_zh` vs `text_zh_cn` documentation is a single comment + a one-page reference doc.** No code change, no migration. The comment goes in `x_monitor/translator.py` near the `_PRAGMATICS_SYSTEM_PROMPT` definition (line 351) explaining why the post-translator uses `literal_zh` while the registry-translator uses `text_zh_cn`. The new `docs/reference/translator-output.md` page is a short table mapping each output column to its translator stage and use case.

## Implementation Units

### U1. Renderer: relabel discourse fields + wire actual classifier output

**Goal:** Stop conflating the translator's post-level `discourse_role` with the classifier's per-brand `discourse_roles`. Surface the actual classifier output.

**Files:**
- `scripts/post_fetch_smoketest.py` — `_render_sample_posts` (line 145), `_run_pipeline` (line 262)
- `tests/test_post_fetch_smoketest_renderer.py` — new tests

**Approach:**
- In `_render_sample_posts`, read `cls.get("discourse_roles")` (already in the in-memory payload from `classify_pragmatics_full`). Emit `cls_disc=` when the field is present; omit the field entirely (do NOT emit `uncategorized` as a placeholder) when the field is absent.
- Rename the post-level header from `discourse:` to `trans_disc:` to make the source unambiguous. Update test assertions accordingly.
- Add a docstring comment to `_render_sample_posts` explaining the two fields' provenance.

**Patterns to follow:** the existing renderer pattern at scripts/post_fetch_smoketest.py:187-201 already reads `cls.get("post_types")` with a fallback to `cls["post_type"]`. Mirror that fallback shape for `discourse_roles`.

**Test scenarios:**
- Renders `trans_disc: genuine_hype` (not `discourse:`) when the translator returned a non-uncategorized value.
- Renders `trans_disc: uncategorized` when the translator returned `uncategorized`.
- Renders `cls_disc=genuine_hype` per brand row when `discourse_roles: ["genuine_hype"]` is in the classifier payload.
- Renders `cls_disc=genuine_hype,sarcasm` when the array has two entries.
- Omits the `cls_disc=` field entirely when `discourse_roles` is absent from the in-memory payload.
- Renders `cls_disc=uncategorized` when the array is `["uncategorized"]`.

**Verification:** run the existing e2e smoketest against the live DB; the new headers appear; no `disc=uncategorized` placeholders remain in the per-brand lines.

### U2. Renderer: include full X / Twitter URL in sample headers

**Goal:** Each post block in `=== SAMPLE POSTS ===` shows the full URL, not just the tweet_id.

**Files:**
- `scripts/post_fetch_smoketest.py` — `_load_latest_cycle_posts` (line 75, add `author_handle` to returned dict), `_load_api_posts` (new helper, see U5), `_render_sample_posts` (line 145)
- `tests/test_post_fetch_smoketest_renderer.py` — new tests

**Approach:**
- In `_load_latest_cycle_posts`, also read `p.author_handle` from the DB row. Include it in the returned post dict.
- In `_render_sample_posts`, change the `--- Post {i} (tweet_id={tid}) ---` line to `--- Post {i} (tweet_id={tid} url=https://x.com/{handle}/status/{tid}) ---`. When `handle` is missing or empty, fall back to `(no handle)` so the URL is unambiguous.
- Same for `_load_fixture_posts` — accept `author_handle` in the fixture JSONL if present.
- Same for `_load_api_posts` (new in U5) — read `handle` / `user.screen_name` from the API response and store it.

**Patterns to follow:** the existing dict shape returned by `_load_latest_cycle_posts` is `{tweet_id, id, text, lang_detected, brand_id, brand_ids}` — just add `author_handle` to that.

**Test scenarios:**
- Renders the URL when `author_handle` is present and non-empty.
- Renders `(no handle)` when `author_handle` is None or empty.
- Renders the URL from a fixture line that has `author_handle`.
- The DB path correctly reads `posts.author_handle` (one integration test with a real DB row).

**Verification:** the e2e smoketest output shows `url=https://x.com/adlenesifi/status/...` style headers; URLs resolve to the correct posts in a browser.

### U3. Classifier prompt: sentiment calibration rules

**Goal:** Add worked examples + explicit rules so the classifier distinguishes launch announcements (neutral) from praise (positive) and weights explicit positive framing in long analytical posts.

**Files:**
- `x_monitor/attribution.py` — `build_pragmatics_full_prompt` (line 1028), extend Rules section
- `tests/test_classify_pragmatics_full_prompt.py` — new tests

**Approach:**
- Add rules 10, 11, 12 to the prompt's Rules section. Rule 10: launch announcement with no evaluative language → `sent=neutral`. Rule 11: long analytical / investment post with explicit positive framing ("strategically positive", "increasingly important", "supports the multiple") → `sent=positive` for the relevant brand, not `mixed`. Rule 12: multi-brand state-of-market posts (factual updates per brand, no aggregate judgment) → `sent=neutral` for each brand unless a specific positive/negative claim is made.
- Add a worked example block at the end of the prompt: three example posts with the expected per-brand output. Examples should be SHORT (1-2 sentences each) so the prompt stays under 2000 tokens total.
- The test file adds 3 prompt-content assertions: "rule 10 mentions 'launch announcement'", "rule 11 mentions 'strategically positive'", "worked example shows event_announcement for one-line posts".

**Patterns to follow:** the existing rules 7, 8, 9 are the model — they fold the new rules into the same numbered list and use the same "If X, prefer Y" phrasing.

**Test scenarios:**
- Prompt text contains the three new rules.
- Prompt text contains the three worked examples.
- Prompt token count stays under 2000 (assert with `len(prompt.split()) * 1.3` as an upper bound).
- Existing prompt-content tests still pass (no regressions in the §5.1 contract).

**Verification:** run a 10-post e2e smoketest after U3 lands. Post 5 (Kimi K2.7 Code GA) should be `kimi sent=neutral`. Post 10 (Qwen investment thesis) should be `qwen sent=positive`.

### U4. Classifier prompt: post_type disambiguation rules

**Goal:** Add rules so `event_announcement` and `performance_comparisons` are the default for the post shapes that should hit them.

**Files:**
- `x_monitor/attribution.py` — `build_pragmatics_full_prompt` (line 1028)
- `tests/test_classify_pragmatics_full_prompt.py` — new tests

**Approach:**
- Add rules 13, 14, 15 to the prompt's Rules section. Rule 13: one-line "X is generally available / Y launched / Z shipped" posts → `pt=event_announcement` (NOT `hands_on_usage`). Rule 14: any post mentioning TTFT / latency / benchmark / ranking / "vs" comparisons / side-by-side races → `pt=performance_comparisons` (with the example being Post 8 — the LLM Drag Race write-up). Rule 15: posts that are pure analytical commentary (price/perf framing, no user-facing hands-on work) → `pt=performance_comparisons` OR `pt=feedback_questions` (the user is implicitly asking "where does this leave me?"), not `hands_on_usage`.
- Extend the worked-example block added in U3 with one example for each new rule (3 more examples; total 6).
- Re-test prompt token count stays under 2500.

**Patterns to follow:** same as U3.

**Test scenarios:**
- Prompt text contains rules 13, 14, 15.
- Prompt text contains the three new worked examples.
- The combined prompt (U3 + U4 additions) is under 2500 tokens.
- Existing prompt-content tests still pass.

**Verification:** run a 10-post e2e smoketest after U4 lands. Post 5 should be `pt=event_announcement`. Post 8 should be `pt=performance_comparisons`. Post 1 (price/perf analytical) should be `pt=performance_comparisons` or `pt=feedback_questions`, NOT `hands_on_usage`.

### U5. Smoketest: no-brand filter in `_load_latest_cycle_posts`

**Goal:** `--source=latest-cycle` skips posts with no monitored-brand attribution.

**Files:**
- `scripts/post_fetch_smoketest.py` — `_load_latest_cycle_posts` (line 75)
- `tests/test_post_fetch_smoketest_latest_cycle.py` — new test

**Approach:**
- In `_load_latest_cycle_posts`, after the `for r in rows` loop, filter `out` to only include posts with non-empty `brand_ids` (the existing field at line 119).
- Add a `posts_with_no_brand_skipped` count to the report header (e.g., `posts_with_no_brand_skipped: 3`).
- The `--source=api-query` path (U7) and `--source=fixture` path get the same filter for free — fixture author controls attribution so the fixture path can opt out by including `attributed_brands: []` explicitly.

**Patterns to follow:** the existing `_load_latest_cycle_posts` builds `out` and returns it; the filter is a single `out = [p for p in out if p["brand_ids"]]` line.

**Test scenarios:**
- A DB with 10 posts (7 brand-attributed, 3 no-brand) returns 7 posts in `out`.
- The `posts_with_no_brand_skipped` counter is 3.
- A DB with all 10 brand-attributed returns 10 posts and the counter is 0.
- A DB with all 10 no-brand returns 0 posts and the counter is 10 (the report should print `smoketest: no posts to process`).

**Verification:** run a 10-post e2e smoketest; `posts_seen` should be the count of brand-attributed posts only; the no-brand posts from the second e2e run (Posts 7, 8, 9) should be absent from the sample.

### U6. Smoketest: live API source `--source=api-query`

**Goal:** New `--source=api-query` calls `TwitterApiClient.run_search` directly and feeds the result into `_run_pipeline()`.

**Files:**
- `scripts/post_fetch_smoketest.py` — new `_load_api_posts(query, since, max_pages, max_results)` helper, `_parse_args` adds `--query` / `--since` / `--max-pages` / `--max-per-page` / `--api-quiet` flags
- `x_monitor/__main__.py` — `cmd_smoketest` (line 981) wires the new source; new subcommand is `x-monitor smoketest --source=api-query --query "kimi" --limit 5`
- `tests/test_post_fetch_smoketest_api_source.py` — new test file
- `tests/fixtures/api_query_fixture.jsonl` — new fixture (3 tweets: 1 multi-brand, 1 single-brand, 1 no-brand)

**Approach:**
- New helper `_load_api_posts(args, brand_keywords, compiled_index)`:
  1. Construct `TwitterApiClient()` (same way as `__main__.py:51`).
  2. Call `client.run_search(query=args.query, max_results=args.limit, since=args.since, max_pages=args.max_pages, max_per_page=args.max_per_page)`.
  3. Map each result row to the smoketest's post dict shape: `tweet_id`, `id`, `text`, `lang_detected`, `author_handle`, `brand_id`, `brand_ids`.
  4. Apply the same `detect_brand_mentions` filter as `_load_latest_cycle_posts` (so the no-brand filter is shared).
  5. Return the filtered list.
- New arg parsing: `--query` (required when `source=api-query`), `--since` (optional YYYY-MM-DD), `--max-pages` (default 5), `--max-per-page` (default 20). Default `args.source` stays `latest-cycle` so CI doesn't accidentally hit the live API.
- CLI help text mentions "costs real TwitterAPI.io quota".
- `--api-quiet` flag silences the `client._request_log` echo (so the smoketest output doesn't drown in HTTP logs).

**Patterns to follow:** the existing `_load_latest_cycle_posts` and `_load_fixture_posts` are the structural templates. The `TwitterApiClient` construction in `__main__.py:51` is the model for the new code.

**Test scenarios:**
- `--source=api-query` with `--query "kimi" --limit 5` constructs `TwitterApiClient`, calls `run_search` once with the right kwargs, feeds the result into `_run_pipeline`.
- The fake `TwitterApiClient.run_search` returns 3 tweets; the smoketest processes 2 (1 brand-attributed, 1 not — the no-brand one is skipped by U5's filter).
- `--query` is required when `source=api-query`; missing it returns exit 2.
- `--since` is optional; absent means no `since:` operator injection.
- The help text mentions the live-API quota cost.

**Verification:** run `x-monitor smoketest --source=api-query --query "kimi K2.7" --limit 3` against a real API call (manual test); the report shows 3 fetched posts, N brand-attributed, the LLM stages run as normal.

### U7. Smoketest report: translation failure breakdown

**Goal:** When `n_failed_translate > 0`, print per-tweet exception class + retry count + last error message.

**Files:**
- `scripts/post_fetch_smoketest.py` — `_run_pipeline` (line 262), new `=== TRANSLATION FAILURES ===` section
- `x_monitor/translator.py` — export `_MAX_RETRIES` constant (currently module-private; export via `__all__` or just read the module attribute — see Approach)

**Approach:**
- In `_run_pipeline`, wrap the `translate_batch_pragmatics` call (line 292) in a try/except that captures the exception. The current code already has a try/except at line 295-298 that prints to stderr and sets `translation_rows = []`. Replace that with: catch the exception, attribute it to every tweet_id in the input batch, set `translation_rows = []` + a parallel `translation_errors: dict[str, dict]` with `{class: exc.__class__.__name__, msg: str(exc)[:200], retries: x_monitor.translator._MAX_RETRIES}` for every tweet_id in the input.
- The renderer prints a new `=== TRANSLATION FAILURES ===` block when `translation_errors` is non-empty: one line per tweet_id with the class + first 80 chars of msg.
- The `n_failed_translate` count is unchanged.
- `_MAX_RETRIES` is currently `x_monitor.translator._MAX_RETRIES` (it's at module level, line 167). The smoketest can `from x_monitor.translator import _MAX_RETRIES` — it's already importable, just not in `__all__`. No change needed in translator.py.

**Patterns to follow:** the existing `=== ERRORS (N translation failures) ===` block at scripts/post_fetch_smoketest.py:406-410 is the model for the new section.

**Test scenarios:**
- A batch where `translate_batch_pragmatics` raises `RuntimeError("proxy 502")` produces a `translation_errors` dict with 10 entries (one per input tweet), each with `class: "RuntimeError"`, `msg: "proxy 502"`, `retries: 3`.
- The `=== TRANSLATION FAILURES ===` section is printed and shows the right line per tweet.
- A successful batch produces an empty `translation_errors` and the section is omitted.
- `_MAX_RETRIES` is read from the translator module and is 3 (or whatever the current value is — assert the value matches the module).

**Verification:** force a translation failure (e.g., set `ANTHROPIC_BASE_URL` to an unreachable host), run a 5-post smoketest; the new section shows up with the expected per-tweet breakdown.

### U8. Docs: `literal_zh` vs `text_zh_cn` clarification

**Goal:** Document the two output columns and their distinct translator stages.

**Files:**
- `x_monitor/translator.py` — add a 3-line comment near `_PRAGMATICS_SYSTEM_PROMPT` (line 351) explaining the naming
- `docs/reference/translator-output.md` — new one-page reference

**Approach:**
- The comment explains: "`literal_zh` is the post-translator's output for X / Twitter posts (lossless, preserves slang). `text_zh_cn` is the registry-translator's output for brands, products, and other lookup tables (formal, named-entity-preserving). Both columns live in `posts`; populated by different translator code paths."
- The reference doc has a table with columns: output column | translator stage | use case | example. Rows: `text_en` | `translate_batch_pragmatics` | English rendering of non-English source | "Anthropics neue KI-Modelle" → "Anthropic's new AI models"; `literal_zh` | `translate_batch_pragmatics` | Chinese rendering of source (lossless with slang) | "GitHub Copilot just dropped Kimi K2.7 like a secret weapon" → "GitHub Copilot 刚刚把 Kimi K2.7 像科幻片里的秘密武器一样扔出来"; `text_zh_cn` | `translate_registry_rows` | Chinese rendering of registry entries (formal) | "Moonshot AI" → "月之暗面"; `cn_equivalent` | `translate_batch_pragmatics` | "How would Chinese netizens say this" free rendering | "Kimi K2.7 Code is generally available" → "Kimi K2.7 Code 正式登陆 Copilot，全量开放".
- The reference doc also includes a section on the deterministic noop (the U5 fix from plan 003) — when `lang_detected` is already `en` or `zh-Hans`, `text_en` or `text_zh_cn` is set to NULL server-side.

**Patterns to follow:** the existing `docs/reference/` directory structure. No new top-level directories.

**Test scenarios:** none — this is documentation only. (A test could verify the new file exists, but that's redundant with the git commit.)

**Verification:** the new file is in `docs/reference/translator-output.md`; the comment is in `translator.py`; both land in the same commit.

## Out of scope / Deferred

- **`no_brand` pseudo-brand for general-AI posts (TODO #57 path B).** User picked path A (filter). Path B is a feature request for a separate plan if non-brand AI posts become a recurring need.
- **Per-brand `unsanctioned_flags` schema.** The 003 plan KTD2 noted this as a possible future schema extension; no current need.
- **Investigating minimax proxy root cause for the 10/10 failure (TODO #58).** The smoketest now diagnoses it (U7), but the underlying proxy reliability is an infra concern outside the scope of this plan.
- **Real LLM-backed `genuine_hype` rule regression test (R8 from 003).** The shipped rule was verified by the 003 e2e run. U3/U4 add new rules but do not re-test R8.
- **A separate `classify_unsanctioned_only` CLI subcommand.** The 003 plan KTD8 added a "backfill unsanctioned-flags" command; the current plan doesn't touch that.

## Open Questions

- **OQ1.** Should the `--source=api-query` source also be reachable from the main `x-monitor run` command (which already calls `apify.run_search`), or stay smoketest-only? Currently scoped to smoketest only. If the main loop ever needs to be smoketest-tested, it can shell out to `x-monitor smoketest --source=api-query` instead of duplicating the call. (No user input needed — default to smoketest-only and revisit if it comes up.)
- **OQ2.** When the no-brand filter is applied (U5), should the smoketest print a warning that posts were filtered? Currently the report just shows `posts_seen: 7` without explanation. A one-line `WARN: 3 posts filtered (no monitored-brand attribution)` is enough; deferred to a future iteration if it becomes confusing.

## Risks & Dependencies

- **Risk:** U3 + U4 expand the prompt past the 2500-token ceiling, increasing per-call latency and cost. **Mitigation:** the token-count assertion in the test fails the PR if the prompt exceeds 2500 tokens.
- **Risk:** The new prompt rules cause regressions in cases the old prompt handled well (e.g., the R8 CTA rule from 003). **Mitigation:** the existing `test_classify_pragmatics_full_prompt.py` tests stay in the suite; the new rules are additive and explicitly say "in addition to rules 1-9".
- **Risk:** The live API source (U6) hits rate limits or quota exhaustion in CI. **Mitigation:** `--source=api-query` is opt-in; default stays `latest-cycle`; the test uses a fake `TwitterApiClient` so CI doesn't hit the live API.
- **Dependency:** U1, U2, U5 all modify `scripts/post_fetch_smoketest.py`. They can ship in any order but should land in the same commit (single renderer change) to avoid a broken intermediate state.
- **Dependency:** U3 + U4 both modify `build_pragmatics_full_prompt`. They should land in the same commit so the prompt content is internally consistent. The test file is shared.

## System-Wide Impact

- **`x-monitor smoketest` users (DevRel, LaunchAgent operational gate).** Output format changes (URL header, `trans_disc` / `cls_disc` rename, translation-failure section). The renderer change is backward-compatible at the data level (the underlying fields are unchanged); the rename is a breaking change to anyone grepping the report for `^discourse:`. Document in the PR body.
- **Dashboard consumers.** None. The smoketest is a CLI tool; its output is human-readable, not a feed to the dashboard. The post-level `discourse` field on `posts` is unchanged; the rename is only in the smoketest report.
- **LaunchAgent operational gate.** The 90s ceiling in the report (currently `WARNING: cycle exceeded 90s ceiling`) is unchanged. The new `translation_failure_breakdown` section is a new failure mode the gate can detect (e.g., `n_failed_translate > 0` is a smoke-test failure even if the cycle finishes under 90s). Document in the gate's config.
- **CI.** The new `--source=api-query` is opt-in; the default source is `latest-cycle` and the existing tests stay deterministic. No CI breakage.

## Sources & Research

- `/tmp/smoketest_e2e_run.txt` — first e2e run (sample=5, 10/10 translations succeeded, all classifications returned `uncategorized` for discourse and `hands_on_usage` for post_type)
- `/tmp/smoketest_e2e_full.txt` — second e2e run (sample=10, 10/10 translations failed)
- Live DB inspection at `data/x_monitoring.db` (migrations 027 + 028 applied; `posts_brands_signals` is the new TEXT-natural-key layout)
- `docs/plans/2026-07-03-003-feat-post-fetch-taxonomy-and-multi-discourse-plan.md` — the immediately prior plan (R8 CTA rule, R6 text_en noop, R12 fail-soft contract, KTD3 generated column)
- `x_monitor/translator.py:160-182` — `_call_with_retry` (current `_MAX_RETRIES=3`, exponential backoff `_BACKOFF_BASE_SECONDS * 2**attempt`)
- `x_monitor/translator.py:300-331` — `_is_english_family`, `_is_simplified_chinese_family` (the noop-rule family introduced in U5 of plan 003)
- `x_monitor/attribution.py:1028-1133` — `build_pragmatics_full_prompt` (the prompt U3 + U4 extend)
- `scripts/post_fetch_smoketest.py:75-121` — `_load_latest_cycle_posts` (U2, U5 modify this)
- `scripts/post_fetch_smoketest.py:145-202` — `_render_sample_posts` (U1, U2 modify this)
- `x_monitor/apify.py:273-313` — `TwitterApiClient.run_search` (U6 calls this)
- `x_monitor/__main__.py:51` — `TwitterApiClient` construction template (U6 mirrors this)

## Definition of Done

- [ ] U1 — `_render_sample_posts` reads `cls["discourse_roles"]` from the in-memory payload; the post-level header is `trans_disc:`; no `disc=uncategorized` placeholder remains in per-brand lines. Test file updated.
- [ ] U2 — Every post block in `=== SAMPLE POSTS ===` shows `url=https://x.com/<handle>/status/<tweet_id>` (or `(no handle)` fallback). DB path, fixture path, and api-query path all carry `author_handle` through.
- [ ] U3 — `build_pragmatics_full_prompt` has new rules 10, 11, 12 for sentiment calibration, plus 3 worked examples. Prompt token count under 2500. Existing prompt tests pass.
- [ ] U4 — `build_pragmatics_full_prompt` has new rules 13, 14, 15 for post_type disambiguation, plus 3 more worked examples. Prompt token count under 2500. Existing prompt tests pass.
- [ ] U5 — `_load_latest_cycle_posts` filters out posts with empty `brand_ids`. The report header includes `posts_with_no_brand_skipped: <int>`. Test file updated.
- [ ] U6 — `--source=api-query` with `--query`, `--since`, `--max-pages`, `--max-per-page` calls `TwitterApiClient.run_search` and feeds into `_run_pipeline`. `--query` is required when `source=api-query`; missing it returns exit 2. Fake `TwitterApiClient` works in tests.
- [ ] U7 — When `n_failed_translate > 0`, the report prints a `=== TRANSLATION FAILURES ===` section with per-tweet exception class + msg + retry count. Successful batches omit the section. Test file updated.
- [ ] U8 — Comment in `x_monitor/translator.py` near `_PRAGMATICS_SYSTEM_PROMPT`. New `docs/reference/translator-output.md` page.
- [ ] All 8 unit-test files pass: `test_post_fetch_smoketest_renderer.py`, `test_post_fetch_smoketest_latest_cycle.py`, `test_post_fetch_smoketest_api_source.py`, `test_classify_pragmatics_full_prompt.py`, `test_classify_pragmatics_full.py`, `test_classify_pragmatics_full_arrays.py`, `test_run_post_fetch.py`, `test_post_fetch_smoketest_strict_budget.py`.
- [ ] An end-to-end smoketest (`x-monitor smoketest --source=latest-cycle --limit 10 --sample 5`) runs cleanly. All 10 posts have populated `trans_disc:`, all brand-attributed posts have populated `cls_disc=`, all 10 have populated URL, no `disc=uncategorized` placeholders.
- [ ] No schema change. No DB migration. The 003 plan's migrations 027 + 028 are unchanged.
