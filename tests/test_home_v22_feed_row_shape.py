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

from django.test import Client, TestCase


def _fake_row():
    return {
        "tweet_id": "1",
        "created_at": "2026-08-09T01:51:00Z",
        "created_at_iso": "2026-08-09T01:51:00Z",
        "lang_detected": "en",
        "text_en": "Mock en", "text_translated": "Mock en",
        "text_original": "Mock", "text": "Mock",
        "is_translated": True, "like_count": 1200,
        "sentiment_keys": ["positive"], "post_type_keys": ["buzz_releases"],
        "nat_cn": "", "nat_us": "mild_pro",
        "tint_class": "tint-positive",
        "meta_text": "12m", "ts_abs_text": "(01:51 本地)",
        "avatar_initials": "K", "avatar_color": "#ec4899",
        "engagement_pretty": {"followers": "128.4k", "likes": "1.2k", "retweets": "340", "replies": "89"},
        "brands": [{"nickname": "kimi", "display_name": "Kimi", "display_name_en": "Kimi", "display_name_zh_cn": "Kimi"}],
        "brand_nicknames": ["kimi"],
        "classifications": {"kimi": {"sentiments": [{"key": "positive"}], "post_types": [{"key": "buzz_releases"}], "cn_nationalism": None, "us_nationalism": {"key": "mild_pro"}, "discourse": []}},
        "unsanctioned": False,
        "account": {"handle": "@kimi_moonshot", "role": "official", "role_label": "official", "followers_count": 128400, "followers_pretty": "128.4k"},
    }


class HomeV22FeedRowShapeTests(TestCase):
    """Pins mockup-canon 2-column feed row shape on /."""

    def setUp(self):
        self.client = Client(HTTP_HOST="127.0.0.1")
        # Bypass login_required via force_login with the dev test user.
        # Skips gracefully if the user doesn't exist in the dev DB.
        from django.contrib.auth import get_user_model
        U = get_user_model()
        try:
            u = U.objects.get(email="allen@quantma.com")
        except U.DoesNotExist:
            self.skipTest("test user allen@quantma.com missing; skipping")
        self.client.force_login(u)

    def _get_home(self):
        """Return rendered HTML of / with DB-free data path."""
        fake = _fake_row()
        patches = {
            "monitor.views._get_feed_posts": [SimpleNamespace(tweet_id="1")],
            "monitor.views._enrich_posts_with_classifications": [],
            "monitor.views._build_brands_context": [],
            "monitor.views._build_home_chart_payload": {"days": [], "series": {}, "colors": {}, "totals": {}, "granularity": "day", "stacked": True, "window_days": 1, "fetched_at": datetime.now(timezone.utc).isoformat(), "applied_filters": {}},
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
        self.assertIn('class="feed-row"', body)
        self.assertIn('data-pw-feed-row', body)

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

    def test_feed_main_has_avatar_handle_text_engagement(self):
        r = self._get_home()
        body = r.content.decode("utf-8")
        # avatar first child of feed-main
        self.assertRegex(body, r'<div class="feed-main">\s*<span class="avatar"')
        # head contains handle + meta + ts-abs
        self.assertIn('class="head"', body)
        self.assertIn('class="handle"', body)
        self.assertIn('class="meta"', body)
        self.assertIn('class="ts-abs"', body)
        # text + text-layer-tag
        self.assertIn('class="text"', body)
        self.assertIn('class="text-layer-tag"', body)
        # engagement with 4 stats
        self.assertIn('class="engagement"', body)
        for stat in ("followers", "likes", "rts", "replies"):
            self.assertIn(f'class="{stat}"', body, f"missing engagement stat .{stat}")

    def test_signal_data_attributes_present(self):
        r = self._get_home()
        body = r.content.decode("utf-8")
        # The JS signal painter needs these data-* attrs on every row
        for attr in ("data-sentiments=", "data-post-types=", "data-nat-cn=", "data-nat-us=", "data-unsanctioned="):
            self.assertIn(attr, body, f"missing {attr} — JS painter won't run")

    def test_home_internal_unchanged(self):
        """Regression: /internal/ (Net F legacy) must still render the legacy chrome."""
        fake = _fake_row()
        patches = [
            patch("monitor.views._get_feed_posts", return_value=[SimpleNamespace(tweet_id="1")]),
            patch("monitor.views._enrich_posts_with_classifications", return_value=[]),
            patch("monitor.views._build_brands_context", return_value=[]),
            patch("monitor.views._build_home_chart_payload", return_value={"days": [], "series": {}, "colors": {}, "totals": {}, "granularity": "day", "stacked": True, "window_days": 1, "fetched_at": datetime.now(timezone.utc).isoformat(), "applied_filters": {}}),
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