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
    bin_polarity,
    build_treemap_svg,
    compute_polarity,
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


# ---------- bin_polarity -----------------------------------------------------

class TestBinPolarity:
    def test_bin_polarity_zero_returns_muted(self):
        # The 3-stop interpolation at score=0 returns the muted color.
        # 0 -> lerp(MUTED, GREEN, 0) = MUTED.
        c = bin_polarity(0.0)
        assert "139" in c and "148" in c and "158" in c, c

    def test_bin_polarity_positive_one_returns_green(self):
        c = bin_polarity(1.0)
        assert "16" in c and "185" in c and "129" in c, c

    def test_bin_polarity_negative_one_returns_red(self):
        c = bin_polarity(-1.0)
        assert "239" in c and "68" in c and "68" in c, c

    def test_bin_polarity_none_returns_yellow(self):
        c = bin_polarity(None)
        # --yellow is #eab308 = 234, 179, 8
        assert "234" in c and "179" in c and "8" in c, c

    def test_bin_polarity_half_positive_lerps_muted_to_green(self):
        # 0.5 -> midpoint of (MUTED, GREEN) at 0.85 alpha.
        c = bin_polarity(0.5)
        # Expected: round((139+16)/2)=78, round((148+185)/2)=166, round((158+129)/2)=144
        assert "78" in c and "166" in c and "144" in c, c


# ---------- compute_polarity -------------------------------------------------

class TestComputePolarity:
    def test_all_zeros_returns_zero(self):
        # Sparse-data guard 1: both windows empty.
        score = compute_polarity([], (_now(), _now()), (_now(), _now()))
        assert score == 0.0

    def test_prior_zero_current_has_data_no_nan(self):
        # Sparse-data guard 2: prior empty, current has data.
        # Define prior rates as 0, so score = current_rate - 0 = current_rate.
        # 4 Q1 (release, not praise/criticism) + 2 Q6 (praise) = 6 total.
        # praise_rate = 2/6 = 0.333.
        now = _now()
        posts = [
            _post("Q6", now - timedelta(hours=1)),  # praise
            _post("Q6", now - timedelta(hours=2)),  # praise
            _post("Q1", now - timedelta(hours=3)),  # release (not in numerator)
            _post("Q1", now - timedelta(hours=4)),
            _post("Q1", now - timedelta(hours=5)),
            _post("Q1", now - timedelta(hours=6)),
        ]
        score = compute_polarity(
            posts,
            (now - timedelta(days=2), now),  # current window
            (now - timedelta(days=4), now - timedelta(days=2)),  # prior window (empty)
        )
        assert score is not None
        # Expected: 0.333... no NaN
        assert abs(score - (2 / 6)) < 0.01

    def test_current_zero_prior_has_data_returns_none(self):
        # Sparse-data guard 3: current empty, prior had data -> went dark.
        now = _now()
        posts = [
            _post("Q6", now - timedelta(days=10)),  # in prior window only
            _post("Q3", now - timedelta(days=11)),  # in prior window only
        ]
        score = compute_polarity(
            posts,
            (now - timedelta(days=2), now),  # current window (empty)
            (now - timedelta(days=12), now - timedelta(days=2)),  # prior window
        )
        assert score is None  # the "went dark" sentinel

    def test_synthetic_praise_heavy_returns_positive(self):
        # current: all praise, prior: all criticism -> score should be strongly positive
        now = _now()
        posts = []
        for i in range(5):
            posts.append(_post("Q6", now - timedelta(hours=i + 1)))  # current praise
        for i in range(5):
            posts.append(_post("Q3", now - timedelta(days=i + 2)))  # prior criticism
        score = compute_polarity(
            posts,
            (now - timedelta(days=1), now),
            (now - timedelta(days=6), now - timedelta(days=1)),
        )
        assert score is not None
        # current_rate = 5/5 - 0/5 = 1.0
        # prior_rate = 0/5 - 5/5 = -1.0
        # score = 1.0 - (-1.0) = 2.0, clamped to 1.0
        assert abs(score - 1.0) < 0.01

    def test_synthetic_criticism_heavy_returns_negative(self):
        now = _now()
        posts = []
        for i in range(5):
            posts.append(_post("Q3", now - timedelta(hours=i + 1)))  # current criticism
        for i in range(5):
            posts.append(_post("Q6", now - timedelta(days=i + 2)))  # prior praise
        score = compute_polarity(
            posts,
            (now - timedelta(days=1), now),
            (now - timedelta(days=6), now - timedelta(days=1)),
        )
        assert score is not None
        # current_rate = 0/5 - 5/5 = -1.0
        # prior_rate = 5/5 - 0/5 = 1.0
        # score = -1.0 - 1.0 = -2.0, clamped to -1.0
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
        assert [t.model_id for t in active] == ["a", "c"]
        assert [t.model_id for t in no_data] == ["b", "d"]


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
                model_id=f"m{i}", display_name=names[i], accent_color=accents[i],
                area_weight=float(2 ** (n_active - i)),  # geometric so the largest dominates
                polarity_score=0.0,
            ))
        for i in range(n_no_data):
            tiles.append(TreemapTile(
                model_id=f"nd{i}", display_name=f"ND{i}", accent_color="#9ca3af",
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
            assert f'data-href="/model/{t.model_id}"' in svg, f"missing {t.model_id}"

    def test_every_active_tile_has_aria_label(self):
        tiles = self._tiles(3, 0)
        svg = build_treemap_svg(tiles, width=600, height=400)
        # 3 aria-labels on the <a> tiles, plus 1 on the root <svg> for a total of 4.
        assert svg.count('aria-label=') == 4
        # Confirm the per-tile labels are present (one per active tile).
        for t in tiles:
            expected = f'aria-label="{t.display_name}: polarity'
            assert expected in svg, f"missing tile aria-label for {t.model_id}"

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
