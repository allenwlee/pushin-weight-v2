"""Broker-watermark contracts for headline backlog coalescing."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace

from monitor.trend_narrative_queue import (
    HEADLINE_WATERMARK_KEY,
    coalesce_envelope,
    update_latest_envelope,
)


def _envelope(source: str, minute: int) -> dict[str, object]:
    return {
        "schema_version": 1,
        "source_cycle_id": source,
        "completed_at": datetime(2026, 8, 12, 12, minute, tzinfo=UTC)
        .isoformat()
        .replace("+00:00", "Z"),
        "outcome": "completed",
        "dry_run": False,
    }


class _Pipeline:
    def __init__(self, store: dict[str, str]):
        self.store = store
        self.pending: tuple[str, str, int] | None = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def watch(self, _key):
        return None

    def get(self, key):
        return self.store.get(key)

    def unwatch(self):
        return None

    def multi(self):
        return None

    def set(self, key, value, ex):
        self.pending = (key, value, ex)

    def execute(self):
        assert self.pending is not None
        key, value, _expiry = self.pending
        self.store[key] = value
        self.pending = None


class _Redis:
    def __init__(self, store: dict[str, str]):
        self.store = store

    def pipeline(self):
        return _Pipeline(self.store)

    def get(self, key):
        return self.store.get(key)


def test_watermark_is_monotonic_and_older_messages_are_superseded(monkeypatch):
    store: dict[str, str] = {}
    fake_redis = SimpleNamespace(Redis=SimpleNamespace(from_url=lambda *a, **k: _Redis(store)))
    monkeypatch.setitem(__import__("sys").modules, "redis", fake_redis)
    monkeypatch.setattr("monitor.trend_narrative_queue.settings", SimpleNamespace(CELERY_BROKER_URL="redis://fixture"))

    newer = _envelope("cycle-new", 15)
    older = _envelope("cycle-old", 0)
    update_latest_envelope(newer, ttl_seconds=60)
    update_latest_envelope(older, ttl_seconds=60)

    assert json.loads(store[HEADLINE_WATERMARK_KEY]) == newer
    assert coalesce_envelope(older) is None
    assert coalesce_envelope(newer) == newer
