# 2026-07-15 — Pipeline resume + LLM auth fix

**Status:** PRIMARY BLOCKER CLEARED. Pipeline past 401s. Secondary issue (LLM batch truncation + SSL read hang) remains.
**Branch:** `main` @ `dcf0a8c` (cursor fix a46020f + until_time dcf0a8c + kill-switch d1f7a3a all live)
**Reporter:** Claude Code (this session)

---

## TL;DR

The "X API error" the operator referenced on 2026-07-14 was an **LLM authentication failure**, not an X API error. Two compounding causes:

1. **Operator kill-switch in place** since 2026-07-14 17:00 JST (`/tmp/x-monitor-paused`). Every scheduled cycle logged "paused: skipping pipeline run" and exited 0.
2. **Stale `ANTHROPIC_API_KEY` in `~/.env.secrets`**: `sk-ant-api...` (Anthropic-native, 108 chars) — the Alibaba-gateway-compatible credential was in the shell (`sk-cp-uhKE...`, 125 chars) but not in the env file. Pipeline rejected every LLM call with HTTP 401.

Fix applied: replaced `ANTHROPIC_API_KEY` in `~/.env.secrets`, removed pause file, cleared stale LOCK + LATEST.running.json.

---

## Diagnosis chain

### Step 1 — Verify cursor fix (commit a46020f + dcf0a8c)

The debug doc (`docs/debug/2026-07-14-171500-cursor-fix-verify-before-revert.md`) flagged that the URL-param `sinceTime` form might be silently dropped. Direct API tests confirmed:

| Test | URL pattern | n=20 results | older_than_floor (1h ago) |
|---|---|---|---|
| A | `sinceTime=<epoch>` URL param | 20 | **14** ← cursor not honored |
| B | `since_time:<epoch>` inline | 8 | **0** ← cursor honored |
| C | no filter (control) | 20 | **14** ← identical to A |
| D | both bounds inline (`since_time:<floor> until_time:<now>`) | 13 | **0** ← cursor honored |

**Tests A and C return byte-identical data → `sinceTime` URL param is silently dropped by TwitterAPI.io. Inline `since_time:` operator is the only working form.**

The cursor fix in commits a46020f + dcf0a8c is correct. **Do NOT revert.**

### Step 2 — Identify actual pipeline failure

`/tmp/x-monitor-pipeline.log` showed every 15-min cycle logging `paused: /tmp/x-monitor-paused exists; skipping pipeline run` since 2026-07-14. The pause file's own content documented the diagnosis:

> "Pipeline re-paused because `classify_pragmatics_full` hangs on a downstream HTTPS call (Alibaba-hosted endpoint, 11+ min SSL read with no response — likely the LLM API key has been failing throughout the 11-day window)."

The user's "X API error" was the LLM proxy, not TwitterAPI.io. This matched debug doc hypothesis #1.

### Step 3 — Verify LLM endpoint reachability

```bash
curl -sS -w "\nHTTP=%{http_code} time=%{time_total}s\n" \
  "${ANTHROPIC_BASE_URL}/v1/messages" -X POST \
  -H "x-api-key: ${ANTHROPIC_API_KEY}" \
  -d '{"model":"claude-haiku-4-5","max_tokens":10,"messages":[{"role":"user","content":"hi"}]}'
```

Result with current shell env: **200 OK in 1.77s**. Gateway is healthy.

### Step 4 — Header format ruled out (red herring)

Per the gateway's 401 message ("Please carry the API secret key in the 'X-Api-Key' field"), I initially suspected an SDK header mismatch. Tested all three forms:

| Header | HTTP | time |
|---|---|---|
| `x-api-key` (SDK default) | 200 | 1.84s |
| `X-Api-Key` (gateway expected) | 200 | 1.77s |
| `Authorization: Bearer` | 200 | 1.84s |

Gateway accepts all three. **Header format was NOT the issue.**

### Step 5 — Discover credential mismatch

```
$ grep "^export ANTHROPIC_API_KEY=" ~/.env.secrets
export ANTHROPIC_API_KEY=<set>

$ zsh -c 'source ~/.env.secrets && echo "${ANTHROPIC_API_KEY:0:10}...len=${#ANTHROPIC_API_KEY}"'
sk-ant-api...len=108

$ echo "${ANTHROPIC_API_KEY:0:10}...len=${#ANTHROPIC_API_KEY}"  # current shell
sk-cp-uhKE...len=125
```

**Two completely different credentials.** `~/.env.secrets` had the Anthropic-native key (rejected by Alibaba gateway); the current shell had the Alibaba-gateway-compatible key (working).

---

## Fix applied

### Backup

```bash
cp ~/.env.secrets ~/.env.secrets.bak.20260715T102104
```

### Replace credential (Python, to avoid secret in shell history)

```python
import os, re
path = os.path.expanduser("~/.env.secrets")
with open(path) as f: content = f.read()
new_key = os.environ["ANTHROPIC_API_KEY"]
new_content = re.sub(
    r'^export ANTHROPIC_API_KEY=.*$',
    f'export ANTHROPIC_API_KEY={new_key}',
    content, flags=re.MULTILINE)
with open(path, "w") as f: f.write(new_content)
```

(Pattern `^export ANTHROPIC_API_KEY=.*$` matches ONLY the bare-name line, not `ANTHROPIC_API_KEY_AL` or `ANTHROPIC_API_KEY_CO_JP`.)

### Remove kill switch + clear locks

```bash
rm -v /tmp/x-monitor-paused
rm -f data/runs/LOCK data/runs/LATEST.running.json
```

---

## Verification

### Live API test

```
$ curl ... ${ANTHROPIC_BASE_URL}/v1/messages -H "x-api-key: <new-key>" -d '{"model":"claude-haiku-4-5",...}'
HTTP=200 time=1.843385s
```

### Real cycle attempt #1 (LaunchAgent auto-fired)

- LaunchAgent `com.fuchitalee.x-monitor.scheduled` ticked at 10:15 JST
- Picked up the pause-file removal
- Pipeline started, ran past auth (no 401s in log)
- Hit `classify_batch_pragmatics_full` with 20-post batch
- Returned: `Unterminated string starting at: line 1 column 3831 (char 3830)`
- Fell back to per-post retries
- Hung in `_ssl__SSLSocket_read → poll` for 5+ minutes (sample at `/tmp/Python_2026-07-15_104242_AM_AIhw.sample.txt`)

### Real cycle attempt #2 (manual)

```bash
nohup bash -c 'cd /Users/fuchitalee/development/minimax-marketing/x-monitoring && .venv/bin/python -m x_monitor run' > /tmp/x-monitor-manual.log 2>&1 &
```

- 5 min elapsed, **0 × 401s** in log (auth fix verified)
- 1 × "Unterminated string" error on the same 20-post batch
- Same SSL read hang

---

## Remaining issue (secondary)

`classify_batch_pragmatics_full` at `x_monitor/attribution.py:1723` is failing on a 20-post batch:

```
classify_batch_pragmatics_full: batch LLM call failed after 3 retries for batch of 20 posts;
falling back to per-post retries: Unterminated string starting at: line 1 column 3831 (char 3830)
```

Single LLM calls work fine (1.8-3.4s in test). The 20-post batch may exceed the gateway's response envelope, OR the gateway rate-limits/stalls after a malformed response.

**Next investigator should check:**
1. Gateway per-minute request cap (was: no explicit cap visible; check after the malformed response)
2. `classify_batch_pragmatics_full` batch size — try reducing from 20 to 10 or 5
3. The batch prompt at `attribution.py:1723` — does it exceed the model's `max_tokens` output limit? (column 3831 of the response is the truncation point)

---

## Files in scope (this session)

| file | change | status |
|---|---|---|
| `~/.env.secrets` | replaced `ANTHROPIC_API_KEY` value | **backed up to `.bak.20260715T102104`** |
| `/tmp/x-monitor-paused` | removed | (was kill-switch sentinel) |
| `data/runs/LOCK` | removed | stale lock from manual cycle |
| `data/runs/LATEST.running.json` | removed | stuck symlink |
| `~/.claude/projects/.../memory/2026-07-15-llm-auth-fix-applied.md` | created | future-agent memory |

## Files NOT changed

- `x_monitor/apify.py` — cursor fix (a46020f + dcf0a8c) is correct, **do NOT revert**
- `x_monitor/attribution.py` — `classify_batch_pragmatics_full` not modified
- `x_monitor/run.py` — `classify_batch_pragmatics_full` call site (line 638) not modified
- `deploy/run-pipeline-with-notify.sh` — kill-switch logic preserved (commit d1f7a3a)
- `data/queries/` — already retired per plan 2026-07-11-001 (not a source of failure)

---

## Live status at end of session (10:45 JST)

- ✅ Pipeline unpaused
- ✅ LLM auth working (0 × 401s in latest runs)
- ✅ TwitterAPI.io cursor honored (verified via direct API test)
- ⚠️  Pipeline still hangs in `_ssl__SSLSocket_read` after the first LLM batch failure
- ⚠️  `classify_batch_pragmatics_full` 20-post batch returns truncated JSON
- ⏸️  No cycle has reached `n_queries_run > 0` since the kill-switch was removed

## Recommended next steps

1. **Reduce batch size** in `classify_batch_pragmatics_full` from 20 → 10 (or 5) and rerun
2. **Add a longer retry backoff** after the "Unterminated string" error (current behavior is 3 fast retries then hang)
3. **Add explicit `max_tokens` cap** in the batch prompt's call site — current value unclear from log
4. **Re-test the gateway after a malformed response** with `curl` to confirm it's not the gateway that hangs (vs. the SDK retry logic)
5. **Schedule another live cycle at 11:00 JST** to confirm whether the SSL read hang is reproducible or transient