"""PostgreSQL contracts for bounded headline candidate snapshots."""

from __future__ import annotations

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
    PostEnrichmentState,
    PostTypeKey,
    PostUnsanctionedFlag,
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
    TrendSnapshotTransactionError,
    build_editor_batches,
    build_trend_analysis_snapshot,
    canonical_snapshot_json,
    normalized_excerpt,
    project_provider_packet,
    select_dossier_evidence,
    select_trend_candidates,
    text_five_gram_jaccard,
)
from monitor.trend_narrative_facts import TrendFactThresholds

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]

AS_OF = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)


def test_snapshot_brand_cap_fails_before_unbounded_detail_queries():
    Brand.objects.bulk_create([Brand(nickname="cap-alpha"), Brand(nickname="cap-beta")])

    with pytest.raises(
        TrendSnapshotTransactionError, match="trend_snapshot_brand_cap_exceeded"
    ):
        build_trend_analysis_snapshot(1, as_of=AS_OF, brand_cap=1)


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
            "start_at": (AS_OF - timedelta(days=1) + timedelta(minutes=15 * start))
            .isoformat()
            .replace("+00:00", "Z"),
            "end_at": (AS_OF - timedelta(days=1) + timedelta(minutes=15 * (end + 1)))
            .isoformat()
            .replace("+00:00", "Z"),
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


def test_u1_editor_batches_use_every_nonempty_dossier_in_canonical_groups():
    snapshot = {
        "packet_schema_version": 3,
        "window_days": 7,
        "as_of": "2026-08-12T12:00:00Z",
        "baseline_context": {"label": "prior_period"},
        "dossiers": [
            {
                "brand_key": key,
                "outcome": "narrative_eligible" if key != "zero" else "no_content",
                "evidence": [],
            }
            for key in [
                "zeta",
                "alpha",
                "delta",
                "zero",
                "beta",
                "eta",
                "gamma",
                "iota",
                "theta",
                "kappa",
                "lambda",
                "mu",
                "nu",
                "xi",
                "omicron",
                "pi",
                "rho",
                "sigma",
                "tau",
                "upsilon",
                "phi",
                "chi",
            ]
        ],
    }

    batches = build_editor_batches(snapshot)

    assert [batch["manifest_brand_keys"] for batch in batches] == [
        ["alpha", "beta", "chi", "delta", "eta"],
        ["gamma", "iota", "kappa", "lambda", "mu"],
        ["nu", "omicron", "phi", "pi", "rho"],
        ["sigma", "tau", "theta", "upsilon", "xi"],
        ["zeta"],
    ]
    assert all("zero" not in batch["manifest_brand_keys"] for batch in batches)


@pytest.mark.parametrize("cardinality", [1, 2, 3, 4, 5])
def test_u1_editor_batch_preserves_one_to_five_brand_cardinality(cardinality: int):
    snapshot = {
        "packet_schema_version": 3,
        "window_days": 1,
        "as_of": "2026-08-12T12:00:00Z",
        "baseline_context": {"label": "prior_period"},
        "dossiers": [
            {
                "brand_key": f"brand-{index}",
                "outcome": "narrative_eligible",
                "evidence": [],
            }
            for index in range(cardinality)
        ],
    }

    batches = build_editor_batches(snapshot)

    assert len(batches) == 1
    assert len(batches[0]["manifest_brand_keys"]) == cardinality
    assert len(batches[0]["dossiers"]) == cardinality


def test_u1_evidence_reservations_roll_over_without_losing_the_window_target():
    ordinary = [
        {
            "evidence_id": f"ordinary-{index}",
            "source_cluster_id": f"cluster-{index}",
            "created_at": f"2026-08-12T0{index}:00:00Z",
            "first_party_role": "public_opaque",
            "source_flags": {"post_kind": "source_post"},
            "excerpt": f"ordinary evidence {index}",
        }
        for index in range(8)
    ]

    selected, allocation = select_dossier_evidence(7, ordinary)

    assert [row["evidence_id"] for row in selected] == [
        f"ordinary-{index}" for index in range(8)
    ]
    assert allocation == {
        "target_count": 8,
        "first_party_reservation": 3,
        "ordinary_reservation": 5,
        "selected_count": 8,
    }


@pytest.mark.parametrize(
    ("window_days", "target", "first_party_reservation"),
    [(1, 6, 2), (7, 8, 3), (30, 10, 4), (365, 12, 4)],
)
def test_u1_evidence_targets_are_fixed_for_every_supported_window(
    window_days: int, target: int, first_party_reservation: int
):
    rows = [
        {
            "evidence_id": f"e-{index}",
            "source_cluster_id": f"c-{index}",
            "first_party_role": "official" if index < target else "public_opaque",
            "source_flags": {"post_kind": "source_post"},
        }
        for index in range(target + 2)
    ]

    selected, allocation = select_dossier_evidence(window_days, rows)

    assert len(selected) == target
    assert allocation["target_count"] == target
    assert allocation["first_party_reservation"] == first_party_reservation
    assert allocation["ordinary_reservation"] == target - first_party_reservation


def test_u1_evidence_reservation_rolls_ordinary_capacity_to_first_party():
    rows = [
        {
            "evidence_id": f"staff-{index}",
            "source_cluster_id": f"staff-cluster-{index}",
            "first_party_role": "staff",
            "source_flags": {"post_kind": "source_post"},
        }
        for index in range(8)
    ] + [
        {
            "evidence_id": "ordinary-0",
            "source_cluster_id": "ordinary-cluster-0",
            "first_party_role": "public_opaque",
            "source_flags": {"post_kind": "source_post"},
        },
        {
            "evidence_id": "ordinary-1",
            "source_cluster_id": "ordinary-cluster-1",
            "first_party_role": "public_opaque",
            "source_flags": {"post_kind": "source_post"},
        },
    ]

    selected, allocation = select_dossier_evidence(7, rows)

    assert len(selected) == 8
    assert sum(row["first_party_role"] == "staff" for row in selected) == 6
    assert allocation["selected_count"] == 8


def test_u1_dedupe_keeps_one_near_identical_evidence_cluster():
    pool = [
        {
            "evidence_id": "first",
            "source_cluster_id": "first",
            "excerpt": "The Ox Alpha model launch is available today",
        },
        {
            "evidence_id": "second",
            "source_cluster_id": "second",
            "excerpt": "The Ox Alpha model launch is available today!",
        },
    ]

    trend_candidates._assign_text_clusters("alpha:full_window", pool)
    selected, _ = select_dossier_evidence(1, pool)

    assert len(selected) == 1
    assert selected[0]["evidence_id"] == "first"


def test_u1_provider_packet_excludes_private_arrays_and_ordinary_identity():
    ordinary = trend_candidates._evidence_candidate(
        {
            "candidate_id": "alpha:full_window",
            "tweet_id": "raw-post-id",
            "author_id": "raw-author-id",
            "author_handle": "ordinary_handle",
            "text": "ordinary discussion",
            "text_en": "ordinary discussion",
            "text_zh_cn": "普通讨论",
            "lang": "en",
            "created_at": AS_OF,
            "quoted_text": None,
            "quoted_status_id": None,
            "is_retweet": False,
            "is_quote": False,
            "is_official": False,
            "first_party_role": "official",
            "classification_status": "succeeded",
            "post_type_keys": ["buzz_releases"],
            "discourse_keys": ["comparison"],
            "sentiment_keys": ["positive"],
            "china_nationalism_keys": ["none"],
            "us_nationalism_keys": ["mild_pro"],
            "unsanctioned_flag_keys": ["misinformation"],
        }
    )
    assert ordinary is not None
    provider = trend_candidates._provider_dossier(
        {
            "brand_key": "alpha",
            "raw_series": {"fine": [1, 2]},
            "aggregate_inputs": {"private": True},
            "source_row_provenance": {"post": "raw-post-id"},
            "evidence_selection_provenance": {"author": "raw-author-id"},
            "evidence": [ordinary],
        }
    )
    evidence = provider["evidence"][0]

    assert "raw_series" not in provider
    assert "aggregate_inputs" not in provider
    assert "author_group_id" not in evidence
    assert "source_cluster_id" not in evidence
    assert "handle_snapshot" not in evidence
    assert evidence["first_party_role"] == "public_opaque"
    assert evidence["taxonomy"] == {
        "post_types": {"status": "available", "values": ["buzz_releases"]},
        "discourse_roles": {"status": "available", "values": ["comparison"]},
        "china_nationalism": {"status": "available", "values": ["none"]},
        "us_nationalism": {"status": "available", "values": ["mild_pro"]},
        "unsanctioned_flags": {"status": "available", "values": ["misinformation"]},
        "language": {"status": "available", "values": ["en"]},
        "sentiment": {"status": "available", "values": ["positive"]},
        "account_role": {"status": "available", "values": ["public_opaque"]},
    }


def test_u1_packet_compaction_preserves_each_evidence_target_or_fails_safe():
    dossiers = []
    for brand_index in range(5):
        evidence = [
            {
                "evidence_id": f"e-{brand_index}-{evidence_index}",
                "excerpt": "x" * 2_000,
                "text_en": "y" * 2_000,
                "text_zh_cn": "中" * 2_000,
            }
            for evidence_index in range(12)
        ]
        dossiers.append(
            {
                "brand_key": f"brand-{brand_index}",
                "outcome": "narrative_eligible",
                "evidence": evidence,
            }
        )
    snapshot = {
        "packet_schema_version": 3,
        "window_days": 365,
        "as_of": "2026-08-12T12:00:00Z",
        "baseline_context": {"label": "prior_period"},
        "dossiers": dossiers,
    }

    batch = build_editor_batches(snapshot)[0]

    assert [len(dossier["evidence"]) for dossier in batch["dossiers"]] == [12] * 5
    assert (
        len(canonical_snapshot_json(batch).encode("utf-8")) <= MAX_PROVIDER_PACKET_BYTES
    )


def test_u1_corpus_phrase_summary_keeps_unseen_phrase_separate_from_taxonomy():
    summary = trend_candidates._corpus_phrase_family_fact(
        [
            {
                "phrase": "ox alpha",
                "prevalence": 4,
                "prior_prevalence": 1,
            }
        ],
        selected_basis=10,
    )

    assert summary["status"] == "available"
    assert summary["labels"] == [
        {
            "key": "ox alpha",
            "selected_count": 4,
            "prior_count": 1,
            "selected_basis_count": 10,
            "prior_basis_count": 0,
            "brand_change_pp": "3",
        }
    ]


def test_u1_corpus_phrase_summary_exposes_atomic_resource_limit():
    summary = trend_candidates._corpus_phrase_family_fact(
        [],
        selected_basis=10,
        extraction_status="resource_limited",
    )

    assert summary == {
        "status": "unavailable",
        "unavailable_reason": "resource_limited",
        "selected_basis_count": 10,
        "labels": [],
    }


def test_u1_shape_summary_replaces_raw_array_with_dominant_late_transition():
    series = [
        {
            "start_at": f"2026-08-{day:02d}T00:00:00+00:00",
            "post_count": count,
        }
        for day, count in zip(range(20, 25), [1, 1, 1, 1, 10], strict=True)
    ]

    summary = trend_candidates._compact_shape_summary(series)

    assert summary["direction"] == "increase"
    assert summary["total_change_pct"] == "900.0"
    assert summary["dominant_transition"] == {
        "from": "2026-08-23T00:00:00+00:00",
        "to": "2026-08-24T00:00:00+00:00",
        "post_count_change": 9,
        "net_change_share_pct": "100.0",
    }
    assert summary["peak"]["post_count"] == 10
    assert summary["trough"]["post_count"] == 1


def test_u1_shape_summary_locates_an_early_change_without_raw_buckets():
    series = [
        {
            "start_at": f"2026-08-{day:02d}T00:00:00+00:00",
            "post_count": count,
        }
        for day, count in zip(range(20, 25), [10, 11, 11, 11, 11], strict=True)
    ]

    summary = trend_candidates._compact_shape_summary(series)

    assert summary["total_change_pct"] == "10.0"
    assert summary["dominant_transition"]["from"] == "2026-08-20T00:00:00+00:00"
    assert summary["dominant_transition"]["to"] == "2026-08-21T00:00:00+00:00"
    assert summary["dominant_transition"]["net_change_share_pct"] == "100.0"


def test_u1_citable_facts_cover_volume_mix_and_first_party_quantities():
    facts = trend_candidates._compact_citable_facts(
        "deepseek",
        {
            "volume": {
                "selected_count": 145,
                "prior_count": 100,
                "change_pct": "45.0",
            },
            "post_type": {
                "labels": [
                    {
                        "key": "buzz_releases",
                        "selected_count": 52,
                        "prior_count": 12,
                        "selected_basis_count": 145,
                        "prior_basis_count": 100,
                        "selected_prevalence": "0.358621",
                        "prior_prevalence": "0.12",
                        "brand_change_pp": "23.8621",
                    }
                ]
            },
            "sentiment": {
                "labels": [
                    {
                        "key": "positive",
                        "selected_count": 80,
                        "prior_count": 42,
                        "selected_basis_count": 145,
                        "prior_basis_count": 100,
                        "selected_prevalence": "0.551724",
                        "prior_prevalence": "0.42",
                        "brand_change_pp": "13.1724",
                    }
                ]
            },
            "account_role": {
                "labels": [
                    {"key": "official", "selected_count": 1, "prior_count": 0},
                    {"key": "staff", "selected_count": 3, "prior_count": 1},
                ]
            },
        },
    )
    by_metric = {fact["metric"]: fact for fact in facts}

    assert by_metric["post_count_change_pct"]["display_en"] == "45%"
    assert by_metric["buzz_releases_share_change_pp"]["display_en"] == "24 pts"
    assert by_metric["positive_share_change_pp"]["display_en"] == "13 pts"
    assert by_metric["official_staff_post_count"]["display_en"] == "4 posts"
    assert all(fact["fact_id"].startswith("f:deepseek:") for fact in facts)


def test_u1_corpus_query_finds_overlapping_unseen_phrase_in_full_posts():
    brand = Brand.objects.create(nickname="zhipu_phrase")
    account = Account.objects.create(author_id="phrase-author", handle="phrase")
    posts = [
        Post.objects.create(
            tweet_id=f"phrase-post-{index}",
            author=account,
            created_at=AS_OF - timedelta(minutes=10 - index),
            text=f"Zhipu update {index}: Ox Alpha release is drawing attention",
        )
        for index in range(3)
    ]
    PostBrand.objects.bulk_create([PostBrand(post=post, brand=brand) for post in posts])

    with CaptureQueriesContext(connection) as queries:
        signals_by_brand, status = trend_candidates._fetch_corpus_phrase_signals(
            [
                {
                    "candidate_id": f"{brand.nickname}:full_window",
                    "brand_key": brand.nickname,
                    "start_at": AS_OF - timedelta(days=1),
                    "end_at": AS_OF,
                }
            ],
            as_of=AS_OF,
        )
    signals = signals_by_brand[brand.nickname]

    ox_alpha = next(signal for signal in signals if signal["phrase"] == "ox alpha")
    assert ox_alpha["prevalence"] == 3
    assert "ox alpha" in ox_alpha["representative_excerpt"]
    assert status == "available"
    assert len(queries) == 1
    source_sql = queries[0]["sql"].casefold()
    assert "regexp_split_to_table" not in source_sql
    assert "lead(" not in source_sql
    assert "p.created_at >=" in source_sql


def test_u1_corpus_query_has_exact_multi_brand_current_prior_ranking():
    primary = Brand.objects.create(nickname="exact_primary")
    peer = Brand.objects.create(nickname="exact_peer")
    account = Account.objects.create(author_id="exact-author", handle="exact")
    window_start = AS_OF - timedelta(days=1)
    rows = [
        ("exact-prior", primary, window_start - timedelta(hours=12), "legacy theme"),
        ("exact-early", primary, window_start + timedelta(hours=1), "legacy theme"),
        ("exact-peer", peer, window_start + timedelta(hours=10), "aa bb"),
        (
            "exact-tie",
            primary,
            window_start + timedelta(hours=12),
            "aa bb cc dd ee ff gg hh ii",
        ),
        ("exact-late", primary, window_start + timedelta(hours=20), "legacy theme"),
    ]
    posts = [
        Post.objects.create(
            tweet_id=tweet_id,
            author=account,
            created_at=created_at,
            text=body,
        )
        for tweet_id, _brand, created_at, body in rows
    ]
    PostBrand.objects.bulk_create(
        [
            PostBrand(post=post, brand=brand)
            for post, (_tweet_id, brand, _created_at, _body) in zip(
                posts, rows, strict=True
            )
        ]
    )

    signals_by_brand, status = trend_candidates._fetch_corpus_phrase_signals(
        [
            {
                "candidate_id": f"{brand.nickname}:full_window",
                "brand_key": brand.nickname,
                "start_at": window_start,
                "end_at": AS_OF,
            }
            for brand in (primary, peer)
        ],
        as_of=AS_OF,
    )

    assert status == "available"
    signals = signals_by_brand[primary.nickname]
    assert [row["phrase"] for row in signals] == [
        "legacy theme",
        "bb cc",
        "cc dd",
        "dd ee",
        "ee ff",
        "ff gg",
        "gg hh",
        "hh ii",
    ]
    assert "aa bb" not in {row["phrase"] for row in signals}
    legacy = signals[0]
    assert legacy["prevalence"] == 2
    assert legacy["prior_prevalence"] == 1
    assert legacy["peer_brand_count"] == 1
    assert legacy["burst_interval"] == {"start_bucket": 0, "end_bucket": 3}
    assert legacy["representative_excerpt"] == "legacy theme"
    assert len(legacy["representative_evidence_ids"]) == 1
    assert signals_by_brand[peer.nickname][0]["peer_brand_count"] == 2


def test_u1_corpus_query_fails_open_atomically_at_source_row_limit(monkeypatch):
    brands = [
        Brand.objects.create(nickname=f"limited_phrase_{index}") for index in range(2)
    ]
    account = Account.objects.create(author_id="limited-author", handle="limited")
    posts = [
        Post.objects.create(
            tweet_id=f"limited-post-{index}",
            author=account,
            created_at=AS_OF - timedelta(minutes=10 - index),
            text=f"Brand {index} has a distinct recurring phrase",
        )
        for index in range(2)
    ]
    PostBrand.objects.bulk_create(
        [
            PostBrand(post=post, brand=brand)
            for post, brand in zip(posts, brands, strict=True)
        ]
    )
    candidates = [
        {
            "candidate_id": f"{brand.nickname}:full_window",
            "brand_key": brand.nickname,
            "start_at": AS_OF - timedelta(days=1),
            "end_at": AS_OF,
        }
        for brand in brands
    ]
    monkeypatch.setattr(trend_candidates, "MAX_CORPUS_SOURCE_ROWS", 1)

    signals, status = trend_candidates._fetch_corpus_phrase_signals(
        candidates,
        as_of=AS_OF,
    )

    assert signals == {}
    assert status == "resource_limited"


@pytest.mark.parametrize(
    ("ceiling_name", "ceiling"),
    [
        ("MAX_CORPUS_SOURCE_TEXT_CHARACTERS", 3),
        ("MAX_CORPUS_TEXT_CHARACTERS", 3),
        ("MAX_CORPUS_DISTINCT_PHRASES_PER_BRAND", 1),
    ],
)
def test_u1_corpus_query_fails_open_at_each_local_resource_ceiling(
    monkeypatch, ceiling_name, ceiling
):
    brand = Brand.objects.create(nickname=f"limited_{ceiling_name.casefold()}")
    account = Account.objects.create(
        author_id=f"author-{ceiling_name}",
        handle=f"handle-{ceiling_name}",
    )
    post = Post.objects.create(
        tweet_id=f"post-{ceiling_name}",
        author=account,
        created_at=AS_OF - timedelta(minutes=5),
        text="one two three",
    )
    PostBrand.objects.create(post=post, brand=brand)
    monkeypatch.setattr(trend_candidates, ceiling_name, ceiling)

    signals, status = trend_candidates._fetch_corpus_phrase_signals(
        [
            {
                "candidate_id": f"{brand.nickname}:full_window",
                "brand_key": brand.nickname,
                "start_at": AS_OF - timedelta(days=1),
                "end_at": AS_OF,
            }
        ],
        as_of=AS_OF,
    )

    assert signals == {}
    assert status == "resource_limited"


def test_u1_corpus_query_fails_open_atomically_at_token_limit(monkeypatch):
    brand = Brand.objects.create(nickname="token_limited_phrase")
    account = Account.objects.create(author_id="token-author", handle="token")
    post = Post.objects.create(
        tweet_id="token-limited-post",
        author=account,
        created_at=AS_OF - timedelta(minutes=5),
        text="one two three four",
    )
    PostBrand.objects.create(post=post, brand=brand)
    monkeypatch.setattr(trend_candidates, "MAX_CORPUS_TOKENS_PER_DOCUMENT", 3)

    signals, status = trend_candidates._fetch_corpus_phrase_signals(
        [
            {
                "candidate_id": f"{brand.nickname}:full_window",
                "brand_key": brand.nickname,
                "start_at": AS_OF - timedelta(days=1),
                "end_at": AS_OF,
            }
        ],
        as_of=AS_OF,
    )

    assert signals == {}
    assert status == "resource_limited"


def test_u1_corpus_query_fails_open_when_top_boundary_tie_is_too_large(monkeypatch):
    brand = Brand.objects.create(nickname="tie_limited_phrase")
    account = Account.objects.create(author_id="tie-author", handle="tie")
    post = Post.objects.create(
        tweet_id="tie-limited-post",
        author=account,
        created_at=AS_OF - timedelta(minutes=5),
        text="one two three four five six",
    )
    PostBrand.objects.create(post=post, brand=brand)
    monkeypatch.setattr(trend_candidates, "MAX_CORPUS_RETAINED_PHRASES", 4)

    signals, status = trend_candidates._fetch_corpus_phrase_signals(
        [
            {
                "candidate_id": f"{brand.nickname}:full_window",
                "brand_key": brand.nickname,
                "start_at": AS_OF - timedelta(days=1),
                "end_at": AS_OF,
            }
        ],
        as_of=AS_OF,
    )

    assert signals == {}
    assert status == "resource_limited"


def test_u1_corpus_documents_normalize_unicode_before_deduping_and_tokenizing():
    spec = {
        "start_at": AS_OF - timedelta(days=1),
        "end_at": AS_OF,
        "upper_at": AS_OF,
        "lower_at": AS_OF - timedelta(days=2),
    }
    rows = [
        (
            "unicode-1",
            "shared-root",
            AS_OF - timedelta(minutes=2),
            "OX e\u0301clair🚀模型 发布",
        ),
        (
            "unicode-2",
            "shared-root",
            AS_OF - timedelta(minutes=1),
            "OX éclair🚀模型 发布",
        ),
    ]

    documents = list(trend_candidates._iter_corpus_documents(rows, spec))

    assert len(documents) == 1
    assert documents[0]["normalized_text"] == "ox éclair 模型 发布"
    assert documents[0]["phrases"] == {
        "ox éclair",
        "éclair 模型",
        "模型 发布",
    }


def test_u1_stable_family_bases_are_not_multiplied_by_multiple_flags():
    brand = Brand.objects.create(nickname="stable_family")
    role = Role.objects.create(key="staff")
    account = Account.objects.create(author_id="stable-author", handle="stable")
    BrandAccount.objects.create(brand=brand, account=account, role=role)
    post = Post.objects.create(
        tweet_id="stable-post",
        author=account,
        created_at=AS_OF - timedelta(minutes=5),
        text="stable family evidence",
        lang="en",
    )
    PostBrand.objects.create(post=post, brand=brand)
    PostEnrichmentState.objects.create(
        post=post,
        translation_status=PostEnrichmentState.Status.SUCCEEDED,
        classification_status=PostEnrichmentState.Status.SUCCEEDED,
    )
    PostUnsanctionedFlag.objects.create(
        post=post,
        flags='["flag_a", "flag_b"]',
        flag_set=["flag_a", "flag_b"],
    )

    facts = trend_candidates._fetch_stable_family_facts(
        [
            {
                "brand_key": brand.nickname,
                "start_at": AS_OF - timedelta(days=1),
                "end_at": AS_OF,
            }
        ]
    )[brand.nickname]

    assert facts["language"]["selected_basis_count"] == 1
    assert facts["account_role"]["selected_basis_count"] == 1
    assert facts["unsanctioned_flags"]["selected_basis_count"] == 1
    assert {
        row["key"]: row["selected_count"]
        for row in facts["unsanctioned_flags"]["labels"]
    } == {"flag_a": 1, "flag_b": 1}


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
    PostBrand.objects.bulk_create([PostBrand(post=post, brand=brand) for post in posts])
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
        if (
            "with requested_bounds as" in normalized
            and "official_accounts as" in normalized
        ):
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
        index
        for index, sql in enumerate(statements)
        if sql.startswith("SET TRANSACTION")
    )
    assert not any(sql.startswith(("SELECT", "WITH")) for sql in statements[:set_index])
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
    assert normalized_evidence_sql.count("CROSS JOIN LATERAL") == 7
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
            normalized_evidence_sql.index(stream_name) : normalized_evidence_sql.index(
                next_name
            )
        ]
        assert "FROM CANDIDATE_POOL POOL" in stream_sql
        assert "FROM POSTS_BRANDS PB" not in stream_sql
        assert stream_sql.count("LIMIT R.RANK_LIMIT") == 1
    assert len(evidence_params) == 6
    assert evidence_params[1] == [brand.nickname]
    assert tuple(evidence_params[-2:]) == (AS_OF, 32)
    # U1 exposes an all-brand compact snapshot rather than the legacy
    # shortlist/candidate projection.  The source rows remain private and the
    # provider view contains a bounded preview only.
    assert snapshot["packet_schema_version"] == 3
    assert [row["brand_key"] for row in snapshot["dossiers"]] == [brand.nickname]
    dossier = snapshot["dossiers"][0]
    # The fixture does not create successful enrichment state, so the compact
    # contract must refuse an editor packet rather than treating raw posts as
    # eligible narrative evidence.
    assert dossier["outcome"] == "data_quality_unavailable"
    assert dossier["evidence_allocation"]["target_count"] == 6
    assert 1 <= len(dossier["evidence"]) <= 6
    provider = project_provider_packet(snapshot)
    assert provider["dossiers"][0].get("raw_series") is None
    assert len(provider["dossiers"][0]["evidence"]) <= 2
    assert raw_author_id not in canonical_snapshot_json(provider)
    assert raw_post_id not in canonical_snapshot_json(provider)

    analysis_statements = [
        sql
        for sql in statements
        if sql.startswith(("SET TRANSACTION", "SELECT", "WITH"))
        and "SET_CONFIG('STATEMENT_TIMEOUT'" not in sql
    ]
    second_brand = Brand.objects.create(nickname="second_snapshot_brand")
    with CaptureQueriesContext(connection) as two_brand_queries:
        two_brand_snapshot = build_trend_analysis_snapshot(
            1,
            as_of=AS_OF,
            thresholds=thresholds,
        )
    two_brand_statements = [
        row["sql"].lstrip().upper()
        for row in two_brand_queries.captured_queries
        if row["sql"].lstrip().upper().startswith(("SET TRANSACTION", "SELECT", "WITH"))
        and "SET_CONFIG('STATEMENT_TIMEOUT'" not in row["sql"].lstrip().upper()
    ]
    assert len(two_brand_statements) == len(analysis_statements)
    assert {row["brand_key"] for row in two_brand_snapshot["dossiers"]} == {
        brand.nickname,
        second_brand.nickname,
    }


def test_snapshot_resource_limit_reaches_provider_without_losing_other_evidence(
    monkeypatch,
):
    _seed_snapshot_posts()
    PostEnrichmentState.objects.bulk_create(
        [
            PostEnrichmentState(
                post=post,
                translation_status=PostEnrichmentState.Status.SUCCEEDED,
                classification_status=PostEnrichmentState.Status.SUCCEEDED,
            )
            for post in Post.objects.all()
        ]
    )
    monkeypatch.setattr(trend_candidates, "MAX_CORPUS_SOURCE_ROWS", 1)
    thresholds = TrendFactThresholds(
        min_posts=2,
        min_authors=2,
        episode_peak_ratio=Decimal(1),
    )

    snapshot = build_trend_analysis_snapshot(
        1,
        as_of=AS_OF,
        thresholds=thresholds,
    )
    provider = project_provider_packet(snapshot)
    editor_batch = build_editor_batches(snapshot)[0]

    for packet in (snapshot, provider, editor_batch):
        dossier = packet["dossiers"][0]
        corpus_family = dossier["family_summaries"]["corpus_phrases"]
        assert dossier["corpus_signals_status"] == "resource_limited"
        assert dossier["corpus_signals"] == []
        assert corpus_family["status"] == "unavailable"
        assert corpus_family["unavailable_reason"] == "resource_limited"
        assert any(fact["family"] == "volume" for fact in dossier["facts"])
        assert dossier["evidence"]
    private_corpus = snapshot["dossiers"][0]["aggregate_inputs"]["corpus_phrases"]
    assert private_corpus["unavailable_reason"] == "resource_limited"


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
            sentiment_id=("bounded_positive" if index < 16 else "bounded_negative"),
        )
        PostBrandDiscourse.objects.create(
            post=post,
            brand=brand,
            discourse_id=("bounded_technical" if index < 16 else "bounded_release"),
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
    assert all(min(int(row[field]) for field in rank_fields) <= 4 for row in rows)
    assert all(1 <= int(row[field]) <= 5 for row in rows for field in rank_fields)
    for field in rank_fields:
        assert sorted(int(row[field]) for row in rows if int(row[field]) <= 4) == [
            1,
            2,
            3,
            4,
        ]
    assert {row["dominant_discourse"] for row in rows} == {"bounded_technical"}
    assert {row["dominant_sentiment"] for row in rows} == {"bounded_positive"}

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

    assert {row["dominant_discourse"] for row in episode_rows} == {"bounded_release"}
    assert {row["dominant_sentiment"] for row in episode_rows} == {"bounded_negative"}


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
    assert (
        not {
            "A shared model launch happened today",
            "A shared model launch happened today!",
        }
        <= selected_excerpts
    )


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
    observed_hours = {datetime.fromisoformat(row["created_at"]).hour for row in lead}
    assert min(observed_hours) <= 2
    assert max(observed_hours) >= 17
    assert len({row["source_cluster_id"] for row in lead}) == len(lead)
    assert len({row["author_group_id"] for row in lead}) == len(lead)

    repeated, repeated_allocations = trend_candidates._select_evidence_with_allocation(
        list(reversed(rows)),
        candidates=candidates,
        policy=policy,
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
    rows = [_adaptive_evidence_row("large:full_window", index) for index in range(300)]

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
    snapshot = {
        "packet_schema_version": 3,
        "window_days": 365,
        "as_of": "2026-08-12T12:00:00Z",
        "baseline_context": {"label": "prior_period"},
        "dossiers": [
            {
                "brand_key": f"brand-{brand_index}",
                "outcome": "narrative_eligible",
                "evidence": [
                    {
                        "evidence_id": f"e-{brand_index}-{evidence_index}",
                        "excerpt": "界" * 1_000,
                        "text_en": "x" * 1_000,
                        "text_zh_cn": "中" * 1_000,
                    }
                    for evidence_index in range(12)
                ],
            }
            for brand_index in range(5)
        ],
    }
    batch = build_editor_batches(snapshot)[0]
    assert (
        len(canonical_snapshot_json(batch).encode("utf-8")) <= MAX_PROVIDER_PACKET_BYTES
    )
    assert [len(row["evidence"]) for row in batch["dossiers"]] == [12] * 5


def test_size_guard_fails_with_a_safe_code():
    oversized = {"value": "x" * MAX_SNAPSHOT_BYTES}

    with pytest.raises(TrendSnapshotSizeError) as exc_info:
        canonical_snapshot_json(oversized, enforce_limit=True)

    assert str(exc_info.value) == "trend_snapshot_too_large"
