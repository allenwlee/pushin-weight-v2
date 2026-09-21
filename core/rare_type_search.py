"""Atomic persistence helpers for the already-paid rare-type search lane.

This module owns database state transitions only.  It deliberately constructs
no provider client and performs no network I/O.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.db.models import Case, F, Value, When

from core.models import (
    RareTypeDecision,
    RareTypeSearchDailyBudget,
    RareTypeSearchHit,
    RareTypeSearchRun,
    SearchQuery,
)

SEARCH_RESERVATION_CREDITS = 300
SEARCH_DAILY_CREDIT_LIMIT = 6_000
SEARCH_RESULT_CREDITS = 15
FIRST_WINDOW = timedelta(minutes=15)
MAX_CATCHUP_WINDOW = timedelta(minutes=30)
PAYLOAD_RETENTION = timedelta(days=30)
DECISION_RETRY_DELAY = timedelta(minutes=15)
MAX_DECISION_ATTEMPTS = 2
MAX_TEXT_LENGTH = 50_000
MAX_BIO_LENGTH = 5_000
MAX_PAYLOAD_BYTES = 128_000


@dataclass(frozen=True)
class SearchRunReservation:
    run: RareTypeSearchRun | None
    created: bool
    reason: str


@dataclass(frozen=True)
class DecisionClaim:
    decision: RareTypeDecision
    claimed: bool
    reused: bool
    reason: str


class HitSerializationError(ValueError):
    """A paid provider response could not be reduced to the public allowlist."""


def _utc_date(value: datetime):
    if value.tzinfo is None:
        raise ValueError("rare-type ledger timestamps must be timezone-aware")
    return value.astimezone(UTC).date()


def _slot_floor(value: datetime) -> datetime:
    _utc_date(value)
    utc_value = value.astimezone(UTC)
    return utc_value.replace(
        minute=(utc_value.minute // 15) * 15, second=0, microsecond=0
    )


def _ensure_daily_budget(*, lane: str, usage_date) -> RareTypeSearchDailyBudget:
    # The conflict-safe insert establishes a physical row before it is locked.
    RareTypeSearchDailyBudget.objects.bulk_create(
        [RareTypeSearchDailyBudget(lane=lane, usage_date=usage_date)],
        ignore_conflicts=True,
    )
    return RareTypeSearchDailyBudget.objects.select_for_update().get(
        lane=lane, usage_date=usage_date
    )


def _attempt_window(*, lane: str, window_end: datetime):
    previous = (
        RareTypeSearchRun.objects.filter(lane=lane)
        .order_by("-attempted_end", "-id")
        .values_list("attempted_end", flat=True)
        .first()
    )
    catchup_floor = window_end - MAX_CATCHUP_WINDOW
    if previous is None:
        return window_end - FIRST_WINDOW, None
    if previous < catchup_floor:
        return catchup_floor, (previous, catchup_floor, "catchup_capped_30m")
    if previous >= window_end:
        # A future/duplicate cursor is not allowed to produce an invalid window.
        return window_end - FIRST_WINDOW, None
    return previous, None


def reserve_search_run(
    *,
    lane: str,
    slot_start: datetime,
    source_query: SearchQuery,
    query_string: str,
    query_hash: str,
    query_version: str,
    environment: str,
    release_sha: str,
    now: datetime,
    reserved_credits: int = SEARCH_RESERVATION_CREDITS,
    daily_credit_limit: int = SEARCH_DAILY_CREDIT_LIMIT,
) -> SearchRunReservation:
    """Reserve one search slot and its daily spend in a single transaction."""

    if not lane or not query_string or not query_version:
        raise ValueError("lane, query_string, and query_version are required")
    if len(query_hash) != 64:
        raise ValueError("query_hash must be a 64-character digest")
    if reserved_credits <= 0 or daily_credit_limit <= 0:
        raise ValueError("credit limits must be positive")
    expected_slot = _slot_floor(now)
    if slot_start != expected_slot:
        raise ValueError("slot_start must be the current UTC 15-minute slot")
    window_end = now
    usage_date = _utc_date(slot_start)

    with transaction.atomic():
        budget = _ensure_daily_budget(lane=lane, usage_date=usage_date)
        existing = RareTypeSearchRun.objects.filter(
            lane=lane, slot_start=slot_start
        ).first()
        if existing is not None:
            return SearchRunReservation(existing, False, "slot_already_reserved")

        charged = budget.search_credits_reserved + budget.search_credits_accounted
        if charged + reserved_credits > daily_credit_limit:
            return SearchRunReservation(None, False, "daily_budget_exhausted")

        window_start, gap = _attempt_window(lane=lane, window_end=window_end)
        run = RareTypeSearchRun.objects.create(
            lane=lane,
            slot_start=slot_start,
            daily_budget=budget,
            source_query=source_query,
            query_string=query_string,
            query_hash=query_hash,
            query_version=query_version,
            window_start=window_start,
            window_end=window_end,
            attempted_start=window_start,
            attempted_end=window_end,
            reserved_credits=reserved_credits,
            has_coverage_gap=gap is not None,
            gap_start=gap[0] if gap else None,
            gap_end=gap[1] if gap else None,
            gap_reason=gap[2] if gap else "",
            environment=environment,
            release_sha=release_sha,
            reserved_at=now,
        )
        budget.search_credits_reserved = F("search_credits_reserved") + reserved_credits
        budget.save(update_fields=["search_credits_reserved", "updated_at"])
        return SearchRunReservation(run, True, "reserved")


def mark_search_dispatched(run_id: int, *, now: datetime) -> bool:
    """Record the irreversible boundary immediately before/after transport send."""

    with transaction.atomic():
        run = RareTypeSearchRun.objects.select_for_update().get(pk=run_id)
        if run.status != RareTypeSearchRun.Status.RESERVED:
            return False
        run.status = RareTypeSearchRun.Status.DISPATCHED
        run.request_count = 1
        run.dispatched_at = now
        run.error_code = ""
        run.error_detail = ""
        run.save(
            update_fields=[
                "status",
                "request_count",
                "dispatched_at",
                "error_code",
                "error_detail",
                "updated_at",
            ]
        )
        return True


def mark_search_failed(
    run_id: int,
    *,
    error_code: str,
    now: datetime,
) -> bool:
    """Fail safely: pre-dispatch releases spend; post-dispatch retains it."""

    run_ref = RareTypeSearchRun.objects.only("daily_budget_id").get(pk=run_id)
    with transaction.atomic():
        budget = RareTypeSearchDailyBudget.objects.select_for_update().get(
            pk=run_ref.daily_budget_id
        )
        run = RareTypeSearchRun.objects.select_for_update().get(pk=run_id)
        if run.status == RareTypeSearchRun.Status.RESERVED:
            budget.search_credits_reserved = max(
                0, budget.search_credits_reserved - run.reserved_credits
            )
            budget.save(update_fields=["search_credits_reserved", "updated_at"])
            run.status = RareTypeSearchRun.Status.FAILED
        elif run.status == RareTypeSearchRun.Status.DISPATCHED:
            run.status = RareTypeSearchRun.Status.USAGE_UNKNOWN
        else:
            return False
        run.error_code = error_code[:128]
        run.error_detail = ""
        run.complete_start = None
        run.complete_end = None
        if run.has_coverage_gap:
            run.gap_end = run.attempted_end
            run.gap_reason = f"{run.gap_reason};{error_code}"[:128]
        else:
            run.has_coverage_gap = True
            run.gap_start = run.attempted_start
            run.gap_end = run.attempted_end
            run.gap_reason = error_code[:128]
        run.finished_at = now
        run.save(
            update_fields=[
                "status",
                "error_code",
                "error_detail",
                "complete_start",
                "complete_end",
                "has_coverage_gap",
                "gap_start",
                "gap_end",
                "gap_reason",
                "finished_at",
                "updated_at",
            ]
        )
        return True


def _mark_result_persistence_failed(
    run_id: int, *, error_code: str, now: datetime
) -> None:
    """Expose local failure without discarding already-recorded paid volume."""

    with transaction.atomic():
        run = RareTypeSearchRun.objects.select_for_update().get(pk=run_id)
        if run.status in [
            RareTypeSearchRun.Status.RETURNED,
            RareTypeSearchRun.Status.EMPTY,
        ]:
            run.status = RareTypeSearchRun.Status.FAILED
        elif run.status in [
            RareTypeSearchRun.Status.DISPATCHED,
            RareTypeSearchRun.Status.USAGE_UNKNOWN,
        ]:
            run.status = RareTypeSearchRun.Status.USAGE_UNKNOWN
        else:
            return
        run.error_code = error_code[:128]
        run.error_detail = ""
        run.complete_start = None
        run.complete_end = None
        if run.has_coverage_gap:
            run.gap_end = run.attempted_end
            run.gap_reason = f"{run.gap_reason};{error_code}"[:128]
        else:
            run.has_coverage_gap = True
            run.gap_start = run.attempted_start
            run.gap_end = run.attempted_end
            run.gap_reason = error_code[:128]
        run.finished_at = now
        run.save(
            update_fields=[
                "status",
                "error_code",
                "error_detail",
                "complete_start",
                "complete_end",
                "has_coverage_gap",
                "gap_start",
                "gap_end",
                "gap_reason",
                "finished_at",
                "updated_at",
            ]
        )


def settle_search_return(
    run_id: int,
    *,
    raw_count: int,
    normalized_count: int | None,
    truncated: bool,
    now: datetime,
    confirmed_credits: int | None = None,
) -> bool:
    """Settle a known provider return without holding a lock across transport."""

    if (
        raw_count < 0
        or (normalized_count is not None and normalized_count < 0)
        or (normalized_count is not None and normalized_count > raw_count)
    ):
        raise ValueError("result counts are inconsistent")
    if confirmed_credits is not None and confirmed_credits < 0:
        raise ValueError("confirmed credits cannot be negative")
    estimated = max(SEARCH_RESULT_CREDITS, raw_count * SEARCH_RESULT_CREDITS)
    run_ref = RareTypeSearchRun.objects.only("daily_budget_id").get(pk=run_id)
    with transaction.atomic():
        budget = RareTypeSearchDailyBudget.objects.select_for_update().get(
            pk=run_ref.daily_budget_id
        )
        run = RareTypeSearchRun.objects.select_for_update().get(pk=run_id)
        if run.status != RareTypeSearchRun.Status.DISPATCHED:
            return False
        budget.search_credits_reserved = max(
            0, budget.search_credits_reserved - run.reserved_credits
        )
        budget.search_credits_accounted = budget.search_credits_accounted + estimated
        budget.save(
            update_fields=[
                "search_credits_reserved",
                "search_credits_accounted",
                "updated_at",
            ]
        )
        run.raw_result_count = raw_count
        run.normalized_result_count = normalized_count
        run.estimated_credits = estimated
        run.confirmed_credits = confirmed_credits
        run.truncated = truncated
        run.status = (
            RareTypeSearchRun.Status.EMPTY
            if raw_count == 0
            else RareTypeSearchRun.Status.RETURNED
        )
        run.returned_at = now
        run.finished_at = now
        if not truncated:
            if raw_count == 0:
                run.complete_start = run.attempted_start
                run.complete_end = run.attempted_end
        else:
            if not run.has_coverage_gap:
                run.has_coverage_gap = True
                run.gap_start = run.attempted_start
                run.gap_reason = "provider_truncated"
            else:
                run.gap_reason = f"{run.gap_reason};provider_truncated"[:128]
            run.gap_end = run.attempted_end
        run.save()
        return True


def _record_unknown_raw_return(
    run_id: int,
    *,
    normalized_count: int,
    truncated: bool,
    now: datetime,
) -> bool:
    """Record returned normalized hits while retaining the full reservation."""

    if normalized_count < 0:
        raise ValueError("normalized count cannot be negative")
    with transaction.atomic():
        run = RareTypeSearchRun.objects.select_for_update().get(pk=run_id)
        if run.status != RareTypeSearchRun.Status.DISPATCHED:
            return False
        run.status = RareTypeSearchRun.Status.USAGE_UNKNOWN
        run.normalized_result_count = normalized_count
        run.truncated = truncated
        run.returned_at = now
        run.finished_at = now
        run.error_code = "raw_usage_unknown"
        if truncated and not run.has_coverage_gap:
            run.has_coverage_gap = True
            run.gap_start = run.attempted_start
            run.gap_end = run.attempted_end
            run.gap_reason = "provider_truncated"
        elif truncated:
            run.gap_end = run.attempted_end
            run.gap_reason = f"{run.gap_reason};provider_truncated"[:128]
        run.save()
        return True


def reserve_decision_budget(
    funding_run_id: int,
    *,
    amount_usd: Decimal,
    cycle_limit_usd: Decimal = Decimal("0.020000000"),
    daily_limit_usd: Decimal = Decimal("0.500000000"),
) -> bool:
    """Reserve Jev spend against the current processing run/day.

    ``funding_run_id`` is the cycle doing the work now, including replay.  It
    is not necessarily the source search run that originally captured a hit.
    """

    if amount_usd <= 0 or cycle_limit_usd <= 0 or daily_limit_usd <= 0:
        raise ValueError("decision budget amounts must be positive")
    run_ref = RareTypeSearchRun.objects.only("daily_budget_id").get(pk=funding_run_id)
    with transaction.atomic():
        budget = RareTypeSearchDailyBudget.objects.select_for_update().get(
            pk=run_ref.daily_budget_id
        )
        run = RareTypeSearchRun.objects.select_for_update().get(pk=funding_run_id)
        cycle_charged = run.decision_usd_reserved + run.decision_usd_accounted
        daily_charged = budget.decision_usd_reserved + budget.decision_usd_accounted
        if cycle_charged + amount_usd > cycle_limit_usd:
            return False
        if daily_charged + amount_usd > daily_limit_usd:
            return False
        run.decision_usd_reserved += amount_usd
        budget.decision_usd_reserved += amount_usd
        run.save(update_fields=["decision_usd_reserved", "updated_at"])
        budget.save(update_fields=["decision_usd_reserved", "updated_at"])
        return True


def settle_decision_budget(
    funding_run_id: int,
    *,
    reserved_usd: Decimal,
    accounted_usd: Decimal,
    confirmed_usd: Decimal | None = None,
) -> bool:
    """Replace a Jev reservation with observed accounting evidence.

    ``funding_run_id`` is the current processing/replay funding context.  An
    ambiguous request intentionally does not call this helper, retaining the
    reservation against both cycle and UTC-day limits.
    """

    if reserved_usd <= 0 or accounted_usd < 0:
        raise ValueError("invalid decision settlement")
    if confirmed_usd is not None and confirmed_usd < 0:
        raise ValueError("confirmed decision cost cannot be negative")
    run_ref = RareTypeSearchRun.objects.only("daily_budget_id").get(pk=funding_run_id)
    with transaction.atomic():
        budget = RareTypeSearchDailyBudget.objects.select_for_update().get(
            pk=run_ref.daily_budget_id
        )
        run = RareTypeSearchRun.objects.select_for_update().get(pk=funding_run_id)
        if (
            run.decision_usd_reserved < reserved_usd
            or budget.decision_usd_reserved < reserved_usd
        ):
            return False
        run.decision_usd_reserved -= reserved_usd
        budget.decision_usd_reserved -= reserved_usd
        run.decision_usd_accounted += accounted_usd
        budget.decision_usd_accounted += accounted_usd
        if confirmed_usd is not None:
            run.decision_usd_confirmed += confirmed_usd
            budget.decision_usd_confirmed += confirmed_usd
        run.save(
            update_fields=[
                "decision_usd_reserved",
                "decision_usd_accounted",
                "decision_usd_confirmed",
                "updated_at",
            ]
        )
        budget.save(
            update_fields=[
                "decision_usd_reserved",
                "decision_usd_accounted",
                "decision_usd_confirmed",
                "updated_at",
            ]
        )
        return True


_AUTHOR_FIELDS = {
    "id": 128,
    "userName": 64,
    "username": 64,
    "name": 256,
    "description": MAX_BIO_LENGTH,
}
_TWEET_FIELDS = {
    "id": 256,
    "text": MAX_TEXT_LENGTH,
    "lang": 32,
    "createdAt": 128,
    "created_at": 128,
    "url": 2_048,
    "twitterUrl": 2_048,
    "conversationId": 256,
    "likeCount": None,
    "retweetCount": None,
    "replyCount": None,
    "quoteCount": None,
}
_NORMALIZED_FIELDS = {
    "id": 256,
    "text": MAX_TEXT_LENGTH,
    "lang": 32,
    "created_at": 128,
    "created_at_raw": 128,
    "like_count": None,
    "retweet_count": None,
    "reply_count": None,
    "quote_count": None,
    "bookmark_count": None,
    "is_reply": None,
    "is_retweet": None,
    "is_quote": None,
    "in_reply_to_user_id": 256,
    "quoted_status_id": 256,
    "quoted_text": MAX_TEXT_LENGTH,
    "quoted_author_handle": 64,
    "author_handle": 64,
    "author_id": 128,
    "author_name": 256,
    "author_description": MAX_BIO_LENGTH,
    "author_profile_bio_text": MAX_BIO_LENGTH,
    "tweet_url": 2_048,
    "tweet_twitter_url": 2_048,
}
_URL_PATTERN = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)


def _bounded_scalar(value: Any, limit: int | None):
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if not isinstance(value, str):
        raise HitSerializationError("allowlisted provider value has unsupported type")
    return value[:limit] if limit is not None else value


def _allowlisted_tweet(
    raw: Mapping[str, Any], *, include_quote: bool
) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise HitSerializationError("provider hit must be an object")
    public: dict[str, Any] = {}
    for key, limit in _TWEET_FIELDS.items():
        if key in raw:
            public[key] = _bounded_scalar(raw[key], limit)
    if "author" in raw:
        author = raw["author"]
        if not isinstance(author, Mapping):
            raise HitSerializationError("provider author must be an object")
        public["author"] = {
            key: _bounded_scalar(author[key], limit)
            for key, limit in _AUTHOR_FIELDS.items()
            if key in author
        }
    if include_quote:
        for key in ("quoted_tweet", "quotedTweet"):
            if key in raw and raw[key] is not None:
                public[key] = _allowlisted_tweet(raw[key], include_quote=False)
    return public


def _collect_public_urls(value: Any, found: set[str]) -> None:
    if isinstance(value, str):
        found.update(
            match.rstrip(".,);]")[:2048] for match in _URL_PATTERN.findall(value)
        )
    elif isinstance(value, Mapping):
        for child in value.values():
            _collect_public_urls(child, found)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _collect_public_urls(child, found)


def _allowlisted_normalized_hit(raw: Mapping[str, Any]) -> dict[str, Any]:
    public = {
        key: _bounded_scalar(raw[key], limit)
        for key, limit in _NORMALIZED_FIELDS.items()
        if key in raw
    }
    present = raw.get("_author_present_fields")
    if present is not None:
        if not isinstance(present, (list, tuple)) or any(
            not isinstance(value, str) for value in present
        ):
            raise HitSerializationError("author presence metadata is malformed")
        allowed_presence = {
            "author_handle",
            "author_name",
            "author_description",
            "author_profile_bio_text",
        }
        public["_author_present_fields"] = sorted(
            {value for value in present if value in allowed_presence}
        )
    source_urls: set[str] = set()
    for key in (
        "text",
        "quoted_text",
        "tweet_url",
        "tweet_twitter_url",
        "extended_entities",
        "card",
        "article",
    ):
        _collect_public_urls(raw.get(key), source_urls)
    if source_urls:
        public["source_urls"] = sorted(source_urls)[:100]
    return public


def serialize_public_hit(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Return only bounded public provider fields; unknown keys never cross."""

    try:
        is_normalized = any(
            key in raw
            for key in (
                "author_id",
                "author_handle",
                "quoted_status_id",
                "tweet_url",
                "_author_present_fields",
            )
        )
        public = (
            _allowlisted_normalized_hit(raw)
            if is_normalized
            else _allowlisted_tweet(raw, include_quote=True)
        )
        encoded = json.dumps(
            public, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    except HitSerializationError:
        raise
    except Exception as exc:
        raise HitSerializationError("provider hit could not be serialized") from exc
    if len(encoded) > MAX_PAYLOAD_BYTES:
        raise HitSerializationError("allowlisted provider hit exceeds payload bound")
    return public


def _decision_content_hash(public_payload: Mapping[str, Any]) -> str:
    """Hash exactly the evidence Jev sees, excluding mutable counters."""

    if "author" in public_payload:
        author = public_payload.get("author") or {}
        quoted = public_payload.get("quoted_tweet") or public_payload.get("quotedTweet")
        quoted_author = (quoted or {}).get("author") or {}
        evidence = {
            "text": public_payload.get("text"),
            "lang": public_payload.get("lang"),
            "created_at": public_payload.get("createdAt")
            or public_payload.get("created_at"),
            "author": {
                key: author.get(key)
                for key in ("id", "userName", "username", "name", "description")
            },
            "quoted": (
                {
                    "id": quoted.get("id"),
                    "text": quoted.get("text"),
                    "lang": quoted.get("lang"),
                    "created_at": quoted.get("createdAt") or quoted.get("created_at"),
                    "author": {
                        key: quoted_author.get(key)
                        for key in (
                            "id",
                            "userName",
                            "username",
                            "name",
                            "description",
                        )
                    },
                }
                if quoted
                else None
            ),
        }
    else:
        evidence = {
            key: public_payload.get(key)
            for key in (
                "text",
                "lang",
                "created_at",
                "author_id",
                "author_handle",
                "author_name",
                "author_description",
                "author_profile_bio_text",
                "quoted_status_id",
                "quoted_text",
                "quoted_author_handle",
            )
        }
    encoded = json.dumps(
        evidence, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _provider_post_id(raw: Mapping[str, Any]) -> str:
    value = raw.get("id") or raw.get("tweet_id")
    if not isinstance(value, (str, int)) or not str(value).strip():
        raise HitSerializationError("provider hit is missing its public id")
    return str(value)[:256]


def persist_hit_batch(
    run_id: int,
    raw_hits: Sequence[Mapping[str, Any]],
    *,
    now: datetime,
    raw_count: int | None = None,
    normalized_count: int | None = None,
    truncated: bool = False,
) -> list[RareTypeSearchHit]:
    """Persist an entire paid page atomically before any interpretation."""

    observed_normalized_count = (
        len(raw_hits) if normalized_count is None else normalized_count
    )
    run_status = RareTypeSearchRun.objects.only("status").get(pk=run_id).status
    if run_status == RareTypeSearchRun.Status.DISPATCHED:
        if raw_count is None:
            _record_unknown_raw_return(
                run_id,
                normalized_count=observed_normalized_count,
                truncated=truncated,
                now=now,
            )
        else:
            settle_search_return(
                run_id,
                raw_count=raw_count,
                normalized_count=observed_normalized_count,
                truncated=truncated,
                now=now,
            )
    try:
        prepared = []
        for raw in raw_hits:
            provider_post_id = _provider_post_id(raw)
            public_payload = serialize_public_hit(raw)
            original_text = public_payload.get("text") or ""
            content_hash = _decision_content_hash(public_payload)
            prepared.append(
                (provider_post_id, original_text, content_hash, public_payload)
            )
    except Exception as exc:
        _mark_result_persistence_failed(
            run_id, error_code="hit_serialization_failed", now=now
        )
        if isinstance(exc, HitSerializationError):
            raise
        raise HitSerializationError("provider hit could not be serialized") from exc

    try:
        with transaction.atomic():
            run = RareTypeSearchRun.objects.select_for_update().get(pk=run_id)
            if run.status not in [
                RareTypeSearchRun.Status.RETURNED,
                RareTypeSearchRun.Status.EMPTY,
                RareTypeSearchRun.Status.USAGE_UNKNOWN,
            ]:
                raise ValueError("hit batches require a known provider return")
            rows = [
                RareTypeSearchHit(
                    run=run,
                    provider_post_id=provider_post_id,
                    content_hash=content_hash,
                    original_text=original_text,
                    public_payload=public_payload,
                    payload_expires_at=now + PAYLOAD_RETENTION,
                    source_query_hash=run.query_hash,
                    source_query_version=run.query_version,
                    source_window_start=run.attempted_start,
                    source_window_end=run.attempted_end,
                    fetched_at=now,
                )
                for provider_post_id, original_text, content_hash, public_payload in prepared
            ]
            created = RareTypeSearchHit.objects.bulk_create(rows)
            if not run.truncated:
                run.complete_start = run.attempted_start
                run.complete_end = run.attempted_end
                run.save(update_fields=["complete_start", "complete_end", "updated_at"])
            return created
    except Exception:
        _mark_result_persistence_failed(
            run_id, error_code="hit_persistence_failed", now=now
        )
        raise


def expire_hit_payloads(*, now: datetime) -> int:
    """Erase 30-day payload material while retaining source identity/audit."""

    return RareTypeSearchHit.objects.filter(
        payload_expires_at__lte=now, payload_expired_at__isnull=True
    ).update(
        public_payload={},
        original_text="",
        payload_expired_at=now,
        gate_state=Case(
            When(
                gate_state__in=[
                    RareTypeSearchHit.GateState.DECISION_PENDING,
                    RareTypeSearchHit.GateState.PROVIDER_FAILED,
                    RareTypeSearchHit.GateState.REVIEW_NEEDED,
                ],
                then=Value(RareTypeSearchHit.GateState.EXPIRED_UNPROCESSED),
            ),
            default=F("gate_state"),
        ),
        updated_at=now,
    )


def claim_decision(
    *,
    provider_post_id: str,
    content_hash: str,
    model: str,
    question_version: str,
    threshold_version: str,
    owner: str,
    now: datetime,
    lease_seconds: int = 60,
) -> DecisionClaim:
    """Create/reuse one decision identity and give at most one worker its lease."""

    if not all(
        [
            provider_post_id,
            content_hash,
            model,
            question_version,
            threshold_version,
            owner,
        ]
    ):
        raise ValueError("decision identity and owner fields are required")
    if len(content_hash) != 64 or lease_seconds <= 0:
        raise ValueError("invalid decision hash or lease")
    identity = {
        "provider_post_id": provider_post_id,
        "content_hash": content_hash,
        "model": model,
        "question_version": question_version,
        "threshold_version": threshold_version,
    }
    with transaction.atomic():
        RareTypeDecision.objects.bulk_create(
            [RareTypeDecision(**identity)], ignore_conflicts=True
        )
        decision = RareTypeDecision.objects.select_for_update().get(**identity)
        if decision.status == RareTypeDecision.Status.COMPLETED:
            return DecisionClaim(decision, False, True, "completed_reuse")
        if decision.status == RareTypeDecision.Status.REVIEW_NEEDED:
            return DecisionClaim(decision, False, False, "review_needed")
        if (
            decision.status == RareTypeDecision.Status.CLAIMED
            and decision.claim_expires_at
            and decision.claim_expires_at > now
        ):
            return DecisionClaim(decision, False, False, "already_claimed")
        if (
            decision.status == RareTypeDecision.Status.CLAIMED
            and decision.claimed_at
            and decision.claimed_at + DECISION_RETRY_DELAY > now
        ):
            return DecisionClaim(decision, False, False, "retry_not_due")
        if decision.next_attempt_at and decision.next_attempt_at > now:
            return DecisionClaim(decision, False, False, "retry_not_due")
        if decision.attempts >= MAX_DECISION_ATTEMPTS:
            decision.status = RareTypeDecision.Status.REVIEW_NEEDED
            decision.claim_owner = ""
            decision.claimed_at = None
            decision.claim_expires_at = None
            decision.save()
            return DecisionClaim(decision, False, False, "attempts_exhausted")

        decision.status = RareTypeDecision.Status.CLAIMED
        decision.attempts += 1
        decision.claim_owner = owner[:128]
        decision.claim_fence += 1
        decision.claimed_at = now
        decision.claim_expires_at = now + timedelta(seconds=lease_seconds)
        decision.next_attempt_at = None
        decision.save()
        return DecisionClaim(decision, True, False, "claimed")


def _valid_probabilities(values: Mapping[str, float]) -> bool:
    return bool(values) and all(
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and 0 <= float(value) <= 1
        for value in values.values()
    )


def complete_decision(
    decision_id: int,
    *,
    owner: str,
    fence: int,
    response_id: str,
    probabilities: Mapping[str, float],
    derived_types: Sequence[str],
    input_tokens: int,
    output_tokens: int,
    cost_usd: Decimal,
    latency_ms: int,
    now: datetime,
) -> bool:
    """Publish a valid claimed decision; stale owners cannot write results."""

    if not response_id or not _valid_probabilities(probabilities):
        return False
    if any(not isinstance(value, str) or not value for value in derived_types):
        return False
    if min(input_tokens, output_tokens, latency_ms) < 0 or cost_usd < 0:
        return False
    with transaction.atomic():
        decision = RareTypeDecision.objects.select_for_update().get(pk=decision_id)
        if not (
            decision.status == RareTypeDecision.Status.CLAIMED
            and decision.claim_owner == owner
            and decision.claim_fence == fence
        ):
            return False
        decision.status = RareTypeDecision.Status.COMPLETED
        decision.response_id = response_id[:255]
        decision.probabilities = dict(probabilities)
        decision.derived_types = list(dict.fromkeys(derived_types))
        decision.input_tokens = input_tokens
        decision.output_tokens = output_tokens
        decision.cost_usd = cost_usd
        decision.latency_ms = latency_ms
        decision.completed_at = now
        decision.last_error_code = ""
        decision.claim_owner = ""
        decision.claimed_at = None
        decision.claim_expires_at = None
        decision.save()
        return True


def fail_decision(
    decision_id: int,
    *,
    owner: str,
    fence: int,
    error_code: str,
    uncertain: bool,
    now: datetime,
) -> bool:
    """Make errors retryable once, then visibly review-needed; never junk."""

    with transaction.atomic():
        decision = RareTypeDecision.objects.select_for_update().get(pk=decision_id)
        if not (
            decision.status == RareTypeDecision.Status.CLAIMED
            and decision.claim_owner == owner
            and decision.claim_fence == fence
        ):
            return False
        decision.last_error_code = error_code[:128]
        decision.claim_owner = ""
        decision.claimed_at = None
        decision.claim_expires_at = None
        if decision.attempts >= MAX_DECISION_ATTEMPTS:
            decision.status = RareTypeDecision.Status.REVIEW_NEEDED
            decision.next_attempt_at = None
        else:
            decision.status = RareTypeDecision.Status.PENDING
            decision.next_attempt_at = now + DECISION_RETRY_DELAY
        # `uncertain` is explicit at the call site and intentionally shares the
        # same non-junk lifecycle as transport/schema errors.
        if uncertain and decision.status == RareTypeDecision.Status.FAILED:
            decision.status = RareTypeDecision.Status.PENDING
        decision.save()
        return True
