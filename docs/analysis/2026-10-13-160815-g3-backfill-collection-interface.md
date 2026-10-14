---
title: G3 and X backfill persistence boundary
date: 2026-10-13
source_revision: db5510ccc94ea326dd5f81e833a9c791e5e84d99
---

# G3 and X Backfill Persistence Boundary

The staging pilot can proceed with atomic JSON checkpoints on the authoritative fuchitalee host.
It does not wait for G3's new table or database API.
This settles the interim route. U1 now implements the shared interface locally on `feat/g3-collection-jobs-history`; migration `0081_collection_jobs` and the API have not been deployed. The X runtime adapter remains separately owned and unimplemented here.

The authoritative G3 subplan is [Shared Collection Jobs and Model History](../plans/2026-10-13-062212-feat-g3-collection-jobs-history-plan.md), particularly R3 and U1.
The peer plan is `docs/plans/2026-10-12-105615-docs-august-harvest-audit-20261012-plan.md` on branch `docs/august-harvest-audit-20261012`.

| Responsibility | Owner | Current boundary |
| --- | --- | --- |
| X pilot and staging run | Backfill session | Existing owner authorization there governs scope, duration and provider budget |
| JSON checkpoint implementation | Backfill session | Frozen campaign identity; committed progress only; atomic replacement retains the prior valid file on failure |
| Shared table, migration and lifecycle | G3 | Exactly one new permanent `collection_jobs` table; extend existing run/scope tables |
| Shared claim/checkpoint/finish API | G3 | Implement and verify U1 before the database adapter begins |
| X database adapter and tests | Backfill session | Integrate against G3's implemented contract after handover |
| X runtime files | Backfill session | `backfill.py`, `cycle.py`, `run_lock.py`, `x_monitor/apify.py` and focused tests remain its file scope |

The locally implemented database mapping is:

- `CollectionJob`: frozen manual instructions, time window, selected calls, query/policy hash and limits. A manually invoked pilot creates no recurring schedule.
- `CollectionRun`: one content-purpose invocation attempt, actual request/usage counters, outcome and lease token. Terminal partial means the attempt ended with campaign work remaining.
- `CollectionScopeRun`: call/time-slice progress committed under the active lease. A new content attempt copies prior committed scopes and records its continuation source; old attempts remain unchanged.
- Existing `Post` and related tables: fetched tweets and enrichment. No per-tweet duplicate observation ledger.
- Existing live cursor/backlog tables: retain their present ownership and meaning; historical completion never advances a scheduled live cursor.

G3's handover includes actual field names, content-purpose constraints, instruction hash validation, claim and stale-writer rejection, checkpoint transaction rules, completion counters and cross-attempt continuation examples.
The adapter must distinguish collection completeness from enrichment degradation.
It must use the on-demand TwitterAPI credential purpose for explicitly launched backfills.

A later JSON import preserves the campaign's frozen identity and records the checkpoint's provenance.
Missing old attempt timestamps remain unknown; file modification time is not a source-event date or an invented database run receipt.
Do not add a standalone backfill table or use catalog-purpose records to evade the content lifecycle.

The database adapter remains dependent on U1; the JSON staging pilot has no such dependency.

## Implemented U1 Interface

Import instruction operations from `core.collection_jobs` and execution operations from `core.collection_state`.
`register_job(job_key=..., source=..., purpose="content", operation="x_backfill", mode="historical", definition=...)` creates a paused instruction or returns the identical existing instruction. A changed instruction requires a new job key.
The version-one definition includes a frozen `scope`, `schedule={"kind":"manual","driver":"manual"}`, and positive `budgets` for `requests`, `bytes`, `seconds`, and `items`. Store only the credential-purpose name; never store credentials.

- `set_job_state(job_id, "ready"|"paused"|"cancelled"|"completed")` coordinates activation. Pausing clears execution pointers and fences the previous worker. Metric/catalog readiness requires an enabled source; explicitly authorized content callers are independent of that unrelated metric-source flag.
- `claim_job(job_id, invocation_id=..., manual_authorized=True, continue_from=...)` returns an immutable `RunClaim(job_id, run_id, lease_token)`. The flag declares the content caller's existing authorization; it grants none. Claims and cooldown checks lock the job briefly, with network calls outside the transaction.
- `checkpoint_scope(claim, scope_key=..., ownership=..., cursor=..., outcome=..., write=...)` commits the database-only evidence callback and scope update in one fenced transaction. The callback receives `(run, scope)`; it must not make provider requests. Ownership pins cannot change on resume.
- `fenced_run(claim)` provides the same checked transaction around an existing database writer. `BusyJob` signals an active claim/cooldown; `StaleClaim` rejects a replaced, expired or paused worker.
- `finish_run(claim, status=..., report=..., request_count=..., selected_count=..., success_count=..., retry_at=..., next_due_at=...)` records completion/yield and job pointers. Catalog partial remains resumable on its logical run; content partial completes its invocation. Report fields separate collection completeness, enrichment and unknown provider billing.
- `record_rejection(job_id, invocation_id=..., reason=..., report=...)` creates an idempotent terminal content receipt without an execution lease or changes to active/attempt/success pointers.
- `import_scope_checkpoints(claim, definition_sha256=..., scopes=..., provenance=...)` admits the adapter's decoded pilot progress into the current historical content attempt. It validates frozen instruction identity and retains import provenance and unknown old attempt timestamps; it creates no historical receipts.

`continue_from` is allowed only for the same historical content job and its preceding completed attempt. It copies all committed scope rows, including completed scopes, while preserving old attempts. New manual/scheduled invocations start with fresh scopes. Scheduled X jobs use `operation="x_cycle"`, recurring mode and `driver="external_render_cron"`; shared dispatch excludes that driver. The local U6 test executes a content claim with the metric-source flag disabled, while an unauthorized caller is still rejected before a claim.

Local U1 evidence: six existing PostgreSQL storage tests passed before implementation; the new tests initially failed on missing API imports. The combined suite now executes nineteen required PostgreSQL tests, including two independent connections racing to claim, old-token rejection, evidence/cursor rollback, content continuation and pilot-import provenance. This is local API evidence, not proof of the U9 scheduled command/runner adapter or deployed behavior.

The owner's subsequent plan amendment includes ordinary scheduled harvest invocations in the later adapter scope (G3 U9).
Record scheduled/manual/backfill attempts in the same content-run ledger through the common command/runner path, with fresh scopes for each scheduled cycle and campaign checkpoint copying only within the same resumed backfill.
The existing Render cron remains the only 15-minute launcher; externally scheduled X jobs cannot also dispatch through the shared due-checker.
Persist rejected-attempt receipts without replacing an active claim, and keep true query bounds, unknown provider billing and enrichment degradation explicit.
After adapter adoption, shared database reports become the source for cost/health reads; logs/JSON are compatibility exports.
This future integration does not interrupt or expand the already authorized JSON pilot and does not transfer ownership of the X runtime files to G3.
