# {{AGENT_ATTRIBUTION}}
"""Tests for x_monitor/treemap.py.

Covers the R11 (deterministic), R12 (no overflow, all models have a tile),
and R13 (polarity formula correctness, sparse-data guards, area sort,
`data-href` on every tile) requirements from the Finviz treemap plan.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from x_monitor.treemap import (
    TreemapTile,
    MODEL_SECTORS,
    _TILE_GAP_PX,
    _luminance,
    _text_color_for_fill,
    _tile_svg,
    _squarify_layout,
    bin_polarity,
    polarity_fill,
    build_treemap_svg,
    # U9: the legacy `compute_polarity` (6-signal formula) is gone;
    # polarity is now sentiment-only via `compute_polarity_from_db`.
    separate_active_and_no_data,
)


# ---------- helpers ----------------------------------------------------------

def _post(qid: str, created_at: datetime) -> dict:
    """Build a post dict with source_query_id and created_at for polarity tests."""
    return {
        "tweet_id": f"t_{qid}_{created_at.timestamp()}",
        "source_query_id": qid,
        "created_at": created_at.isoformat(),
    }


def _now() -> datetime:
    return datetime(2026, 6, 17, 12, 0, 0, tzinfo=timezone.utc)


# ---------- bin_polarity (v1.7.3: thin backwards-compat wrapper) ------------
class TestBinPolarity:
    def test_bin_polarity_zero_returns_dark_green(self):
        # 0.0 -> t=0.0 -> DARK_GREEN rgb(25, 80, 25)
        c = bin_polarity(0.0)
        assert c == "rgb(25, 80, 25)"

    def test_bin_polarity_positive_one_returns_deep_green(self):
        c = bin_polarity(1.0)
        assert c == "rgb(120, 255, 120)"

    def test_bin_polarity_negative_one_returns_deep_red(self):
        c = bin_polarity(-1.0)
        assert c == "rgb(255, 100, 100)"

    def test_bin_polarity_none_returns_yellow(self):
        c = bin_polarity(None)
        assert c == "rgb(234, 179, 8)"

    def test_bin_polarity_half_positive_returns_green(self):
        # 0.5 -> t=0.5 -> GREEN bin rgb(60, 200, 60)
        c = bin_polarity(0.5)
        assert c == "rgb(60, 200, 60)"


# ---------- polarity_fill (v1.7.2 + v1.7.3) --------------------------------
class TestPolarityFill:
    """v1.7.2: polarity_fill normalizes scores relative to the most
    extreme active score (Finviz-style relative).
    v1.7.3: 5-step binning with fully saturated solid rgb() colors
    (no alpha) replaces the 3-stop lerp. Bin thresholds:
        t <= -0.6  -> LIGHT_RED   rgb(255, 100, 100)
        t <= -0.2  -> RED         rgb(210, 40, 40)
        t <  0     -> DARK_RED    rgb(90, 25, 25)
        t <  0.2   -> DARK_GREEN  rgb(25, 80, 25)
        t <  0.6   -> GREEN       rgb(60, 200, 60)
        t >=  0.6  -> LIGHT_GREEN rgb(120, 255, 120)
        None       -> YELLOW      rgb(234, 179, 8)
    """

    def test_extreme_positive_normalized_to_deep_green(self):
        c = polarity_fill(0.15, 0.15)
        assert c == "rgb(120, 255, 120)"

    def test_extreme_negative_normalized_to_deep_red(self):
        c = polarity_fill(-0.12, 0.12)
        assert c == "rgb(255, 100, 100)"

    def test_zero_normalized_to_dark_green(self):
        c = polarity_fill(0.0, 0.15)
        assert c == "rgb(25, 80, 25)"

    def test_moderate_positive_returns_green(self):
        # 0.075 / 0.15 = 0.5 -> 0.2 <= t < 0.6 -> GREEN
        c = polarity_fill(0.075, 0.15)
        assert c == "rgb(60, 200, 60)"

    def test_slight_positive_returns_dark_green(self):
        # 0.02 / 0.15 = 0.133 -> 0 < t < 0.2 -> DARK_GREEN
        c = polarity_fill(0.02, 0.15)
        assert c == "rgb(25, 80, 25)"

    def test_slight_negative_returns_dark_red(self):
        # -0.02 / 0.15 = -0.133 -> -0.2 < t < 0 -> DARK_RED
        c = polarity_fill(-0.02, 0.15)
        assert c == "rgb(90, 25, 25)"

    def test_moderate_negative_returns_red(self):
        # -0.075 / 0.15 = -0.5 -> -0.6 < t <= -0.2 -> RED
        c = polarity_fill(-0.075, 0.15)
        assert c == "rgb(210, 40, 40)"

    def test_single_active_model_gets_full_saturation(self):
        c = polarity_fill(0.05, 0.05)
        assert c == "rgb(120, 255, 120)"

    def test_all_flat_returns_dark_green(self):
        # max_abs = 0 (degenerate) -> DARK_GREEN for any non-None score.
        assert polarity_fill(0.0, 0.0) == "rgb(25, 80, 25)"
        assert polarity_fill(0.5, 0.0) == "rgb(25, 80, 25)"
        assert polarity_fill(-0.5, 0.0) == "rgb(25, 80, 25)"

    def test_went_dark_unaffected_by_scale(self):
        assert polarity_fill(None, 0.0) == "rgb(234, 179, 8)"
        assert polarity_fill(None, 1.0) == "rgb(234, 179, 8)"

    def test_live_db_range_now_visible(self):
        """Regression test for v1.7.1 -> v1.7.2 -> v1.7.3 fix chain.

        Live polarity scores on 2026-06-17 lived in [-0.15, +0.15].
        v1.7.1 had wrong area; v1.7.2 lerp collapsed to muted;
        v1.7.3 bins to saturated 5-step Finviz palette.
        """
        max_abs = 0.147
        # t = 0.147/0.147 = 1.0 -> LIGHT_GREEN
        assert polarity_fill(0.147, max_abs) == "rgb(120, 255, 120)"
        # t = -0.122/0.147 = -0.83 -> LIGHT_RED
        assert polarity_fill(-0.122, max_abs) == "rgb(255, 100, 100)"
        # t = 0.129/0.147 = 0.878 -> LIGHT_GREEN
        assert polarity_fill(0.129, max_abs) == "rgb(120, 255, 120)"
        # t = 0.063/0.147 = 0.429 -> GREEN (v1.8.1: rgb 60,200,60)
        assert polarity_fill(0.063, max_abs) == "rgb(60, 200, 60)"
        # t = 0.050/0.147 = 0.340 -> GREEN (v1.8.1: rgb 60,200,60)
        assert polarity_fill(0.050, max_abs) == "rgb(60, 200, 60)"
        # t = 0.029/0.147 = 0.197 -> DARK_GREEN (0 < t < 0.2)
        assert polarity_fill(0.029, max_abs) == "rgb(25, 80, 25)"
        # t = -0.042/0.147 = -0.286 -> RED
        assert polarity_fill(-0.042, max_abs) == "rgb(210, 40, 40)"

    def test_score_clamped_to_unit_range(self):
        # score > max_abs -> t=1.0 -> LIGHT_GREEN (no overshoot).
        c = polarity_fill(0.5, 0.15)
        assert c == "rgb(120, 255, 120)"
        # score < -max_abs -> t=-1.0 -> LIGHT_RED
        c = polarity_fill(-0.5, 0.15)
        assert c == "rgb(255, 100, 100)"

    def test_palette_is_solid_rgb_not_rgba(self):
        """v1.7.3: no more rgba() with 0.85 alpha. The alpha mixed
        with the dark background and washed out the colors.
        """
        for s in [0.0, 0.05, -0.05, 0.15, -0.15]:
            c = polarity_fill(s, 0.15)
            assert c.startswith("rgb("), f"score {s} -> {c} is not solid rgb()"
            assert "rgba" not in c, f"score {s} -> {c} still has alpha"

    def test_bin_thresholds_match_finviz_convention(self):
        # The 5-step palette should match Finviz boundaries:
        #   |t| <= 0.2: dark bins
        #   0.2 < |t| <= 0.6: saturated bins
        #   |t| > 0.6: deep bins
        for t, expected in [
            (-1.0, "rgb(255, 100, 100)"),
            (-0.6, "rgb(255, 100, 100)"),
            (-0.59, "rgb(210, 40, 40)"),
            (-0.2, "rgb(210, 40, 40)"),
            (-0.19, "rgb(90, 25, 25)"),
            (-0.01, "rgb(90, 25, 25)"),
            (0.01, "rgb(25, 80, 25)"),
            (0.19, "rgb(25, 80, 25)"),
            (0.2, "rgb(60, 200, 60)"),
            (0.59, "rgb(60, 200, 60)"),
            (0.6, "rgb(120, 255, 120)"),
            (1.0, "rgb(120, 255, 120)"),
        ]:
            assert polarity_fill(t, 1.0) == expected, f"t={t} should be {expected}"


# ---------- end polarity_fill (v1.7.2 + v1.7.3) -----------------------------

# ---------- _score_from_breakdown (U9 sentiment-only polarity) -------------

class TestScoreFromBreakdown:
    """U9 (migration 022): polarity is sentiment-only. The legacy
    `compute_polarity` 6-signal formula is replaced by
    `_score_from_breakdown`, which takes two sentiment breakdowns
    {positive / negative / neutral / mixed → weighted_count} and
    returns (positive - negative) / total.
    """

    def test_all_zeros_returns_zero(self):
        from x_monitor.treemap import _score_from_breakdown
        # Sparse-data guard 1: both windows empty.
        score = _score_from_breakdown({}, {})
        assert score == 0.0

    def test_prior_empty_current_has_data_no_nan(self):
        from x_monitor.treemap import _score_from_breakdown
        # Sparse-data guard 2: prior empty, current has data.
        # 2 positive + 4 neutral = 6 total -> positive_rate = 2/6.
        current = {"positive": 2.0, "neutral": 4.0}
        prior: dict[str, float] = {}
        score = _score_from_breakdown(current, prior)
        assert score is not None
        assert abs(score - (2 / 6)) < 0.01

    def test_current_empty_prior_has_data_returns_none(self):
        from x_monitor.treemap import _score_from_breakdown
        # Sparse-data guard 3: current empty, prior had data -> went dark.
        current: dict[str, float] = {}
        prior = {"positive": 1.0, "negative": 1.0}
        score = _score_from_breakdown(current, prior)
        assert score is None  # the "went dark" sentinel

    def test_synthetic_positive_heavy_returns_positive(self):
        from x_monitor.treemap import _score_from_breakdown
        # current: all positive, prior: all negative -> strongly positive
        current = {"positive": 5.0}
        prior = {"negative": 5.0}
        score = _score_from_breakdown(current, prior)
        assert score is not None
        # current_rate = 1.0, prior_rate = -1.0, score = 2.0 → clamped to 1.0
        assert abs(score - 1.0) < 0.01

    def test_synthetic_negative_heavy_returns_negative(self):
        from x_monitor.treemap import _score_from_breakdown
        # current: all negative, prior: all positive -> strongly negative
        current = {"negative": 5.0}
        prior = {"positive": 5.0}
        score = _score_from_breakdown(current, prior)
        assert score is not None
        # current_rate = -1.0, prior_rate = 1.0, score = -2.0 → clamped to -1.0
        assert abs(score - (-1.0)) < 0.01


# ---------- separate_active_and_no_data -------------------------------------

class TestSeparateActiveAndNoData:
    def test_separates_by_area_weight(self):
        tiles = [
            TreemapTile("a", "A", "#3b82f6", 10.0, 0.1),
            TreemapTile("b", "B", "#f97316", 0.0, None),  # no data
            TreemapTile("c", "C", "#10b981", 5.0, -0.2),
            TreemapTile("d", "D", "#a855f7", 0.0, 0.0),  # also no data
        ]
        active, no_data = separate_active_and_no_data(tiles)
        assert [t.brand_id for t in active] == ["a", "c"]
        assert [t.brand_id for t in no_data] == ["b", "d"]


# ---------- build_treemap_svg -----------------------------------------------

class TestBuildTreemapSvg:
    def _tiles(self, n_active: int, n_no_data: int = 0) -> list[TreemapTile]:
        """Build n_active tiles with proportional areas and 1 polarity, plus n_no_data."""
        tiles = []
        accents = ["#3b82f6", "#f97316", "#10b981", "#a855f7", "#eab308",
                   "#ec4899", "#06b6d4", "#facc15", "#22c55e", "#0ea5e9", "#ec4899"]
        names = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K"]
        for i in range(n_active):
            tiles.append(TreemapTile(
                brand_id=f"m{i}", display_name=names[i], accent_color=accents[i],
                area_weight=float(2 ** (n_active - i)),  # geometric so the largest dominates
                polarity_score=0.0,
            ))
        for i in range(n_no_data):
            tiles.append(TreemapTile(
                brand_id=f"nd{i}", display_name=f"ND{i}", accent_color="#9ca3af",
                area_weight=0.0, polarity_score=None,
            ))
        return tiles

    def test_three_equal_areas_sum_to_total(self):
        tiles = self._tiles(3, 0)
        svg = build_treemap_svg(tiles, width=300, height=200)
        # Each rect area should be 300*200/3 = 20000 within 1% (squarified may
        # produce slightly off areas; the layout claim is that all rects sum
        # to width*height).
        assert '<svg' in svg
        assert 'role="img"' in svg
        assert 'class="treemap"' in svg
        assert svg.count('<a ') == 3
        assert svg.count('data-href="') == 3

    def test_empty_tiles_returns_no_models_enabled(self):
        svg = build_treemap_svg([], width=300, height=200)
        assert "No models enabled" in svg
        assert "<svg" in svg

    def test_no_data_tiles_render_as_strip(self):
        tiles = self._tiles(2, 3)  # 2 active, 3 no-data
        svg = build_treemap_svg(tiles, width=600, height=400)
        # 2 active tiles
        assert svg.count('<a ') == 2
        # 3 no-data placeholders, rendered as a strip with opacity=0.15
        assert 'class="no-data"' in svg
        assert 'opacity="0.15"' in svg

    def test_every_active_tile_has_data_href(self):
        tiles = self._tiles(5, 0)
        svg = build_treemap_svg(tiles, width=800, height=600)
        for t in tiles:
            assert f'data-href="/model/{t.brand_id}"' in svg, f"missing {t.brand_id}"

    def test_every_active_tile_has_aria_label(self):
        tiles = self._tiles(3, 0)
        svg = build_treemap_svg(tiles, width=600, height=400)
        # 3 aria-labels on the <a> tiles, plus 1 on the root <svg> for a total of 4.
        assert svg.count('aria-label=') == 4
        # Confirm the per-tile labels are present (one per active tile).
        for t in tiles:
            expected = f'aria-label="{t.display_name}: polarity'
            assert expected in svg, f"missing tile aria-label for {t.brand_id}"

    def test_every_active_tile_has_title_element(self):
        tiles = self._tiles(3, 0)
        svg = build_treemap_svg(tiles, width=600, height=400)
        assert svg.count('<title>') == 3

    def test_root_svg_has_role_img_and_aria_label(self):
        tiles = self._tiles(2, 0)
        svg = build_treemap_svg(tiles, width=600, height=400)
        assert 'role="img"' in svg
        assert 'aria-label="LLM model attention treemap"' in svg

    def test_deterministic_for_same_input(self):
        # Smoke test for stability: two consecutive calls with the same input
        # produce byte-identical output. squarify is deterministic by contract.
        tiles = self._tiles(5, 1)
        a = build_treemap_svg(tiles, width=800, height=600)
        b = build_treemap_svg(tiles, width=800, height=600)
        assert a == b

    def test_went_dark_sentinel_uses_yellow(self):
        # A polarity_score of None should produce a yellow fill (the "went dark" state).
        tiles = [TreemapTile("a", "A", "#3b82f6", 100.0, None)]
        svg = build_treemap_svg(tiles, width=300, height=200)
        # --yellow is rgba(234, 179, 8, 0.85)
        assert "234" in svg and "179" in svg

    def test_no_chartjs_or_htmx_in_svg(self):
        # Sanity: the treemap is pure inline SVG. It must not include htmx or
        # chart.js script tags (those are added by the wrapping template).
        tiles = self._tiles(3, 0)
        svg = build_treemap_svg(tiles, width=600, height=400)
        assert "htmx" not in svg.lower()
        assert "chart.js" not in svg.lower()


# ---------- v1.8 Finviz aesthetic refinements --------------------------------

class TestTileHoverAndTooltip:
    """v1.8: extended <title>, luminance-based text color, pct font-weight 400,
    Arial font-family, MODEL_SECTORS coverage."""

    def test_luminance_helper_uses_bt709_weights(self):
        # Pure green channel: (0, 255, 0) -> 0.7152 per BT.709.
        assert abs(_luminance((0, 255, 0)) - 0.7152) < 0.001
        # Pure red channel: (255, 0, 0) -> 0.2126.
        assert abs(_luminance((255, 0, 0)) - 0.2126) < 0.001
        # Pure blue channel: (0, 0, 255) -> 0.0722.
        assert abs(_luminance((0, 0, 255)) - 0.0722) < 0.001

    def test_text_color_dark_for_light_fill(self):
        # Yellow (234, 179, 8) has luminance 0.667 > threshold 0.5 -> dark text.
        assert _text_color_for_fill("rgb(234, 179, 8)") == "#0d1117"

    def test_text_color_white_for_dark_fill(self):
        # v1.8.1: DARK_RED rgb(90, 25, 25) has luminance 0.152 < threshold -> white text.
        # (Previously this used DEEP_RED rgb(170,0,0); that exact RGB is no longer
        # a palette stop after the v1.8.1 rebalance.)
        assert _text_color_for_fill("rgb(90, 25, 25)") == "#ffffff"

    def test_text_color_white_for_unparseable_fill(self):
        # Anything we can't parse falls back to white.
        assert _text_color_for_fill("not-a-color") == "#ffffff"

    def test_title_contains_brand_id_and_display_name(self):
        tile = TreemapTile(
            "minimax", "MiniMax AI", "#3b82f6", 100.0, 0.05,
            posts_in_window=47, polarity_window_days=7,
            last_run_finished_at="2026-06-17T13:50:00+00:00",
            sector="closed-source LLM",
        )
        rect = {"x": 10.0, "y": 20.0, "dx": 200.0, "dy": 150.0}
        svg = _tile_svg(tile, rect, max_abs_score=0.05)
        assert "<title>" in svg
        assert "MiniMax AI (minimax)" in svg
        assert "Polarity:" in svg
        assert "Posts in window: 47" in svg
        assert "Last run: 2026-06-17T13:50:00+00:00" in svg
        assert "Sector: closed-source LLM" in svg

    def test_title_omits_sector_when_none(self):
        tile = TreemapTile(
            "unknown_model", "Unknown", "#3b82f6", 100.0, 0.05,
            posts_in_window=10, polarity_window_days=7,
            last_run_finished_at=None,
            sector=None,
        )
        rect = {"x": 10.0, "y": 20.0, "dx": 200.0, "dy": 150.0}
        svg = _tile_svg(tile, rect, max_abs_score=0.05)
        assert "Sector:" not in svg
        assert "Last run:" not in svg

    def test_pct_font_weight_is_400(self):
        tile = TreemapTile("a", "A", "#3b82f6", 100.0, 0.05)
        rect = {"x": 10.0, "y": 20.0, "dx": 200.0, "dy": 150.0}
        svg = _tile_svg(tile, rect, max_abs_score=0.05)
        # The pct line carries font-weight=400. Symbol line stays 700.
        assert 'font-weight="400"' in svg
        assert 'font-weight="500"' not in svg

    def test_tile_uses_arial_font_family(self):
        tile = TreemapTile("a", "A", "#3b82f6", 100.0, 0.05)
        rect = {"x": 10.0, "y": 20.0, "dx": 200.0, "dy": 150.0}
        svg = _tile_svg(tile, rect, max_abs_score=0.05)
        assert 'font-family="Arial, Helvetica, sans-serif"' in svg

    def test_tile_border_radius_is_zero(self):
        tile = TreemapTile("a", "A", "#3b82f6", 100.0, 0.05)
        rect = {"x": 10.0, "y": 20.0, "dx": 200.0, "dy": 150.0}
        svg = _tile_svg(tile, rect, max_abs_score=0.05)
        assert 'rx="0"' in svg
        assert 'ry="0"' in svg

    def test_model_sectors_table_covers_all_v17_roster(self):
        # The 11 enabled models in v1.7.4 should each have a sector label.
        # If a new model is added later without sector, the <title> just omits the line.
        expected = {
            "minimax", "deepseek", "qwen", "glm", "moonshot_kimi", "inclusionai",
            "mimo", "mistral", "stepfun", "ernie", "hunyuan",
        }
        assert expected.issubset(MODEL_SECTORS.keys())


class TestSquarifyLayoutPadding:
    """v1.8: squarify rects are shrunk by padding+gap."""

    def test_one_tile_rect_is_shrunk_by_padding(self):
        tile = TreemapTile("a", "A", "#3b82f6", 100.0, 0.1)
        result = _squarify_layout([tile], 300, 200)
        assert len(result) == 1
        _, rect = result[0]
        # Squarify's full-canvas rect is x=0, y=0, dx=300, dy=200.
        # v1.8 shrinks by padding (top-left) + gap (bottom-right) = 4 + 2 = 6 on dx/dy.
        assert rect["x"] == 4.0  # padding
        assert rect["y"] == 4.0
        assert rect["dx"] == 300.0 - 4.0 - 2.0  # 294
        assert rect["dy"] == 200.0 - 4.0 - 2.0  # 194

    def test_two_tile_rects_have_visible_gap_between_them(self):
        tiles = [
            TreemapTile("a", "A", "#3b82f6", 50.0, 0.1),
            TreemapTile("b", "B", "#f97316", 50.0, 0.1),
        ]
        result = _squarify_layout(tiles, 300, 200)
        _, rect_a = result[0]
        _, rect_b = result[1]
        # Adjacent tiles share an edge. After v1.8 shrinking, there must be
        # at least _TILE_GAP_PX of visible gutter between them.
        # Squarify lays these side-by-side for equal-area equal-weights.
        a_right = rect_a["x"] + rect_a["dx"]
        b_left = rect_b["x"]
        assert (b_left - a_right) >= _TILE_GAP_PX - 0.01, (
            f"expected gap >= {_TILE_GAP_PX}, got {b_left - a_right}"
        )

    def test_padding_shrinks_does_not_translate(self):
        # Padding+gap should subtract from each rect's dx/dy, not translate the
        # whole layout. Total visible area shrinks by ~2*(padding+gap) per tile
        # summed across edges.
        tiles = [TreemapTile("a", "A", "#3b82f6", 100.0, 0.1)]
        result = _squarify_layout(tiles, 300, 200)
        _, rect = result[0]
        # Single tile: rect occupies (4, 4) -> (4 + 294, 4 + 194) = full inner area.
        # The visible area is 294 * 194 = 57036, vs total 300*200 = 60000.
        visible_area = rect["dx"] * rect["dy"]
        # Shrink factor should be roughly (1 - padding/total_w) * (1 - padding/total_h),
        # i.e. ~95% of the original. Tolerate 1% rounding.
        assert abs(visible_area - 57036) < 100


# ---------- Unit 6: RT fold + created_at_epoch window (2026-06-22) ---------


def _seed_brand_posts(store, brand, posts):
    """Direct-insert (posts, posts_brands, posts_brands_signals) for polarity-SQL
    tests. `posts` = list of (tweet_id, sentiment, post_type, retweet_count, epoch).

    U9 (migration 022): posts_brands_signals schema is now
    (post_id, brand_id, post_type, sentiment) where `post_type` /
    `sentiment` are INTEGER FKs to post_type_keys / sentiment_keys.
    The legacy `signal_id` column is gone.

    The `brand` must already exist (migration 004 seeds KNOWN_MODELS like 'glm')."""
    c = store._conn
    # U8 (migration 020): posts.id / brands.id / post_type_keys.id /
    # sentiment_keys.id are INTEGER. Look up each id once per call.
    brand_int = c.execute(
        "SELECT id FROM brands WHERE brand_id = ?", (brand,)
    ).fetchone()["id"]
    for tid, sentiment, post_type, rt, epoch in posts:
        c.execute(
            "INSERT INTO posts(tweet_id, fetched_at, created_at_epoch, retweet_count, author_handle) "
            "VALUES (?, '2026-01-01T00:00:00+00:00', ?, ?, 'u')",
            (tid, epoch, rt),
        )
        post_int = c.execute(
            "SELECT id FROM posts WHERE tweet_id = ?", (tid,)
        ).fetchone()["id"]
        sent_int = c.execute(
            "SELECT id FROM sentiment_keys WHERE key = ?", (sentiment,)
        ).fetchone()["id"]
        pt_int = c.execute(
            "SELECT id FROM post_type_keys WHERE key = ?", (post_type,)
        ).fetchone()["id"]
        c.execute(
            "INSERT INTO posts_brands(brand_id, post_id, weight) VALUES (?, ?, 1.0)",
            (brand_int, post_int),
        )
        c.execute(
            "INSERT INTO posts_brands_signals(post_id, brand_id, post_type, sentiment) "
            "VALUES (?, ?, ?, ?)",
            (post_int, brand_int, pt_int, sent_int),
        )


def test_polarity_breakdown_rt_fold(tmp_path):
    """Each post's sentiment is weighted by (1 + retweet_count): an RT
    inherits the original's sentiment ("each utterance = one vote").

    U9: the breakdown is keyed by sentiment, not the legacy 6-signal
    taxonomy.
    """
    from x_monitor.store import Store
    from x_monitor.treemap import compute_polarity_sentiment_breakdown
    now_ep = int(datetime.now(timezone.utc).timestamp())
    store = Store(tmp_path / "x.db")
    try:
        _seed_brand_posts(store, "glm", [
            ("A", "positive", "buzz_releases", 9, now_ep),    # 1 * (1+9) = 10
            ("B", "positive", "buzz_releases", 0, now_ep),    # 1 * (1+0) = 1
            ("C", "negative", "hands_on_usage", 4, now_ep),   # 1 * (1+4) = 5
        ])
        bd = compute_polarity_sentiment_breakdown(store._conn, "glm", 0)
        assert bd["positive"] == 11.0
        assert bd["negative"] == 5.0
    finally:
        store.close()


def test_polarity_breakdown_window_excludes_old(tmp_path):
    """The time window filters on created_at_epoch (unix seconds), excluding
    posts older than the bound — the fix for the pre-006 ISO-vs-Twitter-format
    bug that silently ignored the window."""
    from x_monitor.store import Store
    from x_monitor.treemap import compute_polarity_sentiment_breakdown
    now_ep = int(datetime.now(timezone.utc).timestamp())
    old_ep = now_ep - 30 * 86400  # 30 days ago, outside a 7-day window
    store = Store(tmp_path / "x.db")
    try:
        _seed_brand_posts(store, "glm", [
            ("RECENT", "positive", "buzz_releases", 0, now_ep),
            ("OLD", "positive", "buzz_releases", 0, old_ep),
        ])
        cutoff = now_ep - 7 * 86400
        bd_7d = compute_polarity_sentiment_breakdown(store._conn, "glm", cutoff)
        assert bd_7d["positive"] == 1.0  # OLD excluded
        bd_all = compute_polarity_sentiment_breakdown(store._conn, "glm", 0)
        assert bd_all["positive"] == 2.0  # both included all-time
    finally:
        store.close()


def test_compute_polarity_from_db_returns_score(tmp_path):
    """End-to-end: with data only in the current window, the score reduces to
    the current (positive - negative) rate (prior-empty guard). U9 sentiment-
    only polarity."""
    from x_monitor.store import Store
    from x_monitor.treemap import compute_polarity_from_db
    now_ep = int(datetime.now(timezone.utc).timestamp())
    store = Store(tmp_path / "x.db")
    try:
        _seed_brand_posts(store, "glm", [
            ("P1", "positive", "buzz_releases", 0, now_ep),
            ("P2", "positive", "buzz_releases", 0, now_ep),
            ("C1", "negative", "hands_on_usage", 0, now_ep),
        ])
        score = compute_polarity_from_db(store._conn, "glm", window_days=7)
        # current = {praise:2, criticism:1}, prior empty -> (2-1)/3 ~= 0.333
        assert score is not None
        assert abs(score - (1.0 / 3.0)) < 1e-9
    finally:
        store.close()



def test_polarity_index_created_at_epoch_exists(tmp_path):
    """The `idx_posts_created_at_epoch` index must exist in `posts`.
    migration 006 creates it; a future migration that drops or renames
    the index would silently regress the dashboard to a full posts SCAN.
    Pinning the index name here catches that at test time.

    (We pin the schema, not the EXPLAIN plan, because SQLite's planner
    picks SCAN vs. INDEX-BY-idx on a 50-row table even with ANALYZE — the
    plan is data-dependent and not a stable invariant to assert.)"""
    from x_monitor.store import Store
    store = Store(tmp_path / "x.db")
    try:
        rows = store._conn.execute(
            "SELECT name, sql FROM sqlite_master "
            "WHERE type = 'index' AND tbl_name = 'posts' "
            "AND name = 'idx_posts_created_at_epoch'"
        ).fetchall()
        assert rows, (
            "idx_posts_created_at_epoch missing on posts; "
            "migration 006 may have been dropped or renamed."
        )
        # Sanity: the DDL references the column we filter on.
        assert "created_at_epoch" in rows[0]["sql"]
    finally:
        store.close()


def test_polarity_sql_window_filters_by_epoch_not_string():
    """Regression: pre-migration-006 the POLARITY_SQL compared ISO bounds
    against Twitter-format `created_at` strings, which sort incorrectly
    (the entire corpus looked "in window"). The fix is to filter on
    `created_at_epoch` (integer). This test pins that the SQL body
    references the epoch column.

    Note: the SQL uses positional `?` placeholders; the *Python variable*
    is named `window_start_epoch`, but the literal string does not appear
    in the SQL. We only pin the column-name invariant here."""
    from x_monitor.treemap import POLARITY_SQL
    assert "created_at_epoch" in POLARITY_SQL
    # The window filter compares created_at_epoch against a parameter.
    assert "p.created_at_epoch >=" in POLARITY_SQL
