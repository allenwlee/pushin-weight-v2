from __future__ import annotations

import json
import stat
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from scripts.ollija.incidents import (
    Incident,
    IncidentError,
    IncidentStore,
    guidance_for_failure,
    record_task_incident,
)
from scripts.ollija.tasks import TaskRegistry
from tests.ollija.test_tasks import _grant


@pytest.mark.parametrize(
    "code",
    (
        "virtualenv_missing",
        "tmux_unavailable",
        "ssh_unreachable",
        "shell_failed",
        "environment_invalid",
    ),
)
def test_machine_failures_route_to_infra_shell_first(code: str) -> None:
    guidance = guidance_for_failure(code)

    assert guidance.category == "machine_shell"
    assert guidance.routes[0] == "infra-shell"


def test_code_and_ui_failures_have_deterministic_documentation_routes() -> None:
    code = guidance_for_failure("verification_failed")
    ui = guidance_for_failure("bridgewright_probe_failed")

    assert code.routes == ("ce-debug", "ce-compound")
    assert ui.routes == ("bridgewright", "ce-debug", "ce-compound")


def test_private_incident_records_only_bounded_safe_evidence(tmp_path) -> None:
    registry = TaskRegistry(tmp_path / "state" / "tasks.sqlite3")
    armed = registry.arm(_grant(tmp_path))
    registry.mark_running(armed.task_id, armed.generation)
    paused = registry.pause(
        armed.task_id,
        armed.generation,
        failure_code="verification_failed",
    )

    incident = record_task_incident(
        registry,
        paused,
        phase="checkpoint.verify",
        evidence_refs=("gate.pytest",),
    )

    assert incident is not None
    path = IncidentStore(registry.path.parent).root / f"{incident.incident_id}.json"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    body = json.loads(path.read_text(encoding="utf-8"))
    assert body["code"] == "verification_failed"
    assert body["routes"] == ["ce-debug", "ce-compound"]
    serialized = json.dumps(body)
    assert "prompt" not in serialized
    assert "provider response" not in serialized
    assert "DATABASE_URL" not in serialized


def test_incident_rejects_secret_bearing_or_unbounded_fields() -> None:
    with pytest.raises(IncidentError, match="token_invalid"):
        Incident.create(
            phase="checkpoint",
            code="failed:postgresql://user:secret@example.invalid/db",
            task_id="task-1",
            generation=1,
            attempt=1,
            affected_sha="a" * 40,
            created_at=datetime(2026, 8, 17, tzinfo=UTC),
        )


def test_tampered_incident_is_ignored_by_status_projection(tmp_path) -> None:
    store = IncidentStore(tmp_path / "state")
    incident = Incident.create(
        phase="checkpoint",
        code="verification_failed",
        task_id="task-1",
        generation=1,
        attempt=1,
        affected_sha="a" * 40,
        created_at=datetime(2026, 8, 17, tzinfo=UTC),
    )
    path = store.write(incident)
    body = json.loads(path.read_text(encoding="utf-8"))
    body["code"] = "git_failed"
    path.write_text(json.dumps(body), encoding="utf-8")

    assert store.for_task("task-1") == ()


def test_override_incident_reference_does_not_rewrite_prior_record(tmp_path) -> None:
    store = IncidentStore(tmp_path / "state")
    incident = Incident.create(
        phase="ui.assessment",
        code="bridgewright_probe_failed",
        task_id="task-1",
        generation=1,
        attempt=1,
        affected_sha="a" * 40,
        evidence_refs=("owner_override",),
        created_at=datetime(2026, 8, 17, tzinfo=UTC),
    )
    original = store.write(incident).read_bytes()

    store.write(replace(incident))

    assert store.for_task("task-1") == (incident,)
    assert store.write(incident).read_bytes() == original
