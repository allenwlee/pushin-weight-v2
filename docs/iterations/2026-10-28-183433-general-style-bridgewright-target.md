# General-style homepage, General page and /dashboard/each Bridgewright target contract

Approval status: APPROVED

Approved by: project owner through owner items 1–43 recorded during the
2026-10-22 to 2026-10-27 prototype review sessions, and the 2026-10-28
instruction to port them to production ("lfg with our updates to general,
homepage, dashboard").

Protected production baseline:
`e5edf737fd29666ec470ae55da5aefd69d4f0211`

Prior approved interaction contract:
`docs/iterations/2026-09-21-155037-ui-glyphs-footer-filters-locale-chart-bridgewright-target.md`

Approved requirements record (snapshot of the owner's live record):
`docs/iterations/2026-10-28-183433-general-style-owner-requests-snapshot.md`
(SHA-256 `ebcd50dcca78f5f81145c74566709bc05372bb02b21497f66fabef0194dadee0`)

Approved net-change list (snapshot):
`docs/iterations/2026-10-28-183433-general-style-net-changes-snapshot.html`
(SHA-256 `268387ebb13341c6eeb5ef03d64aac19eca5971e0ed64228e72308d9a6718d38`)

Approved visual reference: the owner-reviewed prototype relay and its
stylesheet and shell (`.context/compound-engineering/ce-prototype/2026-10-22-homepage-general/01-general-skin/screens/`
in the authoritative checkout, git-ignored) and the locked logo assets in
`.context/compound-engineering/ce-prototype/2026-10-26-decagon-line-logo/assets/`.
For every surface named below, the prototype's final state replaces
`docs/ideation/mockups/v24.html` as the oracle. The production page at the
protected SHA remains authoritative for every unnamed surface. This contract
does not authorize delivery beyond what the owner separately requests.

## Approved deltas

| Surface | Approved target |
| --- | --- |
| Page chrome (homepage, /dashboard/each) | General's visual system: DM Sans and Newsreader, General tokens, 18px white panels on a `#f0f2f5` page, white full-width masthead, 1440px measure, 1320/1160/960/700px breakpoints. A left icon rail (General, Trending, Posts by brand, Trend summary, Latest, Pro current) with `#1c1e21` glyphs expands on desktop and becomes a drawer at 700px and below. Labelled Window, Clock and Language controls. Trending bar without heading; "Posts by brand" and feed headings kept; "Filters" label; trend summary in General's story style; feed as a card grid; chart, summary, feed order at 960px and below. No bronze; muted status labels; mixed and official glyphs `#d97706`. |
| Logo and title | The rounded-handle line mark (1px non-scaling lines) replaces `#mark-quiet` and the favicon sitewide. On the homepage, /dashboard/each and General the wordmark is PUSHINWEIGHT in DM Sans italic capitals at 15px, PUSHIN 500 with 0.06em tracking and WEIGHT 800 with 0 tracking; 走个量 is removed from those mastheads; tab title and drawer label read PUSHINWEIGHT. |
| Brand identity | Brand colors come from brand data (Artificial Analysis palette plus four own-identity colors). Brand logos appear in the chart legend, a per-post logo row above the sentiment signals and General's tracked-brand pills; never in the trending bar. Legend and logo names use localized display names. |
| Posts-by-brand chart | No tooltip. Hover, keyboard focus or a pointer within 8px of a line focuses a brand (others' lines 24%, legend 56%, counts in line color, focused line solid). Desktop click pins until a click that hits no line or legend entry; Enter/Space toggles and Escape releases a pin; touch taps (16px) toggle focus. Always-on ping beacons per brand shape at the latest slot (reduced motion: still shapes). Right y axis without border, 16px end gap, monotone curves, `[1, 3]` dotted `#dfe4ec` gridlines, no point markers with an 8px hit radius, fixed 300/240/200px canvas box. Fixed per-brand dash pattern and beacon shape with SVG legend swatches. 1-day axis ends at the last fully harvested bucket and steps back whole hours; localized date axes on 7/30/365 days. |
| Hover-freeze (amends `docs/iterations/2026-08-28-181416-chart-hover-freeze-bridgewright-target.md`) | Only the tooltip display is superseded. Clicking a real 1-day point still freezes the half-open five-minute bucket, pauses refresh, refetches the brand-only bucket feed, unselects the locale buttons, and shows the local/Beijing slot in the feed title; release paths are unchanged. |
| Times and copy | English 12-hour lowercase times ("5:36am"), Chinese and Japanese 24-hour, everywhere times are formatted. Dropdown glyph spacing; "Geopolitical Framing" header; capitalized "National Stance"; globe help icon removed; "3rd Party Brand Promotions"; Brands tabs "Others / Giant" (labels only); "Language"; "Audience Topic"; "Local"; short pending message in all three languages. |
| Flags | Hairline edge on white cards and in dropdowns; drawn at 3:2 by narrowing the existing sprite (option B; owner's A/B/C choice still open). Scroll-loaded rows keep flags under collectstatic-hashed names. |
| General page | Human view: gray page, white masthead, rail and panels. Agent view keeps its dark palette. Both: locked lockup, title, drawer label; tracked-brand pill logos. "Weights: Open \| Closed" unchanged. |
| /dashboard/each | Homepage chrome and copy; chart in a white panel with pill tabs ("Language", "3rd Party Brand Promotions"), shared axis and grid styling, monotone, no points, 1px area outlines, axes from payload dates keeping the newest tick; category tooltip kept; no brand-line features. |
| Footer | "Made with ❤️ in Yokohama. v1.0.0b1 (0.2.0b1)." — public version, then the installed package version. No Beta badge. |
| Cyber-Quan visual regression | This delta supersedes the icon-only Cyber-Quan visual delta of `docs/iterations/2026-08-28-134649-cyber-quan-icons-bridgewright-target.md`. Its prechange-to-candidate icon-delta comparison is retired; the recaptured candidate goldens remain the visual regression check and require owner review. |

## Protected behavior

- Preserve every existing homepage, /dashboard/each and General feature: window,
  clock and locale switching; filters, lens values and persistence; the
  60-second chart refresh; hover-freeze feed narrowing; infinite scroll;
  inspection popovers; headline disclosure; Pro routes.
- Preserve chart, dashboard and feed payload keys and values, brand order
  (Meta first), Giants membership and the default brand selection, except the
  listed copy strings.
- `/internal/`, `/brands/<brand>/` and post detail pages change only through the
  shared mark, favicon and footer.
- No harvesting, provider calls, schema changes, production data writes or
  taxonomy-key changes are authorized by this contract.

## Required state model

- Chart focus: idle, hover, pinned, touch-focus; transitions per the plan's
  state diagram, including pin persistence across the 60-second refresh,
  pin release when a refresh or filter removes the brand, and keyboard
  Enter/Space/Escape.
- Hover-freeze: unchanged from the prior contract except the tooltip.
- Rail: collapsed, expanded (desktop), drawer open and closed (700px and
  below).
- Locale: English, Simplified Chinese and Japanese, with 12-hour and 24-hour
  time formats.

## Evidence contract

- Drive the real anonymous `/`, `/dashboard/each` and `/general/` routes in
  Chromium at 1440, 1100 and 390 pixels in English, Simplified Chinese and
  Japanese; assert computed styles and geometry taken from the prototype's
  final values, beacon presence, focus, pin, keyboard and touch behavior,
  and the absence of any third-party request.
- Compare server outputs against the pre-port baseline in
  `tests/fixtures/general_style_baseline/`.
- The affected and candidate Bridgewright gates require zero failed, skipped,
  errored, missing or unknown obligations at the bound candidate revision, and
  the candidate performance measurement runs on the same revision.
- Automated mobile emulation is not physical-device approval. The owner's
  check on a physical iPhone, through a private review link, remains the
  physical proof for this delta.
