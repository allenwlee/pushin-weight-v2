# August 9 two-hour backfill test across 21 brands

**Incomplete / unsuccessful**: the owner-expanded test covers August 9, 2026, **00:00–02:00 UTC /09:00–11:00 JST**.
The staging database contains **98 newly recovered scoped posts**; **48/49** frozen sample posts have complete persisted literal translation and canonical per-brand classification.
This verifies bounded collection and sampled enrichment. Search exhaustion describes the selected provider queries, not complete historical X coverage.

Executing application source: `6925e8467afb769ef895166c0d96dbd6bafc8247`. Runtime: fuchitalee against verified `pushinweight_staging`; no production release and no writes to production.
The existing staging harvest cron remained suspended. No service, scheduler, shared schema or CollectionJob adapter changed.
G3 approved interim atomic host JSON checkpoints; the shared persistence integration remains separately owned.

## Scope and completion

All 21 configured brands were selected. The normal six B/C keyword/handle calls ran in eight 15-minute slices, The manifest also reserves eight Qwen/B1 units with the verified historical `"Qwen3.8"` name; those units have not run.
Historical Call A remains outside the test because its account population is not frozen.

| Campaign | Units | Drained | New inserts | Frozen sample pending |
| --- | ---: | --- | ---: | ---: |
| all21 | 48 | True | 98 | 1 |
| qwen_historical | 0 | False | 0 | 0 |

Collection drained: **False**. Saved cursor/backlog digests unchanged: **True**.
98 distinct primary recovered IDs include 98 new posts and 0 previously stored posts. 50 recovered posts remain pending outside or within the sampled enrichment contract; their states are retained, and complete enrichment of the entire recovered dataset is not claimed.

## Resource measurements

| Measurement | Observed |
| --- | ---: |
| Physical X API starts | 81 |
| Raw top-level returned X records, including duplicate retrieval/context lookups | 162 |
| Estimated tweet API cost | USD0.031500 |
| Physical model starts | 177 |
| Captured model events | 177 |
| Reported model input/output tokens | 2,571,463 / 34,745 |
| Known provider-reported model cost | USD0.145739 |
| Model requests with unknown cost | 7 |
| Active command elapsed time | 2560.163s |
| Active command CPU time | 43.169s |
| Peak process memory | 118.16MiB |
| Peak Python threads, including measurement thread | 5 |
| Peak observed X request concurrency | 1 |
| Finite invocations used | 13 /15 |

API cost uses the pilot tariff from [TwitterAPI pricing](https://twitterapi.io/pricing): 15 credits per returned tweet, a 15-credit minimum per request, and 100,000 credits per USD. It counts raw return rows before application deduplication. This is an estimate rather than a reconciled invoice. Unknown failed model usage remains unknown.
Translation uses canonical Gemma4 with at most three concurrent post workers; canonical DeepSeek classification issues its split content/brand requests. No Celery worker or beat process is added. Provider-event timing can suggest overlapping model requests, but millisecond duration rounding does not establish an exact concurrency peak.
The 300-second limit is a cooperative request admission deadline. In-flight database persistence can finish afterward; the reported elapsed times retain any overrun. Scheduled-slot reserve and per-unit writer leases remain active.

## Per-call execution

| Call | Attempts, including resumption | Primary rows | Inserts | Existing-row updates |
| --- | ---: | ---: | ---: | ---: |
| B1 | 102 | 118 | 89 | 0 |
| C1 | 23 | 10 | 5 | 1 |
| C2 | 9 | 5 | 0 | 0 |
| C3 | 13 | 8 | 3 | 2 |
| B2 | 10 | 16 | 1 | 3 |
| B3 | 8 | 5 | 0 | 0 |

## Remaining classifier conflict

Normal collection drained 48 units and recovered 98 new posts. The 49-post frozen cohort has 48 complete posts; `2086263847346663470` remains classification pending. The historical Qwen supplement has not started because the controller prioritizes the pending cohort. The approved four-hour 02:00–06:00UTC window has not launched.
A single bounded diagnostic invocation 13 followed the stopped 12-invocation controller; the original cumulative 720 API / 720 model allowance and wall deadline remain unchanged. Actual role responses pass individual validation. The content role classifies the GLM portion, while the brand role assigns unknown sentiment/unavailable context. The current canonical parser rejects classified rows with unknown sentiment. The same classifier path is shared with the scheduled harvester. No labels were filled by hand and the validation rule was preserved. A bounded semantic reassessment would change the selected classifier protocol, so owner direction is pending.
The manual retry starvation was repaired by visiting each pending unit once per invocation. Long translations now use 2000-character chunks with a distinct cache identity; the scheduled 5000-character default is preserved. Cached chunks survive resumption. The previous long-post timeouts and cache collision are resolved in this cohort; its long Indonesian source now has all three locale texts.
The acceptance checker now validates the current-source EN/ZH-CN/JA artifact contract. Its older six-language compatibility helper rejected a valid Spanish `es` result; that compatibility result remains separately recorded.

## What this supports for larger windows

The required live acceptance has not passed, so these measurements do not yet justify expanding execution. A 24-hour window is 12 times the sampled authored interval; a 31-day month is 372 times. Those factors are conditional workload extrapolations only. Different hours, releases, brand name history, search overlap and provider indexing can change volume substantially. The model measurements cover the frozen sample, so multiplying total test cost would understate the cost of enriching every recovered post.
The active-time/CPU difference also includes database/network waiting and model waiting. This local-to-Render test does not measure the throughput of a process colocated with the database. Use measured per-completed-sample model costs and representative additional windows before budgeting a whole month.

## Evidence and delivery

The [original 15-minute failures](2026-10-13-174503-backfill-fixes-and-pilot.md) remain preserved and unsuccessful.
[Same task plan](../../plans/2026-10-12-105615-docs-august-harvest-audit-20261012-plan.md) records the owner amendment and acceptance contract.
Private manifests, the created campaign checkpoint, invocation receipts, raw X responses, model usage events and exact cohort facts remain on fuchitalee under `data/backfill-fixes-20261013/wide-aug09-21brands/`; credentials and raw response bodies are not committed.
The latest committed source passed 304 local regression checks including 110 required PostgreSQL tests with zero skips/errors. Invocations 1–6 used `f5bbe190`, invocation 7 used `ac097648`, and 8–13 used `6925e846`. The first source received an independent review; a later focused Grok review timed out without a usable receipt. Native review and the expanded regression net cover the live repairs; no later independent approval is claimed.

## Subsequent owner acceptance

After this incomplete snapshot, the owner explicitly accepted the remaining pending classifier post as good enough and selected a full24-hour August9 staging run instead of the prepared4-hour step. The strict receipt remains unsuccessful; owner acceptance is recorded separately. The classifier reassessment proposal and earlier all-cohort launch barrier are retired. The new run uses the same committed source and canonical validator, with serial capped batches; pending assessments remain visible.
