# August 9 recovery and Render backfill verification

The authorized August 9 2026 UTC day/all 21 brands collection drained all seven query families and recovered 1,557 new staging Posts. Collection finished locally before the Render transfer. This report proves adoption and storage on Render; it does not claim the provider-backed day ran on Render.

The adapter reuses existing CycleRunner attribution/Post storage and G3 CollectionJob/CollectionRun/CollectionScopeRun. It adds zero tables. Model processing is separate; on-demand TwitterAPI credentials are mandatory, with no scheduled or legacy fallback.

| Observation | Evidence |
|---|---|
| Deployed application source | `4b5f1c5481ba7e94f1f8f07fc812432ad2c04bc6` on staging web and the existing dormant staging-jobs build donor |
| Separate Render job | `job-db7gkaaj9qps73cd1ilg`, succeeded 2026-10-14T04:50:49Z→2026-10-14T04:51:28Z;0.5 CPU / 512 MiB |
| Actual database/role/connection | `pushinweight_staging` / `pushinweight_staging`, PostgreSQL 18.4, internal `dpg-d9vb8ds9v7es738lepsg-a` |
| Credential purpose | `on-demand`; exact managed key present; missing key fails before transport |
| Shared job/run | `58111a25-7e6a-4f96-893f-142a6c4b58ca` / `e474fc1f-b8b4-495c-b2bf-07b20bfedd9c`; historical/content/x_backfill; completed/success |
| Progress reconciliation |13/13 scopes complete;1,660 distinct recovered IDs reconciled against Post |
| Prior paid-request starts |596 (496 sliced + 100 whole-window); provider billing remains unknown |
| Render adoption/probe provider/model calls |0/0 |
| Enrichment at adoption |239 complete, 1,421 pending by durable state; this is separate from collection completion |
| Shared live cursor/backlog |Original digests preserved through recovery, adoption and both storage probes |
| Local verification |224 passed; 123 required PostgreSQL tests executed;0 skips/errors; focused Ruff passes |
| Remote verification |All four PR58 checks passed on 4b5f1c54; native review complete; Grok review timed out without usable output |

The same captured 20-result page produced 18 duplicate Post updates in both locations. Body SHA256: `9c9da28edfe1133fdedc88ad01d489f805fcf65aabd9871481584aa4b828c9ae`.

| Measurement | Local through SSH | Render/internal PostgreSQL |
|---|---:|---:|
| Shared Post writer |66.533s|2.171s|
| Attribution plus storage |68.114s|2.847s|

The shared writer was 30.6 times faster for this matched duplicate-update page. New-insert throughput and full-month runtime remain unmeasured. No extra provider calls or invented posts were used for this comparison.

Two earlier Render attempts failed before acquiring a collection claim: missing on-demand credentials on the provider-free web base, then configuration drift in inactive publisher lanes. Those remain failures. Web was restored to having no provider keys. The final job uses the existing staging-jobs service as its build/environment donor; its normal nonexistent-February 31 schedule is unchanged and was not triggered. The staging harvester stays suspended; production harvesting remains active on its existing 15-minute schedule. Render cannot rebuild a suspended donor, so no staging-harvester resume was attempted.

The collection fingerprint retains collection settings and frozen queries/bounds, while excluding inactive model/discovery/extraction/publication lanes. A real PostgreSQL test failed before this repair; changes to collection settings still fail before a claim. Expired/paused workers cannot commit pages, Post writes and their continuation are atomic, and physical API admission survives interruption.

Raw captures, complete runtime receipts and credentials remain private on fuchitalee. The earlier 15-minute failures and owner-accepted two-hour result are preserved in the task plan. Other August gaps and July/month campaigns remain outside this execution.

Final source confirmation at `fd6f9594df2cfcfa2d6a3982ecc85e13acba3c08` succeeded in separate Render job `job-db7gt9k9v7es73c1i610`, preserving all 1,660 recovered IDs and original cursor/backlog digests with 0 provider/model calls. The mixed invalid-window receipt case is pinned: valid saved IDs/raw count remain visible while the unsafe cursor stays blocked. Its new PostgreSQL test failed before repair; the final focused suite executed 109 tests / 73 required PostgreSQL tests with 0 skips/errors.

Performance is variable: that repeat's shared writer took 105.618 seconds. One bounded diagnostic repeat on the same final source then took 1.714 seconds (total attribution/storage 2.381 seconds), with 1.579 seconds across 380 SQL statements, 1.322 CPU seconds and 106.5 MiB peak resident memory. Both repeats updated the same 18 existing posts and made 0 provider/model calls. The 105-second outlier was not reproduced or causally explained. The original 30.6× comparison remains one observation; it does not establish a stable rate for a day or month. No further performance batches or new dates were launched.
