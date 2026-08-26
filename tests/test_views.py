"""Tests for monitor/views.py — cursor pagination, sort, feed serialization (U2).

Focuses on the pure helpers (_decode_cursor, _encode_cursor,
_post_passes_cursor, _paginate_feed, _serialize_feed_row) which can be
tested without a database.  Integration tests for the full view are
marked with @pytest.mark.django_db.
"""

from __future__ import annotations

import pytest

from monitor.views import (
    _decode_cursor,
    _encode_cursor,
    _feed_tint_class,
    _follower_bin,
    _paginate_feed,
    _partition_home_brands,
    _post_passes_cursor,
    _serialize_feed_row,
    _parse_filters_from_request,
    _FEED_DEFAULT_SORT,
    _FEED_DEFAULT_ORDER,
    FEED_DEFAULT_LIMIT,
)


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


def _make_posts(n: int, *, base_tweet_id: str = "100", start_iso: str = "2026-07-20T10:00:00") -> list[dict]:
    """Build n posts with descending created_at and ascending tweet_id.

    The timestamps step backward by 1 minute each, and tweet_ids
    increment.  This ensures (created_at, tweet_id) tuples are unique
    and the descending sort is stable.
    """
    from datetime import datetime, timedelta, timezone

    base = datetime.fromisoformat(start_iso).replace(tzinfo=timezone.utc)
    posts = []
    for i in range(n):
        dt = base - timedelta(minutes=i)
        tid = str(int(base_tweet_id) + i)
        posts.append(_make_post(
            tweet_id=tid,
            created_at=dt.isoformat(),
            like_count=n - i,  # descending likes: newest has highest
        ))
    return posts


# ============================================================================
# _decode_cursor / _encode_cursor
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


class TestEncodeCursor:
    def test_roundtrip(self):
        original = ("2026-07-20T10:00:00+00:00", "1234567890123456789")
        encoded = _encode_cursor(*original)
        assert _decode_cursor(encoded) == original

    def test_simple(self):
        assert _encode_cursor("2026-07-20T10:00:00Z", "100") == "2026-07-20T10:00:00Z|100"


# ============================================================================
# _post_passes_cursor
# ============================================================================


class TestPostPassesCursor:
    def test_desc_newer_than_cursor_is_blocked(self):
        """For desc, posts newer than or equal to cursor are blocked."""
        post = _make_post("200", "2026-07-20T10:00:00+00:00")
        cursor = ("2026-07-20T09:00:00+00:00", "200")
        # post cursor > reference cursor, so it should be blocked (desc wants <)
        assert not _post_passes_cursor(post, cursor, "desc")

    def test_desc_older_than_cursor_passes(self):
        """For desc, posts older than cursor pass."""
        post = _make_post("200", "2026-07-20T09:00:00+00:00")
        cursor = ("2026-07-20T10:00:00+00:00", "200")
        assert _post_passes_cursor(post, cursor, "desc")

    def test_desc_same_created_at_but_lower_tweet_id_passes(self):
        """Tie-break on tweet_id: lower tweet_id is older, should pass for desc."""
        post = _make_post("199", "2026-07-20T10:00:00+00:00")
        cursor = ("2026-07-20T10:00:00+00:00", "200")
        # (same_iso, 199) < (same_iso, 200) → passes
        assert _post_passes_cursor(post, cursor, "desc")

    def test_desc_same_created_at_same_tweet_id_blocked(self):
        """Exact match is blocked (strict <, not <=)."""
        post = _make_post("200", "2026-07-20T10:00:00+00:00")
        cursor = ("2026-07-20T10:00:00+00:00", "200")
        assert not _post_passes_cursor(post, cursor, "desc")

    def test_asc_older_than_cursor_blocked(self):
        post = _make_post("200", "2026-07-20T09:00:00+00:00")
        cursor = ("2026-07-20T10:00:00+00:00", "200")
        assert not _post_passes_cursor(post, cursor, "asc")

    def test_asc_newer_than_cursor_passes(self):
        post = _make_post("200", "2026-07-20T11:00:00+00:00")
        cursor = ("2026-07-20T10:00:00+00:00", "200")
        assert _post_passes_cursor(post, cursor, "asc")

    def test_asc_same_created_at_higher_tweet_id_passes(self):
        post = _make_post("201", "2026-07-20T10:00:00+00:00")
        cursor = ("2026-07-20T10:00:00+00:00", "200")
        assert _post_passes_cursor(post, cursor, "asc")

    def test_missing_created_at_fails(self):
        post = _make_post("200", "")
        cursor = ("2026-07-20T10:00:00+00:00", "200")
        assert not _post_passes_cursor(post, cursor, "desc")

    def test_missing_tweet_id_fails(self):
        post = {"tweet_id": "", "created_at": "2026-07-20T10:00:00+00:00"}
        cursor = ("2026-07-20T10:00:00+00:00", "200")
        assert not _post_passes_cursor(post, cursor, "desc")


# ============================================================================
# _paginate_feed
# ============================================================================


class TestPaginateFeed:
    def test_first_page_no_cursor_returns_first_n(self):
        posts = _make_posts(25)
        page, cursor, has_more = _paginate_feed(posts, cursor=None, limit=10)
        assert len(page) == 10
        assert page[0]["tweet_id"] == "100"  # newest first
        assert cursor is not None
        assert has_more is True

    def test_first_page_next_cursor_is_last_row(self):
        posts = _make_posts(25)
        page, cursor, has_more = _paginate_feed(posts, cursor=None, limit=10)
        last = page[-1]
        expected = _encode_cursor(last["created_at"], last["tweet_id"])
        assert cursor == expected

    def test_second_page_no_overlap_with_first(self):
        posts = _make_posts(25)
        page1, cursor1, _ = _paginate_feed(posts, cursor=None, limit=10)
        page2, cursor2, _ = _paginate_feed(posts, cursor=cursor1, limit=10)

        ids1 = {r["tweet_id"] for r in page1}
        ids2 = {r["tweet_id"] for r in page2}
        assert ids1.isdisjoint(ids2), "pages must not overlap"
        # page2 should have older posts (higher tweet_id numbers)
        assert all(
            r["tweet_id"] not in ids1 for r in page2
        ), "no duplicate tweet_ids across pages"

    def test_last_page_has_more_false(self):
        posts = _make_posts(12)
        page, cursor, has_more = _paginate_feed(posts, cursor=None, limit=10)
        assert len(page) == 10
        assert has_more is True
        assert cursor is not None

        page2, cursor2, has_more2 = _paginate_feed(posts, cursor=cursor, limit=10)
        assert len(page2) == 2
        assert has_more2 is False
        assert cursor2 is None

    def test_cursor_pagination_asc_order(self):
        posts = _make_posts(25)
        # Reverse to asc (oldest first)
        posts_asc = list(reversed(posts))
        page1, cursor1, has_more1 = _paginate_feed(
            posts_asc, cursor=None, sort="created_at", order="asc", limit=10,
        )
        assert len(page1) == 10
        assert has_more1 is True
        # First page should have the oldest posts (highest tweet_ids)
        assert page1[0]["tweet_id"] == "124"

        page2, cursor2, has_more2 = _paginate_feed(
            posts_asc, cursor=cursor1, sort="created_at", order="asc", limit=10,
        )
        assert len(page2) == 10
        # No overlap
        ids1 = {r["tweet_id"] for r in page1}
        ids2 = {r["tweet_id"] for r in page2}
        assert ids1.isdisjoint(ids2)

    def test_like_count_sort_uses_offset_fallback(self):
        posts = _make_posts(25)
        # like_count desc: newest posts have highest like_count
        page1, cursor1, has_more1 = _paginate_feed(
            posts, cursor=None, sort="like_count", order="desc", limit=10,
        )
        assert len(page1) == 10
        assert has_more1 is True
        # Verify descending like_count: first should be highest
        assert page1[0]["like_count"] >= page1[-1]["like_count"]

        # Even with a cursor, like_count should still use offset (cursor ignored)
        page2, _, _ = _paginate_feed(
            posts, cursor=cursor1, sort="like_count", order="desc", limit=10, offset=10,
        )
        assert len(page2) == 10

    def test_invalid_cursor_graceful_degradation(self):
        """Malformed cursor should return first page (offset=0)."""
        posts = _make_posts(25)
        page, cursor, has_more = _paginate_feed(
            posts, cursor="garbage", sort="created_at", order="desc", limit=10,
        )
        # garbage → decode fails → cursor_pair=None → offset fallback at offset=0
        assert len(page) == 10
        # Should be the first page (newest posts)
        assert page[0]["tweet_id"] == "100"

    def test_limit_zero_returns_empty(self):
        posts = _make_posts(25)
        page, cursor, has_more = _paginate_feed(posts, cursor=None, limit=0)
        assert len(page) == 0

    def test_empty_posts(self):
        page, cursor, has_more = _paginate_feed([], cursor=None, limit=10)
        assert len(page) == 0
        assert cursor is None
        assert has_more is False

    def test_exact_page_size_fills_no_more(self):
        """When posts exactly fill the page, has_more should be False."""
        posts = _make_posts(5)
        page, cursor, has_more = _paginate_feed(posts, cursor=None, limit=5)
        assert len(page) == 5
        assert has_more is False
        assert cursor is None

    def test_offset_fallback_with_explicit_offset(self):
        posts = _make_posts(25)
        page, _, _ = _paginate_feed(
            posts, cursor=None, sort="like_count", order="desc", limit=10, offset=10,
        )
        assert len(page) == 10
        # Should skip first 10
        all_ids = {p["tweet_id"] for p in posts}
        page_ids = {p["tweet_id"] for p in page}
        remaining = all_ids - page_ids
        assert len(remaining) == 15


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
        assert row["brands"] == [{"nickname": "deepseek", "display_name": "DeepSeek"}]
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
            {"key": "genuine_hype", "label": "genuine_hype"},
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
        resp = client.get("/feed/")
        assert resp.status_code == 200
        data = resp.json()
        assert "rows" in data
        assert "next_cursor" in data
        assert "has_more" in data
        assert "applied_filters" in data
        assert "locale" in data

    def test_feed_returns_durable_enrichment_state(self, client, django_user_model):
        from django.utils import timezone

        from core.models import Post, PostEnrichmentState

        user = django_user_model.objects.create_user(
            username="enrichment-user", password="pass",
        )
        post = Post.objects.create(
            tweet_id="enrichment-pending",
            text="pending post",
            created_at=timezone.now(),
        )
        PostEnrichmentState.objects.create(post=post)
        client.force_login(user)

        response = client.get("/feed/")

        assert response.status_code == 200
        row = next(
            item for item in response.json()["rows"]
            if item["tweet_id"] == post.tweet_id
        )
        assert row["enrichment_status"] == "pending"
        assert row["enrichment_status_label"] == "enrichment pending"

    def test_feed_is_public_for_the_anonymous_home(self, client):
        resp = client.get("/feed/")
        assert resp.status_code == 200

    def test_home_internal_canvas_chart_is_not_owned_by_htmx(self, client, django_user_model):
        user = django_user_model.objects.create_user(
            username="internal-chart-user", password="pass",
        )
        client.force_login(user)
        resp = client.get("/internal/")
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
        resp = client.get("/feed/?sort=like_count&order=asc&limit=5")
        assert resp.status_code == 200
        data = resp.json()
        assert data["applied_filters"] == {}

    def test_feed_with_cursor_param(self, client, django_user_model):
        user = django_user_model.objects.create_user(
            username="testuser3", password="pass",
        )
        client.force_login(user)
        resp = client.get("/feed/?cursor=2026-07-20T10:00:00Z|999&limit=10")
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
        resp = client.get("/feed/?brand=nonexistent&limit=5")
        assert resp.status_code == 200

    def test_feed_with_invalid_limit_clamps_to_hard_cap(self, client, django_user_model):
        user = django_user_model.objects.create_user(
            username="testuser5", password="pass",
        )
        client.force_login(user)
        resp = client.get("/feed/?limit=9999")
        assert resp.status_code == 200
        # Should not return more than FEED_HARD_CAP (500)
        data = resp.json()
        assert len(data["rows"]) <= 500
