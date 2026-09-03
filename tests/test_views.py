"""Tests for monitor/views.py cursor compatibility and feed serialization."""

from __future__ import annotations

import pytest

from monitor.views import (
    _decode_cursor,
    _feed_tint_class,
    _follower_bin,
    _parse_filters_from_request,
    _partition_home_brands,
    _serialize_feed_row,
)


def test_home_brand_partition_keeps_authored_closed_tier():
    brands = [{"nickname": nickname} for nickname in (
        "deepseek", "gemini", "gpt", "dots",
    )]
    open_brands, closed_brands = _partition_home_brands(brands)
    assert [brand["nickname"] for brand in open_brands] == [
        "deepseek", "dots",
    ]
    assert [brand["nickname"] for brand in closed_brands] == [
        "gemini", "gpt",
    ]


# ============================================================================
# Helpers for building test data
# ============================================================================


def _make_post(tweet_id: str, created_at: str, like_count: int = 0, **kw) -> dict:
    """Build a minimal enriched post dict."""
    d: dict = {
        "tweet_id": tweet_id,
        "created_at": created_at,
        "like_count": like_count,
        "text": f"text {tweet_id}",
        "text_en": f"text_en {tweet_id}",
        "text_zh_cn": None,
        "lang_detected": "en",
        "brands": [],
        "brand_nicknames": [],
        "classifications_by_brand": {},
        "unsanctioned": False,
        "enrichment_status": "succeeded",
        "account": {"handle": "@user", "role": None, "followers_count": 0},
    }
    d.update(kw)
    return d


# ============================================================================
# Legacy cursor compatibility
# ============================================================================


class TestDecodeCursor:
    def test_valid(self):
        assert _decode_cursor("2026-07-20T10:00:00+00:00|12345") == (
            "2026-07-20T10:00:00+00:00", "12345")

    def test_valid_with_spaces(self):
        assert _decode_cursor(" 2026-07-20T10:00:00+00:00 | 12345 ") == (
            "2026-07-20T10:00:00+00:00", "12345")

    def test_none(self):
        assert _decode_cursor(None) is None

    def test_empty(self):
        assert _decode_cursor("") is None

    def test_no_pipe(self):
        assert _decode_cursor("2026-07-20T10:00:00Z") is None

    def test_empty_parts(self):
        assert _decode_cursor("|12345") is None
        assert _decode_cursor("2026-07-20|") is None


# ============================================================================
# _serialize_feed_row
# ============================================================================


class TestSerializeFeedRow:
    def test_basic_shape(self):
        post = _make_post("100", "2026-07-20T10:00:00+00:00")
        row = _serialize_feed_row(post, "en")
        assert row["tweet_id"] == "100"
        assert row["created_at"] == "2026-07-20T10:00:00+00:00"
        assert row["created_at_iso"] == "2026-07-20T10:00:00+00:00"
        assert "text_translated" in row
        assert "classifications" in row
        assert "account" in row
        assert row["enrichment_status"] == "succeeded"

    def test_account_display_name_prefers_account_then_snapshot_then_handle(self):
        named = _serialize_feed_row(_make_post(
            "100",
            "2026-07-20T10:00:00+00:00",
            author_name="Snapshot Name",
            account={
                "handle": "@user",
                "display_name": "Current Account Name",
                "role": None,
                "followers_count": 0,
            },
        ), "en")
        snapshot = _serialize_feed_row(_make_post(
            "101",
            "2026-07-20T10:00:00+00:00",
            author_name="Snapshot Name",
            account={"handle": "@user", "role": None, "followers_count": 0},
        ), "en")
        handle = _serialize_feed_row(_make_post(
            "102",
            "2026-07-20T10:00:00+00:00",
            account={"handle": "@user", "role": None, "followers_count": 0},
        ), "en")

        assert named["account"]["display_name"] == "Current Account Name"
        assert snapshot["account"]["display_name"] == "Snapshot Name"
        assert handle["account"]["display_name"] == "@user"

    @pytest.mark.parametrize(
        ("locale", "expected_label"),
        (("en", "enrichment pending"), ("zh_cn", "补充处理中")),
    )
    def test_includes_localized_pending_enrichment_state(self, locale, expected_label):
        post = _make_post(
            "100",
            "2026-07-20T10:00:00+00:00",
            enrichment_status="pending",
        )

        row = _serialize_feed_row(post, locale)

        assert row["enrichment_status"] == "pending"
        assert row["enrichment_status_label"] == expected_label

    def test_includes_brands_and_nicknames(self):
        post = _make_post(
            "100", "2026-07-20T10:00:00+00:00",
            brands=[{"nickname": "deepseek", "display_name": "DeepSeek"}],
            brand_nicknames=["deepseek"],
        )
        row = _serialize_feed_row(post, "en")
        assert row["brands"] == [{
            "nickname": "deepseek",
            "display_name": "DeepSeek",
            "display_name_en": "DeepSeek",
            "display_name_zh_cn": "DeepSeek",
            "accent_color": "#9ca3af",
        }]
        assert row["brand_nicknames"] == ["deepseek"]

    def test_includes_classifications(self):
        post = _make_post(
            "100", "2026-07-20T10:00:00+00:00",
            classifications_by_brand={
                "deepseek": {"discourse": ["genuine_hype"], "post_types": [], "sentiments": [], "cn_nationalism": None, "us_nationalism": None},
            },
        )
        row = _serialize_feed_row(post, "en")
        assert "deepseek" in row["classifications"]
        assert row["classifications"]["deepseek"]["discourse"] == [
            {"key": "genuine_hype", "label": "Genuine Hype"},
        ]

    def test_v22_display_contract_includes_signal_and_tint_fields(self):
        """Refresh JSON must carry the same V22 fields consumed by pw-feed."""
        post = _make_post(
            "100", "2026-07-20T10:00:00+00:00",
            classifications_by_brand={
                "kimi": {
                    "discourse": ["genuine_hype"],
                    "post_types": ["buzz_releases"],
                    "sentiments": ["positive"],
                    "cn_nationalism": "pro",
                    "us_nationalism": "mild_pro",
                },
                "deepseek": {
                    "discourse": [],
                    "post_types": ["hands_on_usage"],
                    "sentiments": ["mixed"],
                    "cn_nationalism": None,
                    "us_nationalism": None,
                },
            },
            account={
                "handle": "@user", "role": None, "followers_count": 12_800,
                "followers_pretty": "12.8k",
            },
        )

        row = _serialize_feed_row(post, "en")

        assert row["sentiment_keys"] == ["positive", "mixed"]
        assert row["post_type_keys"] == ["buzz_releases", "hands_on_usage"]
        assert row["nat_cn"] == "pro"
        assert row["nat_us"] == "mild_pro"
        assert row["tint_class"] == "tint-pos-mixed"
        assert "meta_text" in row
        assert "ts_abs_text" in row
        assert row["follower_bin"] == "10k-50k"
        assert row["followers_count"] == 12_800
        assert row["followers_label"] == "12.8k followers"
        assert row["engagement_pretty"]["followers"] == "12.8k"

        zh_row = _serialize_feed_row(post, "zh_cn")
        assert zh_row["followers_label"] == "12.8k 关注者"

    @pytest.mark.parametrize(
        ("followers", "expected"),
        [
            (0, "0-1k"),
            (999, "0-1k"),
            (1_000, "1k-10k"),
            (9_999, "1k-10k"),
            (10_000, "10k-50k"),
            (49_999, "10k-50k"),
            (50_000, "50k-plus"),
            (5_000_000, "50k-plus"),
        ],
    )
    def test_follower_bin_boundaries(self, followers, expected):
        assert _follower_bin(followers) == expected


    def test_home_brand_tiers_use_actual_model_nicknames(self):
        brands = [
            {"nickname": nickname}
            for nickname in ("deepseek", "gemini", "gpt", "claude", "grok", "qwen")
        ]

        open_brands, closed_brands = _partition_home_brands(brands)

        assert [brand["nickname"] for brand in closed_brands] == [
            "gemini", "gpt", "claude", "grok",
        ]
        assert [brand["nickname"] for brand in open_brands] == ["deepseek", "qwen"]

    def test_text_translated_uses_locale(self):
        post = _make_post("100", "2026-07-20T10:00:00+00:00")
        post["text_en"] = "English text"
        post["text"] = "Original text"
        row = _serialize_feed_row(post, "en")
        assert row["text_translated"] == "English text"
        assert row["is_translated"] is True

    def test_text_untranslated_remains_null_so_missing_data_is_visible(self):
        post = _make_post("100", "2026-07-20T10:00:00+00:00")
        post["text_en"] = None
        post["text"] = "Original text"
        row = _serialize_feed_row(post, "en")
        assert row["text_translated"] is None
        assert row["is_translated"] is False

    @pytest.mark.parametrize(
        ("sentiments", "expected"),
        [
            ([], "tint-neutral"),
            (["neutral"], "tint-neutral"),
            (["positive"], "tint-positive"),
            (["negative"], "tint-negative"),
            (["mixed"], "tint-mixed"),
            (["positive", "negative"], "tint-pos-neg"),
            (["positive", "mixed"], "tint-pos-mixed"),
            (["negative", "mixed"], "tint-neg-mixed"),
            (["positive", "negative", "mixed"], "tint-pos-neg-mixed"),
            (["positive", "positive"], "tint-positive"),
        ],
    )
    def test_server_tint_matrix_is_deterministic(self, sentiments, expected):
        assert _feed_tint_class(sentiments) == expected

    def test_active_brand_scope_narrows_display_only(self):
        post = _make_post(
            "scope-100",
            "2026-07-20T10:00:00+00:00",
            brands=[
                {"nickname": "minimax"},
                {"nickname": "moonshot_kimi"},
            ],
            brand_nicknames=["minimax", "moonshot_kimi"],
            classifications_by_brand={
                "minimax": {
                    "discourse": ["genuine_hype"],
                    "post_types": ["hands_on_usage"],
                    "sentiments": ["positive", "positive"],
                    "cn_nationalism": None,
                    "us_nationalism": None,
                },
                "moonshot_kimi": {
                    "discourse": [],
                    "post_types": ["buzz_releases"],
                    "sentiments": ["negative"],
                    "cn_nationalism": "pro",
                    "us_nationalism": "mild_pro",
                },
            },
        )

        all_brands = _serialize_feed_row(post, "en", active_brand_scope="__all__")
        minimax = _serialize_feed_row(post, "en", active_brand_scope=["minimax"])
        kimi = _serialize_feed_row(post, "en", active_brand_scope=["moonshot_kimi"])

        assert all_brands["sentiment_keys"] == ["positive", "negative"]
        assert all_brands["tint_class"] == "tint-pos-neg"
        assert minimax["sentiment_keys"] == ["positive"]
        assert minimax["tint_class"] == "tint-positive"
        assert kimi["sentiment_keys"] == ["negative"]
        assert kimi["tint_class"] == "tint-negative"
        assert minimax["classifications"] == all_brands["classifications"]
        assert kimi["classifications"] == all_brands["classifications"]

    def test_raw_metadata_and_tint_are_locale_invariant(self):
        post = _make_post(
            "locale-100",
            "2026-07-20T10:00:00+00:00",
            text="Original",
            text_en="English",
            text_zh_cn="中文",
            brand_nicknames=["minimax"],
            classifications_by_brand={
                "minimax": {
                    "discourse": ["genuine_hype"],
                    "post_types": ["hands_on_usage"],
                    "sentiments": ["positive"],
                    "cn_nationalism": "pro",
                    "us_nationalism": "mild_pro",
                },
            },
        )

        rows = {
            locale: _serialize_feed_row(post, locale, active_brand_scope="__all__")
            for locale in ("zh_cn", "zh_hans", "en", "original")
        }
        invariant = {
            locale: {
                "sentiment_keys": row["sentiment_keys"],
                "post_type_keys": row["post_type_keys"],
                "nat_cn": row["nat_cn"],
                "nat_us": row["nat_us"],
                "tint_class": row["tint_class"],
                "discourse_key": row["classifications"]["minimax"]["discourse"][0]["key"],
            }
            for locale, row in rows.items()
        }
        assert len({repr(value) for value in invariant.values()}) == 1
        assert invariant["en"]["discourse_key"] == "genuine_hype"


# ============================================================================
# _parse_filters_from_request
# ============================================================================


class TestParseFilters:
    def test_empty(self):
        from django.http import HttpRequest
        req = HttpRequest()
        req.GET = {}
        assert _parse_filters_from_request(req) == {}

    def test_json_filters(self):
        from django.http import HttpRequest
        req = HttpRequest()
        req.GET = {"filters": '{"brands": ["deepseek"], "discourse": ["genuine_hype"]}'}
        result = _parse_filters_from_request(req)
        assert result == {"brands": ["deepseek"], "discourse": ["genuine_hype"]}

    def test_malformed_json_ignored(self):
        from django.http import HttpRequest
        req = HttpRequest()
        req.GET = {"filters": "not-json"}
        result = _parse_filters_from_request(req)
        assert result == {}

    def test_comma_separated_keys(self):
        from django.http import HttpRequest
        req = HttpRequest()
        req.GET = {"discourse": "genuine_hype,sarcasm", "role": "official"}
        result = _parse_filters_from_request(req)
        assert result["discourse"] == ["genuine_hype", "sarcasm"]
        assert result["role"] == ["official"]


# ============================================================================
# Integration tests (require database)
# ============================================================================


@pytest.mark.django_db
class TestFeedViewIntegration:
    """End-to-end tests for /feed/ endpoint using the Django test client.

    Requires a database and an authenticated user.
    """

    def test_feed_returns_json(self, client, django_user_model):
        user = django_user_model.objects.create_user(
            username="testuser", password="pass",
        )
        client.force_login(user)
        resp = client.get("/feed/", secure=True)
        assert resp.status_code == 200
        data = resp.json()
        assert "rows" in data
        assert "next_cursor" in data
        assert "has_more" in data
        assert "applied_filters" in data
        assert "locale" in data

    @pytest.mark.requires_postgres
    def test_feed_routes_hide_ineligible_rows_before_page_limit(self, client, django_user_model):
        from datetime import timedelta

        from django.utils import timezone

        from core.models import Brand, Post, PostBrand, PostEnrichmentState

        user = django_user_model.objects.create_user(
            username="enrichment-user", password="pass",
        )
        now = timezone.now()
        complete_fields = {
            "text": "Source post",
            "text_en": "English translation",
            "text_zh_cn": "中文翻译",
            "commentary_en": "English commentary",
            "commentary_zh_cn": "中文评论",
            "lang_detected": "en",
        }
        pending = Post.objects.create(
            tweet_id="enrichment-pending",
            created_at=now,
            **complete_fields,
        )
        PostEnrichmentState.objects.create(post=pending)
        failed = Post.objects.create(
            tweet_id="enrichment-failed",
            created_at=now - timedelta(seconds=1),
            **complete_fields,
        )
        PostEnrichmentState.objects.create(
            post=failed,
            translation_status=PostEnrichmentState.Status.FAILED,
            classification_status=PostEnrichmentState.Status.SUCCEEDED,
        )
        succeeded = Post.objects.create(
            tweet_id="enrichment-succeeded",
            created_at=now - timedelta(seconds=2),
            **complete_fields,
        )
        PostEnrichmentState.objects.create(
            post=succeeded,
            translation_status=PostEnrichmentState.Status.SUCCEEDED,
            classification_status=PostEnrichmentState.Status.SUCCEEDED,
        )
        legacy = Post.objects.create(
            tweet_id="enrichment-legacy-complete",
            created_at=now - timedelta(seconds=3),
            **complete_fields,
        )
        invalid_succeeded = Post.objects.create(
            tweet_id="enrichment-succeeded-invalid",
            created_at=now - timedelta(seconds=4),
            **{
                **complete_fields,
                "commentary_en": complete_fields["text"],
            },
        )
        PostEnrichmentState.objects.create(
            post=invalid_succeeded,
            translation_status=PostEnrichmentState.Status.SUCCEEDED,
            classification_status=PostEnrichmentState.Status.SUCCEEDED,
        )
        incomplete_legacy = Post.objects.create(
            tweet_id="enrichment-legacy-incomplete",
            created_at=now - timedelta(seconds=5),
            **{
                **complete_fields,
                "commentary_zh_cn": None,
            },
        )
        brand, _ = Brand.objects.get_or_create(
            nickname="deepseek",
            defaults={"display_name": "DeepSeek"},
        )
        for post in (
            pending,
            failed,
            succeeded,
            legacy,
            invalid_succeeded,
            incomplete_legacy,
        ):
            PostBrand.objects.create(post=post, brand=brand)
        client.force_login(user)

        for feed_url in (
            "/feed/?limit=2",
            "/feed/?limit=2&brand=deepseek&locale=zh_cn",
        ):
            response = client.get(feed_url, secure=True)
            assert response.status_code == 200
            assert [row["tweet_id"] for row in response.json()["rows"]] == [
                succeeded.tweet_id,
                legacy.tweet_id,
            ]

        for route in ("/", "/internal/", "/brands/deepseek/"):
            html_response = client.get(route, secure=True)
            assert html_response.status_code == 200
            html = html_response.content.decode("utf-8")
            for visible in (succeeded, legacy):
                assert f'data-tweet-id="{visible.tweet_id}"' in html
            for hidden in (pending, failed, invalid_succeeded, incomplete_legacy):
                assert f'data-tweet-id="{hidden.tweet_id}"' not in html

    def test_feed_is_public_for_the_anonymous_home(self, client):
        resp = client.get("/feed/", secure=True)
        assert resp.status_code == 200

    @pytest.mark.requires_postgres
    def test_feed_filters_canonical_chinese_scripts_without_merging_them(
        self, client
    ):
        import json

        from django.utils import timezone

        from core.models import Post

        complete = {
            "created_at": timezone.now(),
            "text_en": "English translation",
            "text_zh_cn": "中文翻译",
            "commentary_en": "English commentary",
            "commentary_zh_cn": "中文评论",
        }
        Post.objects.create(
            tweet_id="language-filter-hans",
            text="简体中文原文",
            lang_detected="zh-Hans",
            **complete,
        )
        Post.objects.create(
            tweet_id="language-filter-hant",
            text="繁體中文原文",
            lang_detected="zh-Hant",
            **complete,
        )

        simplified = client.get(
            "/feed/",
            {
                "locale": "en",
                "window": 1,
                "filters": json.dumps({"lang": ["zh-hans"], "window": 1}),
            },
            secure=True,
        ).json()
        assert [row["tweet_id"] for row in simplified["rows"]] == [
            "language-filter-hans"
        ]
        assert simplified["rows"][0]["language_display"] == "zh-Hans"

        other = client.get(
            "/feed/",
            {
                "locale": "zh_cn",
                "window": 1,
                "filters": json.dumps({"lang": ["other"], "window": 1}),
            },
            secure=True,
        ).json()
        assert [row["tweet_id"] for row in other["rows"]] == [
            "language-filter-hant"
        ]
        assert other["rows"][0]["language_display"] == "zh-Hant"

    def test_home_internal_canvas_chart_is_not_owned_by_htmx(self, client, django_user_model):
        user = django_user_model.objects.create_user(
            username="internal-chart-user", password="pass",
        )
        client.force_login(user)
        resp = client.get("/internal/", secure=True)
        assert resp.status_code == 200
        html = resp.content.decode("utf-8")
        chart_start = html.index('<section class="home-chart-wrap" id="home-chart"')
        chart_end = html.index("</section>", chart_start)
        chart_region = html[chart_start:chart_end]
        assert "hx-get" not in chart_region
        assert "hx-trigger" not in chart_region
        assert "hx-swap" not in chart_region
        assert '<canvas class="home-chart"' in chart_region

    def test_feed_accepts_sort_params(self, client, django_user_model):
        user = django_user_model.objects.create_user(
            username="testuser2", password="pass",
        )
        client.force_login(user)
        resp = client.get(
            "/feed/?sort=like_count&order=asc&limit=5", secure=True
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["applied_filters"] == {}

    def test_feed_with_cursor_param(self, client, django_user_model):
        user = django_user_model.objects.create_user(
            username="testuser3", password="pass",
        )
        client.force_login(user)
        resp = client.get(
            "/feed/?cursor=2026-07-20T10:00:00Z|999&limit=10", secure=True
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "rows" in data
        assert "next_cursor" in data

    def test_brand_feed_requires_brand(self, client, django_user_model):
        user = django_user_model.objects.create_user(
            username="testuser4", password="pass",
        )
        client.force_login(user)
        # brand_feed_json view requires a brand kwarg (from URL)
        # With the new URL scheme, brand comes as kwarg from the URL pattern
        # The view also accepts ?brand= query param
        resp = client.get("/feed/?brand=nonexistent&limit=5", secure=True)
        assert resp.status_code == 200

    def test_feed_with_invalid_limit_clamps_to_request_max(self, client, django_user_model):
        user = django_user_model.objects.create_user(
            username="testuser5", password="pass",
        )
        client.force_login(user)
        resp = client.get("/feed/?limit=9999", secure=True)
        assert resp.status_code == 200
        # One response stays bounded even though total traversal has no ceiling.
        data = resp.json()
        assert len(data["rows"]) <= 100

    def test_filtered_feed_and_cursor_chain_are_complete_beyond_500(self, client):
        """The real route must filter before slicing and exhaust the full window."""
        import json
        from datetime import timedelta

        from django.utils import timezone

        from core.models import Brand, Post, PostBrand

        now = timezone.now()
        filler = Brand.objects.create(nickname="pagination-filler", display_name="Filler")
        target = Brand.objects.create(nickname="pagination-target", display_name="Target")
        complete = {
            "text": "source",
            "text_en": "translation",
            "text_zh_cn": "翻译",
            "commentary_en": "commentary",
            "commentary_zh_cn": "评论",
            "lang_detected": "en",
        }
        posts = [
            Post(
                tweet_id=f"pagination-{index:04d}",
                created_at=now - timedelta(seconds=1),
                like_count=625 - index,
                **complete,
            )
            for index in range(625)
        ]
        Post.objects.bulk_create(posts)
        PostBrand.objects.bulk_create([
            PostBrand(
                post=post,
                brand=target if index == 0 else filler,
            )
            for index, post in enumerate(posts)
        ])

        selective = client.get(
            "/feed/",
            {
                "limit": 50,
                "window": 7,
                "filters": json.dumps({"brands": [target.nickname], "window": 7}),
            },
            secure=True,
        ).json()
        assert [row["tweet_id"] for row in selective["rows"]] == ["pagination-0000"]

        seen: list[str] = []
        cursor = None
        while True:
            params = {"limit": 50, "window": 7}
            if cursor:
                params["cursor"] = cursor
            payload = client.get("/feed/", params, secure=True).json()
            seen.extend(row["tweet_id"] for row in payload["rows"])
            cursor = payload["next_cursor"]
            if not payload["has_more"]:
                break

        expected = [post.tweet_id for post in reversed(posts)]
        assert seen == expected
        assert len(seen) == len(set(seen)) == 625

        Post.objects.filter(tweet_id__startswith="pagination-").update(like_count=7)
        for order in ("asc", "desc"):
            like_seen: list[str] = []
            cursor = None
            while True:
                params = {
                    "limit": 50,
                    "window": 7,
                    "sort": "like_count",
                    "order": order,
                }
                if cursor:
                    params["cursor"] = cursor
                payload = client.get("/feed/", params, secure=True).json()
                like_seen.extend(row["tweet_id"] for row in payload["rows"])
                cursor = payload["next_cursor"]
                if not payload["has_more"]:
                    break

            expected_likes = sorted(
                (post.tweet_id for post in posts), reverse=order == "desc"
            )
            assert like_seen == expected_likes
            assert len(like_seen) == len(set(like_seen)) == 625
