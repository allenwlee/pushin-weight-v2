---
title: "Promote reviewed backfill measurements into production by replaying captures, not copying rows"
date: "2026-11-05"
category: data-migration
module: backfiller-data-source
problem_type: architecture_pattern
component: database
severity: high
applies_when:
  - "Promoting reviewed measurements from the separate backfill PostgreSQL database (xbackfiller) into production"
  - "Turning a one-off Backfill transfer into an unattended background step after the Backfiller data source"
  - "Moving collection contracts, captures or metric values between databases whose integer IDs, Product keys and taxonomy UUIDs differ"
  - "Writing reviewed historical values to production while the scheduled harvest keeps running"
  - "Reconciling transferred values against measurements production already holds for the same source, metric and day"
symptoms:
  - "Reviewed 0813 measurements existed only in the separate backfill database, so production readers could not use them"
  - "Backfill and production assign different integer IDs, Product BigAutoField keys and taxonomy UUIDs, so a copied contract_hash can never match"
  - "Production joins through collection_observations mapping_id or product_id found 0 rows while exact source-identifier queries found 104 unmapped values"
resolution_type: tooling_addition
related_components:
  - service_object
  - background_job
tags:
  - backfiller
  - backfiller-data-source
  - production-transfer
  - collection-contract
  - idempotent-replay
  - provenance
  - reconciliation
  - benchmark-metrics
---

# Promote reviewed backfill measurements into production by replaying captures, not copying rows

## Context

> **Which backfill this is.** This learning covers the **Backfiller data
> source** (`python manage.py backfiller_data_source`), which collects numeric
> provider measurements such as Hugging Face downloads, Arena ratings and
> OpenRouter tokens into the separate `xbackfiller` database. It also covers the
> **Backfill transfer** (`python manage.py transfer_backfill_contract`) that
> promotes those reviewed measurements into production. It is **not** the
> **X post backfill** (`python manage.py backfill` / `run_backfill`), which
> recovers past X posts through the harvest's `CycleRunner`; see the X post
> backfill learnings under Related. `CONCEPTS.md` defines all three terms.

The Backfiller data source collects historical measurements into a separate PostgreSQL database (Render `dpg-dbfemu2vcj2c73fsafe0-a`, database and login `xbackfiller`). That keeps experimental collection away from production. Reviewed results still have to reach production (`dpg-d9koekqjobas73fvjqng-a`, database `pushinweight_shadow`) with their provenance intact. The move must not duplicate or invent values, and live harvesting must keep running throughout.

The first cohort to make this trip was DeepSeek-V4-Pro-0813: 216 reviewed values from 45 source captures between Aug 13 and Sep 10, 2026. They cover Hugging Face downloads, all-time downloads, likes and trending score; Arena rating, rank, bounds, variance and votes; and OpenRouter tokens. PR #81 added the transfer path:

- `core/data_source_backfill_transfer.py`: export, validation, reconciliation, and replay with verification.
- `core/management/commands/transfer_backfill_contract.py`: the operator command.
- `cohort_collection_spec(...)`, extracted in `core/data_source_backfill_cohort.py:125-157`, so the backfill setup and the production transfer build the same reviewed contract input.

On 2026-11-05 JST, production contract `28f61a49-76e9-47dd-8ac4-502ee02f772e` was committed. It holds the 216 values under product `20d66250-db05-40bf-8fda-94b610bed0c7`, with 0 verification problems and 0 provider calls.

This document records the reasoning that the code doesn't spell out. Whoever turns this one-off transfer into an unattended background step for the Backfiller data source (collect in the backfill DB, then promote) needs to know which properties keep the step safe and which decisions must stay with the owner.

### Why copying rows cannot work

Every identity that ties a measurement together is local to its database:

- **Integer IDs differ.** `Product` uses a `BigAutoField` primary key, with `product_key` as the portable UUID (`core/models.py:3437-3439`). Metric definitions live in the physical table `metrics` (`core/models.py:8670`). The HF downloads v2 definition is id 47 in backfill and id 33 in production.
- **`contract_hash` cannot match across databases.** It is the digest of the frozen contract (`core/benchmark_metric_identity.py:716-724`, `:740-742`). That frozen contract includes the taxonomy version's primary key, which is a random `uuid4` (`core/models.py:8488-8489`). It also includes per-database `source_configuration`: definition snapshots carry the local `id` (`core/benchmark_metric_identity.py:413-414`, `:544`), and `use_policy` is copied from the local `DataSource` row (`:553-556`). The backfill contract hash (`c1c94079…`) can therefore never appear in production.

The unit of transfer is the **source capture**: the archived payload, its source metadata, and the observation and value records it produced. The target rebuilds the contract from the same reviewed spec and replays each capture through the shared writer, `persist_source`. Identity is proved without `contract_hash`, by three checks:

- `catalog_hash`, `mapping_hash` and `methodology_hash` are equal. In this run they were `f921b2b0…`, `946afa47…` and `67859057…` on both sides (`core/data_source_backfill_transfer.py:393-395`).
- Definition snapshots minus `id` are equal (`:71-78`, `:396`).
- Per capture, `payload_sha256` is equal, and every non-local field of every observation and value is equal (`:409-418`).

### Wrong turns worth not repeating

- **Joining on mapping or product found nothing.** Looking for existing production 0813 values through `collection_observations.mapping_id → subject → product`, or through `collection_observations.product_id`, returned 0 rows. The rows exist, but unmapped (`mapping_id` NULL), under production chart contract `75c4a856…`. A query by exact `source_identifier` found 104 of them. Reconciliation therefore matches on source identifier: case-insensitive for HF, exact for the other sources (`core/data_source_backfill_transfer.py:349-350`).
- **The definitions table has a different physical name.** Guessing the table as `source_metrics` failed because the physical table is `metrics`.
- **Locking the product with a join failed.** `Product.objects.select_for_update().select_related('publisher_account')` failed with PostgreSQL "FOR UPDATE cannot be applied to the nullable side of an outer join". The fix locks the product row alone (`:241`).
- **Reconciliation first ran inside the write transaction.** There it would have held the product row lock through about 15 s of scans across roughly 611k production `metric_values`, about 4 s per source in this session's measurements. It now runs before the transaction (`:458-460`).
- **Running from the operator host was considered.** Running the transfer locally against production's external URL was rejected in favour of a documented harvest one-off job (see Guidance 7).
- **Adding a chart preset was considered.** Putting a preset (`methodology.comparisons`) into the transfer contract was rejected. It is ChartEngine scope, and it would change `methodology_hash`, which destroys the equality proof.
- **The shared test DB was out of sync.** It carried another branch's migrations and lacked this branch's, and the wrapper refuses both cases. The session temporarily aligned migration files. `AGENTS.md` on main now prescribes a disposable detached checkout for this situation.

## Guidance

### 1. Export captures and expected records, read-only, into a hashed bundle

`build_bundle` (`core/data_source_backfill_transfer.py:155-201`) refuses three kinds of capture:

- non-success runs or runs with missing evidence archives (`:165-166`);
- archives whose decoded payload no longer hashes to `payload_sha256` (`:168`);
- payloads over 64 KiB (`:33`, `:169`).

It also bounds the capture count to 1–100 (`:32`, `:178`). Database-local foreign keys are replaced by natural keys:

- for observations, the mapping external identifier, the dataset code and `product_key` (`:96-98`);
- for values, `observation_key`, `metric_key` and the metric version (`:109-111`).

The bundle also stores what the chart reader returns for every line (`expected_reader`, `:197`). The command's export mode first validates the backfill connection identity. It then runs inside `SET TRANSACTION READ ONLY` (`core/management/commands/transfer_backfill_contract.py:37-42`).

### 2. Compare everything except database-local fields

Field comparison excludes only clocks and local references. For observations those are `id`, `run`, `scope_run`, `observed_at`, `updated_at`, `mapping`, `request`, `legacy_archive`, `supersedes_observation`, `post`, `source_dataset` and `product`. For values they are `id`, `observation`, `source_metric` and `window_range` (`core/data_source_backfill_transfer.py:35-39`). Everything else must be equal field by field (`_compare`, `:272-290`).

`observed_at` is the replay clock. When payload rows lack it, `prepare_rows` stamps `timezone.now()` (`core/benchmark_metric_store.py:556`), and the run's `observed_at` is always the replay time (`:1115`). For this cohort that was harmless because the readers bucket by source dates. One caveat matters for future cohorts: the HF reader falls back to `observed_at` when an observation has neither `archive_snapshot_date` nor `reconstruction_date` (`core/benchmark_metric_series.py:387-394`). Such a row would move to the replay day. The reader-point comparison (`core/data_source_backfill_transfer.py:419-422`) catches that and blocks the commit. Keep that comparison.

### 3. Rebuild the contract in the target from the same reviewed spec

`_transfer` (`:375-396`) runs these steps in order:

1. `configure_taxonomy` for the one product. It is `get_or_create` by `version_hash` (`core/measurement_taxonomy.py:242-247`).
2. A check that the target's snapshot equals the bundled catalog snapshot.
3. `cohort_collection_spec(...)` with the bundled archive-row key, reference hash and product-type review.
4. A check that the methodology equals the original.
5. `configure_collection`, which is `get_or_create` by `contract_hash` (`core/benchmark_metric_identity.py:735-756`).

A difference anywhere stops the run before any capture is replayed.

### 4. Satisfy target prerequisites explicitly. Never bypass them.

- **Product type.** `prepare_collection` requires `product_type_code == 'llm-model'` for non-statistics contracts (`core/benchmark_metric_identity.py:624-636`). Production had NULL. `_prepare_product` checks the exact reviewed identity (repo, brand, HF type, publisher, private and disabled flags, creation instant). It sets `llm-model` only when the type is NULL and refuses any other existing type (`core/data_source_backfill_transfer.py:236-252`). The reviewed basis is the backfill contract's `methodology.local_product_type_review`.

  One precondition is **not in code**. In this session the operator checked by hand that no production taxonomy snapshot already contained the product. A frozen snapshot that records `type: None` would later fail `prepare_collection`'s "catalog identity changed since taxonomy review" check (`core/benchmark_metric_identity.py:641-645`).
- **Use policy.** `persist_source` calls `enforce_source_collection` (`core/benchmark_metric_store.py:917-924`). That requires `collection` and `retention` to be `allowed` in both the contract's frozen policy and the current `DataSource` policy (`core/benchmark_attribution.py:176-238`). Production's policies allowed hf (including dataset `cfahlgren1/hub-stats`), arena, openrouter and opencode, so the writer ran under normal enforcement.

  Never route production writes through `isolated_backfill_review`. It is the backfill-only bypass (`core/data_source_backfill_target.py:21-29`, `core/benchmark_attribution.py:227`). It also calls `validate_backfill_target(require_write=True)`, which pins the backfill host, database and login, so in production it fails by design.
- **Definitions.** The target must already hold every pinned metric definition with an equal snapshot minus `id` (`core/data_source_backfill_transfer.py:396`). `prepare_rows` separately refuses changed pinned definitions (`core/benchmark_metric_store.py:445-449`).

### 5. Verify retained origins on the target side

17 of the 45 captures were themselves selections from production captures. Their metadata carries `retained_capture_origin`, written by `reuse_capture` (`core/data_source_backfill_reuse.py:53`) with `resource == ORIGIN_RESOURCE` (`:15`). Only the target database still holds the original archive.

`_verify_retained_origin` re-reads that run. It requires the archive id and payload hash to be unchanged, and requires `select_retained_payload(original) == bundled payload` (`core/data_source_backfill_transfer.py:255-269`). This is the strongest provenance check available, and it exists only on the production side. It runs before the write transaction.

### 6. Reconcile against existing production values, read-only, before writing

`reconcile_existing` (`:324-366`) builds one cell per (source, metric, day). It compares each cell with production values from contracts that are **not** a copy of this one; copies are excluded by `mapping_hash` plus `methodology_hash` (`:346-347`), so a re-run does not count itself. `classify_cells` (`:300-321`) assigns one of four states:

- `equivalent`
- `conflicting`
- `inserted_only`
- `transferred_captures_disagree`: two transferred captures give different numbers for the same cell. HF had two captures for 15 days, a retained production capture and an archive snapshot, and they agreed.

The result was 104 equivalent, 67 inserted, 0 conflicting. Missing requested days are listed, never zero-filled (`:362-364`): HF Aug 26, 24 Arena days with no publication, and no OpenCode days.

Reconciliation output is a **finding, not a verification problem**. `apply_bundle` keeps it in `checks`, outside `problems`, so a conflict does not block commit today (`:459-465`).

### 7. One transaction, commit only on zero problems, with rehearsal as forced rollback

`apply_bundle` (`:453-468`) works in this order:

1. Validate the bundle (`:204-219`).
2. Pin the target (`_require_target`, `:222-233`). It refuses the backfill host or database name and requires `current_database()` to equal the `--target-database` argument.
3. Run the read-only checks.
4. Run all writes inside one `transaction.atomic()`. If there are any problems, or `commit` is false, raise a sentinel `_Rollback` and return the report with `committed: False`.

The nested writers (`persist_source`, `claim_direct_run`, `fenced_run`, `configure_*`) all use plain `atomic` blocks on the same connection, so they become savepoints inside the outer transaction (`core/benchmark_metric_store.py:1172-1175`, `core/benchmark_metric_identity.py:735`). A rehearsal is therefore the same code path as the real run, ending in rollback.

Replay order matters too. The bundle orders captures by original `completed_at` (`core/data_source_backfill_transfer.py:84-86`), and `validate_bundle` refuses reordering (`:211-213`). Replayed runs get new clocks. The reader breaks same-day ties by `(direct HF flag, source_as_of or completed_at, completed_at, run id)` (`core/benchmark_metric_series.py:417-433`), so replaying in original order keeps the same winning capture. Do not parallelize replay.

### 8. Run it as a one-off job on the harvest service's image at the deployed revision, never in the web service

The run used a Render one-off job on `pushinweight-harvest` (`crn-d9gv94o4n6ts739tqaug`) at the deployed revision. The job runs `transfer_backfill_contract`, not `run_cycle` or the X post backfill; the harvest service only supplies the image and database access. That gives the approved database access, separate compute, and exactly the reviewed code (`docs/deploy/render.md`, "Historical X batch jobs and safe handover"). `AGENTS.md`, "Protect the live web service", forbids this kind of work inside `pushinweight-web`. A heavy read over Render SSH OOM-restarted (ran out of memory and restarted) the web service on 2026-11-03.

Harvesting does not need to pause. The writer's advisory lock is keyed by (contract, source) (`core/benchmark_metric_store.py:414-425`), and the new contract has no schedule. The only shared row the transfer locks is the product row (`core/data_source_backfill_transfer.py:241`), for the duration of the short write transaction.

Sequence used on 2026-11-05 JST:

1. PR #81 (code plus bundle) merged. Production web and `pushinweight-harvest` auto-deployed at the merge revision, with the migration head unchanged.
2. Rehearsal job `job-dbm16259fdbs73bh51og`: 0 problems, 45 captures, 216 values, 17 retained origins verified, 171 reader points identical to backfill, rolled back.
3. Confirm production was unchanged: product type still NULL, no transfer contract, no subject.
4. Apply job `job-dbm16ud9fdbs73bh7krg`: `committed: true`, 0 problems.
5. Independent read-back via `render psql`: 216 values, 45 success runs whose payload hashes match the bundle, 4 mappings, `scheduling_enabled` false.
6. Idempotency rehearsal `job-dbm17ooae00c738278lg`: contract `created: false`, `captures_created: 0`, 216 values, 0 problems.
7. The first post-deploy harvest cycle was healthy.

Render job logs can lag. Right after the rehearsal finished, its JSON report was missing from the first log fetch and appeared seconds later.

### 9. Know the visibility gap after transfer

The values are visible to readers: `metric_points` returned the 171 observed points. The production chart route, however, is scoped to a contract and needs a preset: `benchmarks/<uuid:contract_id>/<slug:preset>/` (`monitor/urls.py:18`), with presets taken from `methodology.comparisons` (`core/benchmark_metric_identity.py:791`). The transferred contract has no preset, so no production page shows 0813 until ChartEngine adds one in a separate task.

Readers that query by exact source identifier will now see each of the 104 equivalent cells twice, with the same numbers. One copy sits under the chart contract (unmapped) and one under the transfer contract.

### Automating this as a background step for the Backfiller data source

**Already automation-safe (existing behavior):**

- **Deterministic identity on re-run.** The replay ingestion key is `digest([FORMAT, target contract_hash, origin run id, payload_sha256])` (`core/data_source_backfill_transfer.py:400`). `persist_source` returns the existing completed run for a known key and refuses a changed payload (`core/benchmark_metric_store.py:943-961`). Taxonomy, contract and evidence archives are all `get_or_create` by content hash (`core/measurement_taxonomy.py:244`, `core/benchmark_metric_identity.py:741`, `core/collection_capture.py:48`). A re-run writes nothing new, and it re-verifies everything, so it doubles as an audit.
- **Nothing to resume.** The run is all-or-nothing in one transaction, so a failed run leaves no partial state. Retrying after the cause is fixed is safe.
- **Rehearsal is the same code with forced rollback.** No separate "dry-run" logic can drift from the real path.
- **Clear outcome signal.**
  - Success: exit 0, with `problems == []` and `committed == true` (or `committed == false` for a rehearsal).
  - Verification failure: `CommandError("transfer verification failed …; nothing committed")` (`core/management/commands/transfer_backfill_contract.py:55-56`).
  - Guard failures: the `ValueError`/`TypeError`/`KeyError` raised by `require`, and a missing contract (`MetricCollectionContract.DoesNotExist`), become `CommandError` (`:57-58`).
  - Use-policy failures: `UseNotPermitted` is a `PermissionError` (`core/benchmark_attribution.py:138`). The command does not catch it, so it surfaces as an uncaught exception. It still rolls back and still exits non-zero.

  A runner should treat **any** non-zero exit as failure and parse the report only on exit 0.
- **The JSON report is the receipt.** It contains the target database, bundle hash, origin and target contract identity, capture and value counts, reader points, label differences, reconciliation summary and details, and `provider_calls: 0`.

**What must change, or stay owner-gated (recommendations, not existing features):**

- **Bundle transport.** The command reads a file path (`core/management/commands/transfer_backfill_contract.py:50`). Today the bundle is committed JSON shipped inside the deployed image, so each transfer needs a code deploy. That does not suit an unattended loop. Two options:
  - Have the job read captures from the backfill DB read-only. This needs `BACKFILL_DATABASE_URL` on the job's service, which is a credential-scoping decision for the owner.
  - Fetch the bundle from shared storage.

  Either way, `bundle_sha256` proves integrity, not authority. `validate_bundle` checks only that the bundle's own hash matches its content (`core/data_source_backfill_transfer.py:206`), and anyone can recompute it. In this run, authority came from the bundle being reviewed in PR #81. An automated runner should pin an expected `bundle_sha256` (or the backfill contract id and hash) taken from a reviewed record, and refuse anything else.
- **Cohort-specific constants.** The following are hard-coded for 0813:
  - `PRODUCT`, `PUBLISHER`, `IDENTIFIERS`, `START` and `END` (`core/data_source_backfill_cohort.py:19-29`);
  - `SOURCES` and the size caps (`core/data_source_backfill_transfer.py:31-33`);
  - `_prepare_product`'s identity checks;
  - `DEFAULT_REVIEWER`;
  - `select_retained_payload`'s field map.

  Generalizing needs a reviewed per-cohort spec that `cohort_collection_spec` and the transfer both consume. Do not infer cohorts from backfill contents.
- **Product-type review.** Keep it owner-gated. Setting a type only from NULL, with recorded review evidence, is the safe rule. The "no frozen taxonomy snapshot contains this product" precondition should become a coded pre-check before automation relies on it.
- **Use policy.** The runner must not grant or relax policy. A `UseNotPermitted` failure is an owner decision, not a retryable error.
- **Conflicts.** Decide whether `conflicting > 0` or `transferred_captures_disagree > 0` blocks the commit. Today these are reported but never block. A cautious default for an unattended runner is to stop for review, but this is the owner's product decision.
- **Concurrency.** Two runners on the same cohort would contend on the contract's unique hash and the writer's try-lock ("metric collection is already running", `core/benchmark_metric_store.py:420`). Use one runner per cohort, and treat that lock error as "retry later", not as a data failure.
- **Receipt persistence.** The report goes only to stdout (`core/management/commands/transfer_backfill_contract.py:54`), and Render job logs lag and expire. Persist it somewhere durable. Choose existing storage under the schema-first review in `AGENTS.md`; do not add a receipt table by reflex.
- **Fixed invariants.** Never pause harvesting (`AGENTS.md`, "Live-operation continuity is a release invariant"). Never run inside the web service. Keep the expensive read-only checks outside the write transaction.

### Lessons from the collection phase that an unattended runner must also handle (session history)

The 0813 data reached the backfill DB through the Backfiller data source campaign in PR #80 (titled "DataBackfiller"). That phase surfaced failure modes a background runner has to detect on its own (session history):

- **Backfill first, then promote.** The owner rejected writing gap collections straight into production and chose isolated collection, then validation, then a verified transfer. The same review said a proven collector may later write routine updates through a controlled production pipeline. That is the open question an automated runner answers, and it stays an owner decision.
- **A wrong contract scope silently strands values.** The first 0813 contract used the wrong identifier scope for Arena and OpenRouter, so 59 values were left unassigned until a corrected contract replayed the saved evidence. Transfer only the corrected contract revision, and have the runner flag values that the active contract leaves unmapped.
- **"Completed" does not mean "collected".** An Arena job completed with zero provider requests because the product had no provider pins. The rerun then got HTTP 500 on every request. Treat zero-request completions and transport failures as incomplete collection, never as proof that no history exists.
- **Record gaps as evidence, never as zeros.** OpenCode's self-contradicting response was kept but its measurements were rejected. The HF archive simply has no Aug 26 snapshot. Every requested metric and date must end as a stored value or an evidenced gap.
- **Render one-off limits.** Jobs hit time limits (a 10-minute stop at 189 MB during a backup) and needed checkpoints and resume. Deploys by other sessions mid-run made the revision-pinned job refuse to start until it was re-pinned. The image lacked the optional Parquet reader the HF archive jobs need.
- **Settings module.** A one-off script set `DJANGO_SETTINGS_MODULE=pushinweight.settings`; the correct value is `project.settings`.
- **The importer is backfill-only by design.** The first transfer attempt found that the retained-capture importer requires the backfill DB because of the write-target guard. It stopped without writes rather than weakening the guard. That is why the transfer is a separate path.

## Why This Matters

A row copy between these databases would carry IDs that point to different records in production. It also cannot be proved correct, because `contract_hash` legitimately differs. Replay through the shared writer instead puts every production row through the same validation, policy enforcement, evidence archiving and reader semantics as a live collection. Field-by-field verification inside the transaction then proves that the result equals what was reviewed.

The rehearsal, apply and idempotent re-run sequence makes the step safe to run repeatedly. That is the property an unattended background step needs. The owner-gated items above are where an automated runner could silently create authority it does not have: picking product types, bypassing use policy, accepting conflicting numbers, or trusting a self-hashed file.

## When to Apply

- Promoting any reviewed backfill-DB contract, or a future automated backfill cohort, into production or any other non-backfill database.
- Moving measurements between databases where integer IDs, taxonomy UUIDs or `DataSource` policies differ.
- Designing the "promote" phase of an unattended backfiller. Use the automation subsection above as the checklist.
- Not for production-to-production fixes inside one database. Use the shared writer or a reviewed correction there instead.

## Examples

Export, run against the backfill DB. The Django connection and `BACKFILL_DATABASE_URL` must both identify `xbackfiller`, because `validate_backfill_target` checks both (`core/data_source_backfill_target.py:36-59`). Never print the credential.

```bash
DATABASE_URL="$BACKFILL_DATABASE_URL" python manage.py transfer_backfill_contract \
  --export --contract 0b8f0a7d-dd51-4d20-8f93-6c6852329d1d \
  --out docs/analysis/2026-11-05-131906-0813-transfer-bundle.json
# {"bundle_sha256": "11d87ae9…", "captures": 45, "values": 216, "writes": 0, ...}
```

Rehearsal, then apply, as one-off jobs on the `pushinweight-harvest` image at the deployed revision. Run these where the Render CLI is authenticated (fuchitalee; from another host, wrap them in `ssh fuchitalee '…'`). The bundle path is relative to the repository inside the image.

```bash
render jobs create crn-d9gv94o4n6ts739tqaug --confirm --start-command \
  "python manage.py transfer_backfill_contract --bundle docs/analysis/2026-11-05-131906-0813-transfer-bundle.json --target-database pushinweight_shadow"
# Expect: "mode": "rehearsal", "problems": [], "committed": false

render jobs create crn-d9gv94o4n6ts739tqaug --confirm --start-command \
  "python manage.py transfer_backfill_contract --bundle docs/analysis/2026-11-05-131906-0813-transfer-bundle.json --target-database pushinweight_shadow --apply"
# Expect: "mode": "apply", "problems": [], "committed": true
```

Success predicate for a runner:

```python
ok = exit_code == 0 and report["problems"] == [] and report["committed"] is (mode == "apply")
# Recommended extra gate (owner decision): report["reconciliation"]["summary"].get("conflicting", 0) == 0
```

Independent read-back, with counts by source and metric for the new contract:

```bash
render psql dpg-d9koekqjobas73fvjqng-a --command "
SELECT j.source_id, m.metric_key, count(*)
FROM metric_values v
JOIN collection_observations o ON o.id = v.observation_id
JOIN collection_runs r ON r.id = o.run_id
JOIN collection_jobs j ON j.id = r.job_id
JOIN metrics m ON m.id = v.source_metric_id
WHERE j.contract_id = '28f61a49-76e9-47dd-8ac4-502ee02f772e'
GROUP BY 1, 2 ORDER BY 1, 2"
```

Expected for 0813: 216 values in total. Arena has 30 (6 metrics × 5 dates). HF has 157 over 28 days. OpenRouter has 29.

Then repeat the rehearsal command once more as an idempotency check. Expect `contract.created == false`, `captures_created == 0`, `values == 216` and `problems == []`.

End-to-end tests are in `tests/test_data_source_backfill_transfer.py`. Each test first builds and exports a backfill-side contract inside a rolled-back atomic block, then replays it against production-like state (product type NULL, a pre-existing chart contract holding unmapped rows). The tests cover:

- rehearsal leaving no rows;
- apply reproducing the values, reader points and reconciliation;
- idempotent re-apply;
- a single changed value rolling back every write;
- refusal of tampered bundles and payloads, the wrong target database, a conflicting product type, and a changed retained origin.

Full evidence log: `docs/plans/2026-11-05-014520-fix-0813-production-transfer-20261105-plan.md`.

## Related

- [Backfill coverage and completion](../workflow-issues/2026-10-16-131500-backfill-coverage-and-completion.md): acceptance claims for the X post backfill and its staging-to-production Post promotion. It covers a different backfill; its general rule (finishing collection does not prove coverage) also applies to Backfiller data source cohorts.
- [OriginalContent cutover checks](2026-10-08-143200-original-content-cutover-checks.md): an earlier verify-before-switch production import, using dry-run, import and replay with zero discrepancies.
- [X post backfill pipeline learning](../architecture-patterns/backfiller-and-llm-classifier-pipeline-wiring.md): a different backfill (past X posts through `CycleRunner`). It shares only the "reuse the shared pipeline, don't fork a writer" principle that this transfer applies to promotion.
- [Render shadow restore and cutover](../operations/render-shadow-restore-and-cutover.md): a whole-database restore recipe. It also keeps the harvest running, using a final delta instead of a pause; a bounded measurement promotion like this one needs neither.
- [Prepare shared test schema before migration tests](2026-10-22-142740-prepare-shared-test-schema-before-migration-tests.md): the shared test DB mismatch met here.
- Runbooks: `docs/deploy/render.md` (one-off jobs from `pushinweight-harvest`), `docs/reference/collection-jobs.md` (Backfiller-data-source and the 0813 campaign), `AGENTS.md` ("Protect the live web service", "Live-operation continuity").
- PR #80 (DataBackfiller, the collection into the backfill DB) and PR #81 (this transfer path).
