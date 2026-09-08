---
title: Staged AI Enrichment Architecture Roadmap - Plan
type: feat
date: 2026-09-08
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ce-plan-bootstrap
execution: code
ollija:
  change_id: staged-ai-enrichment-roadmap-2026-09-08-194415
  branch: feat/ai-enrichment-stage0
  workflow: lfg
  delivery_target: production
  delivery_selected_by_user: true
---
<!-- BEGIN OLLIJA DELIVERY GUIDE -->
## Ollija Delivery Guide

This block is generated guidance. Do not edit it directly. Correct durable facts in `.ollija/project.yaml` or this template, then rerun `ollija annotate-plan`. Put a user-directed exception in the editable Delivery Exceptions section below.

### Resolved locations

- Authoritative host: `fuchitalee`
- Authoritative repository: `/Users/fuchitalee/development/pushin-weight-v2`
- Ollija release worktree area: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees`
- Active worktree: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/ai-enrichment-stage0`
- Plan: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/ai-enrichment-stage0/docs/plans/2026-09-08-194415-feat-staged-ai-enrichment-roadmap-plan.md`
- Change: `staged-ai-enrichment-roadmap-2026-09-08-194415`
- Branch: `feat/ai-enrichment-stage0`
- Staging branch and blueprint: `staging`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/ai-enrichment-stage0/render-staging.yaml`
- Production branch and blueprint: `main`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/ai-enrichment-stage0/render.yaml`
- Staging URL: `https://pushinweight-staging-web.onrender.com`
- Production URL: `https://pushinweight-web.onrender.com`

### Placement

This worktree is inside the Ollija release worktree area. Reuse it for the whole change. Do not create a second worktree or plan for this branch.

### Delivery scope

- Workflow: `lfg`
- Delivery target: `production`
- Owner selection recorded: `true`

1. Complete implementation and the plan's verification contract.
2. Run the configured focused checks:
   - `pytest tests/ollija`
3. The parent workflow commits only this plan's changes, pushes the feature branch, and records the candidate SHA.
4. Fetch the remote staging lane: `git fetch origin refs/heads/staging`.
5. Require the unchanged candidate SHA to be a fast-forward of that fetched remote ref, then push the exact candidate SHA to `refs/heads/staging` with the server-enforced fast-forward command `git push origin <candidate-sha>:refs/heads/staging`.
6. Verify the remote staging ref resolves to the candidate SHA and the Render deployment for `pushinweight-staging-web` reports that same SHA.
7. Run staging checks. Stop here if they fail.
8. Only after staging passes, fetch the remote production lane: `git fetch origin refs/heads/main`.
9. Require the same unchanged candidate SHA to be a fast-forward of that fetched remote ref, then push the exact candidate SHA to `refs/heads/main` with the server-enforced fast-forward command `git push origin <candidate-sha>:refs/heads/main`.
10. Verify the remote production ref resolves to the candidate SHA and the Render deployment for `pushinweight-web` reports that same SHA before reporting completion.
11. After step 10 succeeds, perform worktree cleanup as the final filesystem action:
    - From `/Users/fuchitalee/development/pushin-weight-v2`, require `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/ai-enrichment-stage0` to remain registered, clean, unlocked, and at the verified candidate SHA. If any guard fails, retain it and report the reason.
    - Run `git -C /Users/fuchitalee/development/pushin-weight-v2 worktree remove /Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/ai-enrichment-stage0` without `--force`.
    - Preserve the local and remote feature branches. Continue final reporting from the authoritative repository root.

### Failure handling

- Never promote a staging candidate whose automated checks failed.
- Implementation failures return to the parent implementation workflow for diagnosis, correction, recommit, and restaging.
- SSH, shell, environment, or multi-machine failures use the repository infra/multi-machine skill first.
- The change ledger is advisory; do not validate or enforce it.
- Never force-remove a worktree. Retain staging-only, failed, dirty, locked,
  noncanonical, or candidate-mismatched worktrees for diagnosis or later
  delivery.
- Do not run an endless retry loop or start a persistent Ollija process.
<!-- END OLLIJA DELIVERY GUIDE -->
# Staged AI Enrichment Architecture Roadmap

## Delivery Exceptions

1. Stage 0 completed staging verification at `04f4165`. The owner now explicitly authorizes its production promotion after the parent reads the production guide and passes its required check. This does not authorize a production harvest pause or resume, manual production cycle, production database manual mutation, or paid acceptance job.
2. The owner authorizes Stage 1 continuation after Stage 0 promotion. Stage 1 development may proceed during the natural Stage 0 production baseline window (owner target: 90 minutes; acceptable baseline: 1–2 hours). Stage 1 staging deployment requires baseline review; Stage 1 production promotion is not authorized. Stages 2–4 remain unauthorized.
3. Keep the canonical Stage 0 worktree through the production baseline and Stage 1 handoff/continuation. The owner-directed rationale is that cleanup must be the final filesystem action across this continuation; do not remove it before then. This exception overrides any earlier cleanup or move-root guidance. Do not move or repurpose the dirty authoritative root or its `docs/llm-cost-token-report-20260903` branch, import unrelated root files, or force-push.
4. The active executable units remain Stage 0 until a Stage 1 plan extension is ready. This production authorization does not expand Stage 0 source scope.

## Goal Capsule

Build a shared measurement and contract foundation for cheaper, faster AI enrichment while preserving current product behavior. The roadmap then sequences four separately authorized changes: compact classification, demand-shaped headline work, split enrichment roles, and bounded multilingual synthesis. This run implements Stage 0 only.

## Product Contract

The default product remains AI synthesis. Literal translation and compact classification stay universal and eager where required for discovery and the reading experience. EN, ZH-CN, and JA have equal support. Later stages must keep collection, charts, filters, and headline consumers inclusive of posts whose synthesis is pending; Stage 0 records this invariant without changing current visibility. Product source: `docs/ideation/2026-09-05-144719-llm-token-efficiency-harvester-ideation.md` plus the session-settled brief.

Settled keep-the-decision (KTD) constraints are:

- AI synthesis remains the per-post default (session-settled: user-directed — chosen over deterministic prose because the product requires analyst explanation).
- Collection/classification remain universal and needed translation remains eager (session-settled: user-directed — chosen over feeding only synthesized or product-labeled posts because discovery and charts require all posts).
- EN, ZH-CN, and JA follow one policy (session-settled: user-directed — chosen over JA on demand because locale parity is required).
- Stages ship separately (session-settled: user-approved — chosen over a combined refactor for causal verification and rollback).
- KTD-1: Final post types are Releases & Updates; Hands-On Usage; Results and Evaluations; Questions & Requests; Advertising & Marketing; Events & Opportunities; Opinions & Reactions; Research & Explanations; Business & Finance; Other (session-settled, user-directed; earlier variants were rejected because this final selection supersedes them).
- KTD-2: Independent product labels are Bug; Complaint; Testimonial; Ideas & requests; Misinformation (session-settled, user-directed; splitting Ideas from requests was rejected as unnecessary).
- KTD-3: Remove discourse while preserving sentiment and nationalism (session-settled, user-directed; posture/sincerity replacement was rejected because none was selected). Nationalism is stored on `PostBrandDiscourse`, so Stage 1 requires a coordinated migration and cutover for it and every discourse consumer.
- KTD-4: Pending discoverability and EN/ZH-CN/JA parity are future targets/current selected direction; Stage 0 does not fix current exclusion or add JA (session-settled, user-directed; deferring JA was rejected because parity is required).

Future completion records must identify content/context, prompt, model, taxonomy, and locale versions. `Other` is a confident residual judgment and is distinct from pending, failure, context-missing, and historical-untyped states. Stage 0 documents these contracts only; it does not add statuses, schema, a ledger, or historical relabeling. The raw 599-post audit has missing judgments; examples remain provenance-bearing analyst material, never gold labels.

## Roadmap

Stage 0 — baseline and contracts: normalize provider usage and emit structured per-transport events into existing logs, then lock deterministic synthetic fixtures and call-chain regression coverage. No paid calls or behavior change.

Stage 1 — compact classification and taxonomy migration: coordinate the 10-type/5-product-label contract and remove discourse safely. It requires a separately authorized release and a frozen-cohort evaluation.

Stage 2 — demand-shaped headline generation: use durable per-brand/window reads, material-change fingerprints, hot-list demand, stale-while-revalidate, and bounded queue work. Existing headline ledger fields remain the starting point.

Stage 3 — split enrichment: separate literal translation, classification, and synthesis preparation/persistence while preserving retries, validation, and fallback semantics.

Stage 4 — lazy synthesis: retain a small shared ready reserve, coalesce explicit demand, prefetch a bounded next slice, and persist EN/ZH-CN/JA results by versioned content/context identity. Each later stage needs its own authorization, contract review, and release gate.

## Implementation Units

Only these Stage 0 units are executable in this plan.

### U0.1 — Workspace, contracts, and fixture manifest

Create the versioned contract at `docs/reference/2026-09-08-194415-enrichment-contracts.md`, baseline at `docs/analysis/2026-09-08-194415-enrichment-stage0-baseline.md`, and fixture manifest at `tests/fixtures/llm_enrichment_evaluation_v1.json`. Record synthetic provenance explicitly and preserve analyst examples with source/provenance fields. Define nullable reported usage fields: `input`, `output`, `cache_read`, `cache_creation`, `reasoning`, and provider-reported `total`. Missing provider fields and total stay null; reserved max tokens are never actual usage; cache/reasoning fields retain provider semantics and are never assumed additive. Record future identity fields and semantic statuses as documentation only.

Owned surfaces: tests/fixtures and plan-adjacent contract documentation. Dependencies: no schema or provider change. Done proof: manifest is deterministic, examples cannot be mistaken for gold, and contract cases cover missing usage, overlap, pending/failure/context-missing, and historical-untyped distinctions.

### U0.2 — Shared usage normalizer and transport events

Add a small shared normalizer at one owned application-transport boundary and emit exactly one structured log event per application transport invocation. Events include event ID/timestamp, role, stage, run, model, provider host class, prompt identity, batch, attempt ordinal and kind, outcome/safe error category, elapsed latency, usage source, and normalized nullable usage. The translator alone uses role `post_translation_synthesis`; classifier, relevancy, and headline calls keep distinct roles. Carry outer retry, repair, and fallback context into that single event rather than emitting again in both helper and wrapper. Metadata-only events exclude API keys, prompts, source/post text, raw request/response bodies, full URLs, and exception messages. Preserve retry policy, role model configuration, response parsing, and output behavior. Do not create a database ledger, speculative TTFT, percentile infrastructure, or cost total based on reserved budgets.

Primary seams are `x_monitor/translator.py::_call_with_retry` and `ClaudeClient.messages_create`; `x_monitor/attribution.py::_call_signal_with_retry` and its classifier factory client; `x_monitor/relevancy.py::build_binary_relevancy_llm_call`; `monitor/trend_narrative_generation.py::execute_per_brand_provider_request` (SDK `max_retries=0`); and `monitor/cycle.py::CycleRunner._run_post_fetch` plus its real factories and `PostEnrichmentState` path. The production post-fetch translator and classifier factories both construct `x_monitor.attribution.AnthropicClaudeClient`, the shared direct HTTP wrapper with no hidden retry; their application loops own up to three explicit attempts. The separate legacy translator SDK wrapper and the headline SDK client use `max_retries=0`; relevancy owns one call; repair/per-post fallback are distinct application invocations. Custom client internals and literal network packets are outside the measured boundary. Reuse the existing headline ledger's input/output/latency fields; wrappers that currently discard provider usage must pass it through to the event normalizer, and reports must deduplicate the ledger from its matching log event.

Owned surfaces: provider wrappers, log event shape, and configuration propagation. Dependencies: U0.1 cases. Done proof: true production callers emit one event per application transport invocation, retries and repair have ordinal events, fallback attempts are visible, and role/model/batch context survives every seam.

### U0.3 — Call-chain regression tests

Use fake SDK/provider responses at the real production callers. Cover `CycleRunner._run_post_fetch` through `PostEnrichmentState` and real factories; translator three-try plus repair behavior; classifier batch failure with per-post fallback; relevancy calls; and `execute_per_brand_stage` through the headline transport. Assert successful usage, missing fields, overlap normalization, redaction, errors, elapsed latency, retry/repair/fallback outcomes, single-boundary event cardinality, and unchanged parsed outputs. Keep all providers fake; test database use is permitted, but no production DB writes or paid calls.

Owned surfaces: existing translator/classifier/headline transport test suites and new focused call-chain tests. Dependencies: U0.2. Done proof: tests fail if instrumentation bypasses a true caller or changes retry/fallback/output behavior.

### U0.4 — Report and promotion proof contract

Document the baseline without inventing spend. A read-only receipt from `render logs -r crn-d9gv94o4n6ts739tqaug --tail 120 --output text`, captured `2026-09-08T20:06:37+0900`, reports deploy `b184276`: run `20260908T103029_0000-508c7fc6` at `10:30:29Z` claimed/succeeded 28 posts in 82.853s post-fetch; run `20260908T100053_0000-c1ed2294` claimed 42, succeeded 40, left 2 pending in 108.909s. A separate read-only `git ls-remote` receipt resolved both remote main and staging to `b184276cc6ec4e7d1a9eba83357e824848dc8f94`. Stage 0 staging verification completed at `04f4165`; production promotion is now owner-authorized. Actual role usage remains unknown; headline input/output/latency already exist. Define promotion proof as focused tests plus `tests/ollija`, exact candidate SHA deployment, web health, and a deterministic fake-provider probe with no provider calls. Do not manually trigger a paid acceptance job. Report worker liveness only if exercised.

Owned surfaces: plan/report and release verification record. Dependencies: U0.1–U0.3 and parent delivery workflow. Done proof: reviewer can distinguish measured facts, unknowns, and later measurements; Stage 0 leaves harvest/headline behavior unchanged.

## Risk and regression net

The main risk is an observability refactor altering provider call shape or failure semantics. The regression net is the U0.3 true-caller suite plus existing queue, translator, classifier, and headline transport tests. It must assert retry counts, repair invocation, batch-to-per-post fallback, output bytes/fields, configured model, and event cardinality. A missing SDK usage field is nullable, never zero-filled. Event logging failure must not make an otherwise successful enrichment fail; if the existing logger cannot accept structured data, adapt at the logging boundary without changing provider behavior.

Do not infer cost from `max_tokens`, label counts, page views, or the 599-post audit. Do not claim headline savings, synthesis savings, p95, TTFT, or worker capacity until later measurement exists. Existing `core/models.PostEnrichmentState` is reusable backlog state for later stages; Stage 0 makes no migration.

## Promotion and rollback

The parent workflow reads the generated Ollija guide and these Delivery Exceptions, then runs the guide's required `annotate-plan --check` before Git or deployment mutation. Stage 0 staging verification completed at `04f4165`; delivery target is now production by explicit owner authorization. Production harvest pause/resume, manual production cycle, database manual mutation, and paid acceptance jobs remain unauthorized.

The forward patch is additive instrumentation and tests. Rollback is a normal forward revert of the candidate commit, followed by production health verification; no force push. Existing harvest, headline, prompt, retry, model, and output behavior must remain usable during rollback. Retain the canonical worktree through the baseline and Stage 1 continuation; cleanup, if warranted by the generated guide, is the final filesystem action only after that continuation.

## Scope, deferred work, and gates

Deferred: all executable work in Stages 1–4; schema/status changes; taxonomy migration; discourse removal and nationalism migration; event/opportunity and recap implementation; any implementation that splits the settled combined Ideas & requests label; synthesis queue/prewarm/lazy loading; headline demand policy; critic/model swaps or specialist cascades; grade/critic changes; historical relabeling; broad summary/page redesign; and real-label accuracy evaluation. These require explicit stage authorization, a frozen prompt/contract where applicable, and a new release plan or updated authorization.

Stage 0 gates are: contract cases are deterministic and provenance-safe; every named transport seam has true-caller coverage; normalizer overlap/missing-field behavior is proven; focused tests and `tests/ollija` pass; staging verified `04f4165`; production serves the exact candidate SHA; web health and fake-provider probe pass without provider calls; and no behavior regression is observed. Later-stage gates must include actual per-role/locale usage, demand, queue, latency, quality, and fallback evidence. The plan does not manufacture a spend baseline.

## Confidence and review state

Confidence is high for Stage 0 scope, seams, and verification, and medium for later economics because production per-role usage, demand, and worker liveness are not yet measured. Independent noninteractive document review by the `telemetry_audit` role completed on 2026-09-08; all P1 and applicable P2 findings were resolved, including event ownership/cardinality, privacy, role separation, true-caller proofs, baseline receipts, settled-decision provenance, and isolated delivery placement. No settled decision was invalidated. Owner read-back confirmed all six P1 corrections, so the plan is implementation-ready for Stage 0 only. The parent owns all Git, worktree, staging, and verification mutations.
