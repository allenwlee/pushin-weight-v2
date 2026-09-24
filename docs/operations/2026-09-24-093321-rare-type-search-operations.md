# Rare-type search operations

This runbook covers the optional `RARE_EXTRA` TwitterAPI search, its Jev gate,
saved-hit replay, and query-version changes. The lane is disabled in checked-in
configuration and this document does not authorize a live call, production
activation, cron pause, deployment, or budget increase.

## Read the current state

Inspect a durable run or post without calling any provider:

```bash
python manage.py rare_type_search_status --run-id 123 --json
python manage.py rare_type_search_status --post-id 1900000000000000000 --json
python -m scripts.harvest_cost --latest --format json
```

Keep these denominators separate:

- `n_provider_attempts` is the number of physical `RARE_EXTRA` requests.
- `n_raw_paid_results` is the provider-returned billing denominator before
  normalization, filtering, or deduplication.
- `n_normalized_hits` is the durable hit input after normalization.
- kept/junk/pending hits describe Jev outcomes.
- persisted/classified/extracted/visible posts describe later lifecycle stages.
- canonical records and evidence attachments are separate; several posts may
  support one canonical record.
- confirmed Twitter credits override estimates. If confirmation is absent, the
  cost tool uses estimated credits; ambiguous provider usage retains and prices
  the full reservation.
- Jev dollars are reported separately from TwitterAPI credits. The
  `jev_slot_*` fields belong to the shared 15-minute processing slot: they may
  include old saved hits or another worker using the same bounded allocation.
  Jev outcome counts for the current source hits remain separate.

Counts-only harvest summaries exclude query text, post text, credentials, and
provider bodies. Use the status command for source-linked inspection under the
existing operator access controls.

## Feature off

The normal rollback is configuration-only: keep
`discovery.rare_types.enabled: false`. A disabled cycle must retain exactly the
seven existing calls (`A`, `B1`, `C1`, `C2`, `C3`, `B2`, `B3`) and make no
`RARE_EXTRA` or Jev requests. Disabling the lane does not delete already-paid
hits, decisions, posts, records, evidence, or review proposals.

After an authorized configuration change, check the plan locally without a
provider call:

```bash
python manage.py run_cycle --dry-run
```

Do not pause or resume the production harvest cron unless the owner explicitly
authorizes that exact service-state change. Follow
`docs/operations/pause-and-resume-harvest-cron.md` if authorization is given.

## Replay saved work

Preview explicit saved hit IDs first. Preview performs no writes and constructs
no provider client:

```bash
python manage.py replay_rare_type_hits 41 42 --json
```

A committed replay is local downstream work. It never performs another X
search or drains Hugging Face verification, accepts at most 20 explicit IDs,
and requires an explicit shared translation/classification transport cap:

```bash
RARE_TYPE_REPLAY_ENABLED=1 python manage.py replay_rare_type_hits \
  41 42 --commit --max-llm-calls 6 --json
```

Jev decisions and targeted extraction retain their own configured budgets.
Use the status command afterward to verify the selected hits advanced and
unrelated pending work did not change.

## Search-credit or Jev-cap exhaustion

Do not raise a cap automatically.

1. Inspect the run. A search status of `daily_budget_exhausted` means no X
   request was dispatched. `usage_unknown` means a request may have been billed
   and its full reservation remains charged.
2. Check `n_pending_hits_global` and the gate-state counts. Jev cap or deadline
   exhaustion leaves saved hits pending; it does not convert them to junk.
3. Check the cost report's basis (`confirmed`, `estimated`, or
   `reserved_usage_unknown`) before calculating remaining budget.
4. Retry only saved explicit IDs with the guarded replay command. Do not repeat
   the paid search slot.
5. Escalate a requested cap change to the owner with current raw paid volume,
   confirmed/estimated cost, pending count, and coverage-gap evidence.

## Query-version rollout

The rendered query, query version, hash, quality assessment, and configured
assessment digest are one release identity. Change them together.

1. Create the reviewed query version within the 512-character rendered limit.
2. Regenerate provider-free query fixtures and the quality assessment. Do not
   edit an old assessment to impersonate the new identity.
3. Verify the new assessment's query hash, Jev model, question hash, threshold
   hash, and digest match configuration.
4. Run the feature-off and failure regression suites. Verify the old summary
   schema versions still parse and the cost tool prices `RARE_EXTRA` once.
5. Use an owner-authorized, bounded on-demand staging acceptance call only
   after the provider-free checks pass. One query version uses one page, zero
   search retries, and one physical attempt per 15-minute slot.
6. Inspect raw paid results, normalized hits, gaps, pending work, costs, and
   end-to-end record evidence separately. A truncated page or failed persistence
   is a visible coverage gap, not a successful complete window.
7. Roll back by disabling the lane. Never reuse a successful old assessment for
   a different query or silently fall back to another Jev model.

## Failure interpretation

- Reservation failure: zero provider calls; no spend was authorized.
- Failure after dispatch: usage may be unknown; retain the reservation and do
  not repeat that slot automatically.
- Hit-persistence failure: record the coverage gap and replay only after the
  saved durable evidence is available; a response lost before persistence
  cannot be called complete.
- Jev outage: saved hits remain pending and unpublished.
- Classification or extraction failure: the linked post remains locally
  replayable; no second search is needed.
- Hugging Face timeout/throttle/private/missing: normal post persistence and
  classification finish first; verification stays bounded and reviewable.
