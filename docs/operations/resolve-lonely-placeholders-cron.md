# Resolve Lonely Placeholders — Cron Runbook

_Plan: `docs/plans/2026-07-31-001-fix-lonely-placeholders-cron-apply-plan.md`_

This runbook covers the launch, monitoring, dead-letter triage, and
rollback for the `resolve_lonely_placeholders` cron that resolves the
10,681 lonely placeholder rows left by Phase 2 reconciliation. The cron
is re-entrant: every run picks up where the previous run left off, with
zero residue on a crash mid-row.

## Launch

The cron runs on `fuchitalee`. The TwitterAPI key lives in
`~/.env.secrets` and the database URL is in `render.yaml` under
`pushinweight-db-shadow`.

```bash
ssh fuchitalee
cd /Users/fuchitalee/development/pushin-weight-v2
source .venv/bin/activate

# Smoke run (no DB writes, no TwitterAPI calls): 5 seconds
DATABASE_URL='postgresql://pushinweight_shadow:<redacted>@dpg-d9koekqjobas73fvjqng-a/pushinweight_shadow' \
  python manage.py resolve_lonely_placeholders --dry-run --json

# Real run: 1 hour target, exits cleanly with partial=true on timeout
DATABASE_URL='postgresql://pushinweight_shadow:<redacted>@dpg-d9koekqjobas73fvjqng-a/pushinweight_shadow' \
  python manage.py resolve_lonely_placeholders --apply --json \
  >> ~/lonely-apply.log 2>&1
```

## Cron entry

The operator chooses one of these two paths at launch time:

### Option A — local launchd on fuchitalee (recommended for the trip)

Create `~/Library/LaunchAgents/com.pushinweight.resolve-lonely.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.pushinweight.resolve-lonely</string>
  <key>ProgramArguments</key>
  <array>
    <string>/Users/fuchitalee/development/pushin-weight-v2/.venv/bin/python</string>
    <string>/Users/fuchitalee/development/pushin-weight-v2/manage.py</string>
    <string>resolve_lonely_placeholders</string>
    <string>--apply</string>
    <string>--json</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>DATABASE_URL</key>
    <string>postgresql://pushinweight_shadow:&lt;redacted&gt;@dpg-d9koekqjobas73fvjqng-a/pushinweight_shadow</string>
    <key>PATH</key>
    <string>/Users/fuchitalee/development/pushin-weight-v2/.venv/bin:/usr/local/bin:/usr/bin:/bin</string>
  </dict>
  <key>StartInterval</key><integer>3600</integer>
  <key>StandardOutPath</key><string>/Users/fuchitalee/lonely-apply-stdout.log</string>
  <key>StandardErrorPath</key><string>/Users/fuchitalee/lonely-apply-stderr.log</string>
  <key>RunAtLoad</key><false/>
</dict>
</plist>
```

Load with `launchctl load ~/Library/LaunchAgents/com.pushinweight.resolve-lonely.plist`.
Verify with `launchctl list | grep resolve-lonely` (you should see the PID).
The job runs once per hour. Each run executes `--max-seconds 3300` (55 min)
so a tick cannot overlap the next one.

### Option B — Render cronJobs (alternative)

If the operator prefers Render's cron scheduler, the cron entry goes in
`render.yaml` under the `pushinweight-harvest` service's `cronJobs:` list.
The command is identical to the launchd command above but with the
Render-internal `DATABASE_URL` (no SSH tunnel needed).

## Monitoring

While the cron is running (or after the trip):

```bash
# Latest exit summary as a single JSON object:
tail -1 ~/lonely-apply.log | jq .

# Watch new lines as they appear:
tail -f ~/lonely-apply.log

# Dead-letter log (append-only, one JSON line per dead-lettered handle):
tail -f ~/lonely-apply-dead-letter.log

# Quick stats: how many dead-letters by reason?
jq -r '.reason' ~/lonely-apply-dead-letter.log | sort | uniq -c | sort -rn

# Quick stats: which cron runs tripped the circuit breaker?
jq 'select(.breaker_tripped == true) | {started_at, looked_up, dead_lettered, by_reason: .dead_letter_reasons}' \
  ~/lonely-apply.log
```

## Dead-letter triage

Each entry in `~/lonely-apply-dead-letter.log` has `handle`, `reason`,
`status_code`, `response_excerpt`, `ts`. The reasons map to actions:

| Reason | Action |
|---|---|
| `not_found_200` | Leave alone. TwitterAPI returned HTTP 200 + `status=error` for this handle. The handle genuinely does not exist on X. |
| `http_404` | Leave alone. TwitterAPI returned a genuine HTTP 404. Same as above. |
| `rate_limited` | Wait 24 hours (let TwitterAPI recover), then re-run with `--no-skip-dead-lettered` to retry just the rate-limited subset. |
| `http_5xx` | Wait 1 hour, retry with `--no-skip-dead-lettered`. |
| `circuit_open` | The circuit breaker tripped (10 consecutive 429/5xx). The cron run exited cleanly with `partial=true`. Wait for the next tick. |
| `apply_integrity_error` | A brands_accounts_pkey collision. Leave alone — the placeholder row stays as-is. The next U12 unique-index migration will surface these as duplicates to investigate manually. |
| `apply_exception` | A non-IntegrityError exception during apply (DB connection drop, etc.). The cron run exits with partial=true and the error in the summary. The placeholder row stays. Investigate after the trip. |

To retry the rate-limited subset:

```bash
cd /Users/fuchitalee/development/pushin-weight-v2
source .venv/bin/activate
# Back up the dead-letter log, filter out the rate-limited rows, write a new log.
# Then re-run --skip-dead-lettered reads the filtered log.
jq -c 'select(.reason == "rate_limited")' ~/lonely-apply-dead-letter.log \
  > ~/lonely-apply-rate-limited-backup.log
jq -c 'select(.reason != "rate_limited")' ~/lonely-apply-dead-letter.log \
  > ~/lonely-apply-dead-letter.log.tmp
mv ~/lonely-apply-dead-letter.log.tmp ~/lonely-apply-dead-letter.log

DATABASE_URL='postgresql://...' \
  python manage.py resolve_lonely_placeholders --apply --json
```

## Stop conditions

The cron keeps ticking until one of:

1. **`placeholder_rows == 0` on the live DB.** Stop the cron (`launchctl unload ...`).
   Run the AFTER-state regression net (flip U1's pinned values to 0) and ship it.
   The plan is complete.
2. **All cron ticks fail for 24 hours.** Check `~/lonely-apply.log` for the
   recurring `error` field. If it's `circuit_open` consistently, TwitterAPI is
   rate-limiting the account — submit a support ticket via the `/qps-limits`
   page (free, not a price-tier gate). If it's `connection_error` consistently,
   the DB or the network is the problem — investigate the host.
3. **The trip is over and the operator returns.** Stop the cron. Read
   `~/lonely-apply.log`, count the successes, triage the dead-letters, decide
   whether to retry or accept the residue.

## Rollback

The apply is per-row with SAVEPOINT rollback, so a partial run leaves zero
inconsistent state. There is no schema change, no migration, no destructive
operation — the cron only DELETEs placeholder rows whose FKs have been
re-pointed to a canonical row, and the canonical row itself is created via
`_ensure_canonical_account_row` (idempotent on prior runs).

If a systemic bug surfaces (the Phase 2 v4/v5 pre-pass pattern), the
rollback is:

```bash
cd /Users/fuchitalee/development/pushin-weight-v2
git revert <commit-sha-of-bad-commit>
# Optional: re-run the cleanup scripts from Phase 2:
#   DATABASE_URL=... uv run --with django python manage.py shell < scripts/u_cleanup_prepass_damage.py
```

The cleanup scripts `scripts/u_cleanup_prepass_damage.py` and
`scripts/u_cleanup_prepass_drift.py` are permanent tools for any future
similar incident.

## After-state regression net

Once `placeholder_rows == 0`, flip U1's pinned values in
`tests/test_lonely_placeholders_regression_net.py`:

```python
EXPECTED_LONELY_PLACEHOLDER_ROWS: int = 0
EXPECTED_LONELY_UNIQUE_HANDLES: int = 0
# handle_prefix + synthetic_prefix floors can stay; the live test
# will assert the new low counts.
```

Run on `pushinweight_shadow` to confirm green, then commit. The
regression net now pins the AFTER state and detects future drift.

## Port-exhaustion mitigation (operator-level)

If `netstat -an | grep TIME_WAIT | wc -l` on fuchitalee exceeds
10,000 during a run, you can stretch the OS limits (macOS/BSD):

```bash
# Widen the ephemeral port range from 49152-65535 (16,384 ports) to
# 32768-65535 (32,768 ports). Half the pressure per cycle.
sudo sysctl -w net.inet.ip.portrange.first=32768
```

This is OUTSIDE the cron; only do it if the cron run is failing because
the host can't allocate sockets. With the U3 hardening (Keep-Alive,
TCPConnector(limit=2), 5 QPS), the cron should never hit this — the
run uses ~2 ephemeral ports total, not 10,681.

## Files

- `monitor/management/commands/resolve_lonely_placeholders.py` — the cron command
- `monitor/twitterapi/caller.py` — the aiohttp caller (U3)
- `monitor/reconcile/apply_one_row.py` — the SAVEPOINT-per-row apply (U4)
- `monitor/reconcile/apply_loop.py` — the apply loop + exit summary (U5)
- `tests/test_lonely_placeholders_regression_net.py` — U1 BEFORE/AFTER pins
- `tests/test_resolve_lonely_placeholders_flags.py` — U2 flag surface
- `tests/test_twitterapi_caller_shape.py` — U3 caller shape + circuit breaker
- `tests/test_resolve_lonely_placeholders_apply.py` — U4 apply path
- `tests/test_resolve_lonely_placeholders_exit_summary.py` — U5 exit summary
- `tests/test_resolve_lonely_placeholders_port_safety.py` — U6 port-safety
- `~/lonely-apply.log` — append-only exit summary log (created on first run)
- `~/lonely-apply-dead-letter.log` — append-only dead-letter log