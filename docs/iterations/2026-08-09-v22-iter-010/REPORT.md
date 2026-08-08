# Iteration 010 (v22) — U4 hover-isolate removed from pw-chart.js; +2 assertions

**Date:** 2026-08-09
**Branch:** feat/v20-homepage-phase-a
**Scope:** Ship U4 (hover-isolate removal) — the plan body explicitly forbids hover-isolate brand hiding. iter 10 audit found `hoveredBrandIndex` actively controlling `ds.hidden` in `pw-chart.js` lines 153-190. Per mockup-canon + plan-execution contract: fix-now.

## Step 0 — Regression Net (pre-edit)

```
Passed: 76
Failed: 0
```

## Step 1 — Audit finding

`grep "hoveredBrandIndex" monitor/static/pw-chart.js` returned 6 active uses:

```
153:          var hoveredBrandIndex = -1;
174:              hoveredBrandIndex = bestBrand;
180:                  hoveredBrandIndex = ds._brandIndex;
188:            ds.hidden = hoveredBrandIndex === -1
190:              : (ds._brandIndex !== hoveredBrandIndex);
```

The `onHover` callback was hiding all non-hovered brand datasets on cursor proximity. Plan § U4 explicitly states: *"Chart: no hover-isolate brand hiding."* and § Net D: *"pw-chart.js post-change: no hover-isolate control flow (`hoveredBrandIndex` absent or inert)."*

## Step 2 — Implementation

### Fix in `monitor/static/pw-chart.js`

Replaced the entire `onHover` callback body (42 lines) with a 4-line no-op:

```javascript
// U4: hover-isolate removed (plan § Net D — `hoveredBrandIndex` must be
// absent or inert). Callback kept as a no-op so Chart.js does not error.
onHover: function (event, activeElements, c) {
  // no-op: all brand lines stay visible on hover
},
```

`grep "hoveredBrandIndex" pw-chart.js` after fix: 1 match, only in the explanatory comment. No active code references.

### Net D extension in `tests/regression_net.py`

`_check_chart_no_hover_isolate(session)` method — 2 new assertions:

1. Fetch `/static/pw-chart.js`, strip comments, assert no active `hoveredBrandIndex` references in non-comment code.
2. Find `onHover` callback body, strip comments, assert body is empty OR contains no `ds.hidden` mutations.

## Step 3 — Post-edit verification

```
Passed: 78
Failed: 0
```

All 76 prior assertions still green + 2 new U4 assertions = 78/0.

## P0 / P1 status after iter 10

| DoD gate | Status |
|---|---|
| Net A — Route & shell identity | ✅ |
| Net B — Window & locale defaults | ✅ |
| Net C — Filter contract | ✅ |
| Net D — Chart contract | ✅ SHIPPED this iter (+2) — hover-isolate absence pinned |
| Net E — Feed contract | ✅ |
| Net F — `/internal/` parity | ✅ |
| Net G — Locale exhibits | ✅ |
| U0 — Nets A–G shipped | ✅ |
| U1 — Route split | ✅ |
| U2 — Defaults | ✅ |
| U3 — Filter bar UI | ✅ |
| U4 — Chart payload reuse + no hover-isolate | ✅ SHIPPED this iter |
| U5 — Pulse/headline/feed chrome | ✅ |
| U6 — Responsive + i18n | 🟡 zh/en ✅; mobile-viewport not yet audited |
| U7 — Integration verification + DoD gate | 🟡 to run |

## Verdict

**PASS.** U4 shipped (hover-isolate control flow removed). Regression net 78/0. All brand lines now stay visible on chart hover, regardless of cursor proximity.

Remaining v22 work:
- U6 mobile-viewport visual audit
- U7 Integration verification + DoD gate confirmation

Scope delivered vs plan promised: match — U4 shipped. No units deferred; no silent narrowing.