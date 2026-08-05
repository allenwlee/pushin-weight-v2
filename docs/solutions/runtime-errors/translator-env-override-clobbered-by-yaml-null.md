---
module: x_monitor
date: 2026-08-05
problem_type: runtime_error
component: tooling
severity: high
symptoms:
  - "translate() raises TimeoutError against api.minimax.io/anthropic on every cron cycle for ~6 hours"
  - "text_zh_cn column NULL on every freshly translated post (lang_detected NULL downstream)"
  - "env var X_MONITOR_TRANSLATOR_BASE_URL is set on the Render cron service but the run_cycle code path ignores it"
  - "translator_base_url: null in config.yaml silently wins over the env-var override"
root_cause: config_error
resolution_type: code_fix
related_components:
  - x_monitor/config.py
  - x_monitor/reattribute.py
  - x_monitor/translator.py
  - docs/plans/2026-08-04-001-swap-translator-to-deepseek-v4-plan.md
tags:
  - translator
  - env-var-override
  - yaml-precedence
  - merge-bug
  - config.py
  - load_config
  - minimax
  - deepseek-v4
last_updated: 2026-08-05
origin_session: 2026-08-05 (translator NULL regression investigation)
related_commits:
  - "f77cb90 fix(config): env-var override of translator_base_url no longer clobbered by yaml null"
status: verified-live
---

# Translator silently re-routed to M3 proxy because yaml `null` overrode env override

## Problem

For roughly 6 hours on 2026-08-05, every cron cycle of `pushinweight-harvest` produced posts with `text_zh_cn IS NULL`, because the translator was dialing `api.minimax.io/anthropic` instead of `api.deepseek.com/anthropic` despite the env var `X_MONITOR_TRANSLATOR_BASE_URL=https://api.deepseek.com/anthropic` being correctly set on the Render service. The translator traceback was a `TimeoutError: The read operation timed out` against the M3 proxy, where the model name had been swapped to `deepseek-v4-pro` — the proxy does not understand that model name and silently held the socket open past the SDK read timeout, leaving `text_zh_cn` null on every translated post.

## Symptoms

- `text_zh_cn IS NULL` on every post fetched in the 6-hour window starting at the 06:20 UTC cron cycle (post-deploy of plan `2026-08-04-001`)
- Translator traceback in `render logs --resources crn-d9gv94o6n6ts739tqaug` reads `TimeoutError: The read operation timed out` against `https://api.minimax.io/anthropic/v1/messages` — never against `api.deepseek.com`
- Service-level env on `pushinweight-harvest` correctly contains `X_MONITOR_TRANSLATOR_BASE_URL=https://api.deepseek.com/anthropic`; `render env list` shows it present and current
- DB query `SELECT count(*) FILTER (WHERE fetched_at >= NOW() - INTERVAL '1 hour' AND text_zh_cn IS NOT NULL) / NULLIF(count(*) FILTER (WHERE fetched_at >= NOW() - INTERVAL '1 hour'), 0) FROM posts` returns ~0 (was ≥ 0.95 prior to deploy)
- `cfg.llm.translator_model` resolves to `"deepseek-v4-pro"` (the new default), confirming the model swap landed but the base URL didn't follow

## What Didn't Work

- **Re-setting the env var via Render dashboard** — it was already correct; toggling it did not change the traceback's base URL
- **Checking the `pushinweight-secrets` env group** — operator step U3 of plan `2026-08-04-001` had landed; the env var was visible and correct
- **Assuming the merge in `load_config` was correct** — the code at `x_monitor/config.py:393` reads `merged_llm = {**env_llm_overrides, **raw_llm}` with a comment "yaml wins over env", so both env and yaml keys appeared present; nothing in a code review of the merge logic flags the bug because both sides of the spread look populated
- **Looking at `cfg.llm.translator_base_url` via `Config()` from a `python manage.py shell`** — returns `None`, which looks like "the env var just didn't make it through", redirecting investigation back at Render rather than at the merge logic
- **Adding more timeout to the SDK call** — the timeout is the right tool against a slow DS V4 call; the bug here is the call never reaches DS V4, so a bigger budget doesn't help

## Solution

The fix lives in `x_monitor/config.py:384-397` — the env-merge block in `load_config`. Build a `raw_llm_filtered` that drops `None` values before the dict spread, so a yaml key set to literal `null` no longer overwrites the env value.

**Before** (`x_monitor/config.py:393`, commit `8a07a99`):

```python
if env_llm_overrides:
    # Plan 2026-08-04-001: yaml wins over env, BUT a yaml `null` is
    # not "set" — it's an explicit instruction to use the default
    # path (which falls back to ANTHROPIC_BASE_URL). Filter nulls
    # from yaml so the env override takes effect. Without this
    # filter, a yaml like `translator_base_url: null` clobbers an
    # env-set value and silently re-routes the translator to the
    # M3 proxy with the DS V4 model name (timeout, lang_detected
    # NULL on every post).
    raw_llm_filtered = {
        k: v for k, v in raw_llm.items() if v is not None
    }
    merged_llm = {**env_llm_overrides, **raw_llm_filtered}  # yaml wins over env (non-null only)
    raw = {**raw, "llm": merged_llm}
```

The comment already explained the intent; the fix (in commit `f77cb90`, pushed, deploy Live) is the `raw_llm_filtered` comprehension on the lines above. After the comprehension, `raw_llm` is the yaml block with `None` values stripped, and the spread `{**env_llm_overrides, **raw_llm_filtered}` lets a yaml non-null still win, while yaml nulls are silently dropped so the env override takes effect.

The corresponding regression pin at `tests/test_translator_env_override.py` covers the four scenarios that produced the bug:

```python
def test_env_overrides_yaml_null_translator_base_url(tmp_path, monkeypatch):
    cfg_path.write_text("""\
llm:
  translator_model: minimax/MiniMax-M3.0[1m]
  translator_base_url: null
""")
    monkeypatch.setenv("X_MONITOR_TRANSLATOR_BASE_URL", "https://api.deepseek.com/anthropic")
    cfg = load_config(cfg_path)
    assert cfg.llm.translator_base_url == "https://api.deepseek.com/anthropic"
```

plus three siblings (`test_yaml_explicit_string_wins_over_env`, `test_no_env_no_yaml_returns_none`, `test_env_unset_yaml_null_returns_none`) that pin the rule in both directions. The file header documents the prod incident so a future reader sees why the test exists.

## Why This Works

The merge in `x_monitor/config.py:393` is `{**env_llm_overrides, **raw_llm}` — a dict spread where the right-hand side wins on key collision. YAML's literal `null` deserializes to a real Python `None`, which is a perfectly valid dict value, so the spread treats `translator_base_url: null` as "this key IS set" and overwrites the env-supplied value with `None`. The downstream consumer at `x_monitor/reattribute.py:466-493` (`build_translator_client_from_env`) resolves `base_url = cfg.llm.translator_base_url or os.environ.get("ANTHROPIC_BASE_URL")` — when `cfg.llm.translator_base_url` is `None`, the `or` short-circuits and the code falls through to `ANTHROPIC_BASE_URL`, which the Render service sets to `https://api.minimax.io/anthropic`. The translator then calls the M3 proxy with model name `deepseek-v4-pro` (the new default from `x_monitor/config.py:160-161`), the proxy holds the socket open because it doesn't recognize the model, the SDK read times out at 120 s, and `text_zh_cn` ends up null.

The "yaml wins" rule is correct for *non-null* values — operators who pin `translator_base_url: https://api.deepseek.com/anthropic` in yaml should not have an env var silently override their pin. But `null` is semantically distinct: it is the explicit instruction to use the default fallback path (per the comment at `config.yaml:99-105`), not an active value. Filtering nulls from `raw_llm` before the spread encodes that distinction in code: nulls are inert placeholders, non-null values are active pins.

This is also why the bug went undetected for 6 hours despite the env var being correctly set. Every layer that an operator or a debugger might inspect (Render dashboard env list, `Config()` shell output, the `if env_llm_overrides` branch in `load_config`) shows the right thing in isolation. The defect lives only in the interaction: the dict spread, the YAML `null` deserialization, and the `or` fallback in `build_translator_client_from_env`.

## Prevention

- **Regression pin tests for yaml-null vs env-override precedence** — the four tests in `tests/test_translator_env_override.py` make the rule falsifiable. Any future refactor of the env-merge block in `x_monitor/config.py:384-397` that re-introduces the null-clobber fails CI on the first test and surfaces the production impact in the assertion message.
- **"YAML wins for non-null values only" rule** — codify in code review: if the yaml value is a literal `null`, the env var wins; if the yaml value is a string or dict, yaml wins. The comprehension `{k: v for k, v in raw_llm.items() if v is not None}` is the canonical implementation; document the rule in a one-line comment at the comprehension site so the intent travels with the code.
- **Document the env-vs-yaml precedence rule in `CONCEPTS.md`** — operators reading `config.yaml:99-105` see the comment `# uses ANTHROPIC_BASE_URL env when null` but have no way to learn the rule for the *other* `llm.*` fields without reading `x_monitor/config.py:384-397`. A short entry in `CONCEPTS.md` ("yaml wins over env except for null values, which are inert placeholders") makes the rule discoverable from the docs index.
- **Startup smoke probe of `cfg.llm.translator_base_url`** — a one-line check at `manage.py run_cycle` startup that prints the resolved base URL (with the host redacted to first-label-only for logs) lets an operator see in the first cron log line where the translator is dialing. If `run_cycle` boots and the log shows `translator_base_url=api.minimax.io` while the env var is `api.deepseek.com`, the drift is visible immediately rather than 6 hours later when `text_zh_cn` goes null.
- **Audit `cfg.llm.*` resolution in the next config-touching change** — every plan that adds an env-var override for an `llm.*` field must list the corresponding yaml-null interaction in its Test scenarios. The swap plan `2026-08-04-001` missed this; the regression pin unit U9 closes the gap.

## Related Issues (from Related Docs Finder)

- `docs/plans/2026-08-04-001-swap-translator-to-deepseek-v4-plan.md` — plan that shipped with this gap; amendment captures the fix
- `docs/solutions/integration-issues/harvest-pipeline-missing-call-queries.md` — closest precedent: different code path (Django settings vs `load_config` merge), same flavor
- `docs/issues/2026-06-20-162625-x-monitor-v18-minimax-proxy-25x-slowdown.md` — documents the `ANTHROPIC_BASE_URL` precedence chain this fix perturbs
- `docs/reference/translator-output.md` — reference doc defining `text_zh_cn` (the column that went NULL)
- `docs/deploy/render.md` — Render runbook; the env-group surface where `X_MONITOR_TRANSLATOR_BASE_URL` lives

**Overlap assessment:** Low. No prior solution covers the yaml-null-vs-env-merge precedence bug specifically; closest precedent is a different mechanism on a related surface.
