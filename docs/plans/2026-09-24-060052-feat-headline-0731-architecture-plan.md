---
title: "feat: reshape headline generation for DeepSeek V4 Flash 0731"
type: feat
date: 2026-09-23
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ce-plan-bootstrap
execution: code
depth: deep
deepened: 2026-09-23
updated: 2026-09-25
ollija:
  change_id: feat-headline-0731-architecture-2026-09-24-060052
  branch: feat/headline-0731-architecture
  workflow: ce-work
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
- Active worktree: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/headline-0731-architecture`
- Plan: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/headline-0731-architecture/docs/plans/2026-09-24-060052-feat-headline-0731-architecture-plan.md`
- Change: `feat-headline-0731-architecture-2026-09-24-060052`
- Branch: `feat/headline-0731-architecture`
- Staging branch and blueprint: `staging`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/headline-0731-architecture/render-staging.yaml`
- Production branch and blueprint: `main`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/headline-0731-architecture/render.yaml`
- Staging URL: `https://pushinweight-staging-web.onrender.com`
- Production URL: `https://pushinweight-web.onrender.com`

### Placement

This worktree is inside the Ollija release worktree area. Reuse it for the whole change. Do not create a second worktree or plan for this branch.

### Delivery scope

- Workflow: `ce-work`
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
    - From `/Users/fuchitalee/development/pushin-weight-v2`, require `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/headline-0731-architecture` to remain registered, clean, unlocked, and at the verified candidate SHA. If any guard fails, retain it and report the reason.
    - Run `git -C /Users/fuchitalee/development/pushin-weight-v2 worktree remove /Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/headline-0731-architecture` without `--force`.
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

- **2026-09-24, owner-requested document publication:** The owner asked to push
  this plan to `main` for reading in VS Code. Publish only this plan and its
  directly supporting research/review documents from a fresh `origin/main`
  base, using an ordinary fast-forward push and `[skip render]` in the commit
  message. Do not merge the implementation branch or activate its candidate.
  A separate, temporary documentation-publication worktree may assemble that
  commit; the canonical implementation worktree and this plan remain the
  execution authority. Suppress only automatic creation of a new plan during
  that worktree's initial checkout; run this canonical plan's Ollija check
  before publication and retain normal commit hooks. Staging/model
  qualification and production-deployment verification are not prerequisites
  for this document-only publication. They remain mandatory for application
  delivery; the existing no-go and root checkout's unrelated changes remain
  intact. This exception does not authorize application or infrastructure
  changes or removal of the canonical implementation worktree.

- **2026-09-25, headline-only staging identity:** The owner selected this
  headline change for production. The shared `staging` branch is currently 43
  commits ahead of `main` with a separate rare-type feature; merging it into
  the headline candidate would carry unrelated application changes to
  production. Preserve the owner's headline-only scope by leaving that branch
  untouched. After the final fresh candidate passes SC2/SC3, commit and push this feature branch,
  disable automatic deploys for the staging web and headline worker, deploy
  the *exact candidate SHA* manually to those services, verify their reported
  SHA, and run the bounded staging checks. Configure the isolated staging
  headline worker to the candidate's three-process command and secret before
  its canary, then restore its prior configuration after testing. Render
  [supports deploying a specific commit](https://render.com/docs/deploys#deploying-a-specific-commit)
  without changing the linked branch. This exception replaces only the
  guide's staging-branch fast-forward step; the exact-SHA checks, production
  fast-forward to `main`, and guarded cleanup still apply. If the manual
  exact-SHA route cannot be verified, stop before production.

- **2026-09-25, owner-directed V56 freeze:** After nineteen prompt/code
  cycles the owner stopped zero-critical SC2 retuning. V56 is the frozen
  candidate. A twelve-case lead-sentence review of the saved V56
  regressions passed. Commit and push this feature branch with that freeze.
  Do not add another critic prompt version. Incomplete Cycle 19 fresh
  generation stays unused. Staging and production remain fail-closed and
  still follow the headline-only exact-SHA exception above; this exception
  authorizes the feature-branch commit/push before those deploys.

# Reshape headline generation for DeepSeek V4 Flash 0731

## Plain-English Summary

This plan makes the cheaper DeepSeek V4 Flash 0731 model viable for Pushin
Weight's trilingual headlines by changing how work is packaged and scheduled.
The current five-brand requests ask 0731 to produce too much structured text at
once and then execute every request serially. The new route keeps one global
ranking call, uses two-brand editor and critic packets, and lets three durable
provider-call tasks run at the same time.

The request format will be tuned specifically for 0731. That
includes stage-specific prompts, JSON mode or schema, output ceilings, sampler
settings, and a critic packet that pairs each draft directly with its own brand
evidence. Reasoning stays disabled. Existing last-good headlines, critic
routing, one-call entitlements, and atomic publication remain intact.

0731 is the committed headline model. There is no competing-model benchmark,
model-selection gate, or alternative-model rollback path. If a configuration
fails, diagnose the cause, improve its packets, prompts, or execution shape,
and test 0731 again. Completion means meeting the product's own factual,
availability, cost, and freshness requirements, then delivering through staging
to production. The owner explicitly selected this direction on 2026-09-24.

The first qualification failed on factual support. Before retesting, this plan
now incorporates the owner's finance-context handoff: distinguish a temporary
spike from sustained activity, recent cooling from overall growth, and a
preceding-period comparison from activity that is unusual for this time. Code
calculates these measurements; the existing writer explains them using posts.
This describes collected discussion, not market value or future performance.

The packet will also become smaller. Exact duplicate post text and internal
selection scores alone account for 26% of captured editor messages and 23% of
critic messages. Remove that repetition, meaningless phrase signals, and
prohibited comparisons before adding historical context. Keep original source
wording, citations, brand identity, time intervals, and coverage limitations.
These are measured byte reductions on saved requests, not yet measured token
or latency savings. The revised design requires fresh qualification; the first
failed run remains evidence and does not become a passing test retroactively.

---

## Goal Capsule

- **Objective:** Make direct DeepInfra 0731 deliver useful, factually supported
  trilingual trend headlines within the product's cost and freshness budgets.
- **Means:** Adapt the provider request contract to 0731, reduce editor and
  critic packets to two brands, and execute the existing durable stage tasks at
  bounded concurrency three, with compact permitted facts and finance-informed
  context (KTD1–KTD11).
- **Authority:** The Product Contract governs observable behavior. The Planning
  Contract governs implementation. The generated Ollija Delivery Guide governs
  delivery authority and permits production only after the qualification and
  staging gates. The present amendment is planning work, not activation.
- **Execution profile:** Execute U7 → U8 → U9, tune 0731 in U4, freeze the
  resulting configuration, then validate it on new unseen data in U5. A failure
  returns to the responsible implementation unit and another finite tuning
  cycle. U6 follows readiness; existing U1–U3 are retained.
- **Deployment conditions:** Do not activate a configuration that misses a
  quality, integrity, completeness, cost, latency, memory, provider-attestation,
  or queue-drain requirement. Keep improving 0731 instead of ending the project
  or reopening model selection. Preserve zero runtime retries, the current
  reasoning-disabled decision, and atomic publication.
- **Landing ownership:** The owner selected production delivery. The release
  still requires qualification, staging, and exact-SHA production verification.

---

## Product Contract

### Summary

Reshape the existing rank-editor-critic headline pipeline around 0731's
strengths and throughput limits while keeping the public headline product and
its safety guarantees intact. Add supported historical and phase context to
the same narrative fields; do not expand the public request/filter contract.

### Problem Frame

Direct DeepInfra testing established that 0731 can complete the headline call
graph, but five-brand serial requests and the existing information contract
need improvement. Recurring errors include unsupported causal language,
claims broader than the sample, reversed volume direction, cross-brand
conflation, translated proper names, and prohibited historical comparisons.
Those are defects to fix in the 0731 route, not reasons to select another model.

The limitation was not hidden reasoning. The baseline ran with reasoning
disabled, while a low-reasoning correction probe exhausted the 11,000-token
ceiling on all three calls. A production-sized priority-tier critic probe
reduced latency from 290.4 seconds to 103.4 seconds. The evidence points to
smaller brand-local packets, explicit checks, bounded concurrency, and
provider-specific request tuning.

### Requirements

- R1. The public result remains one complete English, Simplified Chinese, and
  Japanese narrative for every eligible tracked brand, with the existing
  headline, secondary, proposition, event, confidence, and narrative-kind
  contract.
- R2. One global rank call continues to order every eligible brand. An invalid
  rank response falls back to the complete deterministic order and cannot drop
  a brand.
- R3. Editor and critic work uses deterministic packets of at most two brands;
  an irreducibly oversized pair splits to one-brand packets without dropping
  evidence or changing rank order.
- R4. The 0731 route uses direct DeepInfra, priority service, zero provider or
  SDK retries, and reasoning disabled. The application rejects a response whose
  model or service-tier receipt does not match the configured route.
- R5. Rank, editor, and critic each receive a request shape optimized for 0731.
  The selected prompt, structured-output mode, sampler settings, packet
  projection, and output ceiling are versioned independently and locked before
  qualification.
- R6. A valid editor result reaches the critic as structured brand-local review
  bundles pairing each draft with its own dossier. Raw editor text is included
  only for a mechanically invalid draft the critic may reconstruct.
- R7. After rank completes, up to three existing provider-call tasks may execute
  concurrently. Each task still owns exactly one durable call entitlement and
  at most one outbound transport.
- R8. Risk-based critic bypass remains available only for mechanically valid,
  low-risk editor output under the existing policy. Causal, event-led,
  fact-alignment, incomplete-coverage, invalid, and audit-sampled output still
  reaches the critic.
- R9. Every manifest brand reaches a terminal state before the visible run
  advances atomically. Failed work keeps the previous last-good narrative.
- R10. Budget reservation covers the maximum graph implied by the configured
  brand cap and two-brand batching. Provider receipts preserve model, service
  tier, token counts, cost, request ID, and latency for audit.
- R11. No headline browser request, harvest request count, classification,
  translation, or commentary changes in this work. Headline-only deterministic
  calculations and provider projections may change under R14–R19; source
  classifications and historical database rows are not rewritten.
- R12. Validate a locked 0731 configuration against independent product
  criteria on fresh data. Failure produces a reproducible diagnosis and the
  next bounded correction cycle; it never selects a different headline model.
- R13. Recovery uses the last qualified 0731 configuration, when one exists,
  or disables new generation while serving last-good persisted headlines.
  Never switch model/provider or resend an ambiguous call as recovery. Existing
  stored headlines retain their original provenance; serving them is not a
  new inference through a retired route.
- R14. Every provider stage receives an explicit field allowlist. Preserve the
  rich immutable snapshot privately; omit selection internals and exact text
  duplicates from the model request. Do not trade away evidence cardinality,
  provenance, meaningful minority views, or completeness warnings for size.
  The v38 final-writer one-source trial is a separate factual-ownership
  control, not a token-saving trim: keep all selected evidence in the canonical
  packet, log the lead and omitted count, and require independent review of
  lost synthesis and contradiction context before accepting it.
- R15. Suppressed aggregate comparisons are absent from model-visible facts,
  phrase statistics, summaries, and generated examples, not merely accompanied
  by a warning. This does not redact comparisons an author actually wrote;
  source claims retain attribution and cannot substitute for corpus metrics.
  Each permitted quantitative fact specifies its brand, interval, unit,
  denominator, coverage, and comparison basis. Within-window endpoint change,
  prior-period change, and historical-normalized activity are distinct.
- R16. Historical expectations use comparable, completed intervals within the
  same collection regime and scope. Expose the baseline policy/version, sample
  size, interval, timezone, coverage, and observed/expected ratio. Insufficient
  history produces unavailable context; it never licenses "normal" or "usual."
- R17. Describe overall and recent direction, peak/cooling, persistence, and
  participation breadth using bounded deterministic facts. Incomplete buckets,
  low bases, backfills, and collection changes cannot masquerade as trends.
- R18. Source support must concern the attributed brand/product. A citation
  belonging to a brand dossier is not proof that every entity or number in that
  post concerns that brand. Quoted allegations remain attributed allegations;
  an individual's stated reason cannot establish the cause of an aggregate
  movement or population-wide adoption.
- R19. Retain the rank/editor/critic graph with no new LLM pass. Measure packet
  bytes, provider-reported tokens, SQL/build time, total wall time, and billed
  cost. The finance additions must fit the existing finite resource envelope.

### Key Decisions

- KD1. **0731 is the committed headline model.** (user-directed 2026-09-24:
  "0731 no matter what. will have to improve it if it isn't good.") Optimize
  its request shape and pipeline; no competing model is a benchmark or fallback.
  Governs R4–R6, R12–R13.
- KD2. **Product readiness replaces model parity.** The owner's decision retires
  relative scores and percentage-of-incumbent cost gates. Factual support,
  usefulness, availability, resource limits, and freshness remain testable
  requirements. A failure changes the implementation, not the model choice.
  Governs R12.
- KD3. **Reasoning remains disabled.** (session-settled: user-approved — chosen
  over low reasoning: every low-reasoning critic probe exhausted the response
  budget.) Governs R4–R5.
- KD4. **The normal packet contains two brands.** (session-settled:
  user-approved — chosen over retaining five brands or making every request
  single-brand: two brands reduce model burden without repeating all fixed
  prompt context forty times.) Governs R3, R5–R7.
- KD5. **Integrate finance context and packet cleanup before the next tuning
  campaign.** (user-directed on 2026-09-24.) Preserve the no-go and qualify the
  revised design on fresh data. Jev and semantic reason histories are deferred.
- KD6. **Three rounds are a tuning-cycle boundary, not an abandonment rule.**
  Continue with documented corrections and another budgeted cycle when needed;
  do not stop merely because round three failed or ask to reopen model choice.

### Success Criteria

- SC1. The locked 0731 configuration completes every planned request and gives every
  eligible brand a terminal outcome, with zero unsupported false approvals and
  zero missing locale fields.
- SC2. Three independent reviewers each assess eight disjoint 0731 narratives
  against the frozen source packet, without seeing configuration identity.
  Review factual support, proportionality, why-first relevance, secondary
  usefulness, and translation equivalence. The initial standalone quality
  target is a mean of at least 4/5 on each dimension and zero critical factual
  failures in the **final reader-visible result**. Material errors change
  identity, amount, direction, negation, attribution, event reality or decision-
  relevant meaning. Awkward wording, harmless omissions and mild qualitative
  scope overstatement lower the relevant score; they do not independently
  block release. A materially misleading scope claim still blocks. Report all
  scores and reasons. A hold is acceptable only when the
  source packet cannot support a substantive narrative; withholding supported
  narratives cannot manufacture a zero-error result. These absolute targets
  replace the former comparative gate and must be locked before output review.
- SC3. The final validation run has zero unresolved mechanical-invalid final
  results. An invalid editor draft recovered by its already-planned, valid
  critic is a successful pipeline repair. Report raw, normalized, critic-
  recovered and unresolved counts separately; code normalization cannot supply
  model-written content. Do not add repair calls or retry entitlements.
- SC4. One-day completion p95 is at most 12 minutes, seven-day completion p95 is
  at most 15 minutes, and arrival/drain utilization stays below 0.75 at
  concurrency three.
- SC5. Actual provider-billed generation cost stays within the existing $0.30
  maximum per bounded headline run and its token/call caps. Record observed
  per-window cost and project monthly headline spending from measured run
  frequency, showing its contribution to the owner's $150/month total LLM
  budget. Review-model experiment spending is reported separately. No cost
  ratio against another model is required.
- SC6. Three concurrent worker processes remain below the Render memory ceiling
  with at least 25% headroom, and simultaneous due windows do not build an
  unbounded queue.
- SC7. Duplicate delivery, worker loss, timeout, rate limit, malformed JSON,
  model mismatch, tier mismatch, and one failed brand batch preserve the
  one-transport entitlement and last-good behavior.
- SC8. The production snapshot → projected request → draft/critic → served
  narrative path preserves permitted facts and their scope. Suppressed prior
  comparisons cannot enter any stage, and no historical norm is emitted when
  baseline eligibility is unavailable.
- SC9. Publish before/after per-stage packet and token measurements, including
  the new context. The diagnostic engineering target is at least 20% fewer
  aggregate message bytes than the saved candidate on the same source workload;
  this is not a promised token reduction or a substitute for SC1–SC8. Record a
  target miss and its cause; never remove required evidence to meet it.

### Scope Boundaries

- The visible layout, supported locales, complete rank manifest, critic bypass
  policy, and publication model remain unchanged. Headline facts, phrase
  selection, source-relevance handling, and provider projection are revised;
  numerical inputs retain explicit provenance and versioned meaning.
- No database migration is planned. Existing JSON request and response payloads
  carry versioned request profiles and provider receipts.
- No automatic per-call fallback, speculative dual-model execution, additional
  critic pass, reasoning mode, or browser-triggered generation is added.

#### Deferred to Follow-Up Work

- Test standard-tier ranking as a separate cost optimization after the all-
  priority route qualifies.
- Consider prompt-cache retention only after production prefix reuse is
  measured.
- Revisit one-brand critics if cross-brand conflation persists after a bounded
  tuning cycle; re-budget and validate any changed graph before adopting it.
- Jev; semantic reason-history extraction/taxonomy; chart-image interpretation;
  financial forecasting; arbitrary date/country/post-language headline filters;
  and new statistical libraries such as `ruptures`.
- Full matched historical norms for 30/365-day windows beyond the initial
  bounded baseline policy. Those windows keep supported within-window context
  and explicitly unavailable historic norms, rather than invented comparisons.

---

## Planning Contract

### Draft prompt exhibit

Read [the verbatim draft rank, writer, and critic prompts](../research/2026-09-24-175847-headline-finance-draft-prompts-exhibit.md)
for the proposed complete system messages, user-message templates, and a
fictional compact packet demonstrating historical elevation alongside cooling.
This is an untested design exhibit, not the live prompt implementation or a
qualified profile. U7/U8 must supply its facts and U4 must tune and lock it
before fresh U5 qualification.

### Key Technical Decisions

- KTD1. Extend the strict direct DeepInfra client with named headline profiles
  for rank, editor, and critic. Profiles own allowed sampler fields,
  `reasoning_effort=none`, priority tier, structured-output mode, and exact model
  identity. Arbitrary caller options remain rejected. This applies KD1 and KD3.
- KTD2. Keep the all-brand rank call, then use a configurable two-brand maximum
  in the deterministic split function. The recursive packet-budget split remains
  the one-brand fallback. This applies KD4.
- KTD3. Replace the critic's escaped `editor_response_raw` string on valid
  results with structured per-brand review bundles. Each bundle contains one
  dossier, its matching draft, and local parse diagnostics; invalid output uses
  bounded raw text plus the closed packet.
- KTD4. Use Celery's existing one-call-per-task graph at worker concurrency
  three. Do not add an in-process thread pool: durable claims, fences, unique
  `(run, stage, batch_key)` rows, and the reconciler already provide safe fan-
  out and recovery across processes.
- KTD5. Tune request shape in cycles of up to three diagnostic rounds, then
  lock one immutable stage profile before touching a fresh holdout. Candidate dimensions are
  concise prompt wording, JSON schema versus JSON-object mode, temperature,
  top-p, fixed seed, brand-local projection, and output ceiling. Reasoning,
  retries, arbitrary evidence removal, and extra model calls are not tuning
  dimensions. R14 permits exact duplicate removal and stage-specific
  projection; R18 permits auditable exclusion/replacement of demonstrably
  unrelated evidence without silently reducing the evidence target. The first
  reviewed holdout is now diagnostic material, never an unseen qualification.
  A failed cycle or validation returns to implementation and another finite
  cycle. Track cumulative experimental spending and preserve a bounded manifest
  for each cycle; no unbounded API loop or automatic budget increase is implied.
- KTD6. Reserve for `1 + 2 × ceil(N / 2)` calls. For 40 brands this is 41
  calls. Start with a 300-second timeout, the existing 900-second lease,
  concurrency three, a 1.6M input-token cap, 350k output-token cap, and $0.30
  priority-tier cap. Price reservations use the captured direct-DeepInfra
  priority rates of $0.09 per million input tokens and $0.27 per million output
  tokens; qualification may lower these caps but may not raise them without a
  new finite preflight and refreshed price evidence.
- KTD7. Run 0731 alone as the headline generator. Compare its own configuration
  revisions on diagnostics when useful, and qualify the locked revision against
  SC1–SC9 on fresh data. No competing-model calls, paired model rankings, or
  baseline billing run are required. Independent quality reviewers judge source
  support; they are not alternative generator candidates. This applies KD1–KD2.
- KTD8. Activate by committed 0731 configuration after readiness validation.
  Recovery is a previous qualified 0731 profile or disabled generation plus
  last-good serving. Remove alternate headline model fallback/rollback controls
  during U6; do not delete shared credentials or change other enrichment roles.
- KTD9. Use separate rank/editor/final-writer projections from a versioned
  canonical snapshot. Rank gets concise per-brand notability facts and two
  source previews. Editor gets all selected source evidence and permitted
  context. The v38 diagnostic selects one brand-identifying, substantive lead
  post for the final writer. The complete selected set remains in the local
  audit envelope, while the provider sees only that lead post; when none
  qualifies it sees one example solely to explain a hold. This deliberate
  source-isolation tradeoff prevents transferring claims among visible posts,
  but loses cross-post contradiction checks and synthesis. Qualify its
  usefulness and factual support against the unchanged SC2 gate before
  adopting it. Editor citations are salience hints only after mechanical
  brand-identity and subject-focus checks; draft prose never becomes evidence.
- KTD10. New finance facts are calculated in the existing read-only repeatable-
  read snapshot transaction with finite database work. Adopt the bounded
  initial policy below, calibrate thresholds on diagnostics, and lock the
  policy and projector before fresh qualification.
- KTD11. Reject mechanically invalid fact IDs, units, intervals, and structured
  numerical bindings before publication. The critic separately checks whether
  prose actually follows from the source. Do not treat an ID-ownership check
  or a regex over prose as semantic proof.

### High-Level Technical Design

```mermaid
flowchart LR
    H[Committed harvest envelope] --> F[Immutable facts and eligible historical context]
    F --> S[Compact permitted facts and global rank]
    S --> B[Deterministic two-brand batches]
    B --> Q[(PostgreSQL call ledger)]
    Q --> W1[Celery worker 1]
    Q --> W2[Celery worker 2]
    Q --> W3[Celery worker 3]
    W1 --> D[DeepInfra 0731 priority]
    W2 --> D
    W3 --> D
    D --> Q
    Q --> T[All brands terminal]
    T --> V[Atomic visible-run pointer]
```

```mermaid
sequenceDiagram
    participant R as Reconciler
    participant DB as PostgreSQL ledger
    participant E as Editor task
    participant C as Critic task
    participant DI as DeepInfra 0731
    R->>DB: reserve and claim editors after rank
    par up to three batches
        E->>DI: two-brand editor request
        DI-->>E: trilingual draft and receipt
    end
    E->>DB: complete call and reconcile
    alt valid and low risk
        R->>DB: publish editor result as bypassed
    else critic required
        C->>DI: brand-local evidence and structured draft
        DI-->>C: approve, repair, or hold and receipt
        C->>DB: persist terminal outcomes
    end
    R->>DB: advance pointer only when manifest is terminal
```

```mermaid
flowchart TD
    A[0731 selected] --> F[U7 compact facts and evidence]
    F --> C1[U8 historical and phase context]
    C1 --> R[U9 regression net]
    R --> P[U4 bounded diagnostic tuning cycle]
    P --> L[Lock profiles and prompt versions]
    L --> Q[Untouched full qualification]
    Q --> G{All gates pass?}
    G -- No --> E[Record failures and correct the responsible unit]
    E --> P
    G -- Yes --> C[Commit ready 0731 route and recovery config]
    C --> D{Recorded delivery authority and gates satisfied?}
    D -- No --> H[Stop with deployable candidate]
    D -- Yes --> S[Follow exact-SHA Ollija guide]
```

### Request-Shape Optimization Matrix

| Dimension | Rank | Editor | Critic |
| --- | --- | --- | --- |
| Packet | Salient permitted facts and two source previews per brand | At most two compact dossiers with full selected evidence | Per-brand compact dossier/draft bundles |
| Output | Complete ordered manifest | Trilingual narrative schema | Approve/repair/hold schema |
| Structured mode | Schema or JSON object | Schema or JSON object | Schema or JSON object |
| Emphasis | Relative notability | Why-first copy and citations | Direction, causality, scope, ownership, names, locale parity |
| Reasoning | Disabled | Disabled | Disabled |
| Runtime retries | Zero | Zero | Zero |
| Initial ceiling | 2,400 | 8,000 | 8,000 |

The initial ceilings above are starting defaults, not the previously tested
profile: the first qualification used a 7,000-token rank ceiling. Preserve
exact manifests and re-lock actual ceilings during U4.

### Packet redesign: remove noise before adding context

The saved first qualification contains 50 requests: two ranks, 24 editors,
and 24 critics for the 1/7-day snapshots. The byte audit in
`docs/research/2026-09-24-170254-headline-packet-size-audit.md` examines the
actual message strings in `provider_request`, not the larger retained artifact.

| Stage | Messages | Original aggregate UTF-8 bytes | After duplicate/internal-score removal | Reduction |
| --- | ---: | ---: | ---: | ---: |
| Rank | 2 | 501,126 | 501,126 | 0% |
| Editor | 24 | 1,450,418 | 1,072,295 | 26.1% |
| Critic | 24 | 1,613,273 | 1,235,150 | 23.4% |
| Total | 50 | 3,564,817 | 2,808,571 | 21.2% |

This offline accounting removes only `original_text` when identical to
`excerpt`, `text_en`/`text_zh_cn` when identical to that same excerpt, and
`_ranks`/`_role_eligible`. All 301 selected evidence occurrences remain.
Aliases in the new schema will retain the language/translation relationships.
No prompt was run, and no token or latency reduction is established. The
original receipts total 1,002,636 input tokens across these 50 calls.

Implement these changes in order:

1. **Allowed fields instead of an exclusion list.** `_provider_dossier()`
   currently copies fields unless explicitly excluded, so internal evidence
   fields escape into requests. Keep those in the private snapshot only.
   Define and test explicit nested schemas for every stage; unknown private
   fields must not silently enlarge a request.
2. **One original excerpt, with translation only where useful.** Preserve source
   language, source ID, timestamp, brand-specific author role, and unaltered
   wording including attribution/negation. Exact duplicates use references.
   Retain a distinct existing English translation when needed; test removing a
   redundant second translated rendering separately on multilingual diagnostics.
   Trilingual output does not require three copies of the same input. Do not
   replace source quotations with model-written summaries or cut context just
   to reach a byte target. Retain meaningful truncation/translation status.
3. **One representation of each fact.** Replace redundant `current_value`,
   `source_value`, rendered EN/ZH strings, repeated coverage objects, and family
   summaries with typed facts and shared scope/coverage references where their
   meanings coincide. Preserve genuinely distinct values. Count facts must not
   say `direction=increase` merely because their absolute value is positive.
   Carry counts, units, denominators, intervals, and exact allowed citations;
   format display text in application code where that contract already exists.
4. **Remove unusable comparisons at the boundary.** When comparison is
   suppressed, remove `baseline_value`, `prior_post_count`, prior phrase
   prevalence, change facts, and summary `largest_change` derived from that
   comparison. Keep a concise suppression reason and current coverage. Apply
   this to rank, editor, critic, bypass, and invalid-editor reconstruction.
  The legacy `_provider_family_facts(..., comparison_allowed=...)` filter is
   not proof that the current compact path is filtered. This restriction
   concerns our aggregate comparisons, not an author's quoted product test.
5. **Useful phrases only.** Current top phrases include `https co`, `of the`,
   and `in the`. Strip URL artifacts before phrase extraction and exclude
   language-appropriate stopword-only phrases; rank remaining signals within
   the existing cap of eight, allowing fewer. Preserve model names, versions,
   non-English terms, negative/contrary views, and genuine promotional topics.
   Cross-brand repetition can itself be evidence of a campaign, not automatic
   deletion. Store each representative excerpt once and reference its ID.
   Keep exact source-deduplicated prevalence and resource-limit status; phrase
   frequency still cannot establish a semantic cause or stated-reason trend.
6. **Smaller rank input.** It currently receives full fact/family/phrase blocks
   despite being a ranking task (201–288 KiB per captured rank message). Send
   only salient permitted measurements, identity, eligibility/coverage, and
   the existing two source previews; retain all manifest brands and citations
   needed by the rank schema. Editor and critic retain the detailed evidence.

Critic duplicate removal is partly implemented already: valid critic requests
send structured review bundles without also sending `analysis_packet` or raw
editor JSON. Do not count that existing optimization as a new saving. The
critic still needs its own closed source context; no hidden conversational
memory, narrower contrary-evidence set, or additional LLM call is assumed.

### Finance-informed fact contract

Reuse `monitor/trend_narrative_facts.py` and the snapshot transaction in
`monitor/trend_narrative_candidates.py`; expose new facts through all provider
projections, not only private aggregates. The durable research handoff is
`docs/research/2026-09-24-153052-finance-informed-headline-context.md`.

- **Initial historical policy:** for 1/7-day windows, consider at most eight
  preceding weekly offsets, aligned in UTC with the same start weekday/hour
  and duration as the completed observed interval. Require at least four
  eligible matched intervals and the existing coverage floor, plus no known
  backlog overlap or collection-regime mismatch. Earliest stored-post time
  alone cannot prove complete comparable collection. Unsupported coverage
  becomes unavailable; do not add a new collection system to manufacture it.
  Calculate mean matched post rate and observed/expected ratio, preserving
  sample size, start/end, policy version, timezone, and eligibility reasons.
  Expected zero means unavailable ratio, not infinity. These are initial
  diagnostic defaults; lock any justified changes before qualification.
- **Temporal scope:** prior-period comparison, first-to-last completed bucket
  change, matched historical expectation, and recent change have distinct fact
  types and explicit intervals. Use rates for unequal durations. Exclude an
  unfinished final bucket rather than describing its low count as cooling.
  For 30/365-day windows, keep the shape facts but mark matched historical
  norms unavailable under this initial policy.
- **Shape:** expose overall/recent direction, peak time/rate, time since peak,
  drop from peak, and remaining elevation above a valid baseline. Replace
  ambiguous `total_change_pct` with an interval-specific fact. Add directional
  efficiency `abs(last-first)/sum(abs(adjacent changes))` with explicit
  flat/zero handling; it is not magnitude, significance, or proof of noise.
  Normalized slope/fit is a diagnostic candidate, not another mandatory
  redundant metric in every provider packet.
- **Phases:** at most three supported, ordered phase records with completed
  interval bounds and supporting fact IDs: buildup, spike, sustained elevated
  activity, cooling, return to usual, or repeated bursts. Calibrate duration,
  low-base, and magnitude thresholds using diagnostic fixtures and existing
  episode thresholds. Historical-elevation phrases require a valid norm;
  otherwise use literal peak/cooling descriptions. Mark an ongoing phase
  provisional and never use observations after `as_of`. Do not add `ruptures`
  or a new public taxonomy for this first implementation.
- **Breadth and content:** calculate distinct observed authors and deduplicated
  sources over the same interval. First-party posts and repeated public posts
  are not independent evidence of adoption. Keep representative source text
  and contrary examples alongside shape facts; headlines still lead with the
  topic people discuss. Explicit reasons support that speaker's position,
  not an explanation for all activity. No new sentiment/intent extraction or
  additional model pass is introduced.
- **Bounds and provenance:** fetch historical aggregates in bounded queries,
  never send raw historical post/bucket arrays to the model, and retain the
  existing statement/row/time limits. If history exceeds resource or coverage
  limits, publish supported current context with historical status unavailable.
  Snapshot, comparison policy, semantic fact schema, prompt, and projection
  versions participate in fingerprints/demand identity so stale old packets
  cannot satisfy a redesigned request. Already persisted runs stay immutable.

### System-Wide Impact

- **Provider:** Headlines use the existing direct DeepInfra 0731 transport.
  Retire alternative headline model selection/fallback controls during U6;
  other enrichment routes and their credentials do not move.
- **Queue:** The isolated headline worker changes from one to three processes
  with prefetch one. Harvest and every non-headline queue remain untouched.
- **Persistence:** Existing call identity and state remain authoritative. JSON
  payloads gain fact-policy/projection versions as well as request-profile and
  provider-receipt provenance. Original snapshots and historical runs remain
  readable without rewriting their fact meaning.
- **Serving:** The browser still reads the persisted visible run. No payload or
  UI schema changes.
- **Operations:** Status reports configured versus observed route, batch size,
  concurrency, graph ceiling, latency, cost, and budget suspension.

### Risks & Dependencies

- Priority performance can vary. Qualify with actual p95 and tier receipts.
- Three prefork workers may exceed Render Starter memory. SC6 is an activation
  gate, not a monitoring suggestion. The staging load check must include total
  resident memory and database connections across the parent and child
  processes; if it fails, do not silently substitute a thread pool or lower the
  concurrency after qualification.
- Structured output can improve syntax while harming content. Tune both schema
  and JSON-object forms, then pin one without runtime retries.
- Concurrent completions can reconcile simultaneously. Database uniqueness and
  locks must be proven under concurrency.
- Prompt tuning can overfit known errors. Keep diagnostic and holdout IDs
  disjoint and freeze profiles before qualification.
- Reducing bytes can remove nuance without improving latency. Preserve exact
  source meaning and measure provider tokens and total completion time; input
  cleanup does not eliminate output-generation or queue time.
- Historical collection is not necessarily stable. Suppress unsupported norms
  and broad participation claims rather than interpreting collection changes
  as audience behavior. Versioned defaults are hypotheses until calibrated.
- The active checkout contains unrelated work. Implementation must use an
  isolated canonical worktree or an owner-directed Delivery Exception.

### Alternatives Considered

- **Keep five-brand serial requests:** already failed quality and latency.
- **Use one brand for every call:** simplest packets, but doubles fixed prompt
  overhead; retain it as the oversize fallback.
- **Use an in-process thread pool:** weakens the one-task/one-entitlement failure
  boundary and complicates cancellation.
- **Enable reasoning:** exhausted the response ceiling three times.
- **Switch headline models after a failed test:** rejected by the owner. Fix
  the 0731 route; recover operationally with a qualified 0731 profile or
  disabled generation and last-good serving.

### Sources & Research

- `docs/research/2026-09-23-105318-headline-0731-model-evaluation.md` at commit
  `7e4523b`: full cost, latency, normalization, blind-review, and probe evidence.
- `docs/solutions/architecture-patterns/2026-08-12-205000-cached-bilingual-trend-narratives.md`:
  durable ledger, queue isolation, last-good, and publication pattern.
- [DeepInfra chat API overview](https://docs.deepinfra.com/chat/overview):
  priority service, structured output, and reasoning parameters.
- [DeepInfra reasoning controls](https://docs.deepinfra.com/chat/reasoning):
  `reasoning_effort=none` behavior.
- [DeepInfra 0731 endpoint](https://deepinfra.com/deepseek-ai/DeepSeek-V4-Flash-0731/api):
  exact route, JSON support, priority support, and request schema.
- `docs/research/2026-09-24-163708-headline-0731-qualification-no-go.md`:
  first campaign failure, blinded scores, and remaining activation gates.
- `docs/research/2026-09-24-153052-finance-informed-headline-context.md`:
  preserved finance handoff, official research links, implementation boundaries,
  and limitations; integration authorized by the owner after that handoff.
- `docs/research/2026-09-24-170254-headline-packet-size-audit.md`:
  captured-message byte measurements and reproduction method, without paid calls.
- `docs/research/2026-09-24-175847-headline-finance-draft-prompts-exhibit.md`:
  full proposed prompt text for all three stages, exact user-message templates,
  and an explicitly fictional packet example; not implemented or tested.

---

## Implementation Units

For the revised campaign, reuse U1–U3, then execute **U7 → U8 → U9 → U4 → U5
→ U6**. U6 requires a new passing qualification; old unit IDs and the original
failure record are preserved. U5 failures return to the responsible unit/U4
until 0731 is ready; they do not end the plan or select another model. This
amendment does not initiate implementation or paid calls.

### U1. Add strict 0731 headline transport profiles

**Goal:** Express and attest each headline stage through direct DeepInfra
without loosening other callers.

**Requirements:** R4–R5, R10, R13.

**Dependencies:** None.

**Files:** `x_monitor/deepinfra.py`, `monitor/trend_narrative_generation.py`,
`x_monitor/config.py`, `tests/test_deepinfra.py`,
`tests/test_trend_narrative_generation.py`, `tests/test_llm_config.py`.

**Approach:** Add named rank/editor/critic profiles; admit only their approved
structured-output and priority fields; resolve only `DEEPINFRA_API_KEY`; and
persist the full non-secret provider receipt. Reject model or tier mismatch
before the response can become publication input.

**Execution note:** Characterize the current strict client first because its
omission of headline-only fields protects existing profiles.

**Patterns to follow:** Named DeepInfra request profiles, provider telemetry,
and provider-call JSON payloads.

**Test scenarios:**

- A valid profile emits exact model, priority tier, samplers, structured mode,
  and no reasoning.
- Existing classifier and Gemma profiles remain byte-for-byte unchanged.
- Callers cannot override pinned fields or inject routing controls.
- Missing credential, model/tier mismatch, incomplete response, 429, timeout,
  and malformed usage fail closed without a second transport.
- Successful calls persist actual tokens, cost, request ID, model, tier, and
  latency without credentials.

**Verification:** Transport and configuration tests prove isolation and receipt
attestation; existing enrichment-route tests remain green.

### U2. Build two-brand 0731 request contracts

**Goal:** Reduce per-call cognitive and output load while making brand ownership
and critic evidence alignment explicit.

**Requirements:** R1–R6, R8.

**Dependencies:** U1.

**Files:** `monitor/trend_narrative_candidates.py`,
`monitor/trend_narrative_generation.py`, `x_monitor/config.py`,
`tests/test_trend_narrative_candidates.py`,
`tests/test_trend_narrative_generation.py`.

**Approach:** Replace fixed five-brand math with a two-brand setting; retain
recursive one-brand splitting; version closed stage schemas; send structured
brand-local critic bundles; and shorten prompts around checks for direction,
causality, sample scope, brand ownership, proper names, and locale parity.

**Test scenarios:**

- Zero, one, two, three, and forty eligible brands produce complete ordered
  packets with no batch above two brands.
- An oversized pair splits without losing evidence or changing rank order.
- Each structured draft is paired only with its matching dossier.
- Invalid raw output remains bounded and cannot inject instructions.
- Cross-brand IDs, reversed numbers, translated proper names, and missing locale
  fields trigger the intended control.
- Existing low-risk bypass and risk reasons retain their behavior.

**Verification:** Packet fixtures prove size, ownership, deterministic identity,
and readable versioned prompts; legacy headline validators still pass.

### U3. Run the call graph at concurrency three

**Goal:** Recover wall-clock latency through existing Celery fan-out without
weakening call entitlement or publication.

**Requirements:** R7–R10, R13.

**Dependencies:** U2.

**Files:** `monitor/trend_narrative_tasks.py`, `monitor/tasks.py`,
`x_monitor/config.py`, `render.yaml`, `render-staging.yaml`,
`tests/test_trend_narrative_orchestration.py`,
`tests/test_trend_narrative_lifecycle.py`,
`tests/test_render_headline_topology.py`, `tests/test_headline_status.py`.

**Approach:** Keep one task per ledger row; raise isolated worker concurrency to
three with prefetch one; let each completed editor release its critic without an
all-editor barrier; and derive graph budgets and drain validation from batch
size and concurrency using KTD6.

**Test scenarios:**

- At most three transports run simultaneously and a fourth waits.
- A critic starts while unrelated editors remain active.
- Concurrent reconcilers enqueue each stage/batch at most once.
- Pre-send loss recovers; post-send loss becomes ambiguous and never resends.
- Out-of-order completion cannot publish a partial or older run.
- Forty brands fit the caps; the next call or over-budget request suspends before
  transport.
- Render and status agree on queue, prefetch, and concurrency.

**Verification:** Concurrency tests prove one transport per entitlement and one
monotonic activation; topology remains isolated from harvest and beat.

### U4. Tune and lock the best 0731 request shape

**Goal:** Improve 0731's configuration and request shape until it is ready for
independent validation, without tuning on an unseen validation set.

**Requirements:** R5, R10, R12.

**Dependencies:** U1–U3 and, for the revised campaign, U7–U9.

**Files:** `monitor/trend_narrative_evaluation.py`,
`scripts/headline_0731_bakeoff.py`, `tests/test_trend_narrative_evaluation.py`,
`tests/test_evaluate_trend_headlines_command.py`, `docs/research/`.

**Approach:** Reuse the no-publication harness, pinned to direct DeepInfra
0731, with explicit batch size and bounded concurrency. Freeze a diagnostic
set around the observed semantic failures. Run up to three correction rounds
per finite experiment cycle over KTD5's dimensions; record exact requests,
receipts, error categories, and the change addressing each failure. When a
cycle is insufficient, amend the responsible implementation unit and continue
with another bounded cycle instead of proposing another model. Freeze one
profile per stage for the next independent validation.

**Current iteration rule (owner direction, 2026-09-24):** Narrow the
remaining model work to source attribution: ranking comparison classes and
the actor/action/target of allegations or motives. Finish one correction,
replay both saved source-backed regressions, then run one newly frozen,
disjoint validation set. Resolve audit-verdict contradictions as a separate
schema/code defect. Do not tune for minor wording or optional details. If
either regression remains materially wrong, or fresh review finds a material
error, keep the release closed, diagnose that failure, and run another bounded
0731 correction and genuinely new validation. The owner explicitly authorized
continuing these loops while away until success; record each attempt and
provider bill. Retain the zero-material-error rule and five 4/5 rubric means.

For the revised campaign, treat all first-qualification outputs and reviewer
comments as diagnostic material. Include suppressed comparisons, unrelated
Yi suffix matches, product/parent-brand scope, wrong-company financial figures,
interval-confused percentages, allegation attribution, and spike/cooling
fixtures. Lock baseline/phase thresholds and projection versions alongside
prompts. Compare old/new packet bytes before paid execution; preserve all
selected source IDs or document relevance replacement and insufficient supply.

**Test scenarios:**

- Preflight rejects unbounded resources, concurrency above three, unknown
  route/profile, stale price evidence, and oversized packets.
- Evaluation never exceeds manifest concurrency and writes deterministic output
  order despite completion order.
- Diagnostic and holdout IDs are disjoint; locked profiles cannot change after
  holdout start.
- Every round preserves exact prompt/schema, receipt, errors, tokens, cost,
  latency, and artifact digest.
- The third failed round records a next-cycle diagnosis and bounded manifest,
  not an automatic abandonment or request to reopen the chosen model.
- No competing headline model is called by the active tuning workflow.

**Verification:** The tuning report names all attempted shapes, their observed
failures/improvements, cumulative spending, and the exact locked configuration
or concrete next correction cycle.

### U5. Validate 0731 against product requirements

**Goal:** Establish whether this 0731 revision is ready to deploy and identify
the corrections needed when it is not.

**Requirements:** R1, R8–R19; SC1–SC9.

**Dependencies:** U4.

**Files:** `scripts/headline_0731_bakeoff.py`,
`monitor/trend_narrative_evaluation.py`, `docs/research/`,
`tests/test_trend_narrative_evaluation.py`.

**Approach:** Freeze a new unseen source corpus and historical inputs; do not
reuse already reviewed qualification outputs as a fresh holdout. Run only the
locked 0731 configuration. Apply representation-only normalization; have three
independent reviewers assess 24 narratives, eight disjoint items each, against
their source packets and the five-part SC2 rubric. Hide configuration identity
and freeze the review manifest before exposing output. Measure end-to-end
concurrent wall time, queue drain, memory, tokens, actual billed spending, and
supported-narrative availability. Emit one hashed `ready_0731` or
`improve_0731` result with all unmet SC IDs. Remove comparative-model execution,
paired-model scoring, and alternate-model decision requirements from the active
validation command. Historical evaluation artifacts remain readable.

For `improve_0731`, turn the failures into targeted diagnostic cases, amend the
responsible implementation unit, and return to U4 under another finite budget.
The next validation uses fresh unseen data; do not relabel the same examined
cases as an independent pass. Model selection is closed.
The current iteration rule above narrows each return to U4 to material failures
with a concrete, independently verifiable correction.

**Test scenarios:**

- Lower spending or faster completion cannot offset unsupported claims.
- A critical support error, tier mismatch, incomplete brand, excessive memory,
  or unsafe drain produces `improve_0731` and a correction plan.
- High average usefulness cannot hide a critical factual error or withholding
  narratives that the source packet supports.
- A passing result uses provider receipts and verifies every success criterion
  mechanically before writing the decision.
- No alternate-model API key, output, bill, or comparative score is required.

**Verification:** The report includes raw counts, blinded judgments, bills,
wall-clock distributions, route attestation, hashes, and a readiness decision
with the exact correction path for every unmet criterion.

### U6. Activate 0731 and preserve operational recovery

**Goal:** Deliver the validated 0731 headline route with last-good serving and
recovery that does not change the selected model.

**Requirements:** R4–R5, R10–R13; SC7.

**Dependencies:** U5 with `ready_0731`.

**Files:** `config.yaml`, `render.yaml`, `render-staging.yaml`,
`monitor/trend_narrative_generation.py`, `monitor/trend_narrative_projection.py`,
`monitor/views.py`, `x_monitor/config.py`, `tests/test_llm_config.py`,
`tests/test_headline_status.py`, `tests/test_render_headline_topology.py`,
`docs/reference/headline-trend-narratives.md`, `docs/deploy/render.md`.

**Approach:** Pin the qualified route, profiles, prompt versions, priority
prices, batch/concurrency controls, budgets, and publication epoch; use the
DeepInfra worker secret; remove alternate headline model/fallback controls from
the active path while preserving credentials needed by other roles. Expose
route receipts and capacity in status. Stage the exact candidate disabled-first
before a bounded canary, then deliver through the recorded production guide.
The first release recovers by disabling new generation and serving persisted
last-good output; subsequent releases may also restore a previously qualified
0731 configuration. Neither recovery mode invokes another headline model.

**Test scenarios:**

- Stale model, endpoint, profile, price, tier, credential, or concurrency fails
  closed.
- Status distinguishes configured route from observed receipts without secrets
  or post text.
- Disabled calls serve last-good copy and perform no transport.
- Restoring a qualified 0731 configuration affects new runs without erasing
  rows or retrying an in-progress call; disabling generation preserves serving.
- No configuration or error handler silently routes headlines to another model.
- Shared credentials and non-headline enrichment behavior are unchanged.
- A bounded staged run publishes only after all brands are terminal and serves
  all three locales.

**Verification:** Configuration, topology, status, projection, and recovery
tests pass; reference docs describe the live route rather than experiment
history.

### U7. Compact and constrain the provider packet

**Goal:** Remove repeated and unusable input while correcting the evidence and
fact-scope failures exposed by the first qualification.

**Requirements:** R3, R5–R6, R14–R15, R18–R19; SC8–SC9.

**Dependencies:** Existing U2; first no-go and packet-size audit are diagnostics.

**Files:** `monitor/trend_narrative_candidates.py`,
`monitor/trend_narrative_generation.py`,
`tests/test_trend_narrative_candidates.py`,
`tests/test_trend_narrative_generation.py`, `docs/research/`.

**Approach:** Implement the six packet cleanup steps above. Preserve rich
private snapshots, add strict per-stage projections, and carry concise
unavailability rather than unusable numerical values. Audit source relevance
before selecting examples: Turkish suffix `-yi` alone cannot substantiate
01.AI; a multi-company post's DeepSeek financing cannot become Kling financing.
Use existing verified brand/product relationships and source text; do not
invent an alias or hardcode holdout IDs. Where attribution is uncertain, retain
the uncertainty and require the critic to omit/hold that claim. Do not rewrite
underlying `PostBrand` or classification rows in this headline task.

**Verification:** All provider-visible paths omit suppressed comparisons and
private scores; the canonical audit packet preserves every selected evidence
ID, source language, and negation. The source-isolated final writer records its
lead ID and omitted-source count, and the validator rejects claims cited to
another post. Measure the serialized request actually sent, not only its local
enclosing artifact. Record changed source selection separately from
representation-only savings and evaluate lost cross-post context in SC2.

### U8. Add bounded historical and phase facts

**Goal:** Explain unusual activity and its progression with measured context.

**Requirements:** R16–R19; SC8–SC9.

**Dependencies:** U7.

**Files:** `monitor/trend_narrative_facts.py`,
`monitor/trend_narrative_candidates.py`, `monitor/trend_narrative_demand.py`,
`monitor/trend_narrative_generation.py`,
`tests/test_trend_narrative_facts.py`,
`tests/test_trend_narrative_candidates.py`,
`tests/test_trend_narrative_demand.py`, `docs/research/`.

**Approach:** Implement the Finance-informed fact contract in the existing
snapshot transaction. Start with completed 1/7-day matched intervals, shared
scope references, peak/recent/overall facts, bounded phases, and participation
counts. Inspect available harvest/coverage provenance before admitting any
historic norm. Calibrate on diagnostics; store all rejected/unsupported facts
privately and expose concise unavailable status. Incomplete history must not
prevent a supported current-topic narrative. New content stays in existing
trilingual output fields and requires no browser/filter redesign.

**Verification:** Fixtures distinguish `[10,20,80,40,15]` from a steady rise
with the same endpoints; recent decline from overall growth; a regular weekly
cycle from an unusual burst; and a broad conversation from repeated posts by
one author. Test zero/flat/low bases, missing/incomplete buckets, backfill,
scope changes, source deduplication, and observations after `as_of`. Assert
resource-limited/insufficient baselines remain unavailable, with no divide-by-
zero or invented normal-range claim. Measure database and snapshot-build cost
as well as provider bytes; added context must remain bounded.

### U9. Regression net for factual support and compaction

**Goal:** Prove that the real headline call chain uses the redesigned facts
without weakening last-good serving or introducing new model calls.

**Requirements:** R1, R8–R9, R14–R19; SC7–SC9.

**Dependencies:** U7–U8.

**Files:** `tests/test_trend_narrative_candidates.py`,
`tests/test_trend_narrative_facts.py`,
`tests/test_trend_narrative_generation.py`,
`tests/test_trend_narrative_evaluation.py`,
`tests/test_trend_narrative_orchestration.py`,
`tests/test_trend_narrative_projection.py`, `tests/test_trend_narrative_demand.py`.

**Approach:** Add unit fixtures plus production-caller tests with captured
provider kwargs for snapshot → ranking → editor → critic/reconstruction →
persisted projection. Validate typed numerical bindings and interval/unit/brand
ownership in code. Tune the existing critic to distinguish current counts,
endpoint changes, historical comparisons, source-level allegations, and
unsupported aggregate causality; repair or hold when support is absent.

**Verification:** Cover all three locales, short ambiguous/non-English posts,
per-brand product ownership, a wrong-company amount with a valid evidence ID,
partial taxonomy coverage versus total post counts, unknown extra private
fields, duplicate translation aliases, URL/stopword phrases, retained valid
model/version phrases, retained minority opinions, and stable citation IDs.
Prove valid and invalid-editor critic paths enforce the same eligible-fact
boundary; no code-only fixture is counted as an LLM quality pass. Re-run demand,
one-call, ambiguity, bypass-risk, atomic-publication, and last-good regressions.

---

## Verification Contract

### Automated gates

- Run `pytest tests/test_deepinfra.py tests/test_llm_config.py tests/test_trend_narrative_generation.py`.
- Run `pytest tests/test_trend_narrative_candidates.py tests/test_trend_narrative_orchestration.py tests/test_trend_narrative_lifecycle.py`.
- Run `pytest tests/test_trend_narrative_facts.py tests/test_trend_narrative_demand.py tests/test_trend_narrative_projection.py` for the revised factual and serving contract.
- Run `pytest tests/test_trend_narrative_evaluation.py tests/test_evaluate_trend_headlines_command.py tests/test_headline_status.py tests/test_render_headline_topology.py`.
- Run the full `pytest` suite after focused checks because worker concurrency
  and shared transport cross module boundaries.
- Run `python manage.py check --deploy` against release configuration.
- Run finite tuning and qualification only with explicit manifests and budgets.

### Behavioral gates

- Inspect representative rank, editor, critic, invalid-editor recovery, and
  bypass artifacts in all three locales.
- Preserve every score and comment from the 24-item source-grounded review.
- Verify actual receipts show exact model, priority, tokens, cost, and zero
  reasoning tokens.
- Verify SC4 and SC6 from wall-clock, queue, and process telemetry rather than
  summed provider latency.
- Verify SC8 through captured production-call inputs and output/projection
  checks, including invalid-editor recovery; measure SC9 with unchanged source
  inputs and new historical context included. Preserve byte, token, database,
  provider-latency, and total-wall-time breakdowns separately.

### Release gates

- U5 must record `ready_0731`; an `improve_0731` result returns to correction
  and another bounded validation cycle before U6 changes the active route.
- Before Git or deployment mutation, rerun Ollija's plan check and resolve its
  placement guidance or record an owner-directed Delivery Exception.
- The staging run after fresh qualification must prove no harvest-call change, no queue
  crossover, no partial publication, no route mismatch, and valid operational
  recovery within the 0731-only contract.

---

## Definition of Done

- U1–U5 and U7–U9 are implemented and verified; U6 runs only after a fresh
  `ready_0731`. Original failure evidence remains unchanged.
- Every requirement and success criterion has automated or preserved evaluation
  evidence.
- The delivered route is exact-model direct DeepInfra 0731 priority with
  reasoning disabled, two-brand packets, and concurrency three.
- Failed revisions lead to corrections and retesting of 0731; they do not
  complete the plan or select a replacement model.
- No alternate headline-model benchmark, fallback, or rollback is required or
  retained in the active delivery contract. Last-good persisted output remains
  available with its original provenance.
- Route identity, tier, latency, tokens, and cost are auditable without secrets
  or post text.
- Last-good, call-entitlement, ambiguity, critic-routing, and atomic-publication
  regressions pass.
- Current reference and deployment docs match the qualified runtime.
- Abandoned prompt variants, temporary credentials, unreferenced fixtures, and
  dead code are removed; durable reports and hashes remain.
- Commit, push, staging deployment, and production deployment follow the
  refreshed Ollija production guide and all qualification gates.

## Prior validation evidence and current direction (2026-09-24)

The prior campaign exposed ten critical factual-support failures in 0731,
including suppressed period comparisons and wrong-brand evidence. Its
measurements, review records, hashes, and gate limitations remain unchanged in
[the qualification report](../research/2026-09-24-163708-headline-0731-qualification-no-go.md).

The owner subsequently selected 0731 unconditionally as the model and retired
the comparative benchmark/alternative-model decision. The old report is
historical evidence, not the current decision policy. Its failures remain
diagnostic input; they have not been rewritten as passing results. U7–U9 and
the iterative U4/U5 workflow now address those failures until the 0731 route
meets the product's own requirements. Model choice is settled; deployment still
requires a ready configuration and the staging/production checks.

## Execution progress — 2026-09-24

- U7 complete in `dcc704e`: closed compact packet, deduplicated text, scoped
  facts, cleaned phrases and source relevance.
- U8 complete in `a47aa27`: bounded historical eligibility, completed-bucket
  activity and participation facts; absent collection-regime proof produces
  unavailable historical norms.
- U9 complete in `c60194e`: measurement/value/unit/scope validation and real
  PostgreSQL snapshot-to-publication regression coverage.
- U4 configuration frozen after ten completed diagnostic rounds (200 calls).
  Cycle 4 round 2 was interrupted at the owner's pause; its partial receipts
  remain preserved and are not reported as a completed result. The approved
  final-output severity policy is committed in `94fbc7c`.
- U5 in progress: fresh generation uses 44 eligible brand/window cases, with
  no reused source IDs or exact excerpts from prior diagnostics. The 24 review
  assignments and revised rubric were locked before output. Repaired controls
  require source review; a passed transport alone does not close this gate.
- U6 pending: status receipt reporting prepared; active production routing and
  infrastructure remain unchanged until qualification and staging pass.

Detailed receipts, changes and limitations:
[0731 finance tuning report](../research/2026-09-24-195100-headline-finance-0731-tuning-cycle1.md).

### U4/U9 corrective refinement — explicit critic source check

Cycle 2 showed that correct citation IDs and additional instructions were not
sufficient: the critic approved an unrelated company story and treated an
adversarial instruction as news. Cycle 3 preserves the selected model, disabled
reasoning, three stages and two-brand packets. Its critic response schema 4
adds a bounded source assessment before the verdict: subject, target-brand
relevance, up to four literal cited passages, and up to four draft errors.
Keep these in audit storage only. Reject quote/citation mismatches, approval
with listed errors, and publication when the model's own relevance assessment
is absent/incidental. A valid literal quotation still does not establish
entailment; SC2 remains unchanged. Re-run the diagnostic cycle, freeze the
resulting profile, then use the reserved unseen corpus. Do not promote by
changing the quality target or counting withheld useful narratives as success.

The cycle-3 source check now cites deterministic passage IDs instead of asking
the model to reproduce quotations. Each ID resolves to exact request text;
no generated narrative text is added by code. Source fields are split into
bounded, lossless passages only in the audited critic request. Tests prove
text reconstruction, per-source identity, ownership and audit-only persistence.
This is a request-shape correction for quote-copy failures; independent
semantic review remains required. The full-message compaction experiment,
including finance and this source check, measured 23.99% fewer bytes on the
same archived workload; it does not establish a token reduction.

Cycle 3 closed with the financial-amount correction working, but one invalid
relevance/verdict combination and an unresolved source contradiction. Cycle 4
is explicitly bounded to three correction rounds: assess relevance of the best
supported replacement, preserve reviewed staff discussion, and require a short
source-conflict audit before the verdict. Record disagreements with IDs from
both passages; validate ID ownership and reject duplicate/invented support.
Do not mistake these mechanical checks for semantic qualification. The reserved
unseen set and independent review assignments are still sealed.

### Owner-approved severity policy — 2026-09-24

The owner paused broad iteration to distinguish material errors from minor
wording and harness defects, then approved continuing with this distinction.
`final-output-severity-v2` judges the final reader-visible result. Preserve the
zero-material-error gate and five rubric means of at least 4/5; minor style,
harmless omission and mild scope issues are deductions rather than standalone
release blockers. A normal critic repair counts as a successful pipeline
repair. Keep raw intermediate failures in the report. Fixture defects are
reported separately and make the affected control inconclusive; correct that
fixture and retest its control rather than retuning the generator for it.
Earlier results remain unchanged. The first fresh qualification's assignments
remain fixed; archive the earlier rubric and lock this owner-selected rubric
before generating or reviewing any fresh output. Return to prompt tuning only
for material failures or an unmet aggregate quality threshold.

### Owner-directed correction scope — 2026-09-24

The first fresh review found four material failures among 24 cases: two
source-attribution errors and two useful narratives withheld by contradictory
audit fields. All five rubric means passed; all eight corrupted-draft controls
were successfully repaired. The first replay fixed the ranking comparison but
still approved the misattached accusation. A partial-branch `anyOf` schema
experiment made the live decoder omit required fields, so that shape was
rejected. Complete closed schema branches now retain the local validator.
The owner then authorized continued bounded iterations while away until the
same quality gates pass. A miss still stops promotion of that candidate.

### Cycle 7 source-ownership regression net

The next blind source freeze is
`.context/headline-finance-cycle7/fresh-unseen-source.json` (SHA-256
`713fbf737a5bdff877637064d16c396b0f9a35d84905e3e94a7ccd26605cf61d`).
It excludes selected evidence IDs and exact excerpts from prior frozen sets
before the bounded evidence reservoir is filled. The 24 reviewer assignments
(12 per window, eight per reviewer), fixed rubric, and ten required saved
regressions are sealed in
`.context/headline-finance-cycle7/validation/manifest.json` before any fresh
candidate generation. The combined fixture is
`tests/fixtures/headline_all_source_regressions.json`.

The final 0731 writer receives source spans, verified aliases, deterministic
Chinese discount glosses, and sanitized evidence-ID hints from the editor. It
does not receive an earlier draft as content to approve. Its source check must
own the English wording, which the three-locale narrative copies and translates.
The validator keeps one cited source per proposition and rejects false holds
for direct brand mentions. It rejects unverified cross-post links, including
shared authorship without matching observed handles and shared test-series
claims without explicit source support. A bounded, source-preserving correction
may remove only the unsupported link wording from English, Chinese, and
Japanese together; unknown phrasings remain invalid. Short, non-primary
product keywords by themselves do not establish brand ownership. Raw provider
output and final normalized output must both remain in qualification receipts.

The v31 and v33 ten-case provider replays were mechanically complete but
failed independent factual review on discount meaning and corpus-count/source
scope. The partial v32 replay exposed one source-check/final-line mismatch.
Those receipts and reviewer reasons are recorded in
`docs/research/2026-09-24-195100-headline-finance-0731-tuning-cycle1.md`.
The correction is limited to Chinese 1折 basis in Japanese, attribution of
corpus counts to the collected dataset, and deletion of an unsupported
all-post negative from a bounded nonrandom sample. Mechanical guards reject
unknown variants. The v34 replay exposed a spacing variant of the Japanese
discount error; v35's spacing-tolerant guard closed it. The v35 combined
ten-case replay passed mechanical checks and independent source review with
zero critical failures and factual support at least 4/5 in every case. Fresh
qualification and operational criteria still control U6 activation.

Cycle 8 froze new selected evidence IDs and exact excerpts in
`.context/headline-finance-cycle8/fresh-unseen-source.json` (SHA-256
`b08740c4dc1213ed7dd7aac2c63ff5b4ace87f05be23797fe70c9463b607f94a`)
and sealed 24 disjoint case/reviewer assignments in
`.context/headline-finance-cycle8/validation/manifest.json`. The v31 fresh
run was stopped on a failed regression and produced no reviewed candidate
artifact; Cycle 8 was unseen before the locked v35 fresh generation began.

Cycle 8's v35 fresh run completed, but five of 24 reviewed cases had material
source-ownership or false-hold failures and two final-writer batches were
mechanically invalid. Its unchanged SC2 and SC3 gates failed; no v35
publication is authorized. The supporting report is
`docs/research/2026-09-24-195100-headline-finance-0731-tuning-cycle1.md`.
The next finite diagnostic cycle tests source isolation: v36 exposed all
selected posts and showed that 0731 still transferred a claim from a second
post while citing the chosen lead; v37 exposed only the lead and removed that
transfer in the targeted case but one empty-evidence hold call timed out.
V38 retains one example solely to explain no-lead holds, selects a brand-
centric lead using the existing editor's citations only as untrusted salience
hints, and confines the final writer to that single post. All ten saved
regressions were mechanically valid in the v38 diagnostic. Independent Sol
source review found no critical failure and factual support at least 4/5 for
all ten, closing the saved-regression gate. Cycle 9 then froze a new disjoint
production source and reviewer manifest before v38 fresh generation. Cycle 8
remains diagnostic material and cannot serve as an unseen holdout.

Cycle 9 froze another disjoint production source
(`.context/headline-finance-cycle9/fresh-unseen-source.json`, SHA-256
`ffe8273324a6794a3ce88559d3886435045b9f3869b984a3092f85a46a89b68c`)
and sealed its 24 assignments and eight controls before v38 generation. The
46 calls finished without transport failure for $0.05857470. Three blind
reviewers scored all five dimensions above 4/5 on average and all controls
contained no surviving unsupported claim. SC2 still failed: one supported
InclusionAI Ling-3.0-flash-VL story was withheld because the source snapshot
did not recognize a curated official handle mentioned by a third party. SC3
also failed: a short Sakana AI joke was expanded into an unsupported dated
event, which the validator rejected, invalidating its paired Yi batch. The
Cycle 9 report and reviewer scores remain immutable diagnostic evidence.

V39 adds curated, brand-specific official handles to source attribution and
requires a substantive lead when an entire public dossier consists of brief
opinion/reaction posts. The former restores a supported product story; the
latter prevents short jokes from becoming a headline and keeps their paired
brand's result available. Both rules are tested against Cycle 9 source cases,
not brand-name exceptions in the runtime. Replay Cycle 9 as a diagnostic only,
then run the ten saved regressions and independent source review. Freeze a
**new disjoint** production source and reviewer manifest before candidate fresh
qualification. The unchanged gate still requires ten valid, relevant,
noncritical saved cases, 24 independent fresh reviews with five 4/5 means and
zero material errors, zero unresolved final responses, eight safe controls,
the cost ceiling, and worker timing/memory checks. Only a candidate meeting
these criteria advances through disabled-first staging, bounded staging
publication, exact-SHA production verification, and Ollija-guided delivery.

The v39 replay recovered InclusionAI but exposed a projection mismatch:
provider packets hold post types in `taxonomy.post_types.values`, not the
private `post_type_keys` field. V40 reads the projected field and converts any
model-written no-lead narrative to a deterministic hold before claim
validation; raw output is retained for audit and no content is manufactured.
A small v40 two-window probe retained the paired Upstage story and produced
clean normalized holds when Sakana AI and Yi lacked a substantive lead. Run
the ten saved regressions and independent review under v40, then use a **new**
unseen source and sealed 24-case manifest for formal qualification. The v40
ten-case replay has now finished 10/10 mechanically valid; independent Sol
review found zero critical errors and every factual score at least 4/5.
The new disjoint source freeze and manifest seal completed before fresh
generation.

Cycle 10 completed on a newly frozen, disjoint source (SHA-256
`76631cf01fe419d73f5d1c98fb339e375557c6dc0b800e860aca1867277c63c4`).
V40 used 46 calls and $0.05786667 in provider-billed generation. The final
critic batches were mechanically valid; all five 24-case rubric means exceeded
4/5. Independent review still found two material errors, so SC2 failed and
this candidate cannot advance: Q122 withheld a supported InclusionAI model
release, and Q127 translated Chinese `48折` (pay 48% of the applicable price)
as “48% off” in English and Japanese. The frozen source, manifest, raw calls,
and reviews remain diagnostic evidence under `.context/headline-finance-cycle10/`.

V41 addresses these two root causes only. Snapshot attribution reads exact
brand-linked model names already present in the Product catalog, retaining
only names visible in the bounded source reservoir; it does not admit bare
ambiguous short names such as “Ming.” Discount projection resolves two-digit
Chinese shorthand into both pay and off percentages and repairs the exact
pay-percent-as-discount inversion in the final source-linked text. Tests must
pin the source-to-lead call chain and the three-language discount output.
Replay Cycle 10 only diagnostically, close the ten saved regressions with
independent source review, then freeze a *new*, disjoint production source and
seal assignments before V41's fresh 24-case qualification. No staging
activation is allowed until SC2 and SC3 pass on that fresh source.
V41's ten saved regressions have now passed mechanical and independent Sol
source review with zero critical errors and every factual-support score at
least 4/5. The new Cycle 11 source is frozen at SHA-256
`01c4d2ebc43a19553212249d750605f2b14ec64116a6a467bc68c2b48c9276b3`,
and its 24 review assignments were sealed before generation. Fresh V41
qualification then proceeded under that seal.

Cycle 11's sealed V41 run completed 40/40 calls, 29/29 eligible brand
outcomes, zero mechanically invalid finals, zero missing locales, and
$0.05293098 in provider-billed calls including eight controls. The 24 blind
reviews averaged at least 4/5 on each dimension, but two material findings
failed SC2. Q151 incorrectly attributed a Reliance battery/solar-wafer post
to Upstage because bare secondary `Solar` was treated as brand evidence *and*
the final-source selector treated the last word of `Upstage Solar` as a brand
name. Q166 omitted a cited `Date: Nov 10, 2024` from a Llama hackathon recap
posted in 2026, making an old win look current. The preliminary qualification
at `.context/headline-finance-cycle11/validation/qualification-v41-preliminary.json`
records SC1, SC3, SC4, and SC5 as passed; SC2 and the still-unmeasured staging
operations fail. This remains diagnostic evidence, not a release candidate.

V42 makes one shared attribution correction and one temporal-context
correction. A bare, nonprimary ASCII product keyword cannot anchor a company
headline by itself; exact catalog model names, multiword model names, primary
brand names, and reviewed official handles remain eligible. The lead selector
uses the complete display name rather than treating its final word as an
independent identity. The final critic must preserve an explicit labeled past
event date in all three visible locales; a deterministic source-date guard
repairs an omitted date only when one unambiguous labeled date is more than
90 days before its post. Recheck Q151/Q166 and the ten saved regressions, then
freeze a *new* disjoint source and sealed review assignment before V42's
fresh qualification. Minor review suggestions are recorded but are not a
reason for an unbounded prompt-tuning loop.

The first V42 preparation uncovered a saved regression: a Moonshot Kimi
source was held because its display-name suffix `Kimi` also appears in the
canonical brand key `moonshot_kimi`. The still-running V42 regression replay
and read-only freeze were stopped; their partial files are diagnostic only
and confer no qualification. V43 narrows the suffix rule: accept it only when
the suffix is also a token in the canonical brand key. This keeps `Kimi`
eligible without making generic `Solar` an identity for `upstage`. The
affected focused suite passed 113 tests, including PostgreSQL checks. V43
must use a new regression directory, a new disjoint source freeze, and sealed
review assignments. No V42 results may be counted toward release gates.

V43 passed 10/10 saved mechanical regressions and the expanded headline tests
(318 passed). Independent review found one critical factual error in saved
Q32: the Chinese line attached “one day” to a +5.55% return although the
source applied that period only to an 11-place ranking climb. The already
sealed fresh V43 run was stopped after partial rank/editor calls, before a
complete artifact; it is not qualification evidence. V44 adds one general
numeric-scope rule to the existing source-ledger prompt: each number retains
its entity, metric, and time period independently in EN/ZH/JA. Probe Q32
before replaying the ten saved cases and reviewing them; only after that,
freeze another disjoint source and seal assignments for fresh qualification.
Do not tune minor copy changes or broaden taxonomy in this loop.

The single Q32 V44 probe separated the figures correctly, but the same
prompt produced a wrong daily-return scope in its ten-case replay. This is
model variance, not a solved gate. V45 adds a narrow normalization after the
model's source ledger: when the ledger calls a percentage a period-unspecified
return, separately calls a rank change one-day, and the cited source confirms
both figures, remove a one-day modifier that the Chinese or Japanese text
places directly on the percentage. This only deletes unsupported timing from
visible text; it does not create a new event, figure, or claim. Unit tests
cover both the correction and a genuinely daily return that must remain
untouched. Revalidate the V44 raw Q32 result diagnostically, then run fresh
V45 saved regressions and independent review before any full fresh run.
The V44 live source and 24-case manifest were frozen and sealed but never
used for a completed generation or review. V45 reuses those byte-identical,
still-unseen source and assignment files; its code change is downstream of
source selection. The frozen source SHA remains
`2285a16e82661d4bbcce532b2b55e9e38b95a0ace85253d68867b39eec44e4ea`.
Any V45 generation and all three reviews must refer to that same SHA.
The V45 saved replay passed 10/10 mechanical checks. Independent Sol review
found zero critical failures, no holds, and factual-support scores of at
least 4/5 for every case. A separate diagnostic review of the normalized V44
Q32 raw output scored factual support 5/5 and translation equivalence 4/5,
with no critical error. The sealed 24-case V45 production-shaped trial is the
next gate; saved-case success alone does not authorize staging.

V45 finished all 36 planned calls and 26/26 eligible brand outcomes, with
zero mechanically invalid finals or missing locale fields. Direct DeepInfra
receipts totaled $0.04903794; observed snapshot-plus-generation time was
283.834 seconds for one day and 320.54 seconds for seven days. The blind
24-case review failed SC2 on three concrete failure classes. Q218 and Q223
were false holds of a supported Nemotron 3 Diarization app post: the bare
secondary keyword `nemotron` was correctly excluded as ambiguous, but its
versioned phrase was not admitted as a product identity. Q239 softened a
Chinese abusive quote to Japanese “outdated,” changing the register; Q240
translated AI-service Tokens as Chinese `代币`, implying crypto tokens. The
preliminary qualifier passed SC1, SC3, SC4 and SC5 and failed SC2; SC6–SC9
are unmeasured. No V45 staging activation is allowed.

V46 handles these exact classes without broad taxonomy work. A long secondary
alphabetic product keyword followed by a version number becomes an alias for
the *versioned phrase only*, so `Nemotron 3` can anchor its app post without
making every bare Nemotron mention a source; the short `Solar`/solar-wafer
false match remains excluded. The source-ledger prompt tells the writer to
paraphrase abusive language with equivalent strength across locales if it
cannot translate a slur faithfully. AI app/model usage `Tokens` remain
`Token`, `词元`, or `额度` in Chinese; a source-conditioned normalizer restores
`Token` when an AI-service source explicitly distinguishes it from API Token
and does not discuss cryptocurrency. Focused tests cover both attribution and
lexical guards. Probe Q239/Q240, replay the saved source failures, and only
then freeze and review a new disjoint live source. Do not deploy V45.

## Remaining delivery — U6 V56 pin and exact-SHA promote

Owner-directed freeze: V56 is the candidate. Do not add another critic
prompt version. Remaining work is U6 plus Ollija production delivery.

### U6 pin (this SHA)

Write the bakeoff lock into `config.yaml` `headline_narrative`:

- provider `deepinfra`, base_url `https://api.deepinfra.com/v1/openai`
- model `deepseek-ai/DeepSeek-V4-Flash-0731`
- rank `headline-rank-0731-v3` / `headline_rank_v2`
- editor `headline-editor-finance-v9-ja` / `headline_editor_v4`
- critic `headline-critic-finance-source-audit-source-ledger-only-v56-ja` / `headline_critic_v6`
- timeout 300; rank/editor/critic max tokens 7000/8000/8000
- `per_brand_batch_size` 2, worker concurrency 3
- cost cap `$0.30`, prices `$0.09` / `$0.27`, pricing version `deepinfra-priority-0731-2026-09-24`
- bump `publication_epoch` so persisted last-good is not mixed with V56 prose

Env flags still gate transport: staging worker starts with provider calls
off; production yaml already has them on. Recovery is disable provider
calls and serve last-good.

Merge `origin/main` (`8ba61d5`, HF docs, `[skip render]`) so the candidate
is a fast-forward of `main`. Re-run focused headline + Ollija tests. Commit
and push the feature branch. New HEAD is the candidate SHA.

### Staging then production

Do not push `refs/heads/staging`. Disable auto-deploy on
`pushinweight-staging-web` and `pushinweight-staging-headlines`. Deploy the
exact candidate SHA to those two services. Confirm reported commit SHA.
Prove harvest command/env unchanged. With provider off, last-good still
serves. Then one staging provider-on canary. Stop if SHA, harvest, memory,
or canary fails.

Only then:

```bash
git fetch origin refs/heads/main
git push origin <candidate-sha>:refs/heads/main
```

Confirm `origin/main` and production web + headlines worker report that
SHA. Worktree remove is the final filesystem action and only after that
verification.

**Test scenarios:** `load_config(config.yaml)` returns the V56 lock;
`per_brand_call_cap >= 1 + 2 * ceil(47 / batch_size)`; finance prompt
rejects a non-DeepInfra provider; focused headline and `tests/ollija`
suites pass.
