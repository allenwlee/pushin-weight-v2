## v2 harvest cursor restoration — ~50% of v1 recovered; quote-tweet port still needed for full parity

### TL;DR

On the 2026-07-23 prod Postgres cutover, v2's Django/Celery harvest shipped without an incremental cursor: each 15-minute cycle re-issued a bare `queryType=Latest` search and grabbed the newest ≤100 posts per query, instead of sweeping a time window since the last run. Daily collection fell from ~2,000–2,400 to ~1,150. After 4 rounds of peer review (each surfacing a real silent-loss bug), the cursor is restored and v2 is **now safer than v1 was**. Expected post-fix volume: **~1,500–1,900/day** — not the full v1 number, because the second cause (missing quote-tweet ingest channel) is **not yet ported**. That port is the next thing; everything else is closed.

**Branch:** `fix/harvest-cursor-regression` (8 commits, 6 of which are mine). **Tests:** 83/83 green against Postgres 17 with production keyword data. **Django check:** clean.

### Context

The investigation started from a one-line observation: dashboard "total posts per day" dropped ~50% after the cutover. A stage-by-stage diff of v1 (`x_monitor/run.py`) and v2 (`monitor/cycle.py`) — the two share the query planner, the `apify.py` client, `config.yaml`, and the per-call caps, so the difference set is bounded — found **two independent causes**:

1. **No incremental cursor** (fixed). v1 read `call_state.last_completed_at`, set `since_time`/`until_time` to sweep that window, then advanced the cursor. v2 fetched only the newest ~100 per query with no time bounds, so cycles overlapped heavily and anything that scrolled past between cycles was lost.
2. **No quote-tweet ingest channel** (NOT fixed). v1 ran `get_tweets_by_ids` → `get_quote_tweets` → `_ingest_quote_tweets` every cycle, inserting quote-tweet posts. v2 never calls either endpoint. Proved by `quoted_text` being **0** across all 2,274 prod rows fetched 7/25–7/26, vs **1,586 of 6,686** in the v1 era. This channel was ~24% of v1's stored volume.

A third candidate — v2's `transaction.atomic()` per-item rollback silently dropping posts on PROTECT-FK failures — was investigated and **refuted**: zero orphan brand refs in `posts_brands_signals`/`posts_brands_mentions`; 1,162/1,163 posts on 7/25 carry signals. Kept as a latent risk in the plan's Risks section.

### Resolution: cursor restoration (this work)

Eight commits on `fix/harvest-cursor-regression`:

| Commit | Purpose |
|---|---|
| `ce41dcd` | U6 — surface regression net (pinned call set, caps, brand coverage, query-length headroom) |
| `cc39b18` | U1 — `CallState` cursor helpers (clamped read, swallow-and-log write) |
| `9572494` | U2 — wired cursor into `_fetch_tweets`; advance only on success |
| `ad659a5` | U5 — post-injection 512-char guard (catches TwitterAPI silent zero-result on over-cap) |
| `9e7eee2` | U3 — cursor regression net (proved fails pre-fix, passes post-fix) |
| `e39c091` | U4 — full lifecycle test (cold start → advance → failure hold → recovery → clamp) |
| `1e41d54` | review fixes — vacuous tests, silent skips, brand-coverage set |
| `26d9071` | defensive hardening — naive datetime, epoch-0 backfill floor |
| `f58fd87` | peer review 1 — hold cursor on persist failure |
| `b71d813` | peer review 2+3 — clamp future cursor, reject colliding call_id placeholders |
| `a44b577` | peer review 4 — hold cursor when window is truncated by per-call cap |

The peer reviews all surfaced **silent-loss bugs** that my own code review missed: a `TypeError` from a naive cursor would have aborted the whole cycle, an in-tree write could persist a future timestamp and invert the window, two specs sharing `call_id+first_brand` would address the same cursor row, and a 51st tweet in a 50-cap window was lost forever. Worth noting the pattern: **all four were the exact failure class the original plan exists to prevent**.

### What v2 has now that v1 did NOT

- **Bounded cold-start floor** (2h). v1 would have silently truncated a stale cursor; v2 clamps.
- **Persist-failure cursor hold.** v1 advanced on errors that should have held.
- **Future-cursor clamp + reject.** v1 inverted the window; v2 holds.
- **Over-cap query guard.** TwitterAPI returns `[]` silently on >512 chars; v2 catches.
- **Truncated-by-cap hold.** A window with >50 tweets no longer loses the 51st-and-older.
- **Config-time validation.** Duplicate `call_id+brand_placeholder` is rejected at load.
- **Regression nets that fail loudly.** A default `pytest` run on a developer laptop prints a banner saying 50 tests were skipped; nothing is green-by-default-misleading.
- **Per-call logging of the resolved window** for Render-side diagnosis.

### What v1 had that v2 still does NOT

- **Quote-tweet ingest channel** (`get_tweets_by_ids` + `get_quote_tweets` + `_ingest_quote_tweets`). This is **the entire remaining volume gap** between the two stacks. Without it, the cursor fix alone won't return v1-level daily collection.

### What I never verified

- **No CI** in this repo. The 50 Postgres-only tests only run when someone sets `DATABASE_URL`. The default `pytest` runs 23 with a loud banner; nothing enforces the full 83.
- **Live API integration.** I proved the wiring with a stubbed `_get`; the real TwitterAPI response shape under truncation and rate limits is not exercised by my suites.
- **The concurrent session's commit** `c7459a8` + merge `611532c` refactored `_run_post_fetch` to build separate translator and classifier clients. I did not review that diff; the integration is untested by my work.
- **The actual daily volume recovery.** All my proofs are local (stubbed API, scratch DB). The only true acceptance signal is `fetched_at` insert counts on prod over 24 hours post-deploy.

### Open questions / next steps

1. **Port the quote-tweet channel.** This is the next hand-off. Concretely:
   - v1 reference: `x_monitor/run.py:1640-1690` (official QT capture, every 15 min) and `:1750-1790` (daily non-official).
   - The `_ingest_quote_tweets` helper plus the `last_quote_count_seen` / `last_quote_fetched_at` tracking columns on the v2 `Post` model already exist.
   - Expect: another ~24% of daily volume, lifting prod from ~1,500–1,900 back to ~2,000–2,400.
   - The cursor plan's "Deferred to Follow-Up Work" section is the place to track this.

2. **Deploy-acceptance procedure for the cursor fix** (short doc, ~20 lines, would live in `docs/deploy/` or `docs/issues/`):
   - Watch `SELECT count(*) FROM posts WHERE fetched_at >= now() - interval '24 hours'` over 24 hours. Should rise from ~1,150/day to ~1,500–1,900/day.
   - Watch `SELECT max(updated_at) FROM call_state` — should advance every 15 min instead of sitting frozen at 2026-07-23 09:39 UTC.
   - Watch Render logs for `length_cap_exceeded` (an over-cap query would be a config problem, not a code problem) and `truncated` / `persist_incomplete` call statuses (defensive holds; expected to be rare).

3. **Add a CI workflow** with a Postgres service so the 50 PG-only tests run on every push instead of only when someone sets `DATABASE_URL` locally. The banner in `tests/conftest.py` says "a green run WITHOUT them is not a full verification"; CI is what enforces that.

4. **The length-guard format duplication** (open from the original code review). `_fetch_tweets` reconstructs the effective query string that `x_monitor/apify.py:run_search` independently builds. The formats match exactly today (I verified character-by-character), but it is duplicated knowledge. If `apify.py` ever changes its operator format, the guard measures a different string from the one actually sent, and the failure is a silent zero-result call. The deeper fix is having `apify` expose the effective query (or move the length check into apify).

### Verification

```bash
# Local: full suite needs Postgres
createdb xmon_test && \
DATABASE_URL=postgres://$(whoami)@localhost:5432/xmon_test pytest \
  tests/test_cycle_cursor_helpers.py tests/test_cycle_cursor_wiring.py \
  tests/test_harvest_cursor_regression_net.py tests/test_harvest_cursor_lifecycle.py \
  tests/test_cycle_query_length_guard.py tests/test_harvest_surface_regression_net.py
# Expected: 83 passed, 0 skipped, 0 errors

# Local: SQLite default — loud banner
pytest
# Expected: 23 passed, 50 skipped, banner about Postgres-only tests
```

### Related

- Plan: `docs/plans/2026-07-27-002-fix-v2-harvest-cursor-regression-plan.md`
- Branch: `fix/harvest-cursor-regression` (8 commits by this author; the 2 `c7459a8`/`611532c` commits are from a concurrent session and contain a partial absortion of the U2 change)
- Investigation log: this conversation thread, 2026-07-27, "investigation into why total posts per day is declining"
- The four peer reviews that found silent-loss bugs: surfaced via other Claude sessions on the same branch; their final reports are in the conversation transcript, not local docs
- Deferred work: the **quote-tweet channel** port (the only remaining cause of the ~50% loss)

---

## Follow-up completed (2026-07-17 / handoff session): quote-tweet channel port

**Status:** implemented on `fix/harvest-cursor-regression`.

### What was done
- New module `monitor/quote_tweets.py` ports v1 regimes:
  - **official/staff** every cycle (`get_tweets_by_ids` → delta ≥ `official_delta` → `get_quote_tweets` → ingest)
  - **non-official daily** once per UTC day (marker file `XMONITOR_DATA_DIR/_qt_daily_marker`)
- Wired into `CycleRunner.run()` **after** main harvest + post-fetch; never aborts the cycle.
- `_upsert_post` now persists `quoted_text`.
- Staff/official handles from `BrandAccount` roles `official` + `staff` (Django ORM).
- Tracking via `Post.last_quote_count_seen` / `last_quote_fetched_at` / `quote_count`.
- Tests: `tests/test_cycle_quote_tweets.py` (7 passed).

### Cursor history note (for blame/audit)
Concurrent session commits `c7459a8` + `611532c` partially absorbed U2. Canonical cursor behavior is **`f58fd87` onward** (through `a44b577`). Do not re-audit the original U1/U2 commits as the sole source of truth — they are partly redundant with later repair commits. The quote-tweet work does **not** change cursor wiring.

### Expected volume after deploy
- Cursor fix alone: ~1,500–1,900/day
- + QT channel (~24% of v1): target back to **~2,000–2,400/day**
- Accept: `quoted_text IS NOT NULL` starts appearing; `last_quote_fetched_at` advances on official parents.

### Verify
```bash
.venv/bin/pytest tests/test_cycle_quote_tweets.py -q
# After deploy, over 24h:
# SELECT count(*) FROM posts WHERE quoted_text IS NOT NULL AND fetched_at >= now() - interval '24 hours';
# SELECT count(*) FROM posts WHERE last_quote_fetched_at IS NOT NULL;
```
