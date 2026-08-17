from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from .redaction import UnsafeOutputError, assert_safe_value
from .tasks import AttemptSnapshot, TaskRegistry, TaskSnapshot

INCIDENT_SCHEMA_VERSION = 1
_SAFE_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
_SHA = re.compile(r"[0-9a-f]{40,64}")


class IncidentError(ValueError):
    """An incident envelope or its private local storage is unsafe."""


@dataclass(frozen=True, slots=True)
class IncidentGuidance:
    category: str
    routes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Incident:
    schema_version: int
    incident_id: str
    category: str
    phase: str
    code: str
    routes: tuple[str, ...]
    task_id: str
    generation: int
    attempt: int | None
    affected_sha: str
    evidence_refs: tuple[str, ...]
    created_at: str

    @classmethod
    def create(
        cls,
        *,
        phase: str,
        code: str,
        task_id: str,
        generation: int,
        attempt: int | None,
        affected_sha: str,
        evidence_refs: tuple[str, ...] = (),
        created_at: datetime | None = None,
    ) -> Incident:
        for value in (phase, code, task_id, *evidence_refs):
            if not _SAFE_TOKEN.fullmatch(value):
                raise IncidentError("incident_token_invalid")
        if generation < 1 or (attempt is not None and attempt < 1):
            raise IncidentError("incident_generation_invalid")
        if not _SHA.fullmatch(affected_sha):
            raise IncidentError("incident_sha_invalid")
        guidance = guidance_for_failure(code)
        timestamp = (created_at or datetime.now(UTC)).astimezone(UTC)
        body = {
            "schema_version": INCIDENT_SCHEMA_VERSION,
            "category": guidance.category,
            "phase": phase,
            "code": code,
            "routes": list(guidance.routes),
            "task_id": task_id,
            "generation": generation,
            "attempt": attempt,
            "affected_sha": affected_sha,
            "evidence_refs": list(evidence_refs),
            "created_at": timestamp.isoformat().replace("+00:00", "Z"),
        }
        try:
            assert_safe_value(body, location="incident")
        except UnsafeOutputError as exc:
            raise IncidentError("incident_unsafe") from exc
        incident_id = hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return cls(
            schema_version=INCIDENT_SCHEMA_VERSION,
            incident_id=incident_id,
            category=guidance.category,
            phase=phase,
            code=code,
            routes=guidance.routes,
            task_id=task_id,
            generation=generation,
            attempt=attempt,
            affected_sha=affected_sha,
            evidence_refs=evidence_refs,
            created_at=str(body["created_at"]),
        )

    def to_dict(self) -> dict[str, object]:
        body = asdict(self)
        body["routes"] = list(self.routes)
        body["evidence_refs"] = list(self.evidence_refs)
        assert_safe_value(body, location="incident projection")
        return body

    @classmethod
    def from_dict(cls, body: object) -> Incident:
        if not isinstance(body, dict):
            raise IncidentError("incident_body_invalid")
        try:
            expected_id = str(body["incident_id"])
            incident = cls.create(
                phase=str(body["phase"]),
                code=str(body["code"]),
                task_id=str(body["task_id"]),
                generation=int(body["generation"]),
                attempt=(int(body["attempt"]) if body.get("attempt") is not None else None),
                affected_sha=str(body["affected_sha"]),
                evidence_refs=tuple(str(item) for item in body.get("evidence_refs", ())),
                created_at=datetime.fromisoformat(str(body["created_at"])),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise IncidentError("incident_body_invalid") from exc
        if body.get("schema_version") != INCIDENT_SCHEMA_VERSION:
            raise IncidentError("incident_schema_invalid")
        if expected_id != incident.incident_id:
            raise IncidentError("incident_hash_invalid")
        if body.get("category") != incident.category or tuple(
            body.get("routes", ())
        ) != incident.routes:
            raise IncidentError("incident_guidance_invalid")
        return incident


def guidance_for_failure(code: str | None) -> IncidentGuidance:
    value = (code or "unknown").casefold()
    if any(
        token in value
        for token in (
            "virtualenv",
            "tmux",
            "ssh",
            "shell",
            "environment",
            "supervisor",
            "process_identity",
        )
    ):
        return IncidentGuidance("machine_shell", ("infra-shell", "ce-compound"))
    if any(token in value for token in ("bridgewright", "ui_assessment")):
        return IncidentGuidance(
            "ui_assessment",
            ("bridgewright", "ce-debug", "ce-compound"),
        )
    if any(
        token in value
        for token in ("release", "production", "render", "browser", "staging")
    ):
        return IncidentGuidance(
            "release_verification",
            ("ollija", "ce-debug", "ce-compound"),
        )
    if any(token in value for token in ("cancel", "stop")):
        return IncidentGuidance("cancellation", ("ollija",))
    if any(token in value for token in ("agent", "driver")):
        return IncidentGuidance("agent_driver", ("ce-debug", "ce-compound"))
    if any(
        token in value
        for token in (
            "verification",
            "test",
            "checkpoint",
            "task_diff",
            "task_source",
            "git_",
            "restart_budget",
        )
    ):
        return IncidentGuidance("code_test", ("ce-debug", "ce-compound"))
    return IncidentGuidance("unknown", ("ce-debug", "ce-compound"))


class IncidentStore:
    def __init__(self, state_root: Path) -> None:
        self.root = state_root.expanduser().absolute() / "incidents"

    def write(self, incident: Incident) -> Path:
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.root.is_symlink():
            raise IncidentError("incident_root_symlink")
        self.root.chmod(0o700)
        target = self.root / f"{incident.incident_id}.json"
        data = json.dumps(
            incident.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        if target.exists():
            if target.read_bytes() != data:
                raise IncidentError("incident_immutable_conflict")
            return target
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{incident.incident_id}.",
            dir=self.root,
        )
        temporary = Path(temporary_name)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
            target.chmod(0o600)
        finally:
            if temporary.exists():
                temporary.unlink()
        return target

    def for_task(self, task_id: str) -> tuple[Incident, ...]:
        if not self.root.is_dir():
            return ()
        incidents: list[Incident] = []
        for path in sorted(self.root.glob("*.json")):
            try:
                incident = Incident.from_dict(
                    json.loads(path.read_text(encoding="utf-8"))
                )
            except (OSError, json.JSONDecodeError, IncidentError):
                continue
            if incident.task_id == task_id:
                incidents.append(incident)
        return tuple(sorted(incidents, key=lambda item: item.created_at))


def record_task_incident(
    registry: TaskRegistry,
    task: TaskSnapshot,
    *,
    phase: str,
    attempt: AttemptSnapshot | None = None,
    evidence_refs: tuple[str, ...] = (),
) -> Incident | None:
    if not task.failure_code:
        return None
    try:
        incident = Incident.create(
            phase=phase,
            code=task.failure_code,
            task_id=task.task_id,
            generation=task.generation,
            attempt=attempt.attempt if attempt else None,
            affected_sha=task.outcome_sha or task.starting_sha,
            evidence_refs=evidence_refs,
        )
        IncidentStore(registry.path.parent).write(incident)
        return incident
    except (IncidentError, OSError):
        # The durable task failure remains authoritative if evidence storage is
        # unavailable; recording must not resurrect or hide the failed task.
        return None
