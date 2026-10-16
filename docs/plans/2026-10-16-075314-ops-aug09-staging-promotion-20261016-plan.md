---
title: August backfill verification and July 30 collection parity
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ollija-annotate-plan
execution: code
ollija:
  change_id: ops-aug09-staging-promotion-20261016-2026-10-16-075314
  branch: ops/aug09-staging-promotion-20261016
  workflow: plan
  delivery_target: production
  delivery_selected_by_user: true
  delivery_route: staged
  delivery_route_selected_by_user: false
  staging_transport: branch
---
<!-- BEGIN OLLIJA DELIVERY GUIDE -->
## Ollija Delivery Guide

This block is generated guidance. Do not edit it directly. Correct durable facts in `.ollija/project.yaml` or this template, then rerun `ollija annotate-plan`. Current explicit owner instructions govern this task. Record exceptions below and reflect route changes in metadata; removed requirements must not return through another checklist.

### Resolved locations

- Authoritative host: `fuchitalee`
- Authoritative repository: `/Users/fuchitalee/development/pushin-weight-v2`
- Ollija release worktree area: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees`
- Active worktree: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/ops/aug09-staging-promotion-20261016`
- Plan: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/ops/aug09-staging-promotion-20261016/docs/plans/2026-10-16-075314-ops-aug09-staging-promotion-20261016-plan.md`
- Change: `ops-aug09-staging-promotion-20261016-2026-10-16-075314`
- Branch: `ops/aug09-staging-promotion-20261016`
- Staging branch and blueprint: `staging`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/ops/aug09-staging-promotion-20261016/render-staging.yaml`
- Production branch and blueprint: `main`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/ops/aug09-staging-promotion-20261016/render.yaml`
- Staging URL: `https://pushinweight-staging-web.onrender.com`
- Production URL: `https://pushinweight-web.onrender.com`

### Placement

This worktree is inside the Ollija release worktree area. Reuse it for the whole change. Do not create a second worktree or plan for this branch.

### Delivery scope

- Workflow: `plan`
- Delivery target: `production`
- Owner selection recorded: `true`
- Delivery route: `staged`

1. Complete implementation and the plan's verification contract.
2. Run the configured focused checks:
   - `pytest tests/ollija`
3. The parent workflow commits only this plan's changes, pushes the feature branch, and records the candidate SHA.
4. Fetch the remote staging lane: `git fetch origin refs/heads/staging`.
5. Require the unchanged candidate SHA to be a fast-forward of that fetched remote ref, then push the exact candidate SHA to `refs/heads/staging` with the server-enforced fast-forward command `git push origin <candidate-sha>:refs/heads/staging`.
6. Verify the remote staging ref resolves to the candidate SHA and the deployment for `pushinweight-staging-web` reports that same SHA.
7. Run staging checks. Stop here if they fail.
8. Only after staging passes, fetch the remote production lane: `git fetch origin refs/heads/main`.
9. Require the same unchanged candidate SHA to be a fast-forward of that fetched remote ref, then push the exact candidate SHA to `refs/heads/main` with the server-enforced fast-forward command `git push origin <candidate-sha>:refs/heads/main`.
10. Verify the remote production ref resolves to the candidate SHA and the deployment for `pushinweight-web` reports that same SHA before reporting completion.
11. After step 10 succeeds, perform worktree cleanup as the final filesystem action:
    - From `/Users/fuchitalee/development/pushin-weight-v2`, require `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/ops/aug09-staging-promotion-20261016` to remain registered, clean, unlocked, and at the verified candidate SHA. If any guard fails, retain it and report the reason.
    - Run `git -C /Users/fuchitalee/development/pushin-weight-v2 worktree remove /Users/fuchitalee/development/pushin-weight-v2/.worktrees/ops/aug09-staging-promotion-20261016` without `--force`.
    - Preserve the local and remote feature branches. Continue final reporting from the authoritative repository root.

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

### Current owner authorization — July 30 deployment and production run

The active goal now explicitly authorizes implementation through deployment
and the July 30 2026 UTC 24-hour production batch. This supersedes the prior
on-request/documents-only endpoint below. Use the normal staged delivery route
unless the owner subsequently changes it. Preserve unrelated services and the
normal harvester; deployment permission is not cron-pause permission.

Success requires 3,800–4,200 genuine distinct Posts for the full July 30 window,
with canonical enrichment at least the measured percentage for today's
scheduled production posts. Freeze the baseline timestamp, UTC publication
bounds, exact IDs, denominator and completion definition before execution;
report the mature (older than 30 minutes) cohort separately. Do not manufacture,
truncate or discard valid posts to fit the numerical goal. A count outside the
range remains an unmet goal requiring diagnosis and an honest result.

Complete acquisition across the entire day before classification repair.
Recoverable page/scope/post errors and missing classifications are recorded,
independent work continues, and deferred acquisition/enrichment is repaired
under durable budgets afterward. Preserve ownership/database safety and request
accounting: do not blindly restart unknown requests or ignore lost claims.
Continue autonomously through required tests/review, deployment observation,
24-hour collection, enrichment recovery and requirement-by-requirement audit.

Execution model request: faster model. The native thread model override to
`gpt-6.1-sol` was accepted by the task tool; no separate worker or new goal was
created. Record served identity only when the runtime supplies evidence.

Historical authorization for the completed August 9 phase: the owner authorized
a data-only staging-to-production transfer, conditional on
all 1,660 Posts passing current ingestion/enrichment verification. Code delivery
remains on-request: no commit, push, application deployment, schema/service or
scheduler change. Production completion means independently verified imported
data and CollectionRun provenance on the currently deployed schema.

The separate 502 task remains explicitly held and G3-owned.

# August backfill verification and July 30 collection parity

## Plain-English Summary

The August 9 transfer and diagnosis are recorded below. The current authorized
phase implements, deploys and runs a July 30 backfill with the normal
harvester's relevant collection routes and shared enrichment. Success requires
3,800–4,200 genuine distinct posts and canonical translation plus classification
completion of at least 98.54525862068965%, the frozen current-day baseline.
These are acceptance checks, never instructions to pad or truncate valid data.

Acquire the full day before repairing classification failures. Continue
independent work after recoverable failures, retain paid-call history and use
the on-demand TwitterAPI and DeepInfra credentials. Verify the deployed source,
database records and application projections. Current author membership and
provider search results cannot prove perfect historical recall.

### Completed transfer scope

Verify that the saved staging test contains 1,660 correctly ingested August 9
posts, then bring the missing posts and their required translations,
classifications and extracted records into production. Preserve healthy live
records and their newer account metadata. Record where the copied data came
from; do not charge old model work as new provider requests.

Count overlap first, so staging and production totals are not simply added.
Compare hourly coverage and internal timestamp gaps with neighboring days to
see whether lower volume reflects missing stretches or broader search recall.
No new TwitterAPI or LLM request is authorized or necessary for this transfer.

## Owner requests and scope

- "are the 1660 posts correctly ingested? if so copy them to live db"
- Follow-up: inspect Aug9 (782+1660) versus other days; identify missing hours.
- Source staging job58111a25-7e6a-4f96-893f-142a6c4b58ca. Exact original window
  [2026-08-09T00:00:00Z,2026-08-10T00:00:00Z). Freeze its 1,660 unique IDs.
- Baseline product4e60a2f1/0089. G3 owns subsequent0090 and 502 investigation.
  Recheck actual schema before writes; query CollectionRun through job relations.
- Production baseline Aug9=782, including765 campaign members/763new/19old.
- TOUCH: a bounded operator export/import, required Post relation graph and
  existing collection bookkeeping, tests, private receipts and this plan.
- PRESERVE: existing healthy Post data, newer Account data, source publication
  and model provenance, G3/G5 work, full staging source, scheduled harvest/cursors,
  backlog, leases and other provider ledgers. Zero new/retired tables.
- Stop on identity/schema drift, failed semantic validation, inconsistent natural
  identities, active target claims, unexplained conflicts or unsafe references.
  Do not overwrite conflicts or copy raw numeric foreign keys between databases.

## Schema/writer/reader audit

Read core/models.py,0085/0088/0089 and shared backfill verification/publishers.
Post IDs and brand/taxonomy keys are stable. Account UUIDs need provider/native
identity reconciliation; classification judgments, literal artifacts and extracted
entities have database-local numeric keys that must be remapped. Do not copy
staging provider budgets, active jobs, auth/session or scheduler rows.
Export exact required graph after live verification and inspect actual populated
relations before finalizing table scope. Reuse shared completion_facts/verify_cohort
and application readers for before/after checks; provenance reuses existing
CollectionJob/CollectionRun/CollectionObservation.

## Execution and regression net

1. Re-read live source identity and exact membership under READ ONLY; require
   1,660 rows, all within Aug9UTC, nonempty text/authors/brands, canonical current
   translations and classification, plus required targeted extraction.
2. Freeze content/ID hashes and a scoped export on fuchitalee. Inspect dependency
   graph and natural keys. Compare IDs with production and hourly unions versus
   Aug7/8/10/11, with maximum gaps and per-brand/query evidence where available.
3. Implement the smallest repeatable copier against existing storage; dry-run
   without mutations. Test against disposable real PostgreSQL: numeric key/UUID
   collisions, quoted parents, empty optional edges, canonical lineage, existing
   healthy data preservation, active claims, transaction rollback and replay.
4. Obtain a scoped before-image of existing target rows and a recoverable export
   before production writes. Import bounded atomic batches with finite lock and
   statement timeouts. No normal global writer lock or pause while waiting.
5. Use current job-backed collection registration/fenced run operations for a
   separate transfer receipt; zero provider starts and accurate source metadata.
6. Verify every source ID now exists exactly once and is valid, compare required
   semantic graph, reconcile inserted/retained/conflict counts, independently
   recount Aug9 and preserve source/normal cursor/backlog state.
7. Stop owned tunnel/test resources and publish exact counts and coverage limits.

## Progress

Source job and1660 distinct observation IDs confirmed by compact staging SSH.
Direct staging psql is denied by IP allowlist; no allowlist changes. Large SSH
program and stdin were rejected without output; use existing SSH forwarding
transport and a private local operator environment. No production writes yet.


## Verified admission and rollback boundary (2026-10-16 08:34 UTC)

The source shared verifier returned `(1660,{})`. Frozen source export with
provider-account geography dependencies is
`~/.local/share/render-operations/2026-10-16-aug09-staging-promotion/cohort-export-with-geography.json`,
SHA256 `66bcaad500163949ab8fd28c38bf48f59df2b324e1af2a2724b5213602531769`.
The original source export remains intact. Source membership intersects 730 live
Posts; 930 are absent. Of the existing 730,727 are canonically complete and three
are untouched raw-only records with exactly matching text/native author/date and
brand sets:2086307348243767392,2086386865624756326,2086419983203205206.
Repair only their seven saved enrichment projection fields and attach their saved
canonical graph; preserve their native fields,metrics,author and fetched_at.
No overwrite of partial or current enrichment is admitted.

Production identity verified through an owned authenticated Render SSH tunnel:
database/current_user=pushinweight_shadow; session_user=pushinweight_ollija_20260814.
The role selection is existing service configuration. Staging uses a separate
owned tunnel; no IP allowlist or service environment changed. Production0089 is
observed; the copier uses job-owned execution relations and is compatible with
G3's planned0090 physical legacy-column removal. Stop on other schema drift.

`production-before-image.json` freezes all730 existing Post graphs and existing
provider-qualified Accounts,34,240,792 bytes, in the same private directory.
Healthy727 graph SHA256:
`fecc149605033b3e2a12c7cc456d19cbcde85395a7954674f8fc70ab98bfaf3f`.
Before-image includes relevant existing discovery candidate records. New candidate
anchors may refer to existing Posts; those additions do not authorize changing
existing candidates or canonical Post graphs. Preexisting Account rows and X
metadata are compared using a frozen set of Account IDs, excluding newly created
accounts. Every inserted scalar and mapped foreign key is read back and compared
against its intended source value inside the transaction.

A disposable PostgreSQL18 database at127.0.0.1:55482 rehearses the full1660 graph,
including the exact three raw repairs, numeric-ID collisions, conflicting Account
UUIDs, native-identity remapping, newer Account metadata preservation, canonical
translation/classification verification, forced mid-write rollback and safe replay.
An active target claim is separately rejected. Rehearsal caught missing geography
lookup mapping, shared-job ready-state admission and OneToOne/composite identity
handling before any production mutation; these were corrected and reverified.
Ruff passes. No application or harvest behavior is released by this operator copy.

Rollback: any failed identity, provenance, exact-row, canonical or preservation
check before commit rolls back all Post/child/job/run/observation changes. Sequence
gaps may remain and have no semantic meaning. After commit, retain source export,
before-images, exact930 inserted Post IDs and created Account/discovery IDs in the
transfer report. Do not run blind deletion. A corrective transaction must first
check no later writer has changed or referenced the affected records, remove only
owned evidence/dependency rows in reverse foreign-key order, restore the three raw
preimages, and remove copied Posts/global dependencies only when unreferenced.
Shared job/run history remains as an audited correction. Stop and use a forward
repair if concurrent users make reversal unsafe. No whole-database restore or
scheduler halt is implied.

## Search-coverage findings

All21 brands were included in frozen instructions. No staging results forStepFun
orEXAONE; comparison days have0–2 each, so those do not explain the volume deficit.
Most new staged brand links areDeepSeek430/MiniMax400; links overlap across Posts.
B1 continued beyond its initial80-page checkpoint to110 cursors/2184 raw results;
Qwen continued beyond30 to53/1043. All seven final scopes record drained/complete.
The20-result one-page step preserves/resumes a cursor and is not a20-post query
ceiling. Code explicitly requests Latest. Stage and production share the primary
six query texts, but stage used narrower windows and production a49.5h window.
A provider search-recall difference across window widths is plausible, not proved.
No new provider request was made to test it. The existing union has posts in every
hour (47–91); longest internal gap436s. Staging covers all96 quarter-hour bins.
This does not prove exhaustive X recall or equivalence to historical scheduled
harvest, which also has the A/list route. Expected post-copy Aug9 total1712.


### Additional search admission finding

An offline no-transport reproduction passes a simulated HTTP200 JSON
`status:error`/empty result through the current shared search iterator; it emits
an empty page with has_more=false and continuation_invalid=false. The generic
HTTP client validates HTTP status but does not reject provider-level search
errors. Therefore an error can masquerade as drained. Original raw search bodies
are not retained in these scope envelopes, so this is a demonstrated weakness,
not proof of the Aug9 cause. Do not change active provider behavior under this
data-copy operation; carry response validation and raw terminal-page evidence
into the next backfill work. The frozen queries all use min_faves:0/Latest;
there is no positive minimum-like filter explaining the deficit.

### Concurrent-profile guard correction — 2026-10-16T08:42Z

First production attempt finished full mapped-row/canonical checks at311.70s,
then the account preservation comparison rejected the commit. The outer atomic
transaction rolled back: independent read730source IDs present/0transferjobs,
so930new Posts and all receipts remain absent. No partial promotion occurred.
Read-only diff proves three preexisting Accounts refreshed followers_count,
followers_fetched_at,last_seen_at and their X favourites/media/statuses counters;
no BrandAccount/CompanyAccount differences. This was external live profile work,
not overwrite by the copier (which inserts only new Accounts).

Use PostgreSQL REPEATABLE READ for the one transfer transaction so preservation
checks read a consistent snapshot plus our own writes. Concurrent profile refreshes
remain committed and visible after the transaction; no locks on those existing
Accounts, overwrite, scheduler pause or error suppression. A second local database
connection updates a profile after the transfer snapshot starts: the snapshot stays
consistent and the newer profile survives after commit. This regression passes.
Keep all source/frozen-set/exact-row/canonical/native-field checks and abort on a
true write conflict. Remove a redundant complete preflight inside the final writer;
exact730existing IDs are checked cheaply before the unchanged internal admission.
Retain first rolled-back logs and both profile before-images in the private directory.


### Immediate latest-post diagnostic (separate live cohort)

The bundled read-only latest-N helper ran exactly once, no provider calls or
production changes. Result: status=unhealthy,regression_gate=failed,
acceptance_gate=failed; complete0/pending11/unhealthy9 of20. Commentary en and
zh_cn each0/20(0%); canonical lang_detected8/20(40%); non-zh-Hans text_zh_cn
6/6(100%). Nine flagged rows have missing commentary; one also lacks detected
language. Fresh pending is not counted as complete or failed. This helper checks
commentary, which is not a condition of the current literal-artifact/classification
completion_facts contract used for the staged cohort. Do not infer all current
translation outputs failed or change normal collection under this task.
JSON evidence, stage/reason details and exact immutable cohort are retained at
`~/.local/share/render-operations/2026-10-16-aug09-staging-promotion/latest-production-health.json`.
Ordered tweet IDs: 2110861141459271754, 2110861282588893541, 2110861288129896481, 2110861297780937074, 2110861313983521047, 2110861400667308211, 2110861421034828242, 2110861441616224322, 2110861589041885548, 2110861610814218300, 2111009562526392671, 2111008962841637212, 2111009127250227592, 2111010335352348901, 2111011664011386942, 2111010237285056639, 2111011760702452128, 2111008331892723725, 2111008843027116445, 2111008973365072080.
This observation precedes the Aug9 promotion commit; it is not a passed live-health
check or proof of an effect from this data-only operator. No retry or follow-up
provider/repair/normal-service action was launched from the diagnostic.


### Unequal brand-query coverage

The frozen query texts contain no dedicated EXAONE,Sakana,InclusionAI or
Nemo/Megatron name searches. Those selected brands rely on official-handle mention
terms in B2/B3. All21 being selected is therefore not proof that every brand has
equivalent keyword/author coverage. DeepSeek andMiniMax do have B1 name terms,
so this difference alone does not explain their much larger deficits. Keep
brand selection, actual query terms, normal A/list coverage and measured provider
recall as distinct facts. Offline comparison of all730 overlapping Posts finds
zero staged brand links absent in production; production has eight additional
links retained intact.


## Completed production data-only result

Committed at 2026-10-16T08:45:55.583016+00:00 in246.39seconds. Copied930new Posts and
repaired the exact three raw-only records with saved enrichment; all1660 source
IDs present. Preserved727healthy overlapping Post graphs, all staged brand links
and eight additional production links, and1125preexisting Accounts. New global
records:142Accounts/Xdetails and45discovery candidates; two new candidate anchors
point to existing healthy Posts without modifying existing candidates. No quote
parents were lost. Full copied scalar/mapped-FK read-back and canonical translation/
classification verification passed inside the atomic transaction.

Separate Render CLI READ ONLY SQL confirms1660/1660present,0missing, Aug9UTC1712
(up from782), completed CollectionJob67c854fa-2e8e-41a5-a461-468a3d058601 and
successful CollectionRun17b34968-3c7d-4c81-9a6d-08df9747e4c9, selected/success/
observations1660 each,request_count0. A separate fresh ORM READ ONLY transaction
independently revalidates all1660 canonical results with zero errors, zero native
author/provider identity mismatches and the same1712 daily total. Brand totals
now DeepSeek715/MiniMax579/Qwen406. Source staging verifier also reran1660/0errors.

Private receipts: production-copy-result.json,independent-post-copy.sql/.txt,
independent-semantic-verification.json and complete source/before-images/created
global-ID provenance in the private operator directory above. TwitterAPI0/LLM0
new requests; no copied/rewritten provider cost history. ExistingCollectionJob/
Run/ScopeRun/Observation reused;zero tables added or retired. No code commit,
push,app deployment,schema,service,cron,cursor/backlog or held-chart mutation.
Ruff and whitespace checks pass; full real-data PostgreSQL rehearsal, rollback,
collision, replay, raw-repair, active-claim and concurrent-refresh checks passed.
Separate latest-feed diagnostic remains failed(0complete/11pending/9flagged),
principally commentary fields; its observation is not claimed as a passed gate.

Full historical recall remains unproven: current name/mention/list differences,
broad versus narrow-window return differences and provider-error-as-exhaustion
weakness need bounded diagnosis before a month run. Acquisition coverage is not
established by canonical enrichment success or the copied1712 total.

Cleanup: own local test PostgreSQL55482 stopped; staging SSH forward already
closed by the remote service. Stop the remaining owned production SSH forward
after the independent reads; retain dirty operator worktree/source for review.

Owned test PostgreSQL and both SSH forwarding ports confirmed stopped at 2026-10-16T08:50:05.509141+00:00.
No linked worktree removed; local operator source and receipts retained.


## August9 undercount root-cause investigation — 2026-10-16T11:34:13.499086+00:00

Owner asks why Aug9 backfill rates differ from Oct15; diagnosis endpoint only.
Reuse this plan and isolated worktree. No issue of record, no code release/DBwrite/
schema/scheduler/normal-service mutation. Compare saved known positives, exact
query/scopes/provider page evidence and pipeline rejection counts. Volume
differences alone are not a root-cause proof. Initial hypotheses: incomplete
query/route coverage, provider pagination/search recall, post-fetch filtering or
persistence. Explicitly separate them; do not call all exhausted queries an
exhaustive census. Start with existing evidence and read-only production data.
If a provider probe is necessary to distinguish causes, prepare and announce a
small fixed on-demand-only budget and save raw responses before interpretation.
Prior no-provider constraint applied to the completed data transfer, not this
new owner-requested API/collection diagnosis. No LLM calls are needed.
Local untracked copier/plan cannot cause historical API retrieval differences;
shared code is unchanged in this worktree, so no dirty-tree stash experiment.

### Confirmed acquisition defects and limits — 2026-10-16T12:00Z

Diagnosis completed against frozen queries, read-only production presence and
raw on-demand provider responses. Relevant attribution/cycle/backfill/policy
modules are byte-identical between this worktree's4e60a2f1 and deployedaf7ed771.
Evidence directory: `/Users/fuchitalee/.local/share/render-operations/2026-10-16-aug09-staging-promotion/recall-probe-20261016T114209Z`.
`findings.json` states measured causes/limits, `evidence-sha256.json` seals the
raw pages, physical-request ledger, outcomes, DB presence and offline replay.

1. **Shared attribution loses Latin brand names adjacent to Chinese/Japanese.**
   `x_monitor/attribution.py:compile_keyword_index` wraps Latin literals in Unicode
   word boundaries. CJK letters are Unicode word characters, so `DeepSeekの`,
   `比deepseek` and `高速MiniMax` do not match. Real `_build_brand_index` with
   captured227production keywords validates active-policy coverage; real
   `CycleRunner._attribute_items` then sets `_unattributed`, and `run` drops those
   items before persistence. A dummy DB backend and forbidden network transport
   keep replay offline. The unchanged frozen B1 query returns82noon-hour posts;
   replay keeps69, drops13, and those exact13 are absent from production. Nine
   have clear body brand names (sixDeepSeek/threeMiniMax); four others have no
   explicit body name and are not counted as valid false negatives. This defect
   is shared with normal harvesting, not specific to the batch adapter.
2. **GLM queries require English context even for unambiguous model names.**
   Frozen C3 and policy require `llm OR model OR api OR agentic OR huggingface`
   beside the GLM-family group. Controlled fully drained Aug9day searches return
   64with context and225without;161bare-only,111of those absent from production.
   A conservative73bare-only bodies contain explicit GLM4/5/6 names, Zhipu,
   ChatGLM, Z.ai or 智谱;41are absent, manually reviewed as relevant and all41
   acquire a GLM brand through the real attribution replay. Do not count unrelated
   acronym matches as valid. Exact frozen fullC3 at14:00–15:00UTC returns4;
   bareGLM returns21 and includes clear missing AI posts. This gate also exists
   in normal policy; other normal routes can collect posts it excludes.
3. **Route completeness and provider recall remain separate.** Backfill excludes
   normal CallA/list and RARE_EXTRA; an actualOct15cycle has A18of44new inserts,
   proving it contributes, not its whole-day share. Two original known posts
   (2086263615745888487 DeepSeek and2086487494422335872 MiniMax) remain available
   by ID lookup but absent from bare keyword and narrow author search controls.
   Positive author controls succeed. This demonstrates a provider search limit;
   deletion, shadowban or a particular backend index cause is not observable.

Controlled negative findings: min_faves:0 versus no engagement filter yields
identical29DeepSeek/23MiniMax IDs in matched hours. All35separateDeepSeek noon
results appear in82mixedB1 results. Every tested narrow GLM result appears in
the corresponding day query: window-width loss was not reproduced. Tested
searches followed all continuation pages to provider exhaustion, so these misses
are not explained by a20-post total cap. The independently reproducedHTTP200
provider-error false-completion weakness remains unproved historically.

**Accounting:**59physical request reservations/58capturedresponses/1unknown SSH
outcome, no automatic resend of unknown request011. Known responses estimate
8790credits/USD0.0879, plus USD0.003held for the unknown at20results. All remain
inside original60-request/USD0.25/8MiB bounds; no cap or attempt reset. No LLM,
DB writes, ingestion, service/cron/schema change or application release. No
owned probe/controller remains active. Raw returned counts include duplicates
across controls and unrelated search matches, and are not recovered-post counts.

**Recommended next implementation / regression net (not performed):** repair
shared mixed-script word boundaries while preserving embedded-English-word
rejection in `x_monitor/attribution.py`; extend existing `tests/test_attribution.py`
and real backfill caller/ORM fixture in `tests/test_backfill_pipeline.py` with
the captured CJK false negatives, quotes and negative controls. Treat unambiguous
GLM version/organization names separately from ambiguous bare `glm` context in
policy/spec generation; pin final emitted queries in
`tests/test_specs_from_policy.py` and the real caller. Review normal A/list
coverage explicitly rather than asserting B/C parity. Strengthen existing
`tests/test_apify.py` to rejectHTTP200provider-error/schema failures without
advancing cursors. Acquisition acceptance needs fixed known positives and
per-stage received/attributed/rejected/persisted reconciliation; canonical
enrichment of saved posts plus drained scopes cannot establish recall.

Confidence high for the two reproduced software mechanisms and the observed
search/lookup mismatch; incomplete for the total amount missing onAug9. No
percentage of the Aug9/Oct15 difference is claimed explained. Source fix and a
recovery run remain separate from this completed diagnosis-only request.

### Owner correction: explain differential loss, not shared exclusions — 2026-10-16T12:13Z

Owner rejects shared matcher/context gates as an explanation of departures from
the harvester, and doubts CallA explains the scale. Current task resumes diagnosis:
compare the actual Oct15 deployed revision2c43b4f0 with backfill product4e60a2f1,
quantify route contribution, and reconcile the same known-original post population
through query eligibility, provider return, attribution, persistence and cohort
membership. Shared defects are findings, not differential root causes. Cross-date
traffic levels do not establish the expected Aug9 population. Initial scoped Git
diff of cycle, attribution, API client, config/policy/spec generation and backfill
command between those revisions is empty. Existing59/60physical provider probe
reservations remain59/60, including one unknown not resent; no budget reset or
new API probe yet. Reuse existing evidence and read-only queries first. No code
release, ingestion/production write, LLM, schema, service or cron mutation.

Same-population replay now keeps all930staging-only and730overlapping source
Posts with the real production keyword index/caller. It keeps2089of2094old
harvested campaign misses and all855refound references. These shared filters
therefore cannot explain the differential loss. Current-list membership covers
only19of2094misses, so CallA is unsupported as dominant (historical membership
unknown). Source raw counts/keep ratios and provider-returned ID membership need
matched wide/narrow testing.

### Daily harvester route reconciliation — 2026-10-16

Read-only Render logs filtered to `HARVEST_SUMMARY` contain91cycle summaries
across the full Oct15UTC day. Normal CallA returned731items, kept664, inserted
663, updated1, and recorded28LLM drops. This confirms material platform-wide
CallA activity, but the summaries do not split those results by brand or retain
the full raw result IDs. The Oct15 query's24 `author_account` mention rows in
the four-brand union are only the official-account attribution marker; CallA
also has staff-candidate paths that do not create that marker. Therefore24 is
not a valid upper bound on CallA's four-brand contribution, and the preceding
statement that it ruled CallA out as a dominant cause was too strong. Existing
current-list membership (19 of 2,094 old misses) is also not historical Aug9
membership evidence.

The code confirms a direct route difference: the backfill adapter allowlists
only B1/B2/B3/C1/C2/C3; normal scheduling also synthesizes CallA, and normal
cycles run RARE_EXTRA. RARE_EXTRA used 20-result/one-page calls by design. A
backfill physical request also sets20results/onepage, but persists its cursor
and loops for more requests; it is not a single-20-result cap for the whole
scope. Frozen-query probes were fully drained, so the per-request page size by
itself is not evidence of truncation. Production config permits much deeper
pagination in a normal cycle, while scheduled tip-first work may deliberately
take one page per route before backlog work.

Conclusion: omitting CallA and RARE_EXTRA is the clearest confirmed
backfill-versus-harvester acquisition difference. It can plausibly explain
some missing posts, but the available daily logs cannot assign their
brand-level unique contribution, and Aug9's historical CallA list membership
is unavailable. Aug9-versus-Oct15 traffic is not a controlled same-population
comparison. No evidence supports claiming that CallA alone explains the
shortfall, or that the 20-result page setting alone caused it. A complete
retrospective decomposition is unavailable because full per-call provider
result-ID receipts were not retained for the original normal harvests. No
additional provider calls or database changes were made for this reconciliation.

The owner's renewed explicit request to find the differential cause starts a
distinct bounded window-width measurement, announced before launch. It does not
reset the completed earlier probe: its59reservations/oneunknown/estimatedcost
remain immutable. New phase admits at most180additional physical calls,
USD0.60estimated credit ceiling (20posts/page usual maximum impliesUSD0.54),
64MiBresponses and600active seconds; retries0, unknown outcome stops, strictly
on-demand key, single sequential caller. Combined request ceiling239including
the original59. Compare exact frozen B1 over Aug9noon and original
Aug8T04:15–Aug10T05:45UTC, Latest, normal limit20, fully follow provider cursors.
Retain raw payloads before parse, raw IDs, duplicate/continuation/order/time
evidence and known-stage/production membership. No recovery/ingestion/model
calls, schema, scheduler or service mutations are authorized by this measurement.

### Compounding correction: the width probe was capped — 2026-10-16

The completed private receipt under the Aug9 promotion directory,
`width-probe-20261016T122231Z/summary.json`, records 174 new reservations and
174 captured responses, no new unknown outcomes, USD 0.51645 estimated known
cost, 16,039,421 response bytes and 289.97 seconds. Cumulative reservations are
233, preserving the original unknown outcome. The one-hour control drained
after 6 pages / 82 unique posts. The 49.5-hour query returned 168 pages / 3,360
unique posts and stopped at `page_cap`, not provider exhaustion. It does not
prove wide-window recall equivalence or exhaustion. Earlier wording about
drained frozen searches applies only to the specifically drained walks,
including the six archived Aug9 broad-window walks. No further paid probe was
run to compound these findings.

## July 30 continuation — lessons incorporated before implementation

### Plain-English Summary

Prepare one explicit 24-hour window, July 30 2026 00:00 UTC through July 31
00:00 UTC, for the intended production database. Include Call A and RARE_EXTRA
alongside the applicable B/C searches, using the normal harvester's collection
rules and shared processing code. Keep resumable batch execution rather than
recreating a day as 96 scheduled cycles. A broad date range still requires
following provider pages; one request is not a month's dataset.

Completion requires evidence that the selected routes actually ran, returned
IDs reconcile to distinct saved posts, and applicable enrichment published
correctly. The active goal requires 3,800–4,200 genuine distinct posts and
canonical completion at least 1,829/1,856; preserve every valid post even if the
result falls outside that range. Current
policy and account membership cannot reconstruct precisely what a historical
policy would have found; provider search may not return every eligible post.
Report those limitations without claiming full recall from a healthy cohort.

### Owner decisions and current endpoint

- Owner requested adding Call A and rare and double-checking scope against the
  normal harvester, then explicitly requested ce-compound first.
- Current endpoint: deployed code plus the actual July 30 production run and
  verified goal criteria. The completed ce-compound documentation phase preceded
  the owner's explicit implementation-through-production authorization.
- Intended data destination is production. Record exact database and candidate
  identities before launch. Completed Aug9 data-transfer authority is retained
  as history. The current goal explicitly authorizes code delivery through the
  staged route and the July 30 production batch.
- Select all 21 intended brands, deriving and recording their exact names from
  the current policy. Use the half-open UTC interval `[2026-07-30, 2026-07-31)`.
- Use `TWITTERAPI_IO_ON_DEMAND_API_KEY` and `DEEPINFRA_ON_DEMAND`, resolved by
  existing supported loaders/Render configuration without exposing values.
  No scheduled-key fallback, shared Anthropic credentials or Claude inference.
- Ordinary DeepInfra calls remain selected for timely results. Track physical
  requests, tokens, reported cost, reservations and unknown charges. Set
  concurrency from measured Render/database capacity; preserve cumulative
  budget, deadline and attempt limits across restarts. No provider Batch switch.
- Preserve scheduled credentials, live cursors/backlog, leases, cron and G3's
  shared schema. No new or retired tables are planned.

### Lessons and required evidence

Read the [coverage learning](../solutions/workflow-issues/2026-10-16-131500-backfill-coverage-and-completion.md)
and the existing
[August production month-run notes](/Users/fuchitalee/development/pushin-weight-v2/.worktrees/ops/august-production-backfill-20261015/docs/plans/2026-10-15-064852-ops-august-production-backfill-20261015-plan.md#month-long-next-run-lessons).
The latter contain prior-run tests and job receipts, not checks of the next
candidate. Several repairs were activated only inside specific jobs; establish
their presence in the exact candidate before relying on them.

| Prior lesson | Next-run requirement |
| --- | --- |
| Shared CycleRunner did not imply equal scope; the adapter allowed six B/C routes. | Compare actual scheduled planning/execution with frozen backfill instructions. Include A, applicable B/C and RARE_EXTRA; account for flags and every other enabled discovery route. A missing required route must fail preflight. |
| Official-account markers did not capture all staff results; current membership was not historical membership. | Reuse official/staff role resolution, attribution and staff relevancy gates. Freeze the role/membership evidence and its observation date. Do not use marker counts as route totals. |
| Scheduled author exclusions depend on `scheduled_exclusions`; backfill currently plans without that flag. | Compare final emitted queries and effective exclusions. Match selected current policy unless an explicit historical-policy difference is recorded. Do not silently widen queries to hit 4,000. |
| One-page steps resumed successfully; a later wide probe stopped at a cap. | Preserve exact page/cursor checkpoints and terminal reasons. Cap, deadline, error, invalid continuation and unknown outcome remain incomplete. Record per-route pages and effective bounds. |
| HTTP 200 provider errors could resemble empty pages; historical occurrence was unproved. | Test error-shaped/malformed successful-HTTP responses at the real client boundary. Error must not advance a cursor or mark a scope drained. Keep this defect separate from the unproved cause of August loss. |
| Drained searches and healthy enrichment did not prove recall. | Trace known positives through eligibility, provider return, matching, persistence and membership. Compare both callers on identical inputs; reconcile raw appearances, unique IDs, rejects and writes. |
| Regrouping pending members could strand an already-paid classifier packet. | Replay the original complete input packet/catalog, publish only pending members through shared publishers, then prove idempotent restart with a complete sibling unchanged. Reuse saved valid replies before another paid call. |
| Parser acceptance did not establish canonical publication. | Verify stored translations, classifications, applicable extraction and application projections, including semantic rejection and rollback. Keep negative controls for quantities, URL/CJK adjacency, exact machine-only text and incompatible taxonomy semantics. |
| Unknown sent calls, unsent reservations and invalid replies required different recovery. | Preserve physical history and costs; resume exact unsent requests; keep unknown outcomes explicit. Any authorized replacement retains prior unknowns and cumulative limits. No automatic identity or attempt resets. |
| Adding cohorts and counting later imports overstated baselines. | Deduplicate native IDs. Report existing overlap, inserts, updates and final union. Distinguish publication date from first ingestion date in baseline queries. |

### File scope and shared-storage design

Inspect the fresh candidate and schema first. This compounding tree is
4e60a2f1; G3 changed shared storage after this checkout. Read `core/models.py`,
relevant migrations and current writers/readers before selecting fields. Reuse
CollectionJob for instructions, CollectionRun for attempts, CollectionScopeRun
for committed scope progress and CollectionObservation for evidence/membership.
Post and canonical enrichment remain in existing storage. Coordinate with G3
before any shared-schema change; none is justified or planned here.

Expected bounded implementation files, subject to that inspection:

- `monitor/backfill_collection.py`, `monitor/backfill_resources.py` and
  `monitor/management/commands/backfill.py`: route admission, immutable
  instructions, accounting, resume and reporting.
- `monitor/cycle.py` and its existing planning/author/rare helpers: shared
  collection behavior and publication. Extract reusable hooks where needed;
  do not duplicate matching, author roles or rare gates in an operator script.
- `x_monitor/apify.py`: the confirmed response-boundary weakness if reproduced
  by regression; preserve scheduled credential-purpose enforcement.
- Existing enrichment/replay helpers and tests: first establish which prior
  job-local repairs are present, then include only required corrections for
  the next candidate's real publication and restart checks.

Adding call IDs alone is insufficient. The current collection adapter excludes
LLM/discovery settings from its digest and admits zero model calls. Call A
staff and rare decisions can require inference. Design their on-demand
accounting, input identity and resumability before enabling them; include all
active decision settings in frozen definitions. Reuse rare gating/persistence
while keeping historical ownership separate from scheduled slot reservations.
Do not consume/reset live deduplication state accidentally. Scheduler cadence
and per-cycle budgets are distinct from collection-policy equivalence.

The legacy quote-body collection route was removed from normal harvesting;
do not revive it for current-policy parity. Treat shared matcher/GLM policy
defects separately from explaining differential collection loss. Any shared
correction must reach both callers intentionally, not silently expand only
backfill queries.

### Regression net and execution order

1. Inspect the exact candidate, shared schema and enabled policy. Produce the
   route matrix and frozen query definitions before paid work. Verify intended
   production destination and credential purposes without printing secrets.
2. Extend existing tests for required route admission, brand/author scope,
   effective UTC bounds, role/rare gates and on-demand model accounting. Include
   an omitted-route failure and preserve normal scheduled behavior. Exercise
   deep pagination, interruption/resume, duplicates, capped/unknown/error
   outcomes and atomic page publication.
3. Compare actual scheduled and historical callers on identical captured
   fixtures. Reconcile raw appearances/unique IDs/rejects/writes/observations.
   Start with `tests/test_backfill_pipeline.py`, `tests/test_apify.py`,
   `tests/test_specs_from_policy.py` and related caller tests, adapting to the
   fresh tree instead of inventing a parallel implementation.
4. Test partial saved-response replay, unchanged complete siblings, retained
   costs/attempts, semantic publication failure, cache-only progress and restart
   through real database publishers. Use existing direct-enrichment/cached-replay
   and translation-invariant tests. Require PostgreSQL where correctness depends
   on transactions or database constraints; skipped checks are not passed.
5. Before a later launch, record exact image/source identity, current Render
   resources, bounded requests/cost/time and selected concurrency. Reuse valid
   prior checks only while their relevant code, fixtures and environment match.
6. An authorized 24-hour run persists progress through existing collection
   records. Continue independent work despite post-level failures, retaining
   deferrals for final review as previously requested. Stop unsafe execution on
   lost ownership, provider/auth failure, schema/database identity mismatch,
   exhausted budgets or nonprogressing pagination. Those stops are not success.
7. Close with separate verdicts for scope parity, enumeration, returned-to-stored
   reconciliation and canonical enrichment. Report distinct totals by route,
   hour and brand, overlap/rejections/unknowns, phase durations and provider
   usage. Under/over 4,000 requires explanation, not padding/truncation.
   Month-scale estimates follow measured acquisition and enrichment work rather
   than multiplying scheduled 15-minute cycles.

### Compounding verification

Full ce-compound research and semantic review ran inline under the repository's
Task/Subagent mapping. One relevant prior session and existing month-run notes
informed this continuation. The learning passed frontmatter/schema,
links/commit references, arithmetic and source/receipt checks. One X post
backfill vocabulary entry was added; AGENTS already makes solutions and
CONCEPTS discoverable. The old July pipeline-wiring learning needs a narrow
future refresh and is explicitly identified as historical in the new learning.
No application tests, paid calls, production writes, schema changes or deployment
were performed during this documentation phase.

### Production execution and recall reconciliation — 2026-10-16 15:23 UTC

Production web and harvest are observed live at `99461050b7d283503dde9cffec1b2de920666e35`.
The first full-day collection saved 1,552 distinct eligible Posts after all eight
raw routes exhausted; 192 physical TwitterAPI starts and 282 collection model
starts (7 staff, 275 Jev) are retained. Its enrichment stopped before inference
because an authenticated database login has a different effective default role.
The deployed fix checks `session_user`, preserving the frozen login/database
pins. Four real PostgreSQL role-switch regressions failed before the correction;
90 tests, including 71 required PostgreSQL tests, passed afterward.

Resume Render job `job-db93nic9v7es73ee1sm0` uses the same immutable manifest,
CollectionJob `4808e70c-7f1a-4ceb-a5e6-4090d6618513`, original budgets and
CollectionRun `6471ab7d-66fa-4079-a9e0-891c4e7302f7`. No Twitter searches were
repeated by this resume. At 15:16 UTC, 582 base/targeted model starts had 581
returned responses and 77 durable translation/classification successes. This is
progress, not the goal result. Direct concurrency remains 32 and the on-demand
DeepInfra key is used. Peak observed memory so far is 193.39 MiB on 512 MiB.

A controlled identical-query B1 search for July 30 12:00–13:00 UTC returned
84 distinct raw IDs, while the original full-day B1 enumeration contained only
3 for that hour. Of 57 eligible stored Posts, 35 were absent from the original
cohort. Its shared CollectionJob `d8d24ec9-fccf-4cfb-acfc-3cb0e65f1873` completed
with 6 physical API starts and no model calls. This proves a wide-window recall
omission; it does not establish an undocumented provider cap or full recall.

Reconcile all 24 hours for the six unchanged B/C queries through the existing
`x-backfill/v1` adapter and normal shared Post writer: 144 input scopes in one
additional shared CollectionJob, retaining the exact original query strings,
exclusions, brands and UTC day. A and RARE_EXTRA have already been enumerated.
The job has a fixed 17:30 UTC deadline, 200 requests/600 seconds per attempt,
32 MiB/100,000-item attempt bounds, at most 20 attempts, and 1,000 additional
physical API starts (estimated ceiling USD3.00), with zero model allowance.
The cumulative API baseline is 198, including the six control calls; no prior
history or budget is reset. Ordinary-writer contention waits before claiming a
new attempt. Authentication/payment/rate-limit failures retain checkpoints and
stop the unsafe attempt; independent recoverable scope work can continue.

Storage audit confirms reuse of CollectionJob instructions, CollectionRun
attempts, CollectionScopeRun cursors/receipts and CollectionObservation typed
Post membership. Existing Post and PostEnrichmentState writers remain shared.
No tables or migrations are added or retired. Additional members must be
audited as a distinct union and enriched under the retained aggregate budget
after checking existing paid ownership; do not send duplicate in-flight work.
The 3,800–4,200 genuine-Post and 1,829/1,856 canonical completion criteria remain
unchanged. Retain all valid Posts if enumeration exceeds the expected range.

Normal cron was not paused or reconfigured. Its 14:30 tick skipped because the
backfill held the shared writer lock. The 14:45 tick reported 31 inserts but
degraded coverage; exit zero is not a healthy-cycle claim. The existing lock
still covers a provider page and its write, so month-scale writer fairness
remains an explicit unresolved issue. Observe a new normal cycle and durable
inserts rather than assuming the parallel jobs leave harvesting unaffected.

At 15:33 UTC the hourly job completed all 144 scopes without scope errors,
using 415 new API starts and zero model starts. Its own distinct membership
is 1,839; the original/control/hourly union is 1,899, not the sum of overlapping
job memberships. The retained physical API total is 613. The expected 4,000
has not been demonstrated, and all genuine results remain retained.

Next compare the six literal B1 OR branches individually for the same control
hour, July 30 12:00–13:00 UTC. Derive the brands and query text with the existing
policy spec builder and query renderer; assert the full rendered B1 query
matches its frozen original and each isolated branch is a literal substring.
Retain the exact engagement and excluded-author suffix. This narrows queries
to existing branches, without introducing aliases or broadening collection
scope. Reuse the shared adapter/writer and collection records, with 100 new
API starts (estimated ceiling USD0.30), zero model allowance, 600-second attempt
and fixed 17:30 UTC deadline. Baseline all 613 prior calls and compare returned
IDs to the completed combined one-hour scope. Do not repeat the completed
hourly job. This control tests an additional recall mechanism; its completion
is not evidence that the numerical or enrichment goal has been met.

The branch control completed at 15:34:50 UTC (Render
`job-db947nqjnfac73agem8g`, CollectionJob
`62af53a0-60e6-48be-a576-6bfea0c7a3cd`): 14 physical API starts, zero model
calls, all six branches complete. Their distinct union is exactly the same
84 IDs as the combined one-hour B1 search; zero novel eligible Posts. This
control supplies no reason for a larger branch-isolation sweep. All four jobs
together have 627 physical API starts, counting requests once rather than
adding each job's imported cumulative baseline.

The 15:36:57 read-only raw-receipt census found 3,619 distinct received IDs
across all four jobs, including rejected and rare-inbox results, with no
native-ID timestamps outside July 30 and nonzero results in every UTC hour.
The six hourly routes have raw counts B1=1,716, B2=1,029, B3=123, C1=541,
C2=85, C3=161. Only B1 materially differs from the original full-day walk
(1,095); the other routes differ by at most five appearances. Original A=269
and RARE_EXTRA=275 remain retained. Raw search results are not automatically
eligible Posts, and these observations do not prove a complete X census.

The distinct stored union remains 1,899, all inside the UTC day. At 15:35 the
canonical verifier proved 516 translations, 500 classifications and 500 both;
the frozen 98.54525862068965% rate would require 1,872 of this cohort. Continue
the existing original enrichment job, then process additional incomplete
members from the completed hourly job after outstanding paid ownership has
drained. Deduct all prior reservations and starts from the original aggregate
USD25 base/50,000 model-start/deadline allowances before allocating a supplement;
never reset budgets, hide unknowns, steal active calls or resend healthy overlaps.
The 3,800–4,200 target remains unproven and unmet; keep the goal active while
enrichment and verification can still make concrete progress.

### Enrichment continuation — 2026-10-16 16:00 UTC

The original resume job remains authoritatively running. At 16:00 the durable
ledger has 948 translation/classification successes, 2,589 model starts,
2,587 returned responses and zero ambiguous requests. The 15:44 spend audit
counted 2,019 registered model rows, USD2.777242 reserved and USD0.600438 in
provider-reported cost estimates; 282 collection model starts remain separately
retained. These estimates are not a provider invoice. Mean database send-marker
to saved-reply durations were 10.228846 seconds for translation and 25.482359
seconds for classification, with maxima 89.717293 and 44.709833 seconds. The
duration includes transport and controller persistence. Wave barriers wait for
their slowest request, so measured average call time alone understates runtime.

One exhausted classification was inspected from actual saved packets:
`2082732492084428850`. Rejected replies put catalog-tracked Qwen/Wan into the
untracked promotion list; another hallucinated MiniMax absent from source.
Later paid pair `46897`/`46898` has the same exact user packet and a newer input
fingerprint, but the member was not processed after earlier-input deferral.
Both later envelopes pass the shared DeepInfra parser. A zero-inference replay
through `replay_rejected_classifier_packet` is prepared for after the original
controller terminates and shared drain/claim guards pass. Canonical publication
is still unproven. If rejected, diagnose that actual failure before using the
existing corrected-input recovery helper with an immutable feedback spec and
the same retained policy, history, deadline and spend limits.

A guarded supplemental executor and read-only allocation builder are prepared
for the completed hourly job; neither has been launched. They reuse
`execute_enrichment`, `advance_targeted`, shared publishers and the original
campaign's controller lock. Remaining USD25/model50,000 allowances must deduct
all earlier registered rows/reservations and collection starts. Freeze current
membership/configuration/source pins only after the original controller is
terminal. Healthy overlaps must be preserved, and unfinished original work
must receive cause-specific repair rather than fresh implicit retry counters.
Historical deferral evidence alone is not a current-health verdict: an obsolete
fingerprint may remain exhausted after a later corrected result succeeds. Use
canonical persisted facts and current targeted role health for that decision.
No new application source, schema, deployment, API or model request was made by
these preparations. All current paid work remains with the existing job handle.

At 16:09, a direct read-only production count confirms all 1,899 July30 Posts
are attributed and represented in CollectionObservation; there is no larger
unrecorded cohort hidden by the membership audit. The retired local SQLite
archive and run folders have no July30 data. A read-only staging Render job
`job-db94neajnfac73aihurg` succeeded and found zero July30 Posts. Staging's
external IP allowlist was preserved; no database access rules were changed.

One final bounded acquisition control compares the same B1 12:00–13:00 UTC
query with its four 15-minute subranges. The existing one-hour combined and
six-branch controls both found the same 84 distinct raw IDs. The new control
uses the shared v1 collection adapter, unchanged query/exclusions/brands,
50 physical starts at most (estimated USD0.15 ceiling), zero model allowance,
300-second attempt and unchanged 17:30 UTC control deadline. Its cumulative
API baseline is 627. Further full-day splitting requires actual novel-result
evidence; this control does not reinstate scheduled slot waits or inline LLMs.

The quarter-hour control completed successfully at 16:11:33 UTC: Render
`job-db94p1c9v7es739hg0b0`, CollectionJob
`524b9bbb-0d3a-44b4-b32b-6fa8c029feb0`. All four scopes drained with 10 physical
API starts, zero model calls, 84 raw distinct IDs and 57 eligible Posts. Both
novel raw and novel eligible counts are zero. Total physical API starts across
the five genuine collection jobs are 637; their distinct stored union remains
1,899. Do not launch a larger quarter-hour sweep on this evidence.

The 16:13 read-only canonical audit confirms 1,265 complete translations,
1,249 complete classifications and 1,249 complete for both (65.77145866%) from
all five jobs, with all 1,899 inside the UTC day. The same frozen rate requires
1,872 completions for this denominator; count still falls below 3,800–4,200.
The original Render enrichment handle remains running, with 3,261 model starts,
3,258 returned responses and no ambiguous requests at that snapshot. Full-day
collection, current database count, canonical enrichment and hypothetical X
completeness remain separate claims; none redefines the owner goal.


### Source quantity validation and saved-reply recovery — 2026-10-16 16:40 UTC

The original enrichment controller `job-db93nic9v7es73ee1sm0` is now
succeeded (16:31:15 UTC), with 3,803 saved model starts/replies and no ambiguous
requests. Durable original membership is 1,552: 1,544 translations plus
classifications succeeded, seven classification-pending and one translation-
and classification-pending. Job success does not prove the numerical goal.

One fixable failure is reproduced from six actual saved translations of Post
`2082845127593066980`. All preserve the source's 100-trillion-token study as
100万亿/100兆. The source-only quantity validator recognized the price's
million-token denominator but missed hyphenated and output-qualified counts,
therefore rejected all six valid replies. Fix only
`x_monitor/translation_invariants.py` source recognition, with regression nets
in `tests/test_translation_invariants.py` and `tests/test_backfill_cached_replay.py`.
Preserve the paid prompt's protected spans/instructions, configuration pin,
source fingerprint, URL/handle/identifier masking and magnitude/unit rejection.
Preserve existing whitespace shorthand recognition. Add no tables or migrations;
reuse OriginalContentCall evidence, shared revalidation and canonical publishers.
No query/credential/model/policy/schedule or existing frozen instructions change.

Red-before evidence: five quantity positives and the real PostgreSQL saved-
translation recovery failed against the old validator; six negative controls
passed. Green-after: 157 focused tests (51 required PostgreSQL, zero skips/errors)
and 66 literal tests; final whitespace-compatible rerun 154 passed (16 required
PostgreSQL, zero skips/errors). Django check, scoped Ruff and whitespace check
pass. Offline all six actual paid replies fail old/pass new, without requests.
Focused review is serial inline under the owner's AGENTS task mapping; zero
independent reviewers or external model reviews. No confirmed finding remains.
A tab/newline compatibility issue found in review was repaired and retested.
Review receipt: /tmp/compound-engineering-501/ce-code-review/20261016-163654-hyphen/review.json.

Release through the existing staged route; verify the exact candidate source
and six actual replies on staging read-only with zero provider calls, then the
same production web/harvest revision. Leave the now-terminal original job and
its complete paid history intact. After original claim/request drain, replay
selected valid saved classifier/translation replies; use existing bounded
corrected-input recovery only for actual remaining contract errors. Original
USD25, 50,000 model-start and deadline allowances remain aggregate ceilings.
Then enrich the additional 347 genuine members from hourly reconciliation,
without recollection or resending healthy overlaps. Keep all 77 rare decisions
in their actual review state. No forced decisions to obtain the desired count.

A fresh ordered latest20 cohort was frozen at 16:26:12.274418 UTC; follow up
those exact IDs once no earlier than 16:56:12.274418 UTC. Initial helper result
is unhealthy; do not present it as green or replace the cohort. Canonical
current-day checks remain separate from the helper's legacy commentary facts.
The stored July30 union remains 1,899, below the 3,800–4,200 count requirement.


At 16:43:06 UTC `14a0b27b91227414fae884d7230fb64858417758` is LIVE
on production web and harvest, with login HTTP200. Staging read-only job
`job-db956o6i0phs73cc0od0` proved all six actual saved replies valid, wrong
magnitude rejected, paid prompt unchanged and three matching source hashes,
with zero provider calls/database writes. No cron was paused.

The first private cache launcher `job-db9588dg1s2s73f2ltg0` failed before
its lock or writes because the clients are frozen dataclasses. Corrected
only the private launcher with dataclasses.replace, verified both real client
factories offline and unchanged request identities. After confirmed terminal
failure, uniquely receipted job `job-db9594qjnfac73akfmp0` succeeded
16:45:56 UTC: four saved classifications published and two translations
reopened. All 3,803 physical model rows/starts and USD5.402086 reserved are
unchanged; cached usage remains old paid usage, never a new start.

Bounded corrected-input job `job-db959pk9v7es739j7dp0` succeeded
16:48:09 UTC. It froze the remaining four posts, exact failed-call IDs,
source fingerprints, feedback and unchanged configuration/policy into the
existing CollectionRun before new starts. All eight formerly incomplete
original posts now pass both canonical translation and classification. The
100-trillion-token post reused its saved translations. Targeted follow-on
prepared two requests. No Twitter calls, new tables or budget/attempt reset.
The first local targeted audit saw extraction disabled and therefore could
not establish production role completeness. Render's later guard correctly
refused the supplement because current targeted outputs remain unfinished.
Inspect those failures under the actual Render configuration before recovery.
Preserve old failures and healthy outputs. Supplemental 347-member enrichment
and final complete-cohort audit remain.


### Bounded supplemental extraction scope — 2026-10-16 17:10 UTC

The zero-inference/current-key enrichment guards correctly stopped both
supplement launchers before their first model request. Two old classifier
packets remain unused pending imports although all20 members have healthy
current outputs; preserve that truthful cache history instead of marking them
applied. Actual Render configuration also exposed11 unfinished targeted roles;
the first local audit had extraction disabled and its zero count was invalid.
The production read-only diagnosis and subsequent bounded corrected-input run
`job-db95gkft5n8s73ec5qg0` repaired10. Post2082872979424510292 still lacks
a publishable event after its fixed corrected-input retries. Preserve that
failure and all attempts; do not reset it under a fresh source job.

Implement one optional post_ids selection on the existing shared
scripts.backfill_targeted.advance_targeted. Validate nonempty membership
before advancing paid groups, then restrict the ordinary observation query.
Default callers retain the full existing cohort. Reuse the same prompts,
_prepare, request registration, ordinary-API transport and domain publishers.
No new table/migration, helper pipeline, prompt/model/key, live cursor or
scheduler change. Regression net: real PostgreSQL production-caller publication
for one selected post, excluded failed sibling unchanged, duplicate IDs
normalized, empty/foreign members rejected before any provider call.

Use the same staged production route. Supplemental base enrichment keeps
healthy original overlaps; targeted extraction explicitly selects only the347
new members. Freeze the one original exhausted role in instructions/report
and assert it matches current Render facts; do not silently retry it or hide
it from final verification. Deduct all additional original recovery rows and
reservations before allocating the still-unstarted supplement. Its first two
launches created no provider batches or starts. This continues independent
work while retaining failures for the final full-cohort evaluation, consistent
with the owner instruction. The expected3800–4200 count remains unmet at1899.

The exact20 follow-up was observed once after16:56:12UTC: helper failed with
19unhealthy/1pending, legacycommentary0/20, validlanguage17/20, Chinese15/15;
no missingIDs. Separate canonical facts are19/20, not a helper pass. Normal
16:45 cycle completed16:50:57 with89inserts and degraded capacity refusals;
production read-only DB independently finds89fresh-day rows in that window,
50translation-success and40classification-success at the later snapshot.
No healthy-cycle claim or cron pause. Preserve these limitations.

Regression evidence for this helper:3new tests red before source change;95focused green including40required PostgreSQL and existing Ollija/default/corrected-recovery/consumer checks,0skips/errors. Final strengthened6targeted tests pass including6required PostgreSQL; invalid selection cannot even advance an existing registered paid group. Django check,2-file Ruff and whitespace pass. Serial inline review,0independent reviewers under owner mapping, no confirmed findings; receipt /tmp/compound-engineering-501/ce-code-review/20261016-171148-targeted-selection/review.json. Source changes only subset selection; normal core prompts and content identities stay unchanged.
