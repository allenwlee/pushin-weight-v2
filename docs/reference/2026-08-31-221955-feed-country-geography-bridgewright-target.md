# Feed country geography and disclosure Bridgewright target contract

Approval status: APPROVED

Approved by: project owner through the explicit account-country flag and
single-control headline instructions in the 2026-08-29 through 2026-08-31
session

Protected production baseline:
`41af58ea3775f5741b21dc01a792c93b5739bc35`

Prior approved interaction contract:
`docs/reference/2026-08-28-181416-chart-hover-freeze-bridgewright-target.md`

The production page at the protected SHA remains authoritative for every
unnamed surface.

## Approved deltas

| Surface | Approved target |
| --- | --- |
| Account geography | The public feed uses normalized X User About geography only. It renders one subdued 14-pixel country flag, a guiding-country flag before its child flag, neutral `TW · Taiwan` / `TW · 台湾` text after the China flag, or localized region text when no approved flag exists. Unresolved values render nothing. |
| Metadata order | Official accounts render followers, official badge, then geography. Accounts without the official role render followers, geography, then any staff or community badge. |
| Geography language and meaning | Hover and accessible text use the active English or zh-CN full name and describe the value as X-reported account location, never nationality or self-identification. |
| Headline disclosure | Every schema-3 secondary starts collapsed behind one localized `more` / `更多` button. The same focused button expands as `less` / `收起` and collapses back to `more` / `更多`; secondary copy is selectable non-interactive text. |

## Protected behavior

- Preserve feed ordering, pagination, filtering, request cancellation, text
  cycling, signal order, engagement, role selection, row navigation, and
  initial/replacement parity outside the approved metadata delta.
- Preserve Chart.js rendering, hover-freeze, pulse, Top Voices, narrative
  generation/storage, locale and timezone preferences, and refresh ownership.
- Preserve all approved Cyber-Quan geometry and semantic colors. Country flags
  remain presentation-only, non-focusable, and subordinate to account data.
- Preserve `/internal/`, authentication, persistence, harvesting, provider-call
  behavior, and deployment topology.

## Required state model

- Geography: absent, direct country, guiding-country hierarchy, Taiwan-neutral,
  direct region, and country-to-region fallback in English and zh-CN.
- Roles: official, staff, community, and absent with the required geography
  order in initial and JavaScript-replacement rows.
- Headline disclosure: collapsed -> expanded -> collapsed through one button,
  pointer and native keyboard activation, stable focus, sibling isolation, and
  replacement reset in English and zh-CN.
- Asset safety: all rendered `use` targets resolve to the approved inline
  sprite; unknown symbols fail closed; no feed DOM references `flag-tw`.

## Evidence contract

- Drive the real anonymous `/` route in Chromium at desktop and 390-pixel
  mobile widths through the same locale cookies and `/feed/` replacement path
  used in production.
- Assert exact flag order, 14-pixel width, subdued computed treatment,
  localized hover/accessibility copy, Taiwan prohibition, region fallback,
  unresolved omission, metadata order, and zero horizontal overflow.
- Assert one disclosure button per headline, exact localized labels and ARIA
  transitions, focus retention, sibling isolation, inert secondary copy, and
  collapsed replacement state.
- Keep the feed geography query count bounded as row count and geography
  variety increase.
- The affected and candidate Bridgewright gates require zero failed, skipped,
  errored, missing, or unknown obligations.
