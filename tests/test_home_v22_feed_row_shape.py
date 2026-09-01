"""
iter 14 (U5 feed row structure) — end-to-end call-chain regression pin.

Per skill M18 + plan-execution-contract rule 7: function-level tests
stay green while production callers break. This test exercises the
production Django view chain (URL routing → view function →
template → HTML response) and asserts that the rendered HTML matches
the v22-master mockup-canon shape.

Bypasses the real DB by patching the data-layer functions that the
view depends on (_get_feed_posts, _enrich_posts_with_classifications,
_build_brands_context, _build_home_chart_payload, _multi_top_voices,
_post_to_wire). The shape we test is the view→template→HTML path
which is where the iter 13 P0 drift lived.
"""
from types import SimpleNamespace
from unittest.mock import patch
from datetime import datetime, timezone

import pytest

from tests.v22_support import PostgreSQLV22TestCase, assert_v22_selector_matches


pytestmark = pytest.mark.requires_postgres


def _fake_row():
    return {
        "tweet_id": "1",
        "created_at": "2026-08-09T01:51:00Z",
        "created_at_iso": "2026-08-09T01:51:00Z",
        "lang_detected": "en",
        "language_display": "en",
        "text_en": "Mock en", "text_zh_cn": "模拟直译", "text_translated": "模拟直译",
        "commentary_en": None, "commentary_zh_cn": "模拟综合",
        "text_original": "Mock", "text": "Mock",
        "is_translated": True, "like_count": 1200,
        "sentiment_keys": ["positive"], "post_type_keys": ["buzz_releases"],
        "nat_cn": "", "nat_us": "mild_pro",
        "tint_class": "tint-positive",
        "meta_text": "12m", "ts_abs_text": "(01:51 本地)",
        "follower_bin": "50k-plus", "followers_count": 128400,
        "followers_label": "128.4k followers",
        "engagement_pretty": {"followers": "128.4k", "likes": "1.2k", "retweets": "340", "replies": "89"},
        "brands": [{"nickname": "kimi", "display_name": "Kimi", "display_name_en": "Kimi", "display_name_zh_cn": "Kimi"}],
        "brand_nicknames": ["kimi"],
        "classifications": {"kimi": {"sentiments": [{"key": "positive"}], "post_types": [{"key": "buzz_releases"}], "cn_nationalism": None, "us_nationalism": {"key": "mild_pro"}, "discourse": []}},
        "signal_inspections_json": '{"sentiment":{"positive":[{"text":"Kimi Sentiment: Positive"}]}}',
        "unsanctioned": False,
        "account": {"handle": "@kimi_moonshot", "display_name": "Moonshot AI", "role": "official", "role_label": "official", "followers_count": 128400, "followers_pretty": "128.4k"},
    }


def _fake_chart_payload():
    computed_at = datetime.now(timezone.utc).isoformat()
    return {
        "days": [],
        "series": {},
        "colors": {},
        "totals": {},
        "granularity": "day",
        "stacked": True,
        "window_days": 1,
        "fetched_at": computed_at,
        "computed_at": computed_at,
        "applied_filters": {},
        "pulse": {
            "window_days": 1,
            "computed_at": computed_at,
            "entries": [],
        },
        "top_voices": {"entries": []},
        "trend_narrative": {},
    }


class HomeV22FeedRowShapeTests(PostgreSQLV22TestCase):
    """Pins mockup-canon 2-column feed row shape on /."""

    def _get_home(self):
        """Return rendered HTML of / with DB-free data path."""
        fake = _fake_row()
        brands = [{**fake["brands"][0], "accent_color": "#ec4899"}]
        patches = {
            "monitor.views._feed_page_wire": ([fake], None, False, {}),
            "monitor.views._get_feed_posts": [SimpleNamespace(tweet_id="1")],
            "monitor.views._enrich_posts_with_classifications": [fake],
            "monitor.views._build_brands_context": brands,
            "monitor.views._build_home_chart_payload": _fake_chart_payload(),
            "monitor.views._multi_top_voices": [],
            "monitor.views._post_to_wire": fake,
        }
        cm = []
        for target, return_value in patches.items():
            if isinstance(return_value, dict):
                p = patch(target, return_value=return_value)
            else:
                p = patch(target, return_value=return_value)
            cm.append(p)
        # Start all patches
        for p in cm:
            p.start()
        try:
            r = self.client.get("/?locale=en")
        finally:
            for p in cm:
                p.stop()
        return r

    def test_home_returns_200(self):
        r = self._get_home()
        self.assertEqual(r.status_code, 200, r.content[:500].decode("utf-8", errors="replace"))

    def test_feed_row_outer_div_renders(self):
        r = self._get_home()
        body = r.content.decode("utf-8")
        assert_v22_selector_matches(
            self, body.count('class="feed-row"'), selector=".feed-row",
            locale="en", viewport="desktop",
            oracle_source="v22-master feed row canon",
        )
        assert_v22_selector_matches(
            self, body.count("data-pw-feed-row"), selector="[data-pw-feed-row]",
            locale="en", viewport="desktop",
            oracle_source="v22-master feed row canon",
        )

    def test_feed_row_has_mockup_canon_2column_grid(self):
        r = self._get_home()
        body = r.content.decode("utf-8")
        # Each row must contain .feed-row-shell > (.feed-main | .feed-signals[4 .sig-rows])
        self.assertIn("feed-row-shell tint-positive", body)
        self.assertIn('class="feed-main"', body)
        self.assertIn('class="feed-signals"', body)
        # 4 sig-rows
        for sig in ("sig-sentiment", "sig-post-type", "sig-nat", "sig-unsanctioned"):
            self.assertIn(f'sig-row {sig}"', body, f"missing .sig-row.{sig}")

    def test_feed_main_has_fixed_follower_column_name_text_engagement(self):
        r = self._get_home()
        body = r.content.decode("utf-8")
        # Follower count owns a fixed lead column. The emoji changes size by
        # bin while the text body remains aligned across rows.
        self.assertRegex(
            body,
            r'<div class="feed-main">\s*<div class="follower-lead follower-bin-50k-plus has-account-metadata"',
        )
        self.assertIn('class="follower-glyph"', body)
        self.assertIn('class="follower-count">128.4k</span>', body)
        self.assertIn('aria-label="128.4k followers"', body)
        self.assertIn(
            'class="follower-magnitude pw-inspection-trigger"', body
        )
        self.assertIn('data-pw-inspection="128.4k followers"', body)
        self.assertNotIn('title="128.4k followers"', body)
        self.assertIn(
            'class="account-role role-official pw-inspection-trigger"', body
        )
        self.assertIn('href="#icon-role-badge"', body)
        self.assertIn('aria-label="official"', body)
        self.assertIn('data-pw-inspection="official"', body)
        self.assertIn('aria-expanded="false"', body)
        self.assertNotIn('title="official"', body)
        self.assertNotIn('<span class="avatar"', body)
        # The name is visible, while the account handle remains the link target.
        self.assertIn('>Moonshot AI</a>', body)
        self.assertIn('href="https://x.com/kimi_moonshot"', body)
        self.assertIn('title="Moonshot AI"', body)
        self.assertNotIn('>@kimi_moonshot</a>', body)
        # head contains account name + meta + ts-abs
        self.assertIn('class="head"', body)
        self.assertIn('class="handle"', body)
        self.assertIn('class="meta"', body)
        self.assertIn('class="ts-abs"', body)
        # text + text-layer-tag
        self.assertIn('class="text"', body)
        self.assertIn('class="post-language-tag">en</span>', body)
        self.assertIn('class="text-layer-tag"', body)
        # Follower count moved out of engagement, leaving interaction stats.
        self.assertIn('class="engagement"', body)
        self.assertNotIn('class="followers"', body)
        for stat in ("likes", "rts", "replies"):
            self.assertIn(f'class="{stat}"', body, f"missing engagement stat .{stat}")
        self.assertIn('class="feed-x-link"', body)
        self.assertIn('href="https://x.com/i/web/status/1"', body)

    def test_signal_data_attributes_present(self):
        r = self._get_home()
        body = r.content.decode("utf-8")
        # The JS signal painter needs these data-* attrs on every row
        for attr in ("data-sentiments=", "data-post-types=", "data-nat-cn=", "data-nat-us=", "data-unsanctioned=", "data-signal-inspections="):
            self.assertIn(attr, body, f"missing {attr} — JS painter won't run")

    def test_feed_row_carries_text_layers_and_guarded_x_post_url(self):
        body = self._get_home().content.decode("utf-8")
        for attr in (
            'data-commentary-zh-cn="模拟综合"', 'data-commentary-en=""',
            'data-literal-cn="模拟直译"', 'data-text-en="Mock en"',
            'data-x-url="https://x.com/i/web/status/1"',
        ):
            self.assertIn(attr, body)

    def test_home_internal_unchanged(self):
        """Regression: /internal/ (Net F legacy) must still render the legacy chrome."""
        fake = _fake_row()
        patches = [
            patch("monitor.views._feed_page_wire", return_value=([], None, False, {})),
            patch("monitor.views._get_feed_posts", return_value=[SimpleNamespace(tweet_id="1")]),
            patch("monitor.views._enrich_posts_with_classifications", return_value=[]),
            patch("monitor.views._build_brands_context", return_value=[]),
            patch("monitor.views._build_home_chart_payload", return_value=_fake_chart_payload()),
            patch("monitor.views._multi_top_voices", return_value=[]),
            patch("monitor.views._post_to_wire", return_value=fake),
        ]
        for p in patches: p.start()
        try:
            r = self.client.get("/internal/")
        finally:
            for p in patches: p.stop()
        self.assertEqual(r.status_code, 200, r.content[:500].decode("utf-8", errors="replace"))
        body = r.content.decode("utf-8")
        # Legacy chrome markers (per Net F)
        self.assertIn('id="control-panel"', body)
        # v22 markers MUST be absent on /internal/
        self.assertNotIn('class="feed-row"', body)  # legacy uses <tr>
        self.assertNotIn("feed-row-shell", body)
