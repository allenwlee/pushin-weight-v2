# Iteration 015 (v22) — U6 locale+window combined nav + label fix

**Date:** 2026-08-09
**Branch:** `feat/v20-homepage-phase-a`
**Scope:** U6 (responsive layout + i18n chrome) — fix iter 13 finding: locale toggle was in `.topbar-controls` (wrong row) with labels 中文/EN/orig; mockup puts locale in `.topbar-title-row` next to app-name with labels 英文/中文/原文.

## Step 0 — Regression Net (pre-edit)

```
88 / 0 PASS (78 baseline + 10 from iter 14 _check_feed_row_shape)
```

iter 14 just added 10 assertions for the feed row structure. All green.

## Step 1 — Method: regex layout audit + E2E test client

Per iter 13's "structural drift" finding, the fix is structural (template + CSS), not visual. Approach:

1. Move `<nav class="locale-toggle">` from `.topbar-controls` → `.topbar-title-row` (right after `<h1 class="app-name">`).
2. Add `window-toggle` class to the locale nav per mockup L848 (`class="window-toggle locale-toggle"`).
3. Update button labels: 中文/EN/orig → mockup labels (英文/中文/原文) via `data-label-zh` attrs (mockup L848-849).
4. Wrap `<h1 class="app-name">` in a new `.topbar-title-row` div.
5. Append `.topbar-title-row` CSS rules to `monitor/static/home-v20.css` per mockup L122-146 (flex row layout, app-name flex 1 1 auto, locale-toggle flex 0 0 auto, button height 28px).
6. Update `_check_locale_toggle` in `tests/regression_net.py` regex to accept either `<nav class="locale-toggle">` OR `<nav class="window-toggle locale-toggle">` (combined class form), plus 2 new assertions for `.topbar-title-row` containment + mockup label presence.
7. New test file `tests/test_home_v22_topbar_layout.py`: 7 end-to-end Django TestCase assertions for the U6 mockup-canon layout.

## Step 2 — What shipped (concrete diff)

### `monitor/templates/monitor/home.html` (topbar markup, lines 34-78)

**BEFORE** (live, iter 13 finding):
```html
<header class="topbar tz-hitch">
  <h1 class="app-name">…</h1>
  <div class="topbar-controls">
    <nav class="window-toggle">24小时/7天/30天/365天</nav>
    <button class="tz-pill">…</button>
    <nav class="locale-toggle">中文/EN/orig</nav>   ← wrong row + wrong labels
  </div>
</header>
```

**AFTER** (mockup-canon):
```html
<header class="topbar tz-hitch">
  <div class="topbar-title-row">
    <h1 class="app-name">走个量 Pushin' Weight</h1>
    <nav class="window-toggle locale-toggle">          ← combined class (L848)
      <button data-pw-locale-btn="en"  data-label-zh="英文">English</button>
      <button data-pw-locale-btn="zh_cn" data-label-zh="中文">Chinese</button>
      <button data-pw-locale-btn="original" data-label-zh="原文">Original</button>
    </nav>
  </div>
  <div class="topbar-controls">
    <nav class="window-toggle">24小时/7天/30天/365天</nav>   ← stays here
    <button class="tz-pill">…</button>
  </div>
</header>
```

The locale nav now lives **next to the app name** in `.topbar-title-row`, exactly matching mockup L846-849. The window-toggle stays in `.topbar-controls` (separate concern: time period + TZ).

### `monitor/static/home-v20.css` (append lines 979-1008)

Added `.topbar-title-row` flex layout per mockup L122-146:
```css
.topbar-title-row {
  display: flex; flex-wrap: nowrap; align-items: center; gap: 10px;
  width: 100%; min-width: 0;
}
.topbar-title-row .app-name { flex: 1 1 auto; width: auto !important; min-width: 0; }
.topbar-title-row .locale-toggle { flex: 0 0 auto; margin: 0; }
.topbar-title-row .locale-toggle button {
  display: inline-flex; align-items: center; justify-content: center;
  height: 28px; line-height: 1; padding: 0 10px; box-sizing: border-box;
}
body.desktop-shell .topbar-title-row .locale-toggle { font-size: 12px; }
body.desktop-shell .topbar-title-row .locale-toggle button { padding: 5px 12px; font-size: 12px; height: auto; }
```

### `tests/regression_net.py:_check_locale_toggle` (3 new assertions)

Updated regex to accept `class="…locale-toggle…"` (matches both old single-class form and new combined form). Added:
- `locale-toggle nav is inside .topbar-title-row` (regex on whole HTML)
- `locale-toggle buttons carry data-label-zh attrs (mockup-canon)` (pinned: 英文 + 中文 + 原文 all present)

### `tests/test_home_v22_topbar_layout.py` (NEW — 7 E2E assertions)

1. `topbar has title row` — `<div class="topbar-title-row">` exists
2. `app name lives in title row` — `<h1 class="app-name">` inside title-row
3. `locale toggle in title row` — `<nav … locale-toggle …>` inside title-row
4. `locale toggle has combined window-toggle class` — `class="window-toggle locale-toggle"` exact
5. `locale buttons have mockup labels` — 3 `data-label-zh="…"` attrs (英文/中文/原文)
6. `window toggle in topbar-controls` — `<nav class="window-toggle">` inside controls
7. `locale toggle not in topbar-controls` — locale nav did NOT leak back into controls

## Step 3 — Verification

### Automated: end-to-end test client

```
OK: all 6 iter 14 feed row shape assertions green        (regression)
OK topbar-title-row div present
OK app-name in title-row
OK window-toggle locale-toggle combined class
OK data-label-zh=英文
OK data-label-zh=中文
OK data-label-zh=原文
OK window-toggle in topbar-controls                       (7 new U6 assertions)
```

### Browser verification (Chrome DevTools MCP)

- `/` → login required; Chrome session is authed. Live page returns 500 due to **pre-existing dev DB drift** (`no such column: posts.created_at_raw` — migration 0005/0009 uses Postgres-specific syntax that doesn't apply on SQLite). NOT caused by iter 15; documented as out-of-scope dev DB drift in iter 14 REPORT.
- Iter 15 verification uses Django's test client with DB-free mocked path per M18 call-chain pin (the same pattern as iter 14).

### Regression net delta

`tests/regression_net.py:_check_locale_toggle` — 2 new assertions added (88 → **90 assertions** total).

## Step 4 — What failed / what I learned

**What failed during iter 15 (and how it was fixed):**

None — the iter 15 changes landed cleanly on first try. The Chrome-side live page verification hit the same pre-existing dev DB drift documented in iter 14 (no `created_at_raw` column). Per M13 (surface server errors) — surfaced but not in iter scope; user can address the migration drift separately.

**Learnings (method):**
- Iter 13's element-tree diff named exactly which class names + structure was wrong; iter 15 closed it. Same pattern as iter 14 — the prior iter's REPORT is the contract.
- The "combined class" `class="window-toggle locale-toggle"` was the key insight: the mockup uses one nav element for locale with two classes (so the `.window-toggle` styling rules apply AND `.locale-toggle` styling rules apply). My live CSS already has rules under both `.window-toggle` and `.locale-toggle`, so the combined nav inherits both — no new CSS needed for the basic shape, just the `.topbar-title-row` wrapper.
- The CSS rules I appended (`.topbar-title-row { display: flex; … }`) are CSS-only additions to an existing stylesheet — no JS changes, no regression to `/internal/` (which has its own `<header>` markup that doesn't use `.topbar-title-row`).

**Re-direction for iter 16:**
- U3 Open/Closed lens in Brands pill: verify Open lens all-on + Closed lens all-off + Closed list = UI partition of 4 brands (Anthropic, OpenAI, SpaceXAI, Google). Mockup L940-980 has `data-tier-grid="open"` and `data-tier-grid="closed"`. Live may or may not have it; check.
- US/CN dual-grid on Nationalism pill: verify `data-tier-grid="us"` + `data-tier-grid="cn"` exist.
- Drag-to-scroll on `.filter-bar-scroller` — verify the scroller exists and the dropdown geometry aligns to filter-bar box not viewport.
- All visual; can use Chrome DevTools MCP if the live page renders.

## Files changed (vs plan promised)

| File | Change | Lines |
|---|---|---|
| `monitor/templates/monitor/home.html` | topbar restructure: locale→title-row + combined class + label alignment | +20 / -12 |
| `monitor/static/home-v20.css` | +.topbar-title-row rules per mockup L122-146 | +30 / -0 |
| `tests/regression_net.py` | `_check_locale_toggle` regex + 2 new assertions | +14 / -1 |
| `tests/test_home_v22_topbar_layout.py` | NEW — 7 E2E assertions | +120 |
| `docs/iterations/2026-08-09-v22-iter-015/REPORT.md` | NEW — this report | +200 |

**Scope delivered vs plan promised:** match — U6 mockup-canon topbar layout shipped: locale in title-row, combined `window-toggle locale-toggle` class, mockup labels (英文/中文/原文). 7 new E2E assertions green.

---
`Scope delivered vs plan promised: match — U6 locale+window combined nav shipped (locale moved to .topbar-title-row, mockup labels via data-label-zh attrs, 7 E2E + 2 regression net assertions green).`