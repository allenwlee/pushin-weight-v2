---
type: handoff
date: 2026-08-05
session: 2026-08-05 (local, M3.0)
plan: docs/plans/2026-08-04-001-swap-translator-to-deepseek-v4-plan.md
issue: https://github.com/allenwlee/pushin-weight-v2/issues/13
branch_when_written: main
last_commit: a46d2de
commits_in_this_handoff:
  - f77cb90 fix(config): env-var override of translator_base_url no longer clobbered by yaml null
  - 4c65eea docs(lessons): document translator env-override clobber bug + vocab entry
  - a46d2de fix(translator): model-name inference must honor X_MONITOR_TRANSLATOR_BASE_URL
related_docs:
  - docs/solutions/runtime-errors/translator-env-override-clobbered-by-yaml-null.md
  - docs/plans/2026-08-04-001-swap-translator-to-deepseek-v4-plan.md
  - CONCEPTS.md (new "Translator env-vs-yaml precedence" section)
  - tests/test_translator_env_override.py
  - tests/test_translator_model_resolution.py
status: translator is live and calling DeepSeek; cron is hung on a separate TwitterAPI B3 fetch issue (out of scope here)
resume_command: "cat docs/handoffs/2026-08-05-002-translator-env-override-fix.md && read it"
blocking_inputs_needed: []
---

# Handoff — Translator env-override fix (commits f77cb90 + a46d2de)

## What was happening

The swap-translator plan (`docs/plans/2026-08-04-001-swap-translator-to-deepseek-v4-plan.md`, dated 2026-08-04) shipped to route the translator from the M3 proxy (`api.minimax.io/anthropic`, truncating 12-50% of batches) to DeepSeek V4 Pro (`api.deepseek.com/anthropic`). The plan covered:

- `LlmConfig.translator_model` default → `deepseek-v4-pro` (U2)
- `_call_with_retry` accepts `thinking` kwarg + per-batch `max_tokens` helper (U1)
- `X_MONITOR_TRANSLATOR_BASE_URL` env-var resolution (U2 step 2)

The plan **landed in code** (commits `02953d6` → `4d3db60` → `8a07a99` over the prior week) and the operator step U3 (set `X_MONITOR_TRANSLATOR_BASE_URL` on the `pushinweight-harvest` cron service) was completed.

On 2026-08-05 the user reported `text_zh_cn` showing NULL in the feed again. Investigation surfaced that the translator was still routing to `api.minimax.io/anthropic` despite the env var being correctly set.

## Root cause — two parallel precedence bugs

The swap plan covered the BASE URL precedence rule but missed the parallel MODEL-NAME precedence rule. Both paths need to consult the translator's per-role override env var (`X_MONITOR_TRANSLATOR_BASE_URL`), not the env-group's stale `ANTHROPIC_BASE_URL` (`api.minimax.io/anthropic`).

### Bug 1 — Base URL precedence (`f77cb90`)

`x_monitor/config.py:load_config:393` had:

```python
merged_llm = {**env_llm_overrides, **raw_llm}  # yaml wins over env
```

YAML's literal `null` deserializes to Python `None`, which the dict spread treats as a valid value, so yaml's `translator_base_url: null` overrode the env-var `X_MONITOR_TRANSLATOR_BASE_URL`. The translator then fell back to `ANTHROPIC_BASE_URL=https://api.minimax.io/anthropic`.

**Fix:** filter nulls from `raw_llm` before the env-merge. New code:

```python
raw_llm_filtered = {
    k: v for k, v in raw_llm.items() if v is not None
}
merged_llm = {**env_llm_overrides, **raw_llm_filtered}  # yaml wins over env (non-null only)
```

### Bug 2 — Model-name inference (`a46d2de`)

After `f77cb90`, the translator's HTTP call **did** route to `api.deepseek.com/anthropic` — but DeepSeek rejected every batch with **400**:

```
RuntimeError: LLM API returned 400: {"error":{"message":"The supported API model names
are deepseek-v4-pro or deepseek-v4-flash, but you passed MiniMax-M3.0.","type":"invalid_request_error"}}
```

`x_monitor/attribution.py:_resolve_translator_model:845` was reading `os.environ.get("ANTHROPIC_BASE_URL")` to decide which model name to send. With the env-group still pointing at `api.minimax.io`, the function returned `"MiniMax-M3.0"` even when the base URL had been correctly switched to DeepSeek.

**Fix:** read `X_MONITOR_TRANSLATOR_BASE_URL` first, falling back to `ANTHROPIC_BASE_URL` — mirroring the role-aware resolution already used by `_resolve_thinking_default(role="translator")`.

## What's done

| Step | Commit | Status | Notes |
|---|---|---|---|
| U0 — pre-exec hygiene | (in session) | ✅ done | git fetch + branch/worktree audit; no parallel-surface collisions |
| U1 — diagnose base-URL bug | (in session) | ✅ done | Found yaml null clobber via `load_config` merge + `ANTHROPIC_BASE_URL` env-group mismatch |
| U2 — fix base-URL precedence | f77cb90 | ✅ done | `x_monitor/config.py:384-397` filters nulls before env-merge |
| U3 — push + verify deploy | f77cb90 | ✅ done | Render deploy Live at 2026-08-05T03:01:31Z (web only — translator still hit 400) |
| U4 — diagnose model-name bug | (in session) | ✅ done | Found `_resolve_translator_model` only reading `ANTHROPIC_BASE_URL` |
| U5 — fix model-name inference | a46d2de | ✅ done | `x_monitor/attribution.py:_resolve_translator_model` reads `X_MONITOR_TRANSLATOR_BASE_URL` first |
| U6 — push + verify deploy | a46d2de | ✅ done | Render deploy Live at 2026-08-05T05:59:50Z; next cron at 06:00:11 succeeded |
| U7 — regression pin tests | f77cb90 + a46d2de | ✅ done | 9 new tests across `test_translator_env_override.py` + `test_translator_model_resolution.py` |
| U8 — amend swap plan | 4c65eea | ✅ done | New U8 (base-URL fix) + U9 (model-name fix) + Live-state audit sections |
| U9 — solution doc + CONCEPTS | 4c65eea | ✅ done | `docs/solutions/runtime-errors/translator-env-override-clobbered-by-yaml-null.md` + CONCEPTS.md new section |
| U10 — verify prod translator | (in session) | ✅ done | DB shows 75 posts at 06:01 with 100% `text_zh_cn` populated |
| U11 — open GitHub issue | (in session) | ✅ done | https://github.com/allenwlee/pushin-weight-v2/issues/13 |

## Production verification

At 06:00 UTC 2026-08-05 (post-deploy of `a46d2de`), the next cron cycle ran. The translator's `_call_with_retry` invoked `messages_create` against DeepSeek successfully — no more `RuntimeError.*400` errors. The post-fetch translation stage populated `text_zh_cn` on 100% of the 75 posts persisted in the 06:01 minute.

```sql
SELECT date_trunc('minute', fetched_at), count(*), count(text_zh_cn)
  FROM posts WHERE fetched_at > now() - interval '15 minutes' GROUP BY 1;

         minute         | total | with_zh
------------------------+-------+---------
 2026-08-05 06:01:00+00 |    75 |      75   <-- 100% translation rate
```

## What didn't work

- **Setting `ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic` on the env-group** — would fix Bug 2 but break the classifier (which uses `X_MONITOR_CLASSIFIER_BASE_URL`). Not the right fix.
- **Setting `X_MONITOR_TRANSLATOR_MODEL=deepseek-v4-pro` on the cron service** — would fix the model name, but introduces a parallel-config surface that drifts from the base URL. Worse than the per-role override.
- **Inspecting `cfg.llm.translator_base_url` via `manage.py shell`** — looked correct (post-`f77cb90`); investigation had to look elsewhere for the model-name path. Both code paths needed separate diagnosis.
- **Reading the swap plan as "the model name just works"** — the plan implicitly assumed `_resolve_translator_model` would honor the new env var, but it didn't. Future swap plans need to audit every env-var-reading function in the touched code path.

## Open follow-ups (out of scope)

- **`pushinweight-secrets` env-group** still has `ANTHROPIC_BASE_URL=https://api.minimax.io/anthropic`. With both the base-URL path (commit `f77cb90`) and the model-name path (commit `a46d2de`) now honoring the per-role override, this env value is redundant for the translator. Consider removing or pointing at DeepSeek as a final cleanup. **Do NOT remove until verifying the classifier still works** — it might use this fallback in some edge case.
- **4/5 deferred work** per `docs/plans/2026-08-04-001`: auto `pack_co_brands(max_len)`, admin UI for policy, auto-regen of `twitterapi-live-queries-by-model.md`, hot-reload policy without deploy.
- **`pushinweight-harvest` cron hung on B3 fetch** as of 06:09 UTC. Unrelated to translator fix (TwitterAPI call hung on SSL read, per repo memory). 75 posts in the same cycle were translated successfully. Will resolve on the next 15-min cron tick.

## How to resume

If the user wants to follow up:

1. **Check that translator is still healthy:**
   ```bash
   ssh fuchitalee "render logs --resources crn-d9gv94o4n6ts739tqaug --limit 200 | grep -E 'Cron job run started|translator_batch_failed|RuntimeError.*400' | tail -10"
   ```
2. **Check 1-hour cohort translation rate:**
   ```bash
   ssh fuchitalee 'render psql dpg-d9koekqjobas73fvjqng-a --command "SELECT count(*) FILTER (WHERE text_zh_cn IS NOT NULL), count(*), ROUND(100.0 * count(*) FILTER (WHERE text_zh_cn IS NOT NULL) / count(*)::numeric, 1) FROM posts WHERE fetched_at >= NOW() - INTERVAL '\''1 hour'\''" -o text --confirm'
   ```
3. **Run the new regression tests:**
   ```bash
   ssh fuchitalee 'cd /Users/fuchitalee/development/pushin-weight-v2 && PY=$(pwd)/.venv/bin/python; $PY -m pytest tests/test_translator_env_override.py tests/test_translator_model_resolution.py -v'
   ```
4. **Read the canonical write-up:** `docs/solutions/runtime-errors/translator-env-override-clobbered-by-yaml-null.md`
5. **Read the plan amendment:** `docs/plans/2026-08-04-001-swap-translator-to-deepseek-v4-plan.md` (sections U8, U9, Live-state audit)
6. **Read the vocab entry:** `CONCEPTS.md` (section "Translator env-vs-yaml precedence")

## What this session DID NOT do (deferred)

- Did **not** commit the model-name fix to the plan amendment — the plan was amended at `4c65eea` with the base-URL fix only. The model-name bug (`a46d2de`) is a parallel fix that surfaced *after* the plan amendment. Consider amending the plan again with a U10 section if you want full symmetry.
- Did **not** write a regression test for the prod race where `ANTHROPIC_BASE_URL` is set after `X_MONITOR_TRANSLATOR_BASE_URL` (they're both consulted; ordering matters). The 5 tests in `test_translator_model_resolution.py` cover the static precedence but not the race.
- Did **not** clean up the redundant `ANTHROPIC_BASE_URL=https://api.minimax.io/anthropic` env-group entry. Mentioned above as a follow-up.