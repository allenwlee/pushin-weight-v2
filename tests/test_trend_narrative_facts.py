"""PostgreSQL contract tests for deterministic headline trend facts."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from itertools import count
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

import monitor.trend_narrative_facts as trend_facts
from core.models import (
    Account,
    Brand,
    DiscourseKey,
    HarvestBacklogWindow,
    NationalismKey,
    Post,
    PostBrand,
    PostBrandDiscourse,
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


def _candidate(facts: dict, brand_key: str) -> dict:
    return next(
        candidate
        for candidate in facts["candidates"]
        if candidate["candidate_key"]["brand_key"] == brand_key
    )


def _label(candidate: dict, family: str, key: str) -> dict:
    return next(
        label
        for label in candidate["family_facts"][family]["labels"]
        if label["key"] == key
    )


def test_u1_all_brand_aggregate_keeps_zero_post_brand_and_enrichment_count():
    populated = _brand("u1_populated")
    zero = _brand("u1_zero")
    _brand("u1_sentinel", sentinel=True)
    _seed_posts(
        populated,
        total=1,
        authors=1,
        created_at=AS_OF - timedelta(hours=1),
        prefix="u1-populated",
    )

    facts = trend_facts.aggregate_trend_family_facts(1, as_of=AS_OF)
    zero_candidate = _candidate(facts, zero.nickname)

    assert [
        row["candidate_key"]["brand_key"] for row in facts["candidates"]
    ] == [populated.nickname, zero.nickname]
    assert zero_candidate["family_facts"]["volume"] == {
        "selected_count": 0,
        "selected_authors": 0,
        "selected_usable_raw_count": 0,
        "selected_translation_succeeded_count": 0,
        "selected_classification_succeeded_count": 0,
        "selected_enriched_count": 0,
        "newest_30m_count": 0,
        "newest_30m_translation_succeeded_count": 0,
        "newest_30m_classification_succeeded_count": 0,
        "newest_30m_enriched_count": 0,
        "prior_count": 0,
        "prior_authors": 0,
        "change_pct": None,
        "comparison_state": "unavailable",
    }


def test_u1_partial_metadata_share_uses_the_classified_subset():
    family = trend_facts._metadata_family_fact(
        brand_key="partial_brand",
        family="sentiment",
        keys=["positive"],
        counts={
            ("partial_brand", "sentiment", "positive"): (2, 1),
            ("__market__", "sentiment", "positive"): (3, 2),
        },
        coverage={
            ("partial_brand", "sentiment"): (4, 2),
            ("__market__", "sentiment"): (6, 4),
        },
        selected_basis=10,
        prior_basis=8,
        comparison_allowed=True,
    )

    assert family["selected_total_count"] == 10
    assert family["selected_covered_count"] == 4
    assert family["labels"][0]["selected_basis_count"] == 4
    assert family["labels"][0]["selected_prevalence"] == "0.500000"
    assert family["labels"][0]["brand_change_pp"] == "0.000000"


def test_u1_market_coverage_dedupes_multiple_discourse_acts_per_post():
    brand = _brand("multi_act_coverage")
    current = _seed_posts(
        brand,
        total=1,
        authors=1,
        created_at=AS_OF - timedelta(hours=1),
        prefix="multi-act-current",
    )[0]
    prior = _seed_posts(
        brand,
        total=1,
        authors=1,
        created_at=AS_OF - timedelta(days=1, hours=1),
        prefix="multi-act-prior",
    )[0]
    DiscourseKey.objects.bulk_create(
        [DiscourseKey(key="comparison"), DiscourseKey(key="technical_analysis")]
    )
    PostBrandDiscourse.objects.bulk_create(
        [
            PostBrandDiscourse(
                post=current,
                brand=brand,
                discourse_id="comparison",
                act_id=0,
            ),
            PostBrandDiscourse(
                post=current,
                brand=brand,
                discourse_id="technical_analysis",
                act_id=1,
            ),
            PostBrandDiscourse(
                post=prior,
                brand=brand,
                discourse_id="comparison",
                act_id=0,
            ),
        ]
    )

    _counts, coverage = trend_facts._metadata_counts(
        candidate_keys=[brand.nickname],
        prior_start=AS_OF - timedelta(days=2),
        window_start=AS_OF - timedelta(days=1),
        as_of=AS_OF,
    )

    assert coverage[("__market__", "discourse")] == (1, 1)


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


def test_u1_aggregate_operation_returns_ranked_full_window_candidate():
    brand = _brand("u1_ranked")
    _seed_posts(
        brand,
        total=20,
        authors=10,
        created_at=AS_OF - timedelta(hours=1),
    )

    facts = trend_facts.aggregate_trend_family_facts(1, as_of=AS_OF)

    assert facts["candidates"][0]["candidate_key"] == {
        "candidate_id": "u1_ranked:full_window",
        "brand_key": "u1_ranked",
        "kind": "full_window",
        "start_at": "2026-08-11T12:00:00Z",
        "end_at": "2026-08-12T12:00:00Z",
    }
    assert facts["candidates"][0]["family_ranks"]["volume"] == 1
    assert facts["family_rankings"] == {
        "volume": ["u1_ranked:full_window"],
        "engagement": [],
        "post_type": [],
        "discourse": [],
        "sentiment": [],
        "nationalism": [],
    }


def test_u1_aggregate_does_not_materialize_detail_series(monkeypatch):
    brand = _brand("aggregate_without_detail")
    _seed_posts(
        brand,
        total=20,
        authors=10,
        created_at=AS_OF - timedelta(hours=1),
    )

    def fail_detail_fetch(*args, **kwargs):
        raise AssertionError("aggregate ranking must not fetch complete detail series")

    monkeypatch.setattr(
        trend_facts,
        "_fetch_trend_candidate_series",
        fail_detail_fetch,
    )

    facts = trend_facts.aggregate_trend_family_facts(1, as_of=AS_OF)

    assert facts["family_rankings"]["volume"] == [
        "aggregate_without_detail:full_window"
    ]


def test_u1_aggregate_excludes_metrics_observed_after_cutoff():
    brand = _brand("future_aggregate_metric")
    posts = _seed_posts(
        brand,
        total=20,
        authors=10,
        created_at=AS_OF - timedelta(hours=1),
    )
    Post.objects.filter(pk=posts[0].pk).update(
        like_count=99,
        metrics_refreshed_at=AS_OF + timedelta(minutes=1),
    )

    candidate = _candidate(
        trend_facts.aggregate_trend_family_facts(1, as_of=AS_OF),
        brand.nickname,
    )
    engagement = candidate["family_facts"]["engagement"]["selected"]

    assert engagement["eligible_count"] == 0
    assert engagement["missing_count"] == 20
    assert engagement["totals"] is None
    assert engagement["timing"] == {
        "earliest_refreshed_at": None,
        "latest_refreshed_at": None,
    }


@pytest.mark.parametrize(
    ("window_days", "coarse_count", "fine_count", "coarse_seconds", "fine_seconds"),
    [
        (1, 8, 96, 3 * 60 * 60, 15 * 60),
        (7, 7, 168, 24 * 60 * 60, 60 * 60),
        (30, 10, 30, 3 * 24 * 60 * 60, 24 * 60 * 60),
        (365, 12, 365, 2_628_000, 24 * 60 * 60),
    ],
)
def test_u1_all_windows_return_complete_zero_filled_coarse_and_fine_series(
    window_days: int,
    coarse_count: int,
    fine_count: int,
    coarse_seconds: int,
    fine_seconds: int,
):
    brand = _brand(f"series_{window_days}")
    _seed_posts(
        brand,
        total=1,
        authors=1,
        created_at=AS_OF - timedelta(minutes=1),
    )

    details = trend_facts.fetch_trend_candidate_series(
        window_days,
        as_of=AS_OF,
        candidate_keys=[brand.nickname],
    )
    candidate = details["candidates"][0]

    assert details["schedule"] == {
        "coarse": {
            "bucket_count": coarse_count,
            "duration_seconds": coarse_seconds,
        },
        "fine": {
            "bucket_count": fine_count,
            "duration_seconds": fine_seconds,
        },
    }
    assert len(candidate["coarse_series"]) == coarse_count
    assert len(candidate["fine_series"]) == fine_count
    assert sum(bucket["post_count"] for bucket in candidate["fine_series"]) == 1
    assert candidate["fine_series"][0]["index"] == 0
    assert candidate["fine_series"][-1]["index"] == fine_count - 1


def test_u1_equal_endpoints_with_different_paths_keep_distinct_vectors():
    first = _brand("path_alpha")
    second = _brand("path_beta")
    window_start = AS_OF - timedelta(days=1)
    for brand, middle_minutes in ((first, 6 * 60), (second, 12 * 60)):
        for index, offset in enumerate((1, middle_minutes, 24 * 60 - 1)):
            _seed_posts(
                brand,
                total=1,
                authors=1,
                created_at=window_start + timedelta(minutes=offset),
                prefix=f"{brand.nickname}-{index}",
            )

    details = trend_facts.fetch_trend_candidate_series(
        1,
        as_of=AS_OF,
        candidate_keys=[first.nickname, second.nickname],
    )
    vectors = {
        row["candidate_key"]["brand_key"]: [
            bucket["post_count"] for bucket in row["fine_series"]
        ]
        for row in details["candidates"]
    }

    assert vectors["path_alpha"][0] == vectors["path_beta"][0] == 1
    assert vectors["path_alpha"][-1] == vectors["path_beta"][-1] == 1
    assert vectors["path_alpha"] != vectors["path_beta"]


def test_u1_one_day_spike_survives_inside_365_day_fine_series():
    brand = _brand("year_spike")
    spike_at = AS_OF - timedelta(days=200)
    _seed_posts(brand, total=20, authors=10, created_at=spike_at)

    facts = trend_facts.aggregate_trend_family_facts(365, as_of=AS_OF)
    candidate = _candidate(facts, brand.nickname)
    details = trend_facts.fetch_trend_candidate_series(
        365,
        as_of=AS_OF,
        candidate_keys=[candidate["candidate_key"]],
    )

    assert len(candidate["episodes"]) == 1
    assert candidate["episodes"][0]["peak_post_count"] == 20
    assert candidate["episodes"][0]["baseline_post_count"] == "0.000000"
    assert max(
        bucket["post_count"]
        for bucket in details["candidates"][0]["fine_series"]
    ) == 20


def test_u1_complete_365_daily_values_round_trip_without_shape_loss():
    brand = _brand("daily_round_trip")
    window_start = AS_OF - timedelta(days=365)
    for day in range(365):
        if day % 37 == 0:
            _seed_posts(
                brand,
                total=1 + (day == 185),
                authors=1,
                created_at=window_start + timedelta(days=day, hours=1),
                prefix=f"daily-{day}",
            )

    first = trend_facts.fetch_trend_candidate_series(
        365,
        as_of=AS_OF,
        candidate_keys=[brand.nickname],
    )
    serialized = canonical_fact_json(first)

    assert len(first["candidates"][0]["fine_series"]) == 365
    assert json.loads(serialized) == first
    assert canonical_fact_json(
        trend_facts.fetch_trend_candidate_series(
            365,
            as_of=AS_OF,
            candidate_keys=[brand.nickname],
        )
    ) == serialized


def test_u1_adjacent_episode_buckets_merge_and_only_top_three_survive():
    brand = _brand("episode_merge")
    window_start = AS_OF - timedelta(days=1)
    for bucket_index in (2, 3, 10, 20, 30, 40):
        _seed_posts(
            brand,
            total=20,
            authors=10,
            created_at=window_start
            + timedelta(minutes=15 * bucket_index, seconds=1),
            prefix=f"episode-{bucket_index}",
        )

    candidate = _candidate(
        trend_facts.aggregate_trend_family_facts(1, as_of=AS_OF),
        brand.nickname,
    )

    assert len(candidate["episodes"]) == 3
    assert candidate["episodes"][0]["start_bucket_index"] == 2
    assert candidate["episodes"][0]["end_bucket_index"] == 3
    assert candidate["episodes"][0]["post_count"] == 40
    assert [episode["start_bucket_index"] for episode in candidate["episodes"]] == [
        2,
        10,
        20,
    ]


def test_u1_family_rank_ties_use_canonical_brand_key():
    for key in ("zeta_rank", "alpha_rank"):
        brand = _brand(key)
        _seed_posts(
            brand,
            total=20,
            authors=10,
            created_at=AS_OF - timedelta(hours=1),
        )

    facts = trend_facts.aggregate_trend_family_facts(1, as_of=AS_OF)

    assert facts["family_rankings"]["volume"][:2] == [
        "alpha_rank:full_window",
        "zeta_rank:full_window",
    ]
    assert _candidate(facts, "alpha_rank")["family_ranks"]["volume"] == 1
    assert _candidate(facts, "zeta_rank")["family_ranks"]["volume"] == 2


@pytest.mark.parametrize(
    ("earliest_at", "selected_state", "selected_ratio", "prior_state", "prior_ratio"),
    [
        (
            AS_OF - timedelta(days=1, hours=12),
            "sufficient",
            "1.000000",
            "limited",
            "0.500000",
        ),
        (
            AS_OF - timedelta(hours=18),
            "sufficient",
            "0.750000",
            "limited",
            "0.000000",
        ),
    ],
)
def test_u1_selected_and_prior_coverage_gate_independently(
    earliest_at: datetime,
    selected_state: str,
    selected_ratio: str,
    prior_state: str,
    prior_ratio: str,
):
    brand = _brand(f"coverage_gate_{next(_SERIAL)}")
    _seed_posts(
        brand,
        total=20,
        authors=10,
        created_at=AS_OF - timedelta(hours=1),
    )

    facts = trend_facts.aggregate_trend_family_facts(
        1,
        as_of=AS_OF,
        earliest_at=earliest_at,
    )

    assert facts["coverage"]["selected"]["state"] == selected_state
    assert facts["coverage"]["selected"]["ratio"] == selected_ratio
    assert facts["coverage"]["prior"]["state"] == prior_state
    assert facts["coverage"]["prior"]["ratio"] == prior_ratio
    assert facts["comparison_allowed"] is False
    assert _candidate(facts, brand.nickname)["family_facts"]["volume"][
        "change_pct"
    ] is None


def test_u1_injected_minimum_coverage_controls_aggregate_gate():
    brand = _brand("custom_coverage_gate")
    _seed_posts(
        brand,
        total=20,
        authors=10,
        created_at=AS_OF - timedelta(hours=1),
    )

    facts = trend_facts.aggregate_trend_family_facts(
        1,
        as_of=AS_OF,
        earliest_at=AS_OF - timedelta(hours=18),
        thresholds=TrendFactThresholds(minimum_coverage=Decimal("0.90")),
    )

    assert facts["coverage"]["selected"] == {
        "state": "limited",
        "ratio": "0.750000",
        "earliest_at": "2026-08-11T18:00:00Z",
        "known_backlog_overlap": False,
    }
    assert facts["comparison_allowed"] is False


def test_unresolved_harvest_backlog_is_separate_provenance_and_suppresses_comparison():
    brand = _brand("backlog_coverage_gate")
    _seed_posts(
        brand,
        total=20,
        authors=10,
        created_at=AS_OF - timedelta(hours=1),
    )
    _seed_posts(
        brand,
        total=20,
        authors=10,
        created_at=AS_OF - timedelta(days=1, hours=1),
    )
    gap_start = AS_OF - timedelta(hours=6)
    gap_end = AS_OF - timedelta(hours=4)
    backlog = HarvestBacklogWindow.objects.create(
        brand_id="*",
        call_id="B1",
        call_kind="search",
        bucket="",
        query_id="all-models",
        original_since=gap_start,
        original_until=gap_end,
        remaining_since=gap_start,
        remaining_until=gap_end,
        state=HarvestBacklogWindow.State.PENDING,
        reason_code="provider_truncated",
    )

    facts = trend_facts.aggregate_trend_family_facts(
        1,
        as_of=AS_OF,
        earliest_at=AS_OF - timedelta(days=2),
    )

    assert facts["coverage"]["selected"]["known_backlog_overlap"] is True
    assert facts["coverage"]["prior"]["known_backlog_overlap"] is False
    assert facts["comparison_allowed"] is False
    assert facts["comparison_suppressed_reasons"] == [
        "unresolved_harvest_backlog"
    ]
    assert facts["unresolved_backlog_intervals"] == [
        {
            "start_at": gap_start.isoformat().replace("+00:00", "Z"),
            "end_at": gap_end.isoformat().replace("+00:00", "Z"),
            "backlog_window_ids": [backlog.pk],
            "states": ["pending"],
            "reason_codes": ["provider_truncated"],
        }
    ]
    assert _candidate(facts, brand.nickname)["family_facts"]["volume"][
        "change_pct"
    ] is None


def test_u1_multilabel_metadata_uses_distinct_post_brand_bases():
    brand = _brand("multilabel")
    selected = _seed_posts(
        brand,
        total=20,
        authors=10,
        created_at=AS_OF - timedelta(hours=1),
    )
    prior = _seed_posts(
        brand,
        total=20,
        authors=10,
        created_at=AS_OF - timedelta(days=1, hours=1),
    )
    for key in ("release", "usage"):
        PostTypeKey.objects.create(key=key)
    SentimentKey.objects.create(key="positive")
    DiscourseKey.objects.create(key="genuine_hype")
    for post in selected:
        for post_type in ("release", "usage"):
            PostBrandSignal.objects.create(
                post=post,
                brand=brand,
                post_type_id=post_type,
                sentiment_id="positive",
            )
        for act_id in (1, 2):
            PostBrandDiscourse.objects.create(
                post=post,
                brand=brand,
                discourse_id="genuine_hype",
                act_id=act_id,
            )
    for post in prior:
        PostBrandSignal.objects.create(
            post=post,
            brand=brand,
            post_type_id="release",
            sentiment_id="positive",
        )
        PostBrandDiscourse.objects.create(
            post=post,
            brand=brand,
            discourse_id="genuine_hype",
            act_id=1,
        )

    candidate = _candidate(
        trend_facts.aggregate_trend_family_facts(1, as_of=AS_OF),
        brand.nickname,
    )
    release = _label(candidate, "post_type", "release")
    usage = _label(candidate, "post_type", "usage")
    sentiment = _label(candidate, "sentiment", "positive")
    discourse = _label(candidate, "discourse", "genuine_hype")

    assert release["selected_basis_count"] == usage["selected_basis_count"] == 20
    assert release["selected_count"] == usage["selected_count"] == 20
    assert release["selected_prevalence"] == usage["selected_prevalence"] == "1.000000"
    assert Decimal(release["selected_prevalence"]) + Decimal(
        usage["selected_prevalence"]
    ) == Decimal("2.000000")
    assert sentiment["selected_count"] == sentiment["selected_basis_count"] == 20
    assert discourse["selected_count"] == discourse["selected_basis_count"] == 20


def test_u1_nationalism_axes_are_independent_and_constructive_is_not_anti():
    target = _brand("nationalism_target")
    market = _brand("nationalism_market")
    target_selected = _seed_posts(
        target,
        total=20,
        authors=10,
        created_at=AS_OF - timedelta(hours=1),
    )
    target_prior = _seed_posts(
        target,
        total=20,
        authors=10,
        created_at=AS_OF - timedelta(days=1, hours=1),
    )
    market_selected = _seed_posts(
        market,
        total=20,
        authors=10,
        created_at=AS_OF - timedelta(hours=2),
    )
    market_prior = _seed_posts(
        market,
        total=20,
        authors=10,
        created_at=AS_OF - timedelta(days=1, hours=2),
    )
    DiscourseKey.objects.create(key="analysis")
    for key in ("none", "pro", "constructive_critical", "anti"):
        NationalismKey.objects.create(key=key)

    def add(rows, brand, china: str, us: str):
        for post in rows:
            PostBrandDiscourse.objects.create(
                post=post,
                brand=brand,
                discourse_id="analysis",
                act_id=1,
                china_nationalism_id=china,
                us_nationalism_id=us,
            )

    add(target_selected, target, "constructive_critical", "pro")
    add(target_prior, target, "anti", "none")
    add(market_selected, market, "none", "none")
    add(market_prior, market, "none", "none")

    candidate = _candidate(
        trend_facts.aggregate_trend_family_facts(
            1,
            as_of=AS_OF,
            earliest_at=AS_OF - timedelta(days=2),
        ),
        target.nickname,
    )
    constructive = _label(
        candidate, "china_nationalism", "constructive_critical"
    )
    china_anti = _label(candidate, "china_nationalism", "anti")
    us_pro = _label(candidate, "us_nationalism", "pro")

    assert constructive["selected_count"] == 20
    assert china_anti["selected_count"] == 0
    assert constructive["brand_change_pp"] == "100.000000"
    assert constructive["market_change_pp"] == "50.000000"
    assert constructive["market_relative_change_pp"] == "50.000000"
    assert us_pro["brand_change_pp"] == "100.000000"
    assert _label(candidate, "us_nationalism", "anti")["selected_count"] == 0


def test_u1_engagement_missing_is_unknown_and_post_kinds_remain_distinct():
    brand = _brand("engagement_kinds")
    posts = _seed_posts(
        brand,
        total=4,
        authors=4,
        created_at=AS_OF - timedelta(hours=1),
    )
    observed_at = AS_OF - timedelta(minutes=1)
    Post.objects.filter(pk=posts[0].pk).update(
        like_count=1,
        retweet_count=0,
        quote_count=0,
        reply_count=0,
        metrics_refreshed_at=observed_at,
    )
    Post.objects.filter(pk=posts[1].pk).update(
        is_retweet=True,
        retweet_count=2,
        metrics_refreshed_at=observed_at,
    )
    Post.objects.filter(pk=posts[2].pk).update(
        is_quote=True,
        quote_count=3,
        metrics_refreshed_at=observed_at,
    )
    Post.objects.filter(pk=posts[3].pk).update(like_count=99)

    details = trend_facts.fetch_trend_candidate_series(
        1,
        as_of=AS_OF,
        candidate_keys=[brand.nickname],
    )
    populated = next(
        bucket
        for bucket in details["candidates"][0]["fine_series"]
        if bucket["post_count"] == 4
    )
    engagement = populated["engagement"]

    assert engagement["eligible_count"] == 3
    assert engagement["missing_count"] == 1
    assert engagement["coverage_ratio"] == "0.750000"
    assert engagement["totals"] == {
        "likes": 1,
        "reposts": 2,
        "quotes": 3,
        "replies": 0,
        "interactions": 6,
    }
    assert engagement["intensity"] == "2.000000"
    assert engagement["concentration"] == "0.500000"
    assert engagement["by_post_kind"]["source_post"]["eligible_count"] == 1
    assert engagement["by_post_kind"]["source_post"]["missing_count"] == 1
    assert engagement["by_post_kind"]["repost"]["totals"]["reposts"] == 2
    assert engagement["by_post_kind"]["quote"]["totals"]["quotes"] == 3
    assert engagement["timing"]["latest_refreshed_at"] == "2026-08-12T11:59:00Z"
    assert all(
        bucket["engagement"]["totals"] is None
        for bucket in details["candidates"][0]["fine_series"]
        if bucket["post_count"] == 0
    )


def test_u1_engagement_is_attributed_to_creation_not_refresh_bucket():
    brand = _brand("creation_clock")
    created_at = AS_OF - timedelta(hours=6)
    post = _seed_posts(
        brand,
        total=1,
        authors=1,
        created_at=created_at,
    )[0]
    Post.objects.filter(pk=post.pk).update(
        like_count=7,
        metrics_refreshed_at=AS_OF - timedelta(minutes=1),
    )

    series = trend_facts.fetch_trend_candidate_series(
        1,
        as_of=AS_OF,
        candidate_keys=[brand.nickname],
    )["candidates"][0]["fine_series"]
    engagement_bucket = next(
        bucket for bucket in series if bucket["engagement"]["eligible_count"] == 1
    )

    assert engagement_bucket["start_at"] <= _iso(created_at) < engagement_bucket[
        "end_at"
    ]
    assert series[-1]["engagement"]["eligible_count"] == 0


def test_u1_metrics_observed_after_cutoff_remain_unknown():
    brand = _brand("future_metric_observation")
    post = _seed_posts(
        brand,
        total=1,
        authors=1,
        created_at=AS_OF - timedelta(hours=3),
    )[0]
    Post.objects.filter(pk=post.pk).update(
        like_count=99,
        metrics_refreshed_at=AS_OF + timedelta(minutes=1),
    )

    series = trend_facts.fetch_trend_candidate_series(
        1,
        as_of=AS_OF,
        candidate_keys=[brand.nickname],
    )["candidates"][0]["fine_series"]
    bucket = next(row for row in series if row["post_count"] == 1)

    assert bucket["engagement"]["eligible_count"] == 0
    assert bucket["engagement"]["missing_count"] == 1
    assert bucket["engagement"]["totals"] is None


def test_u1_utc_bucket_boundaries_are_dst_independent():
    brand = _brand("dst_stable")
    _seed_posts(
        brand,
        total=1,
        authors=1,
        created_at=AS_OF - timedelta(hours=5, minutes=30),
    )
    new_york_as_of = AS_OF.astimezone(ZoneInfo("America/New_York"))

    utc = trend_facts.fetch_trend_candidate_series(
        1,
        as_of=AS_OF,
        candidate_keys=[brand.nickname],
    )
    local = trend_facts.fetch_trend_candidate_series(
        1,
        as_of=new_york_as_of,
        candidate_keys=[brand.nickname],
    )

    assert local == utc
    assert utc["candidates"][0]["fine_series"][0]["start_at"].endswith("Z")


def test_u1_bounded_candidate_detail_query_count_is_fixed():
    brands = []
    for key in ("query_alpha", "query_beta", "query_gamma"):
        brand = _brand(key)
        brands.append(brand.nickname)
        _seed_posts(
            brand,
            total=1,
            authors=1,
            created_at=AS_OF - timedelta(hours=1),
        )

    with CaptureQueriesContext(connection) as one_candidate:
        trend_facts.fetch_trend_candidate_series(
            1,
            as_of=AS_OF,
            candidate_keys=brands[:1],
            earliest_at=AS_OF - timedelta(days=2),
        )
    with CaptureQueriesContext(connection) as three_candidates:
        trend_facts.fetch_trend_candidate_series(
            1,
            as_of=AS_OF,
            candidate_keys=brands,
            earliest_at=AS_OF - timedelta(days=2),
        )

    assert len(one_candidate) == len(three_candidates) == 2


def test_u1_candidate_detail_set_is_explicitly_bounded():
    with pytest.raises(ValueError, match="at most"):
        trend_facts.fetch_trend_candidate_series(
            1,
            as_of=AS_OF,
            candidate_keys=[
                f"candidate-{index}"
                for index in range(trend_facts.MAX_DETAIL_CANDIDATES + 1)
            ],
        )


def test_u1_fact_module_has_no_provider_or_network_imports():
    source = Path(trend_facts.__file__).read_text(encoding="utf-8")

    assert "trend_narrative_generation" not in source
    assert "anthropic" not in source.casefold()
    assert "requests" not in source
    assert "httpx" not in source
    assert "urllib" not in source


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
