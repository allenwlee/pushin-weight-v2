# How polarity is calculated

A detailed walkthrough of the polarity score that drives the
treemap's tile fill color on `/`. This is the single most-asked
question about the dashboard — "what does the +/-X.XX% number
mean, and why is it that color?" — and the answer spans four
modules: `treemap.py::compute_polarity_from_db`,
`dashboard.py::_build_treemap_tiles`,
`treemap.py::polarity_fill`, and the v1.7.4 polarity-window
toggle.

This doc is correct as of v1.8 (the company/brand/account
refactor shipped on 2026-06-19; plan at
`docs/plans/2026-06-18-195234-refactor-company-brand-account-model-plan.md`).
The headline change: polarity no longer reads from `posts.signal`
(which was dropped in migration 004); it reads from
`posts_brands_signals(post_id, brand_id, signal)` joined with
`posts_brands` to apply the fractional weight. The polarity
formula itself does not change — the per-brand totals just
become weighted sums instead of integer counts.

---

## 1. The formula

For one brand `b`, the polarity score is:

```
polarity_b = (praise_rate_now - criticism_rate_now)
           - (praise_rate_prior - criticism_rate_prior)
```

where `praise_rate_X = praise_weighted_X / total_weighted_X`
(and similarly for `criticism_rate_X`). The "total" is the
**sum of `pb.weight`** across all kept posts in the window
that were classified into one of the 6 signal buckets:

| QID | signal name        | meaning                                  |
|-----|--------------------|------------------------------------------|
| Q1  | `release`          | new model release / version announcement |
| Q2  | `community_question` | community Q&A / how-to                  |
| Q3  | `criticism`        | complaints, bug reports, "this is bad"    |
| Q4  | `commenter_capture` | someone asking for / comparing products  |
| Q5  | `other`            | everything not in the other 5            |
| Q6  | `praise`           | "this is great," recommendations         |

The score lives in `[-1.0, +1.0]` and is signed. A positive score
means the brand is trending more positive (praise rate is rising
relative to criticism rate); a negative score means the opposite.

The result is rendered as a signed percentage on the tile:
`+1.16%` or `-3.49%` (multiplied by 100, with 1-2 decimals
depending on tile size — see `treemap.py:_tile_svg`).

---

## 2. Where the signal lives now (the v1.8 schema change)

Before v1.8, every kept post had **one** signal in `posts.signal`
(classified post-fetch in v1.7 by the `classify_signal` step),
and the polarity was computed by GROUP BY on that single column
with `posts.model_id` as the brand filter. The post's
`source_query_id` was used as a fallback for pre-v1.7 posts
where `signal` was NULL.

In v1.8, that schema is gone:

- `posts.signal` was **dropped** in migration 004.
- `posts.model_id` was **dropped** in migration 004 (Decision 9).
- `posts_brands(brand_id, post_id, weight)` is now the **only**
  brand attribution. `weight` is REAL with default `1.0`; for a
  post naming N brands, all N rows get `weight = 1.0 / N`.
- A new `posts_brands_signals(post_id, brand_id, signal)` table
  stores the per-brand signal. The classifier now returns
  `list[(brand_id, signal)]` — a "Qwen praised, DeepSeek
  criticized" post writes two rows, one per brand. (R6d)
- The `_QID_TO_SIGNAL` mapping in `dashboard.py:204` is
  retained for any legacy `source_query_id` reads, but the new
  polarity path no longer touches it.

The upshot: **polarity math is now per-brand via a 3-table JOIN**
(see section 5 below for the SQL), and the totals are **weighted
sums** rather than integer counts.

---

## 3. What "now" and "prior" mean (the two windows)

The dashboard ships with `window_days=14` and
`treemap_volume_window_days=7` as defaults (from
`x_monitor/config.py:48,54`). The polarity uses
`polarity_window_days` (v1.7.4) which the user can toggle between
**1d / 7d / 30d** in the topbar; the value is stored in the
`polarity_window` cookie (set via `/api/polarity_window/<int:days>`,
validated against `ALLOWED_POLARITY_WINDOWS = (1, 7, 30)` in
`dashboard.py:220`).

Given a window `N`:

```
now            = latest_run.finished_at, or wall-clock if no run yet
current_window = [now - N days,        now)
prior_window   = [now - 2*N days,      now - N days)
```

Both windows are **half-open** (`[lower, upper)`). A post
timestamped exactly at the boundary `now - N days` falls into the
prior window, not the current window. This matches the standard
left-closed / right-open convention.

`now` is anchored to the **last run's `finished_at`**, not
wall-clock. The point is to make the polarity windows stable
across dashboard refreshes within the same cycle — without this
anchor, the "now" line creeps forward every 30 s, the windows
shift, and the polarity % jiggles visibly even when no new posts
arrived. The relevant code is in
`x_monitor/dashboard.py:564-571` (the `now = datetime...; if
latest_run and latest_run.get("finished_at"): ...` block).

---

## 4. The fractional-weight invariant (why a 2-brand post counts as 0.5 each)

Per Decision 9, every post that names N brands contributes
`weight = 1/N` to each brand's totals. The conservation
invariant is: **sum of `posts_brands.weight` for any one post
equals 1.0** (modulo IEEE 754 rounding — Decision 17 sets the
drift tolerance at 1e-3).

Why this matters for polarity:

- A 2-brand Qwen-vs-MiniMax praise post contributes `0.5` to
  Qwen's `praise` weighted count and `0.5` to MiniMax's. It
  contributes nothing to either brand's `criticism`.
- A 3-brand "Qwen > DeepSeek > MiniMax" release post
  contributes `~0.333` to each brand's `release` weighted
  count.
- A 1-brand single-attribution post contributes `1.0` to its
  brand's bucket.
- Posts in `posts_brands` with `brand_id = '_unattributed'` get
  `weight = 1.0` but contribute **nothing** to any real
  brand's polarity (see section 5's `_unattributed` filter
  and Decision 15).

The weighted sum is computed by the SQL via `SUM(pb.weight)`.
The `current_rate` and `prior_rate` denominators are the same
weighted sums (not integer counts), so the rate stays in
`[-1, +1]` even when a brand's posts are mostly multi-brand.

---

## 5. The v1.8 polarity SQL (the 3-table JOIN)

This is the production SQL, lifted verbatim from the
`POLARITY_SQL` constant in `treemap.py` (Unit 4 / R17 /
Decision 18 of the plan):

```sql
SELECT pbs.signal, SUM(pb.weight) AS weighted_count
FROM posts_brands_signals pbs
JOIN posts_brands pb
  ON pb.post_id = pbs.post_id AND pb.brand_id = pbs.brand_id
JOIN posts p ON p.tweet_id = pbs.post_id
WHERE pbs.brand_id = ?
  AND pbs.brand_id != '_unattributed'
  AND p.created_at >= ?
GROUP BY pbs.signal
```

The 3-table JOIN path (the diagram):

```
posts_brands_signals           posts_brands                posts
(pbs)                         (pb)                       (p)
+--------------------+        +----------------+         +-----------------+
| post_id    (FK)   |        | post_id  (FK)  |         | tweet_id (PK)   |
| brand_id   (FK)   |--JOIN-->| brand_id (PK)  |         | created_at      |
| signal            |  ON    | weight         |--JOIN-->| ...             |
+--------------------+  same  +----------------+  ON     +-----------------+
                       post_id     (1.0/N per     tweet_id
                       AND         post; default  =
                       brand_id    1.0)           pbs.post_id
```

Per Decision 18, this JOIN shape (vs. an IN-subquery on
`tweet_id IN (SELECT ...)`) lets the query planner use the
`posts_brands_signals(brand_id, signal)` and
`posts_brands(brand_id, post_id)` indexes to seek by brand, then
join `posts(tweet_id)` for the time-window filter. EXPLAIN QUERY
PLAN on a 100k-post fixture should show all three indexes used
(no SCAN or SORT nodes).

The three filters in the WHERE clause each carry meaning:

- `pbs.brand_id = ?` — the brand being scored (e.g. `qwen`,
  `minimax`, `deepseek`). This is the per-brand attribution.
- `pbs.brand_id != '_unattributed'` — Decision 15 hard-filter.
  Even though `posts_brands_signals` has a `CHECK
  (brand_id <> '_unattributed')` constraint that prevents
  inserting sentinel rows at all, the WHERE clause is the
  application-level guarantee. The regression test
  `tests/test_polarity.py::test_unattributed_excluded_from_polarity`
  asserts `SUM(weight)` returns `0` for `_unattributed`.
- `p.created_at >= ?` — the lower-bound time filter for the
  window. `compute_polarity_signal_breakdown` optionally appends
  an `AND p.created_at < ?` upper-bound filter for the prior
  window slice (split on `"GROUP BY"` so `POLARITY_SQL` stays
  the single source of truth).

The two window queries (current and prior) are issued
independently; the prior query additionally uses an upper bound
of `current_start_iso` so the two windows don't overlap.

---

## 6. The sparse-data guards (why some tiles say "no data" and others say "went dark")

`compute_polarity_from_db` calls `_score_from_breakdown` (in
`treemap.py`) which has three branches that handle the case where
one or both windows are empty. These are **the most important
behaviors to understand**, because they determine what the tile
shows when a brand is quiet.

```
if current_total == 0 and prior_total == 0:
    return 0.0      # both windows empty -> muted bin
                    # (the brand has no kept posts classified
                    #  into any signal in either window)
                    # -> renders as the DARK_GREEN bin
                    # -> tile shows "0.00%" with a faint fill

if prior_total == 0 and current_total > 0:
    return current_praise_rate - current_criticism_rate
                    # prior window has no data; treat prior rates
                    # as 0 instead of NaN
                    # -> renders the absolute (not relative) net
                    #    positivity, clamped to [-1, +1]

if current_total == 0 and prior_total > 0:
    return None     # "went dark" sentinel
                    # -> renders as YELLOW (--yellow token)
                    # -> tile shows "no data" instead of a percentage
                    # -> treemap places it in a faded strip at the top
```

In v1.8 the `total` values are **weighted sums** (floats), not
integer counts. The `0 == 0` test still works because
`SUM(weight)` returns 0 when no rows match, but the comparison
is on the float total, not the row count.

There is also a `_unattributed`-specific guard in
`compute_polarity_from_db`: if `brand_id == '_unattributed'`,
the function returns `None` immediately (no SQL run), giving
the no-data tile treatment to the sentinel brand per Decision 15.

The "both empty" case (returns 0.0) is what you see for a brand
with no kept posts at all. It looks like the most-extreme
*positive* bin (DARK_GREEN) but is actually neutral — the
`polarity_fill` function only treats 0.0 as the center of the
distribution, not as a real score.

The "went dark" case (returns None) is what you see when a brand
was active in the prior window but has had zero kept posts in the
current window. The user-facing label is "no data" and the tile
fills with the `--yellow` token. **This is the only state where
a tile gets the yellow fill** — and the only state where the
polarity % display is suppressed.

The "prior empty, current not" case is rare in practice (a new
brand) and is treated as a half-life version of the normal case.

---

## 7. The polarity_fill function (where the score becomes a color)

After the score is computed, `polarity_fill` (in
`treemap.py:161-200`) maps it to one of 6 bins using **relative**
(not absolute) thresholds. The thresholds are normalized against
the most extreme score in the *active* tile set:

```
max_abs_score = max(abs(s) for s in active_scores)
t = score / max_abs_score    # in [-1, +1]

t <= -0.6  -> LIGHT_RED    (255, 100, 100)
-0.6 < t <= -0.2  -> RED         (210,  40,  40)
-0.2 < t <  0     -> DARK_RED    ( 90,  25,  25)
 0  < t <  0.2    -> DARK_GREEN  ( 25,  80,  25)
 0.2 <= t <  0.6  -> GREEN       ( 60, 200,  60)
 t >=  0.6        -> LIGHT_GREEN (120, 255, 120)
```

The "relative" part is the key. On day 1, when absolute scores
might be ±0.05, normalizing by the max gives a `t` of ±1.0 for
the most extreme brand, so the bins still spread across the full
red-to-green range. As data accumulates, the same ±0.05 absolute
score becomes a much smaller `t` and falls into a more muted bin.
This is the Finviz convention and it's why the dashboard stays
readable on day 1.

The v1.8.1 palette names are **deliberate**. The most-extreme
bin is the **brightest** color (LIGHT_RED, LIGHT_GREEN); the
muted bins (DARK_RED, DARK_GREEN) are darker. This is the
opposite of how most palettes name things, and the v1.7 plan
shipped the inverted version as a bug (DEEP_GREEN was darker
than GREEN on the dashboard's dark background). The fix in v1.8.1
was to rename so that "most saturated = most extreme = brightest
= LIGHT_*" matches user intuition. The on-screen luminance
(BT.709) is monotonically ascending across the positive side
(0.252 → 0.628 → 0.849) and the negative side (0.152 → 0.299 →
0.521), so the most-extreme tile always reads as the most-visible
on the dark `#0b0f14` background.

The `_YELLOW` constant is the "went dark" sentinel and is
returned only when `score is None`. It is **not** part of the
6-bin polarity palette.

The text color inside each tile is also computed from the fill:
`_text_color_for_fill` runs BT.709 luminance on the fill rgb and
picks `#0d1117` (dark) for `lum >= 0.5` and `#ffffff` (light)
otherwise. This means LIGHT_RED and LIGHT_GREEN tiles get dark
text (legible on the bright fill); RED, GREEN, DARK_RED, and
DARK_GREEN tiles get white text. The same `_LUMINANCE_THRESHOLD =
0.5` is the standard ITU-R BT.709 midpoint.

---

## 8. Worked example (v1.8 weighted sums)

Imagine Qwen has these kept posts in the last 30 days, with the
polarity window set to 7d:

```
Window: current = [day -7,  day 0)     prior = [day -14, day -7)

Current window posts (4 posts):
  post A: single-brand praise        -> weight 1.0, signal=praise
  post B: single-brand criticism     -> weight 1.0, signal=criticism
  post C: Qwen + MiniMax praise      -> weight 0.5 each, signal=praise
  post D: Qwen-only other            -> weight 1.0, signal=other

  Qwen-side weighted sums:
    praise      = 1.0 + 0.5 = 1.5
    criticism   = 1.0
    other       = 1.0
    release/comm_q/comm_capture      = 0
    current_weighted_total = 3.5

  current_rate = (praise - criticism) / total
               = (1.5 - 1.0) / 3.5 = 0.1429

Prior window posts (2 posts):
  post E: single-brand praise        -> weight 1.0
  post F: Qwen + DeepSeek praise     -> weight 0.5 each

  Qwen-side weighted sums:
    praise      = 1.0 + 0.5 = 1.5
    everything else = 0
    prior_weighted_total = 1.5

  prior_rate = (1.5 - 0) / 1.5 = 1.0

polarity = current_rate - prior_rate = 0.1429 - 1.0 = -0.8571
```

Rendered: `-85.71%` (with 2 decimals since the tile is large
enough; the dashboard code at `treemap.py:406` picks decimals
based on tile width). The fill depends on the relative `t`
against the most extreme active brand; if Qwen is the most
extreme on the dashboard, `t = -1.0` and the fill is
`LIGHT_RED`.

If Qwen had **zero** kept posts in the current window but 2 in
the prior window, `compute_polarity_from_db` returns `None`,
the tile shows "no data," and the fill is yellow. This is the
"went dark" state.

If Qwen had **zero** kept posts in both windows, the score is
0.0. The tile shows `+0.00%` (signed zero). The fill is
`DARK_GREEN` (the `0 < t < 0.2` bin, but since `t = 0.0 / 0.0`,
there's a degenerate case where `max_abs_score == 0` and the
function falls back to `DARK_GREEN` for any non-None score).
This is the "brand is being tracked but has no posts yet"
state.

---

## 9. What the treemap cares about vs. what the grid cares about

The treemap (front page `/`) and the grid (`/grid`) compute
polarity **differently in one specific way**:

- **Treemap** uses `_build_treemap_tiles` which:
  - calls `compute_polarity_from_db(conn, brand_id,
    polarity_window_days)` per brand (Unit 4)
  - computes `area_weight` from the lifetime post count
    (a separate query, also via the JOIN shape)
  - The polarity score is the **tile fill**; the area is the
    lifetime post count.

- **Grid** uses `serialize_grid_card` which:
  - calls `compute_polarity_from_db` for the polarity badge
  - computes per-card counts (Q1..Q6 + total) within the
    `window_days` window (default 14d, NOT the polarity
    `polarity_window_days`)
  - The grid shows a stacked-area sparkline of daily post counts
    over the last 14d, the top-3 most-liked posts, and a
    sentiment badge that is **also derived from
    `compute_polarity_from_db`** but using the grid's
    `window_days` (not the polarity toggle).

So the same `compute_polarity_from_db` function is used by both
pages, but the window they call it with is different:
- Treemap: `polarity_window_days` (toggleable 1/7/30)
- Grid: `window_days` (default 14, not user-toggleable in v1.8)

This is a known v1.8.x follow-up: the grid's polarity badge
should probably also use the toggle. It's deferred to a follow-on
plan.

---

## 10. The cookie and the route

The polarity window is stored in a cookie named `polarity_window`
(the constant `POLARITY_WINDOW_COOKIE` in `dashboard.py:221`).
The route `/api/polarity_window/<int:days>` (registered at
`dashboard.py:747`) is a small redirect endpoint that:

1. Validates `days` is in `ALLOWED_POLARITY_WINDOWS` (1, 7, 30)
2. Sets the cookie with a 1-year max-age
3. Redirects to the `next` query param (or `/` as fallback)

The cookie is read on every page render via
`_resolve_polarity_window(req, default=...)` (line 224), which
falls back to `dashboard.treemap_volume_window_days` (default 7)
if the cookie is missing or invalid.

The window-tab UI in the topbar (`window-toggle` in
`dashboard.css:245-281`) shows the 3 buttons and highlights the
active one based on `selected_window_days`, which is the cookie
value resolved server-side and passed to the template.

---

## 11. Where the function lives in the codebase

```
x_monitor/treemap.py
  +-- POLARITY_SQL: str                            (module constant)
  |     The v1.8 3-table JOIN. Single source of
  |     truth; the EXPLAIN test references it
  |     directly.
  +-- compute_polarity_signal_breakdown(
  |       conn, brand_id, window_start_iso,
  |       *, window_end_iso=None) -> dict
  |     Runs POLARITY_SQL (optionally with an
  |     upper-bound filter for the prior window).
  |     Returns {signal: weighted_count}.
  +-- _score_from_breakdown(current, prior) -> float | None
  |     Sparse-data guards. Clamping. Returns None
  |     for "went dark."
  +-- compute_polarity_from_db(
  |       conn, brand_id, window_days, *, now=None)
  |       -> float | None
  |     The v1.8 entry point. Splits into current
  |     and prior windows, calls the breakdown
  |     twice, delegates to _score_from_breakdown.
  |     Returns None for `_unattributed` immediately.
  +-- compute_polarity(posts, current, prior)
  |       -> float | None      (LEGACY v1.7 path)
  |     Still present for backwards compat with
  |     pre-v1.8 tests; new callers should use
  |     compute_polarity_from_db.
  +-- polarity_fill(score, max_abs_score) -> str
  |     Maps the score to one of 6 bins (rgb strings). Returns
  |     YELLOW for None.
  +-- _text_color_for_fill(fill_rgb) -> str
  |     Picks black or white text based on BT.709 luminance.
  +-- _LUMINANCE_THRESHOLD = 0.5
  +-- _LIGHT_RED, _RED, _DARK_RED, _DARK_GREEN, _GREEN, _LIGHT_GREEN
  +-- _YELLOW
       The "went dark" sentinel.

x_monitor/dashboard.py
  +-- _QID_TO_SIGNAL: dict[str, str]    (line 204)
  |     Retained for legacy source_query_id reads.
  |     Not used by the v1.8 polarity path.
  +-- _build_treemap_tiles(latest_run, polarity_window_days)
  |     Calls compute_polarity_from_db once per brand.
  |     Computes area_weight from the lifetime post count.
  +-- ALLOWED_POLARITY_WINDOWS = (1, 7, 30)    (line 220)
  +-- POLARITY_WINDOW_COOKIE = "polarity_window"  (line 221)
  +-- _resolve_polarity_window(req, default)      (line 224)
  +-- _clamp_polarity_window(window, ceiling)    (line 244)
  +-- /api/polarity_window/<int:days> route      (line 747)
       Sets the cookie and redirects.
```

---

## 12. Common failure modes and what they look like

| Symptom | Cause | Fix |
|---|---|---|
| Every tile shows "no data" (yellow) | The current polarity window has zero kept posts for every brand. The pipeline isn't running, or all kept posts have NULL `created_at`. | Check `data/runs/<latest>/summary.json` for the run status. Check `posts.created_at IS NULL` count. |
| One tile is yellow and the rest are normal | That specific brand has zero kept posts in the current window but had data in the prior window. The "went dark" guard fired. | Expected behavior. The dashboard is correctly signaling the brand is quiet. |
| Every tile is `+0.00%` (DARK_GREEN) | Both windows are empty for every brand. The pipeline ingested posts but none have a per-brand signal in `posts_brands_signals`. | Run the v1.8 classify_signal backfill: `python -m x_monitor reattribute-all-posts`. |
| Polarity % changes drastically between cycles | The 30-second dashboard refresh is happening mid-cycle. The `now` anchor is the last run's `finished_at`, but if a run is in progress, the `latest_run` is stale. | Wait for the next pipeline run. The "last updated" topbar shows the staleness. |
| Polarity windows don't update when the cookie is set | The cookie was set on a different domain/path, or the browser is rejecting the cookie. | Inspect the `Set-Cookie` header on `/api/polarity_window/7`; the path is `/` and the max-age is 1 year. |
| The grid's polarity badge doesn't match the treemap's tile fill | Expected. The grid uses `window_days` (default 14, non-toggleable); the treemap uses `polarity_window_days` (toggleable 1/7/30). | v1.8.x follow-up plan to align them. |
| A 2-brand post shows `weight=0.5` on the drill-down but `weight=0.4999...` on aggregation | IEEE 754 rounding on `1.0/3.0`-style weights (Decision 17). | Expected; the conservation test allows a 1e-3 tolerance. |

---

## 13. Tests

The polarity math is covered by `tests/test_treemap.py` and
`tests/test_polarity.py` (test count not enumerated here; see
`x-monitoring/tests/`). The key coverage:

- All 3 sparse-data guard branches (both empty, prior empty,
  current empty)
- The normal path (both windows have data, both signal rates
  positive / both negative / one positive one negative)
- Clamping to [-1, +1] (defensive)
- The polarity_fill bin boundaries (every t boundary value)
- The YELLOW sentinel for None
- The `_unattributed` brand handling (Decision 15) —
  `test_unattributed_excluded_from_polarity` asserts the SUM
  returns 0 for `_unattributed`
- The BT.709 luminance threshold (text color picker)
- The v1.8 fractional weights — a 2-brand post contributes 0.5
  to each brand's totals; the conservation invariant holds
  within the 1e-3 tolerance
- The v1.8 EXPLAIN QUERY PLAN — `test_polarity_uses_index`
  asserts no SCAN nodes appear on a 100k-post fixture
- The cookie set / read / clamp cycle (v1.7.4)

---

## 14. Glossary

- **Window** — a half-open time interval `[lower, upper)`. Posts
  with `lower <= created_at < upper` are included.
- **Signal** — one of `release`, `community_question`,
  `criticism`, `commenter_capture`, `praise`, `other`. Stored
  per-brand in `posts_brands_signals(post_id, brand_id, signal)`
  (v1.8+). Replaces `posts.signal` which was dropped in
  migration 004.
- **Weight** — a `REAL` on `posts_brands(brand_id, post_id,
  weight)`; `1/N` per post naming N brands. Sum equals 1.0
  within 1e-3 tolerance (Decision 17).
- **`_unattributed`** — sentinel `brand_id` for posts with no
  detected brand. Excluded from all polarity and per-brand
  queries (Decision 15). Has a `CHECK` constraint on
  `posts_brands_signals` and an early-return in
  `compute_polarity_from_db`.
- **Polarity** — a number in `[-1, +1]` (or `None` for "went
  dark") computed by `compute_polarity_from_db`. Encodes the
  change in `(praise - criticism) / total_weighted` between the
  current and prior windows.
- **Active tile** — a tile with `area_weight > 0` (i.e., the
  brand has kept posts). Inactive tiles go to the "no data"
  strip.
- **Relative polarity** — `score / max_abs_score` over the
  active set. The denominator makes the palette responsive on
  day 1 when absolute scores are small.
- **"Went dark"** — the brand has data in the prior window but
  zero in the current. Polarity returns `None`, the tile shows
  "no data," the fill is yellow.
- **"No data" (state)** — the brand has zero kept posts
  lifetime. Renders as a faded placeholder strip at the top of
  the treemap, not as a polarity tile.