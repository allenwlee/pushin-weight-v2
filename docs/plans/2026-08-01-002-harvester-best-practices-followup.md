---
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
execution: code
title: "harvester: fix lang_detected null + regression from plan-001 + best-practice follow-ups"
created: 2026-08-01
amended: 2026-08-02
depth: standard
type: fix
amends:
  - docs/plans/2026-08-01-001-refactor-harvester-config-wiring-plan.md
supersedes_status_of_items:
  - The 2026-08-01 plan-002 backlog (logging, error handling, LLM retry,
    module split, cursor resolver, type hints, model-to-config). These
    items are now optional and coordinated against U1 below; they
    no longer block this plan's execution.
amends_2026_08_02:
  - U0 added (priority) to restore harvester after plan-001's commit
    `05c3d92` shipped a `NameError: name 'self' is not defined`
    regression in `plan_calls_for_cycle()`. U0 must land BEFORE
    U1-U6 because the harvester is currently broken (every cycle
    aborts at `_plan_calls`, exit 0, no posts inserted).
---

# harvester: fix lang_detected null + best-practice follow-ups

## Summary

Live Render harvester (`pushinweight-harvest` cron) is broken in TWO ways:

1. **U0 (priority — fix first):** Plan 001's config-wiring refactor (commit `05c3d92`) shipped a regression where `plan_calls_for_cycle()` is a module-level function whose body references `self.cfg`. Every cycle hits `NameError: name 'self' is not defined`, which is caught by the outer `except Exception` in `CycleRunner.run()`, the cycle marks itself `aborted` with `n_inserted=0`, and the process exits 0. Render counts every firing as `status="successful"` because the exit code is 0 — but the cycle did no work. The cron has been firing every 15 min since the commit landed, all marked "successful", with **0 posts inserted**. **The harvester is currently broken.** U0 restores it with a one-line fix + a regression test that would have caught the original bug.

2. **U1-U6 (original priority):** Even when U0 is fixed, every cycle that does run writes `lang_detected = NULL` to every post (7,106 / 7,106 = 100% in the last 24 hours; 31,121 / 35,646 = 87% lifetime). U1-U6 fix the lang_detected bug + add the logging/error-handling discipline that hid it.

Items 1-7 (the original backlog) are demoted to optional, coordinated follow-ups.

## Problem Frame — U0 (regression)

Plan 001's config-wiring refactor (commit `05c3d92`, 2026-08-01) was scoped to migrate module-scope constants + `_load_*` helpers in `monitor/cycle.py` to read from `self.cfg`. Per the refactor plan's U3, the migration was supposed to convert the helpers into methods on `CycleRunner` (or thread `cfg` through) — but the function-signature change was missed for `plan_calls_for_cycle()`.

**Concrete shape (verified via Render logs at 2026-08-01T21:15:23Z + DB query):**

```python
# monitor/cycle.py:766 — defined as module-level function (no self):
def plan_calls_for_cycle() -> list[PlannedCall]:
    list_id = _resolve_x_monitor_list_id(self.cfg)   # ← NameError here
    if list_id is None:
        logger.warning(...)
        return []
    ...

# monitor/cycle.py:851 — invoked as bare function (no self.):
calls = plan_calls_for_cycle()

# monitor/cycle.py:1509 — outer catch absorbs the NameError:
try:
    calls = self._plan_calls()
except Exception as exc:
    logger.exception("CycleRunner.run: plan_calls failed: %s", exc)
    summary["status"] = "aborted"
    ...
    return summary
```

The `except (TypeError, ValueError)` inside `_plan_calls` does NOT catch `NameError`, so the exception propagates to the outer `except Exception`, which logs the traceback, marks the cycle `aborted`, and returns cleanly. Exit code 0 → Render reports the cron run as `status="successful"` → next firing scheduled. **The "successful" status is a lie; the cycle did no work.**

**Why this hid for ~14 hours.** Per Render logs, the cron has been firing every 15 minutes since the commit landed (at least 11:00 UTC onward on 2026-08-01). Every run exited 0 with `n_inserted=0`. Render's `cron_job_run_ended status="successful"` is the only signal Render surfaces; the cycle's own `status="aborted"` lives inside the cycle summary JSON and isn't visible without reading the logs.

**Three real call sites + 8+ test monkeypatches:**

- `monitor/cycle.py:851` (production, in `_plan_calls`)
- `monitor/management/commands/backfill.py:212` (production)
- `tests/test_cycle_cursor_wiring.py`, `tests/test_cycle_query_length_guard.py`, `tests/test_harvest_cursor_regression_net.py`, `tests/test_harvest_cursor_lifecycle.py`, `tests/test_cycle_runtime_constants.py` — 8+ `monkeypatch.setattr(cycle_mod, "plan_calls_for_cycle", lambda: list(calls))` shims.

**Fix shape (Fix B from the diagnostic):** Change the signature to `plan_calls_for_cycle(cfg: Config | None = None)`. When `cfg is None`, fall through to `from x_monitor.config import load_config; cfg = load_config(Path("config.yaml"))`. Production callsites pass `self.cfg` (or their loaded cfg); test lambdas need a one-line update from `lambda: list(calls)` to `lambda cfg=None: list(calls)`. This preserves the "module-level helper shared by CycleRunner and backfill" shape (per the docstring) while fixing the regression.

## Problem Frame — U1-U6 (lang_detected NULL)

The `pushinweight-harvest` cron job on Render runs `python manage.py run_cycle` every 15 minutes. The translator stage in `monitor/cycle.py::_run_post_fetch` builds an LLM client via `build_translator_client_from_env()`, which reads `ANTHROPIC_BASE_URL`. **On Render, `ANTHROPIC_BASE_URL` is NOT set** (it lives only in the local fuchitalee shell, not in the `pushinweight-secrets` env-group).

The `pushinweight-harvest` cron job on Render runs `python manage.py run_cycle` every 15 minutes. The translator stage in `monitor/cycle.py::_run_post_fetch` builds an LLM client via `build_translator_client_from_env()`, which reads `ANTHROPIC_BASE_URL`. **On Render, `ANTHROPIC_BASE_URL` is NOT set** (it lives only in the local fuchitalee shell, not in the `pushinweight-secrets` env-group).

With `ANTHROPIC_BASE_URL` unset:

- `_build_client_for_base_url` falls into the **else** branch (direct Anthropic).
- Constructs `AnthropicClaudeClient(api_key=ANTHROPIC_API_KEY, base_url=None)`.
- The credential *value* `sk-cp-uhKEg1omGu…` is the **MiniMax proxy token** (verified working against `api.minimax.io/anthropic` via direct API: returns a successful model response). The proxy accepts Anthropic-format `x-api-key` auth, so the same token works in either env-var field.
- The token *as exposed in `ANTHROPIC_API_KEY`* is invalid against `api.anthropic.com` (direct Anthropic): verified via direct API — returns `authentication_error: invalid x-api-key`. The MiniMax proxy is the only intended endpoint for this token.
- In the working v1 stack on fuchitalee, this same value is exposed under the credential name **`MINIMAX_API_TOKEN`** (in `~/.env.secrets`) — the factory's `use_minimax_proxy=True` branch reads `MINIMAX_API_TOKEN`, not `ANTHROPIC_API_KEY`. Render's `pushinweight-secrets` env-group sets `ANTHROPIC_API_KEY` but **does not** set `MINIMAX_API_TOKEN`, so the proxy branch never matches and the factory falls into the else (direct-Anthropic) branch — which then fails auth against `api.anthropic.com` for the reason above.
- Every LLM call returns 401; `_call_with_retry` retries 3x then raises.
- `translate_batch_pragmatics` swallows the exception per-batch (translator.py has **zero** logger calls) and appends `_empty_pragmatics_row(t, failed=True)` rows with `lang_detected=None`.
- `cycle.py:1322 if translation_rows:` block runs and writes `lang_detected=None` to every post.

The classifier stage uses a different env var (`X_MONITOR_CLASSIFIER_BASE_URL=https://api.deepseek.com/anthropic` + `DEEPSEEK_API_KEY`) which IS set — that's why the relevancy gate works and the classifier path partially works. The translator has no equivalent override path.

**Why the failure was silent.** No `logger` calls in `x_monitor/translator.py`. The translator's per-batch `except Exception` swallows errors silently; the cycle-level `except Exception as exc: logger.warning(...)` never fires because the exception is consumed downstream. The DB-level symptom (NULL column) was the only signal.

**Why prior sessions missed it.** `monitor/cycle.py` documents the silent-failure path at line 1257 in a comment that references "the DeepSeek base URL" — implying the failure mode was already known but never pinned. The original `docs/issues/2026-07-13-bbf72b83-u3-evidence-review-notes.md` flagged the bug on the v1 stack; v2 carries the same shape.

## Requirements

- **R1.** The harvester cron MUST be able to construct a working translator client using **only** env vars that are present in `pushinweight-secrets`. Operator-tunable override of the translator's endpoint MUST go through `Config` (per Plan 2026-08-01-001's single-source-of-truth discipline) — not ad-hoc env vars read directly in `monitor/cycle.py`.
- **R2.** `Config.llm` MUST be a new pydantic block holding `translator_model: str`, `classifier_model: str`, `relevancy_model: str`, plus the existing `signal_model: str` (Item 7 of the original backlog folds into this). Defaults MUST match the current hardcoded values (`claude-haiku-4-5` for relevancy/signal, `minimax/MiniMax-M3.0[1m]` for translator, `deepseek-v4-pro` for classifier — the last two resolved via `ANTHROPIC_BASE_URL` substring today, made explicit here).
- **R3.** The translator client builder MUST accept a `Config` (or the resolved model name + base URL pair) as input rather than re-reading env vars at call time. The factory MUST be deterministic and pure — same env + same cfg ⇒ same client (or None with a typed warning).
- **R4.** When the translator client cannot be built (missing credential, wrong provider routing), the harvester MUST log a typed warning with `exc_info=True` AND surface the error count in the cycle's `--json` output. No silent skip.
- **R5.** Per-batch translation failures MUST be logged with `exc_info=True` so the operator can grep one Render log line and find the cause. (This is the spirit of original Item 1 applied narrowly to the translator path.)
- **R6.** The `Config.llm` block MUST be pinned in tests (regression net for the AFTER state of operator-tunable LLM config). The translator-client env routing MUST be pinned in tests (regression net for the silent-failure mode that hid the bug).
- **R7.** Render `pushinweight-harvest` cron MUST have the env vars needed for `build_translator_client_from_env()` to succeed via the new `Config.llm` path. Operator adds the missing vars post-deploy.
- **R8.** Existing tests (`tests/test_attribution.py`, `tests/test_build_anthropic_client_from_env.py`, `tests/test_translator.py`) MUST continue to pass without modification, OR be updated only to match the new factory signature (no semantic change to their assertions).

## Key Technical Decisions

- **KTD1. New `LlmConfig` pydantic block on `Config`.** *(session-settled: extends Plan 2026-08-01-001's single-source-of-truth discipline — chosen over "env vars stay where they are": the env vars were the original bug surface; routing through Config eliminates drift.)* Schema fields:
  - `translator_model: str = "minimax/MiniMax-M3.0[1m]"` — default matches current `ANTHROPIC_MODEL` env value on fuchitalee (the value the v1 stack already uses successfully).
  - `classifier_model: str = "deepseek-v4-pro"` — default matches the 2026-07-15 swap plan.
  - `relevancy_model: str = "claude-haiku-4-5"` — default matches `x_monitor/relevancy.py::DEFAULT_RELEVANCY_MODEL`.
  - `signal_model: str = "claude-haiku-4-5"` — default matches `x_monitor/attribution.py::_resolve_signal_model()` default.
  - All fields are required strings (no Optional); missing values surface as pydantic ValidationError on startup.

- **KTD2. Factory builders take `Config` (not env vars).** *(session-settled: user-aligned with Plan 2026-08-01-001's R7 single-source-of-truth — chosen over "keep env-var factory, add Config layer on top": a single source of truth means the factory reads from Config, not env. Env vars become the loader's input, not the factory's.)* `build_translator_client_from_env(cfg: Config) -> AnthropicClaudeClient | None` and `build_anthropic_client_from_env(cfg: Config) -> AnthropicClaudeClient | None` — both signatures change. Callers (CycleRunner, run_cycle mgmt command, tests) pass the loaded `cfg`.

- **KTD3. Env-to-Config resolution stays at the boundary.** *(session-settled: user-aligned with Plan 2026-08-01-001 KTD1 single Config instance — chosen over "load Config from env inside the factory": env resolution belongs in `load_config()`, not in every factory.)* `load_config()` reads env vars (`X_MONITOR_*_MODEL`, `X_MONITOR_TRANSLATOR_BASE_URL`, `DEEPSEEK_API_KEY`, `MINIMAX_API_TOKEN`) into `Config.llm.*` via a `model_validator(mode="before")`. The three credential-name env vars (`MINIMAX_API_TOKEN`, `DEEPSEEK_API_KEY`, `ANTHROPIC_API_KEY`) are read at factory-construction time inside `_build_client_for_base_url`, where the URL-substring routing decides which credential name applies; the factory does not move them into Config (they are credentials, not operator-tunable config). Factories read from `cfg.llm.*` for the model name and base URL; the credential name follows the URL-substring routing, not Config.

- **KTD4. Render env-var fix happens as a separate post-deploy step.** *(session-settled: user direction — chosen over "code-only fix that doesn't touch Render": the v2 harvester's data quality problem is a live production issue, and a code-only fix without the env-var change still leaves the bug present. The deploy sequence is: merge code → wait for green CI → operator adds env vars → next cycle verifies `lang_detected` populates.)* Doc this as Step 5 in the plan; not a code change. The commit message footer MUST include `Scope delivered vs plan promised: match` (per global rules).

- **KTD5. The translation-swallow path is fixed in scope but not silenced.** *(session-settled: user-aligned with original Item 2's "no silent skip" rule — chosen over "leave the swallow as-is, just add a counter": the swallow IS the bug, but the fix is to surface it (log + counter), not to remove the per-batch catch. The per-batch catch is load-bearing — one bad batch must not poison the whole cycle. Just make it visible.)* Add a typed `_error_counts["translator_batch_failed"]` counter on `CycleRunner` AND a per-batch `logger.warning("translator_batch_failed", exc_info=True)` in `translate_batch_pragmatics`. The cycle summary emits the counter; the log emits the exception.

- **KTD6. The classifier swallow path is fixed in the same pass.** *(session-settled: same root cause — the relevancy gate's `messages_create: LLM returned non-JSON (len=4): 'KEEP'` log line at `x_monitor/attribution.py:2192` is the only signal that the classifier path is degrading silently. Same fix shape: typed counter + structured log.)*

- **KTD7. The signal-model hardcoded constant is moved to `Config.llm.signal_model`.** *(session-settled: user-aligned with original Item 7 — chosen over "leave the constant, fix the bug": the constant is one of the four LLM models that now belongs in Config per KTD1. Same change as Item 7, in the same commit.)*

- **KTD8. The model-resolution helpers (`_resolve_signal_model`, `_resolve_translator_model`) stay where they are but read from `Config`.** *(session-settled: user-aligned with Plan 2026-08-01-001's KTD6 — chosen over "delete the resolvers, inline into the factories": the resolvers encapsulate the provider-substring → model default logic, which is non-trivial. They take `cfg` as input instead of reading env.)* `cfg.llm.signal_model` / `cfg.llm.translator_model` are the FIRST-class lookup; the substring-routed default is the FALLBACK when the field is empty.

## File Structure

This plan touches the following files. New files are bolded.

- `x_monitor/config.py` — add `LlmConfig` block + `llm: LlmConfig = LlmConfig()` field on `Config`; add `model_validator(mode="before")` that reads `X_MONITOR_*_MODEL` env vars into `cfg.llm.*`.
- `x_monitor/reattribute.py` — `build_anthropic_client_from_env` and `build_translator_client_from_env` accept `cfg: Config`; resolve base URL + api key from `cfg.llm.*` (and indirectly from `cfg.search.*`-style env-var-driven fields if needed for the base URL itself). Add typed warning on missing credential. Add typed counter on the cycle.
- `x_monitor/translator.py` — add per-batch `logger.warning("translator_batch_failed", exc_info=True)` in `translate_batch_pragmatics`. The `_call_with_retry` resolves the model name from `cfg.llm.translator_model` instead of re-reading `ANTHROPIC_MODEL` env var.
- `x_monitor/attribution.py` — `_resolve_signal_model(cfg: Config) -> str` reads from `cfg.llm.signal_model`; existing `messages_create: LLM returned non-JSON` log line gains `exc_info=True` and a typed counter. Same shape for `classify_pragmatics_full`.
- `monitor/cycle.py` — `_run_post_fetch(kept_all)` reads translator/client models from `self.cfg.llm.*`. `_error_counts["translator_batch_failed"]` and `_error_counts["classifier_batch_failed"]` are surfaced in `--json` output.
- `monitor/management/commands/run_cycle.py` — `load_config(Path("config.yaml"))` already passes `cfg` to `CycleRunner` (Plan 001 U2); no edit needed beyond verifying the path still works.
- **`x_monitor/tests/test_llm_config.py` (new)** — pin `Config.llm` defaults; pin env-var-to-Config resolution; pin factory routing.
- **`x_monitor/tests/test_translator_logging.py` (new)** — pin per-batch log emission with `exc_info=True`.
- `x_monitor/tests/test_build_anthropic_client_from_env.py` — update signatures (KTD2); existing assertions unchanged.
- `x_monitor/tests/test_attribution.py` — update `_resolve_signal_model` callers to pass `cfg`; existing assertions unchanged.

## Implementation Units

### U0. Restore harvester: fix `plan_calls_for_cycle()` regression (PRIORITY)

**Goal.** Stop the regression that crashes every cycle. Restore the harvester to inserting posts.

**Files.**
- Modify: `monitor/cycle.py` lines 766, 851 (function signature + caller)
- Modify: `monitor/management/commands/backfill.py` line 212 (caller)
- Modify: `tests/test_cycle_cursor_wiring.py` (2 sites), `tests/test_cycle_query_length_guard.py` (1 site), `tests/test_harvest_cursor_regression_net.py` (1 site), `tests/test_harvest_cursor_lifecycle.py` (1 site), `tests/test_cycle_runtime_constants.py` (any site) — test lambdas add `cfg=None` kwarg

**Approach.**
1. Change `monitor/cycle.py:766` signature: `def plan_calls_for_cycle(cfg: Config | None = None) -> list[PlannedCall]:`.
2. At the top of the function body (before `list_id = ...`), add:
   ```python
   if cfg is None:
       from pathlib import Path
       from x_monitor.config import load_config
       cfg = load_config(Path("config.yaml"))
   ```
3. Update `monitor/cycle.py:851` to pass `self.cfg`: `calls = plan_calls_for_cycle(self.cfg)`.
4. Update `monitor/management/commands/backfill.py:212` to pass the loaded cfg (mirroring the same call shape from `_plan_calls`).
5. Update the 8+ test monkeypatch shims from `lambda: list(calls)` to `lambda cfg=None: list(calls)` (or equivalent — the test sites already construct the call list, so the cfg arg is unused).
6. Add the regression test (U5 below already pins the failure mode; this U0 also adds a focused test):

**Test scenarios.**
- `tests/test_cycle_regression_net.py::test_plan_calls_for_cycle_signature_accepts_optional_cfg` — `from monitor.cycle import plan_calls_for_cycle; plan_calls_for_cycle()` returns a list of `PlannedCall` (no NameError); `plan_calls_for_cycle(cfg=...)` also returns a list. The signature MUST accept `cfg=None`.
- `tests/test_cycle_regression_net.py::test_cycle_runner_does_not_abort_with_self_undefined` — instantiate `CycleRunner(dry_run=True, cfg=Config(...))` and call `_plan_calls()`; assert the returned list has the expected 7-call layout (not `[]` from the `aborted` path). This test would have caught commit `05c3d92`'s regression.
- `pytest tests/ -v` — all existing tests still pass after the `cfg=None` lambda update.
- **Live verification:** after merge, the next Render cron run produces `CycleRunner.run: 7 calls, N posts seen, K inserted, K attributed in Xs` (NOT `0 inserted`).

**Verification.** `pytest tests/ -v` green. Next Render cycle reports `n_inserted > 0` in the cycle summary.

### U1. Add `LlmConfig` schema + `Config.llm` block + env-var resolution

**Goal.** Single source of truth for the four LLM model names that the harvester uses. Env vars resolve into `Config.llm.*` at `load_config()` time so factories and resolvers never re-read env.

**Files.**
- Modify: `x_monitor/config.py` (add `LlmConfig` class between `CycleConfig` and `Config`; add `llm: LlmConfig = LlmConfig()` field on `Config`; add `model_validator(mode="before")` reading `X_MONITOR_TRANSLATOR_MODEL`, `X_MONITOR_CLASSIFIER_MODEL`, `X_MONITOR_RELEVANCY_MODEL`, `X_MONITOR_SIGNAL_MODEL`)

**Approach.**
1. Define `LlmConfig` in `x_monitor/config.py` directly after `CycleConfig`:
   - `translator_model: str` — required (no default), resolved at `load_config()` from `X_MONITOR_TRANSLATOR_MODEL` env (falling back to `"minimax/MiniMax-M3.0[1m]"`); OR set a default and let env override via `model_validator(mode="before")`.
   - `classifier_model: str` — same pattern, default `"deepseek-v4-pro"`, env override `X_MONITOR_CLASSIFIER_MODEL`.
   - `relevancy_model: str` — default `"claude-haiku-4-5"`, env override `X_MONITOR_RELEVANCY_MODEL`.
   - `signal_model: str` — default `"claude-haiku-4-5"`, env override `X_MONITOR_SIGNAL_MODEL`.
2. Add `llm: LlmConfig = LlmConfig()` to `Config` immediately after `cycle: CycleConfig = CycleConfig()`.
3. Add `model_validator(mode="before")` on `Config` that takes the raw dict (before pydantic field instantiation) and copies `X_MONITOR_*_MODEL` env vars into `raw_dict["llm"]` if not already present in `raw_dict`. This is the env→Config bridge — single boundary, not duplicated in every factory.

**Patterns to follow.**
- `x_monitor/config.py::CycleConfig` is the most recent precedent for a config sub-block with defaults that match prior hardcoded values (Plan 001 U1). Mirror its shape: `Field(default=..., description=...)`.

**Test scenarios.**
- `Config()` (empty dict) loads successfully; `cfg.llm.translator_model == "minimax/MiniMax-M3.0[1m]"`, `cfg.llm.classifier_model == "deepseek-v4-pro"`, `cfg.llm.relevancy_model == "claude-haiku-4-5"`, `cfg.llm.signal_model == "claude-haiku-4-5"`.
- `monkeypatch.setenv("X_MONITOR_TRANSLATOR_MODEL", "custom-model")` then `Config()` yields `cfg.llm.translator_model == "custom-model"`.
- `Config({"llm": {"translator_model": "from-yaml"}})` loads with `cfg.llm.translator_model == "from-yaml"` (yaml wins over env).
- A `config.yaml` without an `llm:` block loads with all four defaults (regression net: existing configs continue to work).

**Verification.** `pytest x_monitor/tests/test_llm_config.py -v` green. Existing `tests/test_query_plan_uniform.py` and `tests/test_migration_035.py` (which call `load_config`) still pass with no signature changes.

### U2. Re-wire the factory builders to read from `Config`

**Goal.** `build_translator_client_from_env` and `build_anthropic_client_from_env` no longer read env at call time. They take `cfg: Config` and resolve model + base URL + credential from `cfg.llm.*`. Missing credential produces a typed warning (not silent None).

**Files.**
- Modify: `x_monitor/reattribute.py` — both factory functions take `cfg: Config` as first positional arg.
- Modify: `x_monitor/attribution.py::_resolve_signal_model` and `_resolve_translator_model` take `cfg: Config`.

**Approach.**
1. Change signatures: `build_translator_client_from_env(cfg: Config) -> AnthropicClaudeClient | None` and `build_anthropic_client_from_env(cfg: Config) -> AnthropicClaudeClient | None`.
2. Inside `_build_client_for_base_url(base_url, caller_label, cfg)`: read `api_key` from the credential relevant to the base URL substring (still MiniMax-token / DeepSeek-key / Anthropic-key resolution), but read `base_url` from `cfg.llm.*` where the model field implies the base URL, OR keep the env-derived base URL since `ANTHROPIC_BASE_URL` is also operator-tunable. **Decision: keep `ANTHROPIC_BASE_URL` env-driven (since it's an LLM-router URL, not a model name), but add an `X_MONITOR_TRANSLATOR_BASE_URL` env that overrides it when set. The factory reads `cfg.llm.translator_base_url` (new optional field) first, then `ANTHROPIC_BASE_URL` env, then defaults to `None` (direct Anthropic).** The model name comes from `cfg.llm.translator_model`.
3. Inside `_build_client_for_base_url`, when the credential is missing, log `logger.warning("translator_credential_missing", extra={"caller_label": ..., "base_url": ..., "expected_credential": "MINIMAX_API_TOKEN" or "DEEPSEEK_API_KEY" or "ANTHROPIC_API_KEY"})`. NOT silent None.
4. `_resolve_signal_model(cfg)`: return `cfg.llm.signal_model` if non-empty (new field on LlmConfig), else fall back to the current substring-routed default (preserving backward compat for any caller that doesn't pass `cfg`).
5. `_resolve_translator_model(cfg)`: same shape — return `cfg.llm.translator_model` if non-empty, else fallback.

**Patterns to follow.**
- `x_monitor/reattribute.py::_build_client_for_base_url` already has a typed warning pattern at the missing-credential branch (lines ~395). Mirror the call shape but include the structured `extra=` dict for dashboard queryability.

**Test scenarios.**
- `build_translator_client_from_env(cfg_with_minimax)` returns an `AnthropicClaudeClient` constructed with `api_key=MINIMAX_API_TOKEN`, `base_url=ANTHROPIC_BASE_URL`, and the model from `cfg.llm.translator_model`. Verified via patched env (monkeypatch) + a `Config` with `llm.translator_model="custom-test-model"`.
- `build_translator_client_from_env(cfg_with_no_minimax_token)` returns None AND emits a `logger.warning` with `extra={"expected_credential": "MINIMAX_API_TOKEN"}` — verified via `caplog`.
- `build_anthropic_client_from_env(cfg_with_deepseek)` returns the DeepSeek client. Mirrors today's behavior.
- `_resolve_signal_model(cfg_with_signal_model_override="my-model")` returns `"my-model"`. `_resolve_signal_model(cfg_with_empty_signal_model)` falls back to substring-routed default.
- `pytest x_monitor/tests/test_build_anthropic_client_from_env.py` (existing) is updated for the new signature; existing assertions are preserved (the env-var fixtures move into a `Config` fixture).

**Verification.** `pytest x_monitor/tests/test_build_anthropic_client_from_env.py x_monitor/tests/test_llm_config.py -v` green.

### U3. Wire `monitor/cycle.py` + `monitor/management/commands/run_cycle.py` to pass `cfg` to factories

**Goal.** `CycleRunner._run_post_fetch` passes `self.cfg` to `build_translator_client_from_env` and `build_anthropic_client_from_env`. The two factory callsites in `monitor/management/commands/run_cycle.py` (relevancy client build, `CycleRunner` construction) also pass `cfg`.

**Files.**
- Modify: `monitor/cycle.py` — `_run_post_fetch` line ~1248 reads `cfg` from `self`; pass to both factories.
- Modify: `monitor/management/commands/run_cycle.py` — line ~110 (relevancy client build) passes the already-loaded `cfg`.

**Approach.**
1. In `monitor/cycle.py::_run_post_fetch`, replace `build_translator_client_from_env()` with `build_translator_client_from_env(self.cfg)` and the same for `build_anthropic_client_from_env()`.
2. In `run_cycle.py::handle`, the relevancy client build at line ~110 passes `cfg` (already loaded per Plan 001 U2).
3. Verify no other callsites in `monitor/cycle.py` or `monitor/management/commands/` read these factories directly.

**Patterns to follow.**
- `monitor/cycle.py::CycleRunner.__init__` already stores `self.cfg` per Plan 001 U2; no new attribute needed.

**Test scenarios.**
- `tests/test_cycle_runtime_constants.py` (added in Plan 001 U4) extends with `test_run_post_fetch_uses_cfg_translator_model`: instantiate `CycleRunner(dry_run=True, cfg=Config(llm=LlmConfig(translator_model="custom")))` and verify (via `monkeypatch` on the factory) the right `cfg.llm.translator_model` flows through.
- `pytest monitor/tests/ -v` green.

**Verification.** `pytest monitor/tests/ x_monitor/tests/ -v` green. `grep -rn "build_translator_client_from_env()" --include="*.py"` returns zero hits outside `tests/test_build_anthropic_client_from_env.py` (the test signature-only pin).

### U4. Translator batch failure → typed warning + exc_info + cycle counter

**Goal.** The silent per-batch exception swallow in `translate_batch_pragmatics` is made visible. The cycle's `--json` output surfaces the count.

**Files.**
- Modify: `x_monitor/translator.py::translate_batch_pragmatics` — per-batch `except Exception as exc:` adds `logger.warning("translator_batch_failed", exc_info=True)` AND accepts a new `on_batch_error` parameter that the cycle uses to bump a counter (already exists per the function's docstring; the cycle just wires it).
- Modify: `x_monitor/attribution.py::classify_batch_pragmatics_full` — same shape for the classifier path. Same `on_batch_error` callback contract.
- Modify: `monitor/cycle.py` — `CycleRunner._run_post_fetch` passes an `on_batch_error` lambda that bumps `self._error_counts["translator_batch_failed"] += 1` (and `classifier_batch_failed += 1`).

**Approach.**
1. `translate_batch_pragmatics` already has the `on_batch_error` parameter (per its docstring at line 614). Verify the parameter is honored; if it isn't, wire it. Add `logger.warning("translator_batch_failed", exc_info=True)` on the per-batch catch block (around line 626 / 632).
2. `classify_batch_pragmatics_full` — add the same log + `on_batch_error` parameter.
3. `monitor/cycle.py` — extend `_error_counts: dict[str, int]` initialization to include the two new keys with default 0; pass `on_batch_error=lambda batch, exc: self._error_counts.update(...)` to both calls.
4. `_summarize_cycle` (or equivalent) emits `n_errors_by_type` in the `--json` output.

**Patterns to follow.**
- `x_monitor/attribution.py:2192` has the existing `messages_create: LLM returned non-JSON (len=%d): %r` log line as a precedent for the per-event warning shape. Add `exc_info=True` and the structured event name.

**Test scenarios.**
- `x_monitor/tests/test_translator_logging.py::test_batch_failure_logs_exc_info` — `FakeClaudeClient` that raises `RuntimeError` on every call; assert `caplog.records` contains a `"translator_batch_failed"` record with `exc_info` populated (verify via `record.exc_info is not None`).
- `x_monitor/tests/test_translator_logging.py::test_batch_failure_invokes_on_batch_error` — same setup; assert the `on_batch_error` callback fires once per failed batch with `(batch, exc)` arguments.
- `monitor/tests/test_cycle_error_counters.py::test_translator_failure_increments_counter` — drive `CycleRunner._run_post_fetch` with a translator client that raises on every batch; assert `summary["n_errors_by_type"]["translator_batch_failed"] == len(kept_all) / 20` (one per 20-post batch).
- Existing `tests/test_translator.py::test_smoke_translation_failure_attributes_to_tweet_id` (which already uses `on_batch_error`) continues to pass.

**Verification.** `pytest x_monitor/tests/test_translator_logging.py monitor/tests/test_cycle_error_counters.py -v` green.

### U5. Regression net: pin the AFTER state

**Goal.** No future edit can silently regress the lang_detected fix. Pins per `feedback_regression_net_in_every_plan.md`.

**Files.**
- Modify: `x_monitor/tests/test_llm_config.py` (added in U1) — add `test_llm_config_defaults_match_v1_translator_model` that asserts `cfg.llm.translator_model == "minimax/MiniMax-M3.0[1m]"` with a `# BEFORE: hardcoded in _resolve_translator_model when ANTHROPIC_BASE_URL contains "minimax.io"` comment so future edits see the diff.
- Modify: `x_monitor/tests/test_translator_logging.py` (added in U4) — pin that EVERY error-path logger call in `translate_batch_pragmatics` uses `exc_info=True` (custom pytest rule, mirrors original Item 1's regression net).
- Add: `monitor/tests/test_cycle_error_counters.py::test_run_post_fetch_summary_has_n_errors_by_type` — assert the `--json` summary dict has the `n_errors_by_type` key with all expected typed counters initialized to 0, so a future edit can't silently drop a counter.
- Modify: `tests/test_build_anthropic_client_from_env.py` — add `test_translator_factory_warns_on_missing_credential` that asserts a `logger.warning` is emitted (NOT silent None) when the expected credential env var is unset.

**Test scenarios.**
- All five pinned-state assertions pass on a clean tree.
- Forcing `_call_with_retry` to NOT pass `exc_info=True` causes `test_batch_failure_logs_exc_info` to fail loudly.
- Removing `n_errors_by_type` from the `--json` summary causes `test_run_post_fetch_summary_has_n_errors_by_type` to fail loudly.
- Removing the `logger.warning` from `_build_client_for_base_url` causes `test_translator_factory_warns_on_missing_credential` to fail loudly.

**Verification.** `pytest x_monitor/tests/test_llm_config.py x_monitor/tests/test_translator_logging.py monitor/tests/test_cycle_error_counters.py x_monitor/tests/test_build_anthropic_client_from_env.py -v` all green.

### U6. Update `config.yaml` to declare the `llm:` block + Render env-var fix (operator step)

**Goal.** Operator can find the LLM config in `config.yaml` and the production env vars are aligned with the new code path.

**Files.**
- Modify: `config.yaml` — add `llm:` block with the four defaults explicitly set, mirroring `cycle:` block style from Plan 001 U1.
- Operator step (NOT a code change; documented): set the missing env vars on `pushinweight-harvest` cron so the translator client can be built post-deploy.

**Approach.**
1. `config.yaml` after the `cycle:` block:
   ```yaml
   # LLM routing (plan 2026-08-01-002 U6). Defaults mirror the values
   # the v1 + v2 stacks used prior to this change; operators can
   # override per-env via X_MONITOR_<role>_MODEL without editing
   # config.yaml. The translator_base_url defaults to the
   # ANTHROPIC_BASE_URL env var (preserves the proxy path the v1
   # shell already configures).
   llm:
     translator_model: "minimax/MiniMax-M3.0[1m]"
     classifier_model: "deepseek-v4-pro"
     relevancy_model: "claude-haiku-4-5"
     signal_model: "claude-haiku-4-5"
   ```
2. **Operator step (post-merge):** On Render, set the following env vars on the `pushinweight-harvest` cron job (and the suspended `pushinweight-beat` / `pushinweight-worker` for parity when they're re-enabled):
   - `ANTHROPIC_BASE_URL=https://api.minimax.io/anthropic` (matches fuchitalee shell — required for the translator to route through the MiniMax proxy; without this, the factory's `use_minimax_proxy` branch never matches and falls into direct-Anthropic).
   - `MINIMAX_API_TOKEN=<the value already in fuchitalee shell at ~/.env.secrets>` (the proxy-side credential; the factory's `use_minimax_proxy=True` branch reads `MINIMAX_API_TOKEN`, NOT `ANTHROPIC_API_KEY`. Render's current `pushinweight-secrets` env-group sets `ANTHROPIC_API_KEY` (with the same value, but under the wrong name) and does NOT set `MINIMAX_API_TOKEN` — that's the precise gap this operator step closes).
   - Verify: next cycle logs `CycleRunner.run: N calls, M posts seen, K inserted, K attributed in Xs` AND a subsequent `SELECT count(*) FROM posts WHERE lang_detected IS NOT NULL AND fetched_at > now() - interval '15 minutes'` returns ≥ K (matching the inserted count).

**Test scenarios.**
- `x_monitor/tests/test_llm_config.py::test_config_yaml_has_llm_block` — loads `Path("config.yaml")` and asserts `cfg.llm.translator_model == "minimax/MiniMax-M3.0[1m]"` (etc.).
- Operator step is NOT a test scenario; verified manually via the DB query above after deploy.

**Verification.** `pytest x_monitor/tests/test_llm_config.py -v` green. Post-deploy DB query returns non-NULL `lang_detected` on all newly-inserted posts for ≥2 consecutive cycles.

## Out of Scope

- Original Item 4 (split `monitor/cycle.py` into focused modules). Demoted to optional coordinated follow-up — see `Optional coordinated follow-ups` below.
- Original Item 5 (extract `CursorResolver` class). Demoted.
- The Celery task wrapper (`monitor/tasks.py`) doesn't currently use `Config` — will need a follow-up if/when Celery integration becomes load-bearing. **Coordinate with:** Plan 001 U2 mentions `monitor/tasks.py` (if exists); if it does, apply the same `cfg` threading in this commit.
- The `_attribute_items` per-post fallback path. Out of scope; unrelated to lang_detected.

## Optional coordinated follow-ups

These items are demoted from the original priority-1-7 backlog. They remain valuable but no longer block this plan. **Status: optional** — pick up as separate `ce-plan` runs when convenient. Each item includes explicit coordination notes so it doesn't re-litigate decisions made in this plan.

### Item 1. Structured logging + per-cycle correlation ID (optional)

**Status:** optional. Originally item 1 in the 2026-08-01 backlog.

**Coordination with this plan.**
- U4 of this plan already adds `logger.warning("translator_batch_failed", exc_info=True)` and the structured `event_name` pattern at the translator batch failure path. Item 1 is the broader application of the same shape across all logger calls. **Do not duplicate the translator batch failure log when picking up Item 1.**
- U2 of this plan already reads from `cfg.llm.*` rather than env. Item 1's structured logging should emit `cfg.run_id` (or equivalent) when one is added; this plan doesn't add `run_id` to Config.
- When picked up: extend `caplog` regression net from U5 to cover all `logger.error` / `logger.warning` sites in `monitor/cycle.py` + `x_monitor/translator.py` + `x_monitor/attribution.py` + `x_monitor/relevancy.py` + `x_monitor/apify.py` (mirror U5's test shape; the five files named in the original Item 1).

**Files.** `monitor/cycle.py`, `x_monitor/attribution.py`, `x_monitor/relevancy.py`, `x_monitor/apify.py`.

**Effort.** ~2 hours.

### Item 2. Replace bare `except Exception as exc:` swallows with typed errors + counters (optional)

**Status:** optional. Originally item 2 in the 2026-08-01 backlog.

**Coordination with this plan.**
- U4 of this plan already adds `_error_counts["translator_batch_failed"]` and `_error_counts["classifier_batch_failed"]` typed counters on `CycleRunner`. **The shape of those counters (string-keyed dict, surfaced via `--json`'s `n_errors_by_type`) is the canonical pattern. Item 2 must follow the same pattern when extending to other swallow sites.**
- U5 of this plan adds the `test_run_post_fetch_summary_has_n_errors_by_type` regression net. Item 2's extension must update this test (add new typed counters to the assertion list) when introducing new counter keys.

**Files.** `monitor/cycle.py` (13 sites per original audit), `x_monitor/attribution.py` (2 sites).

**Effort.** ~3 hours.

### Item 3. LLM retry with jitter + cap + structured logging (optional)

**Status:** optional. Originally item 3 in the 2026-08-01 backlog.

**Coordination with this plan.**
- U2 of this plan replaces the env-var `_resolve_translator_model` with a `cfg`-taking resolver. Item 3's retry budget must read from a new `cfg.llm.translator_max_retry_seconds` (or use a module-level default) — do not re-introduce env reads.
- U4 of this plan adds the `translator_batch_failed` log event. Item 3's retry log event should follow the same `extra={...}` shape (use `extra={"attempt": N, "wait_seconds": X, "error_type": "..."}` per original Item 3).
- The "max ~7.5 seconds" retry-budget pin (original Item 3's regression test) is the canonical timing invariant; preserve it.

**Files.** `x_monitor/attribution.py::_call_signal_with_retry`, `x_monitor/apify.py` (3 sites).

**Effort.** ~1 hour.

### Item 4. Split `monitor/cycle.py` (1922 LOC) into focused modules (optional)

**Status:** optional. Originally item 4 in the 2026-08-01 backlog.

**Coordination with this plan.**
- This plan does NOT touch `monitor/cycle.py` structure (only `_run_post_fetch` and the `_error_counts` dict). When Item 4 is picked up, the U4 changes to `_run_post_fetch` move into `monitor/cycle_post_fetch.py` (per Item 4's split target).
- The `_run_post_fetch` lines ~1248-1252 (factory calls) and ~1267-1303 (translation stage) are the seam. Item 4 splits on these lines.
- `cfg` is already passed through `CycleRunner.__init__` per Plan 001 U2; Item 4 inherits this and threads `cfg` through the new module boundaries.

**Files.** `monitor/cycle.py` (refactored), new files: `monitor/cycle_planning.py`, `monitor/cycle_fetch.py`, `monitor/cycle_post_fetch.py`, `monitor/cycle_summarize.py`.

**Effort.** ~6 hours split + ~2 hours test reorganization.

### Item 5. Extract `CursorResolver` class (optional)

**Status:** optional. Originally item 5 in the 2026-08-01 backlog.

**Coordination with this plan.** No overlap. Item 5 is orthogonal to U1-U6.

**Files.** `monitor/cycle.py` (current `_read_cursor_since`, `_advance_cursor`), new `monitor/cursor.py`.

**Effort.** ~4 hours.

### Item 6. Type hints on remaining untyped helpers (optional)

**Status:** optional. Originally item 6 in the 2026-08-01 backlog.

**Coordination with this plan.**
- U2 changes signatures (`build_translator_client_from_env(cfg: Config)` etc.); these are already typed. Item 6 covers the 5 module-level helpers in `monitor/cycle.py` not touched by this plan.

**Files.** `monitor/cycle.py` (5 functions).

**Effort.** ~30 min.

### Item 7. Move `claude-haiku-4-5` from module constant to `Config` (optional, PARTIALLY COMPLETED)

**Status:** partially completed by this plan. Originally item 7 in the 2026-08-01 backlog.

**Coordination with this plan.**
- U1 of this plan adds `LlmConfig.signal_model` and `LlmConfig.relevancy_model` to `Config.llm`, with defaults `"claude-haiku-4-5"`. **Item 7's "add LlmConfig block" requirement is satisfied.**
- U2 of this plan re-wires `_resolve_signal_model(cfg)` and `DEFAULT_RELEVANCY_MODEL` to read from `cfg.llm.*`. **Item 7's "wire the two module constants" requirement is satisfied** — but only if U2 picks up the `DEFAULT_RELEVANCY_MODEL` change. (Confirm during U2 implementation; if not picked up, defer the relevancy half to a follow-up.)
- The remaining Item 7 work: confirm `x_monitor/relevancy.py::DEFAULT_RELEVANCY_MODEL` is dead (no remaining callers) and remove the module constant. Low risk.

**Files.** `x_monitor/relevancy.py`, `x_monitor/attribution.py`.

**Effort.** ~15 min (deferred cleanup).

## Risks & Mitigations

- **Risk:** Changing the factory signatures breaks every caller, including tests we haven't enumerated. **Mitigation:** `grep -rn "build_translator_client_from_env\|build_anthropic_client_from_env\|_resolve_signal_model\|_resolve_translator_model" --include="*.py"` and update every callsite. Plan 001 already migrated the cycle callsite; U3 verifies the chain.
- **Risk:** `Config.llm` defaults don't match what production is currently doing. **Mitigation:** U1's defaults mirror the values that already work in the v1 stack on fuchitalee (`minimax/MiniMax-M3.0[1m]` from `~/.zshrc`-equivalent). U6's operator step explicitly adds the env var so the new code path matches the old working setup. U5's regression net pins the defaults.
- **Risk:** Per-batch `logger.warning` floods logs in a sustained outage. **Mitigation:** original Item 3 (retry jitter + cap) addresses the root cause; U4's log is bounded to one per failed batch per cycle. Combined failure rate stays within Render log retention.
- **Risk:** Operator forgets U6's env-var step. **Mitigation:** the deploy sequence is explicit (merge → wait for green CI → operator step → verify with DB query). The Definition of Done requires both the code commit AND the post-deploy verification.
- **Risk:** `model_validator(mode="before")` on `Config` interacts badly with existing tests that construct `Config` from partial dicts. **Mitigation:** the validator only reads env vars when the field is not already in the dict; existing tests that pass explicit `llm: LlmConfig(...)` are unaffected.

## Verification Contract

- `pytest x_monitor/tests/ monitor/tests/ -v` — all tests pass, including the new `test_llm_config.py` and `test_translator_logging.py`.
- `grep -rn "build_translator_client_from_env()" --include="*.py"` returns zero hits outside test fixtures.
- `grep -rn "_resolve_signal_model()" --include="*.py"` returns zero hits outside test fixtures.
- `python -c "from x_monitor.config import load_config; from pathlib import Path; print(load_config(Path('config.yaml')).llm)"` prints an `LlmConfig` with all four fields populated.
- Post-deploy Render DB query: `SELECT count(*) FROM posts WHERE lang_detected IS NOT NULL AND fetched_at > now() - interval '30 minutes'` returns ≥ 1 (≥ number of posts inserted in the last 30 min). Repeat across two consecutive cycles.

## Definition of Done

- [ ] **U0 lands FIRST (priority):** `plan_calls_for_cycle(cfg: Config | None = None)` signature change; both production callers pass `cfg`; 8+ test monkeypatches updated; `test_cycle_regression_net.py` ships with 2 new tests. Live Render cron reports `n_inserted > 0` on the next cycle.
- [ ] U1 lands: `LlmConfig` schema + `Config.llm` field + `model_validator(mode="before")` env resolution; `test_llm_config.py` ships with all default + env-override + yaml-overrides-env scenarios green.
- [ ] U2 lands: factory builders take `cfg: Config`; `_resolve_signal_model(cfg)` and `_resolve_translator_model(cfg)` take `cfg`; `build_anthropic_client_from_env.py` tests updated for the new signature, all existing assertions preserved.
- [ ] U3 lands: `monitor/cycle.py::_run_post_fetch` passes `self.cfg`; `monitor/management/commands/run_cycle.py` verified to pass `cfg` to the relevancy client build.
- [ ] U4 lands: per-batch `logger.warning("translator_batch_failed", exc_info=True)` in `translate_batch_pragmatics`; same for `classify_batch_pragmatics_full`; `_error_counts["translator_batch_failed"]` and `_error_counts["classifier_batch_failed"]` on `CycleRunner`; surfaced via `--json` `n_errors_by_type`.
- [ ] U5 lands: regression-net tests in `test_llm_config.py`, `test_translator_logging.py`, `test_cycle_error_counters.py`, `test_build_anthropic_client_from_env.py` all green.
- [ ] U6 lands: `config.yaml::llm:` block committed; operator step documented in plan body; post-deploy DB query verified for ≥2 consecutive cycles.
- [ ] Verification Contract gates all green.
- [ ] One commit on `main` (or feature branch) with `Scope delivered vs plan promised: match` footer.
- [ ] No out-of-scope files modified (verified via `git diff --stat` showing only the files named in U1-U6).
- [ ] Optional coordinated follow-ups (Items 1-7) referenced in `Optional coordinated follow-ups` for future `ce-plan` runs; none of them re-litigate this plan's decisions.

## Cross-references

- `docs/plans/2026-08-01-001-refactor-harvester-config-wiring-plan.md` — the config-only refactor that established `Config` as runtime source of truth; this plan extends the same discipline to LLM model names (was originally optional Item 7 in the 2026-08-01 backlog).
- `docs/issues/2026-07-13-bbf72b83-u3-evidence-review-notes.md` — v1 evidence note that first flagged the lang_detected bug on the X-monitor stack; v2 carried the same shape.
- `docs/issues/2026-07-30-001-internal-restore-failed-pg-restore-eof.md` — adjacent ops issue (DB recovery) tracked separately; out of scope here.
- `feedback_no-silent-scope-narrowing.md` — "fail loud on friction" rule that motivates U4 + U5 + the demotion of Items 1 + 2 (still optional, no longer blocking).
- `feedback_regression_net_in_every_plan.md` — regression-net discipline that U5 codifies for this plan's surface (factory signatures, log emission, typed counters).