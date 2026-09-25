---
title: Feed Processing Indicator Follow-up - Plan
type: feat
date: 2026-09-25
artifact_contract: ce-unified-plan/v1
product_contract_source: ce-plan-bootstrap
execution: code
ollija:
  change_id: feat-feed-processing-indicator-followup-2026-09-25-041204
  branch: feat/feed-processing-indicator-followup
  workflow: plan
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
- Active worktree: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/feed-processing-indicator-followup`
- Plan: `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/feed-processing-indicator-followup/docs/plans/2026-09-25-041204-feat-feed-processing-indicator-followup-plan.md`
- Change: `feat-feed-processing-indicator-followup-2026-09-25-041204`
- Branch: `feat/feed-processing-indicator-followup`
- Staging branch and blueprint: `staging`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/feed-processing-indicator-followup/render-staging.yaml`
- Production branch and blueprint: `main`, `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/feed-processing-indicator-followup/render.yaml`
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
    - From `/Users/fuchitalee/development/pushin-weight-v2`, require `/Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/feed-processing-indicator-followup` to remain registered, clean, unlocked, and at the verified candidate SHA. If any guard fails, retain it and report the reason.
    - Run `git -C /Users/fuchitalee/development/pushin-weight-v2 worktree remove /Users/fuchitalee/development/pushin-weight-v2/.worktrees/feat/feed-processing-indicator-followup` without `--force`.
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

# Feed Processing Indicator Follow-up - Plan

## Plain-English Summary

Each post will show at most one subdued spinning armillary while any of its processing is pending. Its hover will name every pending job in plain language, such as “Translation, analysis and commentary pending.” If language detection is pending, the language tag will use that same armillary rather than a separate globe or second spinner. Permanent failures will keep their existing stop marker.

The feed will leave the classification status cell empty for “Pending” and “Context missing.” It will show a precise two-letter language code for posts currently grouped under “other” when that code can be established. Old “other” rows have lost that detail, so the work includes a bounded language-only repair; unresolved rows will show the honest unknown-language glyph rather than a guessed code.

The same result must appear on the initial page, after a feed refresh, and after a commentary status update. Browser tests will check English, Japanese and Chinese, keyboard hover behavior, reduced motion, and cached glyph assets. Changing language storage also needs a translator call-chain regression and a controlled rollout. The owner selected staging followed by production on 2026-09-25.

---

## Goal Capsule

- **Objective:** A reader sees one quiet indicator per pending post, understands all pending work from its hover, and sees specific language codes when known.
- **Means:** Aggregate durable processing statuses once in the feed wire, render that projection consistently in both feed paths, and retain precise validated language codes at translation time.
- **Authority:** The user selected the visible behavior on 2026-09-25. The current feed contract lives in `docs/reference/feed-ui-contract.md`; `core/models.py` and `x_monitor/translator.py` own persisted language semantics.
- **Stop condition:** Do not invent a two-letter code for a historical `other` row without source evidence or a verified detection result. Do not make provider calls or mutate production data as part of planning.

---

## Product Contract

### Problem Frame

The current feed creates one armillary per pending translation, classification, and commentary job. It can create an additional globe for language detection, so a single post looks crowded. The classification status column repeats “Pending” or “Context missing,” while the translator collapses valid two-letter languages outside its named set into `other`. Readers cannot see which language those posts use.

### Requirements

**Processing indicator**

- R1. A post displays at most one animated armillary regardless of the number of pending jobs. The same limit applies when its language detection is pending.
- R2. The armillary hover and accessible label list every pending job once, in a stable order and in the selected locale. English names are “language detection,” “translation,” “analysis” for classification, and “commentary” for synthesis. The wording uses natural conjunctions, including “Translation, analysis and commentary pending” for that exact set.
- R3. An undetected language awaiting enrichment uses the armillary as that post's single pending marker. If the post has no other pending work, the marker still says “Language detection pending.” If language detection is no longer pending and no language is known, the existing globe and state-specific explanation remain.
- R4. The armillary uses a less prominent amber than the current full-strength yellow. The fixed outer sphere and base stay fixed; the inner ring keeps its full revolution. Reduced-motion users see a stationary marker. The permanent-failure stop marker and its truthful queue semantics remain.

**Status and language display**

- R5. The classification status cell has no visible label or hover trigger for `pending` and `context_missing`. Status data and filters retain their meaning; failed, stale and historical statuses keep their existing visible behavior.
- R6. A known source language currently mapped to `other` is displayed as its lowercase ISO 639-1 two-letter primary code, including in Japanese and Chinese locales. Existing Chinese script tags retain `zh-Hans` and `zh-Hant` where known.
- R7. Historical `other` rows receive a bounded language-only repair without replacing translations, classifications or commentary. A row that cannot be resolved shows the unknown-language glyph and an accurate hover, never the text `other` or an invented code.

### Scope Boundaries

- Feed display, translator language normalization, language-only historical repair, and the language filter compatibility needed for those changes are in scope.
- Harvest query shape, scheduling, provider choice, translation prose, taxonomy classifications, follower hover, and unrelated glyphs are outside scope.
- No production batch, provider call, release or cron pause is authorized by this plan.

### Acceptance Examples

- AE1. **Covers R1–R3.** Given translation, classification and synthesis are pending and the language is unknown, the post has exactly one spinning armillary. Hovering or focusing it names language detection, translation, analysis and commentary once each in the selected locale.
- AE2. **Covers R1, R2, R4.** Given translation has permanently failed while analysis and commentary remain pending, one subdued armillary summarizes pending work and the stop marker retains the translation failure detail.
- AE3. **Covers R3.** Given language detection alone is pending, the language tag area holds the sole armillary and says “Language detection pending.” Given detection has failed with no retry queued, it shows a globe and failure explanation.
- AE4. **Covers R5.** Given a row with `pending` or `context_missing` classification status, its classification status cell is empty while its wire status and filters still reflect that state.
- AE5. **Covers R6, R7.** Given a French source reported as `fr`, the stored and displayed code is `fr` in every locale. A historical `other` row becomes `fr` only after verified language-only repair; an unresolved row shows the globe.

---

## Planning Contract

### Key Technical Decisions

- KTD1. **Aggregate in the serializer.** Build one ordered pending-work projection from the existing durable translation and classification stages plus synthesis demand. Include language detection when `lang_detected` is unknown and translation is pending. The template and JavaScript render the projection and do not recalculate status.
- KTD2. **One placement for the spinner.** Render the sole armillary in the language tag position while language detection is pending, otherwise in the post metadata. Both locations use the same wire hover and CSS class. Failed stop markers may remain alongside it. This resolves R1 and R3 without leaving the language tag blank.
- KTD3. **Preserve precise validated language.** Update `normalize_lang_detected` and prompts to accept registered ISO 639-1 primary codes instead of collapsing them into `other`. Keep rejection and bounded repair for invalid, reserved or private codes. Preserve the existing Chinese script mapping and translation no-op rules.
- KTD4. **Repair historical loss separately.** The stored `other` value cannot reveal the original two-letter code. Add a resumable, bounded language-only batch that re-detects those rows through the configured translator provider, validates the answer, updates only `lang_detected`, and records attempted/unresolved counts. Estimate and cap provider spend before running; do not launch it from the live 15-minute cron. A legacy `other` tag renders as unknown until resolved.
- KTD5. **Keep filter groups stable.** Precise new codes continue to match their named language filters where present; remaining valid two-letter codes stay in the residual “other” filter group. The filter is a category, while the post tag reports the precise code.

### Existing Paths and Dependencies

- `monitor/views.py` owns `_processing_badges`, `_compact_language_display`, `_language_inspection`, `_v22_feed_display_fields`, row serialization and language filter predicates.
- `monitor/templates/monitor/_feed_initial_v22.html`, `monitor/templates/monitor/_feed_language_tag.html`, and `monitor/static/pw-feed.js` render initial, refreshed and synthesis-updated rows. `updateSynthesisRow` currently replaces only a synthesis badge; aggregation must preserve the other pending jobs during that update.
- `monitor/static/home-v20.css` owns armillary color, motion and popover sizing. `monitor/static/pw-processing-glyphs.svg` is already served through Django's content-hashed static manifest.
- `x_monitor/translator.py` currently maps valid codes such as `fr` to `other`. `docs/solutions/runtime-errors/2026-08-10-translator-lang-detected-llm-compliance.md` records why invalid values must still fail through bounded repair.

### Sequencing

1. Characterize the current initial/refresh/synthesis DOM and translator call chain with red regression cases for R1–R7.
2. Change precise language normalization and filter/display projection, then add the bounded historical repair with dry-run and cost reporting.
3. Aggregate pending work in the serializer and update all three browser rendering paths together, including the language tag and subdued CSS.
4. Run focused tests, the affected and candidate Bridgewright gates, and a real browser check before any later delivery decision.

---

## Implementation Units

### U1. Precise language metadata and historical repair

- **Goal:** Satisfy R6–R7 and KTD3–KTD5 without altering translation text.
- **Files:** `x_monitor/translator.py`, `monitor/views.py`, a focused command under `monitor/management/commands/`, `tests/test_translator_lang_detected_compliance.py`, `tests/test_feed_geography.py`, and a command test under `tests/`.
- **Test scenarios:** A valid `fr` or `es-MX` answer persists the two-letter primary code; Chinese script and named languages preserve current handling; malformed/reserved values use the bounded repair and fail empty if still invalid. A real translator caller captures the configured provider/model and stored code. The historical command dry-run reports counts and budget, respects batch and resume bounds, updates only language on successful detection, and leaves unresolved rows untouched. Named and residual language filters still select the correct rows.

### U2. One pending marker and honest status text

- **Goal:** Satisfy R1–R4 across initial HTML, feed refresh and synthesis polling.
- **Files:** `monitor/views.py`, `monitor/templates/monitor/_feed_initial_v22.html`, `monitor/templates/monitor/_feed_language_tag.html`, `monitor/static/pw-feed.js`, `monitor/static/home-v20.css`, `tests/test_home_v22_browser.py`, and `tests/test_home_v22_feed_row_shape.py`.
- **Test scenarios:** Zero, one and several pending jobs each produce at most one armillary; the language-pending case places it at the language tag and the hover lists all pending jobs without duplication. A failed job stays a stop marker while another pending job keeps one armillary. Synthesis polling changes pending to ready or failed without losing translation/classification state. English, Japanese and Chinese hover text, pointer/focus/Escape behavior, subdued computed color, full inner-ring animation and reduced-motion stillness are checked in the real browser.

### U3. Classification status display and contract

- **Goal:** Satisfy R5 and document the resulting feed wire/display distinction.
- **Files:** `monitor/views.py`, `monitor/static/pw-feed.js`, `tests/test_home_v22_browser.py`, `tests/test_home_v22_feed_row_shape.py`, and `docs/reference/feed-ui-contract.md`.
- **Test scenarios:** `pending` and `context_missing` have no visible classification status label or trigger on initial load and after refresh; their status remains in wire fields and filter behavior. Failed, stale and historical status labels still render and inspect normally. The reference contract describes the current state only.

---

## Verification Contract

| Evidence | Required result |
| --- | --- |
| `pytest tests/test_translator_lang_detected_compliance.py tests/test_feed_geography.py tests/test_home_v22_feed_row_shape.py` | Translator call chain, precise codes, filter semantics and row shape pass with no required skips. |
| Focused browser cases in `tests/test_home_v22_browser.py` | Initial, refreshed and synthesis-updated DOM prove R1–R5 for `en`, `ja` and `zh_hans`; old visible “Pending,” “Context missing,” and language `other` text are absent. |
| `uv run --extra dev bridgewright assurance-validate --project-root .`, `assurance-prescribe`, then `python -m tests.ui_assurance.gate --scope affected` | Declaration and affected stateful UI gate pass, including the inverse transitions and request race. |
| Candidate Bridgewright gate with exact candidate SHA and required performance inputs | Zero failed, skipped, errored, missing or unknown normalized obligations before release handoff. |
| Historical repair dry-run and bounded staging batch | Counts and cost cap recorded; successful rows change only `lang_detected`; unresolved rows remain honest and no live cron overlap occurs. |
| Post-deploy language and static audit, only if later delivery is authorized | Exact release SHA and next live harvest cohort verified; valid new non-target codes persist precisely, repaired old rows are counted, and the existing hashed sprite remains cacheable. |

---

## Definition of Done

- One pending armillary maximum per post in every render/update path, with a complete localized hover and subdued appearance.
- Language pending uses that armillary; terminal or unknown language explanations remain truthful.
- Pending and context-missing classification status labels are absent from the visible cell without changing status/filter data.
- No post displays `other` as its language tag. Verified precise codes appear; unresolved historical rows show the unknown-language glyph.
- Translator production-call-chain and rendered-browser regression tests pass; required test, skip, error and Bridgewright obligation counts are reported.
- No provider or production batch is run until an owner selects delivery and the bounded repair budget is approved.
