---
title: Normalize Django API URLs and fix v2 UI bugs - Plan
type: fix
date: 2026-07-24
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ce-plan-bootstrap
execution: code
---

## Goal Capsule

Fix the 5 P0 and 5 P1 UI bugs found in the Django v2 vs Flask v1 comparison,
and normalize the API URL scheme in the process — drop the `v1` prefix and dot
separators, use descriptive paths without version or internal prefixes, and
collapse the two brand URL shapes into one. All changes stay inside `monitor/`
views, URLs, templates, and the JS in `monitor/static/` (already independent
copies from v1). The login wall and Cloudflare protection are unchanged and
outside scope.

Stop conditions: (1) home page renders with charts, sortable/cursor-paginated
feed, and filter-wired chart polls, (2) brand drill-down renders a working
stacked-area chart, (3) spend panel loads without 404, (4) feed rows carry
classification pills, role labels, and formatted follower counts, (5) all
`{% static %}` references are served by WhiteNoise (already fixed in
400e88f), (6) v1 Flask dashboard and launchd agents still green.

---

## Product Contract

### Summary

Normalize the Django URL surface to descriptive paths (`/feed/` not
`/api/v1/home.feed.json`) and fix the 5 P0 + 5 P1 bugs blocking the v2
dashboard at pushinweight.ai, all in one pass through `monitor/` since the URL
changes and bug fixes touch the same files.

### Problem Frame

The Django v2 site deployed to production but four core UI features are broken:
infinite scroll, sort, brand chart, and spend panel. Two more are degraded:
feed rows lack classification pills, and chart polls ignore filter state. The
root cause is twofold: (a) Django views were ported as stubs with simplified
wire shapes, but the client-side JS was retained unchanged from v1 and expects
the full v1 wire contract; (b) the URL scheme was copied verbatim from Flask v1
including the `v1` prefix and dot-separated path segments.

### Requirements

- R1. The multi-brand home page renders at `/` with working chart, feed, and
  filters.
- R2. The brand drill-down page renders at `/brands/<brand>/` with a working
  stacked-area chart and scoped feed.
- R3. Feed pagination uses cursor-based tokens matching the `pw-feed.js` contract
  (`cursor=<iso>|<tweet_id>`, response key `next_cursor`).
- R4. Feed rows carry classification pills (discourse, post type, sentiment,
  nationalism), human-readable role labels, and formatted follower counts.
- R5. Chart htmx polls send active filter state via `hx-vals`.
- R6. The spend panel route exists and returns a rendered partial (data stub
  is acceptable; full harvest-spend integration is deferred).
- R7. The URL scheme drops `v1`, replaces dots with slashes, separates data
  endpoints from htmx partials, and uses a single brand URL shape.
- R8. All static assets load via WhiteNoise (already fixed; verify not
  regressed).
- R9. v1 Flask dashboard and launchd agents are untouched.

### Scope Boundaries

In scope: `monitor/urls.py`, `monitor/views.py`, `monitor/templates/monitor/`,
`monitor/static/` (JS fetch URLs and htmx attributes).

Deferred to follow-up work: full spend-panel data (requires harvest-pipeline
integration), per-discourse stacked chart breakdowns (requires data-pipeline
work), configurable poll intervals, `POST` window/locale endpoints (JS uses
cookies and custom events, not POSTs).

Outside this product's identity: changes to the v1 Flask stack (`x_monitor/`),
the harvest pipeline, data ingestion, or the Google OAuth flow.

---

## Planning Contract

### Key Technical Decisions

- KTD1. **Cursor pagination in Django, not offset in JS.** The JS being
  rewritten anyway for URL changes provides a free choice. Cursor pagination
  handles real-time insertions correctly — new posts arriving between page
  fetches don't shift the offset window. Parse `cursor=<iso>|<tweet_id>` in
  the Django view, filter `WHERE (created_at, tweet_id) < (cursor_iso,
  cursor_tweet_id)`, and return `next_cursor`.
- KTD2. **Separate `_brand_chart.html` partial, not a conditional single
  template.** `pw-brand-chart.js` reads `data-brand-chart` on
  `canvas.home-brand-chart`. A separate partial keeps each JS module's DOM
  contract explicit and avoids conditional attribute logic in a shared
  template.
- KTD3. **Port the full classification enrichment pipeline.** Feed rows
  without classification pills are the most visible degradation. The bulk
  enrichment in `_enrich_posts_with_classifications` already fetches the
  data — the gap is in `_post_to_wire` serializing it and the template
  rendering it. Port the per-row fields (discourse keys, post type keys,
  role labels, followers_pretty, nationalism) to match the Flask
  `_feed_row_to_wire` output.
- KTD4. **URL scheme: descriptive paths, no prefix.** Data endpoints return
  `JsonResponse` at paths describing the resource (`/feed/`, `/chart/`,
  `/brand-chart/<brand>/`). HTML partials for htmx swaps use a `.html` suffix
  on the same paths (`/chart.html`, `/brand-chart/<brand>.html`, `/spend.html`).
  Brand is a query parameter on the feed endpoint (`/feed/?brand=deepseek`) and
  a path segment on the brand-chart endpoint. Brand pages: `/brands/<brand>/`
  for the unscoped drill-down; `/companies/<company>/brands/<brand>/` is the
  future company-scoped path for paid-tier access (routes are registered but
  deferred — they redirect to `/brands/<brand>/` for now). The old
  `/<company>/<brand>/`, `/_/<brand>/`, and all `/api/v1/` URLs are removed.
- KTD5. **The `pw-*.js` files in `monitor/static/` are the edit target.**
  They are already copies (400e88f), independent from `x_monitor/static/`.
  v1 JS is untouched.

### High-Level Technical Design

**URL map — before and after:**

| Purpose | Before | After |
|---|---|---|
| Multi-brand home | `/` | `/` |
| Brand drill-down | `/<company>/<brand>/`, `/_/<brand>/` | `/brands/<brand>/` |
| Company brand listing | — | `/companies/<company>/brands/` |
| Company-scoped brand | — | `/companies/<company>/brands/<brand>/` |
| Feed data | `/api/v1/home.feed.json` | `/feed/` |
| Chart data | `/api/v1/home.chart.json` | `/chart/` |
| Brand chart data | `/api/v1/brand.chart.json/<brand>` | `/brand-chart/<brand>/` |
| Chart partial | `/api/v1/home.chart.html` | `/chart.html` |
| Brand chart partial | (alias, shared view) | `/brand-chart/<brand>.html` |
| Spend partial | `/api/spend.html` (404) | `/spend.html` |
| Locale setter | `/api/v1/home.locale/<locale>` | `/locale/<locale>/` |
| Window setter | `/api/v1/home.window/<n>` | `/window/<n>/` |

**Data flow — feed pagination:**

```mermaid
sequenceDiagram
    participant Browser
    participant pw-feed.js
    participant /feed/
    participant Django ORM
    participant PostgreSQL

    Browser->>pw-feed.js: scroll to sentinel
    pw-feed.js->>pw-feed.js: readCursorFromLastRow(tbody)
    pw-feed.js->>/feed/: GET ?cursor=iso|tweet_id&sort=created_at&order=desc&limit=50
    /feed/->>Django ORM: Post.objects.filter(created_at__lte=iso, tweet_id__lt=tweet_id).order_by('-created_at', '-tweet_id')[:50]
    Django ORM->>PostgreSQL: SELECT ... WHERE (created_at, tweet_id) < ($1, $2) ORDER BY created_at DESC, tweet_id DESC LIMIT 50
    PostgreSQL-->>Django ORM: rows
    /feed/-->>pw-feed.js: {"rows": [...], "next_cursor": "iso|tweet_id", "has_more": true}
    pw-feed.js->>pw-feed.js: state.cursor = payload.next_cursor
    pw-feed.js->>Browser: append rows to tbody
```

**Data flow — chart with filters:**

```mermaid
sequenceDiagram
    participant htmx
    participant /chart.html
    participant Django View
    participant pw-chart.js

    htmx->>/chart.html: GET + hx-vals filters
    Django View->>Django View: TruncDate aggregation + filter narrowing
    Django View-->>htmx: <canvas data-home='{payload}'>
    htmx->>pw-chart.js: htmx:afterSwap → renderAll()
    pw-chart.js->>pw-chart.js: readPayload(canvas) → draw Chart.js
```

### Implementation Units

#### U1. Rewrite URL scheme

- **Goal:** Replace all Django routes, template htmx attributes, and JS fetch
  URLs with the new scheme. No old URLs remain reachable.
- **Requirements:** R7, R8.
- **Dependencies:** None.
- **Files:**
  - `monitor/urls.py` — rewrite all `path()` registrations
  - `monitor/views.py` — update view function signatures (brand from kwarg
    or query param), rename for clarity
  - `monitor/templates/monitor/home.html` — update `hx-get` attributes
  - `monitor/templates/monitor/brand_home.html` — update `hx-get` attributes
  - `monitor/static/pw-feed.js` — update `fetchBatch()` URL, `buildQuery()`
    params, `onLocaleChange()` URL
  - `monitor/static/pw-chart.js` — update hardcoded URL in
    `refetchChartWithFilters()` (`/api/v1/home.chart.html` → `/chart.html`)
  - `monitor/static/pw-brand-chart.js` — update hardcoded URL in
    `refetchBrandChartWithFilters()` (`/api/v1/home.brand.chart.html` →
    `/brand-chart/${brandId}.html`)
  - `monitor/static/pw-locale-toggle.js` — update locale/window POST URLs
    (`/api/v1/home.locale/<locale>` → `/locale/<locale>/`,
    `/api/v1/home.window/<n>` → `/window/<n>/`), or switch to
    client-side cookie setting
  - `monitor/static/pw-filter-store.js` — verify no hardcoded URLs
  - `monitor/static/pw-locale-toggle.js` — update any URL construction
  - `monitor/static/dashboard.js` — verify no hardcoded URLs (31 lines,
    staleness indicator — likely unchanged)
- **Approach:** Start with `urls.py` to establish the new route table, then
  update templates, then JS. The URL contract is defined in KTD4 and the
  table above. All old routes disappear — no redirects (the site has
  no external consumers or bookmarked API URLs). Brand routes collapse:
  `/brands/<brand>/` is the only shape. The view receives brand as a kwarg
  from the URL pattern.
- **Patterns to follow:** Existing `monitor/urls.py` structure (flat
  `urlpatterns` list), `monitor/views.py` function-based views with
  `@login_required`.
- **Test scenarios:**
  - Happy: `GET /` returns 200 with multi-brand home shell.
  - Happy: `GET /brands/deepseek/` returns 200 with brand drill-down.
  - Happy: `GET /feed/` returns JSON with `rows` and `next_cursor`.
  - Happy: `GET /chart/` returns JSON with `days`, `series`, `colors`.
  - Happy: `GET /chart.html` returns HTML partial with `<canvas data-home>`.
  - Happy: `GET /spend.html` returns 200 (stub partial, not 404).
  - Edge: `GET /brands/nonexistent/` returns 404.
  - Edge: Old URLs (`/api/v1/home.feed.json`, `/_/<brand>/`) return 404.
- **Verification:** `python manage.py check` exits 0. Manual browser: every
  page and htmx partial loads without 404s in the network tab.

#### U2. Fix cursor-based feed pagination

- **Goal:** `pw-feed.js` infinite scroll works — scrolling to the sentinel
  fetches the next page, sort headers re-fetch with new sort/order, and
  the feed never repeats the first page.
- **Requirements:** R3.
- **Dependencies:** U1 (URLs must be live before testing pagination).
- **Files:**
  - `monitor/views.py` — rewrite `home_feed_json` and `brand_feed_json`:
    parse `cursor` param, apply cursor filtering, read `sort`/`order`
    params, return `next_cursor` instead of `next_offset`
  - `monitor/static/pw-feed.js` — update `buildQuery()` to send `sort` and
    `order` with the Django-recognized param names; update response handling
    if the Django JSON keys differ from what the JS currently reads
  - `tests/test_views.py` — new: test cursor pagination, sort, and filter
    parameter parsing
- **Approach:** The Django view parses `cursor=<iso>|<tweet_id>` by splitting
  on `|`. Cursor filter: `Q(created_at__lt=iso) |
  Q(created_at=iso, tweet_id__lt=tweet_id)`. Sorts supported: `created_at`
  (asc/desc), `like_count` (asc/desc). Default: `created_at` desc. Response
  shape: `{rows, next_cursor, has_more, applied_filters, locale}`. The
  `readCursorFromLastRow()` in `pw-feed.js` constructs the cursor from the
  last visible row's `data-created-at-iso` and `data-tweet-id` — the Django
  response must include `created_at_iso` and `tweet_id` in each row so the
  JS can build the next cursor from DOM (this already works).
- **Patterns to follow:** Flask `serialize_feed_page()` in
  `x_monitor/dashboard.py` for cursor parsing logic, existing Django
  `_get_feed_posts()` ORM query pattern.
- **Test scenarios:**
  - Happy: `GET /feed/?limit=20` returns 20 rows with `has_more: true`
    and a valid `next_cursor`.
  - Happy: `GET /feed/?cursor=<valid>&limit=20` returns the next 20
    distinct rows (no overlap with first page).
  - Happy: `GET /feed/?sort=like_count&order=desc` returns rows ordered
    by like_count descending. Cursor pagination only applies to the default
    sort (`created_at`); `sort=like_count` falls back to offset-based
    pagination because the DOM cursor is always `created_at|tweet_id`.
  - Edge: `GET /feed/?cursor=<invalid>` returns first page (graceful
    degradation).
  - Edge: `GET /feed/?limit=0` returns empty rows.
  - Edge: Last page returns `has_more: false` and `next_cursor: null`.
  - Integration: `GET /feed/?brand=deepseek` returns only posts
    associated with that brand.
- **Verification:** Manual browser: scroll feed to bottom, observe new rows
  load without duplicates. Click sort header, observe re-fetch. Inspect
  network tab for correct `cursor` and `next_cursor` values.

#### U3. Fix chart endpoints and partials

- **Goal:** Multi-brand chart renders with correct data. Brand drill-down
  stacked-area chart renders (currently a blank element because
  `pw-brand-chart.js` can't find its canvas). Chart polls send active
  filter state.
- **Requirements:** R1, R2, R5.
- **Dependencies:** U1 (new chart URLs).
- **Files:**
  - `monitor/templates/monitor/_home_chart.html` — unchanged (correctly
    produces `<canvas class="home-chart" data-home='...'>`)
  - `monitor/templates/monitor/_brand_chart.html` — new: produces
    `<canvas class="home-brand-chart" data-brand-chart='...'>`
  - `monitor/views.py` — split `home_chart_json` into two views:
    a data endpoint returning `JsonResponse` and an HTML partial endpoint
    returning `render()`. Same for brand chart. Add `granularity` field
    (`"minute"` for 1d window, `"day"` otherwise). Fix 1d day-label
    ordering (oldest-first). Add `stacked` to home chart payload (stub
    empty dicts per brand — full discourse breakdown is deferred).
  - `monitor/templates/monitor/home.html` — add `hx-vals` to chart region,
    include `_home_chart.html` in initial render (no placeholder flash)
  - `monitor/templates/monitor/brand_home.html` — add `hx-vals` to chart
    region, include `_brand_chart.html` in initial render
  - `monitor/static/pw-chart.js` — update hardcoded URL in
    `refetchChartWithFilters()` (line ~245: `/api/v1/home.chart.html` →
    `/chart.html`)
  - `monitor/static/pw-brand-chart.js` — update hardcoded URL in
    `refetchBrandChartWithFilters()` (line ~213:
    `/api/v1/home.brand.chart.html` → `/brand-chart/${brandId}.html`);
    update htmx URL construction for `/brand-chart/<brand>/`
- **Approach:** The URL split is the key change — `.json` routes now actually
  return `JsonResponse`, `.html` routes return `render()`. The home chart
  view already renders an HTML partial (just with a misleading `.json`
  URL); split it into two thin views sharing a `_build_chart_payload()`
  helper. Create `_brand_chart.html` with `data-brand-chart` instead of
  `data-home` so `pw-brand-chart.js`'s `readPayload()` finds it. Fix the
  1d window label ordering by generating labels from 24h ago forward.
- **Patterns to follow:** Flask `serialize_home_chart()` for payload shape,
  existing `_home_chart.html` for the brand partial structure.
- **Test scenarios:**
  - Happy: `GET /chart/?window=7` returns JSON with `days`, `series`,
    `colors`, `totals`, `granularity: "day"`, `stacked`, `window_days: 7`.
  - Happy: `GET /chart/?window=1` returns `granularity: "minute"` with
    288 buckets.
  - Happy: `GET /chart.html` returns HTML with `<canvas class="home-chart"
    data-home='...'>`.
  - Happy: `GET /brand-chart/deepseek.html` returns HTML with
    `<canvas class="home-brand-chart" data-brand-chart='...'>`.
  - Happy: Brand chart canvas renders when `pw-brand-chart.js` calls
    `renderAll()`.
  - Edge: `GET /brand-chart/nonexistent/` returns 404.
  - Edge: 1d window `days` array is oldest-first.
  - Integration: Chart poll with filters selected in the control panel
    sends `?filters=<json>` and returns narrowed data.
- **Verification:** Manual browser: home chart renders on page load (no
  placeholder flash). Brand page chart renders with tabs. Select a filter
  checkbox — chart re-fetches with narrowed data.

#### U4. Enrich feed row serialization

- **Goal:** Feed rows carry the same classification pills, role labels, and
  formatted follower counts as the v1 Flask feed.
- **Requirements:** R4.
- **Dependencies:** U1, U2 (feed endpoint must be working).
- **Files:**
  - `monitor/views.py` — extend `_post_to_wire()` to serialize
    classifications (discourse keys, post type keys, sentiment keys,
    nationalism values per brand), account role label and followers_pretty,
    and unsanctioned flag. Update `_enrich_posts_with_classifications()`
    if needed to supply the data shape `_post_to_wire()` expects.
  - `monitor/templates/monitor/_feed_initial.html` — render classification
    pills for discourse, post type, cn_nationalism, us_nationalism per
    brand; render role_label and followers_pretty instead of raw role and
    followers_count
  - `tests/test_views.py` — new: test `_post_to_wire` output includes
    classifications, role_label, followers_pretty
- **Approach:** `_post_to_wire` currently creates empty stubs for
  classifications. The bulk enrichment in `_enrich_posts_with_classifications`
  already fetches `PostBrandSignal`, `PostBrandDiscourse`, and
  `PostUnsanctionedFlag` — the data is available but not serialized.
  Extend the wire dict to include per-brand `classifications` (discourse
  keys, post type keys, nationalism) and per-post `account` (role_label
  from the `BrandAccount` role field, `followers_pretty` formatted with
  a simple k/m suffix helper). The template renders these same DOM
  structures the Flask `_feed_initial.html.j2` produces (`cls-row`,
  `cls-pill`, `muted-cell` for followers).
- **Patterns to follow:** Flask `_feed_row_to_wire()` in
  `x_monitor/dashboard.py`, Flask `_feed_initial.html.j2` for DOM
  structure and CSS classes.
- **Test scenarios:**
  - Happy: A post with discourse=`genuine_hype` and post_type=`buzz_releases`
    renders both pills in the feed row.
  - Happy: A post with `cn_nationalism=mild_pro` renders the nationalism pill.
  - Happy: An account with `followers_count=15234` renders as "15.2k".
  - Happy: An account with `role=official` renders "Official" (via role_label).
  - Edge: A post with no classifications renders empty `cls-block` (no crash).
  - Edge: An account with null role renders empty string (no "None" text).
- **Verification:** Manual browser: feed rows show colored classification
  pills matching v1 appearance. Follower counts are human-readable.

#### U5. Fix template issues and add spend route

- **Goal:** Remaining template-level bugs fixed: `data-pw-filters` populated
  from context, initial chart canvas included (no placeholder flash), htmx
  trigger on spend panel includes `load`, and `/spend.html`
  routes exist.
- **Requirements:** R1, R2, R6.
- **Dependencies:** U1 (routes), U3 (chart partials exist).
- **Files:**
  - `monitor/views.py` — add `spend` view (returns stub partial with
    placeholder text), pass `applied_filters` to home and brand_home context
  - `monitor/urls.py` — add spend routes
  - `monitor/templates/monitor/home.html` — set `data-pw-filters` from
    context, include `_home_chart.html` in initial render, fix spend
    `hx-trigger` to `load every 60s`
  - `monitor/templates/monitor/brand_home.html` — same fixes for brand page
  - `monitor/templates/monitor/_spend.html` — new: stub spend partial
    (placeholder text matching current stub)
- **Approach:** Each fix is a one-to-few-line change. The spend route maps
  to a view that renders a new `_spend.html` partial. The `applied_filters`
  context variable is JSON-serialized in the view and rendered into
  `data-pw-filters` via `|safe`. The initial chart include replaces the
  placeholder `<div>` with `{% include "monitor/_home_chart.html" %}` (and
  `_brand_chart.html` for the brand page). The htmx trigger fix is a
  one-word change: `every 60s` → `load every 60s`.
- **Patterns to follow:** Flask `home.html.j2` for `data-pw-filters`
  initialization, `_spend_panel.html.j2` for spend partial structure.
- **Test scenarios:**
  - Happy: `GET /` response body includes `data-pw-filters='{...}'` with
    active filters (not `{}`).
  - Happy: `GET /` response body includes `<canvas class="home-chart"`
    (not a placeholder div).
  - Happy: `GET /spend.html` returns 200 with spend panel HTML.
  - Happy: Spend panel htmx triggers on page load (not just after 60s).
  - Edge: `data-pw-filters` is valid JSON parseable by `pw-filter-store.js`.
- **Verification:** Manual browser: page source shows `data-pw-filters` with
  JSON. Chart canvas visible immediately on load (no flash). Spend panel
  loads on page open. Network tab shows no 404 for spend route.

---

## Verification Contract

- `python manage.py check --deploy` exits 0.
- `python manage.py migrate --check` shows no pending migrations.
- `pytest tests/test_views.py -x` passes (new and existing tests).
- Manual browser flow on local `runserver` (or Render preview):
  - Google login → multi-brand home: chart renders, feed loads, scroll
    loads next page
  - Click brand chip → brand page: stacked chart renders, tabs switch
  - Toggle filter checkboxes → chart re-fetches with filters, feed
    re-fetches with filters
  - Sort header click → feed re-orders
  - Locale toggle → feed text switches language, labels update
  - Spend panel loads without 404
- Static files: `curl -sI http://localhost:8000/static/dashboard.css`
  returns 200 (WhiteNoise serving from `staticfiles/`).
- All old URLs return 404: `/api/v1/home.feed.json`,
  `/_/deepseek/`, `/<company>/<brand>/`.

---

## Definition of Done

- U1–U5 implementation units are complete.
- All 5 P0 bugs from the code review are fixed: infinite scroll (#1),
  sort (#2), brand chart rendering (#3), spend route 404 (#4), chart
  poll filters (#5).
- All 5 P1 bugs are fixed: classification pills in feed (#6), role and
  follower display (#7), `data-pw-filters` from context (#8), chart
  `granularity` field (#9), brand chart `tab_datasets` shape (#10).
- P2 items #11 (1d label ordering) and #12 (initial canvas flash) are
  fixed. P2 items #13 (empty filter semantics) and #14 (window/locale
  POST endpoints) remain as documented deferred items — #13 matches
  the Flask behavior after the fix, #14 is unused by the JS.
- P3 items #15 (hardcoded poll_seconds) and #16 (spend htmx trigger)
  are fixed.
- No regressions in v1 Flask dashboard or launchd agents.
