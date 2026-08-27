from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime


class ReceiptError(ValueError):
    """A receipt or durable database comment is not trusted."""


_RECEIPT_FIELDS = {
    "version",
    "action",
    "completed_at",
    "source_resource_id",
    "source_database",
    "target_resource_id",
    "canonical_database",
    "recovery_database",
    "snapshot_at",
    "dump_checksum",
    "dump_bytes",
    "source_counts",
    "candidate_counts",
    "translation_counts",
    "classification_counts",
    "scrubbed_rows",
    "latest_timestamps",
    "terminal_narrative_count",
    "current_narrative_count",
    "rollback_confirmation",
}
_COMMENT_FIELDS = {"kind", "state", "database", "receipt"}
_IDENTIFIER = re.compile(r"[a-z_][a-z0-9_]{0,62}\Z")
_RESOURCE_ID = re.compile(r"[a-z0-9][a-z0-9-]{2,127}\Z")
_CHECKSUM = re.compile(r"[0-9a-f]{64}\Z")
_TIMESTAMP_KEY = re.compile(r"[a-z_][a-z0-9_]{0,62}\.[a-z_][a-z0-9_]{0,62}\Z")


def _timestamp(value: object, *, field: str) -> str:
    if not isinstance(value, str) or "://" in value:
        raise ReceiptError(f"receipt_field_invalid:{field}")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ReceiptError(f"receipt_field_invalid:{field}") from exc
    if parsed.tzinfo is None:
        raise ReceiptError(f"receipt_field_invalid:{field}")
    return value


def _identifier(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ReceiptError(f"receipt_field_invalid:{field}")
    return value


def _resource(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not _RESOURCE_ID.fullmatch(value):
        raise ReceiptError(f"receipt_field_invalid:{field}")
    return value


def _counts(value: object, *, field: str) -> dict[str, int]:
    if not isinstance(value, Mapping):
        raise ReceiptError(f"receipt_field_invalid:{field}")
    result: dict[str, int] = {}
    for key, count in value.items():
        if not isinstance(key, str) or not _IDENTIFIER.fullmatch(key):
            raise ReceiptError(f"receipt_field_invalid:{field}")
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise ReceiptError(f"receipt_field_invalid:{field}")
        result[key] = count
    return result


def _metric_counts(value: object, *, field: str) -> dict[str, int]:
    if not isinstance(value, Mapping):
        raise ReceiptError(f"receipt_field_invalid:{field}")
    result: dict[str, int] = {}
    for key, count in value.items():
        if not isinstance(key, str) or not (
            _IDENTIFIER.fullmatch(key) or _TIMESTAMP_KEY.fullmatch(key)
        ):
            raise ReceiptError(f"receipt_field_invalid:{field}")
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise ReceiptError(f"receipt_field_invalid:{field}")
        result[key] = count
    return result


def _nonnegative_integer(value: object, *, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ReceiptError(f"receipt_field_invalid:{field}")
    return value


@dataclass(frozen=True, slots=True)
class Receipt:
    version: int
    action: str
    completed_at: str
    source_resource_id: str
    source_database: str
    target_resource_id: str
    canonical_database: str
    recovery_database: str
    snapshot_at: str
    dump_checksum: str
    dump_bytes: int
    source_counts: Mapping[str, int]
    candidate_counts: Mapping[str, int]
    translation_counts: Mapping[str, int]
    classification_counts: Mapping[str, int]
    scrubbed_rows: Mapping[str, int]
    latest_timestamps: Mapping[str, str | None]
    terminal_narrative_count: int
    current_narrative_count: int
    rollback_confirmation: str

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> Receipt:
        missing = sorted(_RECEIPT_FIELDS - set(payload))
        unknown = sorted(set(payload) - _RECEIPT_FIELDS)
        if missing:
            raise ReceiptError("receipt_missing_fields:" + ",".join(missing))
        if unknown:
            raise ReceiptError("receipt_unknown_fields:" + ",".join(unknown))
        if payload["version"] != 1:
            raise ReceiptError("receipt_version_invalid")
        action = payload["action"]
        if action not in {"refresh", "rollback"}:
            raise ReceiptError("receipt_action_invalid")
        checksum = payload["dump_checksum"]
        if not isinstance(checksum, str) or not _CHECKSUM.fullmatch(checksum):
            raise ReceiptError("receipt_field_invalid:dump_checksum")
        dump_bytes = payload["dump_bytes"]
        if (
            not isinstance(dump_bytes, int)
            or isinstance(dump_bytes, bool)
            or dump_bytes <= 0
        ):
            raise ReceiptError("receipt_field_invalid:dump_bytes")
        latest = payload["latest_timestamps"]
        if not isinstance(latest, Mapping):
            raise ReceiptError("receipt_field_invalid:latest_timestamps")
        checked_latest: dict[str, str | None] = {}
        for key, value in latest.items():
            if not isinstance(key, str) or not _TIMESTAMP_KEY.fullmatch(key):
                raise ReceiptError("receipt_field_invalid:latest_timestamps")
            checked_latest[key] = (
                None if value is None else _timestamp(value, field=key)
            )
        confirmation = payload["rollback_confirmation"]
        if (
            not isinstance(confirmation, str)
            or not confirmation.startswith("ROLLBACK staging/")
            or "://" in confirmation
            or "\n" in confirmation
        ):
            raise ReceiptError("receipt_field_invalid:rollback_confirmation")
        canonical_database = _identifier(
            payload["canonical_database"], field="canonical_database"
        )
        recovery_database = _identifier(
            payload["recovery_database"], field="recovery_database"
        )
        if confirmation != (
            f"ROLLBACK staging/{recovery_database} -> staging/{canonical_database}"
        ):
            raise ReceiptError("receipt_field_invalid:rollback_confirmation")
        return cls(
            version=1,
            action=str(action),
            completed_at=_timestamp(payload["completed_at"], field="completed_at"),
            source_resource_id=_resource(
                payload["source_resource_id"], field="source_resource_id"
            ),
            source_database=_identifier(
                payload["source_database"], field="source_database"
            ),
            target_resource_id=_resource(
                payload["target_resource_id"], field="target_resource_id"
            ),
            canonical_database=canonical_database,
            recovery_database=recovery_database,
            snapshot_at=_timestamp(payload["snapshot_at"], field="snapshot_at"),
            dump_checksum=checksum,
            dump_bytes=dump_bytes,
            source_counts=_counts(payload["source_counts"], field="source_counts"),
            candidate_counts=_counts(
                payload["candidate_counts"], field="candidate_counts"
            ),
            translation_counts=_metric_counts(
                payload["translation_counts"], field="translation_counts"
            ),
            classification_counts=_metric_counts(
                payload["classification_counts"], field="classification_counts"
            ),
            scrubbed_rows=_counts(payload["scrubbed_rows"], field="scrubbed_rows"),
            latest_timestamps=checked_latest,
            terminal_narrative_count=_nonnegative_integer(
                payload["terminal_narrative_count"],
                field="terminal_narrative_count",
            ),
            current_narrative_count=_nonnegative_integer(
                payload["current_narrative_count"],
                field="current_narrative_count",
            ),
            rollback_confirmation=confirmation,
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "version": self.version,
            "action": self.action,
            "completed_at": self.completed_at,
            "source_resource_id": self.source_resource_id,
            "source_database": self.source_database,
            "target_resource_id": self.target_resource_id,
            "canonical_database": self.canonical_database,
            "recovery_database": self.recovery_database,
            "snapshot_at": self.snapshot_at,
            "dump_checksum": self.dump_checksum,
            "dump_bytes": self.dump_bytes,
            "source_counts": dict(self.source_counts),
            "candidate_counts": dict(self.candidate_counts),
            "translation_counts": dict(self.translation_counts),
            "classification_counts": dict(self.classification_counts),
            "scrubbed_rows": dict(self.scrubbed_rows),
            "latest_timestamps": dict(self.latest_timestamps),
            "terminal_narrative_count": self.terminal_narrative_count,
            "current_narrative_count": self.current_narrative_count,
            "rollback_confirmation": self.rollback_confirmation,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_payload(), sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True, slots=True)
class DatabaseComment:
    state: str
    database: str
    receipt: Receipt


def encode_database_comment(
    *,
    marker_prefix: str,
    state: str,
    database: str,
    receipt: Receipt,
) -> str:
    if state not in {"active", "recovery"}:
        raise ReceiptError("comment_state_invalid")
    checked_database = _identifier(database, field="database")
    payload = {
        "kind": "staging-refresh-receipt",
        "state": state,
        "database": checked_database,
        "receipt": receipt.to_payload(),
    }
    return (
        marker_prefix + ":" + json.dumps(payload, sort_keys=True, separators=(",", ":"))
    )


def decode_database_comment(value: object, *, marker_prefix: str) -> DatabaseComment:
    prefix = marker_prefix + ":"
    if not isinstance(value, str) or not value.startswith(prefix):
        raise ReceiptError("comment_marker_invalid")
    try:
        payload = json.loads(value.removeprefix(prefix))
    except json.JSONDecodeError as exc:
        raise ReceiptError("comment_json_invalid") from exc
    if not isinstance(payload, Mapping):
        raise ReceiptError("comment_payload_invalid")
    unknown = sorted(set(payload) - _COMMENT_FIELDS)
    missing = sorted(_COMMENT_FIELDS - set(payload))
    if unknown:
        raise ReceiptError("comment_unknown_fields:" + ",".join(unknown))
    if missing:
        raise ReceiptError("comment_missing_fields:" + ",".join(missing))
    if payload["kind"] != "staging-refresh-receipt":
        raise ReceiptError("comment_kind_invalid")
    state = payload["state"]
    if state not in {"active", "recovery"}:
        raise ReceiptError("comment_state_invalid")
    database = _identifier(payload["database"], field="database")
    receipt_payload = payload["receipt"]
    if not isinstance(receipt_payload, Mapping):
        raise ReceiptError("comment_receipt_invalid")
    return DatabaseComment(
        state=str(state),
        database=database,
        receipt=Receipt.from_payload(receipt_payload),
    )
