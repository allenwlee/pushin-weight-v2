---
handoff_id: 2026-08-05-001
date_jst: 2026-08-05-11:55
author: grok (continuation)
canonical: /Users/fuchitalee/development/pushin-weight-v2/docs/ideation/mockups/06-tier1-composed.html
local_mirror: /Users/allenwlee/Downloads/pushin-weight-mockups/
status: resolved in v12 — open http://localhost:8765/06-tier1-composed.v12.html
---

# Mockup 06 — Filter pill dropdown, debug handoff

### written by Grok 4.3

## Resolution (v12)

Root causes that made real-Chrome taps look dead even when Playwright
passed earlier versions:

1. **`:focus-within` + bubble-phase click race.** CSS opened the panel
   on focus while a document-level bubble `click` outside-close and
   per-pill bubble handlers fought over `is-open`. Real sessions could
   end with `clicks > 0` and `opens === 0` (see v8 diagnostic).
2. **`overflow-x: auto` on `.filter-bar`.** Spec forces overflow-y to
   compute non-visible too, which **clips** `position:absolute`
   dropdowns. Playwright only asserted `display:block`, not on-screen
   pixels — so green tests still looked empty to a human.
3. **Dot heuristic.** "any unchecked" marked 未授权 `is-changed` on
   load because its single box defaults off. v12 compares against
   `defaultChecked` instead.

## What v12 does

- Single **capture-phase `pointerdown`** on `document` owns open/close.
  No per-pill bubble listeners, no `stopPropagation` dependency.
- Dropdowns use **`position: fixed`**, pinned via
  `getBoundingClientRect` on open / resize / scroll.
- Open state driven **only** by `.is-open` (no `:focus-within` open).
- Inner `.filter-bar-scroller` holds horizontal scroll; bar itself does
  not clip.
- `.title` / `.carat` / `.status-dot` → `pointer-events: none` so the
  click target is always the pill element.
- Keyboard: Enter/Space toggle, Escape closes.
- `__pwDebug.version === 12` for console checks.

## Local URL (server already running on :8765)

```
http://localhost:8765/06-tier1-composed.v12.html
```

Hard-refresh (Cmd+Shift+R), tap **品牌**. Expected:

```js
JSON.stringify(window.__pwDebug)
// clicks >= 1, opens === 1, visibleDropdowns === 1,
// lastTarget.inPill === true, version === 12
```

## Playwright verification (2026-08-05, headless Chromium)

- Open 品牌 → `openCount=1`, `ddDisplay=block`, `position=fixed`
- Uncheck first box → dropdown stays open, dot `is-changed`
- Open 话语 → only that pill open
- Outside topbar click → all closed
- 未授权 on load → `is-default` (not `is-changed`)
- No console errors

## Versions on disk

Local: `/Users/allenwlee/Downloads/pushin-weight-mockups/`
fuchitalee: `docs/ideation/mockups/`

| File | State |
|---|---|
| `06-tier1-composed.v11.html` | Prior debug build |
| `06-tier1-composed.v12.html` | **Current working** |
| `06-tier1-composed.html` (fuchitalee canonical) | = v12 |
| `06-tier1-composed.html` (local) | still Jul 29 baseline (no interactive dropdown) — use `.v12.html` |

## Next (out of scope for this fix)

1. Once user confirms real Chrome, strip `__pwDebug` → v13 clean baseline.
2. Port filter-bar + handler to 07 / 08 / 09 as `.v2.html`.
3. No commit made to `main` by this handoff update.
