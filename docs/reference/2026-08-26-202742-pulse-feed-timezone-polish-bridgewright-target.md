# Pulse, feed, and timezone polish Bridgewright target contract

Approval status: APPROVED

Approved by: project owner through the explicit pulse, chart timezone, and
feed identity instructions in the 2026-08-26 session

Protected production baseline: `c2c713d07f6fb7c9659ae70f4d4d03dcf414ac7b`

Prior approved UI contract:
`docs/reference/2026-08-26-141113-home-preferences-ui-regressions-bridgewright-target.md`

This contract supersedes the prior preferences/UI contract only for the
targets below. Every unnamed surface remains protected by the production
baseline and earlier filter/feed, chart, preferences, and V24 contracts. The
current hosted staging appearance is not an approved baseline; staging must be
assessed against production plus these intentional deltas.

## Approved production targets

| Surface | Approved target |
| --- | --- |
| Desktop pulse navigation | When all 20 model chips overflow, show a visible native horizontal scrollbar. Keep the existing mobile touch-scroll treatment. |
| Selected pulse identity | A selected chip may use the shared blue fill, but its model-colored left edge remains visible before and after pulse refresh. |
| One-day time rows | Keep local and comparison times below the plot at the same 24 fixed hourly positions. Show even-hour `H:00` labels, retain odd-hour hashes, label the rows at the left, and ensure only the local row draws a baseline. |
| Timezone prominence | The selected Local/comparison row is fully opaque. Inactive local lettering uses 55% alpha; inactive comparison lettering uses the existing orange family at 45% alpha. |
| Dynamic comparison zone | Browser-local zones other than `America/Los_Angeles` compare against California. An `America/Los_Angeles` browser compares against `Asia/Shanghai` and renders the Beijing `京` mark with a red gradient and yellow glyph. |
| Feed reach signal | Replace variable follower circles and the engagement follower statistic with one fixed-width follower lead column. It contains a four-size followers emoji and the compact follower count below it. |
| Feed identity | Keep the X account link target handle-based, but show the account display name with handle fallback. Initial and refreshed rows have the same contract. |

## Explicit non-targets

- Do not change `/internal/`, authentication, account schema, migrations,
  harvest/headline behavior, or deployment topology.
- Do not replace Chart.js, the canvas, chart/feed endpoints, aggregation
  meaning, request-race protection, last-good restoration, or non-1d axes.
- Do not change the 20-model inventory or ordering, filter and locale behavior,
  versioned browser preference payload, or mobile topbar contract.
- Do not treat Bridgewright assessment as approval or deployment authority.
- Do not use the current hosted staging appearance as a visual reference.

## Regression net

- Drive the real public route in Chromium at desktop and 390px mobile widths,
  in English and Chinese, with real static assets and Chart.js execution.
- Prove the overflowing desktop pulse scrolls to the final chip and a selected
  non-blue chip keeps its model-colored left edge after refresh.
- Prove the 1d rows have 24 aligned positions, twelve even-hour labels, odd-hour
  hashes, localized left titles, mode-dependent prominence, and one baseline.
- Use Tokyo and Los Angeles browser timezones to prove the comparison descriptor,
  pill clocks, chart hours, feed stamps, accessible names, and `京` icon switch
  together without losing persisted settings.
- Prove all four follower-bin boundaries use equal lead-column and body geometry
  in server-rendered and incrementally replaced rows, and that display-name
  fallback leaves handle-derived links intact.
- Prove 7d, 30d, and 365d, `/internal/`, locale persistence, request racing, and
  the 20-model inventory remain unchanged.

## Approval boundary

Approval applies to this written UI delta and authorizes the Ollija-governed LFG
delivery path. Staging must verify the exact staged candidate SHA before the
same reviewed SHA can be promoted to production. Desktop and physical-iPhone
visual approvals remain explicit owner actions.
