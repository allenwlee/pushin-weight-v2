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