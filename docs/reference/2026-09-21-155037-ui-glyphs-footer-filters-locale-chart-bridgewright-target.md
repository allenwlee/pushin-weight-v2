# UI glyphs, footer, filters, locale, and chart Bridgewright target contract

Approval status: APPROVED

Approved by: project owner through the explicit glyph selections and the
footer, filter, locale, and incomplete-day chart instructions in the
2026-09-21 session

Protected production baseline:
`91faac5b34a4eeed63a8590c88ea53fe29b6a103`

Prior approved interaction contract:
`docs/reference/2026-09-01-114311-feed-inspection-pagination-bridgewright-target.md`

Approved glyph reference:
`docs/reference/2026-09-21-123711-selected-taxonomy-glyphs.svg`

The production page at the protected SHA remains authoritative for every
unnamed surface. This contract authorizes delivery through production.

## Approved deltas

| Surface | Approved target |
| --- | --- |
| Taxonomy glyphs | The selected audience-topic and product-category symbols from the approved SVG reference replace their current equivalents. The Role `Other` row keeps an empty icon-width slot so its text aligns without displaying a fake glyph. |
| Footer | Every full public page ends in normal document flow with the exact muted sentence `Made with ❤️ in Yokohama. v<runtime package version>.`; the version comes from installed package metadata, not duplicated template text. |
| Filter bulk actions | Brand and language retain their existing All/Clear affordances. Sentiment, post type, role, product, and audience-topic filters expose localized All, Clear, and Other only actions. One Other-only action makes one atomic filter update and selects only that family's residual rows. Explicit `other`, classified-but-empty product/topic signals, and unclassified records remain distinct values with OR-within and AND-across semantics. |
| Locale selector | The selector is exactly `en`, `中文`, `日本語` in that order in every locale. Its labels are fixed autonyms. The Original selector is removed, and stale `original` preferences normalize to English without changing unrelated preferences. |
| Incomplete day | For windows longer than one day, only the final total-line segment into today is dotted. The one-day chart and all earlier segments retain their existing stroke. |

## Protected behavior

- Preserve all production layout, feed, chart, filter, persistence, refresh,
  pagination, inspection, and navigation behavior outside the approved deltas.
- Preserve classifier provenance: a classified empty product/topic set is not
  the same as an unclassified, pending, failed, or context-missing result.
- Preserve anonymous `/`, `/internal/`, and brand routes and their existing
  access behavior.
- No harvesting, provider calls, schema changes, or taxonomy-key changes are
  authorized by this contract.

## Required state model

- Each classification family supports all -> clear -> other-only -> all, with
  exactly one committed change per action.
- Post type Other maps to explicit `other` plus unclassified; product and
  audience Other map to classified-empty plus unclassified; sentiment Other
  maps to unclassified; role Other maps to the explicit role value.
- Locale is one of English, Simplified Chinese, or Japanese; legacy Original
  input normalizes to English.
- The daily chart segment state is solid for completed dates and dotted only
  for the last segment whose destination is the current partial day.

## Evidence contract

- Drive the real anonymous homepage in Chromium at desktop and 390-pixel
  mobile widths and verify the selected runtime glyph mappings, Role alignment,
  localized atomic bulk actions, fixed locale autonyms, legacy preference
  normalization, footer text and normal-flow geometry, and chart segment style.
- Exercise the reference model for every residual value and prove that explicit
  Other, classified-empty, and unclassified partitions remain distinct.
- Run the Bridgewright performance profile for desktop and mobile against the
  exact staged candidate, including Lighthouse, web-vitals, DOM, network, and
  immutable flag-sprite checks already owned by that profile.
- The affected and candidate Bridgewright gates require zero failed, skipped,
  errored, missing, or unknown obligations at the bound candidate revision.
