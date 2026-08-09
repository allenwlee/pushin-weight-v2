"""
iter 15 (U6 locale+window combined nav + label fix) — end-to-end call-chain
regression pin.

Per docs/ideation/mockups/06-tier1-composed.v22-master.html L846-849:
  .topbar > .topbar-title-row { h1.app-name | nav.window-toggle.locale-toggle
                                  (英文 / 中文 / 原文) }
                > .topbar-controls { nav.window-toggle (24小时/7天/30天/365天)
                                    | button.tz-pill }

Pins mockup-canon topbar layout on /. Bypasses the live DB via the same
DB-free mock path used in iter 14.
"""
from types import SimpleNamespace
from unittest.mock import patch
from datetime import datetime, timezone

from django.test import Client, TestCase


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


class HomeV22TopbarLayoutTests(TestCase):
    """Pins mockup-canon topbar layout (U6 locale+window combined nav)."""

    def setUp(self):
        self.client = Client(HTTP_HOST="127.0.0.1")
        from django.contrib.auth import get_user_model
        U = get_user_model()
        try:
            u = U.objects.get(email="allen@quantma.com")
        except U.DoesNotExist:
            self.skipTest("test user allen@quantma.com missing; skipping")
        self.client.force_login(u)

    def _get_home(self):
        patches = _patches_active()
        for p in patches: p.start()
        try:
            return self.client.get("/?locale=en")
        finally:
            for p in patches: p.stop()

    def test_topbar_has_title_row(self):
        """Mockup L846: <header><div class="topbar-title-row">…</div>…</header>"""
        r = self._get_home()
        self.assertEqual(r.status_code, 200)
        body = r.content.decode("utf-8")
        self.assertRegex(body, r'<header class="topbar[^"]*"[^>]*>\s*<div class="topbar-title-row">')

    def test_app_name_lives_in_title_row(self):
        r = self._get_home()
        body = r.content.decode("utf-8")
        # h1.app-name must be inside .topbar-title-row
        self.assertRegex(body, r'<div class="topbar-title-row">.*?<h1 class="app-name".*?</h1>.*?</div>',
                         "app-name must live inside .topbar-title-row per mockup L847")

    def test_locale_toggle_in_title_row(self):
        r = self._get_home()
        body = r.content.decode("utf-8")
        # nav.locale-toggle must be inside .topbar-title-row
        import re
        m = re.search(r'<div class="topbar-title-row">.*?nav class="[^"]*locale-toggle[^"]*".*?</nav>.*?</div>',
                      body, re.DOTALL)
        self.assertIsNotNone(m, "locale-toggle nav must be inside .topbar-title-row (mockup L848)")

    def test_locale_toggle_has_combined_window_toggle_class(self):
        """Mockup L848: <nav class="window-toggle locale-toggle">"""
        r = self._get_home()
        body = r.content.decode("utf-8")
        self.assertIn('class="window-toggle locale-toggle"', body,
                      "locale nav must carry both classes per mockup L848")

    def test_locale_buttons_have_mockup_labels(self):
        """Mockup labels: 英文 / 中文 / 原文 (data-label-zh attrs)."""
        r = self._get_home()
        body = r.content.decode("utf-8")
        for label in ("英文", "中文", "原文"):
            self.assertIn(f'data-label-zh="{label}"', body,
                          f"locale button label {label} missing")

    def test_window_toggle_in_topbar_controls(self):
        """Window toggle stays in .topbar-controls (separate from locale)."""
        r = self._get_home()
        body = r.content.decode("utf-8")
        import re
        # The window-toggle nav (the time-window one) must be inside .topbar-controls
        m = re.search(r'<div class="topbar-controls">.*?<nav class="window-toggle"[^>]*>.*?</nav>.*?</div>',
                      body, re.DOTALL)
        self.assertIsNotNone(m, "window-toggle nav must be in .topbar-controls (mockup L854)")

    def test_locale_toggle_not_in_topbar_controls(self):
        """The locale nav must NOT be in .topbar-controls (it moved to title-row)."""
        r = self._get_home()
        body = r.content.decode("utf-8")
        import re
        # Check that .topbar-controls doesn't contain a nav with locale-toggle class
        m = re.search(r'<div class="topbar-controls">.*?<nav[^>]*class="[^"]*locale-toggle[^"]*".*?</div>',
                      body, re.DOTALL)
        self.assertIsNone(m, "locale-toggle nav leaked back into .topbar-controls")