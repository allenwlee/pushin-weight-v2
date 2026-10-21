"""The separate one-model dashboard counts posts and label assignments honestly."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from django.db import connection, transaction
from django.db.models import QuerySet
from django.test import Client, override_settings
from django.test.utils import CaptureQueriesContext

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
        for key in ("other", "releases_updates", "opinions_reactions"):
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
        cls.deepseek = Brand.objects.create(
            nickname="deepseek", display_name="DeepSeek", display_name_en="DeepSeek",
            accent_color="#10b981",
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
        self.assertEqual(
            [(entry["key"], entry["color"]) for entry in chart["entries"]],
            [
                ("__unclassified__", "#000000"), ("neutral", "#cbd5e1"),
                ("mixed", "#8b5cf6"), ("negative", "#ef4444"),
                ("positive", "#3b82f6"),
            ],
        )

    def test_post_type_route_plans_for_all_rows_and_restores_outer_transaction(self):
        original_iterator = QuerySet.iterator
        observed = []

        def inspect_iterator(queryset, *args, **kwargs):
            if queryset.model is PostBrand:
                with connection.cursor() as cursor:
                    cursor.execute("SHOW cursor_tuple_fraction")
                    observed.append(float(cursor.fetchone()[0]))
            yield from original_iterator(queryset, *args, **kwargs)

        for days in (7, 30, 365):
            with self.subTest(days=days), transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("SELECT set_config('cursor_tuple_fraction', '0.35', true)")
                observed.clear()
                with patch.object(QuerySet, "iterator", inspect_iterator), patch(
                    "monitor.views._dashboard_now", return_value=NOW
                ):
                    response = self.client.get(
                        "/dashboard/each/chart/",
                        {"brand": self.minimax.nickname, "tab": "post_types",
                         "window": days, "locale": "en", "tz": "Asia/Tokyo"},
                    )
                self.assertEqual(response.status_code, 200)
                self.assertTrue(observed)
                self.assertTrue(all(value == 1.0 for value in observed), observed)
                self.assertEqual(sum(response.json()["totals"]), 3)
                self.assertEqual(sum(response.json()["series"]["other"]), 2)
                self.assertEqual(sum(response.json()["series"]["__unclassified__"]), 1)
                with connection.cursor() as cursor:
                    cursor.execute("SHOW cursor_tuple_fraction")
                    self.assertEqual(float(cursor.fetchone()[0]), 0.35)

    def test_failed_post_type_route_restores_its_previous_cursor_plan(self):
        observed = []

        def failed_iterator(queryset, *args, **kwargs):
            if queryset.model is PostBrand:
                with connection.cursor() as cursor:
                    cursor.execute("SHOW cursor_tuple_fraction")
                    observed.append(float(cursor.fetchone()[0]))
                raise RuntimeError("owned iterator failure")
            yield from ()

        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SELECT set_config('cursor_tuple_fraction', '0.35', true)")
            with patch.object(QuerySet, "iterator", failed_iterator), self.assertRaisesRegex(
                RuntimeError, "owned iterator failure"
            ):
                self.client.get(
                    "/dashboard/each/chart/",
                    {"brand": self.minimax.nickname, "tab": "post_types", "window": 7},
                )
            self.assertEqual(observed, [1.0])
            with connection.cursor() as cursor:
                cursor.execute("SHOW cursor_tuple_fraction")
                self.assertEqual(float(cursor.fetchone()[0]), 0.35)

    def test_post_type_consumer_error_restores_plan_while_traceback_is_alive(self):
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SELECT set_config('cursor_tuple_fraction', '0.35', true)")
            with patch.object(
                PostBrandSignal.objects, "filter", side_effect=RuntimeError("edge read failure")
            ):
                try:
                    _each_chart_payload(
                        self.minimax.nickname, "post_types", 7, "en", now=NOW
                    )
                except RuntimeError as error:
                    self.assertEqual(str(error), "edge read failure")
                    with connection.cursor() as cursor:
                        cursor.execute("SHOW cursor_tuple_fraction")
                        self.assertEqual(float(cursor.fetchone()[0]), 0.35)
                else:
                    self.fail("Expected the owned edge-reader failure")

    def test_deepseek_three_day_ranking_is_shared_by_other_models(self):
        for index, (kind, age) in enumerate((
            ("releases_updates", 1), ("releases_updates", 2),
            ("opinions_reactions", 1), ("opinions_reactions", 4),
        )):
            post = Post.objects.create(
                tweet_id=f"each-reference-{index}", created_at=NOW - timedelta(days=age),
                lang_detected="ja" if index < 2 else "es",
            )
            PostBrand.objects.create(post=post, brand=self.deepseek)
            PostBrandSignal.objects.create(
                post=post, brand=self.deepseek, post_type_id=kind,
                sentiment_id="neutral",
            )
            PostBrandClassificationState.objects.create(
                post=post, brand=self.deepseek, contract_version=CONTRACT_VERSION,
                taxonomy_version=TAXONOMY_VERSION, prompt_version=PROMPT_VERSION,
                model="test", input_context_fingerprint=f"{index + 20:064x}",
                outcome="classified",
            )
            PostBrandProductLabel.objects.create(
                post=post, brand=self.deepseek,
                product_label_id="bug" if index < 2 else "complaint",
            )
        for days in (1, 7):
            chart = _each_chart_payload(
                self.minimax.nickname, "post_types", days, "en", now=NOW
            )
            keys = [entry["key"] for entry in chart["entries"]]
            self.assertEqual(keys[:2], ["__unclassified__", "other"])
            self.assertLess(keys.index("releases_updates"), keys.index("opinions_reactions"))
            self.assertEqual(chart["entries"][0]["color"], "#000000")
            self.assertEqual(chart["entries"][1]["color"], "#cbd5e1")
        lang = _each_chart_payload(self.minimax.nickname, "lang", 7, "en", now=NOW)
        self.assertEqual([entry["key"] for entry in lang["entries"][:3]],
                         ["undetected", "other", "en"])
        self.assertLess(
            [entry["key"] for entry in lang["entries"]].index("ja"),
            [entry["key"] for entry in lang["entries"]].index("es"),
        )
        role = _each_chart_payload(self.minimax.nickname, "role", 7, "en", now=NOW)
        self.assertEqual([entry["key"] for entry in role["entries"]],
                         ["other", "official", "staff", "community"])
        product = _each_chart_payload(
            self.minimax.nickname, "product_labels", 7, "en", now=NOW
        )
        self.assertEqual([entry["key"] for entry in product["entries"][:2]],
                         ["__unclassified__", "__no_product_signal__"])
        self.assertLess(
            [entry["key"] for entry in product["entries"]].index("bug"),
            [entry["key"] for entry in product["entries"]].index("complaint"),
        )

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
        with CaptureQueriesContext(connection) as queries:
            chart = _each_chart_payload(
                self.minimax.nickname, "sentiment", 1, "en", now=NOW
            )
        self.assertEqual(sum(chart["totals"]), 1008)
        self.assertEqual(sum(chart["series"]["__unclassified__"]), 1006)
        # A chart must aggregate current/legacy classifications in one query,
        # rather than fetch another batch of scalar rows for every 1000 posts.
        classification_reads = [
            query["sql"] for query in queries.captured_queries
            if "posts_brands_classification_states" in query["sql"]
        ]
        self.assertEqual(len(classification_reads), 1)

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
        self.assertContains(page, 'name="each-chart-mode" value="percent" data-each-mode="percent" checked')
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

    def test_sentiment_aggregate_preserves_scalar_ownership_and_window_buckets(self):
        SentimentKey.objects.get_or_create(key="")

        def add(name, sentiments=(), *, state=None, when=NOW - timedelta(minutes=20),
                signal_brand=None, state_brand=None):
            post = Post.objects.create(tweet_id=f"each-parity-{name}", created_at=when)
            PostBrand.objects.create(post=post, brand=self.minimax)
            for kind, sentiment in zip(("other", "opinions_reactions", "releases_updates"), sentiments):
                PostBrandSignal.objects.create(
                    post=post, brand_id=signal_brand or self.minimax.pk,
                    post_type_id=kind, sentiment_id=sentiment,
                )
            if state is not None:
                values = {
                    "contract_version": CONTRACT_VERSION,
                    "taxonomy_version": TAXONOMY_VERSION,
                    "prompt_version": "historical-prompt", "model": "test",
                    "input_context_fingerprint": "7" * 64,
                    "outcome": "context_missing", "sentiment_id": None,
                }
                values.update(state)
                PostBrandClassificationState.objects.create(
                    post=post, brand_id=state_brand or self.minimax.pk, **values,
                )
            return post

        add("legacy-same", ("positive", "positive"))
        add("legacy-conflict", ("positive", "negative"))
        add("literal-sentiment-conflict", ("positive", "POSITIVE"))
        add("literal-sentiment-value", ("POSITIVE",))
        add("legacy-empty", ("", "negative"))
        add("current-owns", ("negative",), state={"sentiment_id": "positive"})
        add("null-owns", ("positive",), state={})
        add("old-contract", ("positive",), state={"contract_version": "unknown"})
        add("old-taxonomy", ("positive",), state={"taxonomy_version": "unknown"})
        add("v2-owns", ("negative",), state={
            "taxonomy_version": STAGE1_TAXONOMY_V2_VERSION, "sentiment_id": "neutral",
        })
        add("other-brand", ("positive",), signal_brand=self.qwen.pk,
            state={"sentiment_id": "negative"}, state_brand=self.qwen.pk)
        add("literal-state-key", ("negative",), state={"sentiment_id": "positive"},
            state_brand=self.minimax.pk.upper())
        add("literal-signal-key", ("positive",), signal_brand=self.minimax.pk.upper())
        add("start-included", ("positive",), when=NOW - timedelta(days=1))
        add("start-excluded", ("negative",), when=NOW - timedelta(days=1, microseconds=1))
        add("end-excluded", ("negative",), when=NOW)
        add("null-date", ("positive",), when=None)
        add("long-history", ("neutral",), when=NOW - timedelta(days=200))
        for brand in (self.minimax.pk, self.minimax.pk.upper()):
            for days in (1, 7, 30, 365):
                for timezone in ("UTC", "Asia/Tokyo", "America/Los_Angeles", "Pacific/Chatham"):
                    with self.subTest(brand=brand, days=days, timezone=timezone):
                        arguments = {"now": NOW, "bucket_timezone": timezone}
                        with patch("monitor.views.aggregate_brand_sentiment_counts", return_value=None):
                            reference = _each_chart_payload(brand, "sentiment", days, "en", **arguments)
                        actual = _each_chart_payload(brand, "sentiment", days, "en", **arguments)
                        self.assertEqual(actual, reference)
