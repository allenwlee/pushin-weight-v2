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
from django.core.management import call_command

from core.models import SentimentKey
from monitor.views import _post_matches_filter
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

COMPUTED_AT = datetime.now(timezone.utc).isoformat()
CHART_PAYLOAD = {
    "days": [],
    "series": {},
    "colors": {},
    "totals": {},
    "granularity": "day",
    "stacked": {},
    "window_days": 1,
    "computed_at": COMPUTED_AT,
    "pulse": {
        "window_days": 1,
        "computed_at": COMPUTED_AT,
        "entries": [{
            "nickname": "qwen",
            "display_name": "Qwen",
            "display_name_en": "Qwen",
            "display_name_zh_cn": "Qwen",
            "accent_color": "#f97316",
            "status": "numeric",
            "direction": "up",
            "delta_percent": 50,
            "delta_magnitude": 50,
        }],
    },
    "top_voices": {"entries": []},
    "trend_narrative": {},
    "applied_filters": {},
}

BRAND_CONTEXT = [
    {
        "nickname": "qwen",
        "display_name": "Qwen",
        "display_name_en": "Qwen",
        "display_name_zh_cn": "Qwen",
        "accent_color": "#f97316",
    },
    {
        "nickname": "anthropic",
        "display_name": "Anthropic",
        "display_name_en": "Anthropic",
        "display_name_zh_cn": "Anthropic",
        "accent_color": "#d97706",
    },
]


def _patches_active():
    return [
        patch("monitor.views._get_feed_posts", return_value=[SimpleNamespace(tweet_id="1")]),
        patch("monitor.views._enrich_posts_with_classifications", return_value=[]),
        patch("monitor.views._build_brands_context", return_value=BRAND_CONTEXT),
        patch("monitor.views._build_home_chart_payload", return_value=CHART_PAYLOAD),
        patch("monitor.views._multi_top_voices", return_value=[]),
        patch("monitor.views._post_to_wire", return_value=FAKE_ROW),
    ]


class HomeV22FilterPillsTests(PostgreSQLV22TestCase):
    """Pins mockup-canon U3 filter-pill surface on /."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        SentimentKey.objects.create(key="positive")
        SentimentKey.objects.create(key="mixed")
        call_command("seed_i18n_labels", verbosity=0)

    def _get_home(self, locale="en"):
        patches = _patches_active()
        for p in patches: p.start()
        try:
            return self.client.get(f"/?locale={locale}")
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

    def test_all_eight_filter_pills_present_in_approved_order(self):
        r = self._get_home()
        body = r.content.decode("utf-8")
        groups = (
            "brands", "sentiment", "post_types", "lang", "role",
            "nationalism", "discourse", "unsanctioned",
        )
        for group in groups:
            self.assertIn(f'data-group="{group}"', body,
                          f"filter-pill for {group} missing")
        positions = [body.index(f'data-group="{group}"') for group in groups]
        self.assertEqual(positions, sorted(positions))

    def test_post_type_and_uncategorized_controls_use_stable_machine_values(self):
        body = self._get_home().content.decode("utf-8")
        post_type = body.split('data-group="post_types"', 1)[1].split(
            'data-group="lang"', 1
        )[0]
        self.assertIn('data-pw-filter-group="post_types"', post_type)
        self.assertIn('value="hands_on_usage"', post_type)
        discourse = body.split('data-group="discourse"', 1)[1].split(
            'data-group="unsanctioned"', 1
        )[0]
        self.assertIn('value="uncategorized"', discourse)

    def test_zh_cn_filter_dropdown_options_are_localized(self):
        body = self._get_home("zh_hans").content.decode("utf-8")
        expected = (
            "正面", "混合", "实际使用", "英语", "未检测", "官方", "其他",
            "温和支持", "荒诞梗", "未分类", "仅显示标记帖子",
        )
        for label in expected:
            self.assertIn(f"<span>{label}</span>", body)

        visible_raw_labels = (
            ">positive</span>", ">hands_on_usage</span>",
            ">official</span>", ">mild_pro</span>",
            ">absurdist_meme</span>", ">uncategorized</span>",
        )
        for raw in visible_raw_labels:
            self.assertNotIn(raw, body)

    def test_fixture_backed_brand_lenses_and_sentiment_grid_are_populated(self):
        body = self._get_home().content.decode("utf-8")
        open_grid = body.split('data-tier-grid="open"', 1)[1].split('data-tier-grid="closed"', 1)[0]
        closed_grid = body.split('data-tier-grid="closed"', 1)[1].split('</div>', 1)[0]
        sentiment_grid = body.split('data-group="sentiment"', 1)[1].split('data-group="nationalism"', 1)[0]
        self.assertIn('value="qwen"', open_grid)
        self.assertIn('value="anthropic"', closed_grid)
        self.assertIn('value="positive"', sentiment_grid)
        self.assertIn('value="mixed"', sentiment_grid)

    def test_pulse_uses_list_items_around_native_toggle_buttons(self):
        body = self._get_home().content.decode("utf-8")
        pulse = body.split('data-pw-pulse ', 1)[1].split('</section>', 1)[0]
        self.assertIn('<li', pulse)
        self.assertIn('data-pw-pulse-entry="qwen"', pulse)
        self.assertIn('aria-pressed="false"', pulse)
        self.assertIn('aria-label="Qwen, up 50 percent"', pulse)
        self.assertNotRegex(pulse, r'<button[^>]+role="listitem"')

    def test_filter_matrix_missing_values_match_only_explicit_buckets(self):
        sample = {
            "brand_nicknames": ["qwen"],
            "discourse": ["genuine_hype"],
            "post_types": ["buzz_releases"],
            "sentiments": ["positive"],
            "role_key": None,
            "lang_detected": "",
            "cn_nationalism": "",
            "us_nationalism": None,
            "unsanctioned": False,
        }
        self.assertTrue(_post_matches_filter(sample, {"role": ["other"]}))
        self.assertTrue(_post_matches_filter(sample, {"lang": ["undetected"]}))
        self.assertTrue(_post_matches_filter(sample, {"cn_nationalism": ["none"]}))
        self.assertTrue(_post_matches_filter(sample, {"us_nationalism": ["none"]}))
        self.assertFalse(_post_matches_filter(sample, {"lang": ["en"]}))
        self.assertFalse(_post_matches_filter(sample, {"sentiment": []}))
        self.assertTrue(_post_matches_filter({**sample, "unsanctioned": True}, {"unsanctioned": "any"}))

        without_discourse = {**sample, "discourse": []}
        self.assertTrue(
            _post_matches_filter(without_discourse, {"discourse": ["uncategorized"]})
        )
        self.assertFalse(
            _post_matches_filter(sample, {"discourse": ["uncategorized"]})
        )
        self.assertTrue(
            _post_matches_filter(
                sample,
                {"discourse": ["uncategorized", "genuine_hype"]},
            )
        )

    def test_filter_matrix_all_partial_empty_or_within_and_across_axes(self):
        sample = {
            "brand_nicknames": ["qwen", "deepseek"],
            "discourse": ["genuine_hype"],
            "post_types": ["buzz_releases"],
            "sentiments": ["mixed"],
            "role_key": "official",
            "lang_detected": "en",
            "cn_nationalism": "pro",
            "us_nationalism": "mild_pro",
            "unsanctioned": False,
        }
        matrix = {
            "brands": ("qwen", "anthropic"),
            "discourse": ("genuine_hype", "sarcasm"),
            "post_types": ("buzz_releases", "hands_on_usage"),
            "sentiment": ("mixed", "positive"),
            "role": ("official", "staff"),
            "lang": ("en", "ja"),
            "cn_nationalism": ("pro", "anti"),
            "us_nationalism": ("mild_pro", "anti"),
        }
        for axis, (matching, nonmatching) in matrix.items():
            with self.subTest(axis=axis, shape="all"):
                self.assertTrue(_post_matches_filter(sample, {axis: "__all__"}))
            with self.subTest(axis=axis, shape="or"):
                self.assertTrue(_post_matches_filter(sample, {axis: [nonmatching, matching]}))
            with self.subTest(axis=axis, shape="partial-miss"):
                self.assertFalse(_post_matches_filter(sample, {axis: [nonmatching]}))
            with self.subTest(axis=axis, shape="empty"):
                self.assertFalse(_post_matches_filter(sample, {axis: []}))

        self.assertTrue(_post_matches_filter(sample, {
            "brands": ["qwen"], "sentiment": ["mixed"], "lang": ["en"],
        }))
        self.assertFalse(_post_matches_filter(sample, {
            "brands": ["qwen"], "sentiment": ["positive"], "lang": ["en"],
        }))
        self.assertTrue(_post_matches_filter(sample, {"unsanctioned": "off"}))
        self.assertFalse(_post_matches_filter(sample, {"unsanctioned": "only"}))
        self.assertTrue(_post_matches_filter(sample, {"unsanctioned": "any"}))
