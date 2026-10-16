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

The owner authorizes a data-only staging-to-production transfer, conditional on
all 1,660 Posts passing current ingestion/enrichment verification. Code delivery
remains on-request: no commit, push, application deployment, schema/service or
scheduler change. Production completion means independently verified imported
data and CollectionRun provenance on the currently deployed schema.

The separate 502 task remains explicitly held and G3-owned.

# August backfill verification and July 30 collection parity

## Plain-English Summary

The August 9 transfer and subsequent diagnosis are recorded below. The next
phase prepares a July 30 backfill that includes the normal harvester's relevant
collection routes and proves both collection and enrichment. Around 4,000
unique posts is the owner's expectation, not a quota or a completion check.
The latest instruction is to capture lessons before implementing that phase;
this update starts no new run or deployment.

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
correctly. The anticipated 4,000 posts is only a comparison point. Current
policy and account membership cannot reconstruct precisely what a historical
policy would have found; provider search may not return every eligible post.
Report those limitations without claiming full recall from a healthy cohort.

### Owner decisions and current endpoint

- Owner requested adding Call A and rare and double-checking scope against the
  normal harvester, then explicitly requested ce-compound first.
- Current endpoint: verified learning plus this continuation plan. Code
  preparation remains the next authorized task; this documentation phase does
  not start implementation, a paid run or deployment.
- Intended data destination is production. Record exact database and candidate
  identities before launch. Completed Aug9 data-transfer authority is retained
  as history; code delivery remains on-request, without inventing new release
  authority from the intended destination.
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
