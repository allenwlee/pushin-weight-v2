# Pushin' Weight UI Style Guide

> **Audience:** the user, when asking for visual changes; the agent, when interpreting those requests. This guide gives every major element a stable name (selector + role + data-attrs + JS owner) so we can talk about the page without guessing.
>
> **Scope:** the two Pushin' Weight home pages — multi-brand (`/`) and single-brand (`/<company>/<brand>` or `/_/<brand>`). Older `treemap` / `combined` / `grid` views are still in the code but deprecated by U10.
>
> **Repo paths (relative):** `x-monitoring/x_monitor/templates/{home,brand_home,_home_chart,_brand_chart,_feed_initial,_spend_panel}.html.j2`, `x-monitoring/x_monitor/static/dashboard.css`, `x-monitoring/x_monitor/static/pw-*.js`.

---

## How to use this guide

When you (the user) say something like:

- *"change the hover tooltip on the green line"* → look up the chart tooltip element below.
- *"the muted text under each post"* → that's `td.muted-cell`, the small grey line.
- *"the pill that says `unsanctioned`"* → `.feed .pill.flagged`.

Each entry gives:

1. **Selector** — what you paste into DevTools (`document.querySelector(...)`).
2. **Visual role** — what it looks like / where it sits.
3. **Data attrs** — `data-pw-*` hooks JS reads.
4. **JS owner** — which module mutates it.
5. **CSS source** — line in `dashboard.css` if relevant.

If you don't see an element in this guide, it's likely inside Chart.js (canvas) and the chart only knows about it via the dataset config in the JSON payload — see [Chart internals](#chart-internals-canvas) at the bottom.

---

## Page shell (both pages share this)

```
<body data-pw-page="multi | brand" data-pw-locale="..." data-pw-window="...">
  <header class="topbar">                       ← page chrome
  <main class="home-pane">                      ← two-pane layout (chart | filters)
  <section class="feed">                        ← bottomless scroll table
  <aside id="api-spend">                        ← latest API-spend panel
</body>
```

| Selector | Role | Notes |
|---|---|---|
| `body[data-pw-page]` | Page-type marker | `"multi"` on `/`, `"brand"` on `/<company>/<brand>` |
| `body[data-pw-filters]` | Initial filter state | JSON blob; `pw-filter-store.js` parses it on boot |
| `body[data-pw-brands]` | Brand list for the line chart | JSON array of slugs |
| `body[data-pw-locale]` | Current display language | `"zh_cn"` / `"en"` / `"original"` |
| `body[data-pw-window]` | Current window days | One of `1`, `7`, `30`, `365` |
| `body[data-pw-brand]` | (single-brand only) | The slug of the locked brand |

---

## Header (`<header class="topbar">`)

Lives at top of every page. Five regions, left → right:

| Selector | Role | Notes |
|---|---|---|
| `header.topbar h1` | App title: **走个量** with `<small>Pushin' Weight</small>` | Hardcoded chrome |
| `header.topbar .muted` (first) | "N models · Nd window" caption | Multi-brand only |
| `header.topbar .brand-title` | "{Brand display name} · Nd window" | Single-brand only |
| `header.topbar a.muted[href="/"]` | "← multi-brand" back link | Single-brand only |
| `nav.window-toggle` | Time-window picker | `<button data-pw-window-btn="N">` |
| `nav.locale-toggle` | Locale picker | `<button data-pw-locale-btn="zh_cn\|en\|original">` |
| `nav.window-toggle .window-toggle-label` | "window:" label | |
| `nav.locale-toggle .locale-toggle-label` | "lang:" label | |
| `.window-btn` | Individual window button | Active state: `.is-active` |
| `.locale-btn` | Individual locale button | Active state: `.is-active` |

**JS owner:** `pw-locale-toggle.js` (toggles `.is-active` and POSTs `/api/set_locale` or `/api/set_window`).

**Style hooks:** `dashboard.css:62-68` (topbar layout), `dashboard.css:541-562` (button styling).

---

## Main two-pane layout (`<main class="home-pane">`)

```
.home-pane (grid 2fr | 1fr)
├── section.home-chart-wrap  (left, 2fr)   ← the line / area chart
└── aside.control-panel      (right, 1fr)  ← filter checkboxes
```

Responsive: collapses to a single column under 900px (chart stacks above filters).

| Selector | Role | Notes |
|---|---|---|
| `main.home-pane` | Layout container | CSS grid, `dashboard.css:335-343` |
| `section.home-chart-wrap` | Chart container card | Bordered card; htmx-polls `/api/v1/home.chart.html` every N s |
| `section.home-chart-wrap#home-chart` | Multi-brand chart wrapper | ID `home-chart` |
| `div.home-chart-wrap#brand-chart` | Single-brand chart wrapper | ID `brand-chart`, lives inside a `<section>` with the tab strip |
| `canvas.home-chart` | Multi-brand **line** chart canvas | 360 px tall; `data-home='{...JSON...}'` |
| `canvas.home-brand-chart` | Single-brand **stacked-area** chart canvas | `data-brand-chart='{...JSON...}'`, `data-pw-tab="post_type"` |
| `aside.control-panel#control-panel` | Filter sidebar | `<h2>Filters</h2>` + N `.control-group` blocks |

**JS owners:** `pw-chart.js` (multi-brand line), `pw-brand-chart.js` (single-brand area).

---

## Filter panel (`<aside class="control-panel">`)

Six `.control-group` blocks plus a 7th for `unsanctioned`. Same structure on both pages; single-brand locks the brand checkbox with `.is-locked`.

```
aside.control-panel
├── h2  "Filters"
├── div.control-group[data-group="Brands"]
│   ├── div.control-group-title  "Brands"
│   └── label.control-row ×N
│       ├── input[type=checkbox][data-pw-filter-group="brands"]
│       ├── span.swatch        ← brand accent color
│       └── text node           ← brand display name
├── div.control-group[data-group="Discourse"]
├── div.control-group[data-group="post_type"]
├── div.control-group[data-group="account.role"]
├── div.control-group[data-group="us_nationalism"]
├── div.control-group[data-group="cn_nationalism"]
└── div.control-group[data-group="unsanctioned"]
```

| Selector | Role | Notes |
|---|---|---|
| `.control-group` | One filter dimension (Brands / Discourse / etc.) | |
| `.control-group-title` | Dimension label | Uppercase, muted |
| `.control-row` | One checkbox row | `<input data-pw-filter-group="…" value="…">` |
| `.control-row.is-locked` | Brand row, single-brand only | Disabled checkbox, 0.7 opacity |
| `.control-row .swatch` | 8×8 colored chip next to brand rows only | `background` set inline by brand accent color |
| `.control-row input[data-pw-filter-group]` | Filter input | `value` = the key (`qwen`, `discourse-meme`, `pt-buzz-releases`, …) |

**Filter groups** (`data-pw-filter-group` value):

| Value | Count | Source list |
|---|---|---|
| `brands` | 20 | `MODEL_DISPLAY_NAMES` keys (multi); 1 locked (single) |
| `discourse` | 10 | `_DASHBOARD_DISCOURSE_KEYS` |
| `post_types` | 6 | `_DASHBOARD_POST_TYPE_KEYS` |
| `role` | 3 | `_DASHBOARD_ROLE_KEYS` |
| `us_nationalism` | 6 | `_DASHBOARD_NATIONALISM_KEYS` |
| `cn_nationalism` | 6 | `_DASHBOARD_NATIONALISM_KEYS` (same scale, separate filter) |
| `unsanctioned` | 1 | `"only"` sentinel — toggles `only flagged posts` |

**JS owner:** `pw-filter-store.js` — watches all `input[data-pw-filter-group]` checkboxes, maintains a `pwFilters` cookie + window event, and forces chart / feed re-fetch.

**CSS:** `dashboard.css:364-409`.

---

## Tab strip (single-brand only)

Sits **above** the chart canvas, inside the same `<section>` as `#brand-chart`:

```
section
├── nav.tab-strip#brand-tabs
│   ├── button.pw-tab.is-active  data-pw-tab="post_type"
│   ├── button.pw-tab            data-pw-tab="discourse"
│   ├── button.pw-tab            data-pw-tab="account_roles"
│   ├── button.pw-tab            data-pw-tab="us_nationalism"
│   ├── button.pw-tab            data-pw-tab="cn_nationalism"
│   └── button.pw-tab            data-pw-tab="unsanctioned"
└── div.home-chart-wrap#brand-chart
```

| Selector | Role |
|---|---|
| `nav.tab-strip#brand-tabs` | Container, flex row, wraps on narrow viewports |
| `.pw-tab` | One tab button |
| `.pw-tab.is-active` | Currently-selected tab |
| `button[data-pw-tab="post_type\|discourse\|account_roles\|us_nationalism\|cn_nationalism\|unsanctioned"]` | Tab discriminator |

**JS owner:** `pw-brand-chart.js:132` reads `tab.getAttribute('data-pw-tab')`, shows/hides the matching dataset group.

**CSS:** `dashboard.css:412-435`.

---

## Chart internals (canvas)

Chart.js renders the canvas; we only control datasets via the JSON payload on `data-home` / `data-brand-chart`.

**Multi-brand line chart (`canvas.home-chart`):**

- One dataset per brand. `label` = brand display name, `borderColor` = `MODEL_ACCENT_COLORS[brand]`, `data` = `[{x: epoch, y: count}, …]`.
- Y axis = total posts/day. X axis = hours (window=1), days (7/30), months (365).
- Hover tooltip is Chart.js's default (corner-adjacent card with brand name + y value). **There is no custom tooltip HTML — changing it means rebuilding via `pw-chart.js`.**

**Single-brand stacked-area chart (`canvas.home-brand-chart`):**

- One dataset per key in the active tab (e.g. for `post_type`: `pt-buzz-releases`, `pt-hands-on-usage`, …).
- `fill: 'origin'`, `backgroundColor` = matching `--pt-*` / `--nat-*` / `--role-*` token.
- Tab switch changes which dataset group is `hidden: true/false`.

**Chart dataset payload shape** (lives in the JSON, not in CSS — to change a color in code, edit `brand_accent_colors` in `dashboard.py`):

```json
{
  "window_days": 7,
  "labels": ["2026-07-01", "2026-07-02", …],
  "datasets": [
    {"label": "Qwen", "data": [12, 18, …], "borderColor": "#3b82f6", "backgroundColor": "#3b82f6"},
    …
  ],
  "applied_filters": {"brands": ["qwen", …], "discourse": […], …}
}
```

**Color tokens (CSS variables):**

| Token | Used by |
|---|---|
| `--pt-buzz-releases`, `--pt-hands-on-usage`, `--pt-performance-comparisons`, `--pt-feedback-questions`, `--pt-advertising-marketing`, `--pt-event-announcement` | post_type palette |
| `--nat-none`, `--nat-mild-pro`, `--nat-pro`, `--nat-constructive-critical`, `--nat-anti`, `--nat-mixed` | nationalism palette (us/cn share) |
| `--role-official`, `--role-staff`, `--role-community` | account.role palette |
| `--bar-advertising-marketing` | legacy alias for the 10th discourse key |

Defined at `dashboard.css:32-47`.

---

## Feed (`<section class="feed">`)

Bottomless-scroll table. Same on both pages; single-brand scopes rows via `data-pw-brand-scope`.

```
section.feed#feed[data-pw-feed]
├── table
│   ├── thead
│   │   └── tr
│   │       ├── th button[data-pw-sort="created_at"][data-pw-order="desc"]   ← datetime
│   │       ├── th "brand"
│   │       ├── th "translated"
│   │       ├── th "original"
│   │       ├── th "classifications"
│   │       └── th "handle"
│   └── tbody[data-pw-feed-body]
│       └── tr[data-pw-feed-row][data-tweet-id="…"] ×N
├── div.feed-sentinel[data-pw-feed-sentinel]   ← "loading more…"
└── div.feed-end[data-pw-feed-end hidden]      ← "end of feed"
```

**Table cell layout (per row, `<tr data-pw-feed-row>`):**

| Cell | Content | Notable classes / attrs |
|---|---|---|
| 1 — datetime | ISO timestamp | `td.muted-cell` |
| 2 — brand | One `<span class="pill">` per brand nickname | `.pill` |
| 3 — translated | `<div class="lang-sub">translated from: [xx]</div>` if `row.lang_detected` exists, then `<div class="cell-truncated" data-pw-cell-truncated>{text_translated}</div>`, then `<div class="muted-cell">★ N</div>` | click expands the truncated div |
| 4 — original | `<div class="cell-truncated" data-pw-cell-truncated>{row.text}</div>` | click expands |
| 5 — classifications | Pills: `<span class="pill">discourse</span>` per discourse, `<span class="pill">post_type</span>` per post_type, `<span class="pill muted">cn:KEY</span>` if `cn_nationalism`, `<span class="pill muted">us:KEY</span>` if `us_nationalism`, and **`<span class="pill flagged">unsanctioned</span>`** if flagged | |
| 6 — handle | `handle · <span class="pill role-{role}">{role_label}</span>` | `.pill.role-official\|staff\|community` |

| Selector | Role | Notes |
|---|---|---|
| `section.feed#feed` | Feed container | `data-pw-feed` triggers `pw-feed.js` init; `data-pw-brand-scope` narrows to one brand |
| `[data-pw-feed-body]` | `<tbody>` — JS appends new rows here | |
| `[data-pw-feed-row][data-tweet-id]` | One row | |
| `[data-pw-feed-sentinel]` | "loading more…" placeholder | IntersectionObserver watches this |
| `[data-pw-feed-end]` | "end of feed" terminator | `hidden` until exhausted |
| `.cell-truncated` | Truncated post text (2-line clamp) | Click toggles `.is-expanded` on `<td>` |
| `.feed td.is-expanded .cell-truncated` | Expanded state (height auto + scroll) | `dashboard.css:486-492` |
| `.lang-sub` | Small grey "translated from: [xx]" line above the translated cell | `dashboard.css:495-499` |
| `.muted-cell` | Small grey text (datetime, like count) | `dashboard.css:494` |
| `.pill` | Pill chip (brands, discourse, post_type, nationalism, role) | `dashboard.css:513-521` |
| `.pill.flagged` | Red "unsanctioned" pill | `dashboard.css:522` |
| `.pill.muted` | Outlined nationalism pill (cn:…, us:…) | `dashboard.css:526` |
| `.pill.role-official`, `.pill.role-staff`, `.pill.role-community` | Role pills with role-tinted bg | `dashboard.css:523-525` |

**Sort controls:** `<button data-pw-sort="created_at" data-pw-order="desc">` in the `<th>` of the datetime column. Click cycles `desc → asc → desc` and POSTs `/api/v1/home.feed.json?sort=…&order=…`.

**JS owners:** `pw-feed.js` (pagination + sort + expansion), `pw-filter-store.js` (re-fetches on filter change).

---

## API-spend panel (`<aside id="api-spend" class="spend-panel-wrap">`)

Bottom-right rail. htmx-polls `/api/spend.html`.

```
aside#api-spend.spend-panel-wrap
└── aside.spend-panel
    ├── header.spend-panel-head
    │   ├── h2 "API spend"
    │   └── span.muted "last cycle · {timestamp}"
    ├── p.muted  "no run yet — wait for the next cycle."   ← when no run
    └── dl.spend-grid + table.spend-endpoints + p.spend-status   ← when run exists
```

| Selector | Role |
|---|---|
| `.spend-panel-wrap` | htmx wrapper, polls `/api/spend.html` |
| `.spend-panel` | Card chrome |
| `.spend-panel-head` | Header row with `<h2>` and last-cycle timestamp |
| `.spend-grid` | 3-cell DL: requests / total duration / total results |
| `.spend-endpoints` | Per-endpoint table (path / n / mean ms / max ms) |
| `.spend-status` | Status-code chips (`200×N`, `429×M`) |

Defined in `_spend_panel.html.j2`; CSS lives in the older v1.7 sections of `dashboard.css`.

---

## Quick lookup: when you say…

| You say | I look up |
|---|---|
| "the title in the header" | `header.topbar h1` (走个量 + Pushin' Weight small) |
| "the N models · Nd caption" | `header.topbar .muted` (multi-brand) / `header.topbar .brand-title` (single-brand) |
| "the back arrow" | `header.topbar a.muted[href="/"]` (single-brand only) |
| "the time-window buttons" | `nav.window-toggle .window-btn` |
| "the lang buttons" | `nav.locale-toggle .locale-btn` |
| "the line chart" / "the area chart" | `canvas.home-chart` / `canvas.home-brand-chart` |
| "the filter checkboxes" | `aside.control-panel .control-row input[data-pw-filter-group]` |
| "the brand color swatch" | `aside.control-panel .control-row .swatch` |
| "the filters header" | `aside.control-panel h2` |
| "the tab strip" (single-brand only) | `nav.tab-strip#brand-tabs .pw-tab` |
| "the feed table" | `section.feed#feed table` |
| "the column headers in the feed" | `section.feed thead th` |
| "the brand pills in a feed row" | `section.feed tr[data-pw-feed-row] td:nth-child(2) .pill` |
| "the translated post text" | `section.feed .cell-truncated[data-pw-cell-truncated]` (cell 3, translated col) |
| "the original post text" | `section.feed .cell-truncated[data-pw-cell-truncated]` (cell 4, original col) |
| "the like count under a post" | `section.feed td:nth-child(3) .muted-cell` (the ★ N line) |
| "the classifications pills in a row" | `section.feed tr[data-pw-feed-row] td:nth-child(5)` |
| "the unsanctioned red pill" | `section.feed .pill.flagged` |
| "the handle + role pill" | `section.feed tr[data-pw-feed-row] td:nth-child(6) .pill.role-{role}` |
| "the loading-more text" | `.feed-sentinel[data-pw-feed-sentinel]` |
| "the end-of-feed text" | `.feed-end[data-pw-feed-end]` |
| "the API spend card" | `aside#api-spend .spend-panel` |

---

## Conventions & invariants

- **No inline JS in templates** — all interactivity lives in `x-monitoring/x_monitor/static/pw-*.js`. If you want a new behavior, name it as a `data-pw-*` hook and add a handler in the appropriate module.
- **`data-pw-*` is the JS contract.** Adding a new filter dimension = new `data-pw-filter-group` value + an entry in `_DASHBOARD_*_KEYS` + a `.control-group` block in both templates.
- **Colors come from CSS variables** (`--pt-*`, `--nat-*`, `--role-*`, `--bar-*`). Don't hardcode hex in JS; reference the variable via `getComputedStyle`.
- **Both templates must stay in sync** — `home.html.j2` and `brand_home.html.j2` mirror each other's structure. If you change one, diff the other.
- **The spend panel (`<aside id="api-spend">`) is shared with legacy views** and lives outside `.home-pane`. It's not part of the chart/feed layout.

---

## Related

- Plan: `docs/plans/2026-07-06-003-feat-pushin-weight-home-pages-plan.md`
- Templates: `x-monitoring/x_monitor/templates/{home,brand_home,_home_chart,_brand_chart,_feed_initial,_spend_panel}.html.j2`
- JS modules: `x-monitoring/x_monitor/static/{pw-filter-store,pw-chart,pw-brand-chart,pw-feed,pw-locale-toggle}.js`
- Styles: `x-monitoring/x_monitor/static/dashboard.css` (U6 section starts at line 330; color tokens at 32-47)