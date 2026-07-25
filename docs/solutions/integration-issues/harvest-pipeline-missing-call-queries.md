---
title: V2 harvest pipeline degraded — only Call A planned, X_MONITOR_X_QUERY_SPECS not loaded
date: 2026-07-24
category: integration-issues
module: monitor
problem_type: integration_issue
component: tooling
symptoms:
  - "Harvest cycle producing ~3 new posts per 15-min run instead of expected ~200"
  - "CycleRunner._plan_calls reports 1 call planned instead of 6"
  - "Cron job runs successfully but nearly all posts are already in DB"
root_cause: config_error
resolution_type: config_change
severity: high
tags: [render, django, harvest, config, yaml, cycle, pipeline, settings]
---

# V2 harvest pipeline degraded — only Call A planned, X_MONITOR_X_QUERY_SPECS not loaded

## Problem

The v2 Django harvest pipeline on Render was planning only 1 API call per cycle (Call A, list-based) instead of 6 (Call A + B1–B3 + C1–C2), producing ~3 new posts per cycle instead of the ~200 the v1 pipeline achieves. The pipeline silently degraded without erroring.

## Symptoms

- `CycleRunner._plan_calls: 1 calls planned` — always exactly 1, never 6
- Cron output: `1 calls, 50 posts seen, 3 inserted` per cycle (vs expected 300/87)
- Dashboard feed showed stale / few new posts
- No errors in logs — the missing calls were simply never planned

## What Didn't Work

- **SCP-ing `settings.py` to Render** — the file deployed correctly but was immediately overwritten by the next `git push`-triggered Render deploy, which pulled the committed version without the config-loading code
- **Checking `X_MONITOR_LIST_ID`** — that env var was correctly set and Call A worked, confirming the list-based query path was functional
- **Running manual cycles** — they showed the same 1-call behavior, ruling out a cron-only issue

## Solution

Two changes in `project/settings.py` and `monitor/cycle.py`:

**1. Load `x_query_specs` from `config.yaml` into Django settings** (`project/settings.py`):

```python
# Before: X_MONITOR_X_QUERY_SPECS was never set
X_MONITOR_LIST_ID = env.int("X_MONITOR_LIST_ID", default=None)

# After: load x_query_specs from config.yaml
X_MONITOR_LIST_ID = env.int("X_MONITOR_LIST_ID", default=None)

_x_query_specs: list[dict] = []
_config_path = BASE_DIR / "config.yaml"
if _config_path.exists():
    try:
        import yaml as _yaml
        with open(_config_path) as _fh:
            _config = _yaml.safe_load(_fh)
        _x_query_specs = _config.get("x_query_specs") or []
    except Exception:
        pass
X_MONITOR_X_QUERY_SPECS = _x_query_specs
```

**2. Filter unsupported fields when constructing `XQuerySpec`** (`monitor/cycle.py`):

```python
# Before: passing raw YAML dict directly to XQuerySpec constructor
specs.append(XQuerySpec(**item))

# After: filter to only dataclass-accepted fields
import dataclasses as _dc
valid_fields = {f.name for f in _dc.fields(XQuerySpec)}
filtered = {k: v for k, v in item.items() if k in valid_fields}
specs.append(XQuerySpec(**filtered))
```

The `config.yaml` `x_query_specs` entries include a `notes` field (human-readable documentation) that is not a valid `XQuerySpec` dataclass field, causing `TypeError: XQuerySpec.__init__() got an unexpected keyword argument 'notes'` when passed directly.

## Why This Works

The v1 pipeline (`x_monitor/run.py`) reads `config.yaml` directly via `x_monitor/config.py:load_config()`. The v2 Django pipeline has its own settings system (`project/settings.py`) and never loaded the YAML config. The `_load_x_query_specs()` function in `cycle.py` reads from `settings.X_MONITOR_X_QUERY_SPECS`, which was never populated. With it defaulting to `None`, `_plan_calls` treated it as an empty list and planned only Call A.

The fix bridges the v1 config system into Django settings, reading the same `config.yaml` file the v1 pipeline uses. The field filtering handles the `notes` and any other YAML-only metadata fields that don't exist on the `XQuerySpec` dataclass.

## Prevention

- **Co-commit config loading with new settings consumers** — when adding a Django setting that reads from `config.yaml`, add the loading code and the consumer in the same commit to avoid a silent-degrade window
- **Add a system check** that warns or errors when `X_MONITOR_X_QUERY_SPECS` is empty in production (`python manage.py check --deploy`)
- **Assert call count in cycle tests** — a test that verifies `_plan_calls()` returns the expected number of calls when `config.yaml` is present
- **Deploy changes that touch settings via `git push`, not `scp`** — Render auto-deploys will overwrite scp'd files

## Related

- `render.yaml` — cron job definition and env vars
- `monitor/cycle.py` — `_plan_calls()`, `_load_x_query_specs()`, `_load_x_monitor_list_id()`
- `x_monitor/query_plan.py` — `XQuerySpec` dataclass definition
- `config.yaml` — source of truth for `x_query_specs`
