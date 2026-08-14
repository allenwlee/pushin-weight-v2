from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tempfile
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from . import RECEIPT_SCHEMA_VERSION
from .results import UnsafeResultError, assert_safe_value


class ReceiptError(ValueError):
    """Raised for an invalid, unsupported, or tampered receipt."""


_SHA = re.compile(r"[0-9a-f]{40,64}")
_SAFE_NAME = re.compile(r"[a-z][a-z0-9_-]*")
_RECEIPT_KINDS = {
    "approval",
    "candidate",
    "failure",
    "last_known_good",
    "production_deploy",
    "refresh",
    "staging_deploy",
}


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ReceiptError("Receipt timestamps must include a timezone")
    return value.astimezone(UTC)


def _timestamp(value: datetime) -> str:
    return _utc(value).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise ReceiptError("Receipt created_at must be an ISO-8601 string")
    try:
        return _utc(datetime.fromisoformat(value))
    except ValueError as exc:
        raise ReceiptError("Receipt created_at is not valid ISO-8601") from exc


def _canonical(body: Mapping[str, Any]) -> bytes:
    return json.dumps(
        body,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


@dataclass(frozen=True, slots=True)
class CandidateIdentity:
    sha: str
    package_version: str
    release_tag: str
    surface_fingerprint: str

    def __post_init__(self) -> None:
        if not _SHA.fullmatch(self.sha):
            raise ReceiptError("Candidate SHA must be 40-64 lowercase hex characters")
        for field_name in ("package_version", "release_tag", "surface_fingerprint"):
            if not getattr(self, field_name):
                raise ReceiptError(f"Candidate {field_name} must not be empty")

    def to_dict(self) -> dict[str, str]:
        return {
            "sha": self.sha,
            "package_version": self.package_version,
            "release_tag": self.release_tag,
            "surface_fingerprint": self.surface_fingerprint,
        }

    @classmethod
    def from_dict(cls, body: object) -> CandidateIdentity:
        if not isinstance(body, Mapping):
            raise ReceiptError("Receipt candidate must be a mapping")
        try:
            return cls(
                sha=str(body["sha"]),
                package_version=str(body["package_version"]),
                release_tag=str(body["release_tag"]),
                surface_fingerprint=str(body["surface_fingerprint"]),
            )
        except KeyError as exc:
            raise ReceiptError(f"Receipt candidate is missing {exc.args[0]}") from exc


@dataclass(frozen=True, slots=True)
class Receipt:
    schema_version: int
    receipt_id: str
    kind: str
    candidate: CandidateIdentity
    created_at: datetime
    payload: Mapping[str, Any]

    @classmethod
    def create(
        cls,
        *,
        kind: str,
        candidate: CandidateIdentity,
        created_at: datetime,
        payload: Mapping[str, Any] | None = None,
    ) -> Receipt:
        if kind not in _RECEIPT_KINDS:
            raise ReceiptError(f"Unsupported receipt kind {kind!r}")
        safe_payload = dict(payload or {})
        try:
            assert_safe_value(safe_payload, location="receipt payload")
        except UnsafeResultError as exc:
            raise ReceiptError(str(exc)) from exc
        unsigned = {
            "schema_version": RECEIPT_SCHEMA_VERSION,
            "kind": kind,
            "candidate": candidate.to_dict(),
            "created_at": _timestamp(created_at),
            "payload": safe_payload,
        }
        receipt_id = hashlib.sha256(_canonical(unsigned)).hexdigest()
        return cls(
            schema_version=RECEIPT_SCHEMA_VERSION,
            receipt_id=receipt_id,
            kind=kind,
            candidate=candidate,
            created_at=_utc(created_at),
            payload=safe_payload,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "receipt_id": self.receipt_id,
            "kind": self.kind,
            "candidate": self.candidate.to_dict(),
            "created_at": _timestamp(self.created_at),
            "payload": dict(self.payload),
        }

    @classmethod
    def from_dict(cls, body: object) -> Receipt:
        if not isinstance(body, Mapping):
            raise ReceiptError("Receipt must be a JSON object")
        version = body.get("schema_version")
        if version != RECEIPT_SCHEMA_VERSION:
            raise ReceiptError(f"Unsupported receipt schema version {version!r}")
        kind = body.get("kind")
        if not isinstance(kind, str) or kind not in _RECEIPT_KINDS:
            raise ReceiptError(f"Unsupported receipt kind {kind!r}")
        payload = body.get("payload")
        if not isinstance(payload, Mapping):
            raise ReceiptError("Receipt payload must be a mapping")
        created_at = _parse_timestamp(body.get("created_at"))
        candidate = CandidateIdentity.from_dict(body.get("candidate"))
        receipt = cls.create(
            kind=kind,
            candidate=candidate,
            created_at=created_at,
            payload=payload,
        )
        if body.get("receipt_id") != receipt.receipt_id:
            raise ReceiptError("Receipt content hash does not match receipt_id")
        return receipt


@dataclass(frozen=True, slots=True)
class LiveAuthorities:
    candidate: CandidateIdentity | None = None
    staging_deployment_id: str | None = None
    staging_deployed_sha: str | None = None
    staging_status: str | None = None
    production_deployment_id: str | None = None
    production_deployed_sha: str | None = None
    production_status: str | None = None
    required_approvals: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class LifecycleEvaluation:
    state: str
    stale_receipt_ids: tuple[str, ...]
    reasons: tuple[str, ...] = ()


def _newest(receipts: Iterable[Receipt], kind: str) -> Receipt | None:
    candidates = [receipt for receipt in receipts if receipt.kind == kind]
    return max(candidates, key=lambda item: item.created_at, default=None)


def evaluate_lifecycle(
    receipts: Iterable[Receipt], live: LiveAuthorities
) -> LifecycleEvaluation:
    all_receipts = tuple(receipts)
    stale: set[str] = set()
    reasons: list[str] = []
    candidate = live.candidate

    if candidate is None:
        return LifecycleEvaluation(
            state="idle",
            stale_receipt_ids=tuple(sorted(item.receipt_id for item in all_receipts)),
        )

    matching = []
    for receipt in all_receipts:
        if receipt.candidate != candidate:
            stale.add(receipt.receipt_id)
        else:
            matching.append(receipt)

    candidate_receipt = _newest(matching, "candidate")
    if candidate_receipt is None:
        reasons.append("candidate_receipt_missing")
        return LifecycleEvaluation("idle", tuple(sorted(stale)), tuple(reasons))

    stage_receipts = [item for item in matching if item.kind == "staging_deploy"]
    stage = _newest(stage_receipts, "staging_deploy")
    stage_valid = bool(
        stage
        and stage.payload.get("deployment_id") == live.staging_deployment_id
        and stage.payload.get("deployed_sha") == candidate.sha
        and live.staging_deployed_sha == candidate.sha
        and stage.payload.get("status") == "live"
        and live.staging_status == "live"
    )
    if not stage_valid:
        stale.update(item.receipt_id for item in stage_receipts)
        for item in matching:
            if item.kind == "approval":
                stale.add(item.receipt_id)
        return LifecycleEvaluation("candidate", tuple(sorted(stale)), tuple(reasons))

    approvals: dict[str, Receipt] = {}
    for receipt in (item for item in matching if item.kind == "approval"):
        approval_kind = receipt.payload.get("approval_kind")
        is_valid = bool(
            isinstance(approval_kind, str)
            and receipt.payload.get("approved") is True
            and receipt.payload.get("deployment_id") == live.staging_deployment_id
            and receipt.payload.get("surface_fingerprint")
            == candidate.surface_fingerprint
        )
        if not is_valid:
            stale.add(receipt.receipt_id)
            continue
        previous = approvals.get(approval_kind)
        if previous is None or receipt.created_at > previous.created_at:
            approvals[approval_kind] = receipt

    if not all(kind in approvals for kind in live.required_approvals):
        return LifecycleEvaluation("staged", tuple(sorted(stale)), tuple(reasons))

    if live.production_status in {
        "build_in_progress",
        "pre_deploy_in_progress",
        "update_in_progress",
    }:
        return LifecycleEvaluation("releasing", tuple(sorted(stale)), tuple(reasons))

    production_receipts = [
        item for item in matching if item.kind == "production_deploy"
    ]
    production = _newest(production_receipts, "production_deploy")
    production_valid = bool(
        production
        and production.payload.get("deployment_id") == live.production_deployment_id
        and production.payload.get("deployed_sha") == candidate.sha
        and live.production_deployed_sha == candidate.sha
        and production.payload.get("status") == "live"
        and live.production_status == "live"
        and production.payload.get("health_passed") is True
        and production.payload.get("smoke_passed") is True
    )
    if production_valid:
        return LifecycleEvaluation("verified", tuple(sorted(stale)), tuple(reasons))

    stale.update(item.receipt_id for item in production_receipts)
    return LifecycleEvaluation("approved", tuple(sorted(stale)), tuple(reasons))


class ReceiptStore:
    def __init__(self, root: Path, *, retention_days: int = 30) -> None:
        if retention_days < 1:
            raise ValueError("retention_days must be positive")
        self.root = root.expanduser().resolve()
        self.retention_days = retention_days

    def _ensure_directory(self, path: Path) -> None:
        missing: list[Path] = []
        current = path
        while not current.exists() and current != current.parent:
            missing.append(current)
            current = current.parent
        for directory in reversed(missing):
            directory.mkdir(mode=0o700)
            directory.chmod(0o700)

    def _receipt_path(self, kind: str, receipt_id: str) -> Path:
        if kind not in _RECEIPT_KINDS or not re.fullmatch(r"[0-9a-f]{64}", receipt_id):
            raise ReceiptError("Invalid receipt path identity")
        return self.root / "receipts" / kind / f"{receipt_id}.json"

    def _atomic_write(self, target: Path, data: bytes, *, immutable: bool) -> Path:
        self._ensure_directory(target.parent)
        if immutable and target.exists():
            if target.read_bytes() != data:
                raise ReceiptError(f"Immutable receipt already exists at {target}")
            return target

        file_descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{target.name}.",
            suffix=".tmp",
            dir=target.parent,
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(file_descriptor, "wb") as handle:
                os.fchmod(handle.fileno(), 0o600)
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
            target.chmod(0o600)
            directory_descriptor = os.open(target.parent, os.O_RDONLY)
            try:
                os.fsync(directory_descriptor)
            finally:
                os.close(directory_descriptor)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
        return target

    def write_receipt(self, receipt: Receipt) -> Path:
        body = _canonical(receipt.to_dict()) + b"\n"
        return self._atomic_write(
            self._receipt_path(receipt.kind, receipt.receipt_id),
            body,
            immutable=True,
        )

    def load_receipt(self, kind: str, receipt_id: str) -> Receipt:
        path = self._receipt_path(kind, receipt_id)
        try:
            body = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ReceiptError(f"Unable to read receipt {receipt_id}: {exc}") from exc
        return Receipt.from_dict(body)

    def iter_receipts(self) -> tuple[Receipt, ...]:
        receipts: list[Receipt] = []
        receipts_root = self.root / "receipts"
        if not receipts_root.exists():
            return ()
        for path in sorted(receipts_root.glob("*/*.json")):
            receipts.append(self.load_receipt(path.parent.name, path.stem))
        return tuple(receipts)

    def set_reference(self, name: str, receipt_id: str) -> Path:
        if not _SAFE_NAME.fullmatch(name) or not re.fullmatch(
            r"[0-9a-f]{64}", receipt_id
        ):
            raise ReceiptError("Invalid receipt reference")
        body = _canonical(
            {"schema_version": RECEIPT_SCHEMA_VERSION, "receipt_id": receipt_id}
        ) + b"\n"
        return self._atomic_write(
            self.root / "references" / f"{name}.json",
            body,
            immutable=False,
        )

    def read_reference(self, name: str) -> str | None:
        if not _SAFE_NAME.fullmatch(name):
            raise ReceiptError("Invalid receipt reference name")
        path = self.root / "references" / f"{name}.json"
        if not path.exists():
            return None
        try:
            body = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ReceiptError(f"Unable to read reference {name}: {exc}") from exc
        if body.get("schema_version") != RECEIPT_SCHEMA_VERSION:
            raise ReceiptError(f"Unsupported reference schema for {name}")
        receipt_id = body.get("receipt_id")
        if not isinstance(receipt_id, str) or not re.fullmatch(
            r"[0-9a-f]{64}", receipt_id
        ):
            raise ReceiptError(f"Reference {name} contains an invalid receipt ID")
        return receipt_id

    def warnings(
        self,
        now: datetime,
        *,
        active_receipt_ids: set[str] | None = None,
    ) -> tuple[str, ...]:
        active = active_receipt_ids or set()
        warnings: list[str] = []
        if not self.root.exists():
            return ()

        for directory in (self.root, *(path for path in self.root.rglob("*") if path.is_dir())):
            mode = stat.S_IMODE(directory.stat().st_mode)
            if mode != 0o700:
                warnings.append(
                    f"state directory permissions must be 0700: {directory} is {mode:04o}"
                )

        threshold = _utc(now) - timedelta(days=self.retention_days)
        receipts_root = self.root / "receipts"
        if receipts_root.exists():
            for path in sorted(receipts_root.glob("*/*.json")):
                mode = stat.S_IMODE(path.stat().st_mode)
                if mode != 0o600:
                    warnings.append(
                        f"receipt permissions must be 0600: {path} is {mode:04o}"
                    )
                try:
                    receipt = self.load_receipt(path.parent.name, path.stem)
                except ReceiptError as exc:
                    warnings.append(str(exc))
                    continue
                if (
                    receipt.receipt_id not in active
                    and receipt.created_at < threshold
                ):
                    warnings.append(
                        f"expired superseded receipt: {receipt.receipt_id}"
                    )
        return tuple(warnings)

    def prune_expired(
        self,
        now: datetime,
        *,
        active_receipt_ids: set[str],
    ) -> tuple[str, ...]:
        """Delete only expired, inactive receipts and return their IDs."""

        threshold = _utc(now) - timedelta(days=self.retention_days)
        removed: list[str] = []
        for receipt in self.iter_receipts():
            if receipt.receipt_id in active_receipt_ids or receipt.created_at >= threshold:
                continue
            path = self._receipt_path(receipt.kind, receipt.receipt_id)
            path.unlink()
            removed.append(receipt.receipt_id)
        return tuple(removed)
