# Chart hover-freeze Bridgewright target contract

Approval status: APPROVED

Approved by: project owner through the explicit Chart.js hover-freeze
instructions in the 2026-08-28 session

Protected production baseline:
`e2d48a2c642ccbf03407a7a1ecfd36161ab0f018`

Prior approved usability contract:
`docs/reference/2026-08-28-164425-feed-headline-usability-bridgewright-target.md`

This target permits only Release B in
`docs/plans/2026-08-19-043225-feat-mockup-v23-plan.md`. The production page at
the protected SHA remains authoritative for every unnamed surface.

## Approved delta

| Surface | Approved target |
| --- | --- |
| One-day tooltip | Hovering a real five-minute point shows a prettified browser-local datetime and the corresponding Beijing datetime above the existing per-brand post counts. |
| Point freeze | Clicking a real point in the 24-hour chart freezes that exact half-open five-minute bucket, keeps the point and tooltip visibly active, pauses chart/feed refresh, and refetches the feed for the bucket. Clicking the same point is idempotent. |
| Frozen filters | The frozen feed preserves the active brand selection and ignores sentiment, post type, role, language, nationalism, discourse, and unsanctioned filters. Underlying preferences remain unchanged. |
| Frozen chrome | Every locale button is visibly and semantically unselected. The feed title becomes the same local/Beijing datetime shown by the tooltip. |
| Release | Clicking a different point, empty chart space, or anywhere outside the chart releases the freeze, clears the tooltip, restores the exact prior locale selection and default feed title, resumes one refresh timer per owner, and performs one normal feed replacement. |
| Other windows | 7-, 30-, and 365-day charts retain their existing hover and click behavior and cannot enter hover-freeze. |

## Protected behavior

- Preserve Chart.js canvas rendering, datasets, brand colors, time axes,
  legend, pulse, Top Voices, trend narratives, and ordinary refresh behavior.
- Preserve every filter value and preference while frozen; hover-freeze is
  transient and must not write cookies, local storage, or server state.
- Preserve feed ordering, serialization, pagination, row interactions, locale
  text cycles, account metadata, Cyber-Quan icons, and normal filtering outside
  the frozen interval.
- Preserve production typography, layout, `/internal/`, authentication,
  persistence, harvesting, database schema, and deployment topology.

## Required state and race model

- Idle -> hovered -> frozen -> released, in English and zh-CN.
- Exact-point, same-point, other-point, empty-space, and outside-click paths.
- One-day versus 7/30/365-day windows; all-brands versus selected brands;
  conflicting non-brand filters; empty and populated five-minute buckets.
- Browser-local date rollover and Beijing conversion, with human-readable text
  rather than raw ISO timestamps.
- Frozen point and tooltip survive mouse movement and Chart.js `afterEvent`.
- In-flight chart/feed responses started before freeze or release cannot commit
  after the newer intent; aborts do not surface false failure state.
- Repeated freeze/release cycles leave exactly one chart timer and one feed
  timer active, never duplicates.

## Server contract

- `/feed/` accepts paired aware `freeze_start` and `freeze_end` values only for
  the one-day window. The interval is positive, at most five minutes, and
  within the current 24-hour chart horizon (with one bucket of clock tolerance).
- The database applies `created_at >= freeze_start` and
  `created_at < freeze_end` before the existing hard cap.
- Malformed, partial, naive, reversed, oversized, out-of-horizon, or non-one-day
  ranges fail closed with HTTP 400.

## Evidence contract

- Drive the real anonymous `/` route in Chromium at a 390px mobile viewport,
  tap coordinates from an actual rendered Chart.js point, and inspect the real
  `/feed/` response and rendered rows.
- Prove exact five-minute request bounds, brand-only effective filters,
  persistent active elements/tooltip after pointer movement, zero selected
  locale buttons, datetime title parity, same-point idempotence, and complete
  restoration after an outside click.
- Cover the formatter, click lifecycle, refresh ownership, stale-response gate,
  invalid server ranges, half-open database boundaries, and EN/zh-CN labels in
  deterministic tests.
- The affected and candidate Bridgewright gates require zero failed, skipped,
  errored, missing, or unknown obligations.
