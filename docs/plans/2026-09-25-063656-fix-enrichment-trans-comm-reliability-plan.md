---
title: "fix: Make translation and commentary retries reliable"
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ollija-annotate-plan
execution: code
ollija:
  change_id: fix-enrichment-trans-comm-reliability-2026-09-25-063656
  branch: fix/enrichment-trans-comm-reliability
  workflow: lfg
  delivery_target: production
  delivery_selected_by_user: true
---

## Plain-English Summary

Long posts currently consume the translation stage's shared time allowance, and a short post can use up retry attempts without ever reaching the model. Commentary also rejects posts whose prompt exceeds the current 4,000-character guard. This change gives long translations smaller, reusable pieces; stops counting a translation attempt that was never sent; raises commentary's input guard to 32,000 characters; and records safe reasons when either stage fails.

The post text, translation model, commentary model, three output languages, and normal harvest search calls stay the same. The two historical short commentary failures are not special-cased or replayed by this plan. Streaming responses are not part of this change. Verification requires production-path tests, staging, then an exact-SHA production release and observation of a subsequent harvest cycle; no cron pause or paid X probe is authorized.

The main tradeoff is that long posts may require more model calls. Chunk caching and existing call/concurrency budgets must prevent an unbounded increase. Production is the owner-selected delivery target.

<!-- BEGIN OLLIJA DELIVERY GUIDE -->
## Ollija Delivery Guide

This block is generated guidance. Do not edit it directly. Correct durable facts in `.ollija/project.yaml` or this template, then rerun `ollija annotate-plan`. Put a user-directed exception in the editable Delivery Exceptions section below.

### Resolved locations

- Authoritative host: `fuchitalee`
- Authoritative repository: `/Users/fuchitalee/development/pushin-weight-v2`
- Ollija release worktree area: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees`
- Active worktree: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/enrichment-trans-comm-reliability`
- Plan: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/enrichment-trans-comm-reliability/docs/plans/2026-09-25-063656-fix-enrichment-trans-comm-reliability-plan.md`
- Change: `fix-enrichment-trans-comm-reliability-2026-09-25-063656`
- Branch: `fix/enrichment-trans-comm-reliability`
- Staging branch and blueprint: `staging`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/enrichment-trans-comm-reliability/render-staging.yaml`
- Production branch and blueprint: `main`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/enrichment-trans-comm-reliability/render.yaml`
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
6. Verify the remote staging ref resolves to the candidate SHA and the deployment for `pushinweight-staging-web` reports that same SHA.
7. Run staging checks. Stop here if they fail.
8. Only after staging passes, fetch the remote production lane: `git fetch origin refs/heads/main`.
9. Require the same unchanged candidate SHA to be a fast-forward of that fetched remote ref, then push the exact candidate SHA to `refs/heads/main` with the server-enforced fast-forward command `git push origin <candidate-sha>:refs/heads/main`.
10. Verify the remote production ref resolves to the candidate SHA and the deployment for `pushinweight-web` reports that same SHA before reporting completion.
11. After step 10 succeeds, perform worktree cleanup as the final filesystem action:
    - From `/Users/fuchitalee/development/pushin-weight-v2`, require `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/enrichment-trans-comm-reliability` to remain registered, clean, unlocked, and at the verified candidate SHA. If any guard fails, retain it and report the reason.
    - Run `git -C /Users/fuchitalee/development/pushin-weight-v2 worktree remove /Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/enrichment-trans-comm-reliability` without `--force`.
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

## Delivery Exceptions

None.

## Goal

Complete literal translations and rich commentary for ordinary and long posts without wasting retries on work never submitted to a provider, while making failures explainable from safe persisted and logged evidence.

---

## Product Contract

### Requirements

- R1. Commentary accepts a complete prompt up to 32,000 **characters**, including instructions and all context. Above-cap input fails safely before a provider call; no silent truncation.
- R2. Commentary failures retain a safe, specific formatter, schema, identity, distinctness, cap, timeout, or provider reason. Store no raw response or sensitive post body in an error field or log.
- R3. Literal translation of a source over 5,000 characters uses deterministic paragraph-bound chunks no longer than 5,000 characters where possible. An oversized single paragraph is split at a safe text boundary without dropping or changing characters. The ordinary short-post route stays intact.
- R4. Each target language reuses successful chunks after a later chunk or target fails, keyed by source fingerprint, detected source language, target, model, and prompt version. Reassembled text is complete and receives the same final translation invariants as the old route. Partial text is never published as a complete post translation.
- R5. A long post cannot consume the shared short-post translation deadline. Maintain bounded model concurrency, request timeouts, and cycle call budget; give long work a dedicated bounded path that can continue in later cycles.
- R6. Distinguish `not_sent_deadline`, `transport_timeout`, and `returned_validation_failed` per target, with chunk index where applicable. A post whose translation received no provider request does not spend a translation attempt. Preserve claim fencing and last-good artifacts.
- R7. Do not alter harvest query shape, classifier semantics, commentary output contract, or the two historical short commentary posts by special case.

### Acceptance examples

- A1. A ~24k-character English post is divided into bounded requests; successful Chinese chunks remain available if a later Japanese request fails. A later cycle sends only missing chunks and publishes all three complete locales after validation.
- A2. With a deadline already exhausted, a short English post makes zero translation calls, has `not_sent_deadline` evidence, and retains its attempt eligibility.
- A3. A commentary prompt between 4,001 and 32,000 characters is sent; a prompt above 32,000 gets a named cap error without a call.
- A4. An invalid tagged commentary response logs/persists a safe parse reason; an otherwise valid response continues through the existing publication checks.

---

## Scope Boundaries

Touch translation orchestration, literal translation, chunk persistence, commentary guard/diagnostics, configuration, and targeted tests. Preserve original text, current published artifacts until a complete replacement exists, classification, X calls, scheduling, and UI. Do not replay or hand-repair historical failures. No provider streaming, new provider, or migration of old partial translation attempts.

---

## Key Technical Decisions

- KTD1 (R1, R2): Raise the current character-counted synthesis prompt guard and configuration bound to 32,000; retain token reservations/pricing separately and do not rename the existing setting in this release. The setting is named `max_input_tokens_per_post` today but checked with `len(prompt)`; tests must pin the real character behavior. User-directed cap increase; rejected 4,000 because it blocks otherwise ordinary commentary.
- KTD2 (R3, R4): Persist validated **per-target chunks** in a separate durable structure keyed by post/source fingerprint/source language/model/prompt version/locale/chunk identity, then assemble and publish through `monitor/post_artifacts.py`. Rejected in-memory-only chunks because the next scheduled cycle cannot reuse them. Invalidate cache on source/language/model/prompt changes; guard writes with the same claim/source fencing as full artifacts.
- KTD3 (R5, R6): Separate long-post work from the short batch's shared deadline and mark a translation attempt only after a real provider call is initiated. Rejected larger single-call timeout because the ~24k-character prompt is near the model's output budget and still starves other posts. Keep the existing max-worker and global model-call caps.
- KTD4 (R2, R6): Use finite safe error codes and bounded structured metadata, not raw exception/response text. The two short commentary cases are diagnostic targets, not acceptance fixtures requiring special repair.

---

## Implementation Units

### U1. Commentary cap and safe failure classification

**Goal:** Allow the agreed 32,000-character prompt and expose why a commentary attempt failed.

**Requirements:** R1, R2, R7; A3, A4.

**Dependencies:** None.

**Files:** `config.yaml`, `x_monitor/config.py`, `x_monitor/synthesis.py`, `monitor/post_synthesis.py`, `monitor/post_artifacts.py`, `tests/test_post_synthesis_lifecycle.py`, `tests/test_u20_translation_synthesis_execute.py`.

**Approach:** Update the cap and its schema bound; preserve prompt construction and output budget. Classify parse, identity, missing-field, duplicate-locale, distinctness, cap, provider and timeout failures at their actual boundaries. Carry a safe code through demand and artifact failure records; add bounded diagnostic details only if needed to distinguish formatter failure without storing response text. Preserve normal retries.

**Test scenarios:** Prompt lengths 4,001, 32,000 and 32,001; each tagged-response failure reason; valid tagged response; output that repeats literal source; transport timeout; assert logs and DB contain only safe codes and not response text. Exercise `process_synthesis_batch` through the fake provider to the demand/artifact.

**Verification:** Targeted tests show provider called below cap, not called above it, and a failed demand carries the right safe reason.

### U2. Durable bounded translation chunks

**Goal:** Make long-post translation incremental and reusable across cycles.

**Requirements:** R3, R4, R7; A1.

**Dependencies:** None.

**Files:** `core/models.py`, `core/migrations/`, `x_monitor/literal_translation.py`, `monitor/post_artifacts.py`, `config/staging_refresh.yaml`, `docs/operations/staging-data-refresh.md`, `tests/test_literal_translation_plaintext.py`, `tests/test_translation_invariants.py`, `tests/test_cycle_plaintext_translation.py`, `tests/staging_refresh/test_policy.py`.

**Approach:** Design deterministic, byte-preserving chunks and a keyed cache with uniqueness at the DB boundary. Translate only missing target chunks, validate each chunk and then the assembled locale using the existing quantity/copy invariants. Prevent cache publication on stale source or claim and preserve last-good full artifacts. Classify partial chunks as excluded runtime state in the staging snapshot policy. Bound chunk count/cost; provide a safe failure for pathological inputs instead of unbounded calls.

**Test scenarios:** Paragraphs straddling 5k boundary; oversized single paragraph; CRLF/newlines/Unicode; duplicate-looking paragraphs; stale source/model/prompt invalidation; mid-locale timeout followed by next-cycle reuse; concurrent claims; migration applies on an empty database; no partial post artifact on failure.

**Verification:** Fake-client integration shows every request body bounded and a resumed 24k post sends only missing chunks; database uniqueness/fencing holds under retry.

### U3. Fair scheduling and truthful attempt accounting

**Goal:** Stop long posts from starving short posts and stop no-call claims from exhausting retries.

**Requirements:** R5, R6; A1, A2.

**Dependencies:** U2.

**Files:** `monitor/cycle.py`, `monitor/post_enrichment.py`, `x_monitor/literal_translation.py`, `x_monitor/provider_telemetry.py`, `tests/test_post_enrichment_queue.py`, `tests/test_cycle_regression_net.py`, `tests/test_enrichment_attempt_deadline.py`, `tests/test_cycle_plaintext_translation.py`.

**Approach:** Preserve one shared cycle and claim mechanism. Process short posts under their existing bounded batch; schedule long work with its own bounded deadline/claim cap and existing global LLM call accounting. Return per-post/locale provider-call counts and safe outcomes to the production caller. Increment translation attempts only for posts with at least one sent translation/detection call; do not decrement an already exhausted historical count. Persist the latest reason at the stage/artifact boundary, including locale/chunk in bounded diagnostic metadata if schema allows. Maintain claim fencing and release semantics.

**Test scenarios:** A long timeout beside short posts; zero-call expired deadline; real timeout; returned-invalid response; successful retry from cached chunks; global call cap exhausted; two concurrent harvest claims. Assert exact calls and attempt counts through `CycleRunner`, not just a helper.

**Verification:** End-to-end production-call-chain tests prove a zero-call post remains retryable and a short post still reaches the provider when long work stalls.

### U4. Release and operational proof

**Goal:** Ship the same checked SHA through staging to production, then verify real enrichment health.

**Requirements:** R1-R7.

**Dependencies:** U1-U3.

**Files:** `docs/plans/2026-09-25-063656-fix-enrichment-trans-comm-reliability-plan.md`, targeted tests above; no production data repair.

**Approach:** Follow the generated Ollija guide. Run focused and broader regression tests, migration check, and `pytest tests/ollija`; verify clean worktree and exact SHA. Stage and verify the staging service and representative synthetic/fake-client behavior. The deployment runbook also requires one bounded, paid staging harvest attempt before production promotion; stop at staging until the owner explicitly authorizes that attempt or directs a recorded exception. If authorized and the runbook acceptance passes, promote the unchanged SHA to production. Use the enrichment-relevant latest-N health-check route: retain the initial cohort, wait its 30-minute grace window, inspect the same IDs. Confirm a subsequent real harvest cycle in logs and DB, including post insertion and translation/commentary states. Do not pause cron.

**Test scenarios:** Staging deployment failure or SHA mismatch blocks production; prod SHA mismatch blocks completion; latest-N fresh pending is inconclusive rather than failed.

**Verification:** Automated checks pass with zero unexpected skips, staging and production report the candidate SHA, and post-deploy cycle plus DB evidence are recorded.

---

## Risks and checks

- Chunking may multiply provider calls. Keep each call bounded, cache successes, enforce the existing cycle-wide call cap and a long-post per-cycle cap, and report call-count change.
- A longer commentary prompt may exceed provider context or cost assumptions even though the app cap allows it. Observe errors and token usage; fail safely with a specific code rather than truncate.
- DB migration and cache uniqueness can race with two workers. Use database constraints and fenced writes; test both the fresh migration and concurrent retry case.
- The staging harvest acceptance gate needs paid provider calls that were excluded from the original plan scope. Production promotion waits for the owner's explicit budget decision or exception; staging deployment and provider-free checks may proceed.
- The root checkout has unrelated `monitor/cycle.py` edits on a different branch. Do not import, overwrite, or commit them. This worktree is isolated.

## Definition of Done

All U1-U4 verification holds; at least one production-call-chain regression covers starvation/attempt accounting and one covers commentary publication; no full artifact is published from partial chunks; all planned failure codes are visible without raw response leakage; staging precedes exact-SHA production promotion; a post-deploy harvest tick and DB cohort are inspected. A failed or inconclusive gate stops promotion/completion and retains the worktree.
