# DataBackfiller 0813 validation and transfer handoff

Observed: 2026-11-04 T 11:05:17.500738+00:00. Operator code: `d85d17b94969f87e560a580ac6fbffb451d66001`.

The existing backfill database now supports current DataBackfiller code. It contains 216 correctly assigned measurement records for DeepSeek V 4 Pro 0813, representing 171 distinct source/metric/date cells. Multiple retained captures agree on their overlapping values. No production data import or application deployment was performed.

## Coverage

The requested release interval is UTC `[2026-08-13T00:00:00Z,2026-09-11T00:00:00Z)` (29 days). Missing values stay blank; they are not zeros.

| Datasource and measurements | Before acquisition, retained production evidence | Backfill DB after collection | Remaining gap |
| --- | --- | --- | --- |
| HF: rolling 30-day downloads, cumulative downloads, likes | August 27–September 10 (15 days) | August 13–25 and August 27–September 10 (28 days) | August 26 has no matching model-file revision in the examined title-filtered history. |
| HF: trending score | None in requested period | Same 28 days | August 26, same archive gap. |
| Net change in rolling download counter | Inputs missing August 13–26 | Within the requested August 14–27 derivation window, August 14–25 can be calculated | August 26 and 27 lack an adjacent input; August 13 additionally needs genuine August 12 evidence. This is not daily new downloads. |
| OpenRouter: total tokens | All 29 days | All 29 days reused | None in requested interval. |
| Arena: rating, rank, lower/upper bounds, variance, votes | August 19,21,27 and September 1,2 | The same five publication dates | Further acquisition is incomplete: the historical API returned HTTP 500 on three requests. Unobserved dates are not proven unpublished. |
| OpenCode: tokens, unique users, sessions | None | No admitted measurements | Current response is invalid: updatedAt October 2 conflicts with an October 3 daily row. Its unchanged 2025 tail is also retained. Do not repair years or treat this as confirmed unavailable history. |

July 30–August 12 is pre-release chart context. No measurements were invented for it. GitHub remains excluded: the shared recipe toolkit is not a confirmed release-specific repository. X brand-post acquisition is outside this campaign.

## Exact identities and selection

| Identity | Value |
| --- | --- |
| Database resource / database / login | `dpg-dbfemu2vcj2c73fsafe0-a` / `xbackfiller` / `xbackfiller` |
| Product | `20d66250-db05-40bf-8fda-94b610bed0c7` |
| Measurement subject | `6cdebe8f-1e7b-5600-a94a-36a8930d5a4f` |
| Corrected numeric contract | `0b8f0a7d-dd51-4d20-8f93-6c6852329d1d` |
| Contract SHA-256 | `c1c94079aed3ba544562ee67bc914b37d7261974736cf88bae9bdf1239fad080` |
| Reviewed reference SHA-256 | `c3266be80e4f17ebe40d022d79147e078dacde55b6cfdaa1d72028052d273706` |
| HF | `deepseek-ai/DeepSeek-V4-Pro-0813`; native archive row `6a7d346291824bcb9cd27db7` |
| HF dataset / examined immutable head | `cfahlgren1/hub-stats` / `4bae9bfcde3d4130e5ca3706e714ba8376cdaba3` |
| Arena | `deepseek-v4-pro-high-20260813`, `text/overall` |
| OpenRouter | `deepseek/deepseek-v4-pro-20260813` |
| OpenCode | `deepseek/deepseek-v4-pro-0813`; `/data/deepseek/deepseek-v4-pro-0813.json` |

HF discovery retained an immutable head and 10 commit pages in PostgreSQL. Selection recognizes commit titles containing `models.parquet` and chooses the newest matching upload per UTC day; it does not inspect every generically titled commit for changed file contents. It found 28 applicable model-file revisions. The August 26 conclusion is limited to that examined source history; it is not a claim about every possible third-party archive. Snapshot, observation, retrieval and measurement clocks remain distinct. OpenCode uses explicit UTC inclusive-start/exclusive-end boundaries.

## Evidence, corrections and replay

The [measurement inventory](2026-11-04-200654-databackfiller-0813-validation-values.csv) contains all 216 selected-contract values with value, observation and run IDs, metric/date fields, historical times and payload hashes. SHA-256: `7c21f322a713a3f0ab4a1161a05ca47bfeea4faac4c73b54997da2b5d5179e0c`. It is an evidence index for a later reviewed transfer, not an executable production import.

Seventeen retained production captures were read without production writes or provider calls. The acquisition added 28 archived HF snapshots. The initial new contract mistakenly used the `model` identifier scope for all providers; non-HF adapters emit the empty scope. That left 59 Arena/OpenRouter values unassigned. A corrected immutable contract was created and all 45 retained/acquired numeric captures were re-admitted through the shared writer, with origin run/archive/hash references. Every correction replay returned the same run and added no duplicate values. Original observations were preserved.

Original contract: `d96b9555-4ad9-4d23-83d2-f02adf9de184`; original campaign: `0813:8e0eff0fe05355eb2308a18c`. Corrected campaign: `0813:53600c4f80f35eaccb53c97a`. Use the corrected contract for the transfer candidate. Do not promote the unassigned original Arena/OpenRouter observations. There are 432 values globally across both contracts;216 belong to the selected corrected contract.

The initial Arena definition performed no acquisition because it selected a model with no provider pins. Its zero-request completion was not accepted as source coverage. A regression now verifies actual campaign dispatch reaches the shared native-publication collector. The replacement `arena-native` attempt reached the provider and recorded the HTTP 500 failures. The old paused Arena definition was left untouched.

Actual OpenCode run: `7f6f0903-7e25-400f-bd30-f6f5e2cda5e8`; retained selected payload archive: `21e86831-c38c-48f0-b09a-779fb4894c20`. Actual Arena native parent: `9dd5d2d8-e746-460a-856b-aa248bf1306b`, job `8d20e9f2-23ca-4890-afbf-2765f5e58a17`; its shared publication run owns the physical requests. Inspect that campaign's request receipts rather than interpreting the parent's zero request counter as zero provider activity.

Public HF campaign replay covered all 29 completed jobs (discovery plus 28 days) with provider transport disabled. The global value count remained 432. The 45 corrected numeric imports were also replay-verified without HTTP.

## Resource and preservation evidence

The two campaign revisions together used 33 attempts and 519 physical requests; their conservative request reservations total 815. All 519 request outcomes are recorded as received and have complete physical accounting; their received bytes total 100,665,418 (about 96 MiB). HTTP error responses are still requests. No new datasource requests remain pending. The aggregate ceilings are 40 attempts,1,000 requests,1 GiB and 3,600 seconds; the per-attempt 80-second bound reserves at most 2,640 seconds for 33 attempts. Package installation is separate from datasource accounting.

Each acquisition ran in a separate existing Render one-off facility, with provider concurrency 1. No permanent service was added. The optional locked PyArrow 25.0.1 decoder was installed with verified wheel hashes only inside temporary archive workers; the web/cron build and environment were not changed. Production harvesting remained active.

The existing backfill DB was upgraded from 0183 to `0223_merge_backfill_retry_policy` through the canonical graph and guarded retirement. All 13 legacy collection JSON columns were retired only after source/page/runtime/report parity. The feature adds 0 tables and 0 columns. The existing approved graph adds 10 tables, retires 2 and renames 1 (physical table count 235→243); the two new migration files widen an existing retry-policy version check to retain both recorded policies.

All 49,274 original Posts match across all 81 original columns, SHA-256 `f38328c8140df8506a730a115c057c44195df7c49c187269c40899b146d56ac1`. All 41 X job states and active/attempt/success pointers match their pre-upgrade inventory; current public readers work after contraction. Five pre-existing pending X request outcomes remain unknown and untouched. Their stale owner was not resumed or reclaimed. The verified 318,148,416-byte backup remains on the authoritative host; its receipt SHA-256 is `e54d13a69d60beb52c9a52520d2f55b0f20dfe3df9b63f8ae8e426ffa953cea8`.

## Verification and later work

Focused tests cover target refusal, current registration/dispatch, schema rehearsal for retry versions 1 and 2, historical-field cache restoration, saved replay, mapping admission, UTC bootstrap and concurrent X/numeric writes on independent connections. The latest combined registry/cohort/OpenCode/HF/reuse run passed 24 tests (20 required PostgreSQL cases); after the Arena dispatch change 16 focused tests passed, followed by 6 cohort/HF tests after the source-population cap change. Earlier relevant checks include 44 X staging/retry/retirement tests and 10 schema/policy rehearsal tests. No required PostgreSQL tests were skipped.

The immediate production latest 20 health observation found 20 fresh-pending posts and 0 unhealthy posts: operationally neutral, enrichment completeness inconclusive. This backend change was not deployed to production. Repository-wide lint reports existing findings; changed runtime/new test lint is clean except the unchanged model-class findings. No project-wide typecheck is configured.

Later production transfer needs its own authorization and must preserve natural identities, definitions, source evidence and timing, resolving foreign IDs locally. Do not copy auto-increment IDs across databases. Further Arena collection should address the failing historical endpoint or use a separately bounded, source-verified archive route. OpenCode requires valid historical source evidence before values can be admitted. Neither gap should be filled with zero or renamed as unavailable merely to finish a chart.

## Review follow-up

The full code review and independent validation confirmed two recovery defects, both reproduced before their fixes: a new contract revision could start a fresh aggregate allowance, and an HF transport exception could leave the active claim until lease expiry. The fixes keep all persisted identities and per-revision reports, combine existing `0813:` owners for locked budget admission, and route connection/stream failures through partial finalization. A simultaneous two-revision test admits only one final request reservation. Mocked send and stream failures retain accounting and allow immediate explicit resume without advancing clocks or overriding leases.

The latest focused and existing-regression suites passed160tests in two runs (31 and129), with no required PostgreSQL skips. Arena and OpenRouter retained-import/replay cases now assert exact persisted product/contract assignment. No additional provider requests or backfill/production data writes were made for these review fixes. Actual collection evidence above remains tied to its recorded acquisition revision; these later tests cover the changed guards and failure paths.
