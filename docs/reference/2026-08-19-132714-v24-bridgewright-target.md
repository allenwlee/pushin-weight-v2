# V24 Bridgewright target contract

Approval status: APPROVED

Approved by: project owner through an explicit instruction in the 2026-08-19 mockup session

Approved mockup: `docs/ideation/mockups/v24.html`

Supersedes: V22 as the Bridgewright mockup target

V24 replaces V22 as Bridgewright's approved mockup. This is a partial target
approval: only the changes named below are targets. Every other V24 element is
reference context or placeholder material and must not be treated as a product
implementation target.

## Approved changes from V22 to V24

| Surface | Approved target |
| --- | --- |
| Locale buttons | English, Simplified Chinese, and Original labels switch without changing any locale button's width or height. The three buttons retain identical geometry. |
| Selected pulse chips | A selected brand chip uses the same blue accent background as the active time-window button. |
| Pulse-chip selection | Brand chips are independent multi-select toggles. Selecting brands shows the union of those brands in the production graph and feed; selecting an active chip again removes it. No selected brands means show all. |
| Timezone pill | Local and California times are always visible in 24-hour format in one bisected pill with a thin divider. Local is selected by default; the selected half uses the blue accent. Switching halves preserves the pill and topbar-control dimensions and continues to update feed timestamps. |
| Time-window buttons | The `1`, `7`, `30`, and `365` day buttons have identical geometry and do not resize when switching among English, Simplified Chinese, and Original. |
| One-day copy | Replace `24小时` with `1天` and `24h` with `1d`. Original uses the English time-window labels. |

The V23 mockup introduced the first four changes. V24 adds stable time-window
geometry and the one-day copy. Together, the table above is the complete
approved V22-to-V24 target delta.

## Explicit non-targets

All V24 surfaces not listed in the approved-change table are not targets.
In particular:

- The Production line graph is not a V24 visual or implementation target.
  Its static SVG paths, sample series, axes, scale, interpolation, density,
  labels, legend details, and placeholder values must not be copied. Preserve
  production's richer graph component, live data source, calculations, and
  interactions. Only brand visibility filtering from the approved pulse-chip
  behavior applies to it.
- The Production feed is not a V24 content, data, or layout target. Preserve
  its live endpoint, records, ordering, pagination, metadata, styling, and
  behavior. Only the approved union brand filter and timezone timestamp
  switching apply to it.
- The mockup's `data-brand` and `data-brands` attributes, extra placeholder
  polylines, hidden-element rules, sample posts, and hard-coded values are
  demonstration scaffolding, not prescribed production architecture.
- The headline, filter groups, filter contents, chart/feed proportions,
  typography, colors outside the named selected states, document title, debug
  metadata, and all other page chrome remain governed by production.

Do not replace any production graph, feed, endpoint, data model, or dynamic
component with static mockup markup or fixture data.

## Regression net

- Prove the production graph remains the existing rich dynamic component and
  continues to receive its existing live series/data inputs.
- Prove the production feed remains connected to its existing live data path.
- Exercise pulse-chip multi-select against both production graph visibility and
  production feed visibility, including deselection and the show-all state.
- Exercise locale changes at desktop and mobile sizes and assert stable locale
  and time-window geometry with no topbar overflow.
- Exercise both timezone halves and assert stable pill/topbar geometry, two
  continuously visible 24-hour times, and the existing feed timestamp change.
- Reject visual or behavioral changes outside the approved-change table.

## Approval boundary

The owner's approval applies to this written partial-target contract and V24's
named control behavior. It does not approve a whole-page V24 pixel match, does
not approve replacement of production systems with mockup scaffolding, and
does not grant deployment or release authority.
