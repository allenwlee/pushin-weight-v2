---
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
execution: code
title: "feat: swap translator to DeepSeek V4 (lift M3 proxy-side response cap)"
created: 2026-08-04
amended: 2026-08-05
amendment_note: "U8 fixes a load_config merge bug where yaml `translator_base_url: null` silently overrode the env-var X_MONITOR_TRANSLATOR_BASE_URL. Translator was hitting MiniMax with a DS V4 model name -> silent socket timeout -> text_zh_cn NULL for 6+ hours. U9 adds a regression pin. Captured in this amendment per user directive. Skill: avoiding-recurring-mistakes M12 (default-model assumption) — the swap shipped the model default without verifying the runtime base URL actually changed."
target_repo: pushin-weight-v2
origin:
  - docs/plans/2026-07-15-002-feat-swap-classifier-to-deepseek-v4-plan.md
  - docs/plans/2026-08-01-002-harvester-best-practices-followup.md
product_contract_source: ce-plan-bootstrap
---

# feat: swap translator to DeepSeek V4 (lift M3 proxy-side response cap)

## Summary

The translator (`x_monitor/translator.py`) currently uses MiniMax M3 via `api.minimax.io/anthropic`. M3 has a hard **proxy-side response cap of ~890-1800 output tokens** that `max_tokens` cannot lift. 12-50% of translator batches fail with truncated JSON mid-response, leaving `lang_detected` NULL on 30-50% of recent prod posts.

This plan replicates the **classifier swap recipe** from `docs/plans/2026-07-15-002-feat-swap-classifier-to-deepseek-v4-plan.md` (which itself landed cleanly in commit `8a07a99`) for the translator path: route through `api.deepseek.com/anthropic` + `deepseek-v4-pro` + `thinking={"type": "disabled"}` + per-batch `max_tokens` sized to batch size.

**Intended outcome:** `lang_detected` coverage on fresh posts recovers from ~36% to ≥ 95%, matching the classifier's post-swap coverage (per plan 2026-07-15-002 R4 / KTD4 evidence: DS V4 emits valid production-shape JSON at batch_size=20 in ~20s).

## Problem Frame

### Three independent lines of evidence on the M3 cap

1. **Today, prod Render cron `crn-d9gv94o4n6ts739tqaug`:** the 06:20 cycle truncated at `len=7244` bytes (~1800 tokens) with `max_tokens=16384` live (commit `02953d6` deployed at 05:46 UTC). `max_tokens` did not lift the cap. The `parse_llm_response` helper correctly rejects truncated JSON; `translate_batch` marks the batch as `translation_failed=True`; `lang_detected` stays NULL for every tweet in the batch.

2. **Plan 2026-07-15-002 (KTD3, R4 evidence):** "M3's 890-token output cap silently truncates anything beyond ~5 posts"; "all max_tokens values (256, 512, 1024, 2048, 4096) timed out at the same column on the M3 path"; "the 8,192-token per-prompt cap on M3 is a real artifact but not the proximate cause of the 890-token truncation; the 890 number is a different proxy-side cap on the response envelope".

3. **Plan 2026-07-15-002 successful swap evidence:** "DeepSeek V4 Pro (via `api.deepseek.com/anthropic` with `thinking={"type": "disabled"}`) emits valid production-shape JSON at batch_size=20 in ~20 seconds, but it hits the `max_tokens=4096` ceiling at batch_size=40 and 80". DS V4 has no proxy-side cap; the 4096-token ceiling is the model's actual limit, and it lifts cleanly to 8192 for larger batches.

### M3 cap and 8K-limit

**Important correction from prior conversation:** the MiniMax M3 docs say M3 supports up to 128K-512K output tokens, and we initially read the M3 cap as a "max_tokens" issue that bumping to 16384 would resolve. The 2026-07-15-002 evidence shows the cap is a **proxy-side response envelope** (hard ~890-1800 tokens), not the model-side limit. DS V4's actual model-side cap is 8K output tokens (per its API docs), so the swap also gives us less than the M3 docs suggest, but enough to clear the proxy cap that's biting us.

### Why the 2026-07-15-002 plan was classifier-only

That plan's "Out of scope" section explicitly states: *"Translator path (`x_monitor/translator.py`) — uses its own client copy and its own retry block. Not part of this swap. The translator still hits MiniMax M3 by default; the smoke probe does not exercise it."* This plan closes that gap with the same recipe.

## Requirements

- **R1.** `_call_with_retry` in `x_monitor/translator.py` MUST call `messages_create` with `thinking={"type": "disabled"}` when the base URL is `api.deepseek.com`, mirroring `_resolve_thinking_default()` in `x_monitor/attribution.py:805`.
- **R2.** The translator's effective base URL MUST route to `https://api.deepseek.com/anthropic` (or operator-overridable via `X_MONITOR_TRANSLATOR_BASE_URL`), not `https://api.minimax.io/anthropic`. The `pushinweight-secrets` env group is updated accordingly.
- **R3.** `LlmConfig.translator_model` default changes from `minimax/MiniMax-M3.0[1m]` to `deepseek-v4-pro`. Existing `tests/test_llm_config.py` defaults-pin MUST be updated to match.
- **R4.** Per-batch `max_tokens` MUST be sized to the batch: `min(8192, max(4096, 200 * len(tweets)))`, mirroring the classifier's helper. At default `_TRANSLATION_BATCH_SIZE=20`, this evaluates to 4096 (matches plan 2026-07-15-002 KTD4 evidence: 1975 tokens used at batch_size=20 with 50% budget headroom). At batch_size=10, it evaluates to 4096; at batch_size=40, it evaluates to 8000.
- **R5.** The translator's `messages_create` call must include the resolved `thinking` parameter (DS V4 needs `{"type": "disabled"}` explicitly threaded; M3 ignores the parameter). The existing `test_translator_max_tokens.py` test is updated to assert both `max_tokens` AND `thinking` are present in the call.
- **R6.** Existing `tests/test_translator.py`, `tests/test_translator_pragmatics.py`, `tests/test_translator_logging.py` MUST continue to pass without semantic changes. The 2 pre-existing failures (`test_translate_batch_pragmatics_returns_four_prongs`, `test_translate_batch_pragmatics_text_zh_cn_null_when_lang_is_already_zh`) reproduce on the older `fix/harvester-lang-detected` branch without these changes — they are unrelated, will remain deselected per the 2026-08-01-001 / 2026-08-01-002 history, and are out of scope here.
- **R7.** Live verification: after deploy, the next 1-hour cohort shows `lang_detected` coverage ≥ 95% (vs. the 30-50% baseline). No `len=large` (9K-12K bytes / 1800+ tokens) truncation signatures in the cron log.
- **R8.** One commit on `main` with the `Scope delivered vs plan promised: match` footer. No out-of-scope files modified.

## Key Technical Decisions

- **KTD1. Replicate the classifier-swap recipe exactly, not redesign it.** *(session-settled: user-directed — chosen over "design a new translator-specific recipe": the classifier swap shipped clean in commit `8a07a99` and was probed against the same batch size; reusing the recipe eliminates a re-probe cycle and the env-var routing machinery is already in place. Variations are deferred to follow-ups.)* Pattern: `https://api.deepseek.com/anthropic` + `deepseek-v4-pro` + `thinking={"type": "disabled"}` + per-batch `max_tokens = min(8192, max(4096, 200 * len(tweets)))`.

- **KTD2. Keep `_TRANSLATION_BATCH_SIZE=20`.** *(session-settled: user-aligned with classifier-swap choice — chosen over "drop to 10 to give DS V4 more headroom per batch": the classifier plan shipped with batch_size=20 and DS V4 handled it at 4096 tokens with 50% headroom. Plan 2026-07-15-002 KTD4 evidence shows 1975 tokens used at batch_size=20. Doubling the LLM call count would multiply cost without evidence of need.)* Per-batch `max_tokens` sized via the helper handles any future batch size change.

- **KTD3. Thread `thinking` through `_call_with_retry` as an explicit kwarg, not env-derived at call site.** *(session-settled: user-aligned with plan 2026-07-15-002 KTD3 — chosen over "resolve thinking inside `_call_with_retry`": a kwarg matches the existing `_call_signal_with_retry` signature and keeps the test seam clean. `_resolve_thinking_default()` is imported from `x_monitor.attribution.py` and used the same way.)*

- **KTD4. Drop the 60-second SDK timeout to no lower than 120 seconds.** *(session-settled: technical-decision — chosen over "leave 60s as-is": today, the 60s SDK timeout occasionally fires before the LLM finishes a 4096-token output. DS V4 at batch_size=20 takes ~20s; doubling the budget gives comfortable headroom. Bumping to 180s is over-budget for a model that should never need it.)* Set `kwargs.setdefault("timeout", 120.0)` in `AnthropicClaudeClient.__init__`. (Comment in the existing code at line 936 already cites the "M3 returns ~890 tokens in <10s; DS V4 in <5s" historical claim — that comment is updated to reflect the new timeout rationale.)

- **KTD5. Add `X_MONITOR_TRANSLATOR_BASE_URL` env-var resolution to `LlmConfig`.** *(session-settled: aligns with plan 2026-08-01-002 U2/U6 which already specified this field — chosen over "operator edits the env-group's `ANTHROPIC_BASE_URL`": the translator and classifier need different base URLs (DS V4 vs MiniMax proxy) and `ANTHROPIC_BASE_URL` is shared. `X_MONITOR_TRANSLATOR_BASE_URL` is the per-role override. The `pushinweight-secrets` env group is updated to set `X_MONITOR_TRANSLATOR_BASE_URL=https://api.deepseek.com/anthropic`.)*

- **KTD6. Update `LlmConfig.translator_model` default to `deepseek-v4-pro`.** *(session-settled: technical-decision — chosen over "leave default as M3 and force operator to set env-var": the M3 default is the bug surface. Updating the default prevents operator-onboarding mistakes where a fresh install defaults to the broken path. Existing operators who set `X_MONITOR_TRANSLATOR_MODEL=minimax/MiniMax-M3.0[1m]` keep M3.)*

- **KTD7. No new `LlmConfig` field for `thinking_disabled` — reuse `X_MONITOR_*_THINKING` env-vars if the classifier ever needs operator override.** *(technical-decision — chosen over "add `thinking_disabled: bool = True` to LlmConfig": a bool is a coarse knob; the `thinking` parameter is a dict (`{"type": "disabled"}` or `{"type": "enabled"}` for some models). Mirroring the classifier's per-base-URL resolution keeps the seam tight. If a future model needs operator-overridable thinking, add the env-var at that time.)*

- **KTD8. Plan ships with NO `x_monitor/quote_tweets.py` changes.** *(technical-decision — chose over "also update quote_tweets": the `quote_tweets` path uses its own env-derived client; per plan 2026-08-01-002 it was out of scope for the original Config.llm plumbing and is independently operator-overridable. Adding it here widens scope without evidence of need.)*

## File Structure

- `x_monitor/translator.py` — thread `thinking` kwarg through `_call_with_retry` (line 162-191); update per-batch `max_tokens` helper (new helper at line ~155); update timeout comment in `AnthropicClaudeClient.__init__` (line 936).
- `x_monitor/config.py` — change `LlmConfig.translator_model` default (line 160-163) from `minimax/MiniMax-M3.0[1m]` to `deepseek-v4-pro`; add `X_MONITOR_TRANSLATOR_BASE_URL` env-var resolution in the `model_validator` (around line 387).
- `x_monitor/attribution.py` — no code change; reuse existing `_resolve_thinking_default()` helper (line 805).
- `monitor/cycle.py` — no code change; the existing `build_translator_client_from_env(cfg)` call site at line ~1253 already passes `self.cfg`, which now carries the new `translator_model` and `translator_base_url` from `LlmConfig`.
- `tests/test_llm_config.py` — update the default-pin test for `translator_model` (currently asserts `minimax/MiniMax-M3.0[1m]`); add a default-pin for `translator_base_url` resolution.
- `tests/test_translator_max_tokens.py` — extend the existing pin (currently asserts `max_tokens=16384`) to also assert `thinking={"type": "disabled"}` is passed; update the value to the new per-batch helper.
- `tests/test_translator.py::FakeClaudeClient` — no semantic change; it already accepts arbitrary kwargs in `messages_create`.

**Env-group change (operator step, not a code change):** update `pushinweight-secrets` on Render to set `X_MONITOR_TRANSLATOR_BASE_URL=https://api.deepseek.com/anthropic` on the `pushinweight-harvest` cron service. The existing `DEEPSEEK_API_KEY` already in the env group is reused; no new credential needed.

## Implementation Units

### U1. Add `thinking` parameter and per-batch `max_tokens` helper to translator's `_call_with_retry`

**Goal.** Thread `thinking={"type": "disabled"}` (resolved per-base-URL via `_resolve_thinking_default()`) through `_call_with_retry` and replace the hardcoded `max_tokens=4096` with a per-batch helper `min(8192, max(4096, 200 * len(tweets)))`.

**Files.**
- Modify: `x_monitor/translator.py` lines 162-195 (`_call_with_retry`)

**Approach.**
1. Import `_resolve_thinking_default` from `.attribution` at the top of the function (mirroring the existing `_resolve_translator_model` import at line 179).
2. Accept a new `thinking: dict | None` parameter on `_call_with_retry`, defaulting to `_resolve_thinking_default()`.
3. Compute `max_tokens` via a new module-level helper `_max_tokens_for_batch_size(n: int) -> int` returning `min(8192, max(4096, 200 * n))`. Inline call to `max_tokens=_max_tokens_for_batch_size(len(tweets))`.
4. Pass both `thinking=thinking` and `max_tokens=...` into `client.messages_create(...)`.
5. Update the docstring to reflect the new kwarg.
6. **M11 fix:** the existing `max_tokens=16384` comment at `x_monitor/translator.py:184-187` references `docs/plans/2026-08-04-002-bump-translator-max-tokens.md` — a plan file that does not exist (the change was committed as `02953d6` without a plan doc). Replace the comment with: per-batch sizing now done by the new helper; reference the actual commit `02953d6` and this plan.

**Patterns to follow.** `_call_signal_with_retry` in `x_monitor/attribution.py:1953-1985` already threads `thinking` + `max_tokens`; the same shape applies here.

**Test scenarios.**
- Calling `_call_with_retry` with `ANTHROPIC_BASE_URL` set to `https://api.deepseek.com/anthropic` produces a `messages_create` call with `thinking={"type": "disabled"}` and `max_tokens=4096` (when len(tweets) <= 20).
- Calling with `ANTHROPIC_BASE_URL` set to `https://api.minimax.io/anthropic` produces NO `thinking` kwarg (M3 ignores it; the param is omitted from the SDK call per plan 2026-07-15-002 KTD3 default-application rule).
- The new `_max_tokens_for_batch_size(40)` returns 8000; `_max_tokens_for_batch_size(80)` returns 8192 (capped).
- Existing `tests/test_translator.py::test_translate_batch_*` continue to pass without modification (the `FakeClaudeClient` records all kwargs; the new kwargs are added but no existing test asserts on their absence).

**Verification.** `pytest tests/test_translator.py -v` green. `pytest tests/test_translator_max_tokens.py -v` green after the U2 update.

### U2. Update `LlmConfig.translator_model` default + add `X_MONITOR_TRANSLATOR_BASE_URL` resolution

**Goal.** Change `LlmConfig.translator_model` default from `minimax/MiniMax-M3.0[1m]` to `deepseek-v4-pro`. Add an `X_MONITOR_TRANSLATOR_BASE_URL` env-var path through `load_config()`'s `model_validator(mode="before")` so the translator's base URL can be set independently of `ANTHROPIC_BASE_URL` (which the classifier still uses for DS V4 routing per the env group's `X_MONITOR_CLASSIFIER_BASE_URL`).

**Files.**
- Modify: `x_monitor/config.py` lines 160-163 (default change); lines 380-400 (`model_validator` env-var resolution block)

**Approach.**
1. Change `LlmConfig.translator_model: str = Field(default="minimax/MiniMax-M3.0[1m]", ...)` to `default="deepseek-v4-pro"`. Update the docstring to point to plan 2026-08-04-001.
2. In the `model_validator(mode="before")` block (around line 380-400), extend the existing `translator_model` env-var resolution to also resolve `X_MONITOR_TRANSLATOR_BASE_URL` into `raw_dict["llm"]["translator_base_url"]` when not already in the yaml. Existing yaml-wins-over-env rule preserved.

**Patterns to follow.** Same shape as the existing `X_MONITOR_TRANSLATOR_MODEL` resolution at line 387. Existing `translator_base_url: str | None = Field(default=None, ...)` field at line 164 stays — env resolution populates it.

**Test scenarios.**
- `Config()` (no env) yields `cfg.llm.translator_model == "deepseek-v4-pro"` (new default) and `cfg.llm.translator_base_url is None`.
- `monkeypatch.setenv("X_MONITOR_TRANSLATOR_MODEL", "custom-model")` then `Config()` yields `cfg.llm.translator_model == "custom-model"`.
- `monkeypatch.setenv("X_MONITOR_TRANSLATOR_BASE_URL", "https://api.deepseek.com/anthropic")` then `Config()` yields `cfg.llm.translator_base_url == "https://api.deepseek.com/anthropic"`.
- `Config({"llm": {"translator_model": "from-yaml"}})` loads with the yaml value (yaml wins over env).

**Verification.** `pytest tests/test_llm_config.py -v` green after the U4 update.

### U3. Update `pushinweight-secrets` env group with `X_MONITOR_TRANSLATOR_BASE_URL` (operator step)

**Goal.** Wire the translator to the DS V4 endpoint on Render. The env group is shared, so this is an operator-level change on the `pushinweight-harvest` cron service.

**Approach.**
1. On Render dashboard, edit the `pushinweight-secrets` env group (or add a service-level env var on `pushinweight-harvest`) to set `X_MONITOR_TRANSLATOR_BASE_URL=https://api.deepseek.com/anthropic`.
2. No `DEEPSEEK_API_KEY` change needed — the existing credential in the env group works for both classifier and translator (DS V4 is the model on both paths post-swap).
3. Verify: next cycle logs include a successful `messages_create` call to `api.deepseek.com/anthropic` for the translator path (vs. the prior `api.minimax.io/anthropic`).

**Test scenarios.** Not a code test; verified via prod cycle log inspection and prod DB query.

**Verification (per M5 — verification as retrofit, every operator step names its verification query).** Run the next cron cycle, then execute:
- `render logs --resources crn-d9gv94o4n6ts739tqaug --start <post-deploy-utc> --output text | grep -E "translator_batch_failed|messages_create.*translator"` — expect `0` truncation failures, expect `api.deepseek.com` in the base URL.
- `PGPASSWORD=... psql -h dpg-d9koekqjobas73fvjqng-a.oregon-postgres.render.com -U pushinweight_shadow -d pushinweight_shadow -t -A -c "SELECT count(*) FILTER (WHERE fetched_at >= NOW() - INTERVAL '1 hour' AND lang_detected IS NOT NULL), count(*) FILTER (WHERE fetched_at >= NOW() - INTERVAL '1 hour'), ROUND(100.0 * count(*) FILTER (WHERE fetched_at >= NOW() - INTERVAL '1 hour' AND lang_detected IS NOT NULL)::numeric / NULLIF(count(*) FILTER (WHERE fetched_at >= NOW() - INTERVAL '1 hour'), 0), 1) FROM posts;"` — expect ratio ≥ 95%.

### U4. Update regression net `test_translator_max_tokens.py` for new helper + thinking kwarg

**Goal.** Pin the new per-batch `max_tokens` helper and the new `thinking` kwarg in a regression net. Existing test pinned `max_tokens=16384` (the bump from 4096) — that test now needs to assert the new helper's output AND the presence of `thinking` when routed to DS V4.

**Files.**
- Modify: `tests/test_translator_max_tokens.py` (the regression net landed 2026-08-04 in commit `02953d6`)

**Approach.**
1. Update the existing `EXPECTED_MAX_TOKENS` constant to `4096` (the new per-batch default for `_TRANSLATION_BATCH_SIZE=20`).
2. Add a new test `test_translator_threads_thinking_disabled_to_deepseek` that monkeypatches `ANTHROPIC_BASE_URL` to `https://api.deepseek.com/anthropic`, calls `translate_batch` with a 5-tweet input, and asserts the captured `thinking` kwarg is `{"type": "disabled"}` AND `max_tokens` is 4096 (the helper's output for n=5).
3. Add a new test `test_translator_omits_thinking_for_minimax` that monkeypatches `ANTHROPIC_BASE_URL` to `https://api.minimax.io/anthropic` and asserts the captured `thinking` kwarg is absent (None).
4. Update the file-header docstring to reflect the new contract: `max_tokens` is now derived from batch size; `thinking` is base-URL-dependent.
5. The BEFORE comments in assertions explain the chain: 4096-token M3 cap → bump to 16384 (commit `02953d6`) → swap to DS V4 lifts the proxy cap → per-batch helper at 4096 is the new contract (proven at batch_size=20 by plan 2026-07-15-002 evidence).

**Patterns to follow.** `test_translator_max_tokens.py` file already has the right style (file-header docstring, `EXPECTED_*` constant, `assert ..., "BEFORE: ..."`).

**Test scenarios.**
- All 4 existing assertion paths still pass after the constant update.
- `test_translator_threads_thinking_disabled_to_deepseek` passes on the fixed code, fails on the pre-fix code (no `thinking` was threaded).
- `test_translator_omits_thinking_for_minimax` passes on the fixed code, fails on the pre-fix code (thinking is now omitted for M3, but the pre-fix code passed it unconditionally — verify by reading the captured kwarg set).

**Verification.** `pytest tests/test_translator_max_tokens.py -v` green.

### U5. Update `tests/test_llm_config.py` default pin for new `translator_model`

**Goal.** The existing default-pin test for `LlmConfig.translator_model` asserts `cfg.llm.translator_model == "minimax/MiniMax-M3.0[1m]"` — that assertion is now wrong and must update to `"deepseek-v4-pro"`. The pin exists to catch silent drift; updating the pin is part of the contract change, not a regression.

**Files.**
- Modify: `tests/test_llm_config.py` (find the existing pin test for `translator_model`)

**Approach.**
1. Update the existing assertion from `"minimax/MiniMax-M3.0[1m]"` to `"deepseek-v4-pro"`.
2. Add a BEFORE comment in the assertion: "BEFORE: `minimax/MiniMax-M3.0[1m]` was the v1 + v2 default; swapped to `deepseek-v4-pro` on 2026-08-04 to lift the M3 proxy-side response cap (plan 2026-08-04-001). Operators who want M3 back set `X_MONITOR_TRANSLATOR_MODEL=minimax/MiniMax-M3.0[1m]`."
3. Add a new default-pin for `translator_base_url` resolution (env → cfg field).

**Patterns to follow.** Existing `test_llm_config_defaults_match_v1_translator_model` style (file-header docstring + `EXPECTED_*` constant + BEFORE comment).

**Test scenarios.**
- Existing test updated to pass with the new default.
- New env-override test: `monkeypatch.setenv("X_MONITOR_TRANSLATOR_BASE_URL", "...")` populates `cfg.llm.translator_base_url`.
- New yaml-wins test: `Config({"llm": {"translator_model": "from-yaml"}})` keeps the yaml value.

**Verification.** `pytest tests/test_llm_config.py -v` green.

## Live-state audit (2026-08-05) — yaml null silently overrode env

Investigation of the `text_zh_cn` regression surfaced this drift:

- Translator traceback hits `api.minimax.io/anthropic` (the M3 proxy), not `api.deepseek.com/anthropic`.
- Service-level env on `pushinweight-harvest` correctly has `X_MONITOR_TRANSLATOR_BASE_URL=https://api.deepseek.com/anthropic`.
- `load_config` merge code at `x_monitor/config.py:384-394`:
  ```python
  merged_llm = {**env_llm_overrides, **raw_llm}  # yaml wins over env
  ```
- `config.yaml` has `llm.translator_base_url: null` (the original M3 fallback instruction).
- YAML's `null` is a real Python `None`, which OVERWRITES the env value in the dict spread. `cfg.llm.translator_base_url` ends up `None`, so `build_translator_client_from_env` falls through to `ANTHROPIC_BASE_URL=https://api.minimax.io/anthropic`.

Net effect: the swap plan shipped model default `deepseek-v4-pro` + env-var resolution code, BUT the env override never reached `cfg.llm.translator_base_url` because yaml `null` was treated as "set". MiniMax got the DS V4 model name, timed out the socket read silently, every cycle produced `text_zh_cn IS NULL`.

This is the canonical "drift in the env-vs-yaml precedence rule" failure mode the swap plan's U2 step 2 should have caught but didn't: "yaml wins over env" is true for non-null values; `null` is an explicit instruction to use the default fallback, not "yaml wins".

### U8. Filter yaml null from the env-merge so operator env vars take effect

**Goal.** `cfg.llm.translator_base_url` honors `X_MONITOR_TRANSLATOR_BASE_URL` when yaml has `translator_base_url: null`. Operators pin the fallback intentionally; the env override is the actual production path.

**Files.**
- Modify: `x_monitor/config.py` lines 384-397 (`load_config` env-merge block).

**Approach.**
1. After building `raw_llm = raw.get("llm", {})`, also build `raw_llm_filtered = {k: v for k, v in raw_llm.items() if v is not None}`.
2. Merge env into the filtered dict: `merged_llm = {**env_llm_overrides, **raw_llm_filtered}`.
3. Comment update: replace the `# yaml wins over env` with `# yaml wins over env (non-null only)` and a paragraph explaining the bug.

**Test scenarios.**
- yaml `translator_base_url: null` + env `X_MONITOR_TRANSLATOR_BASE_URL=https://api.deepseek.com/anthropic` -> `cfg.llm.translator_base_url == "https://api.deepseek.com/anthropic"`.
- yaml `translator_base_url: https://api.deepseek.com/anthropic` + env `X_MONITOR_TRANSLATOR_BASE_URL=https://api.minimax.io/anthropic` -> yaml wins (non-null).
- yaml `translator_base_url: null` + no env -> `cfg.llm.translator_base_url is None` (fallback path).
- yaml has no `llm:` block at all + env -> env takes effect.

**Verification (M5).**
- `pytest tests/test_translator_env_override.py -v` green (4 cases).
- After deploy: next cron cycle logs `messages_create` to `api.deepseek.com/anthropic` (not `api.minimax.io/anthropic`).
- 1-hour cohort `lang_detected` coverage ≥ 95%.

### U9. Regression net for env-vs-yaml precedence in `load_config`

**Goal.** Future drift in the merge logic fails loudly instead of silently overwriting the translator's base URL.

**Files.**
- New: `tests/test_translator_env_override.py` (pinned 2026-08-05 with the U8 fix).

**Approach.**
1. The test file covers the 4 scenarios from U8's Test scenarios section.
2. File header documents the prod incident in a `Why this file exists` section.
3. Test assertions include the BEFORE state in the failure message (mirroring the `BEFORE` style from `test_harvest_surface_regression_net.py`).

**Verification.** `pytest tests/test_translator_env_override.py -v` green.

## Out of Scope

- `monitor/quote_tweets.py` — has its own env-derived client; was out of scope for plan 2026-08-01-002 U2 and stays out of scope here.
- `x_monitor/reattribute.py` — the per-post reattribute path; uses a different env-var routing path. Plan 2026-08-01-002 U2 left it alone; this plan does the same.
- The pre-existing failures in `tests/test_translator_pragmatics.py` (`test_translate_batch_pragmatics_returns_four_prongs` and `test_translate_batch_pragmatics_text_zh_cn_null_when_lang_is_already_zh`) — these are the noop-coercion regressions reproduced on the older `fix/harvester-lang-detected` branch without these changes. Out of scope; deselected per the 2026-08-01-001 / 2026-08-01-002 history.
- Increasing the SDK timeout beyond 120s — DS V4 at batch_size=20 takes ~20s per the classifier plan probe data; 120s gives 6x headroom. Bumping higher is over-budget.
- Adding `thinking_disabled: bool` to `LlmConfig` — the param is a dict, not a bool; per-base-URL resolution via `_resolve_thinking_default()` is sufficient.

## Deferred to Follow-Up Work

- Drop the M3 client construction entirely (30-day follow-up per plan 2026-07-15-002 OQ3) if DS V4 stays stable. The M3 code is kept for rollback until the deprecate point.
- The remaining 12-50% of translator batches that fail for other reasons (60s SDK timeout, network blips) once the proxy cap is lifted. Watch the next 24-48h of cron logs for any residual failure modes.
- The 2 pre-existing test failures in `test_translator_pragmatics.py` — separate bug in the noop-coercion logic; not in scope here.
- Per-operator-tunable `thinking` mode (some operators may want `adaptive` for non-translation paths). Add `LlmConfig.thinking_disabled: bool` only if a concrete operator asks for it.

## Risks & Mitigations

- **Risk:** DS V4 has different latency characteristics than M3; 60s SDK timeout may now fire on rich batches. **Mitigation:** KTD4 bumps timeout to 120s, mirroring the headroom the classifier plan documents. If still too tight, follow-up U1F can bump to 180s.

- **Risk:** A bad swap could leave the translator producing unparseable JSON in a new way (DS V4 might emit a different shape on edge cases). **Mitigation:** `parse_llm_response` (commit `6fc7c39`) soft-fails to `{"results": []}` on parse failure, which `translate_batch._parse_response` already handles by marking the batch as `translation_failed=True`. Worst case: a few cycles of empty batches; no data corruption.

- **Risk:** Operators who set `X_MONITOR_TRANSLATOR_MODEL=minimax/MiniMax-M3.0[1m]` keep M3 by default. If they don't also set `X_MONITOR_TRANSLATOR_BASE_URL=https://api.minimax.io/anthropic`, the translator falls into the M3 default base URL. **Mitigation:** Keep the existing `ANTHROPIC_BASE_URL` resolution as the default. KTD5 ensures `X_MONITOR_TRANSLATOR_BASE_URL` is the override, but if unset, `ANTHROPIC_BASE_URL` resolves to `api.minimax.io/anthropic` for the M3 path — same as today.

- **Risk:** DS V4 API rate limits at higher traffic than M3 (200+ posts/cycle × 4-8 LLM calls/cycle). **Mitigation:** DS V4's per-token pricing is similar to M3 (per plan 2026-07-15-002 cost analysis); the swap was already proven at 200+ posts/cycle on the classifier path. No new risk.

## Verification Contract

- `pytest tests/test_translator_max_tokens.py tests/test_translator.py tests/test_translator_pragmatics.py tests/test_translator_logging.py tests/test_llm_config.py tests/test_llm_response_parser_regression_net.py -v` — all green. The 2 pre-existing failures in `test_translator_pragmatics.py` are deselected (unrelated to this change, reproduced on the older `fix/harvester-lang-detected` branch).
- `pytest tests/ -k "not requires_postgres"` — full sweep minus postgres-only tests.
- Live: push to main; wait for Render auto-deploy; observe the next 1-2 cron cycles via `render logs --resources crn-d9gv94o4n6ts739tqaug`.
- Live DB query: `SELECT count(*) FILTER (WHERE fetched_at >= NOW() - INTERVAL '1 hour' AND lang_detected IS NOT NULL), count(*) FILTER (WHERE fetched_at >= NOW() - INTERVAL '1 hour') FROM posts` returns ratio ≥ 95%.
- No `len=large` (9K-12K bytes / 1800+ tokens) truncation signatures in the post-deploy cron log window.
- Sandbox (per 2026-08-04 U2 followup): `python sandbox_translate.py 20 /tmp/posts.csv` against the new code shows `lang_detected: 20 / 20 (100%)`, `translation_failed: 0`, and `thinking` kwarg present in the captured `messages_create` call.

## M-Rule Audit (from `avoiding-recurring-mistakes` skill)

| M-rule | Status | Notes |
|---|---|---|
| M1 — Re-derive settled decisions | ✅ Pass | Plan reads `LlmConfig` defaults from current `x_monitor/config.py:160-163`; doesn't re-derive. No AGENTS.md/CONCEPTS.md in target repo to re-derive from. |
| M5 — Verification as retrofit | ✅ Now covered | U3's verification section now names the exact `render logs` and `psql` queries (was missing before this audit). |
| M7 — Re-inventing harvest/cycle | ✅ Pass | KTD1 explicitly says "Replicate the classifier-swap recipe exactly, not redesign it." |
| M8 — Rate/concurrency guards | ✅ Already in place | Single-cycle runner with `_max_llm_calls` per-batch cap (`monitor/cycle.py:824`); no concurrent LLM calls today. DS V4 swap doesn't change the call shape (1 call per 20-tweet batch, 4-7 calls per cycle), so no new guard needed. |
| M11 — Reference-doc remnants | ✅ Will fix at execution | The pre-existing `max_tokens=16384` comment at `x_monitor/translator.py:184-187` references `docs/plans/2026-08-04-002-bump-translator-max-tokens.md` — that plan file does not exist; the change was just commit `02953d6`. U1 updates the comment to reference the actual commit and this plan. |
| M12 — Default-model assumption | ✅ Already in place | `_call_with_retry` resolves the model name explicitly via `_resolve_translator_model(cfg)` (line 179-180, line 184) — never falls back to a default. The swap changes the resolved value (DS V4 instead of M3), not the resolution mechanism. |
| M14 — Off-convention plan filename | ✅ Pass | Plan at `docs/plans/2026-08-04-001-swap-translator-to-deepseek-v4-plan.md` — date + serial + kebab-slug. |
| M16 — Inventing API surface | ✅ Pass | DS V4 max_tokens=8192 sourced from context7 docs; M3 cap sourced from plan 2026-07-15-002 probe data. |

## Definition of Done

- [ ] U1 lands: `_call_with_retry` accepts `thinking` kwarg; per-batch `max_tokens` helper wired
- [ ] U2 lands: `LlmConfig.translator_model` default → `deepseek-v4-pro`; `X_MONITOR_TRANSLATOR_BASE_URL` resolution in `model_validator`
- [ ] U3 lands: `pushinweight-secrets` env group updated with `X_MONITOR_TRANSLATOR_BASE_URL=https://api.deepseek.com/anthropic` (operator step)
- [ ] U4 lands: `tests/test_translator_max_tokens.py` updated with thinking pin and per-batch helper pin
- [ ] U5 lands: `tests/test_llm_config.py` default pin updated to `deepseek-v4-pro` with BEFORE comment
- [ ] All pytest gates green
- [ ] Live: 1h prod DB `lang_detected` coverage ≥ 95%
- [ ] Live: no `len=large` truncation in cron log
- [ ] One commit on main with `Scope delivered vs plan promised: match` footer
- [ ] No out-of-scope files modified (verified via `git diff --stat` showing only `x_monitor/translator.py`, `x_monitor/config.py`, `tests/test_translator_max_tokens.py`, `tests/test_llm_config.py`)

## Sources & Research

- **Plan 2026-07-15-002** (classifier swap, landed in `8a07a99`): the recipe this plan replicates. Key sections: KTD3 (thinking default), KTD4 (per-batch max_tokens helper), R4 (DS V4 cleanly handles batch_size=20 at 4096 tokens with 50% headroom).
- **Plan 2026-08-01-002** (lang_detected U0-U6, landed in `8a07a99`): the LlmConfig plumbing and env-var resolution pattern.
- **Commit `6fc7c39`** (parser trailing-prose fix, landed 2026-08-04): the soft-fail safety net for any new parse failures.
- **Commit `02953d6`** (max_tokens bump to 16384, landed 2026-08-04): revealed the proxy-side cap is not liftable via `max_tokens`, prompting this swap.
- **Live prod logs (Render cron `crn-d9gv94o4n6ts739tqaug`)**: 06:20 cycle truncation at `len=7244` with `max_tokens=16384` live — the operational evidence for the swap.
- **Local sandbox `sandbox_translate.py`**: 20-post translator probe returning 100% lang_detected on M3 (no proxy cap hit because the batch is small enough) — confirms the translator path is otherwise correct; only the proxy cap is the bug.
- **Context7 lookup (2026-08-04)**: DS V4 max output = 4096 default, 8192 beta. M3 docs claim 128K-512K but plan 2026-07-15-002 evidence shows the proxy caps at ~890-1800 tokens regardless.

## Product Contract preservation

This is a direct `ce-plan-bootstrap` planning run (no upstream requirements doc). No Product Contract IDs to preserve. R1-R8 capture the full product surface.
