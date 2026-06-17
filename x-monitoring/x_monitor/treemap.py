# {{AGENT_ATTRIBUTION}}
"""Finviz-style treemap layout + polarity + SVG assembly (inline SVG, no d3).

Public surface:
- build_treemap_svg(tiles, *, width, height) -> str
- compute_polarity(posts, current_window, prior_window) -> float | None
- bin_polarity(score: float | None) -> str
- separate_active_and_no_data(tiles) -> (active_tiles, no_data_tiles)
- TreemapTile (NamedTuple)

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

from collections import Counter
from typing import Iterable, NamedTuple

import squarify

# NOTE: We intentionally do NOT import _QID_TO_SIGNAL or _parse_post_timestamp
# from .dashboard at module load. dashboard.py imports build_treemap_svg from
# THIS module, so any top-level import here would form a cycle. Both names
# are resolved lazily inside compute_polarity below.


# CSS color tokens from x_monitor/static/dashboard.css (lines 4-14).
# These are the source of truth for the polarity palette; the SVG embeds
# the resolved rgba() string per tile (no CSS variable lookups in SVG).
_RED = (239, 68, 68)       # #ef4444
_MUTED = (139, 148, 158)   # #8b949e
_GREEN = (16, 185, 129)    # #10b981
_YELLOW = (234, 179, 8)    # #eab308 — used for the "went dark" sentinel


class TreemapTile(NamedTuple):
    """One model's data for the treemap layout.

    model_id: canonical model id (e.g. "minimax", "mistral")
    display_name: human label (e.g. "MiniMax AI", "Mistral")
    accent_color: hex string from MODEL_ACCENT_COLORS (used as rect stroke)
    area_weight: float, the tile's area weight (Q1 + Q4 in the current window).
                 0 means "no data" -> rendered as a placeholder, not in the layout.
    polarity_score: float in [-1, +1], or None for the "went dark" sentinel.
    """

    model_id: str
    display_name: str
    accent_color: str
    area_weight: float
    polarity_score: float | None


# Tiny epsilon so a 0-area tile still gets a rect (squarify requires all sizes > 0).
# We don't WANT 0-area tiles in the layout (they go to the no-data strip), but the
# constant is referenced in case a future unit wants to render 1px "stubs" for them.
SIZE_EPSILON = 1e-6


def _lerp_color(c1: tuple[int, int, int], c2: tuple[int, int, int], t: float) -> str:
    """Linearly interpolate two RGB triples at t in [0, 1] and return rgba() string.

    Output is rgba(0-255, 0-255, 0-255, 0.85) — fixed 0.85 alpha for legibility
    on a dark background (matches the grid cards' fill convention).
    """
    t = max(0.0, min(1.0, t))
    r = round(c1[0] + (c2[0] - c1[0]) * t)
    g = round(c1[1] + (c2[1] - c1[1]) * t)
    b = round(c1[2] + (c2[2] - c1[2]) * t)
    return f"rgba({r}, {g}, {b}, 0.85)"


def polarity_fill(score: float | None, max_abs_score: float) -> str:
    """Map a polarity score to a divergent palette color, relative to the
    most extreme score in the active set.

    Normalization:
        t = score / max_abs_score, clamped to [-1, +1]
    Then 3-stop interpolation red -> muted -> green at |t| in [0, 1]:
        t < 0  -> lerp(RED, MUTED, t + 1.0)     # -1 full red, 0 muted
        t > 0  -> lerp(MUTED, GREEN, t)         #  0 muted, +1 full green
        t == 0 -> muted

    The "went dark" sentinel (score is None) returns --yellow regardless
    of the scale, so it stays visually distinct from the muted bin.

    `max_abs_score` is the absolute value of the most extreme polarity
    score in the active tile set. If all scores are 0 (e.g. only one
    active model, or all flat), max_abs_score == 0 and the function
    returns muted for any score, which is the correct degenerate case.
    """
    if score is None:
        return f"rgba({_YELLOW[0]}, {_YELLOW[1]}, {_YELLOW[2]}, 0.85)"
    if max_abs_score <= 0:
        # Degenerate: only one active model, or all flat. Stay muted.
        return f"rgba({_MUTED[0]}, {_MUTED[1]}, {_MUTED[2]}, 0.85)"
    t = max(-1.0, min(1.0, score / max_abs_score))
    if t < 0:
        return _lerp_color(_RED, _MUTED, t + 1.0)
    if t > 0:
        return _lerp_color(_MUTED, _GREEN, t)
    # t == 0 exactly -> muted
    return f"rgba({_MUTED[0]}, {_MUTED[1]}, {_MUTED[2]}, 0.85)"


def bin_polarity(score: float | None) -> str:
    """Backwards-compatible wrapper for tests that predate polarity_fill.

    Treats the score as if it were already normalized to [-1, +1] (i.e.
    max_abs_score=1). New code should call polarity_fill directly with
    the active-set max-abs.
    """
    return polarity_fill(score, 1.0)


def compute_polarity(
    posts: Iterable[dict],
    current_window: tuple,
    prior_window: tuple,
) -> float | None:
    """Compute the polarity score for one model.

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
    """
    sizes = [t.area_weight for t in active]
    normed = squarify.normalize_sizes(sizes, width, height)
    rects = squarify.squarify(normed, 0, 0, width, height)
    return list(zip(active, rects))


def _tile_svg(tile: TreemapTile, rect: dict[str, float], max_abs_score: float) -> str:
    """Render one active tile as an <a> wrapping a <rect> with a <text> label."""
    x, y, dx, dy = rect["x"], rect["y"], rect["dx"], rect["dy"]
    fill = polarity_fill(tile.polarity_score, max_abs_score)
    label = _xml_escape(tile.display_name)
    polarity_str = (
        "no data" if tile.polarity_score is None
        else f"{tile.polarity_score:+.2f}"
    )
    aria = (
        f"{tile.display_name}: polarity {polarity_str}, "
        f"area weight {tile.area_weight:.0f}"
    )
    title = f"{tile.display_name} — polarity {polarity_str}"
    # Truncate label to fit the tile width (8px per char at 11pt font is a safe rough).
    if dx < 60:
        label = ""
    elif len(label) * 7 > dx:
        label = label[: max(1, int(dx / 7) - 1)] + "…"
    return (
        f'<a href="/model/{tile.model_id}" data-href="/model/{tile.model_id}" '
        f'aria-label="{_xml_escape(aria)}">'
        f'<title>{_xml_escape(title)}</title>'
        f'<rect x="{x:.2f}" y="{y:.2f}" width="{dx:.2f}" height="{dy:.2f}" '
        f'fill="{fill}" stroke="{tile.accent_color}" stroke-width="2" '
        f'rx="2" ry="2"/>'
        + (f'<text x="{x + dx / 2:.2f}" y="{y + dy / 2 + 4:.2f}" '
           f'font-size="13" fill="#0d1117" text-anchor="middle" '
           f'font-weight="600" pointer-events="none">{label}</text>'
           if label else "")
        + "</a>"
    )


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
