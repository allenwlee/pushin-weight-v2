---
title: Rare-Type Query Widening Research - Plan
type: feat
date: 2026-09-23
topic: rare-type-query-widening-research
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ce-brainstorm
execution: code
ollija:
  change_id: feat-combined-rare-type-extra-search-2026-09-23-070740
  branch: feat/combined-rare-type-extra-search
  workflow: plan
  delivery_target: staging
  delivery_selected_by_user: true
---
<!-- BEGIN OLLIJA DELIVERY GUIDE -->
## Ollija Delivery Guide

This block is generated guidance. Do not edit it directly. Correct durable facts in `.ollija/project.yaml` or this template, then rerun `ollija annotate-plan`. Put a user-directed exception in the editable Delivery Exceptions section below.

### Resolved locations

- Authoritative host: `fuchitalee`
- Authoritative repository: `/Users/fuchitalee/development/pushin-weight-v2`
- Ollija release worktree area: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees`
- Active worktree: `/Users/fuchitalee/development/pushin-weight-v2`
- Plan: `/Users/fuchitalee/development/pushin-weight-v2/docs/plans/2026-09-23-070740-feat-rare-type-query-widening-research-plan.md`
- Change: `feat-combined-rare-type-extra-search-2026-09-23-070740`
- Branch: `feat/combined-rare-type-extra-search`
- Staging branch and blueprint: `staging`, `/Users/fuchitalee/development/pushin-weight-v2/render-staging.yaml`
- Production branch and blueprint: `main`, `/Users/fuchitalee/development/pushin-weight-v2/render.yaml`
- Staging URL: `https://pushinweight-staging-web.onrender.com`
- Production URL: `https://pushinweight-web.onrender.com`

### Placement

1. Move this worktree from `/Users/fuchitalee/development/pushin-weight-v2` to `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/combined-rare-type-extra-search` before any other delivery action.
2. Rerun `ollija annotate-plan` after the move; this guide contains stale active-worktree paths until then.
Ollija does not move or reject the worktree.

### Delivery scope

- Workflow: `plan`
- Delivery target: `staging`
- Owner selection recorded: `true`

1. Complete implementation and the plan's verification contract.
2. Run the configured focused checks:
   - `pytest tests/ollija`
3. The parent workflow commits only this plan's changes, pushes the feature branch, and records the candidate SHA.
4. Fetch the remote staging lane: `git fetch origin refs/heads/staging`.
5. Require the unchanged candidate SHA to be a fast-forward of that fetched remote ref, then push the exact candidate SHA to `refs/heads/staging` with the server-enforced fast-forward command `git push origin <candidate-sha>:refs/heads/staging`.
6. Verify the remote staging ref resolves to the candidate SHA and the deployment for `pushinweight-staging-web` reports that same SHA.
7. Run staging checks. Stop here if they fail.

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

## Delivery Exceptions

None.

# Rare-Type Query Widening Research - Plan

## Plain-English Summary

Measure broader extra-search strings so they find more relevant AI personnel, jobs, events, opportunities, and model-release posts, even if they also fetch junk. Target research volumes are about 20 raw posts/hour, with 50/hour worth exploring. Do not turn extra search on in harvest. Do not rewrite the full-feature plan’s enablement gates in this run.

Grok/X search is used first to learn wording. TwitterAPI.io on-demand, harvest-shaped one-call queries (outer parens, `min_faves:0`, time kwargs, under 512) validate what the production lane would actually return. Cap: 6 on-demand pages (3 candidates × 2 matched 15-minute windows).

## Goal Capsule

- **Objective:** Compare baseline vs broader vs broadest combined extra-search strings on matched windows and recommend which, if any, better recovers relevant posts near 20 and 50 raw posts/hour.
- **Means:** Versioned candidate strings, Grok X search for vocabulary, then a 6-page ON_DEMAND TwitterAPI.io pilot. (KTD1–KTD4)
- **Authority:** Product behavior of extra search remains off. This plan does not authorize `run_cycle` extra-search enablement.
- **Execution profile:** Code (trial harness + evidence report).
- **Stop conditions:** Stop if 6 pages are spent; if a candidate saturates 20/page and buries rare types; if ON_DEMAND is missing (report blocked live calls, still deliver Grok comparison).
- **Open blockers:** None for Grok research. TwitterAPI.io depends on ON_DEMAND.

## Product Contract

### Summary

Research-only widening of the Boolean extra-search query. Extra search stays off in harvest.

### Requirements

- R1. Keep one combined `advanced_search` shape: outer parens around OR groups, `min_faves:0`, time via `run_search` kwargs, rendered length ≤ 512.
- R2. Candidate A is the current `rare-types-v2-2026-09-22` planner string. B broadens action wording. C broadens wording and relaxes mandatory AI/LLM co-occurrence on high-signal branches.
- R3. Prefer relevant discoveries (including novel untracked orgs) over keeper percentage. Record junk; do not reject a candidate only for falling below 60% keepers.
- R4. Use ON_DEMAND TwitterAPI credentials only. No scheduled or legacy key. No Post inserts. No harvest enablement.
- R5. At most 6 TwitterAPI.io pages this run (3 candidates × 2 predeclared 15-minute windows × 1 page). Empty pages still count.
- R6. Deliver an evidence report under `docs/analysis/harvester/` with exact strings, window table, and judgments from post text (not DB labels as gold).

## Planning Contract

### Key Technical Decisions

- KTD1. Research does not enable extra search on `run_cycle`. (session-settled: user-directed)
- KTD2. Grok/X search first; TwitterAPI.io validates production-shaped queries. (session-settled: user-approved LFG of that recommendation)
- KTD3. Six-page ON_DEMAND cap this run. (writer assumption in LFG; 12×300 matrix was not authorized)
- KTD4. Do not silently edit the full-feature plan’s $0.06/day cap; flag it in the report if 20–50/hour cannot fit.

### Implementation Units

### U1. Freeze three planner strings under 512

- **Goal:** A, B, C planner strings with harvest wrap, hashed, length-checked.
- **Files:** `docs/analysis/harvester/2026-09-23-070740-rare-type-query-widening.md` (candidates section)
- **Approach:** A = current `planned_query_string()`. B/C drafted from live-DB misses (hiring without exact “we're hiring”, 出任/换帅, speaking/panel, apply without deadline, 开源/发布/unknown model names).
- **Test:** Render each with dummy epochs; `assert_under_length_cap`; outer `) min_faves:0`.
- **Dependencies:** none

### U2. Grok X keyword probe of B/C phrases

- **Goal:** Confirm broader phrases retrieve the known-positive examples and fresh EN/ZH/JA hits.
- **Approach:** `x_keyword_search` Latest; record interface, query, timestamps. Not an hourly rate.
- **Dependencies:** U1

### U3. Six-page TwitterAPI.io matched-window pilot

- **Goal:** Same two completed 15-minute UTC windows for A, B, and C.
- **Files:** trial command or one-shot Python using `TwitterApiClient.from_env(ON_DEMAND)`, `max_retries=0`, `max_pages=1`.
- **Approach:** Windows: two recent completed 15-minute buckets (e.g. last full :00–:15 and :15–:30 before run). Save full JSON locally; do not insert posts.
- **Dependencies:** U1

### U4. Evidence report

- **Goal:** Recommendation plus table: raw/unique/capped, relevant/junk/uncertain, overlap unknown if staging/prod DB unavailable.
- **Files:** `docs/analysis/harvester/2026-09-23-070740-rare-type-query-widening.md`
- **Dependencies:** U2, U3 (U3 skipped with explicit blocker if no ON_DEMAND)

## Verification Contract

- Length checks on A/B/C.
- Report names provider per row (Grok vs TwitterAPI.io).
- No `run_cycle --scheduled`. No secret values in git files.

## Definition of Done

- Report written with A/B/C strings and Grok results.
- TwitterAPI.io 6-page table or documented ON_DEMAND miss.
- Extra search still off. Unrelated dirty files untouched.
