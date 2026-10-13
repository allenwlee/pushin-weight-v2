---
title: Shared collection planning evidence
date: 2026-10-13
source_revision: db5510ccc94ea326dd5f81e833a9c791e5e84d99
---

# Shared Collection Planning Evidence

This evidence supports [the G3 jobs/history plan](../plans/2026-10-13-062212-feat-g3-collection-jobs-history-plan.md).
Work was limited to source/document inspection, primary documentation research and planning artifacts.
No application test, production database query/write, collector batch, model download, scheduler change or deployment was performed in this planning run.

## Current Repository Evidence

`core/models.py` and `0080_collection_schema` already supply generalized runs, scoped progress and observations.
The current run lifecycle admits metric/catalog purposes; metric partial is terminal, while catalog partial remains resumable.
`SourceSubjectMapping` still requires a metric contract and its uniqueness is contract-scoped.
`CollectionObservation` status is ok/error, with separate publication precision and catalog outcome fields.
These concrete constraints shape U1/U2 and prevent a fake catalog-purpose X adapter or arbitrary observation statuses.

`core/account_identity.py.upsert_account` currently admits X/HF only.
Native GH accounts therefore require a deliberate admission change, not just a GH namespace seed.
`scripts/benchmark_download_collector/sources.py` has an OpenRouter daily-ranking reader but no `/api/v1/models` catalog reader.
U4 now includes the missing catalog acquisition for API-only products.

`core/benchmark_metric_history.py.prepare_history` admits reviewed archives, selected-JSON hashes, date spans below 366 days and at most 366 snapshots per manifest.
Long campaigns must be chunked rather than weakening those checks.
`scripts/staging_refresh/database.py` currently deletes catalog observations/scopes/runs in foreign-key order with raw SQL.
New job pointers and content runs must be handled explicitly before those deletions.

The earlier release-date comparison was copied without changing its bytes, together with its linked inventory and family register.
It examined 19 HF repositories representing 17 of 43 proposed release groups, with earlier repository clocks retained where they relate to in-window products.
It does not establish a complete release census or guaranteed first public upload dates.

## Primary Documentation Checked October 13

- [GitHub repositories](https://docs.github.com/en/rest/repos/repos), [releases](https://docs.github.com/en/rest/releases/releases), [commits](https://docs.github.com/en/rest/commits/commits) and [starring](https://docs.github.com/en/rest/activity/starring): retain native identities and distinguish repository, commit and release clocks. Present stargazer events are not a complete historical star-count series.
- [HF API](https://huggingface.co/docs/huggingface_hub/package_reference/hf_api): current SDK creation sorting differs from the older REST client's hardcoded modification-order path. Verify the actual request contract before adding cohort creation sorting; preserve the existing catalog path.
- [HF download statistics](https://huggingface.co/docs/hub/en/models-download-stats): rolling counters measure qualifying requests and cannot supply a fabricated daily download or user series.
- [OpenRouter model catalog](https://openrouter.ai/docs/api/api-reference/models/list-all-models-and-their-properties): exposes provider identity and a `created` field. Its use as an API-only listing creation basis is an explicit cohort assumption, separate from release availability.
- [OpenRouter daily rankings](https://openrouter.ai/docs/api/api-reference/datasets/daily-token-totals-for-top-50-models): daily top 50 plus aggregate other; history floor 2025-01-01. Unknown individual usage remains unknown.
- [Arena historical dataset](https://huggingface.co/datasets/lmarena-ai/leaderboard-dataset): published snapshots have full/latest splits and distinct scoring configurations. The plan pins the relevant publication/configuration rather than treating latest as complete history.

Raw documentation responses remain local and ignored under `.firecrawl/g3-collection-history/`.
Only primary sources changed provider-contract decisions; irrelevant search results were excluded.

## Confidence Check

Depth is Deep; persistent schema, backfills and external providers are material risks.
Three sections were selected for a targeted sequential pass:

| Section | Score | Concrete strengthening |
| --- | --- | --- |
| Key technical decisions | 3: one trigger, risk and critical-section bonuses | Native repo/event/revision keys keep multiple releases/commits distinct |
| Implementation units | 3: one trigger, risk and critical-section bonuses | Correct source paths and add GH admission to the existing account helper |
| System-wide impact | 3: one trigger, risk and critical-section bonuses | Guard rollback after new-purpose/mapping data and preserve staging foreign-key order |

The existing single-table decision and newest-100 chronology were preserved.
No alternate model or independent agent was invoked.

## Document Review

`ce-doc-review` ran in non-interactive mode with six sequential inline lenses: coherence, feasibility, product, scope, security and adversarial.
AGENTS.md routes Task/Subagent work into the main thread; all coverage is recorded as non-independent, and no cross-model reviewer was dispatched.
Pack resolution returned no roots, warnings or errors.

One practical defect was retained: the initial draft assumed an existing OpenRouter model catalog reader.
Following that instruction would omit API-only models from the creation-ordered cohort.
The authorized correction adds its bounded acquisition, explicit endpoint admission, reviewed catalog-to-ranking identity and a recorded-fixture test to U4.
The Product Contract is unchanged; no proposed fixes, decisions or FYIs remain.

The [structured original/resolved review](2026-10-13-160815-g3-collection-plan-review.json) retains the original evidence, dispositions, coverage and final document identity.
The [backfill boundary note](2026-10-13-160815-g3-backfill-collection-interface.md) records JSON pilot now, shared API then adapter, without claiming that the proposed API is implemented.

## Owner Amendment: Database Authority and Scheduled Harvest

The same plan now includes an explicit GH-name-to-canonical-subject proposal, a focused child-to-parent foreign-key flowchart and a business-data storage map.
The proposed schema delta is still one new `collection_jobs` table, alterations to existing `collection_runs`/`source_subject_mappings`, and no retirements or renames.
All current physical names in that map were checked against `core/models.py` without importing Django or running a migration.

Measurement alignment was checked against `SourceMetric`, `MetricValue`, `numeric_value`, `value_times`, provider row adapters and the earlier benchmark plan's temporal/history contract.
A known number with unknown effective time is persisted; a missing numeric value has no value row.
The new compliance matrix carries state/flow, since-origin, single known boundaries, source timezone, archive/retrieval/publication clocks, revisions and compatible aggregation.
Adapter-to-writer execution proofs remain implementation work.

The current scheduled path is `run_cycle --scheduled` → `CycleRunner.run` → `_finish_summary` → `finalize_and_persist`.
`scripts/harvest_cost/emit.py` emits canonical summary/cohort logs and writes `data/runs/<run_id>.json` plus a latest pointer.
No `CollectionRun` write exists in that overall path at the pinned revision, although posts, enrichment, cursor/backlog state and other subsystem records already use PostgreSQL.

U9 now assigns the later scheduled/manual/backfill receipt integration to the X owner after shared-API handover.
The proposal preserves the cron, separates rejected attempts from active claims, uses fresh scheduled scopes and keeps backfill continuation campaign-specific.
Business state becomes database-authoritative; production cost/recovery readers use run reports and optional files are exports.
The separately authorized JSON staging pilot remains independent and temporary.

The amended plan has 15 requirements, nine units and ten technical decisions.
The focused source/structure checks pass; no application tests or live database checks were executed for this amendment.
The review record preserves the first review and adds the amendment's source-backed checks and current plan identity.
