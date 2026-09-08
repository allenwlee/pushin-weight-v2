"""Bounded Stage 1 current-versus-historical scalar reader."""

from __future__ import annotations

from dataclasses import dataclass

from core.classification_contract import CONTRACT_VERSION, TAXONOMY_VERSION
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
    current_rows = PostBrandClassificationState.objects.filter(
        post_id__in=post_ids,
        contract_version=CONTRACT_VERSION,
        taxonomy_version=TAXONOMY_VERSION,
    ).values(
        "post_id",
        "brand_id",
        "sentiment_id",
        "china_nationalism_id",
        "us_nationalism_id",
        "outcome",
    )
    current = {
        (row["post_id"], row["brand_id"]): row
        for row in current_rows
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
        row = current.get(pair)
        if row is not None:
            output[pair] = BrandScalarRead(
                row["sentiment_id"] or None,
                row["china_nationalism_id"] or None,
                row["us_nationalism_id"] or None,
                "current",
                outcome=row["outcome"],
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
