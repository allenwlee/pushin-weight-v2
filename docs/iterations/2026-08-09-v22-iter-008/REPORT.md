# Iteration 008 (v22) — U1 route split + Net F (/internal/ parity)

**Date:** 2026-08-09
**Branch:** feat/v20-homepage-phase-a
**Scope:** Ship U1 (route split — move legacy home to `/internal/`) + Net F (parity assertion) per v22 plan § Goal Capsule and § "Comprehensive regression nets". Closes the iter-7 audit finding (`/internal/` returned 404).

## Step 0 — Regression Net (pre-edit)

```
Passed: 62 (62 iter-7 assertions; Net F deferred)
Failed: 0
```

## Step 1 — Root cause recap (from iter 7)

iter 1-4 shipped the v22 chrome to `/`, overwriting `monitor/templates/monitor/home.html` and the `home()` view. The legacy home was never moved to `/internal/` — no `/internal/` route existed in `monitor/urls.py`. Plan § Goal Capsule was violated: *"Do not delete or replace; move today's homepage to /internal/."*

## Step 2 — Implementation

### Restored legacy template

`monitor/templates/monitor/home.html` was overwritten by v22 chrome. Saved the pre-v22 home.html from git tree at `6ac2ddd^` to `monitor/templates/monitor/home_internal.html` (180 lines). The pre-v22 template uses legacy markers: `id="control-panel"`, `id="home-chart"`, `.filter-group`, `.locale-btn`, `.feed-row`.

### Added `home_internal` view

`monitor/views.py:1211` — copy of the pre-v22 `home()` view body, pointed at `monitor/home_internal.html`. Shares all helper functions with the v22 `home()` view (`_resolve_locale`, `_resolve_home_window`, `_build_brands_context`, `_get_feed_posts`, `_enrich_posts_with_classifications`, `_post_to_wire`, `_build_home_chart_payload`).

### Added `/internal/` route

`monitor/urls.py:16` — `path("internal/", views.home_internal, name="home_internal")`. The v22 chrome stays at `/`.

### Added Net F to regression_net.py

`_check_internal_parity(session)` method runs the same authenticated session against `/internal/` (derived from the base URL) and asserts:

- HTTP 200 on `/internal/`
- 5 legacy markers present: `id="control-panel"`, `id="home-chart"`, `.window-toggle`, `.locale-btn`, `.filter-group`
- 3 v22 markers ABSENT: `.pulse-chip`, `.voice-chip`, `.filter-pill` (legacy must not depend on v22 chrome)
- App title still has both `走个量` and `Pushin' Weight`

10 new assertions (5 legacy-present + 3 v22-absent + 2 title).

## Step 3 — Post-edit verification

```
Passed: 72
Failed: 0
```

All 62 prior assertions still green + 10 new Net F assertions = 72/0.

## P0 / P1 status after iter 8

| DoD gate | Status |
|---|---|
| Net A — Route & shell identity | ✅ (`/` serves v22 chrome, `/internal/` serves legacy chrome, both 200) |
| Net B — Window & locale defaults | ✅ |
| Net C — Filter contract | ✅ |
| Net D — Chart contract | ✅ |
| Net E — Feed contract | ✅ |
| Net F — `/internal/` parity | ✅ SHIPPED this iter (+10) |
| Net G — Locale exhibits | ✅ |
| U0 — Nets A–G shipped | ✅ |
| U1 — Route split | ✅ SHIPPED this iter |
| U2 — Defaults | 🟡 partial (defaults are 24h/zh_cn/local in code; not yet pinned in regression_net.py as standalone assertions, but covered by Net B + Net G) |
| U3 — Filter bar UI → v22 pills | ✅ (chrome validated by iter 6 visual audit) |
| U4 — Chart payload reuse + hover-isolate removal | 🟡 payload reuse ✅; hover-isolate removal not yet asserted in regression_net.py |
| U5 — Pulse, headline, feed chrome | ✅ (visual drift net covers 7 regions) |
| U6 — Responsive + i18n | 🟡 zh/en covered; mobile viewport not yet audited |
| U7 — Integration verification + DoD gate | 🟡 to run |

## Verdict

**PASS.** U1 (route split) shipped + Net F (/internal/ parity) shipped. Regression net 72/0. `/internal/` serves the legacy home; `/` serves the v22 chrome. Both pages return 200 with the correct chrome.

Remaining v22 work:
- U2 standalone pin (defaults)
- U4 hover-isolate absence assertion
- U6 mobile-viewport visual audit
- U7 integration verification + DoD gate confirmation
- End-to-end check via browser at `/` and `/internal/`

Scope delivered vs plan promised: match — U1 + Net F shipped together (the deferred Net F from iter 7 is now closed). No units deferred; no silent narrowing.