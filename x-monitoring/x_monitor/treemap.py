# {{AGENT_ATTRIBUTION}}
"""Finviz-style treemap layout + polarity + SVG assembly (inline SVG, no d3).

Public surface:
- build_treemap_svg(tiles, *, width, height) -> str
- compute_polarity(posts, current_window, prior_window) -> float | None
    LEGACY (v1.7): reads post-level source_query_id + posts.created_at.
    Still used by tests that predate the v1.8 multi-brand rewrite.
    New code should call compute_polarity_from_db (the SQL-backed version).
- compute_polarity_from_db(conn, brand_id, window_days, *, now=None) -> float | None
    v1.8 (Unit 4 / R17): reads posts_brands_signals + posts_brands via the
    JOIN shape from Decision 18. Filters _unattributed (Decision 15).
- compute_polarity_signal_breakdown(conn, brand_id, window_start_epoch, *,
                                     window_end_epoch=None) -> dict[str, float]
    v1.8 (Unit 4 / R17): raw signal -> weighted_count breakdown per
    brand in [window_start_epoch, window_end_epoch). The dryrun
    verification calls this directly.
- bin_polarity(score: float | None) -> str
- separate_active_and_no_data(tiles) -> (active_tiles, no_data_tiles)
- TreemapTile (NamedTuple)
- POLARITY_SQL (str constant): the SQL string passed to sqlite3 for
    the polarity breakdown. Single source of truth for EXPLAIN tests.

The treemap is one level deep: one <a> per enabled model, wrapped around
a <rect>. Tile area encodes tweet volume (Q1 + Q4 in the current N-day
window). Tile fill encodes the polarity score (rate change between the
current and prior N-day windows). The "no data" state renders as a faded
per-model placeholder at the top of the treemap (one placeholder per
no-data model), at 15% opacity, so the model is visibly tracked but not
weighted into the layout.

The layout uses the squarify PyPI package (Bruls/Huijing/van Wijk
squarified treemaps, Apache-2.0, https://pypi.org/project/squarify/).
No randomness; the algorithm is deterministic by contract.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Iterable

import squarify

# NOTE: We intentionally do NOT import _QID_TO_SIGNAL or _parse_post_timestamp
# from .dashboard at module load. dashboard.py imports build_treemap_svg from
# THIS module, so any top-level import here would form a cycle. Both names
# are resolved lazily inside compute_polarity below.


# v1.8.1 — Finviz-style 5-step divergent palette, balanced so the most-extreme
# bin is the BRIGHTEST on the dark dashboard background. This matches the
# user-intuitive Finviz convention: extremes are vivid ("light"), middle is
# muted ("dark"). The previous v1.7.3 palette named extremes as DEEP_* which
# read as darker on screen (DEEP_GREEN rgb(0,150,0) has luminance 0.421,
# lower than GREEN rgb(30,180,30) at 0.538) — opposite of what users expect.
#
# The 6 visible bins are (from -1 to +1):
#   t <= -0.6  -> LIGHT_RED    (most negative, brightest red)
#   -0.6 < t <= -0.2  -> RED         (negative, medium red)
#   -0.2 < t <  0     -> DARK_RED    (slightly negative, just tinted)
#    0  < t <  0.2    -> DARK_GREEN  (slightly positive, just tinted)
#    0.2 <= t <  0.6  -> GREEN       (positive, medium green)
#    t >=  0.6        -> LIGHT_GREEN (most positive, brightest green)
#
# Luminance (BT.709) is monotonically ascending across the positive side
# (0.252 -> 0.628 -> 0.849) and the negative side (0.152 -> 0.299 -> 0.521)
# so the most-extreme tile always reads as the most-visible on the dark bg.
#
# None (the "went dark" sentinel) returns YELLOW as before so the
# visual cue is preserved across palette rewrites.
_LIGHT_RED = (255, 100, 100)
_RED = (210, 40, 40)
_DARK_RED = (90, 25, 25)
_DARK_GREEN = (25, 80, 25)
_GREEN = (60, 200, 60)
_LIGHT_GREEN = (120, 255, 120)
_YELLOW = (234, 179, 8)    # the "went dark" sentinel


@dataclass(frozen=True)
class TreemapTile:
    """One model's data for the treemap layout.

    brand_id: canonical model id (e.g. "minimax", "mistral")
    display_name: human label (e.g. "MiniMax AI", "Mistral")
    accent_color: hex string from MODEL_ACCENT_COLORS (used as rect stroke)
    area_weight: float, the tile's area weight (cumulative post count).
                 0 means "no data" -> rendered as a placeholder, not in the layout.
    polarity_score: float in [-1, +1], or None for the "went dark" sentinel.
    posts_in_window: int, count of posts in the polarity window (for <title>).
                     Defaults to 0 for fixtures / tests that don't care.
    polarity_window_days: int, the polarity window the score was computed over
                          (for <title>). Defaults to 0.
    last_run_finished_at: str | None, ISO timestamp of the latest pipeline run
                          (for <title>). None when no run has completed yet.
    sector: str | None, human label (e.g. "closed-source LLM") for <title>.
            None when the model is not in MODEL_SECTORS.
    """

    brand_id: str
    display_name: str
    accent_color: str
    area_weight: float
    polarity_score: float | None
    posts_in_window: int = 0
    polarity_window_days: int = 0
    last_run_finished_at: str | None = None
    sector: str | None = None


# Tiny epsilon so a 0-area tile still gets a rect (squarify requires all sizes > 0).
# We don't WANT 0-area tiles in the layout (they go to the no-data strip), but the
# constant is referenced in case a future unit wants to render 1px "stubs" for them.
SIZE_EPSILON = 1e-6

# v1.8 — Finviz aesthetic refinements. Defaults locked; tune from live visual diff.
_TILE_PADDING_PX = 4
_TILE_GAP_PX = 2
_TILE_BORDER_RADIUS = 0
_FONT_FAMILY = "Arial, Helvetica, sans-serif"
_LUMINANCE_THRESHOLD = 0.5
_TEXT_DARK = "#0d1117"
_TEXT_LIGHT = "#ffffff"


# Sector taxonomy for the 11 enabled models (v1.7 roster). Used by the
# native <title> tooltip. New models default to None if not listed here.
MODEL_SECTORS: dict[str, str] = {
    "minimax": "closed-source LLM",
    "deepseek": "Chinese open-source LLM",
    "qwen": "Chinese open-source LLM",
    "glm": "Chinese open-source LLM",
    "moonshot_kimi": "Chinese closed-source LLM",
    "inclusionai": "Chinese open-source LLM",
    "mimo": "Chinese open-source LLM",
    "mistral": "Western open-source LLM",
    "stepfun": "Chinese multimodal",
    "ernie": "Chinese closed-source LLM",
    "hunyuan": "Chinese closed-source LLM",
}


def _luminance(rgb: tuple[int, int, int]) -> float:
    """ITU-R BT.709 relative luminance for an sRGB 0-255 tuple.

    Output in [0, 1]. Used to pick black-vs-white text against a saturated
    polarity fill so dark fills get white text and light fills get dark text.
    """
    r, g, b = rgb
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255.0


def _text_color_for_fill(fill_rgb: str) -> str:
    """Pick white or dark text for a polarity fill string.

    `fill_rgb` is an `rgb(R, G, B)` string (the format polarity_fill emits).
    Anything we don't recognise falls back to white.
    """
    m = re.match(r"^rgb\((\d+),\s*(\d+),\s*(\d+)\)$", fill_rgb.strip())
    if not m:
        return _TEXT_LIGHT
    r, g, b = (int(m.group(i)) for i in (1, 2, 3))
    lum = _luminance((r, g, b))
    return _TEXT_DARK if lum >= _LUMINANCE_THRESHOLD else _TEXT_LIGHT


def _rgb(c: tuple[int, int, int]) -> str:
    """Format a solid rgb() string from a 3-tuple. No alpha."""
    return f"rgb({c[0]}, {c[1]}, {c[2]})"


def polarity_fill(score: float | None, max_abs_score: float) -> str:
    """Map a polarity score to a Finviz-style 5-step divergent palette,
    relative to the most extreme score in the active set.

    Bin thresholds (Finviz convention):
        t <= -0.6  -> DEEP_RED
        -0.6 < t <= -0.2  -> RED
        -0.2 < t <  0     -> DARK_RED
         0  < t <  0.2    -> DARK_GREEN
         0.2 <= t <  0.6  -> GREEN
         t >=  0.6        -> DEEP_GREEN

    The "went dark" sentinel (score is None) returns --yellow regardless
    of the scale.

    `max_abs_score` is the absolute value of the most extreme polarity
    score in the active tile set. If all scores are 0, the function
    returns DARK_RED for any negative score and DARK_GREEN for any
    positive score (degenerate-but-readable). For score == 0 exactly
    we pick DARK_GREEN (the conventional "neutral slight positive"
    read in Finviz, since both dark bins are visually similar and
    green is the conventional default).
    """
    if score is None:
        return _rgb(_YELLOW)
    if max_abs_score <= 0:
        # Degenerate. Default to dark green for any non-None score.
        return _rgb(_DARK_GREEN)
    t = max(-1.0, min(1.0, score / max_abs_score))
    if t <= -0.6:
        return _rgb(_LIGHT_RED)
    if t <= -0.2:
        return _rgb(_RED)
    if t < 0:
        return _rgb(_DARK_RED)
    if t < 0.2:
        return _rgb(_DARK_GREEN)
    if t < 0.6:
        return _rgb(_GREEN)
    return _rgb(_LIGHT_GREEN)


def bin_polarity(score: float | None) -> str:
    """Backwards-compatible wrapper for tests that predate polarity_fill.

    Treats the score as if it were already normalized to [-1, +1] (i.e.
    max_abs_score=1). New code should call polarity_fill directly with
    the active-set max-abs.
    """
    return polarity_fill(score, 1.0)


# --- v1.8: SQL-backed polarity (Unit 4, R17, Decision 18) -------------------

# The polarity SQL, factored as a module-level constant so EXPLAIN QUERY PLAN
# tests can reference the same string the production code runs.
# - Decision 18 (JOIN not IN subquery): the query planner can use the
#   posts_brands_signals(brand_id, signal_id) and posts_brands(brand_id, post_id)
#   indexes to seek by brand, then join posts(tweet_id) for the time-window
#   filter. EXPLAIN should show all three indexes used (no SORT or SCAN).
# - Decision 15 (_unattributed filter): the WHERE clause excludes the
#   sentinel brand so the treemap's "unattributed" bin doesn't pollute
#   the polarity score.
# - weight = SUM(pb.weight * (1 + p.retweet_count)): each post's signal is
#   amplified by its pure-retweet count — an RT inherits the original's
#   signal ("each utterance = one vote"). A 2-brand post contributes
#   0.5*(1+rt) to each brand (Decision 9 fractional weight x RT fold).
# - the window filters on created_at_epoch (unix seconds), NOT the
#   Twitter-format created_at: ISO-bound string comparison against the
#   weekday-leading Twitter format sorted incorrectly and silently ignored
#   the time window pre-migration-006.
POLARITY_SQL: str = (
    "SELECT pbs.signal_id, SUM(pb.weight * (1 + p.retweet_count)) AS weighted_count "
    "FROM posts_brands_signals pbs "
    "JOIN posts_brands pb "
    "  ON pb.post_id = pbs.post_id AND pb.brand_id = pbs.brand_id "
    "JOIN posts p ON p.tweet_id = pbs.post_id "
    "WHERE pbs.brand_id = ? "
    "  AND pbs.brand_id != '_unattributed' "
    "  AND p.created_at_epoch >= ? "
    "GROUP BY pbs.signal_id"
)


def compute_polarity_signal_breakdown(
    conn,
    brand_id: str,
    window_start_epoch: str,
    *,
    window_end_epoch: str | None = None,
) -> dict[str, float]:
    """Return {signal: weighted_count} for one brand.

    Implements Unit 4 / R17 / Decision 18 of the call-path attribution
    pipeline. Reads from posts_brands_signals + posts_brands + posts via
    the JOIN shape (no IN subquery). The _unattributed brand is excluded
    by the WHERE clause (Decision 15); pass `_unattributed` explicitly
    returns an empty dict by the same mechanism (the != filter).

    Args:
        conn: a sqlite3.Connection (the Store's _conn).
        brand_id: the brand slug (e.g. "minimax"). "_unattributed"
            returns an empty dict by the same WHERE filter.
        window_start_epoch: unix-second epoch for the lower bound. Posts
            with created_at_epoch >= window_start_epoch are included.
        window_end_epoch: optional unix-second upper bound (exclusive). When
            None, the SQL omits the upper-bound filter and the result
            includes all posts from window_start_epoch forward. The
            polarity score uses this to slice [now-2N, now-N) precisely.

    Returns:
        A dict mapping signal name (release / community_question /
        criticism / commenter_capture / praise / other) to weighted
        count. Weights are 1/N for multi-brand posts per Decision 9.

    Notes:
        - Indexes used: idx_posts_brands_signals_brand_id_signal_id,
          idx_posts_brands_brand_post, posts (PK). EXPLAIN should show
          no SCAN or SORT on a populated DB.
    """
    if window_end_epoch is None:
        rows = conn.execute(
            POLARITY_SQL, (brand_id, window_start_epoch),
        ).fetchall()
    else:
        # POLARITY_SQL ends with "GROUP BY pbs.signal_id"; insert the
        # upper-bound filter BEFORE the GROUP BY so it is applied
        # before aggregation. Splitting on "GROUP BY" and re-appending
        # keeps the constant a single source of truth.
        head, tail = POLARITY_SQL.rsplit("GROUP BY", 1)
        sql_with_upper = head + "AND p.created_at_epoch < ? GROUP BY" + tail
        rows = conn.execute(
            sql_with_upper,
            (brand_id, window_start_epoch, window_end_epoch),
        ).fetchall()
    return {r["signal_id"]: float(r["weighted_count"]) for r in rows}


def _score_from_breakdown(
    current: dict[str, float],
    prior: dict[str, float],
) -> float | None:
    """Compute the polarity score from two signal breakdowns.

    Same sparse-data guards as the legacy compute_polarity() function:
      - both windows empty (no praise/criticism AND no total) -> 0.0
      - prior empty but current has data -> current_praise_rate -
        current_criticism_rate (no NaN propagation)
      - current empty but prior had data -> None (the "went dark" sentinel)
      - normal path -> (current_praise_rate - current_criticism_rate) -
        (prior_praise_rate - prior_criticism_rate), clamped to [-1, 1]

    `total` is computed as the sum of all signals in the breakdown.
    This matches the legacy definition (Q1+Q2+Q3+Q4+Q5+Q6 signal counts)
    when the breakdown covers all 6 signals. With per-brand signals
    from posts_brands_signals, the breakdown only includes the 6 v1
    signal names, so the totals are equivalent.
    """
    current_total = sum(current.values())
    prior_total = sum(prior.values())
    current_praise = current.get("praise", 0.0)
    current_criticism = current.get("criticism", 0.0)
    prior_praise = prior.get("praise", 0.0)
    prior_criticism = prior.get("criticism", 0.0)

    # Sparse-data guard 1: both windows empty -> 0.0
    if current_total == 0 and prior_total == 0:
        return 0.0

    # Sparse-data guard 2: prior empty but current has data
    if prior_total == 0:
        current_rate = (current_praise - current_criticism) / current_total
        return max(-1.0, min(1.0, current_rate))

    # Sparse-data guard 3: current empty but prior had data -> went dark
    if current_total == 0:
        return None

    # Normal path
    current_rate = (current_praise - current_criticism) / current_total
    prior_rate = (prior_praise - prior_criticism) / prior_total
    score = current_rate - prior_rate
    return max(-1.0, min(1.0, score))


def compute_polarity_from_db(
    conn,
    brand_id: str,
    window_days: int,
    *,
    now=None,
) -> float | None:
    """Compute the polarity score for one brand from the DB.

    v1.8 (Unit 4 / R17). Reads posts_brands_signals + posts_brands via the
    JOIN shape from Decision 18. Splits the window into [now-N, now) and
    [now-2N, now-N); the score is the rate-of-change between them.

    Args:
        conn: a sqlite3.Connection.
        brand_id: the brand slug (e.g. "minimax"). "_unattributed"
            returns None (no-data tile per Decision 15).
        window_days: the polarity window in days (N). The prior window
            is [now-2N, now-N); the current window is [now-N, now).
        now: anchor datetime (test seam). Defaults to
            datetime.now(timezone.utc). Accepts naive datetimes
            (treated as UTC) for convenience.

    Returns:
        A float in [-1.0, +1.0] or None for the "went dark" sentinel.
        For `_unattributed`, returns None (no-data tile).
    """
    from datetime import datetime, timedelta, timezone

    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    if brand_id == "_unattributed":
        # Per Decision 15, the sentinel has no meaningful polarity;
        # treat as no-data.
        return None

    # Compute epoch bounds for the window queries. posts.created_at_epoch
    # is a unix-second integer (populated by insert_posts / backfilled by
    # the migration-006 script); filtering on it fixes the pre-006 bug where
    # ISO-bound string comparison against the Twitter-format created_at
    # sorted incorrectly and silently ignored the time window.
    current_start_epoch = int((now - timedelta(days=window_days)).timestamp())
    prior_start_epoch = int((now - timedelta(days=2 * window_days)).timestamp())

    # Current window: [now-N, now). Prior window: [now-2N, now-N).
    # The breakdown helper accepts an optional upper bound for the
    # windowed prior slice, so we can run two clean queries that
    # don't overlap. Without window_end_epoch=current_start_epoch the prior
    # slice would include the current window's posts (the SQL has only
    # a lower bound by default).
    current = compute_polarity_signal_breakdown(
        conn, brand_id, current_start_epoch,
    )
    prior = compute_polarity_signal_breakdown(
        conn, brand_id, prior_start_epoch,
        window_end_epoch=current_start_epoch,
    )

    return _score_from_breakdown(current, prior)


def compute_polarity(
    posts: Iterable[dict],
    current_window: tuple,
    prior_window: tuple,
) -> float | None:
    """Compute the polarity score for one model (LEGACY v1.7 path).

    polarity = (praise_rate_current - criticism_rate_current)
             - (praise_rate_prior - criticism_rate_prior)

    Each rate is signal_count / total_q1_to_q6_count in the respective window.
    `total_q1_to_q6_count` is the sum of Q1, Q2, Q3, Q4, Q5, Q6 signal counts
    (all posts classified into one of the 6 buckets).

    Sparse-data guards (per the plan's R3):
      - current_total == 0 AND prior_total == 0 -> 0.0 (muted bin; no data anywhere)
      - prior_total == 0 AND current_total > 0 -> define prior rates as 0;
        return current_praise_rate - current_criticism_rate (no NaN propagation)
      - current_total == 0 AND prior_total > 0 -> None (the "went dark" sentinel;
        the route maps it to --yellow and the UI labels "went dark")

    Returns a float in approximately [-1.0, +1.0] or None for the went-dark case.
    """
    # Lazy import: dashboard.py imports from this module at top-level, so a
    # module-level import here would cycle. These two helpers are pure
    # functions of `dashboard.py`'s module state, so resolving them at call
    # time is safe and avoids the cycle.
    from .dashboard import _QID_TO_SIGNAL, _parse_post_timestamp

    current_lower, current_upper = current_window
    prior_lower, prior_upper = prior_window

    current_praise = current_criticism = current_total = 0
    prior_praise = prior_criticism = prior_total = 0

    for p in posts:
        sqid = p.get("source_query_id") or ""
        signal = _QID_TO_SIGNAL.get(sqid)
        if signal is None:
            continue
        dt = _parse_post_timestamp(p.get("created_at"))
        if dt is None:
            continue
        if current_lower <= dt < current_upper:
            current_total += 1
            if signal == "praise":
                current_praise += 1
            elif signal == "criticism":
                current_criticism += 1
        elif prior_lower <= dt < prior_upper:
            prior_total += 1
            if signal == "praise":
                prior_praise += 1
            elif signal == "criticism":
                prior_criticism += 1

    # Sparse-data guard 1: both windows empty -> 0.0
    if current_total == 0 and prior_total == 0:
        return 0.0

    # Sparse-data guard 2: prior empty but current has data -> define prior rates as 0
    if prior_total == 0:
        # No NaN, no division by zero. current_total > 0 here.
        current_rate = (current_praise - current_criticism) / current_total
        # Clamp to [-1, 1] in case of any future signal-counting bug.
        return max(-1.0, min(1.0, current_rate))

    # Sparse-data guard 3: current empty but prior had data -> went dark
    if current_total == 0:
        return None

    # Normal path: both windows have data.
    current_rate = (current_praise - current_criticism) / current_total
    prior_rate = (prior_praise - prior_criticism) / prior_total
    score = current_rate - prior_rate
    return max(-1.0, min(1.0, score))


def separate_active_and_no_data(
    tiles: list[TreemapTile],
) -> tuple[list[TreemapTile], list[TreemapTile]]:
    """Split tiles into active (non-zero area) and no-data (zero area).

    A tile is "no data" if its area_weight is 0 (or negative — defensive).
    """
    active: list[TreemapTile] = []
    no_data: list[TreemapTile] = []
    for t in tiles:
        if t.area_weight > 0:
            active.append(t)
        else:
            no_data.append(t)
    return active, no_data


def _no_data_strip_svg(no_data: list[TreemapTile], width: int) -> str:
    """Render the no-data placeholders as a horizontal strip at the top.

    Each placeholder is a small box (min 80x40) at 15% opacity, with the
    model name. The strip spans the full SVG width, with boxes laid out
    left-to-right. If there are more than 6 no-data models, the strip
    wraps to a second row.
    """
    if not no_data:
        return ""
    box_w = max(80, width // max(len(no_data), 1) - 4)
    box_h = 40
    per_row = max(1, width // box_w)
    parts: list[str] = ['<g class="no-data" opacity="0.15">']
    for i, tile in enumerate(no_data):
        row = i // per_row
        col = i % per_row
        x = col * box_w + 2
        y = row * (box_h + 2) + 2
        # Use the model's accent color as fill (faded via the opacity attr)
        parts.append(
            f'<rect x="{x}" y="{y}" width="{box_w - 4}" height="{box_h}" '
            f'fill="{tile.accent_color}" stroke="{tile.accent_color}" '
            f'stroke-width="1" rx="2" ry="2"/>'
            f'<text x="{x + (box_w - 4) / 2}" y="{y + box_h / 2 + 4}" '
            f'font-size="11" fill="#8b949e" text-anchor="middle" '
            f'pointer-events="none" opacity="0.6">{_xml_escape(tile.display_name)} (no data)</text>'
        )
    parts.append("</g>")
    return "".join(parts)


def _xml_escape(s: str) -> str:
    """Minimal XML escape for user-controlled text in SVG."""
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _squarify_layout(
    active: list[TreemapTile], width: int, height: int
) -> list[tuple[TreemapTile, dict[str, float]]]:
    """Run the squarify layout and return (tile, rect_dict) pairs.

    `squarify.squarify` returns rects in the same order as the input sizes,
    so we zip them back to the tiles.

    v1.8: each rect is shrunk by `_TILE_PADDING_PX` on the top-left edge
    and `_TILE_GAP_PX` on the bottom-right edge to produce a visible
    inner margin and inter-tile gutter. Total area decreases by ~1-2%
    per edge — visually negligible.
    """
    sizes = [t.area_weight for t in active]
    normed = squarify.normalize_sizes(sizes, width, height)
    rects = squarify.squarify(normed, 0, 0, width, height)
    shrunk: list[tuple[TreemapTile, dict[str, float]]] = []
    for tile, r in zip(active, rects):
        new_x = float(r["x"]) + _TILE_PADDING_PX
        new_y = float(r["y"]) + _TILE_PADDING_PX
        new_dx = max(0.0, float(r["dx"]) - _TILE_PADDING_PX - _TILE_GAP_PX)
        new_dy = max(0.0, float(r["dy"]) - _TILE_PADDING_PX - _TILE_GAP_PX)
        shrunk.append((tile, {"x": new_x, "y": new_y, "dx": new_dx, "dy": new_dy}))
    return shrunk


def _tile_svg(tile: TreemapTile, rect: dict[str, float], max_abs_score: float) -> str:
    """Render one active tile as an <a> wrapping a <rect> with two <text>
    labels: the model name on top, the polarity as a signed percentage
    below it.

    v1.8 refinements (Finviz aesthetic):
    - Font family = `Arial, Helvetica, sans-serif` (was system-ui).
    - Pct font-weight = 400 (was 500). Symbol line stays bold (700).
    - Text color = luminance-based (was always white). Dark fills keep
      white text, light fills get dark text (#0d1117).
    - Tile border radius = 0 (was 2). Finviz tiles are sharp squares.
    - Native <title> tooltip carries brand_id, polarity, window days,
      post count, last-run timestamp, and sector.

    Font size is adaptive to the smaller of the tile width/height so
    small tiles get a smaller label and don't overflow.
    """
    x, y, dx, dy = rect["x"], rect["y"], rect["dx"], rect["dy"]
    fill = polarity_fill(tile.polarity_score, max_abs_score)
    text_color = _text_color_for_fill(fill)
    name = _xml_escape(tile.display_name)
    # Polarity as a signed percentage. Multiply by 100 because the raw
    # polarity is a rate difference in [-1, +1]. Two decimals matches
    # Finviz (+1.16%, -3.49%) but is dropped to 1 decimal under 100px
    # wide tiles to save space.
    if tile.polarity_score is None:
        pct_str = "no data"
        pct_val_for_title = "no data"
    else:
        pct_val = tile.polarity_score * 100
        decimals = 1 if dx < 100 or dy < 80 else 2
        pct_str = f"{pct_val:+.{decimals}f}%"
        pct_val_for_title = pct_str
    aria = (
        f"{tile.display_name}: polarity {pct_str}, "
        f"area weight {tile.area_weight:.0f}"
    )
    # v1.8 — extended native <title>. Browser-rendered SVG tooltip; no JS.
    title_lines = [
        f"{tile.display_name} ({tile.brand_id})",
        f"Polarity: {pct_val_for_title} (vs prior {tile.polarity_window_days}d)",
        f"Posts in window: {tile.posts_in_window}",
    ]
    if tile.last_run_finished_at:
        title_lines.append(f"Last run: {tile.last_run_finished_at}")
    if tile.sector:
        title_lines.append(f"Sector: {tile.sector}")
    title = "\n".join(title_lines)
    # Adaptive font size. Finviz uses ~16pt for the name and ~12pt for
    # the percentage. We scale to ~16% of the shorter side, clamped to
    # [9, 22]. Tile must be at least 60x40 to render any text at all.
    if dx < 60 or dy < 40:
        name = ""
        pct_str_render = ""
    else:
        font = max(9, min(22, int(min(dx, dy) * 0.18)))
        # Truncate the name if it would overflow (rough: 0.6em per char).
        char_w = font * 0.6
        if len(name) * char_w > dx * 0.9:
            max_chars = max(1, int(dx * 0.9 / char_w) - 1)
            name = name[:max_chars] + "…"
        pct_str_render = pct_str
    parts = [
        f'<a href="/model/{tile.brand_id}" data-href="/model/{tile.brand_id}" '
        f'aria-label="{_xml_escape(aria)}">',
        f'<title>{_xml_escape(title)}</title>',
        f'<rect x="{x:.2f}" y="{y:.2f}" width="{dx:.2f}" height="{dy:.2f}" '
        f'fill="{fill}" stroke="{tile.accent_color}" stroke-width="2" '
        f'rx="{_TILE_BORDER_RADIUS}" ry="{_TILE_BORDER_RADIUS}"/>',
    ]
    if name:
        # Two-line layout: name slightly above center, pct slightly below.
        cx = x + dx / 2
        cy = y + dy / 2
        # Stagger by font size so the two lines don't overlap.
        name_y = cy - font * 0.2
        pct_y = cy + font * 0.9
        parts.append(
            f'<text x="{cx:.2f}" y="{name_y:.2f}" '
            f'font-size="{font}" fill="{text_color}" text-anchor="middle" '
            f'font-weight="700" pointer-events="none" '
            f'font-family="{_FONT_FAMILY}">{name}</text>'
        )
        parts.append(
            f'<text x="{cx:.2f}" y="{pct_y:.2f}" '
            f'font-size="{max(8, font - 2)}" fill="{text_color}" text-anchor="middle" '
            f'font-weight="400" pointer-events="none" '
            f'font-family="{_FONT_FAMILY}">{_xml_escape(pct_str_render)}</text>'
        )
    parts.append("</a>")
    return "".join(parts)


def build_treemap_svg(
    tiles: list[TreemapTile], *, width: int = 1200, height: int = 800
) -> str:
    """Return the inline SVG string for the treemap.

    The treemap is one level deep: one <a> per enabled model, wrapped around
    a <rect>. Tile area encodes tweet volume (Q1 + Q4 in the current N-day
    window). Tile fill encodes the polarity score.

    No-data models (area_weight == 0) are rendered as a faded horizontal
    strip at the top of the treemap, with one placeholder per model at
    15% opacity. They are not laid out as part of the squarify layout.
    """
    active, no_data = separate_active_and_no_data(tiles)

    svg: list[str] = [
        f'<svg class="treemap" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}" '
        f'role="img" aria-label="LLM model attention treemap" '
        f'xmlns="http://www.w3.org/2000/svg">'
    ]

    if not active and not no_data:
        svg.append(
            f'<text x="50%" y="50%" text-anchor="middle" fill="#8b949e" '
            f'font-size="14">No models enabled</text>'
        )
        svg.append("</svg>")
        return "".join(svg)

    if no_data:
        # Reserve top 50px for the no-data strip.
        no_data_strip_h = 50 if len(no_data) <= 6 else 90
        svg.append(_no_data_strip_svg(no_data, width))
        layout_height = height - no_data_strip_h
        svg.append(f'<g transform="translate(0, {no_data_strip_h})">')
    else:
        layout_height = height
        svg.append("<g>")

    if active:
        # Relative polarity: normalize to the most extreme active score so
        # the strongest positive signal in the dashboard hits full green
        # and the strongest negative hits full red. This is the same
        # approach Finviz uses (relative, not absolute threshold) and
        # keeps the palette responsive on day 1 when absolute scores are
        # small. Went-dark (None) and no-data (area=0) are excluded.
        # If the active set has a single tile, max_abs_score will be
        # that tile's |score| and it lands at full saturation — which
        # is the right "you're the only signal" read.
        active_scores = [t.polarity_score for t in active if t.polarity_score is not None]
        max_abs_score = max((abs(s) for s in active_scores), default=0.0)
        # squarify returns 4-tuple lists in the same order as the input sizes.
        # All sizes are > 0 by separate_active_and_no_data's contract.
        for tile, rect in _squarify_layout(active, width, layout_height):
            svg.append(_tile_svg(tile, rect, max_abs_score))

    svg.append("</g>")
    svg.append("</svg>")
    return "".join(svg)
