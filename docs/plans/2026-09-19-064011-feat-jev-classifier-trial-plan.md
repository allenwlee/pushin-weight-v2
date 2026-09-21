---
title: "Jev Classifier Trial - Plan"
type: feat
date: "2026-09-19"
topic: jev-classifier-trial
artifact_contract: ce-unified-plan/v1
artifact_readiness: requirements-only
product_contract_source: ce-brainstorm
execution: code
ollija:
  change_id: feat-jev-classifier-trial-2026-09-19-064011
  branch: docs/llm-cost-token-report-20260903
  workflow: plan
  delivery_target: on-request
  delivery_selected_by_user: false
---
<!-- BEGIN OLLIJA DELIVERY GUIDE -->
## Ollija Delivery Guide

This block is generated guidance. Do not edit it directly. Correct durable facts in `.ollija/project.yaml` or this template, then rerun `./bin/ollija annotate-plan`. Put a user-directed exception in the editable Delivery Exceptions section below.

### Resolved locations

- Authoritative host: `fuchitalee`
- Authoritative repository: `/Users/fuchitalee/development/pushin-weight-v2`
- Ollija release worktree area: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees`
- Active worktree: `/Users/fuchitalee/development/pushin-weight-v2`
- Plan: `/Users/fuchitalee/development/pushin-weight-v2/docs/plans/2026-09-19-064011-feat-jev-classifier-trial-plan.md`
- Change: `feat-jev-classifier-trial-2026-09-19-064011`
- Branch: `docs/llm-cost-token-report-20260903`
- Staging branch and blueprint: `staging`, `/Users/fuchitalee/development/pushin-weight-v2/render-staging.yaml`
- Production branch and blueprint: `main`, `/Users/fuchitalee/development/pushin-weight-v2/render.yaml`
- Staging URL: `https://pushinweight-staging-web.onrender.com`
- Production URL: `https://pushinweight-web.onrender.com`

### Placement

1. Move this worktree from `/Users/fuchitalee/development/pushin-weight-v2` to `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/docs/llm-cost-token-report-20260903` before any other delivery action.
2. Rerun `./bin/ollija annotate-plan` after the move; this guide contains stale active-worktree paths until then.
Ollija does not move or reject the worktree.

### Delivery scope

- Workflow: `plan`
- Delivery target: `on-request`
- Owner selection recorded: `false`

Target is not authorized until the owner selects it. Wait for a later explicit release request; do not commit, push, stage, or promote on this guide alone.

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
# Jev Classifier Trial - Plan

## Plain-English Summary

Jev is a decision model, not a writer. It returns yes/no probabilities, a pick from a list, or a score. It cannot translate posts or write commentary.

This plan covers one job: trial Jev as a possible replacement for the planned DeepSeek V4 Flash 0731 classifier. Each label is its own yes/no; code combines those answers into today's labels. Jev becomes the live classifier only if it is not worse on the hard cases you already care about (multi-label completeness, implied praise, brand-specific sentiment and stance). If the trial is mixed, 0731 stays. There is no Jev-in-front safety net.

As of 18 Sep 2026, Jev is on OpenRouter in beta (`~typesafe/jev-latest` → `typesafe/jev-1.13`). That is the trial access path. It uses OpenRouter's Decisions API, not chat completions. The TypeSafe waitlist is no longer a blocker for this eval.

This document does not authorize production. It does not cover translation, commentary, headlines, or new feed features.

---

## Goal Capsule

- **Objective:** The operator can decide, from a scored trial on existing owner-reviewed packets, whether Jev may replace 0731 as the classifier without making the named hard cases worse.
- **Means:** Run Jev through OpenRouter's Decisions API on the same reviewed corpus and label contract as 0731; combine per-label yes/no answers in code; switch only if the hard-case bar passes.
- **Product authority:** Classification only. Translation, commentary, headlines, ranking, alerts, and LLM-gating of writers are surrounding areas, not this plan's requirements.
- **Open blockers:** None for starting the offline OpenRouter trial. Production switch remains blocked until the trial passes R3. OpenRouter lists Jev as beta; capacity and the 32k listed context vs TypeSafe's 64k must be treated as trial constraints, not as proven production limits.

---

## Product Contract

### Summary

Trial Jev as a drop-in classifier candidate via OpenRouter. Keep today's label contract. Replace 0731 only if hard cases do not regress. Mixed or failed trial leaves 0731 in place.

### Problem Frame

The planned Stage 1 classifier is two 0731 roles per batch of 20. It is cheap and competitive on owner-reviewed development packets, but post-type exact sets and secondary-label recall stay weak. TypeSafe Jev is built for typed decisions with many independent questions in one call, which matches multi-label completeness better than a single JSON blob. Direct TypeSafe access was waitlisted. OpenRouter listed Jev on 18 Sep 2026, so the trial can run without that waitlist. Early OpenRouter users report speed and cost as advertised, and mixed quality on nuanced reading — the same risk this trial exists to measure.

### How This Work Fits Together

<!-- ce-section: work-relationships -->

This plan owns **classification**. The broader Jev breakdown below is current understanding, not a committed roadmap.

- **Classification (this plan).** Trial and possible replace of 0731. Depends on OpenRouter Decisions access and existing owner-reviewed packets. Enables a later production classifier change only if R3 passes.
  - **Judge existing LLM jobs.** Can proceed independently of a production Jev classifier. Shares the same OpenRouter Jev route. Still to decide whether commentary/headline grounding checks are worth a separate plan.
  - **New feed features.** Ranking, badges, alerts, commentary spend gates. Depends on stored per-label probabilities if classification ships Jev; can be prototyped independently. Deferred.
  - **Translation and commentary writers.** Outside Jev's identity. Jev cannot emit text. 0731/4.1 remain the writer candidates from the separate model-selection thread.

### Key Decisions

- **Classification is the only active Jev job** (session-settled: user-directed — chosen over new feed uses, judging writers, or a usage-map-first brainstorm). Governs R1.
- **Replace 0731 only if the reviewed set wins** (session-settled: user-directed — chosen over always-in-front dual-running, decompose-now with 0731 backup, or eval-only-forever). Governs R3, R4.
- **Wins means no regression on hard cases** (session-settled: user-directed — chosen over beating overall agreement, matching 0731 plus cost/speed, or owner eyeball with no percentage). Governs R3.
- **Yes/no per label, combine in code** (session-settled: user-directed — chosen over mimicking two 0731 roles or blanking low-confidence labels as context_missing). Governs R2.
- **Trial access is OpenRouter Decisions, not the TypeSafe waitlist** (session-settled: user-directed — chosen after Jev listed on OpenRouter 18 Sep 2026). Governs R7.
- **Full current label set and mixed-language packets are in the trial.** User skipped those menus; this is an assumption, not a session-settled choice. Governs R5, R6.

### Requirements

**Trial job**

- R1. The first Jev work is an offline classifier trial against existing owner-reviewed packets. It does not change production classification until R3 passes.
- R2. Each post type, promotion flag, and similar multi-label is its own yes/no. Sentiment and stance stay pick-one. Code combines answers into today's persisted labels. `Other` is used only when every type is no.
- R3. Jev replaces 0731 only when it is not worse on multi-label completeness, implied praise, or brand-specific sentiment and stance. A higher overall agreement or a cheaper bill is not enough.
- R4. If the trial is mixed or fails R3, 0731 remains the classifier. The product does not run Jev in front of 0731 in production.

**Label coverage**

- R5. The trial covers the full current classification contract (post types including exclusive `Other`, audience topics, untracked promotions, per-brand product labels, sentiment, geopolitical modes, national stance, and context_missing), not a field subset.
- R6. ZH/JA posts already in the reviewed packets can fail the switch. The trial does not ignore CJK because English looks fine.
- R8. The trial reuses existing reviewed packets. It does not demand a new owner labeling pass.

**Access**

- R7. The trial calls Jev through OpenRouter's Decisions API using a pinned Jev 1.13 identifier. It does not send Jev through chat-completions. It does not wait on a TypeSafe waitlist key to start.
- R9. OpenRouter beta capacity issues (timeouts, 429s, incomplete answers) are recorded as operational failures, separate from semantic hard-case misses.
- R10. Any later classifier implementation stays staging-only until the owner separately selects a delivery target. This plan does not authorize production activation.

### Actors

- A1. Owner/operator who already reviewed the packets and will read the trial report.
- A2. Feed readers who see labels only if a later switch ships; this trial does not change what they see.
- A3. Jev on OpenRouter (beta Decisions route).
- A4. 0731 DeepInfra two-role classifier as the frozen control.

### Key Flows

- F1. Offline trial
  - **Trigger:** Operator starts the Jev classifier trial.
  - **Actors:** A1, A3, A4
  - **Steps:** Load the existing reviewed packets. Score 0731 control if not already frozen. Call Jev on OpenRouter Decisions with per-label questions. Combine answers in code into the current contract. Score hard-case axes and operational failures separately.
  - **Outcome:** A pass/fail against R3, plus an operational-failure count from R9.
  - **Covered by:** R1, R2, R3, R7, R8, R9
- F2. Switch or keep
  - **Trigger:** Trial report exists.
  - **Actors:** A1, A2, A4
  - **Steps:** If R3 passes, Jev may become the planned classifier default in a later staging implementation. If mixed or fail, keep 0731. Do not add a production Jev-in-front path.
  - **Outcome:** One classifier default, not two.
  - **Covered by:** R3, R4, R10

### Acceptance Examples

- AE1. Hard-case miss fails the switch
  - **Covers R3, R4.**
  - **Given:** Jev's overall agreement is higher than 0731, but it is worse on multi-label completeness or implied praise on the reviewed packet.
  - **When:** The operator reads the trial report.
  - **Then:** 0731 stays. Jev is not adopted.
- AE2. CJK miss fails the switch
  - **Covers R6, R3.**
  - **Given:** English rows look fine and a ZH or JA reviewed row regresses on a hard-case axis.
  - **When:** The trial is scored.
  - **Then:** The switch fails. English-only success is not a pass.
- AE3. OpenRouter 429 is not a semantic miss
  - **Covers R9.**
  - **Given:** Some Jev calls return 429 or timeout and others complete with labels.
  - **When:** The report is written.
  - **Then:** Incomplete calls are counted as operational failures, not as wrong labels.
- AE4. Chat-completions is the wrong call
  - **Covers R7.**
  - **Given:** A client posts Jev as a chat model on OpenRouter.
  - **When:** The trial harness runs.
  - **Then:** That path is rejected. Only Decisions API calls count.

### Success Criteria

- S1. The trial report states pass/fail on R3 with the hard-case axes named, not only an overall percentage.
- S2. Owner blanks in the reviewed packets stay unknown, not negative gold.
- S3. No production classifier, prompt, or database write is required for the trial to be complete.

### Scope Boundaries

**Deferred for later**

- Jev as a grounding judge on commentary or headlines.
- Commentary spend gates, feed ranking, badges, and rare-type alerts.
- Dual-running Jev in front of 0731.
- Local OpenJev / SemIf / Hillary 4B logit scorers as a production classifier.

**Outside this product's identity**

- Jev writing translations, commentary, or headlines.
- Replacing headline spend as part of this trial.
- Treating OpenRouter chat-completions as a Jev interface.

### Dependencies / Assumptions

- OpenRouter listed Jev on 18 Sep 2026 as beta. Listing: `~typesafe/jev-latest` aliasing `typesafe/jev-1.13`. Price on that page: $0.042 per million input, output free. Listed context: 32k tokens (TypeSafe direct docs say 64k). Recheck before a large run.
- Existing owner-reviewed packets and the 0731 two-role control live in the ai-enrichment-stage1 worktree analysis, not on this docs-branch checkout.
- Full contract and CJK-in-packet assumptions stand because those menus were skipped.
- Classification unit cost for 0731 DeepInfra is $0.093 per 1,000 posts (R116 token mix). Jev classifier savings are small versus headlines/translation. Cost is not the switch bar (R3).

### Outstanding Questions

**Resolve Before Planning**

- None for an offline OpenRouter trial that only writes a report.

**Deferred to Planning**

- Exact OpenRouter request shape, pinning `typesafe/jev-1.13` vs the `latest` alias, and how to pack ~40 questions under the listed 32k cap.
- Whether 0731 control scores are reused from frozen R116/fresh-40 artifacts or re-run.
- How many OpenRouter calls per post (one state, many questions) versus batching posts (rejected for Jev accuracy, but concurrency of 20 one-post calls is allowed).
- Where trial outputs and the report file are written.

### Sources / Research

- Classifier contract and two-role 0731 prompts: `core/classification_contract.py`, `x_monitor/classifier_0731_prompts.py` in `.worktrees/feat/ai-enrichment-stage1`.
- Stage 1 classifier default: `docs/plans/2026-09-08-134925-feat-ai-enrichment-stage1-plan.md` (worktree copy).
- 0731 cost/quality: `docs/analysis/2026-09-15-213853-u18-v4-0731-deepinfra-batch20-comparison.md`; unit table `docs/research/2026-09-17-144306-snapshot-only-model-task-cost-screen/README.md`.
- Live classification token share (old one-role 4.1, not 0731): `docs/analysis/2026-09-17-140729-production-token-volume-by-pacific-hour.md`.
- Machine-local grounding extraction: `/tmp/compound-engineering-501/ce-brainstorm/jev-pushinweight-20260918/grounding.md`.
- OpenRouter listing and Decisions API (18 Sep 2026): OpenRouter `~typesafe/jev-latest`; TypeSafe CTO note to treat the beta gently.

---

## Delivery Exceptions
