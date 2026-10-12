---
status: ready
priority: p2
issue_id: "002"
tags: [g5, general-page, django, ui]
dependencies: []
---

# Connect the General page locally

## Problem Statement

The accepted General prototype has sample lower feeds and no permanent Post pages or left navigation.

## Findings

The owner chose ce-work option 1: independent lower feeds, Post detail pages and navigation, implemented and verified locally. G2 owns OriginalContent publication and retention; that part stays a dependency. G5 was fast-forwarded from f4159057 to accepted origin/main dcbedf22, preserving its earlier plan/glossary/review edits.

## Proposed Solutions

Use the thin Django readers and saved commentary already selected in the [canonical plan](../docs/plans/2026-10-02-060108-feat-g5-general-page-plan.md). No new generator or pipeline is needed.

## Recommended Action

Execute inline in the existing G5 worktree under the supplied AGENTS.md sequential-work rule. Local verification only; no commits, pushes, staging or production delivery. No external implementation engine configured. Progress belongs here, not in the plan body.

## Acceptance Criteria

- [x] U1: shared classified-Post projection and existing-route characterization.
- [x] U2: Calendar/Free stuff lifecycle ordering and honest dates.
- [x] U3: newest fetched Jobs and source-backed personnel announcements.
- [x] U4 Post portion: permanent URLs, saved revisions, sources, media, metadata.
- [x] U5: accepted shell plus collapsible navigation, login and synchronized settings.
- [x] U6: real cards, continuation, race-safe refresh, locale and audience behavior.
- [x] U7 local evidence/reference portion: integrated browser/regression checks, advisory local measurements and reader reference.
- [x] Local preview data: replace the four synthetic examples with an isolated copy of existing collected Posts and verify all four feeds in the browser.
- [x] R17/G5-R23: independent weights, temporary Closed notice, preference recovery and browser regression proof.
- [x] U8/G5-R24: real published Chatter/Pulse through shared readers, current-main sync, fresh isolated snapshot, complete bodies/citations and desktop/mobile browser proof.
- [ ] U7 release verification: exact committed candidate/performance gate, representative temporal-feed population and reconciliation of the remaining geography-seed failure. These are not passed or waived; current main corrected the earlier Account UUID fixture failure.
- [ ] Full-plan follow-up: published-history retention, the planned `/content/` adapter and G4 Agent presentation. The shared Chatter/Pulse reader integration is complete locally.

## Work Log

### 2026-10-08T15:08:37+09:00 — Start

- Source oracle opened in isolated headless browser session pw-g5-general at :58417, 1280×577 anonymous English, DeepSeek/context. Captured the accepted colors, top/bottom grid and controls before edits.
- PostgreSQL 17.9 is available locally; use a uniquely named disposable database, never production or another session's database.
- Created a private G5 virtual environment from the existing frozen lock. Initial locked sync reported stale project/lock metadata; frozen sync installed existing pinned versions without changing the lock.
- Pre-work inventory and glossary preservation recorded under .context/g5-integration-20261008/. Only earlier G5 documentation was dirty.

### 2026-10-08T15:26:00+09:00 — Reader boundary

- U1 four tests failed on the absent reader, then passed through real PostgreSQL. U2 lifecycle tests failed on absent timing/order; U3 Jobs/people tests failed on absent fact projection/age.
- All 18 reader/timing/jobs/people tests now pass (zero skips/errors). The existing database rejects naive datetime facts; adjusted that fixture to missing precision instead of bypassing its constraint. Reviewed supersession fixtures now satisfy the actual same-person/reviewer trigger.
- Official-company branch at dcbedf22 with active company-only edits; its plan explicitly preserves people extraction. No edits there.
- Three ce-simplify-code lenses run inline under supplied AGENTS.md mapping. Reuse: existing commentary/lifecycle helpers are retained. Quality: expanded the nested target choice. Efficiency: page Jobs/people in PostgreSQL and omit unused temporal raw payloads. No configured type checker found; Ruff and scoped PostgreSQL verification follow.

### 2026-10-08T16:22:55+09:00 — Local implementation and verification

- Local preview: http://100.102.74.50:58418/general/?lang=en and Post example http://100.102.74.50:58418/posts/8802/?lang=en. Uses four synthetic records in an isolated PostgreSQL database; no production records or provider requests. The owned server was restarted after final Python changes. Accepted :58417 and :58011 remain intact.
- Product identity: `worktree-sha256:04f9e92313b1a051ae4f8bd4a78cc235aace9bb96a392527e08a2fda939f3161`, based on `dcbedf22`. Hash includes relevant base readers/models/settings, assets, compiled locales and dependency files; it is not a release SHA.
- 83 PostgreSQL tests passed together, plus one real-browser authenticated logout/preference-isolation test: 84 distinct passing tests, zero required skips/errors. Includes all 41 new G5 tests and existing synthesis/intelligence/editorial tests. Receipts: `.context/g5-integration-20261008/integration-final.log` and `auth-nav.log`.
- General's 48 normalized real-browser obligations pass, zero failed/skipped/errored/missing/unknown. Six outer panel rectangles match Human/Agent at 1440/1280/900/390px in both navigation states; screenshots and exact rectangles in `.context/g5-integration-20261008/browser/`. Authenticated logout, no-JS item links, mobile keyboard dismissal, reload persistence, continuation and delayed-response races exercise real routes.
- One visual repair: the shared sprite initially created a blank 155px header gap; red browser assertion caught it, and the existing hidden-sprite rule fixed it. No visual-oracle edits. A restored-page timer defect and empty-username URL credential leak were each reproduced by a failing test before a scoped fix; final relevant tests pass.
- Wider affected gate: 264 passed, two failures in unchanged geography tests. Both reproduced against a clean archive of `dcbedf22` with the same environment, independently of the G5 source: missing seeded country rows and a legacy non-UUID account fixture. The gate remains failed; neither failure is labeled a pass. Receipts: `affected-gate.log` and `baseline-regression.log`.
- Scoped Ruff, JavaScript syntax checks and whitespace checks pass. Repository-wide Ruff reports pre-existing broad lint debt; no unrelated lint cleanup. Three simplification lenses removed duplicate initial JSON payload and no-op test setup, retained existing helpers and bounded SQL paging.
- Advisory local measurement with four fixtures: General warm median 36.21 ms / 39 queries / 38,679 response bytes; individual feed requests 11–19 ms / 10–11 queries; Post detail 20.23 ms / 13 queries. Browser has 398 DOM elements and no horizontal overflow at 1280/390px. This is unsealed local evidence, not representative production or release performance proof. Receipt: `local-performance.json`.
- Added maintained [reader/URL reference](../docs/reference/general-page.md). G2 OriginalContent publication/retention and G4 Agent transport are explicitly unavailable in this independent slice. Pro's eventual General entry remains a release integration task; its current template has no Reading control.
- Completed ce-code-review lenses sequentially in the main thread per supplied AGENTS.md; no independent reviewer/model claim. Final [review receipt](../docs/reviews/2026-10-08-162910-g5-local-implementation-review.json) records no unresolved implementation finding and a not-ready-for-full-release verdict. The ten review lenses were inline; no external review took place. No commit, push, staging, deployment or owner GUI action.

### 2026-10-08T16:59:49+09:00 — Populate the local review preview

- Owner reported empty Calendar, Free stuff, Jobs and Who’s moving. Actual browser inspection confirmed the local server still used only the four synthetic Qwen records; Closed weights therefore showed four empty panels. The missing real-data connection was a G5 preview omission, not a dependency on G2’s Chatter/Pulse work.
- Created the dedicated `pw_g5_collected_20261008` database on the existing local PostgreSQL 18 cluster, port 55436, using the retained `pw_benchmark_production_rehearsal_20261008` snapshot as a template. Verified zero source connections before copying; no connections were terminated. Copy took 53.54 seconds. The source database was not edited. The copy contains 304,184 Posts, with latest saved fetch 2026-10-08 12:46:12 JST; it is a dated snapshot, not an automatically refreshing production connection.
- Restarted only the owned :58418 Django preview against that dedicated copy. Review: http://100.102.74.50:58418/general/?lang=en&weights=open&audience=human . The original four-record database remains available for earlier fixture evidence. Accepted :58417/:58011 and every other session’s runtime remain unchanged. No application code, styling, production state, collection, generation, provider requests or deployment changed.
- Real Chromium proof passes: all four Open-weight panels initially show 20 genuine Post IDs; More produces 40 Calendar, 40 Free stuff, 28 Jobs (end of available results) and 40 Who’s moving cards, without duplicates. The first card in each panel opens its own permanent Post page with HTTP 200 and the matching canonical URL. EN/JA/ZH-CN each retain 20 cards per panel. Six Human/Agent panel rectangles remain identical at 1280px and 390px, with no horizontal overflow or JavaScript exceptions. Inspected the actual desktop screenshot.
- Closed weights has zero matching eligible cards in this snapshot; that remains an honest empty state. Of the first 80 Open-weight cards, only 10 have saved normalized commentary (Calendar 1, Free stuff 3, Jobs 2, Who’s moving 4); the other 70 use the existing labeled source/literal-translation fallback. Many Calendar rows lack precise dates. No commentary, dates or closed-weight records were invented. The owner’s conditional source-hiding compliance question is still undecided; this correction does not change the existing source-text exposure policy.
- Saved source identity/counts and real browser evidence in `.context/g5-integration-20261008/collected-data/{data-source.json,browser-verification.json,general-real-desktop.png,general-real-mobile.png}`. The first verification attempt assumed a full second page for every panel; Jobs correctly had only eight remaining items, so the read-only verification was corrected to assert the actual response size and terminal cursor. This was an evidence-script assumption, not an application defect.
- The earlier 84 scoped tests and 48 fixture-based obligations still cover the unchanged implementation; the additional real-data browser receipt covers this new preview database. Neither constitutes an exact committed release candidate or production performance gate. Full-plan G2 integration and the existing release checks remain open.

### 2026-10-08T17:32:02+09:00 — Independent weight controls and Closed notice

- Owner requires Open and Closed to be independent selections, with Closed temporarily showing “Coming Soon!” and deselecting after dismissal. Reproduced the old radio behavior in the actual anonymous :58418 browser: clicking Closed changed the URL/filter, removed Open and cleared all 20 Jobs cards, without a popup. Saved route/locale/viewport/source identity and screenshot in `.context/g5-weights-20261008/before.json` and `before-closed.png`.
- Added a shared header/sidebar weights partial, pressed-state semantics and native dialog with localized EN/ZH-CN/JA copy. Open toggles independently; Closed can appear selected alongside Open during the notice, then clears on OK/Escape while restoring focus. Selecting Closed issues no feed request and retains the prior card IDs, geometry, selection and URL. Open-off returns no brands rather than accidentally returning the full inventory.
- General stores its weight selection under the existing account-scoped `:general` preference key, alongside audience/navigation; Pro's exclusive lens is preserved. Old Closed/both URLs and old saved Closed preferences recover to Open with a one-time notice. No-JavaScript links provide the same notice and preserve the Open/none choice. The populated snapshot and accepted :58417/:58011 prototypes are unchanged; only the owned :58418 process was restarted.
- The new real-route browser regression failed before the product fix, then passed with all 11 view tests: 12 focused tests, zero required skips/errors. The full affected gate then ran 272 tests: 270 pass and the same two previously reproduced base geography tests fail (missing seeded countries; legacy non-UUID account fixture). Required PostgreSQL status: 110 executed, zero skipped/errors. The broader gate remains failed, not waived; no unrelated fix was introduced.
- General's revised control model has 49 normalized obligations and a clean assessment: 49 passed, zero failed/skipped/errored/missing/unknown. It includes Open off/on request reversal and an explicit Closed-unavailable invariant. Product identity: `worktree-sha256:336ae739d1264c8eb6e4d4375a6e1f8320dd71aa8e6ba7ac68946c36aead48c5`; model digest `3bce122f0aaa4d88cb2b5ffe7f0d8fdade6fe95f8355b53855474c2ad3e5f53a`. This supersedes the earlier local implementation identity for the changed controls.
- Actual populated-preview checks pass at 1280px/390px in Human and Agent modes: all 80 initial card IDs and six panel rectangles retained, zero Closed feed requests, no horizontal overflow or JavaScript exceptions. Mobile sidebar Enter/Escape/focus return, stale URL/preferences recovery and no-JavaScript dismissal pass. Native modal Tab can focus browser chrome; the browser check verifies it cannot focus background page controls. Inspected the popup screenshot. Evidence: `.context/g5-weights-20261008/live-browser.json` and four `popup-*.png` screenshots.
- Scoped Ruff, JavaScript syntax, declaration validation/prescription and whitespace checks pass. Updated G5-R23, R17/AE7/U5 and the current reader reference. No commit, push, deployment, paid work, source-hiding policy change or other-session mutation. Exact committed candidate/performance and broader G2 integration remain release work, outside this local UI correction.

### 2026-10-08T20:19:34+09:00 — Weight notice copy and position

- Owner requested the literal message “Open Weights Coming Soon!” and a window nearer the toggle. Updated English plus Chinese/Japanese translations; retained the existing Closed trigger and all selection/feed behavior. Recorded the refinement in G5-R23 and R17/AE7/U5.
- The dialog now sits 8px below its invoking header/sidebar toggle, or above when needed, with viewport clamping. Resize and scroll update the position. When responsive navigation hides the invoking sidebar toggle, the still-open notice follows the visible header equivalent. Without JavaScript, the existing centered notice remains the fallback.
- Real-route regression first failed on the old centered position (299px gap in the deterministic fixture), then passed for all three locales at 1280px/390px in both control locations. An additional resize case exposed closed native details retaining layout rectangles while hidden; the regression failed before checking the details-open state and passed after the correction. Initial/follow-up red receipts are `red.log` and `resize-red.log`; focused green is `resize-fixed.log`.
- Final product identity: `worktree-sha256:93425f3caec77df1ee7fe44c4953e12a338185a1c6418f1b572cd23e810bfbe3`. The final affected run reports 270 passed/two unchanged base geography failures; 110 required PostgreSQL tests executed, zero skipped/errors. General's 49 declared obligations are clean, zero failed/skipped/errored/missing/unknown. The broader gate remains failed and unwaived; no unrelated changes were made. Evidence: `.context/g5-weight-notice-position-20261008/verified-gate.log` and copied General assessment/evidence JSON.
- Populated :58418 preview passes all four header/sidebar × desktop/mobile cases with an 8px gap and all 80 card IDs retained; both resize directions pass with no JavaScript exceptions. Actual screenshots inspected; `live-browser.json` and four screenshots are saved beside the test receipts. JavaScript syntax, scoped Ruff, whitespace and Ollija checks pass. Existing database, layout, Pro, accepted prototypes and other owners remain unchanged. Local preview only; no Git delivery, deployment or provider work.


## October 9 — U8 published Chatter/Pulse

- Complete locally: current-main sync, isolated snapshot refresh, shared published readers,
  complete content/citations, regression and browser proof (G5-R24).
- Native inline execution; local review endpoint, no shipping tail. Preserve all
  earlier G5 edits. Before-main files/patch and stash retained under
  `.context/g5-original-content-20261009/` and local Git stash.
- Browser baseline reproduced both placeholders at :58418; 1280×900 top panels
  are 430px tall. Current main fast-forwarded to `00d73117`; WIP restored cleanly.

- Shared-reader integration and browser regression are implemented. Initial four
  PostgreSQL route tests failed on absent rendered publications, then passed.
  Access-off, unpublished, locale fallback, long body and seven non-X citations
  are covered through the real General route. Desktop/mobile browser checks
  verify saved-edition navigation, sources and six unchanged panel rectangles.
- Current source `9884c875aba3a4fedf78dfc5557cd304f2a45220aff8ae933f5e368281c01338`:
  affected gate 279 passed / one existing Japanese geography-seed failure,
  59 subtests passed, 115 required PostgreSQL tests executed / zero skipped/errors;
  all 49 General obligations passed with zero missing/unknown. Current main fixed
  the earlier Account UUID fixture failure. Scoped Ruff/JS/whitespace pass.
- Reuse/quality/efficiency and access review ran inline; no separate or external
  reviewer claim. No additional simplification needed. Fresh real snapshot and
  final live-content parity completed below.

- 2026-10-09T06:18:13+09:00: Consistent read-only production snapshot download continues; process is actively copying shared OriginalContent call records. No production settings/data are changed. The target is the new `pw_g5_collected_20261009` on the existing private PG18 cluster; prior G5/source databases remain untouched. Final live parity script is prepared and awaits restore.

- 2026-10-09T06:59:27+09:00: Fresh managed export created at 06:37 JST restored successfully to the dedicated `pw_g5_collected_20261009` database on local PostgreSQL 18 port 55436, through migration 0079. It contains 306,938 Posts (latest fetch 06:33:50 JST), two approved Chatter editions and 17 approved Pulse editions. The slower direct dump was deliberately canceled only after the managed export restored; its nonzero exit is an intentional supersession, not a restore failure. No production rows, schema, runtime settings or scheduled collection were changed, and no generation was run.
- While the fresh export prepared, the earlier G5-only snapshot was upgraded through 0079 and reconciled with G2's existing backfill command: 63 assessments, 49 calls, 18 editions, zero exceptions. Its source rehearsal database was preserved. Browser verification passed on that intermediate copy; the preview now uses the newer restored snapshot instead.
- The owned :58418 preview is running on current-main `00d73117` plus the preserved G5 changes, with shared OriginalContent reads enabled and generation disabled. Real browser verification passed for all six desktop/mobile × EN/ZH-CN/JA views: exact headline/byline/full body, ordered source count/URLs, saved-edition links, all four populated lower feeds, identical Human/Agent outer rectangles, no overflow and no JavaScript exceptions. Across those views, 96 displayed source links matched the shared-reader output. Desktop and mobile screenshots were visually inspected.
- Chatter shows the shared featured edition plus prior distinct stories in a disclosure; Pulse shows six current editions with archive access. Every displayed edition includes its entire body and all citation URLs in a Sources disclosure. English fallback is disclosed; global editorial selection remains independent of lower-feed weights. G4's Agent presentation remains unavailable under the existing contract.
- Final receipts and screenshots: `.context/g5-original-content-20261009/{render-export-receipt.json,data-source.json,shared-readers.json,live-browser.json,live-en-1280.png,live-mobile-top.png,local-review.json}`. Earlier code-test and 49-obligation evidence remains applicable to the unchanged product identity above. The remaining geography-seed failure is recorded, not waived. Local review only; no commit, push, deployment or owner GUI action.
