---
title: Backfiller fixes from the OpenAI/Anthropic size test - Plan
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ollija-annotate-plan
execution: code
ollija:
  change_id: fix-backfill-size-test-fixes-20261030-2026-10-30-015749
  branch: fix/backfill-size-test-fixes-20261030
  workflow: plan
  delivery_target: on-request
  delivery_selected_by_user: false
---
<!-- BEGIN OLLIJA DELIVERY GUIDE -->
## Ollija Delivery Guide

This block is generated guidance. Do not edit it directly. Correct durable facts in `.ollija/project.yaml` or this template, then rerun `ollija annotate-plan`. Current explicit owner instructions govern this task. Record exceptions below and reflect route changes in metadata; removed requirements must not return through another checklist.

### Resolved locations

- Authoritative host: `fuchitalee`
- Authoritative repository: `/Users/fuchitalee/development/pushin-weight-v2`
- Ollija release worktree area: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees`
- Active worktree: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/backfill-size-test-fixes-20261030`
- Plan: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/backfill-size-test-fixes-20261030/docs/plans/2026-10-30-015749-fix-backfill-size-test-fixes-20261030-plan.md`
- Change: `fix-backfill-size-test-fixes-20261030-2026-10-30-015749`
- Branch: `fix/backfill-size-test-fixes-20261030`
- Staging branch and blueprint: `staging`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/backfill-size-test-fixes-20261030/render-staging.yaml`
- Production branch and blueprint: `main`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/backfill-size-test-fixes-20261030/render.yaml`
- Staging URL: `https://pushinweight-staging-web.onrender.com`
- Production URL: `https://pushinweight-web.onrender.com`

### Placement

This worktree is inside the Ollija release worktree area. Reuse it for the whole change. Do not create a second worktree or plan for this branch.

### Delivery scope

- Workflow: `plan`
- Delivery target: `on-request`
- Owner selection recorded: `false`

Target is not authorized until the owner selects it. Wait for a later explicit release request; do not commit, push, stage, or promote on this guide alone.

### Failure handling

- Complete applicable, unwaived checks for the selected route. A waived check is waived, never passed. Owner-selected direct production does not require staging.
- Product defects return to the parent implementation workflow; repeat only checks invalidated by the fix. Environment failures require repairing the environment, not a new source commit. Retry only after a relevant fact changes.
- SSH, shell, environment, or multi-machine failures use the repository infra/multi-machine skill first.
- The change ledger is advisory; do not validate or enforce it.
- Never force-remove a worktree. Retain staging-only, failed, dirty, locked,
  noncanonical, or candidate-mismatched worktrees for diagnosis or later
  delivery.
- Do not run an endless retry loop or start a persistent Ollija process.
<!-- END OLLIJA DELIVERY GUIDE -->

## Delivery Exceptions

- 2026-10-30 (JST): the owner asked to plan all seven backfiller fixes and build fixes 1–3 first ("Plan all 7, build 1–3 first").
  - The endpoint is an open pull request with CI decided. No merge, staging or production delivery without the owner's go.
- 2026-10-30 (JST): the pull request targets `ops/xbackfiller-db-20261026`, not `main` (owner choice "PR into the July branch").
  - July runs from pinned source archives of that branch, at schema 0183. `main` is at schema 0205 and 220 commits ahead of their merge base.
  - Bringing these fixes to `main` happens when that branch itself lands on `main`, which is follow-up U9.

# Backfiller fixes from the OpenAI/Anthropic size test - Plan

## Plain-English Summary

The six-hour OpenAI/Anthropic size test (PR #72, which never merges to `main`) used the backfiller harder than July has, and exposed seven backfiller problems. This plan records all seven and fixes the first three now:

1. a provider HTTP 520 error stops a backfill run, which is how July stopped;
2. the spending cap counts conservative reservations, which run 6–7 times the real bill, so a $30 cap stops at about $5 of real spend;
3. an unused import fails the backfill CI lint step, so that job's database tests never run.

The first three are already written and tested on PR #72. This change carries only those pieces onto the branch July actually runs from, `ops/xbackfiller-db-20261026`. It leaves behind the OpenAI/Anthropic brand config, the size-test routes and the size-test scripts. Nothing in production changes, and July's saved windows behave exactly as before: a window without the new `spend_basis` field produces the same manifest and the same spending policy.

The other four problems are recorded with evidence, but they are not built in this change:

4. 15% of search requests were paid twice at run boundaries;
5. posts that fail model validation three times stay unfinished forever;
6. the backfill database lacks production's list memberships;
7. a run whose final check fails still exits as success.

Moving everything onto `main` is a separate, larger step (U9), because the July branch is 220 commits behind `main` at an older schema.

Completion is checked by the existing and new tests passing on the pull request's CI. The PostgreSQL tests can only run in CI, because the shared local test database is not at this branch's schema. A pull request is opened against the July branch; merging it is the owner's decision, and July's session then decides when to launch from the merged revision.

## Context and evidence

- **Size-test plan:** `docs/plans/2026-10-27-113859-ops-oai-anthropic-size-20261027-plan.md` on branch `ops/oai-anthropic-size-20261027`, especially the U9 and U10 execution records.
- **Size-test report:** `docs/analysis/2026-10-30-095822-oai-anthropic-size-report.md` (run notes at the end).
- **Machine-local receipts** on fuchitalee: `~/.local/share/render-operations/2026-10-29-oai-anthropic-size-test/`.
  - `final-phase-receipt.json`, `final-failures.json` and `cls-failures.json` (enrichment outcome);
  - `collection-phase-summary.txt` (collection);
  - `handback-receipt.json` (July handback).
- **How July runs:** Render one-off jobs that download and verify a pinned source archive of this branch line, for example `ba3a2685` and `447e8286` (`~/.local/share/render-operations/2026-10-26-xbackfiller-db-move/collect-payload.json`, `entity-rollout.json`).
  - The database is xbackfiller (`dpg-dbfemu2vcj2c73fsafe0-a`), at schema `0183_rg6_typed_statistics_identity`.
- **Branch state on 2026-10-30:**
  - `origin/ops/xbackfiller-db-20261026` is at `ccf10e1b`. It is checked out clean in worktree `.worktrees/ops/u10-staging-20261025` and has no open PR.
  - `origin/main` is at `c445ec24`, migration `0205`.
- **Source commits on PR #72's branch, and how each applies to `ccf10e1b`** (`git merge-tree`, files untouched):
  - `47f8b721` applies cleanly;
  - `6df3bb4a` applies cleanly;
  - `cef1168e` applies cleanly;
  - the `spend_basis` plumbing in `6a13d480` is entangled with the size-test routes, slices and lab lists, so it is re-written here as a minimal change.

## Scope

**TOUCH**
- `tests/test_account_user_about_model.py` (lint)
- `monitor/backfill_retry.py`
- `core/provider_batches.py`
- `monitor/backfill_enrichment.py`
- `scripts/backfill_campaign.py`
- `monitor/management/commands/run_backfill.py`
- the tests named in each unit

**PRESERVE**
- July's saved manifests and their frozen policies. A window without `spend_basis` gives a byte-identical manifest and a `policy_snapshot` without the key.
- The scheduled harvester path (`run_cycle`, `CycleRunner` collection, `config.yaml`, `config/harvest_policy.yaml`).
- The 8-call production query shape, the brand set and all size-test-only code.

**EXCLUDED**
- OpenAI/Anthropic config (`fce17cfc`).
- Named routes, slices, `author_list_ids` and ceilings (`6a13d480`, except `spend_basis`).
- The `scripts/backfill_size_*` files and the size report.
- Any merge, deploy, cron change or production write.

## Key Technical Decisions

- **KTD1. Target the July branch.** July launches from pinned archives of `ops/xbackfiller-db-20261026` against a 0183 database, so a fix on `main` (0205) does not reach July.
  - (session-settled: user-directed, 2026-10-30, chosen over a branch from `main` with the base folded in.)
- **KTD2. Carry the proven commits, then add only the missing plumbing.**
  - `47f8b721`, `6df3bb4a` and `cef1168e` are cherry-picked with their tests. They ran in PR #72's CI database proof, run 40769414567: 181 of 184 passed, and the 3 failures predate that plan.
  - `cef1168e` alone is unreachable from `run_backfill`, because no window can set `spend_basis`. The plumbing is therefore re-written minimally:
    - campaign windows accept one optional `spend_basis` field (`reservation` or `settled`);
    - unknown window fields are rejected;
    - `_enrich_window` passes the field to `policy_snapshot` only when present.
  - Plain `since`/`until` rows keep today's tuple input, so campaign names and manifests are unchanged.
- **KTD3. The regression net pins the July-shaped manifest.**
  - The manifest test from `f01d0f03` is ported to pin that a plain window keeps today's exact manifest and policy.
  - Its companion frozen-query test is omitted: it depends on the size-test frozen query file, which is not on this branch and would only skip.
- **KTD4. The local PostgreSQL gap is recorded, not worked around.** The shared test database (`~/.local/bin/pushinweight-test-db`) refuses because this branch's migration `0183` is pending there. Pure-Python tests run locally with `scripts/pytest-local`. PostgreSQL-marked tests run in the PR's CI on a fresh database, as they did for PR #72.

## Implementation Units

### U1. CI lint fix

- **Goal:** the backfill workflow's ruff step passes, so its PostgreSQL tests run.
- **Change:** cherry-pick `47f8b721` (removes the unused `transaction` import at `tests/test_account_user_about_model.py:7`, which arrived in `e41c4ff1`).
- **Verification:** `ruff check tests/test_account_user_about_model.py` is clean.

### U2. HTTP 520 retries at the same cursor

- **Goal:** a provider 520 is transient, as 500/502/503/504 already are. July stopped on one.
- **Change:** cherry-pick `6df3bb4a`, which adds 520 to `transient()` in `monitor/backfill_retry.py`.
- **Tests:**
  - `tests/test_backfill_retry_statuses.py` (pure);
  - the 520 recovery case in `tests/test_backfill_staging_retry.py` (PostgreSQL; it exercises the staging prefetcher's retry at the same cursor, the call-chain pin per M18).
- **Verification:** the pure test fails before the change and passes after it; the CI PostgreSQL case passes.

### U3. Settled spend basis, reachable from a campaign window

- **Goal:** a campaign window can choose `spend_basis: "settled"`, so `max_usd` counts provider-reported cost for finished requests and reservations for the rest.
- **Change:**
  - cherry-pick `cef1168e` (`core/provider_batches.py`: `SPEND_BASES`, `counted_model_spend`, `campaign_model_totals`, `admit_model_request`; and `monitor/backfill_enrichment.py`: `policy_snapshot(spend_basis=...)`);
  - in `scripts/backfill_campaign.py`, add `WINDOW_FIELDS = {"since", "until", "spend_basis"}` and `_window_input` (a dict row is validated, an unknown field gives `unknown_window_field`, an invalid basis gives `invalid_spend_basis`). `manifest()` copies a present basis into the window, and `_enrich_window` passes it to `policy_snapshot`;
  - in `monitor/management/commands/run_backfill.py`, `--windows` rows with only `since`/`until` stay tuples, and any other row passes through as a dict for `manifest()` to validate.
- **Tests:**
  - `tests/test_backfill_spend_basis.py`, plus the cases in `tests/test_backfill_direct_enrichment.py` and `tests/test_backfill_native_enrichment.py` (from `cef1168e`);
  - new `tests/test_backfill_campaign.py` cases: the basis reaches `policy_snapshot` only when present, and a window with `spend_basis` gets it in the manifest while an unknown field or an invalid basis is rejected;
  - a new `tests/test_run_backfill_command.py` case (PostgreSQL): a `--windows` file with `spend_basis` plans a manifest carrying it, without creating jobs.
- **Live evidence:** the size test (`6a13d480`'s version of this plumbing) held $84.86 in reservations against $7.96 settled, and kept classifying under a $30 cap.

### U4. Regression net for July-shaped inputs

- **Goal:** prove July's plain windows are unchanged.
- **Change:** port `test_manifest_without_new_window_fields_keeps_its_july_shape` and `_stub_manifest_inputs` from `f01d0f03` into `tests/test_backfill_campaign.py`.
- **Verification:** the test passes before and after U3. Pinning before the change shows today's shape; the same assertions pass after.

### Follow-up units (recorded, not built in this change)

- **U5. Paid re-fetches at run boundaries.**
  - 691 of 4,614 search requests (15%) were paid twice: a response arrived as a run ended, its page did not commit, and the next run re-fetched it (`lost_responses`, `monitor/backfill_staging.py` around line 200).
  - One 6-hour window took 38 runs.
  - First step: find why runs end so often, then commit in-flight pages or reuse the received body.
- **U6. Unfinished posts after three validation failures.**
  - 64 posts were never classified and 60 never finished targeted extraction.
  - `deferred_enrichment_work` (`monitor/backfill_enrichment.py:777`) keeps each post's attempt count across regrouped packets, so no re-run retries them.
  - About 9% of member results fail canonical validation per pass, which adds about 10% to classification cost.
  - Needs a bounded way to finish them, and a look at the validation failures (model `deepseek-ai/DeepSeek-V4-Flash-0731`, `canonical_validation_failed`).
- **U7. Backfill-database list memberships and roles.**
  - xbackfiller holds no Call A list memberships, and only 98 of production's 232 roles at the last count, so a window planned there freezes no Call A author roles.
  - July's saved windows carry their own frozen contexts (207 for job `d4440f2e…`).
  - Needs a standing, read-only-sourced sync before planning a window. The size test's seed (`scripts/backfill_size_seed.py`) was deliberately undone.
- **U8. Exit status after a failed final check.** The size test's final enrichment receipt said `failed`, with 123 posts deferred, but the Render job exited `succeeded`. Decide whether exit 0 is intended under `--evaluate-at-end`; if not, return non-zero.
- **U9. Land the July branch, with these fixes, on `main`.**
  - It conflicts across 220 commits, in `monitor/backfill_collection.py`, `backfill_promotion.py`, `backfill_staging.py`, `cycle.py` and `tests/test_backfill_staging_retry.py`.
  - xbackfiller must move from schema 0183 to 0205 before July can run `main`-based code.
  - It needs its own plan and coordination with the July session.

## Verification Contract

| Check | Command or source | Pass condition |
|---|---|---|
| Lint | `.venv/bin/ruff check` on changed files | clean |
| Pure tests | `scripts/pytest-local tests/test_backfill_retry_statuses.py tests/test_backfill_campaign.py -q` | all pass; skips reported |
| PostgreSQL tests | PR CI ("Historical X backfill" and the others), on a fresh database | the new and cherry-picked tests pass; other outcomes match the base branch's |
| No behavior change for July | U4 test, plus manifest bytes for plain windows | identical |
| Scope | `git diff origin/ops/xbackfiller-db-20261026 --stat` | only TOUCH files |

## Definition of Done

- U1–U4 are committed on `fix/backfill-size-test-fixes-20261030`, with named files only.
- The branch is pushed and a PR is open against `ops/xbackfiller-db-20261026`.
- Each CI check is decided; any failure is compared with the base branch's and reported.
- U5–U9 stay recorded here as follow-ups. Merging, and launching July from the merged revision, are the owner's and July session's decisions.
