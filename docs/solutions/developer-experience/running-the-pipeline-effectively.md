---
title: "Running the x-monitor pipeline effectively: LaunchAgent labels, pause sentinel, and recovering from TwitterAPI.io SSL read hangs"
date: 2026-07-17
category: "docs/solutions/developer-experience/"
module: "x_monitor.run + deploy (LaunchAgent plumbing)"
problem_type: "developer_experience"
component: "tooling"
severity: "medium"
applies_when:
  - "two LaunchAgents for the same project have nearly-identical Labels and `launchctl list` can't tell them apart"
  - "a scheduled harvest cycle is wedged at `_ssl__SSLSocket_read → poll` holding `data/runs/LOCK` with 0% CPU"
  - "shell curl to twitterapi.io works but the pipeline's httpx call hangs"
  - "operator needs to manually retry a stuck run without losing the next scheduled boundary"
  - "nothing is running — first thing to check is whether `/tmp/x-monitor-paused` is gating the agents"
tags:
  - "launchd"
  - "launchagent"
  - "x-monitor"
  - "pipeline"
  - "twitterapi-io"
  - "ssl-hang"
  - "httpx"
  - "data-runs-lock"
  - "harvest"
  - "config-reload"
  - "kill-switch"
  - "pause-sentinel"
related_components:
  - "x-monitor LaunchAgents (~/Library/LaunchAgents)"
  - "deploy/install.sh"
  - "deploy/install-scheduled.sh"
  - "deploy/run-pipeline-watchpaths.sh"
  - "deploy/run-pipeline-with-notify.sh"
  - "x_monitor.run.RunPipeline"
  - "x_monitor.apify.TwitterApiClient (httpx)"
related_issues:
  - "docs/plans/2026-06-19-005-feat-fix-x-monitor-cron-runtime-plan.md"
  - "docs/issues/2026-06-20-162625-x-monitor-v18-minimax-proxy-25x-slowdown.md"
  - "docs/debug/2026-07-14-171500-cursor-fix-verify-before-revert.md"
  - "docs/debug/2026-07-14-160222-call-state-not-persisting.md"
related_memory:
  - "memory/2026-07-14-sinceTime-fix-applied.md"
  - "memory/2026-07-15-llm-auth-fix-applied.md"
  - "memory/2026-07-17-twitterapi-ssl-read-hang.md"
related_plans:
  - "docs/plans/2026-06-19-005-feat-fix-x-monitor-cron-runtime-plan.md"
---

# Running the x-monitor pipeline effectively

## Context

Two operational frictions surfaced while running the x-monitor pipeline
on macOS via `launchd` LaunchAgents; both cost time and obscured what
the system was actually doing:

1. **Indistinguishable LaunchAgent labels.** The repo shipped two
   plists whose `Label` strings were nearly identical:
   - `com.fuchitalee.x-monitor` (WatchPaths on `config.yaml`)
   - `com.fuchitalee.x-monitor.scheduled` (15-minute `StartCalendarInterval`)

   The bare-vs-`.scheduled` suffix is invisible from the
   `~/Library/LaunchAgents/` directory name (the first agent's plist
   file had no role-suffix either), and during a session I confused
   them — typed `launchctl list | grep scheduled` expecting to see
   the timer, didn't see what I needed, and chased the wrong agent.
   The labels in `launchctl list` were also too short to tell at a
   glance what each one fires on — both started with the same 22
   characters.

2. **TwitterAPI.io SSL read hang.** After the rename landed and the
   harvest agent was kicked, two consecutive 15-minute cycles hung
   inside httpx's TLS path. The python process was alive, used 0%
   CPU, sat at ~90 MB RSS, held `data/runs/LOCK` (FD 3w), and never
   wrote to `/tmp/x-monitor-pipeline.log` because Python was
   buffering stdout. The running-JSON showed `n_queries_run=0` and
   `phase_timings={}` — i.e. nothing had been issued yet, the hang
   was on the *first* outbound request. Shell `curl` against the same
   endpoint returned in 49 ms; Python `urllib.request.urlopen(...,
   timeout=5)` returned in 290 ms (401 = endpoint answered). Only
   `httpx` on Python 3.14.5 + macOS 26.3.1 hung in
   `_ssl__SSLSocket_read → poll(2)`. This is a known pitfall, not a
   one-off; an adjacent failure mode (LLM proxy SSL hang) was
   captured in [[memory/2026-07-15-llm-auth-fix-applied]].

3. **Stale pause sentinel.** During the same diagnostic session a
   third item surfaced: `/tmp/x-monitor-paused` had been present
   since 2026-07-16 06:12 (an operator pause from the day before)
   and was gating *all* runs from both agents — without surfacing
   clearly in the logs.

The three issues compound: a stuck cycle looks like a launchd issue
if you can't tell which agent is supposed to be firing, and the pause
sentinel makes it look like nothing is wired up.

## Guidance

### Practice 1 — Name LaunchAgents after what they do

The Label string and the plist filename are the operator's first
point of orientation. Encode the trigger mechanism in the name so
`launchctl list | grep` is self-documenting and the file in
`~/Library/LaunchAgents/` reads as a role, not a project.

For the x-monitor pipeline the two roles are:

| Trigger                          | New Label                                | Fires on                          |
| -------------------------------- | ---------------------------------------- | --------------------------------- |
| File change (`WatchPaths`)       | `com.fuchitalee.x-monitor.config-reload` | `config.yaml` edits               |
| Time schedule (`StartCalendarInterval`) | `com.fuchitalee.x-monitor.harvest` | Quarter-hour cadence (minute 0)   |

Rename the plist file to match the Label so the Label and the file in
`~/Library/LaunchAgents/` stay in sync. The deploy scripts that
copy/install those files (`deploy/install.sh`,
`deploy/install-scheduled.sh`) must be updated together — the
`PLIST_SRC`/`PLIST_DST` variables, the `grep` pattern in the
verification step, and the `echo` messages all reference the old
filenames and would silently misroute if left behind.

Also: rename the log files. The harvest plist's
`StandardOutPath`/`StandardErrorPath` originally pointed at
`scheduled-stdout.log` / `scheduled-stderr.log`. After the rename
these become `harvest-stdout.log` / `harvest-stderr.log` so `tail -f`
lines up with the agent name.

The shell scripts the agents invoke
(`deploy/run-pipeline-watchpaths.sh`,
`deploy/run-pipeline-with-notify.sh`) should each carry an
`# Invoked by:` header naming the agent. The osascript subtitle in
the notify path was `"scheduled run"` — change to `"harvest run"` to
match.

### Practice 2 — Pause sentinel + SSL-hang recovery

The pause sentinel `/tmp/x-monitor-paused` is honored by both
LaunchAgents as a hard gate (no-op exit). Treat it as a first-class
operational control, not a debug aid:

- **Pause:** `touch /tmp/x-monitor-paused` halts both agents
  cleanly without unloading them. State survives reboots because
  `/tmp` on macOS is persistent unless explicitly purged.
- **Resume:** `rm /tmp/x-monitor-paused`.
- **Verify first:** `ls -la /tmp/x-monitor-paused` before debugging
  anything else. A stale sentinel has bitten at least once.

For the SSL hang specifically, the diagnostic ladder is:

```bash
# 1. Is the process actually doing anything?
ps -o pid,pcpu,rss,stat,command -p <pid>      # 0% CPU + S state = hung
lsof -p <pid> | grep LOCK                      # holding data/runs/LOCK?

# 2. Is Python buffering stdout?
ls -la /tmp/x-monitor-pipeline.log             # size 0 with a live process = buffering

# 3. Can the network path reach the API at all?
time curl -sS -o /dev/null -w "%{http_code}\n" \
  "https://api.twitterapi.io/health"           # ~49ms + 401 = OK

# 4. Can Python's stdlib reach it?
python3 -c "import urllib.request, time; \
  t=time.time(); \
  urllib.request.urlopen('https://api.twitterapi.io/health', timeout=5); \
  print(f'{time.time()-t:.3f}s')"              # ~0.29s + 401 = OK

# 5. Is it only httpx that hangs?
#    If 3 and 4 are fast and only httpx hangs, the workaround applies.
```

If only step 5 hangs, the workaround is to fail the run and let the
next scheduled boundary retry:

```bash
kill -TERM <pid>                               # SIGTERM the stuck python
rm data/runs/LATEST.running.json               # release the run sentinel
# wait for next 0/15/30/45 minute boundary
```

Do not `kill -9` — let python close its file descriptors so the
lockfile handle on FD 3 is released cleanly. If
`LATEST.running.json` is left in place, the next run sees it as an
in-flight run and refuses to start.

The same shape occurred against the LLM proxy on 2026-07-14 (see
[[docs/debug/2026-07-14-171500-cursor-fix-verify-before-revert]]);
the discriminating test (`curl` + `urllib` succeed, `httpx` hangs) is
identical regardless of upstream endpoint, and so is the workaround.

## Why This Matters

The two failures compound in practice. Without self-describing
LaunchAgent names, the operator can't tell which log to read, which
agent to unload, or which script to grep — and during the SSL hang
the only way to know which agent was wedged was the timestamp on the
wrong log file. After the rename, `launchctl list | grep
com.fuchitalee.x-monitor` outputs two lines whose suffixes
immediately answer "which one fires on edits vs. on the
quarter-hour", and the plist filenames in `~/Library/LaunchAgents/`
match the labels one-for-one.

The SSL hang matters because the failure mode is *silent*: no
exception, no timeout, no log line. Python's stdout buffering means
`/tmp/x-monitor-pipeline.log` stays at 0 bytes for the duration of
the hang. Without the diagnostic ladder above, an operator would
naturally assume the API is down (it isn't) or that the LLM call is
slow (it never gets that far — `n_queries_run=0`). The
`httpx`-vs-`urllib` distinction is the load-bearing signal: when
stdlib HTTP works but httpx doesn't, the issue is in httpx's TLS
path on this Python/macOS combination, not in the network or the
upstream API.

The pause sentinel matters because a one-line file gates an entire
pipeline. A previous operator's pause will silently suppress every
run from both agents until the file is removed. The first thing to
check when "nothing is running" is `ls /tmp/x-monitor-paused` —
not the launchctl state.

## When to Apply

**For the rename pattern:** any time you have two or more
LaunchAgents for the same project whose only difference is the
trigger mechanism (`WatchPaths`, `StartCalendarInterval`,
`StartInterval`, manual `launchctl kickstart`, etc.). Encode the
mechanism in the Label and the filename. If the agent's job
description changes (e.g. harvest now also notifies), update the
label to match — don't let the label drift from the role.

**For the SSL-hang recovery:** any time `launchctl list` shows the
agent ran recently but `n_queries_run=0`, the running-JSON is stale,
the python process is alive at 0% CPU holding `data/runs/LOCK`, and
stdout buffering has hidden any error. The diagnostic ladder is the
same regardless of upstream API — the question is always "can shell
curl reach it, can Python stdlib reach it, can httpx reach it?".
Only the third failing is the known
httpx-on-Python-3.14.5-macOS-26.3.1 pattern; in that case the
workaround (SIGTERM + remove `.running.json` + retry) is the
recovery, not the fix.

**For the pause sentinel:** before any "why isn't the pipeline
running" investigation, before any `launchctl unload`, before any
`tail -f` of the pipeline log. The sentinel is invisible from
`launchctl list` output.

## Examples

### Example A — Old vs new plist filenames

**Before** (operator can't tell which is which from `ls`):

```
deploy/
  com.fuchitalee.x-monitor.plist             # WatchPaths on config.yaml
  com.fuchitalee.x-monitor.scheduled.plist   # 15-min StartCalendarInterval
```

**After** (filename encodes role):

```
deploy/
  com.fuchitalee.x-monitor.config-reload.plist   # WatchPaths on config.yaml
  com.fuchitalee.x-monitor.harvest.plist         # 15-min StartCalendarInterval
```

`launchctl list | grep com.fuchitalee.x-monitor` now returns:

```
12345   0   com.fuchitalee.x-monitor.config-reload
12346   0   com.fuchitalee.x-monitor.harvest
```

### Example B — Old vs new operator reload sequence

**Before** (rename had to be done by hand, easy to miss a file):

```bash
# manually rename plists on disk, edit install scripts, reload
launchctl unload ~/Library/LaunchAgents/com.fuchitalee.x-monitor.plist
launchctl unload ~/Library/LaunchAgents/com.fuchitalee.x-monitor.scheduled.plist
# ... edit each plist by hand ...
launchctl load ~/Library/LaunchAgents/com.fuchitalee.x-monitor.plist
launchctl load ~/Library/LaunchAgents/com.fuchitalee.x-monitor.scheduled.plist
```

**After** (pull, then run the updated install scripts):

```bash
launchctl unload ~/Library/LaunchAgents/com.fuchitalee.x-monitor.plist
launchctl unload ~/Library/LaunchAgents/com.fuchitalee.x-monitor.scheduled.plist
rm ~/Library/LaunchAgents/com.fuchitalee.x-monitor.plist
rm ~/Library/LaunchAgents/com.fuchitalee.x-monitor.scheduled.plist
bash deploy/install.sh
bash deploy/install-scheduled.sh
launchctl list | grep com.fuchitalee.x-monitor
```

Both install scripts now `cp` the renamed plist, `launchctl load`
it under the new label, and the verification `grep` matches the new
filename.

### Example C — Plist Label change (concrete)

`deploy/com.fuchitalee.x-monitor.config-reload.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!--
  Role: config-reload agent.
  Trigger: WatchPaths on config.yaml (file-edit).
  Invokes: deploy/run-pipeline-watchpaths.sh
-->
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.fuchitalee.x-monitor.config-reload</string>
  <key>WatchPaths</key>
  <array>
    <string>/Users/fuchitalee/development/minimax-marketing/x-monitoring/config.yaml</string>
  </array>
  ...
</dict>
</plist>
```

`deploy/com.fuchitalee.x-monitor.harvest.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!--
  Role: harvest agent (15-minute cadence).
  Trigger: StartCalendarInterval at minute 0 (0, 15, 30, 45).
  Invokes: deploy/run-pipeline-with-notify.sh
  Logs: ~/Library/Logs/x-monitor/harvest-{stdout,stderr}.log
-->
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.fuchitalee.x-monitor.harvest</string>
  <key>StartCalendarInterval</key>
  <array>
    <dict><key>Minute</key><integer>0</integer></dict>
    <dict><key>Minute</key><integer>15</integer></dict>
    <dict><key>Minute</key><integer>30</integer></dict>
    <dict><key>Minute</key><integer>45</integer></dict>
  </array>
  <key>StandardOutPath</key>
  <string>/Users/fuchitalee/Library/Logs/x-monitor/harvest-stdout.log</string>
  <key>StandardErrorPath</key>
  <string>/Users/fuchitalee/Library/Logs/x-monitor/harvest-stderr.log</string>
  ...
</dict>
</plist>
```

### Example D — SSL-hang diagnostic walkthrough

Observed in this session:

```text
$ ps -o pid,pcpu,rss,stat,command -p 84123
  PID  %CPU    RSS STAT COMMAND
84123   0.0  90240   S   python3 deploy/run-pipeline-with-notify.py --scheduled

$ lsof -p 84123 | grep LOCK
python3  84123  user  3w  REG  .../x-monitoring/data/runs/LOCK

$ ls -la /tmp/x-monitor-pipeline.log
-rw-r--r-- 1 user wheel 0 Jul 17 09:47 /tmp/x-monitor-pipeline.log
# 0 bytes — python is buffering stdout

$ cat x-monitoring/data/runs/LATEST.running.json
{"run_id": "20260717-094500-...", "n_queries_run": 0, "phase_timings": {}}
# n_queries_run=0 — hang is on the FIRST outbound request, not deep in a query

$ time curl -sS -o /dev/null -w "%{http_code}\n" \
    "https://api.twitterapi.io/health"
401
curl -- real 0.049s

$ python3 -c "import urllib.request, time; \
    t=time.time(); \
    urllib.request.urlopen('https://api.twitterapi.io/health', timeout=5); \
    print(f'{time.time()-t:.3f}s')"
0.290s
# stdlib works — hang is specific to httpx

# Recovery:
$ kill -TERM 84123
$ rm x-monitoring/data/runs/LATEST.running.json
# next 15-minute boundary retries
```

The `time curl` and `python3 ...urllib...` tests are the
discriminating signal. When they succeed and only `httpx` hangs,
the failure is in httpx's TLS path on Python 3.14.5 + macOS 26.3.1,
not in the network or the API. Don't waste time restarting `launchd`
or rotating API keys — those won't change anything.

### Example E — Pause sentinel check

```bash
$ ls -la /tmp/x-monitor-paused
-rw-r--r-- 1 user wheel 0 Jul 16 06:12 /tmp/x-monitor-paused
# 35 hours old — left over from yesterday's pause

$ tail -5 /tmp/x-monitor-pipeline.log
# last line is from yesterday 06:12 — both agents have been silent since

# Resume:
$ rm /tmp/x-monitor-paused
$ launchctl kickstart -k gui/$(id -u)/com.fuchitalee.x-monitor.harvest
# next quarter-hour boundary (or this kickstart) fires the agent
```

## File reference

| Path                                                                  | What changed                                              |
| --------------------------------------------------------------------- | --------------------------------------------------------- |
| `deploy/com.fuchitalee.x-monitor.config-reload.plist`                 | Renamed; Label + comment header                           |
| `deploy/com.fuchitalee.x-monitor.harvest.plist`                       | Renamed; Label + comment header; log paths renamed        |
| `deploy/install.sh`                                                   | `PLIST_SRC`/`DST`, grep pattern, echo messages            |
| `deploy/install-scheduled.sh`                                         | Same updates; "scheduled" → "harvest" everywhere          |
| `deploy/run-pipeline-watchpaths.sh`                                   | Added `# Invoked by:` header                              |
| `deploy/run-pipeline-with-notify.sh`                                  | Added `# Invoked by:` header; osascript "harvest run"     |
| `x-monitoring/README.md`                                              | Full rewrite (~440 lines); major section on both agents   |
| `x-monitoring/deploy/README.md`                                       | LaunchAgents section listing both new labels              |

## Related

- [[docs/plans/2026-06-19-005-feat-fix-x-monitor-cron-runtime-plan.md]] — original install of the two agents; rename is a follow-up, not new ground.
- [[docs/issues/2026-06-20-162625-x-monitor-v18-minimax-proxy-25x-slowdown.md]] — flagged `pipeline_lock` (`fcntl.flock` on `data/runs/LOCK`) failing under double-fire and called out a "11+ min SSL read is a connection-pool issue" hypothesis — same surface as this TwitterAPI.io hang.
- [[docs/debug/2026-07-14-171500-cursor-fix-verify-before-revert.md]] — 11+ min SSL read against the LLM proxy (Alibaba Cloud 47.89.128.168); same `_ssl__SSLSocket_read` shape, different endpoint. Same diagnostic ladder applies.
- [[docs/debug/2026-07-14-160222-call-state-not-persisting.md]] — documents the `/tmp/x-monitor-paused` kill-switch activation procedure (`rm /tmp/x-monitor-paused; launchctl load ...`) that this learning also covers.
- [[memory/2026-07-14-sinceTime-fix-applied]] — when the SSL hang is recovered and the pipeline resumes, cursor logic MUST use inline `since_time:<epoch>` operator, not URL-side `sinceTime`.
- [[memory/2026-07-15-llm-auth-fix-applied]] — `ANTHROPIC_API_KEY` rotated; pipeline past 401s but SSL hang + LLM batch truncation remain.
- [[memory/2026-07-17-twitterapi-ssl-read-hang]] — same SSL hang observation, auto-memory snapshot.
- [[x-monitoring/deploy/README.md]] — canonical deploy doc; the rename + sentinel are already documented there.
- [[x-monitoring/x_monitor/run.py]] — hosts `pipeline_lock` and `self.lock_path = self.runs_dir / 'LOCK'`; the operator-recovery story depends on FD 3 holding this path.
- [[x-monitoring/x_monitor/apify.py]] — hosts `TwitterApiClient`, the httpx-using code path that hangs.
