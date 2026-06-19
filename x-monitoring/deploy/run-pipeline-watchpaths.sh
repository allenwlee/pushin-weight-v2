#!/bin/zsh
# {{AGENT_ATTRIBUTION}}
# Run the x-monitor pipeline from the WatchPaths LaunchAgent.
#
# Triggered by file changes in data/queries or data/accounts (PR merge of
# detection yaml). Fires often (every config edit) so this wrapper deliberately
# OMITS the osascript notification the scheduled wrapper uses — too noisy for
# WatchPaths cadence. Errors still land in ~/Library/Logs/x-monitor/stderr.log.
#
# The pipeline_lock inside x_monitor.run prevents overlap if a previous cycle
# is still running.
set -uo pipefail

cd /Users/fuchitalee/development/minimax-marketing/x-monitoring
source ~/.env.secrets

LOG=/tmp/x-monitor-pipeline.log
.venv/bin/python -m x_monitor run > "$LOG" 2>&1
exit $?