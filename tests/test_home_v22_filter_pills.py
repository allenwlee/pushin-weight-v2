"""
iter 16 (U3 Open/Closed lens + drag-scroll + dropdown geometry) — end-to-end
call-chain regression pin.

Pins mockup-canon U3 surface on /:
  - Brand pill: data-lens-pair="open,closed" + data-tier-grid="open"+"closed"
  - Nationalism pill: data-lens-pair="us,cn" + data-tier-grid="us"+"cn"
  - Scoped all/clear (data-dd-scope="visible") on both lens pills
  - .filter-bar-scroller container present (drag-scroll target)
  - pw-filter-pills.js script tag in <head> (the 404'd reference)
"""
from types import SimpleNamespace
from unittest.mock import patch
from datetime import datetime, timezone

import pytest

from tests.v22_support import PostgreSQLV22TestCase, assert_v22_selector_matches


pytestmark = pytest.mark.requires_postgres


FAKE_ROW = {
    "tweet_id": "1", "created_at": "2026-08-09T01:51:00Z",
    "created_at_iso": "2026-08-09T01:51:00Z", "lang_detected": "en",
    "text_en": "Mock en", "text_translated": "Mock en",
    "text_original": "Mock", "text": "Mock",
    "is_translated": True, "like_count": 1200,
    "sentiment_keys": ["positive"], "post_type_keys": ["buzz_releases"],
    "nat_cn": "", "nat_us": "mild_pro",
    "tint_class": "tint-positive", "meta_text": "12m", "ts_abs_text": "(01:51 本地)",
    "avatar_initials": "K", "avatar_color": "#ec4899",
    "engagement_pretty": {"followers": "128.4k", "likes": "1.2k", "retweets": "340", "replies": "89"},
    "brands": [{"nickname": "kimi", "display_name": "Kimi", "display_name_en": "Kimi", "display_name_zh_cn": "Kimi"}],
    "brand_nicknames": ["kimi"],
    "classifications": {"kimi": {"sentiments": [{"key": "positive"}], "post_types": [{"key": "buzz_releases"}], "cn_nationalism": None, "us_nationalism": {"key": "mild_pro"}, "discourse": []}},
    "unsanctioned": False,
    "account": {"handle": "@kimi_moonshot", "role": "official", "role_label": "official", "followers_count": 128400, "followers_pretty": "128.4k"},
}

CHART_PAYLOAD = {"days": [], "series": {}, "colors": {}, "totals": {}, "granularity": "day", "stacked": True, "window_days": 1, "fetched_at": datetime.now(timezone.utc).isoformat(), "applied_filters": {}}


def _patches_active():
    return [
        patch("monitor.views._get_feed_posts", return_value=[SimpleNamespace(tweet_id="1")]),
        patch("monitor.views._enrich_posts_with_classifications", return_value=[]),
        patch("monitor.views._build_brands_context", return_value=[]),
        patch("monitor.views._build_home_chart_payload", return_value=CHART_PAYLOAD),
        patch("monitor.views._multi_top_voices", return_value=[]),
        patch("monitor.views._post_to_wire", return_value=FAKE_ROW),
    ]


class HomeV22FilterPillsTests(PostgreSQLV22TestCase):
    """Pins mockup-canon U3 filter-pill surface on /."""

    def _get_home(self):
        patches = _patches_active()
        for p in patches: p.start()
        try:
            return self.client.get("/?locale=en")
        finally:
            for p in patches: p.stop()

    def test_filter_bar_scroller_present(self):
        r = self._get_home()
        self.assertEqual(r.status_code, 200)
        body = r.content.decode("utf-8")
        assert_v22_selector_matches(
            self, body.count('class="filter-bar-scroller"'),
            selector=".filter-bar-scroller", locale="en", viewport="desktop",
            oracle_source="v22-master L914-1078",
        )

    def test_root_filter_bar_has_no_legacy_control_panel_id(self):
        r = self._get_home()
        self.assertEqual(r.status_code, 200)
        body = r.content.decode("utf-8")
        self.assertNotIn('id="control-panel"', body)

    def test_root_chart_uses_mockup_safe_data_marker_not_legacy_id(self):
        r = self._get_home()
        self.assertEqual(r.status_code, 200)
        body = r.content.decode("utf-8")
        self.assertIn('<section class="home-chart-wrap" data-pw-chart', body)
        self.assertNotIn('id="home-chart"', body)

    def test_brands_pill_has_open_closed_lens(self):
        r = self._get_home()
        body = r.content.decode("utf-8")
        self.assertIn('data-lens-pair="open,closed"', body)
        self.assertIn('data-tier-grid="open"', body)
        self.assertIn('data-tier-grid="closed"', body)

    def test_nationalism_pill_has_us_cn_lens(self):
        r = self._get_home()
        body = r.content.decode("utf-8")
        self.assertIn('data-lens-pair="us,cn"', body)
        self.assertIn('data-tier-grid="us"', body)
        self.assertIn('data-tier-grid="cn"', body)

    def test_scoped_all_clear_buttons(self):
        r = self._get_home()
        body = r.content.decode("utf-8")
        # Mockup has 4 visible-scope actions: Brands all + clear, Nat all + clear
        self.assertGreaterEqual(body.count('data-dd-scope="visible"'), 4,
                                "expected >= 4 scoped all/clear actions on lens pills")

    def test_pw_filter_pills_js_loaded(self):
        r = self._get_home()
        body = r.content.decode("utf-8")
        # The 404'd file — must now be referenced in <script src=...>
        self.assertIn('pw-filter-pills.js', body)
        self.assertRegex(body, r'<script[^>]*src="[^"]*pw-filter-pills\.js[^"]*"')

    def test_filter_bar_aria_label(self):
        r = self._get_home()
        body = r.content.decode("utf-8")
        # The filter-bar nav has aria-label (used by screen readers)
        self.assertIn('aria-label="Filter groups"', body)

    def test_all_seven_filter_pills_present(self):
        """Mockup L914-1078: Brands, Discourse, Role, Lang, Sentiment, Nationalism, Unsanctioned."""
        r = self._get_home()
        body = r.content.decode("utf-8")
        for group in ("brands", "discourse", "role", "lang", "sentiment", "nationalism", "unsanctioned"):
            self.assertIn(f'data-group="{group}"', body,
                          f"filter-pill for {group} missing")
