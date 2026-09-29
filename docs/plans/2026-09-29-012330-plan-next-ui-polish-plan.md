---
title: Feed and Homepage UI Polish - Plan
type: fix
date: 2026-09-29
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ollija-annotate-plan
execution: code
ollija:
  change_id: plan-next-ui-polish-2026-09-29-012330
  branch: plan/next-ui-polish
  workflow: plan
  delivery_target: production
  delivery_selected_by_user: true
  delivery_route: staged
  delivery_route_selected_by_user: false
  staging_transport: branch
---
# Feed and Homepage UI Polish - Plan

## Plain-English Summary

This plan combines the headline, filter, engagement and geography changes with the earlier processing-glyph, language-tag and hover requirements. Readers will see one quiet pending sphere per post, useful localized hover details, specific language codes when known, and less visual clutter.

Earlier processing and hover work is carried forward as behavior to preserve and repair only where a current gap is demonstrated. The newer language-state decision governs: an undetected language uses the sphere while work is pending and the existing unsuccessful glyph otherwise, with wording that distinguishes an actual failure from an unknown language. Historical language repair remains a separately bounded, deferred operation.

The owner invoked LFG on 2026-09-29, authorizing implementation, verification and review of this combined plan, then explicitly selected production. Work uses the existing isolated branch, reconciles current main, and checks the rendered homepage in English, Simplified Chinese and Japanese across initial load and live updates. Delivery verifies the candidate on staging and promotes the same revision to production. The main regression risk is disagreement between initial HTML, feed replacement and commentary polling.

<!-- BEGIN OLLIJA DELIVERY GUIDE -->
## Ollija Delivery Guide

This block is generated guidance. Do not edit it directly. Correct durable facts in `.ollija/project.yaml` or this template, then rerun `ollija annotate-plan`. Current explicit owner instructions govern this task. Record exceptions below and reflect route changes in metadata; removed requirements must not return through another checklist.

### Resolved locations

- Authoritative host: `fuchitalee`
- Authoritative repository: `/Users/fuchitalee/development/pushin-weight-v2`
- Ollija release worktree area: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees`
- Active worktree: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/plan/next-ui-polish`
- Plan: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/plan/next-ui-polish/docs/plans/2026-09-29-012330-plan-next-ui-polish-plan.md`
- Change: `plan-next-ui-polish-2026-09-29-012330`
- Branch: `plan/next-ui-polish`
- Staging branch and blueprint: `staging`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/plan/next-ui-polish/render-staging.yaml`
- Production branch and blueprint: `main`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/plan/next-ui-polish/render.yaml`
- Staging URL: `https://pushinweight-staging-web.onrender.com`
- Production URL: `https://pushinweight-web.onrender.com`

### Placement

This worktree is inside the Ollija release worktree area. Reuse it for the whole change. Do not create a second worktree or plan for this branch.

### Delivery scope

- Workflow: `plan`
- Delivery target: `production`
- Owner selection recorded: `true`
- Delivery route: `staged`

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
    - From `/Users/fuchitalee/development/pushin-weight-v2`, require `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/plan/next-ui-polish` to remain registered, clean, unlocked, and at the verified candidate SHA. If any guard fails, retain it and report the reason.
    - Run `git -C /Users/fuchitalee/development/pushin-weight-v2 worktree remove /Users/fuchitalee/development/pushin-weight-v2/.worktrees/plan/next-ui-polish` without `--force`.
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

The 2026-09-29 LFG request lifts this draft's previous implementation/review hold. The owner's subsequent “deploy to production” instruction authorizes release of PR #48 through production, including ordinary branch promotion and deployment. The staged route remains selected. Historical provider batches, production data repair, and a harvest pause remain outside scope. Preserve the independent quality-sweep and country/Muse branches and their resources. Reuse the recorded verification where the relevant product code and environment assumptions are unchanged; documentation of this delivery selection does not require repeating the product suite.

## Goal Capsule

- **Objective:** Make the public homepage easier to read, with truthful processing states, precise language tags, and complete localized hover details.
- **Means:** Update the existing Django feed projection, server templates, JavaScript renderers and focused styles; preserve the existing static sprite and lookup-label model.
- **Authority:** The combined R1–R16 contract and the owner's 2026-09-29 LFG request. Current owner instructions govern delivery.
- **Completion:** All applicable requirements verified through the real page and update paths, reviewed changes persisted, and the selected delivery endpoint observed.

## Consolidated sources and precedence

The owner requested this consolidation on 2026-09-29. This document is the active implementation plan; the earlier documents retain their historical implementation and delivery records.

| Source | Requirements carried here |
| --- | --- |
| `docs/plans/2026-09-25-023434-feat-feed-processing-glyphs-ja-hover-plan.md` | Selected A stop marker and animated C armillary; truthful queue messages; enlarged hover visuals; Japanese lookup labels and hover copy; X-logo follower wording; cached glyph assets. See R5 and R9–R16. |
| `docs/plans/2026-09-25-041204-feat-feed-processing-indicator-followup-plan.md` | One subdued sphere per post; combined pending-work hover; language detection uses that same sphere; blank pending/context-missing classification labels; precise language codes; deferred historical language-only repair. See R5 and R9–R12 and the deferred repair section. |
| The existing next-UI draft in this file | Headline voices, filter help, country subtitles, Product title, updated language fallback, engagement removal, specific geopolitical hovers, and country-marker typography. R1–R8 retain their IDs and meaning. |

**Product Contract preservation:** R1–R8 retained; earlier requirements consolidated into R9–R16 and the deferred repair section. R5 explicitly supersedes the older globe fallback for undetected feed language tags. The older globe acceptance examples must not be copied into this batch.

The earlier indicator release is documented as deployed at `e327ed7175cde1bfc31d29f317b4bfb4416ebdd0` in `docs/solutions/workflow-issues/2026-09-25-203900-authorized-release-blocked-by-inherited-gates.md`. That is historical delivery evidence, not a fresh browser check. Establish which carried requirements still hold on the selected implementation revision before scheduling fixes. Prior delivery authorization, checks and waivers remain attached to their original release.

## Scope and boundaries

- **Source baseline:** branched from the staged quality candidate `fix/product-quality-sweep` at `1edbc3adaa19b370498ef0fbb026319fc676d397`. Its frozen plan is `docs/plans/2026-09-28-023934-main-plan.md`. Reconcile current main into this worktree, preserving its dashboard additions; never edit the other branch or rewrite its frozen candidate. This branch inherits the quality-sweep changes, which must be disclosed in its delivery diff if they have not yet reached main.
- **Touch later:** public homepage templates, the live feed/headline renderers, localizable UI copy, focused styles, and corresponding route/browser regression tests. Candidate files include `monitor/templates/monitor/home.html`, `monitor/templates/monitor/_feed_initial_v22.html`, `monitor/templates/monitor/_feed_language_tag.html`, `monitor/static/pw-feed.js`, `monitor/static/pw-chart.js`, `monitor/static/home-v20.css`, `monitor/static/pw-processing-glyphs.svg`, `monitor/views.py`, `tests/test_home_v22_browser.py`, `tests/test_home_v22_feed_row_shape.py`, and `tests/test_home_v22_filter_pills.py`.
- **Carried language/lookup paths:** inspect the existing precise-code handling in `x_monitor/translator.py`, the locale catalogs, and the `seed_i18n_labels` command. Reuse existing behavior; repair a demonstrated gap against R12–R13 rather than adding another normalization or lookup system. Label repairs use the existing language-keyed tables and idempotent seeding.
- **Preserve:** account follower counts and their X-logo hover, post-to-X links, non-voice headline content, existing filter mechanics, stored engagement data, translation/classification retry policy, and the separate geography-harvest work. Remove only UI elements and now-unused UI plumbing that the owner named.
- **Deferred:** the historical language-provider batch and the known headline-content issue set aside in the quality batch. This plan changes presentation and existing label lookup gaps, not classifier decisions or retry policy.

## Product Contract

### Summary

Apply R1–R8 and preserve or restore R9–R16 through the existing public homepage and its live updates.

### Problem Frame

Headline voices and engagement counters add clutter, country cues differ by locale, and undetected language uses a misleading generic fallback. The inherited quality candidate also separates language processing from other pending work, violating the combined plan's one-sphere rule.

### Key Decisions

- **One selected armillary and specific hover detail.** (session-settled: user-directed — chosen over a separate spinner per processing job: the owner wants one quiet indicator per post.) Governs R9–R10.
- **Selected stop marker for terminal work.** (session-settled: user-directed — chosen over treating every failed attempt as permanent: queued work must still look pending.) Governs R5 and R10.
- **Latest language fallback wins.** R5 replaces the older globe fallback while preserving the distinction between unknown language and actual failure.

### Requirements

### Headline, filter, engagement and geography changes

- **R1 — Headlines:** Remove `.headline-voices` completely from every headline presentation, including initial HTML and subsequent headline refreshes. Do not leave its label, star, empty state, or space behind. Keep the headline narrative, disclosure, status, and other content.
- **R2 — Filter help:** Remove the visible `?` from the `.filter-help-trigger.pw-inspection-trigger` in the geopolitical filter pill. Preserve a keyboard-accessible, clearly named way to open the explanation using the existing globe glyph.
- **R3 — Country subtitles:** In the geopolitical dropdown's `.dd-subtitle` rows, replace the written country names “China” and “US/U.S.” with their respective country flags in every locale, while retaining an understandable, localized “national stance” label and accessible country name.
- **R4 — Product pill:** Change the English `.filter-pill[data-group="product_labels"]` title from “Products” to “Product”. Keep the filter group key and filtering behavior unchanged; check static and locale-switch rendering for stale plural text.
- **R5 — Language state:** A language code not yet detected gets a spinning sphere only while language detection/translation is genuinely pending or processing. This is the same single sphere governed by R9, placed in the language-tag position and summarizing all pending work under R10. A failed or otherwise non-pending undetected state gets the existing unsuccessful glyph, replacing the older globe fallback. Its hover distinguishes actual failure from undetected language with no queued work; unknown language alone must not be described as permanent failure or imply another automatic attempt. If another process is still pending, the post can show the unsuccessful language glyph and its one pending sphere together. Initial server HTML and live replacement/language cycling must agree.
- **R6 — Engagement clutter:** Remove like, repost/retweet, and reply numbers *and their icons* from every post row, both initial and dynamically inserted. Do not remove the post's X link or the account follower magnitude.
- **R7 — Geography signal detail:** Hovering or keyboard-focusing the `.pw-icon.signal-icon` for a geopolitical class must reveal that post's specific geopolitical subcategory, not just the generic geography family name. Preserve the established inspection popover behavior for other signal families and national stance.
- **R8 — Country marker typography:** Make the adjacent `中` and `美` markers match the flag glyph's visual size and weight. Show these characters only in Simplified Chinese and Japanese chrome. In English chrome show the two-letter ISO country codes `CN` and `US`. Keep the underlying national-stance values and hover explanations unchanged.

### Processing indicators and language tags carried forward

- **R9 — One quiet pending sphere:** A post displays at most one animated C armillary across language detection, translation, analysis/classification and commentary, including jobs queued again after a failed attempt. Use subdued amber/greater transparency so it is less prominent than the original bright yellow. Keep the outer sphere and base fixed while the inner ring completes a full revolution; reduced-motion users get a stationary glyph. When language detection is pending, use its language-tag placement; otherwise use the existing processing-indicator position.
- **R10 — Specific combined hover and failure state:** List every pending job once in a stable, localized order: language detection, translation, analysis, commentary. Use natural wording such as “Translation, analysis and commentary pending” or, when it is the only job, “Language detection pending.” Preserve detail that distinguishes first processing, an attempt queued again, and terminal failure. Use the selected A stop marker for a genuinely failed job with no retry queued; a completed job has no processing marker, and cancellation/expiry alone does not establish permanent failure. R5 separately defines the language-tag fallback. A terminal failure can coexist with the single sphere for other pending jobs.
- **R11 — Blank classification status cells:** Render no visible `classification-state-label` and no empty hover trigger for `pending` or `context_missing`. Preserve their status data and filter behavior; retain the existing failed, stale and historical status explanations.
- **R12 — Precise language codes:** Show a known source language as its lowercase ISO 639-1 two-letter code, including languages previously grouped as `other`; retain existing `zh-Hans`/`zh-Hant` handling. The same code appears in every interface locale. Preserve validated precise codes in the existing translator path, reject malformed codes, and keep named language filters and the residual “other” filter group working. Never display `other` as a post-language tag or guess a code from it. Unresolved rows follow R5 until a verified detection result exists.

### Hover, localization and asset requirements carried forward

- **R13 — Complete Japanese feed hovers:** Under `ja` and `ja-JP`, localize all feed hover headings, state messages, follower wording, role/geography descriptions and date tooltips, including “Audience topic” and “Sentiment.” Include current and visible historical taxonomy values. Audit and repair missing `ja` label rows in the existing `(key, lang)` lookup tables; this needs language rows, not new per-locale columns. Preserve English/Chinese labels and the frozen geography migration seed. Missing Japanese labels use localized unavailable wording and remain observable for repair, rather than exposing an English slug. Proper names, handles, codes and source quotations retain their identities.
- **R14 — Enlarged hover visual:** Every glyph- or flag-bearing feed inspection shows the same visual a few pixels larger inside the hover beside its text. Preserve aspect ratio, tone and the armillary animation/reduced-motion behavior. Existing text-only triggers can show their enlarged text badge; R11's blank statuses have no trigger. Keep hover, keyboard focus, click-to-pin, Escape dismissal and viewport-edge positioning working after initial load and every feed update. Build visuals from trusted glyph/flag content; do not parse source or hover text as HTML.
- **R15 — Follower wording:** The follower hover reads as the count, the actual X logo, and localized “followers,” for example “102k [X logo] followers.” Use the logo asset, not a substitute letter X. R6's engagement removal must preserve this hover and the account follower count.
- **R16 — Cached glyphs:** Serve all new glyph assets through the existing content-hashed static mechanism, with browser caching and immutable cache headers for hashed files. Reuse the same cached assets in feed rows and enlarged hovers. Preserve accessible names even when the visible control is glyph-only.

## Deferred historical language repair

The earlier follow-up includes a bounded, resumable language-only repair for historical `other` rows whose precise language was lost. Preserve that remaining item here: use verified language detection, update only the detected-language metadata, leave translations/classifications/commentary intact, and report attempted, resolved and unresolved rows. An unresolved row continues to use R5's truthful state display.

Before any separate repair run, inspect the existing command, obtain a dry-run count and explicit provider-spend/batch bounds, and preserve its resume and concurrency protections. It remains outside the live 15-minute cron and outside this UI-only implementation/delivery scope. The earlier release specifically deferred the provider batch; combining documents does not authorize that batch or a production pause.

## Language-state finding

`monitor/views.py` treats a missing or `other` language as undetected. It inserts a language-position pending sphere only while the translation stage is `pending` or `processing`; its inspection text already distinguishes `failed` from generic `undetected`. The translation backlog can retry a pending stage but eventually marks it failed after its configured attempt or age limits. The current server template `monitor/templates/monitor/_feed_language_tag.html` and client renderer `monitor/static/pw-feed.js` use the globe for **all** non-pending undetected rows, including failed ones. A generic undetected row with no pending stage does not itself establish that another retry is scheduled. R5 aligns the glyph with the actual persisted stage; it does not alter the retry policy.

## Planning Contract

### Key Technical Decisions

- KTD1. **Reuse the existing worktree and render paths.** Reconcile main into this branch, then keep `_post_to_wire` and `_processing_badges` as the shared state projection consumed by initial HTML and the client. No new endpoint, scheduler, queue or schema is needed. Covers R1–R16.
- KTD2. **Aggregate language and other pending work once.** The inherited `_processing_badges` removes translation from its pending set after adding a language marker, then can add a second metadata marker. Replace that split with one ordered message and one placement, retaining the frozen historical duration notes and terminal badges. Preserve the commentary polling wire shape so updates replace the same projection. Covers R5, R9–R11. This supersedes the inherited quality candidate's separate-language-marker behavior only within this new branch.
- KTD3. **Remove display plumbing, preserve API compatibility.** Delete headline-voices markup, its renderer and dedicated styles, and remove engagement counters from both feed renderers. Keep the existing `top_voices` response and stored engagement fields for other consumers. Change the Product title in the template and `monitor/static/pw-locale-toggle.js`. Covers R1, R4, R6.
- KTD4. **Reuse trusted glyph assets for help and language state.** Use the existing cached globe in the geopolitical help trigger and `icon-failed-stop` for R5's unsuccessful language fallback. Preserve the trigger's accessible name and existing inspection controller. Country subtitles use existing flag assets with localized accessible country names; visible stance markers use one locale-aware helper and a shared size/weight style. Covers R2–R3, R5, R8, R14–R16.
- KTD5. **Keep detailed geography on the existing server projection.** `_feed_signal_inspections` already receives each localized geopolitical subtype and combines brand attribution and national stance. Trace the real hover through `paintSignals` and the shared controller; preserve specific subtype text and remove any generic override demonstrated by the browser. Test both reporting and framework/nationalism, including multiple brand contributors. Covers R7 and R13–R14.
- KTD6. **Repair carried requirements only when a gap is shown.** The branch already contains precise-code normalization, Japanese hover headings, label seeding, enlarged hover visuals, X-logo followers and cached processing assets. Use the existing tests and real rendered behavior to identify remaining gaps. No new language columns or historical provider run. Covers R11–R16.

### Language and pending state projection

| Language | Translation/detection stage | Language position | Other pending work |
| --- | --- | --- | --- |
| Known precise code | Any | Specific code | One metadata sphere if anything is pending |
| Unknown | Pending/processing | Sole sphere; hover includes all pending jobs | Included in the language-position sphere |
| Unknown | Failed | Unsuccessful glyph with failure wording | One metadata sphere if another job is pending |
| Unknown | No pending or failed stage | Unsuccessful glyph with undetected wording | One metadata sphere if another job is pending |
| Historical `other` | Any | Follow the unknown-language rows above | Never invent a code |

### Sequencing and verification direction

Reconcile the branch and capture the baseline before changing product behavior. Add browser/call-chain regression pins for the requested differences, implement U2–U4, then complete U5. Freeze these requirements as the acceptance set; repeat only evidence invalidated by a fix. The local preview and PostgreSQL test database must be disposable and isolated from other sessions.

## Implementation Units

### U1. Establish the integrated baseline and regression fixtures

- **Goal:** Preserve current main and the inherited quality candidate while pinning R1–R16 on the real public route.
- **Files:** `tests/test_home_v22_browser.py`, `tests/test_home_v22_feed_row_shape.py`, `tests/test_home_v22_filter_pills.py`, `tests/test_views.py`, `tests/test_post_synthesis_api.py`, `tests/test_pw_feed_formatter.js`.
- **Approach:** Merge current main into this worktree with ordinary conflict resolution. Create an isolated deterministic PostgreSQL test/preview environment and capture the anonymous homepage before product edits. Reuse fixture helpers and label seeds; do not change the owner's mockup or add broad exceptions to make checks pass.
- **Test scenarios:** Desktop and 390px mobile; English, Japanese and Simplified Chinese; initial load, locale change, feed replacement, language cycling, headline refresh and commentary updates. Record the current duplicate-sphere case and unwanted voices/counters as the before state.
- **Verification:** Required browser setup succeeds without skips; each intended product difference has a meaningful red assertion before its fix. Dependencies: none.

### U2. Simplify headline, filters and engagement display

- **Goal:** Implement R1–R4 and R6 while retaining R15.
- **Files:** `monitor/templates/monitor/home.html`, `monitor/templates/monitor/_feed_initial_v22.html`, `monitor/static/pw-chart.js`, `monitor/static/pw-feed.js`, `monitor/static/pw-locale-toggle.js`, `monitor/static/home-v20.css`, corresponding U1 tests.
- **Approach:** Apply KTD3–KTD4. Preserve the headline narrative, freshness/disclosure controls, account followers, X links and filter request semantics.
- **Test scenarios:** Zero voice/counter/icon matches before and after live replacement; no leftover voice spacing; Product survives locale round trips; help globe opens by pointer and keyboard without toggling the surrounding filter; country subtitle flags have meaningful localized accessible names.
- **Verification:** Real template tests, JavaScript formatter tests and the focused browser flow pass. Dependency: U1.

### U3. Restore one pending sphere and truthful language fallback

- **Goal:** Implement R5 and restore R9–R12 across every update path.
- **Files:** `monitor/views.py`, `monitor/templates/monitor/_feed_language_tag.html`, `monitor/templates/monitor/_feed_initial_v22.html`, `monitor/static/pw-feed.js`, `monitor/static/home-v20.css` only for a demonstrated style gap, `tests/test_views.py`, `tests/test_post_synthesis_api.py`, `tests/test_pw_feed_formatter.js`, `tests/test_home_v22_browser.py`, `tests/test_home_v22_feed_row_shape.py`.
- **Approach:** Apply KTD2 and the language-state table. Keep precise-code normalization and retry scheduling intact. Use persisted stage/attempt evidence for retry detail; do not infer terminal failure from an absent language.
- **Test scenarios:** Language-only pending; all jobs pending; known language plus pending work; retry queued; mixed terminal and pending work; failed detection; unknown with no queued work; cancelled/expired commentary; ready transition; commentary poll and language-cycle replacement. Assert one sphere, stable ordered job names, retained duration notes and no pending/context-missing label.
- **Verification:** Serializer → real view/template and synthesis API → browser paths agree for all three locales. Existing precise-language and filter regressions pass. Dependency: U1.

### U4. Complete geography and hover presentation

- **Goal:** Implement R7–R8 and verify/repair R13–R16.
- **Files:** `monitor/views.py`, `monitor/static/pw-feed.js`, `monitor/static/home-v20.css`, existing label seed/catalog paths only for demonstrated missing values, `tests/test_home_v22_browser.py`, `tests/test_views.py`, `tests/test_pw_feed_formatter.js`, existing geography/label tests.
- **Approach:** Apply KTD5–KTD6. Use CN/US in English and 中/美 in Japanese/Chinese with measured matching glyph size/weight. Keep subtype details and brand contributors in the shared inspection text.
- **Test scenarios:** Reporting and framework/nationalism show distinct localized subtypes; multi-brand rows retain contributors; markers switch by interface locale; Japanese headings/known historical labels remain Japanese; unknown labels are localized; enlarged hover glyphs, follower X logo, focus/Escape/pinning and reduced motion work after replacement.
- **Verification:** Browser text and computed geometry prove the visible requirements; seed repairs, if needed, are idempotent; hashed asset serving retains immutable caching. Dependency: U1.

### U5. Verify, review and deliver the exact revision

- **Goal:** Prove the combined behavior and reach the owner's selected endpoint.
- **Files:** Affected regression files; `tests/fixtures/ui_assurance/declaration.json` and its existing evidence inputs; `docs/reference/feed-ui-contract.md` at its current resolved location if the display contract needs updating.
- **Approach:** Run the focused tests and affected assurance profile, simplify/review the task diff, fix eligible findings, seal the product-source revision, and run candidate assurance with performance evidence from that candidate. Use an isolated local fixture or the owned staging deployment for performance measurement; another production revision is only a baseline. Reuse valid evidence for subsequent documentation-only commits.
- **Test scenarios:** Exact source identity, zero required skips/errors, all relevant stateful obligations, cache headers, anonymous access, desktop/mobile locale flows and unchanged dashboard/worker boundaries. Inspect the selected deployed revision and visible requirements before reporting delivery.
- **Verification:** Commands and required results below; no paid provider batch, production data repair or harvest pause. Dependencies: U2–U4.

## Verification Contract

- Establish the carried-forward baseline before changing it: inspect the selected revision for R9–R16 and distinguish already-satisfied requirements from demonstrated gaps. Reuse relevant existing regression evidence with its revision and scope recorded; historical deployment evidence alone is not proof of current rendered behavior.
- Start with the real public homepage URL, rendered through the view/template and in a browser. Pin the reported state before changing product UI; cover initial HTML, feed replacement, headline refresh, and any locale switch that changes these labels.
- Check English, Simplified Chinese, and Japanese at desktop and mobile widths. Assert the removed elements have zero visible matches; confirm flag accessibility, keyboard/focus inspection, precise geography subcategory text, and unchanged X links and follower counts.
- Exercise language-state fixtures for pending, processing, failed, and non-pending undetected, including unresolved historical `other` rows. Prove sphere versus unsuccessful glyph in both server and client render paths; do not infer a retry or terminal failure from missing language data alone.
- **Processing regression net:** in `tests/test_home_v22_browser.py` and `tests/test_home_v22_feed_row_shape.py`, cover language-only pending, several pending jobs, retry after failure, mixed pending and terminal failures, ready, cancelled/expired commentary, and status transitions during commentary polling. Require at most one sphere, complete localized hover text, correct placement, and blank pending/context-missing classification cells in every render path.
- **Hover regression net:** check Japanese family headings and lookup values (including historical/missing labels), larger glyph/flag visuals, follower count plus SVG X logo, keyboard/pointer interactions, reduced motion and cached hashed asset responses. Keep account followers when engagement icons disappear; R7's specific geopolitical subcategory must remain localized under R13.
- **Language regression net:** reuse `tests/test_translator_lang_detected_compliance.py` and `tests/test_feed_geography.py` for precise codes, Chinese script tags, invalid codes and language-filter compatibility. If normalization needs a repair, exercise the real translator caller with captured downstream arguments as well as the helper. Any lookup seed repair must be idempotent and leave existing English/Chinese rows intact. No provider batch is needed to prove these UI requirements.
- Run the affected homepage UI assurance profile during implementation and candidate-level assurance before release. Choose and record the performance scope from the actual product changes; a waived or unperformed check is never reported as passed.

### Commands and evidence

- Focused Python coverage: `pytest tests/test_home_v22_feed_row_shape.py tests/test_home_v22_filter_pills.py tests/test_views.py tests/test_post_synthesis_api.py tests/test_feed_geography.py tests/test_translator_lang_detected_compliance.py`, with a dedicated local PostgreSQL URL and persistent task-specific pytest temporary directory.
- Client coverage: `node --test tests/test_pw_feed_formatter.js` and the existing chart/locale tests affected by U2.
- Browser coverage: relevant cases in `tests/test_home_v22_browser.py`, then the affected assurance gate's required stateful tests.
- Declaration checks: `uv run --extra dev bridgewright assurance-validate --project-root .` and `uv run --extra dev bridgewright assurance-prescribe --project-root .`.
- Stateful checks: `uv run --extra dev python -m tests.ui_assurance.gate --scope affected`; candidate command and exact performance inputs follow the existing `fix-ui` contract. Seal the intended source before claiming candidate coverage.
- Delivery: follow the selected guide and current owner exceptions; record the actual deployed SHA and environment separately from local test results.

## Definition of Done

- R1–R16 hold on initial HTML and the applicable dynamic paths in English, Japanese and Simplified Chinese.
- One subdued sphere maximum per post, truthful language/terminal states, correct job detail and preserved duration notes.
- Requested clutter is absent; followers, X links, headline narrative/disclosure and filter semantics remain functional.
- Meaningful caller/browser regressions and required assurance obligations pass, with executed/skipped/error counts and source identity recorded.
- Reviewed task changes are committed and reach the owner's selected delivery endpoint; the running revision and required visible behavior are observed.
- Deferred historical provider/data work remains explicitly deferred.
