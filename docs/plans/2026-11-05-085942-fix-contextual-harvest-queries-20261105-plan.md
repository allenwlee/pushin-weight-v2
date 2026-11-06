---
title: fix/contextual-harvest-queries-20261105 plan
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ollija-annotate-plan
execution: code
ollija:
  change_id: fix-contextual-harvest-queries-20261105-2026-11-05-085942
  branch: fix/contextual-harvest-queries-20261105
  workflow: work
  delivery_target: production
  delivery_selected_by_user: true
  delivery_route: direct
  delivery_route_selected_by_user: true
---
<!-- BEGIN OLLIJA DELIVERY GUIDE -->
## Ollija Delivery Guide

This block is generated guidance. Do not edit it directly. Correct durable facts in `.ollija/project.yaml` or this template, then rerun `ollija annotate-plan`. Current explicit owner instructions govern this task. Record exceptions below and reflect route changes in metadata; removed requirements must not return through another checklist.

### Resolved locations

- Authoritative host: `fuchitalee`
- Authoritative repository: `/Users/fuchitalee/development/pushin-weight-v2`
- Ollija release worktree area: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees`
- Active worktree: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/contextual-harvest-queries-20261105`
- Plan: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/contextual-harvest-queries-20261105/docs/plans/2026-11-05-085942-fix-contextual-harvest-queries-20261105-plan.md`
- Change: `fix-contextual-harvest-queries-20261105-2026-11-05-085942`
- Branch: `fix/contextual-harvest-queries-20261105`
- Staging branch and blueprint: `staging`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/contextual-harvest-queries-20261105/render-staging.yaml`
- Production branch and blueprint: `main`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/contextual-harvest-queries-20261105/render.yaml`
- Staging URL: `https://pushinweight-staging-web.onrender.com`
- Production URL: `https://pushinweight-web.onrender.com`

### Placement

This worktree is inside the Ollija release worktree area. Reuse it for the whole change. Do not create a second worktree or plan for this branch.

### Delivery scope

- Workflow: `work`
- Delivery target: `production`
- Owner selection recorded: `true`

1. Complete implementation and the plan's verification contract.
2. Run the configured focused checks:
   - `pytest tests/ollija`
3. The parent workflow commits only this plan's changes, pushes the feature branch, and records the candidate SHA.
4. On the owner-selected direct route, fetch the remote production lane: `git fetch origin refs/heads/main`.
5. Require the same unchanged candidate SHA to be a fast-forward of that fetched remote ref, then push the exact candidate SHA to `refs/heads/main` with the server-enforced fast-forward command `git push origin <candidate-sha>:refs/heads/main`.
6. Verify the remote production ref resolves to the candidate SHA and the deployment for `pushinweight-web` reports that same SHA before reporting completion.
7. After step 6 succeeds, perform worktree cleanup as the final filesystem action:
    - From `/Users/fuchitalee/development/pushin-weight-v2`, require `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/contextual-harvest-queries-20261105` to remain registered, clean, unlocked, and at the verified candidate SHA. If any guard fails, retain it and report the reason.
    - Run `git -C /Users/fuchitalee/development/pushin-weight-v2 worktree remove /Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/contextual-harvest-queries-20261105` without `--force`.
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

Owner now requests deployment of the reviewed eighteen-call contextual refactor and its C1/B2/B4 noise corrections. Production is selected; retain the owner-selected direct production route from this conversation. Staging deployment is omitted, not passed. Complete required regressions, exact-request byte checks, matching discovery assessment, necessary policy-keyword reconciliation and observed production verification. Preserve live collection, schedules, provider/model caps, unrelated worktrees and historical labels. R1–R5 semantic attribution proposals remain deferred. No new provider/model experiment is selected; use existing real captures for assessment where their exact inputs still match.

# Contextual tracked-brand queries

## Plain-English Summary

Retain the expanded brand/product coverage, but require relevant surrounding terms for ambiguous words. A wedding ring, a Formula1Kimi, ordinary-languageYi/MiMo, or GoogleDrive must not become a model-brand match. Official account mentions remain independent branches.

Reuse the shared policy renderer and named brand/family blocks. Restore context in retrieval and brand attribution, qualify URL evidence, and retain the request-byte guard. Split whole brands or named NVIDIA families into another call when needed; do not remove context to make a query fit. No schema/table changes.

Verify locally using stored evidence, meaningful caller regressions and an independent relevance set. This does not activate the candidate in production.

## Scope and implementation

- TOUCH: policy/named grouping, shared planner/config inventory, matching of five ambiguous portfolios, qualified observed URLs/handles, their scheduled and X post backfill caller wiring, regression tests and offline report.
- PRESERVE: other brands' expanded product aliases, curated list, the two-call special-events inventory, official tracked-brand mentions, live collection/enrichment, database identities/labels, keyword inventory, all provider/model/page/result/concurrency caps and other sessions.
- Recover expanded proposal from8bc08062 as an implementation input, never as accepted relevance evidence. Reuse its tested packing machinery without reinstating unsafe policy or arbitrary hostname/path attribution.
- Use existing alias_context rules for concurrent terms; give highly ambiguous people/common words stronger product qualifiers than genericAI when saved negatives demand it. Guard legacy DB aliases as well as new search tokens.
- Admit URL evidence only from explicitly named repository owners/official hosts or unambiguous product/model identifiers; never infer NVIDIA from drive.google.com or Moonshot from an F1 kimi path.
- Keep brand exclusion lists scoped to their brand and account mentions independent. Preserve historical query recipes in X post backfill.

## Frozen evaluation and limits

- Existing12hour snapshot8281posts: report search coverage against stored labels as agreement only, not relevance.
- Independent three-cycle review1381brand/post pairs for fivebrands:168identified references,1192reviewed false references,21uncertain. Retain separate NVIDIA company/finance and product scope; never score uncertain as a precision win.
- Develop using first cycle386pairs; hold later995pairs as a separate evaluation partition. Keep original IDs/text, review decisions and hashes frozen in external local evidence.
- At most3policy variants on the development partition, then one held-out report. Report every positive loss and retained negative by brand. Additional changes require new evidence/explicit recorded reason, not an unbounded tuning loop.
- Add positive/negative controls for each collision, including genericAI+wrongbrand, Unicode words, quote context, model-version names, official mentions, approved model repositories and arbitrary unrelated URL paths. Do not pass by deleting every broad-name positive.

## Regression net and verification

- Pin observed false attribution red on current code/expanded old candidate before correction. Test both detection and persisted PostBrand/Mention projection through real CycleRunner with fake captured search/model clients; zero paid calls.
- Use shared permanent testDB exclusively through pushinweight-test-db. Reuse compatibility overlays only if shared history needs them; never restore/create/drop another DB. Run scoped query/attribution/filter/cursor/backfill regressions and existing optional caller tests affected by changes. Required skips are incomplete, not passed.
- Mandatory byte review: render all enabled list/base/unchanged discovery requests through actual shared planner and XClient effective bound injection with10digit timestamps and active author exclusions. Record callID/bytes/headroom and code/policy/config hashes; fail above512. Audit scheduled/manual/current-policy backfill and disabled frozen legacy separately. Re-run after any relevant change/main integration.
- Separate retrieval match, correct brand admission and semantically reviewed brand relevance in report. Explicitly state this is a local simulation, not provider indexing/completeness proof.
- Review cost using configured harvest-cost model and actual call inventory; extra calls need owner authority (granted), but activation remains unrequested.

## Exit criteria

Locally implemented candidate with maintainable exact query exhibit, complete full-wire byte proof, meaningful positive/negative regression net, by-brand frozen-data report and explicit residuals. No production activation.

## Local review delivered — 2026-11-05, JST

Owner's latest endpoint is a complete current/proposed combination comparison and an invokable saved template. The candidate remains local and uncommitted. This work made zero X/provider/model requests and no production mutations; public provider documentation was read, but it did not establish period-token behavior.

### Complete comparison and saved subskill

- [Full comparison](../analysis/harvester/2026-11-05-212319-harvest-query-diff.html): 665 current source combinations, 1,281 proposed combinations, 1,343 displayed rows. Every source occurrence is retained, including duplicates and the unchanged discovery calls. CSV, full comparison JSON, and current/proposed request manifests share the filename stem.
- Status counts: 588 equivalent, 74 broader per branch, 3 narrower, 0 without a mapped route, and 678 additional displayed alternatives. These are expression counts, not extra-post counts. A broader individual branch may already have been covered by another old alternative.
- The three deliberate tightenings are unquoted `dots AND studio` to a quoted phrase/company evidence; `Yi AND model` to stronger language-model evidence; and unquoted `ox AND alpha` to `"Ox Alpha"`. They are not claimed equivalent.
- Current source: saved restored-release receipt `data/runs/2026-11-05-161100-restore-harvest/complete-enabled-byte-audit.json` in the authoritative root, baseline `bca0cbf5` / `76b17899`. The source hash, candidate policy/config/code hashes and equal sample request bounds are in the manifests. This is not a fresh production-query capture.
- Restored the old contextual terms for the other brands as well as the five noisy portfolios. NVIDIA translations remain contextual; official mentions remain independent. ChatGLM and explicit GLM4/5/6 stand alone. MiMo versions are conjunctions. `"dots studio"` is quoted, bare dots requires company identity, and Sakana requires relevant context. `Z.ai` remains contextual because literal-dot indexing is unverified.
- Saved `.claude/skills/change-harvester/subskills/harvest-query-diff/SKILL.md` and its deterministic generator, with a parent-skill pointer and `.agents/skills/harvest-query-diff` discovery link. Invoke **`$change-harvester harvest-query-diff`** or **`$harvest-query-diff`**. The same new files are installed in the authoritative checkout for immediate discovery; its pre-existing parent-skill edits were preserved. Skill validation passed, and both copies match byte for byte.

### Complete request-byte review

Actual planner plus caller timestamp/author-exclusion injection: **16 base calls + 2 unchanged discovery calls = 18**, versus the restored 10. This is eight additional requests per sweep before pagination; no claim that 18 is the globally minimal packing. Owner permits additional calls to retain context. Grouping uses whole brands or named NVIDIA families. The separate Giants work remains untouched.

| Call | Logical ownership | UTF-8 bytes | Spare |
| --- | --- | ---: | ---: |
| A | Curated list | 96 | 416 |
| B1 | Meta, LG | 390 | 122 |
| C1 | NVIDIA named models | 485 | 27 |
| C2 | NVIDIA software | 436 | 76 |
| C3 | GLM, Yi | 488 | 24 |
| C4 | Dots / Xiaohongshu | 322 | 190 |
| B2 | Mistral, Sakana | 509 | 3 |
| B3 | Qwen, DeepSeek, Hunyuan | 469 | 43 |
| B4 | MiniMax, Kuaishou | 449 | 63 |
| C5 | NVIDIA qualified product names | 488 | 24 |
| B5 | InclusionAI | 303 | 209 |
| B6 | Moonshot / Kimi | 456 | 56 |
| C6 | NVIDIA company, qualified tools | 411 | 101 |
| B7 | Xiaomi / MiMo | 337 | 175 |
| B8 | ERNIE, Upstage, SenseTime | 511 | 1 |
| B9 | Doubao, StepFun | 507 | 5 |
| SPECIALEVENTS1 | Unchanged discovery | 476 | 36 |
| SPECIALEVENTS2 | Unchanged discovery | 484 | 28 |

All complete requests pass the 512-byte gate. B8 has only one byte spare; any suffix, policy, configuration or caller change requires rerendering the complete inventory. Context must not be deleted to make room. Packing equivalence is tested against the complete combination expansion of the uncompressed brand blocks.

### Regression results

**357 focused tests + 13 real-caller PostgreSQL tests passed; zero required skips/errors.** This is the selected affected test set, not the full repository suite. Proof is in `.local/contextual-harvest-query-review/final-policy-tests.log` and `caller-referral-after.log`.

The real CycleRunner tests persist positive/negative examples through the actual writer with fake external transports, exercise all 16 scheduled base calls, maintain independent mentions and cross-brand exclusion behavior, and cover backfill/cursor/full-request-byte behavior. One new caller assertion first failed because an `f1` substring in a saved referral URL triggered the racing ban. A shared exclusion helper now bounds `f1` while preserving intentional substring bans such as `hamil` matching Hamilton. The same assertion passes through the actual database writer. Historical call-level exclusions retain their old behavior.

Shared PostgreSQL was used only through the exclusive-lock wrapper. Four already-applied migration files were temporarily supplied to reconcile its existing history, with one empty compatibility marker; that marker and all five temporary files were removed afterward. No application schema changes or new tables were introduced.

Five saved genuine CUDA/LMStudio, CUDA/graphics, NVIDIA/kernels and Kimi/智谱 controls exposed missing qualifiers. Those specific regression fixes and their frozen fixture are recorded in `tests/fixtures/contextual_saved_positive_controls.json`; this was a bounded positive-control repair, not an open-ended search for higher scores. No further variants were tuned from the held-out replay.

Browser proof verifies all 1,343 rows visible initially, all three narrowed rows via filtering, reset/search behavior, 28 exact-request appendix entries, both download links and zero page errors. The generator validates formatted queries against the raw expressions.

### Saved-data findings and limits

The locked 12-hour window is **2026-11-04 22:00 through 2026-11-05 10:00 JST**, containing 8,281 saved posts. Current local expressions match 9,434 of 9,554 stored brand/post pairs; proposed expressions match 9,464. Posts with multiple stored brands count more than once. The 25 unattributed posts are separate: current catches 1, proposed catches 2. These are agreement with saved labels and saved current list membership, not relevance or live-provider recall.

Selected low-volume/sensitive brands, shown as current → proposed / stored: InclusionAI 12 → 11 / 13; Yi 9 → 7 / 9; Upstage 20 → 20 / 23; MiniMax 399 → 403 / 429; Moonshot 700 → 715 / 716; NVIDIA-model identity 50 → 51 / 51; MiMo 34 → 34 / 34; Dots 2 → 2 / 2. The complete by-brand result is `.local/contextual-harvest-query-review/12h-summary.json`.

The separate frozen cleanup cohort has these candidate outcomes:

| Brand | Previously removed false references still admitted / removed | Previously kept references matching / kept |
| --- | ---: | ---: |
| InclusionAI | 2 / 326 | 4 / 4 |
| Yi | 0 / 182 | 0 / 0 |
| MiMo | 0 / 48 | 4 / 4 |
| Moonshot / Kimi | 1 / 112 | 58 / 68 |
| NVIDIA | 0 / 524 | 74 / 113 |

Three known false references remain: InclusionAI `2118238921998176675`, `2118239815149736041`, and Kimi `2118237750344536097`. Of 189 previously kept references, 140 match and 49 do not. That keep set includes uncertain short text and company/finance references; do not call all 49 irrelevant or claim perfect recall. The replay uses proposed policy tokens in memory and saved body/quote/entity evidence, without activating database keywords or reconstructing every account-affiliation relationship. Full per-pair results and unchanged source data are preserved in local evidence. These limitations remain visible in the comparison; it is a review artifact, not a deployment-readiness certification.

## Follow-up: period-matching confirmation — 2026-11-05 22:25:39 JST

The owner then requested “confirm if dot is read as space or char.” This authorized a separate four-request operator check; it does not change the earlier offline-audit accounting or grant production activation. Used only the on-demand credential, four physical requests, one page each, no retries, no policy or database mutation. Exact saved controls and raw receipts: `.local/contextual-harvest-query-review/2026-11-05-222224-dot-confirmation/`.

Observed `Z.ai` → 0, `Z AI` → 2, `"Z.ai"` → 0, `"Z AI"` → 1. The spaced queries recovered the known adjacent/separated controls; dotted queries did not. Therefore the dotted form is not equivalent to a space in this test. A known expanded-domain control also failed to return, so literal-dot positive matching and a universal punctuation rule remain unproven. Keep context in the current proposal. Estimated spend 75 credits ($0.00075); raw/unique counts 3/2. A local timestamp-parser repair reused saved response bytes and did not repeat requests.


## Follow-up: bounded query edits and punctuation knowledge — 2026-11-05 22:58:50 JST

The owner requested Earth-2 context repair, standalone quoted Step Flash names,
expanded joining handles, Japanese/Chinese release nouns, and the dot finding in
the harvester skill. This supersedes the earlier instruction to keep discovery
query text unchanged; its **two-call count remains unchanged**. Endpoint remains
local implementation and local review. No release or new provider requests.

### Implemented behavior

- `Earth-2` requires `NVIDIA`; climate/weather/forecasting alone no longer qualify
  the NVIDIA brand. This also applies to shared brand attribution.
- Exact `"Step 3.5 Flash"` and `"Step 3.7 Flash"` phrases are independent StepFun
  aliases in both query construction and attribution. Other Step terms retain
  their context.
- Joining discovery replaces the old complete phrase with `"I've joined"`
  AND one of `@OpenAI`, `@AnthropicAI`, `@GoogleDeepMind`, `@deepseek_ai`.
  These four fit while preserving all pre-existing jobs/events/opportunity and
  multilingual branches. A fifth handle does not fit the existing eleven-digit
  timestamp contract without deleting a retained branch. Lower-priority Qwen,
  Zhipu, MiniMax, Meta, NVIDIA and Mistral handles are therefore not added to
  this discovery branch; their tracked-brand query routes remain.
- Release nouns add `模型` (Chinese model), `モデル` (Japanese model) and `权重`
  (Chinese weights). All English nouns, release verbs and independent HF URL
  routes remain. No additional useful bilingual term fits that same timestamp
  allowance. Removing redundant `min_faves:0` text from the two discovery calls
  leaves their effective minimum at zero; the real caller test verifies this.
- `special-events-v1-2026-11-05` identifies the revised discovery text.
  New handle sources: the social links on [OpenAI](https://openai.com/),
  [Anthropic](https://www.anthropic.com/) and
  [Google DeepMind](https://deepmind.google/). DeepSeek's handle was retained.

### Full-request byte review

Still **16 base + 2 discovery = 18 calls**. The current export includes the
active author exclusion on base calls and both real caller time bounds.
C5 changes from 488 to **449 bytes**; B9 remains **507 bytes**. All other base
calls retain their earlier byte totals, with B8 tightest at **511 bytes**.
Discovery calls use **510 / 505 bytes** with ten-digit timestamps and
**512 / 507 bytes** with their supported eleven-digit maximum. The first
therefore has zero headroom at its maximum. No context was deleted to fit.

The new source manifest includes the discovery module hash as well as policy,
configuration, planner, packer, attribution and caller hashes. It is a local
proposal export, not an activated or freshly dispatched query inventory.

### Regression evidence and release limitation

**370 focused checks and 47 PostgreSQL/caller checks pass; 2 existing release
checks fail; zero required skips/errors.** Evidence:

- `followup-before.log`: new Earth/Step failures before the fix. Initial discovery
  controls also exposed the offline replay tool's intentionally unsupported URL
  operators; the text-only controls now explicitly isolate text alternatives.
- `followup-after.log`: 368 pass, one obsolete exact C5-length expectation fails.
  `followup-length-after.log` verifies its corrected 391-character expectation
  (449 full request bytes). This preserves exactness and the separate byte cap.
- `phrase-diff-before.log` / `phrase-diff-after.log`: the comparison previously
  failed to recognize that a longer exact phrase implies its contiguous shorter
  phrase plus handle. A small generic implication repair passes all 67 query-diff
  checks, including a negative control where an intervening word breaks the
  shorter phrase. This adds one check to the 369 focused checks above.
- `followup-caller.log`: 49 required PostgreSQL tests execute, 47 pass, and the
  production/staging blueprint assessment checks fail. The real CycleRunner
  persists Earth/Step examples with the intended brands, excludes the weather
  collision, dispatches the two discovery calls through fake transport, preserves
  scheduled credential purpose, zero engagement floor and the allowance guards.

All logs are in `.local/contextual-harvest-query-review/`. The shared test DB used
its exclusive wrapper; the empty migration marker and temporary history overlays
were removed. There are no application schema/table changes.

**Do not deploy this candidate yet.** The immutable October 27 discovery
assessment identifies the previous query strings. The real planner rejects it
for the revised tuple, which would abort a configured harvest cycle. Existing
blueprint tests, assessment files and fail-before-provider checks remain intact.
No old evidence was retagged and no synthetic test assessment is deployment
proof. A matching real assessment is required before a later release. This is
an explicit local-proposal limitation, not a passed or waived release check.

### Durable skill knowledge and local review

The dot observation is now linked from `change-harvester/SKILL.md` to
`references/2026-11-05-222224-dot-search.md` in both the authoritative checkout
and the candidate. It records the four exact query variants, counts, capped
pagination, controls, evidence location and the limited conclusion: dotted and
spaced forms differed; literal-dot positive matching remains unverified. It
explicitly does not generalize to numeric versions or hyphens. Both copies
match; skill validation passes. No additional punctuation probes were run.

The updated invokable comparison generator is synchronized to the authoritative
skill. Latest review files:

- [Verbatim calls](../analysis/harvester/2026-11-05-225718-proposed-harvest-calls-verbatim.html).
- [Complete combination comparison](../analysis/harvester/2026-11-05-225718-harvest-query-diff.html),
  with CSV, full result JSON and current/proposed manifests beside it.

The refreshed comparison lists 665 current and 1,333 proposed source combinations
in 1,395 rows: 587 equivalent, 75 broader, 3 intentionally narrower, no unmapped
current route, and 730 added alternatives. These are expression counts, not
measured extra relevant posts. Earlier frozen-data scores remain historical
results for the preceding candidate; they have not been recomputed for these
Earth/Step/discovery edits.


## Owner-authorized live comparison — 2026-11-05 23:14:47 JST

Owner now authorizes one TwitterAPI test of the revised calls and confirms the
comparison baseline is the last five completed harvest cycles. Preserve the
local-only release endpoint; this adds bounded on-demand retrieval authority,
not deployment, production writes, keyword activation or LLM requests.

Frozen experiment: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/contextual-harvest-queries-20261105/data/runs/2026-11-05-230504-contextual-query-live-test`. Reuse the five captured cycles (135 archived
base-search HTTP responses, 6,072,348 exact bytes, no missing archive) and their
stored brand memberships; include corresponding saved discovery hits separately.
One proposed-query run covers 2026-11-05T22:30:28+09:00 through
2026-11-05T22:45:28+09:00 (15 minutes). All 18 final request strings pass
512 UTF-8 bytes. Hard ceiling: 100 physical requests, zero retries, 360 seconds,
15 pages per ordinary call, 8 for C1, 1 per discovery call; estimated ceiling
30,000 credits / $0.30 at 20 tweets/page. Use only the on-demand key.

Freeze queries and baseline; no adaptive query edits or extra windows. Capture
raw responses before normalization, retain duplicates, empty/error requests and
continuation state. Stop on cap, provider/transport error, repeated cursor or
no progress. Mark unfinished searches incomplete. Count unique posts per brand
using the same proposed text/quote/mention/URL matcher on both sets, and show
actual stored baseline counts separately. These are retrieval/matching counts,
not final post-fetch model decisions or certified relevance. Match the common
covered interval for a secondary same-time comparison because production calls
have staggered 15-minute bounds. Show per-cycle counts, averages, differences,
coverage limits, actual calls/spend and representative posts locally.


## Live comparison result — 2026-11-05 23:31:23 JST

Completed the owner-authorized single-window TwitterAPI test. **51 physical
requests, zero retries, 519 raw rows, 450 distinct posts, 69 duplicate returns,
8,025 estimated credits ($0.08025), 85.71 seconds.** All 16 base calls reached
provider exhaustion. Both discovery calls used their existing one-page caps
and remain incomplete samples. No query was changed after freezing the test.
No production data/configuration, classifier/model request, or release action.

The baseline consists of the last five completed cycles captured at experiment
start: 21:45, 22:00, 22:15, 22:30, 22:45 JST on November 5. It reuses 135 exact
base-search response archives plus 131 retained public discovery hits from ten
requests; all ten use the production identity `pushinweight-harvest`. The first
read assumed the generic environment value `production` and returned no discovery
rows; a bounded read of actual persisted identities corrected that filter. No
old query was dispatched again. Baseline averages: 29 physical requests, 308.8
raw rows, 293.4 distinct returned posts and 218.6 posts matched by the shared
proposed brand rules. New query totals: 450 distinct (+53.4%), 363 with tracked
brand evidence, 431 brand/post pairs. All 25 discovery-only additions are outside
the tracked-brand matcher; they are not silently allocated to a brand.

Main by-brand comparison (old five-run average -> test), with identical proposed
matching on both sets: NVIDIA 7.8->90, Meta 86->84, DeepSeek 59.8->64, Kimi 20.2->38,
Mistral 4->29, Qwen 29->29, Doubao 1.6->25, Hunyuan 20->18, Kuaishou 8->17,
MiniMax 9.2->10, GLM 5->9, MiMo 2->6, ERNIE 4.6->5, SenseTime 0.8->3,
InclusionAI 2.4->2, Sakana 0->1, StepFun 0.4->1, and Dots/LG/Upstage/Yi 0->0.
Actual persisted baseline brand counts are separately shown, because later
filtering and attribution differ from a raw query test. Do not turn retrieval
counts into relevant-post or recall claims.

The fixed test bounds are 22:30:28–22:45:28 JST. Old regular calls had staggered
15-minute bounds and the old discovery windows varied slightly. The report's
same-time view restricts both populations to their common 22:31:52–22:45:28
interval (13m36s), preventing time skew from being mistaken for query coverage.

### Concrete remaining defects and unknowns

- NVIDIA's 90 includes finance-only material and BIGBANG COSMOS WORLD TOUR
  (`2118338888783810819`), which matches the standalone Cosmos world phrase.
  Generic NVIDIA+AI still admits stock recaps. Do not treat all 90 as relevant.
- Mistral's 29 includes Spanish/French ordinary uses of standalone Magistral;
  three concrete counterexamples are recorded. This alias needs context.
- Xiaomi+model admits a Doubao refusal comparison that mentions Xiaomi as a
  consumer brand (`2118338519689249276`), without identifying Xiaomi AI work.
- Official Kling mention greetings are returned under the explicitly retained
  independent-mention rule; they are not substantive model discussion.
- Three old posts in the common interval were absent from the live result:
  `2118338710504952265` (DeepSeek), `2118338227233013833` (DeepSeek/Kimi),
  `2118335981887558022` (Meta). Offline expressions predict a matching route;
  the absence cause is unproven. No extra lookups/retries were performed.
- Zero results for sparse brands do not certify adequate coverage. Old stored
  Upstage labels averaged 0.4, while common-rule matching found zero.

These are bounded manual counterexamples, not a full precision evaluation. The
new raw response cohort does not by itself replace the existing discovery
quality assessment, and the candidate remains unsuitable for deployment.

### Evidence and review delivery

Report: [2026-11-05-232900-harvest-live-test.html](../analysis/harvester/2026-11-05-232900-harvest-live-test.html),
with counts JSON, by-brand CSV and exact tested-query manifest. Browser checks
verify all 21 rows, NVIDIA 7.8->90 and common-interval 10->79, filtering/reset,
three download links and zero JavaScript errors. Screenshot inspected.

Source experiment `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/contextual-harvest-queries-20261105/data/runs/2026-11-05-230504-contextual-query-live-test` retains raw request/response bytes, baseline SQL and
archives, 51 dispatch receipts, 519 hit rows, reconciliation and reviewed finding
IDs. No missing IDs, timestamp violations, normalization errors or conflicting
identities were found. Request/hit/raw counts reconcile exactly, and pricing is
linked in the report. Query/policy/config hashes still identify the frozen
local candidate. Further query changes require a separate recorded iteration.


## Saved-result noise audit — 2026-11-06 06:50:40 JST

Owner asks which of the largest increases need changes and how much is noise.
One bounded manual review covers every returned post for the five largest
absolute increases, plus Xiaomi/MiMo: 190 distinct posts, 205 brand/post
judgments. Cohort and rubric were frozen in `noise-audit-manifest.json`; every
judgment and reason is recorded in `noise-audit-manual.txt` and `noise-audit.json`
under the existing live experiment. Saved expanded URL evidence identifies three
Kimi cases; that evidence clarification is recorded. No new provider/model
request, query edit, database write or deployment. All nine frozen source hashes
still match.

Noise includes wrong identity/topic, stock-only/general material without concrete
AI product or operating information, and generic official-tag replies. Retain
AI demos/use/opinions, topical ads, NVIDIA DLSS/CUDA/inference hardware, company
AI operations and repeated news. This is topical relevance, not factual
verification, novelty, or proof that noise reached the product feed.

| Brand | Relevant | Noise / test | Uncertain | Noise / same-time new additions |
|---|---:|---:|---:|---:|
| NVIDIA AI | 61 | 24/90 (26.7%) | 5 | 17/69 |
| Mistral | 5 | 24/29 (82.8%) | 0 | 18/18 |
| Doubao / ByteDance | 25 | 0/25 | 0 | 0/22 |
| Moonshot / Kimi | 38 | 0/38 | 0 | 0/20 |
| Kuaishou / Kling | 3 | 13/17 (76.5%) | 1 | 3/7 |
| Xiaomi / MiMo | 5 | 1/6 (16.7%) | 0 | 1/1 |

NVIDIA noise comprises three concert matches, five unrelated tagged topics,
two generic tagged replies, thirteen market/stock posts and one non-AI GPU
cryptography post. Mistral has eighteen ordinary-language Magistral matches
and six generic replies. Kling has three platform-spam matches, eight greetings
and two replies about other AI brands. Xiaomi's one false match is a Doubao
refusal test naming Xiaomi as a consumer brand. Six uncertain cases remain
separate; aggregate 137 topical / 62 noise / 6 uncertain brand/post pairs.

Recommendations, not implemented: qualify Magistral in B2; qualify Cosmos world
in C1 and refine generic NVIDIA+AI in C6 while retaining real product/compute
coverage; stop allowing 快手+视频 alone in B4. Preserve the owner's independent
official-mention requirement and handle non-substantive or unrelated tagged
replies through contextual post-fetch filtering. Preserve the broad Xiaomi AI
net while requiring a Xiaomi-linked AI claim in attribution. Doubao/Kimi need
no precision-driven tightening based on this window. Query changes must retain
the complete-request 512-byte checks and regression comparison.

Review: `2026-11-06-064828-harvest-noise-audit.html`, companion JSON and all-judgment CSV.
Opened and verified in local Chrome on allenwlee. Browser checks cover six
summary rows, all205 judgments, brand/category/common-interval filtering and
zero JavaScript errors. Source IDs, counts and unchanged candidate hashes
reconcile. Single-window limits and uncertainty are visible in the report.


## Targeted draft comparison — 2026-11-06 07:39:00 JST

Owner requests drafted changes using `harvest-query-diff`, only relevant rows,
shown locally. Scope is draft/review only. The left input is the exact November5
tested proposal, explicitly not current production. The report uses the canonical
`.claude/skills/change-harvester/subskills/harvest-query-diff/scripts/query_diff.py`
parser/expander/formatter. Both root and candidate discovery links are symlinks
into that parent-owned subskill; no independent maintained skill copy exists.

Recommended executable draft changes only C1, B2 and B4: qualify Cosmos world
with NVIDIA/model; move Magistral into explicit AI/Mistral context, reuse the
existing Sakana multilingual context group (the six new Mistral/Mixtral routes
are visible); remove 快手+视频 alone. Retain all32 official mentions independently.
Magistral unrestricted URL matching is replaced by explicit Mistral-owned roots;
community Magistral-only URLs without body context may lose attribution, an
unmeasured limitation shown in the report. No runtime policy or application
file is changed: the draft YAML is confined to the review evidence directory.

A stricter NVIDIA company query was evaluated offline and rejected because it
lost three relevant NVIDIA and three Kimi brand/post pairs. Keep C6 retrieval
and draft a per-brand semantic filter instead. Final verification also found
that the false Xiaomi association is a useful Doubao post; retain broad B7
retrieval and draft correction of the associated brand. Preserve the post.
Doubao/Kimi query strings remain unchanged. The second draft received this
coverage-preserving correction; no further optimization loop or paid request.

R1–R5 are concrete but unimplemented relevance rules: non-substantive official-tag
replies, unrelated tagged brands, stock-only/general NVIDIA context, Xiaomi
named inside another model's response, and positive/uncertain retention. Current
B/C results are persisted directly; the binary relevance gate is for CallA staff,
not a general B/C per-brand gate. Do not claim these rules already execute or
that a whole-post DROP gate can safely remove an unrelated brand association.
No new table or additional TwitterAPI search call is proposed. Implementation
and any model-call/cost decision remain outside this draft endpoint.

### Query-byte and regression evidence

All18 complete scheduled requests and manual/backfill request shapes were
rendered through `plan_calls_for_cycle` plus `XClient._effective_search_query`,
including scheduled author exclusions and maximum-width10-digit bounds.
Base HEAD is `76b178991cb7a4301a9f0a95ab3e384b46ac398a`; all nine frozen
code/config/policy source hashes still match the tested candidate. The draft
policy SHA and complete inputs are in `current.json` / `proposed.json`.

| Call | Tested bytes | Draft bytes | Spare |
|---|---:|---:|---:|
| A | 96 | 96 | 416 |
| B1 | 390 | 390 | 122 |
| C1 | 485 | 503 | 9 |
| C2 | 436 | 436 | 76 |
| C3 | 488 | 488 | 24 |
| C4 | 322 | 322 | 190 |
| B2 | 509 | 509 | 3 |
| B3 | 469 | 469 | 43 |
| B4 | 449 | 437 | 75 |
| C5 | 449 | 449 | 63 |
| B5 | 303 | 303 | 209 |
| B6 | 456 | 456 | 56 |
| C6 | 411 | 411 | 101 |
| B7 | 337 | 337 | 175 |
| B8 | 511 | 511 | 1 |
| B9 | 507 | 507 | 5 |
| SPECIALEVENTS1 | 510 | 510 | 2 |
| SPECIALEVENTS2 | 505 | 505 | 7 |

Regression net: 14 positive and6 negative controls;32 independent mention-only
controls;15 named-group equivalence checks; unchanged source hashes; all137
audited relevant brand/post pairs retained. Query/policy changes remove24 of62
noise pairs;38 remain (NVIDIA21, Mistral6, Kling10, Xiaomi1), with six uncertain
cases separate. Semantic rules are not included in the measured improvement.
The original captured15-minute cohort and manual relevance labels stay fixed.
Offline matching is approximate; no new TwitterAPI/model call, DB read/write,
release or runtime policy change. Earlier release-assessment limitations remain.

Complete expansion:1,333 tested →1,347 draft occurrences. Owner-requested view
shows 35 relevant comparison rows:26 protected/equivalent,2 narrower,
1 removed broad route,6 new contextual alternatives. Every changed combination
is present; full unfiltered JSON and all18 exact requests remain downloadable.
Browser checks confirm default row completeness, search/status/reset controls,
all8 downloads and zero JavaScript errors; summary and comparison inspected.

Review `2026-11-06-073357-targeted-harvest-query-diff.html` and eight companions were copied to the
authorized allenwlee day directory and opened in a verified new Chrome tab.
Evidence: `data/runs/2026-11-06-072313-contextual-noise-draft`. User endpoint complete; production untouched.


## Owner-selected production delivery — 2026-11-06T14:44:18+09:00

### Plain-English Summary

Deploy the reviewed 18-call contextual refactor with the three approved noise corrections. The observed Magistral, Cosmos-tour and Kuaishou-video collisions receive explicit context. Keep the remaining brand-aware semantic rules as proposals. Preserve the existing live schedule, shared resource limits and historical data. No schema changes; zero tables added or retired.

### Execution and regression net

1. Apply the exact reviewed draft policy and add observed positive/negative controls through the real CycleRunner writer; retain existing scheduled/backfill/cursor/query-byte coverage.
2. Resolve discovery assessment identity from the exact saved November5 query captures, independently read their rows, verify production overlap read-only and reuse only hash-matching functional model receipts. Do not retag old-query evidence, invent a pass, or weaken the gate.
3. Run affected pure tests, the shared PostgreSQL caller suite under its exclusive wrapper, and Ollija checks. Repair stale environment/test setup without changing shared schema. Review the entire final diff and every changed caller.
4. Audit all18 complete wire requests after main integration, scheduled/manual/backfill shapes and supported maximum timestamp widths. Record bytes/headroom and final hashes.
5. Check production policy-keyword readiness and activation tuple; reconcile only necessary missing policy keywords via the existing idempotent command. Commit/push the selected candidate, then advance main without force. Keep schedules running and preserve unrelated service settings.
6. Verify deployed candidate SHA on web and harvest; inspect a natural scheduled cycle in logs and persisted rows. Use the enrichment-relevant latest20 health route, preserving the exact cohort for its thirty-minute follow-up.

Delivery authority: user says “ok let's deploy”; retain prior explicit direct-production selection. Owner authorizes this release, not an unrelated feature or fresh paid experiment. Current remote main and candidate base both76b17899 at intake. The dirty candidate is retained work for this same refactor.

### Release verification — 2026-11-06 15:06 JST

- Applied the reviewed C1/B2/B4 changes and preserved the independent account-mention branches. Restored Dots' hyphenated literal aliases for stored-post attribution; the search pack eliminates their redundant alternatives, so all reviewed wire strings remain unchanged.
- Final PostgreSQL/caller run: **208 passed; required executed115, skipped0, errors0**. This includes real CycleRunner persistence, scheduled/current-policy/frozen backfill paths, query caps, cursor lifecycle, attribution and reattribution. Shared-database compatibility used already-applied migration files plus an empty temporary merge marker; all temporary files and the marker were removed afterward. No schema DDL or new test database.
- Pure focused run:320 passed with3 expired-date fixture failures. The three checks now pass after freezing the fixture clock before its original deadline; frozen recipe hashes and the expired-deadline rejection remain unchanged. A subsequent75-check compatibility/policy run passed; six stale SQLite fixture checks were repaired for current numeric keys and all seven reattribution tests then passed in the final208-check run. Existing seeded Kimi ownership is preserved by using a unique synthetic alias in the legacy JSON fixture.
- Additional historical renderer/policy suite:132 passed. Import lint on newly introduced Python files passes. `git diff --check` passes. These are scoped release checks, not a claim that the entire repository suite ran.
- Final actual-planner audit:18 enabled complete requests in scheduled, manual and current-policy backfill modes. Scheduled bytes: A96, B1390, C1503, C2436, C3488, C4322, B2509, B3469, B4437, C5449, B5303, B6456, C6411, B7337, B8511, B9507, SPECIALEVENTS1510, SPECIALEVENTS2505. Discovery also passes its eleven-digit timestamp width at512/507 bytes. B8 has one byte of headroom. Byte receipt includes final code/config/policy hashes.
- Production readiness read found136 missing literal keywords across15 brands. Activation uses the existing `onboard_brand --sync-policy-keywords` command in17 bounded batches (maximum32 per brand per invocation), inside one outer transaction. It preserves existing rows, requires the exact reviewed missing set, proves full attribution readiness and18-call planning before commit, and makes no provider request. Activate after the new harvest image is live, between natural ticks; do not pause or reschedule collection.
- Discovery assessment now matches the exact November5 captured queries. It reuses two saved physical search responses and56 matching historical functional-provider receipts; **zero new TwitterAPI/model calls**. Assessment digest: `9fe76b9489038126e5e7e1141d0a7a7271ed33b070a0c79095173d7170220e0c`. Labels explicitly distinguish uncertain source judgments from human gold.
- Pre-deployment latest20 snapshot at14:58JST:0 complete,1 fresh-pending,19 unhealthy. Nineteen already lack both commentary fields; one lacks detected language. This baseline predates the candidate. It is a failed completeness check, not a passed or waived check. Recheck the exact IDs after15:28JST and report the result separately from deployment/cycle verification.
- Live services remain on76b17899 before release. Prepare only the two assessment environment values on harvest/enrichment, preserving every other setting and schedule. Render's documented save-only environment update takes effect at the next deployment: https://render.com/docs/configure-environment-variables . No Blueprint apply or staging operation.
- Existing cost sensitivity remains:10 to18 logical searches before pagination, eight additional calls per sweep. Empty-call floor difference is120 credits ($0.0012) per sweep at the configured15-credit floor; this is not a prediction of actual result volume. Inspect the first new natural cycle using `scripts.harvest_cost`.

Detailed local execution evidence: `.local/contextual-harvest-release-20261106/`. Historical draft/display receipts remain in this worktree; do not force-remove it during cleanup.
