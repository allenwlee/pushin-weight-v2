# Production filter and feed Bridgewright target contract

Approval status: APPROVED

Approved by: project owner through the explicit six-item production-change
instruction in the 2026-08-19 session

Protected production baseline: `d821c4b7188c7df8100efec7d21195d9e1277d58`

Prior approved mockup contract:
`docs/reference/2026-08-19-132714-v24-bridgewright-target.md`

This contract feeds a narrow production delta into Bridgewright. The live
production behavior at the protected baseline remains authoritative for every
surface not explicitly named below. The V24 mockup remains context for its
previously approved controls; it is not a whole-page replacement target.

## Approved production targets

| Surface | Approved target |
| --- | --- |
| Filter order and post type | The named pills appear left-to-right as Brands, Sentiment, Post Type, Lang, Role, Nationalism. The still-required Discourse pill and existing Unsanctioned pill remain available after that named sequence. Post Type uses the existing `post_types` filter state and existing chart/feed request paths. |
| Chinese filter dropdowns | Under zh-CN, all visible filter-dropdown controls and taxonomy choices use Simplified Chinese labels. Stable machine values and request payload keys do not change. Brand proper names may use their existing localized registry names. |
| Uncategorized discourse | Discourse exposes a localized synthetic `uncategorized` choice. It matches posts with no discourse classification in both feed and chart filtering, and composes as OR with selected classified discourse values. Existing discourse keys keep their meaning. |
| Commentary persistence and feed text cycle | Add nullable `posts.commentary_zh_cn` and `posts.commentary_en` columns. Persist the existing translator `cn_equivalent` output to `commentary_zh_cn`; normalize blank and `N/A` output to `NULL`. Do not populate `commentary_en` yet. In zh-CN, advance through available Chinese commentary, literal Chinese, then English, and wrap. Missing or duplicate layers are skipped rather than relabeling literal translation as synthesis. The text interaction does not open X. |
| Feed row link | Clicking non-interactive whitespace/content in a feed row opens that row's X post. Clicking the text-cycle element, handle/link, or signal column does not trigger the row link. |
| Locale selection | Selecting English activates only English. Original remains a separate explicit locale and is not auto-selected with English. |

## Explicit non-targets

- The production Chart.js component is not a visual, structural, calculation,
  scale, series, interpolation, legend, or data-source target in this batch.
  It may change only enough to apply the existing `post_types` filter and the
  new synthetic `discourse=uncategorized` predicate.
- The production feed layout, pagination, sorting, metadata, tinting,
  classification markers, endpoint, and data ordering are not targets. Only
  the text-cycle and scoped row-link interactions listed above may change.
- Classifier behavior, translator prompts/calls/models, harvest cadence and
  fetch behavior, headline worker, all other database schema, stored taxonomy
  keys, authentication, deployment topology, and V24 control behavior are not
  targets. No historical commentary backfill or live LLM spend is approved.
- No static graph path, fixture post, placeholder value, or mockup-only data
  attribute is a production target.

Do not replace a production component with mockup scaffolding or regress any
behavior outside the approved-target table.

## Regression net

- Assert the pill order and presence through the real Django `/` route.
- Assert every zh-CN dropdown's visible option text is localized while its
  checkbox values remain stable machine keys.
- Exercise classified, uncategorized, mixed, and empty discourse selections
  through both feed matching and the existing Chart.js payload request path.
- Exercise commentary -> literal Chinese -> English -> commentary in a real
  browser, including server-rendered and refreshed feed rows. Assert blank
  `commentary_en` does not create an English synthesis layer.
- Exercise the production `CycleRunner` with the existing translator output
  and assert `cn_equivalent` reaches `commentary_zh_cn` while
  `commentary_en` remains `NULL` and LLM call shape is unchanged.
- Exercise row whitespace, text, handle, and signal clicks independently and
  assert only row whitespace opens the post URL.
- Assert exactly one locale button is active for English, zh-CN, and Original.
- Preserve one live Chart.js canvas, its existing rich payload, and the
  existing live `/chart.html` and `/feed/` consumers.

## Approval boundary

Approval applies only to this written delta. It does not approve the separate
substantial Chart.js batch, staging, deployment, or production release.
