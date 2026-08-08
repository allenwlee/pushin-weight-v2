# Iteration 005 (v22) — Visual-drift net + 4 drifted regions fixed

**Date:** 2026-08-08
**Branch:** feat/v20-homepage-phase-a
**Scope:** Implement § "Visual-drift detection: Element Audit + Chrome DevTools MCP" — create `tests/visual_tokens.py` (5 pinned regions) + `tests/element_audit.py` (Chrome DevTools MCP-driven diff runner); fix all drifted regions surfaced by the pre-edit audit per mockup-canon rule (no defer, no split, no review pause — every drift = fix-now).

## Step 0 — Regression Net (pre-edit)

```
Passed: 50
Failed: 0
```

## Step 1 — Visual Audit (pre-edit)

Chrome DevTools MCP `evaluate_script` captured `getComputedStyle()` for 5 pinned regions against the live page (`http://127.0.0.1:5050/?locale=en`):

| Region | Mockup pin | Live value | Status |
|---|---|---|---|
| `.pulse-chip .name` color | `rgb(243, 244, 246)` | `rgb(0, 0, 0)` | **DRIFT — user-reported defect** |
| `.voice-chip` bg | `rgba(124, 58, 237, 0.18)` | `rgba(124, 58, 237, 0.18)` | ✅ |
| `.voice-chip` color | `rgb(233, 213, 255)` | `rgb(233, 213, 255)` | ✅ |
| `.feed-handle` color | `rgb(243, 244, 246)` | `rgb(0, 0, 238)` | **DRIFT — browser default link blue** |
| `.feed-handle` text-decoration | `none` | `underline` | **DRIFT — browser default anchor** |
| `.feed-handle` font-weight | `600` | `400` | **DRIFT — browser default** |
| `.filter-button.is-active` | (not yet pinned in plan) | matches mockup | n/a |
| `.delta.up::before` | (data-dependent) | `NOT FOUND` | tolerated (no up-trending brands in current window) |

**4 drifted regions**: pulse-chip-name color + feed-handle (color, text-decoration, font-weight). All 4 fix-now per mockup-canon.

## Step 2 — Root cause

The CSS file `monitor/static/home-v20.css` had a `.pulse-chip .name` rule (expects `<span class="name">` inside `.pulse-chip`) but the template uses `<span class="pulse-chip-name">` (one-word class). Selectors didn't match → element fell back to browser/inherited styles. The `.feed-handle-link` rule in `monitor/static/dashboard.css` requires a `.feed` ancestor class, but the v22 home template uses `.feed-strip > .feed-scroll > .feed-rows` — no `.feed` class anywhere in the chain. Both rules exist; both are inert.

## Step 3 — Implementation

### New file: `tests/visual_tokens.py`

Single source of truth for pinned computed-style values. 5 regions pinned with BEFORE comments capturing the 2026-08-08 drift history. Reads from `VISUAL_TOKENS` dict; `regions()` and `pinned()` helpers for the audit runner.

### New file: `tests/element_audit.py`

Chrome DevTools MCP-driven diff runner. Reads `/tmp/element_audit_live.json` (written by MCP `evaluate_script`) + optional `/tmp/element_audit_mockup.json`, diffs against `visual_tokens.py`. Tolerates data-dependent absences (`.delta.up::before`). Exit 0 on all-pass, 1 on any drift. Designed to be driven by the agent's MCP session — the audit runner itself stays pure-Python.

### CSS fix: `monitor/static/home-v20.css` (appended)

```css
/* v22 iter 5: visual-drift fix — pin pulse-chip-name and feed-handle-link to mockup values */
.pulse-chip-name {
  color: var(--text);
  font-weight: 500;
}
.feed-strip .feed-handle-link {
  color: var(--text);
  font-weight: 600;
  text-decoration: none;
}
.feed-strip .feed-handle-link:hover {
  color: var(--link);
  text-decoration: underline;
}
```

`.feed-strip` is the existing v22 home parent class (already in template); using it instead of `.feed` matches the v22 chrome without breaking the legacy `/internal` page (which still has `.feed` ancestor).

## Step 4 — Visual Audit (post-edit)

```
{
  ".pulse-chip .name": {"color": "rgb(243, 244, 246)", "fontWeight": "500"},
  ".voice-chip": {"color": "rgb(233, 213, 255)", "backgroundColor": "rgba(124, 58, 237, 0.18)", ...},
  ".feed-handle": {"color": "rgb(243, 244, 246)", "textDecoration": "none", "fontWeight": "600"},
  ".delta.up::before": "NOT FOUND"
}
```

All 4 drifted regions now match the mockup pins. Pulse-chip-name visible. Feed handle styled correctly. No new drift introduced.

## Step 5 — Regression Net (post-edit)

```
Passed: 50
Failed: 0
```

## P0 / P1 status after iter 5

| Issue | Status |
|---|---|
| `.pulse-chip-name` color (black on dark fill) | ✅ RESOLVED (this iter) |
| `.feed-handle` color/text-decoration/font-weight | ✅ RESOLVED (this iter, surfaced by the audit) |

**All audit-surfaced visual drift in iter 5 closed.**

## Verdict

**PASS.** Visual-drift net shipped (`tests/visual_tokens.py` + `tests/element_audit.py`), 4 drifted regions fixed in CSS, regression net still 50/0 green. Foundation ready for Phase B (U3 filter chrome, U4 chart wrap, U5 pulse/headline/feed chrome, U6 responsive + i18n) — every future iter now has an automatic visual-diff gate.
