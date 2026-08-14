from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from typing import Any

from . import RESULT_SCHEMA_VERSION
from .redaction import assert_safe_value


@dataclass(frozen=True, slots=True)
class NextAction:
    command: str
    reason: str


@dataclass(frozen=True, slots=True)
class EvidenceRef:
    kind: str
    identifier: str
    candidate_sha: str | None = None


@dataclass(frozen=True, slots=True)
class CommandError:
    code: str
    message: str
    retryable: bool = False


@dataclass(frozen=True, slots=True)
class CommandResult:
    command: str
    status: str
    state: str
    summary: str
    next_action: NextAction | None = None
    evidence: tuple[EvidenceRef, ...] = ()
    warnings: tuple[str, ...] = ()
    errors: tuple[CommandError, ...] = ()
    details: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        if self.status not in {"ok", "blocked", "failed"}:
            raise ValueError(f"Unsupported command status {self.status!r}")

        body: dict[str, Any] = {
            "schema_version": RESULT_SCHEMA_VERSION,
            "command": self.command,
            "status": self.status,
            "state": self.state,
            "summary": self.summary,
            "next_action": asdict(self.next_action) if self.next_action else None,
            "evidence": [asdict(item) for item in self.evidence],
            "warnings": list(self.warnings),
            "errors": [asdict(item) for item in self.errors],
            "details": dict(self.details),
        }
        assert_safe_value(body)
        return body
