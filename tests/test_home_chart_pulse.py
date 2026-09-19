"""PostgreSQL contract tests for the shared home chart and pulse payload."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser
from unittest.mock import patch

import pytest
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext

from core.classification_contract import (
    CONTRACT_VERSION,
    PROMPT_VERSION,
    TAXONOMY_VERSION,
)
from core.models import (
    Account,
    Brand,
    BrandAccount,
    DiscourseKey,
    NationalismKey,
    Post,
    PostBrand,
    PostBrandClassificationState,
    PostBrandDiscourse,
    PostBrandProductLabel,
    PostBrandSignal,
    PostTypeKey,
    ProductLabelKey,
    Role,
    SentimentKey,
)
from monitor.views import (
    _HOME_CHART_CACHE,
    _HOME_PULSE_CACHE,
    _HOME_TOP_VOICES_CACHE,
    _build_home_chart_payload,
    _build_home_pulse_payload,
    _clear_home_pulse_cache,
    _enrich_posts_with_classifications,
    _post_matches_filter,
    _round_pulse_percent,
    _serialize_feed_row,
)
from tests.v22_support import PostgreSQLV22TestCase

pytestmark = pytest.mark.requires_postgres

ANCHOR = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)


class _ChartFragmentParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[str] = []
        self.canvas_attrs: list[dict[str, str | None]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append(tag)
        if tag == "canvas":
            self.canvas_attrs.append(dict(attrs))


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
)
class HomeChartPulseTests(PostgreSQLV22TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        Brand.objects.filter(
            nickname__in=("anthropic", "google_deepmind")
        ).delete()
        specs = {
            "up": (6, 4),
            "down": (2, 4),
            "flat": (4, 4),
            "new": (3, 0),
            "absent": (0, 0),
        }
        for nickname in specs:
            Brand.objects.create(
                nickname=nickname,
                display_name=nickname.title(),
                display_name_en=nickname.title(),
                display_name_zh_cn=f"中{nickname}",
                accent_color="#123456",
            )

        serial = 0
        for nickname, (current, prior) in specs.items():
            brand = Brand.objects.get(nickname=nickname)
            for index in range(current):
                created_at = ANCHOR - timedelta(hours=24) if nickname == "up" and index == 0 else ANCHOR - timedelta(hours=1, minutes=index)
                post = Post.objects.create(tweet_id=f"pulse-{serial}", created_at=created_at)
                PostBrand.objects.create(post=post, brand=brand)
                serial += 1
            for index in range(prior):
                created_at = ANCHOR - timedelta(hours=48) if nickname == "up" and index == 0 else ANCHOR - timedelta(hours=25, minutes=index)
                post = Post.objects.create(tweet_id=f"pulse-{serial}", created_at=created_at)
                PostBrand.objects.create(post=post, brand=brand)
                serial += 1

        up = Brand.objects.get(nickname="up")
        for suffix, created_at in (("at-anchor", ANCHOR), ("future", ANCHOR + timedelta(seconds=1))):
            post = Post.objects.create(tweet_id=f"pulse-{suffix}", created_at=created_at)
            PostBrand.objects.create(post=post, brand=up)

    def setUp(self):
        super().setUp()
        _clear_home_pulse_cache()

    def test_ae11_exact_equal_window_projection_and_single_query_cache(self):
        with self.assertNumQueries(1):
            pulse = _build_home_pulse_payload(1, now=ANCHOR)

        by_nickname = {entry["nickname"]: entry for entry in pulse["entries"]}
        self.assertEqual(list(by_nickname), sorted(("up", "down", "flat", "new", "absent")))
        self.assertEqual(
            (by_nickname["up"]["current_count"], by_nickname["up"]["prior_count"], by_nickname["up"]["delta_percent"], by_nickname["up"]["direction"]),
            (6, 4, 50, "up"),
        )
        self.assertEqual(
            (by_nickname["down"]["current_count"], by_nickname["down"]["prior_count"], by_nickname["down"]["delta_percent"], by_nickname["down"]["direction"]),
            (2, 4, -50, "down"),
        )
        self.assertEqual(
            (by_nickname["flat"]["current_count"], by_nickname["flat"]["prior_count"], by_nickname["flat"]["delta_percent"], by_nickname["flat"]["direction"]),
            (4, 4, 0, "flat"),
        )
        self.assertEqual(
            (by_nickname["new"]["current_count"], by_nickname["new"]["prior_count"], by_nickname["new"]["delta_percent"], by_nickname["new"]["direction"]),
            (3, 0, None, None),
        )
        self.assertEqual(by_nickname["new"]["status"], "new")
        self.assertEqual(
            (by_nickname["absent"]["current_count"], by_nickname["absent"]["prior_count"], by_nickname["absent"]["delta_percent"], by_nickname["absent"]["direction"]),
            (0, 0, 0, "flat"),
        )
        self.assertEqual(pulse["window_days"], 1)
        self.assertEqual(pulse["computed_at"], ANCHOR.isoformat())

        with self.assertNumQueries(0):
            self.assertEqual(_build_home_pulse_payload(1, now=ANCHOR), pulse)

    def test_canonical_twenty_model_query_is_date_bounded_and_single_query(self):
        with CaptureQueriesContext(connection) as queries:
            pulse = _build_home_pulse_payload(1, now=ANCHOR)

        self.assertEqual(len(queries), 1)
        self.assertEqual(
            [entry["nickname"] for entry in pulse["entries"]],
            ["absent", "down", "flat", "new", "up"],
        )
        self.assertEqual(len(pulse["entries"]), 5)
        sql = queries.captured_queries[0]["sql"].upper()
        self.assertGreaterEqual(sql.count("SELECT COUNT"), 2)
        self.assertNotIn("FILTER (WHERE", sql)

    def test_half_away_from_zero_rounding_and_rounded_zero_direction(self):
        self.assertEqual(_round_pulse_percent(9, 8), 13)
        self.assertEqual(_round_pulse_percent(7, 8), -13)
        self.assertEqual(_round_pulse_percent(200, 201), 0)

    def test_chart_uses_set_based_shared_predicate_and_atomic_pulse_anchor(self):
        PostTypeKey.objects.get_or_create(key="releases_updates")
        SentimentKey.objects.get_or_create(key="positive")
        DiscourseKey.objects.get_or_create(key="genuine_hype")
        ProductLabelKey.objects.get_or_create(key="bug")
        NationalismKey.objects.get_or_create(key="pro")
        NationalismKey.objects.get_or_create(key="mild_pro")
        account = Account.objects.create(author_id="chart-account", handle="chart-account")
        brand = Brand.objects.get(nickname="up")
        post = Post.objects.create(
            tweet_id="chart-filter-match",
            author=account,
            created_at=ANCHOR - timedelta(minutes=5),
            lang_detected="en",
        )
        PostBrand.objects.create(post=post, brand=brand)
        PostBrandSignal.objects.create(
            post=post,
            brand=brand,
            post_type_id="releases_updates",
            sentiment_id="positive",
        )
        PostBrandDiscourse.objects.create(
            post=post,
            brand=brand,
            discourse_id="genuine_hype",
            act_id=1,
            china_nationalism_id="pro",
            us_nationalism_id="mild_pro",
        )
        PostBrandProductLabel.objects.create(
            post=post,
            brand=brand,
            product_label_id="bug",
        )
        PostBrandClassificationState.objects.create(
            post=post,
            brand=brand,
            contract_version=CONTRACT_VERSION,
            taxonomy_version=TAXONOMY_VERSION,
            prompt_version=PROMPT_VERSION,
            model="stage1-chart-fixture",
            source_language="en",
            input_context_fingerprint="1" * 64,
            outcome=PostBrandClassificationState.Outcome.CLASSIFIED,
            sentiment_id="positive",
            china_nationalism_id="pro",
            us_nationalism_id="mild_pro",
        )

        active = {
            "brands": ["up"],
            "product_labels": ["bug"],
            "post_types": ["releases_updates"],
            "sentiment": ["positive"],
            "lang": ["en"],
            "cn_nationalism": ["pro"],
            "us_nationalism": ["mild_pro"],
            "unsanctioned": "off",
        }
        # Pulse, brand inventory, chart aggregate, and the co-timestamped
        # Top Voices projection. A disabled narrative performs no DB read.
        with self.assertNumQueries(4):
            payload = _build_home_chart_payload(1, active, now=ANCHOR)
        self.assertEqual(payload["totals"], {"up": 1})
        self.assertEqual(payload["computed_at"], payload["pulse"]["computed_at"])
        self.assertEqual(payload["window_days"], payload["pulse"]["window_days"])

        empty = _build_home_chart_payload(
            1,
            {**active, "product_labels": []},
            now=ANCHOR + timedelta(seconds=1),
        )
        self.assertEqual(empty["totals"], {"up": 0})
        self.assertEqual(empty["pulse"], payload["pulse"], "ordinary filters must not change market-wide pulse")
        self.assertEqual(empty["computed_at"], empty["pulse"]["computed_at"])

    def test_default_chart_uses_one_bounded_post_join(self):
        """The common chart path must not rescan posts through a subquery."""
        with CaptureQueriesContext(connection) as captured:
            payload = _build_home_chart_payload(
                30,
                {"unsanctioned": "off"},
                now=ANCHOR,
            )

        chart_queries = [
            query["sql"]
            for query in captured.captured_queries
            if 'FROM "posts_brands"' in query["sql"] and ' AS "day"' in query["sql"]
        ]
        self.assertEqual(len(chart_queries), 1)
        self.assertNotIn(" IN (SELECT ", chart_queries[0].upper())
        self.assertNotIn("ORDER BY", chart_queries[0].upper())
        self.assertEqual(payload["window_days"], 30)

    @patch("monitor.views.django_timezone.now", return_value=ANCHOR)
    def test_complete_chart_projection_cache_is_canonical_and_isolated(self, _now):
        first_filters = {"brands": ["up", "down"], "unsanctioned": "off"}
        equivalent_filters = {"brands": ["down", "up"], "unsanctioned": "off"}

        with CaptureQueriesContext(connection) as cold_queries:
            cold = _build_home_chart_payload(30, first_filters)
        with CaptureQueriesContext(connection) as warm_queries:
            warm = _build_home_chart_payload(30, equivalent_filters)

        self.assertGreater(len(cold_queries), 0)
        self.assertEqual(len(warm_queries), 0)
        self.assertEqual(warm, cold)
        self.assertIsNot(warm, cold)

        warm["totals"]["up"] = -1
        cached_again = _build_home_chart_payload(30, first_filters)
        self.assertNotEqual(cached_again["totals"]["up"], -1)

        cache_key = next(iter(_HOME_CHART_CACHE))
        cached_at, cached_payload = _HOME_CHART_CACHE[cache_key]
        _HOME_CHART_CACHE[cache_key] = (cached_at - 61, cached_payload)
        with CaptureQueriesContext(connection) as expired_queries:
            _build_home_chart_payload(30, first_filters)
        self.assertGreater(len(expired_queries), 0)

        with CaptureQueriesContext(connection) as locale_miss:
            _build_home_chart_payload(30, first_filters, locale="zh_cn")
        with CaptureQueriesContext(connection) as filter_miss:
            _build_home_chart_payload(30, {"brands": ["up"], "unsanctioned": "off"})
        self.assertGreater(len(locale_miss), 0)
        self.assertGreater(len(filter_miss), 0)

    def test_complete_chart_projection_cache_has_a_fixed_entry_cap(self):
        with patch("monitor.views._HOME_CHART_CACHE_MAX_ENTRIES", 2):
            for brand in ("up", "down", "flat"):
                _build_home_chart_payload(30, {"brands": [brand]})

        self.assertEqual(len(_HOME_CHART_CACHE), 2)

    @patch("monitor.views.django_timezone.now", return_value=ANCHOR)
    def test_complete_chart_cache_does_not_extend_component_cache_age(self, _now):
        _build_home_chart_payload(30, {"brands": ["up"]})
        pulse_cached_at = _HOME_PULSE_CACHE[30][0]
        voices_cached_at = _HOME_TOP_VOICES_CACHE[(30, 3)][0]
        _HOME_CHART_CACHE.clear()

        _build_home_chart_payload(30, {"brands": ["down"]})
        chart_cached_at = next(iter(_HOME_CHART_CACHE.values()))[0]

        self.assertEqual(
            chart_cached_at,
            min(pulse_cached_at, voices_cached_at),
            "the complete cache must not give older components a fresh TTL",
        )

    def test_posts_date_index_covers_chart_and_top_voice_keys(self):
        index = next(
            (
                candidate
                for candidate in Post._meta.indexes
                if candidate.name == "idx_posts_created_cover"
            ),
            None,
        )

        self.assertIsNotNone(index)
        self.assertEqual(index.fields, ["created_at"])
        self.assertEqual(index.include, ("tweet_id", "author"))

    def test_in_memory_empty_axes_match_set_based_zero_semantics(self):
        sample = {
            "brand_nicknames": ["up"],
            "product_labels": ["bug"],
            "post_types": ["releases_updates"],
            "sentiments": ["positive"],
            "role_key": "official",
            "lang_detected": "en",
            "cn_nationalism": "pro",
            "us_nationalism": "mild_pro",
            "unsanctioned": False,
        }
        for axis in ("brands", "product_labels", "post_types", "sentiment", "role", "lang", "cn_nationalism", "us_nationalism"):
            with self.subTest(axis=axis):
                self.assertFalse(_post_matches_filter(sample, {axis: []}))

    def test_empty_product_labels_remain_visible_by_default_but_not_when_filtered(self):
        PostTypeKey.objects.get_or_create(key="other")
        ProductLabelKey.objects.get_or_create(key="bug")
        SentimentKey.objects.get_or_create(key="neutral")
        brand = Brand.objects.create(
            nickname="product-bucket",
            display_name="Product Bucket",
            display_name_en="Product Bucket",
            display_name_zh_cn="产品桶",
            accent_color="#123456",
        )
        missing = Post.objects.create(
            tweet_id="product-empty",
            created_at=ANCHOR - timedelta(minutes=10),
        )
        classified = Post.objects.create(
            tweet_id="product-labeled",
            created_at=ANCHOR - timedelta(minutes=5),
        )
        PostBrand.objects.create(post=missing, brand=brand)
        PostBrand.objects.create(post=classified, brand=brand)
        for index, post in enumerate((missing, classified)):
            PostBrandSignal.objects.create(
                post=post,
                brand=brand,
                post_type_id="other",
                sentiment_id="neutral",
            )
            PostBrandClassificationState.objects.create(
                post=post,
                brand=brand,
                contract_version=CONTRACT_VERSION,
                taxonomy_version=TAXONOMY_VERSION,
                prompt_version=PROMPT_VERSION,
                model="stage1-chart-fixture",
                source_language="en",
                input_context_fingerprint=f"{index + 1:064x}",
                outcome=PostBrandClassificationState.Outcome.CLASSIFIED,
                sentiment_id="neutral",
            )
        PostBrandProductLabel.objects.create(
            post=classified,
            brand=brand,
            product_label_id="bug",
        )

        missing_row = {"brand_nicknames": [brand.nickname], "product_labels": []}
        classified_row = {
            "brand_nicknames": [brand.nickname],
            "product_labels": ["bug"],
        }
        only_bug = {
            "brands": [brand.nickname],
            "product_labels": ["bug"],
            "unsanctioned": "off",
        }

        self.assertFalse(_post_matches_filter(missing_row, only_bug))
        self.assertTrue(_post_matches_filter(classified_row, only_bug))
        self.assertEqual(
            _build_home_chart_payload(1, only_bug, now=ANCHOR)["totals"][brand.nickname],
            1,
        )
        self.assertEqual(
            _build_home_chart_payload(
                1,
                {"brands": [brand.nickname], "unsanctioned": "off"},
                now=ANCHOR + timedelta(seconds=1),
            )["totals"][brand.nickname],
            2,
        )

    def test_type_and_product_edges_require_exact_current_classified_state(self):
        PostTypeKey.objects.get_or_create(key="other")
        ProductLabelKey.objects.get_or_create(key="bug")
        SentimentKey.objects.get_or_create(key="neutral")
        brand = Brand.objects.create(nickname="stage1-edge-gate")
        posts = {}
        for index, state_kind in enumerate(
            ("historical", "context_missing", "stale", "classified")
        ):
            post = Post.objects.create(
                tweet_id=f"stage1-edge-{state_kind}",
                created_at=ANCHOR - timedelta(minutes=index + 1),
            )
            posts[state_kind] = post
            PostBrand.objects.create(post=post, brand=brand)
            PostBrandSignal.objects.create(
                post=post,
                brand=brand,
                post_type_id="other",
                sentiment_id="neutral",
            )
            PostBrandProductLabel.objects.create(
                post=post,
                brand=brand,
                product_label_id="bug",
            )
            if state_kind == "historical":
                continue
            PostBrandClassificationState.objects.create(
                post=post,
                brand=brand,
                contract_version=(
                    "stale-contract" if state_kind == "stale" else CONTRACT_VERSION
                ),
                taxonomy_version=(
                    "stale-taxonomy" if state_kind == "stale" else TAXONOMY_VERSION
                ),
                prompt_version=PROMPT_VERSION,
                model="fixture-stage1",
                input_context_fingerprint=f"{index + 1:064x}",
                outcome=(
                    PostBrandClassificationState.Outcome.CONTEXT_MISSING
                    if state_kind == "context_missing"
                    else PostBrandClassificationState.Outcome.CLASSIFIED
                ),
                sentiment_id=("neutral" if state_kind != "context_missing" else None),
            )

        rows = _enrich_posts_with_classifications(
            Post.objects.filter(tweet_id__startswith="stage1-edge-").prefetch_related(
                "brands__brand"
            ),
            brand_nickname=brand.nickname,
        )
        by_id = {row["tweet_id"]: row for row in rows}
        for state_kind in ("historical", "context_missing", "stale"):
            row = by_id[f"stage1-edge-{state_kind}"]
            self.assertEqual(row["post_types"], [])
            self.assertEqual(row["product_labels"], [])
            self.assertNotEqual(
                row["classifications_by_brand"][brand.nickname]["classification_status"],
                "classified",
            )
        current = by_id["stage1-edge-classified"]
        self.assertEqual(current["post_types"], ["other"])
        self.assertEqual(current["product_labels"], ["bug"])

        all_payload = _build_home_chart_payload(
            1, {"brands": [brand.nickname], "unsanctioned": "off"}, now=ANCHOR
        )
        product_payload = _build_home_chart_payload(
            1,
            {
                "brands": [brand.nickname],
                "product_labels": ["bug"],
                "unsanctioned": "off",
            },
            now=ANCHOR + timedelta(seconds=1),
        )
        self.assertEqual(all_payload["totals"][brand.nickname], 4)
        self.assertEqual(product_payload["totals"][brand.nickname], 1)

    def test_role_filter_matches_feed_and_chart_for_multi_brand_posts(self):
        role, _ = Role.objects.get_or_create(key="official")
        account = Account.objects.create(author_id="role-account", handle="role-account")
        brand = Brand.objects.get(nickname="up")
        post = Post.objects.create(
            tweet_id="role-filter-match",
            author=account,
            created_at=ANCHOR - timedelta(minutes=5),
        )
        PostBrand.objects.create(post=post, brand=brand)
        BrandAccount.objects.get_or_create(brand=brand, account=account, defaults={"role": role})

        filters = {"brands": ["up"], "role": ["official"], "unsanctioned": "off"}
        chart = _build_home_chart_payload(1, filters, now=ANCHOR)
        enriched = _enrich_posts_with_classifications(
            Post.objects.filter(tweet_id=post.tweet_id).prefetch_related("brands__brand"),
        )

        self.assertEqual(chart["totals"]["up"], 1)
        self.assertEqual(
            [row["tweet_id"] for row in enriched if _post_matches_filter(row, filters)],
            [post.tweet_id],
        )

    def test_first_partial_minute_is_included_after_exact_cutoff(self):
        brand = Brand.objects.create(
            nickname="boundary",
            display_name="Boundary",
            display_name_en="Boundary",
            display_name_zh_cn="边界",
            accent_color="#123456",
        )
        included = Post.objects.create(
            tweet_id="boundary-included",
            created_at=ANCHOR - timedelta(days=1) + timedelta(seconds=40),
        )
        excluded = Post.objects.create(
            tweet_id="boundary-excluded",
            created_at=ANCHOR - timedelta(days=1) + timedelta(seconds=20),
        )
        PostBrand.objects.create(post=included, brand=brand)
        PostBrand.objects.create(post=excluded, brand=brand)

        chart = _build_home_chart_payload(1, {}, now=ANCHOR + timedelta(seconds=30))

        self.assertEqual(chart["totals"]["boundary"], 1)

    def test_refresh_row_preserves_repost_and_reply_counts(self):
        row = _serialize_feed_row(
            {
                "tweet_id": "engagement-refresh",
                "created_at": ANCHOR.isoformat(),
                "text": "text",
                "text_en": "text",
                "text_zh_cn": None,
                "lang_detected": "en",
                "like_count": 11,
                "retweet_count": 7,
                "reply_count": 3,
                "brands": [],
                "brand_nicknames": [],
                "classifications_by_brand": {},
                "unsanctioned": False,
                "account": {"handle": "@engagement", "followers_count": 0},
            },
            "en",
        )

        self.assertEqual(row["retweet_count"], 7)
        self.assertEqual(row["reply_count"], 3)
        self.assertEqual(row["engagement_pretty"]["retweets"], "7")
        self.assertEqual(row["engagement_pretty"]["replies"], "3")

    @patch("monitor.views.django_timezone.now", return_value=ANCHOR)
    def test_root_and_chart_partial_share_canvas_payload_with_pulse(self, _now):
        root = self.client.get("/", secure=True)
        self.assertEqual(root.status_code, 200)
        self.assertContains(root, '<canvas class="home-chart"', html=False)
        self.assertContains(root, "data-pw-pulse", html=False)
        self.assertContains(root, 'class="pw-icon-sprite"', html=False)
        self.assertNotContains(root, '<svg class="home-chart"', html=False)

        partial = self.client.get("/chart.html?renderer=canvas", secure=True)
        self.assertEqual(partial.status_code, 200)
        self.assertContains(partial, '<canvas class="home-chart"', html=False)
        self.assertNotContains(partial, "<svg", html=False)

        chart = self.client.get("/chart/", secure=True).json()
        self.assertIn("pulse", chart)
        self.assertEqual(chart["computed_at"], chart["pulse"]["computed_at"])

    def test_chart_payload_attribute_autoescapes_untrusted_filter_values(self):
        hostile = "O'Reilly <img src=x onerror=alert(1)> & onmouseover=alert(2)"
        filters = {"brands": [hostile]}
        response = self.client.get(
            "/chart.html", {"filters": json.dumps(filters)}, secure=True
        )
        self.assertEqual(response.status_code, 200)

        parser = _ChartFragmentParser()
        parser.feed(response.content.decode("utf-8"))
        self.assertEqual(parser.tags, ["canvas", "p"])
        self.assertEqual(len(parser.canvas_attrs), 1)
        self.assertEqual(
            set(parser.canvas_attrs[0]),
            {"class", "aria-label", "data-home"},
            "untrusted JSON must not create canvas attributes",
        )
        payload = json.loads(parser.canvas_attrs[0]["data-home"] or "")
        self.assertEqual(payload["applied_filters"], filters)
