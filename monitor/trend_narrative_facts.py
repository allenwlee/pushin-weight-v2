"""Deterministic, provider-free facts for the V22 headline narrative.

The database chooses aggregate counts; application code applies the product's
ranking and threshold vocabulary.  This module deliberately has no config,
task, HTTP, or LLM dependency so the resulting packet remains reproducible.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from django.db import connection
from django.db.models import Count, Min, Q

from core.models import HarvestBacklogWindow, PostBrand

ALLOWED_TREND_WINDOWS = frozenset({1, 7, 30, 365})
FACT_PACKET_SCHEMA_VERSION = 1
ANALYTICAL_FACT_SCHEMA_VERSION = 2
MAX_DETAIL_CANDIDATES = 12
MAX_EPISODES_PER_CANDIDATE = 3
_RANK_FAMILY_KEYS = (
    "volume",
    "engagement",
    "post_type",
    "discourse",
    "sentiment",
    "nationalism",
)
_METADATA_FAMILY_KEYS = (
    "post_type",
    "discourse",
    "sentiment",
    "china_nationalism",
    "us_nationalism",
)
_POST_KINDS = ("source_post", "repost", "quote")
_EARLIEST_NOT_PROVIDED = object()


@dataclass(frozen=True, slots=True)
class TrendWindowSchedule:
    coarse_bucket_count: int
    coarse_bucket_seconds: int
    fine_bucket_count: int
    fine_bucket_seconds: int

    def as_packet(self) -> dict[str, dict[str, int]]:
        return {
            "coarse": {
                "bucket_count": self.coarse_bucket_count,
                "duration_seconds": self.coarse_bucket_seconds,
            },
            "fine": {
                "bucket_count": self.fine_bucket_count,
                "duration_seconds": self.fine_bucket_seconds,
            },
        }


@dataclass(frozen=True, slots=True)
class TrendCandidateKey:
    """Serializable identity for a full-window or exceptional-episode fact."""

    candidate_id: str
    brand_key: str
    kind: str
    start_at: datetime
    end_at: datetime

    def as_packet(self) -> dict[str, str]:
        return {
            "candidate_id": self.candidate_id,
            "brand_key": self.brand_key,
            "kind": self.kind,
            "start_at": _iso_utc(self.start_at),
            "end_at": _iso_utc(self.end_at),
        }


@dataclass(frozen=True, slots=True)
class TrendFactThresholds:
    """Product-owned defaults, injectable later from the runtime config SSOT."""

    min_posts: int = 20
    min_authors: int = 10
    contested_ratio: Decimal = Decimal("0.80")
    minimum_coverage: Decimal = Decimal("0.75")
    surging_ratio: Decimal = Decimal("1.50")
    rising_ratio: Decimal = Decimal("1.15")
    steady_ratio: Decimal = Decimal("0.85")
    episode_peak_ratio: Decimal = Decimal("3.0")

    def __post_init__(self) -> None:
        if self.min_posts < 1 or self.min_authors < 1:
            raise ValueError("post and author floors must be positive")
        ratios = (
            self.contested_ratio,
            self.minimum_coverage,
            self.surging_ratio,
            self.rising_ratio,
            self.steady_ratio,
            self.episode_peak_ratio,
        )
        if any(not isinstance(value, Decimal) for value in ratios):
            raise TypeError("trend ratios must be Decimal values")
        if not Decimal(0) <= self.contested_ratio <= Decimal(1):
            raise ValueError("contested_ratio must be between zero and one")
        if not Decimal(0) <= self.minimum_coverage <= Decimal(1):
            raise ValueError("minimum_coverage must be between zero and one")
        if not (
            self.surging_ratio
            >= self.rising_ratio
            >= self.steady_ratio
            >= Decimal(0)
        ):
            raise ValueError("momentum ratios must be descending and nonnegative")
        if self.episode_peak_ratio < Decimal(1):
            raise ValueError("episode_peak_ratio must be at least one")


DEFAULT_TREND_THRESHOLDS = TrendFactThresholds()

_WINDOW_SCHEDULES = {
    1: TrendWindowSchedule(8, 3 * 60 * 60, 96, 15 * 60),
    7: TrendWindowSchedule(7, 24 * 60 * 60, 168, 60 * 60),
    30: TrendWindowSchedule(10, 3 * 24 * 60 * 60, 30, 24 * 60 * 60),
    365: TrendWindowSchedule(12, 2_628_000, 365, 24 * 60 * 60),
}


def canonical_fact_json(packet: dict[str, Any]) -> str:
    """Return UTF-8-friendly canonical JSON for hashing and persistence."""
    return json.dumps(
        packet,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def aggregate_trend_family_facts(
    window_days: int,
    *,
    as_of: datetime,
    thresholds: TrendFactThresholds = DEFAULT_TREND_THRESHOLDS,
    earliest_at: datetime | None | object = _EARLIEST_NOT_PROVIDED,
) -> dict[str, Any]:
    """Return set-based rank inputs, metadata changes, and fine episodes.

    The caller owns the surrounding read transaction. Query count is fixed by
    family, not by brand cardinality, and only aggregate rows leave PostgreSQL.
    """
    _validate_window(window_days)
    as_of_utc = _as_utc(as_of)
    window = timedelta(days=window_days)
    window_start = as_of_utc - window
    prior_start = window_start - window
    if earliest_at is _EARLIEST_NOT_PROVIDED:
        earliest_at = earliest_trend_fact_at(as_of=as_of_utc)
    if earliest_at is not None and not isinstance(earliest_at, datetime):
        raise TypeError("earliest_at must be a datetime or None")
    if isinstance(earliest_at, datetime):
        earliest_at = _as_utc(earliest_at)

    selected_coverage = _interval_coverage(
        earliest_at=earliest_at,
        start_at=window_start,
        end_at=as_of_utc,
    )
    prior_coverage = _interval_coverage(
        earliest_at=earliest_at,
        start_at=prior_start,
        end_at=window_start,
    )
    unresolved_backlog_intervals = _unresolved_backlog_intervals(
        start_at=prior_start,
        end_at=as_of_utc,
    )
    selected_backlog_overlap = _intervals_overlap_range(
        unresolved_backlog_intervals,
        start_at=window_start,
        end_at=as_of_utc,
    )
    prior_backlog_overlap = _intervals_overlap_range(
        unresolved_backlog_intervals,
        start_at=prior_start,
        end_at=window_start,
    )
    comparison_allowed = (
        selected_coverage >= thresholds.minimum_coverage
        and prior_coverage >= thresholds.minimum_coverage
        and not selected_backlog_overlap
        and not prior_backlog_overlap
    )

    aggregate_rows = _aggregate_brand_rows(
        prior_start=prior_start,
        window_start=window_start,
        as_of=as_of_utc,
    )
    # The compact narrative contract is not a shortlist: every non-sentinel
    # brand has a full-window fact row, including true zero-post brands.
    all_brand_keys = [str(row["brand_key"]) for row in aggregate_rows]
    episode_rows = _aggregate_episode_rows(
        candidate_keys=all_brand_keys,
        window_start=window_start,
        as_of=as_of_utc,
        schedule=_WINDOW_SCHEDULES[window_days],
        thresholds=thresholds,
    )
    episodes_by_brand: dict[str, list[dict[str, Any]]] = {
        brand_key: [] for brand_key in all_brand_keys
    }
    for episode in episode_rows:
        episodes_by_brand[str(episode["brand_key"])].append(
            _episode_packet(
                episode,
                window_start=window_start,
                fine_bucket_seconds=_WINDOW_SCHEDULES[
                    window_days
                ].fine_bucket_seconds,
            )
        )

    taxonomy = _metadata_taxonomy()
    metadata_counts, metadata_coverage = _metadata_counts(
        candidate_keys=all_brand_keys,
        prior_start=prior_start,
        window_start=window_start,
        as_of=as_of_utc,
    )
    market_selected_basis = sum(
        int(row["selected_posts"] or 0) for row in aggregate_rows
    )
    market_prior_basis = sum(int(row["prior_posts"] or 0) for row in aggregate_rows)

    candidates: list[dict[str, Any]] = []
    scores: dict[str, dict[str, Decimal]] = {
        family: {} for family in _RANK_FAMILY_KEYS
    }
    for row in aggregate_rows:
        brand_key = str(row["brand_key"])
        candidate_id = f"{brand_key}:full_window"
        volume = _volume_fact(row, comparison_allowed=comparison_allowed)
        engagement = _engagement_fact(row, comparison_allowed=comparison_allowed)
        family_facts: dict[str, Any] = {
            "volume": volume,
            "engagement": engagement,
        }
        for family in _METADATA_FAMILY_KEYS:
            family_facts[family] = _metadata_family_fact(
                brand_key=brand_key,
                family=family,
                keys=taxonomy[family],
                counts=metadata_counts,
                coverage=metadata_coverage,
                selected_basis=int(row["selected_posts"] or 0),
                prior_basis=int(row["prior_posts"] or 0),
                market_selected_basis=market_selected_basis,
                market_prior_basis=market_prior_basis,
                comparison_allowed=comparison_allowed,
            )
        candidate = {
            "candidate_key": TrendCandidateKey(
                candidate_id=candidate_id,
                brand_key=brand_key,
                kind="full_window",
                start_at=window_start,
                end_at=as_of_utc,
            ).as_packet(),
            "display_name_en": str(row["display_name_en"] or brand_key),
            "display_name_zh_cn": str(
                row["display_name_zh_cn"] or row["display_name_en"] or brand_key
            ),
            "family_ranks": {},
            "family_facts": family_facts,
            "episodes": episodes_by_brand.get(brand_key, []),
        }
        candidates.append(candidate)
        scores["volume"][candidate_id] = Decimal(int(row["selected_posts"] or 0))
        if engagement["selected"]["eligible_count"]:
            scores["engagement"][candidate_id] = _ranking_score(
                engagement["selected"]["intensity"],
                engagement.get("intensity_change_pct"),
            )
        for family in ("post_type", "discourse", "sentiment"):
            family_score = _labels_ranking_score(
                family_facts[family]["labels"],
                comparison_allowed=comparison_allowed,
            )
            if family_score >= 0:
                scores[family][candidate_id] = family_score
        nationalism_score = max(
            _labels_ranking_score(
                family_facts["china_nationalism"]["labels"],
                comparison_allowed=comparison_allowed,
            ),
            _labels_ranking_score(
                family_facts["us_nationalism"]["labels"],
                comparison_allowed=comparison_allowed,
            ),
        )
        if nationalism_score >= 0:
            scores["nationalism"][candidate_id] = nationalism_score

    by_id = {row["candidate_key"]["candidate_id"]: row for row in candidates}
    family_rankings: dict[str, list[str]] = {}
    for family in _RANK_FAMILY_KEYS:
        ranked_ids = sorted(
            scores[family],
            key=lambda candidate_id: (
                -scores[family][candidate_id],
                by_id[candidate_id]["candidate_key"]["brand_key"].casefold(),
                by_id[candidate_id]["candidate_key"]["brand_key"],
            ),
        )
        family_rankings[family] = ranked_ids
        for rank, candidate_id in enumerate(ranked_ids, start=1):
            by_id[candidate_id]["family_ranks"][family] = rank

    candidates.sort(
        key=lambda row: (
            row["family_ranks"].get("volume", 1_000_000),
            row["candidate_key"]["brand_key"].casefold(),
            row["candidate_key"]["brand_key"],
        )
    )
    return {
        "schema_version": ANALYTICAL_FACT_SCHEMA_VERSION,
        "window_days": window_days,
        "as_of": _iso_utc(as_of_utc),
        "window_start": _iso_utc(window_start),
        "prior_start": _iso_utc(prior_start),
        "schedule": _WINDOW_SCHEDULES[window_days].as_packet(),
        "coverage": {
            "selected": {
                **_coverage_packet(
                    selected_coverage,
                    earliest_at,
                    minimum_coverage=thresholds.minimum_coverage,
                ),
                "known_backlog_overlap": selected_backlog_overlap,
            },
            "prior": {
                **_coverage_packet(
                    prior_coverage,
                    earliest_at,
                    minimum_coverage=thresholds.minimum_coverage,
                ),
                "known_backlog_overlap": prior_backlog_overlap,
            },
        },
        "unresolved_backlog_intervals": unresolved_backlog_intervals,
        "comparison_suppressed_reasons": (
            ["unresolved_harvest_backlog"]
            if selected_backlog_overlap or prior_backlog_overlap
            else []
        ),
        "comparison_allowed": comparison_allowed,
        "thresholds": _analytical_threshold_packet(thresholds),
        "family_rankings": family_rankings,
        "candidates": candidates,
    }


def fetch_trend_candidate_series(
    window_days: int,
    *,
    as_of: datetime,
    candidate_keys: Sequence[str | Mapping[str, Any]],
    earliest_at: datetime | None | object = _EARLIEST_NOT_PROVIDED,
    allow_unbounded: bool = False,
) -> dict[str, Any]:
    """Return complete zero-filled graph series for a candidate set.

    Provider-facing callers use the default bounded form.  The immutable U1
    snapshot explicitly opts into the all-brand form and retains those raw
    series privately; it never projects them across the provider boundary.
    """
    return _fetch_trend_candidate_series(
        window_days,
        as_of=as_of,
        candidate_keys=candidate_keys,
        earliest_at=earliest_at,
        enforce_candidate_limit=not allow_unbounded,
    )


def build_trend_fact_packet(
    window_days: int,
    *,
    as_of: datetime,
    thresholds: TrendFactThresholds = DEFAULT_TREND_THRESHOLDS,
    earliest_at: datetime | None | object = _EARLIEST_NOT_PROVIDED,
) -> dict[str, Any]:
    """Build one canonical market-wide fact packet using at most two queries.

    Query one finds the earliest committed, non-sentinel post-brand edge for
    corpus coverage. Query two returns one aggregate row per non-sentinel brand
    inside the selected half-open window. No post or signal rows are loaded.
    """
    _validate_window(window_days)
    as_of_utc = _as_utc(as_of)
    window_start = as_of_utc - timedelta(days=window_days)
    midpoint = window_start + (as_of_utc - window_start) / 2

    if earliest_at is _EARLIEST_NOT_PROVIDED:
        earliest_at = earliest_trend_fact_at(as_of=as_of_utc)
    if earliest_at is not None and not isinstance(earliest_at, datetime):
        raise TypeError("earliest_at must be a datetime or None")
    coverage_ratio = _coverage_ratio(
        earliest_at=earliest_at,
        window_start=window_start,
        as_of=as_of_utc,
    )
    coverage_limited = coverage_ratio < thresholds.minimum_coverage

    packet = _empty_packet(
        window_days=window_days,
        as_of=as_of_utc,
        window_start=window_start,
        midpoint=midpoint,
        earliest_at=earliest_at,
        coverage_ratio=coverage_ratio,
        coverage_limited=coverage_limited,
        thresholds=thresholds,
    )
    if earliest_at is None:
        return packet

    rows = list(
        PostBrand.objects.filter(
            brand__is_sentinel=False,
            post__created_at__gte=window_start,
            post__created_at__lt=as_of_utc,
        )
        .values(
            "brand_id",
            "brand__display_name",
            "brand__display_name_en",
            "brand__display_name_zh_cn",
        )
        .annotate(
            selected_posts=Count("post_id", distinct=True),
            selected_authors=Count("post__author_id", distinct=True),
            earlier_posts=Count(
                "post_id",
                filter=Q(
                    post__created_at__gte=window_start,
                    post__created_at__lt=midpoint,
                ),
                distinct=True,
            ),
            earlier_authors=Count(
                "post__author_id",
                filter=Q(
                    post__created_at__gte=window_start,
                    post__created_at__lt=midpoint,
                ),
                distinct=True,
            ),
            recent_posts=Count(
                "post_id",
                filter=Q(
                    post__created_at__gte=midpoint,
                    post__created_at__lt=as_of_utc,
                ),
                distinct=True,
            ),
            recent_authors=Count(
                "post__author_id",
                filter=Q(
                    post__created_at__gte=midpoint,
                    post__created_at__lt=as_of_utc,
                ),
                distinct=True,
            ),
        )
    )

    if coverage_limited:
        return _derive_coverage_limited(packet, rows, thresholds)
    return _derive_normal(packet, rows, thresholds)


def earliest_trend_fact_at(*, as_of: datetime) -> datetime | None:
    """Return the shared corpus coverage boundary for one harvest envelope."""
    as_of_utc = _as_utc(as_of)
    return PostBrand.objects.filter(
        brand__is_sentinel=False,
        post__created_at__lt=as_of_utc,
    ).aggregate(earliest_at=Min("post__created_at"))["earliest_at"]


def _fetch_trend_candidate_series(
    window_days: int,
    *,
    as_of: datetime,
    candidate_keys: Sequence[str | Mapping[str, Any]],
    earliest_at: datetime | None | object,
    enforce_candidate_limit: bool,
) -> dict[str, Any]:
    _validate_window(window_days)
    as_of_utc = _as_utc(as_of)
    normalized_keys = _normalize_candidate_keys(candidate_keys)
    if enforce_candidate_limit and len(normalized_keys) > MAX_DETAIL_CANDIDATES:
        raise ValueError(
            f"candidate_keys must contain at most {MAX_DETAIL_CANDIDATES} entries"
        )
    window_start = as_of_utc - timedelta(days=window_days)
    prior_start = window_start - timedelta(days=window_days)
    schedule = _WINDOW_SCHEDULES[window_days]
    if not normalized_keys:
        return {
            "schema_version": ANALYTICAL_FACT_SCHEMA_VERSION,
            "window_days": window_days,
            "as_of": _iso_utc(as_of_utc),
            "window_start": _iso_utc(window_start),
            "schedule": schedule.as_packet(),
            "coverage": {
                "selected": _coverage_packet(Decimal(0), None),
                "prior": _coverage_packet(Decimal(0), None),
            },
            "candidates": [],
        }

    earliest_is_explicit = earliest_at is not _EARLIEST_NOT_PROVIDED
    if earliest_at is not _EARLIEST_NOT_PROVIDED:
        if earliest_at is not None and not isinstance(earliest_at, datetime):
            raise TypeError("earliest_at must be a datetime or None")
        earliest_value = _as_utc(earliest_at) if earliest_at is not None else None
    else:
        earliest_value = None
    rows = _series_rows(
        candidate_keys=normalized_keys,
        window_start=window_start,
        as_of=as_of_utc,
        schedule=schedule,
        earliest_is_explicit=earliest_is_explicit,
        earliest_at=earliest_value,
    )
    metadata_rows = _metadata_series_rows(
        candidate_keys=normalized_keys,
        window_start=window_start,
        as_of=as_of_utc,
        schedule=schedule,
    )
    resolved_earliest = rows[0]["earliest_at"] if rows else earliest_value
    if isinstance(resolved_earliest, datetime):
        resolved_earliest = _as_utc(resolved_earliest)
    selected_coverage = _interval_coverage(
        earliest_at=resolved_earliest,
        start_at=window_start,
        end_at=as_of_utc,
    )
    prior_coverage = _interval_coverage(
        earliest_at=resolved_earliest,
        start_at=prior_start,
        end_at=window_start,
    )

    by_brand: dict[str, dict[str, Any]] = {
        key: {
            "coarse": [],
            "fine": [],
            "metadata": {
                family: {
                    "coverage_counts": [0] * schedule.coarse_bucket_count,
                    "labels": {},
                }
                for family in _METADATA_FAMILY_KEYS
            },
        }
        for key in normalized_keys
    }
    for row in rows:
        resolution = str(row["resolution"])
        index = int(row["bucket_index"])
        seconds = (
            schedule.coarse_bucket_seconds
            if resolution == "coarse"
            else schedule.fine_bucket_seconds
        )
        start_at = window_start + timedelta(seconds=seconds * index)
        end_at = min(as_of_utc, start_at + timedelta(seconds=seconds))
        by_brand[str(row["brand_key"])][resolution].append(
            _series_bucket(row, index=index, start_at=start_at, end_at=end_at)
        )
    for row in metadata_rows:
        brand = by_brand[str(row["brand_key"])]["metadata"]
        family = str(row["family"])
        index = int(row["bucket_index"])
        if row["row_type"] == "coverage":
            brand[family]["coverage_counts"][index] = int(row["value"] or 0)
            continue
        label = str(row["label_key"])
        values = brand[family]["labels"].setdefault(
            label,
            [0] * schedule.coarse_bucket_count,
        )
        values[index] = int(row["value"] or 0)

    candidates = []
    for brand_key in normalized_keys:
        candidates.append(
            {
                "candidate_key": TrendCandidateKey(
                    candidate_id=f"{brand_key}:full_window",
                    brand_key=brand_key,
                    kind="full_window",
                    start_at=window_start,
                    end_at=as_of_utc,
                ).as_packet(),
                "coarse_series": by_brand[brand_key]["coarse"],
                "fine_series": by_brand[brand_key]["fine"],
                "metadata_series": by_brand[brand_key]["metadata"],
            }
        )
    return {
        "schema_version": ANALYTICAL_FACT_SCHEMA_VERSION,
        "window_days": window_days,
        "as_of": _iso_utc(as_of_utc),
        "window_start": _iso_utc(window_start),
        "schedule": schedule.as_packet(),
        "coverage": {
            "selected": _coverage_packet(selected_coverage, resolved_earliest),
            "prior": _coverage_packet(prior_coverage, resolved_earliest),
        },
        "candidates": candidates,
    }


def _normalize_candidate_keys(
    candidate_keys: Sequence[str | Mapping[str, Any]],
) -> list[str]:
    if isinstance(candidate_keys, (str, bytes)):
        raise TypeError("candidate_keys must be a sequence of candidate identities")
    normalized: list[str] = []
    seen: set[str] = set()
    for value in candidate_keys:
        if isinstance(value, str):
            key = value
        elif isinstance(value, Mapping):
            key = str(value.get("brand_key") or "")
        else:
            raise TypeError("candidate identity must be a brand key or mapping")
        if not key or key != key.strip():
            raise ValueError("candidate brand keys must be nonempty and trimmed")
        folded = key.casefold()
        if folded not in seen:
            seen.add(folded)
            normalized.append(key)
    return normalized


def _series_rows(
    *,
    candidate_keys: Sequence[str],
    window_start: datetime,
    as_of: datetime,
    schedule: TrendWindowSchedule,
    earliest_is_explicit: bool,
    earliest_at: datetime | None,
) -> list[dict[str, Any]]:
    sql = """
        WITH requested AS (
            SELECT brand_key, min(position)::integer AS position
            FROM unnest(%s::text[]) WITH ORDINALITY AS item(brand_key, position)
            GROUP BY brand_key
        ),
        schedule(resolution, bucket_count, bucket_seconds) AS (
            VALUES
                ('coarse', %s::integer, %s::integer),
                ('fine', %s::integer, %s::integer)
        ),
        earliest AS (
            SELECT CASE
                WHEN %s::boolean THEN %s::timestamptz
                ELSE min(p.created_at)
            END AS earliest_at
            FROM posts_brands pb
            JOIN posts p ON p.tweet_id = pb.post_id
            JOIN brands b ON b.nickname = pb.brand_id
            WHERE NOT b.is_sentinel AND p.created_at < %s::timestamptz
        ),
        base AS (
            SELECT
                r.brand_key,
                p.tweet_id,
                p.author_id,
                p.created_at,
                p.metrics_refreshed_at,
                (
                    p.metrics_refreshed_at IS NOT NULL
                    AND p.metrics_refreshed_at <= %s::timestamptz
                ) AS metrics_observed,
                coalesce(p.like_count, 0)::bigint AS likes,
                coalesce(p.retweet_count, 0)::bigint AS reposts,
                coalesce(p.quote_count, 0)::bigint AS quotes,
                coalesce(p.reply_count, 0)::bigint AS replies,
                CASE
                    WHEN coalesce(p.is_retweet, false) THEN 'repost'
                    WHEN coalesce(p.is_quote, false) THEN 'quote'
                    ELSE 'source_post'
                END AS post_kind
            FROM requested r
            JOIN posts_brands pb ON pb.brand_id::text = r.brand_key
            JOIN posts p ON p.tweet_id = pb.post_id
            WHERE p.created_at >= %s::timestamptz
              AND p.created_at < %s::timestamptz
        )
        SELECT
            r.position,
            r.brand_key,
            s.resolution,
            bucket.bucket_index,
            e.earliest_at,
            count(b.tweet_id)::integer AS post_count,
            count(DISTINCT b.author_id)::integer AS author_count,
            count(b.tweet_id) FILTER (
                WHERE b.metrics_observed
            )::integer AS eligible_count,
            count(b.tweet_id) FILTER (
                WHERE NOT b.metrics_observed
            )::integer AS missing_count,
            sum(b.likes) FILTER (WHERE b.metrics_observed) AS likes,
            sum(b.reposts) FILTER (WHERE b.metrics_observed) AS reposts,
            sum(b.quotes) FILTER (WHERE b.metrics_observed) AS quotes,
            sum(b.replies) FILTER (WHERE b.metrics_observed) AS replies,
            max(b.likes + b.reposts + b.quotes + b.replies) FILTER (
                WHERE b.metrics_observed
            ) AS top_interactions,
            min(b.metrics_refreshed_at) FILTER (
                WHERE b.metrics_observed
            ) AS earliest_refreshed_at,
            max(b.metrics_refreshed_at) FILTER (
                WHERE b.metrics_observed
            ) AS latest_refreshed_at,
            count(b.tweet_id) FILTER (
                WHERE b.post_kind = 'source_post'
                  AND b.metrics_observed
            )::integer AS source_post_eligible,
            count(b.tweet_id) FILTER (
                WHERE b.post_kind = 'source_post'
                  AND NOT b.metrics_observed
            )::integer AS source_post_missing,
            sum(b.likes) FILTER (WHERE b.post_kind = 'source_post' AND b.metrics_observed) AS source_post_likes,
            sum(b.reposts) FILTER (WHERE b.post_kind = 'source_post' AND b.metrics_observed) AS source_post_reposts,
            sum(b.quotes) FILTER (WHERE b.post_kind = 'source_post' AND b.metrics_observed) AS source_post_quotes,
            sum(b.replies) FILTER (WHERE b.post_kind = 'source_post' AND b.metrics_observed) AS source_post_replies,
            count(b.tweet_id) FILTER (
                WHERE b.post_kind = 'repost' AND b.metrics_observed
            )::integer AS repost_eligible,
            count(b.tweet_id) FILTER (
                WHERE b.post_kind = 'repost' AND NOT b.metrics_observed
            )::integer AS repost_missing,
            sum(b.likes) FILTER (WHERE b.post_kind = 'repost' AND b.metrics_observed) AS repost_likes,
            sum(b.reposts) FILTER (WHERE b.post_kind = 'repost' AND b.metrics_observed) AS repost_reposts,
            sum(b.quotes) FILTER (WHERE b.post_kind = 'repost' AND b.metrics_observed) AS repost_quotes,
            sum(b.replies) FILTER (WHERE b.post_kind = 'repost' AND b.metrics_observed) AS repost_replies,
            count(b.tweet_id) FILTER (
                WHERE b.post_kind = 'quote' AND b.metrics_observed
            )::integer AS quote_eligible,
            count(b.tweet_id) FILTER (
                WHERE b.post_kind = 'quote' AND NOT b.metrics_observed
            )::integer AS quote_missing,
            sum(b.likes) FILTER (WHERE b.post_kind = 'quote' AND b.metrics_observed) AS quote_likes,
            sum(b.reposts) FILTER (WHERE b.post_kind = 'quote' AND b.metrics_observed) AS quote_reposts,
            sum(b.quotes) FILTER (WHERE b.post_kind = 'quote' AND b.metrics_observed) AS quote_quotes,
            sum(b.replies) FILTER (WHERE b.post_kind = 'quote' AND b.metrics_observed) AS quote_replies
        FROM requested r
        CROSS JOIN schedule s
        CROSS JOIN LATERAL generate_series(
            0, s.bucket_count - 1
        ) AS bucket(bucket_index)
        CROSS JOIN earliest e
        LEFT JOIN base b
          ON b.brand_key = r.brand_key
         AND floor(
                extract(epoch FROM (b.created_at - %s::timestamptz))
                / s.bucket_seconds
             )::integer = bucket.bucket_index
        GROUP BY r.position, r.brand_key, s.resolution, bucket.bucket_index,
                 e.earliest_at
        ORDER BY r.position, s.resolution, bucket.bucket_index
    """
    params = [
        list(candidate_keys),
        schedule.coarse_bucket_count,
        schedule.coarse_bucket_seconds,
        schedule.fine_bucket_count,
        schedule.fine_bucket_seconds,
        earliest_is_explicit,
        earliest_at,
        as_of,
        as_of,
        window_start,
        as_of,
        window_start,
    ]
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        return _dict_rows(cursor)


def _metadata_series_rows(
    *,
    candidate_keys: Sequence[str],
    window_start: datetime,
    as_of: datetime,
    schedule: TrendWindowSchedule,
) -> list[dict[str, Any]]:
    sql = """
        WITH requested AS (
            SELECT brand_key, min(position)::integer AS position
            FROM unnest(%s::text[]) WITH ORDINALITY AS item(brand_key, position)
            GROUP BY brand_key
        ),
        base AS (
            SELECT
                r.position,
                r.brand_key,
                p.tweet_id,
                floor(
                    extract(epoch FROM (p.created_at - %s::timestamptz))
                    / %s::integer
                )::integer AS bucket_index
            FROM requested r
            JOIN posts_brands pb ON pb.brand_id::text = r.brand_key
            JOIN posts p ON p.tweet_id = pb.post_id
            WHERE p.created_at >= %s::timestamptz
              AND p.created_at < %s::timestamptz
        ),
        metadata_edges AS (
            SELECT DISTINCT b.position, b.brand_key, b.tweet_id,
                            b.bucket_index, 'post_type'::text AS family,
                            s.post_type_key::text AS label_key
            FROM base b
            JOIN posts_brands_signals s
              ON s.post_id = b.tweet_id
             AND s.brand_id::text = b.brand_key
            UNION ALL
            SELECT DISTINCT b.position, b.brand_key, b.tweet_id,
                            b.bucket_index, 'sentiment'::text,
                            s.sentiment::text
            FROM base b
            JOIN posts_brands_signals s
              ON s.post_id = b.tweet_id
             AND s.brand_id::text = b.brand_key
            UNION ALL
            SELECT DISTINCT b.position, b.brand_key, b.tweet_id,
                            b.bucket_index, 'discourse'::text,
                            d.discourse_key::text
            FROM base b
            JOIN posts_brands_discourse d
              ON d.post_id = b.tweet_id
             AND d.brand_id::text = b.brand_key
            UNION ALL
            SELECT DISTINCT b.position, b.brand_key, b.tweet_id,
                            b.bucket_index, 'china_nationalism'::text,
                            d.china_nationalism::text
            FROM base b
            JOIN posts_brands_discourse d
              ON d.post_id = b.tweet_id
             AND d.brand_id::text = b.brand_key
            WHERE d.china_nationalism IS NOT NULL
            UNION ALL
            SELECT DISTINCT b.position, b.brand_key, b.tweet_id,
                            b.bucket_index, 'us_nationalism'::text,
                            d.us_nationalism::text
            FROM base b
            JOIN posts_brands_discourse d
              ON d.post_id = b.tweet_id
             AND d.brand_id::text = b.brand_key
            WHERE d.us_nationalism IS NOT NULL
        ),
        label_counts AS (
            SELECT position, brand_key, bucket_index, family, label_key,
                   count(DISTINCT tweet_id)::integer AS value
            FROM metadata_edges
            GROUP BY position, brand_key, bucket_index, family, label_key
        ),
        coverage_counts AS (
            SELECT position, brand_key, bucket_index, family,
                   count(DISTINCT tweet_id)::integer AS value
            FROM metadata_edges
            GROUP BY position, brand_key, bucket_index, family
        )
        SELECT 'label'::text AS row_type, position, brand_key, bucket_index,
               family, label_key, value
        FROM label_counts
        UNION ALL
        SELECT 'coverage'::text, position, brand_key, bucket_index,
               family, NULL::text, value
        FROM coverage_counts
        ORDER BY position, brand_key, bucket_index, family, row_type, label_key
    """
    params = [
        list(candidate_keys),
        window_start,
        schedule.coarse_bucket_seconds,
        window_start,
        as_of,
    ]
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        return _dict_rows(cursor)


def _series_bucket(
    row: Mapping[str, Any],
    *,
    index: int,
    start_at: datetime,
    end_at: datetime,
) -> dict[str, Any]:
    post_count = int(row["post_count"] or 0)
    eligible_count = int(row["eligible_count"] or 0)
    missing_count = int(row["missing_count"] or 0)
    totals = _interaction_totals(row, prefix="", eligible_count=eligible_count)
    interactions = totals["interactions"] if totals is not None else 0
    top_interactions = int(row["top_interactions"] or 0)
    by_post_kind = {
        kind: {
            "eligible_count": int(row[f"{kind}_eligible"] or 0),
            "missing_count": int(row[f"{kind}_missing"] or 0),
            "totals": _interaction_totals(
                row,
                prefix=f"{kind}_",
                eligible_count=int(row[f"{kind}_eligible"] or 0),
            ),
        }
        for kind in _POST_KINDS
    }
    return {
        "index": index,
        "start_at": _iso_utc(start_at),
        "end_at": _iso_utc(end_at),
        "post_count": post_count,
        "author_count": int(row["author_count"] or 0),
        "engagement": {
            "eligible_count": eligible_count,
            "missing_count": missing_count,
            "coverage_ratio": _decimal_string(
                _ratio(eligible_count, post_count)
            ),
            "totals": totals,
            "intensity": (
                _decimal_string(Decimal(interactions) / Decimal(eligible_count))
                if eligible_count
                else None
            ),
            "concentration": (
                _decimal_string(
                    Decimal(top_interactions) / Decimal(interactions)
                    if interactions
                    else Decimal(0)
                )
                if eligible_count
                else None
            ),
            "by_post_kind": by_post_kind,
            "timing": {
                "earliest_refreshed_at": _iso_utc(row["earliest_refreshed_at"]),
                "latest_refreshed_at": _iso_utc(row["latest_refreshed_at"]),
            },
        },
    }


def _interaction_totals(
    row: Mapping[str, Any],
    *,
    prefix: str,
    eligible_count: int,
) -> dict[str, int] | None:
    if not eligible_count:
        return None
    likes = int(row[f"{prefix}likes"] or 0)
    reposts = int(row[f"{prefix}reposts"] or 0)
    quotes = int(row[f"{prefix}quotes"] or 0)
    replies = int(row[f"{prefix}replies"] or 0)
    return {
        "likes": likes,
        "reposts": reposts,
        "quotes": quotes,
        "replies": replies,
        "interactions": likes + reposts + quotes + replies,
    }


def _dict_rows(cursor) -> list[dict[str, Any]]:
    names = [column.name for column in cursor.description]
    return [dict(zip(names, values, strict=True)) for values in cursor.fetchall()]


def _aggregate_episode_rows(
    *,
    candidate_keys: Sequence[str],
    window_start: datetime,
    as_of: datetime,
    schedule: TrendWindowSchedule,
    thresholds: TrendFactThresholds,
) -> list[dict[str, Any]]:
    """Detect supported fine-bucket episodes without returning every bucket."""
    if not candidate_keys:
        return []
    sql = """
        WITH requested AS (
            SELECT DISTINCT brand_key
            FROM unnest(%s::text[]) AS item(brand_key)
        ),
        observed AS (
            SELECT
                pb.brand_id::text AS brand_key,
                floor(
                    extract(epoch FROM (p.created_at - %s::timestamptz))
                    / %s::integer
                )::integer AS bucket_index,
                count(*)::integer AS post_count,
                count(DISTINCT p.author_id)::integer AS author_count
            FROM requested r
            JOIN posts_brands pb ON pb.brand_id::text = r.brand_key
            JOIN posts p ON p.tweet_id = pb.post_id
            WHERE p.created_at >= %s::timestamptz
              AND p.created_at < %s::timestamptz
            GROUP BY pb.brand_id, bucket_index
        ),
        buckets AS (
            SELECT
                r.brand_key,
                bucket.bucket_index,
                coalesce(o.post_count, 0)::integer AS post_count,
                coalesce(o.author_count, 0)::integer AS author_count
            FROM requested r
            CROSS JOIN generate_series(
                0, %s::integer - 1
            ) AS bucket(bucket_index)
            LEFT JOIN observed o
              ON o.brand_key = r.brand_key
             AND o.bucket_index = bucket.bucket_index
        ),
        baselines AS (
            SELECT
                brand_key,
                percentile_cont(0.5) WITHIN GROUP (
                    ORDER BY post_count
                )::numeric AS baseline_post_count
            FROM buckets
            GROUP BY brand_key
        ),
        qualifying AS (
            SELECT
                b.*,
                base.baseline_post_count,
                b.bucket_index - row_number() OVER (
                    PARTITION BY b.brand_key ORDER BY b.bucket_index
                )::integer AS episode_group
            FROM buckets b
            JOIN baselines base USING (brand_key)
            WHERE b.post_count >= %s::integer
              AND b.author_count >= %s::integer
              AND b.post_count::numeric
                    / greatest(base.baseline_post_count, 1::numeric)
                  >= %s::numeric
        ),
        grouped AS (
            SELECT
                brand_key,
                episode_group,
                min(bucket_index)::integer AS start_bucket_index,
                max(bucket_index)::integer AS end_bucket_index,
                sum(post_count)::integer AS post_count,
                max(baseline_post_count) AS baseline_post_count
            FROM qualifying
            GROUP BY brand_key, episode_group
        ),
        peaks AS (
            SELECT DISTINCT ON (q.brand_key, q.episode_group)
                q.brand_key,
                q.episode_group,
                q.post_count AS peak_post_count,
                q.author_count AS peak_author_count
            FROM qualifying q
            ORDER BY q.brand_key, q.episode_group,
                     q.post_count DESC, q.author_count DESC,
                     q.bucket_index ASC
        ),
        ranked AS (
            SELECT
                g.*,
                p.peak_post_count,
                p.peak_author_count,
                p.peak_post_count::numeric
                    / greatest(g.baseline_post_count, 1::numeric)
                    AS peak_to_baseline,
                row_number() OVER (
                    PARTITION BY g.brand_key
                    ORDER BY
                        p.peak_post_count::numeric
                            / greatest(g.baseline_post_count, 1::numeric) DESC,
                        g.post_count DESC,
                        g.start_bucket_index ASC
                ) AS episode_rank
            FROM grouped g
            JOIN peaks p USING (brand_key, episode_group)
        )
        SELECT
            brand_key,
            start_bucket_index,
            end_bucket_index,
            post_count,
            peak_post_count,
            peak_author_count,
            baseline_post_count,
            peak_to_baseline
        FROM ranked
        WHERE episode_rank <= %s::integer
        ORDER BY lower(brand_key), brand_key, episode_rank
    """
    params = [
        list(candidate_keys),
        window_start,
        schedule.fine_bucket_seconds,
        window_start,
        as_of,
        schedule.fine_bucket_count,
        thresholds.min_posts,
        thresholds.min_authors,
        thresholds.episode_peak_ratio,
        MAX_EPISODES_PER_CANDIDATE,
    ]
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        return _dict_rows(cursor)


def _episode_packet(
    row: Mapping[str, Any],
    *,
    window_start: datetime,
    fine_bucket_seconds: int,
) -> dict[str, Any]:
    brand_key = str(row["brand_key"])
    start_index = int(row["start_bucket_index"])
    end_index = int(row["end_bucket_index"])
    start_at = window_start + timedelta(seconds=fine_bucket_seconds * start_index)
    end_at = window_start + timedelta(seconds=fine_bucket_seconds * (end_index + 1))
    return {
        "episode_id": f"{brand_key}:{start_index}-{end_index}",
        "start_bucket_index": start_index,
        "end_bucket_index": end_index,
        "start_at": _iso_utc(start_at),
        "end_at": _iso_utc(end_at),
        "post_count": int(row["post_count"]),
        "peak_post_count": int(row["peak_post_count"]),
        "peak_author_count": int(row["peak_author_count"]),
        "baseline_post_count": _decimal_string(
            Decimal(row["baseline_post_count"])
        ),
        "peak_to_baseline": _decimal_string(Decimal(row["peak_to_baseline"])),
    }


def _aggregate_brand_rows(
    *, prior_start: datetime, window_start: datetime, as_of: datetime
) -> list[dict[str, Any]]:
    sql = """
        WITH windowed_posts AS (
            SELECT
                b.nickname::text AS brand_key,
                b.display_name,
                b.display_name_en,
                b.display_name_zh_cn,
                p.tweet_id,
                p.author_id,
                p.created_at >= %s::timestamptz AS is_selected,
                p.metrics_refreshed_at <= %s::timestamptz AS metrics_observed,
                p.metrics_refreshed_at,
                pes.translation_status,
                pes.classification_status,
                coalesce(p.like_count, 0)::bigint AS likes,
                coalesce(p.retweet_count, 0)::bigint AS reposts,
                coalesce(p.quote_count, 0)::bigint AS quotes,
                coalesce(p.reply_count, 0)::bigint AS replies,
                (
                    coalesce(p.like_count, 0)
                    + coalesce(p.retweet_count, 0)
                    + coalesce(p.quote_count, 0)
                    + coalesce(p.reply_count, 0)
                )::bigint AS interactions
            FROM brands b
            LEFT JOIN posts_brands pb ON pb.brand_id = b.nickname
            LEFT JOIN posts p
              ON p.tweet_id = pb.post_id
             AND p.created_at >= %s::timestamptz
             AND p.created_at < %s::timestamptz
            LEFT JOIN post_enrichment_states pes ON pes.post_id = p.tweet_id
            WHERE NOT b.is_sentinel
        )
        SELECT
            brand_key,
            coalesce(display_name_en, display_name, brand_key)
                AS display_name_en,
            coalesce(display_name_zh_cn, display_name_en, display_name,
                     brand_key) AS display_name_zh_cn,
            count(tweet_id) FILTER (WHERE is_selected)::integer
                AS selected_posts,
            count(DISTINCT author_id) FILTER (WHERE is_selected)::integer
                AS selected_authors,
            count(tweet_id) FILTER (
                WHERE is_selected
                  AND translation_status = 'succeeded'
                  AND classification_status = 'succeeded'
            )::integer AS selected_enriched,
            count(tweet_id) FILTER (WHERE NOT is_selected)::integer
                AS prior_posts,
            count(DISTINCT author_id) FILTER (WHERE NOT is_selected)::integer
                AS prior_authors,
            count(tweet_id) FILTER (
                WHERE is_selected AND metrics_observed
            )::integer AS selected_metrics_eligible,
            count(tweet_id) FILTER (
                WHERE NOT is_selected AND metrics_observed
            )::integer AS prior_metrics_eligible,
            sum(likes) FILTER (WHERE is_selected AND metrics_observed)
                AS selected_likes,
            sum(reposts) FILTER (WHERE is_selected AND metrics_observed)
                AS selected_reposts,
            sum(quotes) FILTER (WHERE is_selected AND metrics_observed)
                AS selected_quotes,
            sum(replies) FILTER (WHERE is_selected AND metrics_observed)
                AS selected_replies,
            max(interactions) FILTER (WHERE is_selected AND metrics_observed)
                AS selected_top_interactions,
            min(metrics_refreshed_at) FILTER (
                WHERE is_selected AND metrics_observed
            ) AS selected_earliest_refreshed_at,
            max(metrics_refreshed_at) FILTER (
                WHERE is_selected AND metrics_observed
            ) AS selected_latest_refreshed_at,
            sum(likes) FILTER (WHERE NOT is_selected AND metrics_observed)
                AS prior_likes,
            sum(reposts) FILTER (WHERE NOT is_selected AND metrics_observed)
                AS prior_reposts,
            sum(quotes) FILTER (WHERE NOT is_selected AND metrics_observed)
                AS prior_quotes,
            sum(replies) FILTER (WHERE NOT is_selected AND metrics_observed)
                AS prior_replies,
            max(interactions) FILTER (
                WHERE NOT is_selected AND metrics_observed
            ) AS prior_top_interactions,
            min(metrics_refreshed_at) FILTER (
                WHERE NOT is_selected AND metrics_observed
            ) AS prior_earliest_refreshed_at,
            max(metrics_refreshed_at) FILTER (
                WHERE NOT is_selected AND metrics_observed
            ) AS prior_latest_refreshed_at
        FROM windowed_posts
        GROUP BY brand_key, display_name_en, display_name_zh_cn, display_name
        ORDER BY lower(brand_key), brand_key
    """
    params = [window_start, as_of, prior_start, as_of]
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        return _dict_rows(cursor)


def _metadata_taxonomy() -> dict[str, list[str]]:
    sql = """
        SELECT family, key FROM (
            SELECT 'post_type'::text AS family, key::text FROM post_type_keys
            UNION ALL
            SELECT 'sentiment', key::text FROM sentiment_keys
            UNION ALL
            SELECT 'discourse', key::text FROM discourse_keys
            UNION ALL
            SELECT 'china_nationalism', key::text FROM nationalism_keys
            UNION ALL
            SELECT 'us_nationalism', key::text FROM nationalism_keys
        ) vocabulary
        ORDER BY family, lower(key), key
    """
    result = {family: [] for family in _METADATA_FAMILY_KEYS}
    with connection.cursor() as cursor:
        cursor.execute(sql)
        for family, key in cursor.fetchall():
            result[str(family)].append(str(key))
    return result


def _metadata_counts(
    *,
    candidate_keys: Sequence[str],
    prior_start: datetime,
    window_start: datetime,
    as_of: datetime,
) -> tuple[
    dict[tuple[str, str, str], tuple[int, int]],
    dict[tuple[str, str], tuple[int, int]],
]:
    if not candidate_keys:
        return {}, {}
    sql = """
        WITH requested AS (
            SELECT DISTINCT brand_key
            FROM unnest(%s::text[]) AS item(brand_key)
        ),
        edges AS (
            SELECT
                pb.post_id,
                pb.brand_id::text AS brand_id,
                CASE WHEN p.created_at >= %s::timestamptz
                     THEN 'selected' ELSE 'prior' END AS period
            FROM posts_brands pb
            JOIN posts p ON p.tweet_id = pb.post_id
            JOIN brands b ON b.nickname = pb.brand_id
            WHERE NOT b.is_sentinel
              AND p.created_at >= %s::timestamptz
              AND p.created_at < %s::timestamptz
        ),
        signal_labels AS (
            SELECT DISTINCT
                e.post_id,
                e.brand_id,
                e.period,
                label.family,
                label.label_key
            FROM edges e
            JOIN posts_brands_signals s
              ON s.post_id = e.post_id AND s.brand_id::text = e.brand_id
            CROSS JOIN LATERAL (
                VALUES
                    ('post_type'::text, s.post_type_key::text),
                    ('sentiment'::text, s.sentiment::text)
            ) AS label(family, label_key)
        ),
        discourse_labels AS (
            SELECT DISTINCT
                e.post_id,
                e.brand_id,
                e.period,
                label.family,
                label.label_key
            FROM edges e
            JOIN posts_brands_discourse d
              ON d.post_id = e.post_id AND d.brand_id::text = e.brand_id
            CROSS JOIN LATERAL (
                VALUES
                    ('discourse'::text, d.discourse_key::text),
                    ('china_nationalism'::text,
                     d.china_nationalism::text),
                    ('us_nationalism'::text, d.us_nationalism::text)
            ) AS label(family, label_key)
            WHERE label.label_key IS NOT NULL
        ),
        labels AS (
            SELECT * FROM signal_labels
            UNION ALL
            SELECT * FROM discourse_labels
        ),
        scoped_labels AS (
            SELECT
                l.post_id,
                l.brand_id,
                l.period,
                l.family,
                l.label_key,
                l.brand_id AS scope_key
            FROM labels l
            JOIN requested r ON r.brand_key = l.brand_id
            UNION ALL
            SELECT
                post_id,
                brand_id,
                period,
                family,
                label_key,
                '__market__'::text AS scope_key
            FROM labels
        ),
        label_counts AS (
            SELECT
                scope_key,
                family,
                label_key,
                count(*) FILTER (WHERE period = 'selected')::integer
                    AS selected_count,
                count(*) FILTER (WHERE period = 'prior')::integer
                    AS prior_count
            FROM scoped_labels
            GROUP BY scope_key, family, label_key
        ),
        candidate_family_edges AS (
            SELECT DISTINCT
                l.post_id,
                l.brand_id,
                l.period,
                l.family
            FROM labels l
            JOIN requested r ON r.brand_key = l.brand_id
        ),
        coverage_counts AS (
            SELECT
                brand_id AS scope_key,
                family,
                count(*) FILTER (WHERE period = 'selected')::integer
                    AS selected_count,
                count(*) FILTER (WHERE period = 'prior')::integer
                    AS prior_count
            FROM candidate_family_edges
            GROUP BY brand_id, family
        )
        SELECT 'label' AS row_type, scope_key, family, label_key,
               selected_count, prior_count FROM label_counts
        UNION ALL
        SELECT 'coverage', scope_key, family, '__coverage__',
               selected_count, prior_count FROM coverage_counts
        ORDER BY row_type, scope_key, family, label_key
    """
    params: list[Any] = [list(candidate_keys), window_start, prior_start, as_of]
    counts: dict[tuple[str, str, str], tuple[int, int]] = {}
    coverage: dict[tuple[str, str], tuple[int, int]] = {}
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        for row_type, scope, family, label, selected, prior in cursor.fetchall():
            pair = (int(selected or 0), int(prior or 0))
            if row_type == "coverage":
                coverage[(str(scope), str(family))] = pair
            else:
                counts[(str(scope), str(family), str(label))] = pair
    return counts, coverage


def _volume_fact(
    row: Mapping[str, Any], *, comparison_allowed: bool
) -> dict[str, Any]:
    selected = int(row["selected_posts"] or 0)
    prior = int(row["prior_posts"] or 0)
    change = _percent_change(selected, prior) if comparison_allowed else None
    return {
        "selected_count": selected,
        "selected_authors": int(row["selected_authors"] or 0),
        "selected_enriched_count": int(row["selected_enriched"] or 0),
        "prior_count": prior,
        "prior_authors": int(row["prior_authors"] or 0),
        "change_pct": change,
        "comparison_state": (
            "unavailable"
            if not comparison_allowed
            else "new_or_low_base"
            if prior == 0
            else "available"
        ),
    }


def _engagement_fact(
    row: Mapping[str, Any], *, comparison_allowed: bool
) -> dict[str, Any]:
    selected = _period_engagement(row, prefix="selected")
    prior = _period_engagement(row, prefix="prior")
    change = None
    if (
        comparison_allowed
        and prior["intensity"] is not None
        and Decimal(prior["intensity"]) > 0
        and selected["intensity"] is not None
    ):
        change = _decimal_string(
            (Decimal(selected["intensity"]) / Decimal(prior["intensity"]) - 1)
            * 100
        )
    return {
        "selected": selected,
        "prior": prior,
        "intensity_change_pct": change,
    }


def _period_engagement(
    row: Mapping[str, Any], *, prefix: str
) -> dict[str, Any]:
    total_posts = int(row[f"{prefix}_posts"] or 0)
    eligible = int(row[f"{prefix}_metrics_eligible"] or 0)
    totals = _interaction_totals(
        row,
        prefix=f"{prefix}_",
        eligible_count=eligible,
    )
    interactions = totals["interactions"] if totals is not None else 0
    return {
        "eligible_count": eligible,
        "missing_count": total_posts - eligible,
        "coverage_ratio": _decimal_string(_ratio(eligible, total_posts)),
        "totals": totals,
        "intensity": (
            _decimal_string(Decimal(interactions) / Decimal(eligible))
            if eligible
            else None
        ),
        "concentration": (
            _decimal_string(
                Decimal(int(row[f"{prefix}_top_interactions"] or 0))
                / Decimal(interactions)
                if interactions
                else Decimal(0)
            )
            if eligible
            else None
        ),
        "timing": {
            "earliest_refreshed_at": _iso_utc(
                row[f"{prefix}_earliest_refreshed_at"]
            ),
            "latest_refreshed_at": _iso_utc(
                row[f"{prefix}_latest_refreshed_at"]
            ),
        },
    }


def _metadata_family_fact(
    *,
    brand_key: str,
    family: str,
    keys: Sequence[str],
    counts: Mapping[tuple[str, str, str], tuple[int, int]],
    coverage: Mapping[tuple[str, str], tuple[int, int]],
    selected_basis: int,
    prior_basis: int,
    market_selected_basis: int,
    market_prior_basis: int,
    comparison_allowed: bool,
) -> dict[str, Any]:
    selected_covered, prior_covered = coverage.get((brand_key, family), (0, 0))
    labels = []
    for key in keys:
        selected, prior = counts.get((brand_key, family, key), (0, 0))
        market_selected, market_prior = counts.get(
            ("__market__", family, key), (0, 0)
        )
        selected_prevalence = _ratio(selected, selected_basis)
        prior_prevalence = _ratio(prior, prior_basis)
        market_selected_prevalence = _ratio(
            market_selected, market_selected_basis
        )
        market_prior_prevalence = _ratio(market_prior, market_prior_basis)
        brand_change = (
            (selected_prevalence - prior_prevalence) * 100
            if comparison_allowed
            else None
        )
        market_change = (
            (market_selected_prevalence - market_prior_prevalence) * 100
            if comparison_allowed
            else None
        )
        labels.append(
            {
                "key": key,
                "selected_basis_count": selected_basis,
                "prior_basis_count": prior_basis,
                "selected_count": selected,
                "prior_count": prior,
                "selected_prevalence": _decimal_string(selected_prevalence),
                "prior_prevalence": _decimal_string(prior_prevalence),
                "brand_change_pp": (
                    _decimal_string(brand_change) if brand_change is not None else None
                ),
                "market_change_pp": (
                    _decimal_string(market_change)
                    if market_change is not None
                    else None
                ),
                "market_relative_change_pp": (
                    _decimal_string(brand_change - market_change)
                    if brand_change is not None and market_change is not None
                    else None
                ),
            }
        )
    return {
        "selected_covered_count": selected_covered,
        "prior_covered_count": prior_covered,
        "selected_coverage_ratio": _decimal_string(
            _ratio(selected_covered, selected_basis)
        ),
        "prior_coverage_ratio": _decimal_string(_ratio(prior_covered, prior_basis)),
        "labels": labels,
    }


def _ranking_score(value: str | None, change: str | None) -> Decimal:
    if change is not None:
        return abs(Decimal(change))
    if value is not None:
        return Decimal(value)
    return Decimal(-1)


def _labels_ranking_score(
    labels: Sequence[Mapping[str, Any]], *, comparison_allowed: bool
) -> Decimal:
    if comparison_allowed:
        values = [
            abs(Decimal(str(label["brand_change_pp"])))
            for label in labels
            if label.get("brand_change_pp") is not None
        ]
    else:
        values = [
            Decimal(int(label["selected_count"] or 0))
            for label in labels
            if int(label["selected_count"] or 0) > 0
        ]
    return max(values, default=Decimal(-1))


def _percent_change(selected: int, prior: int) -> str | None:
    if prior <= 0:
        return None
    return _decimal_string((Decimal(selected) / Decimal(prior) - 1) * 100)


def _ratio(numerator: int, denominator: int) -> Decimal:
    if not denominator:
        return Decimal(0)
    return Decimal(numerator) / Decimal(denominator)


def _interval_coverage(
    *, earliest_at: datetime | None, start_at: datetime, end_at: datetime
) -> Decimal:
    return _coverage_ratio(
        earliest_at=earliest_at,
        window_start=start_at,
        as_of=end_at,
    )


def _unresolved_backlog_intervals(
    *,
    start_at: datetime,
    end_at: datetime,
) -> list[dict[str, Any]]:
    rows = HarvestBacklogWindow.objects.filter(
        state__in=[
            HarvestBacklogWindow.State.PENDING,
            HarvestBacklogWindow.State.CLAIMED,
            HarvestBacklogWindow.State.QUARANTINED,
        ],
        remaining_since__lt=end_at,
        remaining_until__gt=start_at,
    ).order_by("remaining_since", "remaining_until", "pk")
    merged: list[dict[str, Any]] = []
    for row in rows:
        interval_start = max(_as_utc(row.remaining_since), start_at)
        interval_end = min(_as_utc(row.remaining_until), end_at)
        if merged and interval_start <= merged[-1]["_end"]:
            current = merged[-1]
            current["_end"] = max(current["_end"], interval_end)
            current["backlog_window_ids"].append(row.pk)
            current["states"].add(str(row.state))
            current["reason_codes"].add(str(row.reason_code))
            continue
        merged.append(
            {
                "_start": interval_start,
                "_end": interval_end,
                "backlog_window_ids": [row.pk],
                "states": {str(row.state)},
                "reason_codes": {str(row.reason_code)},
            }
        )
    return [
        {
            "start_at": _iso_utc(interval["_start"]),
            "end_at": _iso_utc(interval["_end"]),
            "backlog_window_ids": sorted(interval["backlog_window_ids"]),
            "states": sorted(interval["states"]),
            "reason_codes": sorted(interval["reason_codes"]),
        }
        for interval in merged
    ]


def _intervals_overlap_range(
    intervals: Sequence[Mapping[str, Any]],
    *,
    start_at: datetime,
    end_at: datetime,
) -> bool:
    return any(
        _parse_utc(str(interval["start_at"])) < end_at
        and _parse_utc(str(interval["end_at"])) > start_at
        for interval in intervals
    )


def _coverage_packet(
    ratio: Decimal,
    earliest_at: datetime | None,
    *,
    minimum_coverage: Decimal = DEFAULT_TREND_THRESHOLDS.minimum_coverage,
) -> dict[str, Any]:
    return {
        "state": "sufficient" if ratio >= minimum_coverage else "limited",
        "ratio": _decimal_string(ratio),
        "earliest_at": _iso_utc(earliest_at),
    }


def _analytical_threshold_packet(
    thresholds: TrendFactThresholds,
) -> dict[str, Any]:
    return {
        "min_posts": thresholds.min_posts,
        "min_authors": thresholds.min_authors,
        "minimum_coverage": str(thresholds.minimum_coverage),
        "episode_peak_ratio": str(thresholds.episode_peak_ratio),
        "max_episodes_per_candidate": MAX_EPISODES_PER_CANDIDATE,
    }


def _validate_window(window_days: object) -> None:
    if (
        isinstance(window_days, bool)
        or not isinstance(window_days, int)
        or window_days not in ALLOWED_TREND_WINDOWS
    ):
        raise ValueError(
            f"window_days must be one of {sorted(ALLOWED_TREND_WINDOWS)}"
        )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware")
    return value.astimezone(UTC)


def _iso_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_utc(value: str) -> datetime:
    return _as_utc(datetime.fromisoformat(value))


def _timedelta_microseconds(value: timedelta) -> int:
    return (
        value.days * 86_400_000_000
        + value.seconds * 1_000_000
        + value.microseconds
    )


def _coverage_ratio(
    *,
    earliest_at: datetime | None,
    window_start: datetime,
    as_of: datetime,
) -> Decimal:
    if earliest_at is None:
        return Decimal(0)
    covered_start = max(_as_utc(earliest_at), window_start)
    covered = max(0, _timedelta_microseconds(as_of - covered_start))
    window = _timedelta_microseconds(as_of - window_start)
    return min(Decimal(1), Decimal(covered) / Decimal(window))


def _decimal_string(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.000001")), "f")


def _threshold_packet(thresholds: TrendFactThresholds) -> dict[str, Any]:
    return {
        "min_posts": thresholds.min_posts,
        "min_authors": thresholds.min_authors,
        "contested_ratio": str(thresholds.contested_ratio),
        "minimum_coverage": str(thresholds.minimum_coverage),
        "momentum": {
            "surging": str(thresholds.surging_ratio),
            "rising": str(thresholds.rising_ratio),
            "steady": str(thresholds.steady_ratio),
        },
    }


def _empty_packet(
    *,
    window_days: int,
    as_of: datetime,
    window_start: datetime,
    midpoint: datetime,
    earliest_at: datetime | None,
    coverage_ratio: Decimal,
    coverage_limited: bool,
    thresholds: TrendFactThresholds,
) -> dict[str, Any]:
    return {
        "schema_version": FACT_PACKET_SCHEMA_VERSION,
        "window_days": window_days,
        "as_of": _iso_utc(as_of),
        "window_start": _iso_utc(window_start),
        "midpoint": _iso_utc(midpoint),
        "coverage": {
            "state": "limited" if coverage_limited else "sufficient",
            "ratio": _decimal_string(coverage_ratio),
            "earliest_at": _iso_utc(earliest_at),
        },
        "thresholds": _threshold_packet(thresholds),
        "narrative_type": "insufficient_data",
        "primary_brand": None,
        "secondary_brand": None,
        "earlier_leader": None,
        "momentum": None,
    }


def _canonical_key(row: dict[str, Any]) -> tuple[str, str]:
    key = str(row["brand_id"])
    return (key.casefold(), key)


def _ranked(
    rows: list[dict[str, Any]],
    *,
    count_field: str,
    author_field: str,
    thresholds: TrendFactThresholds,
) -> list[dict[str, Any]]:
    eligible = [
        row
        for row in rows
        if int(row[count_field] or 0) >= thresholds.min_posts
        and int(row[author_field] or 0) >= thresholds.min_authors
    ]
    return sorted(
        eligible,
        key=lambda row: (-int(row[count_field] or 0), *_canonical_key(row)),
    )


def _brand_snapshot(
    row: dict[str, Any],
    *,
    coverage_limited: bool,
) -> dict[str, Any]:
    key = str(row["brand_id"])
    display_name = row["brand__display_name"] or key
    snapshot: dict[str, Any] = {
        "key": key,
        "display_name_en": row["brand__display_name_en"] or display_name,
        "display_name_zh_hans": row["brand__display_name_zh_cn"]
        or display_name,
    }
    if coverage_limited:
        snapshot.update(
            selected_posts=int(row["selected_posts"] or 0),
            selected_authors=int(row["selected_authors"] or 0),
        )
    else:
        snapshot.update(
            recent_posts=int(row["recent_posts"] or 0),
            recent_authors=int(row["recent_authors"] or 0),
            earlier_posts=int(row["earlier_posts"] or 0),
            earlier_authors=int(row["earlier_authors"] or 0),
        )
    return snapshot


def _is_contested(
    leader: dict[str, Any],
    runner_up: dict[str, Any] | None,
    *,
    count_field: str,
    thresholds: TrendFactThresholds,
) -> bool:
    if runner_up is None:
        return False
    return (
        Decimal(int(runner_up[count_field] or 0))
        / Decimal(int(leader[count_field] or 0))
        >= thresholds.contested_ratio
    )


def _derive_coverage_limited(
    packet: dict[str, Any],
    rows: list[dict[str, Any]],
    thresholds: TrendFactThresholds,
) -> dict[str, Any]:
    selected = _ranked(
        rows,
        count_field="selected_posts",
        author_field="selected_authors",
        thresholds=thresholds,
    )
    if not selected:
        return packet
    packet["narrative_type"] = "coverage_limited"
    packet["primary_brand"] = _brand_snapshot(
        selected[0], coverage_limited=True
    )
    if _is_contested(
        selected[0],
        selected[1] if len(selected) > 1 else None,
        count_field="selected_posts",
        thresholds=thresholds,
    ):
        packet["secondary_brand"] = _brand_snapshot(
            selected[1], coverage_limited=True
        )
    return packet


def _momentum(
    *,
    recent_posts: int,
    earlier_posts: int,
    thresholds: TrendFactThresholds,
) -> str:
    if earlier_posts == 0:
        return "new"
    ratio = Decimal(recent_posts) / Decimal(earlier_posts)
    if ratio >= thresholds.surging_ratio:
        return "surging"
    if ratio >= thresholds.rising_ratio:
        return "rising"
    if ratio >= thresholds.steady_ratio:
        return "steady"
    return "cooling"


def _derive_normal(
    packet: dict[str, Any],
    rows: list[dict[str, Any]],
    thresholds: TrendFactThresholds,
) -> dict[str, Any]:
    recent = _ranked(
        rows,
        count_field="recent_posts",
        author_field="recent_authors",
        thresholds=thresholds,
    )
    if not recent:
        return packet

    earlier = _ranked(
        rows,
        count_field="earlier_posts",
        author_field="earlier_authors",
        thresholds=thresholds,
    )
    leader = recent[0]
    runner_up = recent[1] if len(recent) > 1 else None
    earlier_leader = earlier[0] if earlier else None
    contested = _is_contested(
        leader,
        runner_up,
        count_field="recent_posts",
        thresholds=thresholds,
    )

    if contested:
        narrative_type = "contested"
    elif earlier_leader is not None and (
        _canonical_key(earlier_leader) != _canonical_key(leader)
    ):
        narrative_type = "handoff"
    else:
        narrative_type = "leader"

    packet["narrative_type"] = narrative_type
    packet["primary_brand"] = _brand_snapshot(leader, coverage_limited=False)
    if contested and runner_up is not None:
        packet["secondary_brand"] = _brand_snapshot(
            runner_up, coverage_limited=False
        )
    if earlier_leader is not None:
        packet["earlier_leader"] = _brand_snapshot(
            earlier_leader, coverage_limited=False
        )
    packet["momentum"] = _momentum(
        recent_posts=int(leader["recent_posts"] or 0),
        earlier_posts=int(leader["earlier_posts"] or 0),
        thresholds=thresholds,
    )
    return packet
