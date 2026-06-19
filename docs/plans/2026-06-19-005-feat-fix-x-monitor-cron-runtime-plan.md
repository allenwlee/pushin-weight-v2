---
title: Fix x-monitor cron runtime (plist Python, list_id config, signal classifier)
type: fix
status: active
date: 2026-06-19
---

# Fix x-monitor cron runtime

## Overview

The x-monitor pipeline on fuchitalee has not successfully completed a cycle since 2026-06-16 19:11 JST (~50 hours of silence). Three independent defects prevent the cron from running, and a fourth data-table anomaly blocks the dashboard from rendering signals even when the cron does run. This plan ships four small, ordered fixes:

1. **Patch the live LaunchAgent** to invoke the venv's Python interpreter instead of `python3` (which resolves to a system Python that has no `x_monitor` package installed).
2. **Install the scheduled 15-minute LaunchAgent** so the pipeline runs on cadence rather than only on YAML file changes.
3. **Add `x_monitor_list_id` to `config.yaml`** so `RunPipeline.execute()` stops raising the v1.7 list-required `ValueError`.
4. **Diagnose and remediate `post_brand_signals = 0`** in the production SQLite DB — the v1.8 `reattribute` subcommand was run without an `AnthropicClaudeClient`, so per-brand signal classification was silently skipped, leaving the dashboard's polarity cards unrenderable.

## Problem Frame

Verified 2026-06-19 21:20 JST on fuchitalee:

- `launchctl list | grep x-monitor` shows only `com.fuchitalee.x-monitor` loaded. The 15-minute scheduled plist `com.fuchitalee.x-monitor.scheduled` exists at `x-monitoring/deploy/com.fuchitalee.x-monitor.scheduled.plist` but is NOT symlinked into `~/Library/LaunchAgents/` and therefore NOT loaded.
- `~/Library/Logs/x-monitor/stdout.log` mtime: 2026-06-16 19:11 JST (last successful cycle).
- `~/Library/Logs/x-monitor/stderr.log` mtime: 2026-06-18 14:02 JST (last error, captured below).
- Latest `posts.created_at`: 2026-05-27 19:20 JST — 22 days before the last successful cycle. The pipeline has not ingested any new posts in 22 days.
- DB row counts: `posts=2008`, `post_brands=2700`, `post_mentions=2147`, `post_brand_signals=0`, `_migrations=4`. Migration 004 is live and the v1.8 attribution ran on historical data — but signals are empty.
- The two stacked errors in `stderr.log`:
  1. `/opt/homebrew/opt/python@3.14/bin/python3.14: No module named x_monitor.__main__; 'x_monitor' is a package and cannot be directly executed` — the live plist invokes bare `python3`, which resolves to system/Homebrew Python 3.14 with no `x_monitor` importable.
  2. `ValueError: config.x_monitor_list_id must be set in v1.7 — Call A is list-based; see plan §'Call A — list-based fan-in' for the operator steps to create the list.` — even if the Python issue were fixed, the v1.7 gate at `x_monitor/run.py:376-384` raises unconditionally before any TwitterAPI.io request.

The combined effect: the LaunchAgent slot is reserved but no process has run successfully in 50 hours; the dashboard renders stale data and the treemap polarities show as zero.

## Requirements Trace

- **R1.** After this plan lands, `python3 -m x_monitor run` invoked from the live `~/development/minimax-marketing/x-monitoring/` checkout exits 0 and writes one new cycle to `~/Library/Logs/x-monitor/scheduled-stdout.log` (or `stdout.log`) within 15 minutes of unit completion.
- **R2.** The scheduled LaunchAgent is loaded via `launchctl load -w ~/Library/LaunchAgents/com.fuchitalee.x-monitor.scheduled.plist` and `launchctl list` shows `com.fuchitalee.x-monitor.scheduled` with a numeric PID.
- **R3.** `python3 -m x_monitor run --dry-run` exits 0 (NOT 2) on the live checkout after both plist and config fixes are applied.
- **R4.** After one full cron cycle, `SELECT COUNT(*) FROM posts WHERE created_at > datetime('now', '-1 day')` returns ≥ 1.
- **R5.** After the signal-classifier remediation, `SELECT COUNT(*) FROM post_brand_signals` returns > 0 and matches the `post_brands` row count within ±5% (some `compute_post_brands` rows may be `_unattributed` and excluded by the v1.8 CHECK constraint).
- **R6.** The dashboard at `http://localhost:5000/grid` renders polarity values (not zeros) for ≥ 1 brand card after one cron cycle.
- **R7.** Both plist edits are idempotent: reloading the plist twice does not duplicate cron invocations or break the venv interpreter reference.

## Scope Boundaries

- **No new feature work.** This plan fixes runtime blockers and a data gap. No new dashboards, no new extractors, no new detection YAML.
- **No new v1.8 code paths.** The four extractors + `compute_post_brands` already work end-to-end. The failures are operational (cron wiring) and a missed reattribute flag (`--anthropic`).
- **No re-fetching of historical data.** The 2,008 posts already in the DB stay. The 22-day ingestion gap closes naturally once the cron runs.
- **No x.com list-add attempts.** The 12-handle list-add was previously BLOCKED on the x.com API + Cloudflare (per memory `project_x_monitoring_list_management_2026-06-17.md` and `project_x_monitoring_cloudflare_block_2026-06-18.md`). This plan assumes the operator has either already populated the list in the x.com UI manually OR accepts degraded data quality for the brands whose handles are missing. The v1.7 startup sanity check + 3-cycle list-drift detection (per `feedback_twitterapi_unknown_list_silent_fallback.md`) will surface a wrong list_id within 3 cycles.
- **No translation changes.** `text_en` / `text_zh_cn` / `lang_detected` are populated by `x_monitor.translator` separately and are out of scope.

## Context & Research

### Relevant Code and Patterns

- `~/Library/LaunchAgents/com.fuchitalee.x-monitor.plist` (LIVE, WatchPaths-driven) — current `ProgramArguments` is `/bin/zsh -c "source ~/.env.secrets && exec python3 -m x_monitor run"`. Needs `python3` → `<absolute>/x-monitoring/.venv/bin/python`.
- `x-monitoring/deploy/com.fuchitalee.x-monitor.scheduled.plist` (NOT LOADED) — uses `StartCalendarInterval` with minutes 0/15/30/45. Invokes `x-monitoring/deploy/run-pipeline-with-notify.sh` which already correctly uses `.venv/bin/python`. Pattern to mirror: the wrapper script isolates the venv path and adds osascript failure notification.
- `x-monitoring/deploy/run-pipeline-with-notify.sh` — reference pattern: `cd <abs>; source ~/.env.secrets; .venv/bin/python -m x_monitor run > "$LOG" 2>&1` followed by an osascript notification on non-zero exit.
- `x-monitoring/x_monitor/run.py:376-384` — the v1.7 `x_monitor_list_id` gate. Fixes by setting `x_monitor_list_id: 2067062923525275922` in `config.yaml`. **NOTE:** prior memory recorded this as `2067062923525275926` (digit transposition at position 7); the correct ID per `project_x_monitoring_v17_2026-06-17.md` and `project_x_monitoring_list_management_2026-06-17.md` is `2067062923525275922`. Pydantic field at `x_monitor/config.py:94` accepts `int | None`.
- `x-monitoring/x_monitor/reattribute.py:271-290` — `classify_signal(text, brand_ids, brand_registry, anthropic_client=None)`. **The default `anthropic_client=None` skips signal classification entirely**, which is why `post_brand_signals=0`. Fix requires re-running `reattribute` with an `AnthropicClaudeClient` instance built from env.
- `x-monitoring/x_monitor/store.py:796-828` — `insert_post_mentions` correctly implements ON CONFLICT DO UPDATE. The reattribute path already calls it (verified in `reattribute.py`). The 2,147 `post_mentions` rows in production confirm the path works for `body_keyword` and `search_term` sources — `user_mention` and `hashtag` are not populated by the cron hot path (documented gap in `run.py:498-560` comment), but the reattribute does populate them from `posts.entities` JSON.

### Institutional Learnings (must-respect)

1. **`feedback_pkill_matches_all_dashboardapp.md`** (P0): `pkill -f DashboardApp` kills the live dashboard on :5000 along with any worktree copy because the argv strings are identical. **All dashboard restart steps in Unit 3 must use `lsof -nP -iTCP:5000 -sTCP:LISTEN -t | xargs -r kill`.** This pattern is restated in `x-monitoring/deploy/migration-004-runbook.md` deploy step 3.
2. **`feedback_twitterapi_unknown_list_silent_fallback.md`** (P0): TwitterAPI.io's `list:<id>` operator silently returns 20 random Latest tweets when the list ID is unknown or typo'd (HTTP 200, no error). The v1.7 startup sanity check catches this on the first cycle. **Unit 3 must include a one-shot query against the configured list_id and assert ≥1 of the canonical brand handles appears in the first 20 results** — this is the operator's defense against silent fallback.
3. **`feedback_x_api_free_tier_blocks_lists.md`** + **`project_x_monitoring_cloudflare_block_2026-06-18.md`** (P0): the x.com list-add API is BLOCKED on Free tier (HTTP 403 code 453) and additionally Cloudflare-gated. The list at `2067062923525275922` may have 0–12 members depending on whether the operator manually added handles in the x.com UI. The plan does NOT attempt to add handles; the v1.7 plan's startup sanity check + 3-cycle list-drift detection will surface empty-list conditions.
4. **`feedback_worktree_hygiene_x_monitoring.md`** (P1): worktrees live at `<repo>/worktrees/<name>/` and symlink `.venv` and `data/x_monitoring.db` from main. The cron plist's `WorkingDirectory` is the main checkout. **All edits in this plan target the main checkout files**, not worktrees.
5. **`project_x_monitoring_v18_2026-06-19.md`** (P1): the v1.8 reattribute on 2028 historical posts ran on 2026-06-19 without `--anthropic`, hence `post_brand_signals=0`. The v1.8 runbook's MON-09 monitoring check ("post_brand_signals distribution by signal: all zeros after 4h = per-brand classifier not running") would have caught this. Unit 4 is the remediation.
6. **`feedback_reload_plugins_resets_project_config.md`** + general macOS LaunchAgent hygiene (P2): after `launchctl unload && launchctl load` on a plist, watch the next cycle's stderr/stdout to confirm the new program arguments took effect. `launchctl print <label>` shows the loaded `ProgramArguments` verbatim.

### External References

- macOS `launchctl` reference: `launchctl load -w <plist>` registers and enables the agent (writes to `~/Library/LaunchAgents/<label>.plist` override directory). Without `-w`, the agent is loaded but not bootstrapped at next login. Per `man launchctl`, prefer `bootstrap gui/$(id -u) <plist>` for newer macOS — but the existing `load` invocation has worked for v1.6 plists, so keep the established pattern.

## Key Technical Decisions

- **Patch the LIVE plist AND install the SCHEDULED plist, do not replace one with the other.** The WatchPaths plist is still useful for forcing an immediate cycle after a `data/queries/<model>.yaml` edit. The scheduled plist provides the 15-minute baseline cadence. Both target the same WorkingDirectory and the same `RunPipeline.execute()` call path. The user explicitly requested "patch both."
- **Mirror the existing wrapper-script pattern in the WatchPaths plist** instead of inlining `.venv/bin/python` directly. This keeps the two plists consistent and makes future venv-path changes a single-file edit. Create a second wrapper `deploy/run-pipeline-watchpaths.sh` (or generalize the existing one with an argument) — recommendation: a shared wrapper that accepts the cycle mode via env var.
- **List ID `2067062923525275922`** (not `...77926`). Three prior memory entries document this; the trailing `5` vs `7` digit transposition is exactly the failure mode `feedback_twitterapi_unknown_list_silent_fallback.md` warns about. Pydantic accepts an integer YAML literal; do NOT quote it (causes string coercion in some YAML loaders).
- **Smoke test runs `--dry-run` AFTER the config patch lands.** The `x_monitor_list_id` `ValueError` fires before the `--dry-run` short-circuit, so dry-running before the config fix would just reproduce the same error. Sequencing matters.
- **post_brand_signals remediation = re-run reattribute with `--anthropic`**, not by editing source code. `x_monitor/reattribute.py` already accepts `anthropic_client=...` as a parameter; the CLI subparser at `x_monitor/__main__.py:786` accepts `--with-llm` (verified) which constructs the client from env. The fix is operational, not code.
- **Reattribute runs on the SAME database the cron writes to**, so the smoke-test cycle and the signal-backfill cycle are independent operations on independent tables. No need to quiesce the cron during backfill (the `pipeline_lock` in `x_monitor.run` prevents overlapping `run` calls, but `reattribute` and `run` do not contend on the same lock).

## Open Questions

### Resolved During Planning

- **Which plist is the live cron?** The WatchPaths plist `com.fuchitalee.x-monitor` is the only one in `launchctl list`. The scheduled plist exists in `deploy/` but is not loaded.
- **Why is `post_mentions=2147` not 0?** Because the reattribute path runs through `attribute_to_brands` (plural) which emits `MentionRow`s from all 4 sources where data is available. `body_keyword` + `search_term` produce 2147 rows; `user_mention` and `hashtag` would add more if `posts.entities` JSON is populated (per the documented `run.py:498-560` limitation).
- **Why is `post_brand_signals=0`?** Because the 2026-06-19 reattribute ran without `--anthropic` and `classify_signal(anthropic_client=None)` returns `{}`.
- **Is the list actually populated with 12 handles?** Unknown. Not blocking this plan. The cron will surface empty-list conditions via degraded signal/noise in the dashboard within 3 cycles.

### Deferred to Implementation

- **Exact `--with-llm` CLI flag wiring on `__main__.py`** — verified the flag exists per memory; exact argparse definition may have moved. Implementer should grep before referencing.
- **Whether `anthropic_client=None` triggers a warning at reattribute time** — if it does, the stderr from the 2026-06-19 run would document the gap. If not, the post_brand_signals=0 anomaly was silent. Implementer should check stderr for any `classify_signal` warnings.
- **Number of rows to expect after re-run** — depends on the Anthropic API response shape and rate limits. The 2,008 posts × ~1.3 brands/post = ~2,700 signal rows expected (matches the post_brands row count).

## High-Level Technical Design

> *Directional guidance for review, not implementation specification. The implementing agent should treat this as context, not code to reproduce.*

### Cron firing sequence after this plan

```
┌──────────────────────────────────────────────────────────────┐
│ macOS launchd                                                │
│                                                              │
│  ┌─ com.fuchitalee.x-monitor (WatchPaths)  ─ loaded today ─┐│
│  │  Trigger: file change in data/queries, data/accounts     ││
│  │  Program: deploy/run-pipeline-watchpaths.sh              ││
│  │  └─→ cd ~/development/minimax-marketing/x-monitoring     ││
│  │      source ~/.env.secrets                               ││
│  │      .venv/bin/python -m x_monitor run                  ││
│  └──────────────────────────────────────────────────────────┘│
│                                                              │
│  ┌─ com.fuchitalee.x-monitor.scheduled  ─ NEWLY LOADED ─────┐│
│  │  Trigger: StartCalendarInterval Minute=0,15,30,45       ││
│  │  Program: deploy/run-pipeline-with-notify.sh (existing)  ││
│  │  └─→ cd ~/development/minimax-marketing/x-monitoring     ││
│  │      source ~/.env.secrets                               ││
│  │      .venv/bin/python -m x_monitor run                  ││
│  │      [on non-zero exit] osascript display notification   ││
│  └──────────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────────┘
                          ↓
            ┌──────────────────────────────┐
            │ RunPipeline.execute()        │
            │ (x_monitor/run.py:376)       │
            │                              │
            │  if config.x_monitor_list_id │
            │     is None:                 │
            │      raise ValueError        │ ←── UNIT 2 FIXES THIS
            │                              │
            │  plan = plan_calls(          │
            │    data_dir, models,         │
            │    x_monitor_list_id=cfg...) │
            │  for call in plan:           │
            │    tweets = api.search(...)  │
            │    for tweet in tweets:      │
            │      insert_posts(           │
            │        tweet, mentions, ...) │
            │        → posts               │
            │        → post_brands         │
            │        → post_mentions       │
            │        → post_brand_signals  │
            └──────────────────────────────┘
                          ↓
                 ~/Library/Logs/x-monitor/
                 scheduled-stdout.log (NEW after unit 1+2)
                 stdout.log (continues from WatchPaths)
```

### Signal-classifier remediation

```
x-monitor v1.8 reattribute CLI
                            ↓
        ┌─────────────────────────────────┐
        │ python3 -m x_monitor reattribute│
        │   --with-llm                    │ ←── CLI flag constructs
        │   --batch-size 100              │     AnthropicClaudeClient
        └─────────────────────────────────┘     from env
                            ↓
            reattribute_all_posts(db,
                anthropic_client=client)
                            ↓
        ┌─────────────────────────────────────┐
        │ for post in posts:                  │
        │   mentions = attribute_to_brands(…) │
        │   post_brands = compute_post_brands(│
        │       post, mentions)               │
        │   signals = classify_signal(         │
        │       text, brand_ids,              │
        │       brand_registry,               │
        │       anthropic_client=client)      │ ←── now returns dict
        │                                      │     instead of {}
        │   for brand_id, signal in signals:  │
        │     insert_post_brand_signals(…)     │
        └─────────────────────────────────────┘
                            ↓
                post_brand_signals: 0 → ~2700
```

## Implementation Units

### Unit 1: Patch the live WatchPaths LaunchAgent and create a shared wrapper script

**Goal:** Make `com.fuchitalee.x-monitor.plist` invoke `.venv/bin/python` instead of bare `python3`, via a wrapper script that mirrors the pattern used by the scheduled plist.

**Requirements:** R1, R7

**Files:**
- Modify: `x-monitoring/deploy/run-pipeline-with-notify.sh` (generalize to accept cycle mode via env, OR create a sibling)
- Create: `x-monitoring/deploy/run-pipeline-watchpaths.sh` (alternative: a second wrapper for the WatchPaths plist)
- Modify: `~/Library/LaunchAgents/com.fuchitalee.x-monitor.plist`
- Create (operator action, documented in plan): `~/Library/LaunchAgents/com.fuchitalee.x-monitor.scheduled.plist` (symlink to `x-monitoring/deploy/com.fuchitalee.x-monitor.scheduled.plist`)

**Approach:**
- Either (a) generalize `run-pipeline-with-notify.sh` to accept a `$1` arg for "cycle mode" (`scheduled` vs `watchpaths`) and use it in the osascript notification subtitle, OR (b) create a sibling `run-pipeline-watchpaths.sh` that omits the osascript notification (WatchPaths fires on every YAML edit — too noisy). The sibling approach is preferred because WatchPaths fires often and osascript popups on every config edit would be annoying.
- The WatchPaths plist's new `ProgramArguments`: `/bin/zsh -c "<abs>/x-monitoring/deploy/run-pipeline-watchpaths.sh"`.
- The wrapper script body mirrors `run-pipeline-with-notify.sh` lines 1-12 (the pre-osascript section): `cd`, `source ~/.env.secrets`, `.venv/bin/python -m x_monitor run`, `exit $?`.
- After editing, run `launchctl unload ~/Library/LaunchAgents/com.fuchitalee.x-monitor.plist && launchctl load -w ~/Library/LaunchAgents/com.fuchitalee.x-monitor.plist` (or use `launchctl kickstart -k gui/$(id -u)/com.fuchitalee.x-monitor` for an in-place restart).
- Confirm with `launchctl print gui/$(id -u)/com.fuchitalee.x-monitor` that the loaded `program arguments` shows the wrapper script path.

**Patterns to follow:**
- `x-monitoring/deploy/run-pipeline-with-notify.sh:1-12` — the existing wrapper pattern.
- `x-monitoring/deploy/com.fuchitalee.x-monitor.scheduled.plist` — sibling plist for the cron cadence.

**Test scenarios:**
- **Happy path - wrapper script invoked manually:** `. /path/to/run-pipeline-watchpaths.sh` exits 0 (no osascript side effect, since it's the WatchPaths variant) and writes to `~/Library/Logs/x-monitor/watchpaths-stdout.log` (new log file).
- **Happy path - WatchPaths plist reload:** after `launchctl load -w`, `launchctl print` shows the wrapper script path as `program = /bin/zsh`.
- **Edge case - launchctl unload + reload idempotent:** running `launchctl unload` then `launchctl load -w` twice does not produce two cron registrations.
- **Error path - plist XML malformed:** `plutil -lint ~/Library/LaunchAgents/com.fuchitalee.x-monitor.plist` exits 0.

**Verification:**
- `launchctl print gui/$(id -u)/com.fuchitalee.x-monitor | grep "program = "` shows `/bin/zsh -c ...run-pipeline-watchpaths.sh`.
- `tail -20 ~/Library/Logs/x-monitor/stdout.log` shows a successful cycle summary (NOT the `No module named x_monitor.__main__` traceback).
- `plutil -lint` exit 0 on the edited plist.

---

### Unit 2: Install the scheduled 15-minute LaunchAgent

**Goal:** Symlink `x-monitoring/deploy/com.fuchitalee.x-monitor.scheduled.plist` into `~/Library/LaunchAgents/` and load it via launchctl so the pipeline fires every 15 minutes.

**Requirements:** R1, R2

**Files:**
- Create: `~/Library/LaunchAgents/com.fuchitalee.x-monitor.scheduled.plist` (operator action: `ln -s <abs>/x-monitoring/deploy/com.fuchitalee.x-monitor.scheduled.plist ~/Library/LaunchAgents/`)
- No code changes; this is purely operational.

**Approach:**
- Verify the deploy plist still references the correct WorkingDirectory (`/Users/fuchitalee/development/minimax-marketing/x-monitoring`) and ProgramArguments (the existing wrapper script).
- Create the symlink in `~/Library/LaunchAgents/` (launchd reads plists from this directory on a per-user basis).
- `launchctl load -w ~/Library/LaunchAgents/com.fuchitalee.x-monitor.scheduled.plist` — `-w` registers the agent and writes the override so it persists across logins.
- Wait one full 15-minute boundary and confirm `tail ~/Library/Logs/x-monitor/scheduled-stdout.log` shows a new cycle.

**Patterns to follow:**
- `x-monitoring/deploy/run-pipeline-with-notify.sh` (existing wrapper — already correct, no changes needed).
- `x-monitoring/deploy/com.fuchitalee.x-monitor.scheduled.plist` (existing template — no changes needed).

**Test scenarios:**
- **Happy path - plist symlinked:** `ls -la ~/Library/LaunchAgents/com.fuchitalee.x-monitor.scheduled.plist` shows the symlink resolves to the deploy directory.
- **Happy path - plist loaded:** `launchctl list | grep x-monitor.scheduled` shows the label with a numeric PID (NOT `-`).
- **Happy path - cron fires on cadence:** after one 15-minute boundary, `tail ~/Library/Logs/x-monitor/scheduled-stdout.log` shows a new cycle summary.
- **Edge case - symlink survives reboot:** `launchctl print gui/$(id -u)/com.fuchitalee.x-monitor.scheduled | grep "state = "` shows `running` or `waiting`.
- **Error path - symlink target missing:** if `x-monitoring/deploy/com.fuchitalee.x-monitor.scheduled.plist` is moved or deleted, `launchctl load` fails with a clear error. Implementer should `ls -la` the symlink before `launchctl load`.

**Verification:**
- `launchctl list | grep x-monitor` shows BOTH labels (`com.fuchitalee.x-monitor` AND `com.fuchitalee.x-monitor.scheduled`) with numeric PIDs.
- After waiting one full 15-minute boundary, `tail ~/Library/Logs/x-monitor/scheduled-stdout.log` shows a new successful cycle.

---

### Unit 3: Add `x_monitor_list_id` to `config.yaml` and run the dry-run smoke test

**Goal:** Unblock the `x_monitor_list_id` `ValueError` gate in `RunPipeline.execute()` by setting the field in `config.yaml`, then prove the full pipeline executes end-to-end via `--dry-run`.

**Requirements:** R1, R3, R4

**Files:**
- Modify: `x-monitoring/config.yaml` (append one line)

**Approach:**
- Append to `x-monitoring/config.yaml` (root level, not nested):
  ```yaml
  x_monitor_list_id: 2067062923525275922
  ```
  Pydantic field at `x_monitor/config.py:94` accepts `int | None`; bare integer YAML parses as int. Do NOT quote the number (some YAML loaders coerce strings to int differently and the `list:` operator in TwitterAPI.io will choke on a stringified ID).
- Run `cd ~/development/minimax-marketing/x-monitoring && .venv/bin/python -m x_monitor run --dry-run` from a shell. Expected exit code: 0. Expected stderr: the dry-run cost summary printed to stderr (per `cmd_run` lines 76-91 of `__main__.py`).
- (Optional) Run `.venv/bin/python -c "from x_monitor.config import load_config; print(load_config('config.yaml').x_monitor_list_id)"` to confirm the field parses.
- Per `feedback_twitterapi_unknown_list_silent_fallback.md`, run one real (non-dry-run) cycle and check the first 20 results for ≥1 expected brand handle. This validates the list_id is correct and the list is populated.

**Patterns to follow:**
- `x-monitoring/x_monitor/config.py:94` — the pydantic field definition.
- `x-monitoring/x_monitor/run.py:376-384` — the gate being unblocked.
- `x-monitoring/deploy/migration-004-runbook.md` — the v1.8 deploy sequence and MON-01..10 monitoring checks.

**Test scenarios:**
- **Happy path - config parses:** `load_config('config.yaml').x_monitor_list_id == 2067062923525275922`.
- **Happy path - dry-run exits 0:** `.venv/bin/python -m x_monitor run --dry-run` exits 0 and prints the cost summary to stderr.
- **Happy path - first real cycle: ≥1 expected brand handle** in the first 20 results (sanity check per `feedback_twitterapi_unknown_list_silent_fallback.md`).
- **Edge case - list_id typo:** if the field is set to an invalid integer (e.g., `2067062923525275999`), the dry-run still exits 0 (the dry-run path doesn't actually query TwitterAPI.io), but the FIRST real cycle returns 20 random Latest tweets with no expected handle. Operator should verify.
- **Error path - config field removed:** removing the line reproduces the `ValueError: config.x_monitor_list_id must be set in v1.7` gate. Implementer should confirm the rollback path works.

**Verification:**
- `.venv/bin/python -m x_monitor run --dry-run` exits 0.
- After one real cycle, `SELECT COUNT(*) FROM posts WHERE created_at > datetime('now', '-1 day')` returns ≥ 1 (proves the cron is ingesting).
- `tail ~/Library/Logs/x-monitor/scheduled-stdout.log` shows the cycle summary with `posts_inserted` > 0 (NOT the `ValueError` traceback).

---

### Unit 4: Diagnose and remediate `post_brand_signals = 0` via reattribute with `--anthropic`

**Goal:** Backfill the empty `post_brand_signals` table by re-running the v1.8 reattribute subcommand with an `AnthropicClaudeClient` instance, populating per-brand signal classifications for all 2,008 historical posts.

**Requirements:** R5, R6

**Files:**
- No code changes; this is an operational remediation using existing CLI subcommand `x_monitor.reattribute --with-llm`.

**Approach:**
- Verify the `--with-llm` flag exists on the `reattribute` subparser (per memory `project_x_monitoring_v18_2026-06-19.md` and the unit-5 commit that landed it).
- Confirm `ANTHROPIC_API_KEY` is set in `~/.env.secrets` (the same file the wrapper scripts source). If not, the operator must add it.
- Run `.venv/bin/python -m x_monitor reattribute --with-llm --batch-size 50` from a shell. This invokes `reattribute_all_posts` with an `AnthropicClaudeClient` constructed from env. Expected runtime: ~5-15 minutes for 2,008 posts at Haiku 4.5 speeds (~$0.10-0.30 at current pricing).
- The reattribute is idempotent (per Decision 14 in the v1.8 plan: ON CONFLICT DO UPDATE), so re-running later is safe.
- After the reattribute, run `SELECT COUNT(*) FROM post_brand_signals` and confirm it approaches `COUNT(*) FROM post_brands` minus any `_unattributed` rows.

**Patterns to follow:**
- `x-monitoring/x_monitor/reattribute.py:271-290` — the `classify_signal(..., anthropic_client=...)` call.
- `x-monitoring/x_monitor/store.py:831+` — `insert_post_brand_signals` ON CONFLICT policy.
- `x-monitoring/deploy/migration-004-runbook.md` MON-09 — the monitoring check this unit satisfies.

**Test scenarios:**
- **Happy path - reattribute populates signals:** after running with `--with-llm`, `SELECT COUNT(*) FROM post_brand_signals` returns > 0 (target: ~2,700, matching `post_brands` row count minus `_unattributed`).
- **Happy path - signal distribution non-trivial:** `SELECT signal, COUNT(*) FROM post_brand_signals GROUP BY signal` returns ≥ 2 distinct signals (e.g., `praise`, `community_question`, `criticism`, `commenter_capture`).
- **Edge case - rate-limit hit:** the Anthropic API may rate-limit at scale; the reattribute should log warnings and continue (per `reattribute.py` exception handler) rather than abort the whole batch.
- **Edge case - missing API key:** if `ANTHROPIC_API_KEY` is unset, `AnthropicClaudeClient.from_env()` raises; the implementer should pre-check via `.venv/bin/python -c "from x_monitor.anthropic_client import AnthropicClaudeClient; print(AnthropicClaudeClient.from_env())"` and fail fast.
- **Error path - dashboard still shows zeros after reattribute:** if `post_brand_signals` populates but the dashboard polarity cards still show zeros, the issue is in `x_monitor/treemap.py:compute_polarity` (already v1.8-aware per the v1.8 plan). Investigate whether the dashboard is reading from main checkout vs a stale worktree.

**Verification:**
- `SELECT COUNT(*) FROM post_brand_signals` returns > 0 (target: ~2,700).
- `SELECT signal, COUNT(*) FROM post_brand_signals GROUP BY signal ORDER BY 2 DESC LIMIT 5` shows the expected signal distribution (e.g., `praise` and `community_question` dominating).
- Dashboard at `http://localhost:5000/grid` renders polarity values (not zeros) for ≥ 1 brand card. If the dashboard is on a stale worktree checkout, restart via `lsof -nP -iTCP:5000 -sTCP:LISTEN -t | xargs -r kill && nohup .venv/bin/python -m x_monitor dashboard --port 5000 > ~/Library/Logs/x-monitor/dashboard.log 2>&1 &` per the v1.8 deploy runbook.

## System-Wide Impact

- **Interaction graph:** LaunchAgent → wrapper script → `python3 -m x_monitor run` → `RunPipeline.execute()` → `plan_calls()` → `TwitterApiClient.search()` → `Store.insert_posts()` → 4 tables in one transaction. Unit 1+2+3 fix the entry points. Unit 4 uses a separate entry point (`reattribute`) that bypasses TwitterAPI.io and reads from the local DB.
- **Error propagation:** the v1.7 list-id `ValueError` was uncaught in `cmd_run`, so it propagated to `sys.exit(2)` and was captured in `stderr.log`. After Unit 3, this code path succeeds; any future failure will be captured by the osascript notification in the scheduled wrapper (Unit 2) OR by `tail -f ~/Library/Logs/x-monitor/stdout.log` for the WatchPaths wrapper (Unit 1, no osascript).
- **State lifecycle risks:** the reattribute (Unit 4) writes `post_brand_signals` rows in ON CONFLICT DO UPDATE batches of 100. A partial-write failure leaves some rows with old signals; the next reattribute run overwrites them (idempotent). No cleanup needed.
- **API surface parity:** `x_monitor/reattribute.py` and `x_monitor/run.py` are the two entry points that call `classify_signal`; only the reattribute path supports `--with-llm`. The cron hot path (`RunPipeline.execute`) does NOT wire the Anthropic client, so newly-ingested posts will continue to land in `post_brand_signals=0` UNTIL a follow-up plan lands. The dashboard will continue to show zeros for live data; the Unit 4 remediation only fixes the historical 2,008 posts. **This is a known limitation; document in the plan's Operational Notes section.**
- **Integration coverage:** Units 1+2+3 prove the cron fires and the pipeline executes end-to-end. Unit 4 proves the per-brand signal classifier works against historical data. Neither unit mocks; both run against the production database.
- **Unchanged invariants:** the v1.8 schema (migration 004), the v1.8 `attribute_to_brands` orchestrator, the existing detection tables (`brand_accounts`, `brand_hashtags`, etc.), the existing 2,700 `post_brands` rows, and the existing 2,147 `post_mentions` rows all remain unchanged. Only the cron wiring (Units 1+2), config (Unit 3), and `post_brand_signals` table (Unit 4) are touched.

## Risks & Dependencies

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| List ID `2067062923525275922` is wrong (digit transposition not caught) | Low | Medium — silent fallback to 20 random Latest tweets | Unit 3 includes the first-cycle sanity check asserting ≥1 expected brand handle per `feedback_twitterapi_unknown_list_silent_fallback.md` |
| The list is empty (operator never added 12 handles manually) | Medium | Medium — dashboard shows zero or low data quality | The v1.7 plan's 3-cycle list-drift detection surfaces this; documented as out-of-scope for this plan |
| `ANTHROPIC_API_KEY` is missing from `~/.env.secrets` | Medium | High — Unit 4 reattribute aborts before any signals populate | Unit 4 includes a pre-check via `AnthropicClaudeClient.from_env()` and fails fast |
| The cron hot path (`RunPipeline.execute`) does NOT wire `AnthropicClaudeClient`, so new posts still land with `post_brand_signals=NULL` after this plan | High | Medium — dashboard polarity degrades over time | Documented in Operational Notes; follow-up plan to wire LLM classifier into the cron hot path |
| The dashboard process is stale and reads from a worktree instead of main | Low | Medium — Unit 4 verification fails | Unit 4 verification step includes the port-based dashboard restart per `feedback_pkill_matches_all_dashboardapp.md` |
| `launchctl load` rejects the scheduled plist (macOS Gatekeeper / SIP) | Low | High — Unit 2 fails entirely | Plist is in the user's `~/Library/LaunchAgents/` (not `/Library/LaunchAgents/`), so no SIP issues expected. If it fails, run `plutil -lint` and check Console.app for `launchd` errors |
| Wrapper script loses executable bit after edit | Low | High — cron fails silently with "Permission denied" | `chmod +x deploy/run-pipeline-watchpaths.sh` immediately after edit; `ls -la` to verify `-rwxr-xr-x` |
| Both plists fire on the same minute (overlap) | Low | Medium — `pipeline_lock` in `x_monitor.run` prevents duplicate execution | The lock prevents overlap; if both fire, the second one acquires the lock but exits early. No data corruption, but a slight extra log entry |

## Documentation / Operational Notes

- **Live cron firing on 15-minute cadence requires Unit 1 + Unit 2 + Unit 3 to all land.** Unit 1 alone fixes the Python interpreter issue but the cron only fires on WatchPaths events; the 15-minute cadence requires Unit 2. Unit 3 unblocks the actual pipeline execution. If any one is missing, the pipeline still does not run on cadence.
- **New posts continue to have `post_brand_signals=NULL` after this plan.** The cron hot path (`x_monitor/run.py`) does not wire `AnthropicClaudeClient`, so newly-ingested posts land with empty signal rows. The dashboard polarity will degrade over time. **Follow-up plan needed:** wire `AnthropicClaudeClient` into `RunPipeline.execute()` so the cron populates signals on every ingest.
- **The v1.8 deploy runbook** (`x-monitoring/deploy/migration-004-runbook.md`) should be updated after this plan lands to add the venv Python pattern and the scheduled-plist load step. Out of scope for this plan; flag for follow-up.
- **MON-03** in the v1.8 runbook expects `post_mentions ≥ 500` after 1 hour. Current state: 2,147 (healthy). No action needed.
- **MON-09** in the v1.8 runbook expects `post_brand_signals` distribution non-zero after 4 hours. Current state: 0 (failing). Unit 4 of this plan remediates.

## Sources & References

- **Related code:**
  - `x-monitoring/x_monitor/run.py:376-384` — list-id `ValueError` gate
  - `x-monitoring/x_monitor/reattribute.py:271-290` — `classify_signal(..., anthropic_client=None)` call
  - `x-monitoring/x_monitor/config.py:94` — `x_monitor_list_id: int | None` field
  - `x-monitoring/x_monitor/store.py:796-828` — `insert_post_mentions` ON CONFLICT policy
  - `x-monitoring/deploy/run-pipeline-with-notify.sh` — wrapper script pattern
  - `x-monitoring/deploy/com.fuchitalee.x-monitor.scheduled.plist` — scheduled plist template
  - `x-monitoring/deploy/migration-004-runbook.md` — v1.8 deploy sequence + MON-01..10
- **Related memory files:**
  - `project_x_monitoring_v18_2026-06-19.md` — v1.8 ship report
  - `project_x_monitoring_v17_2026-06-17.md` — v1.7 list-add plan context
  - `project_x_monitoring_list_management_2026-06-17.md` — list-add BLOCKED on Free tier
  - `project_x_monitoring_cloudflare_block_2026-06-18.md` — list-add BLOCKED on Cloudflare
  - `feedback_pkill_matches_all_dashboardapp.md` — `lsof`-based kill, NEVER `pkill`
  - `feedback_twitterapi_unknown_list_silent_fallback.md` — startup sanity check pattern
  - `feedback_x_api_free_tier_blocks_lists.md` — list management API tier restriction
  - `feedback_worktree_hygiene_x_monitoring.md` — worktree symlink pattern