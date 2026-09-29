"""The separate one-model dashboard counts posts and label assignments honestly."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from django.test import Client, override_settings

from core.classification_contract import (
    CONTRACT_VERSION,
    PROMPT_VERSION,
    STAGE1_TAXONOMY_V2_VERSION,
    TAXONOMY_VERSION,
)
from core.models import (
    Brand,
    Post,
    PostBrand,
    PostBrandClassificationState,
    PostBrandProductLabel,
    PostBrandSignal,
    PostTypeKey,
    ProductLabelKey,
    SentimentKey,
)
from monitor.views import _each_chart_payload
from tests.v22_support import PostgreSQLV22TestCase

pytestmark = pytest.mark.requires_postgres
NOW = datetime(2026, 9, 29, 12, tzinfo=UTC)


@override_settings(SECURE_SSL_REDIRECT=False)
class DashboardEachTests(PostgreSQLV22TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        for key in ("positive", "mixed", "neutral", "negative"):
            SentimentKey.objects.get_or_create(key=key)
        for key in ("other", "releases_updates"):
            PostTypeKey.objects.get_or_create(key=key)
        for key in ("bug", "complaint"):
            ProductLabelKey.objects.get_or_create(key=key)
        cls.minimax = Brand.objects.create(
            nickname="each-minimax",
            display_name="MiniMax",
            display_name_en="MiniMax",
            accent_color="#4477ee",
        )
        cls.qwen = Brand.objects.create(
            nickname="each-qwen",
            display_name="Qwen",
            display_name_en="Qwen",
            accent_color="#ff8833",
        )
        specs = (
            ("positive", ("releases_updates", "other"), ("bug", "complaint")),
            ("mixed", ("other",), ("bug",)),
            (None, (), ()),
        )
        for index, (sentiment, types, products) in enumerate(specs):
            post = Post.objects.create(
                tweet_id=f"each-post-{index}",
                created_at=NOW - timedelta(minutes=index + 1),
                lang_detected="en",
            )
            PostBrand.objects.create(post=post, brand=cls.minimax)
            for key in types:
                PostBrandSignal.objects.create(
                    post=post,
                    brand=cls.minimax,
                    post_type_id=key,
                    sentiment_id="positive",
                )
            for key in products:
                PostBrandProductLabel.objects.create(
                    post=post, brand=cls.minimax, product_label_id=key
                )
            if sentiment:
                PostBrandClassificationState.objects.create(
                    post=post,
                    brand=cls.minimax,
                    contract_version=CONTRACT_VERSION,
                    taxonomy_version=TAXONOMY_VERSION,
                    prompt_version=PROMPT_VERSION,
                    model="test",
                    input_context_fingerprint=f"{index + 1:064x}",
                    outcome="classified",
                    sentiment_id=sentiment,
                )
        other = Post.objects.create(
            tweet_id="each-other", created_at=NOW - timedelta(minutes=1)
        )
        PostBrand.objects.create(post=other, brand=cls.qwen)

    def test_sentiment_partitions_one_brand(self):
        chart = _each_chart_payload(
            self.minimax.nickname, "sentiment", 1, "en", now=NOW
        )
        self.assertEqual(sum(chart["totals"]), 3)
        self.assertEqual(sum(chart["series"]["positive"]), 1)
        self.assertEqual(sum(chart["series"]["mixed"]), 1)
        self.assertEqual(sum(chart["series"]["__unclassified__"]), 1)
        self.assertEqual(sum(sum(values) for values in chart["series"].values()), 3)
        self.assertEqual(chart["counting_unit"], "posts")

    def test_multilabel_stack_counts_assignments(self):
        types = _each_chart_payload(
            self.minimax.nickname, "post_types", 1, "en", now=NOW
        )
        self.assertEqual(sum(types["series"]["other"]), 2)
        self.assertEqual(sum(types["series"]["releases_updates"]), 1)
        self.assertEqual(sum(types["series"]["__unclassified__"]), 1)
        self.assertEqual(sum(sum(values) for values in types["series"].values()), 4)
        self.assertEqual(types["counting_unit"], "label_assignments")
        products = _each_chart_payload(
            self.minimax.nickname, "product_labels", 1, "en", now=NOW
        )
        self.assertEqual(sum(products["series"]["bug"]), 2)
        self.assertEqual(sum(products["series"]["complaint"]), 1)
        self.assertEqual(sum(products["series"]["__unclassified__"]), 1)

    def test_combined_v2_event_does_not_become_exact_event(self):
        PostTypeKey.objects.get_or_create(key="events_opportunities")
        post = Post.objects.create(
            tweet_id="each-v2-combined", created_at=NOW - timedelta(minutes=10)
        )
        PostBrand.objects.create(post=post, brand=self.minimax)
        PostBrandSignal.objects.create(
            post=post,
            brand=self.minimax,
            post_type_id="events_opportunities",
            sentiment_id="neutral",
        )
        PostBrandClassificationState.objects.create(
            post=post,
            brand=self.minimax,
            contract_version=CONTRACT_VERSION,
            taxonomy_version=STAGE1_TAXONOMY_V2_VERSION,
            prompt_version=PROMPT_VERSION,
            model="test",
            input_context_fingerprint="4" * 64,
            outcome="classified",
            sentiment_id="neutral",
        )
        chart = _each_chart_payload(
            self.minimax.nickname, "post_types", 1, "en", now=NOW
        )
        self.assertEqual(sum(chart["series"]["events"]), 0)
        self.assertEqual(sum(chart["series"]["opportunities"]), 0)
        self.assertEqual(sum(chart["series"]["__unclassified__"]), 2)

    def test_chart_reads_beyond_feed_limit_and_across_chunks(self):
        posts = [
            Post(
                tweet_id=f"each-bulk-{index}",
                created_at=NOW - timedelta(minutes=15),
            )
            for index in range(1005)
        ]
        Post.objects.bulk_create(posts)
        PostBrand.objects.bulk_create(
            [PostBrand(post=post, brand=self.minimax) for post in posts]
        )
        chart = _each_chart_payload(
            self.minimax.nickname, "sentiment", 1, "en", now=NOW
        )
        self.assertEqual(sum(chart["totals"]), 1008)
        self.assertEqual(sum(chart["series"]["__unclassified__"]), 1006)

    def test_public_route_and_endpoint_keep_home_intact(self):
        client = Client(HTTP_HOST="127.0.0.1")
        self.assertEqual(client.get("/").status_code, 200)
        page = client.get(
            "/dashboard/each", {"locale": "en", "brand": self.minimax.nickname}
        )
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'data-pw-page="each"')
        self.assertContains(page, 'data-pw-brand-scope="each-minimax"')
        self.assertContains(page, 'role="tablist"')
        self.assertNotContains(page, 'class="filter-bar"')
        self.assertNotContains(page, "model-select")
        data = client.get(
            "/dashboard/each/chart/",
            {
                "locale": "en",
                "brand": self.minimax.nickname,
                "tab": "sentiment",
                "window": 7,
            },
        )
        self.assertEqual(data.status_code, 200)
        self.assertEqual(data.json()["brand"], self.minimax.nickname)
        self.assertEqual(data.json()["tab"], "sentiment")
        self.assertEqual(
            client.get("/dashboard/each/chart/", {"brand": "invalid"}).status_code, 400
        )
