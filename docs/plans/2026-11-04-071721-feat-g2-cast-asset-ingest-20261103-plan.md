---
title: feat/g2-cast-asset-ingest-20261103 plan
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ollija-annotate-plan
execution: code
ollija:
  change_id: feat-g2-cast-asset-ingest-20261103-2026-11-04-071721
  branch: feat/g2-cast-asset-ingest-20261103
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
- Active worktree: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/g2-cast-asset-ingest-20261103`
- Plan: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/g2-cast-asset-ingest-20261103/docs/plans/2026-11-04-071721-feat-g2-cast-asset-ingest-20261103-plan.md`
- Change: `feat-g2-cast-asset-ingest-20261103-2026-11-04-071721`
- Branch: `feat/g2-cast-asset-ingest-20261103`
- Staging branch and blueprint: `staging`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/g2-cast-asset-ingest-20261103/render-staging.yaml`
- Production branch and blueprint: `main`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/g2-cast-asset-ingest-20261103/render.yaml`
- Staging URL: `https://pushinweight-staging-web.onrender.com`
- Production URL: `https://pushinweight-web.onrender.com`

### Placement

This worktree is inside the Ollija release worktree area. Reuse it for the whole change. Do not create a second worktree or plan for this branch.

### Delivery scope

- Workflow: `plan`
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
    - From `/Users/fuchitalee/development/pushin-weight-v2`, require `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/g2-cast-asset-ingest-20261103` to remain registered, clean, unlocked, and at the verified candidate SHA. If any guard fails, retain it and report the reason.
    - Run `git -C /Users/fuchitalee/development/pushin-weight-v2 worktree remove /Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/g2-cast-asset-ingest-20261103` without `--force`.
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

None.

# G2 cast importer and Graphics reference reader

## Plain-English Summary

Bring the saved importer and reader together so Graphics Editor can use real people and their reference media from production storage. The owner has confirmed the saved reference media for Sam Altman, Elon Musk, Jensen Huang and Dario Amodei and authorized their import. Match and preserve existing files, add missing references and retain the evidence for their identities and sources.

Reuse the existing import worktree, which holds the only uncommitted versions of these components, and bring it up to date carefully before implementation. Preserve the older G2 editorial worktree and all saved source files. Use the existing people and media tables; no new tables or columns. Verify the reader using the actual imported bytes, not just database rows. Keep live services and harvesting running.

This plan covers the reader, importer and authorized four-person transfer. The separate Graphics Editor plan remains the authority for video generation, exports and the shared Chatter interface. On November 4 the owner explicitly requested production deployment; the normal staged route applies.

## Context and scope

Authoritative Graphics plan: `/Users/fuchitalee/development/collect-chinese-workers-worktrees/cast-speed-20261026/docs/plans/2026-11-03-043540-feat-cast-still-supply-batch-plan.md`, GE-U1B and GE-U2. This plan is the implementation detail for those units, not a replacement for that plan. User confirmed all saved media for Sam Altman, Elon Musk, Jensen Huang and Dario Amodei on November 4 and directed upload attached to their existing person records. Do not invent a separate rights or reuse gate; preserve source and recorded rights facts without inventing a rights finding.

## Implementation units

1. **Preserve and refresh workspace.** Inspect `git status`, peer claims and current origin/main; inventory and hash all eight untracked importer, mapping, reader and test files before updating. Reuse this worktree; merge or otherwise integrate current main only after confirming no untracked collision, preserving all files. Do not delete or clean either this worktree or `.worktrees/feat/g2-editorial`; reassess cleanup only after work is safely committed and the user-selected delivery endpoint is complete.
2. **Reconcile references.** Read the four original `reference-pack.json` files under `.worktrees/feat/g2-editorial/.local/g2-cast-batch-02-20261022/{altman,musk,amodei}` and `.local/g2-cast-final-four-20261022/huang`. Enumerate source photos, clips and prepared reference images with paths, SHA-256, identity, source and parent lineage; compare each with existing `people_media` and `staff_media_objects`. Distinguish originals and derived inputs from generated output. Detect duplicates and preserve existing attribution. Confirm all scoped bytes exist and decode. Jensen and Dario already have attachments; the prior 6/14 counts were inflated by a duplicate-name join.
3. **Importer.** Update `core/management/commands/ingest_g2_cast_assets.py`, `core/staff_assets/g2_cast_ingest.py` and tests to encode the owner's actual confirmation for these people and exact files in existing evidence fields. Preserve source-verification, suitability and reuse facts accurately; do not fabricate permission. Make preview detect existing-object and attribution conflicts before writing; document and test per-item transactions, partial failure, retry and object reconciliation. Validate destination identity, hashes, bytes and safe no-overwrite behavior. Keep application transfers out of the live web and workers; use a bounded local or isolated one-off execution path with proper credentials and durable receipts.
4. **Reader.** Update `core/staff_assets/graphics_references.py` and tests to retrieve real bytes from production storage with matching identity, original source and lineage. Honor the owner's confirmed inputs and use decision without imposing extra approval, rights, reuse or suitability requirements. Return recorded evidence and meaningful errors for missing or invalid data. Do not falsely mark unknown source rights as cleared.
5. **Verify and transfer.** Run targeted importer and reader tests through the permanent shared PostgreSQL wrapper. Include owner-confirmed pending names, duplicate and different attribution, missing/corrupt content, wrong destination, partial failure and rerun, real video, reference selection and owner-selected use. Freeze the exact four-person manifest and run a full preview, then execute the already authorized production media transfer. Independently read database associations and storage bytes back, compare SHA-256 and run the reader end to end for representative images. Report created, reused, excluded and failed entries separately and preserve receipts. No schema changes or provider-generation calls.

## Delivery and exit

The owner-confirmed transfer is complete: 12 new Altman/Musk references and 10 existing Huang/Amodei references were read back by hash and by the local reader. Production deployment was explicitly requested after that transfer. Record outcomes in the existing Graphics plan. Worktree closure is not authorized by this plan and must never remove uncommitted files or saved reference packs.
