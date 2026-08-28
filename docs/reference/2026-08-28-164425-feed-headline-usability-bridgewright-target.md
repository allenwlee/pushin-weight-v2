# Feed and headline usability Bridgewright target contract

Approval status: APPROVED

Approved by: project owner through the explicit feed/headline usability
instructions in the 2026-08-28 session

Protected production baseline:
`e1447569c4097f2abc6af110358f10afc33a5168`

Prior approved icon contract:
`docs/reference/2026-08-28-134649-cyber-quan-icons-bridgewright-target.md`

This target permits only Release A in
`docs/plans/2026-08-19-043225-feat-mockup-v23-plan.md`. The production page at
the protected SHA is authoritative for every unnamed surface.

## Approved deltas

| Surface | Approved target |
| --- | --- |
| Feed text | A text-layer activation advances the layer and expands the text from three to at most nine lines on mobile, or four to at most twelve on desktop. The row grows no more than three times its default height and collapses outside. zh-CN uses synthesis, literal, source. |
| Trend headline | Each schema-3 secondary starts hidden. Localized detail/hide link-style controls and the secondary itself disclose or collapse exactly one item with synchronized keyboard and ARIA state. |
| Filter choices | Existing feed-semantic Cyber-Quan SVGs precede applicable option labels without changing checkbox keys, dropdown geometry, or semantic colors. |
| Account role | One rough credential-badge symbol appears below the follower count for official, staff, or community, in amber, violet, or green. Other/absent reserves an empty slot. |
| Identity header | Long CJK, Latin, and unbroken display names ellipsize so handle plus immutable metadata remain on one line at 320px and above. |

## Protected behavior

- Preserve the Chart.js canvas, payload, scales, tooltip, datasets, refresh
  transaction, pulse, Top Voices, and narrative generation/storage.
- Preserve feed ordering, pagination, refresh/cancellation, row X navigation,
  filter predicates, locale preference, timezone conversion, and signal order.
- Preserve all existing Cyber-Quan geometry and colors. Add only the role-badge
  symbol; blue remains exclusive to selected states.
- Preserve production typography, overall layout, `/internal/`, authentication,
  persistence, harvester, and deployment topology.

## Required state model

- Feed text: synthesis-collapsed, literal-expanded, source-expanded, outside-
  collapsed; pointer and keyboard; SSR and refreshed rows; EN and zh-CN.
- Headline detail: collapsed and expanded for each of two items, hide-link,
  secondary-click, keyboard, refreshed-collapse, legacy schema, and empty state.
- Role badge: official, staff, community, absent, and multi-role precedence;
  SSR/refreshed parity and complete role-filter matching.
- Filter dropdown: closed, open and on-screen, interior checkbox remains open,
  exterior click closes; every applicable option has a resolved nonzero SVG.
- Responsive identity: long CJK, Latin, and unbroken names at 320px, 390px, and
  desktop; metadata visible; one line; zero horizontal overflow.

## Evidence contract

- Drive the authenticated real `/` route in Chromium, not a standalone mockup.
- Test English and zh-CN at desktop, 390px, and 320px and cover both the initial
  response and JavaScript replacement paths.
- Assert visible geometry: row height ratio and clamp, headline hidden boxes,
  filter rectangle intersection, identity/meta line boxes, SVG target existence
  and nonzero bounds, signal-column position, and document scroll width.
- Compare matched baseline/candidate screenshots with allow regions limited to
  feed text height, schema-3 headline disclosure controls/secondary, filter
  choice icon cells, follower role slots, and truncated identity text.
- The affected and candidate Bridgewright gates require zero failed, skipped,
  errored, missing, or unknown obligations.
