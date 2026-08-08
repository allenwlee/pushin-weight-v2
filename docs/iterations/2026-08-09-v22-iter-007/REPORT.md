# Iteration 007 (v22) — Comprehensive regression nets: C, D, G shipped; F deferred

**Date:** 2026-08-09
**Branch:** feat/v20-homepage-phase-a
**Scope:** Implement v22 plan § "Comprehensive regression nets" — extend `tests/regression_net.py` with Nets C (filter contract), D (chart contract), G (locale exhibits). Net F (`/internal/` parity) deferred to iter 8 because U1 (route split) hasn't shipped yet.

## Step 0 — Regression Net (pre-edit)

```
Passed: 50
Failed: 0
```

## Step 1 — Implementation

### Net C — Filter contract (added)

Pinned the 5 dashboard filter key tuples from `monitor/views.py` (lines 110-141):

```
_DASHBOARD_DISCOURSE_KEYS    (10 keys: genuine_hype, sarcasm, dunk_yingyang, ...)
_DASHBOARD_POST_TYPE_KEYS    (6 keys: buzz_releases, hands_on_usage, ...)
_DASHBOARD_ROLE_FILTER_KEYS  (4 keys: official, staff, community, other)
_DASHBOARD_NATIONALISM_KEYS  (6 keys: none, mild_pro, pro, ...)
_DASHBOARD_LANG_FILTER_KEYS  (13 keys: en, zh-hans, ja, es, tr, fr, pt, ...)
```

Plus asserted the 7 filter groups render as `<div class="filter-pill" data-group="...">` in the home HTML (the actual wire shape, not the assumed `data-pw-filter-group` attribute the plan body documented).

### Net D — Chart contract (added)

Three assertions: chart canvas present (data-pw-chart / home-chart / `<canvas>`), chart heading text matches both en (`Daily total posts per brand`) and zh_cn (`每日各品牌帖子总数`), `pw-chart.js` script loaded.

### Net G — Locale exhibits (added)

Three assertions: app title has zh_cn `走个量`, English name `Pushin' Weight` (any apostrophe variant), locale toggle exposes exactly 3 buttons (`zh_cn / en / original`).

## Step 2 — Net F deferral (audit finding)

Per Net F spec, the audit ran against `http://127.0.0.1:5050/internal/`:

```
final URL: http://127.0.0.1:5050/internal/
status: 404
size: 4882 bytes
```

**`/internal/` returns 404.** Root cause: iter 1-4 shipped the v22 chrome to `/` (replacing the legacy home in-place) but never added the `/internal/` route to `monitor/urls.py`. The plan body § Goal Capsule explicitly requires *"Do not delete or replace the existing homepage in place: move today's homepage to /internal/"* and Stop Condition S2 forbids deleting/breaking `/internal` legacy behavior. This was missed because iter 1-4 PASS verdicts were structural-only (HTML regression net) and didn't include URL-routing checks.

**Decision:** defer Net F to iter 8, ship iter 7 with C/D/G only. `tests/regression_net.py` annotated with the deferral note pointing at iter 8 for the Net F implementation.

## Step 3 — Post-edit verification

```
Passed: 62
Failed: 0
```

12 new assertions added (6 filter contract + 3 chart contract + 3 locale exhibits). No regressions vs the pre-edit 50.

## P0 / P1 status after iter 7

| DoD gate | Status |
|---|---|
| Net A — Route & shell identity | partial (Net F subset deferred; URL routing not yet audited) |
| Net B — Window & locale defaults | ✅ shipped (pre-existing 7 assertions) |
| Net C — Filter contract | ✅ shipped this iter (+6) |
| Net D — Chart contract | ✅ shipped this iter (+3) |
| Net E — Feed contract | ✅ shipped (pre-existing 8 assertions) |
| Net F — `/internal/` parity | 🟡 DEFERRED to iter 8 (route 404, U1 missing) |
| Net G — Locale exhibits | ✅ shipped this iter (+3) |
| Visual drift net | ✅ shipped iter 5 |
| Regression net green | ✅ 62/0 |

## Verdict

**PARTIAL PASS.** Nets C, D, G shipped (62 assertions green). Net F deferred with explicit annotation. Iter 8 must ship U1 (route split — move legacy home to `/internal/`) + Net F assertion to close the `/internal/` 404 gap.

Scope delivered vs plan promised: narrower — Net F deferred for reason Z (U1 route split not yet shipped; iter 1-4 replaced legacy home in-place at `/` without adding `/internal/` route. iter 8 will land U1 + Net F together).