---
title: Mobile-First Homepage Redesign
date: 2026-07-29
focus: mobile-first dashboard where real estate is precious; line graph is the first read; control panel drastically compressed; trending-model surface for devrel staff wanting a one-look state-of-LLM-on-X
status: ideation
artifact_type: ranked_candidates
output_format: markdown
---

# Mobile-First Homepage Redesign — Ideation

## Focus

> Imagine the homepage on web mobile. Real estate is precious. Stacked, the first read should be the line graph as is. The control panel should be drastically compressed. Devrel staff will want a one-look update on the state of LLM on X — e.g. they saw the latest Kimi 3 open weights released on Hugging Face and want to know what the X reaction has been generally. One seed idea: a top-trending div that shows which model is trending most in the past 15 min or 1 hour, with a one-sentence summary. Ideate what this limited web-first homepage looks like.

## Grounding Context

**Codebase context:**
- `monitor/templates/monitor/home.html` — current homepage template
- `monitor/templates/monitor/brand_home.html` — single-brand variant
- `docs/reference/home-pages-ui-guide.md` — full UI contract for both pages
- Current layout: `grid 2fr | 1fr` (`.home-pane`) — chart left, filter sidebar right
- Current mobile breakpoint: stacks chart above filters at < 900px
- Topbar: app title, brand count, window-toggle (1d/7d/30d), locale-toggle (中文/EN/orig)
- Filter panel: **6 groups, ~52 controls** (20 brands + 10 discourse + 6 post types + 3 roles + 6 US nationalism + 6 CN nationalism + 1 unsanctioned)
- Chart: 360 px tall line/area chart, htmx-polls every 60s, Chart.js canvas with `data-home='{...}'`
- Harvest cadence: every 15 min via Render cron (pushinweight-harvest)
- DB queries: per-call Postgres on Render (free tier, ~1GB disk)

**Topic context:**
- The persona is **devrel staff** at an AI lab / model publisher. They land on this homepage after seeing a Hugging Face release, want to know "is X talking about this and how?"
- Their flow is scan-and-decide: spend 5 seconds on the page, decide whether to drill in.
- Mobile means narrow viewport, slow network possible, one-thumb interaction.
- The "first read" must answer the question **"what just dropped / is hot right now in LLM on X?"** — the line chart shows volume over time, but doesn't answer "what specifically?"

**Past learnings:**
- `home-pages-ui-guide.md` is the canonical contract — must be updated if any idea changes the wire shape
- The b1 plan (`docs/plans/2026-07-28-001-feat-b1-purity-official-handles-plan.md`) is in flight — any harvest-funnel change will reshape volume per brand
- Filter state lives in a `pwFilters` cookie + window event; any compressed control panel must keep this working

**Topic axes (Phase 1.5 decomposition):**
1. Top-of-fold signal — what is the devrel user seeing within the first 300 px?
2. Compressed filter surface — where do the 52 controls go on mobile?
3. Trending-model surface — how is "what's hot right now" computed and shown?
4. Line chart retention — the chart is sacred; how does it stay prominent and tappable?
5. Drill-down path — from one-look to deep view, what is the gesture?
6. Refresh cadence — 60s htmx poll is fine on desktop; what's the mobile beat?

**Generation frame axis (frames used):** trend-signal, control-compression, gesture-flow, content-density, novelty-of-context, anti-pattern.

---

## Candidate Ideas

### 1. The "Pulse Bar" — first 64 px above the chart

**One-liner:** A horizontally scrollable strip of brand chips above the chart, each chip showing the last-15-min volume as a tiny sparkline + delta-vs-prior-window.

**Concrete shape:** Above the chart card, render a 64-px-tall strip: `[DeepSeek ↗ +47]` `[Kimi ↗ +312]` `[Qwen ↘ −12]` ... ordered by `delta_pct` desc, capped at ~12 visible chips with horizontal scroll for the rest. Each chip is tappable → drills into the brand's `/brand_home`. The chip's color matches the brand's line color in the chart below, so users learn the visual key.

**Where this fits:** answers Axis 1 (top-of-fold signal) and Axis 3 (trending-model surface) at once. The chips are the pulse bar — replaces the need for any separate "trending" component.

**Pros:**
- Fits the line graph's color code → no new visual language
- Tappable in thumb reach zone on mobile
- Naturally compresses (1 row vs full panel)
- Updates on the same htmx 60s poll as the chart

**Cons:**
- "What's trending" depends on which brands have a relative-spike, not absolute volume — Kimi +312 sounds huge, but on a base of 5, that's noise. Need a sensible floor.
- Sparkline-in-64px may render unreadable on tiny screens.

**Verdict:** **Strong.** Most directly addresses the focus.

---

### 2. The "Headline Strip" — single one-sentence sentence

**One-liner:** Below the chart, a single horizontal scrolling text strip: `Kimi 3 open weights — X volume +312% in last 60 min · 87 posts · top voices: @kimi_moonshot, @awnihannun, @rasbt`...

**Concrete shape:** Generated by a server-side template tag that picks the most-elevated brand in the last 60 min (spike detector), and includes: brand name, % delta, top voices by post volume, and the most-engaged post in the window (one URL). One row, tappable anywhere → opens that brand's home.

**Where this fits:** directly serves the user's "Kimi 3 just dropped on HF, what does X think" use case. One sentence is one read.

**Pros:**
- Pure information density — no extra components
- The single sentence is the first thing the eye lands on after the chart
- No mobile-vs-desktop distinction needed (it's just text)
- Computable from existing data (posts table has everything)

**Cons:**
- A spike detector needs a definition — % delta over what baseline? 60-min mean? 24-hr mean? This is non-trivial to get right.
- Generating the headline requires either a template-time computation (slow, stale) or a per-poll aggregation (each poll recomputes).

**Verdict:** **Strong.** Single sentence is a different visual register than the pulse bar; both could coexist.

---

### 3. The "Stacked Pinwheel" — chart shrinks, controls collapse to a chip

**One-liner:** Line chart stays full-width but reduces height from 360 → 180 px on mobile. Control panel becomes a single "Filters" chip at the chart's top-right; tapping opens a bottom-sheet modal with all 52 controls.

**Concrete shape:**
- Chart wrapper: `aspect-ratio: 2/1` on mobile (180 px tall at 360 px wide)
- Chart title row inside the card: `[Filters ⌄]` button at right; tap → slide-up modal from screen bottom
- Modal: full-height bottom sheet, scrollable filter groups, "Apply" CTA
- Dismiss returns to chart; selected filters shown as a row of small chips above the chart

**Where this fits:** Axis 4 (chart retention at smaller size) and Axis 2 (filter compression).

**Pros:**
- The chart stays the dominant visual, just shorter
- The bottom-sheet pattern is well-known on iOS/Android — discoverable
- Full filter surface still accessible — no feature loss

**Cons:**
- 180-px chart may lose legibility for 20+ lines; small sparklines inside the chart could clip
- A bottom-sheet modal adds a layer of friction (one extra tap)
- "Apply" CTA implies filters don't update live — needs careful state handling

**Verdict:** **Strong.** Especially if combined with Idea 1 or 2 above.

---

### 4. The "Drill-Down Tap" — chart line is a button

**One-liner:** Tapping a line in the chart navigates to that brand's home page; the chart on the homepage becomes a navigation surface, not just a display.

**Concrete shape:** Chart.js exposes click handlers on dataset points/lines. Wire `onClick` → `window.location = /<brand_slug>`. Visual cue: hovered line thickens slightly; tooltip shows the brand name + delta instead of just "Click to view". A "View all" link at chart footer goes to the full multi-brand view.

**Where this fits:** Axis 5 (drill-down path).

**Pros:**
- One-tap navigation; matches mobile muscle memory
- Zero new UI surface needed; the chart already encodes brand identity (color)
- Reduces the need for a brand filter or sidebar — the chart IS the brand picker

**Cons:**
- Chart.js tap-target detection on lines (vs points) needs explicit plugin or `onClick` config — may be fiddly
- Users wanting filters not for brands but for discourse/nationalism still need the bottom-sheet
- Risk: casual taps accidentally navigate away

**Verdict:** **Strong.** Especially if combined with the bottom-sheet modal from Idea 3.

---

### 5. The "Voice Pulse" — top 3 voices in last 60 min, not top 3 brands

**One-liner:** A small list of @handles, not brands. "Who is talking about LLMs most right now?"

**Concrete shape:** A vertical stack of 3 rows, each: avatar + handle + post count + last post snippet. Updates every 60s. Tap a handle → opens the user's profile in X (external link) OR a per-author filter view.

**Where this fits:** Reframes Axis 3 from "what model" to "who is talking about it" — which is the devrel staff's actual question when their model launches.

**Pros:**
- Devrel cares about voices (community, journalists, KOLs), not brand-aggregate volume
- More directly answers the "what's the X reaction" framing in the focus
- Compact: 3 rows ≈ 240 px

**Cons:**
- Requires a per-author aggregation query that doesn't exist yet (posts are keyed by tweet_id, not aggregated by author)
- An author who posts a lot about sports would be noise; need a brand-context filter inside the voice query
- Pivot from the existing model-centric UI is jarring for current users

**Verdict:** **Medium.** Useful as a secondary surface but adds an aggregation job. Better as a "below the pulse bar" widget.

---

### 6. The "Fresh Drop" callout — pin the latest model release to the top

**One-liner:** A static banner above the chart showing the latest model release from `huggingface.co` (e.g. Kimi 3, Llama 4, etc.) and the X-volume-delta arrow for that brand since release.

**Concrete shape:** Pull from Hugging Face's API or our `hf_orgs` table for the most recent release among tracked brands. Render: brand logo + "Kimi 3 released 2h ago" + small arrow. If the brand is in our tracked list, also show "+312% X volume".

**Where this fits:** Axis 1, but with a specific external-data trigger.

**Pros:**
- Directly addresses "I just saw Kimi 3 on HF" — surface the brand the user is thinking about
- Always-on, no spike detector required

**Cons:**
- Requires an HF API integration we may not have (or polling that adds infra)
- If a tracked model hasn't released in weeks, the banner is stale-looking
- Tag-team with the pulse bar: when a brand spikes, it appears in both — feels redundant

**Verdict:** **Medium.** Powerful when there's a recent release; falls flat during quiet periods.

---

### 7. The "Time Toggle" — quick-pick 15m / 1h / 24h above the chart

**One-liner:** Replace the existing `1d / 7d / 30d` window toggle (for desktop deep work) with a 4-button `15m / 1h / 24h / 7d` toggle on mobile. The default-15m view shows the pulse-bar data most relevant to "what just dropped".

**Concrete shape:** A button group above the chart card. 15m/1h/24h are mobile-first; 7d is desktop. Pressing one changes the chart's query window (same htmx endpoint, new query param). The pulse bar updates to match the same window.

**Where this fits:** Axis 6 (refresh cadence) and Axis 3 (trending over different windows).

**Pros:**
- 15m window directly serves the "what just dropped" use case
- Same control system as the existing window-toggle — no new component
- Lets the user pivot from "what's hot NOW" (15m) to "what's been hot this week" (7d)

**Cons:**
- 15-min charts are visually noisy (jagged lines); may need smoothing
- Re-querying for 15-min data every 60s may hit Postgres harder than 24-hr aggregations
- Removes the original 1d default which some users rely on

**Verdict:** **Strong.** Tactical and mobile-natural. Worth pairing with Idea 1 or 2.

---

### 8. The "Single-Pane Card" — replace the 2-column grid with one tall scrolling card

**One-liner:** Drop the desktop's `2fr|1fr` grid entirely on mobile; everything lives in one scrollable column with cards stacked.

**Concrete shape:**
```
[Topbar — minimal: title + window toggle]
[Pulse bar — 64 px]
[Chart card — 180 px tall, tap-to-drill]
[Headline strip — 1 row]
[Truncated feed — top 5 most-engaged posts in the current window, "see all" → ]
[Footer — link to single-brand view]
```

**Where this fits:** Axis 1, 2, 4 — combines everything into one scroll.

**Pros:**
- One single column is the iOS/Android idiom — minimal learning curve
- Each card is independently tappable → natural drill-down
- 1-line summary works in this layout

**Cons:**
- Removes the desktop's efficient 2-column layout unless a `@media (min-width: 900px)` rule restores it
- 5-6 cards stacked may exceed thumb-reach; need to test scroll depth on a 6.1" screen
- The desktop experience shouldn't regress — must keep the 2fr|1fr for ≥ 900px

**Verdict:** **Strong.** This is more of a layout philosophy that wraps several other ideas; clean home for ideas 1-4 together.

---

### 9. The "Drag-to-Reorder Brands" — users curate their own pulse bar

**One-liner:** The pulse bar's chips are draggable; long-press to reorder, double-tap to pin/unpin.

**Concrete shape:** HTML5 drag-and-drop on mobile (works with touch in modern browsers via polyfill, OR a long-press → drag handler). Pinned brands stay at the front. State stored in localStorage + pwFilters cookie.

**Where this fits:** Axis 3 personalization.

**Pros:**
- Each devrel staff can make the bar their own — Kimi folks pin Kimi, Mistrol folks pin Mistral
- Differentiator vs everything else

**Cons:**
- Drag-and-drop on mobile is fragile; native gesture conflict with scroll
- Per-user state sync between devices is non-trivial
- Adds engineering surface for marginal benefit

**Verdict:** **Weak.** Skipped — too much engineering for a small benefit, can come later.

---

### 10. The "Self-Loading Trend Story" — a one-line paragraph that expands on tap

**One-liner:** Like Idea 2 but the headline strip is a one-line summary that, on tap, expands inline to a 3-sentence paragraph with more context (top 3 posts, top voices, sentiment breakdown).

**Concrete shape:**
```
[Kimi 3 open weights dropped 2h ago — X volume +312% · 87 posts · tap for detail]
  ↓ tap
[Kimi 3 open weights dropped 2h ago on Hugging Face.
 X volume up +312% in the last 60 min (87 posts).
 Top voices: @kimi_moonshot (12 posts), @awnihannun (8), @rasbt (6).
 Sentiment: 71% positive, 18% mixed, 11% negative. Tap for full breakdown →]
```

**Where this fits:** Axis 1 with progressive disclosure (the drill-down on the same surface).

**Pros:**
- Single tap reveals depth without leaving the homepage
- "Sentiment breakdown" is a small compute, not a heavy LLM call
- Self-contained — doesn't depend on external APIs

**Cons:**
- Sentiment classification isn't currently in the pipeline (only after the b1 plan lands)
- The expanded view competes with the chart for attention; may need to overlay or push the chart down
- A "87 posts" count requires an aggregation query

**Verdict:** **Medium.** Better than Idea 2 alone (single sentence can be too thin) but heavier to implement.

---

### 11. The "Quick-Lane Filters" — replace 52 checkboxes with 4 pill toggles

**One-liner:** Above the chart, 4 large pill buttons: `[All]` `[Release]` `[Buzz]` `[Meme]` — each maps to a preset filter combo.

**Concrete shape:**
- `[All]` → all brands, all post types, no nationalism filter
- `[Release]` → release + announcement post types only
- `[Buzz]` → release + meme + commentary post types
- `[Meme]` → memes + jokes only
- Tap → updates the chart via htmx, same pwFilters cookie backend
- Long-press / "More filters" → opens the bottom-sheet from Idea 3

**Where this fits:** Axis 2 (filter compression). The 90% case for a mobile user.

**Pros:**
- 4 buttons fit easily above the chart; ~56 px tall
- Each preset maps to existing filter keys — no new data
- Drill-down to full filters via the bottom-sheet

**Cons:**
- "Buzz" / "Meme" labels need product clarification — what's the difference?
- Requires us to define which filter combos each preset maps to; a config doc
- The presets may not match every user's filter habit; some may always want the full panel

**Verdict:** **Strong.** Simple, native to mobile, complementary to the bottom-sheet.

---

### 12. The "Bilingual Sidebar" — half the filter panel is zh_cn on mobile too

**One-liner:** (Anti-pattern) — preserve the full filter sidebar in the same place, just shrink the font.

**Verdict:** **Rejected.** The focus says "drastically compressed" — this is the opposite. The filter panel currently holds 52 controls; on a 360-px-wide phone, even at 12 px font, that's 5+ screen-heights of scroll. Antithetical to the brief.

---

### 13. The "Bottom Tab Bar" — five fixed tabs at screen bottom

**One-liner:** Move from "scroll to find" to "tab to switch": tab bar at bottom = `Pulse / Chart / Feed / Filters / More`.

**Concrete shape:** Sticky `<nav class="tab-bar">` with 5 icons + labels at the bottom of every page. Each tab is a section of the homepage; tapping scrolls to it or replaces content. iOS/Android idiom.

**Where this fits:** Mobile-native navigation pattern; complements the stacked-card layout (Idea 8).

**Pros:**
- Standard mobile pattern; no learning curve
- Always thumb-reachable

**Cons:**
- Wastes 56 px of vertical real estate on a screen already short on it
- Adds navigation state (which tab is active) we don't currently track
- Conflicts with the "Pulse bar" idea (Pulse as both a top widget AND a tab is redundant)

**Verdict:** **Weak.** Real estate cost too high. Tab bars are great for app shells but heavy for a content-dense dashboard.

---

### 14. The "Voice Notes for Charts" — micro-audio summaries

**One-liner:** A play button next to the chart that reads aloud "Kimi is up 312 percent, Qwen is flat, DeepSeek is down 12" via Web Speech API.

**Verdict:** **Rejected.** Novelty without utility for the devrel persona; sound in an open-plan office is a footgun; Web Speech API support is uneven.

---

### 15. The "Comparison-Overlay Mode" — pinch out to see two time windows overlaid

**One-liner:** Pinch-zoom on the chart overlays last-week vs this-week as semi-transparent curves.

**Verdict:** **Weak.** Mobile pinch-zoom is already overloaded by browser zoom; adding semantic pinch is confusing. Better as a desktop feature later.

---

### 16. The "Empty-View Skeleton" — what does the homepage look like during a quiet 15-min window?

**One-liner:** When no brand is spiking, the pulse bar reads "Quiet — no model is trending right now" and shows the top 3 by absolute volume in a muted style.

**Where this fits:** Anti-brittleness for Idea 1.

**Pros:**
- The pulse bar degrades gracefully — important since spikes are rare
- Sets correct user expectation: "if you want to see real activity, look at 1h or 7d"

**Cons:**
- None significant — this is just the empty-state design.

**Verdict:** **Strong.** Cheap to add and necessary if we ship Idea 1.

---

### 17. The "Tap-and-Hold for Tooltip" — gesture-rich interaction

**One-liner:** On the chart, tap-and-hold a line for 0.5s to expand a tooltip with brand name + delta; tap (no hold) to drill in.

**Where this fits:** Axis 5 (drill-down gesture).

**Pros:**
- Distinguishes "look" from "go"
- Standard mobile chart gesture

**Cons:**
- Holding for 0.5s may feel sluggish; 0.3s is too short for accidental-tap protection
- Accessibility: motion-impaired users may struggle

**Verdict:** **Weak standalone; consider as a complement to Idea 4 if we go that route.**

---

### 18. The "Static QR-Ready Card" — printable / shareable homepage state

**One-liner:** A "Share this snapshot" button that generates a PNG of the current homepage state with a deep link back.

**Verdict:** **Weak.** Out of scope for mobile UX focus; better as a future "weekly digest" feature.

---

## Rejection Summary (one-line each)

| # | Idea | Reason |
|---|---|---|
| 9 | Drag-to-reorder | Mobile drag fragility, sync complexity, low benefit |
| 12 | Shrink the sidebar | Antithetical to "drastically compressed" |
| 13 | Bottom tab bar | Wastes real estate, conflicts with Pulse bar |
| 14 | Audio summaries | Novelty without utility, bad in shared spaces |
| 15 | Pinch-to-compare | Browser-zoom conflict |
| 17 | Tap-and-hold tooltip | Useful only as Idea 4 complement, weak standalone |
| 18 | QR-share | Out of scope |

---

## Survivors — Ranked

### Tier 1 (recommended composition — pick together)

**Idea 1 (Pulse Bar) + Idea 3 (Stacked Pinwheel / chart at 180 px) + Idea 4 (Tap-to-drill chart) + Idea 8 (Single-Pane Card layout) + Idea 11 (Quick-Lane Filters) + Idea 16 (Quiet-state skeleton)**

This is **the** mobile-first homepage. Concretely:

```
┌─────────────────────────────────────────────┐
│ Pushin' Weight · 多模态       [15m|1h|24h|7d]│  ← topbar compressed
├─────────────────────────────────────────────┤
│ [DeepSeek ↗][Kimi ↗ +312%][Qwen ↘][Mistral] │  ← Pulse bar, 64 px
├─────────────────────────────────────────────┤
│ Filters: [All][Release][Buzz][Meme]   ⌄    │  ← Quick-lane pills + "more"
├─────────────────────────────────────────────┤
│ ┌─────────────────────────────────────────┐ │
│ │  Multi-brand line chart, 180 px tall    │ │  ← tap line = drill in
│ │  (line = brand, tap = navigate)         │ │
│ └─────────────────────────────────────────┘ │
├─────────────────────────────────────────────┤
│ Kimi 3 open weights · X volume +312% in 60m │  ← Headline strip (Idea 2/10)
│ Tap for detail →                           │
├─────────────────────────────────────────────┤
│ Top 5 most-engaged posts in 15m window     │  ← truncated feed
│ 1. @kimi_moonshot: "..." — 1.2k ❤️          │
│ 2. @awnihannun: "..." — 480 ❤️              │
│ ...                                        │
│ See all →                                  │
└─────────────────────────────────────────────┘
```

This fits the brief exactly:
- Line graph stays as the first read (well, second-after-pulse — but the pulse is a 64-px ancillary that complements, not replaces)
- Control panel drastically compressed (52 controls → 4 pills + bottom-sheet)
- One-look update on the state of LLM on X via the pulse bar + headline strip
- Works on a 360 px wide screen, all in thumb reach

**Effort estimate:** Medium. Touches:
- New endpoint for pulse-bar data (cached, recomputed on harvest tick)
- New endpoint for headline strip (LLM-free, SQL aggregation)
- `home.html` mobile-block overhaul: topbar simplified, pulse bar, chart card with 180-px height on mobile, quick-lane pills
- `dashboard.css` mobile media query tweaks
- `pw-chart.js` click-handler wiring
- New bottom-sheet partial for full filter access
- Empty-state handling for quiet 15-min windows

### Tier 2 (consider as follow-up)

**Idea 5 (Voice Pulse)** — useful as a "top voices" sub-widget under the pulse bar. Implementation requires a per-author aggregation query (medium cost).

**Idea 7 (Time Toggle)** — quick to add. Pair with Tier 1 to give users 15m/1h/24h/7d without changing desktop defaults.

**Idea 10 (Self-Loading Trend Story)** — expands Idea 2's headline into a tap-to-reveal 3-sentence paragraph with sentiment. Requires sentiment classification (planned for post-b1).

### Tier 3 (deferred)

- Idea 6 (Fresh Drop callout) — depends on HF API integration; revisit when we have HF polling.
- Idea 9, 12, 13, 14, 15, 17, 18 — rejected or deferred.

---

## Open Questions for the Next Step

1. **What's a "spike"?** Ideas 1, 2, 10 all depend on a definition. Need to pick a window (60-min baseline? 24-hr baseline?) and a threshold (absolute? z-score? % delta?). Should be product-led.
2. **Sentiment classification** (Idea 10) — is this on the post-b1 roadmap? If not, the trend-story expansion slips.
3. **Is mobile traffic a meaningful share of pushinweight.ai visits today?** If < 10%, this redesign is lower priority than the desktop 2-fr refinement; if > 30%, ship Tier 1 first.
4. **Does the line chart's brand-color key match the pulse bar chip colors?** The reference doc says yes (color-swatch span next to brand rows), but verify the brand color is consistent across chart.js datasets and CSS custom properties.

---

## What to Do Next

The natural follow-up is `ce-brainstorm` on **Idea 1 + Tier 1 composition** — picking the specific spike definition, the pulse bar's visual language, and the bottom-sheet filter UX. That should produce a requirements-only unified plan that `ce-plan` can convert into implementation units (new pulse-bar endpoint, headline endpoint, home.html mobile overhaul, CSS tweaks, click handlers, empty-state).

If Tier 1 feels too big for one plan, slice into two:
- **Plan A:** Pulse bar + headline strip + quick-lane pills (no chart changes)
- **Plan B:** Chart tap-to-drill + 180-px mobile chart height + bottom-sheet filter modal