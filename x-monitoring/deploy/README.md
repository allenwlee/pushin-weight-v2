# {{AGENT_ATTRIBUTION}}
# x-monitor LaunchAgent deployment

## Install

```bash
cd /Users/fuchitalee/development/minimax-marketing/x-monitoring
bash deploy/install.sh
```

This copies `com.fuchitalee.x-monitor.plist` to `~/Library/LaunchAgents/` and loads it via `launchctl`.

## Prerequisites

- `~/.env.secrets` exists and contains `export TWITTERAPI_IO_API_KEY="..."` (from https://twitterapi.io)
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

- **WatchPaths** on `config.yaml` — a PR merge that changes the config triggers a re-run. `data/queries/` and `data/accounts/` are both retired (plans 2026-07-11-001 + 2026-07-11-002 U4); DB-touching migrations run via `x-monitor migrate`, not via WatchPaths.
- The pipeline acquires `fcntl.flock` on `data/runs/LOCK` so a WatchPaths double-fire (PR merge mid-run) cleanly exits 0 with `degraded:already_running: true` in the run JSON.
- TwitterAPI.io is hit directly (no cookies); the API key is the only auth surface. On 429/5xx the client retries with backoff; persistent auth failure aborts the run and records `degraded:twitterapi_auth: true`.

## Uninstall

```bash
launchctl unload ~/Library/LaunchAgents/com.fuchitalee.x-monitor.plist
rm ~/Library/LaunchAgents/com.fuchitalee.x-monitor.plist
```

## Security notes

- `TWITTERAPI_IO_API_KEY` is sourced from `~/.env.secrets` via the plist's `ProgramArguments`. The plist itself does NOT contain the literal key value.
- No user cookies are stored on disk; the TwitterAPI.io actor handles auth server-side using your API key only.
- The plist is loaded into the user's GUI domain (`gui/$(id -u)/...`) so it runs with the user's permissions, not root.

## Migration history

- **2026-06-08:** Migrated from `automation-lab/twitter-scraper` (Apify) to `TwitterAPI.io`. The previous setup required user cookies (`auth_token`, `ct0` in `~/.config/x-monitor/cookies.json`) because the Apify actor's search and followers modes both required authenticated sessions. TwitterAPI.io exposes the same data cookie-free at a fraction of the cost (~$0.15/1k tweets vs $3/1k via Apify search-with-cookies).
