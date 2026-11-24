---
title: Reduce feed classifier catalog input cost - Plan
type: perf
date: 2026-11-24
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ce-plan-bootstrap
execution: code
ollija:
  change_id: docs-compact-feed-catalog-20261124-2026-11-24-083652
  branch: docs/compact-feed-catalog-20261124
  workflow: delivery
  delivery_target: production
  delivery_selected_by_user: true
  delivery_route: direct
  delivery_route_selected_by_user: true
---
# Reduce the feed classifier’s catalog input cost

## Plain-English Summary

**November 24 production selection.** Ship the standing 182 brands plus batch-specific additions with their entries shortened. Allow the scheduled worker to combine one to five ready posts for up to 60 seconds from the oldest ready post, keeping the 20-post maximum and the existing decision-slot limit. For 22 ready posts, submit the 20 immediately. If those calls finish before the remainder’s deadline, leave the two pending so the next poll can combine them with new arrivals. If a full-batch call is still running at the deadline, submit the small pair through the existing bounded executor. Existing provider capacity and budget still apply. A reader-requested translation or independent release job can bypass the optional wait. Sixteen of 17 small groups in the six-hour production sample shared a run with a full group, so an idle-only delay would miss most of the opportunity. Reader-requested translation and historical replay retain their own timing. The owner selected production after reviewing the paid trial, including its retention uncertainty. The batch-only catalog remains experimental.

### Production implementation and verification

- Enable compact entries for scheduled feed classification while retaining full catalog identity for publication and old saved requests. Exercise the actual configured production path and verify a full-entry rollback.
- Add a scheduled worker regression for 22 ready posts, six or more ready posts, a full batch, an aging remainder across polls and restarts, no eligible target, mixed translation and retry work and a quiet queue. Keep deferred work uncharged and release claims. Check the oldest eligible post can flush without new arrivals.
- Run the focused catalog, runtime, publication, collection and worker suites. Review the integrated branch, verify its deployed revision and inspect ordinary worker calls for input tokens, batch sizes, successful publication and backlog. Keep source collection active throughout. No manual paid replay or historical rewrite.
- Use the staged route exception for an occupied environment. The shared staging branch is carrying an unrelated Chatter release at fa85d9d3. Production rollout covers these two changes only.

### Recorded release comparison

From 19:30 through 20:30 JST, before this release, the enrichment worker reported 114 successful classifier calls, 84 full 20-post calls and eight calls containing one to five posts. Median full-call input was 77,951 tokens. There were 29 retryable provider errors. Worker passes reported 840 published classifications. Adjacent harvest runs inserted 267, 246, 220 and 198 posts, with all 18 fetch calls run and zero persistence failures. The existing degraded reasons were list reconciliation and first-page search timeouts. Compare against matched post-deployment windows, keeping different traffic volume, cache usage, provider errors and cohort ages visible.

The matched 200-post trial is documented in the [quality comparison](../analysis/2026-11-24-181148-feed-catalog-paid-quality-comparison.md). Of 13 pairs which lost a usable answer moving from full to compact standing entries, the independent rubric supported the previous combined labels in five. Missing source-supported labels remain a release risk. All 629 frozen posts reproduced the selected trial catalog's exact serialized representation; this is a request check, distinct from the outcome measurement.

### Local release verification

The integrated queue, worker, two-role executor, targeted extraction and fixed-slot suite passed 207 tests, including 150 required PostgreSQL cases. Collection and pagination passed 146 tests. A separate targeted-extraction and backfill run passed 78 tests. Overlapping runs should not be added to get a unique test count. The wider release and historical enrichment suite passed 175 and failed 11. Each failing test also failed on unmodified main at 24812f0e. The Django system check and 40 repository delivery checks passed. The backend diff has no browser interaction or display changes. Independent review verified the slow-provider fallback and the handling of release jobs found during a pass. Waiting IDs do not trigger additional release intake.

### Historical experiment scope

Send DeepSeek the names and products that help it read the posts in its current batch. Today even a single mention of Qwen brings its full product list into both calls. First shorten the entries while keeping the same brands. Then measure the additional effect of removing the fixed 182-brand minimum. Both changes use the current two-call classifier.

On the same 200 archived posts, selecting relevant brands alone cut input about 50%. Selecting brands **and** sending only relevant terms cut it about 86% in an offline estimate. A separate historical model comparison cost 77% less, but its versions disagreed on post type for 120 of 197 comparable brand judgments. That comparison also changed instructions. Today’s bill and label quality require fresh evidence. The current production hotfix is the comparison point and the way back.

Success means the feed costs less per distinct, successfully classified post while people still find the same posts and get supported labels for the right brand. Verify collection, classification and dollars separately. A lower bill during a search outage or fewer published labels does not qualify. This is a planning artifact. Extra paid experiments, production data operations and rollout require their own authority.

## Goal Capsule

- **Objective** — reduce recurring feed classification spend while preserving recovered collection and reader coverage.
- **Means** — reuse the batch selector and existing matching, serialization, publication and telemetry paths at `24812f0e`. Keep the current model, two roles, batching and reservation behavior.
- **Finish** — a reproducible comparison of control, shorter entries, and shorter entries without the floor, with per-stage quality, coverage, cost and rollback evidence. Separate locally verified implementation from live activation and observed savings.

---

## Product Contract

### Summary

Only the catalog sent to the scheduled feed classifier and enrichment worker changes. Product matching and publication retain their full local view.

### Problem Frame

The emergency fix `6ab9b30d` limited which brands go into a feed batch. Its selector scans names and aliases, but returns the *entire* row after one hit. Brands in the fixed baseline bypass the scan. Adding products to a popular brand can therefore grow every request. Earlier experiments combined smaller inputs with new wording, label ownership logic and ultimately a different per-post processing path. Coverage and cost moved together, making attribution difficult.

### Requirements

- R1. Preserve membership, order and ownership of every real post/brand decision slot, even when the brand has no literal name match. Preserve existing sentinel/discovery behavior. Extra owners may supply context only.
- R2. Retain literal evidence from the post, available English translation, stored quote, local parent and the reviewed affiliations already supplied to feed. Keep supported labels with their target brand. Use the existing policy for independently supported advertising, promotion and release.
- R3. Compare the two changes independently with the current fixed-floor control. Keep source text, questions, transport, output parser, call count, budgets and batch grouping fixed for the catalog comparison.
- R4. Protect historical requests, completions, retry isolation, publication, the background release path and downstream reader visibility. Preserve the full local catalog and existing exact promotion matching.
- R5. Preserve collection under both X providers, including search coverage, pagination, cursor decisions and inserts. Judge savings using present-day provider-billed spend per usable post alongside volume, quality and retained labels.

### Acceptance examples

- A quote says `雪猫`, a translation contains a brand alias, and the body contains an official handle. The compact view retains the relevant owners and evidence from each available source. An ID-only quote supplies no invented text.
- In Maya v1.1.64 post `2121908611320266918`, NVIDIA keeps `other` / `neutral`. Maya’s release and praise stay with Maya. Repeat with NVIDIA discussed by a neighboring post. Genuine WordPress Meta Box `2121100720535691663` keeps its existing namesake treatment.
- Token Machine promotes a giveaway with Qwen as the prize. Preserve independently supported per-brand labels and the actual promoter. When two tracked brands own one product term, show both as context and record the existing ambiguous ownership disposition without dropping the rest of the post.
- A promotion retry gets different batch neighbors. The other brand’s completed sentiment and type survive. A later material source correction proceeds under the existing replacement rules.

### Scope boundaries

Search providers, credentials, query contents, claim limit, concurrency, translation scheduling, Jev routing, classifier taxonomy, reader rules and Pulse extraction remain under their existing owners. No schema additions, production reclassification, backfills, pauses or production writes for the comparison. Any richer per-subject promotion output would be a separate product/contract change.

---

## Planning Contract

### Key technical decisions

- KTD1. Extend `_feed_prompt_catalog` at the actual 20-post / 99-decision batch boundary. Build the view once for both roles. Keep the three comparative states available independently (session-settled: user-approved — chosen over restoring the compact prototype wholesale because separate measurements identify the cause of any loss).
- KTD2. Use the current canonical catalog row shape and existing validator. Keep ID and available display name, plus original-spelling field values that match a visible source. Let the existing canonical builder fill empty arrays and its ID-alias fallback. The historical sparse-token estimate must be remeasured with this exact representation. Keep catalog field identities and all owners. Keep matched account handles with their existing role metadata where supplied. Per-post author affiliations remain source evidence.
- KTD3. Factor the current literal boundary matching around `_literal_term_pattern`. The prior Jev-era implementation (`61c571f0`, `421d4d16`) provides a cached matcher and source-matched product precedent. Its original-language-only input, minimum lengths and per-post Jev transport have different semantics. Keep the current feed’s matching boundary and evidence sources. Reuse compact prototype tests where their expectations still apply.
- KTD4. Keep the full catalog in `tracked_brand_catalog` for local decisions. The compact `_feed_prompt_catalog` and its canonical revision identify exactly what was sent to the model. Per-brand replacement fingerprints remain based on feed-material evidence. A different catalog revision alone cannot replace a finished feed judgment.
- KTD5. Keep the existing two-role instructions byte-identical across the initial comparisons. In particular `classifier_0731_prompts.py` describes promotion relative to `tracked_brands`. Exact matching in the publisher corrects reported subjects only. A flat list of post-level promotion flags has no flag-to-subject map. Validate this contract explicitly. If the shorter view causes ownership/category errors, hold the affected stage. Qualify any minimal live-feed wording correction separately, with the same frozen inputs and a distinct revision. Broadening the output to all promotions would change semantics.

### High-level technical design

| Comparative state | Feed rows | Fields sent | Eligible callers |
|---|---|---|---|
| A, recovery control | 182 historical IDs plus current targets, reviewed affiliations and visible owners | Current full rows | Existing scheduled/enrichment feed gate |
| B, shorter entries | Exactly A’s row IDs and order per batch | Canonical projected rows | Same |
| C, no fixed minimum | B’s targets, reviewed affiliations and visible owners, no unconditional historical IDs | Same projection as B | Same |
| Existing manual, repair, deferred or Pulse-specific path | Its established catalog or frozen request | Its established bytes | Existing caller-specific behavior |

Directional flow: stored post and context → existing decision slots → batch-level required IDs and literal matches → one canonical prompt catalog shared by both calls → strict merge → publisher and reader. Full-catalog branch: Django snapshot → local hardware-label filter, promotion ownership check and release work. Retry branch: stored request → original catalog and ordered slots → cached replies → only eligible posts may publish.

### Assumptions and stop conditions

The numerical margins below are proposed verification choices, not historical service levels. Freeze them before inspecting candidate answers. Extra model calls have **no budget authorized by this plan**. The earlier U5 cap applied to another experiment. Missing model outputs, actual charges or sufficient examples yield an inconclusive result. Local implementation can be verified independently of paid qualification or rollout.

---

## Implementation Units

### U1. Freeze the recovery control and pin the real call chain

**Requirements:** R1–R5. **Dependencies:** none. **Files:** `monitor/cycle.py`, `monitor/enrichment_worker.py`, `x_monitor/attribution.py`, `tests/test_enrichment_worker.py`, `tests/test_u18a_classifier_contract_v4.py`, `tests/test_classified_product_releases.py`.

1. Pin the verified base and record the effective pipeline, role revisions, model, tokenizer, settings and catalog revision. Capture the control through the real scheduled/enrichment entry points with fake transports in an isolated test database. Capture both outgoing role requests, reserved physical calls, strict parse, final selection and reader result. Keep the per-post evidence, slot order, expected row owners and full catalog as comparison inputs. Give each arm the same isolated pre-dispatch fixture state, including due claims, selected judgments, translations and budgets. In a positive control, change one valid fake reply and prove that only that arm’s reader value changes. Use a deliberately shared state only for the retry and rollback tests.
2. Freeze a consecutive present-day cohort by first collection time before selecting on outcome. Target at least 200 eligible posts across complete JST slots and record every associated PostBrand, including pending, invalid and context-missing. Retain original batch boundaries. Stratify by brand, language, provider when linked, and single/multi-brand. Keep a separate manually judged challenge set. Include recent catalog additions and both provider shapes.
3. Record exact saved packet/role coverage. Where production has no raw request or no original batch grouping, mark reconstructed or unpairable. Create reproducible synthetic/local fixtures for uncovered contracts. Baseline characterization passes at A. New positive expectations for smaller packets should fail on A for the expected reason. Never weaken a passing semantic test to encode the candidate.

**Exit:** A/A yields identical serialized bytes, slots, fingerprints, stored outcomes and reader buckets with the same saved answers. Actual model repeat variability, when measured, is a separate line.

### U2. Shorten entries, keep the floor

**Requirements:** R1–R4, KTD1–KTD5. **Depends on:** U1. **Files:** `x_monitor/attribution.py`, existing feed-only selection in `monitor/cycle.py`, `tests/test_u18a_classifier_contract_v4.py`, `tests/test_enrichment_worker.py`, `tests/test_promotion_subject_matcher.py`.

1. Extend the existing selector to collect all literal matches per owner and field, including required and baseline brands. The current boolean short-circuit skips those rows and stops at the first hit. Scan each distinct catalog term against evidence spans once per batch where practical, preserving ties. Evidence cannot span two posts, a post and its translation, or a quote boundary. Verify B’s row membership against A and investigate any difference before adopting a changed match boundary.
2. Project a copy of the selected rows via `_tracked_brand_catalog`. Preserve case, CJK adjacency, exact repository IDs, handles, hashtags, domains and scope of account roles. Keep sorting deterministic. Match recorded aliases without treating a term in another post as evidence for this post. Do not truncate source, pages or decisions to meet a token goal.
3. At the existing feed eligibility gate make A/B independently selectable. Prefer the existing feed configuration boundary with a single validated mode if runtime rollback needs a setting. Default to A until authorized activation. Keep `None` (legacy caller/full catalog) distinct from an explicit empty floor. Old no-option callers retain existing behavior.
4. Exercise production call sites with two roles and the stored result. Compare against U1 including product-only and repo-only mentions, a brand with hundreds of unrelated products, an empty-match target and reviewed affiliation, shared aliases, a newer brand, and `Muse` in `museum`. Prove both roles get the same canonical catalog, the hash validates, the full local catalog is intact, and no extra reads or calls occur per post/role.

**Exit:** B preserves A’s row IDs, case bytes and decision slots, reduces actual serialized input, and passes the verification contract against A before C is advanced.

### U3. Remove the floor in a separate change

**Requirements:** R1–R5, KTD1–KTD5. **Depends on:** measured B for activation. Local tests may be prepared alongside U2. **Files:** same selector and feed gate as U2, `tests/test_u18a_classifier_contract_v4.py`, `tests/test_classified_product_releases.py`, `tests/test_classifier_translation_u5.py`, `tests/test_backfill_direct_enrichment.py`.

1. C supplies an explicit empty baseline and keeps every expected target, reviewed affiliation passed to feed, and all owners of actual mentions. Preserve source projection, batching, roles and membership of decision slots. Brands appearing only in neighboring posts remain context for those posts.
2. Test an unrelated baseline brand disappears, an unmentioned target remains, a recently added product or alias owner remains, both owners of a shared name remain, and a sentinel-only discovery slot round-trips. Compare the same post alone, in a mixed batch, with different neighbors, and across a batch split. Missing or extra role slots must still be rejected. Valid release-dispute siblings and existing release-only behavior stay covered on their proper paths.
3. Run B/C and A/C comparisons. With a missing translation use the original post; when an existing translation supplies the only match it remains available. For equivalent normalized records from TwitterAPI.io and TwexAPI capture identical requests. For a TwexAPI quote with only its ID preserve the targets and absence of quote text, including when the fuller version had an additional context-only brand.

**Exit:** C demonstrably removes unrelated brands and further reduces tokens. Activate independently only when the semantic, cost and operational gates pass; otherwise B remains a separately viable outcome.

### U4. Verify persistence, historical playback, collection and rollout at each stage

**Requirements:** R1–R5. **Runs at:** U1 control, U2 B and U3 C. **Files:** `monitor/cycle.py`, `monitor/backfill_enrichment.py`, `monitor/classification_persistence.py`, `x_monitor/classifier_0731_prompts.py`, `tests/test_backfill_direct_enrichment.py`, `tests/test_enrichment_worker.py`, `tests/test_classified_product_releases.py`, `tests/test_cycle_regression_net.py`.

- A pending role, invalid sibling, partial batch, budget refusal/deadline, retry or duplicate completion follows the existing publication and reservation rules. Drive a mixed-brand promotion retry through the worker. A finished sibling remains selected, a material correction still follows the existing replacement path, and an independently due release or translation can run with the remaining budget.
- Replay an old paid backfill request after catalog growth and after a neighbor has completed. Keep its exact original request bytes/hash, role order, full member list, source, catalog and original role revision. Consume only the pending member, once, with zero physical sends. Exercise scheduled/enrichment, manual, repair, saved and Pulse-backfill callers explicitly. Keep manual/deferred requests on the existing protocol and both local full-catalog readers intact.
- Drive an actual scheduled cycle with recorded search pages and fake HTTP through persistence. Compare time bounds, provider order/switch, cursors, logical calls, physical page requests, coverage, fetched IDs, distinct inserts and PostBrand attribution with A. Cover full page followed by a TwexAPI empty continuation, a failed first page, provider cooldown, a saved quote with and without body, and manual current-policy queries.
- For activation later, select A → B → C one step at a time. Retain A as immediate rollback of B, and B as rollback of C. Exercise mode rollback with already-claimed work and paid deferred replies in flight. The switch affects future dispatches. Record which mode served in-flight work and report affected IDs and any erroneous labels still selected. Historical corrections require separate authorization. Keep live harvesting running throughout. A missing verified stage metric holds promotion.

---

## Verification Contract

### Proof and regression suites

Use a verified branch-specific fixture database or the repository’s locked shared test wrapper. Never run tests against production. Commands below belong to implementation. Planning does not execute them.

| Proof | Commands or expected evidence |
|---|---|
| Prompt, transport and ownership | `scripts/pytest-local tests/test_u18a_classifier_contract_v4.py tests/test_u18_runtime_0731.py tests/test_promotion_subject_matcher.py`. Capture actual outgoing user and system content for both roles. |
| Worker, persistence, retry, reader and Pulse | `~/.local/bin/pushinweight-test-db pytest tests/test_enrichment_worker.py tests/test_classifier_translation_u5.py tests/test_u18a_v4_classification_persistence.py tests/test_classified_product_releases.py tests/test_backfill_direct_enrichment.py`. Include the existing Maya, shared-name and mixed-brand retry cases and new end-to-end pins. |
| Collection protection | `~/.local/bin/pushinweight-test-db pytest tests/test_cycle_regression_net.py tests/test_cycle_search_caps.py tests/test_cycle_tip_sweep.py tests/test_twexapi_search.py tests/test_twexapi_breaker.py tests/test_x_provider_contract.py tests/test_harvest_query_exhibit.py`. Re-run the inherited renderer/byte gate below for every active shape. |
| Costs and retries | Exercise `tests/test_provider_telemetry_call_chain.py` and the existing DeepInfra usage path. Charge every physical attempt once including failures and retries where usage is provided. Unknown charges stay unknown. Keep missing receipts and refusals before dispatch distinct from paid attempts. |
| Revision and coverage | Compare any failing check with clean pinned main. Fix a causal regression. For a stale assertion document the original property and test that property on the current schema/path. Record executed, skipped and unavailable suites explicitly. |

### Same-batch measurement and acceptance

1. Compare A/A, A/B, B/C and A/C at fixed cases, slots, source, catalog snapshot, model settings and role order. For each arm and role record exact sent bytes, input tokens from the pinned tokenizer, per-batch median/p95 and total. Benchmark selection and prompt construction on the full current catalog, including a product-heavy batch. Report wall time and budget headroom. Both calls keep the same reservation, and each attempt stays within the current dispatch deadline.
2. Pair on ordered post IDs, role and attempt, with the physical request ID and original/effective revision. A first-post batch key alone is insufficient. Record input, cached input, output and retries. Primary financial metric is all attributable charges, including failed/retried attempts, divided by distinct fixed-cohort posts with at least one real brand meeting the reader-visible type-and-sentiment test at the same observation age. A zero denominator is undefined. Report fully covered, partially covered, context-only, and sentinel-only posts, every eligible brand pair, and spend per 1,000 eligible posts. In `x_monitor/deepinfra.py::_usage`, `cost_usd` preferentially reads `usage.estimated_cost`. Label it provider-estimated unless a settled billing record establishes the actual charge. Keep tokenizer predictions, provider estimates and verified charges in separate columns. Use existing request-linked billing records or an isolated reconcilable billing total for the exact arm/time/request set. Missing evidence leaves actual dollar savings unverified. Keep the historical 77% cost reduction and offline 86% input reduction as references only.
3. Quality denominator is every frozen eligible PostBrand. Primary retention numerator is pairs with a selected usable sentiment **and** post type visible through the reader. Report first usable, current selected, post type, sentiment, audience, geopolitics and product separately, with actual values as well as fill rates. Break out pending, invalid and completed `context_missing`, post-level promoted subjects/flags, and release decisions. Keep provider, language, per-brand, multi-brand and newest-brand counts with denominators.
4. Freeze expected outcomes for the challenge set before viewing candidate labels. Include the acceptance examples, Qwen Models ordinary prose, a true namesake, a tracked product named without its publisher, a genuinely unknown promoter, and mixed tracked/untracked promotions with different flags. Score source-grounded type and sentiment for each brand, exact surviving promoters and evidence, and the post-level set of flags. A flag supported only by an excluded tracked promotion fails. Per-subject links among multiple surviving subjects are unobservable in this contract. For the fixed first qualification cohort, blind-score the challenge cases and all representative pairs, including unchanged outputs. Freeze the adjudication rubric before opening the arms. Saved A answers passed through B/C only test decoding/publication. Only exact candidate-output receipts or a separately authorized paired experiment test changed model behavior. Quote the proposed cost, cohort, sample size and hard cap before requesting spend, including any A/A repeats.
5. Proposed advancement criteria, frozen before candidate outputs: zero failed deterministic invariants and zero newly introduced ownership errors on the challenge set. On the representative cohort require no observed decrease in primary retention or adjudicated label correctness, with a one-sided 95% lower bound for each paired difference above −2 percentage points (resample by batch). Show usable-to-unusable and correct-to-incorrect pairs separately from gains for each axis and segment. A confirmed candidate-caused loss of a supported label or a newly wrong owner holds the stage anywhere in the adjudicated cohort. Keep legitimate corrections visible. An unexplained loss stays open. Require fewer total input tokens per advancing step and lower verified billed cost per usable post versus its predecessor under comparable cache conditions for the financial pass. With estimates only, report local/estimated results and hold the billed-cost verdict and stage promotion. Too few batches or missing receipts means insufficient evidence, not a pass. Compare C against A as well.
6. Once rollout is separately authorized, observe at least four completed consecutive 15-minute slots per step and recheck an identical frozen latest-20 cohort after its 30-minute grace. Count per-brand unique posts/hour by first collection, deduplicated all-brand totals, and at fixed age their usable classifications. Compare with the immediately preceding healthy control and the recovery report’s matched JST time slots. Record expected/sent searches, pages, provider receipts/429s/5xx, cursor and coverage, backlog/age, timeouts, cycle duration, worker reservations and unclassified reasons. A concurrent supplier incident leaves the live comparison inconclusive. A verified candidate-caused loss, retry cross-write, wrong owner or budget overrun switches back to the preceding verified state before further rollout.

### Search query continuity

Capture exact outgoing scheduled and manual query text with fake providers. Compare A/B/C byte-for-byte for each enabled call including configured special events, exclusions, Boolean groups and time bounds. Inventory call ID, final UTF-8 bytes, headroom to 512, registry/config revision and fixture. Put the completed control and candidate audit in the change review before approving activation. The Nov 20 control exhibit in `docs/plans/2026-11-20-112341-fix-feed-enrichment-unclassified-20261120-plan.md` lists every audited call and the optional special-event variants, including B8 at 511 bytes. That exhibit is historical. Revalidate the actual active registry, exclusions, emitter and backfill/scheduled variants on the integration revision. No live X calls are needed. A missing enabled call, differing byte sequence or overflow fails this gate.

---

## Definition of Done

1. The two changes have independent before/after measurements and rollback proofs. Report which of A, B or C qualified. Preserve the last verified state when a later step lacks evidence.
2. Real caller-to-reader tests cover both DeepSeek calls, all target slots, local ownership, retries and replay, and provider-to-insert collection parity. Canonical snapshots pass their validator. Historical packets remain consumable without a new model call.
3. Record the results and remaining unknowns for collection, reader-visible label quality and billed cost separately. Local/offline proof, authorized paired-model proof and observed production proof have separate statuses.
4. No schema migration, fresh production backfill, search change, spend authorization or deploy is implicit in this plan.

## Sources and prior evidence

- Current base `24812f0e`. Selector `6ab9b30d`, source-matched terms `61c571f0` and `421d4d16`, shared-owner publication fix `84b921ae`. Runtime `x_monitor/attribution.py`, `monitor/cycle.py`, `monitor/backfill_enrichment.py`, `monitor/classification_persistence.py`.
- In the authoritative checkout’s historical worktree `.worktrees/docs/classifier-catalog-removal-20261111`, inspect `monitor/tagged_brand_entries.py` and `tests/test_tagged_brand_entries.py` as uncommitted reference files. Its `docs/analysis/2026-11-13-163752-classifier-catalog-validation.md` records the paired 200-post comparison. Its 10 batches overrepresent hard previously successful posts and contain no Token Machine post.
- `docs/plans/2026-11-24-012909-fix-feed-collection-recovery-20261123-plan.md` records recovery and collection metrics. `docs/solutions/integration-issues/2026-11-21-065100-enrichment-reservations-and-reader-coverage.md` documents why reservations and attempt counts can conceal reader-visible losses.

<!-- BEGIN OLLIJA DELIVERY GUIDE -->
## Ollija Delivery Guide

Generated by `ollija annotate-plan`; do not edit between the markers. Delivery policy lives in `AGENTS.md` under "Plans and delivery". Project facts (host, repository, branches, environments, URLs and blueprints) live in `.ollija/project.yaml`. Record owner exceptions under Delivery Exceptions below.

- Plan: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/docs/compact-feed-catalog-20261124/docs/plans/2026-11-24-083652-docs-compact-feed-catalog-20261124-plan.md`
- Branch: `docs/compact-feed-catalog-20261124`
- Change: `docs-compact-feed-catalog-20261124-2026-11-24-083652`
- Active worktree: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/docs/compact-feed-catalog-20261124`
- Workflow: `delivery`
- Delivery target: `production`
- Route: `direct`
- Owner selection recorded: `true`

### Placement

This worktree is inside the Ollija release worktree area. Reuse it for the whole change. Do not create a second worktree or plan for this branch.

### Delivery steps

1. Complete implementation and the plan's verification contract.
2. Run the configured focused checks:
   - `pytest tests/ollija`
3. The parent workflow commits only this plan's changes, pushes the feature branch, and records the candidate SHA.
4. On the owner-selected direct route, fetch the remote production lane: `git fetch origin refs/heads/main`.
5. Require the same unchanged candidate SHA to be a fast-forward of that fetched remote ref, then push the exact candidate SHA to `refs/heads/main` with the server-enforced fast-forward command `git push origin <candidate-sha>:refs/heads/main`.
6. Verify the remote production ref resolves to the candidate SHA and the deployment for `pushinweight-web` reports that same SHA before reporting completion.
7. After step 6 succeeds, perform worktree cleanup as the final filesystem action:
    - From `/Users/fuchitalee/development/pushin-weight-v2`, require `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/docs/compact-feed-catalog-20261124` to remain registered, clean, unlocked, and at the verified candidate SHA. If any guard fails, retain it and report the reason.
    - Run `git -C /Users/fuchitalee/development/pushin-weight-v2 worktree remove /Users/fuchitalee/development/pushin-weight-v2/.worktrees/docs/compact-feed-catalog-20261124` without `--force`.
    - Preserve the local and remote feature branches. Continue final reporting from the authoritative repository root.

Occupied staging: if a staged route finds `staging` in use by an unrelated release while production is authorized, follow the occupied-staging default in `AGENTS.md`.
<!-- END OLLIJA DELIVERY GUIDE -->

## Delivery Exceptions

The shared staging branch contains a separate Chatter trial at fa85d9d3. Use the repository’s occupied-staging direct-production route. Keep local trial receipts on the authoritative host.
