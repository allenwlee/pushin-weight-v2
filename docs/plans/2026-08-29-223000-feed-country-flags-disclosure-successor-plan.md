---
title: Feed Country Flags and Reversible Headline Disclosure - Plan
type: feat
date: 2026-08-29
artifact_contract: ce-unified-plan/v1
artifact_readiness: requirements-only
product_contract_source: split-successor
execution: code
---

# Feed Country Flags and Reversible Headline Disclosure

## Goal Capsule

- **Objective:** Let homepage readers identify an account's persisted country at a glance and expand or collapse each trend explanation through one predictable localized control.
- **Authority:** This Product Contract preserves the UI scope split from `docs/plans/2026-08-29-093958-feat-feed-country-flags-disclosure-plan.md`. A future planning run must select this successor through Ollija before implementation.
- **Execution profile:** Deferred. Do not execute until the staging account-enrichment pilot is reviewed and the owner authorizes this successor.
- **Stop conditions:** Stop if staging evidence does not support persisted `country_code`, if the display rule for uncertain provider values remains unresolved, or if the deferred working diff cannot be reconciled against current main.

---

## Product Contract

### Summary

Move the approved country-flag reference into durable documentation, render the approved subdued SVG flag below account metadata in the homepage feed, and replace separate headline detail/hide controls with one reversible `more`/`less` disclosure.

### Problem Frame

The approved 197-country SVG set exists, but feed rendering must wait for a verified persisted account-country source. The current headline has separate detail and hide interactions, so its action and state are not predictable.

### Key Decisions

- PD1. **Use one headline disclosure control.** (session-settled: user-directed — chosen over separate detail and hide controls: one control should describe and reverse its own state.) Governs R2-R5.
- PD2. **Place the flag relative to the official-role slot.** (session-settled: user-directed — chosen over a fixed flag slot: official accounts place the flag below the badge; other accounts place it directly below followers.) Governs R9-R10.
- PD3. **Localize the full country-name hover text.** (session-settled: user-directed — chosen over a code or English-only tooltip: the locale toggle should govern the visible name.) Governs R7, R10-R11.
- PD5. **Use the approved subdued SVG treatment.** (session-settled: user-approved — chosen over CSS pixels and full-brightness artwork: the flag should stay subordinate in the feed.) Governs R8-R10.
- PD7. **Promote the approved review page to reference documentation.** (session-settled: user-directed — chosen over leaving it under ideation: it is the implementation reference.) Governs R1.
- PD8. **Use official zh-CN territory display names.** (session-settled: user-directed — chosen over improvised translations: names come from a pinned Unicode CLDR standard source.) Governs R7-R8 and R11.

### Requirements

**Reference and country identity**

- R1. Move `docs/ideation/2026-08-29-162947-country-flag-svg-reference.html` to `docs/reference/2026-08-29-162947-country-flag-svg-reference.html` and preserve deterministic 197-flag generation.
- R6. Use only persisted `Account.country_code` from the completed enrichment work as feed flag identity.
- R7. Resolve each supported code through one approved manifest to its reviewed symbol, English name, and official Simplified Chinese name.
- R8. Render no flag, placeholder, or profile-location/geotag fallback when `country_code` is blank or unsupported.
- R9. Render the approved Recommended SVG treatment at the same 14-pixel size as role icons.
- R10. Order official accounts as followers, official badge, flag. Without `role-official`, put the flag directly under followers and before preserved non-official badges.
- R11. Initial HTML and JavaScript replacement rows expose the same locale-selected full country name in hover and accessible text without adding a tab stop.

**Headline disclosure**

- R2. A collapsed headline shows one English `more` or zh-CN `更多` button, hidden secondary copy, and `aria-expanded="false"`.
- R3. Activating the button expands only its item, reveals secondary copy, changes the same button to English `less` or zh-CN `收起`, and sets `aria-expanded="true"`.
- R4. Activating `less` collapses the same item, restores the collapsed label and ARIA state, and leaves focus on the button.
- R5. Server-rendered and JavaScript-replacement narratives use the same one-button contract; refresh resets replacement items to collapsed.

**Boundaries and delivery**

- R13. Preserve feed ordering, pagination, role logic, filters, chart behavior, cookies, `/internal/`, and all unnamed homepage surfaces.
- R14. Extend the latest Bridgewright target with country presence/absence, locale, role placement, headline transitions, and protected boundaries.
- R15. Obtain a new explicit Ollija delivery target before implementation. This deferred document grants no commit, deployment, database, or provider-call authority.

### Acceptance Examples

- AE1. Deterministic generation leaves the approved HTML only under `docs/reference` and preserves all 197 flag identities.
- AE2. An English item transitions `more` to `less` to `more` through the same focused button.
- AE3. A zh-CN item performs the same transition with `更多` and `收起`.
- AE4. An official US account renders followers, official badge, then the Recommended 14-pixel flag with `United States` as hover and accessible text.
- AE5. A no-role CN account under zh-CN renders the flag directly below followers with `中国` as hover and accessible text.
- AE6. A row with free-form location or geotag but no persisted `country_code` renders no flag or reserved gap.
- AE7. Initial and replacement rows match in identity, locale, order, dimensions, filter, and escaping at narrow and desktop widths.
- AE8. Bridgewright affected and candidate gates succeed with no required missing, skipped, errored, failed, or unknown obligations.

### Scope Boundaries

**In scope after authorization**

- Approved flag-reference movement and deterministic country assets.
- Homepage ORM-to-wire-to-server/client flag rendering and localized names.
- One reversible localized headline disclosure.
- Bridgewright coverage and an owner-selected delivery lane.

### Deferred to Follow-Up Work

- Production Account enrichment and recurring User About refresh remain owned by the enrichment plan or later operations work.

**Outside this plan**

- Changing the stored country source or interpreting profile location.
- Adding provider calls, migrations, Account columns, or backfill behavior.
- Redesigning `/internal/`, feed order, role assignment, or headline content generation.

### Open Questions

- **Blocking:** After reviewing the 100-account staging evidence, decide whether `location_accurate=false` or null may render a flag or whether the feed requires true. The answer governs final UI eligibility but does not change Account persistence.
- **Deferred:** Select staging or production delivery through Ollija when this successor is activated.

### Sources

- `docs/reference/2026-08-29-162947-country-flag-svg-reference.html` — approved visual source after movement.
- `docs/plans/2026-08-29-093958-feat-feed-country-flags-disclosure-plan.md` — typed Account source and staging evidence dependency.
- `monitor/templates/monitor/_feed_initial_v22.html`, `monitor/static/pw-feed.js`, and `monitor/templates/monitor/home.html` — existing initial/replacement/headline surfaces to reconcile when planning resumes.
