---
artifact_contract: "ce-handoff/v1"
created_at: "2026-08-11T08:02:49Z"
title: "Harvester near-real-time pipeline execution handoff"
summary: "U9 through U13 are committed and verified; resume at U14 in the clean isolated fuchitalee worktree, preserving the live-operations authorization boundary."
keywords: ["harvester", "twitterapi", "latency", "enrichment", "pushin-weight-v2", "fuchitalee"]
cwd: "/Users/fuchitalee/development/pushin-weight-v2/.worktrees/harvester-near-real-time"
resume_focus: "Continue the finalized harvester plan at U14, then complete offline U15 and U7; stop for explicit authority before U8, U16, or U17 live/destructive operations."
repository: "pushin-weight-v2"
repo_root_sha: "aff2eb3769a99795697f11c9cadeae825672b5d9"
branch: "fix/harvester-near-real-time"
head: "41aa987c044168208b697ee8366bd5ec254845b3"
worktree_path: "/Users/fuchitalee/development/pushin-weight-v2/.worktrees/harvester-near-real-time"
---

# Objective and latest user intent

Reduce the roughly one-hour delay between an X post and its appearance in the app while preserving recall, attribution, translation, classification, safety flags, and auditable evidence. The canonical implementation plan is already finalized. The user asked to execute it, requested a strong regression net, and is now closing the originating laptop; continue from this document in a new session on `fuchitalee`.

# Resume location and repository state

- SSH host: `fuchitalee`.
- Use only `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/harvester-near-real-time`.
- Branch: `fix/harvester-near-real-time`.
- Captured HEAD: `41aa987c044168208b697ee8366bd5ec254845b3`.
- At capture, this isolated worktree was clean and was six commits ahead of `origin/main` with no remote divergence.
- The primary checkout at `/Users/fuchitalee/development/pushin-weight-v2` is dirty with unrelated user work, including homepage/feed files and untracked research/handoff artifacts. Preserve it and do not use it for this plan.
- No commit was pushed and no PR was opened in this session.
- The U14 helper agent was interrupted before it wrote any files. There is no U14 diff to recover and no agent process should be assumed live.

# Authoritative references

- `docs/plans/2026-08-01-002-harvester-best-practices-followup.md` is the execution authority. U13 is at lines 435-474, U14 at 476-508, U15 at 510-540, U7 at 542-577, U16 at 579-606, and U17 begins at 608.
- Full plan SHA-256 at capture: `a72e9597361fdb996b0bb0d34fed1de06f52dfcd54c03f1314fcc40d890b4086`.
- The protected verbatim 14-item review artifact expected SHA-256 is `5da0b934b25e4c74cfff8f96bc52da09c49730b370fc13bef98d75f0cfad0d9c`. Reverify it before and after future plan-adjacent work.
- Read root `AGENTS.md`, `CONCEPTS.md`, `.claude/skills/avoiding-recurring-mistakes/SKILL.md`, and `.claude/skills/working-with-harvester/SKILL.md` before implementation. The prior session used the Compound Engineering `ce-work` workflow.
- Local PostgreSQL test URL: `postgresql://fuchitalee@localhost:5432/pushinweight_u9`.
- Python environment: `/Users/fuchitalee/development/pushin-weight-v2/.venv`.

# Completed units and commits

The finalized plan is commit `d7ef46a`. The following implementation units are complete and committed in order:

- U9: `f8eb0bc feat(harvester): add bounded state and single-flight`
- U10: `42e8c0f feat(harvester): prioritize fresh tips and preserve backlog`
- U11: `6ed131a feat(harvester): reconcile curated list membership`
- U12: `17af1e0 feat(harvester): route Call A by current author role`
- U13: `41aa987 feat(harvester): make enrichment state truthful`

U9-U12 established the PostgreSQL state primitives, one-writer advisory lock, truthful capped pagination and residual backlog ownership, seven-call tip-first order, current curated-list reconciliation, and Call A official-versus-staff routing. Official accounts bypass relevance and retain self-attribution; staff accounts alone receive relevance filtering.

U13 added:

- Truthful `n_inserted`, `n_updated`, and `n_persist_failed` propagation through production summaries and quote/backlog callers.
- Durable `PostEnrichmentState` creation in the same transaction as accepted-post persistence.
- Oldest-first PostgreSQL enrichment claims capped at 20 per cycle, eight attempts, 24-hour max age, lease expiry/recovery, and shared-deadline deferral.
- Post-fetch execution immediately after the seven live tips and before list reconciliation/backlog work.
- Typed missing-translator/classifier degradation only when durable work exists.
- Strict Django persistence for the four seeded `UnsanctionedFlagKey` values, successful-empty deletion, malformed/unknown preservation, mixed-known persistence, and bounded redacted dead letters in `monitor/unsanctioned_flags.py`.
- Additive pending/failed/succeeded feed state through `monitor/views.py`, `monitor/static/pw-feed.js`, and `monitor/templates/monitor/_feed_initial_v22.html`. Pending/failed rows remain feed-visible with a localized accessible signal; succeeded/legacy rows remain visually unchanged.
- The August 10 translation invariants were preserved; the two translator regression files were not edited.

Key U13 seams are `monitor/cycle.py:121` (claim batch), `monitor/cycle.py:126` (claim helper), `monitor/cycle.py:1612` (durable post-fetch), `monitor/cycle.py:2246` (cycle entry), `monitor/views.py:620` (feed status collapse), and `monitor/views.py:789` (bulk feed enrichment).

# Verification evidence

- Affected cursor/call-routing suite: `73 passed`; required PostgreSQL `executed=66 skipped=0 errors=0`.
- U13 durable queue: `5 passed`; required PostgreSQL `executed=5 skipped=0 errors=0`.
- Real PostgreSQL/Playwright homepage suite across desktop/mobile and all locales: `4 passed`; required PostgreSQL `executed=4 skipped=0 errors=0`.
- Additive feed view tests: `4 passed`; JS formatter: `27 passed, 0 failed`.
- August 10 translator preservation: `43 passed`.
- Broad U9-U13 regression cohort, with three known unrelated baseline assertions explicitly deselected: `298 passed, 3 deselected`; required PostgreSQL `executed=113 skipped=0 errors=0`.
- `manage.py makemigrations --check --dry-run`: no changes detected.
- `manage.py check`: no issues.
- Changed Python modules compiled successfully and `git diff --check` was clean before the U13 commit.

Three pre-existing `tests/test_views.py` assertions remain red when that entire file is run: `TestFeedViewIntegration::test_feed_requires_login`, `TestSerializeFeedRow::test_includes_classifications`, and `TestSerializeFeedRow::test_text_untranslated_falls_back_to_original`. Their asserted lines and behaviors were not changed by U13. Do not silently rewrite them as part of latency work; either fix them in a separately justified scope or continue to name/deselect them when reporting this branch's regression cohort.

# Remaining work

## U14 - next natural continuation

U14 has not started. Implement the latency and canonical summary schema defined at plan lines 476-508:

- Server-owned clocks only: cycle start, request start, each page receipt, accepted-post commit, and post-fetch completion.
- Preserve the actual page-receipt/commit pair across pagination and duplicates; never substitute X `created_at` or `Post.fetched_at`.
- Separate planned metadata from exactly one executed live-call result, tag replays, and preserve real filter counters.
- Add deterministic, structurally allowlisted, redacted `HARVEST_SUMMARY` serialization with schema/service/deploy/run context and hash.
- Add `monitor/harvest_summary.py`; update `monitor/cycle.py`, `scripts/harvest_cost/emit.py`, and the tests named by U14.
- Keep `/feed/` and visible-DOM timings in the PostgreSQL/Playwright cohort harness rather than claiming a browser clock in server code.

Start with characterization/red tests in `tests/test_harvest_latency_summary.py`, `tests/test_cycle_anomaly_metrics.py`, `tests/test_cycle_cost_emit.py`, and `tests/test_harvest_cost_summary_regression_net.py`. The interrupted helper agent produced no red evidence and no files.

## After U14

1. U15: implement offline, fail-closed Render log synchronization and CLI fixtures. Its live smoke must be read-only and must verify account/service scope without ever printing a token.
2. U7: add the end-to-end production-call-chain deletion net through `run_cycle`, Celery/backfill lock boundaries, `CycleRunner`, PostgreSQL, browser, and static-secret layers.
3. Re-run the full PostgreSQL, translator, browser, cost, plan-hash, and static-secret gates before any live rollout.

# Live and destructive authorization boundary

No live Render service, production database, cron, credential, deployment, remote ref, or history was changed in this session.

U8, U16, and U17 require actions beyond ordinary repo implementation: pausing/resuming Render, removing service-local environment delivery, rotating and invalidating a production PostgreSQL credential, deploying, observing two scheduled cycles, and rewriting hosted Git/history/remnants. Do not perform those implicitly. First obtain explicit current-user authority, exact owner/maintenance window, and protected-ref/host coordination as required by the plan.

The read-only current-tree inventory found embedded connection URLs in multiple documentation/operations artifacts and service-local `DATABASE_URL` entries for both web and harvest in `render.yaml`, alongside `pushinweight-secrets`. Never quote or log those values. The user's review item 13 requires checking every runtime/script/document consumer before deletion. Group-only delivery must be proved while paused before credential invalidation; history scrub comes only after invalidation and explicit rewrite authority.

# Continuity warnings

- Work only in the isolated worktree. The primary checkout's overlapping homepage/feed changes belong to the user.
- Preserve the plan and its verbatim 14-item artifact byte-for-byte.
- Do not reverse the August 10 translator fix.
- Do not treat pending or failed enrichment as classified clean.
- Do not run legacy SQLite store tests as production proof; required state/flag/lock evidence is PostgreSQL.
- Do not stage, commit, deploy, push, or mutate live state merely because a handoff says work remains. Confirm the current user's intent in the resumed session, as required by `ce-handoff`.
