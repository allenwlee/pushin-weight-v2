# {{AGENT_ATTRIBUTION}}
# x-monitor LaunchAgent deployment

## Install

```bash
cd /Users/fuchitalee/development/minimax-marketing/x-monitoring
bash deploy/install.sh
```

This copies `com.fuchitalee.x-monitor.plist` to `~/Library/LaunchAgents/` and loads it via `launchctl`.

## Prerequisites

- `~/.env.secrets` exists and contains `export APIFY_API_TOKEN="..."`
- `~/.config/x-monitor/cookies.json` exists (mode 600) with `auth_token` and `ct0`
- The x-monitoring repo is on a stable path (the plist hardcodes `/Users/fuchitalee/development/minimax-marketing/x-monitoring`)
- `python3 -m x_monitor migrate` has been run at least once on the target machine

## Manual run

```bash
launchctl kickstart -k gui/$(id -u)/com.fuchitalee.x-monitor
```

The `-k` flag kills any in-flight run and starts a fresh one.

## Logs

- stdout: `~/Library/Logs/x-monitor/stdout.log`
- stderr: `~/Library/Logs/x-monitor/stderr.log`
- run JSONs: `/Users/fuchitalee/development/minimax-marketing/x-monitoring/data/runs/<run_id>.json`
- durable alert surface: `data/runs/LATEST.json`

## Triggers

- **WatchPaths** on `data/queries/` and `data/accounts/` — a PR merge that changes either triggers a re-run.
- The pipeline acquires `fcntl.flock` on `data/runs/LOCK` so a WatchPaths double-fire (PR merge mid-run) cleanly exits 0 with `degraded:already_running: true` in the run JSON.
- Cookies are validated at run-start via a 1-tweet probe search. Failure → `degraded:cookies: true` in the run JSON; cron keeps running.

## Uninstall

```bash
launchctl unload ~/Library/LaunchAgents/com.fuchitalee.x-monitor.plist
rm ~/Library/LaunchAgents/com.fuchitalee.x-monitor.plist
```

## Security notes

- `APIFY_API_TOKEN` is sourced from `~/.env.secrets` via the plist's `ProgramArguments`. The plist itself does NOT contain the literal `APIFY_API_TOKEN=...` value.
- Cookies live at `~/.config/x-monitor/cookies.json` (mode 600) — the only place a cookie value is stored on disk outside the plist.
- The plist is loaded into the user's GUI domain (`gui/$(id -u)/...`) so it runs with the user's permissions, not root.
