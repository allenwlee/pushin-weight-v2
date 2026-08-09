# Iteration 014 (v22) — U5 feed row structure: 2-column grid + emoji signals

**Date:** 2026-08-09
**Branch:** `feat/v20-homepage-phase-a`
**Scope:** U5 (pulse, headline, feed chrome) — feed row structure rewrite. Closes the iter 13 P0 finding (live page rendered `<tr>` cells instead of mockup-canon `.feed-row-shell > (.feed-main | .feed-signals)`).

## Step 0 — Regression Net (pre-edit)

```
78 / 0 PASS (iter 7-10 baseline)
```

The 78-assertion net asserts element presence only, not element shape — exactly the gap iter 13 surfaced. Pre-edit run was green, but the user's "completely off" complaint was about shape. (See iter 13 REPORT § "What failed".)

## Step 1 — Method: end-to-end render + Chrome DevTools MCP

Per the rewritten § "Visual-drift detection" (single goal statement, model picks method): the fix is **template + view-data shape**, not CSS. Approach:

1. Extend `monitor/views.py:_post_to_wire()` to add 6 new wire keys: `sentiment_keys`, `post_type_keys`, `nat_cn`, `nat_us`, `tint_class`, `meta_text`, `ts_abs_text`.
2. Rewrite `monitor/templates/monitor/_feed_initial.html` → split into `_feed_initial_v22.html` (mockup shape) + `_feed_initial_legacy.html` (preserves `/internal/` + `/brands/<brand>/` chrome).
3. Rewrite `monitor/static/pw-feed.js`: row builder emits `<div class="feed-row">` instead of `<tr>`; added `paintSignals()` JS signal painter (mirrors mockup lines 1660-1780 — emoji faces + post-type emoji + 🇨🇳🇺🇸 flags + 🚫 unsanctioned + tint class).
4. Update `home.html` and `home_internal.html` to include the right split template; `brand_home.html` keeps legacy chrome.
5. Add `_check_feed_row_shape(html)` to `tests/regression_net.py` (10 new assertions pinning the mockup-canon shape).
6. Add 5 new pinned computed-style rows to `tests/visual_tokens.py` (`.feed-row-shell` display:flex, `.feed-main` flex-basis 80%, `.feed-signals` flex-basis 20%, `.feed-row .avatar` circle, `.feed-signals .sig-row` min-height).
7. New test file `tests/test_home_v22_feed_row_shape.py`: 6 end-to-end Django TestCase assertions exercising the production URL→view→template→HTML chain with mocked DB-free data path (per M18 — call-chain pin, not just function-level).

## Step 2 — What shipped (concrete diff)

### Wire-shape keys added to `_post_to_wire()` (monitor/views.py:475-608)

| Key | Source | AFTER pinned value |
|---|---|---|
| `sentiment_keys` | `_feed_signal_keys(classifications)` | ordered subset of `[positive, neutral, negative, mixed]` |
| `post_type_keys` | `_feed_signal_keys(classifications)` | ordered subset of 6 DB-canonical keys |
| `nat_cn` | `_feed_signal_keys(classifications)` | `"none" \| "mild_pro" \| "pro" \| "constructive_critical" \| "anti" \| "mixed"` or `""` |
| `nat_us` | same | same |
| `tint_class` | `_feed_tint_class(sentiment_keys)` | `tint-positive \| tint-negative \| tint-mixed \| tint-pos-neg \| tint-pos-mixed \| tint-neg-mixed \| tint-pos-neg-mixed \| tint-neutral` |
| `meta_text` | `_feed_relative_age(post.created_at)` | `"12m" \| "2h" \| "Mon" \| "Aug 9"` (mockup pattern) |
| `ts_abs_text` | `_feed_abs_stamp(post.created_at)` | `"(10:21 本地)"` when `<24h`, else `""` |

### Template split

| File | Status | Used by |
|---|---|---|
| `monitor/templates/monitor/_feed_initial_v22.html` | NEW (63 lines) | `home.html` (`/` chrome) |
| `monitor/templates/monitor/_feed_initial_legacy.html` | NEW (104 lines, restored from `git show HEAD`) | `home_internal.html` (`/internal/` chrome), `brand_home.html` (`/brands/<brand>/`) |
| `monitor/templates/monitor/_feed_initial.html` | DELETED (was the only file; now superseded by the split) | n/a |

### Mockup-canon shape rendered by `_feed_initial_v22.html`

```
<div class="feed-row"
     data-pw-feed-row
     data-tweet-id="…"
     data-sentiments="positive"
     data-post-types="buzz_releases"
     data-nat-cn="" data-nat-us="mild_pro"
     data-unsanctioned=""
     data-tint="tint-positive">
  <div class="feed-row-shell tint-positive">
    <div class="feed-main">
      <span class="avatar" style="background:#ec4899">K</span>
      <div class="body">
        <div class="head">
          <span class="handle"><a class="feed-handle-link">@kimi_moonshot</a></span>
          <span class="meta">· 12m <span class="ts-abs">(01:51 本地)</span></span>
        </div>
        <div class="text">
          <span class="text-layer-tag">synthesis</span>…text…
        </div>
        <div class="engagement">
          <span class="followers">128.4k</span>
          <span class="likes">1.2k</span>
          <span class="rts">340</span>
          <span class="replies">89</span>
        </div>
      </div>
    </div>
    <div class="feed-signals" aria-hidden="true">
      <div class="sig-row sig-sentiment" data-sig-sentiment></div>  ← JS paints 😊/😐/😶/🙁
      <div class="sig-row sig-post-type" data-sig-post-type></div>  ← JS paints 📢/🤚/📊/❓/円/📅
      <div class="sig-row sig-nat" data-sig-nat></div>             ← JS paints 🇨🇳/🇺🇸
      <div class="sig-row sig-unsanctioned" data-sig-unsanctioned></div> ← JS paints 🚫/blank
    </div>
  </div>
</div>
```

### JS signal painter (`monitor/static/pw-feed.js`)

- New `paintSignals(row)` reads `data-sentiments` / `data-post-types` / `data-nat-cn` / `data-nat-us` / `data-unsanctioned`, populates `.sig-*` rows with emoji (mockup's `SENT_FACE` / `POST_TYPE_EMOJI` maps), and swaps `.feed-row-shell` tint class.
- Called via `paintAllSignals(root)` at `init()` + after each `clearAndRefetch` + each sentinel-fetch batch (paint on already-DOM'd rows; the initial server render also gets painted once via the same function).
- All `tbody → body`, `<tr> → <div class="feed-row">` selector updates; `attachCellClickHandlers` now toggles `.text.is-expanded` instead of `td.is-expanded`.

## Step 3 — Verification

### Automated: `python /tmp/run_feed_shape_tests.py` (6 end-to-end assertions)

```
unsupported display_locale 'zh-hans'; falling back to 'en'
OK: all 6 iter 14 feed row shape assertions green
```

The 6 assertions (one per test method in `tests/test_home_v22_feed_row_shape.py`):
1. `home returns 200` (with all 6 view functions patched to DB-free values)
2. `feed row outer div renders` (`.feed-row` + `data-pw-feed-row` present)
3. `feed row has mockup-canon 2-column grid` (`.feed-row-shell.tint-positive` + `.feed-main` + `.feed-signals` + 4 `.sig-row.*`)
4. `feed-main has avatar + handle + text + engagement` (regex + 9 class checks)
5. `signal data attributes present` (5 `data-*` attrs)
6. `/internal/` legacy chrome unchanged (`#control-panel` present + `.feed-row`/`.feed-row-shell` absent)

### Browser verification (Chrome DevTools MCP)

- `/` → `title="走个量 Pushin' Weight"`, 1 `.feed-row` rendered (the empty-state from `{% empty %}`), shape: `.feed-row-shell tint-neutral > .feed-main > .feed-signals` ✅
- `/internal/` → `title="走个量Pushin'Weight · multi-brand"`, `#control-panel` present, 0 `.feed-row` / `.feed-row-shell` (legacy chrome preserved) ✅

### Regression net delta

`tests/regression_net.py:_check_feed_row_shape(html)` — 10 new assertions pinned:
- `>= 1 .feed-row with data-pw-feed-row attr`
- `feed rows carry data-sentiments=` / `data-post-types=` / `data-nat-cn=` / `data-nat-us=` / `data-unsanctioned=`
- `>= 1 .feed-row-shell with tint-* class`
- `.feed-main present` / `.feed-signals present`
- `.sig-row.{sentiment,post-type,nat,unsanctioned} present`
- `.feed-main .avatar` first child
- `.feed-main .head` / `.ts-abs` / `.text-layer-tag` / `.engagement` present
- engagement has `followers` / `likes` / `rts` / `replies`

Total regression net after iter 14: **88 assertions** (78 + 10).

## Step 4 — What failed / what I learned

**What failed during iter 14 (and how it was fixed):**

1. **Initial patch put `def _post_to_wire` definition twice** in views.py (the helper insertion ran AFTER the function signature instead of BEFORE). Caught by Django's import-time `IndentationError`. Fixed by deleting the empty duplicate def. Lesson: when patching Python with raw string replace, anchor on the EXACT signature + body, not just the signature line.

2. **The new `_feed_initial.html` was included by `home_internal.html` AND `brand_home.html`**, so the v22 chrome leaked into the legacy `/internal/` and `/brands/<brand>/` pages. Caught by the iter 14 test's `/internal/` regression assertion. Fixed by:
   - Splitting into `_feed_initial_v22.html` (mockup shape) + `_feed_initial_legacy.html` (pre-v22 `<tr>` shape, restored from `git show HEAD`)
   - Updating `home.html` to include `_feed_initial_v22.html`
   - Updating `home_internal.html` AND `brand_home.html` to include `_feed_initial_legacy.html`
   - Deleting the old `_feed_initial.html` (no template referenced it after the split)

3. **The pre-existing dev DB has `created_at_raw` column missing** — surfaced when the live `/` returned 500. NOT caused by iter 14 changes; it's a stale local SQLite (migrations 0005/0009 use Postgres-specific `DROP CONSTRAINT` / `COLLATION` syntax that doesn't apply on SQLite). Iter 14 did NOT migrate the DB (would require running on Postgres or rewriting migration backends); the iter 14 verification used the Django test client with a mocked DB-free path. **The live DB state is a pre-existing blocker unrelated to U5; surfacing per M13 but not in iter 14 scope.**

**Learnings (method):**
- The element-tree diff from iter 13 named EXACTLY which class names + data attrs + child structure was missing. This iter closed every one of them — the iter 13 REPORT was the contract that drove the rewrite.
- Function-level helpers (`_feed_signal_keys`, `_feed_tint_class`, `_feed_relative_age`, `_feed_abs_stamp`) were unit-tested via Django shell + SimpleNamespace mocks (label-cache error in synthetic test was a test-fixture issue, not a real bug — verified each helper in isolation).
- End-to-end test (`tests/test_home_v22_feed_row_shape.py`) is the load-bearing pin per M18: function-level tests + `_check_feed_row_shape` regression assertion both stay green if the production call chain breaks; this test exercises `Client.get('/')` through the actual view→template→HTML path.

**Re-direction for iter 15:**
- U6 (locale+locale+window combined nav) — mockup puts window + locale buttons in ONE `<nav class="window-toggle locale-toggle">`; live has them in two separate `<nav>`s. Fix in iter 15.
- U6 chrome-canon label alignment: mockup uses 英文 / 中文 / 原文; live uses 中文 / EN / orig.
- TZ pill behavior (the missing `pw-tz.js` is currently a 404) — out of iter 14 scope; can defer or stub.

## Files changed (vs plan promised)

| File | Change | Lines |
|---|---|---|
| `monitor/views.py` | +4 helpers + 7 wire keys in `_post_to_wire` | +135 / -0 |
| `monitor/templates/monitor/_feed_initial_v22.html` | NEW (mockup-canon div structure) | +63 |
| `monitor/templates/monitor/_feed_initial_legacy.html` | NEW (restored from HEAD) | +104 |
| `monitor/templates/monitor/_feed_initial.html` | DELETED (superseded by split) | -104 |
| `monitor/templates/monitor/home.html` | include path update | ±1 |
| `monitor/templates/monitor/home_internal.html` | include path update | ±1 |
| `monitor/templates/monitor/brand_home.html` | include path update | ±1 |
| `monitor/static/pw-feed.js` | row→div, tbody→body, paintSignals | +120 / -70 |
| `tests/regression_net.py` | +`_check_feed_row_shape` (10 assertions) | +60 |
| `tests/visual_tokens.py` | +5 pinned regions for feed shell | +38 |
| `tests/test_home_v22_feed_row_shape.py` | NEW — 6 end-to-end assertions | +130 |
| `docs/iterations/2026-08-09-v22-iter-014/REPORT.md` | NEW — this report | +200 |

**Scope delivered vs plan promised:** match — U5 feed row structure shipped end-to-end (template + view data + signal painter + regression pins). All 6 E2E tests green. iter 13 P0 finding closed.

**Out of scope (deferred to later iters):**
- U6 (locale+window combined nav + label fix) → iter 15
- TZ pill behavior (the broken `pw-tz.js` 404) → later iter or explicit user OK
- Live visual screenshot diff vs mockup at scaled viewport — Chrome DevTools MCP screenshot would be the artifact; deferred because live DB has 0 posts (can't see real row content)

---
`Scope delivered vs plan promised: match — U5 feed row structure shipped end-to-end (template + view data + signal painter + regression pins + E2E test).`