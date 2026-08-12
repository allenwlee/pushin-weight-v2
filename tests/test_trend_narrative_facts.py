"""PostgreSQL contract tests for deterministic headline trend facts."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta, timezone
from itertools import count

import pytest

from core.models import (
    Account,
    Brand,
    Post,
    PostBrand,
    PostBrandSignal,
    PostTypeKey,
    SentimentKey,
)
from monitor.trend_narrative_facts import (
    ALLOWED_TREND_WINDOWS,
    TrendFactThresholds,
    build_trend_fact_packet,
    canonical_fact_json,
)

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]

AS_OF = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)
_SERIAL = count()


def _brand(nickname: str, *, sentinel: bool = False) -> Brand:
    return Brand.objects.create(
        nickname=nickname,
        display_name=nickname.replace("_", " ").title(),
        display_name_en=nickname.replace("_", " ").title(),
        display_name_zh_cn=f"中{nickname}",
        is_sentinel=sentinel,
    )


def _seed_posts(
    brand: Brand,
    *,
    total: int,
    authors: int,
    created_at: datetime,
    prefix: str | None = None,
) -> list[Post]:
    """Seed deterministic post-brand pairs without signal-table dependence."""
    assert total >= 0
    assert authors > 0
    serial = next(_SERIAL)
    prefix = prefix or f"{brand.nickname}-{serial}"
    accounts = [
        Account.objects.create(
            author_id=f"{prefix}-author-{index}",
            handle=f"{prefix[:40]}-{index}",
        )
        for index in range(authors)
    ]
    posts = [
        Post(
            tweet_id=f"{prefix}-post-{index}",
            author=accounts[index % authors],
            created_at=created_at + timedelta(microseconds=index),
        )
        for index in range(total)
    ]
    Post.objects.bulk_create(posts)
    PostBrand.objects.bulk_create([PostBrand(post=post, brand=brand) for post in posts])
    return posts


def _seed_coverage_anchor(brand: Brand, *, window_days: int = 1) -> None:
    _seed_posts(
        brand,
        total=1,
        authors=1,
        created_at=AS_OF - timedelta(days=window_days),
        prefix=f"coverage-{brand.nickname}-{next(_SERIAL)}",
    )


def _key(entry: dict | None) -> str | None:
    return entry["key"] if entry is not None else None


def test_recent_minimax_leads_and_earlier_deepseek_is_handoff_contrast():
    minimax = _brand("minimax")
    deepseek = _brand("deepseek")
    _seed_posts(
        deepseek,
        total=20,
        authors=10,
        created_at=AS_OF - timedelta(hours=18),
    )
    _seed_posts(
        minimax,
        total=20,
        authors=10,
        created_at=AS_OF - timedelta(hours=6),
    )

    packet = build_trend_fact_packet(1, as_of=AS_OF)

    assert packet["narrative_type"] == "handoff"
    assert _key(packet["primary_brand"]) == "minimax"
    assert _key(packet["earlier_leader"]) == "deepseek"
    assert packet["secondary_brand"] is None
    assert packet["momentum"] == "new"


def test_half_open_boundaries_and_duplicate_signals_do_not_multiply_counts():
    brand = _brand("boundary")
    _seed_coverage_anchor(brand)
    recent = _seed_posts(
        brand,
        total=19,
        authors=10,
        created_at=AS_OF - timedelta(hours=1),
    )
    midpoint = _seed_posts(
        brand,
        total=1,
        authors=1,
        created_at=AS_OF - timedelta(hours=12),
    )[0]
    at_as_of = _seed_posts(
        brand,
        total=1,
        authors=1,
        created_at=AS_OF,
    )[0]
    _seed_posts(
        brand,
        total=1,
        authors=1,
        created_at=AS_OF + timedelta(seconds=1),
    )
    for key in ("buzz_releases", "hands_on_usage"):
        PostTypeKey.objects.create(key=key)
    SentimentKey.objects.create(key="positive")
    for key in ("buzz_releases", "hands_on_usage"):
        PostBrandSignal.objects.create(
            post=recent[0],
            brand=brand,
            post_type_id=key,
            sentiment_id="positive",
        )

    packet = build_trend_fact_packet(1, as_of=AS_OF)

    assert packet["narrative_type"] == "leader"
    assert packet["primary_brand"]["recent_posts"] == 20
    assert packet["primary_brand"]["earlier_posts"] == 1
    assert midpoint.created_at == AS_OF - timedelta(hours=12)
    assert at_as_of.created_at == AS_OF


def test_contested_boundary_accepts_100_to_80_but_not_100_to_79():
    leader = _brand("leader")
    exact = _brand("runner_80")
    below = _brand("runner_79")
    _seed_coverage_anchor(leader)
    _seed_posts(leader, total=100, authors=10, created_at=AS_OF - timedelta(hours=1))
    _seed_posts(exact, total=80, authors=10, created_at=AS_OF - timedelta(hours=2))
    _seed_posts(below, total=79, authors=10, created_at=AS_OF - timedelta(hours=3))

    packet = build_trend_fact_packet(1, as_of=AS_OF)
    assert packet["narrative_type"] == "contested"
    assert _key(packet["primary_brand"]) == "leader"
    assert _key(packet["secondary_brand"]) == "runner_80"

    PostBrand.objects.filter(brand=exact).delete()
    packet = build_trend_fact_packet(1, as_of=AS_OF)
    assert packet["narrative_type"] == "leader"
    assert packet["secondary_brand"] is None


def test_exact_count_tie_is_broken_by_canonical_brand_key():
    zeta = _brand("zeta")
    alpha = _brand("alpha")
    _seed_coverage_anchor(zeta)
    _seed_posts(zeta, total=20, authors=10, created_at=AS_OF - timedelta(hours=1))
    _seed_posts(alpha, total=20, authors=10, created_at=AS_OF - timedelta(hours=2))

    packet = build_trend_fact_packet(1, as_of=AS_OF)

    assert packet["narrative_type"] == "contested"
    assert _key(packet["primary_brand"]) == "alpha"
    assert _key(packet["secondary_brand"]) == "zeta"


def test_both_post_and_distinct_author_floors_are_required():
    too_few_posts = _brand("few_posts")
    too_few_authors = _brand("few_authors")
    _seed_coverage_anchor(too_few_posts)
    _seed_posts(
        too_few_posts,
        total=19,
        authors=10,
        created_at=AS_OF - timedelta(hours=1),
    )
    _seed_posts(
        too_few_authors,
        total=20,
        authors=9,
        created_at=AS_OF - timedelta(hours=2),
    )

    packet = build_trend_fact_packet(1, as_of=AS_OF)

    assert packet["narrative_type"] == "insufficient_data"
    assert packet["primary_brand"] is None


@pytest.mark.parametrize(
    ("recent", "earlier", "expected"),
    [
        (20, 0, "new"),
        (30, 20, "surging"),
        (23, 20, "rising"),
        (34, 40, "steady"),
        (33, 40, "cooling"),
    ],
)
def test_momentum_boundaries(recent: int, earlier: int, expected: str):
    brand = _brand(f"momentum_{expected}")
    coverage_anchor = _brand(f"coverage_{expected}")
    _seed_coverage_anchor(coverage_anchor)
    if earlier:
        _seed_posts(
            brand,
            total=earlier,
            authors=10,
            created_at=AS_OF - timedelta(hours=18),
        )
    _seed_posts(
        brand,
        total=recent,
        authors=10,
        created_at=AS_OF - timedelta(hours=6),
    )

    packet = build_trend_fact_packet(1, as_of=AS_OF)

    assert packet["momentum"] == expected


def test_coverage_below_75_percent_ranks_available_range_without_comparison():
    brand = _brand("partial_year")
    earliest = AS_OF - timedelta(days=270)
    _seed_posts(brand, total=1, authors=1, created_at=earliest)
    _seed_posts(
        brand,
        total=20,
        authors=10,
        created_at=AS_OF - timedelta(days=200),
    )

    packet = build_trend_fact_packet(365, as_of=AS_OF)

    assert packet["coverage"]["state"] == "limited"
    assert packet["coverage"]["ratio"] == "0.739726"
    assert packet["narrative_type"] == "coverage_limited"
    assert _key(packet["primary_brand"]) == "partial_year"
    assert packet["primary_brand"]["selected_posts"] == 21
    assert packet["earlier_leader"] is None
    assert packet["momentum"] is None


def test_coverage_exactly_75_percent_uses_normal_half_window_rules():
    brand = _brand("exact_coverage")
    earliest = AS_OF - timedelta(days=365 * 0.75)
    _seed_posts(brand, total=1, authors=1, created_at=earliest)
    _seed_posts(
        brand,
        total=20,
        authors=10,
        created_at=AS_OF - timedelta(days=10),
    )

    packet = build_trend_fact_packet(365, as_of=AS_OF)

    assert packet["coverage"]["state"] == "sufficient"
    assert packet["coverage"]["ratio"] == "0.750000"
    assert packet["narrative_type"] == "leader"
    assert packet["momentum"] == "surging"


def test_coverage_limited_without_an_eligible_brand_is_insufficient_data():
    brand = _brand("partial_sparse")
    _seed_posts(
        brand,
        total=19,
        authors=10,
        created_at=AS_OF - timedelta(days=10),
    )

    packet = build_trend_fact_packet(365, as_of=AS_OF)

    assert packet["coverage"]["state"] == "limited"
    assert packet["narrative_type"] == "insufficient_data"
    assert packet["primary_brand"] is None
    assert packet["earlier_leader"] is None
    assert packet["momentum"] is None


def test_sentinel_brands_are_excluded_from_coverage_and_ranking():
    real = _brand("real")
    sentinel = _brand("_unattributed", sentinel=True)
    _seed_coverage_anchor(real)
    _seed_posts(real, total=20, authors=10, created_at=AS_OF - timedelta(hours=1))
    _seed_posts(
        sentinel,
        total=100,
        authors=20,
        created_at=AS_OF - timedelta(days=30),
    )

    packet = build_trend_fact_packet(1, as_of=AS_OF)

    assert packet["coverage"]["state"] == "sufficient"
    assert _key(packet["primary_brand"]) == "real"
    assert "_unattributed" not in canonical_fact_json(packet)


def test_packet_and_canonical_json_are_stable_and_json_serializable():
    brand = _brand("unicode_brand")
    _seed_coverage_anchor(brand)
    _seed_posts(brand, total=20, authors=10, created_at=AS_OF - timedelta(hours=1))

    first = build_trend_fact_packet(1, as_of=AS_OF)
    second = build_trend_fact_packet(1, as_of=AS_OF)
    first_json = canonical_fact_json(first)

    assert first == second
    assert first_json == canonical_fact_json(second)
    assert json.loads(first_json) == first
    assert ": " not in first_json
    assert ", " not in first_json
    assert "\\u4e2d" not in first_json


@pytest.mark.parametrize("window_days", [0, 2, 14, 366, True, "1"])
def test_invalid_windows_are_rejected(window_days):
    with pytest.raises(ValueError, match="window_days"):
        build_trend_fact_packet(window_days, as_of=AS_OF)


def test_naive_as_of_is_rejected():
    with pytest.raises(ValueError, match="timezone-aware"):
        build_trend_fact_packet(
            1,
            as_of=datetime(2026, 8, 12, 12, 0),  # noqa: DTZ001 - rejection fixture
        )


def test_non_utc_as_of_is_normalized_to_utc():
    brand = _brand("utc_normalized")
    _seed_coverage_anchor(brand)
    _seed_posts(brand, total=20, authors=10, created_at=AS_OF - timedelta(hours=1))
    tokyo = timezone(timedelta(hours=9))

    packet = build_trend_fact_packet(1, as_of=AS_OF.astimezone(tokyo))

    assert packet["as_of"] == "2026-08-12T12:00:00Z"
    assert packet["window_start"] == "2026-08-11T12:00:00Z"
    assert packet["midpoint"] == "2026-08-12T00:00:00Z"


def test_all_fixed_windows_use_at_most_two_set_based_queries(
    django_assert_max_num_queries,
):
    brand = _brand("bounded")
    _seed_posts(
        brand,
        total=1,
        authors=1,
        created_at=AS_OF - timedelta(days=365),
    )
    _seed_posts(
        brand,
        total=20,
        authors=10,
        created_at=AS_OF - timedelta(hours=1),
    )

    assert ALLOWED_TREND_WINDOWS == frozenset({1, 7, 30, 365})
    for window_days in sorted(ALLOWED_TREND_WINDOWS):
        with django_assert_max_num_queries(2):
            packet = build_trend_fact_packet(window_days, as_of=AS_OF)
        assert _key(packet["primary_brand"]) == "bounded"


def test_thresholds_are_frozen_and_can_be_injected_without_config_imports():
    brand = _brand("injected")
    _seed_coverage_anchor(brand)
    _seed_posts(brand, total=2, authors=2, created_at=AS_OF - timedelta(hours=1))
    thresholds = TrendFactThresholds(min_posts=2, min_authors=2)

    packet = build_trend_fact_packet(1, as_of=AS_OF, thresholds=thresholds)

    assert packet["narrative_type"] == "leader"
    with pytest.raises(AttributeError):
        thresholds.min_posts = 3
