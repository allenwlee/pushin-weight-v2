# Homepage preferences and UI regressions Bridgewright target contract

Approval status: APPROVED

Approved by: project owner through the explicit homepage persistence and UI
instructions in the 2026-08-26 session

Protected production baseline: `2184d58fa718cdc7bde2eb30861dd1f388aa3523`

Prior approved chart contract:
`docs/reference/2026-08-24-162449-home-chart-time-axes-bridgewright-target.md`

This contract supersedes the prior chart contract only for the targets below.
The protected production baseline and earlier filter/feed and V24 contracts
remain authoritative for every unnamed surface. The current hosted staging
appearance is not an approved baseline; staging must be assessed against
production plus these intentional deltas.

## Approved production targets

| Surface | Approved target |
| --- | --- |
| Browser preferences | One versioned, user-namespaced browser payload remembers locale, window, Local/CA mode, lenses, filters, and pulse selections across locale navigation, reload, and later sessions. Locale retains its server cookie. URL state is a transient override. Account defaults and saved views are deferred. |
| Pulse chrome | Remove `.pulse-bar-head` and show all 20 canonical enabled-model chips in canonical order, including zero-activity models. |
| One-day time axes | Put both hourly axes below the line graph, local immediately above California. Label even wall-clock hours `0:00` through `22:00`; retain an unlabeled tick hash for odd hours. |
| Axis prominence | Local retains the chart lettering family and is more prominent. California retains the orange timezone-pill family at lower opacity. |
| Feed identity signal | Replace public V22 initials avatars with four follower-count circles: 0–999, 1,000–9,999, 10,000–49,999, and 50,000+. Diameter and opacity increase by bin; an accessible follower count remains available. |
| Mobile title | Keep `走个量` unchanged and show `Pushin'` and `Weight` on two complete lines aligned to its height. |
| Model tiers | Closed contains `gemini`, `gpt`, `claude`, and `grok`; none of those remain in Open. |

## Explicit non-targets

- Do not change `/internal/`, the legacy initials avatar, authentication,
  database models, migrations, harvest/headline behavior, or deployment
  topology.
- Do not replace the Chart.js canvas, chart/feed endpoints, aggregation
  meaning, request-race protection, last-good restoration, or non-1d axes.
- Do not automatically write browser state into an account. A future explicit
  default-brand, saved-default, or named-view feature may reuse the payload.
- Do not treat Bridgewright assessment as approval or deployment authority.
- Do not use the pre-existing hosted staging appearance as a visual reference.

## Regression net

- Drive the real public route in Chromium at desktop and 390px mobile widths,
  in English and Chinese, with real static assets and Chart.js execution.
- Change filters, 30d, CA, Closed, and locale; prove the same state reaches the
  first chart/feed refresh after locale navigation, reload, and a new page.
- Prove exactly 20 pulse buttons, four disjoint Closed brands, no pulse heading,
  complete two-line English title geometry, and all four follower boundaries in
  both server-rendered and incrementally replaced rows.
- Prove both 1d scales are below the plot in local-then-California pixel order,
  with twelve even-hour labels, 24 hashes, relative colors, and unchanged
  longer-window behavior.
- Compare the exact deployed staging candidate against the protected production
  baseline at matched locale, viewport, and state; permit only this contract's
  named differences.

## Approval boundary

Approval applies to this written UI delta and staging-only delivery. It does
not approve promotion to production or replace explicit owner review.
