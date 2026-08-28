# Production Runbook -- v1-to-v2 Cutover

Last updated: 2026-08-27

> This historical cutover runbook does not authorize copying production data.
> The current guarded production-to-staging snapshot procedure, including its
> dedicated read-only role and recovery controls, is
> [`docs/operations/staging-data-refresh.md`](operations/staging-data-refresh.md).

This document covers the cutover from the legacy v1 Flask/SQLite/launchd
stack to the v2 Django/PostgreSQL/Render stack. Read it fully before
starting.

## Architecture during migration

During the migration window, **both stacks run in parallel**:

- **v1 (macOS):** 2 launchd agents harvest to SQLite. The Flask dashboard
  reads from that SQLite. This is the **live production surface**.
- **v2 (Render):** Celery beat + worker harvest to managed PostgreSQL. The
  Django dashboard reads from that PG behind Google OAuth. This is the
  **validation surface** -- not yet customer-facing.

Both stacks share the same API keys (TwitterAPI.io, Anthropic) but write
to independent databases. There is no write-write conflict.

## Pre-flight checks (before starting battle-test)

Complete every item before entering the battle-test window.

### v1 health check

- [ ] `launchctl list | grep com.fuchitalee.x-monitor.harvest` shows PID
- [ ] `launchctl list | grep com.fuchitalee.x-monitor.config-reload` shows PID
- [ ] `data/runs/LATEST.json` exists and was updated within the last 30 min
- [ ] `x-monitor dashboard status` reports running
- [ ] `http://127.0.0.1:5000/` loads the multi-brand home
- [ ] No `degraded` keys in `LATEST.json` for > 3 consecutive cycles

### v2 deploy health check

- [ ] Render dashboard shows `xmonitor-web` as "Live" (green)
- [ ] Render dashboard shows `xmonitor-worker` as "Live" (green)
- [ ] Render dashboard shows `xmonitor-beat` as "Live" (green)
- [ ] `xmonitor-db` (PostgreSQL) is "Available"
- [ ] `xmonitor-redis` (Redis) is "Available"

### v2 functional check

Run from Render web shell:

- [ ] `python manage.py check --deploy` exits 0
- [ ] `python manage.py migrate --check` shows no pending migrations
- [ ] `python manage.py load_seed` runs idempotently (shows 0 new rows)
- [ ] `python manage.py seed_i18n_labels` runs idempotently
- [ ] `python manage.py run_cycle --dry-run --limit-per-call 5` completes
  without errors and reports > 0 calls planned

### OAuth check

- [ ] Visit `https://xmonitor-web.onrender.com/accounts/login/`
- [ ] Sign in with Google (authorized email)
- [ ] Redirected to multi-brand home page
- [ ] Single-brand pages load (e.g., `/alibaba/qwen/`)

### Data port check

- [ ] `scripts/port_sqlite_to_django.py` completed without errors
- [ ] `scripts/bridge_sqlite_to_pg.py --source data/runs/LATEST.json` completed
  without errors
- [ ] `python manage.py validate_cycle --source-legacy data/runs/LATEST.json --tolerance-pct 5` exits 0

## Battle-test protocol (1-2 days minimum)

The goal is to confirm v2 harvest equivalence under real production load
BEFORE cutting over. Run this protocol for at least 24 hours (48 hours
recommended if the comparison window spans a weekend or a day with
unusual tweet volume).

### Hour 0: Start parallel running

1. Confirm v1 launchd agents are running (they never stopped)
2. Confirm v2 Celery beat is scheduling tasks (check `xmonitor-beat` logs)
3. Confirm v2 Celery worker is executing cycles (check `xmonitor-worker` logs)

### Every 6 hours: Validate equivalence

After each 6-hour window (4 harvest cycles), run the validator:

```bash
# On macOS (local), after the latest legacy cycle completes:
python manage.py validate_cycle \
  --source-legacy data/runs/LATEST.json \
  --tolerance-pct 10
```

**Pass criteria:** exits 0, all metrics within tolerance.

If a check fails, compare the per-call breakdown in the legacy and target
summaries to identify the specific call/brand with a discrepancy. Common
causes:

- **Timing skew:** Legacy and new cycles ran at slightly different times,
  catching different subsets of tweets. Increase tolerance to 15% if the
  cycle start times differ by > 5 minutes.
- **API pagination:** TwitterAPI.io can return different pages for the
  same query at different times. This is expected noise within ~10%.
- **LLM nondeterminism:** Classification output can vary between runs.
  The validator checks post counts, not classification contents -- this
  should not affect the comparison.

### Hour 24: Extended validation

- [ ] v1 `LATEST.json` shows continuous operation (no gaps > 15 min)
- [ ] v2 Celery beat logs show consistent 15-min scheduling (no gaps)
- [ ] v2 worker logs show completed cycles for each beat tick
- [ ] `validate_cycle` exits 0 for at least 3 of the last 4 windows
- [ ] No `degraded:twitterapi_auth` in either stack
- [ ] No OAuth 500s on the v2 dashboard
- [ ] Dashboard renders all routes correctly (spot-check 3 brand pages)

### Hour 48 (recommended): Final validation

- [ ] All above checks still green
- [ ] Total post count in v2 PG is within 5% of v1 SQLite for the
  ported window
- [ ] Per-brand post distribution matches within 15% for all 20 brands
- [ ] At least one full daily cycle budget was consumed by v2 (check
  worker logs for `n_calls_run` vs `n_calls_planned`)

## Approval gates

**Do not proceed to cutover until ALL gates are green.**

### Gate 1: Operator sign-off

- [ ] Operator has reviewed the 24-hour (or 48-hour) validation report
- [ ] Operator has spot-checked the v2 dashboard: feed loads, charts
  render, locale toggle works, brand pages respond
- [ ] Operator has confirmed no regressions in post coverage vs. v1
- [ ] Operator explicitly approves: "v2 is ready for cutover"

### Gate 2: Technical sign-off

- [ ] `validate_cycle` exits 0 for the final comparison window
- [ ] Render services have stable uptime for the full battle-test period
- [ ] No unapplied Django migrations
- [ ] Google OAuth login works from the operator's device
- [ ] The bridge script ran successfully within the last cycle

### Gate 3: Rollback readiness

- [ ] v1 launchd plists are still on disk (not deleted)
- [ ] v1 SQLite DB is intact (`ls -lh data/x_monitoring.db` shows > 80 MB)
- [ ] The v1 dashboard start command still works (`x-monitor dashboard start`)
- [ ] Operator has the rollback plan printed/saved (this document, next section)

## Cutover procedure

**Only after all approval gates are green.**

### Step 1: Final bridge sync

```bash
# On macOS (local), after the latest legacy cycle completes:
python scripts/bridge_sqlite_to_pg.py
python manage.py validate_cycle \
  --source-legacy data/runs/LATEST.json \
  --tolerance-pct 5
# Must exit 0
```

### Step 2: Unload v1 launchd agents

```bash
# Stop the legacy harvest -- do NOT delete the plist files
launchctl unload ~/Library/LaunchAgents/com.fuchitalee.x-monitor.harvest.plist
launchctl unload ~/Library/LaunchAgents/com.fuchitalee.x-monitor.config-reload.plist

# Verify they stopped
launchctl list | grep com.fuchitalee.x-monitor
# Should show no PIDs
```

### Step 3: Verify v2 is harvesting independently

Wait 15 minutes, then check:

- [ ] `xmonitor-beat` log shows the scheduled tick
- [ ] `xmonitor-worker` log shows a completed cycle
- [ ] The cycle stats show normal counts (not degraded, not 0)
- [ ] `python manage.py run_cycle --dry-run --limit-per-call 10` completes

### Step 4: Switch dashboard traffic

- The v2 dashboard at `https://xmonitor-web.onrender.com/` becomes the
  canonical URL
- If there's a DNS alias or redirect from a custom domain, update it now
- Notify the team the dashboard URL has moved

### Step 5: Confirm end-to-end

- [ ] Visit the v2 dashboard URL, sign in with Google
- [ ] Multi-brand home loads with recent data (posts from the last hour)
- [ ] Single-brand pages work
- [ ] Feed scrolls with cursor pagination
- [ ] Charts render with data points matching expected brands

## Rollback procedure

If v2 shows problems after cutover, revert to v1.

### Step 1: Stop v2 harvest

In Render Dashboard:
1. Suspend `xmonitor-beat` (stops scheduling new cycles)
2. Suspend `xmonitor-worker` (stops processing queued cycles)
3. Leave `xmonitor-web` running (can still serve -- or suspend if desired)

### Step 2: Restart v1 harvest

```bash
# Reload the plist files (never deleted)
launchctl load ~/Library/LaunchAgents/com.fuchitalee.x-monitor.harvest.plist
launchctl load ~/Library/LaunchAgents/com.fuchitalee.x-monitor.config-reload.plist

# Verify PIDs are back
launchctl list | grep com.fuchitalee.x-monitor
```

### Step 3: Wait for first v1 cycle

- Wait 15 minutes for the next scheduled tick
- Check `data/runs/LATEST.json` was updated
- `x-monitor dashboard start` if the Flask dashboard was stopped

### Step 4: Switch traffic back

- Point DNS or team bookmarks back to `http://<macOS-host>:5000/`
- Notify the team

### Step 5: Investigate v2 issue

- Review Render logs for errors during the problem window
- Check for API key expiration or quota exhaustion
- Fix and re-enter battle-test protocol before re-attempting cutover

## Post-cutover cleanup (after 1 week of stable v2)

Only after v2 has run stably in production for at least one week:

- [ ] Archive the v1 launchd plists (move to `deploy/archive/`, do not delete)
- [ ] Archive the v1 SQLite DB (compress and move to `data/archive/`)
- [ ] Update `CLAUDE.md` to remove the legacy schema image rule
- [ ] Update `README.md` to remove the v1 documentation and "Legacy" banner
- [ ] Consider retiring the `x_monitor/` Python package (keep as
  read-only reference for 30 days before deleting)

## Emergency contacts

| Role | Who | When to contact |
|---|---|---|
| Operator (primary) | Allen Lee | Any cutover issue |
| Render platform | Render support | Service outage, DB unavailable |
| TwitterAPI.io | TwitterAPI.io support | API key issues, rate limiting |

## Reference

- README.md -- full architecture overview
- docs/deploy/render.md -- Render deployment runbook
- docs/reference/db-schema.md -- legacy SQLite schema reference
- core/models.py -- v2 Django ORM models (source of truth for PG schema)
- project/settings.py -- Django settings (env vars, Celery config)
- render.yaml -- Render Blueprint (infrastructure-as-code)
