"""
iter 16 (U3 Open/Closed lens + drag-scroll + dropdown geometry) — end-to-end
call-chain regression pin.

Pins mockup-canon U3 surface on /:
    - Brand pill: data-lens-pair="open,closed" + data-tier-grid="open"+"closed"
    - Current U18A Audience Topics and Geopolitical controls are present.
  - .filter-bar-scroller container present (drag-scroll target)
  - pw-filter-pills.js script tag in <head> (the 404'd reference)
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.core.management import call_command

from core.models import Post, PostUntrackedBrandPromotion, SentimentKey
from monitor.views import (
    _display_role_key,
    _display_role_label,
    _filter_home_posts_queryset,
    _normalize_home_filters,
    _post_matches_filter,
)
from tests.v22_support import PostgreSQLV22TestCase, assert_v22_selector_matches

pytestmark = pytest.mark.requires_postgres


def test_display_role_badge_uses_deterministic_precedence_and_locale() -> None:
    assert _display_role_key(["community", "official", "staff"]) == "official"
    assert _display_role_key(["community", "staff"]) == "staff"
    assert _display_role_key(["other"]) is None
    labels = {
        ("role", "official", "en"): "Official",
        ("role", "official", "zh-cn"): "官方",
    }
    assert _display_role_label("official", "en", labels) == "Official"
    assert _display_role_label("official", "zh_cn", labels) == "官方"


FAKE_ROW = {
    "tweet_id": "1", "created_at": "2026-08-09T01:51:00Z",
    "created_at_iso": "2026-08-09T01:51:00Z", "lang_detected": "en",
    "text_en": "Mock en", "text_translated": "Mock en",
    "text_original": "Mock", "text": "Mock",
    "is_translated": True, "like_count": 1200,
    "sentiment_keys": ["positive"], "post_type_keys": ["releases_updates"],
    "nat_cn": "", "nat_us": "mild_pro",
    "tint_class": "tint-positive", "meta_text": "12m", "ts_abs_text": "(01:51 本地)",
    "avatar_initials": "K", "avatar_color": "#ec4899",
    "engagement_pretty": {"followers": "128.4k", "likes": "1.2k", "retweets": "340", "replies": "89"},
    "brands": [{"nickname": "kimi", "display_name": "Kimi", "display_name_en": "Kimi", "display_name_zh_cn": "Kimi"}],
    "brand_nicknames": ["kimi"],
    "classifications": {"kimi": {"sentiments": [{"key": "positive"}], "post_types": [{"key": "releases_updates"}], "product_labels": [], "cn_nationalism": None, "us_nationalism": {"key": "mild_pro"}}},
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
        "nickname": "claude",
        "display_name": "Claude",
        "display_name_en": "Claude",
        "display_name_zh_cn": "Claude",
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
        SentimentKey.objects.get_or_create(key="positive")
        SentimentKey.objects.get_or_create(key="mixed")
        call_command("seed_i18n_labels", verbosity=0)

    def _get_home(self, locale="en"):
        patches = _patches_active()
        for item in patches:
            item.start()
        try:
            return self.client.get(f"/?locale={locale}")
        finally:
            for item in patches:
                item.stop()

    def test_filter_bar_scroller_present(self):
        r = self._get_home()
        self.assertEqual(r.status_code, 200)
        body = r.content.decode("utf-8")
        assert_v22_selector_matches(
            self, body.count('class="filter-bar-scroller"'),
            selector=".filter-bar-scroller", locale="en", viewport="desktop",
            oracle_source="v22-master L914-1078",
        )

    def test_filter_json_cannot_break_out_of_body_attribute(self):
        patches = _patches_active()
        for item in patches:
            item.start()
        try:
            response = self.client.get(
                "/",
                {"filters": '{"brands":["x\' onmouseover=\'alert(1)"]}'},
                follow=True,
            )
        finally:
            for item in patches:
                item.stop()

        body = response.content.decode("utf-8")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("' onmouseover='alert(1)", body)
        self.assertIn("x&#x27; onmouseover=&#x27;alert(1)", body)

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

    def test_shadow_only_geopolitical_pill_is_not_rendered(self):
        r = self._get_home()
        body = r.content.decode("utf-8")
        self.assertNotIn('data-group="geopolitical_modes"', body)
        self.assertNotIn('data-pw-filter-group="china_national_stance"', body)
        self.assertNotIn('data-pw-filter-group="us_national_stance"', body)

    def test_scoped_all_clear_buttons(self):
        r = self._get_home()
        body = r.content.decode("utf-8")
        self.assertGreaterEqual(body.count('data-dd-scope="visible"'), 2,
                                "expected scoped all/clear actions on brand lens")

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

    def test_stage1_filter_pills_replace_discourse_in_preserved_order(self):
        r = self._get_home()
        body = r.content.decode("utf-8")
        groups = (
            "brands", "sentiment", "post_types", "lang", "role",
            "audience_topics", "product_labels",
        )
        for group in groups:
            self.assertIn(f'data-group="{group}"', body,
                          f"filter-pill for {group} missing")
        positions = [body.index(f'data-group="{group}"') for group in groups]
        self.assertEqual(positions, sorted(positions))
        self.assertNotIn('data-group="discourse"', body)
        self.assertNotIn('data-group="nationalism"', body)

    def test_u18a_controls_expose_current_axes_and_promotion_accessibility(self):
        body = self._get_home().content.decode("utf-8")
        audience = body.split('data-group="audience_topics"', 1)[1].split(
            'data-group="product_labels"', 1
        )[0]
        for key in ("local_inference", "model_distillation", "api_developer_surface"):
            self.assertIn(f'value="{key}"', audience)
        for key in (
            "cost_performance", "evals_benchmarks", "openness_license", "agents_tools",
        ):
            self.assertNotIn(f'value="{key}"', audience)
        self.assertNotIn('data-group="geopolitical_modes"', body)
        self.assertNotIn('data-group="untracked_brand_promotions"', body)

    def test_u18a_positive_filters_do_not_match_pre_v4_unavailable_rows(self):
        pre_v4 = {
            "brand_nicknames": ["qwen"],
            "classifications_by_brand": {
                "qwen": {
                    "audience_topics": [],
                    "audience_topics_status": "unavailable",
                    "geopolitical_modes": [],
                    "geopolitical_modes_status": "unavailable",
                    "china_national_stance": None,
                    "china_national_stance_status": "unavailable",
                    "us_national_stance": None,
                    "us_national_stance_status": "unavailable",
                },
            },
        }
        self.assertFalse(_post_matches_filter(
            pre_v4, {"audience_topics": ["local_inference"]}
        ))

    def test_u18a_available_filters_match_current_brand_assignments(self):
        current = {
            "brand_nicknames": ["qwen"],
            "classifications_by_brand": {
                "qwen": {
                    "audience_topics": ["local_inference"],
                    "audience_topics_status": "available",
                    "geopolitical_modes": ["framework"],
                    "geopolitical_modes_status": "available",
                    "china_national_stance": "pro",
                    "china_national_stance_status": "available",
                    "us_national_stance": "anti",
                    "us_national_stance_status": "available",
                },
            },
        }
        self.assertTrue(_post_matches_filter(
            current, {"audience_topics": ["local_inference"]}
        ))

    def test_all_stage1_types_and_product_labels_use_stable_machine_values(self):
        body = self._get_home().content.decode("utf-8")
        post_type = body.split('data-group="post_types"', 1)[1].split(
            'data-group="lang"', 1
        )[0]
        self.assertIn('data-pw-filter-group="post_types"', post_type)
        for key in (
            "releases_updates", "hands_on_usage", "results_analysis",
            "questions_requests", "advertising_marketing", "events", "opportunities",
            "job_listings", "personnel_changes",
            "opinions_reactions", "research_explanations", "business_finance",
            "other",
        ):
            self.assertIn(f'value="{key}"', post_type)
        self.assertNotIn('value="news_reporting"', post_type)
        products = body.split('data-group="product_labels"', 1)[1].split(
            '</nav>', 1
        )[0]
        for key in ("bug", "complaint", "testimonial", "ideas_requests"):
            self.assertIn(f'value="{key}"', products)
        self.assertNotIn('value="investigate_claim"', products)
        self.assertNotIn("misinformation", products)

    def test_zh_cn_filter_dropdown_options_are_localized(self):
        body = self._get_home("zh_hans").content.decode("utf-8")
        expected = (
            "正面", "混合", "实际使用", "英语", "未检测", "官方", "其他",
            "缺陷",
        )
        for label in expected:
            self.assertIn(f">{label}</span>", body)

        visible_raw_labels = (
            ">positive</span>", ">hands_on_usage</span>",
            ">official</span>",
            ">bug</span>",
        )
        for raw in visible_raw_labels:
            self.assertNotIn(raw, body)

    def test_fixture_backed_brand_lenses_and_sentiment_grid_are_populated(self):
        body = self._get_home().content.decode("utf-8")
        open_grid = body.split('data-tier-grid="open"', 1)[1].split('data-tier-grid="closed"', 1)[0]
        closed_grid = body.split('data-tier-grid="closed"', 1)[1].split('</div>', 1)[0]
        sentiment_grid = body.split('data-group="sentiment"', 1)[1].split('data-group="post_types"', 1)[0]
        self.assertIn('value="qwen"', open_grid)
        self.assertIn('value="claude"', closed_grid)
        self.assertIn('value="positive"', sentiment_grid)
        self.assertIn('value="mixed"', sentiment_grid)

    def test_feed_semantic_icons_precede_filter_option_labels(self):
        body = self._get_home().content.decode("utf-8")
        expected = (
            ("sentiment", "positive"),
            ("sentiment", "negative"),
            ("post_types", "hands_on_usage"),
            ("post_types", "advertising_marketing"),
            ("role", "official"),
            ("role", "staff"),
            ("role", "community"),
        )
        for group, value in expected:
            section = body.split(f'data-group="{group}"', 1)[1].split(
                'class="filter-pill"', 1
            )[0]
            option = section.split(f'value="{value}"', 1)[1].split('</label>', 1)[0]
            self.assertIn("data-pw-semantic-icon", option)
            self.assertIn(f'data-pw-semantic-family="{group}"', option)
            self.assertIn(f'data-pw-semantic-key="{value}"', option)
        self.assertNotIn("data-pw-semantic-icon", body.split('data-group="lang"', 1)[1].split(
            'class="filter-pill"', 1
        )[0])

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
            "product_labels": [],
            "post_types": ["releases_updates"],
            "sentiments": ["positive"],
            "role_key": None,
            "lang_detected": "",
            "cn_nationalism": "",
            "us_nationalism": None,
            "unsanctioned": False,
        }
        self.assertTrue(_post_matches_filter(sample, {"role": ["other"]}))
        self.assertTrue(_post_matches_filter(sample, {"lang": ["undetected"]}))
        self.assertFalse(_post_matches_filter(sample, {"cn_nationalism": ["none"]}))
        self.assertFalse(_post_matches_filter(sample, {"us_nationalism": ["none"]}))
        self.assertFalse(_post_matches_filter(sample, {"lang": ["en"]}))
        self.assertFalse(_post_matches_filter(sample, {"sentiment": []}))
        self.assertTrue(_post_matches_filter({**sample, "unsanctioned": True}, {"unsanctioned": "any"}))

        self.assertFalse(_post_matches_filter(sample, {"product_labels": ["bug"]}))
        self.assertTrue(_post_matches_filter(sample, {"product_labels": "__all__"}))

    def test_product_label_filter_keeps_brand_provenance(self):
        sample = {
            "brand_nicknames": ["brand_a", "brand_b"],
            "classifications_by_brand": {
                "brand_a": {
                    "product_labels": [], "post_types": [], "sentiments": [],
                    "cn_nationalism": None, "us_nationalism": None,
                },
                "brand_b": {
                    "product_labels": ["bug"], "post_types": ["other"],
                    "sentiments": ["positive"],
                    "cn_nationalism": "none", "us_nationalism": "none",
                },
            },
            "product_labels": ["bug"],
            "post_types": ["other"],
            "sentiments": ["neutral"],
            "role_keys": [],
            "lang_detected": "en",
            "cn_nationalism": None,
            "us_nationalism": None,
            "unsanctioned": False,
        }
        self.assertFalse(_post_matches_filter(
            sample, {"brands": ["brand_a"], "product_labels": ["bug"]}
        ))
        self.assertTrue(_post_matches_filter(
            sample, {"brands": ["brand_b"], "product_labels": ["bug"]}
        ))
        sparse = {
            **sample,
            "classifications_by_brand": {
                "brand_b": sample["classifications_by_brand"]["brand_b"]
            },
        }
        self.assertFalse(_post_matches_filter(
            sparse, {"brands": ["brand_a"], "product_labels": ["bug"]}
        ))
        for axis, selected in (
            ("post_types", ["other"]),
            ("sentiment", ["positive"]),
            ("cn_nationalism", ["none"]),
            ("us_nationalism", ["none"]),
        ):
            with self.subTest(axis=axis):
                self.assertFalse(_post_matches_filter(
                    sample, {"brands": ["brand_a"], axis: selected}
                ))
                self.assertTrue(_post_matches_filter(
                    sample, {"brands": ["brand_b"], axis: selected}
                ))

    def test_filter_matrix_all_partial_empty_or_within_and_across_axes(self):
        sample = {
            "brand_nicknames": ["qwen", "deepseek"],
            "product_labels": ["bug"],
            "post_types": ["releases_updates"],
            "sentiments": ["mixed"],
            "role_key": "official",
            "lang_detected": "en",
            "cn_nationalism": "pro",
            "us_nationalism": "mild_pro",
            "unsanctioned": False,
        }
        matrix = {
            "brands": ("qwen", "anthropic"),
            "product_labels": ("bug", "complaint"),
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

    def test_shadow_only_promotion_family_is_absent_and_legacy_is_separate(self):
        body = self._get_home().content.decode("utf-8")
        self.assertNotIn('data-group="untracked_brand_promotions"', body)
        normalized = _normalize_home_filters({
            "untracked_brand_promotions": ["general"]
        })
        self.assertEqual(normalized["untracked_brand_promotions"], "any")
        self.assertEqual(
            normalized["_unavailable_filters"], ["untracked_brand_promotions"]
        )
        legacy = {"untracked_brand_promotions": [], "legacy_unsanctioned": True}
        self.assertTrue(_post_matches_filter(legacy, {"unsanctioned": "only"}))

    def test_invalid_current_values_are_removed_and_reported(self):
        normalized = _normalize_home_filters({
            "audience_topics": ["retired_topic", "local_inference"],
            "untracked_brand_promotions": ["bogus", "general"],
        })
        self.assertEqual(normalized["audience_topics"], ["local_inference"])
        self.assertEqual(normalized["untracked_brand_promotions"], "any")
        self.assertEqual(
            normalized["_unavailable_filters"],
            ["audience_topics", "untracked_brand_promotions"],
        )
        retired_only = _normalize_home_filters({"audience_topics": ["retired_topic"]})
        self.assertIsNone(retired_only["audience_topics"])

    def test_valid_shadow_only_values_are_removed_and_reported(self):
        normalized = _normalize_home_filters({
            "post_types": ["news_reporting"],
            "product_labels": ["investigate_claim"],
            "geopolitical_modes": ["framework"],
            "china_national_stance": ["pro"],
            "us_national_stance": ["anti"],
            "untracked_brand_promotions": ["general"],
        })
        for key in (
            "post_types", "product_labels", "geopolitical_modes",
            "china_national_stance", "us_national_stance",
        ):
            self.assertIsNone(normalized[key])
        self.assertEqual(normalized["untracked_brand_promotions"], "any")
        self.assertEqual(
            normalized["_unavailable_filters"],
            [
                "china_national_stance", "geopolitical_modes", "post_types",
                "product_labels", "untracked_brand_promotions",
                "us_national_stance",
            ],
        )

    def test_shadow_only_promotion_row_does_not_hide_post_by_default(self):
        now = datetime.now(timezone.utc)
        post = Post.objects.create(
            tweet_id="shadow-promotion-visible",
            text="A visible post carrying retained shadow evidence.",
            created_at=now,
        )
        PostUntrackedBrandPromotion.objects.create(
            post=post,
            promotion_keys=["general"],
            evidence={"source": "shadow-test"},
            contract_version="classifier-contract/v4",
            taxonomy_version="taxonomy/v4",
            prompt_version="classifier-prompts/v4",
            model="test-model",
            provider_role="content",
        )
        normalized = _normalize_home_filters({})
        self.assertEqual(normalized["untracked_brand_promotions"], "any")
        visible = _filter_home_posts_queryset(
            1,
            normalized,
            now=now + timedelta(seconds=1),
        )
        self.assertTrue(visible.filter(tweet_id=post.tweet_id).exists())
