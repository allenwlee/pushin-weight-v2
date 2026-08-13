"""PostgreSQL contract tests for the shared home chart and pulse payload."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser
from unittest.mock import patch

import pytest
from django.test import override_settings

from core.models import (
    Account,
    Brand,
    BrandAccount,
    DiscourseKey,
    NationalismKey,
    Post,
    PostBrand,
    PostBrandDiscourse,
    PostBrandSignal,
    PostTypeKey,
    Role,
    SentimentKey,
)
from monitor.views import (
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
        self.assertEqual(list(by_nickname), ["up", "flat", "new", "down"])
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
        self.assertNotIn("absent", by_nickname)
        self.assertEqual(pulse["window_days"], 1)
        self.assertEqual(pulse["computed_at"], ANCHOR.isoformat())

        with self.assertNumQueries(0):
            self.assertEqual(_build_home_pulse_payload(1, now=ANCHOR), pulse)

    def test_half_away_from_zero_rounding_and_rounded_zero_direction(self):
        self.assertEqual(_round_pulse_percent(9, 8), 13)
        self.assertEqual(_round_pulse_percent(7, 8), -13)
        self.assertEqual(_round_pulse_percent(200, 201), 0)

    def test_chart_uses_set_based_shared_predicate_and_atomic_pulse_anchor(self):
        PostTypeKey.objects.create(key="buzz_releases")
        SentimentKey.objects.create(key="positive")
        DiscourseKey.objects.create(key="genuine_hype")
        NationalismKey.objects.create(key="pro")
        NationalismKey.objects.create(key="mild_pro")
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
            post_type_id="buzz_releases",
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

        active = {
            "brands": ["up"],
            "discourse": ["genuine_hype"],
            "post_types": ["buzz_releases"],
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
            {**active, "discourse": []},
            now=ANCHOR + timedelta(seconds=1),
        )
        self.assertEqual(empty["totals"], {"up": 0})
        self.assertEqual(empty["pulse"], payload["pulse"], "ordinary filters must not change market-wide pulse")
        self.assertEqual(empty["computed_at"], empty["pulse"]["computed_at"])

    def test_in_memory_empty_axes_match_set_based_zero_semantics(self):
        sample = {
            "brand_nicknames": ["up"],
            "discourse": ["genuine_hype"],
            "post_types": ["buzz_releases"],
            "sentiments": ["positive"],
            "role_key": "official",
            "lang_detected": "en",
            "cn_nationalism": "pro",
            "us_nationalism": "mild_pro",
            "unsanctioned": False,
        }
        for axis in ("brands", "discourse", "post_types", "sentiment", "role", "lang", "cn_nationalism", "us_nationalism"):
            with self.subTest(axis=axis):
                self.assertFalse(_post_matches_filter(sample, {axis: []}))

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
        root = self.client.get("/")
        self.assertEqual(root.status_code, 200)
        self.assertContains(root, '<canvas class="home-chart"', html=False)
        self.assertContains(root, "data-pw-pulse", html=False)
        self.assertNotContains(root, "<svg", html=False)

        partial = self.client.get("/chart.html?renderer=canvas")
        self.assertEqual(partial.status_code, 200)
        self.assertContains(partial, '<canvas class="home-chart"', html=False)
        self.assertNotContains(partial, "<svg", html=False)

        chart = self.client.get("/chart/").json()
        self.assertIn("pulse", chart)
        self.assertEqual(chart["computed_at"], chart["pulse"]["computed_at"])

    def test_chart_payload_attribute_autoescapes_untrusted_filter_values(self):
        hostile = "O'Reilly <img src=x onerror=alert(1)> & onmouseover=alert(2)"
        filters = {"brands": [hostile]}
        response = self.client.get("/chart.html", {"filters": json.dumps(filters)})
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
