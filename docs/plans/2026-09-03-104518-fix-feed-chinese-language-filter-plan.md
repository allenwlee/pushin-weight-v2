---
title: fix/feed-chinese-language-filter plan
artifact_contract: ce-unified-plan/v1
artifact_readiness: requirements-only
product_contract_source: ollija-annotate-plan
execution: code
ollija:
  change_id: fix-feed-chinese-language-filter-2026-09-03-104518
  branch: fix/feed-chinese-language-filter
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
- Active worktree: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/feed-chinese-language-filter`
- Plan: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/feed-chinese-language-filter/docs/plans/2026-09-03-104518-fix-feed-chinese-language-filter-plan.md`
- Change: `fix-feed-chinese-language-filter-2026-09-03-104518`
- Branch: `fix/feed-chinese-language-filter`
- Staging branch and blueprint: `staging`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/feed-chinese-language-filter/render-staging.yaml`
- Production branch and blueprint: `main`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/feed-chinese-language-filter/render.yaml`
- Staging URL: `https://pushinweight-staging-web.onrender.com`
- Production URL: `https://pushinweight-web.onrender.com`

### Placement

This worktree is inside the Ollija release worktree area. Reuse it for the whole change. Do not create a second worktree or plan for this branch.

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

## Delivery Exceptions

The owner explicitly requested that this fix be pushed through production in
the initiating request on 2026-09-03. The ordinary-plan metadata remains
`delivery_target: on-request`; this request supplies that release authority.

# Goal

Repair the production feed's Chinese source-language filtering and display
without changing translation, enrichment, or Traditional Chinese's placement
in the `Other` filter bucket.

## Product Contract

- Selecting only `简体中文` returns posts persisted with the canonical
  `lang_detected=zh-Hans` value.
- Traditional Chinese remains grouped under `Other`; no separate Traditional
  Chinese filter is added.
- The compact post-language tag displays the persisted canonical script codes:
  `zh-Hans` for Simplified Chinese and `zh-Hant` for Traditional Chinese in all
  display locales.
- English, other language, undetected, translation-layer, and unrelated feed
  behavior remain unchanged.

## Implementation

1. Map the filter's stable `zh-hans` UI key to the canonical `zh-Hans` value
   already produced by enrichment and persisted in PostgreSQL.
2. Preserve `zh-Hant` as an `Other`-bucket language while projecting Chinese
   tags as `zh-Hans`/`zh-Hant` rather than collapsing them to `zh`.
3. Add focused unit, endpoint, and browser regression coverage through the
   real homepage/filter/feed call chain.

## Verification and delivery

1. Run Bridgewright affected-scope assurance and the focused Django/browser
   tests, plus the repository regression net required for an existing-behavior
   change.
2. Commit the clean canonical worktree, push the feature branch, stage the
   exact candidate through the documented staging branch/Blueprint, and verify
   the Simplified-only filter and both Chinese tags in a real browser.
3. Promote that exact tested SHA to `main`, verify production through the same
   browser flow, then apply Ollija's guarded final worktree cleanup only if its
   generated conditions still pass.
