# {{AGENT_ATTRIBUTION}}
# x-monitor LaunchAgent deployment

## LaunchAgents

Two macOS launchd agents run the pipeline. Both have self-describing
labels so they're never confused for each other:

| Label | Trigger | Cadence | Wrapper |
|---|---|---|---|
| `com.fuchitalee.x-monitor.harvest` | `StartCalendarInterval` at minute 0,15,30,45 | 96 cycles/day (15-min heartbeat) | `deploy/run-pipeline-with-notify.sh` |
| `com.fuchitalee.x-monitor.config-reload` | `WatchPaths` on `config.yaml` (ThrottleInterval 300s) | Event-driven (config edits only) | `deploy/run-pipeline-watchpaths.sh` |

Both wrappers invoke `python -m x_monitor run` and source
`~/.env.secrets` first. Both honor the operator pause sentinel at
`/tmp/x-monitor-paused` — `touch` it to halt all runs, `rm` to resume.
Both are debounced by the `pipeline_lock` `fcntl.flock` on
`data/runs/LOCK`, so a config edit mid-cycle cleanly exits 0.

The harvest agent pops macOS notifications on failure or signal-drop
spike; the config-reload agent does not (too noisy for config-edit
cadence).

## Install

```bash
cd /Users/fuchitalee/development/minimax-marketing/x-monitoring

bash deploy/install.sh             # config-reload (WatchPaths)
bash deploy/install-scheduled.sh   # harvest (15-min cadence)

launchctl list | grep com.fuchitalee.x-monitor
# expect both labels listed with a PID
```

The install scripts copy each plist into `~/Library/LaunchAgents/` and
do an unload/load cycle so re-running them is idempotent.

## Prerequisites

- `~/.env.secrets` exists and contains
  `export TWITTERAPI_IO_API_KEY="..."` (from https://twitterapi.io) and
  `export ANTHROPIC_API_KEY="..."` (LLM classification).
- The x-monitoring repo is on a stable path (the plists hardcode
  `/Users/fuchitalee/development/minimax-marketing/x-monitoring`).
- `python3 -m x_monitor migrate` has been run at least once on the
  target machine.

## Manual run

```bash
launchctl kickstart -k gui/$(id -u)/com.fuchitalee.x-monitor.harvest
launchctl kickstart -k gui/$(id -u)/com.fuchitalee.x-monitor.config-reload
```

The `-k` flag kills any in-flight run and starts a fresh one.

## Logs

| Agent | Stdout | Stderr |
|---|---|---|
| `.harvest` | `~/Library/Logs/x-monitor/harvest-stdout.log` | `~/Library/Logs/x-monitor/harvest-stderr.log` |
| `.config-reload` | `~/Library/Logs/x-monitor/stdout.log` | `~/Library/Logs/x-monitor/stderr.log` |

Pipeline execution log (always, regardless of agent): `/tmp/x-monitor-pipeline.log`

Run JSONs: `/Users/fuchitalee/development/minimax-marketing/x-monitoring/data/runs/<run_id>.json`

Durable alert surface: `data/runs/LATEST.json` (the rolling symlink the
dashboard reads for staleness + http_log spend summary).

## WatchPaths

The `.config-reload` agent watches `config.yaml` and fires whenever it
changes. Operator-edit surfaces that benefit from this trigger:

- `enabled_models` — add/remove a brand
- `daily_ceiling` — adjust the daily tweet budget
- `x_query_specs` — modify a Call C co-occurrence spec
- `query_rot_streak_threshold` — change the rot threshold
- `dashboard` (port, host, locale) — requires restart, not just rerun

DB-touching migrations are NOT triggered by WatchPaths — run them
manually via `x-monitor migrate`. The same goes for any change to
`data/queries/`, `data/accounts/`, or `data/filters/` — those YAML
files are no longer the runtime source of truth (retired 2026-07-11 in
favor of the `brand_keywords` and `brands_accounts` DB tables).

## Triggers in detail

- **WatchPaths** on `config.yaml` — a PR merge that changes the config
  triggers a re-run via the config-reload agent.
- **`StartCalendarInterval`** at minute 0,15,30,45 — the harvest agent
  fires 96×/day.
- The pipeline acquires `fcntl.flock` on `data/runs/LOCK` so a
  WatchPaths double-fire (PR merge mid-run) cleanly exits 0 with
  `degraded:already_running: true` in the run JSON.
- TwitterAPI.io is hit directly (no cookies); the API key is the only
  auth surface. On 429/5xx the client retries with backoff; persistent
  auth failure aborts the run and records
  `degraded:twitterapi_auth: true`.

## Uninstall

```bash
launchctl unload ~/Library/LaunchAgents/com.fuchitalee.x-monitor.config-reload.plist
launchctl unload ~/Library/LaunchAgents/com.fuchitalee.x-monitor.harvest.plist
rm ~/Library/LaunchAgents/com.fuchitalee.x-monitor.config-reload.plist
rm ~/Library/LaunchAgents/com.fuchitalee.x-monitor.harvest.plist
```

## Security notes

- `TWITTERAPI_IO_API_KEY` and `ANTHROPIC_API_KEY` are sourced from
  `~/.env.secrets` via the wrapper scripts. Neither plist contains the
  literal key values.
- No user cookies are stored on disk; TwitterAPI.io handles auth
  server-side using your API key only.
- The plists are loaded into the user's GUI domain
  (`gui/$(id -u)/...`) so they run with the user's permissions, not root.

## Migration history

- **2026-07-17** — Renamed the two LaunchAgents to
  `.harvest` (15-min heartbeat) and `.config-reload` (WatchPaths) so
  they're unambiguous from their labels alone.
- **2026-06-08** — Migrated from `automation-lab/twitter-scraper`
  (Apify) to TwitterAPI.io. The previous setup required user cookies
  (`auth_token`, `ct0` in `~/.config/x-monitor/cookies.json`) because
  the Apify actor's search and followers modes both required
  authenticated sessions. TwitterAPI.io exposes the same data
  cookie-free at a fraction of the cost (~$0.15/1k tweets vs $3/1k via
  Apify search-with-cookies).
- **2026-06-16** — Cron cadence changed from 30-min to 15-min
(`StartCalendarInterval` at 0,15,30,45).
