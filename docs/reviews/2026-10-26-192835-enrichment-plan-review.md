# Enrichment plan review

Document: ../plans/2026-10-26-095132-fix-enrichment-tracked-promotion-20261026-plan.md
Mode: non-interactive; planning corrections authorized by the current request.
Coverage: coherence, feasibility, adversarial recovery cases, and credential boundaries, reviewed sequentially inline under repository tool mapping. No independent or cross-model corroboration is claimed.

| Finding | Evidence and consequence | Disposition |
| --- | --- | --- |
| Restart-safe cost enforcement had no suitable storage | Existing synthesis/editorial budgets own different workloads; backfill budget owns CollectionJob runs. A process restart would reset an in-memory allowance. | Applied: one typed EnrichmentBudgetWindow, atomic conservative reservation, fixed configured window identity, explicit ownership and constraints. |
| Small pilot could be mistaken for sustained capacity proof | 200 posts cannot show 1,100 completions/hour sustained under arrivals and retries. | Applied: pilot screens only; three saturated hours within four-hour observation prove capacity. |
| Undefined eligibility could hide failed fresh posts | Removing terminal/budget failures could make the 99% completion metric pass with real gaps. | Applied: include all fresh scheduled states and report exceptions. |
| Manual and scheduled credential selection was ambiguous | Existing backfill factory uses DEEPINFRA_ON_DEMAND; normal pipeline uses DEEPINFRA_API_KEY. Silent fallback would mix spending ownership. | Applied: explicit pilot versus scheduled/recovery purposes, no fallback, secret-free artifacts. |

Resolved result: fixes_applied=4; proposed_fixes_count=0; decisions_count=0; fyi_count=0. Known execution prerequisites remain the shared test-schema alignment and concrete authorized spending/release settings already described in the plan. No code execution or production validation is claimed by this review.

## Capacity decision follow-up, October 26

The owner selected two commentary slots now, incremental increases only when needed, and a pipeline capable of accommodating 2–3× future intake. Reconciled the plan in place: U0 is the active trial, KTD7 defines growth scenarios and shared provider accounting, KTD2 uses configurable enrichment process-slot ownership, and KTD4 starts with existing translation/classification concurrency. The earlier assumed six translation slots and permanent single-worker exclusion are superseded. No second process is activated. The existing production grant is retained with the owner's capacity-review pause.

Local U0 evidence: 23 targeted provider-free tests passed with zero skips; a 40-call simulated-provider comparison took 2.294 seconds with one slot and 1.156 seconds with two. Database lifecycle/API/prewarm tests could not start because G2/RG6 advanced the shared schema beyond this checkout through 0186. A broader lock invocation had 33 passes and two required database skips, not a passing gate. The full lifecycle/API/prewarm suite remains unexecuted. Three full-config lint findings reproduce unchanged at HEAD. No live throughput, paid provider test, or production activation is claimed.

## Owner-requested alternative database test, October 26 21:49 JST

The owner proposed `xbackfiller-db`. Its schema is also newer (0183), but inspection of the eight commentary-related tables found no missing model columns or extra required columns. Its commentary queue was empty. Because it contains operational historical collection data, the standard pytest setup/flush workflow was not used.

Two bounded PostgreSQL integration scenarios passed against the changed commentary code with fake transports and transaction rollback: two concurrent calls published two artifacts/six locale texts; a timeout in one call left the sibling publication intact. Both scenarios claimed only two posts, left the third pending at zero attempts, and recorded exact returned token usage. Fixture absence was verified after rollback, with zero paid model calls. Sequence allocation may advance despite rollback. The source-hashed receipt is `.local/commentary-two-slot/xbackfiller-rollback-receipt.json` in the task worktree.

This supplies real persistence evidence for U0. It does not substitute for the full lifecycle/API/prewarm regression suite, prove live throughput, or resume deployment. The earlier unsupported-lookup harness failure rolled back; a subsequent import-path launch error occurred before connecting. The corrected saved script passed both scenarios.

## Expanded regression verification, October 26

The owner then requested testing everything. The full commentary lifecycle/API/prewarm coverage is now executed: **54 commentary tests passed**, including two-slot publication/accounting. The final broader run covered 78 modules and returned **901 passed, 34 failed, zero skipped**; 287 PostgreSQL-required cases executed with no required skips or setup errors. Twelve topology checks passed separately and Django system checks found no issues. Ruff's 47 findings in legacy cycle/config/classification files reproduce unchanged at HEAD; no added findings.

Testing used the permanent shared database through its unmodified exclusive wrapper. A verification-only checkout keeps G2 schema/model definitions at `0186` while existing runtime/test files are restored from production `56587a05` and the current candidate diff applied. No migration or production change. The source manifest records this compatibility boundary; it is not proof of running against production schema `0168`.

The 34 failures comprise 31 missing frozen U18 fixture dependencies and three assertions independently reproduced without our patch: two expect seven collection calls where current configuration yields eight/C4; one expects extraction cap zero where production configuration declares twenty. No tests were silently skipped, no historical fixtures fabricated, and no collection settings changed. These are unresolved broader-suite failures, not new two-slot regressions established by this run.

Earlier diagnostic runs are retained: 899/35 on G2 runtime, with four scheduled-lineage failures also present without our patch; 228/19 after replacing only the cycle file, exposing a mismatched runtime/test setup. The final run corrects that pairing, and all six cursor-page sweep tests pass. Canonical evidence copy: `.local/commentary-two-slot/regression-proof/`; the plan carries exact revisions, counts, failure causes and source limitations. The continuous enrichment worker/recovery units remain unimplemented and deployment remains paused.

## Resumed implementation and release review, October 27

The owner's LFG instruction resumes production delivery. The candidate now extends current production `8785ea76` / schema0195 and includes the continuous worker, due queue, actual-attempt checkpoints, bounded dispatch/cost reservations, safe recovery and health commands. One typed budget table is added by0197; G2's unreleased0196 and the test-only0198 merge are excluded.

Current broad verification:387 passed with one baseline refresh assertion independently reproduced at unchanged8785;119 required PostgreSQL tests ran with zero skips. Follow-up refresh/recovery coverage:78 passed and the same baseline failure. Final worker/config/topology coverage:52 passed,24 required PostgreSQL tests, zero skips. All43 Ollija/topology checks also passed. Baseline failures remain failures, not waived passes.

Inline review repaired refresh lifecycle exclusion, transactional rollback when recovery receipt persistence fails, and missing worker settings for literal translation/rare-type processing. Added real call-chain malformed/ambiguous promotion cases preserve existing classifications. Three scaled-arrival queue cases test1x/2x/3x scheduling; live throughput still needs the staged pilot and observation.

Correctness, standards, testing, maintainability, performance, data migration, reliability and adversarial lenses were completed sequentially by the parent per repository instructions. No remaining product defect was established. Independent coverage is unavailable: Claude returned402 without a review, and the single Grok fallback timed out after600 seconds without an artifact. Neither is reported as a passed review.

Code is ready for the staged release. Production activation, spending-window selection, pilot semantics, actual capacity and incident recovery accounting remain operational work; no production success is claimed by this review.
