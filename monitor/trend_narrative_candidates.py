"""Bounded candidate selection and graph-ready trend snapshot assembly."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import defaultdict
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from heapq import nlargest
from itertools import pairwise
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
COMPACT_DOSSIER_SCHEMA_VERSION = 3
MAX_SHORTLIST_CANDIDATES = 6
MAX_EVIDENCE_CHARACTERS = 1_000
MAX_SNAPSHOT_BYTES = 256 * 1024
MAX_PROVIDER_PACKET_BYTES = 128 * 1024
MAX_EDITOR_BRANDS_PER_BATCH = 5
MAX_SNAPSHOT_BRANDS = 100
MAX_QUANTITATIVE_FACTS_PER_CANDIDATE = 24
MAX_CORPUS_SOURCE_ROWS = 20_000
MAX_CORPUS_SOURCE_TEXT_CHARACTERS = 8 * 1024 * 1024
MAX_CORPUS_TEXT_CHARACTERS = 32_000
MAX_CORPUS_TOKENS_PER_DOCUMENT = 8_192
MAX_CORPUS_DISTINCT_PHRASES_PER_BRAND = 750_000
MAX_CORPUS_RETAINED_PHRASES = 100_000
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
EVIDENCE_QUERY_RANK_STREAMS = 6
SUPPORTING_CONTEXT_ROLE = "supporting_context"
_CLASSIFIER_DERIVED_FAMILIES = frozenset(
    {
        "post_type",
        "sentiment",
        "discourse",
        "china_nationalism",
        "us_nationalism",
        "unsanctioned_flags",
    }
)

_WHITESPACE_RE = re.compile(r"\s+")
_PURE_REPOST_RE = re.compile(r"^\s*RT\s+@", re.IGNORECASE)
_CORPUS_TOKEN_SEPARATOR_RE = re.compile(r"(?:[^\w-]|_)+", re.UNICODE)

_CORPUS_SOURCE_ROWS_SQL = """
    SELECT pb.brand_id::text AS brand_key,
           p.tweet_id::text,
           coalesce(p.quoted_status_id::text, p.tweet_id::text) AS source_root_id,
           p.created_at,
           p.text
    FROM posts p
    JOIN posts_brands pb ON pb.post_id = p.tweet_id
    WHERE pb.brand_id::text = ANY(%s::text[])
      AND p.created_at >= %s::timestamptz
      AND p.created_at < %s::timestamptz
      AND nullif(btrim(p.text), '') IS NOT NULL
    ORDER BY pb.brand_id::text, p.created_at, p.tweet_id
    LIMIT %s
"""


class TrendSnapshotError(ValueError):
    """A safe analysis failure with no post content in its message."""


class TrendSnapshotSizeError(TrendSnapshotError):
    """The persisted or provider projection exceeded its fixed byte ceiling."""


class TrendSnapshotTransactionError(TrendSnapshotError):
    """Snapshot construction could not establish its required read boundary."""


class _CorpusPhraseResourceLimit(RuntimeError):
    """The optional phrase family exceeded its deterministic local budget."""


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

# These are a product contract, not an adaptive quality heuristic.  Each lane
# can donate unused places to the other lane, so a complete ordinary-only
# dossier is just as full as one with first-party announcements.
DOSSIER_EVIDENCE_TARGETS: dict[int, tuple[int, int]] = {
    1: (6, 2),
    7: (8, 3),
    30: (10, 4),
    365: (12, 4),
}


def select_dossier_evidence(
    window_days: int,
    evidence: Sequence[Mapping[str, Any]],
    *,
    newest_segment_start: datetime | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Select fixed-size, deduplicated evidence with deterministic rollover.

    First-party status is a validated account-edge property supplied by the
    query.  Ordinary rows never acquire identity merely because they mention a
    trusted account.
    """
    try:
        target, first_party_reservation = DOSSIER_EVIDENCE_TARGETS[window_days]
    except KeyError as exc:
        raise ValueError("unsupported dossier window") from exc
    ordinary_reservation = target - first_party_reservation
    by_cluster: dict[str, Mapping[str, Any]] = {}
    for row in sorted(evidence, key=_dossier_evidence_sort_key):
        cluster = str(row.get("source_cluster_id") or row.get("evidence_id") or "")
        if cluster and cluster not in by_cluster:
            by_cluster[cluster] = row
    deduplicated = list(by_cluster.values())
    first_party = [
        row
        for row in deduplicated
        if str(row.get("first_party_role") or "public_opaque") in {"official", "staff"}
    ]
    ordinary = [row for row in deduplicated if row not in first_party]
    selected: list[dict[str, Any]] = []

    # Reservations are filled independently, then all remaining candidates
    # compete in one stable pool.  Do not silently lower target for packet
    # pressure; byte compaction happens after this selection.
    selected.extend(dict(row) for row in first_party[:first_party_reservation])
    selected.extend(
        dict(row) for row in ordinary[:ordinary_reservation] if len(selected) < target
    )
    chosen = {str(row.get("evidence_id") or "") for row in selected}
    for row in sorted(first_party + ordinary, key=_dossier_evidence_sort_key):
        if len(selected) >= target:
            break
        evidence_id = str(row.get("evidence_id") or "")
        if evidence_id not in chosen:
            selected.append(dict(row))
            chosen.add(evidence_id)
    if window_days == 1 and newest_segment_start is not None:
        newest = [
            row
            for row in deduplicated
            if _evidence_at_or_after(row, newest_segment_start)
        ]
        if newest and not any(
            _evidence_at_or_after(row, newest_segment_start) for row in selected
        ):
            replacement = min(newest, key=_dossier_evidence_sort_key)
            replace_at = max(
                range(len(selected)),
                key=lambda index: _dossier_evidence_sort_key(selected[index]),
            )
            selected[replace_at] = dict(replacement)
    return selected, {
        "target_count": target,
        "first_party_reservation": first_party_reservation,
        "ordinary_reservation": ordinary_reservation,
        "selected_count": len(selected),
    }


def _evidence_at_or_after(
    row: Mapping[str, Any], boundary: datetime
) -> bool:
    created_at = row.get("created_at")
    if not created_at:
        return False
    try:
        return _parse_utc(str(created_at)) >= boundary
    except (TypeError, ValueError):
        return False


def _dossier_evidence_sort_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
    role = str(row.get("first_party_role") or "public_opaque")
    source_flags = row.get("source_flags") or {}
    # Authored trusted announcements and originals lead each lane, then
    # temporal/subject diversity already represented by the bounded reservoir,
    # engagement, and finally stable opaque IDs settle ties.
    return (
        0 if role in {"official", "staff"} else 1,
        0 if source_flags.get("post_kind") == "source_post" else 1,
        -int(row.get("_interactions") or row.get("interactions") or 0),
        str(row.get("created_at") or ""),
        str(row.get("evidence_id") or ""),
    )


def build_editor_batches(
    snapshot: Mapping[str, Any],
    *,
    brand_order: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    """Project deterministic packets of at most five brands from a V3 snapshot.

    ``brand_order`` is the mechanically validated rank-stage order. Missing or
    ineligible keys are ignored and eligible keys omitted by the rank response
    are appended canonically, so evaluation and production share one batching
    implementation without allowing the model to drop a brand.
    """
    if (
        int(snapshot.get("packet_schema_version") or 0)
        != COMPACT_DOSSIER_SCHEMA_VERSION
    ):
        raise ValueError("compact_dossier_snapshot_required")
    dossiers = [
        dict(row)
        for row in snapshot.get("dossiers", [])
        if str(row.get("outcome")) == "narrative_eligible"
    ]
    dossiers.sort(
        key=lambda row: (str(row["brand_key"]).casefold(), str(row["brand_key"]))
    )
    if brand_order is not None:
        by_key = {str(row["brand_key"]): row for row in dossiers}
        ordered_keys = list(
            dict.fromkeys(str(key) for key in brand_order if str(key) in by_key)
        )
        ordered_keys.extend(key for key in by_key if key not in ordered_keys)
        dossiers = [by_key[key] for key in ordered_keys]
    batches = []
    for index in range(0, len(dossiers), MAX_EDITOR_BRANDS_PER_BATCH):
        members = dossiers[index : index + MAX_EDITOR_BRANDS_PER_BATCH]
        batch_key = (
            f"{snapshot['window_days']}d:"
            f"{index // MAX_EDITOR_BRANDS_PER_BATCH + 1:03d}"
        )
        batches.extend(_fit_or_split_editor_batch(snapshot, members, batch_key))
    return batches


def _fit_or_split_editor_batch(
    snapshot: Mapping[str, Any],
    members: Sequence[Mapping[str, Any]],
    batch_key: str,
) -> list[dict[str, Any]]:
    """Split only irreducibly oversized multi-brand packets, preserving order."""
    batch = {
        "packet_schema_version": COMPACT_DOSSIER_SCHEMA_VERSION,
        "window_days": snapshot["window_days"],
        "as_of": snapshot["as_of"],
        "baseline_context": dict(snapshot["baseline_context"]),
        "batch_key": batch_key,
        "manifest_brand_keys": [str(row["brand_key"]) for row in members],
        "dossiers": [_provider_dossier(row) for row in members],
    }
    try:
        _fit_editor_batch_to_packet_budget(batch)
    except TrendSnapshotSizeError as exc:
        if str(exc) != "compact_editor_packet_too_large" or len(members) == 1:
            raise
        midpoint = len(members) // 2
        return [
            *_fit_or_split_editor_batch(
                snapshot, members[:midpoint], f"{batch_key}.1"
            ),
            *_fit_or_split_editor_batch(
                snapshot, members[midpoint:], f"{batch_key}.2"
            ),
        ]
    return [batch]


def _provider_dossier(dossier: Mapping[str, Any]) -> dict[str, Any]:
    """Return the bounded public-to-provider half of one dossier."""
    projected = {
        key: value
        for key, value in dossier.items()
        if key
        not in {
            "raw_series",
            "aggregate_inputs",
            "source_row_provenance",
            "evidence_selection_provenance",
        }
    }
    projected["family_summaries"] = {
        family: {
            key: value
            for key, value in dict(summary).items()
            if key not in {"denominator", "total_post_count"}
        }
        for family, summary in dict(dossier.get("family_summaries") or {}).items()
    }
    projected["evidence"] = []
    for evidence in dossier.get("evidence", []):
        row = {
            key: value
            for key, value in evidence.items()
            if key
            not in {
                "author_group_id",
                "source_cluster_id",
                "post_type_keys",
                "discourse_keys",
                "sentiment_keys",
                "china_nationalism_keys",
                "us_nationalism_keys",
                "unsanctioned_flag_keys",
            }
        }
        if row.get("first_party_role") not in {"official", "staff"}:
            row.pop("handle_snapshot", None)
        projected["evidence"].append(row)
    return projected


def _fit_editor_batch_to_packet_budget(batch: dict[str, Any]) -> None:
    """Compact text only; evidence cardinality is an invariant."""

    def size() -> int:
        return len(canonical_snapshot_json(batch).encode("utf-8"))

    while size() > MAX_PROVIDER_PACKET_BYTES:
        candidates = [
            evidence
            for dossier in batch["dossiers"]
            for evidence in dossier.get("evidence", [])
            if len(str(evidence.get("excerpt") or "")) > 160
            or evidence.get("text_en")
            or evidence.get("text_zh_cn")
        ]
        if not candidates:
            raise TrendSnapshotSizeError("compact_editor_packet_too_large")
        evidence = max(
            candidates,
            key=lambda row: (
                len(str(row.get("excerpt") or "")),
                len(str(row.get("text_en") or ""))
                + len(str(row.get("text_zh_cn") or "")),
                str(row.get("evidence_id") or ""),
            ),
        )
        excerpt = str(evidence.get("excerpt") or "")
        if len(excerpt) > 160:
            evidence["excerpt"] = excerpt[: max(160, len(excerpt) // 2)]
        elif evidence.get("text_zh_cn"):
            evidence.pop("text_zh_cn", None)
        else:
            evidence.pop("text_en", None)


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
        raise ValueError(f"limit must be between 1 and {MAX_SHORTLIST_CANDIDATES}")
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
        row = {key: value for key, value in item.items() if key != "signal"}
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
    brand_cap: int = MAX_SNAPSHOT_BRANDS,
) -> dict[str, Any]:
    """Build and serialize one immutable snapshot under one read-only DB view."""
    if connection.vendor != "postgresql":
        raise TrendSnapshotTransactionError("trend_snapshot_requires_postgresql")
    if connection.in_atomic_block:
        raise TrendSnapshotTransactionError("trend_snapshot_requires_fresh_transaction")
    if brand_cap < 1 or brand_cap > MAX_SNAPSHOT_BRANDS:
        raise ValueError("snapshot brand cap must be between 1 and 100")
    as_of_utc = _as_utc(as_of)
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
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
        full_window = [
            row
            for row in facts.get("candidates", [])
            if row.get("candidate_key", {}).get("kind") == "full_window"
        ]
        if len(full_window) > brand_cap:
            raise TrendSnapshotTransactionError("trend_snapshot_brand_cap_exceeded")
        brand_keys = [str(row["candidate_key"]["brand_key"]) for row in full_window]
        details = fetch_trend_candidate_series(
            window_days,
            as_of=as_of_utc,
            candidate_keys=brand_keys,
            allow_unbounded=True,
        )
        evidence_rows = _fetch_evidence_rows(
            [
                {
                    "candidate_id": row["candidate_key"]["candidate_id"],
                    "brand_key": row["candidate_key"]["brand_key"],
                    "start_at": row["candidate_key"]["start_at"],
                    "end_at": row["candidate_key"]["end_at"],
                }
                for row in full_window
            ],
            as_of=as_of_utc,
            rank_limit=evidence_policy.reservoir_rank_limit,
        )
        # Read a bounded source corpus once, then deduplicate and count phrases
        # locally. This deliberately does not reuse the evidence reservoir: a
        # phrase must not disappear merely because its posts missed that sample.
        corpus_signals, corpus_extraction_status = _fetch_corpus_phrase_signals(
            [
                {
                    "candidate_id": row["candidate_key"]["candidate_id"],
                    "brand_key": row["candidate_key"]["brand_key"],
                    "start_at": row["candidate_key"]["start_at"],
                    "end_at": row["candidate_key"]["end_at"],
                }
                for row in full_window
            ],
            as_of=as_of_utc,
        )
        stable_family_facts = _fetch_stable_family_facts(
            [
                {
                    "brand_key": row["candidate_key"]["brand_key"],
                    "start_at": row["candidate_key"]["start_at"],
                    "end_at": row["candidate_key"]["end_at"],
                }
                for row in full_window
            ],
            comparison_allowed=bool(facts.get("comparison_allowed")),
        )
        snapshot = _assemble_compact_snapshot(
            facts=facts,
            full_window=full_window,
            details=details,
            evidence_rows=evidence_rows,
            corpus_signals=corpus_signals,
            corpus_extraction_status=corpus_extraction_status,
            stable_family_facts=stable_family_facts,
        )
        canonical_snapshot_json(snapshot)
        # Exercise every deterministic editor packet before this immutable
        # snapshot escapes the repeatable-read boundary.  Compaction may trim
        # text copies, never evidence rows; an irreducible packet fails safe.
        build_editor_batches(snapshot)
    return snapshot


def project_provider_packet(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Remove complete fine vectors and private source metadata for DeepSeek."""
    if (
        int(snapshot.get("packet_schema_version") or 0)
        == COMPACT_DOSSIER_SCHEMA_VERSION
    ):
        return _project_compact_ranking_packet(snapshot)
    candidates = []
    comparison_allowed = bool(snapshot.get("comparison_allowed"))
    minimum_coverage = Decimal(
        str(snapshot.get("thresholds", {}).get("minimum_coverage") or 0)
    )
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
                "family_facts": _provider_family_facts(
                    candidate["family_facts"],
                    comparison_allowed=comparison_allowed,
                ),
                "quantitative_facts": _quantitative_display_facts(
                    candidate,
                    comparison_allowed=comparison_allowed,
                    minimum_coverage=minimum_coverage,
                ),
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
        "quantitative_fact_schema_version": 1,
        "evidence_policy": snapshot.get("evidence_policy", {}),
        "series_axis": {"coarse": snapshot["series_axis"]["coarse"]},
        "candidates": candidates,
    }


def _provider_family_facts(
    value: Any,
    *,
    comparison_allowed: bool,
) -> Any:
    """Hide prior-window inputs when the snapshot suppresses comparison."""
    if comparison_allowed:
        return value
    if isinstance(value, Mapping):
        projected = {}
        for key, nested in value.items():
            normalized_key = str(key).casefold()
            if "prior" in normalized_key or "change" in normalized_key:
                projected[key] = None
            elif normalized_key == "comparison_state":
                projected[key] = "unavailable"
            else:
                projected[key] = _provider_family_facts(
                    nested,
                    comparison_allowed=False,
                )
        return projected
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [
            _provider_family_facts(item, comparison_allowed=False) for item in value
        ]
    return value


def _quantitative_display_facts(
    candidate: Mapping[str, Any],
    *,
    comparison_allowed: bool,
    minimum_coverage: Decimal,
) -> list[dict[str, Any]]:
    if not comparison_allowed:
        return []
    candidate_id = str(candidate["candidate_id"])
    family_facts = candidate.get("family_facts", {})
    projected: list[dict[str, Any]] = []
    volume = family_facts.get("volume", {})
    volume_change = volume.get("change_pct")
    if volume_change is None:
        volume_change = volume.get("selected_prior_pct_change")
    fact = _quantitative_display_fact(
        candidate_id=candidate_id,
        family="volume",
        metric="change_pct",
        label_key="",
        source_value=volume_change,
        unit="percent",
    )
    if fact is not None:
        projected.append(fact)

    engagement = family_facts.get("engagement", {})
    fact = _quantitative_display_fact(
        candidate_id=candidate_id,
        family="engagement",
        metric="intensity_change_pct",
        label_key="",
        source_value=engagement.get("intensity_change_pct"),
        unit="percent",
    )
    if fact is not None:
        projected.append(fact)

    for family in (
        "post_type",
        "discourse",
        "sentiment",
        "china_nationalism",
        "us_nationalism",
    ):
        family_fact = family_facts.get(family, {})
        if not _metadata_comparison_has_coverage(
            family_fact,
            minimum_coverage=minimum_coverage,
        ):
            continue
        facts = []
        for label in family_fact.get("labels", []):
            label_key = str(label.get("key") or "")
            prevalence_fact = _quantitative_display_fact(
                candidate_id=candidate_id,
                family=family,
                metric="brand_change_pp",
                label_key=label_key,
                source_value=label.get("brand_change_pp"),
                unit="percentage_points",
            )
            if prevalence_fact is not None:
                facts.append(prevalence_fact)
            prior_count = int(label.get("prior_count") or 0)
            selected_count = int(label.get("selected_count") or 0)
            if prior_count > 0:
                count_change = (
                    Decimal(selected_count) / Decimal(prior_count) - 1
                ) * 100
                count_fact = _quantitative_display_fact(
                    candidate_id=candidate_id,
                    family=family,
                    metric="count_change_pct",
                    label_key=label_key,
                    source_value=count_change,
                    unit="percent",
                )
                if count_fact is not None:
                    count_fact["source_selected_count"] = selected_count
                    count_fact["source_prior_count"] = prior_count
                    facts.append(count_fact)
        projected.extend(
            sorted(
                facts,
                key=lambda item: (
                    -abs(Decimal(str(item["source_value"]))),
                    str(item["label_key"]).casefold(),
                    str(item["label_key"]),
                ),
            )[:4]
        )
    return projected[:MAX_QUANTITATIVE_FACTS_PER_CANDIDATE]


def _metadata_comparison_has_coverage(
    family_fact: Mapping[str, Any],
    *,
    minimum_coverage: Decimal,
) -> bool:
    try:
        selected = Decimal(str(family_fact["selected_coverage_ratio"]))
        prior = Decimal(str(family_fact["prior_coverage_ratio"]))
    except (InvalidOperation, KeyError, TypeError):
        return False
    return selected >= minimum_coverage and prior >= minimum_coverage


def _quantitative_display_fact(
    *,
    candidate_id: str,
    family: str,
    metric: str,
    label_key: str,
    source_value: object,
    unit: str,
) -> dict[str, Any] | None:
    if source_value is None:
        return None
    source_text = str(source_value)
    try:
        exact = Decimal(source_text)
    except InvalidOperation:
        return None
    if not exact.is_finite():
        return None
    magnitude = abs(exact)
    quantum = Decimal("0.1") if magnitude < 1 else Decimal(1)
    rounded = magnitude.quantize(quantum, rounding=ROUND_HALF_UP)
    display_number = format(rounded, "f")
    if "." in display_number:
        display_number = display_number.rstrip("0").rstrip(".")
    suffix_en = "%" if unit == "percent" else " percentage points"
    suffix_zh_cn = "%" if unit == "percent" else "个百分点"
    fact_key = f"{candidate_id}:{family}:{metric}:{label_key}"
    return {
        "fact_id": "qf_" + _digest(fact_key)[:24],
        "candidate_id": candidate_id,
        "family": family,
        "metric": metric,
        "label_key": label_key,
        "unit": unit,
        "source_value": format(exact, "f"),
        "rounding": "nearest_tenth_below_one_else_whole",
        "direction": "increase" if exact > 0 else "decrease" if exact < 0 else "flat",
        "display_en": display_number + suffix_en,
        "display_zh_cn": display_number + suffix_zh_cn,
    }


def _candidate_streams(
    facts: Mapping[str, Any],
    sources: Mapping[str, Mapping[str, Any]],
    *,
    limit: int,
) -> dict[str, list[dict[str, Any]]]:
    streams: dict[str, list[dict[str, Any]]] = {family: [] for family in FAMILY_ORDER}
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
        key: value for key, value in replacement.items() if key != "signal"
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


def _assemble_compact_snapshot(
    *,
    facts: Mapping[str, Any],
    full_window: Sequence[Mapping[str, Any]],
    details: Mapping[str, Any],
    evidence_rows: Sequence[Mapping[str, Any]],
    corpus_signals: Mapping[str, Sequence[Mapping[str, Any]]],
    corpus_extraction_status: str,
    stable_family_facts: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Assemble U1's private all-brand snapshot without a post-text archive."""
    details_by_brand = {
        str(row["candidate_key"]["brand_key"]): row
        for row in details.get("candidates", [])
    }
    pools = _prepare_evidence_pools(
        evidence_rows,
        policy=DEFAULT_EVIDENCE_SELECTION_POLICY,
    )
    selected_coverage = facts.get("coverage", {}).get("selected", {})
    prior_coverage = facts.get("coverage", {}).get("prior", {})
    comparison_allowed = bool(facts.get("comparison_allowed"))
    comparison_reasons = list(facts.get("comparison_suppressed_reasons") or [])
    dossiers = []
    for source in sorted(
        full_window,
        key=lambda row: (
            str(row["candidate_key"]["brand_key"]).casefold(),
            str(row["candidate_key"]["brand_key"]),
        ),
    ):
        candidate_key = source["candidate_key"]
        brand_key = str(candidate_key["brand_key"])
        detail = details_by_brand[brand_key]
        family_facts = {
            **dict(source.get("family_facts") or {}),
            **dict(stable_family_facts.get(brand_key) or {}),
        }
        volume = family_facts.get("volume", {})
        selected_count = int(volume.get("selected_count") or 0)
        usable_raw_count = int(volume.get("selected_usable_raw_count") or 0)
        current_complete = selected_coverage.get("state") == "sufficient" and not bool(
            selected_coverage.get("known_backlog_overlap")
        )
        newest_segment_start = (
            _parse_utc(str(facts["as_of"])) - timedelta(minutes=30)
            if int(facts["window_days"]) == 1
            else None
        )
        selected_evidence, allocation = select_dossier_evidence(
            int(facts["window_days"]),
            pools.get(str(candidate_key["candidate_id"]), []),
            newest_segment_start=newest_segment_start,
        )
        outcome = (
            "narrative_eligible"
            if usable_raw_count and selected_evidence
            else "no_content"
            if current_complete
            else "data_quality_unavailable"
        )
        brand_corpus_signals = list(corpus_signals.get(brand_key) or [])
        family_facts["corpus_phrases"] = _corpus_phrase_family_fact(
            brand_corpus_signals,
            selected_basis=selected_count,
            extraction_status=corpus_extraction_status,
        )
        prior_count = int(family_facts.get("volume", {}).get("prior_count") or 0)
        brand_comparison_allowed = comparison_allowed and prior_count > 0
        brand_comparison_reasons = [
            *comparison_reasons,
            *(
                ["prior_period_empty"]
                if comparison_allowed and prior_count == 0
                else []
            ),
        ]
        dossiers.append(
            {
                "brand_key": brand_key,
                "display_name_en": source["display_name_en"],
                "display_name_zh_cn": source["display_name_zh_cn"],
                "outcome": outcome,
                "enrichment_coverage": _enrichment_coverage(
                    volume,
                    window_days=int(facts["window_days"]),
                ),
                "comparison_status": {
                    "allowed": brand_comparison_allowed,
                    "current_post_count": selected_count,
                    "prior_post_count": prior_count,
                    "selected_coverage": selected_coverage,
                    "prior_coverage": prior_coverage,
                    "suppression_reasons": brand_comparison_reasons,
                },
                "family_summaries": _compact_family_summaries(family_facts),
                "facts": _compact_citable_facts(brand_key, family_facts),
                "shape_summary": _compact_shape_summary(detail["coarse_series"]),
                "corpus_signals_status": corpus_extraction_status,
                "corpus_signals": brand_corpus_signals,
                "evidence_allocation": allocation,
                "evidence": selected_evidence,
                "raw_series": {
                    "coarse": detail["coarse_series"],
                    "fine": detail["fine_series"],
                    "metadata": detail.get("metadata_series", {}),
                },
                "aggregate_inputs": family_facts,
                "source_row_provenance": {
                    "candidate_id": candidate_key["candidate_id"],
                    "kind": candidate_key["kind"],
                    "start_at": candidate_key["start_at"],
                    "end_at": candidate_key["end_at"],
                },
                "evidence_selection_provenance": {
                    "reservoir_count": len(
                        pools.get(str(candidate_key["candidate_id"]), [])
                    ),
                    "dedupe": "source_cluster_id",
                },
            }
        )
    return {
        "packet_schema_version": COMPACT_DOSSIER_SCHEMA_VERSION,
        "snapshot_schema_version": TREND_SNAPSHOT_SCHEMA_VERSION,
        "window_days": facts["window_days"],
        "as_of": facts["as_of"],
        "baseline_context": {
            "kind": "prior_period",
            "start_at": facts["prior_start"],
            "end_at": facts["window_start"],
            "historic_norm_wording_allowed": False,
        },
        "coverage": facts["coverage"],
        "dossiers": dossiers,
    }


def _enrichment_coverage(
    volume: Mapping[str, Any], *, window_days: int
) -> dict[str, Any]:
    total = int(volume.get("selected_count") or 0)
    translated = int(volume.get("selected_translation_succeeded_count") or 0)
    classified = int(volume.get("selected_classification_succeeded_count") or 0)
    enriched = int(volume.get("selected_enriched_count") or 0)
    newest = None
    if window_days == 1:
        newest = {
            "total_post_count": int(volume.get("newest_30m_count") or 0),
            "translation_succeeded_count": int(
                volume.get("newest_30m_translation_succeeded_count") or 0
            ),
            "classification_succeeded_count": int(
                volume.get("newest_30m_classification_succeeded_count") or 0
            ),
            "fully_enriched_count": int(
                volume.get("newest_30m_enriched_count") or 0
            ),
        }
    return {
        "total_post_count": total,
        "translation_succeeded_count": translated,
        "classification_succeeded_count": classified,
        "fully_enriched_count": enriched,
        "translation_status": _enrichment_stage_status(translated, total),
        "classification_status": _enrichment_stage_status(classified, total),
        "newest_30m": newest,
    }


def _enrichment_stage_status(succeeded: int, total: int) -> str:
    if total <= 0 or succeeded <= 0:
        return "unavailable"
    return "complete" if succeeded >= total else "partial"


def _compact_family_summaries(family_facts: Mapping[str, Any]) -> dict[str, Any]:
    total_post_count = int(
        (family_facts.get("volume") or {}).get("selected_count") or 0
    )
    result = {}
    for family in (
        "volume",
        "post_type",
        "sentiment",
        "discourse",
        "china_nationalism",
        "us_nationalism",
    ):
        value = dict(family_facts.get(family) or {})
        classifier_family = family in _CLASSIFIER_DERIVED_FAMILIES
        covered_post_count = (
            int(value.get("selected_covered_count") or 0)
            if classifier_family
            else total_post_count
        )
        status_value = dict(value)
        status_value["selected_total_count"] = total_post_count
        result[family] = {
            "status": _family_summary_status(status_value),
            "covered_post_count": covered_post_count,
            "total_post_count": total_post_count,
            "denominator": covered_post_count,
            "current_leader": _leading_label(value, change=False),
            "largest_change": _leading_label(value, change=True),
        }
    # These source-backed families use the same status vocabulary as the
    # classifier families.  An empty flag set is available data, not an
    # unavailable aggregate.
    for family in ("language", "unsanctioned_flags", "account_role", "corpus_phrases"):
        value = dict(family_facts.get(family) or {})
        classifier_family = family == "unsanctioned_flags"
        covered_post_count = int(value.get("selected_basis_count") or 0)
        status_value = dict(value)
        status_value["selected_total_count"] = total_post_count
        if classifier_family:
            status_value.pop("status", None)
            status_value["selected_covered_count"] = covered_post_count
        summary = {
            "status": (
                _family_summary_status(status_value)
                if classifier_family
                else value.get("status", "unavailable")
            ),
            "covered_post_count": covered_post_count,
            "total_post_count": total_post_count,
            "denominator": covered_post_count,
            "current_leader": _leading_label(value, change=False),
            "largest_change": _leading_label(value, change=True),
        }
        if value.get("unavailable_reason"):
            summary["unavailable_reason"] = value["unavailable_reason"]
        result[family] = summary
    return result


def _family_summary_status(value: Mapping[str, Any]) -> str:
    """Make zero, suppressed source data, and unavailable distinct."""
    explicit = value.get("status")
    if explicit in {"suppressed", "unavailable"}:
        return str(explicit)
    basis = int(
        value.get("selected_total_count")
        or value.get("selected_count")
        or value.get("selected_basis_count")
        or 0
    )
    covered = value.get("selected_covered_count")
    if covered is None:
        return "available" if explicit == "available" or value else "unavailable"
    covered_count = int(covered or 0)
    if covered_count <= 0:
        return "unavailable"
    if basis and covered_count < basis:
        return "partial"
    return "available"


def _corpus_phrase_family_fact(
    signals: Sequence[Mapping[str, Any]],
    *,
    selected_basis: int,
    extraction_status: str = "available",
) -> dict[str, Any]:
    """Express bounded corpus phrases as a stable aggregate family."""
    labels = []
    for signal in signals:
        current = int(signal.get("prevalence") or 0)
        prior = int(signal.get("prior_prevalence") or 0)
        labels.append(
            {
                "key": str(signal.get("phrase") or ""),
                "selected_count": current,
                "prior_count": prior,
                "selected_basis_count": selected_basis,
                "prior_basis_count": 0,
                "brand_change_pp": str(current - prior),
            }
        )
    return {
        "status": (
            "available"
            if selected_basis and extraction_status == "available"
            else "unavailable"
        ),
        "unavailable_reason": (
            extraction_status if extraction_status != "available" else None
        ),
        "selected_basis_count": selected_basis,
        "labels": labels,
    }


def _leading_label(value: Mapping[str, Any], *, change: bool) -> str | None:
    labels = list(value.get("labels") or [])
    if not labels:
        return None
    key = "brand_change_pp" if change else "selected_count"
    return (
        str(
            max(
                labels,
                key=lambda row: (
                    abs(Decimal(str(row.get(key) or "0")))
                    if change
                    else Decimal(str(row.get(key) or "0")),
                    str(row.get("key") or ""),
                ),
            ).get("key")
            or ""
        )
        or None
    )


def _compact_citable_facts(
    brand_key: str, family_facts: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """Return a bounded set of exact facts an editor may quote.

    Each populated family contributes its current leader and, when the prior
    period is comparable, its largest movement.  The LLM therefore receives
    both the present conversation mix and the numerical change behind it
    without receiving every raw label row.
    """
    volume = family_facts.get("volume") or {}
    selected = int(volume.get("selected_count") or 0)
    prior = int(volume.get("prior_count") or 0)
    facts = [
        _compact_fact(
            brand_key=brand_key,
            family="volume",
            metric="post_count",
            label_key=None,
            current_value=selected,
            baseline_value=prior,
            source_value=selected,
            unit="posts",
        )
    ]
    volume_change = volume.get("change_pct")
    if volume_change is not None:
        facts.append(
            _compact_fact(
                brand_key=brand_key,
                family="volume",
                metric="post_count_change_pct",
                label_key=None,
                current_value=selected,
                baseline_value=prior,
                source_value=volume_change,
                unit="percent",
            )
        )

    engagement = family_facts.get("engagement") or {}
    engagement_change = engagement.get("intensity_change_pct")
    if engagement_change is not None:
        facts.append(
            _compact_fact(
                brand_key=brand_key,
                family="engagement",
                metric="intensity_change_pct",
                label_key=None,
                current_value=(engagement.get("selected") or {}).get("intensity"),
                baseline_value=(engagement.get("prior") or {}).get("intensity"),
                source_value=engagement_change,
                unit="percent",
            )
        )

    for family in (
        "post_type",
        "sentiment",
        "discourse",
        "china_nationalism",
        "us_nationalism",
        "language",
        "unsanctioned_flags",
    ):
        family_fact = family_facts.get(family) or {}
        if family in _CLASSIFIER_DERIVED_FAMILIES and not int(
            family_fact.get("selected_covered_count")
            or family_fact.get("selected_basis_count")
            or 0
        ):
            continue
        labels = list(family_fact.get("labels") or [])
        if not labels:
            continue
        current = max(
            labels,
            key=lambda row: (
                int(row.get("selected_count") or 0),
                str(row.get("key") or "").casefold(),
                str(row.get("key") or ""),
            ),
        )
        facts.append(
            _compact_label_fact(
                brand_key=brand_key,
                family=family,
                label=current,
                metric_suffix="share_pct",
                source_value=_label_share_percent(current, selected=True),
                unit="percent",
            )
        )
        comparable = [row for row in labels if row.get("brand_change_pp") is not None]
        if comparable:
            changed = max(
                comparable,
                key=lambda row: (
                    abs(Decimal(str(row.get("brand_change_pp") or "0"))),
                    str(row.get("key") or "").casefold(),
                    str(row.get("key") or ""),
                ),
            )
            facts.append(
                _compact_label_fact(
                    brand_key=brand_key,
                    family=family,
                    label=changed,
                    metric_suffix="share_change_pp",
                    source_value=changed["brand_change_pp"],
                    unit="percentage_points",
                )
            )

    account_labels = {
        str(row.get("key") or ""): row
        for row in (family_facts.get("account_role") or {}).get("labels", [])
    }
    first_party_current = sum(
        int((account_labels.get(role) or {}).get("selected_count") or 0)
        for role in ("official", "staff")
    )
    first_party_prior = sum(
        int((account_labels.get(role) or {}).get("prior_count") or 0)
        for role in ("official", "staff")
    )
    if first_party_current or first_party_prior:
        facts.append(
            _compact_fact(
                brand_key=brand_key,
                family="account_role",
                metric="official_staff_post_count",
                label_key="official_staff",
                current_value=first_party_current,
                baseline_value=first_party_prior,
                source_value=first_party_current,
                unit="posts",
            )
        )

    corpus_labels = list((family_facts.get("corpus_phrases") or {}).get("labels") or [])
    if corpus_labels:
        phrase = max(
            corpus_labels,
            key=lambda row: (
                int(row.get("selected_count") or 0),
                str(row.get("key") or "").casefold(),
                str(row.get("key") or ""),
            ),
        )
        facts.append(
            _compact_fact(
                brand_key=brand_key,
                family="corpus_phrases",
                metric="document_count",
                label_key=str(phrase.get("key") or ""),
                current_value=int(phrase.get("selected_count") or 0),
                baseline_value=int(phrase.get("prior_count") or 0),
                source_value=int(phrase.get("selected_count") or 0),
                unit="posts",
            )
        )
    for fact in facts:
        fact["coverage_scope"] = _fact_coverage_scope(
            str(fact["family"]),
            family_facts,
            total_post_count=selected,
        )
    return facts[:MAX_QUANTITATIVE_FACTS_PER_CANDIDATE]


def _fact_coverage_scope(
    family: str,
    family_facts: Mapping[str, Any],
    *,
    total_post_count: int,
) -> dict[str, Any]:
    value = family_facts.get(family) or {}
    if family in _CLASSIFIER_DERIVED_FAMILIES and family != "unsanctioned_flags":
        covered = int(value.get("selected_covered_count") or 0)
    elif family == "unsanctioned_flags":
        covered = int(value.get("selected_basis_count") or 0)
    elif family == "engagement":
        covered = int((value.get("selected") or {}).get("eligible_count") or 0)
    else:
        covered = total_post_count
    return {
        "status": _enrichment_stage_status(covered, total_post_count),
        "covered_post_count": covered,
        "total_post_count": total_post_count,
    }


def _compact_label_fact(
    *,
    brand_key: str,
    family: str,
    label: Mapping[str, Any],
    metric_suffix: str,
    source_value: object,
    unit: str,
) -> dict[str, Any]:
    label_key = str(label.get("key") or "")
    return _compact_fact(
        brand_key=brand_key,
        family=family,
        metric=f"{label_key}_{metric_suffix}",
        label_key=label_key,
        current_value=_label_share_percent(label, selected=True),
        baseline_value=_label_share_percent(label, selected=False),
        source_value=source_value,
        unit=unit,
    )


def _label_share_percent(label: Mapping[str, Any], *, selected: bool) -> Decimal:
    prefix = "selected" if selected else "prior"
    explicit = label.get(f"{prefix}_prevalence")
    if explicit is not None:
        return Decimal(str(explicit)) * 100
    count = int(label.get(f"{prefix}_count") or 0)
    basis = int(label.get(f"{prefix}_basis_count") or 0)
    return Decimal(count) * 100 / Decimal(basis) if basis else Decimal(0)


def _compact_fact(
    *,
    brand_key: str,
    family: str,
    metric: str,
    label_key: str | None,
    current_value: object,
    baseline_value: object,
    source_value: object,
    unit: str,
) -> dict[str, Any]:
    exact = Decimal(str(source_value))
    magnitude = abs(exact)
    quantum = Decimal("0.1") if magnitude < 1 else Decimal(1)
    rounded = magnitude.quantize(quantum, rounding=ROUND_HALF_UP)
    display = format(rounded, "f")
    if "." in display:
        display = display.rstrip("0").rstrip(".")
    suffix_en = {
        "percent": "%",
        "percentage_points": " pts",
        "posts": " posts",
    }[unit]
    suffix_zh_cn = {
        "percent": "%",
        "percentage_points": "个百分点",
        "posts": "条帖子",
    }[unit]
    identity = ":".join(
        value for value in (brand_key, family, metric, label_key) if value
    )
    return {
        "fact_id": f"f:{identity}",
        "family": family,
        "metric": metric,
        "label_key": label_key,
        "current_value": _fact_value(current_value),
        "baseline_value": _fact_value(baseline_value),
        "source_value": format(exact, "f"),
        "unit": unit,
        "direction": ("increase" if exact > 0 else "decrease" if exact < 0 else "flat"),
        "display_en": display + suffix_en,
        "display_zh_cn": display + suffix_zh_cn,
    }


def _fact_value(value: object) -> str | None:
    if value is None:
        return None
    try:
        exact = Decimal(str(value))
    except InvalidOperation:
        return str(value)
    return format(exact, "f")


def _compact_shape_summary(
    series: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Describe the shape without exposing the full bucket array."""
    if not series:
        return {
            "direction": "flat",
            "start_segment_post_count": 0,
            "end_segment_post_count": 0,
            "total_change_pct": None,
            "dominant_transition": None,
            "peak": None,
            "trough": None,
        }
    counts = [int(row.get("post_count") or 0) for row in series]
    start = counts[0]
    end = counts[-1]
    net = end - start
    transitions = [
        (index, counts[index] - counts[index - 1]) for index in range(1, len(counts))
    ]
    total_movement = sum(abs(change) for _, change in transitions)
    dominant = max(
        transitions,
        key=lambda item: (abs(item[1]), -item[0]),
        default=None,
    )
    dominant_packet = None
    if dominant is not None:
        index, change = dominant
        dominant_packet = {
            "from": series[index - 1].get("start_at"),
            "to": series[index].get("start_at"),
            "post_count_change": change,
            "net_change_share_pct": (
                format(
                    (Decimal(abs(change)) * 100 / Decimal(total_movement)).quantize(
                        Decimal("0.1"), rounding=ROUND_HALF_UP
                    ),
                    "f",
                )
                if total_movement
                else "0.0"
            ),
        }
    peak_index = max(range(len(counts)), key=lambda index: (counts[index], -index))
    trough_index = min(range(len(counts)), key=lambda index: (counts[index], index))
    return {
        "direction": "increase" if net > 0 else "decrease" if net < 0 else "flat",
        "start_segment_post_count": start,
        "end_segment_post_count": end,
        "total_change_pct": (
            format(
                (Decimal(net) * 100 / Decimal(start)).quantize(
                    Decimal("0.1"), rounding=ROUND_HALF_UP
                ),
                "f",
            )
            if start
            else None
        ),
        "comparison_state": "available" if start else "new_or_low_base",
        "dominant_transition": dominant_packet,
        "peak": {
            "at": series[peak_index].get("start_at"),
            "post_count": counts[peak_index],
        },
        "trough": {
            "at": series[trough_index].get("start_at"),
            "post_count": counts[trough_index],
        },
    }


def _project_compact_ranking_packet(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    dossiers = []
    for dossier in snapshot.get("dossiers", []):
        row = _provider_dossier(dossier)
        # Ranking is the only all-brand transport. Keep its content-led
        # signals and citable facts, but omit per-brand trajectories/episodes
        # and cap evidence previews so 20+ brands fit the shared budget.
        for key in ("metadata_trajectories", "episodes", "evidence_allocation"):
            row.pop(key, None)
        row["evidence"] = [
            {
                "evidence_id": evidence["evidence_id"],
                "created_at": evidence.get("created_at"),
                "excerpt": evidence.get("excerpt"),
                "first_party_role": evidence.get("first_party_role", "public_opaque"),
            }
            for evidence in dossier.get("evidence", [])[:2]
        ]
        dossiers.append(row)
    return {
        "packet_schema_version": COMPACT_DOSSIER_SCHEMA_VERSION,
        "window_days": snapshot["window_days"],
        "as_of": snapshot["as_of"],
        "baseline_context": snapshot["baseline_context"],
        "dossiers": dossiers,
    }


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
    evidence_by_candidate, evidence_allocations = _select_evidence_with_allocation(
        evidence_rows,
        candidates=evidence_candidates,
        policy=evidence_policy,
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
            "starts": [row["start_at"] for row in first[f"{resolution}_series"]],
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
            "coverage_ratios": [row["engagement"]["coverage_ratio"] for row in series],
            "likes": [totals_value(row, "likes") for row in series],
            "reposts": [totals_value(row, "reposts") for row in series],
            "quotes": [totals_value(row, "quotes") for row in series],
            "replies": [totals_value(row, "replies") for row in series],
            "interactions": [totals_value(row, "interactions") for row in series],
            "intensities": [row["engagement"]["intensity"] for row in series],
            "concentrations": [row["engagement"]["concentration"] for row in series],
            "post_kinds": {},
        },
    }
    if include_post_kinds:
        for kind in ("source_post", "repost", "quote"):
            result["engagement"]["post_kinds"][kind] = {
                "eligible_counts": [
                    int(row["engagement"]["by_post_kind"][kind]["eligible_count"])
                    for row in series
                ],
                "missing_counts": [
                    int(row["engagement"]["by_post_kind"][kind]["missing_count"])
                    for row in series
                ],
                "interactions": [
                    (
                        int(
                            row["engagement"]["by_post_kind"][kind]["totals"][
                                "interactions"
                            ]
                        )
                        if row["engagement"]["by_post_kind"][kind]["totals"] is not None
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
        coverage_counts = [int(value) for value in source.get("coverage_counts", [])]
        if len(coverage_counts) != len(post_counts):
            coverage_counts = [0] * len(post_counts)
        labels = {}
        for fact in facts.get("labels", []):
            key = str(fact.get("key") or "")
            counts = [int(value) for value in raw_labels.get(key, [])]
            if len(counts) != len(post_counts):
                counts = [0] * len(post_counts)
            if (
                not any(counts)
                and not int(fact.get("selected_count") or 0)
                and not int(fact.get("prior_count") or 0)
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
        (Decimal(numerator) / Decimal(denominator)).quantize(Decimal("0.000001"))
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


def _fetch_stable_family_facts(
    candidates: Sequence[Mapping[str, Any]],
    *,
    comparison_allowed: bool = True,
) -> dict[str, dict[str, dict[str, Any]]]:
    """Aggregate non-classifier dossier families in one set-based query.

    These are source-backed values, not inferred taxonomy.  In particular an
    empty unsanctioned flag set has status ``available`` when classification
    completed for at least one post, rather than being represented as an
    invented ``none`` flag.
    """
    if not candidates:
        return {}
    sql = """
        WITH requested AS (
            SELECT DISTINCT ON (brand_key)
                brand_key, start_at, end_at
            FROM unnest(%s::text[], %s::timestamptz[], %s::timestamptz[])
                AS item(brand_key, start_at, end_at)
            ORDER BY brand_key
        ),
        edges AS (
            SELECT
                r.brand_key,
                p.tweet_id,
                CASE WHEN p.created_at >= r.start_at
                     THEN 'selected' ELSE 'prior' END AS period,
                coalesce(nullif(btrim(p.lang), ''), 'und') AS language,
                coalesce(role.role_id::text, 'public_opaque') AS account_role,
                coalesce(pes.classification_status, 'pending') AS classification_status
            FROM requested r
            JOIN posts_brands pb ON pb.brand_id::text = r.brand_key
            JOIN posts p ON p.tweet_id = pb.post_id
            LEFT JOIN post_enrichment_states pes ON pes.post_id = p.tweet_id
            LEFT JOIN LATERAL (
                SELECT ba.role_id
                FROM brands_accounts ba
                WHERE ba.brand_id::text = r.brand_key
                  AND ba.accounts_id = p.author_id
                  AND ba.role_id IN ('official', 'staff')
                ORDER BY CASE ba.role_id WHEN 'official' THEN 0 ELSE 1 END
                LIMIT 1
            ) role ON true
            WHERE p.created_at >= r.start_at - (r.end_at - r.start_at)
              AND p.created_at < r.end_at
        ),
        bases AS (
            SELECT brand_key, period, 'language'::text AS family,
                   count(*)::integer AS count
            FROM edges GROUP BY brand_key, period
            UNION ALL
            SELECT brand_key, period, 'account_role', count(*)::integer
            FROM edges GROUP BY brand_key, period
            UNION ALL
            SELECT brand_key, period, 'unsanctioned_flags',
                   count(*) FILTER (WHERE classification_status = 'succeeded')::integer
            FROM edges GROUP BY brand_key, period
        ),
        labels AS (
            SELECT brand_key, period, 'language'::text AS family, language AS label
            FROM edges
            UNION ALL
            SELECT brand_key, period, 'account_role', account_role FROM edges
            UNION ALL
            SELECT e.brand_key, e.period, 'unsanctioned_flags', flag.flag_key
            FROM edges e
            JOIN posts_unsanctioned_flags u ON u.post_id = e.tweet_id
            CROSS JOIN LATERAL jsonb_array_elements_text(
                coalesce(u.flag_set, '[]'::jsonb)
            ) flag(flag_key)
            WHERE e.classification_status = 'succeeded'
        ),
        label_counts AS (
            SELECT brand_key, family, label,
                   count(*) FILTER (WHERE period = 'selected')::integer AS selected_count,
                   count(*) FILTER (WHERE period = 'prior')::integer AS prior_count
            FROM labels GROUP BY brand_key, family, label
        ),
        basis_counts AS (
            SELECT brand_key, family,
                   max(count) FILTER (WHERE period = 'selected')::integer AS selected_count,
                   max(count) FILTER (WHERE period = 'prior')::integer AS prior_count
            FROM bases GROUP BY brand_key, family
        )
        SELECT 'label'::text AS row_type, brand_key, family, label,
               selected_count, prior_count FROM label_counts
        UNION ALL
        SELECT 'basis', brand_key, family, NULL::text,
               selected_count, prior_count FROM basis_counts
        ORDER BY row_type, brand_key, family, label
    """
    params = [
        [str(row["brand_key"]) for row in candidates],
        [_parse_utc(str(row["start_at"])) for row in candidates],
        [_parse_utc(str(row["end_at"])) for row in candidates],
    ]
    labels: dict[tuple[str, str], list[dict[str, Any]]] = {}
    bases: dict[tuple[str, str], tuple[int, int]] = {}
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        for row_type, brand_key, family, label, selected, prior in cursor.fetchall():
            key = (str(brand_key), str(family))
            if row_type == "basis":
                bases[key] = (int(selected or 0), int(prior or 0))
            else:
                labels.setdefault(key, []).append(
                    {
                        "key": str(label),
                        "selected_count": int(selected or 0),
                        "prior_count": int(prior or 0),
                    }
                )
    result: dict[str, dict[str, dict[str, Any]]] = {}
    for brand_key in {str(row["brand_key"]) for row in candidates}:
        result[brand_key] = {}
        for family in ("language", "unsanctioned_flags", "account_role"):
            selected_basis, prior_basis = bases.get((brand_key, family), (0, 0))
            values = labels.get((brand_key, family), [])
            for value in values:
                selected_prevalence = (
                    Decimal(value["selected_count"]) / Decimal(selected_basis)
                    if selected_basis
                    else Decimal(0)
                )
                prior_prevalence = (
                    Decimal(value["prior_count"]) / Decimal(prior_basis)
                    if prior_basis
                    else Decimal(0)
                )
                value.update(
                    selected_basis_count=selected_basis,
                    prior_basis_count=prior_basis,
                    selected_prevalence=format(selected_prevalence, "f"),
                    prior_prevalence=format(prior_prevalence, "f"),
                    brand_change_pp=(
                        format((selected_prevalence - prior_prevalence) * 100, "f")
                        if comparison_allowed
                        else None
                    ),
                )
            result[brand_key][family] = {
                "status": "available" if selected_basis else "unavailable",
                "selected_basis_count": selected_basis,
                "prior_basis_count": prior_basis,
                "labels": values,
            }
    return result


def _fetch_corpus_phrase_signals(
    candidates: Sequence[Mapping[str, Any]], *, as_of: datetime
) -> tuple[dict[str, list[dict[str, Any]]], str]:
    """Return at most eight prominent two-word phrases per brand.

    PostgreSQL performs one date-bounded source read. Python then scans every
    deduplicated document twice: first for exact current/prior document counts,
    then only for phrases tied for a possible top-eight position. This avoids
    expanding the corpus into a million-row SQL window/grouping pipeline while
    keeping the final counts, peer coverage, burst bounds, and excerpts exact.
    Raw source rows exist only inside this immutable snapshot transaction and
    are hard-bounded by row, text, token, and vocabulary ceilings. Crossing a
    ceiling makes this optional family atomically ``resource_limited`` for all
    brands; no sampled or partial phrase result escapes to the provider.
    """
    if not candidates:
        return {}, "available"
    as_of_utc = _as_utc(as_of)
    specs: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        brand_key = str(candidate["brand_key"])
        if brand_key in specs:
            raise TrendSnapshotTransactionError("duplicate_corpus_phrase_brand")
        start_at = _parse_utc(str(candidate["start_at"]))
        end_at = _parse_utc(str(candidate["end_at"]))
        if end_at <= start_at:
            raise TrendSnapshotTransactionError("invalid_corpus_phrase_window")
        upper_at = min(end_at, as_of_utc)
        specs[brand_key] = {
            "candidate_id": str(candidate["candidate_id"]),
            "start_at": start_at,
            "end_at": end_at,
            "upper_at": upper_at,
            "lower_at": start_at - (end_at - start_at),
        }
    lower_at = min(spec["lower_at"] for spec in specs.values())
    upper_at = max(spec["upper_at"] for spec in specs.values())
    if upper_at <= lower_at:
        return {}, "available"
    rows_by_brand: dict[str, list[tuple[Any, ...]]] = defaultdict(list)
    source_row_count = 0
    source_text_characters = 0
    with connection.cursor() as cursor:
        cursor.execute(
            _CORPUS_SOURCE_ROWS_SQL,
            [
                sorted(specs),
                lower_at,
                upper_at,
                MAX_CORPUS_SOURCE_ROWS + 1,
            ],
        )
        while batch := cursor.fetchmany(500):
            for brand_key, tweet_id, source_root_id, created_at, text in batch:
                source_row_count += 1
                text_characters = len(str(text or ""))
                source_text_characters += text_characters
                if (
                    source_row_count > MAX_CORPUS_SOURCE_ROWS
                    or text_characters > MAX_CORPUS_TEXT_CHARACTERS
                    or source_text_characters > MAX_CORPUS_SOURCE_TEXT_CHARACTERS
                ):
                    return {}, "resource_limited"
                rows_by_brand[str(brand_key)].append(
                    (tweet_id, source_root_id, created_at, text)
                )

    # Peer count is the final ranking tie-breaker. Retain every phrase tied at
    # the eighth primary (selected count, selected-minus-prior) score so the
    # second pass can apply that tie-breaker without approximating the top 8.
    retained: dict[str, set[str]] = {}
    retained_phrase_count = 0
    exact_counts: dict[tuple[str, str], tuple[int, int]] = {}
    try:
        for brand_key, spec in specs.items():
            counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])
            for document in _iter_corpus_documents(
                rows_by_brand.get(brand_key, []), spec
            ):
                count_index = 0 if document["selected"] else 1
                for phrase in document["phrases"]:
                    counts[phrase][count_index] += 1
                if len(counts) > MAX_CORPUS_DISTINCT_PHRASES_PER_BRAND:
                    raise _CorpusPhraseResourceLimit
            top_scores = nlargest(
                8,
                (
                    (selected, selected - prior)
                    for selected, prior in counts.values()
                    if selected > 0
                ),
            )
            if not top_scores:
                retained[brand_key] = set()
                continue
            boundary_score = top_scores[-1]
            retained[brand_key] = {
                phrase
                for phrase, (selected, prior) in counts.items()
                if (
                    selected,
                    selected - prior,
                )
                >= boundary_score
            }
            retained_phrase_count += len(retained[brand_key])
            if retained_phrase_count > MAX_CORPUS_RETAINED_PHRASES:
                raise _CorpusPhraseResourceLimit
            for phrase in retained[brand_key]:
                exact_counts[(brand_key, phrase)] = tuple(counts[phrase])
    except _CorpusPhraseResourceLimit:
        return {}, "resource_limited"

    candidate_phrases = set().union(*retained.values()) if retained else set()
    peer_brands: dict[str, set[str]] = defaultdict(set)
    representatives: dict[tuple[str, str], tuple[str, str]] = {}
    burst_bounds: dict[tuple[str, str], tuple[int, int]] = {}
    try:
        if candidate_phrases:
            for brand_key, spec in specs.items():
                own_phrases = retained.get(brand_key, set())
                for document in _iter_corpus_documents(
                    rows_by_brand.get(brand_key, []), spec
                ):
                    if not document["selected"]:
                        continue
                    matching = document["phrases"] & candidate_phrases
                    for phrase in matching:
                        peer_brands[phrase].add(brand_key)
                    for phrase in matching & own_phrases:
                        key = (brand_key, phrase)
                        representatives.setdefault(
                            key,
                            (
                                str(document["tweet_id"]),
                                str(document["normalized_text"]),
                            ),
                        )
                        bucket = int(document["burst_bucket"])
                        prior_bounds = burst_bounds.get(key)
                        burst_bounds[key] = (
                            (bucket, bucket)
                            if prior_bounds is None
                            else (
                                min(prior_bounds[0], bucket),
                                max(prior_bounds[1], bucket),
                            )
                        )
    except _CorpusPhraseResourceLimit:
        return {}, "resource_limited"

    result: dict[str, list[dict[str, Any]]] = {}
    for brand_key, phrases in retained.items():
        ranked = sorted(
            phrases,
            key=lambda phrase: (
                -exact_counts[(brand_key, phrase)][0],
                -(
                    exact_counts[(brand_key, phrase)][0]
                    - exact_counts[(brand_key, phrase)][1]
                ),
                len(peer_brands[phrase]),
                phrase,
            ),
        )[:8]
        candidate_id = specs[brand_key]["candidate_id"]
        for phrase_text in ranked:
            selected, prior = exact_counts[(brand_key, phrase_text)]
            tweet_id, representative_text = representatives.get(
                (brand_key, phrase_text), ("", "")
            )
            start, end = burst_bounds.get((brand_key, phrase_text), (0, 0))
            result.setdefault(brand_key, []).append(
                {
                    "corpus_signal_id": "cs_"
                    + _digest(str(candidate_id), phrase_text)[:24],
                    "phrase": phrase_text,
                    "prevalence": int(selected or 0),
                    "prior_prevalence": int(prior or 0),
                    "peer_brand_count": len(peer_brands[phrase_text]),
                    "burst_interval": {
                        "start_bucket": int(start or 0),
                        "end_bucket": int(end or 0),
                    },
                    # The identifier is opaque and deterministic. It names a
                    # source row without leaking its raw post ID or author.
                    "representative_evidence_ids": [
                        "ce_"
                        + _digest(str(candidate_id), str(tweet_id), phrase_text)[:24]
                    ]
                    if tweet_id
                    else [],
                    "representative_excerpt": normalized_excerpt(
                        str(representative_text or ""), max_characters=280
                    ),
                }
            )
    return result, "available"


def _iter_corpus_documents(
    rows: Sequence[tuple[Any, ...]], spec: Mapping[str, Any]
) -> Iterator[dict[str, Any]]:
    """Yield source-deduplicated phrase documents for one brand."""
    seen_sources: set[tuple[str, str]] = set()
    start_at = spec["start_at"]
    end_at = spec["end_at"]
    upper_at = spec["upper_at"]
    lower_at = spec["lower_at"]
    duration_seconds = (end_at - start_at).total_seconds()
    for tweet_id, source_root_id, created_at, text in rows:
        if created_at is None or created_at < lower_at or created_at >= upper_at:
            continue
        source_text = unicodedata.normalize("NFC", str(text or ""))
        if len(source_text) > MAX_CORPUS_TEXT_CHARACTERS:
            raise _CorpusPhraseResourceLimit
        lowered = source_text.lower()
        source_key = (
            str(source_root_id or tweet_id),
            _WHITESPACE_RE.sub(" ", lowered),
        )
        if source_key in seen_sources:
            continue
        seen_sources.add(source_key)
        normalized = _CORPUS_TOKEN_SEPARATOR_RE.sub(" ", lowered).strip()
        tokens = [token for token in normalized.split() if len(token) >= 2]
        if len(tokens) > MAX_CORPUS_TOKENS_PER_DOCUMENT:
            raise _CorpusPhraseResourceLimit
        phrases = {f"{current} {following}" for current, following in pairwise(tokens)}
        selected = created_at >= start_at
        yield {
            "tweet_id": str(tweet_id),
            "normalized_text": normalized,
            "phrases": phrases,
            "selected": selected,
            "burst_bucket": (
                int(4 * (created_at - start_at).total_seconds() / duration_seconds)
                if selected and duration_seconds > 0
                else 0
            ),
        }


def _fetch_evidence_rows(
    candidates: Sequence[Mapping[str, Any]],
    *,
    as_of: datetime,
    rank_limit: int,
) -> list[dict[str, Any]]:
    if not candidates:
        return []
    # Sample each candidate window before ranking evidence roles. The four time
    # buckets keep older catalyst posts eligible without letting any role scan
    # the full brand history. A post gets rank_limit + 1 for streams that did
    # not select it; downstream role eligibility therefore uses a real ordinal
    # only for a bounded selection.
    sql = """
        WITH requested_bounds AS (
            SELECT
                item.candidate_id,
                item.brand_key,
                item.start_at,
                item.end_at,
                item.position,
                bounds.as_of,
                bounds.rank_limit
            FROM unnest(
                %s::text[], %s::text[], %s::timestamptz[],
                %s::timestamptz[]
            ) WITH ORDINALITY AS item(
                candidate_id, brand_key, start_at, end_at, position
            )
            CROSS JOIN (
                SELECT %s::timestamptz AS as_of, %s::bigint AS rank_limit
            ) bounds
        ),
        time_buckets AS (
            SELECT
                r.*,
                bucket.bucket_index,
                r.start_at
                    + (r.end_at - r.start_at)
                    * (bucket.bucket_index::double precision / 4.0)
                    AS bucket_start,
                r.start_at
                    + (r.end_at - r.start_at)
                    * ((bucket.bucket_index + 1)::double precision / 4.0)
                    AS bucket_end
            FROM requested_bounds r
            CROSS JOIN generate_series(0, 3) AS bucket(bucket_index)
        ),
        candidate_pool AS (
            SELECT
                bucket.position,
                bucket.candidate_id,
                bucket.brand_key,
                ranked.tweet_id
            FROM time_buckets bucket
            CROSS JOIN LATERAL (
                SELECT p.tweet_id::text AS tweet_id
                FROM posts p
                WHERE p.created_at >= bucket.bucket_start
                  AND p.created_at < bucket.bucket_end
                  AND p.created_at < bucket.as_of
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
                  AND EXISTS (
                        SELECT 1
                        FROM posts_brands pb
                        WHERE pb.post_id = p.tweet_id
                          AND pb.brand_id = bucket.brand_key
                  )
                ORDER BY p.created_at DESC, p.tweet_id ASC
                LIMIT bucket.rank_limit
            ) ranked
        ),
        official_accounts AS (
            SELECT ba.brand_id::text AS brand_key, ba.accounts_id,
                   min(ba.role_id::text) AS first_party_role
            FROM brands_accounts ba
            JOIN requested_bounds r ON r.brand_key = ba.brand_id::text
            WHERE ba.role_id IN ('official', 'staff')
            GROUP BY ba.brand_id, ba.accounts_id
        ),
        official_stream AS (
            SELECT
                r.position,
                r.candidate_id,
                r.brand_key,
                NULL::text AS dominant_discourse,
                NULL::text AS dominant_sentiment,
                ranked.tweet_id,
                ranked.stream_rank::bigint AS official_rank,
                r.rank_limit + 1 AS catalyst_rank,
                r.rank_limit + 1 AS original_rank,
                r.rank_limit + 1 AS discourse_rank,
                r.rank_limit + 1 AS contrast_rank
            FROM requested_bounds r
            CROSS JOIN LATERAL unnest(ARRAY(
                SELECT p.tweet_id::text
                FROM candidate_pool pool
                JOIN posts p ON p.tweet_id = pool.tweet_id
                LEFT JOIN official_accounts official
                  ON official.brand_key = r.brand_key
                 AND official.accounts_id = p.author_id
                WHERE pool.position = r.position
                ORDER BY
                    (official.accounts_id IS NOT NULL) DESC,
                    (
                        p.metrics_refreshed_at IS NOT NULL
                        AND p.metrics_refreshed_at <= r.as_of
                    ) DESC,
                    CASE
                        WHEN p.metrics_refreshed_at IS NOT NULL
                         AND p.metrics_refreshed_at <= r.as_of
                        THEN coalesce(p.like_count, 0)
                           + coalesce(p.retweet_count, 0)
                           + coalesce(p.quote_count, 0)
                           + coalesce(p.reply_count, 0)
                        ELSE 0
                    END DESC,
                    p.created_at ASC,
                    p.tweet_id ASC
                LIMIT r.rank_limit
            )) WITH ORDINALITY AS ranked(tweet_id, stream_rank)
        ),
        catalyst_stream AS (
            SELECT
                r.position,
                r.candidate_id,
                r.brand_key,
                NULL::text AS dominant_discourse,
                NULL::text AS dominant_sentiment,
                ranked.tweet_id,
                r.rank_limit + 1 AS official_rank,
                ranked.stream_rank::bigint AS catalyst_rank,
                r.rank_limit + 1 AS original_rank,
                r.rank_limit + 1 AS discourse_rank,
                r.rank_limit + 1 AS contrast_rank
            FROM requested_bounds r
            CROSS JOIN LATERAL unnest(ARRAY(
                SELECT p.tweet_id::text
                FROM candidate_pool pool
                JOIN posts p ON p.tweet_id = pool.tweet_id
                WHERE pool.position = r.position
                ORDER BY
                    p.created_at ASC,
                    CASE
                        WHEN p.metrics_refreshed_at IS NOT NULL
                         AND p.metrics_refreshed_at <= r.as_of
                        THEN coalesce(p.like_count, 0)
                           + coalesce(p.retweet_count, 0)
                           + coalesce(p.quote_count, 0)
                           + coalesce(p.reply_count, 0)
                        ELSE 0
                    END DESC,
                    p.tweet_id ASC
                LIMIT r.rank_limit
            )) WITH ORDINALITY AS ranked(tweet_id, stream_rank)
        ),
        original_stream AS (
            SELECT
                r.position,
                r.candidate_id,
                r.brand_key,
                NULL::text AS dominant_discourse,
                NULL::text AS dominant_sentiment,
                ranked.tweet_id,
                r.rank_limit + 1 AS official_rank,
                r.rank_limit + 1 AS catalyst_rank,
                ranked.stream_rank::bigint AS original_rank,
                r.rank_limit + 1 AS discourse_rank,
                r.rank_limit + 1 AS contrast_rank
            FROM requested_bounds r
            CROSS JOIN LATERAL unnest(ARRAY(
                SELECT p.tweet_id::text
                FROM candidate_pool pool
                JOIN posts p ON p.tweet_id = pool.tweet_id
                WHERE pool.position = r.position
                ORDER BY
                    (NOT coalesce(p.is_retweet, false)) DESC,
                    (
                        p.metrics_refreshed_at IS NOT NULL
                        AND p.metrics_refreshed_at <= r.as_of
                    ) DESC,
                    CASE
                        WHEN p.metrics_refreshed_at IS NOT NULL
                         AND p.metrics_refreshed_at <= r.as_of
                        THEN coalesce(p.like_count, 0)
                           + coalesce(p.retweet_count, 0)
                           + coalesce(p.quote_count, 0)
                           + coalesce(p.reply_count, 0)
                        ELSE 0
                    END DESC,
                    p.created_at DESC,
                    p.tweet_id ASC
                LIMIT r.rank_limit
            )) WITH ORDINALITY AS ranked(tweet_id, stream_rank)
        ),
        evidence_seed AS (
            SELECT
                position,
                candidate_id,
                brand_key,
                tweet_id,
                min(official_rank) AS official_rank,
                min(catalyst_rank) AS catalyst_rank,
                min(original_rank) AS original_rank,
                min(discourse_rank) AS discourse_rank,
                min(contrast_rank) AS contrast_rank
            FROM (
                SELECT * FROM official_stream
                UNION ALL
                SELECT * FROM catalyst_stream
                UNION ALL
                SELECT * FROM original_stream
            ) seed_stream_rows
            GROUP BY position, candidate_id, brand_key, tweet_id
        ),
        requested AS (
            SELECT
                r.*,
                discourse.dominant_discourse,
                sentiment.dominant_sentiment
            FROM requested_bounds r
            LEFT JOIN LATERAL (
                SELECT d.discourse_key::text AS dominant_discourse
                FROM evidence_seed seed
                JOIN posts_brands_discourse d
                  ON d.post_id = seed.tweet_id
                 AND d.brand_id::text = seed.brand_key
                WHERE seed.position = r.position
                GROUP BY d.discourse_key::text
                ORDER BY
                    count(DISTINCT seed.tweet_id) DESC,
                    lower(d.discourse_key::text),
                    d.discourse_key::text
                LIMIT 1
            ) discourse ON TRUE
            LEFT JOIN LATERAL (
                SELECT s.sentiment::text AS dominant_sentiment
                FROM evidence_seed seed
                JOIN posts_brands_signals s
                  ON s.post_id = seed.tweet_id
                 AND s.brand_id::text = seed.brand_key
                WHERE seed.position = r.position
                  AND s.sentiment IS NOT NULL
                GROUP BY s.sentiment::text
                ORDER BY
                    count(DISTINCT seed.tweet_id) DESC,
                    lower(s.sentiment::text),
                    s.sentiment::text
                LIMIT 1
            ) sentiment ON TRUE
        ),
        seed_rows AS (
            SELECT
                seed.position,
                seed.candidate_id,
                seed.brand_key,
                requested.dominant_discourse,
                requested.dominant_sentiment,
                seed.tweet_id,
                seed.official_rank,
                seed.catalyst_rank,
                seed.original_rank,
                seed.discourse_rank,
                seed.contrast_rank
            FROM evidence_seed seed
            JOIN requested ON requested.position = seed.position
        ),
        discourse_stream AS (
            SELECT
                r.position,
                r.candidate_id,
                r.brand_key,
                r.dominant_discourse,
                r.dominant_sentiment,
                ranked.tweet_id,
                r.rank_limit + 1 AS official_rank,
                r.rank_limit + 1 AS catalyst_rank,
                r.rank_limit + 1 AS original_rank,
                ranked.stream_rank::bigint AS discourse_rank,
                r.rank_limit + 1 AS contrast_rank
            FROM requested r
            CROSS JOIN LATERAL unnest(ARRAY(
                SELECT p.tweet_id::text
                FROM candidate_pool pool
                JOIN posts p ON p.tweet_id = pool.tweet_id
                WHERE pool.position = r.position
                ORDER BY
                    (
                        r.dominant_discourse IS NOT NULL
                        AND EXISTS (
                            SELECT 1
                            FROM posts_brands_discourse d
                            WHERE d.post_id = p.tweet_id
                              AND d.brand_id::text = r.brand_key
                              AND d.discourse_key::text = r.dominant_discourse
                        )
                    ) DESC,
                    (
                        p.metrics_refreshed_at IS NOT NULL
                        AND p.metrics_refreshed_at <= r.as_of
                    ) DESC,
                    CASE
                        WHEN p.metrics_refreshed_at IS NOT NULL
                         AND p.metrics_refreshed_at <= r.as_of
                        THEN coalesce(p.like_count, 0)
                           + coalesce(p.retweet_count, 0)
                           + coalesce(p.quote_count, 0)
                           + coalesce(p.reply_count, 0)
                        ELSE 0
                    END DESC,
                    p.created_at DESC,
                    p.tweet_id ASC
                LIMIT r.rank_limit
            )) WITH ORDINALITY AS ranked(tweet_id, stream_rank)
        ),
        contrast_stream AS (
            SELECT
                r.position,
                r.candidate_id,
                r.brand_key,
                r.dominant_discourse,
                r.dominant_sentiment,
                ranked.tweet_id,
                r.rank_limit + 1 AS official_rank,
                r.rank_limit + 1 AS catalyst_rank,
                r.rank_limit + 1 AS original_rank,
                r.rank_limit + 1 AS discourse_rank,
                ranked.stream_rank::bigint AS contrast_rank
            FROM requested r
            CROSS JOIN LATERAL unnest(ARRAY(
                SELECT p.tweet_id::text
                FROM candidate_pool pool
                JOIN posts p ON p.tweet_id = pool.tweet_id
                WHERE pool.position = r.position
                ORDER BY
                    (
                        r.dominant_sentiment IS NOT NULL
                        AND EXISTS (
                            SELECT 1
                            FROM posts_brands_signals s
                            WHERE s.post_id = p.tweet_id
                              AND s.brand_id::text = r.brand_key
                              AND s.sentiment IS NOT NULL
                        )
                        AND NOT EXISTS (
                            SELECT 1
                            FROM posts_brands_signals s
                            WHERE s.post_id = p.tweet_id
                              AND s.brand_id::text = r.brand_key
                              AND s.sentiment::text = r.dominant_sentiment
                        )
                    ) DESC,
                    (
                        p.metrics_refreshed_at IS NOT NULL
                        AND p.metrics_refreshed_at <= r.as_of
                    ) DESC,
                    CASE
                        WHEN p.metrics_refreshed_at IS NOT NULL
                         AND p.metrics_refreshed_at <= r.as_of
                        THEN coalesce(p.like_count, 0)
                           + coalesce(p.retweet_count, 0)
                           + coalesce(p.quote_count, 0)
                           + coalesce(p.reply_count, 0)
                        ELSE 0
                    END DESC,
                    p.created_at DESC,
                    p.tweet_id ASC
                LIMIT r.rank_limit
            )) WITH ORDINALITY AS ranked(tweet_id, stream_rank)
        ),
        recent_stream AS (
            SELECT
                r.position,
                r.candidate_id,
                r.brand_key,
                r.dominant_discourse,
                r.dominant_sentiment,
                ranked.tweet_id,
                r.rank_limit + 1 AS official_rank,
                r.rank_limit + 1 AS catalyst_rank,
                r.rank_limit + 1 AS original_rank,
                r.rank_limit + 1 AS discourse_rank,
                r.rank_limit + 1 AS contrast_rank
            FROM requested r
            CROSS JOIN LATERAL unnest(ARRAY(
                SELECT p.tweet_id::text
                FROM candidate_pool pool
                JOIN posts p ON p.tweet_id = pool.tweet_id
                WHERE pool.position = r.position
                ORDER BY p.created_at DESC, p.tweet_id ASC
                LIMIT r.rank_limit
            )) WITH ORDINALITY AS ranked(tweet_id, stream_rank)
        ),
        stream_rows AS (
            SELECT * FROM seed_rows
            UNION ALL
            SELECT * FROM discourse_stream
            UNION ALL
            SELECT * FROM contrast_stream
            UNION ALL
            SELECT * FROM recent_stream
        ),
        bounded_ids AS (
            SELECT
                position,
                candidate_id,
                brand_key,
                dominant_discourse,
                dominant_sentiment,
                tweet_id,
                min(official_rank) AS official_rank,
                min(catalyst_rank) AS catalyst_rank,
                min(original_rank) AS original_rank,
                min(discourse_rank) AS discourse_rank,
                min(contrast_rank) AS contrast_rank
            FROM stream_rows
            GROUP BY
                position,
                candidate_id,
                brand_key,
                dominant_discourse,
                dominant_sentiment,
                tweet_id
        ),
        base_posts AS (
            SELECT
                bounded.position,
                bounded.candidate_id,
                bounded.brand_key,
                p.tweet_id,
                p.author_id,
                p.quoted_status_id,
                p.created_at,
                p.text,
                p.text_en,
                p.text_zh_cn,
                p.lang,
                p.author_handle,
                coalesce(pes.translation_status, 'pending')
                    AS translation_status,
                coalesce(pes.classification_status, 'pending')
                    AS classification_status,
                p.quoted_text,
                coalesce(p.is_retweet, false) AS is_retweet,
                coalesce(p.is_quote, false) AS is_quote,
                (
                    p.metrics_refreshed_at IS NOT NULL
                    AND p.metrics_refreshed_at <= requested.as_of
                ) AS metrics_observed,
                (
                    coalesce(p.like_count, 0)
                    + coalesce(p.retweet_count, 0)
                    + coalesce(p.quote_count, 0)
                    + coalesce(p.reply_count, 0)
                )::bigint AS stored_interactions,
                official.accounts_id IS NOT NULL AS is_official,
                coalesce(official.first_party_role, 'public_opaque')
                    AS first_party_role,
                bounded.dominant_discourse,
                bounded.dominant_sentiment,
                bounded.official_rank,
                bounded.catalyst_rank,
                bounded.original_rank,
                bounded.discourse_rank,
                bounded.contrast_rank
            FROM bounded_ids bounded
            JOIN requested ON requested.position = bounded.position
            JOIN posts p ON p.tweet_id = bounded.tweet_id
            LEFT JOIN post_enrichment_states pes ON pes.post_id = p.tweet_id
            LEFT JOIN official_accounts official
              ON official.brand_key = bounded.brand_key
             AND official.accounts_id = p.author_id
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
                , array_agg(
                    DISTINCT d.china_nationalism::text
                    ORDER BY d.china_nationalism::text
                ) FILTER (WHERE d.china_nationalism IS NOT NULL)
                    AS china_nationalism_keys
                , array_agg(
                    DISTINCT d.us_nationalism::text
                    ORDER BY d.us_nationalism::text
                ) FILTER (WHERE d.us_nationalism IS NOT NULL)
                    AS us_nationalism_keys
            FROM base_posts base
            JOIN posts_brands_discourse d
              ON d.post_id = base.tweet_id
             AND d.brand_id::text = base.brand_key
            GROUP BY base.candidate_id, base.brand_key, base.tweet_id
        ),
        unsanctioned_arrays AS (
            SELECT
                base.candidate_id,
                base.brand_key,
                base.tweet_id,
                array_agg(DISTINCT flag.flag_key ORDER BY flag.flag_key)
                    AS unsanctioned_flag_keys
            FROM base_posts base
            JOIN posts_unsanctioned_flags u ON u.post_id = base.tweet_id
            CROSS JOIN LATERAL jsonb_array_elements_text(u.flag_set) flag(flag_key)
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
                    AS discourse_keys,
                coalesce(dis.china_nationalism_keys, ARRAY[]::text[])
                    AS china_nationalism_keys,
                coalesce(dis.us_nationalism_keys, ARRAY[]::text[])
                    AS us_nationalism_keys,
                coalesce(uns.unsanctioned_flag_keys, ARRAY[]::text[])
                    AS unsanctioned_flag_keys
            FROM base_posts base
            LEFT JOIN signal_arrays sig
              ON sig.candidate_id = base.candidate_id
             AND sig.brand_key = base.brand_key
             AND sig.tweet_id = base.tweet_id
            LEFT JOIN discourse_arrays dis
              ON dis.candidate_id = base.candidate_id
             AND dis.brand_key = base.brand_key
             AND dis.tweet_id = base.tweet_id
            LEFT JOIN unsanctioned_arrays uns
              ON uns.candidate_id = base.candidate_id
             AND uns.brand_key = base.brand_key
             AND uns.tweet_id = base.tweet_id
        )
        SELECT *
        FROM candidate_posts
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
        rank_limit,
    ]
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        names = [column.name for column in cursor.description]
        return [dict(zip(names, values, strict=True)) for values in cursor.fetchall()]


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
            str(signal.get("family") or "") for signal in candidate.get("signals", [])
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
            source_representatives.append((matched_cluster, str(evidence["excerpt"])))
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
            matched_theme = (
                "th_"
                + _digest(
                    candidate_id,
                    str(evidence["excerpt"]),
                )[:20]
            )
            theme_representatives.append((matched_theme, str(evidence["excerpt"])))
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
        len({str(key) for evidence in pool for key in evidence.get(field, [])})
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
            (evidence for evidence in pool if evidence["_role_eligible"][role]),
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
            {str(key) for evidence in pool for key in evidence.get(field, [])}
        )
        for key in keys:
            choices = [evidence for evidence in pool if key in evidence.get(field, [])]
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
    evidence_id = (
        "e_"
        + _digest(
            candidate_id,
            str(row["tweet_id"]),
            occurrence_source,
            excerpt,
        )[:24]
    )
    author_group_id = (
        "ag_" + _digest(str(row["author_id"]))[:20] if row.get("author_id") else None
    )
    if row.get("quoted_status_id"):
        source_cluster_id = "sc_root_" + _digest(str(row["quoted_status_id"]))[:20]
    else:
        source_cluster_id = "sc_text_" + _digest(excerpt)[:20]
    first_party_role = str(
        row.get("first_party_role") or "public_opaque"
        if bool(row.get("is_official"))
        else "public_opaque"
    )
    source_language = str(row.get("lang") or "und")
    text_en = normalized_excerpt(row.get("text_en"), max_characters=excerpt_characters)
    text_zh_cn = normalized_excerpt(
        row.get("text_zh_cn"), max_characters=excerpt_characters
    )
    translation_status = str(row.get("translation_status") or "pending")
    classification_status = str(row.get("classification_status") or "pending")
    classifier_status = (
        "available" if classification_status == "succeeded" else classification_status
    )

    def classified(values: Sequence[Any]) -> dict[str, Any]:
        return {
            "status": classifier_status,
            "values": sorted(str(value) for value in values if value),
        }

    return {
        "evidence_id": evidence_id,
        "author_group_id": author_group_id,
        "source_cluster_id": source_cluster_id,
        "excerpt": excerpt,
        "created_at": _iso_utc(row["created_at"]),
        "source_language": source_language,
        "translation_status": translation_status,
        "classification_status": classification_status,
        "original_text": post_text,
        "text_en": text_en,
        "text_zh_cn": text_zh_cn,
        "translation_label_en": (
            f"translated from {source_language.upper()}"
            if text_en and source_language.casefold() not in {"en", "und"}
            else None
        ),
        "translation_label_zh_cn": (
            f"译自{source_language.upper()}"
            if text_zh_cn
            and source_language.casefold() not in {"zh", "zh-cn", "zh_cn", "und"}
            else None
        ),
        "first_party_role": first_party_role,
        # Names deliberately mirror the persisted production taxonomy.  Each
        # family declares status even for a successful empty flag set, so the
        # provider never has to infer whether absence means zero or unknown.
        "taxonomy": {
            "post_types": classified(row.get("post_type_keys", [])),
            "discourse_roles": classified(row.get("discourse_keys", [])),
            "china_nationalism": classified(row.get("china_nationalism_keys", [])),
            "us_nationalism": classified(row.get("us_nationalism_keys", [])),
            "unsanctioned_flags": classified(row.get("unsanctioned_flag_keys", [])),
            "language": {
                "status": "available" if row.get("lang") else "unavailable",
                "values": [str(row.get("lang"))] if row.get("lang") else [],
            },
            "sentiment": classified(row.get("sentiment_keys", [])),
            "account_role": {
                "status": "available",
                "values": [first_party_role],
            },
        },
        "handle_snapshot": (
            str(row.get("author_handle") or "")
            if first_party_role in {"official", "staff"}
            else None
        ),
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
            "metrics_observed": bool(row.get("metrics_observed")),
            "occurrence_source": occurrence_source,
        },
        "post_type_keys": sorted(str(key) for key in row.get("post_type_keys", [])),
        "discourse_keys": sorted(str(key) for key in row["discourse_keys"]),
        "sentiment_keys": sorted(str(key) for key in row["sentiment_keys"]),
    }


def _evidence_support(evidence: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    author_groups = {
        str(row["author_group_id"]) for row in evidence if row.get("author_group_id")
    }
    source_clusters = {str(row["source_cluster_id"]) for row in evidence}
    official_count = sum(bool(row["source_flags"]["official"]) for row in evidence)
    return {
        "official_source_count": official_count,
        "distinct_author_group_count": len(author_groups),
        "distinct_source_cluster_count": len(source_clusters),
        "event_claim_may_be_supported": bool(
            official_count or (len(author_groups) >= 2 and len(source_clusters) >= 2)
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
