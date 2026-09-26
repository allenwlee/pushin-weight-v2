---
title: Propagate owner-directed delivery fixes
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ollija-annotate-plan
execution: code
ollija:
  change_id: fix-release-guidance-propagation-2026-09-25-122924
  branch: fix/release-guidance-propagation
  workflow: plan
  delivery_target: on-request
  delivery_selected_by_user: false
---
<!-- BEGIN OLLIJA DELIVERY GUIDE -->
## Ollija Delivery Guide

This block is generated guidance. Do not edit it directly. Correct durable facts in `.ollija/project.yaml` or this template, then rerun `ollija annotate-plan`. Current explicit owner instructions govern this task. Record exceptions below and reflect route changes in metadata; removed requirements must not return through another checklist.

### Resolved locations

- Authoritative host: `fuchitalee`
- Authoritative repository: `/Users/fuchitalee/development/pushin-weight-v2`
- Ollija release worktree area: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees`
- Active worktree: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/release-guidance-propagation`
- Plan: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/release-guidance-propagation/docs/plans/2026-09-25-122924-fix-release-guidance-propagation-plan.md`
- Change: `fix-release-guidance-propagation-2026-09-25-122924`
- Branch: `fix/release-guidance-propagation`
- Staging branch and blueprint: `staging`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/release-guidance-propagation/render-staging.yaml`
- Production branch and blueprint: `main`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/fix/release-guidance-propagation/render.yaml`
- Staging URL: `https://pushinweight-staging-web.onrender.com`
- Production URL: `https://pushinweight-web.onrender.com`

### Placement

This worktree is inside the Ollija release worktree area. Reuse it for the whole change. Do not create a second worktree or plan for this branch.

### Delivery scope

- Workflow: `plan`
- Delivery target: `on-request`
- Owner selection recorded: `false`
- Delivery route: `staged`

Target is not authorized until the owner selects it. Wait for a later explicit release request; do not commit, push, stage, or promote on this guide alone.

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

The owner requested implementation, commit, and push, then on 2026-09-26 explicitly requested
merging all four branches to their repositories' `main`. The current endpoint is verified
remote-main integration and the previously installed local guidance. `on-request` does not
cancel this explicit Git scope. No additional application deployment operation is requested.
Unrelated dirty work stays in its original checkouts. No staging or production acceptance is
applicable to these workflow and assurance-wrapper changes.

# Propagate owner-directed delivery fixes

## Plain-English Summary

Make the release workflow preserve the user's chosen endpoint and exceptions across tools,
resumes, and installations. Update shared instructions, Ollija, the Compound Engineering
fork, and PushinWeight's release guidance. Candidate performance checks must identify the
code actually measured. Ship these changes as pushed branches and refresh local agent tools.
Application production resources, credentials, harvest scheduling, and unrelated work remain
outside this task. Verification uses disposable repositories, focused tests, and bounded
fresh-agent decision exercises.

## Implementation units

- U1: infra canonical agent-execution/Allen Speak sources, guarded idempotent synchronization,
  disposable-home regressions; install the managed dotfile blocks on fuchitalee.
- U2: standalone Ollija route metadata, direct/commit staging rendering, persistent opt-out,
  source/example skill parity, CLI/discovery regressions; reinstall command and managed skill.
- U3: Compound Engineering 3.28.2 fork: endpoint-aware shipping, ready-plan reuse, current
  authorization on resume; mechanical guards and fresh-context decision evidence.
- U4: PushinWeight project instructions, template/hook, scoped runbooks, risk-selected UI
  performance mode and identity checks; correct earlier incident documents and glossary.
- U5: review owned diffs, commit only explicit task files, push each feature branch, verify
  remote SHAs and installed-source parity. No merge, deployment, or unrelated files.

## Regression net

- Ollija: direct production emits no staging mutation; staged default remains; commit staging
  preserves the shared branch; opt-out is byte-identical under discovery/check/hook; missing
  authority or contradictory route fails without writes.
- Infra: managed updates preserve other settings/permissions/frontmatter; repeated sync is
  a no-op; malformed later targets prevent partial updates.
- PushinWeight: old production cannot pass candidate performance; baseline is labelled;
  not-required needs a rationale and still runs product checks; product failure still blocks.
- CE: ready earlier-session plan reuses its path; explicit continuation retains authorization;
  orientation-only stays read-only; selected production endpoint survives child PR defaults.

## Verification and delivery record

Implementation and local installation are complete. Publication uses these feature branches;
the parent verifies each remote ref against its local HEAD after pushing. This plan travels
with the PushinWeight commit, so its own commit ID is supplied by Git rather than embedded.

| Repository | Branch | Implementation commit |
| --- | --- | --- |
| `allenwlee/infra` | `fix/agent-authorization-guidance` | `e8b1a8c` |
| `allenwlee/ollija` | `fix/owner-directed-delivery` | `98fe0e8` |
| `allenwlee/compound-engineering-plugin` | `fix/authorized-delivery-continuation` | `4b3d5341` |
| `allenwlee/pushin-weight-v2` | `fix/release-guidance-propagation` | This plan's commit |

### Verification

- Infra: `python3 -m unittest discover -s utilities/claude-code -p test_sync_agent_guidance.py`
  passed all three tests. Real `sync-agent-guidance.py --write`, then `--check`, reports current.
- Ollija: `.venv/bin/python -m pytest -q` passed all 123 tests; Ruff passed. The suite includes
  real Git checkout-hook opt-out, direct route, exact-commit staging, resume, contradictory
  selection, and existing metadata indentation. No real release is executed by these tests.
- PushinWeight: `python -m pytest -q tests/test_ui_assurance_gate.py
  tests/test_fix_ui_skill_assurance.py tests/ollija` passed all 47 tests. This changes workflow
  and assurance code, not a visible UI surface; browser/product deployment tests are not run.
- Compound Engineering: the required full run completed with 4,214 passed, one skipped,
  and six failures. Four involved changed text/size/catalog contracts; they were corrected
  and the final six-file contract run passed all 184 tests. Two involved unchanged Pi timeout
  and shared test-fixture state; their isolated reruns passed (one and two tests). The full
  suite was not repeated, so this is not a claim that the complete suite is green.
- Plugin `bun run release:validate` and `bun run plugin:validate` passed. `git diff --check`
  passed in each repository before commit.
- Fresh Claude and Codex CLI decisions passed production completion, PR-only restraint,
  and currently authorized handoff continuation (two hosts per case, 120-second bounds).
- Ready-plan baseline using upstream `020c5e10`: both hosts chose planning again solely due
  to session age. With the edited skill and a real existing fixture, both read the selected
  plan and chose implementation. An earlier fixture omitted the named file; that invalid
  setup was corrected without changing the expected outcome or weakening the readiness rule.
- A fresh independent Codex reader caught a planning-reference read broadened to the defect
  route during shortening. The route qualifier was restored; the reader's wording concerns
  were clarified while retaining the original blocked-return and verbatim-retry safeguards.
- Decision cells prove routing/restraint only. They do not simulate live merges, deployment,
  paid API calls, or production service behavior. Local detailed logs are in
  `/private/tmp/ce-delivery-*20260925*` and `/private/tmp/ollija-release-*20260925.log` on fuchitalee.

### Installed sources

- Infra canonical sources are under `~/infra/utilities/claude-code/`; the tested sync updated
  only managed blocks in `~/.codex/AGENTS.md`, `~/.claude/CLAUDE.md`, and the Allen Speak skill.
  Source copies also live on the pushed infra branch. Other preexisting infra changes remain.
- Ollija was installed with `uv tool install --force
  /Users/fuchitalee/development/ollija/.worktrees/fix/owner-directed-delivery`; `ollija init`
  refreshed the managed shared skill, whose bytes match the source. The primary checkout's
  preexisting README change is untouched. Use this tested checkout until branch integration.
- Codex: `bun run codex:dev -- local` links the maintained CE checkout's `skills/`.
- Claude: its user CE marketplace now points to that checkout, installed through the CLI.
  Same-version edits required uninstall with `--keep-data` and reinstall; `plugin update`
  alone retained stale bytes. Installed skill bytes were verified after reinstall. Other
  marketplaces and plugins were preserved. No cache file was edited directly.
- Start fresh agent sessions to load all changed guidance. No repo artifacts were created
  on allenwlee, no application deployment occurred, and no production data was changed.

### Remaining integration scope

The initial commit-and-push request finished at the recorded feature branches and local tool
installation. The 2026-09-26 continuation authorizes merging those four branches to remote
`main`. Use ordinary non-forced integration, satisfying actual repository protection and PR
policy. All four remote bases were ancestors of their feature candidates at intake; the CE
fork includes its upstream 3.28.2 baseline update. Verify candidate ancestry in remote-main,
or the equivalent merged tree for repositories requiring squash merges. Retain source checkouts/worktrees while installations point at them
and preserve unrelated local-main commits and dirty files in primary checkouts.
