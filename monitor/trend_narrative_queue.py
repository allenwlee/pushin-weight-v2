"""Broker-local coalescing for queued headline refresh envelopes.

The database remains the publication authority.  This small Redis watermark
only prevents an outage backlog from making older envelopes reserve slots
before the newest useful envelope is handled.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)

HEADLINE_WATERMARK_KEY = "pushinweight:trend-narratives:latest-envelope:v1"


def update_latest_envelope(envelope: dict[str, Any], *, ttl_seconds: int) -> None:
    """Advance the broker watermark monotonically; broker errors are isolated."""
    try:
        import redis

        client = redis.Redis.from_url(
            settings.CELERY_BROKER_URL,
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        with client.pipeline() as pipe:
            while True:
                try:
                    pipe.watch(HEADLINE_WATERMARK_KEY)
                    current = _decode(pipe.get(HEADLINE_WATERMARK_KEY))
                    if current is not None and _ordering_key(current) >= _ordering_key(envelope):
                        pipe.unwatch()
                        return
                    pipe.multi()
                    pipe.set(
                        HEADLINE_WATERMARK_KEY,
                        json.dumps(envelope, separators=(",", ":")),
                        ex=max(ttl_seconds * 2, 60),
                    )
                    pipe.execute()
                    return
                except redis.WatchError:
                    continue
    except Exception:
        logger.warning("headline envelope watermark unavailable", exc_info=True)


def coalesce_envelope(envelope: dict[str, Any]) -> dict[str, Any] | None:
    """Return the newest queued envelope, or ``None`` for an older message."""
    try:
        import redis

        client = redis.Redis.from_url(
            settings.CELERY_BROKER_URL,
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        latest = _decode(client.get(HEADLINE_WATERMARK_KEY))
    except Exception:  # noqa: BLE001 - fail open to the durable task ledger
        return envelope
    if latest is None:
        return envelope
    if _ordering_key(latest) > _ordering_key(envelope):
        return None
    return latest


def _decode(value: str | None) -> dict[str, Any] | None:
    if not value:
        return None
    try:
        decoded = json.loads(value)
    except (TypeError, ValueError):
        return None
    return decoded if isinstance(decoded, dict) else None


def _ordering_key(envelope: dict[str, Any]) -> tuple[datetime, str]:
    raw = str(envelope.get("completed_at") or "")
    try:
        timestamp = datetime.fromisoformat(raw).astimezone(UTC)
    except (TypeError, ValueError):
        timestamp = datetime.min.replace(tzinfo=UTC)
    return timestamp, str(envelope.get("source_cycle_id") or "")
