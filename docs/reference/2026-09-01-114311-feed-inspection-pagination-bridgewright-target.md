# Feed inspection and window-complete pagination Bridgewright target contract

Approval status: APPROVED

Approved by: project owner through the explicit feed inspection, X navigation,
language, geography hierarchy, chart sizing, and pagination instructions in the
2026-08-31 through 2026-09-01 session

Protected production baseline:
`05552d030ab7369f3c9cc4b1464fc707868f88a0`

Prior approved interaction contract:
`docs/reference/2026-08-31-221955-feed-country-geography-bridgewright-target.md`

Approved flag and inspection-card visual reference:
`docs/ideation/2026-09-01-112352-country-flag-svg-reference.html`

The production page at the protected SHA remains authoritative for every
unnamed surface. This contract authorizes staging delivery only.

## Approved deltas

| Surface | Approved target |
| --- | --- |
| Feed inspection | Follower magnitude, every account-role badge, geography, and every visible sentiment, post-type, China/US nationalism, and unsanctioned signal use one immediate body-level dark inspection card and a normal pointer cursor, never the help/question-mark cursor. Hover or focus previews; click or tap pins; another activation transfers; repeat activation, outside input, or Escape dismisses. Copy is active-locale only, viewport-clamped, and contains every contributing brand behind a deduplicated icon. |
| Original-post navigation | A monochrome X logo immediately right of replies is the only control that opens the exact original post. Row bodies and metadata inspection never navigate to X; account-name links retain their separate destination. |
| Language and regions | Every text layer begins with a persisted-language token. English uses the ISO 639-1 primary code; zh-CN uses a centralized Simplified-Chinese name and distinguishes Traditional Chinese. English leading region directions abbreviate to N/S/E/W/NE/NW/SE/SW without mutating full accessible or canonical labels. |
| Geography hierarchy | Approved parent/child flags form a vertical 38-pixel tree. Parent and standalone flags share a centerline; the child is lower and rightward behind a CSS-border elbow. Taiwan retains the approved China-flag plus `TW · Taiwan` / `TW · 台湾` text treatment. The first account metadata begins two pixels farther below the follower count, with no empty role spacer. |
| One-day chart | Only the public homepage one-day total line uses stroke `4 / 3` and point radius `1`; its hit radius and all other chart windows and surfaces are unchanged. |
| Feed pagination | PostgreSQL applies the selected window, eligibility, and every supported filter before stable sort-aware keyset pagination. Each request defaults to 50 rows, derives continuation from one lookahead row, has no cumulative 500-row ceiling, and exhausts equal-sort ties exactly once. |

## Protected behavior

- Preserve the approved 215-symbol flag sprite, flag art, 14 × 7.875-pixel
  recommended treatment, normalized geography relationships, and Taiwan rule.
- Preserve text cycling, row selection, account links, engagement counts,
  signal ordering, filter semantics, chart freeze, refresh ownership, locale and
  timezone preferences, headline disclosure, pulse, and Top Voices outside the
  approved deltas.
- Preserve feed eligibility and the anonymous `/`, `/internal/`, and brand
  routes; no harvesting, provider calls, schema changes, or production release
  are authorized by this contract.

## Required state model

- Inspection: closed -> preview -> pinned -> transferred -> closed, with one
  live popover and safe owner removal during feed replacement.
- Navigation: row activation is inert for original-post navigation; X
  activation opens exactly that post with safe new-tab semantics.
- Geography: country, parent/child hierarchy, Taiwan-neutral text, region, and
  unresolved states in English and zh-CN, with SSR/replacement parity.
- Pagination: first page -> beyond 500 -> exhausted for all supported windows,
  including equal timestamp and equal like-count ties.

## Evidence contract

- Drive real anonymous `/` and `/feed/` callers in Chromium at desktop and
  390-pixel mobile widths in English and zh-CN.
- Prove immediate inspection for follower magnitude, role badges, geography,
  and signals; pin/transfer/dismiss behavior; normal pointer cursors; no native
  inspection titles; X-only outbound navigation; language persistence through text cycling,
  compact English region text, hierarchy geometry, metadata spacing, and no
  horizontal overflow.
- Traverse at least 625 matching equal-sort rows in 50-row pages, prove exact
  once-only identity coverage, and prove a selective result below the prior
  global 500-row boundary remains reachable.
- Prove the one-day Chart.js option delta and unchanged seven-day options and
  hit radius.
- The affected and candidate Bridgewright gates require zero failed, skipped,
  errored, missing, or unknown obligations at the bound source revision.
