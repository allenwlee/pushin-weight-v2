---
title: Concurrent classification + prompt caching
date: 2026-07-08
type: feat
status: ready
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
execution: code
---

# Context

Two production-readiness gaps in `classify_pragmatics_full`:

1. **Sequential-by-default.** The classification loop in `x_monitor/run.py:663-680` calls the LLM one tweet at a time. At 200 tweets/cycle (the typical 15-min cadence) and ~5.8 s/post (measured on `MiniMax-M3`), a single cycle takes ~1,155 s ≈ 19 min — **exceeding the 15-min cadence budget**.

2. **No prompt caching.** `build_pragmatics_full_prompt` builds a single ~3,500-token string per call. Of those, ~3,000 tokens are static (taxonomy enumeration, rules 1–19, worked examples A–J) and only ~500 tokens are dynamic (the one tweet's text + brand list). MiniMax's pricing for cached reads is **$0.06/M tokens** vs **$0.30/M** for uncached input — a **5× cost reduction** on the static prefix after the first call.

Both fixes are independent of the v13 prompt calibration work. The v13 plan (`docs/plans/2026-07-08-002`) adds examples regardless of token cost; this plan ensures the resulting prompt stays affordable at production cadence.

**Outcome:**
- Async concurrency: 5 concurrent `classify_pragmatics_full` calls in `_run_post_fetch` (cap tunable via env var). Expected wall-clock reduction: **5×**.
- Prompt caching: static prompt prefix moved to a `system` block with `cache_control: {"type": "ephemeral"}`. Expected cost reduction: **4–5×** for cycles after the first.

These compose: a 200-tweet cycle at 5 concurrency with caching finishes in **~232 s ≈ 4 min** (down from ~22 min) at **~$0.07** (down from ~$0.33).

# Files to modify

| Path | Change |
|---|---|
| `x-monitoring/x_monitor/attribution.py` | (1) Split `build_pragmatics_full_prompt` into `build_static_prefix()` + `build_dynamic_suffix()`. (2) Add `_call_signal_cached` that sends the static prefix as a cached `system` block. (3) Keep the legacy `build_pragmatics_full_prompt` as a thin wrapper for back-compat. |
| `x-monitoring/x_monitor/run.py` | (1) Wrap the classification loop in `_run_post_fetch` (line 663) in `asyncio.gather` with `Semaphore(5)`. (2) Make `AnthropicClaudeClient.messages_create` async-aware via `asyncio.to_thread` (or add `amessages_create`). |
| `x-monitoring/x_monitor/__main__.py` | Same wrapping as `run.py:663` for the standalone CLI path that also calls `classify_pragmatics_full` (line 934). |
| `x-monitoring/tests/test_concurrent_classify.py` | **New file.** 6 tests covering concurrency cap, fail-soft per post, partial-failure counting, and that the static prefix is identical across calls (cache hit invariant). |
| `x-monitoring/tests/test_prompt_caching.py` | **New file.** 4 tests covering cache_control marker presence, static prefix byte-identity, and that the dynamic suffix is the only per-call difference. |
| `~/.claude/skills/custom-claude-skills/pushin_weight_smoketest/SKILL.md` | Update frontmatter description + Canonical command if `--concurrency` flag is added to the smoketest (deferred to a future U-ID; not in this plan). |

# Implementation

## U1. Prompt caching (attribution.py)

### U1a. Split the prompt builder

The current `build_pragmatics_full_prompt` (lines 1041-1260) returns a single string with two functional parts:

| Part | Lines | Tokens | Purpose |
|---|---|---|---|
| **Static prefix** | 1042-1107 (header + taxonomy enumeration + rules 1-9) | ~1,400 | Teaches the LLM the schema. Identical across all calls. |
| **Substantive prefix** | 1108-1249 (rules 10-19 + worked examples A-J) | ~1,600 | Teaches the LLM the boundary cases. Identical across all calls. |
| **Dynamic suffix** | (currently f-stringed inline) | ~500 | Tweet text + brand list. Varies per call. |

Both static parts belong in the **system** block with `cache_control: {"type": "ephemeral"}`. The dynamic suffix goes in the **user** block without caching.

**Refactor:**

```python
def build_static_prefix() -> list[dict]:
    """Return the static prompt prefix as a list of content blocks
    suitable for the Anthropic API's `system` parameter with cache_control."""
    return [
        {
            "type": "text",
            "text": (
                "You classify a tweet's relationship to a list of brands, "
                "across FIVE dimensions.\n\n"
                # ... (full taxonomy enumeration + rules 1-19 + worked
                # examples A-J, lifted verbatim from the current prompt)
            ),
            "cache_control": {"type": "ephemeral"},
        }
    ]

def build_user_suffix(text: str, brand_ids: list[str]) -> list[dict]:
    """Return the tweet-specific portion as a user message."""
    brand_list = ", ".join(brand_ids) if brand_ids else "(none)"
    return [
        {
            "type": "text",
            "text": (
                f"Tweet text:\n\"\"\"\n{text}\n\"\"\"\n\n"
                f"Brands (in order): {brand_list}\n\n"
                "Return the JSON object matching the schema described in "
                "the system prompt above."
            ),
        }
    ]
```

`build_pragmatics_full_prompt` becomes a thin back-compat wrapper:

```python
def build_pragmatics_full_prompt(text: str, brand_ids: list[str]) -> str:
    """Legacy single-string prompt. Returns the cached-prefix + suffix
    joined for callers that don't yet speak the messages API shape."""
    # Concatenate static prefix + dynamic suffix as before.
    # Tests that string-match the prompt continue to pass.
```

The smoketest and any other callers that build a single-string prompt keep working. The production path (U2) switches to the messages-shape API.

### U1b. New caller for cached messages API

```python
async def classify_pragmatics_full_cached(
    text: str,
    brand_ids: list[str],
    brand_registry: list,
    anthropic_client: "AsyncClaudeClient | None" = None,
) -> dict[str, Any]:
    """U1 (caching): same return shape as classify_pragmatics_full, but
    sends the static prefix as a cached system block.

    Cache lifetime: ~5 minutes (Anthropic ephemeral cache TTL, proxied
    through MiniMax). At 15-min cycle cadence, the cache survives
    between cycles — first cycle pays the write cost, every cycle
    after reads from cache for ~$0.06/M tokens.
    """
    empty = {"by_brand": {}, "unsanctioned_flags": []}
    if not brand_ids or not text:
        return empty
    if anthropic_client is None:
        return empty

    registry_ids = (
        {b.brand_id for b in brand_registry} if brand_registry
        else set(brand_ids)
    )
    response = await anthropic_client.messages_create_cached(
        model=_SIGNAL_MODEL,
        max_tokens=2048,
        system=build_static_prefix(),   # with cache_control
        messages=[
            {"role": "user", "content": build_user_suffix(text, brand_ids)},
        ],
    )
    parsed = _parse_pragmatics_full_response(response, registry_ids)
    if not parsed["by_brand"]:
        logger.warning(
            "classify_pragmatics_full_cached returned no classifications "
            "for text=%r brand_ids=%r",
            text[:80], brand_ids,
        )
    return parsed
```

The `messages_create_cached` method on `AnthropicClaudeClient` is a small wrapper that calls the underlying SDK with `system` (a list of content blocks) instead of `system` (a string). MiniMax's Anthropic-API proxy supports `system` as either a string or a list; the list form is required for `cache_control` markers.

## U2. Async concurrency (run.py)

### U2a. Wrap the classification loop

Replace the sequential loop at `x_monitor/run.py:663-680` with:

```python
import asyncio
from .attribution import classify_pragmatics_full_cached

async def _classify_batch(
    kept_posts: list[dict],
    brand_registry_rows: list,
    anthropic_client,
    concurrency: int = 5,
) -> list[tuple[dict, dict]]:
    """Run classify_pragmatics_full_cached over kept_posts with bounded
    concurrency. Returns list of (post, classification_result) tuples,
    preserving input order. Per-post exceptions are caught and the
    post's slot becomes ({}, []) — same fail-soft contract as the
    legacy loop."""
    sem = asyncio.Semaphore(concurrency)

    async def _one(post):
        async with sem:
            try:
                result = await classify_pragmatics_full_cached(
                    text=post.get("text") or "",
                    brand_ids=list(post.get("brand_ids") or []),
                    brand_registry=brand_registry_rows,
                    anthropic_client=anthropic_client,
                )
            except Exception as e:
                log.warning(
                    "_classify_batch: classify failed for "
                    "tweet_id=%s: %s",
                    post.get("id") or post.get("tweet_id"), e,
                )
                result = {"by_brand": {}, "unsanctioned_flags": []}
            return post, result

    tasks = [
        _one(post) for post in kept_posts
        if post.get("brand_ids")  # skip no-brand posts (same as legacy)
    ]
    return await asyncio.gather(*tasks)
```

### U2b. Synchronous adapter for the existing call site

`_run_post_fetch` is currently a sync function. Wrap the async call:

```python
t0 = time.monotonic()
results = asyncio.run(_classify_batch(
    kept_posts, brand_registry_rows, anthropic_client,
    concurrency=int(os.environ.get("X_MONITOR_CLASSIFY_CONCURRENCY", "5")),
))
t_classify = time.monotonic() - t0

# results is a list of (post, classification) tuples; iterate
# exactly like the old loop, building signal_rows / discourse_rows /
# unsanctioned_by_post.
```

`asyncio.run` is fine here because `_run_post_fetch` itself is the top of a sync call stack (called from `run.py:main` and `__main__.py:main`, both sync). If we later want to call this from an async context (e.g., a long-running supervisor), we'll need an `await` path — out of scope for this plan.

### U2c. Tunable concurrency

`X_MONITOR_CLASSIFY_CONCURRENCY` env var, default 5. The smoketest passes `--concurrency=5` (or 1 for debugging). The CI tests run with `1` to keep them deterministic.

### U2d. AnthropicClaudeClient async support

The current `messages_create` is sync. Add a thin async wrapper:

```python
class AnthropicClaudeClient:
    async def messages_create_cached(self, **kwargs) -> dict:
        """Async wrapper around the sync SDK call. Runs the blocking
        HTTP request in a thread to keep the event loop responsive."""
        return await asyncio.to_thread(self.messages_create, **kwargs)
```

`asyncio.to_thread` is the right primitive here — it offloads the blocking SDK call to a thread pool worker without requiring us to await the Anthropic SDK's native async client (which may not exist or may not be supported by the MiniMax proxy).

## U3. Tests

### U3a. `tests/test_prompt_caching.py` (4 tests)

| Test | Asserts |
|---|---|
| `test_static_prefix_has_cache_control` | `build_static_prefix()` returns a list with at least one block whose `cache_control` is `{"type": "ephemeral"}`. |
| `test_static_prefix_byte_identical_across_calls` | Two calls to `build_static_prefix()` return content-block-identical output (no f-string interpolation in the prefix). |
| `test_user_suffix_is_only_per_call_difference` | Two calls to `build_user_suffix("text A", ["b1"])` and `build_user_suffix("text B", ["b2"])` produce suffixes whose only difference is the embedded text + brand_list. |
| `test_legacy_prompt_unchanged` | `build_pragmatics_full_prompt("text", ["b1"])` returns a string whose first 200 chars match the legacy expected output (regression guard). |

### U3b. `tests/test_concurrent_classify.py` (6 tests)

| Test | Asserts |
|---|---|
| `test_classify_batch_preserves_order` | `_classify_batch([p1, p2, p3, p4, p5])` returns 5 (post, result) tuples in input order, regardless of completion order. |
| `test_classify_batch_concurrency_cap` | Monkeypatch the inner `_one` to record the running-task count. Run 20 posts at concurrency=5. Assert max-in-flight ≤ 5. |
| `test_classify_batch_fail_soft` | Inject one post that raises inside `classify_pragmatics_full_cached`. Assert that post's slot is `({"by_brand": {}, "unsanctioned_flags": []})` and other posts complete normally. |
| `test_classify_batch_skips_no_brand_posts` | Mix 5 brand-attributed posts with 3 no-brand posts. Assert result length is 5. |
| `test_concurrency_env_var` | Set `X_MONITOR_CLASSIFY_CONCURRENCY=3` and run a 10-post batch with the in-flight recorder. Assert max-in-flight ≤ 3. |
| `test_classify_batch_empty_input` | `_classify_batch([])` returns `[]`. |

## U4. Verification

### U4a. Unit-level

```bash
cd x-monitoring
python3 -m pytest tests/test_prompt_caching.py tests/test_concurrent_classify.py -v
```
All 10 tests pass.

### U4b. Integration against the live DB

Run the smoketest end-to-end and observe timings:

```bash
cd x-monitoring
python3 -m scripts.post_fetch_smoketest --source=latest-n --latest=20 \
    | tee /tmp/smoketest_after_concurrency.txt
```

Expected: `t_classify_ms` drops from **~58 s** (sequential, 10 posts) to **~12-15 s** (5-concurrent, 10 posts). `t_total_ms` should drop accordingly.

### U4c. Cost verification (after one cycle's worth of cache priming)

Run the smoketest twice in succession (first call pays cache write, second reads from cache). Compare input token counts in the API response:

```python
# Add a one-shot diagnostic script at scripts/diag_cache_hit.py
# that prints `usage.input_tokens`, `usage.cache_creation_input_tokens`,
# `usage.cache_read_input_tokens` from the response.
```

Expected on the second call:
- `cache_creation_input_tokens = 0` (cache exists from first call)
- `cache_read_input_tokens ≈ 3,000` (the static prefix)
- `input_tokens ≈ 500` (only the dynamic suffix is uncached)

### U4d. Rate-limit observability

Add a temporary `log.info` line in `messages_create_cached` that logs the response headers (specifically `x-ratelimit-*`). Run the smoketest at concurrency=5, 10, 20 in succession and observe:
- Any 429s? → concurrency too high.
- `x-ratelimit-remaining-tokens` declining? → headroom is real, can raise.
- All headers missing? → MiniMax proxy doesn't surface them; treat as unlimited and rely on 429s as the only signal.

This becomes the empirical cap-setting data point.

# Commit strategy

Two commits in dependency order:

```
feat(x-monitor): prompt caching for classify_pragmatics_full

- attribution.py: split build_pragmatics_full_prompt into
  build_static_prefix() (cached system block) and
  build_user_suffix() (uncached user block). Add
  classify_pragmatics_full_cached() that uses the messages API
  with cache_control markers. Legacy build_pragmatics_full_prompt
  preserved as a back-compat wrapper.
- tests/test_prompt_caching.py: 4 tests covering cache_control
  marker presence, byte-identity of the static prefix, and
  that the dynamic suffix is the only per-call difference.
```

```
feat(x-monitor): async concurrency for classify_pragmatics_full

- run.py: wrap the classification loop in _run_post_fetch with
  asyncio.gather + Semaphore(5). Tunable via
  X_MONITOR_CLASSIFY_CONCURRENCY env var (default 5).
- AnthropicClaudeClient: add async messages_create_cached wrapper
  using asyncio.to_thread.
- __main__.py: same wrapping for the standalone CLI classify path.
- tests/test_concurrent_classify.py: 6 tests covering order
  preservation, concurrency cap enforcement, fail-soft per post,
  no-brand skip, env-var override, empty input.
```

# Why this is independent of v13

v13 (`docs/plans/2026-07-08-002`) adds examples to the prompt without changing the call pattern. v13 does not require async or caching to land first. The two plans compose:

| Work | Cycle wall-clock (200 tweets) | Cycle cost |
|---|---|---|
| Today (sequential, no cache) | ~22 min | ~$0.33 |
| v13 only (sequential, no cache, +5 examples) | ~22 min | ~$0.50 |
| Async only (sequential timing, but cached) | ~4 min | ~$0.07 |
| v13 + async + caching | ~4 min | ~$0.10 |

If async/caching land first, v13's expanded prompt costs only 40% more than the current prompt (because the static prefix is cached). If they don't, v13 adds ~50% to a cycle that's already over budget.

The right sequencing is: **land this plan first, then v13**. The benefit of either landing without the other is real (cost reduction or latency reduction alone), but the compound effect is the goal.

# Open Questions

1. **Does the MiniMax proxy actually support `cache_control`?** The Anthropic API supports it; the docs confirm `cache_control` is in the parameter list for MiniMax-M3. **Empirically unverified**: the first cache write needs to actually return `cache_creation_input_tokens > 0` in the response. U4c covers this.

2. **What is the actual concurrency cap?** Docs don't publish rate limits. U4d covers empirical cap-setting.

3. **Does `asyncio.to_thread` introduce enough overhead to negate concurrency gains?** Each classification call still hits the proxy; `asyncio.to_thread` only offloads the blocking SDK call. The per-call overhead is < 1ms. Not a real concern, but worth a smoke test.

4. **Should `__main__.py:934` (the standalone CLI classify path) also be async-wrapped?** Same code path as `run.py:663`. U2 says yes — it's a one-line copy. If you'd rather scope this plan tighter, drop U2c's `__main__.py` change to a follow-up.

5. **Backwards compatibility.** `build_pragmatics_full_prompt` keeps its signature and returns the joined string. The smoketest's string-based assertions still pass. The only breaking change is the new async requirement for `_run_post_fetch` — but that's only called from sync entry points, which we wrap with `asyncio.run`, so the public API is unchanged.