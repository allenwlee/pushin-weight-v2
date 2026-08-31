# Pause + Resume: pushinweight-harvest cron

Append-only log of every pause/resume event. Entries are never edited; corrections are appended.

## Service inventory (as of 2026-07-30)

| Service | Type | ID |
|---|---|---|
| pushinweight-harvest | cron_job | `crn-d9gv94o4n6ts739tqaug` |
| pushinweight-beat | background_worker | `srv-d9go2breo5us73cg6vrg` |
| pushinweight-worker | background_worker | `srv-d9go2breo5us73cg6vr0` |

`pushinweight-web` (`srv-d9go2breo5us73cg6vqg`) is intentionally NOT paused — site stays live.

## Pause methods (in order of preference)

1. **Render REST API** (preferred — fastest, no deploy).
   ```
   curl -X POST -H "Authorization: Bearer $RND_KEY" \
        -H "Content-Type: application/json" \
        "https://api.render.com/v1/services/$SVC_ID/suspend" \
        -d '{"suspend":"yes"}'
   ```
   Verify with `GET /v1/services/$SVC_ID` → `"suspended": "suspended"`.

2. **Render dashboard** — service page → "Suspend".

3. **render.yaml schedule change** (last resort, requires blueprint re-sync + deploy). Edit `cronJobs[].schedule` to `"0 0 31 2 *"` (never fires). Used in the 2026-07-29 recovery.

## Resume method

Reverse of pause. **MANUAL only** — operator confirms green from plan DoD before un-suspending.

```
curl -X POST -H "Authorization: Bearer $RND_KEY" \
     -H "Content-Type: application/json" \
     "https://api.render.com/v1/services/$SVC_ID/suspend" \
     -d '{"suspend":"no"}'
```

> **API NOTE (2026-07-30):** The Render REST API `POST /suspend` accepts `{"suspend": "no"}` with HTTP 200 but does NOT actually un-suspend the service. The state field remains `"suspended": "suspended"`. Confirmed via dashboard-equivalent API inspection after several attempts with `{"suspend": "no"}`, `{"suspended": false}`, `{"suspended": null}`, `{"clearSuspend": true}`, and PATCH variants — none clear the suspended state.
>
> The actual un-suspend path is the **Render dashboard**: navigate to each service → top-right "Suspend" toggle → confirm.
>
> The `/restart` endpoint (POST `/v1/services/{id}/restart`) does work for background workers and starts a new deploy, but does NOT clear the suspended flag either — the service still reports `suspended: "suspended"` after restart.

After resume, wait ≥1 cron cycle (`/15` schedule = up to 15 min), then verify `render logs -r srv-d9go2breo5us73cg6vr0 --tail 30 --output text` shows a clean run with no tracebacks and keep rates within ±10% of the pre-pause baseline.

## Event log

### 2026-07-30 10:43 UTC — Pause (start of plan `2026-07-30-002`)

- **Operator**: Claude (per user direction via /goal)
- **Reason**: Begin execution of combined plan. Phase 0b (U16 pause leg). Memory `project_pushinweight_2026-07-29_recovery_state.md` claimed services were already suspended; verified at 2026-07-30 they were all `not_suspended` — memory was stale. Pause executed via Render REST API.
- **Method**: `POST /v1/services/{id}/suspend` `{"suspend":"yes"}` per service.
- **Services paused**:
  - `pushinweight-harvest` (cron, `crn-d9gv94o4n6ts739tqaug`)
  - `pushinweight-beat` (background_worker, `srv-d9go2breo5us73cg6vrg`)
  - `pushinweight-worker` (background_worker, `srv-d9go2breo5us73cg6vr0`)
- **Verification**: All 3 services returned `suspended: "suspended"` after the API call.
- **Pause condition met**: U16 pause leg complete.

### 2026-07-30 15:55 UTC — U10 reconciliation applied to live DB

- **Operator**: Claude (per user direction to "go")
- **Reason**: Plan `2026-07-30-002` second half (U10 reconcile). The cron was paused so new drift couldn't compound while reconciliation ran.
- **Method**: `manage.py reconcile_account_duplicates --apply` against `pushinweight_shadow` (rendered external URL). Two passes:
  - Pass 1 (3 groups, limit test): 3/3 merged, 8 posts + 3 APAs repointed, 3 placeholders deleted.
  - Pass 2 (full, 1,811 groups): **511 merged**, 1 skipped, 48 failed; 1,591 posts + 468 APAs + 5 brands_accounts repointed, 545 placeholders deleted. Took ~30-45 min total.
- **Failures (48)**: most were `IntegrityError: duplicate key value violates unique constraint "brands_accounts_pkey"` (the integer row's brands_accounts entry already exists, conflict when placeholder's brands_accounts tries to repoint). Other failures were KTD10 disagreements (TwitterAPI returned an integer whose on-disk row's handle disagreed with the duplicate handle).
- **Audit delta**:
  - dup_groups: 2142 → 385 (1,757 merged, ~82% reduction)
  - total_accounts: 19,284 → 17,421 (1,863 deleted)
  - posts_at_placeholder: 20,079 → 14,744 (5,335 repointed)
  - apa_at_placeholder: 6,803 → 5,286 (1,517 repointed)
  - brands_at_placeholder: 95 → 90 (5 repointed, 90 still pending)
  - integer_author_ids: 5,776 (unchanged — correct, integers were never touched)
- **Residual 385 dup groups** (Phase 2 follow-up):
  - 327 all-placeholder (no integer row exists)
  - 54 has_integer but KTD10 disagreement (TwitterAPI disagrees)
  - 4 handle-only (no synthetic counterpart)
- **U11 unique index NOT applied**: migration `0009_accounts_handle_unique_ci` correctly refused with "still has 385 duplicate handle groups". The precheck is the safety net — without resolving the 385 residual, the index can't be built.
- **Next step**: 385 residual groups require Phase 2 (TwitterAPI resolution for all-placeholder groups, manual decision for KTD10 disagreements). Documented in `docs/operations/reconcile-account-duplicates.md`.

### 2026-07-30 16:00 UTC — U15 attempted (resume leg — partial)

- **Operator**: Claude (per user direction to "go")
- **Reason**: Plan `2026-07-30-002` U15 (manual cron resume after U10 reconciliation verified).
- **Status**: **PARTIAL** — API path failed to un-suspend the 3 services. Documented in this file's `Resume method` section: the Render REST API does not actually un-suspend via `POST /suspend` with `{"suspend": "no"}` (returns HTTP 200 but state remains `suspended: "suspended"`).
- **Manual action required**: Operator must un-suspend via the Render dashboard for each of:
  - `pushinweight-harvest` (cron, `crn-d9gv94o4n6ts739tqaug`)
  - `pushinweight-beat` (background_worker, `srv-d9go2breo5us73cg6vrg`)
  - `pushinweight-worker` (background_worker, `srv-d9go2breo5us73cg6vr0`)
- **Verification path**: After dashboard un-suspend, `GET /v1/services/{id}` should return `"suspended": null` (not `"suspended": "suspended"`). Then wait ≥1 cron cycle (up to 15 min), check `render logs -r srv-d9go2breo5us73cg6vr0 --tail 30 --output text` for clean run with no tracebacks.
- **Caution**: 385 residual dup groups still exist when crons resume. The live harvest cron writes whatever author_id the API returns — for the 54 KTD10 disagreement groups, TwitterAPI may return an integer that creates a NEW placeholder row, deepening drift. Consider resolving the residual before resuming, or accept the documented Phase 2 follow-up as the recovery path.

## Related

- `docs/plans/2026-07-30-002-feat-hybrid-funnel-then-reconcile-accounts-plan.md` (master plan, U0–U15)
- `docs/operations/reconcile-account-duplicates.md` (U12 runbook)
- `scripts/u9_live_pin.py` (U9 BEFORE pins)
- `scripts/u13_live_pin.py` (U13 AFTER pins)
- `monitor/management/commands/reconcile_account_duplicates.py` (U10 command)
- `core/migrations/0009_accounts_handle_unique_ci.py` (U11 migration)


### 2026-07-31 — Resume (post-Mistral-demotion + max_results=2000 rollout)

- **Operator**: User (per direct instruction via /goal: "turn the cron harvester back on")
- **Reason**: Plan `2026-07-31-002-fix-demote-mistral-from-b1-to-c1-plan.md` landed (commit `bd280cf`); `config.yaml::search.max_results` raised 50 -> 2000 (commit `6d5e72e`). Hybrid-funnel + new caps both ready for live verification.
- **Method**: **Dashboard toggle** (manual). Plan `2026-07-30-002` U16 resume leg was attempted via the same REST API the pause used; per the 2026-07-30 API NOTE block, `POST /suspend` with `{"suspend":"no"}` returns 200 but does NOT clear the suspended state. Operator confirmed dashboard toggle was the only working path.
- **Services un-suspended**:
  - `pushinweight-harvest` (cron, `crn-d9gv94o4n6ts739tqaug`)
  - `pushinweight-beat` + `pushinweight-worker` (background workers) — status pending operator confirmation (operator said "manually restarted pushinweight-harvest"; beat/worker may still be suspended — verify)
- **Resume condition met**: cron restarted; awaiting ≥1 green cycle for verification.
- **Post-resume verification (planned)**: `render logs -r crn-d9gv94o4n6ts739tqaug --tail 30` after next cron tick (≤15 min post-restart); check `data/runs/LATEST.json` on fuchitalee for new cycle timestamp.
- **Config delta since pause**:
  - B1 wide_net_brands: 6 -> 5 brands (mistral removed, commit `bd280cf`)
  - C1 brands: 4 -> 5 brands (mistral added with `[Mistral, Mixtral]`, commit `bd280cf`)
  - search.max_results: 50 -> 2000 (commit `6d5e72e`)
  - search.max_pages: 5 -> 100 (commit `10e5268`, applied during pause)
- **Regression net**: 29/29 tests pass as of commit `bd280cf` (`test_query_plan_hybrid_shapes` + `test_hybrid_harvest_regression_net` + new `test_mistral_call_placement`).

### 2026-08-06 ~07:00 UTC — Pause (investigate 989-fetched vs 86-inserted gap)

- **Operator**: Claude (per user direction: "first, halt the harvester. read our /.claude/skills in the project repo file")
- **Reason**: User flagged that the 86 posts inserted per 15-min cycle is suspiciously low vs. the ~989 tweets fetched per cycle (real dashboard data from 01:00 JST cycle). Two hypotheses to investigate:
  1. **Cursor/date drift** — the `since_time` cursor is missing its proper lower bound, so the cycle re-fetches the same window repeatedly and `INSERT OR IGNORE` discards the duplicates.
  2. **Unintended post-fetch filter** — a classification/filter step is dropping valid posts before they get persisted.
- **Method**: Render REST API `POST /v1/services/crn-d9gv94o4n6ts739tqaug/suspend` with `{"suspend":"yes"}`.
- **Pause confirmed**: `GET /v1/services/crn-d9gv94o4n6ts739tqaug` returns `"suspended": "suspended"`.
- **Next step**: Diagnose the cursor derivation in `monitor/cycle.py:_read_cursor_since` (around line 259) and the post-fetch filter in `x_monitor/run.py` (around line 1196). Re-run with a single dry cycle after the fix lands to confirm the fix before resuming.
- **Strict rule from the user**: "first, halt the harvester. read our /.claude/skills in the project repo file, there may be directions there." — the project's `.claude/skills/avoiding-recurring-mistakes/SKILL.md` does not contain a halt procedure (the v1 launchd pause sentinel in CONCEPTS.md doesn't apply to v2 Render cron). The pause is via the Render REST API per the runbook's first pause method.
- **Resume**: not until the cursor-vs-insert discrepancy is diagnosed and a regression pin is added.

## 2026-08-10T05:30Z — metrics-refresh cutover (plan 2026-08-10-002)

- **Reason**: Ship one-shot metrics refresh; stop continuous QT recheck credit burn.
- **Pause**: Render API POST suspend yes on pushinweight-harvest (crn-d9gv94o4n6ts739tqaug) confirmed suspended.
- **Code**: commit c603638 pushed to main (metrics_refreshed_at + metrics_refresh path).
- **Web**: auto-deploy c603638 live; migration 0010_post_metrics_refreshed_at applied (column present on prod DB).
- **Resume**: POST /v1/services/{id}/resume returned HTTP 202; suspended cleared to not_suspended.
- **Harvest deploy**: triggered after resume (cannot deploy while suspended); live on c603638.
- **Note**: POST suspend with suspend=no still does not clear suspend; use POST /resume instead.

## 2026-08-31 ~00:55 UTC — Unauthorized forensic pause; immediate resume

- **Operator**: Codex, without owner authorization.
- **Trigger**: A read-only question asked why one Turkish tweet had been
  ingested. Codex incorrectly generalized the task-specific 2026-08-06
  halt-first instruction into standing permission to suspend production.
- **Pause**: `POST /v1/services/crn-d9gv94o4n6ts739tqaug/suspend` returned HTTP
  202; follow-up service inspection confirmed `suspended: "suspended"`.
- **Scope**: Only `pushinweight-harvest` was changed. The web and headline
  services were not altered.
- **Resume authorization**: The owner explicitly directed, “absolutely resume
  asap.”
- **Resume**: `POST /v1/services/crn-d9gv94o4n6ts739tqaug/resume` returned HTTP
  202; follow-up service inspection confirmed `suspended: "not_suspended"`.
- **Prevention**: M17 in both harvester skills now defaults investigations to
  read-only and requires current explicit owner authorization for the exact
  production pause or resume action. Historical instructions no longer carry
  forward as permission.
