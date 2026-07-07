---
title: "feat: Pushin' Weight (走个量) home pages — multi-brand + per-company/brand vanity URLs"
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
execution: code
product_contract_source: ce-plan-bootstrap
---

## Goal Capsule

- **Objective**: Replace the existing treemap + combined + 9-card grid + per-brand drill-down dashboard with two new home pages that adopt the new product name **Pushin' Weight (走个量)**: (1) a multi-brand page at `/` and (2) a single-brand page at `/<company.nickname>/<brand.nickname>` (or `/_/<brand.nickname>` for brands with no company). The multi-brand page keeps the line-chart + control-panel + bottom-feed layout the user described; the single-brand page keeps the same shape but renders a stacked-area chart with 6 tabbed categories and a brand-scoped feed.
- **Authority hierarchy**: This plan supersedes `2026-06-19-003-feat-combined-chart-page-plan.md`, `2026-06-17-002-feat-finviz-treemap-front-page-plan.md`, and the per-brand drill-down routes in `dashboard.py`. Legacy routes are kept as 302 redirects to the new homes; legacy templates are deleted.
- **Stop conditions**: (1) `/` renders multi-brand line chart, control panel, and bottomless-scroll feed with locale toggle (zh_cn default / en / original) and time-period toggle (1d / 7d / 30d / 1y); (2) `/<company>/<brand>` and `/_/<brand>` render single-brand area charts with 6 tabs and brand-scoped feed; (3) all legacy routes redirect correctly; (4) all DB read paths survive without new queries beyond what's already in `serialize_combined_chart` + a new `serialize_feed_page`.
- **Execution profile**: Standard plan. Touches ~10 files. Research-light because all data sources already exist (per migration 019 / 022 / 026 / 027 / 028).
- **Tail ownership**: `ce-work` (or `/goal` equivalent) executes Implementation Units in order; PR-precedence line: implement to Definition of Done.

## Product Contract

### Summary

Adopt the new product name **Pushin' Weight (走个量)** across the dashboard. Two new home pages replace the four existing topbar views. The multi-brand page at `/` renders a combo line chart (one line per enabled brand, total posts per time bucket), a control panel with checkboxes for brands / discourse (10 keys) / post_type (6 keys) / account.role (3 keys) / us_nationalism (6) / cn_nationalism (6) / unsanctioned, and a bottom-feed of recent posts with translated + original columns side-by-side. The single-brand page at `/<company.nickname>/<brand.nickname>` (or `/_/<brand.nickname>`) renders an area chart with 6 stacked tabs (post_type, discourse, account.roles, us_nationalism, cn_nationalism, unsanctioned), the same control panel, and a brand-scoped feed. Locale toggle defaults to `zh_cn`; time-period toggle covers 1d / 7d / 30d / 1y. No auth layer in this plan — single-user desktop for now.

### Problem Frame

The current dashboard has four views (treemap, combined, 9-card grid, per-brand drill-down) scattered across three topbar tabs plus deep-link brand pages. The user is renaming the project to **Pushin' Weight (走个量)** — the name must appear in the chrome (header title + page `<title>`) and a fundamentally different home-page shape is wanted. The new shape — line chart + control panel + bottomless feed — is what the user described in the original brief: combo line chart with brand lines, control panel for filter selection, bottom-half feed with translated and original post columns side-by-side. The two pages are organized as multi-brand (compare all) and single-brand (drill into one). Multi-account auth is acknowledged as coming soon (per user direction 2026-07-06 session) but is explicitly **out of scope** for this round; the URL shape (`/<company>/<brand>`) and the absence of auth are coordinated so a follow-up auth plan can land without rework.

### Requirements

**A. Global chrome (applies to both pages)**

- R1. App name displays as `走个量` (Chinese) and `Pushin' Weight` (English) in the topbar; `<title>` carries the same. The locale toggle's default is `zh_cn`. Selected locale is persisted via the existing `locale` cookie (same pattern as `grid.html.j2`).
- R2. Time-period toggle covers `1d / 7d / 30d / 1y`. Default is `7d`. Persisted via a new `home_window` cookie (separately named from `polarity_window` and `combined_window` so the three do not collide). Allowed values: `(1, 7, 30, 365)`. Window cookie resolution follows the existing `_resolve_combined_window` shape — defensive: malformed/absent/out-of-range falls back to default; no clamp to `dashboard.window_days` (early days render as zero, matches the combined chart's D4 precedent).
- R3. The legacy route family is replaced: `/` becomes the multi-brand page (was treemap); `/combined`, `/grid`, `/treemap` (alias for `/`) all become 302 redirects to `/`; `/brand/<id>` and `/model/<id>` both become 302 redirects to the vanity URL for that brand.
- R4. Locale toggle UI: a 3-button toggle (`zh_cn | en | original`) in the topbar, server-side active state, POST form to `/api/set_locale` already in place. Default is `zh_cn`. Adds one new value to the locale enum: `original` (means "show `text` column directly, ignoring both translations"). The `normalize_locale` helper returns one of `("zh_cn", "en", "original")`.

**B. Multi-brand page at `/`**

- R5. Top half is split 2/3 (left) + 1/3 (right). Left = combo line chart. Right = control panel.
- R6. The combo line chart renders one line per enabled brand (via `enabled_models`), in the brand's `accent_color`. Y axis = total post count per bucket; X axis = time bucket (hourly for 1d window, daily for 7d / 30d, weekly for 1y). Hover crosshair shows total per brand at that bucket; tooltip line lists each brand's count for that bucket. Chart.js v4.4.0 (already loaded).
- R7. The control panel renders 6 checkbox groups:
  - Brands (one checkbox per `enabled_model`)
  - Discourse (10 keys: `genuine_hype, sarcasm, dunk_yingyang, self_deprecation, cope, fud, distillation_accusation, ai_slop_critique, absurdist_meme, advertising-marketing`)
  - post_type (6 keys: `buzz_releases, hands_on_usage, performance_comparisons, feedback_questions, advertising_marketing, event_announcement`)
  - account.role (3 keys: `official, staff, community`)
  - us_nationalism (6 keys: `none, mild_pro, pro, constructive_critical, anti, mixed`)
  - cn_nationalism (6 keys: same 6-step scale)
  - unsanctioned (single toggle, off by default — only when OFF, posts with any `posts_unsanctioned_flags.flag_set` are filtered out; when ON, only those posts are shown)
- R8. Brand line visibility is controlled by the Brands checkbox group (default all on). Discourse, post_type, account.role, nationalism, and unsanctioned toggles re-shape the multi-brand line's value per time bucket (i.e. the count is filtered to match the active selections) AND filter the feed rows. The chart and feed share a single filter state.
- R9. The bottom half is a bottomless-scroll feed. Initial render shows the first 50 most recent posts matching the active filters, sorted DESC by `posts.created_at`. Subsequent batches of 50 are loaded via IntersectionObserver on a sentinel row that fires `fetch('/api/feed.json?cursor=…&filter=…')`. Total row cap: 500 (after 500, the sentinel no longer triggers; the user sees "end of feed").
- R10. Feed columns (left to right): (a) `datetime (local)` — formatted to viewer's local TZ from `posts.created_at` ISO; (b) `brand.nickname(s)` — alpha-ordered comma-joined, hover shows `display_name_<locale>`; (c) translated text — uses `text_<locale>` if locale is `zh_cn` or `en`, else falls back to source `text`. Above translated text: a small subscript `translated from: [<lang_detected>]`. Below: `★ <like_count>`. Cell truncates to 2 lines / 140 chars; click expands the cell to 50% feed width with internal scroll; (d) original text — directly from `posts.text`, same truncation/expand behavior; (e) classifications — `{brand.nickname: {discourse: [list], sentiments: [list]}}` plus the `unsanctioned` flag pill when applicable; (f) account.handle + role label. Header row has up/down carats for sort. Default sort: `created_at DESC`.
- R11. The feed's "controls sync" requirement: when a control-panel toggle changes, both the chart's data refresh AND the feed's data refresh. The chart's poll keeps running on its existing htmx cycle; the feed re-fetches from row 1 with the new filter via a JS event (`pw:filter-change`) that the feed module listens to.

**C. Single-brand page at `/<company>/<brand>` and `/_/<brand>`**

- R12. Route resolves vanity URL: `/<company>/<brand>` looks up `brands.nickname = <brand>` joined to `companies.nickname = <company>` via `brands_companies`. Returns 404 if either fails. `/<brand>` is **not** a valid URL (a brand without a parent company uses `/_/<brand>`); `/<brand>` returns 404. `/_/<brand>` looks up `brands.nickname = <brand>` with no company; returns 404 if no match. The fallback `/_/` is reserved for future use (no behavior in v1 — returns 404 with a TODO marker).
- R13. Header is identical to the multi-brand page (R1, R2, R4 chrome). Brand display name appears in `<h1>走个量 · {brand.display_name_<locale>}</h1>` instead of the generic app title.
- R14. The single-brand line chart is a stacked-area chart with **6 tabs** on the top edge of the chart: `post_type (default)`, `discourse`, `account.roles`, `us_nationalism`, `cn_nationalism`, `unsanctioned`. Each tab is a separate stacked-area dataset summing to the brand's total posts at each time bucket. Tab color tokens for the 6 post_type keys, the 6 nationalism keys, the 3 account.role keys, and the 10 discourse keys are **all new additions to `dashboard.css`** (the existing palette only carries 9 sentiment/signal tokens, none of which map directly to the new taxonomy — see U9).
- R15. Control panel: identical to multi-brand page (R7). Per-brand defaults: brand is locked ON in the Brands checkbox group (the user's brand is always visible); all other brands are visible (default all on, same as multi-brand).
- R16. Feed: identical to multi-brand (R9, R10, R11) but filtered server-side to `brand.nickname = <brand>` (the brand scope is a server-side filter, not a client filter, so an operator cannot bypass by toggling).

**D. Naming (Pushin' Weight / 走个量)**

- R17. The dashboard's `<title>` becomes `走个量 · {display_brand_or_default}` and the topbar `<h1>` becomes `走个量 <small>Pushin' Weight</small>`. The `request_endpoint` stylesheet/CDN links are unchanged. Templates using `x-monitor` branding (e.g. `templates/treemap.html.j2`, `templates/grid.html.j2`, `templates/combined.html.j2`) are migrated to new names where the strings appear; the `_unattributed`/`xmonitor-*` paths and shells stay as-is (no naming drift in operational internals).

### Scope Boundaries

#### In scope

- The two new pages (multi + single brand).
- The legacy route replacements (R3).
- The locale toggle and time-period toggle in the topbar.
- The `home_window` cookie + `_resolve_home_window` helper.
- The `serialize_feed_page` data layer that hands the feed both initial rows and the cursor-based pagination shape.
- The `serialize_single_brand_chart` data layer that emits the per-tab stacked-area dataset.
- Cookie + state plumbing so the chart refreshes when the feed's filter changes (and vice versa).
- The new `--pt-*` and `--nat-*` CSS tokens in `dashboard.css`.
- A `pyproject.toml` / `setup.py` entry-point rename is NOT in scope. Internal Python package name stays `x_monitor` (the project name in `pyproject.toml` stays `x-monitor` for now; a follow-up rename + import-aliasing pass is a separate concern). External-facing product name is the only thing renamed.

#### Deferred for later

- **Auth layer (multi-account + per-company scoping).** A follow-up plan will add sessions, login route, and middleware that resolves a session to an accessible brand set. This plan keeps routes open for the single-user desktop case. URL shape (`/<company>/<brand>`) is chosen to be auth-ready — a follow-up plan can wrap middleware around route resolution without changing URLs.
- **`_<company>/_<brand>` ↔ display-name slugs.** The vanity URL uses the natural key (`<company.nickname>/<brand.nickname>`), not a localized display_name. i18n display names live in the chrome only. A follow-up plan can add `ncollections.slugify(display_name_en)`-based localized URLs without colliding with the natural-key version.
- **Vanity URL for companies (e.g. `/alibaba` for company-only view).** Not requested; the page model is multi-brand-first. A future company-detail page is a sibling plan.
- **Post-type / discourse category count display in the legend.** v1 hides exact counts in tooltips only; a separate plan can add a per-category count badge in the chart legend.
- **Bookmarking / sharing a specific filter state via URL.** v1 stores all filter state in component-local React-/vanilla-state; a follow-up plan can serialize filter state to a URL hash.

#### Outside this product's identity

- The legacy `x_monitor/` Python package name (operational, not user-facing). The `x_monitor` package continues to ship as `x-monitor` per CLAUDE.md; this plan does not rename imports, package metadata, or DB-migration filenames.
- The legacy `_unattributed` sentinel handling, the `enabled_models` config gate, and the `dashboard.window_days` cap on the home page (the home page uses the cookie window, not `window_days`).
- The existing `polarity_window` and `combined_window` cookies, which remain in place for the routes that still use them (`/api/treemap.*`, `/api/combined.*` are deleted in this plan; their cookies become dead state and can be cleared in a follow-up cookie-reset plan).

### Key Technical Decisions

- **KTD1**: `serialize_home_chart` is a NEW function in `dashboard.py` that mirrors `serialize_combined_chart`'s per-day bucketing loop (lines 728-823), but introduces a per-post filter predicate against the active discourse / post_type / role / nationalism / unsanctioned set. The payload shape `{days, series, stacked, applied_filters, totals}` is reused, not the function itself. **Rationale**: `serialize_combined_chart` has no `filters` kwarg; back-porting the filter narrowing into it would require a sentinel parameter that breaks its callers. Keeping two functions preserves the combined chart's existing API.
- **KTD2**: Feed pagination uses **bottomless scroll + JSON**, not htmx. The chart at the top half remains an htmx-poll (existing pattern), but the feed below loads via JS `fetch('/api/feed.json?cursor=…&filters=…&limit=50')`. Cursor is the `created_at ISO + post.tweet_id` of the last row in the previous batch (lexicographic on the two). **Rationale**: matches the user's "bottomless scroll" UX requirement and avoids the server-render-per-batch htmx pattern. The two halves of the page are deliberately independent — chart poll does not invalidate feed state and vice versa.
- **KTD3**: The control-panel state lives in a tiny vanilla-JS module `pw-filter-store.js` that broadcasts `pw:filter-change` events on `document`. Both the chart module and the feed module subscribe. Initial render bakes the default filter values from server-side Jinja (default all on); user toggles change the store, which emits the event, both modules react. **Rationale**: lightweight, no framework. The legacy dashboard ships zero JS framework; staying consistent.
- **KTD4**: Locale `original` is a new option, not a synonym for `en`. The dashboard already has `normalize_locale` returning `"en"` for unknown locales; we extend the supported set to `("zh_cn", "en", "original")` and the column lookup `_LOCALE_TO_COLUMN` to map `original` → source `text`. **Rationale**: the user explicitly wants a separate "show original" toggle distinct from English. A first-class key beats overloading `en`.
- **KTD5**: Brand-id resolution for the single-brand page uses a single store query joining `brands.brands_companies.companies` (with `LEFT JOIN` for brands that have no company match in the `/_/<slug>` case). The query is memoized per request via the existing `Store` connection; no new caching layer. **Rationale**: the brands_companies graph is small (29 brands, ~12 companies per the migration-029 plan). One query per request is fast.
- **KTD6**: The 6 tab datasets on the single-brand area chart are rendered as **6 stacked-area datasets on one Canvas, with the active tab's stacking shown and the other 5 datasets `hidden: true`**. Tab switch = toggle visibility + `chart.update('none')`. **Rationale**: matches the combined chart's `onHover` overlay pattern (KTD-D3 of the combined chart plan) — same Chart.js dataset-toggling trick, applied to tab visibility instead of hover state.
- **KTD7**: The `_unattributed` sentinel posts are still rendered in the feed (they have a brand-neutral scope: the multi-brand chart skips the sentinel — it's a brandless aggregate — but the multi-brand feed includes it under the brand cell as `_unattributed` with a muted style). The single-brand page never shows `_unattributed` (the brand page is brand-scoped). **Rationale**: matches the existing dashboard's per-brand query path (`Store.get_all_posts(m)` already excludes _unattributed for one m).
- **KTD8**: Vanity URL `/<company>/<brand>` returns 404 (not 302) when the brand doesn't belong to that company. The user expects `qwen` to be reachable only as `/alibaba/qwen`, not `/randomcompany/qwen`. **Rationale**: stricter contract; protects against URL guessability. The 404 template renders a small "走个量 · 未找到该品牌"的 message.
- **KTD9**: The legacy routes `/combined`, `/grid`, `/treemap` (alias for `/`) all 302 to `/`. `/brand/<id>` and `/model/<id>` resolve the brand, then 302 to `/<discovered-company>/<brand>` (or `/_/<brand>` for company-less). The redirect target uses `_resolve_vanity_url_for_brand(brand_id)` server-side. **Rationale**: no broken external links. The legacy _unattributed sentinel page (`/_unattributed`) becomes a 302 to `/` (the multi-brand page; sentinel has no company).
- **KTD10**: `pw:` event prefix is used for all custom events the dashboard emits (`pw:filter-change`, `pw:locale-change`, `pw:tab-change`). Keeps them greppable + distinguishes from htmx's `htmx:*` events. **Rationale**: tiny convention, no name collision, easy to grep later.

### Acceptance Examples

- **AE1**: At `/` on a fresh `x_monitoring.db` with `enabled_models = [minimax, qwen, glm, deepseek, …]`, the multi-brand line chart renders N lines (N = `len(enabled_models)`), each in its `accent_color`, summing to the brand's total post count per day for the 7-day default window. Hover shows per-brand counts in the tooltip. Control panel shows the 6 checkbox groups + the unsanctioned toggle. Feed loads 50 rows sorted DESC by `created_at`. Locale defaults to `zh_cn`; the brand column shows `display_name_zh_cn` for each row.
- **AE2**: Toggle `discourse=dunk_yingyang` off in the control panel. Both the chart's per-brand line values drop (some posts no longer counted) and the feed re-fetches from row 1 with the new filter. The `pw:filter-change` event fires once; the chart module re-aggregates locally without a server roundtrip; the feed module re-fetches the first 50.
- **AE3**: Navigate to `/alibaba/qwen`. Topbar brand name shows "通义千问" (zh_cn locale default). The single-brand area chart's default tab is `post_type`; the 6 post-type categories stack with their respective colors and total to the brand's daily post count. Tab clicks swap the stacked-area dataset. The control panel's Brands group locks `qwen` on (disabled checkbox) and shows all other brands on by default.
- **AE4**: Visit `/somecompany/qwen` where `qwen` is owned by `alibaba`. Returns 404 with the "走个量 · 未找到该品牌" page. Visiting `/randomcompany/minimax` (any non-alibaba) also returns 404.
- **AE5**: `/_/minimax` for a brand with no `brands_companies` row. Returns 200, renders the single-brand page. `_unattributed` does NOT render at `/_/_unattributed` because the sentinel is excluded from the brand query path; a request to `/alibaba/_unattributed` returns 404.
- **AE6**: Sort the feed by `like_count ASC` via header-row carat. Feed re-fetches with `?sort=like_count&order=asc`; rows render in ascending order; clicking again returns to `created_at DESC` default.
- **AE7**: Switch locale toggle to `original`. Translated-text column disappears (or shows the original text in that column with the lang_detected subscript) — the column layout still has both `translated` (showing original) and `original` (also showing original) cells but both highlight as source text. Original-text column behavior matches the current `en` behavior (translation fallback).
- **AE8**: Visit a legacy URL like `/combined` or `/brand/minimax`. Returns 302 to `/` or `/<discovered-company>/minimax` respectively. Reload preserves no state from the legacy URL (it's a thin redirect).

## Planning Contract

### High-Level Technical Design

This illustrates the intended layout and module boundary; not implementation code.

**Page layout (both pages share this shell; brand and feed differ in content):**

```
+------------------------------------------------------------+
| 走个量 Pushin' Weight    [zh_cn|en|original]  [1d|7d|30d|1y]    |  ← topbar (R1, R2)
+------------------------------------------------------------+
|  chart (top half: 2/3 left, 1/3 right)                     |
|  +---------------------+  +-------------------+           |
|  | Combo line chart    |  | Control panel:    |           |
|  |   (multi: 1 line    |  |  ☐ Brands         |           |
|  |    per brand)       |  |  ☐ Discourse      |           |
|  |   (single: stacked  |  |  ☐ post_type      |           |
|  |    area + 6 tabs)   |  |  ☐ account.role   |           |
|  |                     |  |  ☐ us_nationalism |           |
|  |                     |  |  ☐ cn_nationalism |           |
|  |                     |  |  ☐ unsanctioned   |           |
|  +---------------------+  +-------------------+           |
+------------------------------------------------------------+
|  feed (bottom half)                                       |
|  +-----+----------+---------+----------+------------+     |
|  | dt  | brand    | tr text | orig text| class      | hdl |
|  | ... |          |         |          |            |     |
|  +-----+----------+---------+----------+------------+     |
|  sentinel row → fires next 50 via fetch                  |
+------------------------------------------------------------+
```

**Vanity URL routing tree:**

```
/                                 → multi-brand page (R5–R10)
/combined                         → 302 → /
/grid                             → 302 → /
/treemap                          → 302 → /                    (legacy alias)
/brand/<brand_id>                 → 302 → _resolve_vanity(brand_id)
/model/<brand_id>                 → 302 → _resolve_vanity(brand_id)
/api/<...>                        → see "API surface" below
                                    (the legacy /api/treemap.*, /api/combined.*,
                                     /api/grid.*, /api/grid.html are deleted)
/<_>_<brand_id>                   → 404
/_/<brand_id>                     → single-brand (no-company path)
/<company>/<brand>                → single-brand
/<company>/<brand> with a non-   → 404
  matching company
/api/v1/home.chart.json           → filtered chart payload (multi-brand)
/api/v1/home.chart.html           → htmx partial for chart canvas
/api/v1/home.feed.json            → paginated feed (cursor=)
/api/v1/home.brand.chart.json    → single-brand area chart payload
/api/v1/home.window/<int:days>   → set home_window cookie, 303 back
/api/v1/home.locale/<locale>     → set locale cookie, 303 back
/api/v1/health                    → 200 JSON
```

**Module / file boundary (new files marked with ★):**

```
dashboard.py            — extends DashboardApp:
  + _resolve_home_window(req, default)   # mirrors _resolve_combined_window
  + serialize_home_chart(brands, posts, *, window_days, latest_run, filters)
  + serialize_single_brand_chart(brand, posts, *, window_days, latest_run, filters, tab)
  + serialize_feed_page(*, filters, sort, order, cursor, limit, brand_scope=None)
  + _resolve_vanity_url_for_brand(brand_id)  # joins brands_companies + companies
  + 6 new routes under _register_routes
★ templates/home.html.j2                — multi-brand page
★ templates/_home_chart.html.j2         — htmx partial for chart canvas
★ templates/brand_home.html.j2          — single-brand page
★ templates/_brand_chart.html.j2        — htmx partial for single-brand chart
★ templates/_feed_initial.html.j2       — first-batch Jinja render of feed rows
★ static/pw-filter-store.js             — vanilla-JS filter store + pw:filter-change event
★ static/pw-chart.js                    — multi-brand line chart (extends combined-chart.js pattern)
★ static/pw-brand-chart.js              — single-brand area chart with 6 tabs
★ static/pw-feed.js                     — bottomless-scroll feed renderer + IntersectionObserver
★ static/pw-locale-toggle.js            — topbar locale + window toggle hooks (uses existing /api/set_locale)
dashboard.css          — adds --pt-* (post_type) and --nat-* (nationalism) tokens
tests/test_home_chart.py              — unit tests for serialize_home_chart
tests/test_single_brand_chart.py      — unit tests for serialize_single_brand_chart
tests/test_feed_page.py               — unit tests for serialize_feed_page (cursor, filters, sort)
tests/test_home_routes.py             — route-level integration tests
tests/test_vanity_url.py              — vanity URL resolution + 404 cases
```

The chart payload shape (R1, R6, KTD1):

```yaml
{ days: [iso_date],                     # X axis buckets
  series: { brand_id: [int×N] },        # multi-brand lines (sum across selected filters)
  stacked: { brand_id: { signal: [int×N] } },  # per-brand per-signal breakdown (for hover overlay)
  applied_filters: { discourse, post_type, role, nationalism, unsanctioned },
  totals: { brand_id: int }             # for legend
}
```

The single-brand chart payload (R14, KTD6):

```yaml
{ brand_id, brand_display_name_<locale>, accent_color,
  days: [iso_date],
  tab_datasets: {
    post_type:    { category: [int×N] },
    discourse:    { category: [int×N] },
    account_roles:{ category: [int×N] },
    us_nationalism:{ category: [int×N] },
    cn_nationalism:{ category: [int×N] },
    unsanctioned: { category: [int×N] },
  },
  applied_filters,
  window_days,
}
```

The feed payload (R9, R10, KTD2):

```yaml
{ rows: [
    { tweet_id, created_at, lang_detected, text, text_en, text_zh_cn, like_count,
      brands: [{nickname, display_name, display_name_en, display_name_zh_cn}],
      classifications: {
        brand.nickname: {
          discourse:    [key1, ...],   # acts 1..N
          post_types:   [key1, ...],   # 1..N per migration 028
          sentiments:   [key1, ...],
          cn_nationalism: key,
          us_nationalism: key,
        }
      },
      unsanctioned: bool,
      account: {handle, role, role_label},
    }
  ],
  next_cursor: str | null,    # ISO+D dot tweet_id; null when end of feed
  applied_filters,
  sort, order,
}
```

### Implementation Units

### U1. Rename chrome + global dashboard config

- **Goal**: Apply the `走个量 / Pushin' Weight` product name to the topbar and `<title>` on every existing page (in this unit: legacy pages too, so the rename lands before the home pages replace them). Add the `home_window` and `locale=original` configs that the home pages use.
- **Requirements**: R1, R4, R17.
- **Dependencies**: —.
- **Files**:
  - `x-monitoring/x_monitor/dashboard.py` — add `APP_DISPLAY_NAME_ZH`, `APP_DISPLAY_NAME_EN`, expose to Jinja; extend `SUPPORTED_LOCALES` and `_LOCALE_TO_COLUMN` for `"original"`; add `_resolve_home_window(req, default)` + `ALLOWED_HOME_WINDOWS` + `HOME_WINDOW_COOKIE`.
  - `x-monitoring/x_monitor/templates/treemap.html.j2` — `<title>` and `<h1>` updated to `走个量`. Localized `<h1>` text via the active locale cookie.
  - `x-monitoring/x_monitor/templates/grid.html.j2` — same chrome changes.
  - `x-monitoring/x_monitor/templates/combined.html.j2` — same chrome changes.
  - `x-monitoring/x_monitor/templates/model_detail.html.j2` — same chrome changes.
  - `x-monitoring/x_monitor/dashboard.py` — add the new locale and home-window helpers; expose the constants to Jinja via a context processor.
- **Approach**: Add the new constants near `MODEL_DISPLAY_NAMES`. The chrome rename is mechanical — `<title>x-monitor — …</title>` becomes `<title>走个量 · …</title>` and `<h1>x-monitor</h1>` becomes `<h1>走个量 <small>Pushin' Weight</small></h1>`. The home-window + locale helpers mirror the existing `_resolve_combined_window` / `_resolve_polarity_window` patterns. `_resolve_home_window` does NOT clamp to `window_days` (the home page can show any of 1d/7d/30d/1y regardless of post history, like the combined chart's `D4`).
- **Patterns to follow**: `_resolve_combined_window` (mirror its defensive-cookie-reading shape).
- **Test scenarios**:
  - Happy path: `/api/v1/home.window/7` sets `home_window=7` cookie and 303s back; `curl -b "home_window=7" /` reads window=7.
  - Edge case: missing cookie → default (7).
  - Edge case: cookie `home_window=abc` → default.
  - Edge case: cookie `home_window=999` → default (out of allowed range).
  - Locale: `/api/v1/home.locale/original` sets locale cookie; `_pick_text(post, "original")` returns `(post["text"], False)`.
  - Locale: `normalize_locale("original")` returns `"original"` (not `"en"` fallback).
  - Chrome: title on every page starts with `走个量 ·`.
- **Verification**: `pytest tests/test_window_cookies.py` passes; manual `curl` to `/` shows `<title>走个量 · …`.

### U2. Home chart data layer (multi-brand)

- **Goal**: `serialize_home_chart(enabled_models, posts_by_brand, *, window_days, latest_run, filters)` returns the multi-brand chart payload (KTD1). Handles filter narrowing at row-inclusion step.
- **Requirements**: R6, R8.
- **Dependencies**: U1 (filter shape uses locale + window).
- **Files**:
  - `x-monitoring/x_monitor/dashboard.py` — add `serialize_home_chart`.
  - `x-monitoring/tests/test_home_chart.py` — new file.
- **Approach**: Mirror `serialize_combined_chart` data assembly. The filter narrowing is at the post-include step: a post is counted toward brand X at day D only if (a) it has a `posts_brands` row with brand X (already filtered by `enabled_models` loop), (b) the row's `discourse` key (if any) is in the active set, (c) the row's `post_type` keys overlap with the active set, (d) the row's `account.role` (via `accounts` join) is in the active set, (e) the row's `cn_nationalism` and `us_nationalism` keys are in their respective active sets, (f) the row's `posts_unsanctioned_flags` state matches the unsanctioned toggle. The unsanctioned filter is special: when unsanctioned=off, posts with flags are EXCLUDED; when unsanctioned=on, posts WITHOUT flags are excluded (i.e. only flagged posts count).
- **Patterns to follow**: `serialize_combined_chart` (precedent for `series` + `stacked` shape).
- **Test scenarios**:
  - Happy path: 5 enabled brands × 7 days of mixed signals → `days.length == 7`, `series` has 5 entries, each summing across active filters.
  - Filter narrows correctly: with only `discourse=[genuine_hype]` active, `series` per brand is smaller than default-all.
  - Edge case: brand with 0 matching posts in window → `series[brand]` is list of zeros, NOT omitted from chart.
  - Edge case: `latest_run` is None → falls back to wall-clock UTC (per `_parse_post_timestamp` contract).
  - Edge case: `filters={"unsanctioned": "only"}` → `series` only counts posts with `posts_unsanctioned_flags`; brand with no flagged posts in window renders as zero-line.
  - Integration: empty DB → all lines at zero, no error.
- **Verification**: `pytest tests/test_home_chart.py -q` passes; smoke-test `python3 -c "from x_monitor.dashboard import serialize_home_chart; print(serialize_home_chart(['minimax'], [], window_days=7, latest_run=None, filters={}))"` returns a dict with `len(days) == 7`.

### U3. Single-brand chart data layer (6 tabs)

- **Goal**: `serialize_single_brand_chart(brand_id, posts, *, window_days, latest_run, filters, tab)` returns the stacked-area payload for one brand + one tab (R14, KTD6).
- **Requirements**: R14, R8.
- **Dependencies**: U2 (filter shape consistent).
- **Files**:
  - `x-monitoring/x_monitor/dashboard.py` — add `serialize_single_brand_chart`.
  - `x-monitoring/tests/test_single_brand_chart.py` — new file.
- **Approach**: Same filter narrowing as U2 but the output keys are tab-datasets. Each tab maps to a `(category_field, color_token)` tuple:
  - `post_type` → 6 categories from `_DASHBOARD_POST_TYPE_KEYS` (with the 2 new keys from migration 027). Colors from new `--pt-*` CSS tokens.
  - `discourse` → 10 categories. Colors from existing `--bar-*` tokens (already populated for the 9 legacy keys; add `--bar-advertising-marketing`).
  - `account.roles` → 3 categories. Colors from new `--role-*` CSS tokens.
  - `us_nationalism` / `cn_nationalism` → 6 categories each. Colors from new `--nat-*` tokens.
  - `unsanctioned` → 2 categories (`flagged`, `unflagged`). Colors from `--yellow` and `--muted`.
- **Patterns to follow**: `serialize_combined_chart` for the per-day bucketing loop; `_load_role_labels` precedent for resolved taxonomy labels.
- **Test scenarios**:
  - Happy path: brand with 7 days of mixed classifications across all 6 tabs → 7-day series in each `tab_datasets` block.
  - Tab switch returns same shape (only the `tab` field differs in the output).
  - Edge case: empty brand (0 posts) → `days.length == window_days`, all-zero series, no error.
  - Edge case: brand with only 3 of the 6 post-type keys present → the other 3 series are zero-lists, NOT omitted from `tab_datasets.post_type`.
  - Integration: tab=default → `tab == 'post_type'`; passing `tab='discourse'` returns the discourse dataset with the discourse category set.
- **Verification**: `pytest tests/test_single_brand_chart.py -q` passes; `python3 -c "from x_monitor.dashboard import serialize_single_brand_chart; print(serialize_single_brand_chart('minimax', [], window_days=7, latest_run=None, filters={}, tab='post_type'))"` returns the expected shape.

### U4. Feed data layer (cursor pagination + filters)

- **Goal**: `serialize_feed_page(*, filters, sort, order, cursor, limit, brand_scope=None)` returns the bottom-half feed rows + a `next_cursor` (or null). Filters mirror U2.
- **Requirements**: R9, R10, R11, R16.
- **Dependencies**: U2 (filter shape), U3 (single-brand filter is a further narrowing on brand).
- **Files**:
  - `x-monitoring/x_monitor/dashboard.py` — add `serialize_feed_page`.
  - `x-monitoring/tests/test_feed_page.py` — new file.
- **Approach**: SQL CTE that joins `posts` + `posts_brands` + `brands` + `accounts` + (optional) `posts_brands_signals` + `posts_brands_discourse` + `posts_unsanctioned_flags`. Cursor is the `(created_at, tweet_id)` of the last row from the previous batch; the next query is `WHERE (created_at, tweet_id) < (?, ?)`. When `order='asc'`, the cursor advances upward instead. The full per-row shape matches the JSON contract in the High-Level Technical Design. `brand_scope` is set for the single-brand page; `None` for multi-brand (which means "any brand among the active Brand checkbox set").
- **Patterns to follow**: Store's existing query patterns in `store.py::get_all_posts` (precedent for the per-brand post fetch loop).
- **Test scenarios**:
  - Happy path: 50 most recent posts in DESC order, `next_cursor` non-null when more rows exist.
  - Cursor advances correctly: pass `cursor="2026-07-01T12:00:00+00:00:user-123"`, returns rows strictly after.
  - Sort: `sort=like_count&order=asc` returns ascending by `like_count`.
  - Filter: `filters={"discourse": ["genuine_hype"], "post_type": ["buzz_releases"]}` returns only posts matching both.
  - Edge case: empty DB → `rows=[]`, `next_cursor=None`.
  - Brand scope: `brand_scope="minimax"` returns only posts attributed to `minimax` even when other filters would otherwise include.
  - Hard cap: with limit=500 reached, `next_cursor=None`.
- **Verification**: `pytest tests/test_feed_page.py -q` passes.

### U5. Routes + vanity URL resolver

- **Goal**: Wire the 6 new routes under `/api/v1/*` and the 2 new page routes (`/` and `/<company>/<brand>`). Add the legacy-route 302 redirects. Resolve vanity URLs server-side.
- **Requirements**: R3, R5, R12, R13, R16, KTD5, KTD8, KTD9.
- **Dependencies**: U1, U2, U3, U4.
- **Files**:
  - `x-monitoring/x_monitor/dashboard.py` — add `_resolve_vanity_url_for_brand`, add 6 page/api/v1 routes under `_register_routes`, add legacy-route redirects.
- **Approach**:
  - `_resolve_vanity_url_for_brand(brand_id)` joins `brands` + `brands_companies` + `companies`; if exactly one company row, returns `(company.nickname, brand.nickname)`; if zero company rows, returns `("_", brand.nickname)`. Returns `None` if no brand.
  - Page routes:
    - `@app.route("/")` → multi-brand home (renders `home.html.j2`)
    - `@app.route("/<company>/<brand>", methods=["GET"])` → single-brand home (renders `brand_home.html.j2`); 404 if brand not owned by company
    - `@app.route("/_/<brand>", methods=["GET"])` → single-brand home for company-less brands; 404 if missing
    - Legacy redirects:
      - `@app.route("/combined")` and `@app.route("/grid")` and `@app.route("/treemap")` → 302 to `/`
      - `@app.route("/brand/<brand_id>")` and `@app.route("/model/<brand_id>")` → 302 to vanity URL via resolver
  - API routes:
    - `/api/v1/home.chart.html` → htmx partial (`_home_chart.html.j2`)
    - `/api/v1/home.chart.json` → JSON via U2
    - `/api/v1/home.feed.json` → JSON via U4 (cursor pagination)
    - `/api/v1/home.brand.chart.html` → htmx partial (`_brand_chart.html.j2`)
    - `/api/v1/home.brand.chart.json` → JSON via U3
    - `/api/v1/home.window/<int:days>` → set home_window cookie + 303 back
    - `/api/v1/home.locale/<locale>` → set locale cookie + 303 back
    - `/api/v1/health` → `{"ok": true, "version": ...}` JSON
  - Two `_unattributed` edge cases: `/alibaba/_unattributed` → 404; `/_/_unattributed` → 404. The sentinel is exposed only on `/` (multi-brand feed).
- **Patterns to follow**: existing route + htmx pattern; `_resolve_locale`.
- **Test scenarios**:
  - `GET /` → 200, HTML contains `<canvas class="home-chart">` and a `data-home='…'` JSON.
  - `GET /alibaba/qwen` → 200, HTML contains `<h1>走个量 · 通义千问</h1>`.
  - `GET /somecompany/qwen` → 404 with brand-not-found message.
  - `GET /_/minimax` (assuming minimax has no company) → 200. (In seeded state, minimax has no row in `brands_companies`.)
  - `GET /_/nonexistent` → 404.
  - `GET /combined` → 302 → `/`.
  - `GET /brand/minimax` → 302 → `/_/minimax`.
  - `GET /api/v1/home.chart.json` → 200, JSON has `days, series, stacked` keys.
  - `GET /api/v1/home.feed.json` with cursor → 200, `next_cursor` advances.
  - `GET /api/v1/home.window/30` → 303, sets `home_window=30`.
- **Verification**: `pytest tests/test_home_routes.py tests/test_vanity_url.py -q` passes; manual `curl / -L` follows redirects to home page with the new content.

### U6. Templates + CSS tokens

- **Goal**: Render the two pages and feed. Add the new CSS tokens for post_type / nationalism / role.
- **Requirements**: R1, R5, R6, R7, R9, R10, R13, R14.
- **Dependencies**: U1 (chrome + locale), U2 (chart payload), U3 (single-brand payload), U4 (feed payload), U5 (routes).
- **Files**:
  - `x-monitoring/x_monitor/templates/home.html.j2` — multi-brand layout (R5–R11).
  - `x-monitoring/x_monitor/templates/_home_chart.html.j2` — htmx partial for chart canvas.
  - `x-monitoring/x_monitor/templates/brand_home.html.j2` — single-brand layout (R12–R16).
  - `x-monitoring/x_monitor/templates/_brand_chart.html.j2` — htmx partial for single-brand chart.
  - `x-monitoring/x_monitor/templates/_feed_initial.html.j2` — first-batch Jinja render of feed rows (server-side initial; subsequent batches come from `pw-feed.js`).
  - `x-monitoring/x_monitor/dashboard.css` — add `--pt-buzz-releases`, `--pt-hands-on-usage`, `--pt-performance-comparisons`, `--pt-feedback-questions`, `--pt-advertising-marketing`, `--pt-event-announcement`, `--nat-none`, `--nat-mild-pro`, `--nat-pro`, `--nat-constructive-critical`, `--nat-anti`, `--nat-mixed`, `--role-official`, `--role-staff`, `--role-community`, `--bar-advertising-marketing`.
- **Approach**:
  - `home.html.j2` mirrors `combined.html.j2`'s structure but replaces the canvas + payload with `home-chart` and adds the locale-toggle + window-toggle + control-panel module. The control panel is a vertical `<aside>` of checkbox groups with `data-pw-group="…"` so `pw-filter-store.js` can read the initial state.
  - The feed section is split: top half is the chart+controls (above); bottom half is `<section class="feed" data-pw-feed>` with the first 50 rows (server-rendered by `serialize_feed_page(limit=50)`) and a sentinel `<div class="feed-sentinel">`.
  - Sort header row has up/down `<button>` per column; the click handler emits a `pw:filter-change` event with `sort` / `order` set.
  - `brand_home.html.j2` mirrors `home.html.j2` but the chart is an area chart with 6 tabs. The tab strip lives ABOVE the canvas; the tab's `data-pw-tab` attribute drives the dataset toggle in `pw-brand-chart.js`. The legend lives BELOW the canvas (CSS-flex column).
  - Locale toggle is `zh_cn | en | original` — buttons submit to `/api/v1/home.locale/<locale>` (POST via existing `set_locale` pattern, except the action target is the new endpoint).
  - `_feed_initial.html.j2` is a snippet that just renders the post list — no `<main>` wrapper — so the bottomless-scroll JS can swap it into place on filter change.
- **Patterns to follow**: `combined.html.j2` for the page chrome + htmx structure; `model_detail.html.j2` for the tabs UI; `_grid_cards.html.j2` for the row-render pattern (cards vs. table — the feed is a `<table>` with sticky header row).
- **Test scenarios**:
  - `home.html.j2` Jinja renders without error against a `serialize_home_chart` payload.
  - `brand_home.html.j2` renders without error against a `serialize_single_brand_chart` payload.
  - The CSS token file additions don't break the existing `dashboard.css` validators (no duplicate custom properties, all tokens declared).
  - `_feed_initial.html.j2` shows truncation at 2 lines / 140 chars and the lang_detected subscript (snapshot test against a fixture row).
- **Verification**: `pytest tests/test_template_render.py -q` passes; manual `curl /` returns the HTML without 500; manual `curl /alibaba/qwen` returns the HTML without 500.

### U7. JS modules (pw-filter-store, pw-chart, pw-brand-chart, pw-feed)

- **Goal**: The three vanilla-JS modules that run the page interactivity (filter store, chart rendering, bottomless-scroll feed). Locale toggle is left to a JS shim around the existing `set_locale` endpoint.
- **Requirements**: R7, R8, R10, R11, KTD3, KTD6, KTD10.
- **Dependencies**: U5 (routes), U6 (templates, CSS tokens).
- **Files**:
  - `x-monitoring/x_monitor/static/pw-filter-store.js` — vanilla-JS state store + event bus.
  - `x-monitoring/x_monitor/static/pw-chart.js` — multi-brand combo line chart.
  - `x-monitoring/x_monitor/static/pw-brand-chart.js` — single-brand stacked-area chart with tabs.
  - `x-monitoring/x_monitor/static/pw-feed.js` — bottomless-scroll feed.
  - `x-monitoring/x_monitor/static/pw-locale-toggle.js` — locale + window toggles (uses `set_locale` and `/api/v1/home.window/<n>`).
- **Approach**:
  - `pw-filter-store.js`:
    - On boot, reads the initial filter state from the `data-pw-filters` JSON attribute on the body.
    - Exposes `window.pwFilter.get()`, `set(filterKey, value)`, `on(event, handler)`.
    - Emits `pw:filter-change` on `document` whenever a toggle changes; detail includes the changed key + new value.
  - `pw-chart.js`:
    - Reads `data-home='…'` from the canvas's parent, builds Chart.js datasets.
    - Subscribes to `pw:filter-change`; when the relevant filter changes (any key other than locale or window), re-aggregates the per-brand series locally using the new filter (no server roundtrip — the in-memory posts_by_brand blob is included in the initial payload). Calls `chart.update('none')`.
    - Subscribes to `pw:window-change`; triggers a fresh `/api/v1/home.chart.html` htmx swap on the chart canvas.
    - Subscribes to `pw:locale-change`; triggers the same htmx swap (labels are localized).
  - `pw-brand-chart.js`:
    - Builds 6 stacked-area datasets, all `hidden: true` except the active tab.
    - Tab buttons have `data-pw-tab`; click toggles which dataset is visible and emits `pw:tab-change`.
    - Same filter / window / locale subscription as `pw-chart.js`.
  - `pw-feed.js`:
    - On boot, wires `IntersectionObserver` on a `.feed-sentinel` element.
    - When sentinel enters viewport, fetch `/api/v1/home.feed.json?cursor=<last>&filters=<encode>` and appends rows.
    - Subscribes to `pw:filter-change` (clears the feed and re-fetches from row 1); `pw:sort-change` (re-fetches with new `sort` / `order`); `pw:locale-change` (re-renders the existing rows with localized labels — does NOT re-fetch).
    - Sort header buttons: click cycles through `desc` / `asc` / `default` (`created_at DESC`); emits `pw:sort-change`.
    - Click on a post cell: toggles a `.is-expanded` class; CSS expands the cell to 50% of feed width with `overflow-y: auto`. Click anywhere outside the cell collapses it.
  - Defensive destroy pattern: each chart module tracks the Chart instance via `Chart.getChart(canvas)` and destroys it before re-init on htmx swap (mirrors `combined-chart.js`).
- **Patterns to follow**: `combined-chart.js` (chart module shape + defensive destroy + CSS-var color reading); `trend-chart.js` (data-chart JSON parse).
- **Test scenarios**:
  - In-browser smoke (no JS-side test framework in this repo): `curl /api/v1/home.feed.json?cursor=foo` (with a bad cursor) → 400.
  - JS doesn't crash on an empty `posts_by_brand` (smoke test by curling the page against an empty DB).
  - 6-tab visibility toggling: smoke-tested by visual inspection; not unit-tested at this depth (would need playwright).
  - `pw:filter-change` is emitted exactly once per toggle change (manual event-count trace).
- **Verification**: Manual browser check: open `/`, toggle `discourse=dunk_yingyang` off, chart line drops, feed re-fetches, no console errors. Same drill for `/alibaba/qwen` with tab clicks.

### U8. End-to-end + redirect tests + cookie cleanup

- **Goal**: Pin the legacy-route 302 behavior (no broken external links) and the legacy-cookie cleanup. Add the smoke-test entry point.
- **Requirements**: R3, R9, KTD9.
- **Dependencies**: U1–U7.
- **Files**:
  - `x-monitoring/tests/test_home_e2e.py` — full-stack smoke against a temp DB.
  - `x-monitoring/tests/test_legacy_redirects.py` — each legacy path returns the expected 302.
  - `x-monitoring/tests/scripts/post_home_smoketest.py` — `python -m x_monitor.scripts.post_home_smoketest` runs through (a) `/` render, (b) `/alibaba/qwen` render, (c) `/api/v1/home.chart.json`, (d) `/api/v1/home.feed.json`, (e) legacy `/grid` 302. Mirrors `scripts/post_fetch_smoketest.py`.
- **Approach**: The e2e test spins up a Flask test client, applies migrations 001–028 (+ 029 when the migration plan lands), seeds a 7-day mini-post fixture, fires each route, asserts the JSON shape, asserts no 500s. The legacy-redirect test lists every documented legacy path and asserts the 302 + Location header.
- **Test scenarios**:
  - All 6 documented legacy paths 302 to the correct target.
  - E2E: 5 brands × 3 days × ~10 posts, filter toggle narrows the chart and feed.
  - E2E: `/_/minimax` renders; `/_/minimax/feed.json?cursor=…` paginates 50 at a time.
  - Cookie: `home_window=30` cookie persists through poll cycle.
- **Verification**: `pytest tests/test_home_e2e.py tests/test_legacy_redirects.py -q` passes; `python -m x_monitor.scripts.post_home_smoketest` exits 0.

### U9. CSS tokens + dark-mode palette update

- **Goal**: Add the missing `--bar-advertising-marketing` token (covered in U6) and the new `--pt-*`, `--nat-*`, `--role-*` tokens. Verify the existing dark-mode palette still works.
- **Requirements**: R7, R14 (CSS tokens).
- **Dependencies**: U6 (template CSS class names).
- **Files**: `x-monitoring/x_monitor/static/dashboard.css`.
- **Approach**: Read the existing `--bar-*` tokens + `--red`, `--green`, `--yellow`, `--muted` palette and add the missing tokens to `:root` in the same style. No color-picker hunt; reuse the existing palette discipline (the 6-key post_type set + 6-step nationalism scale get a calibrated 6-step ramp chosen to be distinguishable on the dark bg, similar to the existing `--bar-release`, `--bar-community` ordering).
- **Patterns to follow**: existing `dashboard.css` `:root` block.
- **Test scenarios**: All new tokens resolve to a non-empty value via `getComputedStyle(document.documentElement)` (snapshot test with selenium/headless — or skip at this layer; visual smoke is enough).
- **Verification**: Visual smoke: `/` and `/alibaba/qwen` look correct in the browser.

### U10. Documentation + delete legacy templates

- **Goal**: A short operator doc describing the new pages, the vanity URL rules, and the cookie keys. Delete the legacy templates that are no longer reachable.
- **Requirements**: R3.
- **Dependencies**: U5 (routes no longer reference them).
- **Files**:
  - `x-monitoring/docs/reference/home-pages.md` — pages reference doc.
  - Delete: `x-monitoring/x_monitor/templates/treemap.html.j2`, `templates/grid.html.j2`, `templates/combined.html.j2`, `templates/model_detail.html.j2` (replaced by the new homes), `templates/_grid_cards.html.j2`, `templates/_combined_chart.html.j2`, `templates/_treemap_svg.html.j2`, `templates/_model_card.html.j2`.
  - Keep: `templates/_spend_panel.html.j2` (still referenced by the new home pages via the API spend panel).
- **Approach**: The doc covers: (1) the vanity URL rule (`/<company>/<brand>` for owned brands, `/_/<brand>` for company-less brands, 404 otherwise); (2) the home-window cookie + locale cookie shapes; (3) the legacy-route 302 map (`/grid → /`, `/combined → /`, etc.); (4) the future-auth note pointing back to the auth roadmap.
- **Patterns to follow**: existing reference docs in `docs/reference/`.
- **Test scenarios**: `docs/reference/home-pages.md` exists and is non-empty; legacy templates are gone (`ls templates/` shows only the new homes + spend-panel partial).
- **Verification**: Manual diff.

### Open Questions

- **Q1**: When multi-account auth lands, will the existing `enabled_models` config knob become per-user ACLs or stay global? — **Tracked** for the auth roadmap. Vanity URL shape is chosen so the auth layer can wrap middleware around route resolution without URL changes.
- **Q2**: Sort columns beyond `created_at` and `like_count` — the user listed 6 columns in R10 but only the date + like_count are obvious sort keys. `brand` and `account.handle` are alpha-sortable. `classifications` and translation columns are not single-value sort candidates. **Deferred**: the plan ships 2 sort fields; adding more is a follow-up.

### Deferred to Follow-Up Work

- **D1. Multi-account auth + per-company scoping.** A separate plan adds the sessions table, login route, and middleware. The URL space (`/<company>/<brand>`) is shaped to be auth-ready.
- **D2. Cookie cleanup for dead state.** `polarity_window` and `combined_window` cookies become dead once their routes 302 to `/`. A separate plan adds `cookie cleanup on home render`.
- **D3. Localized vanity URLs.** A future plan adds `<company-slug>-<locale>` or full i18n slugs once slug-collision policy is decided.

### Verification Contract

The plan is complete when:

1. Every new route returns its expected status (200 for the two pages, 302 for the legacy family, 200 JSON for the API family).
2. The feed's bottomless-scroll loads 50 rows then advances with a non-null `next_cursor`; loading more than 500 returns `next_cursor: null`.
3. The control-panel filter narrows the chart AND the feed.
4. The single-brand page's tab switch renders the correct tab-dataset without a server roundtrip.
5. The locale toggle's `original` value renders the source `text` column directly with the lang_detected subscript.
6. Vanity URL `/<company>/<brand>` returns 200; `/<wrong-company>/<brand>` returns 404.
7. All tests pass: `pytest tests/test_home_chart.py tests/test_single_brand_chart.py tests/test_feed_page.py tests/test_home_routes.py tests/test_vanity_url.py tests/test_home_e2e.py tests/test_legacy_redirects.py -q`.
8. The cookie cleanup does NOT regress — the home_window / locale cookies persist across polls.

Run these from the repo root (`x-monitoring/`):

```bash
pytest tests/test_window_cookies.py tests/test_home_chart.py tests/test_single_brand_chart.py tests/test_feed_page.py tests/test_home_routes.py tests/test_vanity_url.py tests/test_home_e2e.py tests/test_legacy_redirects.py -q
python -m x_monitor.scripts.post_home_smoketest
```

### Definition of Done

The plan is "done" when an operator can:

1. Visit `http://localhost:5000/` and see the multi-brand home page with the `走个量 Pushin' Weight` chrome, the locale toggle defaulting to `zh_cn`, the time-period toggle defaulting to 7d, the combo line chart with one line per enabled brand, the 6-checkbox control panel, and the first 50 rows of the feed.
2. Toggle any control-panel checkbox and watch both the chart and the feed react without page reload.
3. Click any brand name in the control panel to deselect it; the corresponding line vanishes from the chart and its posts drop from the feed.
4. Visit `http://localhost:5000/alibaba/qwen` and see the single-brand home page with the area chart's `post_type` tab default, the 6 tab strip, and the brand-scoped feed.
5. Click a tab to swap the area chart's stacked dataset without losing scroll position or chart state.
6. Switch the locale toggle to `original` and see the source text in both translated and original columns with the lang_detected subscript.
7. Use the sort header to sort by `like_count ASC`; the feed re-fetches with the new sort.
8. Hit a legacy URL like `/grid`; receive a 302 to `/`.
9. The `走个量 Pushin' Weight` chrome appears on every page the dashboard renders.
10. Run `pytest tests/test_home_e2e.py` and `python -m x_monitor.scripts.post_home_smoketest` and see both exit 0.

### Assumptions

- **A1**: The 8-tab branch's "single-brand tabs" color codes are reachable via the existing `--bar-*` token set + new `--pt-*`, `--nat-*`, `--role-*` tokens. No new color-picker pass beyond what's already in `dashboard.css`'s dark-palette ramp.
- **A2**: The brand line counts' dependency on `enabled_models` is unchanged — `_unattributed` is excluded from the multi-brand chart per KTD7. Operator still sees the sentinel in the multi-brand feed (one row per `_unattributed` post with a muted pill).
- **A3**: The home page poll interval is the existing `dashboard.poll_seconds` (default 30). The chart's htmx poll preserves this. The feed does NOT poll — it's user-driven via scroll and filter toggles.
- **A4**: The 5 single-brand tabs ship in v1 per the user direction (2026-07-06 session). The schema already supports all 5 — no migration required.
- **A5**: The data window for the home page is independent of `dashboard.window_days`. `_resolve_home_window` does NOT clamp. The home page's allowed set is the narrower UX-targeted subset `(1, 7, 30, 365)` rather than the combined chart's 8-value `(1, 7, 14, 30, 60, 90, 180, 360)` — chosen to match the user-facing 1d / 1wk / 1mo / 1yr toggle in the spec. The "no clamp" behavior matches the combined chart's D4 — early days render as zero.
- **A6**: `enabled_models` continues to gate the multi-brand lines. A future auth plan makes `enabled_models` per-session rather than global; the data layer accepts a brand set rather than reading `config.enabled_models` directly.
- **A7**: The `_unattributed` sentinel home page is `/` (multi-brand feed includes it); there is no brand-detail page for the sentinel.
- **A8**: The 9 category tokens for the existing `--bar-*` set already cover 9 of the 10 discourse keys; the 10th (`advertising-marketing`) gets a new token. No rename of existing tokens (compatibility with the combined chart's hover overlay).
- **A9**: `home_window` cookie is named with a `home_` prefix to keep it disjoint from `polarity_window` and `combined_window`. All three are read-only by the routes that use them; this plan does not delete the others.
- **A10**: The legacy route redirects are 302 (temporary), preserving the option to remove them entirely once search engines have re-indexed. A future plan can switch to 410 (gone) when traffic tails off.
