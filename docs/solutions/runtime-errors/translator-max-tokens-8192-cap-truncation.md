---
module: x_monitor
date: 2026-08-05
problem_type: runtime_error
component: tooling
severity: high
symptoms:
  - "translator_batch_failed with non-JSON response len=12134..28283 in prod cron logs"
  - "text_zh_cn column NULL on freshly translated posts (~25% of cycles)"
  - "stop_reason=max_tokens in raw API responses (response truncated mid-JSON)"
  - "constant 8192 max_tokens for every batch size regardless of n"
root_cause: wrong_assumption
resolution_type: code_fix
related_components:
  - x_monitor/translator.py
  - tests/test_translator_max_tokens.py
  - docs/plans/2026-08-04-001-swap-translator-to-deepseek-v4-plan.md
tags:
  - translator
  - max_tokens
  - deepseek
  - truncation
  - output-budget
  - JSON-decode
---

# Translator `max_tokens=8192` cap silently truncates prod batches

## Symptom

After the M3 → DeepSeek V4 swap (commit `4d3db60`, plan
`2026-08-04-001`) landed, the 08:00 UTC cron cycle produced 253 posts
with **78.3%** `text_zh_cn` coverage. The 07:00 and 06:00 cycles were
69.7% and 89.3% respectively. The 06:00 cycle had previously shown
**100%** coverage immediately after the swap (per handoff
`2026-08-05-002`), then degraded.

Cron logs from the 06:00–09:00 UTC window:

```
2026-08-05 06:17:53  messages_create: LLM returned non-JSON (len=28283): '{...}'
2026-08-05 06:18:45  translator_batch_failed
2026-08-05 06:33:12  messages_create: LLM returned non-JSON (len=14399): '{...}'
2026-08-05 06:37:51  messages_create: LLM returned non-JSON (len=26076): '{...}'
2026-08-05 06:51:32  messages_create: LLM returned non-JSON (len=12134): '{...}'
2026-08-05 07:20:14  messages_create: LLM returned non-JSON (len=15976): '{...}'
2026-08-05 08:03:23  messages_create: LLM returned non-JSON (len=20968): '{...}'
2026-08-05 08:34:03  messages_create: LLM returned non-JSON (len=14399): '{...}'
```

6 truncations in 9 cycles, all in the 12K–28K char range. All
directly preceded by `translator_batch_failed`.

## Root cause — constant 8192 cap on a variable-density output

`x_monitor/translator.py:_max_tokens_for_batch_size` post-swap:

```python
return min(8192, max(8192, 200 * n))  # collapses to 8192 for every n
```

Two defects in one expression:

1. **`max(8192, 200 * n)` ignores the coefficient for n ≤ 40.** The
   200 tokens/post figure was inherited from the classifier plan
   (`2026-07-15-002 KTD4`) where it was empirically sufficient
   (99 tokens/post at batch_size=20, 108 tokens/post at batch_size=40).
   The translator's output is richer (text_en + literal_zh +
   cn_equivalent + annotation + JSON framing). At batch_size=20 the
   observed density is **~977 tokens/post**.
2. **`min(8192, 8192)` makes the cap a constant.** `helper(1)` and
   `helper(100)` both returned 8192.

The 8192 cap was based on an outdated "DS V4 beta max" comment. Live
API probe (2026-08-05) confirmed `max_tokens=65536` is accepted
(HTTP 200). The API ceiling is roughly 65k, not 8k.

## Why the prior fix didn't catch it

The plan `2026-08-04-001` U1 step 2 specified the helper:

```python
return min(8192, max(4096, 200 * n))
```

…and the regression test `test_translator_max_tokens.py` pinned
8192 at the helper level. The plan was reviewed and the test was
green. Both pin and helper were buggy in the same direction — the
test "passed" by agreeing with the bug.

When `4d3db60` (the second iteration, post-2026-08-04 followup) bumped
the floor to 8192, the bug became invisible: `max(8192, 200 * n)`
clamped to 8192 for every n that mattered, and the test still
asserted 8192.

## Empirical evidence (2026-08-05 09:08 UTC)

Loaded 20 prod-typical failing posts (no `text_zh_cn`, real text
content) from the 09:00 cycle. Replayed with the new helper value
against the live DS V4 API:

| Setting | Result |
|---|---|
| `max_tokens=8192` (old) | `stop_reason=max_tokens`, 8,192 output tokens, 30,357 chars of mid-JSON cut |
| `max_tokens=20000` (new) | `stop_reason=end_turn`, 15,318 output tokens, 41,925 chars, 20/20 result rows with full fields |

The new budget is 5% headroom over the observed worst case (20,000
vs 19,554 output tokens for a 20-post batch).

## Resolution

Replaced the helper:

```python
# Before
return min(8192, max(8192, 200 * n))

# After
return min(65536, max(16384, 1000 * n))
```

Three regression pins added in `tests/test_translator_max_tokens.py`:

- `test_max_tokens_helper_covers_prod_observed_rich_batch` —
  `helper(20) >= 20_000` (would fail on the 8192-cap pre-fix).
- `test_max_tokens_helper_cap_matches_deepseek_max` —
  `helper(100) <= 65536 AND helper(100) >= 20_000`.
- `test_max_tokens_helper_rejects_pre_8192_truncation` —
  `helper(1) < helper(20) < helper(60)` (rejects the constant-8192
  bug shape).

Each pin includes the BEFORE state in the failure message so any
future regression fails loudly with the empirical context.

## Files changed

- `x_monitor/translator.py` — `_max_tokens_for_batch_size` (lines 65-96).
- `tests/test_translator_max_tokens.py` — 3 new pins + updated module
  docstring, pin constants, and assertion messages.

## Verification

- Local: `pytest tests/test_translator_max_tokens.py -v` → 7 passed.
- End-to-end: 20-post prod-data repro parses cleanly with the new
  helper, 20/20 result rows with full translation fields.
- Production: cron deploy `c09a291` Live at 2026-08-05T09:08:56Z.
  Next cycle at 09:15 (in progress at time of writing) shows no
  `messages_create: LLM returned non-JSON` except the classifier's
  designed `KEEP`/`DROP` no-ops (4-char responses).

## Lessons

1. **Borrowed coefficients need re-measurement.** The 200 tokens/post
   figure came from `test_classifier_swap.deepseek_v4_probe.json` at
   batch_size=20/40. The translator's output is richer (4 fields +
   JSON framing per post vs 1 tuple per post). The classifier probe
   is *not* a substitute for translator probe.

2. **Test pins that lack empirical anchors drift with the bug.**
   `EXPECTED_MAX_TOKENS_AT_BATCH_20 = 8192` was a green test that
   pinned a wrong value. The new pins anchor on the prod observation
   (`19,554 output tokens`) and the API ceiling (`65536`), not on
   historical code.

3. **Live API probes are cheap.** The `max_tokens=65536` HTTP probe
   takes ~1 second and prevents "based on outdated spec" assumptions
   from shipping. Should be a standard step in any
   swap-to-new-model plan.

4. **Truncation is silent.** `parse_llm_response` soft-fails to
   `{"results": []}` on parse failure, which `translate_batch` logs
   as `translator_batch_failed` but doesn't raise. The cycle
   completes; downstream sees `text_zh_cn IS NULL`. The terminal
   user sees a missing translation row, not an error. Always
   profile end-to-end.

## Cross-references

- Handoff: `docs/handoffs/2026-08-05-002-translator-env-override-fix.md`
- Plan: `docs/plans/2026-08-04-001-swap-translator-to-deepseek-v4-plan.md`
  (U10/U11 sections)
- Vocab: `CONCEPTS.md` ("Translator env-vs-yaml precedence" section
  should be extended to "Translator output budget sizing")
- Related: `docs/solutions/runtime-errors/translator-env-override-clobbered-by-yaml-null.md`
  (the previous bug in the same swap that this one was hidden behind)
