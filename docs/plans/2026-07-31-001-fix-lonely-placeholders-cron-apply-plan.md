---
title: "Resolve 10,681 lonely placeholders via cron-managed TwitterAPI apply"
date: 2026-07-31
type: feat
artifact_readiness: implementation-ready
execution: code
target_repo: pushin-weight-v2
amends:
  - docs/plans/2026-07-30-002-feat-hybrid-funnel-then-reconcile-accounts-plan.md
---

# Resolve 10,681 lonely placeholders via cron-managed TwitterAPI apply

## Goal Capsule

Resolve the 10,681 lonely placeholder rows that Phase 2 reconciliation left in `pushinweight_shadow` (deferred 2026-07-30 — see `docs/investigations/2026-07-30-002-phase-2-partial-final-report.md`). Each row has a unique lowercase handle with no integer `author_id` — TwitterAPI.io can resolve it, but only at a rate that survives both the vendor's per-endpoint throttling AND fuchitalee's 16,384-port ephemeral limit.

**Stop when.** `placeholder_rows = 0` AND `lonely_apply_dead_letter.log` shows no rows newer than 7 days AND the `uniq_accounts_handle_lower` migration precheck passes (`SELECT COUNT(*) FROM (SELECT LOWER(handle) FROM accounts GROUP BY LOWER(handle) HAVING COUNT(*) > 1) AS d` returns 0).

**Execution profile.** One cron-driven Python command, re-entrant across runs, ~60 min wall-clock per pass at 5 QPS. Designed to be started, walked away from, and resumed on the next cron tick — partial progress is always consistent because every apply is per-row succeed-or-dead-letter inside a SAVEPOINT.

**Why a cron, not a one-shot loop.** Three reasons the prior Phase 2 work didn't finish:

1. TwitterAPI returns intermittent 429s and stealth-404s under load — a single 10K pass hits them somewhere in the middle. A cron run that crashes partway through leaves partial state; a cron run that completes 1,500 rows then hits a 429 can cool down and resume the next tick without losing work.
2. fuchitalee's ephemeral-port TIME_WAIT choked v6 at `TCPConnector(limit=100)` — 13,952 sockets stuck. Concurrency 2 keeps TIME_WAIT under 30 sockets at any moment, which the OS can recycle within the 15s `tcp.msl` window.
3. The user is leaving on a 2-hour car trip. The plan must finish within 1 hour of cron start, and must be safely re-startable if a tick gets interrupted.

**Out of band.** Re-resolving the 29 dead-lettered residual dup groups from Phase 2 (separate plan once TwitterAPI auth is reliable for ≥24h); the `uniq_accounts_handle_lower` migration itself (U12 in `2026-07-30-002`, depends on this plan finishing); re-enabling the paused harvester cron (U16 resume leg in `2026-07-30-002`).

---

## Product Contract

### Problem Frame

`pushinweight_shadow` has 10,681 placeholder rows (9,694 unique lowercase handles) that Phase 2 reconciliation couldn't repoint because no integer `author_id` exists for the handle in `accounts`. The pre-pass v6 attempt resolved 226 of 10,908 via `aiohttp` parallel lookups (`feat/reconcile: parallel pre-pass + User-Agent fix + canonical-insert`) before the run was stopped — fuchitalee's ephemeral port range was exhausted (16,384 ports, 13,952 in TIME_WAIT) by `TCPConnector(limit=100)`.

A successful resolution path must:

1. **Survive TwitterAPI rate limits** — vendor blog claims 200 QPS, observed per-endpoint throttling at sustained >30 QPS with intermittent 429s and stealth 404s. Plan calls for 5 QPS — 6× under any plausible ceiling.
2. **Survive fuchitalee ephemeral-port exhaustion** — `TCPConnector(limit=2)` keeps inflight sockets ≤ 2, TIME_WAIT ≤ 30 at any moment. v6 evidence: `limit=100` broke at 13,952 TIME_WAIT. v7 with `limit=2` runs indefinitely.
3. **Be cron-reentrant** — operator can start the cron, leave for 2 hours, return to either "still running" (good), "finished" (better), or "stopped at row 4,231 because TwitterAPI 429'd" (also fine — next tick picks up at row 4,232). The apply must never produce inconsistent state on a crash mid-row.
4. **Distinguish transient 429 from permanent not-found** — Phase 2 conflated HTTP 404 with HTTP-200 + `{"status":"error","msg":"user not found","data":null}`. v7 separates: 429 → backoff + retry same handle on next tick; 200-with-empty → dead-letter; HTTP 404 → dead-letter.

### Scope Boundaries

**In scope.**

- U1 — pin the current 10,681 lonely-placeholder state as a regression net BEFORE the apply.
- U2 — a new `manage.py resolve_lonely_placeholders` Django command with `--apply` and `--batch-size` and `--max-seconds` flags.
- U3 — `aiohttp`-based TwitterAPI caller with `TCPConnector(limit=2)`, `User-Agent: curl/7.84.0`, `Retry-After`-aware backoff, dead-letter logging.
- U4 — apply step that runs the existing `_repoint_fk` logic (already ships in `reconcile_account_duplicates.py`) per-row inside SAVEPOINT transactions.
- U5 — entry/exit summary that writes a structured log to `~/lonely-apply.log` so the cron can be checked at a glance.
- U6 — re-entrancy test (kill -9 mid-apply, restart, verify no orphan placeholders + no duplicate rows).
- U7 — operator runbook for the cron launch + monitoring + dead-letter triage.

**Out of scope.**

- The 29 dead-lettered residual dup groups from Phase 2 (separate plan; handle list in `~/residual-apply-v2.log`).
- The `uniq_accounts_handle_lower` unique index migration (U12 in `2026-07-30-002`; depends on this plan finishing).
- Re-enabling the paused harvester cron (U16 resume leg in `2026-07-30-002`).
- Switching `author_id` to BIGINT (out of scope; touches every consumer).
- Backfilling author metadata (display_name, bio, follower counts) on the now-canonical rows.

### Requirements (traceability)

- **R1 — Operator's 1-hour wall-clock budget.** Implementation must finish 10,681 rows in ≤ 60 minutes on the live `pushinweight_shadow` DB at the chosen rate (5 QPS + 50 rows/sec apply). Source: user's pre-trip constraint.
- **R2 — Cron-reentrant.** Killing the process mid-apply must leave the DB in a state where a fresh invocation picks up exactly where it left off, with no orphan placeholders and no canonical-row duplicates. Source: cron pattern + operator's "leave for 2 hours" constraint.
- **R3 — Survive fuchitalee port exhaustion.** With `TCPConnector(limit=2)`, the running process must keep `netstat -an | grep TIME_WAIT | wc -l` under 100 at all times. Source: v6 incident — 13,952 TIME_WAIT blocked all DB connections.
- **R4 — Distinguish transient vs permanent API failures.** 429 / connection-error → backoff + queue for next tick. 200-with-empty / 404 → dead-letter to `~/lonely-apply-dead-letter.log`. Source: Phase 2 reconciliation showed the conflation caused real handles to be dead-lettered.
- **R5 — No schema change.** The apply reads + writes the existing `accounts` / `posts` / `account_post_appearances` / `brands_accounts` tables using the same `_repoint_fk` / `_ensure_canonical_account_row` paths Phase 2 ships. No new columns, no new indexes, no new migrations. Source: keeps this plan narrow — the unique index is a separate plan's work.
- **R6 — Test-first.** Each behavioral change ships with a pytest test that fails before the change and passes after. Source: global CLAUDE.md TDD rule + Phase 2's bug-history lesson (3 regressions caught by tests that would have shipped without them).

---

## Planning Contract

### Key Technical Decisions

- **KTD1 — Rate = 5 QPS sustained, concurrency = 2.** Hard-coded as constants in the new module. Wall-clock target: 36 min lookups + 4 min apply + ~20 min retry / dead-letter overhead = ~60 min for 10,681 rows. Sourced from `docs/research/twitterapi_docs/rate-limit-ux.md` (community reports of intermittent 429s without `Retry-After` above ~30 QPS) and Phase 2's v6 incident (13,952 TIME_WAIT at `limit=100`). 6× under any plausible per-endpoint ceiling; ~16× under fuchitalee's port ceiling.

- **KTD2 — Per-row SAVEPOINT transactions.** Each placeholder resolution is `BEGIN ... SAVEPOINT lonely_<author_id> ... RELEASE` or `ROLLBACK TO lonely_<author_id>`. On process kill mid-row, the outermost transaction is open only for the duration of one `_ensure_canonical_account_row` + `_repoint_fk` cycle (~50ms) — never long enough to leave partial state. Sourced from Phase 2's existing pattern in `_repoint_fk`.

- **KTD3 — TwitterAPI caller uses `aiohttp` with `TCPConnector(limit=2)`, not `ThreadPoolExecutor`.** Sourced from Phase 2 bug history: ThreadPoolExecutor serialized on the GIL at ~1 req/sec; aiohttp at limit=2 sustained the full 5 QPS budget without port exhaustion.

- **KTD4 — User-Agent header is `curl/7.84.0`.** Sourced from Phase 2 fix: `urllib.request.Request` sends `Python-urllib/3.x` which TwitterAPI rejects with 403.

- **KTD5 — Dead-letter log is line-delimited JSON in `~/lonely-apply-dead-letter.log`.** Each entry has `{handle, author_id, reason, status_code, response_excerpt, ts}`. The cron run reads its own dead-letter log on startup to skip already-dead-lettered handles (R2 re-entrancy). Format chosen so the operator can `jq` the file for triage.

- **KTD6 — Exit summary is a single line of JSON on stdout AND appended to `~/lonely-apply.log`.** Fields: `{started_at, finished_at, total_placeholders, looked_up, resolved, dead_lettered, retried, rate_actual_qps, max_time_wait_sockets}`. The cron entry checks `~/lonely-apply.log` after each tick.

- **KTD7 — `--max-seconds 3300` default (55 min).** Below the 1-hour budget to leave slack for the final write + log flush. The cron tick is 1 hour; if the apply runs longer, the cron `timeout` kills it gracefully and the next tick picks up. Sourced from user's 1-hour wall-clock target.

### Patterns to follow

- The apply logic reuses `_repoint_fk` and `_ensure_canonical_account_row` from `monitor/management/commands/reconcile_account_duplicates.py` (lines 414–469 in the Phase 2 partial-final-report commit graph). Don't rewrite — import.
- The `_twitterapi_lookup_batch` aiohttp pattern from the same file (Phase 2 v6 fix) is the reference for the new caller's shape.
- The cron style follows `docs/operations/pause-and-resume-harvest-cron.md` for log conventions (timestamped lines, `~/` paths, exit summary at the end).

### Assumptions

- A1 — The TwitterAPI key in `~/.env.secrets` on fuchitalee is valid and not currently rate-limited at 5 QPS. Phase 2 reconciliation saw clean 200s at single-shot probes; no global block in evidence.
- A2 — The `pushinweight_shadow` DB is reachable from fuchitalee via the existing `DATABASE_URL` in `.env`. Verified during Phase 2.
- A3 — The Phase 2 partial-final-report's audit numbers (10,681 lonely placeholders, 9,694 unique handles) are still accurate on 2026-07-31. U1's regression net asserts this.
- A4 — fuchitalee's `tcp.msl=15000` (15s TIME_WAIT) is unchanged. Mitigated by KTD1's limit=2 — irrelevant if it changed.

### Risks

- **R-1 — TwitterAPI returns 200-with-empty for a handle that DOES exist on X.** Phase 2's aiohttp pre-pass saw this for some handles; retry-with-backoff didn't help. Mitigation: dead-letter these to `~/lonely-apply-dead-letter.log` and accept that they remain lonely placeholders. They can be re-resolved in a follow-up plan if TwitterAPI auth stabilizes.
- **R-2 — fuchitalee's network drops mid-batch.** Mitigation: SAVEPOINT per row means a connection drop kills only the current row; next cron tick resumes.
- **R-3 — A 1-hour cron tick + 55-min `--max-seconds` = tight scheduling.** Mitigation: if the apply gets close to `--max-seconds`, it writes a `partial=true` exit summary and the cron timeout doesn't penalize the next tick.
- **R-4 — Operator's 1-hour wall-clock budget is tight if TwitterAPI throttles unexpectedly.** Mitigation: 5 QPS is 6× under any observed ceiling. If 429s do appear, the apply backs off automatically. Worst case: 2 cron ticks (~2 hours) finish the work.

---

## Implementation Units

### U1. Pin current 10,681 lonely-placeholder state as regression net (BEFORE pins)

**Goal.** Ship a pytest test that pins the exact count of lonely placeholders, the unique-handle count, and the per-placeholder-type breakdown. Test passes green on `pushinweight_shadow` BEFORE any apply runs; will be flipped to AFTER state in a follow-up commit.

**Files.**

- New: `tests/test_lonely_placeholders_regression_net.py`
- Reads: `monitor/management/commands/reconcile_account_duplicates.py` (the `_find_lonely_placeholders` function — reuse the query, don't duplicate)

**Pinned values (from `docs/investigations/2026-07-30-002-phase-2-partial-final-report.md`):**

```python
LONELY_PLACEHOLDER_ROW_COUNT = 10681       # was 10908 before v6 resolved 226
LONELY_PLACEHOLDER_UNIQUE_HANDLES = 9694
# Per-prefix breakdown:
HANDLE_PREFIX_PLACEHOLDER_ROWS = ?         # assert in test setup
SYNTHETIC_PREFIX_PLACEHOLDER_ROWS = ?
NON_INTEGER_NON_PLACEHOLDER_EDGE_ROWS = 22
# BEFORE pins for surface elements this plan intentionally does NOT change:
INTEGER_AUTHOR_ID_COUNT = 6356
TOTAL_ACCOUNTS = 17059
DUP_HANDLE_GROUPS = 29                     # Phase 2 dead-lettered residual
```

Run on `pushinweight_shadow` first to capture the actual prefix breakdown (test setup queries DB once and pins the result; the assertion is on the pinned values, not re-queried).

**Patterns to follow.** Same shape as `tests/test_regression_net_after_apply.py` (Phase 2 U14) — pytest with `@pytest.mark.django_db`, queries the live DB via the test runner's connection.

**Test scenarios.**

1. `test_lonely_placeholder_row_count_pinned` — asserts `count == LONELY_PLACEHOLDER_ROW_COUNT`.
2. `test_lonely_placeholder_unique_handle_count_pinned` — asserts the case-insensitive distinct count.
3. `test_per_prefix_breakdown_pinned` — three separate assertions for `handle:`, `synthetic:`, edge cases.
4. `test_integer_author_id_count_unchanged` — assert `6356` (the apply doesn't touch integer rows).
5. `test_total_accounts_unchanged` — assert `17059` (U12 unique-index is a separate plan).
6. `test_dup_handle_groups_unchanged` — assert `29` (Phase 2's residual dead-letters, not this plan's scope).

### U2. New `manage.py resolve_lonely_placeholders` command — flag surface

**Goal.** Ship a Django management command that exposes `--apply`, `--batch-size`, `--max-seconds`, `--rate-qps`, `--concurrency`, `--dry-run`, `--skip-dead-lettered`. Defaults are KTD1 (rate=5, concurrency=2) + KTD7 (max-seconds=3300). `--dry-run` is the default behavior.

**Files.**

- New: `monitor/management/commands/resolve_lonely_placeholders.py`
- Reads: `monitor/management/commands/reconcile_account_duplicates.py` (imports `_find_lonely_placeholders`, `_repoint_fk`, `_ensure_canonical_account_row` — do not duplicate logic)
- Tests: `tests/test_resolve_lonely_placeholders_flags.py`

**Command structure (sketch).**

```python
class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--batch-size", type=int, default=200)
        parser.add_argument("--max-seconds", type=int, default=3300)
        parser.add_argument("--rate-qps", type=float, default=5.0)
        parser.add_argument("--concurrency", type=int, default=2)
        parser.add_argument("--dry-run", action="store_true", default=True)
        parser.add_argument("--skip-dead-lettered", action="store_true", default=True)

    def handle(self, *args, **opts):
        # 1. Read ~/lonely-apply-dead-letter.log if --skip-dead-lettered
        # 2. SELECT lonely placeholders (exclude dead-lettered)
        # 3. Loop: aiohttp TwitterAPI caller (KTD3) at --rate-qps
        # 4. Per successful lookup: call _repoint_fk + _ensure_canonical_account_row
        # 5. Per dead-letter: append to ~/lonely-apply-dead-letter.log
        # 6. Write exit summary to ~/lonely-apply.log + stdout
```

**Patterns to follow.** Mirrors `reconcile_account_duplicates.py`'s `add_arguments` + `handle` shape; same `--json` summary output convention; same `BaseCommand` import path.

**Test scenarios.**

1. `test_default_flags_match_ktd1_ktd7` — bare invocation has rate=5, concurrency=2, max-seconds=3300, dry-run=True.
2. `test_apply_flag_disables_dry_run` — `--apply` flips `dry-run` off.
3. `test_skip_dead_lettered_reads_log` — populates `~/lonely-apply-dead-letter.log` with 5 handles; asserts the candidate queryset excludes them.
4. `test_exit_summary_written_to_log` — invokes with `--apply --batch-size 1`; asserts a single JSON line appended to `~/lonely-apply.log` with all required fields.
5. `test_max_seconds_triggers_graceful_exit` — sets `--max-seconds 1`; asserts the command exits with `partial=true` in the summary.

### U3. `aiohttp` TwitterAPI caller with rate gating + dead-letter logging

**Goal.** Ship the `_twitterapi_lookup_handle` async function that: caps concurrency at `TCPConnector(limit=2)`, gates requests to `--rate-qps` via `asyncio.sleep`, honors `Retry-After`, and returns one of `{success: {author_id, ...}, dead_letter: {reason, status_code, response_excerpt}}`.

**Files.**

- New: `monitor/twitterapi/caller.py` (or inline in the command if the surface is small — decide during execution)
- Reads: Phase 2's `_twitterapi_lookup_batch` from `reconcile_account_duplicates.py`
- Tests: `tests/test_twitterapi_caller_shape.py`

**Shape.**

```python
async def lookup_batch(handles: list[str], *, rate_qps: float, concurrency: int) -> AsyncIterator[LookupResult]:
    """Yield per-handle results. Concurrency <= concurrency arg. Pacing <= rate_qps."""
    connector = aiohttp.TCPConnector(limit=concurrency)
    async with aiohttp.ClientSession(
        connector=connector,
        headers={"X-API-Key": TWITTERAPI_KEY, "User-Agent": "curl/7.84.0"},
    ) as session:
        sem = asyncio.Semaphore(concurrency)
        gate_interval = 1.0 / rate_qps
        async def one(handle: str) -> LookupResult:
            async with sem:
                try:
                    async with session.get(f"{BASE}/twitter/user/info", params={"userName": handle}, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        if resp.status == 429:
                            retry_after = float(resp.headers.get("Retry-After", "2"))
                            await asyncio.sleep(retry_after)
                            # ONE retry inline; further 429s → dead-letter "rate_limited"
                            async with session.get(...) as resp2:
                                return _classify(resp2, handle)
                        return _classify(resp, handle)
                except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                    return LookupResult.dead_letter(handle, reason="connection_error", exc=repr(e))
            await asyncio.sleep(gate_interval)  # pacing gate

        await asyncio.gather(*(one(h) for h in handles))
```

**Classification rules (KTD4):**

- HTTP 200 + `{"status":"success","data":{...}}` → success
- HTTP 200 + `{"status":"error","msg":"user not found","data":null}` → dead_letter (`reason="not_found_200"`)
- HTTP 404 → dead_letter (`reason="http_404"`)
- HTTP 429 after one retry → dead_letter (`reason="rate_limited"`)
- HTTP 5xx → dead_letter (`reason="http_5xx"`)
- Connection error / timeout → dead_letter (`reason="connection_error"`)

**Test scenarios.**

1. `test_429_with_retry_after_triggers_one_retry` — mock session returns 429 then 200; asserts two requests made.
2. `test_429_after_retry_is_dead_letter` — mock returns 429 twice; asserts dead_letter result.
3. `test_200_with_empty_data_is_dead_letter` — mock returns `{"status":"error",...}` with HTTP 200.
4. `test_http_404_is_dead_letter` — mock returns 404.
5. `test_concurrency_capped_at_two` — instrument the connector; assert `limit == 2` passed through.
6. `test_user_agent_is_curl` — captured headers assert `"User-Agent": "curl/7.84.0"`.

### U4. Apply step — reuse `_repoint_fk` + `_ensure_canonical_account_row` per row inside SAVEPOINT

**Goal.** The apply step calls the existing Phase 2 functions per placeholder, inside a SAVEPOINT transaction, so a mid-row crash leaves zero residue.

**Files.**

- Modify: `monitor/management/commands/resolve_lonely_placeholders.py` (U2 file — apply logic added here)
- Reads: `monitor/management/commands/reconcile_account_duplicates.py::_repoint_fk` + `_ensure_canonical_account_row`

**Per-row apply (sketch).**

```python
def apply_one(author_id: str, canonical: dict) -> ApplyResult:
    """Resolve one lonely placeholder. Returns (resolved | dead_letter)."""
    with transaction.atomic():
        sid = transaction.savepoint()
        try:
            canonical_id = _ensure_canonical_account_row(canonical)
            _repoint_fk("posts", author_id, canonical_id)
            _repoint_fk("account_post_appearances", author_id, canonical_id)
            _repoint_fk("brands_accounts", author_id, canonical_id)
            transaction.savepoint_commit(sid)
            return ApplyResult.resolved(author_id, canonical_id)
        except IntegrityError as e:
            transaction.savepoint_rollback(sid)
            return ApplyResult.dead_letter(author_id, reason="integrity_error", exc=repr(e))
```

**Critical: do NOT pre-pass INSERT canonical rows.** Phase 2 v4/v5 shipped this bug — caused 387–587 new duplicate groups that needed three cleanup scripts (`u_cleanup_prepass_damage.py`, `u_cleanup_prepass_drift.py`, v6 +1 dup group revert). The existing `_ensure_canonical_account_row` already does the right KTD10 semantics; the apply loop's INSERT happens inside the same SAVEPOINT as the placeholder DELETE, so concurrent readers never see a double-row state.

**Test scenarios.**

1. `test_apply_one_resolves_lonely_placeholder` — given a lonely placeholder + a TwitterAPI 200 response; assert `posts.author_id` repointed, placeholder row deleted, no duplicate created.
2. `test_apply_one_integrity_error_is_dead_letter` — pre-create a brands_accounts collision; assert dead_letter result, no orphan rows.
3. `test_mid_apply_crash_leaves_no_residue` — `kill -9` the test process mid-apply (use `pytest --forked` or manual SIGKILL); restart; assert no orphan placeholders + no duplicate canonicals.

### U5. Exit summary + log conventions

**Goal.** Ship a single-line JSON exit summary on stdout AND appended to `~/lonely-apply.log`. Each run's entry is one line, so the operator can `tail -f ~/lonely-apply.log` and `tail -f ~/lonely-apply-dead-letter.log` to monitor cron progress.

**Files.**

- New: `monitor/management/commands/resolve_lonely_placeholders.py` (U2 file — exit summary added here)
- Tests: `tests/test_resolve_lonely_placeholders_exit_summary.py`

**Exit summary shape (one JSON object per line).**

```json
{
  "started_at": "2026-07-31T14:00:00+09:00",
  "finished_at": "2026-07-31T14:55:23+09:00",
  "total_placeholders": 10681,
  "looked_up": 10681,
  "resolved": 9123,
  "dead_lettered": 1558,
  "retried_after_429": 42,
  "rate_actual_qps": 4.92,
  "max_time_wait_sockets": 23,
  "partial": false,
  "dead_letter_reasons": {"not_found_200": 1401, "rate_limited": 95, "http_404": 62}
}
```

**Log paths (KTD5, KTD6).**

- `~/lonely-apply.log` — append-only, one JSON line per cron run. Operator monitors this.
- `~/lonely-apply-dead-letter.log` — append-only, one JSON line per dead-lettered handle. The next run reads this on startup and skips already-dead-lettered handles (R2 re-entrancy + `--skip-dead-lettered`).

**Test scenarios.**

1. `test_exit_summary_has_required_fields` — bare `--dry-run` invocation produces stdout matching the schema above (with `resolved=0`).
2. `test_exit_summary_appended_to_log` — invoke twice; assert `~/lonely-apply.log` has two lines.
3. `test_dead_letter_log_has_required_fields` — pre-poison a handle to force dead_letter; assert the dead-letter log line has `handle, reason, status_code, response_excerpt, ts`.

### U6. Re-entrancy + port-exhaustion regression tests

**Goal.** Two integration tests that prove (a) a SIGKILL mid-apply leaves the DB in a state where the next run picks up cleanly, and (b) `TCPConnector(limit=2)` keeps TIME_WAIT under 100 sockets for the full 10,681-row run.

**Files.**

- New: `tests/test_resolve_lonely_placeholders_reentrancy.py`
- New: `tests/test_resolve_lonely_placeholders_port_safety.py`

**Test scenarios (re-entrancy).**

1. `test_sigkill_mid_apply_resumes_cleanly` — invoke with `--apply --batch-size 1`, SIGKILL after the first row resolves; re-invoke; assert `count(placeholder_rows) == initial - 1` and no duplicate canonical rows.
2. `test_skip_dead_lettered_excludes_already_logged` — pre-populate `~/lonely-apply-dead-letter.log` with 5 handles; invoke; assert those 5 are not in the candidate queryset.
3. `test_partial_run_writes_partial_true` — set `--max-seconds 1`; assert the exit summary has `partial=true` and the next run picks up the remaining rows.

**Test scenarios (port safety).**

1. `test_time_wait_stays_under_100_sockets` — instrument the apply loop to sample `netstat -an | grep TIME_WAIT | wc -l` every 100 rows; assert max ≤ 100 for the full synthetic 10K-row run.
2. `test_concurrency_2_does_not_exhaust_ports` — same as above but explicit assertion that the connector was created with `limit=2`.

### U7. Operator runbook for cron launch + monitoring + dead-letter triage

**Goal.** A new `docs/operations/resolve-lonely-placeholders-cron.md` that documents: the launch command, the cron entry, the log paths, the monitoring recipe, the dead-letter triage steps, and the rollback plan (none needed — the apply is per-row, but document the `git revert` story).

**Files.**

- New: `docs/operations/resolve-lonely-placeholders-cron.md`

**Sections (required).**

1. **Launch** — exact command, exact env vars, exact working directory. `cd /Users/fuchitalee/development/pushin-weight-v2 && source .venv/bin/activate && DATABASE_URL=... python manage.py resolve_lonely_placeholders --apply >> ~/lonely-apply.log 2>&1`.
2. **Cron entry** — `0 * * * *` hourly tick, with `timeout 3600` and the launch command. Documented in `render.yaml` if deploy-side, or in `~/Library/LaunchAgents/` if local-side — operator chooses at launch time.
3. **Monitoring** — `tail -f ~/lonely-apply.log`, `tail -f ~/lonely-apply-dead-letter.log`, `jq` recipes for the exit summary.
4. **Dead-letter triage** — for each `reason` value, what to do. `not_found_200` and `http_404` → leave alone (these are genuinely not on X); `rate_limited` → wait 24h, re-run with `--apply --skip-dead-lettered=false` to retry the rate-limited subset; `http_5xx` → wait 1h, retry.
5. **Stop conditions** — when `placeholder_rows = 0` OR when all cron ticks have failed for 24h.
6. **Rollback** — none needed per-row; if a Phase 2-style systemic bug surfaces, `git revert` the U2/U3 commits and re-run the cleanup scripts.
7. **After-state regression net** — once `placeholder_rows = 0`, flip U1's pinned values to `0` and ship as the U14-style AFTER pins.

---

## Sequencing

**Phase 0: Pre-flight safety net (U1)**
1. U1 first — pins the current 10,681 state. Test passes green BEFORE any apply code is written.

**Phase 1: Apply path (U2 → U3 → U4)**
2. U2 ships the command skeleton + flag surface. `--dry-run` is the default; nothing touches the DB.
3. U3 ships the aiohttp caller with tests. Tested in isolation with mock sessions.
4. U4 wires U3's results into the existing `_repoint_fk` / `_ensure_canonical_account_row` paths. SAVEPOINT per row.

**Phase 2: Observability + re-entrancy (U5 → U6)**
5. U5 ships the exit summary + log conventions. Tested against `--dry-run`.
6. U6 ships the re-entrancy + port-safety integration tests. Run against the live `pushinweight_shadow` DB in a single `--apply --batch-size 100` smoke run before the cron goes live.

**Phase 3: Operator enablement (U7)**
7. U7 ships the runbook. Single doc commit.
8. Operator launches the cron, walks away, returns to either "finished" or "still running, partial state on disk."

**Phase 4: Post-trip verification**
9. After the trip: operator reads `~/lonely-apply.log`, asserts `placeholder_rows` is dropping, triages dead-letters per the runbook.

**Hard sequencing constraints.**

- KTD8: U1 must complete (and pass green) before U2 begins.
- KTD9: U4 must NOT pre-pass INSERT canonical rows — the SAVEPOINT per-row pattern is the only correct path. Re-uses Phase 2's `_ensure_canonical_account_row` which already handles KTD10 semantics.
- KTD10: U6's port-safety test must pass before the cron goes live.
- KTD11: U5's exit summary must include `partial=true` if `--max-seconds` triggered, so the cron can decide whether to retry the same row range next tick.

---

## Verification Contract

- `pytest tests/test_lonely_placeholders_regression_net.py -v` — U1 ships green BEFORE any apply.
- `pytest tests/test_resolve_lonely_placeholders_flags.py tests/test_twitterapi_caller_shape.py tests/test_resolve_lonely_placeholders_exit_summary.py -v` — U2 + U3 + U5 green.
- `pytest tests/test_resolve_lonely_placeholders_reentrancy.py tests/test_resolve_lonely_placeholders_port_safety.py -v` — U6 green against `pushinweight_shadow`.
- `python manage.py resolve_lonely_placeholders --dry-run --json` — prints the candidate count (10,681 minus any dead-lettered) and exits.
- `python manage.py resolve_lonely_placeholders --apply --batch-size 100 --max-seconds 60` — 60-second smoke run on `pushinweight_shadow`. Asserts: ≤ 300 rows resolved (5 QPS × 60s), exit summary written, dead-letter log appended for any failures.
- After the cron finishes (or operator returns from the trip): `python manage.py reconcile_account_duplicates --dry-run --json` should report `dup_groups == 29` (Phase 2 residual) and `placeholder_rows == 0` (this plan's work).

---

## Definition of Done

- U1 regression net ships with pinned BEFORE values, passes green on `pushinweight_shadow`.
- U2–U5 ship as a coordinated change in a single PR. All unit tests pass.
- U6 re-entrancy + port-safety tests pass on `pushinweight_shadow`.
- U7 runbook ships at `docs/operations/resolve-lonely-placeholders-cron.md`.
- 60-second smoke run on `pushinweight_shadow` resolves ≥ 250 rows, writes exit summary, writes dead-letter log entries for failures.
- Cron entry installed (operator choice: launchd on fuchitalee OR `render.yaml` cronJobs — whichever is live at trip time).
- Operator launches the cron before leaving on the trip; first cron tick is observed within 5 minutes of launch (verify `tail ~/lonely-apply.log`).
- All commits include the **Scope delivered vs plan promised: [match | narrower: deferred Y for reason Z]** line per global rules.

---

## Deferred to Follow-Up Work

- **The 29 Phase 2 residual dup groups.** Separate plan once TwitterAPI auth is reliable for ≥24h. Handle list in `~/residual-apply-v2.log`.
- **The `uniq_accounts_handle_lower` migration (U12 in `2026-07-30-002`).** Runs as part of the next production deploy AFTER this plan finishes. The precheck refuses until `dup_groups == 0`.
- **Re-enabling the paused harvester cron (U16 resume leg in `2026-07-30-002`).** Operator decision after U12 + a clean harvest cycle.
- **Backfilling author metadata** (display_name, bio, follower counts) onto the now-canonical rows. A second-pass script that joins `accounts` with the harvested post payloads.
- **Switching `author_id` to BIGINT.** Out of scope; touches every consumer.
- **Flipping U1's pinned values to AFTER state** (a follow-up commit) once `placeholder_rows == 0`.

---

## Sources & Research

- `docs/research/twitterapi_docs/rate-limit-ux.md` — the 30-day community research on TwitterAPI rate limits, intermittent 429s, stealth 404s.
- `docs/research/twitterapi_docs/endpoint/get_user_by_username.md` — the single-handle lookup endpoint (`/twitter/user/info`).
- `docs/research/twitterapi_docs/endpoint/batch_get_user_by_userids.md` — the bulk endpoint (100 IDs/call) — DEFERRED; the plan uses single-handle lookups because the lonely-placeholder handles are unknown integer IDs.
- `docs/research/twitterapi_docs/endpoint/introduction.md` — the 200 QPS claim (which Phase 2 reconciliation showed is not safely achievable in practice).
- `docs/investigations/2026-07-30-002-phase-2-partial-final-report.md` — the Phase 2 partial state, the 10,681 figure, the v6 port-exhaustion incident.
- `monitor/management/commands/reconcile_account_duplicates.py` — the Phase 2 apply logic this plan reuses (do not rewrite).
- `docs/operations/pause-and-resume-harvest-cron.md` — the cron log conventions this plan follows.
- `feedback_regression_net_in_every_plan.md` — the global rule that U1 pins the current state BEFORE the apply runs.

---

## Scope Delta — 2026-07-31

Plan authored 2026-07-31. No prior scope to amend; this is the first cut. If the cron run surfaces unexpected friction (e.g., TwitterAPI returns all-200 with empty data for the lonely set, or fuchitalee's TIME_WAIT behaves differently than the v6 evidence suggests), the plan body will be amended in-place per global CLAUDE.md rule 5 — operator decision logged here with the narrower scope.

