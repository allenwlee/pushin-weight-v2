"""Bounded Stage 1 current-versus-historical scalar reader."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from django.db import connection

from core.classification_contract import (
    COMPATIBLE_TAXONOMY_VERSIONS,
    CONTRACT_VERSION,
)
from core.models import (
    PostBrandClassificationState,
    PostBrandDiscourse,
    PostBrandSignal,
)


@dataclass(frozen=True)
class BrandScalarRead:
    sentiment: str | None
    china_nationalism: str | None
    us_nationalism: str | None
    source: str
    conflicts: tuple[str, ...] = ()
    outcome: str | None = None
    contract_version: str | None = None
    taxonomy_version: str | None = None


def aggregate_brand_sentiment_counts(
    *, brand_id: str, start: datetime, end: datetime, day_timezone: str | None,
) -> list[tuple[date | int, str | None, int]] | None:
    """Count the scalar reader's exact sentiments without transferring each post.

    Current state owns explicit nulls and unrecognized versions. Only pairs
    without state may use one distinct nonempty historical sentiment. Other
    backends retain the existing row reader; no saved state is introduced.
    Binary comparisons preserve that reader's literal Python keys, while the
    additional identity predicates retain the case-insensitive lookup indexes.
    """
    if connection.vendor != "postgresql":
        return None
    bucket_sql = (
        "(created_at AT TIME ZONE %s)::date" if day_timezone is not None
        else "floor(extract(epoch FROM (created_at - %s::timestamptz)) / 300)::int"
    )
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            WITH wanted AS MATERIALIZED (
                SELECT pb.post_id, p.created_at
                FROM posts_brands pb JOIN posts p ON p.tweet_id = pb.post_id
                WHERE pb.brand_id = %s AND p.created_at >= %s AND p.created_at < %s
            ), legacy AS (
                SELECT g.post_id,
                    CASE WHEN count(DISTINCT nullif(g.sentiment, '') COLLATE "C") = 1
                         THEN min(nullif(g.sentiment, '') COLLATE "C") END AS sentiment
                FROM posts_brands_signals g JOIN wanted w ON w.post_id = g.post_id
                LEFT JOIN posts_brands_classification_states s
                    ON s.post_id = g.post_id AND s.brand_id = g.brand_id
                    AND s.brand_id COLLATE "C" = g.brand_id COLLATE "C"
                WHERE g.brand_id = %s AND g.brand_id COLLATE "C" = %s
                    AND s.post_id IS NULL
                GROUP BY g.post_id
            ), resolved AS (
                SELECT w.created_at,
                    CASE WHEN s.post_id IS NOT NULL THEN
                        CASE WHEN s.contract_version = %s AND s.taxonomy_version = ANY(%s)
                             THEN nullif(s.sentiment, '') END
                        ELSE l.sentiment END AS sentiment
                FROM wanted w
                LEFT JOIN posts_brands_classification_states s
                    ON s.post_id = w.post_id AND s.brand_id = %s
                    AND s.brand_id COLLATE "C" = %s
                LEFT JOIN legacy l ON l.post_id = w.post_id
            )
            SELECT {bucket_sql}, sentiment COLLATE "C", count(*)
            FROM resolved GROUP BY 1, 2
            """,
            [
                brand_id, start, end, brand_id, brand_id, CONTRACT_VERSION,
                list(COMPATIBLE_TAXONOMY_VERSIONS), brand_id, brand_id,
                day_timezone if day_timezone is not None else start,
            ],
        )
        return cursor.fetchall()


def _one_distinct(values) -> tuple[str | None, bool]:
    distinct = {value for value in values if value is not None}
    if len(distinct) == 1:
        return distinct.pop(), False
    return None, len(distinct) > 1


def read_brand_scalars(*, post_id: str, brand_id: str) -> BrandScalarRead:
    """Read current state first, otherwise unambiguous legacy scalar rows.

    A current state owns all three axes even when one is explicitly null;
    historical fallthrough is therefore impossible after cutover.
    """
    return read_brand_scalars_many([(post_id, brand_id)])[(post_id, brand_id)]


def read_brand_scalars_many(
    pairs: list[tuple[str, str]],
) -> dict[tuple[str, str], BrandScalarRead]:
    """Resolve any number of pairs with three bounded relation queries."""
    wanted = set(pairs)
    if not wanted:
        return {}
    post_ids = {post_id for post_id, _brand_id in wanted}
    state_rows = PostBrandClassificationState.objects.filter(
        post_id__in=post_ids,
    ).values(
        "post_id",
        "brand_id",
        "contract_version",
        "taxonomy_version",
        "sentiment_id",
        "china_nationalism_id",
        "us_nationalism_id",
        "outcome",
    )
    states = {
        (row["post_id"], row["brand_id"]): row
        for row in state_rows
        if (row["post_id"], row["brand_id"]) in wanted
    }
    signals: dict[tuple[str, str], list[str | None]] = {pair: [] for pair in wanted}
    for post_id, brand_id, sentiment in PostBrandSignal.objects.filter(
        post_id__in=post_ids
    ).values_list("post_id", "brand_id", "sentiment_id"):
        if (post_id, brand_id) in wanted:
            signals[(post_id, brand_id)].append(sentiment)
    discourse: dict[tuple[str, str], list[tuple[str | None, str | None]]] = {
        pair: [] for pair in wanted
    }
    for post_id, brand_id, china, us in PostBrandDiscourse.objects.filter(
        post_id__in=post_ids
    ).values_list("post_id", "brand_id", "china_nationalism_id", "us_nationalism_id"):
        if (post_id, brand_id) in wanted:
            discourse[(post_id, brand_id)].append((china, us))
    output: dict[tuple[str, str], BrandScalarRead] = {}
    for pair in wanted:
        row = states.get(pair)
        if row is not None:
            recognized = (
                row["contract_version"] == CONTRACT_VERSION
                and row["taxonomy_version"] in COMPATIBLE_TAXONOMY_VERSIONS
            )
            output[pair] = BrandScalarRead(
                (row["sentiment_id"] or None) if recognized else None,
                (row["china_nationalism_id"] or None) if recognized else None,
                (row["us_nationalism_id"] or None) if recognized else None,
                "current" if recognized else "unrecognized",
                outcome=row["outcome"] if recognized else None,
                contract_version=row["contract_version"],
                taxonomy_version=row["taxonomy_version"],
            )
            continue
        sentiment, sentiment_conflict = _one_distinct(
            value for value in signals[pair] if value
        )
        china, china_conflict = _one_distinct(
            value[0] for value in discourse[pair] if value[0]
        )
        us, us_conflict = _one_distinct(
            value[1] for value in discourse[pair] if value[1]
        )
        conflicts = tuple(
            name
            for name, conflict in (
                ("sentiment", sentiment_conflict),
                ("china_nationalism", china_conflict),
                ("us_nationalism", us_conflict),
            )
            if conflict
        )
        output[pair] = BrandScalarRead(
            sentiment,
            china,
            us,
            "historical" if any((sentiment, china, us)) else "unknown",
            conflicts,
        )
    return output
