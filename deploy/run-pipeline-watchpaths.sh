#!/bin/zsh
# {{AGENT_ATTRIBUTION}}
# Run the x-monitor pipeline from the WatchPaths LaunchAgent.
# Invoked by: com.fuchitalee.x-monitor.config-reload
# (pair: com.fuchitalee.x-monitor.harvest for the 15-min cadence).
#
# Triggered by config.yaml edits (PR merge of an x_query_specs change,
# daily_ceiling tweak, etc.). Fires often (every config edit) so this
# wrapper deliberately OMITS the osascript notification the scheduled
# wrapper uses — too noisy for WatchPaths cadence. Errors still land
# in ~/Library/Logs/x-monitor/stderr.log.
#
# Plan 2026-07-11-002 (U4): data/queries/ and data/accounts/ are both
# retired; the launchd WatchPaths only watches config.yaml. DB-touching
# migrations run via `x-monitor migrate`, not via WatchPaths.
#
# The pipeline_lock inside x_monitor.run prevents overlap if a previous cycle
# is still running.
set -uo pipefail

# Kill switch (2026-07-14): operator paused all TwitterAPI.io calls.
# Sentinel file at /tmp/x-monitor-paused gates the actual pipeline run.
# To resume, remove the file. Both this WatchPaths wrapper and the
# scheduled wrapper check the same sentinel so a config edit can't
# fire a stray run either.
if [[ -f /tmp/x-monitor-paused ]]; then
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) paused: /tmp/x-monitor-paused exists; skipping pipeline run" >> /tmp/x-monitor-pipeline.log
  exit 0
fi

cd /Users/fuchitalee/development/pushin-weight-v2
source ~/.env.secrets

LOG=/tmp/x-monitor-pipeline.log
.venv/bin/python -m x_monitor run > "$LOG" 2>&1
exit $?