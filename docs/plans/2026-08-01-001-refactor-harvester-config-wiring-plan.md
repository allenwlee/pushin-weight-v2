---
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
execution: code
title: "refactor: adopt x_monitor.config.load_config() as harvester runtime source of truth"
created: 2026-08-01
depth: standard
type: refactor
---

# refactor: adopt x_monitor.config.load_config() as harvester runtime source of truth

## Summary

The v2 harvester runtime (`monitor/cycle.py`) loads config from **three independent paths** that have drifted apart from `config.yaml`:

1. **Hardcoded `KNOWN_MODELS` frozenset** in `project/settings.py` (mirrors `config.yaml::enabled_models` by coincidence — drift risk)
2. **Module-scope constants** in `monitor/cycle.py` (`_CURSOR_OVERLAP`, `_MAX_LOOKBACK`, `_C1_MAX_RESULTS`, `_C1_MAX_PAGES`, `_MAX_TRUNCATION_WALKS`) — no operator override path
3. **Django settings** (`X_MONITOR_X_QUERY_SPECS`) populated by `project/settings.py` from `config.yaml` — works, but mixed-mode (settings + ad-hoc loaders + pydantic schema exists but unused)

A comprehensive pydantic schema (`x_monitor/config.py::Config`) covers every config.yaml field. It's used by tests and scripts via `load_config()`, but **the runtime cron does not use it.** This refactor closes that gap.

## Problem Frame

The 2026-07-31 cap-bump episode (`max_results 50 → 2000`, `max_pages 5 → 100`) shipped a `config.yaml` edit that **didn't reach the runtime for ~12 hours** because:

- The runtime reads from Django settings (`settings.X_MONITOR_CYCLE_LIMIT_PER_CALL`)
- Django settings were populated only by the `--limit-per-call 50` CLI flag in `render.yaml`
- The 2026-07-31 wiring added `X_MONITOR_CYCLE_LIMIT_PER_CALL` reads from `config.yaml::search.*` in `project/settings.py` (commit `9dad380`) — but this still uses Django settings, not the pydantic schema

The pattern is: every config.yaml field that the runtime touches needs to be wired through Django settings manually, with a custom getter in `monitor/cycle.py`. Adding a new field requires touching 3 files. The pydantic schema provides a single source of truth but isn't used.

After this refactor: every `config.yaml` field the runtime reads comes from `Config(...)` loaded once at startup. Adding a new field requires touching `x_monitor/config.py::Config` and the consumer.

## Requirements

- R1. `monitor/cycle.py` MUST instantiate `Config = load_config(Path("config.yaml"))` once per cycle (or once per process) and pass the relevant fields through the call chain.
- R2. `KNOWN_MODELS` in `project/settings.py` MUST be removed; runtime reads `Config.enabled_models` instead.
- R3. `_CURSOR_OVERLAP`, `_MAX_LOOKBACK`, `_C1_MAX_RESULTS`, `_C1_MAX_PAGES`, `_MAX_TRUNCATION_WALKS` MUST move from `monitor/cycle.py` module scope to `config.yaml::cycle:` block + `Config.cycle` pydantic field.
- R4. The `_load_enabled_models`, `_load_x_monitor_list_id`, `_load_x_query_specs`, `_load_primary_keywords`, `_load_brand_search_terms` ad-hoc helpers in `monitor/cycle.py` MUST either delegate to `cfg.<field>` access or be removed if redundant.
- R5. `manage.py run_cycle` MUST accept a `--config <path>` flag for test/script use (default: `config.yaml`). Required so tests can pass fixtures without disk I/O.
- R6. `CycleRunner.__init__` MUST accept `cfg: Config | None = None` (defaults to `load_config(Path("config.yaml"))` at instantiation).
- R7. The runtime config-loading path MUST be **single-sourced** — no ad-hoc fallback to Django settings for the fields covered by `Config`.
- R8. The 7-call hybrid shape (A + B1 + B2 + B3 + C1 + C2 + C3) MUST be preserved; this is a refactor of the loading mechanism, not the call structure.

## Key Technical Decisions

- **KTD1. Single `Config` instance per process.** *(session-settled: user-directed — chosen over "load config per cycle": config.yaml is read-only at runtime; per-process load avoids repeated disk I/O and matches the current `_load_X` pattern.)* `load_config()` is called once at `CycleRunner.__init__` time (or once at process start for the cron). The instance is held on `self.cfg` for the cycle's lifetime.

- **KTD2. `cycle:` block in config.yaml, not `runtime:` or `harvester:` block.** *(session-settled: user-directed — chosen over `runtime:`: the constants are specifically about the cycle's behavior — cursor overlap, lookback, C1 override, truncation walks. `runtime:` would imply a broader scope.)* Schema: `cycle: {cursor_overlap_seconds, max_lookback_hours, c1_max_results, c1_max_pages, max_truncation_walks}`.

- **KTD3. Django settings (`X_MONITOR_X_QUERY_SPECS` etc.) removed; `Config.x_query_specs` is the only source.** *(session-settled: user-directed — chosen over "keep both paths for backwards compat": the schema is strictly more comprehensive than the Django settings, no runtime caller uses anything the schema doesn't have, and keeping both paths re-creates the drift risk we're closing.)* Single source of truth.

- **KTD4. `KNOWN_MODELS` in `project/settings.py` removed; `Config.enabled_models` is canonical.** *(session-settled: user-directed — chosen over "keep KNOWN_MODELS as a validator-only fallback": the pydantic `_validate_models` validator on `Config.enabled_models` already enforces the "must be in known set" invariant; the frozenset becomes redundant once Config is loaded.)*

- **KTD5. Pydantic field ordering keeps `Config`'s current shape.** Adding `cycle: CycleConfig` between `dashboard` and `call_b_groups` (after `dashboard: DashboardConfig = DashboardConfig()`). No re-ordering of existing fields.

- **KTD6. `monitor/cycle.py::_load_enabled_models` removed; replaced with `cfg.enabled_models`.** *(session-settled: user-directed — chosen over "delegate to existing loader": the loader's fallback to `Brand.objects.filter(is_sentinel=False)` is for the no-config-yet case; the runtime always has config.yaml loaded, so the fallback is unreachable. Removing the loader eliminates dead code.)*

- **KTD7. `Config.cycle` defaults match current hardcoded values.** Schema default values are the existing constants, so a config.yaml without a `cycle:` block has zero observable behavior change. *(This is the regression-net safety net: the new schema defaults match the old hardcoded constants, so existing tests pass without config changes.)*

## Implementation Units

### U1. Add `CycleConfig` schema and `cycle:` block to `Config`

**Goal.** Define the pydantic schema for the 5 hardcoded runtime constants, surface them on `Config.cycle`, and add the `cycle:` block to `config.yaml` with current values.

**Files.**
- `x_monitor/config.py` — add `CycleConfig` class + field on `Config`
- `config.yaml` — add `cycle:` block with current values

**Approach.**
1. Define `CycleConfig` in `x_monitor/config.py` between `SearchConfig` (line 114) and `Config` (line 134). Fields:
   - `cursor_overlap_seconds: int = Field(default=60, ge=0)` (mirrors `_CURSOR_OVERLAP = timedelta(minutes=1)`)
   - `max_lookback_hours: int = Field(default=2, ge=1)` (mirrors `_MAX_LOOKBACK = timedelta(hours=2)`)
   - `c1_max_results: int = Field(default=150, ge=1)` (mirrors `_C1_MAX_RESULTS = 150`)
   - `c1_max_pages: int = Field(default=8, ge=1)` (mirrors `_C1_MAX_PAGES = 8`)
   - `max_truncation_walks: int = Field(default=5, ge=1)` (mirrors `_MAX_TRUNCATION_WALKS = 5`)
2. Add `cycle: CycleConfig = CycleConfig()` field to `Config` between `dashboard` and `call_b_groups`.
3. Add `cycle:` block to `config.yaml` after the `search:` block (around line 86):
   ```yaml
   # Cycle-level runtime constants (post-2026-08-01 wiring).
   # All five have defaults that match the prior hardcoded values, so
   # omitting this block preserves existing behavior.
   cycle:
     cursor_overlap_seconds: 60   # 1 minute overlap between windows
     max_lookback_hours: 2        # clamp cold-start sweep to 2h
     c1_max_results: 150          # C1 override (R4 in 2026-07-30-002)
     c1_max_pages: 8              # 150 / 20 per page
     max_truncation_walks: 5      # drain retries on truncated windows
   ```

**Test scenarios.**
- `x_monitor.config.load_config(Path("config.yaml"))` returns a `Config` whose `cfg.cycle` is a `CycleConfig` instance with the 5 expected fields and values from `config.yaml`.
- A `config.yaml` without a `cycle:` block loads successfully and yields the schema defaults (regression net for "defaults match old constants").
- Pydantic validators fire on bad values: `cursor_overlap_seconds=-1` raises; `max_lookback_hours=0` raises; etc.
- The existing `tests/test_query_plan_uniform.py` and `tests/test_migration_035.py` (which call `load_config`) still pass — no signature changes.

**Verification.** `pytest tests/test_query_plan_uniform.py tests/test_migration_035.py -v` green.

### U2. `CycleRunner.__init__` accepts `cfg: Config | None = None`; load once at process start

**Goal.** Plumb the `Config` instance into `CycleRunner` and the call chain so per-cycle constants come from `self.cfg.cycle` not module scope.

**Files.**
- `monitor/cycle.py` — `CycleRunner.__init__` signature, instantiation path
- `monitor/management/commands/run_cycle.py` — pass `cfg` to `CycleRunner(...)`
- `monitor/management/commands/backfill.py` — same
- `monitor/tasks.py` (if exists) — Celery task wrapper, same

**Approach.**
1. Add `cfg: Config | None = None` keyword to `CycleRunner.__init__`.
2. Inside `__init__`, if `cfg is None`, instantiate via `from x_monitor.config import load_config; cfg = load_config(Path("config.yaml"))`. Store on `self.cfg`.
3. In `monitor/management/commands/run_cycle.py::handle`, instantiate `cfg = load_config(Path("config.yaml"))` once at the top, pass to `CycleRunner(cfg=cfg, ...)`.
4. Same in `monitor/management/commands/backfill.py`.
5. Same in `monitor/tasks.py::run_cycle_task` if it constructs `CycleRunner`.

**Test scenarios.**
- `CycleRunner(dry_run=True)` (no cfg arg) loads `config.yaml` from the repo root and exposes `runner.cfg` with the 7-call hybrid shape preserved.
- `CycleRunner(cfg=Config(...))` uses the passed config and skips the disk load.
- Two `CycleRunner` instances in the same process share `cfg` when passed explicitly (operator-managed singleton).

**Verification.** `pytest tests/ -k "cycle" -v` green; manual `CycleRunner(dry_run=True)._plan_calls()` returns 7 calls (matches existing pre-refactor behavior).

### U3. Replace module-scope constants + `_load_*` helpers with `self.cfg.<field>` access

**Goal.** Remove the duplicate state in `monitor/cycle.py` so every config field comes from `self.cfg`. This is the biggest delta — touches `_fetch_tweets`, the cursor resolution path, and the truncation walk loop.

**Files.**
- `monitor/cycle.py` — multiple edits
- `project/settings.py` — remove `KNOWN_MODELS`, remove `X_MONITOR_X_QUERY_SPECS` Django setting wiring
- `tests/test_query_plan_uniform.py` — no edits (load_config already used)
- `tests/test_cycle_anomaly_metrics.py`, `tests/test_query_plan_hybrid_shapes.py`, `tests/test_mistral_call_placement.py` — verify still pass

**Approach.**
1. **Module-scope constants**: Remove `_CURSOR_OVERLAP`, `_MAX_LOOKBACK`, `_C1_MAX_RESULTS`, `_C1_MAX_PAGES`, `_MAX_TRUNCATION_WALKS` from `monitor/cycle.py`. Replace usages with `self.cfg.cycle.cursor_overlap_seconds` (converted to `timedelta(seconds=...)`), `self.cfg.cycle.max_lookback_hours`, etc.
2. **`_load_enabled_models`**: Remove. Replace all callers with `self.cfg.enabled_models` or `self.cfg.enabled_models` intersected with the brand filter from `--brands`.
3. **`_load_x_monitor_list_id`**: Remove. Replace callers with `self.cfg.x_monitor_list_id` (added to the `Config` schema if not present — verify by inspecting the schema; current schema has `x_monitor_list_id` as a top-level field already per the 2026-07-22 prod-Django cutover).
4. **`_load_x_query_specs`**: Remove. Replace callers with `self.cfg.x_query_specs`. The runtime gets specs from `Config.x_query_specs` directly (already a `list[XQuerySpec]` from the pydantic load).
5. **`_load_primary_keywords`, `_load_brand_search_terms`**: KEEP (these read from the DB, not config — different concern).
6. **Django settings cleanup**: In `project/settings.py`, remove:
   - `KNOWN_MODELS` frozenset block
   - `X_MONITOR_X_QUERY_SPECS` Django setting (the load + assign block)
   - `X_MONITOR_CYCLE_LIMIT_PER_CALL`, `X_MONITOR_CYCLE_MAX_PAGES_PER_CALL`, `X_MONITOR_CYCLE_MAX_PER_PAGE` settings (the 2026-07-31 wiring that read from `config.yaml::search.*`) — these are now redundant; `Config.search.{max_results, max_pages, max_per_page}` is the source.

**Test scenarios.**
- `CycleRunner(dry_run=True)._plan_calls()` returns 7 calls with the same shape as pre-refactor (verified via existing `tests/test_query_plan_hybrid_shapes.py` and `tests/test_cycle_call_layout.py`).
- `tests/test_mistral_call_placement.py::test_seven_call_shape_invariant` still passes (verifies the 7-call count).
- `tests/test_hybrid_harvest_regression_net.py::test_call_b_groups_brand_split_unchanged` still passes (verifies call_b_groups[0] has 5 brands post-mistral demotion).
- `monitor/cycle.py` no longer imports `KNOWN_MODELS` from `project.settings` (verified via `grep`).
- `monitor/cycle.py` no longer references `_CURSOR_OVERLAP`, `_MAX_LOOKBACK`, `_C1_MAX_RESULTS`, `_C1_MAX_PAGES`, `_MAX_TRUNCATION_WALKS` (verified via `grep`).
- `project/settings.py` no longer defines `KNOWN_MODELS` or the X_MONITOR_CYCLE_* settings.

**Verification.** `pytest tests/ -v` all green; grep audits clean; manual smoke test via `manage.py run_cycle --dry-run` produces 7 calls and writes no rows.

### U4. Pin the cycle shape + 5-cycle-constants as regression net

**Goal.** Robust regression nets: tests that pin the AFTER state so any future change to `Config.cycle` defaults or `cycle.py` constant reads fails loudly. Per user's explicit ask.

**Files.**
- `tests/test_cycle_runtime_constants.py` (new) — pins `Config.cycle` defaults + runtime reads

**Approach.**
1. **Constants default-pinning test**: Create a `tests/test_cycle_runtime_constants.py::test_cycle_config_defaults` test that loads `Config()` with an empty dict and asserts:
   - `cfg.cycle.cursor_overlap_seconds == 60`
   - `cfg.cycle.max_lookback_hours == 2`
   - `cfg.cycle.c1_max_results == 150`
   - `cfg.cycle.c1_max_pages == 8`
   - `cfg.cycle.max_truncation_walks == 5`
   - All have a docstring + `BEFORE` comment explaining what the prior hardcoded values were, so a future change sees the diff.
2. **Runtime-resolves-from-config test**: Create `tests/test_cycle_runtime_constants.py::test_cycle_runner_uses_config_cycles` that:
   - Patches `Path("config.yaml")` to point at a temp file with `cycle: {c1_max_results: 999}` (a deliberately weird value)
   - Instantiates `CycleRunner(dry_run=True, cfg=load_config(tmp_path))`
   - Asserts `runner.cfg.cycle.c1_max_results == 999` (proves the runner reads from `cfg.cycle`, not from a hardcoded constant)
3. **Known-models-removed test**: `test_no_known_models_frozenset_in_settings` — imports `project.settings` and asserts `hasattr(settings, "KNOWN_MODELS") is False`. Pins the deletion.
4. **7-call hybrid shape pin** (already in `tests/test_mistral_call_placement.py::test_seven_call_shape_invariant`): no new test needed; existing test covers it.
5. **Runtime-no-settings-fallback pin**: `test_cycle_runner_no_x_query_specs_fallback` — asserts `monitor.cycle._load_x_query_specs` no longer exists (the function is removed).

**Test scenarios.**
- All 5 default-pinning assertions pass.
- All 3 runtime-resolution assertions pass (weird config values propagate through).
- Removing `KNOWN_MODELS` causes the deletion-pin test to fail.
- Restoring `_load_x_query_specs` to its old form causes the runtime-no-settings-fallback pin to fail.
- All existing tests in `tests/test_query_plan_hybrid_shapes.py`, `tests/test_hybrid_harvest_regression_net.py`, `tests/test_mistral_call_placement.py`, `tests/test_cycle_call_layout.py` still pass.

**Verification.** `pytest tests/ -v` all green; deletion-pin tests pass.

## Out of Scope

- Touching `monitor/quote_tweets.py`, `monitor/views.py`, `monitor/dashboard.py` — they have their own config loaders (env-driven) and are out of the harvester scope.
- The `claude-haiku-4-5` LLM model name in `x_monitor/relevancy.py` and `x_monitor/attribution.py` — operator can override via env var; not in config.yaml today.
- The `_CURSOR_OVERLAP` value being `60` seconds — the schema default is 60; operator can change in `config.yaml`. Refactor is about the wiring, not the value.
- Removing `_load_primary_keywords` and `_load_brand_search_terms` — these read from the DB, not config.yaml. Different concern.

## Deferred to Follow-Up Work

- `monitor/quote_tweets.py::staff_handles_set(enabled_models=...)` could also be migrated to `cfg.enabled_models` once its QuoteTweetConfig is plumbed the same way. Out of scope here per "harvester only".
- The pydantic schema's `_validate_models` enforces `enabled_models ⊆ KNOWN_MODELS`. After this refactor, `KNOWN_MODELS` lives only in `x_monitor/config.py`. Consider extracting to a separate `brands.py` constant module if the circular import becomes painful.

## Risks & Mitigations

- **Risk:** Removing `KNOWN_MODELS` from `project/settings.py` breaks other code paths that import it. **Mitigation:** `grep -r "KNOWN_MODELS" --include="*.py"` before delete; the audit shows only `monitor/cycle.py:68` imports it (KTD6's load_enabled_models path). After cycle.py stops using it, the import has no callers.
- **Risk:** Runtime behavior changes when the constants move from module scope to `Config.cycle` if the schema default values drift from the hardcoded values. **Mitigation:** KTD7 — defaults match prior hardcoded values exactly. U4's regression net pins the defaults.
- **Risk:** Two `CycleRunner` instances in the same process (e.g., backfill + cron) get different `cfg` instances if one is loaded per-call. **Mitigation:** KTD1 — `load_config()` is called once at process start (in `manage.py run_cycle::handle`), and `cfg` is passed through. Same path for backfill.
- **Risk:** `Config.x_query_specs` doesn't survive a pydantic validation failure that the old `_load_x_query_specs` would have swallowed (the old loader silently returned None on bad input). **Mitigation:** KTD7 — pydantic raises on bad input, which is correct behavior; the operator fixes the config and restarts. The old "swallow and skip" behavior was the source of the 2026-07-22 drift bug.
- **Risk:** Tests that construct `XQuerySpec(...)` directly (not via `Config`) may break if `Config` adds new required fields. **Mitigation:** The existing `Config` schema is unchanged; only adding `cycle: CycleConfig`. No existing field becomes required.

## Verification Contract

- `pytest tests/ -v` — all tests pass, including the new `tests/test_cycle_runtime_constants.py` (4 new tests) and the unchanged existing tests.
- `grep -r "KNOWN_MODELS" --include="*.py" /Users/fuchitalee/development/pushin-weight-v2/` returns zero hits outside `x_monitor/config.py`.
- `grep -r "_CURSOR_OVERLAP\|_MAX_LOOKBACK\|_C1_MAX_RESULTS\|_C1_MAX_PAGES\|_MAX_TRUNCATION_WALKS" --include="*.py" /Users/fuchitalee/development/pushin-weight-v2/monitor/` returns zero hits.
- `manage.py run_cycle --dry-run --json` produces a 7-call plan output that matches the pre-refactor shape (verified via diff against the 2026-08-01 pre-refactor `--json` output).
- `python -c "from monitor.cycle import CycleRunner; r = CycleRunner(dry_run=True); print(r.cfg.cycle)"` prints a `CycleConfig` instance with the 5 expected fields populated.
- Live cron cycle (post-deploy): cycle fires within 15 min, completes without error, persists ≥1 post.

## Definition of Done

- [ ] U1 lands: `CycleConfig` schema + `cycle:` block in `config.yaml`
- [ ] U2 lands: `CycleRunner.__init__` accepts `cfg` kwarg; `run_cycle` + `backfill` instantiate it
- [ ] U3 lands: 5 module-scope constants removed, 4 `_load_X` helpers removed, `KNOWN_MODELS` + `X_MONITOR_*` settings removed from `project/settings.py`
- [ ] U4 lands: `tests/test_cycle_runtime_constants.py` ships with 4 new tests, all green
- [ ] Verification Contract gates all green
- [ ] One commit on `main` (or feature branch) with `Scope delivered vs plan promised: match` footer
- [ ] No out-of-scope files modified (verified via `git diff --stat` showing only `x_monitor/config.py`, `config.yaml`, `monitor/cycle.py`, `monitor/management/commands/run_cycle.py`, `monitor/management/commands/backfill.py`, `monitor/tasks.py`, `project/settings.py`, `tests/test_cycle_runtime_constants.py`)
- [ ] Live cron cycle verified to fire + persist on the new code
