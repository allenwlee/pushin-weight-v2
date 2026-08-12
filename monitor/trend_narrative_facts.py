"""Deterministic, provider-free facts for the V22 headline narrative.

The database chooses aggregate counts; application code applies the product's
ranking and threshold vocabulary.  This module deliberately has no config,
task, HTTP, or LLM dependency so the resulting packet remains reproducible.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from django.db.models import Count, Min, Q

from core.models import PostBrand

ALLOWED_TREND_WINDOWS = frozenset({1, 7, 30, 365})
FACT_PACKET_SCHEMA_VERSION = 1
_EARLIEST_NOT_PROVIDED = object()


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

    def __post_init__(self) -> None:
        if self.min_posts < 1 or self.min_authors < 1:
            raise ValueError("post and author floors must be positive")
        ratios = (
            self.contested_ratio,
            self.minimum_coverage,
            self.surging_ratio,
            self.rising_ratio,
            self.steady_ratio,
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


DEFAULT_TREND_THRESHOLDS = TrendFactThresholds()


def canonical_fact_json(packet: dict[str, Any]) -> str:
    """Return UTF-8-friendly canonical JSON for hashing and persistence."""
    return json.dumps(
        packet,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
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
