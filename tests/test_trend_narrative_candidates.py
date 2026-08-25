"""PostgreSQL contracts for bounded headline candidate snapshots."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

import monitor.trend_narrative_candidates as trend_candidates
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
from monitor.trend_narrative_candidates import (
    MAX_PROVIDER_PACKET_BYTES,
    MAX_SNAPSHOT_BYTES,
    SNAPSHOT_LOCK_TIMEOUT_MS,
    SNAPSHOT_STATEMENT_TIMEOUT_MS,
    EvidenceSelectionPolicy,
    TrendSnapshotSizeError,
    build_trend_analysis_snapshot,
    canonical_snapshot_json,
    normalized_excerpt,
    project_provider_packet,
    select_trend_candidates,
    text_five_gram_jaccard,
)
from monitor.trend_narrative_facts import TrendFactThresholds

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]

AS_OF = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)


def _candidate(
    brand_key: str,
    *,
    episodes: list[tuple[int, int]] | None = None,
) -> dict:
    episode_rows = [
        {
            "episode_id": f"{brand_key}:{start}-{end}",
            "start_bucket_index": start,
            "end_bucket_index": end,
            "start_at": (
                AS_OF - timedelta(days=1) + timedelta(minutes=15 * start)
            ).isoformat().replace("+00:00", "Z"),
            "end_at": (
                AS_OF - timedelta(days=1) + timedelta(minutes=15 * (end + 1))
            ).isoformat().replace("+00:00", "Z"),
            "post_count": 40 - start,
            "peak_post_count": 30 - start,
            "peak_author_count": 12,
            "baseline_post_count": "1.000000",
            "peak_to_baseline": f"{30 - start}.000000",
        }
        for start, end in episodes or []
    ]
    return {
        "candidate_key": {
            "candidate_id": f"{brand_key}:full_window",
            "brand_key": brand_key,
            "kind": "full_window",
            "start_at": "2026-08-11T12:00:00Z",
            "end_at": "2026-08-12T12:00:00Z",
        },
        "display_name_en": brand_key.upper(),
        "display_name_zh_cn": f"中{brand_key}",
        "family_ranks": {},
        "family_facts": {
            "volume": {"selected_count": 20, "change_pct": "10.000000"},
            "engagement": {"selected": {"eligible_count": 20}},
            "post_type": {"labels": []},
            "discourse": {"labels": []},
            "sentiment": {"labels": []},
            "china_nationalism": {"labels": []},
            "us_nationalism": {"labels": []},
        },
        "episodes": episode_rows,
    }


def _facts(candidates: list[dict], rankings: dict[str, list[str]]) -> dict:
    return {
        "schema_version": 2,
        "window_days": 1,
        "as_of": "2026-08-12T12:00:00Z",
        "window_start": "2026-08-11T12:00:00Z",
        "prior_start": "2026-08-10T12:00:00Z",
        "schedule": {
            "coarse": {"bucket_count": 8, "duration_seconds": 10_800},
            "fine": {"bucket_count": 96, "duration_seconds": 900},
        },
        "coverage": {},
        "comparison_allowed": True,
        "thresholds": {},
        "family_rankings": rankings,
        "candidates": candidates,
    }


def test_family_seed_merge_then_round_robin_preserves_diversity():
    candidates = [_candidate("a", episodes=[(2, 3)])] + [
        _candidate(key) for key in "bcdefg"
    ]
    rankings = {
        "volume": ["a:full_window", "b:full_window"],
        "engagement": ["a:full_window", "c:full_window"],
        "post_type": ["a:full_window", "d:full_window"],
        "discourse": ["a:full_window", "e:full_window"],
        "sentiment": ["a:full_window", "f:full_window"],
        "nationalism": ["a:full_window", "g:full_window"],
    }

    selected = select_trend_candidates(_facts(candidates, rankings))

    assert [row["candidate_id"] for row in selected] == [
        "a:2-3",
        "b:full_window",
        "c:full_window",
        "d:full_window",
        "e:full_window",
        "f:full_window",
    ]
    assert [signal["family"] for signal in selected[0]["signals"]] == [
        "volume",
        "engagement",
        "post_type",
        "discourse",
        "sentiment",
        "nationalism",
    ]


def test_volume_stream_reaches_second_brand_before_extra_same_brand_episode():
    candidates = [
        _candidate("alpha", episodes=[(2, 2), (10, 10), (20, 20)]),
        _candidate("beta"),
    ]
    rankings = {
        "volume": ["alpha:full_window", "beta:full_window"],
        "engagement": [],
        "post_type": [],
        "discourse": [],
        "sentiment": [],
        "nationalism": [],
    }

    selected = select_trend_candidates(_facts(candidates, rankings))

    assert [row["candidate_id"] for row in selected] == [
        "alpha:2-2",
        "beta:full_window",
        "alpha:10-10",
        "alpha:20-20",
    ]


def test_normalization_and_near_duplicate_threshold_are_frozen():
    first = normalized_excerpt("  New\u0301\n  model\tlaunch  ")
    second = normalized_excerpt("Néw model launch!")

    assert first == "Neẃ model launch"
    assert len(normalized_excerpt("x" * 1_100)) == 1_000
    assert text_five_gram_jaccard("abcdefghij", "abcdefghij") == Decimal(1)
    assert text_five_gram_jaccard(first, second) < Decimal("0.90")
    assert text_five_gram_jaccard(
        "A shared model launch happened today",
        "A shared model launch happened today!",
    ) >= Decimal("0.90")


def _seed_snapshot_posts() -> tuple[Brand, str, str]:
    brand = Brand.objects.create(
        nickname="snapshot_brand",
        display_name="Snapshot Brand",
        display_name_en="Snapshot Brand",
        display_name_zh_cn="快照品牌",
    )
    official_role = Role.objects.create(key="official")
    raw_author_id = "private-author-identity"
    accounts = [
        Account.objects.create(
            author_id=raw_author_id if index == 0 else f"private-author-{index}",
            handle=f"snapshot-{index}",
        )
        for index in range(3)
    ]
    BrandAccount.objects.create(
        brand=brand,
        account=accounts[0],
        role=official_role,
    )
    raw_post_id = "private-post-identity"
    posts = [
        Post(
            tweet_id=raw_post_id if index == 0 else f"private-post-{index}",
            author=accounts[index],
            created_at=AS_OF - timedelta(minutes=5) + timedelta(seconds=index),
            text=(
                "Snapshot Brand released OffListModel today"
                if index == 0
                else f"Independent reaction {index} to the release"
            ),
            like_count=10 - index,
            metrics_refreshed_at=AS_OF - timedelta(minutes=1),
            is_quote=index == 2,
        )
        for index in range(3)
    ]
    Post.objects.bulk_create(posts)
    PostBrand.objects.bulk_create(
        [PostBrand(post=post, brand=brand) for post in posts]
    )
    PostTypeKey.objects.create(key="reaction")
    SentimentKey.objects.create(key="positive")
    SentimentKey.objects.create(key="negative")
    DiscourseKey.objects.create(key="technical_analysis")
    NationalismKey.objects.create(key="pro")
    NationalismKey.objects.create(key="anti")
    for index, post in enumerate(posts):
        PostBrandSignal.objects.create(
            post=post,
            brand=brand,
            post_type_id="reaction",
            sentiment_id="negative" if index == 2 else "positive",
        )
        PostBrandDiscourse.objects.create(
            post=post,
            brand=brand,
            discourse_id="technical_analysis",
            act_id=1,
            china_nationalism_id="pro",
            us_nationalism_id="anti" if index == 2 else "pro",
        )
    pure_repost = Post.objects.create(
        tweet_id="private-repost-id",
        author=accounts[1],
        created_at=AS_OF - timedelta(minutes=4),
        text="RT @source copied release text",
        is_retweet=True,
        like_count=999,
        metrics_refreshed_at=AS_OF - timedelta(minutes=1),
    )
    PostBrand.objects.create(post=pure_repost, brand=brand)
    return brand, raw_author_id, raw_post_id


def test_snapshot_build_is_repeatable_read_bounded_and_redacted(caplog, monkeypatch):
    def forbid_harvest(*args, **kwargs):
        raise AssertionError("headline snapshot must not invoke harvesting")

    monkeypatch.setattr("monitor.cycle.CycleRunner.run", forbid_harvest)
    brand, raw_author_id, raw_post_id = _seed_snapshot_posts()
    thresholds = TrendFactThresholds(
        min_posts=2,
        min_authors=2,
        episode_peak_ratio=Decimal(1),
    )

    evidence_queries = []

    def capture_evidence_query(execute, sql, params, many, context):
        normalized = sql.casefold()
        if "with requested_bounds as" in normalized and "official_accounts as" in normalized:
            evidence_queries.append((sql, params))
        return execute(sql, params, many, context)

    with (
        connection.execute_wrapper(capture_evidence_query),
        CaptureQueriesContext(connection) as queries,
    ):
        snapshot = build_trend_analysis_snapshot(
            1,
            as_of=AS_OF,
            thresholds=thresholds,
        )

    statements = [row["sql"].lstrip().upper() for row in queries.captured_queries]
    set_index = next(
        index for index, sql in enumerate(statements) if sql.startswith("SET TRANSACTION")
    )
    assert not any(
        sql.startswith(("SELECT", "WITH")) for sql in statements[:set_index]
    )
    assert "REPEATABLE READ" in statements[set_index]
    assert "READ ONLY" in statements[set_index]
    timeout_statement = next(
        sql for sql in statements if "SET_CONFIG('STATEMENT_TIMEOUT'" in sql
    )
    assert str(SNAPSHOT_STATEMENT_TIMEOUT_MS) in timeout_statement
    assert str(SNAPSHOT_LOCK_TIMEOUT_MS) in timeout_statement
    assert len(evidence_queries) == 1
    evidence_sql, evidence_params = evidence_queries[0]
    normalized_evidence_sql = " ".join(evidence_sql.upper().split())
    pool_position = normalized_evidence_sql.index("CANDIDATE_POOL AS")
    official_position = normalized_evidence_sql.index("OFFICIAL_STREAM AS")
    assert "GENERATE_SERIES(0, 3)" in normalized_evidence_sql
    assert normalized_evidence_sql.count("CROSS JOIN LATERAL") == 6
    assert normalized_evidence_sql.count("LIMIT BUCKET.RANK_LIMIT") == 1
    assert pool_position < official_position
    stream_bounds = (
        ("OFFICIAL_STREAM AS", "CATALYST_STREAM AS"),
        ("CATALYST_STREAM AS", "ORIGINAL_STREAM AS"),
        ("ORIGINAL_STREAM AS", "EVIDENCE_SEED AS"),
        ("DISCOURSE_STREAM AS", "CONTRAST_STREAM AS"),
        ("CONTRAST_STREAM AS", "STREAM_ROWS AS"),
    )
    for stream_name, next_name in stream_bounds:
        stream_sql = normalized_evidence_sql[
            normalized_evidence_sql.index(stream_name) :
            normalized_evidence_sql.index(next_name)
        ]
        assert "FROM CANDIDATE_POOL POOL" in stream_sql
        assert "FROM POSTS_BRANDS PB" not in stream_sql
        assert stream_sql.count("LIMIT R.RANK_LIMIT") == 1
    assert len(evidence_params) == 6
    assert evidence_params[1] == [brand.nickname]
    assert tuple(evidence_params[-2:]) == (AS_OF, 32)
    analysis_statements = [
        sql
        for sql in statements
        if sql.startswith(("SET TRANSACTION", "SELECT", "WITH"))
        and "SET_CONFIG('STATEMENT_TIMEOUT'" not in sql
    ]
    assert len(analysis_statements) == 10
    assert len(snapshot["candidates"]) == 1
    candidate = snapshot["candidates"][0]
    assert candidate["brand_key"] == brand.nickname
    assert 1 <= len(candidate["evidence"]) <= 48
    assert candidate["evidence_allocation"]["selected_count"] == len(
        candidate["evidence"]
    )
    assert candidate["evidence"][0]["roles"][0] == "official_or_catalyst"
    assert all(
        "RT @source" not in evidence["excerpt"]
        for evidence in candidate["evidence"]
    )
    assert any(
        "contrasting_reaction" in evidence["roles"]
        and evidence["source_flags"]["post_kind"] == "quote"
        for evidence in candidate["evidence"]
    )
    assert candidate["evidence_support"]["event_claim_may_be_supported"] is True
    assert (
        candidate["evidence_support"]["evidence_only_entity_may_be_supported"]
        is True
    )
    trajectories = candidate["metadata_trajectories"]
    assert trajectories["post_type"]["coverage_percent"][-1] == 75
    assert trajectories["post_type"]["labels"]["reaction"]["counts"][-1] == 3
    assert trajectories["sentiment"]["labels"]["negative"]["counts"][-1] == 1
    assert trajectories["discourse"]["labels"]["technical_analysis"]["counts"][-1] == 3
    assert trajectories["china_nationalism"]["labels"]["pro"]["counts"][-1] == 3
    assert trajectories["us_nationalism"]["labels"]["anti"]["counts"][-1] == 1

    canonical = canonical_snapshot_json(snapshot)
    provider = project_provider_packet(snapshot)
    provider_json = canonical_snapshot_json(provider)
    assert len(canonical.encode("utf-8")) <= MAX_SNAPSHOT_BYTES
    assert len(provider_json.encode("utf-8")) <= MAX_PROVIDER_PACKET_BYTES
    assert raw_author_id not in canonical
    assert raw_post_id not in canonical
    assert "fine_series" not in provider_json
    assert provider["evidence_policy"]["version"] == "adaptive-v1"
    assert provider["candidates"][0]["evidence_allocation"] == candidate[
        "evidence_allocation"
    ]
    assert provider["candidates"][0]["evidence"][0]["post_type_keys"] == [
        "reaction"
    ]
    assert provider["candidates"][0]["metadata_trajectories"] == trajectories
    assert not caplog.records
    assert json.loads(canonical) == snapshot
    assert not Brand.objects.filter(nickname="OffListModel").exists()

    repeated = build_trend_analysis_snapshot(
        1,
        as_of=AS_OF,
        thresholds=thresholds,
    )
    assert canonical_snapshot_json(repeated) == canonical

    second_brand = Brand.objects.create(nickname="second_snapshot_brand")
    second_accounts = [
        Account.objects.create(
            author_id=f"second-private-author-{index}",
            handle=f"second-snapshot-{index}",
        )
        for index in range(3)
    ]
    second_posts = [
        Post(
            tweet_id=f"second-private-post-{index}",
            author=account,
            created_at=AS_OF - timedelta(minutes=10) + timedelta(seconds=index),
            text=f"Independent second-brand evidence {index}",
        )
        for index, account in enumerate(second_accounts)
    ]
    Post.objects.bulk_create(second_posts)
    PostBrand.objects.bulk_create(
        [PostBrand(post=post, brand=second_brand) for post in second_posts]
    )
    with CaptureQueriesContext(connection) as two_brand_queries:
        two_brand_snapshot = build_trend_analysis_snapshot(
            1,
            as_of=AS_OF,
            thresholds=thresholds,
        )
    two_brand_statements = [
        row["sql"].lstrip().upper()
        for row in two_brand_queries.captured_queries
            if row["sql"].lstrip().upper().startswith(
                ("SET TRANSACTION", "SELECT", "WITH")
            )
            and "SET_CONFIG('STATEMENT_TIMEOUT'"
            not in row["sql"].lstrip().upper()
        ]
    assert len(two_brand_statements) == len(analysis_statements) == 10
    assert len({row["brand_key"] for row in two_brand_snapshot["candidates"]}) == 2


def test_evidence_query_returns_deterministic_per_stream_bounded_ranks():
    brand = Brand.objects.create(nickname="bounded_evidence_brand")
    official_role = Role.objects.create(key="official")
    PostTypeKey.objects.create(key="bounded_reaction")
    SentimentKey.objects.bulk_create(
        [SentimentKey(key="bounded_positive"), SentimentKey(key="bounded_negative")]
    )
    DiscourseKey.objects.bulk_create(
        [
            DiscourseKey(key="bounded_technical"),
            DiscourseKey(key="bounded_release"),
        ]
    )
    accounts = [
        Account.objects.create(
            author_id=f"bounded-author-{index:02d}",
            handle=f"bounded-handle-{index:02d}",
        )
        for index in range(60)
    ]
    BrandAccount.objects.create(brand=brand, account=accounts[0], role=official_role)
    posts = [
        Post(
            tweet_id=f"bounded-post-{index:02d}",
            author=accounts[index],
            created_at=(
                AS_OF - timedelta(hours=24 - index)
                if index < 16
                else AS_OF - timedelta(minutes=60 - (index - 16))
            ),
            text=f"Bounded evidence post {index:02d}",
            like_count=500 if index == 7 else index * 10 if index < 16 else 0,
            metrics_refreshed_at=AS_OF - timedelta(minutes=1),
            is_quote=index % 4 == 0,
        )
        for index in range(60)
    ]
    Post.objects.bulk_create(posts)
    PostBrand.objects.bulk_create([PostBrand(post=post, brand=brand) for post in posts])
    for index, post in enumerate(posts):
        PostBrandSignal.objects.create(
            post=post,
            brand=brand,
            post_type_id="bounded_reaction",
            sentiment_id=(
                "bounded_positive" if index < 16 else "bounded_negative"
            ),
        )
        PostBrandDiscourse.objects.create(
            post=post,
            brand=brand,
            discourse_id=(
                "bounded_technical" if index < 16 else "bounded_release"
            ),
            act_id=1,
        )

    candidate = {
        "candidate_id": "bounded_evidence_brand:full_window",
        "brand_key": brand.nickname,
        "start_at": (AS_OF - timedelta(days=1)).isoformat(),
        "end_at": AS_OF.isoformat(),
    }

    rows = trend_candidates._fetch_evidence_rows(
        [candidate],
        as_of=AS_OF,
        rank_limit=4,
    )
    repeated = trend_candidates._fetch_evidence_rows(
        [candidate],
        as_of=AS_OF,
        rank_limit=4,
    )

    rank_fields = (
        "official_rank",
        "catalyst_rank",
        "original_rank",
        "discourse_rank",
        "contrast_rank",
    )
    assert repeated == rows
    assert len(rows) <= 4 * len(rank_fields)
    assert all(
        min(int(row[field]) for field in rank_fields) <= 4 for row in rows
    )
    assert all(
        1 <= int(row[field]) <= 5 for row in rows for field in rank_fields
    )
    for field in rank_fields:
        assert sorted(
            int(row[field]) for row in rows if int(row[field]) <= 4
        ) == [1, 2, 3, 4]
    assert {row["dominant_discourse"] for row in rows} == {
        "bounded_technical"
    }
    assert {row["dominant_sentiment"] for row in rows} == {
        "bounded_positive"
    }

    episode_rows = trend_candidates._fetch_evidence_rows(
        [
            {
                **candidate,
                "candidate_id": "bounded_evidence_brand:episode",
                "start_at": (AS_OF - timedelta(hours=4)).isoformat(),
            }
        ],
        as_of=AS_OF,
        rank_limit=4,
    )

    assert {row["dominant_discourse"] for row in episode_rows} == {
        "bounded_release"
    }
    assert {row["dominant_sentiment"] for row in episode_rows} == {
        "bounded_negative"
    }


def test_near_duplicate_source_clusters_cannot_fill_two_evidence_roles():
    base = {
        "candidate_id": "alpha:full_window",
        "brand_key": "alpha",
        "quoted_status_id": None,
        "created_at": AS_OF - timedelta(minutes=1),
        "quoted_text": None,
        "is_retweet": False,
        "is_quote": False,
        "metrics_observed": True,
        "interactions": 5,
        "is_official": False,
        "sentiment_keys": [],
        "discourse_keys": [],
        "dominant_discourse": None,
        "dominant_sentiment": None,
        "official_rank": 1,
        "catalyst_rank": 1,
        "original_rank": 1,
        "discourse_rank": 1,
        "contrast_rank": 1,
    }
    rows = [
        {
            **base,
            "tweet_id": "copy-a",
            "author_id": "author-a",
            "text": "A shared model launch happened today",
        },
        {
            **base,
            "tweet_id": "copy-b",
            "author_id": "author-b",
            "text": "A shared model launch happened today!",
            "catalyst_rank": 2,
            "original_rank": 2,
        },
        {
            **base,
            "tweet_id": "independent-c",
            "author_id": "author-c",
            "text": "An independent hands-on reaction",
            "catalyst_rank": 3,
            "original_rank": 3,
        },
    ]

    selected = trend_candidates._select_evidence(rows)["alpha:full_window"]

    assert len({row["source_cluster_id"] for row in selected}) == len(selected)
    selected_excerpts = {row["excerpt"] for row in selected}
    assert not {
        "A shared model launch happened today",
        "A shared model launch happened today!",
    } <= selected_excerpts


def _adaptive_evidence_row(
    candidate_id: str,
    index: int,
    *,
    author_id: str | None = None,
) -> dict:
    hands_on = index % 2 == 0
    positive = index % 3 != 0
    return {
        "candidate_id": candidate_id,
        "brand_key": candidate_id.split(":", 1)[0],
        "tweet_id": f"{candidate_id}-post-{index:02d}",
        "author_id": author_id or f"{candidate_id}-author-{index:02d}",
        "quoted_status_id": None,
        "created_at": AS_OF - timedelta(hours=23) + timedelta(minutes=25 * index),
        "text": (
            "Hands-on users report faster downloads and stronger reasoning "
            f"during workflow-{index} benchmark-{index} device-{index}"
            if hands_on
            else "Release discussion compares model access and pricing "
            f"across region-{index} cohort-{index} plan-{index}"
        ),
        "quoted_text": None,
        "is_retweet": False,
        "is_quote": index % 5 == 0,
        "metrics_observed": True,
        "interactions": 500 - index,
        "is_official": index == 0,
        "post_type_keys": ["hands_on" if hands_on else "release"],
        "sentiment_keys": ["positive" if positive else "negative"],
        "discourse_keys": ["technical_analysis" if hands_on else "release_buzz"],
        "dominant_discourse": "technical_analysis",
        "dominant_sentiment": "positive",
        "official_rank": index + 1,
        "catalyst_rank": index + 1,
        "original_rank": index + 1,
        "discourse_rank": index + 1,
        "contrast_rank": index + 1,
    }


def test_adaptive_evidence_deepens_the_story_leader_and_preserves_strata():
    policy = EvidenceSelectionPolicy(
        version="test-adaptive-v1",
        reservoir_rank_limit=32,
        floor=4,
        lead_ceiling=24,
        comparison_ceiling=8,
        excerpt_characters=600,
        provider_packet_bytes=MAX_PROVIDER_PACKET_BYTES,
    )
    candidates = [
        {
            "candidate_id": "deepseek:full_window",
            "start_at": (AS_OF - timedelta(days=1)).isoformat(),
            "end_at": AS_OF.isoformat(),
            "signals": [
                {"family": "volume", "rank": 1, "stream_position": 1},
                {"family": "discourse", "rank": 1, "stream_position": 1},
                {"family": "sentiment", "rank": 1, "stream_position": 1},
            ],
            "family_facts": {"volume": {"selected_count": 4_000}},
        },
        {
            "candidate_id": "comparison:full_window",
            "start_at": (AS_OF - timedelta(days=1)).isoformat(),
            "end_at": AS_OF.isoformat(),
            "signals": [
                {"family": "volume", "rank": 2, "stream_position": 2},
            ],
            "family_facts": {"volume": {"selected_count": 48}},
        },
    ]
    rows = [
        *[_adaptive_evidence_row("deepseek:full_window", index) for index in range(48)],
        *[
            {
                **_adaptive_evidence_row("comparison:full_window", index),
                "text": (
                    f"Comparison note {index} uses token-{index:02d} "
                    f"channel-{index:02d} subject-{index:02d} source-{index:02d}"
                ),
                "post_type_keys": [],
                "sentiment_keys": [],
                "discourse_keys": [],
                "dominant_discourse": None,
                "dominant_sentiment": None,
            }
            for index in range(12)
        ],
    ]

    selected, allocations = trend_candidates._select_evidence_with_allocation(
        rows,
        candidates=candidates,
        policy=policy,
    )

    lead = selected["deepseek:full_window"]
    comparison = selected["comparison:full_window"]
    assert len(lead) == 24
    assert len(comparison) == 4
    assert allocations["deepseek:full_window"]["allocation_class"] == "lead"
    assert allocations["comparison:full_window"]["allocation_class"] == "floor"
    assert {row["post_type_keys"][0] for row in lead} == {"hands_on", "release"}
    assert {row["sentiment_keys"][0] for row in lead} == {"positive", "negative"}
    assert {row["discourse_keys"][0] for row in lead} == {
        "technical_analysis",
        "release_buzz",
    }
    observed_hours = {
        datetime.fromisoformat(row["created_at"]).hour
        for row in lead
    }
    assert min(observed_hours) <= 2
    assert max(observed_hours) >= 17
    assert len({row["source_cluster_id"] for row in lead}) == len(lead)
    assert len({row["author_group_id"] for row in lead}) == len(lead)

    repeated, repeated_allocations = (
        trend_candidates._select_evidence_with_allocation(
            list(reversed(rows)),
            candidates=candidates,
            policy=policy,
        )
    )
    assert repeated == selected
    assert repeated_allocations == allocations


def test_adaptive_evidence_returns_every_sparse_independent_post():
    policy = EvidenceSelectionPolicy(
        version="test-adaptive-v1",
        reservoir_rank_limit=32,
        floor=4,
        lead_ceiling=48,
        comparison_ceiling=12,
        excerpt_characters=600,
        provider_packet_bytes=MAX_PROVIDER_PACKET_BYTES,
    )
    candidate = {
        "candidate_id": "sparse:full_window",
        "start_at": (AS_OF - timedelta(days=1)).isoformat(),
        "end_at": AS_OF.isoformat(),
        "signals": [{"family": "volume", "rank": 1, "stream_position": 1}],
        "family_facts": {"volume": {"selected_count": 3}},
    }
    rows = [_adaptive_evidence_row("sparse:full_window", index) for index in range(3)]

    selected, allocations = trend_candidates._select_evidence_with_allocation(
        rows,
        candidates=[candidate],
        policy=policy,
    )

    assert len(selected["sparse:full_window"]) == 3
    assert allocations["sparse:full_window"]["selected_count"] == 3
    assert allocations["sparse:full_window"]["target_count"] == 3


def test_same_author_posts_never_create_independent_event_support():
    rows = [
        {
            **_adaptive_evidence_row(
                "one-author:full_window",
                index,
                author_id="same-author",
            ),
            "is_official": False,
        }
        for index in range(12)
    ]

    selected = trend_candidates._select_evidence(rows)["one-author:full_window"]
    support = trend_candidates._evidence_support(selected)

    assert support["distinct_author_group_count"] == 1
    assert support["event_claim_may_be_supported"] is False


def test_high_volume_reservoir_and_final_allocation_remain_bounded():
    policy = EvidenceSelectionPolicy(
        version="test-adaptive-v1",
        reservoir_rank_limit=32,
        floor=4,
        lead_ceiling=48,
        comparison_ceiling=12,
        excerpt_characters=600,
        provider_packet_bytes=MAX_PROVIDER_PACKET_BYTES,
    )
    candidate = {
        "candidate_id": "large:full_window",
        "start_at": (AS_OF - timedelta(days=1)).isoformat(),
        "end_at": AS_OF.isoformat(),
        "signals": [{"family": "volume", "rank": 1, "stream_position": 1}],
        "family_facts": {"volume": {"selected_count": 4_000}},
    }
    rows = [
        _adaptive_evidence_row("large:full_window", index)
        for index in range(300)
    ]

    selected, allocations = trend_candidates._select_evidence_with_allocation(
        rows,
        candidates=[candidate],
        policy=policy,
    )

    allocation = allocations["large:full_window"]
    assert allocation["reservoir_count"] <= 32 * 5
    assert allocation["selected_count"] == len(selected["large:full_window"])
    assert allocation["selected_count"] <= 48


def test_worst_case_snapshot_and_provider_projection_stay_bounded():
    _seed_snapshot_posts()
    base = build_trend_analysis_snapshot(
        1,
        as_of=AS_OF,
        thresholds=TrendFactThresholds(
            min_posts=2,
            min_authors=2,
            episode_peak_ratio=Decimal(1),
        ),
    )
    worst = deepcopy(base)
    worst["window_days"] = 365
    worst["series_axis"]["fine"]["bucket_count"] = 365
    worst["series_axis"]["fine"]["starts"] = [
        f"2025-08-{(index % 28) + 1:02d}T00:00:00Z" for index in range(365)
    ]
    worst["series_axis"]["fine"]["ends"] = [
        f"2025-08-{(index % 28) + 1:02d}T23:59:59Z" for index in range(365)
    ]
    template = worst["candidates"][0]
    candidates = []
    for candidate_index in range(6):
        candidate = deepcopy(template)
        candidate["candidate_id"] = f"brand-{candidate_index}:full_window"
        candidate["source_candidate_id"] = candidate["candidate_id"]
        candidate["brand_key"] = f"brand-{candidate_index}"
        for key, values in candidate["series"]["fine"].items():
            if key == "engagement":
                continue
            candidate["series"]["fine"][key] = (values * 4)[:365]
        engagement = candidate["series"]["fine"]["engagement"]
        for key, values in engagement.items():
            if key == "post_kinds":
                continue
            engagement[key] = (values * 4)[:365]
        for values in engagement["post_kinds"].values():
            for key, array in values.items():
                values[key] = (array * 4)[:365]
        target_count = 48 if candidate_index == 0 else 12
        candidate["evidence"] = [
            {
                **deepcopy(template["evidence"][0]),
                "evidence_id": f"e_{candidate_index}_{evidence_index}",
                "source_cluster_id": f"sc_{candidate_index}_{evidence_index}",
                "author_group_id": f"ag_{candidate_index}_{evidence_index}",
                "excerpt": "界" * 1_000,
            }
            for evidence_index in range(target_count)
        ]
        candidate["evidence_allocation"] = {
            "policy_version": "adaptive-v1",
            "allocation_class": "lead" if candidate_index == 0 else "comparison",
            "story_rank": candidate_index + 1,
            "reservoir_count": target_count,
            "available_independent_source_count": target_count,
            "protected_floor_count": 4,
            "target_count": target_count,
            "selected_count": target_count,
            "packet_trimmed_count": 0,
        }
        candidates.append(candidate)
    worst["candidates"] = candidates
    worst["selection"]["candidate_count"] = 6

    trend_candidates._fit_snapshot_evidence_to_packet_budget(
        worst,
        max_bytes=MAX_PROVIDER_PACKET_BYTES,
    )

    snapshot_bytes = len(canonical_snapshot_json(worst).encode("utf-8"))
    provider_bytes = len(
        canonical_snapshot_json(project_provider_packet(worst)).encode("utf-8")
    )

    assert snapshot_bytes <= MAX_SNAPSHOT_BYTES
    assert provider_bytes <= MAX_PROVIDER_PACKET_BYTES
    assert sum(
        candidate["evidence_allocation"]["packet_trimmed_count"]
        for candidate in worst["candidates"]
    ) > 0
    assert len(worst["candidates"][0]["evidence"]) >= len(
        worst["candidates"][1]["evidence"]
    )


def test_size_guard_fails_with_a_safe_code():
    oversized = {"value": "x" * MAX_SNAPSHOT_BYTES}

    with pytest.raises(TrendSnapshotSizeError) as exc_info:
        canonical_snapshot_json(oversized, enforce_limit=True)

    assert str(exc_info.value) == "trend_snapshot_too_large"
