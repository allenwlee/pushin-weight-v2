# {{AGENT_ATTRIBUTION}}
"""Single review-queue module (R25). Backed by data/_review_queue.json."""

from __future__ import annotations

import fcntl
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

log = logging.getLogger(__name__)

Status = Literal["open", "resolved", "dismissed"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ReviewQueue:
    """JSON-backed review queue. Single source of truth (R25).

    File lock via fcntl.flock prevents concurrent writes from the pipeline
    and a manual CLI invocation.
    """

    def __init__(self, path: Path):
        self.path = path

    def _read_unlocked(self) -> list[dict]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        return data if isinstance(data, list) else []

    def _write_unlocked(self, items: list[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        tmp.replace(self.path)

    def _with_lock(self, fn):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        with open(lock_path, "w") as f:
            try:
                fcntl.flock(f, fcntl.LOCK_EX)
                return fn()
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    def list(self, status: Status | None = None) -> list[dict]:
        def op() -> list[dict]:
            items = self._read_unlocked()
            if status is None:
                return items
            return [i for i in items if i.get("status") == status]

        return self._with_lock(op)

    def add(
        self,
        tweet_id: str,
        reason: str,
        note: str = "",
        brand_id: str | None = None,
    ) -> dict:
        def op() -> dict:
            items = self._read_unlocked()
            # Idempotent: if tweet_id already present, just update reason.
            for it in items:
                if it.get("tweet_id") == tweet_id:
                    it["reason"] = reason
                    it["note"] = note
                    it["updated_at"] = _now_iso()
                    if brand_id:
                        it["brand_id"] = brand_id
                    self._write_unlocked(items)
                    return it
            entry = {
                "tweet_id": tweet_id,
                "reason": reason,
                "note": note,
                "status": "open",
                "brand_id": brand_id,
                "created_at": _now_iso(),
                "updated_at": _now_iso(),
            }
            items.append(entry)
            self._write_unlocked(items)
            return entry

        return self._with_lock(op)

    def resolve(self, tweet_id: str, note: str = "") -> dict | None:
        return self._set_status(tweet_id, "resolved", note)

    def dismiss(self, tweet_id: str, note: str = "") -> dict | None:
        return self._set_status(tweet_id, "dismissed", note)

    def _set_status(self, tweet_id: str, status: Status, note: str) -> dict | None:
        def op() -> dict | None:
            items = self._read_unlocked()
            for it in items:
                if it.get("tweet_id") == tweet_id:
                    it["status"] = status
                    if note:
                        it["note"] = note
                    it["updated_at"] = _now_iso()
                    self._write_unlocked(items)
                    return it
            return None

        return self._with_lock(op)

    def append_rule_match(
        self,
        tweet_id: str,
        reason: str,
        brand_id: str,
        rule: str = "",
    ) -> None:
        """Pipeline-side: append a rule-derived match.

        Distinguishes from operator `--add` by setting 'rule' field.
        """
        self.add(tweet_id=tweet_id, reason=reason, note=rule, brand_id=brand_id)
