---
title: feat/dots-b-family-tokens plan
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ollija-annotate-plan
execution: code
ollija:
  change_id: feat-dots-b-family-tokens-2026-09-03-100320
  branch: feat/dots-b-family-tokens
  workflow: lfg
  delivery_target: production
  delivery_selected_by_user: true
---
<!-- BEGIN OLLIJA DELIVERY GUIDE -->
## Ollija Delivery Guide

This block is generated guidance. Do not edit it directly. Correct durable facts in `.ollija/project.yaml` or this template, then rerun `./bin/ollija annotate-plan`. Put a user-directed exception in the editable Delivery Exceptions section below.

### Resolved locations

- Authoritative host: `fuchitalee`
- Authoritative repository: `/Users/fuchitalee/development/pushin-weight-v2`
- Ollija release worktree area: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees`
- Active worktree: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/dots-b-family-tokens`
- Plan: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/dots-b-family-tokens/docs/plans/2026-09-03-100320-feat-dots-b-family-tokens-plan.md`
- Change: `feat-dots-b-family-tokens-2026-09-03-100320`
- Branch: `feat/dots-b-family-tokens`
- Staging branch and blueprint: `staging`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/dots-b-family-tokens/render-staging.yaml`
- Production branch and blueprint: `main`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/dots-b-family-tokens/render.yaml`
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
    - From `/Users/fuchitalee/development/pushin-weight-v2`, require `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/dots-b-family-tokens` to remain registered, clean, unlocked, and at the verified candidate SHA. If any guard fails, retain it and report the reason.
    - Run `git -C /Users/fuchitalee/development/pushin-weight-v2 worktree remove /Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/dots-b-family-tokens` without `--force`.
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

- Owner selected `delivery_target: production` in the LFG request on 2026-09-03.
- Do not pause or resume the harvest cron.
- Do not add the bare token `dots`.
- Do not move dots from B to C.
- Do not change the 7-call shape (A + B1 + B2 + B3 + C1 + C2 + C3).
- Do not rewrite B1 truncation/backlog ownership in this change. Token expansion only. Production still needs a later coverage fix if B1 remains tip-capped.
- After production SHA verification, run onboard for the updated dots aliases so BrandKeyword rows exist before fail-closed cycle preflight. That onboard is a bounded Render management command, not a harvest run.

# Goal

Make Call B1's dots brand search include the rest of the Dots Studio product family (`dots.ocr`, `dots.tts`, `dots.llm1`, `dots.vlm`, `dots.mocr`) so those posts can match the same bare B path as `dots3-note` / `dots studio` / `dots3` / `dots4`. Persist the same aliases in the onboard CSV so production BrandKeyword coverage matches policy.

## Product Contract

- B1 query contains the new family tokens and still contains the existing dots3-note / dots studio / dots3 / dots4 tokens.
- B1 query does not gain a standalone `dots` token.
- Dots remains `paths: [bare]` only. No C pack. No 8th call.
- `onboard_brand` of the updated CSV inserts the new patterns as non-primary BrandKeyword rows and remains idempotent.
- Cycle attribution preflight (`_build_brand_index`) still finds a literal DB mapping for every active policy token.

## Settled decisions

- Dots stays on B, not C. Provenance: user-directed. Rejected: C with llm/model or dots+rednote as the only path.
- Do not add bare `dots`. Provenance: user-directed. Rejected: generic dots on B or C.
- Add family tokens to B. Provenance: user-directed (`ok let's do that`). Rejected: leaving OCR/TTS/llm1 off the token list.
- Delivery through production. Provenance: user-directed (`ollija to production`). Rejected: stop after staging.

## TOUCH / PRESERVE

TOUCH:

- `config/harvest_policy.yaml` dots.tokens
- `config/brands/2026-08-31-013447-harvester-quality-upgrade.csv` keyword_aliases
- query exhibit / policy regression tests
- one onboard coverage assertion for the new patterns

PRESERVE:

- 7-call shape, B2/B3 handles, C packs
- dots version_family (`prefix: dots`, major 3, lookback 0, lookahead 1)
- Call A roster / dotsstudioai (out of this unit)
- B1 tip-only one-page clamp and backlog pending_limit

## Units

### U1 — Policy tokens

Add to `config/harvest_policy.yaml` under `brands.dots.tokens`, after the existing two:

- `dots.ocr`
- `dots.tts`
- `dots.llm1`
- `dots.vlm`
- `dots.mocr`

Keep `dots3-note` and `dots studio`. Version family still emits `dots3` and `dots4`.

### U2 — Onboard CSV aliases

Append the same five strings to `keyword_aliases` on the dots row of `config/brands/2026-08-31-013447-harvester-quality-upgrade.csv`, pipe-separated, non-primary.

### U3 — Regression pins

- Update `EXPECTED_QUERY_EXHIBIT["B1"]` and `EXPECTED_AFTER_QUERY_LENGTHS["B1"]`.
- Pin `dots.tokens` in `test_policy_after_hunyuan_glm_dots_declarations`.
- Pin that live B1 `query_string` contains `dots.ocr` and `dots.tts` and that `"dots"` is not a policy token.
- After onboard of the live CSV, `BrandKeyword` exists for each new pattern with `is_primary=False`.
- Assert B1 query length remains `< 512`.

## Production delivery

1. Implement and verify locally with the focused harvest-policy tests.
2. Follow the generated Ollija guide for staging then production SHA promotion.
3. After production web/harvest deploy is at the candidate SHA, on the harvest service (or one-off Render shell against prod DB):

   `python manage.py onboard_brand --csv config/brands/2026-08-31-013447-harvester-quality-upgrade.csv`

   Dry-run first if the command is available. Do not `run_cycle`. Do not pause cron.
4. Done means: next scheduled cycles have BrandKeyword rows for the new tokens, and B1's planned query string includes them. A Dots insert is hoped-for but not guaranteed while B1 remains a shared 20-result tip.

## Credit / risk

Adding five OR tokens to shared B1 does not add a call. It slightly widens the B1 match set. Cost per scheduled cycle stays one B1 page unless truncation walks fire. No `scripts.harvest_cost` volume increase from extra logical calls.
