# v20 Homepage — Agentic Iteration Scenario Matrix

**Date:** 2026-08-07
**Target:** pushinweight.ai homepage (`/`) on the `feat/v20-homepage-phase-a` branch
**Visual source of truth:** `docs/ideation/mockups/06-tier1-composed.v20-{mobile,desktop}-{en,zhcn}.html`
**Viewport:** 390×844 (iPhone 14/15 standard), devicePixelRatio=2, isMobile=true
**Stop condition:** 100 iterations

## Local servers

| Surface | URL | Source |
|---|---|---|
| Live dev (Django) | `http://127.0.0.1:5050/` | fuchitalee `:5050` via SSH tunnel |
| Mockup canonical | `http://127.0.0.1:8001/06-tier1-composed.v20-mobile-en.html` | fuchitalee `:8001` (python -m http.server) |
| Mockup variants | `…/v20-mobile-zhcn.html`, `v20-desktop-en.html`, `v20-desktop-zhcn.html` | same server |

## Scenarios

| # | Scenario | Pre-state | Actions | Expected | Captures |
|---|---|---|---|---|---|
| A | Unauthenticated landing | no session | open `/` | login CTA, no data, show v20 layout | 1 live + 1 mockup |
| B | Authenticated default | logged in, defaults | open `/` | chart + filter rail, default brand set | 1 live + 1 mockup |
| C | Filter interaction | logged in, default | tap brand pill to unselect DeepSeek → wait → screenshot | chart line drops, mention count updates, KPIs reflect | 1 before + 1 after |
| D | Locale switch | logged in, defaults | tap locale toggle en ↔ zh_cn | chart labels, axis, legend, recommendation text all translated; layout reflows | 2 screenshots |
| E | Time window switch | logged in, defaults | tap 24h → 7d → 30d | chart axis and data update, no overlap | 3 screenshots |
| F | Empty / no-data state | logged in, filter to brand with no mentions | observe | graceful empty state, no broken layout, no "NaN" | 1 live + 1 mockup |
| G | Mobile scroll | logged in, defaults | swipe down | filter drawer collapses, chart scrolls, no overlap | 1 live + 1 mockup |
| H | Recommendations | logged in, defaults | scroll to recommendations section | 3-5 recommendation cards with @handle, text, permalink | 1 live + 1 mockup |

## Element Audit (Step 0 of every iteration)

Before any scenario capture, the live page must contain every visible element that the v20 mockup shows, and the visible elements must be functionally identical (same DOM role, same text content, same purpose, same approximate position). This is the load-bearing pre-flight — if the live page is missing a section, no scenario diff is meaningful.

Procedure:

1. `navigate_page` to the live URL (e.g. `/` for scenarios A-G, append `?locale=zh_cn` for locale variants).
2. Wait for the page to settle: `wait_for` the body, `list_console_messages` to confirm no JS errors, then `evaluate_script` a `document.readyState === 'complete'` check to confirm full load.
3. `take_snapshot` to get the a11y tree of the live page.
4. Navigate to the corresponding mockup (`v20-mobile-en.html` etc.), `take_snapshot` again.
5. **Viewport-morphology check** (see dedicated section above): `resize_page` to the other breakpoint, re-snapshot, verify the DOM structure morphs correctly (desktop -> mobile: feed nests under top-voices; mobile -> desktop: feed becomes a sibling).
6. Diff the two a11y trees by **section**, not by exact pixel position:
   - For each top-level `<section>`, `<header>`, `<nav>`, `<main>`, `<footer>` in the mockup, confirm an equivalent element exists in the live page.
   - For each heading (`h1`-`h6`), confirm the live page has the same heading at the same nesting level, with the same text content (or a translation-equivalent for `zh_cn` variants).
   - For each interactive control (`button`, `a[href]`, `input`, `select`), confirm it exists in the live page with the same role and similar text.
   - For the feed element specifically, verify its structural parent matches the breakpoint (under top-voices at mobile, sibling at desktop).
7. Write `audit.md` in the iteration dir with:
   - **Identical (matched):** elements present in both, same role, same text
   - **Missing on live (P0 blocker):** elements in the mockup but not on the live page - list each
   - **Extra on live:** elements on the live page but not in the mockup - usually acceptable, but flag if they break layout
   - **Different position:** elements present in both but in a different structural region - flag for design review
7. If any P0 missing element is found, **stop the scenario captures and surface to the user**. The v20 home cannot match the mockup if a section is missing. Fix the missing element first, then re-run the audit.

The audit is fast (~5-10 MCP calls) and runs every iteration. It catches regressions early - if a previous iteration's fix removed a section, the next iteration's audit catches it.

### What "identical" means at the audit level

The audit defines "identical" at the structural level: every visible region in the mockup exists on the live page with the same role and same text content. Rendering differences (color, spacing, animation, minor typographic drift) are captured by the per-scenario diff (Step 1) and ranked P1/P2/P3 - they are not blockers. Element-presence is the P0 gate.

### First iteration is audit-first

Iteration 1 runs the Element Audit against the canonical mobile-en mockup, then against mobile-zhcn (if locale is reachable), then runs scenario A (unauthenticated landing). Subsequent iterations re-run the audit as Step 0 first, then proceed to the chosen scenario.

## Viewport morphology (desktop -> mobile is the SAME page)

The v20 home is a **single responsive page**, not two separate desktop and mobile layouts. The mockup files (`v20-desktop-en.html`, `v20-mobile-en.html`) are previews of the same page at different breakpoints, not separate code paths. The plan body is explicit:

- One `<body>` element, one template, one CSS bundle.
- Tailwind responsive prefixes (`md:`, `sm:`) handle the layout changes.
- The feed lives **inside the "Top Voices" section** at mobile widths (it sits below the top-voices list rather than as its own full-width section). This is the load-bearing layout rule - if the feed is rendered as a separate region at mobile widths, the morphology is broken.

### What this means for the iteration loop

Per-iteration procedure for the responsive check:

1. **Element Audit at desktop width** (1440x900, or whatever the available window allows):
   - Run the standard audit against the `v20-desktop-en.html` mockup.
   - Capture the live page snapshot at desktop width.
   - Verify: top voices section, chart section, recommendations section, feed section all present. At desktop width, the feed is **its own full-width section** below the top voices.
2. **Element Audit at mobile width** (390x844):
   - `mcp__chrome-devtools__resize_page 390 844` to switch to mobile viewport.
   - Wait for the page to settle (`wait_for` on the body, `evaluate_script` for `document.readyState === 'complete'`).
   - Take the second snapshot.
   - Verify: top voices section is still present, but the **feed is now nested inside the top-voices section** rather than being its own sibling. If the feed re-renders as a separate section at mobile width, that's a P0 (morphology is broken).
3. **Morphology diff**: compare the two a11y trees specifically around the feed's structural parent:
   - Desktop: feed is a sibling of top-voices (both sit under `main`)
   - Mobile: feed is a child of top-voices
   - If the parent chain differs between breakpoints, the responsive code is using `hidden` / `block` toggles instead of relocating the DOM. That's wrong - the relocation should be in the DOM, not just visual.
4. Save both desktop and mobile snapshots to the iteration dir: `audit-desktop-snapshot.txt` and `audit-mobile-snapshot.txt`. Add a `morphology.md` with the parent's-a11y-path comparison.
5. The morphology check is part of every iteration's Element Audit, alongside the standard t=0 / t=60 time-based pass.

### Why this matters

Per the v18 plan, the v20 home is meant to ship as one responsive surface, not two separate pages. If the implementation gives desktop and mobile different templates or hides/shows DOM nodes by breakpoint instead of relocating them, the iteration report must flag this as a P0 - the page will not match the v20 contract, and any future change risks breaking one breakpoint without the other noticing.

The 4 v20 mockup files (desktop/mobile x en/zh_cn) are kept on disk because they are useful previews for designers and reviewers, but they should be **structurally identical** aside from the CSS-class differences that drive the layout. The audit can verify this by comparing the desktop and mobile snapshots' `<body>` children: they should be the same set of nodes, with the same IDs, with the same data-attributes, just different classlists.

## Time-based element testing (audit variation)

The v20 home displays live data that refreshes over time (recommendations stream, mention counts, time-series chart points). Static snapshots miss elements that only appear after a delay. **Every iteration must include a time-based test pass** that re-runs the audit after a 30s to 60s wait, and compares the delayed state to the t=0 state.

Why this matters:

- Recommendations and live-tile sections may be empty at t=0 and populate after the first data fetch completes (typical 30-60s depending on the harvester schedule).
- Auto-refresh logic (the 60s refresh in the original `pw-feed.js`) is exactly what we want to verify, not bypass.
- The audit at t=0 may show "missing recommendation cards" as a P0 blocker, but at t=60 the section is populated; the time-based pass prevents false positives.

Procedure for the time-based pass:

1. After completing the t=0 Element Audit, leave the live page open in the Chrome DevTools MCP browser.
2. Wait 60 seconds using `evaluate_script` to set a timer (since `wait_for` only waits for text, not time): `await new Promise(resolve => setTimeout(resolve, 60000))` - or use `wait_for` with a text that appears after data loads.
3. `take_snapshot` again to capture the post-wait a11y tree.
4. Diff the t=0 tree against the t=60 tree:
   - **New elements that appeared:** recommendation cards, mention rows, chart updates - these are expected, not blockers.
   - **New elements that appeared but should have been there at t=0:** P0 - the live page is failing to render critical content immediately.
   - **Elements that changed state (e.g. "Loading..." -> "47 mentions"):** expected, not a blocker.
5. Save both snapshots to the iteration dir: `audit-t0-snapshot.txt` and `audit-t60-snapshot.txt`.
6. Update `audit.md` with the time-based diff: section per element, marked `appeared_after_t0` or `present_at_t0`.

The time-based pass is essentially the same audit run twice with a 60s gap. It catches the most common category of false-positive P0 in data-driven UIs: "element missing" that is actually "element lazy-loaded after the data fetch completes."

For iteration 1 specifically, the time-based pass is doubly important because the recommendations and live-feed sections are likely empty at t=0 and may take a full minute to populate. **Do not flag time-populated elements as P0 blockers** - flag them as `expected_populated_at_t60` in the audit.

## Iteration loop

For each iteration N (1..20):

### Step 0 - Element Audit (FIRST thing every iteration)

Run the audit above against the live page + the corresponding mockup. If any P0 missing element is found, stop and surface to the user. **Do not proceed to scenario captures while P0 audit failures are open.**

### Step 1 - Scenario capture

1. Choose the highest-priority unresolved scenario from the previous iteration's report (or start with A if first iteration).
2. Use Chrome DevTools MCP to:
   - `resize_page 390x844` with `devicePixelRatio: 2`, `isMobile: true`
   - Disable animations: `evaluate_script "document.head.insertAdjacentHTML('beforeend', '<style>* { transition: none !important; animation: none !important; }</style>')"`
   - Execute the scenario's action sequence
   - `take_screenshot` to `/tmp/pushin-weight-iterations/NNNN-scenario-<name>/live.png`
   - Navigate to mockup, screenshot to `v20.png`
3. Write `diff-notes.md` with: matched, mismatched (ranked by severity), uncovered.
4. Verdict: pass / fail / uncovered.
5. Aggregate verdicts into `/tmp/pushin-weight-iterations/NNNN-report.md`.6. Run the time-based pass: wait 60s, take a second snapshot, write `audit-t60-snapshot.txt` next to t=0, update `audit.md` with the t=0 vs t=60 diff.
7. Commit iteration artifacts to `feat/v20-homepage-phase-a` branch.
8. If a clear blocker emerged, fix it (one commit, with plan-execution-contract line).
9. If iteration == 20, stop. Write `/tmp/pushin-weight-iterations/FINAL-SUMMARY.md`.

## Auth handling

Iteration 1: Element Audit (at t=0 and t=60) + scenario A only (no auth). Then sign in via the form on `/accounts/login/?next=/`, persist the session cookie in the Chrome DevTools MCP browser context, run audit + scenarios B, C, G, H.

If login fails (missing test account, password reset required, etc.), the agent surfaces the blocker rather than guessing. Logs in next iteration after the user resolves.

## What "matches" / "doesn't match" means

For each scenario, the diff is structural:

- **Matches:** layout, hierarchy, spacing, typography, component rendering, color, motion (post-disable)
- **Doesn't match:** same list, ranked:
  - **P0 (blocker):** element missing, broken layout, console error, JS error
  - **P1:** visible regression vs mockup
  - **P2:** polish / proportion / color
  - **P3:** nice-to-have

## Regression net (fix-breaks-fix prevention)

Every iteration must run the regression net FIRST, before declaring PASS on the new scenario. The net is pinned in `tests/regression_net.py` and asserts the structural elements from iter 2's audit that must not regress.

```python
# Pinned assertions — run before any scenario verdict
EXPECTED_SECTIONS = {
    "banner": {"logo", "window-toggle", "tz-pill", "locale-toggle"},
    "trending-models": {"8 brand pills", "Trending label"},
    "filter-groups": {"Brands", "Discourse", "account.role", "lang", "Sentiment", "Nationalism", "unsanctioned"},
    "chart": {"Daily total posts per brand canvas"},
    "top-voices": {"Top voices", "☆ by followers"},  # empty body is OK; heading must remain
    "feed": {"本窗口最新 heading", "feed-scroll container", "≥50 cards"},
}
EXPECTED_HEADER = "走个量 Pushin' Weight"
EXPECTED_FILTER_BUTTONS = 7
EXPECTED_TIME_WINDOWS = ["24h", "7d", "30d", "365d"]
EXPECTED_LOCALE_TOGGLE = {"zh_cn", "en", "original"}
```

If any assertion fails, the iteration is a **REGRESSION**, not a pass. The agent must revert or fix before advancing.

### Per-iteration contract

Replace the previous loop with this stricter sequence:

```
For iteration N:
  1. Run regression_net.py against the live page (asserts all PASSes from previous iterations still pass)
  2. Pick scenario from the matrix (table-driven, not agent-decided)
  3. Run Step 0 audit (current spec)
  4. Screenshot the mockup at the same viewport + locale (the previous loop skipped this — that's the drift)
  5. Screenshot the live page at the same viewport + locale
  6. Diff: live vs mockup (NOT live vs previous live)
  7. If diff shows new P0: file gap, add to implementation contract below
  8. If diff shows regression: STOP, revert or fix, surface to user
  9. Otherwise: write report, commit, advance iteration N+1
```

The critical change is **step 6: compare live against mockup, not against previous live**. This is the cure for the drift the user identified.

## Implementation contract (what infra the mockup needs)

The mockup shows the *surface* (UI shape). For each surface region, the chain that produces it must be documented. This table is the source of truth for "what needs to be built."

| Mockup region | DB query | View function | Template loop | Empty state | Loading state |
|---|---|---|---|---|---|
| **Top Voices** (`@kimi_moonshot (☆ 12)`) | Top 3 accounts by `follower_count` joined to mentions in current window, grouped by handle | `_multi_top_voices()` — **NOT YET ADDED** | `{% for v in top_voices %}` inside `<div class="headline-strip .body">` — **NOT YET ADDED** | "no top voices this period" | skeleton shimmer |
| **Trending models** (Kimi, DeepSeek, MiniMax...) | 7-8 brands ordered by `recent_post_count DESC` | `_build_brands_context()` — exists | `{% for brand in brands\|slice:":8" %}` — exists | brand list empty → no chips render | "loading brands..." shimmer |
| **Chart** (Daily total posts per brand) | Posts grouped by brand × day for home window | `_build_home_chart_payload()` — exists, returns `payload` | `{% include "monitor/_home_chart.html" %}` with `data-home` attr — exists | empty chart, no lines drawn | htmx GET /chart.html skeleton |
| **Latest in window** (feed cards) | Posts in current window, filtered, scrolled | `_get_feed_posts()` + `_enrich_posts_with_classifications()` — exists | `{% include "monitor/_feed_initial.html" %}` — exists | "no posts in window" | "loading more..." |
| **Locale toggle** (`中文 / EN / orig`) | n/a (session) | `_resolve_locale(request)` — exists | `<nav class="locale-toggle">` — **ADDED in iter 24** | n/a | n/a |
| **Filter pills** (Brands, Discourse, etc.) | static taxonomy | `_DASHBOARD_*` keys — exist | `{% for k in lang_entries %}` — exists | empty filter group | "loading filters..." shimmer |

### Mockup-side infra mirror

For each visible mockup region, the DB layer that produces it:

| Mockup region | Required DB table | Required fields | Required index |
|---|---|---|---|
| Top Voices | `monitor_account` joined to `feed_rows` | `handle`, `follower_count`, `mention_count` | `(window_days, mention_count DESC)` |
| Trending models | `monitor_brand` | `nickname`, `accent_color`, `recent_post_count` | `(recent_post_count DESC LIMIT 8)` |
| Chart | `feed_rows` aggregated | `created_at`, `brand_id`, `count` | `(created_at, brand_id)` |
| Latest in window | `feed_rows` | `tweet_id`, `text_en`, `author_handle`, `engagement` | `(created_at DESC, klass_filter)` |
| Locale toggle | session | `active_locale` | n/a |
| Filter pills | `monitor_taxonomy` (static) | `key`, `display_name` | n/a |

The "Top Voices" row has nothing in the view-function or template-loop columns — that's exactly the bug iter 9 found. This table makes the implementation gap explicit and falsifiable.

## Commit policy

Agent commits to branch `feat/v20-homepage-phase-a`. No push, no PR. Each commit gets the plan-execution-contract `Scope delivered vs plan promised: [match | narrower: deferred Y for reason Z]` line.
