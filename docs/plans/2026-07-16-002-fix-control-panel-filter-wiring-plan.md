---
title: fix: Wire control-panel filter changes to chart + feed (all dimensions)
date: 2026-07-16
type: fix
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ce-plan-bootstrap
execution: code
---

## Goal Capsule

- **Objective:** Make the Pushin' Weight home control panel a real filter. Toggling any checkbox in any group (Brands / Discourse / post_type / account.role / us_nationalism / cn_nationalism / unsanctioned) must update both the multi-brand line chart AND the home feed in real time, and the per-axis state must survive the periodic htmx poll.
- **User-facing impact:** On `/` (multi-brand), unselecting all models → chart collapses to empty/zero lines AND feed goes empty. Selecting one model → chart shows only that line AND feed shows only that brand's posts. Currently broken end-to-end (4 distinct bugs); this plan makes it consistent with the rest of the dashboard's filter UX.
- **Authority hierarchy:** User confirmed scope on 2026-07-16 ("All filter dimensions" over "brand-only" or "server-only"). All four bugs feed the same symptom — fixing them piecemeal would leave one widget out of sync.
- **Execution profile:** Standard. Crosses 4 files (`x_monitor/dashboard.py`, `x_monitor/_home_routes.py`, `x_monitor/static/pw-chart.js`, `x_monitor/static/pw-feed.js`) plus 2 templates (`x_monitor/templates/home.html.j2`, `x_monitor/templates/brand_home.html.j2`) plus tests. Five implementation units, server-first, then JS, then htmx, then tests.
- **Stop conditions:** All five implementation units merged; all unit tests green; live `/` page shows empty chart + empty feed when all brands unchecked, and both update within 500ms of a checkbox click (no full-page reload); periodic poll continues to honor the filter state.
- **Tail ownership:** `ce-work` owns implementation and the merge. Post-merge live verification (browser check via the local tunnel) is a verification gate, not a follow-up plan.

## Product Contract

### Summary

The Pushin' Weight home page (`/`, multi-brand) renders a control panel with seven filter groups (Brands + 6 taxonomy axes). The panel was wired to a client-side store (`pw-filter-store.js`) that emits `pw:filter-change` events on every checkbox toggle, but only **one** consumer (the feed) actually listened, and even the feed only honored the filter on the *second* page (the immediate refetch after a toggle ignored the filter). The line chart never subscribed at all, and the periodic htmx poll re-fetched the chart HTML with no filter params. The server-side `_post_matches_filter` predicate also lacked a branch for `filters["brands"]` — even if the JS sent a correct filter, the chart code iterates all `enabled_models` unconditionally and the feed's brand-narrowing code was missing.

### Problem Frame

User report (2026-07-16): "right now it seems to not be working. when i unselect all the models, there doesn't seem to be any reaction in the feed nor in the line graph. both should adjust accordingly."

Diagnosis (4 distinct bugs, all confirmed via curl + Read):

1. **`x_monitor/static/pw-chart.js` does not subscribe to `pw:filter-change`.** The header comment (line 9) advertises the behavior, but `grep -n "filter-change" pw-chart.js` returns only the tooltip filter function name. Toggling any checkbox is silent for the chart.
2. **`x_monitor/static/pw-feed.js` `clearAndRefetch()` calls `fetchBatch()` with no arguments.** Line 297: `fetchBatch()` (no arg). The infinite-scroll path (line 354) correctly reads `window.pwFilter.get()` and threads it through `buildQuery`, which is why the *second* paginated batch honors the filter but the immediate first-page refetch ignores it.
3. **`x_monitor/templates/home.html.j2` `hx-get` on `#home-chart` has no `hx-vals` or `hx-include`.** Even if the JS subscribed, the htmx `every {{ poll_seconds }}s` poll re-fetches the same un-filtered URL.
4. **Server-side: `_post_matches_filter` (`x_monitor/dashboard.py:1056`) has no branch for `filters["brands"]`.** Verified: `curl '/api/v1/home.feed.json?filters={"brands":[]}'` returns 2 rows, not 0. On the chart path, `serialize_home_chart` (`x_monitor/dashboard.py:1099`) iterates `enabled_models` unconditionally and never intersects with `filters["brands"]`. On the feed path, `serialize_feed_page` (line 1521) calls `_post_matches_filter` which also lacks the brand branch.

The bug chain is layered: even if all JS is correct, the server still won't narrow on `brands`; even if the server narrows, the chart won't notice until either htmx re-polls (with old URL → unfiltered) or the JS subscribes.

### Requirements

R1. `_post_matches_filter` accepts a `brands` filter value (list of brand nicknames) and returns False for any post whose `brand_nicknames` does not include at least one of the listed nicknames. Empty list = match nothing (narrows to zero).
R2. `serialize_home_chart` intersects `enabled_models` with `filters["brands"]` when the filter is a non-`__all__` list, and emits the empty/zero series for any brand filtered out.
R3. `render_home_multi` (`x_monitor/_home_routes.py`) honors `filters["brands"]` by either (a) skipping per-brand `_denormalize_posts` calls for filtered-out brands, or (b) letting the chart/feed predicates handle it — implementation choice deferred, but the route must not call SQL for brands the user has excluded (efficiency + correctness on `_unattributed` posts).
R4. `pw-feed.js` `clearAndRefetch()` passes `window.pwFilter.get()` to `fetchBatch(filters)`. Same for any other entry point that triggers an immediate refetch.
R5. `pw-chart.js` subscribes to `pw:filter-change` and re-fetches `/api/v1/home.chart.html?filters=<json>` on every event, then destroys and re-renders the Chart.js instance on the new canvas.
R6. `home.html.j2` and `brand_home.html.j2` add `hx-vals='js:{filters: JSON.stringify(window.pwFilter ? window.pwFilter.get() : {})}'` to the chart region so htmx's periodic poll honors the filter.
R7. ~~The filter survives filter-induced races: if the user toggles checkboxes rapidly, late responses from earlier fetches must not overwrite the latest state. Use an in-flight token (incrementing counter or AbortController) to drop stale responses.~~ **Deferred to follow-up per user discussion (2026-07-16):** rapid-fire toggling is not a real use case for deliberate filter selection. If a stale-response race ever surfaces in the wild, add the guard as a separate unit. Not in scope for this plan.
R8. All existing tests pass: `tests/test_home_e2e.py`, `tests/test_feed_page.py`, `tests/test_group_posts_by_id.py`, plus the 16 JS tests in `tests/test_pw_feed_formatter.js`.
R9. New server tests cover: (a) `brands=["qwen"]` returns only qwen posts; (b) `brands=[]` returns zero posts; (c) `_post_matches_filter` with brands filter returns False for non-matching posts.
R10. New JS tests cover: (a) `pw:filter-change` is dispatched on toggle; (b) `pw-chart.js` listener is wired (smoke check via spy on `fetch`); (c) `clearAndRefetch` passes the current filter to `fetchBatch`.

### Considered alternatives

**Server-only fix (skip the JS rewire).** Rejected. The chart never re-renders on filter change without a full-page reload, which is the literal user complaint. The htmx poll still hits the un-filtered URL. Even if the server narrows correctly, the UI behavior the user wants requires the JS to actually react.

**Force a full-page reload on filter change.** Rejected. Breaks cursor pagination state, breaks auto-refresh, breaks the relative-timestamp formatting on the existing rows, and would lose the `data-pw-filters` cookie/localStorage round-trip the store already provides.

**Add a `filters` cookie so the server can read it without query params.** Rejected for this scope. The query-string path already works for `fetchBatch` and `serialize_home_chart`; cookies would duplicate state and force a server-side cookie parser. The htmx `hx-vals='js:...'` covers the periodic poll with the same in-memory store the click handler reads.

**Use `IntersectionObserver` on the chart region to lazily re-render instead of an explicit listener.** Rejected. The filter changes come from the control panel (DOM-adjacent), not from chart visibility. An explicit `pw:filter-change` listener is the right seam.

**Drop the `unsanctioned` single-toggle group from the rewrite (treat it as `__all__`/`only` semantics only).** Rejected. The store already handles it correctly; the bug is symmetric across all 7 groups. Fixing all 7 is the same code shape as fixing 6.

## Implementation Units

### U1. Server: brand narrowing in `_post_matches_filter`

- **Goal:** Add a `brands` branch to the per-post filter predicate so any caller that consumes `filters["brands"]` honors it.
- **Requirements:** R1.
- **Dependencies:** None.
- **Files:**
  - `x-monitoring/x_monitor/dashboard.py` (modify, ~5 lines)
  - `x-monitoring/tests/test_home_e2e.py` (add 2 tests)
- **Approach:** Inside `_post_matches_filter`, add a branch before the existing axes:
  - If `filters["brands"]` is a list (the new contract — the store already emits arrays on toggle, `__all__` only at hydration default), check whether `post.get("brand_nicknames") or []` intersects with the list. Empty list → return False for every post.
  - Sentinel `__all__` → skip the branch (no narrowing).
  - The brand-narrowing check uses `set.isdisjoint()` semantics for O(n+m).
- **Test scenarios:**
  - `test_post_matches_filter_brands_empty_returns_false`: any post + `brands=[]` → False.
  - `test_post_matches_filter_brands_overlap_returns_true`: post with `brand_nicknames=["qwen"]` + `brands=["qwen","glm"]` → True.
  - `test_post_matches_filter_brands_no_overlap_returns_false`: post with `brand_nicknames=["deepseek"]` + `brands=["qwen"]` → False.
  - `test_post_matches_filter_brands_all_sentinel_skips`: `brands="__all__"` → no brand narrowing (other axes still applied).
- **Verification:** `pytest tests/test_home_e2e.py -k brands -q` passes 4 new tests; existing `test_home_e2e` suite remains green (no behavior change when `brands` is absent or `__all__`).

### U2. Server: brand narrowing in `serialize_home_chart` and `render_home_multi`

- **Goal:** Make the multi-brand chart honor `filters["brands"]` — when set, the chart shows only the selected brands' lines and emits zero series for filtered-out ones.
- **Requirements:** R2, R3.
- **Dependencies:** U1.
- **Files:**
  - `x-monitoring/x_monitor/dashboard.py` (modify `serialize_home_chart`, ~10 lines)
  - `x-monitoring/x_monitor/_home_routes.py` (modify `render_home_multi`, ~5 lines)
  - `x-monitoring/tests/test_home_e2e.py` (add 3 tests)
- **Approach:**
  - In `serialize_home_chart`: after computing `enabled_models`, derive `visible_models = enabled_models if (brands is None or brands == "__all__") else [b for b in enabled_models if b in brands]`. Initialize `series`, `stacked`, `totals` only for `visible_models`. The per-brand loop iterates `visible_models`. The `colors` dict echoes the visible subset so the JS doesn't render accent colors for filtered-out lines.
  - In `render_home_multi`: when `filters["brands"]` is a concrete list, intersect `config.enabled_models` with it before calling `_denormalize_posts` — saves SQL roundtrips for excluded brands and prevents `_unattributed` posts from leaking back in via per-brand queries.
- **Test scenarios:**
  - `test_home_chart_with_brand_filter_returns_only_filtered_series`: `serialize_home_chart(enabled_models=["qwen","glm"], ..., filters={"brands":["qwen"]})` → `series` has only `qwen`, `totals` has only `qwen`, `colors` has only `qwen`.
  - `test_home_chart_with_brand_filter_empty_returns_empty_payload`: `filters={"brands":[]}` → `series == {}`, `totals == {}`.
  - `test_home_chart_with_all_sentinel_returns_all_brands`: `filters={"brands":"__all__"}` (sentinel form) → all `enabled_models` present.
- **Verification:** New tests pass. Existing `test_home_e2e.py` brand-coverage tests still pass.

### U3. JS: `pw-chart.js` subscribes to `pw:filter-change`

- **Goal:** Wire the chart so any control-panel toggle triggers a re-fetch + re-render with the new filter.
- **Requirements:** R5, R7.
- **Dependencies:** None (server-side is independent — chart listens regardless of whether server honors yet).
- **Files:**
  - `x-monitoring/x_monitor/static/pw-chart.js` (modify, ~30 lines)
  - `x-monitoring/tests/test_pw_chart_filter.js` (new file, ~80 lines)
- **Approach:**
  - On `DOMContentLoaded` (after the initial `renderAll()`), call `document.addEventListener('pw:filter-change', handler)`.
  - Handler reads `window.pwFilter.get()`, builds `?filters=<encoded JSON>` query string, calls `fetch('/api/v1/home.chart.html' + query)`, parses the new HTML fragment, replaces `#home-chart`'s innerHTML, then re-runs `renderOne(canvas)` on the new canvas.
  - **Scope:** listener only acts when `#home-chart` exists. On the single-brand page (`/brand_home.html.j2`), `pw-chart.js` is loaded but `#home-chart` is absent — the listener no-ops there, and `pw-brand-chart.js` owns `#brand-chart`.
  - Edge case: filter-change fires before initial render finishes → guard with a `ready` flag set after first `renderAll()`.
  - Mirror the pattern in `pw-brand-chart.js` for the single-brand page (the brand page has brand filter locked, but other 6 filter groups still apply). The brand-chart endpoint requires `?brand=<id>`; read it from `document.body.getAttribute('data-pw-brand')` (set by `brand_home.html.j2`).
- **Test scenarios:**
  - `test_pw_chart_subscribes_to_filter_change_on_init`: dispatch `pw:filter-change` with `filters.brands=[]`; assert `fetch` was called with `/api/v1/home.chart.html?filters=%7B%22brands%22%3A%5B%5D%7D`.
  - `test_pw_chart_no_ops_on_single_brand_page`: regression for H1 — when only `#brand-chart` exists, `pw-chart.js` listener fires no fetch.
  - `test_pw_chart_skips_filter_before_ready`: dispatch `pw:filter-change` before initial render; assert no `fetch` call.
- **Verification:** New JS tests pass via `node tests/test_pw_chart_filter.js`. Browser smoke test: open `/`, uncheck all brands, observe chart canvas becomes empty within 500ms.

### U4. JS: `pw-feed.js clearAndRefetch` passes current filter

- **Goal:** Make the immediate post-toggle refetch honor the filter (not just the infinite-scroll path).
- **Requirements:** R4.
- **Dependencies:** None.
- **Files:**
  - `x-monitoring/x_monitor/static/pw-feed.js` (modify, 1 line + a duplicate-call site fix)
  - `x-monitoring/tests/test_pw_feed_formatter.js` (extend existing file with 2 new tests)
- **Approach:**
  - In `clearAndRefetch()`, change `fetchBatch()` to `fetchBatch(window.pwFilter.get())`.
  - Audit the file for other `fetchBatch()` no-arg call sites (line 297 already found; check the auto-refresh timer at line ~427) and pass the filter there too. The auto-refresh fetches page 1 so it should respect current filters.
- **Test scenarios:**
  - `test_clear_and_refetch_passes_current_filter`: stub `window.pwFilter.get` to return `{brands:["qwen"]}`, simulate toggle, assert the fetch URL contains `filters=%7B%22brands%22%3A%5B%22qwen%22%5D%7D`.
  - `test_auto_refresh_refetch_passes_current_filter`: same assertion on the auto-refresh timer path.
- **Verification:** New JS tests pass. Manual browser test: toggle a brand checkbox on `/`, observe the first page of the feed updates to that brand within 500ms.

### U5. htmx: periodic chart poll honors filter via `hx-vals`

- **Goal:** Make htmx's `every {{ poll_seconds }}s` re-poll of `#home-chart` carry the current filter state in the URL.
- **Requirements:** R6.
- **Dependencies:** None.
- **Files:**
  - `x-monitoring/x_monitor/templates/home.html.j2` (modify, 1 attribute)
  - `x-monitoring/x_monitor/templates/brand_home.html.j2` (modify, 1 attribute)
- **Approach:**
  - On `<section class="home-chart-wrap" id="home-chart" hx-get="/api/v1/home.chart.html" hx-trigger="every {{ poll_seconds }}s" hx-swap="innerHTML">`, add `hx-vals='js:{filters: JSON.stringify(window.pwFilter ? window.pwFilter.get() : {})}'`.
  - The `js:` prefix tells htmx to evaluate the expression client-side on every request — re-evaluates `pwFilter.get()` each poll, so the latest filter is always sent.
  - Guard for `window.pwFilter` being undefined (script load order): the JS files use `defer`, so `pwFilter` is set before the first poll fires. The fallback `{}` matches the un-filtered default.
- **Test scenarios:** None — this is template-only wiring, verified via browser observation:
  - Open `/`, observe a poll fires (network tab shows `/api/v1/home.chart.html?filters=...`), uncheck all brands, observe the next poll carries `filters.brands=[]` and the chart fragment is empty.
  - `Test expectation: none — template attribute, verified by browser smoke test.`
- **Verification:** Browser smoke test passes. The unit-testable contract lives in U3 (JS listener) — U5 is the periodic-poll complement.

## Files Touched

| File | Unit | Change kind |
|---|---|---|
| `x-monitoring/x_monitor/dashboard.py` | U1, U2 | modify (`_post_matches_filter`, `serialize_home_chart`) |
| `x-monitoring/x_monitor/_home_routes.py` | U2 | modify (`render_home_multi`) |
| `x-monitoring/x_monitor/static/pw-chart.js` | U3 | modify (subscribe + handler + race guard) |
| `x-monitoring/x_monitor/static/pw-brand-chart.js` | U3 | modify (mirror for single-brand page) |
| `x-monitoring/x_monitor/static/pw-feed.js` | U4 | modify (pass filter at all call sites) |
| `x-monitoring/x_monitor/templates/home.html.j2` | U5 | modify (add `hx-vals`) |
| `x-monitoring/x_monitor/templates/brand_home.html.j2` | U5 | modify (add `hx-vals`) |
| `x-monitoring/tests/test_home_e2e.py` | U1, U2 | extend (~5 new tests) |
| `x-monitoring/tests/test_pw_chart_filter.js` | U3 | new file (~80 lines) |
| `x-monitoring/tests/test_pw_feed_formatter.js` | U4 | extend (~30 lines, 2 new tests) |

## Verification Contract

- **Unit tests:** `pytest x-monitoring/tests/test_home_e2e.py x-monitoring/tests/test_feed_page.py x-monitoring/tests/test_group_posts_by_id.py -q --basetemp=$HOME/pytest-basetemp-filter-wiring` → all green, including 5 new server tests.
- **JS tests:** `node x-monitoring/tests/test_pw_feed_formatter.js && node x-monitoring/tests/test_pw_chart_filter.js` → 16 + new tests all green.
- **Curl smoke (server-side):**
  - `curl '/api/v1/home.feed.json?limit=5&filters={"brands":["qwen"]}' | jq '.rows[].brand_nicknames'` → all rows contain "qwen".
  - `curl '/api/v1/home.feed.json?limit=5&filters={"brands":[]}' | jq '.rows | length'` → 0.
  - `curl '/api/v1/home.chart.html?filters={"brands":["qwen"]}' | grep -c data-brand` → 1 (only qwen).
- **Browser smoke (live `/`):** Open via local tunnel. Toggle all-brands-off → chart lines vanish, feed empties, both within 500ms. Toggle one brand on → chart shows that line, feed shows that brand's rows. Wait one poll cycle → state persists (no drift back to all-brands).
- **Regression:** All previously-passing tests remain green.

## Definition of Done

- All 5 implementation units merged into `main`.
- Verification Contract fully passes (unit + JS + curl + browser).
- Plan file updated with end-of-unit `Scope delivered vs plan promised: ...` line on every commit (per Plan-Execution Contract).
- Memory file `~/.claude/projects/-Users-allenwlee/memory/project_x_monitor_filter_wiring_2026-07-16.md` written with: (a) the 4-bug structure (so future sessions know where each seam lives), (b) the brand-page scoping rule (pw-chart.js owns #home-chart only).
- Live `/` verified by user before closing the unit.

## Risks & Dependencies

- **htmx `hx-vals='js:...'` requires htmx ≥ 1.9 with the `js:` prefix enabled.** Project pins htmx 1.9.10 (confirmed in `home.html.j2`); `js:` prefix is supported. No upgrade needed.
- **Server route change in `render_home_multi` may change SQL call count** — when all brands are excluded, the loop runs zero times (vs. 20). Net effect is faster; no regression risk on the "all on" default.
- **Race-condition guard** (originally proposed as R7) was deferred per user discussion. Rapid toggle is not a real use case here; if it ever surfaces, add the guard as a follow-up.
- **`pw-brand-chart.js` mirror in U3** requires reading `data-pw-brand` from `<body>` (the brand-chart route needs `?brand=<id>` in the URL). The template sets `data-pw-brand="{{ brand_id }}"`; the JS listener falls back to no-op if it's missing.

## Out of scope

- Persisting filter state across page reloads (localStorage round-trip) — the store already has the scaffolding but no unit currently exercises it. Defer to a follow-up plan if the user requests sticky filters.
- URL-as-state (encoding filters in `?filters=...` for shareable URLs) — not requested.
- Adding a "Reset filters" button to the control panel — UX improvement, not a wiring bug.
- Per-checkbox debouncing — the in-flight token already prevents stale-response races; debouncing is a UX nicety that can wait.

## Sources & Research

- Diagnosis was performed via direct file reads + curl probes (no external research needed — local codebase was the entire problem surface).
- Memory file `~/.claude/projects/-Users-allenwlee/memory/project_x_monitor_feed_pretty_2026-07-16.md` provided context on the recent feed UI changes (U2/U3/U4/U5 of the pretty-dates plan) which sit adjacent to this work and share the `_feed_row_to_wire` / cursor serializer contract.
- `references/plan-sections.md` (skill-local) and the existing 2026-07-15 unified plans informed the format and metadata conventions.