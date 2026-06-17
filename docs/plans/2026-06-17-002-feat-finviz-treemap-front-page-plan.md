---
title: Finviz-Style Treemap Front Page
type: feat
status: active
date: 2026-06-17
deepened: 2026-06-17
---

# Finviz-Style Treemap Front Page

## Overview

Replace the existing 9-card grid on `/` with a Finviz-style treemap that uses inline SVG to render one tile per LLM model. Tile area encodes tweet volume in a fixed window (Q1 release + Q4 commenter_capture attention signals). Tile fill encodes the change in positive/negative tweet rate between the current and prior window (a defined polarity score, not raw counts). Drill-down navigation is preserved. The existing grid is moved to `/grid` (its JSON/fragment endpoints `/api/grid.html` and `/api/grid.json` keep their existing paths so htmx polling on the new `/grid` route continues to work without code changes). v1 ships with 11 enabled models — the 7 currently tracked plus Mistral, StepFun, Baidu ERNIE, and Tencent Hunyuan. Tiles for models with zero collected posts render as a faded "no data" state.

**Conventions used throughout this plan:** All JSON payload keys and Python identifiers are snake_case (matching the existing `/api/grid.json` shape and the project's Python style).

## Problem Frame

DevRel's daily entry point into the x-monitoring system is a 9-card grid that lists each model with a 14-day stacked-area sparkline, a signal breakdown, and a top-3 of highest-liked posts. That view answers "what happened to each model" but is weak at the one thing DevRel does first every morning: **identify which models are gaining or losing attention, and which are quiet vs. struggling**. Finviz solves exactly this for equities: one glance ranks the universe by area and flags movement by color. We want the same affordance for the model set, using tweet rate change in place of stock price change and tweet volume in place of market cap.

The replacement is the natural next step after v1.6 (May 30 → June 7 brainstorm → 9-card grid → treemap). v1 is intentionally minimal: no hover subcategories, no per-tile detail panels, no smooth transitions on re-render. The goal is one-glance triage.

**Who is affected:** MiniMax devrel team (single-user MVP).
**What is changing:** `/` now shows the treemap. The existing 9-card grid moves to `/grid` (its JSON/fragment endpoints `/api/grid.html` and `/api/grid.json` keep their existing paths so htmx polling on the new `/grid` route continues to work without code changes). The grid is **preserved**, not retired. Per-model drill-down at `/model/<model_id>` is unchanged. The enabled model set grows from 7 to 11 with query YAMLs and config additions for the 4 new models.
**Why it matters:** A treemap front page answers the morning triage question ("which models moved?") in under five seconds. The current grid forces sequential scanning of nine cards and treats absence-of-criticism as good news, which it is not.

## Requirements Trace

- **R1.** `/` renders a treemap: one inline SVG, one `<rect>` (or `<g>` group) per enabled model, server-side rendered, polled at the existing 30s cadence. The existing 9-card grid is moved to `/grid` and remains fully functional — same cards, same htmx polling, same drill-down links. A 2-tab **topbar nav strip** (`Treemap | 9-Card Grid`) appears on both `/` and `/grid`; the active tab is determined server-side per route and gets `aria-current="page"` plus a CSS active class. The strip is keyboard-focusable, lives inside the existing topbar, and persists across htmx re-renders (it's not inside the `#treemap` or `#grid` htmx target).
- **R2.** Tile area = `commenter_capture_count + release_count` in the current N-day volume window. N is `DashboardConfig.treemap_volume_window_days` (default 7). Fits inside the existing 14-day post window.
- **R3.** Tile fill = polarity score, defined as `(praise_rate_current − criticism_rate_current) − (praise_rate_prior − criticism_rate_prior)`, where each `rate = signal_count / total_q1_to_q6_count` in the respective window (`total_q1_to_q6_count` is the sum of Q1, Q2, Q3, Q4, Q5, Q6 signal counts — all posts classified into one of the 6 buckets). `prior` = the window of the same length immediately preceding the current window. The score is mapped to a 5-step divergent palette interpolated between the existing `--red` (`#ef4444`) and `--green` (`#10b981`) CSS tokens, with a mid-stop at the existing `--muted` (`#8b949e`) token. **Sparse-data guards:** if `current_total == 0 AND prior_total == 0`, return 0.0 (muted); if `prior_total == 0 AND current_total > 0`, define prior rates as 0 (do not propagate NaN); if `current_total == 0 AND prior_total > 0`, return a sentinel value (e.g. `None`) that the route maps to the muted bin and that the UI labels "went dark" to distinguish from "no change". The polarity_score is a float in approximately `[-1.0, +1.0]`.
- **R4.** Each tile is clickable and navigates to `/model/<model_id>`. Drill-down is non-negotiable.
- **R5.** Tile border = the model's existing `MODEL_ACCENT_COLORS` accent. Tile fill = polarity color. This follows the Finviz convention of fill = comparison metric, border = identity.
- **R6.** A model with zero posts in the current window renders as a single faded tile spanning the full treemap width at low opacity (e.g. 0.15) with a "no data" label, rather than a 0-area rect. Same shape applies to all 4 new models on day 1.
- **R7.** The topbar retains the existing `<span id="last-run-stamp">` element so the existing `dashboard.js` staleness timer continues to work without modification.
- **R8.** v1 ships with 11 enabled models: the existing 7 (MiniMax AI, Qwen, DeepSeek, GLM, Xiaomi MiMo, Moonshot Kimi, InclusionAI) plus Mistral, StepFun, Baidu ERNIE, Tencent Hunyuan. The `minimax` model_id maps to the existing display name "MiniMax AI" (not "MiniMax").
- **R9.** For each of the 4 new models, a `data/queries/<model_id>.yaml` is added with at least one `Q1` (release, `from:<official_handle>`) and one `Q2` (community question) query, matching the query-string format used in the existing 7 YAMLs (see `data/queries/qwen.yaml` and `data/queries/deepseek.yaml`). Q1 and Q2 use only the `min_faves:` operator (project convention); `-filter:replies` and `min_retweets:` are not in `KNOWN_OPERATORS` and must not appear in the new YAMLs. The Q1 brand-name fallback (if the official handle is unconfirmed) must include a context disambiguator: `("Mistral" OR "Mixtral") (AI OR model OR LLM OR 7B OR 8x7B) -weather -meteorology`.
- **R10.** Per-model `display_name`, `accent_color`, and `KNOWN_MODELS` registry entries are added for each new model.
- **R11.** The treemap is layout-deterministic for a given (model list, volumes, polarity scores) input. The `squarify` library is deterministic by contract (no `random.seed` calls in its code path; same input → same `(x, y, dx, dy)` cell list). Repeatable tests are possible without monkey-patching.
- **R12.** Tests cover: deterministic layout, no overflow (sum of tile areas equals the SVG viewBox), `data-href` on every tile, polarity formula correctness on a synthetic 3-model fixture, "no data" tile rendering for a model with 0 posts, route 200 on `/` for an empty store and for a populated store.
- **R13.** `/api/treemap.json` payload shape is documented: `{ "tiles": [{ "model_id", "display_name", "accent_color", "area_weight", "polarity_score" }, ...], "fetched_at", "window": { "volume_days", "change_days", "anchor" } }`. `polarity_score` is a float in `[-1.0, +1.0]` computed per R3; 0.0 indicates no data in either window or no change between windows; `null` indicates the "went dark" sentinel. The `tiles` array is sorted by `area_weight` desc with ties broken by `display_name` ascending (alphabetical). The sort is performed in the route handler that builds the tile list (the same handler that calls `build_treemap_svg`); `build_treemap_svg`'s caller is responsible for pre-sorting. The `window.anchor` is `latest_run.finished_at` (with wall-clock fallback at the route layer, mirroring `serialize_grid_card`). External consumers can rely on this shape. **`/api/grid.json` is NOT deprecated and NOT aliased** — it keeps serving the grid's per-model card payload at its existing path (used by htmx polling on the new `/grid` route). The previous `/api/grid.json` `{ "cards": [...] }` shape is unchanged because the grid itself is unchanged; the new `/api/treemap.json` shape is a sibling, not a replacement.

## Scope Boundaries

### In scope (v1)

- New `x_monitor/treemap.py` module: slice-and-dice layout (~30–60 lines), polarity computation (~40 lines), inline SVG string assembly (~40 lines). Total ~120 lines, no third-party dependency.
- New template `x_monitor/templates/treemap.html.j2` and partial `x_monitor/templates/_treemap_svg.html.j2`.
- New CSS rules in `x_monitor/static/dashboard.css` for the treemap container and tile hover.
- Replacement of the `/` route in `x_monitor/dashboard.py` to render the treemap page.
- The existing 9-card grid moves to `/grid` (and the fragment/JSON endpoints to `/api/grid.html` and `/api/grid.json` at their existing paths). The grid is **preserved**, not removed. A 2-tab **topbar nav strip** (`Treemap | 9-Card Grid`) appears on both `/` and `/grid`; the active tab is server-side-determined. This is the primary cross-link affordance, replacing the previous "← View 9-card grid" / "← Back to treemap" text-link pair.
- New `DashboardConfig.treemap_volume_window_days: int = 7` config key. (R3 uses the same window length for current and prior, so no separate `treemap_change_window_days` is needed in v1; the prior window is always `treemap_volume_window_days` long.)
- New `KNOWN_MODELS` entries, `MODEL_DISPLAY_NAMES`, `MODEL_ACCENT_COLORS` for Mistral, StepFun, Baidu ERNIE, Tencent Hunyuan.
- New `data/queries/{mistral,stepfun,ernie,hunyuan}.yaml` files following the existing query-string template in `data/queries/qwen.yaml` and `data/queries/deepseek.yaml`.
- New test file `tests/test_treemap.py` with the unit's required scenarios.

### Out of scope (deferred to v1.1+)

- Subcategory nesting (Finviz's "Industry → Sector → Stock" hierarchy). v1 is one-level.
- Hover detail panels, tooltips, smooth color transitions.
- Per-signal tile color (using Q1–Q6 signal type as a third visual dimension).
- Splitting InclusionAI into sub-brands (Ling/Ring/Ming). The single `inclusionai` model_id remains.
- LLM-based polarity scoring. v1 uses the discrete Q1–Q6 signals; an LLM classifier (e.g. sentiment for non-praise/non-criticism tweets) is a v1.1+ concern.
- Adjusting the `daily_ceiling: 333` budget to accommodate 4 new models. v1 ships with the existing budget; if the new models saturate it, a follow-up plan adjusts the ceiling.
- Backfilling historical data for the 4 new models. They start collecting on day 1; the "no data" tile covers the period before the first successful run.

## Context & Research

### Repo patterns to follow

- **Inline SVG returned as a string from a Python module** — `x_monitor/account_graph.py` builds a Fruchterman-Reingold force-directed graph and returns the `<svg>` markup as a string. The new `x_monitor/treemap.py` follows the same shape: a pure function `(input) -> str` that the route calls and passes via `{{ treemap_svg | safe }}`. No JavaScript framework, no d3, no vis.js, no Chart.js matrix plugin. The drill-down page already loads `chart.js@4.4.0` via CDN; the treemap does not need a second chart library because its layout is a one-shot static arrangement that re-renders every 30s.
- **Server-side rendering, client-side polling** — `x_monitor/templates/grid.html.j2` uses `<main id="grid" hx-get="/api/grid.html" hx-trigger="every {{ poll_seconds }}s" hx-swap="innerHTML">` to re-render only the inner content. The treemap reuses this exact pattern with `<main id="treemap" hx-get="/api/treemap.html" hx-trigger="every {{ poll_seconds }}s" hx-swap="innerHTML">`. The outer `<main>` persists, so the `hx-trigger` attribute survives re-renders.
- **CSS custom properties for color tokens** — `x_monitor/static/dashboard.css` defines `--red`, `--green`, `--yellow`, `--bar-release`, `--bar-criticism`, `--bar-praise` on `:root`. The treemap's polarity color is interpolated between `--red` and `--green` server-side (Python emits the exact `rgba()` string per tile based on polarity bin). No new colors are introduced.
- **`serialize_grid_card` is the existing per-model aggregate** — `x_monitor/dashboard.py:130-243`. The treemap needs similar per-model data: windowed counts of Q1 (release), Q3 (criticism), Q4 (commenter_capture), Q6 (praise), and the total. These can be computed from the same `Store.get_all_posts(model_id)` data that `serialize_grid_card` consumes, so the treemap helper runs alongside it.
- **The "now" anchor is `latest_run.finished_at`** — used by `serialize_grid_card` to keep the 24h/7d/14d windows stable across renders. The treemap uses the same anchor so the volume and prior-period windows are coherent with the grid that previously occupied `/`.
- **Tests use `DashboardApp` + `tempfile.TemporaryDirectory` + `app.app.test_client()`** — established in `tests/test_dashboard.py`. New `tests/test_treemap.py` follows the same pattern.

### Institutional learnings

- **Polarity ≠ absence of criticism.** The pipeline classifies tweets into discrete buckets (Q1 release, Q2 community_question, Q3 criticism, Q4 commenter_capture, Q5 other, Q6 praise). Most tweets land in Q5 (other) or Q4 (commenter_capture) — they are not positive, they are simply uncategorized. The plan must define polarity as a rate change between two windows, with an explicit denominator, so a quiet model is not painted maximally green.
- **Q1 + Q4 is the "attention" volume signal.** Q5 (other) is too noisy to use for tile area. Q1 (release) is the official-channel signal. Q4 (commenter_capture) is the reply-volume signal. Together they reflect genuine attention and suppress the Q5 noise floor.
- **The current "9-card grid" framing in the existing plan is being replaced.** The plan `docs/plans/2026-06-07-001-feat-chinese-models-x-monitoring-plan.md` describes "9-model grid + community account graph" as the v1 UI. The treemap supersedes the grid; the drill-down graph stays. This is consistent with the ideate doc's Frame 2 #5 ("search for signal, not noise") and Frame 3 #8 ("actionable, not comprehensive").
- **Staleness indicator must be reused, not re-implemented.** v1.6 added client-side staleness (`#last-run-stamp.stale`) in `dashboard.js`. The treemap topbar reuses the same `<span id="last-run-stamp">` element so the existing timer picks it up automatically.
- **No treemap / squarify / d3 code exists in the repo.** This is a fresh module. The plan uses the `squarify` PyPI package (Apache-2.0, last release Jul 2024) for the layout algorithm, matching the project's bias toward library-backed simple algorithms (`account_graph.py` uses a seeded RNG and pure-Python Fruchterman-Reingold — kept in-tree only because no maintained PyPI alternative exists for that niche). `squarify` is preferred over a hand-rolled slice-and-dice because it ships the Bruls/Huijing/van Wijk algorithm in ~60 lines, has zero recursion edge cases at 11 tiles, and produces visibly better aspect ratios than a naive horizontal/vertical split.

### External references

- **Finviz map:** https://finviz.com/map. The visual reference for tile area = metric-magnitude, tile color = movement-direction. Read-only inspiration; no code reuse.
- **Squarified treemaps (Bruls/Huijing/van Wijk, 2000):** the original paper behind Finviz's layout. Deferred to v1.1.
- **Slice-and-dice treemap:** the simpler recursive algorithm that alternates horizontal/vertical splits. Not used in v1 (replaced by the `squarify` library's squarified layout, see Unit 5). Listed here for context only.

## Key Technical Decisions

| # | Decision | Rationale | Rejected alternatives |
|---|----------|-----------|----------------------|
| 1 | **Inline SVG, server-rendered, returned as a string from a new `x_monitor/treemap.py` module** | Matches the `account_graph.py` pattern; no new JS dependency; trivial to test for determinism. | Chart.js matrix plugin (re-introduces the JS framework the plan was written to avoid). d3-hierarchy (rejected dependency). DOM JS canvas (no graceful degradation, htmx re-render complexity). |
| 2 | **`/` becomes the treemap; the existing 9-card grid moves to `/grid` (not retired)** | The treemap is the new showcase. The grid is preserved at a sibling route so DevRel can still fall back to the card view for "I want the per-model stacked-area sparkline" use cases the treemap doesn't surface. | Retire the grid entirely (loses the sparkline + top-3 cards affordance). Query-param toggle (`/?view=grid`) (URL-ugly and easy to bookmark in the wrong state). Single-page app with a sidebar tab switcher (overkill for 2 views). |
| 3 | **Tile area = `release + commenter_capture` in the current N-day window** | Both are attention signals. Suppresses the Q5 (other) noise floor that would otherwise dominate the layout. | Total tweet count (over-weighted by Q5 noise). Like count or retweet count (skews toward celebrity posts, not model attention). |
| 4 | **Tile fill = polarity rate change between two windows, with explicit denominator** | Sparse-data safe: a quiet model is not painted green just because it has no criticism tweets. A model with a sudden shift in praise/criticism rate between the two windows is the only thing that paints red or green. | Raw praise − criticism count change (small models look like big moves). Absence-of-criticism as positive (rejected: too misleading). |
| 5 | **5-step divergent palette interpolated between `--red` and `--green`** | Discrete bins are visually scannable; full continuous gradient is harder to read at a glance. 5 steps is a common Finviz-like granularity. | Binary red/green (loses magnitude). 9-step gradient (more bins than v1 needs). |
| 6 | **Squarified layout via the `squarify` PyPI package (Apache-2.0, ~10 KB)** | Replaces the planned ~30-line hand-rolled slice-and-dice with the Bruls/Huijing/van Wijk algorithm Finviz actually uses; produces visibly better aspect ratios at 11 tiles of varying area; one new PyPI dep that is pure-Python and last released Jul 2024. | Hand-rolled slice-and-dice (~30 lines but ugly thin strips at 11 nodes — see Risks table). d3-hierarchy (rejected: JS dep). echarts (rejected: 360 KB minified or 30 MB Node SSR dep). react-treemap (rejected: React). |
| 7 | **`DashboardConfig.treemap_volume_window_days` and `treemap_change_window_days` config keys, default 7 each** | Window choice has implications for sparse-data behavior. Config-driven so the operator can tune without a code change. | Hardcoded 7 days (operator cannot tune for low-volume models). 14 days (loses the 7d vs prior-7d symmetry). |
| 8 | **Per-model accent on tile border; polarity color on tile fill** | Finviz convention: fill = comparison metric, border = identity. The accent color is already in `MODEL_ACCENT_COLORS` and renders correctly in dark mode via CSS variables. | Accent color on tile fill (looks like a categorical legend, not a heatmap). Polarity on border (loses the visual signal of magnitude). |
| 9 | **"No data" tile is a single faded strip at the top of the treemap with the model name and a placeholder** | 11 distinct models with 0 posts would otherwise render as 11 invisible tiles, breaking the "one-glance triage" goal. The faded strip is honest: it shows the model is being tracked, just has no data yet. | Hide models with 0 posts (silently drops the new models from the treemap on day 1, which is misleading). Render a normal 0-area rect (invisible to the eye). |
| 10 | **11 enabled models from day 1, including 4 new ones (Mistral, StepFun, ERNIE, Hunyuan) with minimal Q1+Q2 query YAMLs** | The user explicitly asked for these models in the treemap. v1 accepts that the new models will paint as "no data" for the first few runs while the pipeline builds up history. | Phased rollout (delays the showcase). Skip the new models (loses the user's product intent). |
| 11 | **`/api/treemap.html` partial returns only the SVG fragment; `/api/treemap.json` returns the structured payload for external consumers** | Mirrors the existing `/api/grid.html` + `/api/grid.json` pair. htmx polls the `.html` partial; a future CLI or external dashboard can poll the JSON. | Single endpoint returning the full page (no htmx partial advantage). Single endpoint returning only JSON (no HTML, harder to debug in a browser). |
| 12 | **`Q1_TO_SIGNAL` mapping, `_parse_post_created_at`, `_load_latest_run`, and the `posts` schema are unchanged** | v1 derives everything from existing data. No new columns, no new tables, no migration. The "rate change" polarity uses existing Q1–Q6 signal labels. | New `polarity_score` column (migration cost, requires re-scoring all historical posts). New `posts.polarity` denormalized field (same migration cost). |

## Open Questions

### Resolved During Planning

- **"Replacing 'x tweets' for stock price" — should polarity be tweet rate change or something else?** Resolved as rate change (R3). Tweet volume = area, tweet rate change = color.
- **"v1 doesn't need hover, although eventually we will have it"** — Resolved as v1 ships without hover. v1.1+ adds it. Documented in scope boundaries.
- **"Replacing 'x tweets' for stock price" — what is the polarity denominator?** Resolved as the explicit praise/criticism rate formula in R3, with a denominator that prevents the "no criticism = maximally green" failure mode flagged by the repo research.
- **"9 models" vs "7 enabled models" mismatch.** Resolved: the treemap ships with 11 models (existing 7 + 4 new). InclusionAI is not split.

### Deferred to Implementation

- **Exact RGB values for the 5 polarity bins.** Will be derived empirically from `--red` and `--green` in the implementation pass; the plan only specifies "5-step divergent palette interpolated between `--red` and `--green`".
- **Tile label content (model name only? name + volume? name + polarity score?).** The plan specifies tile border = accent, tile fill = polarity; label content is a small UX choice the implementer can make during the layout pass.
- **Whether the "no data" tile is always a single horizontal strip spanning the treemap, or a per-model placeholder at the model's expected position.** The plan says "single faded strip at the top" as a starting point; the implementer can choose a per-model rendering if it looks better.
- **The new model query YAMLs' exact query strings.** The plan requires at least one Q1 and one Q2 per new model, following the existing R6 template; the actual query strings are hand-written during implementation.

## High-Level Technical Design

> *This illustrates the intended approach and is directional guidance for review, not implementation specification. The implementing agent should treat it as context, not code to reproduce.*

The treemap is a function from (model list, per-model volumes, per-model polarity scores) to an inline `<svg>` string. Layout is squarified (Bruls/Huijing/van Wijk) via the `squarify` PyPI package: sort models by area descending, call `squarify.normalize_sizes(...)` then `squarify.squarify(...)` to get a list of `(x, y, dx, dy)` rect tuples, then emit one `<rect>` per tuple.

```
# Pseudo-code, directional only
sizes = [max(tile.area_weight, EPS) for tile in tiles_sorted_by_area_desc]  # EPS avoids 0-area
normed = squarify.normalize_sizes(sizes, width, height)
rects = squarify.squarify(normed, 0, 0, width, height)   # list of (x, y, dx, dy)
for tile, (x, y, dx, dy) in zip(tiles_sorted_by_area_desc, rects):
    emit <a href="/model/{tile.model_id}"><rect x={x} y={y} width={dx} height={dy} .../></a>
```

Empty input (no enabled models) emits a centered `<text>No models enabled</text>`; the route handles the empty case before calling `build_treemap_svg`.

The polarity score is computed per model from the Q1–Q6 signal counts in two windows (current N days, prior N days). Windows are anchored to `latest_run.finished_at`, matching the existing grid. Window edges follow the half-open convention `current_window = [anchor - N, anchor)`, `prior_window = [anchor - 2N, anchor - N)` (using `dt >= lower AND dt < upper`, mirroring `serialize_grid_card`). The polarity score is binned via a 3-stop interpolation: `score < 0 → lerp(red, muted, score+1)`, `score > 0 → lerp(muted, green, score)`, `score == 0 → muted`. The 5 visible bins are: `score ≤ -0.5` (red), `-0.5 < score < 0` (red→muted), `score = 0` (muted), `0 < score < 0.5` (muted→green), `score ≥ 0.5` (green). The muted middle bin (gray, neither red nor green) prevents the "no change = green" failure mode.

The "no data" state is detected per model: if the model has 0 posts in the current window, it is not laid out as a normal tile. Instead, all "no data" models are rendered as a horizontal strip of placeholder boxes at the top of the treemap, each at 15% opacity, with the model name. This preserves the "the model is being tracked" affordance for the 4 new models on day 1.

## Implementation Units

- [ ] **Unit 1: Add new model entries to config + display name map + accent color map**

**Goal:** Make the 4 new models (Mistral, StepFun, ERNIE, Hunyuan) known to the data layer and the rendering layer, with display names and accent colors consistent with the existing 7.

**Order of operations (critical for config validation):**
1. Add 4 model_ids to `KNOWN_MODELS` in `config.py` first (this is the single source of truth).
2. Add to `config.yaml` `enabled_models` (validation will fail if step 1 is not done).
3. Add to `MODEL_DISPLAY_NAMES` and `MODEL_ACCENT_COLORS` in `dashboard.py`.

**Requirements:** R8, R10

**Dependencies:** None

**Files:**
- Modify: `x-monitoring/x_monitor/config.py` (add entries to `KNOWN_MODELS`)
- Modify: `x-monitoring/x_monitor/dashboard.py` (add entries to `MODEL_DISPLAY_NAMES` and `MODEL_ACCENT_COLORS`)
- Modify: `x-monitoring/config.yaml` (add the 4 model_ids to `enabled_models`)

**Approach:**
- Pick accent colors distinct from the existing 7. Suggested: Mistral `#facc15` (yellow), StepFun `#22c55e` (emerald), ERNIE `#0ea5e9` (sky), Hunyuan `#ec4899` (pink). Final values chosen during implementation; the plan only constrains them to be distinct from existing 7 and from each other.
- Display names: "Mistral", "StepFun", "Baidu ERNIE", "Tencent Hunyuan" (matches the Chinese-models brainstorm's R5 transliteration pattern).
- The treemap layout must work with the 11-model set immediately; no sharding or "show only models with posts" logic in this unit.

**Patterns to follow:**
- Existing 7 entries in `MODEL_DISPLAY_NAMES` and `MODEL_ACCENT_COLORS` (`x_monitor/dashboard.py` lines 23-45).
- Existing 7 entries in `KNOWN_MODELS` (`x_monitor/config.py`).

**Test scenarios:**
- `KNOWN_MODELS` contains all 11 model_ids; old 7 are unchanged; new 4 are present.
- `MODEL_DISPLAY_NAMES` has all 11 keys.
- `MODEL_ACCENT_COLORS` has all 11 keys, all values are distinct.
- `config.yaml` parses with the new `enabled_models` list; `Config.enabled_models` returns all 11 in order.

**Verification:**
- `python -c "from x_monitor.config import load_config, KNOWN_MODELS; c = load_config(__import__('pathlib').Path('config.yaml')); assert len(c.enabled_models) == 11; assert all(m in KNOWN_MODELS for m in c.enabled_models)"` succeeds.
- `python -m pytest tests/test_config.py` passes.
- `python -m pytest tests/test_dashboard.py` still passes (no regression on the existing 7).

---

- [ ] **Unit 2: Add minimal query YAMLs for the 4 new models**

**Goal:** Each new model has at least one Q1 (release) and one Q2 (community question) query, so the pipeline can begin collecting posts on the next run.

**Requirements:** R9

**Dependencies:** Unit 1

**Files:**
- Create: `x-monitoring/data/queries/mistral.yaml`
- Create: `x-monitoring/data/queries/stepfun.yaml`
- Create: `x-monitoring/data/queries/ernie.yaml`
- Create: `x-monitoring/data/queries/hunyuan.yaml`

**Approach:**
- Follow the existing R6 query-string format from the 7 current YAMLs: `id`, `description`, `query_string`, `expected_signal`, `priority`, `enabled`, `last_run_at` (null), `last_post_id_seen` (null).
- For Q1 (release): `from:<official_handle>` (e.g. `from:MistralAI`, `from:StepFunAI`, `from:Baidu_ERNIE`, `from:HunyuanAI`). If the official handle is not confirmed at implementation time, fall back to a brand-name query: `("Mistral" OR "Mixtral") (AI OR model OR LLM OR 7B OR 8x7B) -weather -meteorology` (the context disambiguator is required to prevent blowing the daily_ceiling with off-topic recall).
- For Q2 (community question): `("Mistral" OR "Mixtral") (how OR 教程 OR tutorial OR guide) min_faves:2` style, matching the existing 7 YAMLs' convention. No `lang:` filter (all-languages, per the chinese-models brainstorm's R4 — an external plan). Q1 and Q2 use only the `min_faves:` operator (`-filter:replies` and `min_retweets:` are not in `KNOWN_OPERATORS` and must not appear in the new YAMLs).
- Priority: Q1 = p0, Q2 = p1.

**Patterns to follow:**
- `x-monitoring/data/queries/qwen.yaml` and `x-monitoring/data/queries/deepseek.yaml` for the Q1/Q2 query structure.
- The 5 query operators list in the chinese-models brainstorm's R3.

**Test scenarios:**
- Each new YAML is valid YAML and has the required keys.
- Each new YAML has at least one Q1 and one Q2 query.
- The pipeline loads all 11 query files without error.

**Verification:**
- `python -c "from x_monitor.queries import load_queries; from pathlib import Path; root = Path('data/queries'); qs = {m: load_queries(m, root) for m in ['mistral','stepfun','ernie','hunyuan']}; assert all(any(q['expected_signal'] == 'release' for q in qs[m]) for m in qs); assert all(any(q['expected_signal'] == 'community_question' for q in qs[m]) for m in qs)"` succeeds. (Note: the actual function is `load_queries(model_id, root)` returning a single model's queries, not a `load_all_queries` aggregator. The verification iterates the 4 model_ids and calls `load_queries` per model.)

---

- [ ] **Unit 3: Implement `x_monitor/treemap.py` (layout + polarity + SVG assembly)**

**Goal:** A pure Python module that takes a list of model payloads and returns an inline `<svg>` string. Layout is squarified (Bruls/Huijing/van Wijk) via the `squarify` PyPI package. Polarity is a 5-step divergent color. "No data" models get a faded placeholder strip.

**Requirements:** R1, R2, R3, R5, R6, R11

**Dependencies:** Units 1, 5

**Files:**
- Create: `x-monitoring/x_monitor/treemap.py`
- Test: `x-monitoring/tests/test_treemap.py`

**Approach:**
- Public function: `build_treemap_svg(tiles: list[TreemapTile], *, width: int, height: int) -> str` where `TreemapTile` is a `NamedTuple` of `(model_id, display_name, accent_color, area_weight, polarity_score)`.
- Helper: `compute_polarity(posts, current_window, prior_window) -> float | None` — implements the R3 formula with explicit denominator and the R3 sparse-data guards. Returns a value in approximately `[-1, +1]`, or `None` for the "went dark" sentinel. Sparse-data behavior: (a) if `current_total == 0 AND prior_total == 0`, return `0.0`; (b) if `prior_total == 0 AND current_total > 0`, define prior rates as `0` (avoid `0/0` NaN propagation); (c) if `current_total == 0 AND prior_total > 0`, return `None` (the "went dark" sentinel).
- Helper: `bin_polarity(score: float | None) -> str` — maps `[-1, +1]` to one of 5 `rgba()` strings interpolated between `--red` (`#ef4444`) and `--green` (`#10b981`) via `--muted` (`#8b949e`). 3-stop interpolation: `score < 0 → lerp(red, muted, score+1)`, `score > 0 → lerp(muted, green, score)`, `score == 0 → muted`. The 5 bins: `score ≤ -0.5` (red), `-0.5 < score < 0` (red→muted), `score = 0` (muted), `0 < score < 0.5` (muted→green), `score ≥ 0.5` (green). `None` (went dark) maps to `--yellow` (visually distinct from the no-data faded strip).
- Helper: `slice_and_dice(items_sorted_by_area_desc, rect) -> list[(model_id, sub_rect)]` — recursive layout, alternating horizontal/vertical splits with proportional area splits. Returns a flat list of `(model_id, bounding_rect)` tuples. `sub_rect` is a `(x, y, w, h)` tuple. Returns a centered `<text>No models enabled</text>` SVG when `items` is empty.
- Helper: `separate_active_and_no_data(tiles) -> (active_tiles, no_data_tiles)` — splits the input. No-data tiles (those with `area_weight == 0` AND no prior posts) get a separate per-model placeholder strip render (per-model placeholders at fixed minimum size, not a single merged strip, to avoid hiding active tiles on day 1 when 4 of 11 models are no-data).
- SVG assembly: emits one `<a href="/model/{model_id}" data-href="/model/{model_id}">` wrapping a `<rect>` for each active tile, with the model's accent color on the rect's `stroke`, the polarity color on `fill`, and the model name in a `<text>` label inside the rect. The no-data strip is a separate `<g>` element with reduced opacity.
- Determinism: no `random.seed` calls. Sort order is stable. Output for a given input is byte-identical.

**Patterns to follow:**
- `x_monitor/account_graph.py` — pure function returning a string, no globals, no side effects.
- The CSS color tokens in `x_monitor/static/dashboard.css` lines 4-14.

**Test scenarios:**
- `build_treemap_svg` with 3 tiles of equal area produces 3 rects whose areas sum to `width * height` within 1px.
- `build_treemap_svg` with 3 tiles of area ratio 1:2:4 produces rects with areas in approximately the same ratio.
- `build_treemap_svg` with empty tiles returns an SVG with a centered "No models enabled" text element.
- `build_treemap_svg` is deterministic — calling twice with the same input produces byte-identical output (smoke test; the primary stability check is rank stability, not byte equality).
- `build_treemap_svg` rank-stability: perturbing a single model's area by 5% keeps that model within 1 rank of its prior position.
- `compute_polarity` with all-zero input returns `0.0` (muted bin).
- `compute_polarity` with `current=1, prior=0` returns `0.0` (no NaN propagation).
- `compute_polarity` with `current=0, prior=5` returns `None` (the "went dark" sentinel).
- `compute_polarity` with `current=1000, prior=5` does not amplify noise (`abs(score) < 0.2` — small prior window does not produce 0.2+ swing from 1-tweet noise).
- `compute_polarity` on a synthetic 3-model fixture (e.g., fixtures/synthetic_polarity.json with model_a praise-heavy, model_b criticism-heavy, model_c balanced) returns the expected polarity_score for each model, matching the R3 formula.
- `compute_polarity` with a sudden increase in praise rate returns a positive score.
- `compute_polarity` with a sudden increase in criticism rate returns a negative score.
- `bin_polarity(0.0)` returns the muted color string.
- `bin_polarity(1.0)` returns the `--green` end of the palette.
- `bin_polarity(-1.0)` returns the `--red` end of the palette.
- `bin_polarity(None)` returns the `--yellow` (went-dark) color string.
- `separate_active_and_no_data` correctly splits tiles with `area_weight == 0` from tiles with `area_weight > 0`.
- `build_treemap_svg` with 4 no-data tiles and 7 active tiles produces 4 no-data placeholder elements and 7 active `<rect>` elements with no overlap (the day-1 deployment state).
- The output SVG contains `data-href="/model/{model_id}"` for every active tile.
- The output SVG contains the model's `display_name` in a `<text>` label.
- The output SVG contains a `<title>` child inside each `<a>` with the model's name, polarity, and area weight (for tooltips and screen readers).
- The output SVG contains `aria-label` on each `<a>` element with the model's polarity and area weight (for screen readers).
- The output SVG contains `role="img"` and `aria-label` on the root `<svg>`.
- The output SVG tiebreaks two equal-area tiles by `display_name` ascending (alphabetical).

**Verification:**
- `python -m pytest tests/test_treemap.py` passes with 100% coverage of the `treemap.py` module.
- A manual `build_treemap_svg` call with 3 synthetic tiles produces an SVG that renders correctly in a browser at 1200×800.

---

- [ ] **Unit 4: Add config key for the treemap volume window**

**Goal:** Make the volume window (for both tile area and polarity's prior-window lookback) config-driven, not hardcoded.

**Requirements:** R2, R3

**Dependencies:** None (soft dependency: Unit 3 must be parameterized on `volume_window` so Unit 6 can wire the config into the route handler)

**Files:**
- Modify: `x-monitoring/x_monitor/config.py` (add field to `DashboardConfig`)
- Modify: `x-monitoring/config.yaml` (add the new key under `dashboard`)

**Approach:**
- Add `treemap_volume_window_days: int = 7` to `DashboardConfig`. (R3 uses the same window length for current and prior, so no separate `treemap_change_window_days` is needed in v1.)
- Add the corresponding key to `config.yaml` under `dashboard:` so the operator sees it.
- Validation: the value must be a positive integer; the value must be ≤ `window_days` (14 by default), or the pipeline data is insufficient to compute the prior window. Raise a clear `ValueError` at config load time if violated. Note: if `window_days < treemap_volume_window_days`, the prior window is empty and polarity will be 0.0 for all models; operationally, keep `window_days ≥ 14` when `treemap_volume_window_days = 7`.

**Patterns to follow:**
- Existing `DashboardConfig` class fields and validation in `x_monitor/config.py`.

**Test scenarios:**
- Default value is 7.
- Loading `config.yaml` with the new key returns the configured value.
- A config with `treemap_volume_window_days > window_days` raises a `ValueError` with a clear message.

**Verification:**
- `python -m pytest tests/test_config.py` passes.
- The dashboard starts and renders the treemap with the new config keys.

---

- [ ] **Unit 5: Add `squarify` (PyPI, Apache-2.0) as the layout algorithm dependency**

**Goal:** Pin the layout algorithm to a real, maintained, license-clean library instead of hand-rolling a slice-and-dice routine. The dependency is added to `pyproject.toml`, declared in any `requirements*.txt` if present, and the venv on fuchitalee is reinstalled so Unit 6 (route) and Unit 7 (treemap module) can import it.

**Requirements:** R1, R11

**Dependencies:** None (Unit 6 — the new treemap module — imports it; this unit just makes the import possible)

**Files:**
- Modify: `x-monitoring/pyproject.toml` (add `squarify` to the `dependencies` list, pinned to `>=0.4,<1.0` to match the Jul 2024 release line)
- Modify: `x-monitoring/requirements.txt` (if present — project today uses `pyproject.toml` only, but Unit 5 verifies and updates any `requirements*.txt` for completeness)

**Approach:**
- `squarify` is on PyPI as `squarify` (import name `squarify`), Apache-2.0 licensed, last release 0.4.1 (Jul 2024). Pure Python, no compiled extensions, ~10 KB installed.
- Pin: `squarify>=0.4,<1.0` in `pyproject.toml`. The 0.4.x API is stable; the 1.x line is not yet released.
- On fuchitalee, after the `pyproject.toml` change, run `cd /Users/fuchitalee/development/minimax-marketing/x-monitoring && .venv/bin/pip install -e .` to install the dep into the dashboard's venv. Restart the dashboard PID so the new dep is loaded.
- The repo research found no existing treemap / squarify / d3 imports in `x-monitoring/x_monitor/**` — this is the only new dep added by this plan beyond the `pyproject.toml` baseline.
- Document the dep in `x-monitoring/README.md` under a new "Treemap dependencies" subsection: 1 PyPI dep, Apache-2.0, ~10 KB, no system packages required.

**Patterns to follow:**
- Existing dep entries in `x-monitoring/pyproject.toml` (look for the `dependencies` list near the bottom of the file).
- The venv install pattern from `x-monitoring/deploy/README.md` if one is documented.

**Test scenarios:**
- `python -c "import squarify; print(squarify.__version__)"` succeeds in `x-monitoring/.venv/bin/python` and prints `0.4.x`.
- `pip show squarify` shows the dep installed from the PyPI cache (no manual wheel download).
- `pyproject.toml` parses without error after the edit (`python -c "import tomllib; tomllib.load(open('pyproject.toml','rb'))"`).
- A 30-second smoke test: `python -c "import squarify; print(squarify.squarify([1,1,1,1], 0, 0, 100, 100))"` returns a list of 4 `(x, y, dx, dy)` tuples whose total area equals `100 * 100` within 1px.

**Verification:**
- `python -c "import squarify; assert squarify.squarify([3, 1, 1, 1], 0, 0, 100, 100)"` returns 4 cells.
- `.venv/bin/python -c "import squarify; print(squarify.__version__)"` reports a `0.4.x` version.
- The dashboard restarts and `/api/treemap.html` (added in Unit 6) responds 200.

---

- [ ] **Unit 6: Add treemap route + htmx partial + JSON endpoint; replace `/` grid route**

**Goal:** Wire `x_monitor/treemap.py` into the dashboard. `/` renders the treemap. `/grid` renders the existing 9-card grid (moved from `/`). `/api/treemap.html` and `/api/treemap.json` are new. `/api/grid.html` and `/api/grid.json` keep their existing paths (htmx polling on `/grid` continues to hit them). The grid code (`serialize_grid_card`, `grid.html.j2`, the grid CSS) is unchanged.

**Requirements:** R1, R11, R12

**Dependencies:** Units 1, 3, 4, 5

**Files:**
- Modify: `x-monitoring/x_monitor/dashboard.py` (add 3 routes, remove 3 routes)
- Create: `x-monitoring/x_monitor/templates/treemap.html.j2` (full page)
- Create: `x-monitoring/x_monitor/templates/_treemap_svg.html.j2` (htmx partial)
- Modify: `x-monitoring/x_monitor/static/dashboard.css` (add `.treemap`, `.treemap rect`, `.treemap .no-data`, `.treemap text` rules)
- Test: `x-monitoring/tests/test_dashboard.py` (update existing tests; add new ones)

**Approach:**
- In `DashboardApp._register_routes()`:
  - **Move** the existing grid-rendering handler from `@app.route("/")` to `@app.route("/grid")`. The handler body and template (`grid.html.j2`) are unchanged. `/api/grid.html` and `/api/grid.json` keep their existing paths — htmx polling on the new `/grid` continues to work without changes to the fragment endpoint.
  - Add `@app.route("/")` for the new treemap page. Reads `latest_run` via `_load_latest_run` (with a wall-clock fallback at the route layer, mirroring `serialize_grid_card`'s `now = datetime.now(timezone.utc)` default — `_load_latest_run` itself does not fall back to wall-clock), builds a list of `TreemapTile` per enabled model. **Wrap the per-model data fetch + polarity compute in try/except; on exception, log a warning and render that model as a no-data tile with a tooltip showing the error reason.** The try/except is enforced (not "should") so that a single model's locked-read exception does not abort the whole 11-tile render. Sorts the tile list by `(-area_weight, display_name)` (R13) and calls `build_treemap_svg`, then renders `treemap.html.j2`.
  - Add `@app.route("/api/treemap.html")` that returns only the `_treemap_svg.html.j2` partial, with the same `<main id="treemap" hx-get="/api/treemap.html" hx-trigger="every {{ poll_seconds }}s" hx-swap="innerHTML">` outer wrapper. The partial must NOT include a `<main>` tag (otherwise the inner `<main>` would be orphaned and the outer hx-trigger would not advance on subsequent polls).
  - Add `@app.route("/api/treemap.json")` that returns the structured tile payload (model_id, area_weight, polarity_score, accent_color) as JSON, for external consumers. The handler sorts by `(-area_weight, display_name)` per R13.
- Template `treemap.html.j2`:
  - Inherits the existing topbar (`<header class="topbar">` with `<span id="last-run-stamp">`) and adds a 2-tab nav strip below the topbar (or beside it, on the right) that renders as:
    ```html
    <nav class="view-tabs" aria-label="View switcher">
      <a href="/" class="view-tab is-active" aria-current="page">Treemap</a>
      <a href="/grid" class="view-tab">9-Card Grid</a>
    </nav>
    ```
    The active tab (`is-active` class + `aria-current="page"`) is set server-side based on `request.path`. The strip lives **outside** the `<main id="treemap">` htmx target so it persists across re-renders.
  - Renders `{{ treemap_svg | safe }}` inside a `<main id="treemap" hx-get="/api/treemap.html" hx-trigger="every {{ poll_seconds }}s" hx-swap="innerHTML">` wrapper.
  - Adds a small legend in the top-right of the treemap container: a 5-cell swatch row labeled `−−, −, ·, +, ++` with a caption "Color = praise/criticism rate change vs prior week. Area = attention (release + commenter_capture)." (Under 100px tall, 300px wide.)
  - Loads htmx from CDN (same as `grid.html.j2`).
  - Does NOT load Chart.js or trend-chart.js (not needed for a static SVG).
- Template `grid.html.j2` (existing, **unchanged** in shape): adds the same `.view-tabs` nav strip, but with the `is-active` class on the `<a href="/grid">` tab and `aria-current="page"` on it. The strip lives **outside** the `<main id="grid">` htmx target.
- Template `_treemap_svg.html.j2`: contains only the `<svg>` fragment returned by `build_treemap_svg`. No outer wrapper, no `<main>` tag.
- CSS additions (all wrapped in `@media (prefers-reduced-motion: no-preference) { ... }` to respect the macOS/iOS Reduce Motion setting and WCAG 2.3.3):
  - `.view-tabs { display: flex; gap: 0; border-bottom: 1px solid var(--border); }` for the tab strip layout.
  - `.view-tab { padding: 8px 16px; color: var(--fg-muted); text-decoration: none; border-bottom: 2px solid transparent; }` for inactive tabs.
  - `.view-tab.is-active { color: var(--fg); border-bottom-color: var(--accent); font-weight: 600; }` for the active tab.
  - `.view-tab:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }` for keyboard focus.
  - `.treemap { width: 100%; max-width: 1400px; margin: 0 auto; }` for the SVG container.
  - `.treemap rect { transition: stroke-width 0.15s ease; }` (no fill transition — fill is server-rendered and innerHTML swap destroys element identity; stroke-width is used for the hover/focus affordance).
  - `.treemap a:focus rect { stroke-width: 3; stroke: var(--fg); }` and `.treemap a:focus-visible rect { outline: 2px solid var(--accent); outline-offset: 2px; }` for keyboard navigation.
  - `.treemap a:hover rect { stroke-width: 3; }` for the drill-down affordance.
  - `.treemap .no-data { opacity: 0.3; }` for the no-data strip.
  - `.treemap text { font-size: 14px; fill: var(--fg); pointer-events: none; }` for the model name labels.
- Add a startup validation in `DashboardApp.__init__` (or in `load_config`) that asserts every entry in `enabled_models` has a `display_name` and an `accent_color` in the corresponding maps. Raise a clear `ValueError` at startup with the missing model_id.
- Tests: update the existing `/` grid tests to assert the new treemap response. Add a 200-response test, a "no data" tile test, and a JSON endpoint shape test. Tests assert: htmx script is present exactly once, chart.js and trend-chart.js scripts are NOT present, dashboard.js IS present (for staleness timer), and each `<a>` tile has a non-empty `aria-label` or `<title>`.

**Patterns to follow:**
- Existing route pattern in `DashboardApp._register_routes()` (`x_monitor/dashboard.py` lines 260-348).
- Existing htmx polling pattern in `x_monitor/templates/grid.html.j2`.
- Existing topbar in `x_monitor/templates/grid.html.j2` (reuse unchanged).

**Test scenarios:**
- `GET /` returns 200, response body contains `<svg`, response body contains `class="treemap"`.
- `GET /` for a model with 0 posts renders the no-data strip.
- `GET /` for 4 no-data + 7 active models (the day-1 state) renders 4 no-data placeholders and 7 active tiles with no overlap.
- `GET /` for an empty `enabled_models` list renders the "No models enabled" message.
- `GET /grid` returns 200, response body contains the existing 9-card grid markup (the grid is not retired, only relocated from `/`).
- `GET /grid` and `GET /api/grid.html` both return 200; the htmx polling pattern in `grid.html.j2` continues to work without modification.
- `GET /api/treemap.html` returns 200, response body contains only the SVG fragment, no `<main>` wrapper, no `<main>` tag.
- `GET /api/treemap.json` returns 200, response body is a JSON object with `tiles` and `fetched_at` keys.
- `GET /api/treemap.json` for 3 enabled models returns 3 entries in the `tiles` array.
- The treemap response is deterministic for a fixed set of posts (two consecutive calls return byte-identical output).
- The topbar's `<span id="last-run-stamp">` is present in the `/` response.
- The topbar contains a `<nav class="view-tabs">` with two `<a class="view-tab">` children; the active tab carries `aria-current="page"` and the `is-active` class.
- `GET /` has the `is-active` class on the `Treemap` tab; `GET /grid` has the `is-active` class on the `9-Card Grid` tab.
- The nav strip is NOT inside the `<main id="treemap">` or `<main id="grid">` htmx target (verified by checking that the strip element appears in both the full page and the htmx fragment responses in the same form — only the full page contains the strip; the fragment contains only the inner content).
- Each `.view-tab` is keyboard-focusable and has a visible `:focus-visible` outline.
- The htmx script tag is referenced exactly once; chart.js and trend-chart.js are NOT loaded.
- The drill-down route `/model/<model_id>` is unchanged, and a "← Back to treemap" link is present in the drill-down topbar. (The tab strip is **not** rendered on drill-down pages — drill-down is a detail view, not a top-level view, so the back-link affordance is the right one. The tab strip lives only on `/` and `/grid`.)
- A `Config` validation error is raised at startup if any `enabled_models` entry lacks a `display_name` or `accent_color`.
- The existing `x-monitoring/tests/test_dashboard.py` grid-route tests are updated to point at `/grid` (the route was renamed, the assertions are otherwise unchanged).

**Verification:**
- `python -m pytest tests/test_dashboard.py tests/test_treemap.py` passes.
- A manual `GET /` from a populated store renders an SVG with one tile per enabled model.
- A manual `GET /` from a store with 0 posts for a model renders a no-data placeholder.
- The existing drill-down page at `/model/<model_id>` still works.

---

## Acceptance Criteria

> The following end-to-end checks must pass before declaring v1 done. Originally Unit 7 in earlier drafts; demoted to a verification section because the steps are operational checks, not implementation units.

- [ ] **Unit 7: Acceptance verification (operational)**

**Goal:** Restart the running dashboard so the new treemap is served on port 5000. Verify all 11 models render (7 with data, 4 with the no-data placeholder). Verify the rate-change polarity paints sensibly for the 7 with data.

**Approach:**
- Restart the dashboard PID (the running process holds the old routes in memory).
- `curl http://$(tailscale ip -4):5000/` and inspect the response. (Tailscale IPs can change on re-auth; use the current IP via `tailscale ip -4` or the documented Tailscale MagicDNS name, e.g. `http://fuchitalee:5000/`.)
- `curl http://$(tailscale ip -4):5000/api/treemap.json` and inspect the JSON payload.
- For each of the 11 models, confirm a tile is present in the SVG output.
- For the 4 new models (Mistral, StepFun, ERNIE, Hunyuan), confirm the no-data placeholder renders.
- For the 7 existing models, confirm the polarity color is one of the 5 expected bins (no out-of-range values).
- Run the pipeline once to seed posts for the new models: `x-monitor run` (or wait for the next 15-min cron).
- Re-verify the treemap after the first successful run for the new models.

**Patterns to follow:**
- The dashboard restart pattern from `data/dashboard.pid` (kill the old PID, spawn a new one with the same command line).
- The pipeline run pattern from `deploy/com.fuchitalee.x-monitor.scheduled.plist`.

**Test scenarios:**
- (These are end-to-end verifications, not unit tests.)
- `GET /` returns 200 with a 1500+ character SVG body.
- The SVG body contains 11 `<a>` elements (one per enabled model).
- The 4 new models' `<a>` elements have `data-href` pointing to `/model/{mistral,stepfun,ernie,hunyuan}`.
- `GET /api/treemap.json` returns 11 entries.
- The 4 new models' JSON entries have `area_weight: 0` and `polarity_score: 0.0` on day 1.

**Verification:**
- The treemap renders in a browser at the Tailscale URL and is visually correct.
- Clicking a tile navigates to `/model/<model_id>`.
- After the first pipeline run that collects posts for the 4 new models, the treemap re-renders with non-zero area weights and polarity scores for those models.

## System-Wide Impact

- **Interaction graph:** The existing htmx polling mechanism (`hx-trigger="every {{ poll_seconds }}s"`) drives the treemap re-render. The 30s cadence is unchanged. The `dashboard.js` IIFE that updates the `#last-run-stamp.stale` indicator runs unchanged because the treemap topbar reuses the same DOM element.
- **Error propagation:** Errors in `Store.get_all_posts(model_id)` for a single model MUST NOT abort the whole treemap render. The route handler wraps each per-model data fetch + polarity compute in try/except, logs a warning, and continues with the other models. A model that fails to load renders as a no-data tile with the error reason (enforced in Unit 6, not "should").
- **State lifecycle risks:** The `latest_run.finished_at` anchor is the source of truth for window edges. If the anchor is more than 1 hour old, the existing client-side staleness timer paints the topbar amber. The treemap inherits this behavior. No new stale state is introduced.
- **API surface parity:** One route is moved (the grid handler relocates from `/` to `/grid`; `/api/grid.html` and `/api/grid.json` keep their existing paths so htmx polling on `/grid` continues to work). Two routes are added (`/api/treemap.html`, `/api/treemap.json`). The new `/` endpoint is not back-compatible with the old `/` (which used to return the grid); the new `/api/treemap.json` payload shape is `{ "tiles": [...], "fetched_at", "window": { ... } }` per R13. No 410 alias is needed because the grid endpoint still exists at `/api/grid.json` and the grid page still exists at `/grid`. **Existing `x-monitoring/tests/test_dashboard.py` grid tests must be updated to point at `/grid`** (the route was renamed, the assertions are otherwise unchanged). The existing `serialize_grid_card` helper is unchanged and is still called by the grid route and the grid tests.
- **Integration coverage:** The treemap is a new "view" of the data; the existing 9-card grid is preserved as a sibling view at `/grid`. The per-model drill-down remains untouched. A click on a treemap tile must land on the same `/model/<model_id>` page that the grid card click lands on. This is verified by the drill-down test scenario in Unit 6, plus a new test that the grid route is still 200 after the move.
- **Unchanged invariants:** The `posts` schema is unchanged. The Q1–Q6 signal labels are unchanged. `Store.get_all_posts` is unchanged. `serialize_grid_card` is unchanged (still used by tests; the new treemap helper runs alongside it). The LaunchAgent schedule is unchanged. The pipeline's daily_ceiling is unchanged.

## Risks & Dependencies

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| 4 new models exhaust the `daily_ceiling: 333` budget on day 1 | Medium | Pipeline degrades to skip-order behavior; some queries get 0 results | v1 ships with the existing ceiling; the 4 new models each have only Q1 + Q2 queries, so the per-model cost is bounded; observe the first 7 days of pipeline behavior; raise the ceiling in a follow-up plan if needed. **Budget math (worst case):** 11 models × 2 queries/model = 22 queries/run; at 50 results/query (the Apify page cap), worst case is 1100 tweets/run, exceeding the 333 ceiling by ~3.3×. The ceiling is enforced per-run, so the pipeline will hit `degraded:budget` and apply `degraded_skip_order` (Q6 → Q5 → Q3 → Q2 → Q4 → Q1). In practice this means Q2 queries for the 4 new models are the first to be skipped. This is acceptable for v1 (the treemap only requires Q1 + Q2 to be present in the YAML, not that they succeed every run). The follow-up plan should re-tune the ceiling based on observed per-run tweet volume after 7 days. |
| Polarity formula misreads a model with mostly Q4 (commenter_capture) as low-polarity | Low | Treemap under-represents models with strong engagement but no praise/criticism | The tile area (R2) uses `Q1 + Q4`, so a high-engagement model is still visible via area; polarity is the second dimension. The plan does not conflate the two. |
| `squarify` (PyPI) goes unmaintained or ships a breaking change in the 0.4.x line | Low | Layout fails to render; dashboard returns 500 on `/` | Pinned to `>=0.4,<1.0` in `pyproject.toml`. A breaking change in 0.4.x would require an explicit unit test failure before this unit ships. If `squarify` is deprecated entirely, the unit-test interface (`squarify.squarify(sizes, x, y, dx, dy) -> list[tuple[float, float, float, float]]`) is a stable-enough contract to vendor the 60-line algorithm into `x_monitor/treemap.py` in a follow-up commit. The Risks table no longer lists "ugly aspect ratios" because Unit 5 made the layout squarified from day 1. |
| `latest_run.finished_at` is null on first deploy | Low | Windows are not well-defined; treemap may render with all-zero windows | `_load_latest_run` already falls back to wall-clock `datetime.now(timezone.utc)`. The fallback is exercised in tests via the empty-store scenarios. |
| 11 tiles don't fit in the standard 1200×800 viewport at 1-2 line labels | Low | Some tiles are too small to display a model name | Tile labels are short (e.g. "MiniMax", "ERNIE"). A 60×40 tile is enough for an 11-14px label. If a model has a very long display name, truncate to 8 characters in the layout helper. |
| Moving the grid from `/` to `/grid` breaks an undocumented external consumer that hits `/` expecting the grid | Low | A user-side bookmark or script fails | The plan flags this in "API surface parity" above. There are no known external consumers in this repo. If a future consumer is discovered, it can be re-pointed to `/grid` (the path the grid was moved to). |
| The 4 new models' query YAMLs use a guessed official handle that returns 0 results | Medium | Day-1 collection is sparse | The plan allows the Q1 query to fall back to a brand-name query (e.g. `("Mistral" OR "Mixtral")`) if the official handle is unconfirmed. The Chinese-models brainstorm R5 covers transliteration variants as a recall supplement. **Acceptance criterion for Unit 2:** before merging Unit 2, a one-shot probe search confirms each new model's Q1 query returns ≥1 result against the live X API (or TwitterAPI.io). If a Q1 returns 0 results, the Q1 is rewritten as a brand-name query before merge. This is a manual gate, not a CI check. |
| Tile aspect ratio makes the polarity color hard to read at small sizes | Low | Color signal is lost for the smallest tile | The 5-step palette has a muted middle bin (gray) and strong red/green end bins, so the contrast is high even at small sizes. No mitigation needed for v1. |

## Documentation / Operational Notes

- Update `x-monitoring/README.md` to reflect the new front page. **The 9-card grid is preserved at `/grid` and should be documented as a sibling view**, not removed. Add a one-paragraph description of the treemap with a reference to the treemap color encoding (area = attention, color = polarity rate change), and a one-line note that the legacy 9-card grid is reachable from the topbar tab strip or directly at `/grid`.
- Update `docs/plans/2026-06-07-001-feat-chinese-models-x-monitoring-plan.md` to note that Unit 7 (Flask dashboard) is amended: the grid HTML is replaced by a treemap, the drill-down is unchanged. Add a one-paragraph amendment note to the front matter of that plan.
- Add a "Treemap Front Page" section to `x-monitoring/deploy/README.md` describing the restart procedure (kill PID in `data/dashboard.pid`, spawn new process).
- No new env vars are introduced. No new secret is required. **One new PyPI dependency is required:** `squarify` (Apache-2.0, ~10 KB) is added in Unit 5 to `x-monitoring/pyproject.toml` and reinstalled into the venv on fuchitalee. No new system packages are required.
- The pipeline continues to use the LaunchAgent schedule; no plist change is needed for the 4 new models because the WatchPaths trigger already re-runs the pipeline when query YAMLs are added.

## Sources & References

- **Repo research:** `/Users/fuchitalee/development/minimax-marketing/x-monitoring/x_monitor/dashboard.py` (routes, `serialize_grid_card`, `_load_latest_run`, `_QID_TO_SIGNAL`); `/Users/fuchitalee/development/minimax-marketing/x-monitoring/x_monitor/store.py` (`get_all_posts`, `_parse_post_created_at`); `/Users/fuchitalee/development/minimax-marketing/x-monitoring/x_monitor/templates/grid.html.j2` (htmx polling pattern); `/Users/fuchitalee/development/minimax-marketing/x-monitoring/x_monitor/account_graph.py` (inline-SVG-from-Python pattern).
- **Existing plan:** `/Users/allenwlee/.claude/projects/-Users-allenwlee/memory/MEMORY.md` x-monitor v1.6 entry; `/Users/allenwlee/development/minimax-marketing/docs/plans/2026-06-07-001-feat-chinese-models-x-monitoring-plan.md` (the plan being amended).
- **External inspiration:** Finviz map at https://finviz.com/map. Read-only reference.
- **Algorithm reference:** Squarified treemaps (Bruls/Huijing/van Wijk, 2000). **Used in v1 via the `squarify` PyPI package** (see Unit 5). No longer deferred.


---

## v1.7.1 Amendment — Area formula changed to cumulative total

**Date:** 2026-06-17
**Branch:** `feat/finviz-treemap-front-page` (post-review, before merge)
**Author:** agent + user direction

### What changed

The treemap **area** formula was changed from
`Q1_count + Q4_count in the current N-day window` to
`total post count per model to-date` (cumulative, no time filter).

The **polarity** formula is unchanged: it remains `Q6_praise_rate(current_window) −
Q6_praise_rate(prior_window)` over the 7-day polarity windows.

### Why

On the live fuchitalee DB (post v1.6 deployment, 2008 posts across 7 models),
the old formula produced an essentially-empty treemap: only Xiaomi MiMo and
DeepSeek had any Q1+Q4 posts in the current 7-day window, and the other 5
in-DB models (Moonshot Kimi, MiniMax, Qwen, GLM, InclusionAI) showed as a
near-invisible 0.15-opacity no-data strip. The 4 brand-new models added in
v1.7 (Mistral, StepFun, ERNIE, Hunyuan) had no posts at all.

The user feedback: "I want to see all 11 models and have area = how much
total conversation each model has to-date."

Cumulative total makes the treemap legible on day 1 (when the new models
still have 0 posts, they remain in the no-data strip — that's correct: no
posts, no area). The polarity color still responds to recent change, so a
model can have a large area (lots of cumulative conversation) and a red
tile (criticism rate rising) at the same time.

### Files changed

- `x-monitoring/x_monitor/dashboard.py` — `_build_treemap_tiles` now
  computes `area_weight = len(posts)` (cumulative) instead of the Q1+Q4
  windowed loop. Docstring updated. Comment in body updated.
- `x-monitoring/tests/test_dashboard.py` — added
  `TestTreemapRoutes::test_treemap_area_is_cumulative_total_not_windowed`
  which seeds 8 in-window + 5 out-of-window posts and asserts the area is
  13 (cumulative), not 4 (old Q1+Q4-windowed count).

### What did NOT change

- Polarity math (`compute_polarity` in `x_monitor/treemap.py`).
- Treemap algorithm (`squarify` + `build_treemap_svg`).
- No-data strip rendering, sparse-data guards, 5-step polarity palette.
- Sort order (`-area_weight, display_name`).
- Routes, htmx partial, JSON shape, 2-tab nav strip.
- Test count (314 + 2 pre-existing failures unchanged).

### Validation

- 8/8 `TestTreemapRoutes` tests pass.
- 314/316 total tests pass (the 2 pre-existing MagicMock failures in
  `test_headlines.py::TestEnrichPostsXArticle` are unrelated to this branch).
- Live-rendered `/api/treemap.json` on fuchitalee worktree shows
  `area_weight` matching per-model post counts (e.g. deepseek=353,
  moonshot_kimi=372, xiaomi_mimo=276, qwen=292, minimax=299, glm=210,
  inclusionai=206; mistral/stepfun/ernie/hunyuan=0 → no-data strip).

### Trade-offs

- `len(posts)` materialises all posts per model per poll. At 11 models ×
  ~200 posts each, this is fine. If the model roster grows past ~50 or the
  per-model post count exceeds ~10k, swap to a `Store.count_posts(model_id)`
  method. Documented in the new docstring.
- Cumulative area is monotonic — a model that stops being discussed still
  has a large tile. If "freshness" matters more than "lifetime volume",
  the next iteration could blend: `area = log(cumulative + 1) × freshness`.
  Deferred to v1.8.

## v1.8 Amendment — Finviz CSS-level fidelity

### What changed

The Finviz-style treemap moves from "behaviorally correct" to "visually
refined." Concretely, six v1.8 deltas, each grounded in Finviz's general
aesthetic direction. v1.8 ships with values-locked sensible defaults
(Arial, 4px padding, 2px gap, 0px radius, 0.5 luminance threshold); the
live visual diff is the tuning step, not a pre-implementation gate.

**Note on the original Finviz-fidelity ask:** the v1.8 plan was first
drafted assuming Finviz's treemap rendered as inspectable inline SVG.
User investigation on 2026-06-17 confirmed Finviz now renders the
treemap inside a `<canvas>` element (`<canvas class="chart initialized"
width="1568" height="872">`) — there are no `<rect>` or `<text>` nodes
in the DOM, and all tile geometry/colors/fonts live in the canvas
pixel buffer. This makes "exact" Finviz CSS extraction impossible without
a pixel-level diff against a screenshot. The v1.8 implementation ships
with sensible defaults instead.

1. **Tile inner padding (~4–6px)** — current tiles render the label
   edge-to-edge against the `<rect>` border. Finviz gives every label
   a small inner margin so it does not collide with the colored border.
   Implementation: shrink each squarified rect by `padding` on every
   edge in `_squarify_layout` (in `x_monitor/treemap.py`), and shift
   the `<text>` x/y by the same `padding`. **Padding value is 4px (sensible default; tune from live visual diff).**

2. **Inter-tile gap (~2px)** — current tiles are stroke-separated only
   (the 2px stroke bleeds into the next tile). Finviz has a visible
   gutter between every tile. Implementation: shrink each squarified
   rect by `gap` on the right and bottom edges, in addition to the
   padding from (1). **Gap value is 2px (sensible default).**

3. **Font-family → Arial / Helvetica** — current tiles use
   `system-ui, -apple-system, sans-serif` (Apple/Segoe UI). Finviz
   renders in a sans-serif web stack that visual inspection matches
   Arial. Implementation: change the `font-family` attribute on both
   `<text>` elements in `_tile_svg` to `Arial, Helvetica, sans-serif`.
   Also update the body font-family in `dashboard.css:25` to match
   (the per-tile `font-family` overrides the body, but the topbar and
   legend should also use Arial for visual consistency). **Font value is `Arial, Helvetica, sans-serif` (sensible default).**

4. **Pct font-weight 400 (was 500)** — current `polarity +X.XX%` line
   is medium-weight. Finviz renders the pct line in regular weight
   while the symbol line stays bold. Implementation: change the
   second `<text>` element's `font-weight="500"` to
   `font-weight="400"`.

5. **Luminance-based text color (was always white)** — current tiles
   render both text lines in `#ffffff`. Finviz renders black text on
   light tiles (DEEP_GREEN, GREEN) and white text on dark tiles
   (DEEP_RED, RED, DARK_RED, DARK_GREEN). Implementation: compute
   relative luminance of the polarity fill (call a new
   `_luminance(rgb_tuple)` helper using ITU-R BT.709:
   `0.2126*R + 0.7152*G + 0.0722*B`, normalized to `[0, 1]`), threshold
   at `0.5`, and pick `#0d1117` (dark) or `#ffffff` (light). Apply to
   both `<text>` elements. **Threshold value is 0.5 (sensible default; ITU-R BT.709 standard midpoint).**

6. **Extended `<title>` tooltip** — current tiles emit
   `<title>{display_name} — polarity {pct_str}</title>` (line 331 of
   `x_monitor/treemap.py`). v1.8 extends this with the model_id,
   polarity percentage, polarity window days, total post count in
   the polarity window, and last-run timestamp:
   ```
   <title>MiniMax AI (minimax)
   Polarity: +4.92% (vs prior 7d)
   Posts in window: 47
   Last run: 2026-06-17 13:50 UTC
   Sector: closed-source LLM</title>
   ```
   Browser-native SVG tooltip. **No JS**, no new CSS, no new dep —
   respects v1.7 Decision #1 (inline SVG, no JS framework). The
   `<title>` already exists; the change is the string format and
   the data it carries.

   Data sources for the new fields:
   - `model_id`: `tile.model_id` (already in `TreemapTile`)
   - `pct_str`: already computed in `_tile_svg`
   - Window days: pass through from `_build_treemap_tiles` →
     `_tile_svg` (currently `polarity_window_days` is local to the
     builder; needs to be added to the tile dataclass or passed as
     a parameter)
   - Posts in window: precompute in `_build_treemap_tiles` and
     stash on the tile
   - Last-run timestamp: pass `_load_latest_run(self.runs_dir)`
     result into `_build_treemap_tiles` (already loaded at the
     route level — just pass through)
   - Sector: needs a new `MODEL_SECTORS: dict[str, str]` table in
     `x_monitor/treemap.py` (closed-source LLM, Chinese open-source,
     Western open-source, etc.). **v1.8 ships with sensible defaults
     for the 11 enabled models; new models default to `None`.**

7. **(Already specced, never shipped) Stroke-width hover affordance** —
   the v1.7 plan called for (but did not ship) `.treemap rect {
   transition: stroke-width 0.15s ease; }` and `.treemap a:hover rect
   { stroke-width: 3; }`. v1.8 ships this baseline. Two new CSS
   rules in `dashboard.css`, no JS, no SVG change.

### CSS values (locked sensible defaults)

Finviz's treemap is canvas-rendered (no inspectable inline SVG in the
DOM), so exact rgb/px values cannot be extracted via DOM inspection. v1.8
locks in sensible defaults and treats the live visual diff against the
Finviz screenshot as the tuning step. Constants live at the top of
`x_monitor/treemap.py` and can be tuned in a follow-up commit without
schema or test changes.

| Property | v1.8 value | Rationale |
|----------|------------|-----------|
| Tile inner padding | `4 px` | Finviz screenshots show ~4–6px margin; 4px is a safe default |
| Inter-tile gap | `2 px` | Visible gutter; 1px reads as noise at the live dashboard density |
| Tile font-family | `Arial, Helvetica, sans-serif` | Universal web-safe stack; matches Finviz visual weight |
| Tile border radius | `0` (sharp) | Finviz tiles are square; current `rx=2` is rounded leftover from v1.7 |
| Tile stroke width | `2` (unchanged) | Existing divider stroke; survives the new gap |
| Text-color luminance threshold | `0.5` | ITU-R BT.709 midpoint; standard convention |
| Pct font weight | `400` | Was 500; Finviz pct line is regular weight |
| Symbol font weight | `700` | Unchanged; bold name on every tile |
| Body font-family (dashboard.css) | `Arial, Helvetica, sans-serif` | Match tile font for topbar/legend visual consistency |
| Topbar/treemap-wrap padding | `0.5rem` | Modest bump from current `1rem` text-padding |
| Sector taxonomy | 11-model default dict | `MODEL_SECTORS` table filled in; new models default to `None` |

### Why

Three converging signals:

- **User request (2026-06-17):** "use exact styling from finviz.com/map,
  css, etc for our treemap." CSS-level fidelity is the explicit ask.
- **Finviz reference trajectory:** the v1.7 plan already pointed at
  Finviz as the visual reference (Decision table, line 88) and
  committed to "no JS framework, inline SVG, server-rendered." v1.8
  advances the Finviz-fidelity dimension without breaking the
  no-JS-framework commitment by extending the existing native `<title>`
  element instead of building a custom popup.
- **Pull-forward from deferred v1.1+ list:** the v1.7 plan explicitly
  deferred hover detail panels (line 60). v1.8 pulls forward a
  lightweight version of that (native `<title>` extension + CSS
  stroke-width hover) while leaving the JS-driven custom popup for
  v1.9 if ever needed.

### Files changed

- Modify: `x-monitoring/x_monitor/treemap.py`
  - `_squarify_layout`: shrink each rect by padding (top-left) and
    gap (bottom-right) before returning the rect tuple
  - `_tile_svg`: use new padding/gap constants; compute luminance
    for text color; lower pct font-weight to 400; expand `<title>`
    string with the 5 new fields
  - Add module-level constants `_TILE_PADDING_PX`, `_TILE_GAP_PX`,
    `_FONT_FAMILY`, `_LUMINANCE_THRESHOLD`, `_luminance(rgb)`
    helper, `MODEL_SECTORS: dict[str, str]` table
  - Add fields to `TreemapTile` dataclass: `posts_in_window: int`,
    `polarity_window_days: int` (so `<title>` can read them)
  - Update `_build_treemap_tiles` to populate the new fields from
    the existing per-model data (posts in window requires a small
    filter or `len()` over the already-fetched post list)

- Modify: `x-monitoring/x_monitor/dashboard.py`
  - Pass `_load_latest_run(...)` result into `_build_treemap_tiles`
    so the tile dataclass can carry the last-run timestamp
  - No new routes

- Modify: `x-monitoring/x_monitor/templates/treemap.html.j2`
  - Add `<script src="/static/dashboard.js" defer></script>` if not
    already there (verify; current template loads no JS)
  - No template structural change (the `<title>` extension is
    inside the SVG which is shared between `/` and
    `/api/treemap.html`)

- Modify: `x-monitoring/x_monitor/static/dashboard.css`
  - Update body `font-family` to match `_FONT_FAMILY`
  - Add new `:root` CSS vars: `--finviz-tile-padding`,
    `--finviz-tile-gap`, `--finviz-font-family`
  - Add `.treemap rect { transition: stroke-width 0.15s ease; }`
  - Add `.treemap a:hover rect { stroke-width: 3; }`
  - Add `.treemap-wrap { padding: 0.5rem; }`

- Modify: `x-monitoring/tests/test_treemap.py`
  - Add new test class `TestTileHoverAndTooltip` with scenarios:
    - Tile rect is shrunk by padding on top-left
    - Tile rect is shrunk by gap on bottom-right
    - Adjacent tiles have visible gap (rect.right of A < rect.left of B)
    - Luminance < threshold → text color is `#0d1117`
    - Luminance >= threshold → text color is `#ffffff`
    - `<title>` contains model_id, polarity %, window days, post count, last-run timestamp
    - `pct_str` second-line font-weight is 400 (was 500)
    - `MODEL_SECTORS` table is populated for all enabled models
  - Add new test class `TestSquarifyLayoutPadding`:
    - One-tile layout: rect is shrunk by padding on each edge
    - Two-tile layout: gap between tiles is exactly `_TILE_GAP_PX`
    - Total area after padding matches total area before padding
      (within rounding) — confirms padding is "shrink, don't translate"

- Create: `docs/screenshots/treemap-home.png` (replace)
  - Manually re-capture after the CSS values are locked in
  - Commit the new PNG (no automated capture script exists; see
    "Operational notes" below)

### What did NOT change

- **Routes** (`/`, `/api/treemap.html`, `/api/treemap.json`,
  `/api/polarity_window/<int:days>`).
- **htmx partial contract** (`/api/treemap.html` returns SVG-only;
  `<main>` wrapper persists across polls so `hx-trigger` stays
  attached).
- **Polarity math** (`compute_polarity`, `polarity_fill`, the
  5-step Finviz palette rgb values, the relative normalization).
- **No-data strip rendering** (still at the top, 50/90px height,
  15% opacity).
- **Sort order** (`-area_weight, display_name`).
- **2-tab topbar nav strip** (Treemap | 9-Card Grid, `.view-tab` /
  `.view-tab.is-active` CSS, request.endpoint-driven active state).
- **Polarity window toggle** (v1.7.4's 1d/7d/30d, the
  `_resolve_polarity_window` + `_clamp_polarity_window` helpers,
  the `polarity_window` cookie). v1.8 only consumes the
  `polarity_window_days` value via the new tile field; the toggle
  behavior is untouched.
- **Test baseline**: 338 pass + 2 pre-existing
  `test_headlines.py::TestEnrichPostsXArticle` failures
  (MagicMock JSON serialization bug, not introduced by this
  branch). Net-new tests land in `TestTileHoverAndTooltip` and
  `TestSquarifyLayoutPadding` — total v1.8 deltas: 8–12 new tests.
- **No new JS frameworks, no new CDN deps, no new PyPI deps**.
  Decision #1 (inline SVG, no JS framework) is preserved by using
  the browser-native `<title>` element for the tooltip.

### Validation

- **346–350 tests pass** (338 + 8–12 new), 2 pre-existing failures
  unchanged.
- Live `/` and `/api/treemap.json` on the worktree :5050 dashboard
  return 200, 11 tiles (or `len(enabled_models)` if config changes),
  and the `<title>` element on every tile carries all 6 fields
  (model name + model_id, polarity %, window days, post count,
  last-run timestamp, sector).
- Manual visual diff: open the worktree :5050 dashboard. Tile
  padding, gap, font, text color, and pct weight are visible and
  consistent. If a tile reads as visually wrong, the constants at the
  top of `x_monitor/treemap.py` are the tuning surface.
- Stroke-width hover: hover any tile in the browser, confirm the
  tile border thickens from 2px to 3px within 150ms.
- Native `<title>` hover: hover any tile, wait ~500ms for the
  native browser tooltip, confirm the popup shows the full 6-field
  content (model name, polarity %, window days, post count,
  last-run, sector).

### Trade-offs

- **No JS hover popup.** Finviz shows a custom HTML popup; v1.8
  uses the browser-native `<title>` popup. The trade is preserving
  v1.7 Decision #1 (no JS framework). Native `<title>` popup is
  less visually polished (OS-styled, not Finviz-styled) but
  requires zero new code. If the user later wants the Finviz-
  styled popup, v1.9 can add a small (~40 line) vanilla JS
  handler in `dashboard.js` — explicitly approve the JS
  exception then.
- **User-supplied numeric values.** Finviz is JS-rendered + Cloudflare-
  gated; exact rgb/px values cannot be programmatically extracted.
  v1.8 ships with placeholder values and a visual-diff loop. The
  visual diff IS the lock-in step; the plan does not pre-lock
  numbers because that would risk implementing against values the
  user disagrees with on inspection.
- **Sector taxonomy is a new manual data table.** `MODEL_SECTORS`
  requires per-model categorization. v1.8 ships with the table
  filled for the 11 current models; new models added later will
  fail `_validate_dashboard_config` (which already raises on
  missing `display_name` / `accent_color`) unless we extend it to
  also raise on missing sector. Decision deferred — for v1.8
  just leave sector as `None` if missing, and the `<title>`
  string omits the sector line.
- **Padding + gap shrinks the rect, not translates.** This is the
  simplest implementation (squarify returns rects in
  `[0, width] × [0, height]`, then we shrink each rect by
  `padding + gap`). A more elaborate implementation would
  post-process the layout to re-pack tiles with gap-aware
  dimensions; v1.8 stays simple and accepts that the gap reduces
  total visible area by ~1–2% (visually negligible).
- **CSS-only hover affordance is limited.** Stroke-width thickening
  on hover is the only motion. Finviz uses subtle scale, color
  shift, or shadow. CSS-only `transform: scale(1.02)` on hover
  is doable but may cause SVG re-render jank on rapid hover —
  deferred to v1.9.

### Operational notes

- **No automated screenshot-capture script.** `docs/screenshots/`
  is committed manually. After v1.8 lands, the implementer takes
  a fresh screenshot (browser dev tools → capture node, or
  `Cmd+Shift+4`) and commits it as `docs/screenshots/treemap-home.png`.
  The previous treemap-home.png is from v1.7.0.
- **Worktree hygiene.** v1.8 work happens in the existing
  `worktrees/treemap/` worktree on branch `feat/finviz-treemap-front-page`
  at commit `cfeff50` (the v1.7.4 tip). Do not create a sibling
  worktree. Use `lsof -nP -iTCP:5050 -sTCP:LISTEN -t` to find the
  worktree dashboard PID before any restart; never
  `pkill -f DashboardApp`.
- **Live :5050 dashboard restart is required** for the CSS / SVG
  changes to take effect. Plan: stop worktree dashboard
  (`lsof -nP -iTCP:5050 -sTCP:LISTEN -t | xargs kill`),
  restart via `nohup .venv/bin/python run_dashboard_5050.py > /tmp/wt_v18.log 2>&1 &`,
  verify with `curl -sS http://localhost:5050/api/treemap.json | jq -r '.tiles[0]'`.