---
type: handoff
date: 2026-08-05
session: 2026-08-05 (local, M3.0)
plan: docs/plans/2026-08-04-001-swap-translator-to-deepseek-v4-plan.md
branch_when_written: main
last_commit: c09a291
commits_in_this_handoff:
  - c09a291 fix(translator): max_tokens=20k for 20-post batches truncates-as-8192
related_docs:
  - docs/solutions/runtime-errors/translator-max-tokens-8192-cap-truncation.md
  - docs/plans/2026-08-04-001-swap-translator-to-deepseek-v4-plan.md
  - tests/test_translator_max_tokens.py
  - CONCEPTS.md (new "Translator output budget sizing" section — TODO)
status: translator reaches 100% coverage on the 09:15 cycle; no truncation since deploy
resume_command: "cat docs/handoffs/2026-08-05-003-translator-max-tokens-8192-truncation.md"
blocking_inputs_needed: []
---

# Handoff — Translator max_tokens=8192 truncation fix (commit c09a291)

## What was happening

After the M3 → DeepSeek V4 translator swap (`docs/plans/2026-08-04-001`)
landed on 2026-08-04 across commits `02953d6` → `4d3db60` → `8a07a99`,
the 08:00 UTC cron cycle produced 253 posts with **78.3%** `text_zh_cn`
coverage. The 07:00 cycle was 89.3%, the 06:00 cycle was 69.7%. The
06:00 cycle had briefly shown 100% coverage immediately after the
swap (per handoff `2026-08-05-002`), then degraded.

The handoff `2026-08-05-002` claimed the translator was "live and
calling DeepSeek" — that part was true. The 400-error class was
fixed. But a different failure class (mid-JSON truncation) was
running concurrently and was not surfaced.

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
   cn_equivalent + annotation + JSON framing). Observed prod density
   is ~977 tokens/post.
2. **`min(8192, 8192)` makes the cap a constant.** `helper(1)` and
   `helper(100)` both returned 8192.

The 8192 cap was based on an outdated "DS V4 beta max" comment. Live
API probe (2026-08-05) confirmed `max_tokens=65536` is accepted
(HTTP 200). The API ceiling is roughly 65k, not 8k.

## Why the prior fix didn't catch it

The plan `2026-08-04-001` U1 step 2 specified the helper as
`min(8192, max(4096, 200 * n))` and the regression test
`test_translator_max_tokens.py` pinned 8192 at the helper level. The
plan was reviewed and the test was green. Both pin and helper were
buggy in the same direction — the test "passed" by agreeing with
the bug.

When `4d3db60` (the second iteration, post-2026-08-04 followup)
bumped the floor to 8192, the bug became invisible: `max(8192, 200*n)`
clamped to 8192 for every n that mattered, and the test still
asserted 8192.

## Empirical evidence

Loaded 20 prod-typical failing posts (no `text_zh_cn`, real text
content) from the 09:00 cycle. Replayed with the new helper value
against the live DS V4 API:

| Setting | stop_reason | output_tokens | chars | parsed rows |
|---|---|---|---|---|
| `max_tokens=8192` (old) | max_tokens | 8,192 | 30,357 | 0 (mid-JSON cut) |
| `max_tokens=20000` (new) | end_turn | 15,318 | 41,925 | 20/20 with full fields |

## What's done

| Step | Commit | Status | Notes |
|---|---|---|---|
| U1 — diagnose post-002 truncation | (in session) | ✅ done | Found 6 truncations in 9 cycles (06:00–09:00); all len=12134-28283 |
| U2 — helper inspection | (in session) | ✅ done | `min(8192, max(8192, 200*n))` collapses to 8192 |
| U3 — live API probe | (in session) | ✅ done | DS V4 accepts max_tokens=65536 (HTTP 200) |
| U4 — repro on prod posts | (in session) | ✅ done | 20-post live-API repro confirmed truncation at 8192, full at 20000 |
| U5 — fix helper | c09a291 | ✅ done | `min(65536, max(16384, 1000 * n))` |
| U6 — update test pins | c09a291 | ✅ done | 3 new regression pins, all constants updated |
| U7 — push + verify deploy | c09a291 | ✅ done | Render deploy Live at 2026-08-05T09:08:56Z |
| U8 — verify prod coverage | (in session) | ✅ done | 09:15 cycle: 80/80 posts with text_zh_cn (100%); zero translator_batch_failed |
| U9 — write solution doc | (in session) | ✅ done | `docs/solutions/runtime-errors/translator-max-tokens-8192-cap-truncation.md` |
| U10 — amend swap plan | (in session) | ✅ done | U10/U11 sections in `docs/plans/2026-08-04-001-...` |

## Production verification

09:15 UTC cycle (post-deploy):

```sql
SELECT date_trunc('minute', fetched_at), count(*), count(text_zh_cn)
  FROM posts
  WHERE fetched_at >= '2026-08-05 09:15:00+00'
    AND fetched_at < '2026-08-05 09:30:00+00'
  GROUP BY 1;

         minute         | total | with_zh
------------------------+-------+---------
 2026-08-05 09:15:00+00 |    80 |      80   <-- 100% translation rate
```

No `messages_create: LLM returned non-JSON` (except the classifier's
designed `KEEP`/`DROP` no-ops, 4-char responses — those are correct).

## What didn't work

- **Reading the plan comment "DS V4 max is 8192" as authoritative** —
  the comment was wrong, and the test pin was green because it pinned
  the wrong value. Future helper changes need an empirical anchor
  (live API probe), not a comment.
- **Checking only `RuntimeError.*400` for translator health** — the
  400 error class was fixed, but the truncation class was running
  concurrently. The new failure mode is mid-JSON soft-fail, which
  doesn't raise. Always check end-to-end translation rate, not just
  exception count.
- **Comparing `text_zh_cn` rate across hours on the same day** — the
  06:00 cycle already showed 100% post-deploy, but a 4-cycle average
  would have caught the 06:00–09:00 regression. Don't trust a single
  minute's coverage rate.

## Open follow-ups (out of scope)

- **Truncate-then-retry contract.** The fix raises the budget so
  20-post batches finish naturally. If a future batch grows beyond
  65k output tokens, the response will still truncate. Consider a
  defensive split-batch retry once the budget is hit. (No current
  evidence this would trigger — 20-post batches finish at 15k–20k.)
- **`CONCEPTS.md` vocab entry** — "Translator env-vs-yaml precedence"
  (added in handoff 002) should be extended to "Translator output
  budget sizing" with the new formula and the API ceiling.
- **Classifier probe refresh.** The 200 tokens/post coefficient was
  borrowed from the classifier plan but never re-measured for the
  translator. The translator plan should add its own probe (similar
  to `2026-07-15-002` KTD4 but for translation fields).
- **The 4 pre-existing test failures** in `test_translator_pragmatics.py`
  and `test_translator_registry.py` and `test_translation_null_fallback.py`
  are unrelated to this fix (baseline: same failures on clean main with
  this commit stashed). Not regressed.

## How to resume

1. **Check translator health (last 1 hr):**
   ```bash
   ssh fuchitalee 'render psql dpg-d9koekqjobas73fvjqng-a --command "SELECT count(*) FILTER (WHERE text_zh_cn IS NOT NULL), count(*), ROUND(100.0 * count(*) FILTER (WHERE text_zh_cn IS NOT NULL) / count(*)::numeric, 1) FROM posts WHERE fetched_at >= NOW() - INTERVAL '\''1 hour'\''" -o text --confirm'
   ```
2. **Check for translator truncations:**
   ```bash
   ssh fuchitalee 'render logs --resources crn-d9gv94o4n6ts739tqaug --limit 1000 --confirm | grep -E "translator_batch_failed|messages_create: LLM returned non-JSON" | grep -v "len=4" | tail -10'
   ```
3. **Run regression net:**
   ```bash
   cd /Users/fuchitalee/development/pushin-weight-v2 && .venv/bin/python -m pytest tests/test_translator_max_tokens.py -v
   ```
4. **Read the canonical write-up:**
   `docs/solutions/runtime-errors/translator-max-tokens-8192-cap-truncation.md`

## What this session DID NOT do (deferred)

- Did **not** add a CONCEPTS.md entry for "Translator output budget
  sizing". The fix is documented in the solution doc and plan
  amendment; vocab entry can be a follow-up.
- Did **not** add a live-API probe step to the swap plan template.
  The probe recipe (1 curl with max_tokens=65536) should be standard
  in any swap-to-new-LLM plan.
- Did **not** write a defensive split-batch retry for the 65k-cap
  edge case. Not needed today.
