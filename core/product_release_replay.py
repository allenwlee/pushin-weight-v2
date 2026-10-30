"""Replay supplied collection evidence without contacting a database or provider.

Adapters must supply the original physical request clock when reusing a cached
page. Post publication time and page processing time do not select the cohort.
The manifest describes supplied evidence, never asserts complete X coverage.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from typing import Literal
from zoneinfo import ZoneInfo

from core.product_release_intake import (
    RULE_VERSION,
    ReleaseCandidate,
    SourceRecord,
    detect,
)


def _utc(value: datetime) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError("An explicit timezone/UTC offset is required")
    return value.astimezone(UTC)


def _parse_time(value: str, zone: ZoneInfo | None) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is not None:
        if zone and parsed.astimezone(zone).replace(tzinfo=None) != parsed.replace(
            tzinfo=None
        ):
            raise ValueError("UTC offset conflicts with the named timezone")
        return _utc(parsed)
    if zone is None:
        raise ValueError("An explicit timezone/UTC offset is required")
    possibilities = set()
    for fold in (0, 1):
        utc = parsed.replace(tzinfo=zone, fold=fold).astimezone(UTC)
        if utc.astimezone(zone).replace(tzinfo=None) == parsed:
            possibilities.add(utc)
    if len(possibilities) != 1:
        raise ValueError(
            "Ambiguous or nonexistent local time; provide a valid explicit UTC offset"
        )
    return possibilities.pop()


@dataclass(frozen=True)
class ReplayWindow:
    start: datetime
    end: datetime

    def __post_init__(self):
        object.__setattr__(self, "start", _utc(self.start))
        object.__setattr__(self, "end", _utc(self.end))
        if self.start >= self.end:
            raise ValueError("Window end must be after start")

    @classmethod
    def parse(
        cls, start: str, end: str, *, timezone: str | None = None
    ) -> ReplayWindow:
        zone = ZoneInfo(timezone) if timezone else None
        return cls(_parse_time(start, zone), _parse_time(end, zone))

    def contains(self, value: datetime) -> bool:
        return self.start <= _utc(value) < self.end


def _validate_identity(namespace: str, source_id: str, locator: str) -> None:
    if any(
        not isinstance(value, str) or not value.strip()
        for value in (namespace, source_id, locator)
    ):
        raise ValueError("Source identity and evidence reference must be nonempty text")


@dataclass(frozen=True)
class CollectionAppearance:
    namespace: str
    source_id: str
    physical_request_id: str
    collected_at: datetime
    processed_at: datetime | None = None

    def __post_init__(self):
        _validate_identity(self.namespace, self.source_id, self.physical_request_id)
        object.__setattr__(self, "collected_at", _utc(self.collected_at))
        if self.processed_at is not None:
            object.__setattr__(self, "processed_at", _utc(self.processed_at))

    @property
    def identity(self) -> tuple[str, str]:
        return self.namespace, self.source_id


@dataclass(frozen=True)
class FirstStorage:
    namespace: str
    source_id: str
    stored_at: datetime
    locator: str

    def __post_init__(self):
        _validate_identity(self.namespace, self.source_id, self.locator)
        object.__setattr__(self, "stored_at", _utc(self.stored_at))

    @property
    def identity(self) -> tuple[str, str]:
        return self.namespace, self.source_id


@dataclass(frozen=True)
class ReplayResult:
    window: ReplayWindow
    source_ids: tuple[tuple[str, str], ...]
    source_records: tuple[SourceRecord, ...]
    appearances: tuple[CollectionAppearance, ...]
    first_storage: tuple[FirstStorage, ...]
    missing_source_ids: tuple[tuple[str, str], ...]
    candidates: tuple[ReleaseCandidate, ...]
    coverage: Literal["physical_receipts", "first_storage_only", "mixed", "no_evidence"]
    limitations: tuple[str, ...]
    input_digest: str
    rule_version: str = RULE_VERSION


def _json_default(value):
    if isinstance(value, datetime):
        return _utc(value).isoformat()
    raise TypeError(f"Unsupported manifest value: {type(value).__name__}")


def replay(
    sources: Iterable[SourceRecord],
    appearances: Iterable[CollectionAppearance],
    window: ReplayWindow,
    *,
    first_storage: Iterable[FirstStorage] = (),
) -> ReplayResult:
    """Select exact source inputs; detect using currently supplied saved enrichment.

    First-storage fallback is opt-in by supplying records, with its limitation
    recorded. Nothing here creates Products or deduplicates cross-post events.
    """
    by_source = {}
    for source in sources:
        previous = by_source.setdefault(source.identity, source)
        if previous != source:
            raise ValueError(f"Conflicting source input: {source.identity}")

    request_clocks = {}
    selected_appearances = {}
    for appearance in appearances:
        previous = request_clocks.setdefault(
            appearance.physical_request_id, appearance.collected_at
        )
        if previous != appearance.collected_at:
            raise ValueError(
                f"Conflicting physical request clock: {appearance.physical_request_id}"
            )
        if window.contains(appearance.collected_at):
            # Processing a saved page again is not another physical observation.
            key = (*appearance.identity, appearance.physical_request_id)
            selected_appearances[key] = replace(appearance, processed_at=None)
    ordered_appearances = tuple(
        selected_appearances[key] for key in sorted(selected_appearances)
    )
    physical_sources = {row.identity for row in ordered_appearances}

    storage_by_source = {}
    for stored in first_storage:
        previous = storage_by_source.setdefault(stored.identity, stored)
        if previous != stored:
            raise ValueError(f"Conflicting first-storage evidence: {stored.identity}")
    fallback = tuple(
        storage_by_source[key]
        for key in sorted(storage_by_source)
        if key not in physical_sources
        and window.contains(storage_by_source[key].stored_at)
    )
    selected_ids = tuple(sorted(physical_sources | {row.identity for row in fallback}))
    missing = tuple(key for key in selected_ids if key not in by_source)
    selected = [by_source[key] for key in selected_ids if key in by_source]
    candidates = tuple(
        candidate for source in selected if (candidate := detect(source)) is not None
    )

    limitations = ["supplied_evidence_only_completeness_unverified"]
    if fallback:
        limitations.append("first_storage_does_not_cover_refetches")
    if missing:
        limitations.append("source_content_missing")
    if ordered_appearances and fallback:
        coverage = "mixed"
    elif ordered_appearances:
        coverage = "physical_receipts"
    elif fallback:
        coverage = "first_storage_only"
    else:
        coverage = "no_evidence"
    manifest = {
        "version": 1,
        "rule_version": RULE_VERSION,
        "window": asdict(window),
        "source_ids": selected_ids,
        "sources": [asdict(source) for source in selected],
        "appearances": [asdict(row) for row in ordered_appearances],
        "first_storage": [asdict(row) for row in fallback],
        "missing_source_ids": missing,
    }
    digest = hashlib.sha256(
        json.dumps(
            manifest,
            default=_json_default,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    return ReplayResult(
        window,
        selected_ids,
        tuple(selected),
        ordered_appearances,
        fallback,
        missing,
        candidates,
        coverage,
        tuple(limitations),
        digest,
    )
