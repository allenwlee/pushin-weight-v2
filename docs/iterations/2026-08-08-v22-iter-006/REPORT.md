# Iteration 006 (v22) — Phase B chrome visual-drift audit + fixes

**Date:** 2026-08-08
**Branch:** feat/v20-homepage-phase-a
**Scope:** Wider visual-drift audit on Phase B regions (U3 filter chrome, U4 chart wrap, U5 pulse/headline, U6 responsive feed). Surface browser-default leaks and fix per mockup-canon.

## Step 0 — Regression Net (pre-edit)

```
Passed: 50
Failed: 0
```

## Step 1 — Visual audit (pre-edit, live vs v22-master)

| Region | Mockup pin | Live value | Status |
|---|---|---|---|
| `.locale-toggle button` color | `rgb(148, 163, 184)` | `rgb(0, 0, 0)` | **DRIFT — browser default** |
| `.locale-toggle button` border-radius | `6px` | `0px` | **DRIFT** |
| `.locale-toggle button` border-color | `rgb(148, 163, 184)` | `rgb(0, 0, 0)` | **DRIFT** |
| `.feed-row` color | `rgb(243, 244, 246)` | `rgb(0, 0, 238)` | **DRIFT — browser link blue** |
| `.feed-row` border-color | `rgb(243, 244, 246)` | `rgb(0, 0, 238)` | **DRIFT** |
| `.filter-group-button` | (matches mockup) | matches | ✅ |
| `.filter-pill` | (matches mockup) | matches | ✅ |
| `.chart-wrap` | (matches mockup) | matches | ✅ |
| `.pulse-bar-wrap` | (matches mockup) | matches | ✅ |
| `.voice-chip` | (iter 4 pin) | matches | ✅ |

**3 new pinned regions, 5 drifts surfaced, all browser-default leaks** (same root cause class as iter 5: CSS rules don't match the v22 template's actual selectors).

## Step 2 — Implementation

### CSS appended to `monitor/static/home-v20.css`

```css
/* v22 iter 6: visual-drift fix — pin locale-toggle and feed-row to mockup values */
.locale-toggle button,
[data-pw-locale-btn] {
  color: rgb(148, 163, 184);
  background: transparent;
  border: 1px solid rgb(148, 163, 184);
  border-radius: 6px;
  padding: 5px 12px;
  font-size: 12px;
}
.feed-row,
.feed-rows > * {
  color: var(--text);
  border-color: var(--text);
}
```

### `tests/visual_tokens.py` — 2 new pinned regions

`.locale-toggle button` (6 properties) and `.feed-row` (2 properties) added with BEFORE comments. Total pinned regions: 5 → 7.

## Step 3 — Post-edit verification

```
Regression net: 50/0 PASS
Visual audit (locale-toggle): color rgb(148,163,184) ✓, border-radius 6px ✓, border rgb(148,163,184) ✓
Visual audit (feed-row): color rgb(243,244,246) ✓, border rgb(243,244,246) ✓
```

All 5 drifts closed. No new drift introduced.

## Step 4 — Status

| Phase B unit | Visual-drift status |
|---|---|
| U3 Filter chrome | ✅ all sampled regions match (filter-group-button, filter-pill) |
| U4 Chart chrome | ✅ chart-wrap matches mockup |
| U5 Pulse/headline chrome | ✅ pulse-bar-wrap, voice-chip, pulse-chip-name (iter 5) match |
| U6 Responsive feed | ✅ feed-strip, feed-handle (iter 5), feed-row (iter 6) match |

**No remaining visual drifts in the U3-U6 sampled regions.**

## Verdict

**PASS.** 5 visual drifts closed; 2 new pinned regions added; regression net stable at 50/0; visual-drift net now covers 7 regions. Phase B chrome cutover has been substantially validated against the v22-master mockup. Remaining work toward v22 condition: U0 (Nets A–G), U7 (Integration verification), and DoD gate confirmation.