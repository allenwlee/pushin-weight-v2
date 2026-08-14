"""Bounded candidate selection and graph-ready trend snapshot assembly."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from django.db import connection, transaction

from monitor.trend_narrative_facts import (
    DEFAULT_TREND_THRESHOLDS,
    TrendFactThresholds,
    aggregate_trend_family_facts,
    canonical_fact_json,
    fetch_trend_candidate_series,
)

TREND_SNAPSHOT_SCHEMA_VERSION = 1
MAX_SHORTLIST_CANDIDATES = 6
MAX_EVIDENCE_CHARACTERS = 1_000
MAX_SNAPSHOT_BYTES = 256 * 1024
MAX_PROVIDER_PACKET_BYTES = 128 * 1024
SNAPSHOT_STATEMENT_TIMEOUT_MS = 30_000
SNAPSHOT_LOCK_TIMEOUT_MS = 5_000
NEAR_DUPLICATE_JACCARD = Decimal("0.90")
RECURRING_THEME_JACCARD = Decimal("0.35")
FAMILY_ORDER = (
    "volume",
    "engagement",
    "post_type",
    "discourse",
    "sentiment",
    "nationalism",
)
EVIDENCE_ROLE_ORDER = (
    "official_or_catalyst",
    "top_engaged_original",
    "dominant_discourse_representative",
    "contrasting_reaction",
)
EVIDENCE_QUERY_RANK_STREAMS = 5
SUPPORTING_CONTEXT_ROLE = "supporting_context"

_WHITESPACE_RE = re.compile(r"\s+")
_PURE_REPOST_RE = re.compile(r"^\s*RT\s+@", re.IGNORECASE)


class TrendSnapshotError(ValueError):
    """A safe analysis failure with no post content in its message."""


class TrendSnapshotSizeError(TrendSnapshotError):
    """The persisted or provider projection exceeded its fixed byte ceiling."""


class TrendSnapshotTransactionError(TrendSnapshotError):
    """Snapshot construction could not establish its required read boundary."""


@dataclass(frozen=True, slots=True)
class EvidenceSelectionPolicy:
    """Versioned hard bounds for one deterministic evidence allocation."""

    version: str = "adaptive-v1"
    reservoir_rank_limit: int = 32
    floor: int = 4
    lead_ceiling: int = 48
    comparison_ceiling: int = 12
    excerpt_characters: int = MAX_EVIDENCE_CHARACTERS
    provider_packet_bytes: int = MAX_PROVIDER_PACKET_BYTES

    def __post_init__(self) -> None:
        if not self.version or len(self.version) > 64:
            raise ValueError("evidence policy version must contain 1-64 characters")
        if not 4 <= self.reservoir_rank_limit <= 64:
            raise ValueError("evidence reservoir rank limit must be between 4 and 64")
        if not 1 <= self.floor <= self.comparison_ceiling <= self.lead_ceiling <= 64:
            raise ValueError("evidence allocation limits must be ordered within 1-64")
        if not 200 <= self.excerpt_characters <= MAX_EVIDENCE_CHARACTERS:
            raise ValueError("evidence excerpt limit must be between 200 and 1000")
        if not 32 * 1024 <= self.provider_packet_bytes <= MAX_PROVIDER_PACKET_BYTES:
            raise ValueError(
                "evidence provider packet limit is outside the safe envelope"
            )


DEFAULT_EVIDENCE_SELECTION_POLICY = EvidenceSelectionPolicy()


def canonical_snapshot_json(
    packet: Mapping[str, Any],
    *,
    enforce_limit: bool = False,
) -> str:
    encoded = canonical_fact_json(dict(packet))
    if enforce_limit and len(encoded.encode("utf-8")) > MAX_SNAPSHOT_BYTES:
        raise TrendSnapshotSizeError("trend_snapshot_too_large")
    return encoded


def normalized_excerpt(
    value: str | None,
    *,
    max_characters: int = MAX_EVIDENCE_CHARACTERS,
) -> str:
    """Normalize an exact evidence excerpt and apply the fixed character cap."""
    if not value:
        return ""
    normalized = unicodedata.normalize("NFC", value)
    collapsed = _WHITESPACE_RE.sub(" ", normalized).strip()
    return collapsed[:max_characters]


def text_five_gram_jaccard(left: str, right: str) -> Decimal:
    left_grams = _character_ngrams(normalized_excerpt(left), size=5)
    right_grams = _character_ngrams(normalized_excerpt(right), size=5)
    if not left_grams and not right_grams:
        return Decimal(1)
    union = left_grams | right_grams
    if not union:
        return Decimal(0)
    return Decimal(len(left_grams & right_grams)) / Decimal(len(union))


def select_trend_candidates(
    facts: Mapping[str, Any],
    *,
    limit: int = MAX_SHORTLIST_CANDIDATES,
) -> list[dict[str, Any]]:
    """Apply fixed-family seed, merge, round-robin, and brand backstop rules."""
    if limit < 1 or limit > MAX_SHORTLIST_CANDIDATES:
        raise ValueError(
            f"limit must be between 1 and {MAX_SHORTLIST_CANDIDATES}"
        )
    sources = {
        str(row["candidate_key"]["candidate_id"]): row
        for row in facts.get("candidates", [])
    }
    streams = _candidate_streams(facts, sources, limit=limit)
    selected: list[dict[str, Any]] = []
    selected_by_id: dict[str, dict[str, Any]] = {}

    def add(item: Mapping[str, Any]) -> None:
        candidate_id = str(item["candidate_id"])
        signal = dict(item["signal"])
        if candidate_id in selected_by_id:
            existing = selected_by_id[candidate_id]
            if signal not in existing["signals"]:
                existing["signals"].append(signal)
            return
        row = {
            key: value
            for key, value in item.items()
            if key != "signal"
        }
        row["signals"] = [signal]
        selected.append(row)
        selected_by_id[candidate_id] = row

    positions: dict[str, int] = {}
    for family in FAMILY_ORDER:
        stream = streams[family]
        positions[family] = 0
        if stream:
            add(stream[0])
            positions[family] = 1
        if len(selected) >= limit:
            break

    while len(selected) < limit:
        advanced = False
        for family in FAMILY_ORDER:
            position = positions[family]
            stream = streams[family]
            if position >= len(stream):
                continue
            add(stream[position])
            positions[family] += 1
            advanced = True
            if len(selected) >= limit:
                break
        if not advanced:
            break

    _apply_distinct_brand_backstop(
        selected=selected,
        selected_by_id=selected_by_id,
        streams=streams,
        supported_brand_keys={
            str(row["candidate_key"]["brand_key"])
            for row in facts.get("candidates", [])
        },
        limit=limit,
    )
    return selected


def build_trend_analysis_snapshot(
    window_days: int,
    *,
    as_of: datetime,
    thresholds: TrendFactThresholds = DEFAULT_TREND_THRESHOLDS,
    evidence_policy: EvidenceSelectionPolicy = DEFAULT_EVIDENCE_SELECTION_POLICY,
) -> dict[str, Any]:
    """Build and serialize one immutable snapshot under one read-only DB view."""
    if connection.vendor != "postgresql":
        raise TrendSnapshotTransactionError("trend_snapshot_requires_postgresql")
    if connection.in_atomic_block:
        raise TrendSnapshotTransactionError(
            "trend_snapshot_requires_fresh_transaction"
        )
    as_of_utc = _as_utc(as_of)
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(
                "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
            )
            cursor.execute(
                "SELECT set_config('statement_timeout', %s, true), "
                "set_config('lock_timeout', %s, true)",
                [
                    str(SNAPSHOT_STATEMENT_TIMEOUT_MS),
                    str(SNAPSHOT_LOCK_TIMEOUT_MS),
                ],
            )
        facts = aggregate_trend_family_facts(
            window_days,
            as_of=as_of_utc,
            thresholds=thresholds,
        )
        shortlist = select_trend_candidates(facts)
        brand_keys = list(
            dict.fromkeys(str(row["brand_key"]) for row in shortlist)
        )
        details = fetch_trend_candidate_series(
            window_days,
            as_of=as_of_utc,
            candidate_keys=brand_keys,
        )
        evidence_rows = _fetch_evidence_rows(
            shortlist,
            as_of=as_of_utc,
            rank_limit=evidence_policy.reservoir_rank_limit,
        )
        snapshot = _assemble_snapshot(
            facts=facts,
            shortlist=shortlist,
            details=details,
            evidence_rows=evidence_rows,
            evidence_policy=evidence_policy,
        )
        _fit_snapshot_evidence_to_packet_budget(
            snapshot,
            max_bytes=evidence_policy.provider_packet_bytes,
        )
        canonical_snapshot_json(snapshot, enforce_limit=True)
        provider_json = canonical_snapshot_json(project_provider_packet(snapshot))
        if len(provider_json.encode("utf-8")) > evidence_policy.provider_packet_bytes:
            raise TrendSnapshotSizeError("trend_provider_packet_too_large")
    return snapshot


def project_provider_packet(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Remove complete fine vectors and private source metadata for DeepSeek."""
    candidates = []
    for candidate in snapshot.get("candidates", []):
        candidates.append(
            {
                "candidate_id": candidate["candidate_id"],
                "brand_key": candidate["brand_key"],
                "display_name_en": candidate["display_name_en"],
                "display_name_zh_cn": candidate["display_name_zh_cn"],
                "kind": candidate["kind"],
                "start_at": candidate["start_at"],
                "end_at": candidate["end_at"],
                "signals": candidate["signals"],
                "family_facts": candidate["family_facts"],
                "metadata_trajectories": candidate.get(
                    "metadata_trajectories",
                    {},
                ),
                "episodes": candidate["episodes"],
                "coarse_series": candidate["series"]["coarse"],
                "evidence_allocation": candidate.get("evidence_allocation", {}),
                "evidence_support": candidate["evidence_support"],
                "evidence": [
                    {
                        "evidence_id": evidence["evidence_id"],
                        "source_cluster_id": evidence["source_cluster_id"],
                        "theme_cluster_id": evidence.get("theme_cluster_id", ""),
                        "author_group_id": evidence["author_group_id"],
                        "excerpt": evidence["excerpt"],
                        "roles": evidence["roles"],
                        "source_flags": evidence["source_flags"],
                        "post_type_keys": evidence.get("post_type_keys", []),
                        "discourse_keys": evidence["discourse_keys"],
                        "sentiment_keys": evidence["sentiment_keys"],
                    }
                    for evidence in candidate["evidence"]
                ],
            }
        )
    return {
        "snapshot_schema_version": snapshot["snapshot_schema_version"],
        "window_days": snapshot["window_days"],
        "as_of": snapshot["as_of"],
        "coverage": snapshot["coverage"],
        "unresolved_backlog_intervals": snapshot.get(
            "unresolved_backlog_intervals",
            [],
        ),
        "comparison_suppressed_reasons": snapshot.get(
            "comparison_suppressed_reasons",
            [],
        ),
        "comparison_allowed": snapshot["comparison_allowed"],
        "thresholds": snapshot["thresholds"],
        "evidence_policy": snapshot.get("evidence_policy", {}),
        "series_axis": {"coarse": snapshot["series_axis"]["coarse"]},
        "candidates": candidates,
    }


def _candidate_streams(
    facts: Mapping[str, Any],
    sources: Mapping[str, Mapping[str, Any]],
    *,
    limit: int,
) -> dict[str, list[dict[str, Any]]]:
    streams: dict[str, list[dict[str, Any]]] = {
        family: [] for family in FAMILY_ORDER
    }
    rankings = facts.get("family_rankings", {})
    for family in FAMILY_ORDER:
        primary_items: list[dict[str, Any]] = []
        extra_volume_episodes: list[dict[str, Any]] = []
        ranked_source_ids = list(rankings.get(family, []))[:limit]
        for rank, source_id in enumerate(ranked_source_ids, start=1):
            source = sources.get(str(source_id))
            if source is None:
                continue
            episodes = list(source.get("episodes") or [])
            episode = episodes[0] if episodes else None
            primary_items.append(
                _candidate_stream_item(
                    source,
                    family=family,
                    family_rank=rank,
                    episode=episode,
                    episode_rank=1 if episode is not None else None,
                )
            )
            if family == "volume":
                for episode_rank, extra in enumerate(episodes[1:], start=2):
                    extra_volume_episodes.append(
                        _candidate_stream_item(
                            source,
                            family=family,
                            family_rank=rank,
                            episode=extra,
                            episode_rank=episode_rank,
                        )
                    )
        streams[family] = (primary_items + extra_volume_episodes)[:limit]
        for stream_position, item in enumerate(streams[family], start=1):
            item["signal"]["stream_position"] = stream_position
    return streams


def _candidate_stream_item(
    source: Mapping[str, Any],
    *,
    family: str,
    family_rank: int,
    episode: Mapping[str, Any] | None,
    episode_rank: int | None,
) -> dict[str, Any]:
    source_key = source["candidate_key"]
    brand_key = str(source_key["brand_key"])
    if episode is None:
        candidate_id = f"{brand_key}:full_window"
        kind = "full_window"
        episode_id = "full_window"
        start_at = source_key["start_at"]
        end_at = source_key["end_at"]
    else:
        candidate_id = str(episode["episode_id"])
        kind = "episode"
        episode_id = candidate_id
        start_at = episode["start_at"]
        end_at = episode["end_at"]
    signal: dict[str, Any] = {"family": family, "rank": family_rank}
    if episode_rank is not None:
        signal["episode_rank"] = episode_rank
    return {
        "candidate_id": candidate_id,
        "source_candidate_id": str(source_key["candidate_id"]),
        "brand_key": brand_key,
        "episode_id": episode_id,
        "kind": kind,
        "start_at": start_at,
        "end_at": end_at,
        "display_name_en": str(source.get("display_name_en") or brand_key),
        "display_name_zh_cn": str(
            source.get("display_name_zh_cn")
            or source.get("display_name_en")
            or brand_key
        ),
        "signal": signal,
    }


def _apply_distinct_brand_backstop(
    *,
    selected: list[dict[str, Any]],
    selected_by_id: dict[str, dict[str, Any]],
    streams: Mapping[str, Sequence[Mapping[str, Any]]],
    supported_brand_keys: set[str],
    limit: int,
) -> None:
    if len(supported_brand_keys) < 2 or not selected:
        return
    selected_brands = {str(row["brand_key"]) for row in selected}
    if len(selected_brands) >= 2:
        return
    family_priority = {family: index for index, family in enumerate(FAMILY_ORDER)}
    replacement: Mapping[str, Any] | None = None
    replacement_key: tuple[Any, ...] | None = None
    for family in FAMILY_ORDER:
        for item in streams[family]:
            if str(item["brand_key"]) in selected_brands:
                continue
            item_key = (
                int(item["signal"]["rank"]),
                family_priority[str(item["signal"]["family"])],
                int(item["signal"]["stream_position"]),
                str(item["candidate_id"]).casefold(),
                str(item["candidate_id"]),
            )
            if replacement_key is None or item_key < replacement_key:
                replacement = item
                replacement_key = item_key
    if replacement is None:
        return
    replacement_row = {
        key: value
        for key, value in replacement.items()
        if key != "signal"
    }
    replacement_row["signals"] = [dict(replacement["signal"])]
    if len(selected) < limit:
        selected.append(replacement_row)
        selected_by_id[str(replacement_row["candidate_id"])] = replacement_row
        return
    duplicate_brand = str(selected[0]["brand_key"])
    replace_at = next(
        (
            index
            for index in range(len(selected) - 1, 0, -1)
            if str(selected[index]["brand_key"]) == duplicate_brand
        ),
        None,
    )
    if replace_at is None:
        return
    removed = selected[replace_at]
    selected_by_id.pop(str(removed["candidate_id"]), None)
    selected[replace_at] = replacement_row
    selected_by_id[str(replacement_row["candidate_id"])] = replacement_row


def _assemble_snapshot(
    *,
    facts: Mapping[str, Any],
    shortlist: Sequence[Mapping[str, Any]],
    details: Mapping[str, Any],
    evidence_rows: Sequence[Mapping[str, Any]],
    evidence_policy: EvidenceSelectionPolicy,
) -> dict[str, Any]:
    sources = {
        str(row["candidate_key"]["candidate_id"]): row
        for row in facts.get("candidates", [])
    }
    details_by_brand = {
        str(row["candidate_key"]["brand_key"]): row
        for row in details.get("candidates", [])
    }
    evidence_candidates = []
    for selected in shortlist:
        source = sources[str(selected["source_candidate_id"])]
        evidence_candidates.append(
            {
                **selected,
                "family_facts": _relevant_family_facts(
                    source,
                    selected["signals"],
                ),
            }
        )
    evidence_by_candidate, evidence_allocations = (
        _select_evidence_with_allocation(
            evidence_rows,
            candidates=evidence_candidates,
            policy=evidence_policy,
        )
    )
    series_axis = _shared_series_axis(details)
    candidates = []
    for selected in shortlist:
        source = sources[str(selected["source_candidate_id"])]
        detail = details_by_brand[str(selected["brand_key"])]
        evidence = evidence_by_candidate.get(str(selected["candidate_id"]), [])
        signals = [dict(signal) for signal in selected["signals"]]
        family_facts = _relevant_family_facts(source, signals)
        coarse_series = _compact_series(
            detail["coarse_series"],
            include_post_kinds=True,
        )
        candidates.append(
            {
                "candidate_id": selected["candidate_id"],
                "source_candidate_id": selected["source_candidate_id"],
                "brand_key": selected["brand_key"],
                "episode_id": selected["episode_id"],
                "kind": selected["kind"],
                "start_at": selected["start_at"],
                "end_at": selected["end_at"],
                "display_name_en": selected["display_name_en"],
                "display_name_zh_cn": selected["display_name_zh_cn"],
                "signals": signals,
                "family_facts": family_facts,
                "metadata_trajectories": _compact_metadata_trajectories(
                    detail.get("metadata_series", {}),
                    family_facts=family_facts,
                    post_counts=coarse_series["post_counts"],
                ),
                "episodes": list(source.get("episodes") or []),
                "series": {
                    "coarse": coarse_series,
                    "fine": _compact_series(
                        detail["fine_series"],
                        include_post_kinds=False,
                    ),
                },
                "evidence_allocation": evidence_allocations.get(
                    str(selected["candidate_id"]),
                    _empty_evidence_allocation(evidence_policy),
                ),
                "evidence_support": _evidence_support(evidence),
                "evidence": evidence,
            }
        )
    return {
        "snapshot_schema_version": TREND_SNAPSHOT_SCHEMA_VERSION,
        "fact_schema_version": facts["schema_version"],
        "window_days": facts["window_days"],
        "as_of": facts["as_of"],
        "window_start": facts["window_start"],
        "prior_start": facts["prior_start"],
        "coverage": facts["coverage"],
        "unresolved_backlog_intervals": facts.get(
            "unresolved_backlog_intervals",
            [],
        ),
        "comparison_suppressed_reasons": facts.get(
            "comparison_suppressed_reasons",
            [],
        ),
        "comparison_allowed": facts["comparison_allowed"],
        "thresholds": facts["thresholds"],
        "evidence_policy": {
            "version": evidence_policy.version,
            "reservoir_rank_limit": evidence_policy.reservoir_rank_limit,
            "floor": evidence_policy.floor,
            "lead_ceiling": evidence_policy.lead_ceiling,
            "comparison_ceiling": evidence_policy.comparison_ceiling,
            "excerpt_characters": evidence_policy.excerpt_characters,
            "provider_packet_bytes": evidence_policy.provider_packet_bytes,
        },
        "selection": {
            "family_order": list(FAMILY_ORDER),
            "max_candidates": MAX_SHORTLIST_CANDIDATES,
            "candidate_count": len(candidates),
            "evidence_query_row_ceiling": (
                len(shortlist)
                * evidence_policy.reservoir_rank_limit
                * EVIDENCE_QUERY_RANK_STREAMS
            ),
        },
        "series_axis": series_axis,
        "candidates": candidates,
    }


def _relevant_family_facts(
    source: Mapping[str, Any], signals: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    source_facts = source.get("family_facts", {})
    families = {"volume"}
    families.update(str(signal["family"]) for signal in signals)
    if "nationalism" in families:
        families.remove("nationalism")
        families.update({"china_nationalism", "us_nationalism"})
    return {
        family: source_facts[family]
        for family in (
            "volume",
            "engagement",
            "post_type",
            "discourse",
            "sentiment",
            "china_nationalism",
            "us_nationalism",
        )
        if family in families and family in source_facts
    }


def _shared_series_axis(details: Mapping[str, Any]) -> dict[str, Any]:
    candidates = details.get("candidates", [])
    if not candidates:
        return {
            resolution: {
                **details["schedule"][resolution],
                "starts": [],
                "ends": [],
            }
            for resolution in ("coarse", "fine")
        }
    first = candidates[0]
    return {
        resolution: {
            **details["schedule"][resolution],
            "starts": [
                row["start_at"] for row in first[f"{resolution}_series"]
            ],
            "ends": [row["end_at"] for row in first[f"{resolution}_series"]],
        }
        for resolution in ("coarse", "fine")
    }


def _compact_series(
    series: Sequence[Mapping[str, Any]],
    *,
    include_post_kinds: bool,
) -> dict[str, Any]:
    def totals_value(bucket: Mapping[str, Any], key: str) -> int | None:
        totals = bucket["engagement"]["totals"]
        return int(totals[key]) if totals is not None else None

    result: dict[str, Any] = {
        "post_counts": [int(row["post_count"]) for row in series],
        "author_counts": [int(row["author_count"]) for row in series],
        "engagement": {
            "eligible_counts": [
                int(row["engagement"]["eligible_count"]) for row in series
            ],
            "missing_counts": [
                int(row["engagement"]["missing_count"]) for row in series
            ],
            "coverage_ratios": [
                row["engagement"]["coverage_ratio"] for row in series
            ],
            "likes": [totals_value(row, "likes") for row in series],
            "reposts": [totals_value(row, "reposts") for row in series],
            "quotes": [totals_value(row, "quotes") for row in series],
            "replies": [totals_value(row, "replies") for row in series],
            "interactions": [
                totals_value(row, "interactions") for row in series
            ],
            "intensities": [
                row["engagement"]["intensity"] for row in series
            ],
            "concentrations": [
                row["engagement"]["concentration"] for row in series
            ],
            "post_kinds": {},
        },
    }
    if include_post_kinds:
        for kind in ("source_post", "repost", "quote"):
            result["engagement"]["post_kinds"][kind] = {
                "eligible_counts": [
                    int(
                        row["engagement"]["by_post_kind"][kind][
                            "eligible_count"
                        ]
                    )
                    for row in series
                ],
                "missing_counts": [
                    int(
                        row["engagement"]["by_post_kind"][kind]["missing_count"]
                    )
                    for row in series
                ],
                "interactions": [
                    (
                        int(
                            row["engagement"]["by_post_kind"][kind]["totals"][
                                "interactions"
                            ]
                        )
                        if row["engagement"]["by_post_kind"][kind]["totals"]
                        is not None
                        else None
                    )
                    for row in series
                ],
            }
    return result


def _compact_metadata_trajectories(
    metadata_series: Mapping[str, Any],
    *,
    family_facts: Mapping[str, Any],
    post_counts: Sequence[int],
) -> dict[str, Any]:
    trajectories = {}
    for family in (
        "post_type",
        "discourse",
        "sentiment",
        "china_nationalism",
        "us_nationalism",
    ):
        facts = family_facts.get(family)
        if not isinstance(facts, Mapping):
            continue
        source = metadata_series.get(family, {})
        raw_labels = source.get("labels", {})
        coverage_counts = [
            int(value) for value in source.get("coverage_counts", [])
        ]
        if len(coverage_counts) != len(post_counts):
            coverage_counts = [0] * len(post_counts)
        labels = {}
        for fact in facts.get("labels", []):
            key = str(fact.get("key") or "")
            counts = [int(value) for value in raw_labels.get(key, [])]
            if len(counts) != len(post_counts):
                counts = [0] * len(post_counts)
            if not any(counts) and not int(fact.get("selected_count") or 0) and not int(
                fact.get("prior_count") or 0
            ):
                continue
            labels[key] = {
                "counts": counts,
                "prevalence": [
                    _ratio_string(count, basis)
                    for count, basis in zip(counts, post_counts, strict=True)
                ],
            }
        trajectories[family] = {
            "coverage_counts": coverage_counts,
            "coverage_percent": [
                _ratio_percent(count, basis)
                for count, basis in zip(
                    coverage_counts,
                    post_counts,
                    strict=True,
                )
            ],
            "labels": labels,
        }
    return trajectories


def _ratio_string(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "0.000000"
    return str(
        (Decimal(numerator) / Decimal(denominator)).quantize(
            Decimal("0.000001")
        )
    )


def _ratio_percent(numerator: int, denominator: int) -> int:
    if denominator <= 0:
        return 0
    return int(
        (Decimal(numerator) * 100 / Decimal(denominator)).quantize(
            Decimal(1),
            rounding=ROUND_HALF_UP,
        )
    )


def _fetch_evidence_rows(
    candidates: Sequence[Mapping[str, Any]],
    *,
    as_of: datetime,
    rank_limit: int,
) -> list[dict[str, Any]]:
    if not candidates:
        return []
    sql = """
        WITH requested AS (
            SELECT candidate_id, brand_key, start_at, end_at, position
            FROM unnest(
                %s::text[], %s::text[], %s::timestamptz[],
                %s::timestamptz[]
            ) WITH ORDINALITY AS item(
                candidate_id, brand_key, start_at, end_at, position
            )
        ),
        official_accounts AS (
            SELECT DISTINCT ba.brand_id::text AS brand_key, ba.accounts_id
            FROM brands_accounts ba
            JOIN requested r ON r.brand_key = ba.brand_id::text
            WHERE ba.role_id = 'official'
        ),
        base_posts AS (
            SELECT
                r.position,
                r.candidate_id,
                r.brand_key,
                p.tweet_id,
                p.author_id,
                p.quoted_status_id,
                p.created_at,
                p.text,
                p.quoted_text,
                coalesce(p.is_retweet, false) AS is_retweet,
                coalesce(p.is_quote, false) AS is_quote,
                (
                    p.metrics_refreshed_at IS NOT NULL
                    AND p.metrics_refreshed_at <= %s::timestamptz
                ) AS metrics_observed,
                (
                    coalesce(p.like_count, 0)
                    + coalesce(p.retweet_count, 0)
                    + coalesce(p.quote_count, 0)
                    + coalesce(p.reply_count, 0)
                )::bigint AS stored_interactions,
                official.accounts_id IS NOT NULL AS is_official
            FROM requested r
            JOIN posts_brands pb ON pb.brand_id::text = r.brand_key
            JOIN posts p ON p.tweet_id = pb.post_id
            LEFT JOIN official_accounts official
              ON official.brand_key = r.brand_key
             AND official.accounts_id = p.author_id
            WHERE p.created_at >= r.start_at
              AND p.created_at < r.end_at
              AND p.created_at < %s::timestamptz
              AND (
                    (
                        nullif(btrim(p.text), '') IS NOT NULL
                        AND (
                            NOT coalesce(p.is_retweet, false)
                            OR p.text !~* '^\\s*RT\\s+@'
                        )
                    )
                    OR (
                        NOT coalesce(p.is_retweet, false)
                        AND nullif(btrim(p.quoted_text), '') IS NOT NULL
                      )
              )
        ),
        signal_arrays AS (
            SELECT
                base.candidate_id,
                base.brand_key,
                base.tweet_id,
                array_agg(
                    DISTINCT s.post_type_key::text ORDER BY s.post_type_key::text
                ) FILTER (WHERE s.post_type_key IS NOT NULL) AS post_type_keys,
                array_agg(
                    DISTINCT s.sentiment::text ORDER BY s.sentiment::text
                ) FILTER (WHERE s.sentiment IS NOT NULL) AS sentiment_keys
            FROM base_posts base
            JOIN posts_brands_signals s
              ON s.post_id = base.tweet_id
             AND s.brand_id::text = base.brand_key
            GROUP BY base.candidate_id, base.brand_key, base.tweet_id
        ),
        discourse_arrays AS (
            SELECT
                base.candidate_id,
                base.brand_key,
                base.tweet_id,
                array_agg(
                    DISTINCT d.discourse_key::text
                    ORDER BY d.discourse_key::text
                ) AS discourse_keys
            FROM base_posts base
            JOIN posts_brands_discourse d
              ON d.post_id = base.tweet_id
             AND d.brand_id::text = base.brand_key
            GROUP BY base.candidate_id, base.brand_key, base.tweet_id
        ),
        candidate_posts AS (
            SELECT
                base.*,
                CASE WHEN base.metrics_observed
                     THEN base.stored_interactions ELSE 0
                END::bigint AS interactions,
                coalesce(sig.post_type_keys, ARRAY[]::text[])
                    AS post_type_keys,
                coalesce(sig.sentiment_keys, ARRAY[]::text[])
                    AS sentiment_keys,
                coalesce(dis.discourse_keys, ARRAY[]::text[])
                    AS discourse_keys
            FROM base_posts base
            LEFT JOIN signal_arrays sig
              ON sig.candidate_id = base.candidate_id
             AND sig.brand_key = base.brand_key
             AND sig.tweet_id = base.tweet_id
            LEFT JOIN discourse_arrays dis
              ON dis.candidate_id = base.candidate_id
             AND dis.brand_key = base.brand_key
             AND dis.tweet_id = base.tweet_id
        ),
        discourse_counts AS (
            SELECT candidate_id, discourse_key, count(*) AS post_count
            FROM candidate_posts,
                 unnest(discourse_keys) AS item(discourse_key)
            GROUP BY candidate_id, discourse_key
        ),
        dominant_discourse AS (
            SELECT DISTINCT ON (candidate_id)
                candidate_id, discourse_key
            FROM discourse_counts
            ORDER BY candidate_id, post_count DESC,
                     lower(discourse_key), discourse_key
        ),
        sentiment_counts AS (
            SELECT candidate_id, sentiment_key, count(*) AS post_count
            FROM candidate_posts,
                 unnest(sentiment_keys) AS item(sentiment_key)
            GROUP BY candidate_id, sentiment_key
        ),
        dominant_sentiment AS (
            SELECT DISTINCT ON (candidate_id)
                candidate_id, sentiment_key
            FROM sentiment_counts
            ORDER BY candidate_id, post_count DESC,
                     lower(sentiment_key), sentiment_key
        ),
        ranked AS (
            SELECT
                cp.*,
                dd.discourse_key AS dominant_discourse,
                ds.sentiment_key AS dominant_sentiment,
                row_number() OVER (
                    PARTITION BY cp.candidate_id
                    ORDER BY cp.is_official DESC, cp.metrics_observed DESC,
                             cp.interactions DESC, cp.created_at ASC,
                             cp.tweet_id ASC
                ) AS official_rank,
                row_number() OVER (
                    PARTITION BY cp.candidate_id
                    ORDER BY cp.created_at ASC, cp.interactions DESC,
                             cp.tweet_id ASC
                ) AS catalyst_rank,
                row_number() OVER (
                    PARTITION BY cp.candidate_id
                    ORDER BY (NOT cp.is_retweet) DESC,
                             cp.metrics_observed DESC,
                             cp.interactions DESC, cp.created_at DESC,
                             cp.tweet_id ASC
                ) AS original_rank,
                row_number() OVER (
                    PARTITION BY cp.candidate_id
                    ORDER BY (
                                dd.discourse_key IS NOT NULL
                                AND dd.discourse_key = ANY(cp.discourse_keys)
                             ) DESC,
                             cp.metrics_observed DESC,
                             cp.interactions DESC, cp.created_at DESC,
                             cp.tweet_id ASC
                ) AS discourse_rank,
                row_number() OVER (
                    PARTITION BY cp.candidate_id
                    ORDER BY (
                                ds.sentiment_key IS NOT NULL
                                AND cardinality(cp.sentiment_keys) > 0
                                AND NOT (
                                    ds.sentiment_key = ANY(cp.sentiment_keys)
                                )
                             ) DESC,
                             cp.metrics_observed DESC,
                             cp.interactions DESC, cp.created_at DESC,
                             cp.tweet_id ASC
                ) AS contrast_rank
            FROM candidate_posts cp
            LEFT JOIN dominant_discourse dd USING (candidate_id)
            LEFT JOIN dominant_sentiment ds USING (candidate_id)
        )
        SELECT *
        FROM ranked
        WHERE official_rank <= %s
           OR catalyst_rank <= %s
           OR original_rank <= %s
           OR discourse_rank <= %s
           OR contrast_rank <= %s
        ORDER BY position, least(
                    official_rank, catalyst_rank, original_rank,
                    discourse_rank, contrast_rank
                 ), created_at, tweet_id
    """
    params = [
        [str(row["candidate_id"]) for row in candidates],
        [str(row["brand_key"]) for row in candidates],
        [_parse_utc(str(row["start_at"])) for row in candidates],
        [_parse_utc(str(row["end_at"])) for row in candidates],
        as_of,
        as_of,
        *([rank_limit] * EVIDENCE_QUERY_RANK_STREAMS),
    ]
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        names = [column.name for column in cursor.description]
        return [
            dict(zip(names, values, strict=True)) for values in cursor.fetchall()
        ]


def _select_evidence(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    selected, _allocations = _select_evidence_with_allocation(
        rows,
        candidates=(),
        policy=DEFAULT_EVIDENCE_SELECTION_POLICY,
    )
    return selected


def _select_evidence_with_allocation(
    rows: Sequence[Mapping[str, Any]],
    *,
    candidates: Sequence[Mapping[str, Any]],
    policy: EvidenceSelectionPolicy,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, dict[str, Any]]]:
    pools = _prepare_evidence_pools(rows, policy=policy)
    candidate_rows = {
        str(candidate["candidate_id"]): candidate for candidate in candidates
    }
    for candidate_id, pool in pools.items():
        if candidate_id in candidate_rows:
            continue
        created = sorted(str(row["created_at"]) for row in pool)
        candidate_rows[candidate_id] = {
            "candidate_id": candidate_id,
            "start_at": created[0] if created else "",
            "end_at": created[-1] if created else "",
            "signals": [],
            "family_facts": {},
        }

    ranked_ids = sorted(
        candidate_rows,
        key=lambda candidate_id: (
            _story_potential_key(
                candidate_rows[candidate_id],
                pools.get(candidate_id, []),
            ),
            candidate_id.casefold(),
            candidate_id,
        ),
        reverse=True,
    )
    lead_id = ranked_ids[0] if ranked_ids else ""
    selected_by_candidate: dict[str, list[dict[str, Any]]] = {}
    allocations: dict[str, dict[str, Any]] = {}
    for story_rank, candidate_id in enumerate(ranked_ids, start=1):
        candidate = candidate_rows[candidate_id]
        pool = pools.get(candidate_id, [])
        signal_families = {
            str(signal.get("family") or "")
            for signal in candidate.get("signals", [])
        }
        if candidate_id == lead_id:
            allocation_class = "lead"
            ceiling = policy.lead_ceiling
        elif len(signal_families) > 1 or signal_families.intersection(
            {"post_type", "discourse", "sentiment", "nationalism"}
        ):
            allocation_class = "comparison"
            ceiling = policy.comparison_ceiling
        else:
            allocation_class = "floor"
            ceiling = policy.floor
        available_clusters = len(
            {str(evidence["source_cluster_id"]) for evidence in pool}
        )
        target = min(ceiling, available_clusters)
        selected = _select_candidate_evidence(
            pool,
            candidate=candidate,
            target=target,
        )
        selected_by_candidate[candidate_id] = selected
        allocations[candidate_id] = {
            "policy_version": policy.version,
            "allocation_class": allocation_class,
            "story_rank": story_rank,
            "reservoir_count": len(pool),
            "available_independent_source_count": available_clusters,
            "protected_floor_count": min(policy.floor, available_clusters),
            "target_count": target,
            "selected_count": len(selected),
            "packet_trimmed_count": 0,
        }
    return selected_by_candidate, allocations


def _prepare_evidence_pools(
    rows: Sequence[Mapping[str, Any]],
    *,
    policy: EvidenceSelectionPolicy,
) -> dict[str, list[dict[str, Any]]]:
    pools: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        candidate_id = str(row["candidate_id"])
        evidence = _evidence_candidate(
            row,
            excerpt_characters=policy.excerpt_characters,
        )
        if evidence is None:
            continue
        evidence["_ranks"] = {
            "official_or_catalyst": (
                int(row["official_rank"])
                if row["is_official"]
                else int(row["catalyst_rank"])
            ),
            "top_engaged_original": int(row["original_rank"]),
            "dominant_discourse_representative": int(row["discourse_rank"]),
            "contrasting_reaction": int(row["contrast_rank"]),
        }
        evidence["_role_eligible"] = {
            "official_or_catalyst": True,
            "top_engaged_original": not bool(row["is_retweet"]),
            "dominant_discourse_representative": bool(
                row["dominant_discourse"]
                and row["dominant_discourse"] in row["discourse_keys"]
            ),
            "contrasting_reaction": bool(
                row["dominant_sentiment"]
                and row["sentiment_keys"]
                and row["dominant_sentiment"] not in row["sentiment_keys"]
            ),
        }
        evidence["_interactions"] = int(row.get("interactions") or 0)
        pools.setdefault(candidate_id, []).append(evidence)

    max_rows = policy.reservoir_rank_limit * EVIDENCE_QUERY_RANK_STREAMS
    for candidate_id, unbounded_pool in list(pools.items()):
        pool = sorted(
            unbounded_pool,
            key=lambda evidence: (
                min(evidence["_ranks"].values()),
                str(evidence["created_at"]),
                str(evidence["evidence_id"]),
            ),
        )[:max_rows]
        _assign_text_clusters(candidate_id, pool)
        pools[candidate_id] = pool
    return pools


def _assign_text_clusters(
    candidate_id: str,
    pool: Sequence[dict[str, Any]],
) -> None:
    ordered = sorted(
        pool,
        key=lambda item: (
            str(item["excerpt"]).casefold(),
            str(item["evidence_id"]),
        ),
    )
    source_representatives: list[tuple[str, str]] = []
    theme_representatives: list[tuple[str, str]] = []
    for evidence in ordered:
        matched_cluster = next(
            (
                cluster_id
                for cluster_id, excerpt in source_representatives
                if text_five_gram_jaccard(excerpt, evidence["excerpt"])
                >= NEAR_DUPLICATE_JACCARD
            ),
            None,
        )
        if matched_cluster is None:
            matched_cluster = str(evidence["source_cluster_id"])
            source_representatives.append(
                (matched_cluster, str(evidence["excerpt"]))
            )
        evidence["source_cluster_id"] = matched_cluster

        matched_theme = next(
            (
                theme_id
                for theme_id, excerpt in theme_representatives
                if text_five_gram_jaccard(excerpt, evidence["excerpt"])
                >= RECURRING_THEME_JACCARD
            ),
            None,
        )
        if matched_theme is None:
            matched_theme = "th_" + _digest(
                candidate_id,
                str(evidence["excerpt"]),
            )[:20]
            theme_representatives.append(
                (matched_theme, str(evidence["excerpt"]))
            )
        evidence["theme_cluster_id"] = matched_theme

    for evidence in pool:
        theme_rows = [
            item
            for item in pool
            if item["theme_cluster_id"] == evidence["theme_cluster_id"]
        ]
        authors = {
            str(item["author_group_id"])
            for item in theme_rows
            if item.get("author_group_id")
        }
        clusters = {str(item["source_cluster_id"]) for item in theme_rows}
        evidence["_theme_support_count"] = min(len(authors), len(clusters))


def _story_potential_key(
    candidate: Mapping[str, Any],
    pool: Sequence[Mapping[str, Any]],
) -> tuple[int, int, int, int, int, int]:
    signals = list(candidate.get("signals", []))
    signal_families = {str(signal.get("family") or "") for signal in signals}
    mix_signal_count = len(
        signal_families.intersection(
            {"post_type", "discourse", "sentiment", "nationalism"}
        )
    )
    recurring_themes = {
        str(evidence.get("theme_cluster_id") or "")
        for evidence in pool
        if int(evidence.get("_theme_support_count") or 0) >= 2
    }
    label_diversity = sum(
        len(
            {
                str(key)
                for evidence in pool
                for key in evidence.get(field, [])
            }
        )
        for field in ("post_type_keys", "discourse_keys", "sentiment_keys")
    )
    independent_authors = len(
        {
            str(evidence["author_group_id"])
            for evidence in pool
            if evidence.get("author_group_id")
        }
    )
    independent_clusters = len(
        {str(evidence["source_cluster_id"]) for evidence in pool}
    )
    volume = _selected_volume(candidate.get("family_facts", {}).get("volume", {}))
    return (
        len(recurring_themes),
        mix_signal_count,
        len(signal_families),
        label_diversity,
        min(independent_authors, independent_clusters),
        volume,
    )


def _selected_volume(volume: Mapping[str, Any]) -> int:
    values = [
        volume.get("selected_count"),
        volume.get("selected_posts"),
        volume.get("full_window", {}).get("post_count")
        if isinstance(volume.get("full_window"), Mapping)
        else None,
    ]
    for value in values:
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            continue
    return 0


def _select_candidate_evidence(
    pool: Sequence[Mapping[str, Any]],
    *,
    candidate: Mapping[str, Any],
    target: int,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    selected_ids: dict[str, dict[str, Any]] = {}
    selected_clusters: set[str] = set()
    selected_authors: set[str] = set()

    def add(evidence: Mapping[str, Any], *, role: str) -> bool:
        evidence_id = str(evidence["evidence_id"])
        if evidence_id in selected_ids:
            public = selected_ids[evidence_id]
            if role not in public["roles"]:
                public["roles"].append(role)
            return False
        cluster_id = str(evidence["source_cluster_id"])
        if len(selected) >= target or cluster_id in selected_clusters:
            return False
        public = {
            key: value for key, value in evidence.items() if not key.startswith("_")
        }
        public["roles"] = [role]
        selected.append(public)
        selected_ids[evidence_id] = public
        selected_clusters.add(cluster_id)
        if evidence.get("author_group_id"):
            selected_authors.add(str(evidence["author_group_id"]))
        return True

    for role in EVIDENCE_ROLE_ORDER:
        ranked = sorted(
            (
                evidence
                for evidence in pool
                if evidence["_role_eligible"][role]
            ),
            key=lambda evidence: (
                str(evidence.get("author_group_id") or "") in selected_authors,
                evidence["_ranks"][role],
                str(evidence["evidence_id"]),
            ),
        )
        for evidence in ranked:
            if add(evidence, role=role):
                break
            if str(evidence["evidence_id"]) in selected_ids:
                break

    recurring = sorted(
        (
            evidence
            for evidence in pool
            if int(evidence.get("_theme_support_count") or 0) >= 2
        ),
        key=lambda evidence: (
            -int(evidence["_theme_support_count"]),
            str(evidence["theme_cluster_id"]),
            str(evidence["created_at"]),
            str(evidence["evidence_id"]),
        ),
    )
    for evidence in recurring:
        add(evidence, role=SUPPORTING_CONTEXT_ROLE)

    for segment in range(3):
        segment_rows = [
            evidence
            for evidence in pool
            if _evidence_time_segment(evidence, candidate=candidate) == segment
        ]
        for evidence in sorted(
            segment_rows,
            key=lambda item: (
                str(item.get("author_group_id") or "") in selected_authors,
                str(item["created_at"]),
                str(item["evidence_id"]),
            ),
        ):
            if add(evidence, role=SUPPORTING_CONTEXT_ROLE):
                break

    for field in ("post_type_keys", "discourse_keys", "sentiment_keys"):
        keys = sorted(
            {
                str(key)
                for evidence in pool
                for key in evidence.get(field, [])
            }
        )
        for key in keys:
            choices = [
                evidence for evidence in pool if key in evidence.get(field, [])
            ]
            for evidence in sorted(
                choices,
                key=lambda item: (
                    str(item.get("author_group_id") or "") in selected_authors,
                    -int(item.get("_interactions") or 0),
                    str(item["evidence_id"]),
                ),
            ):
                if add(evidence, role=SUPPORTING_CONTEXT_ROLE):
                    break

    remaining = sorted(
        pool,
        key=lambda evidence: (
            str(evidence.get("author_group_id") or "") in selected_authors,
            -int(evidence.get("_theme_support_count") or 0),
            -len(evidence.get("post_type_keys", [])),
            -len(evidence.get("discourse_keys", [])),
            -len(evidence.get("sentiment_keys", [])),
            -int(evidence.get("_interactions") or 0),
            min(evidence["_ranks"].values()),
            str(evidence["created_at"]),
            str(evidence["evidence_id"]),
        ),
    )
    for evidence in remaining:
        add(evidence, role=SUPPORTING_CONTEXT_ROLE)
    return selected


def _evidence_time_segment(
    evidence: Mapping[str, Any],
    *,
    candidate: Mapping[str, Any],
) -> int:
    created_at = _parse_utc(str(evidence["created_at"]))
    try:
        start_at = _parse_utc(str(candidate.get("start_at") or ""))
        end_at = _parse_utc(str(candidate.get("end_at") or ""))
    except ValueError:
        return 1
    duration = (end_at - start_at).total_seconds()
    if duration <= 0:
        return 1
    position = (created_at - start_at).total_seconds() / duration
    if position < 1 / 3:
        return 0
    if position < 2 / 3:
        return 1
    return 2


def _empty_evidence_allocation(
    policy: EvidenceSelectionPolicy,
) -> dict[str, Any]:
    return {
        "policy_version": policy.version,
        "allocation_class": "floor",
        "story_rank": 0,
        "reservoir_count": 0,
        "available_independent_source_count": 0,
        "protected_floor_count": 0,
        "target_count": 0,
        "selected_count": 0,
        "packet_trimmed_count": 0,
    }


def _fit_snapshot_evidence_to_packet_budget(
    snapshot: dict[str, Any],
    *,
    max_bytes: int,
    max_snapshot_bytes: int = MAX_SNAPSHOT_BYTES,
) -> None:
    """Trim low-priority excerpts until both serialized forms are bounded."""

    def packet_bytes() -> int:
        packet = project_provider_packet(snapshot)
        return len(canonical_snapshot_json(packet).encode("utf-8"))

    candidates = list(snapshot.get("candidates", []))
    def snapshot_bytes() -> int:
        return len(canonical_snapshot_json(snapshot).encode("utf-8"))

    while packet_bytes() > max_bytes or snapshot_bytes() > max_snapshot_bytes:
        removable = [candidate for candidate in candidates if candidate["evidence"]]
        if not removable:
            if snapshot_bytes() > max_snapshot_bytes:
                raise TrendSnapshotSizeError("trend_snapshot_too_large")
            raise TrendSnapshotSizeError("trend_provider_packet_too_large")
        candidate = min(removable, key=_packet_trim_priority)
        candidate["evidence"].pop()
        allocation = candidate["evidence_allocation"]
        allocation["selected_count"] = len(candidate["evidence"])
        allocation["packet_trimmed_count"] = (
            int(allocation.get("packet_trimmed_count") or 0) + 1
        )
        candidate["evidence_support"] = _evidence_support(candidate["evidence"])


def _packet_trim_priority(candidate: Mapping[str, Any]) -> tuple[int, int, int]:
    """Prefer comparison extras, then weak floors, before lead evidence."""
    allocation = candidate.get("evidence_allocation", {})
    selected_count = len(candidate.get("evidence", []))
    policy_floor = int(allocation.get("protected_floor_count") or 0)
    above_floor = selected_count > policy_floor
    is_lead = allocation.get("allocation_class") == "lead"
    story_rank = int(allocation.get("story_rank") or 0)
    phase = (
        0
        if above_floor and not is_lead
        else 1
        if above_floor
        else 2
        if not is_lead
        else 3
    )
    return (
        phase,
        -story_rank,
        -selected_count,
    )


def _evidence_candidate(
    row: Mapping[str, Any],
    *,
    excerpt_characters: int = MAX_EVIDENCE_CHARACTERS,
) -> dict[str, Any] | None:
    post_text = normalized_excerpt(
        row.get("text"),
        max_characters=excerpt_characters,
    )
    quoted_text = normalized_excerpt(
        row.get("quoted_text"),
        max_characters=excerpt_characters,
    )
    is_retweet = bool(row["is_retweet"])
    if post_text and not (is_retweet and _PURE_REPOST_RE.match(post_text)):
        excerpt = post_text
        occurrence_source = "original_post"
    elif quoted_text and not is_retweet:
        excerpt = quoted_text
        occurrence_source = "quoted_source"
    else:
        return None
    candidate_id = str(row["candidate_id"])
    evidence_id = "e_" + _digest(
        candidate_id,
        str(row["tweet_id"]),
        occurrence_source,
        excerpt,
    )[:24]
    author_group_id = (
        "ag_" + _digest(str(row["author_id"]))[:20]
        if row.get("author_id")
        else None
    )
    if row.get("quoted_status_id"):
        source_cluster_id = "sc_root_" + _digest(
            str(row["quoted_status_id"])
        )[:20]
    else:
        source_cluster_id = "sc_text_" + _digest(excerpt)[:20]
    return {
        "evidence_id": evidence_id,
        "author_group_id": author_group_id,
        "source_cluster_id": source_cluster_id,
        "excerpt": excerpt,
        "created_at": _iso_utc(row["created_at"]),
        "roles": [],
        "source_flags": {
            "official": bool(row["is_official"]),
            "post_kind": (
                "repost"
                if is_retweet
                else "quote"
                if bool(row["is_quote"])
                else "source_post"
            ),
            "metrics_observed": bool(row["metrics_observed"]),
            "occurrence_source": occurrence_source,
        },
        "post_type_keys": sorted(
            str(key) for key in row.get("post_type_keys", [])
        ),
        "discourse_keys": sorted(str(key) for key in row["discourse_keys"]),
        "sentiment_keys": sorted(str(key) for key in row["sentiment_keys"]),
    }


def _evidence_support(evidence: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    author_groups = {
        str(row["author_group_id"])
        for row in evidence
        if row.get("author_group_id")
    }
    source_clusters = {str(row["source_cluster_id"]) for row in evidence}
    official_count = sum(
        bool(row["source_flags"]["official"]) for row in evidence
    )
    return {
        "official_source_count": official_count,
        "distinct_author_group_count": len(author_groups),
        "distinct_source_cluster_count": len(source_clusters),
        "event_claim_may_be_supported": bool(
            official_count
            or (len(author_groups) >= 2 and len(source_clusters) >= 2)
        ),
        "evidence_only_entity_may_be_supported": bool(
            len(author_groups) >= 2 and len(source_clusters) >= 2
        ),
    }


def _character_ngrams(value: str, *, size: int) -> set[str]:
    if not value:
        return set()
    if len(value) <= size:
        return {value}
    return {value[index : index + size] for index in range(len(value) - size + 1)}


def _digest(*parts: str) -> str:
    encoded = "\x1f".join(parts).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return _as_utc(parsed)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware")
    return value.astimezone(UTC)


def _iso_utc(value: datetime) -> str:
    return _as_utc(value).isoformat().replace("+00:00", "Z")
