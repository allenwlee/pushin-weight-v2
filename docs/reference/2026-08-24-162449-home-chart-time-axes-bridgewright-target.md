# Home chart time-axis and performance Bridgewright target contract

Approval status: APPROVED

Approved by: project owner through the explicit home-chart regression and
time-axis instruction in the 2026-08-24 session

Protected production baseline: `e290ba67ef0cd382a34fc774cd3cc173e5a00b1f`

Prior approved production contract:
`docs/reference/2026-08-19-174833-production-filter-feed-bridgewright-target.md`

This contract adds a narrow production Chart.js delta to Bridgewright. It
supersedes the prior contract's Chart.js non-target only for the approved
targets below. The protected production baseline, prior filter/feed contract,
and V24 mockup contract remain authoritative for every unnamed surface.

## Approved production targets

| Surface | Approved target |
| --- | --- |
| Long-window response | Switching to 30d and 365d returns and atomically commits the matching chart, pulse, narrative, and top-voice projection before the existing 12-second timeout. A warm switch targets two seconds, with comparable baseline evidence required for any relative-improvement fallback. |
| One-day geometry | The 1d plot uses the full usable chart-card width. The y-axis title and ticks start at the left of the chart section without an unexplained gutter or clipped text. Other windows retain their current geometry. |
| One-day time axes | The 1d chart has a top local-time x-axis and a bottom California-time x-axis. Both show exactly 24 fixed hourly positions for the same absolute instants, labeled only with integer hours. Other windows retain one date axis. |
| Axis color | The local axis keeps the chart lettering color. The California axis uses the current California timezone-pill tint, `#fbbf24`. |
| Legend order | The chart legend starts in the same order as the visible pulse chips, then appends any chart-only brands in deterministic series order. |

## Explicit non-targets

- Do not replace the production Chart.js component, its one live canvas, the
  shared `/chart.html` response, or its rich payload with mockup scaffolding,
  static paths, fixture values, or a second renderer.
- Do not change aggregation meaning, five-minute one-day bucket cardinality,
  filter semantics, tooltip content, hidden discourse datasets, locale refresh,
  periodic refresh, request-race handling, or last-good restoration.
- Do not change the production feed, filter taxonomy, timezone-pill selection
  behavior, internal home, brand chart, headline worker, harvester,
  authentication, data model, or deployment topology.
- Do not add a database table, materialized view, migration, worker, endpoint,
  client dependency, or deployment resource for this target.

## Regression net

- Prove the fixed 24-position local and California axes through the real public
  home route in a non-default browser timezone at desktop and mobile widths,
  including date and daylight-saving boundaries.
- Prove deterministic oldest and newest one-day data use the available plot
  width while y-axis labels remain visible and non-1d geometry stays stable.
- Prove legend order follows the visible pulse ranking without changing dataset
  order or payload insertion order.
- Compare cold and warm 30d and 365d window switches on the protected baseline
  and changed branch with the same PostgreSQL fixture, Chromium setup, locale,
  timezone, and cache state.
- Preserve the existing filter, locale, atomic-projection, request-race,
  last-good, and one-canvas browser regression nets.

## Approval boundary

Approval applies only to this written chart delta. It does not approve staging or production release.
Every prior non-target not explicitly superseded above remains protected.
