from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from scripts.ollija.adapters.base import AuthorityObservation
from scripts.ollija.git import CommandOutcome, GitObservation
from scripts.ollija.status import (
    CheckObservation,
    StatusFacts,
    build_status_result,
    probe_tool,
)

SHA = "a" * 40


class FakeRunner:
    def __init__(self, outcomes: list[CommandOutcome]) -> None:
        self.outcomes = outcomes
        self.commands: list[tuple[str, ...]] = []

    def run(
        self, args: list[str] | tuple[str, ...], *, cwd: Path, timeout: float = 10
    ) -> CommandOutcome:
        self.commands.append(tuple(args))
        return self.outcomes.pop(0)


def _facts(*, state: str = "candidate") -> StatusFacts:
    return StatusFacts(
        authority=AuthorityObservation(
            hostname="fuchitalee",
            repository_root=Path("/repo"),
            repository_slug="allenwlee/pushin-weight-v2",
            mutation_allowed=True,
        ),
        git=GitObservation(
            repository_root=Path("/repo"),
            head_sha=SHA,
            branch="staging",
            detached=False,
            registered_worktree=True,
            dirty_paths=(),
            production_sha="1" * 40,
            staging_sha=SHA,
            branch_relationship="staging_ahead",
            remote_reachable=True,
        ),
        lifecycle_state=state,
        package_version="0.2.0b1",
        checks=(
            CheckObservation("render", "passed", "authenticated"),
            CheckObservation("bridgewright", "passed", "reachable"),
        ),
    )


def test_candidate_recommends_candidate_bound_refresh_sequence() -> None:
    candidate = build_status_result(_facts(state="candidate"))
    local = build_status_result(_facts(state="local_refreshed"))
    ready = build_status_result(_facts(state="ready_to_stage"))

    assert candidate.next_action is not None
    assert candidate.next_action.command == "ollija refresh-local"
    assert local.next_action is not None
    assert local.next_action.command == "ollija refresh-staging"
    assert ready.next_action is not None
    assert ready.next_action.command == "ollija stage"


def test_live_but_unsealed_release_recommends_verification_not_release() -> None:
    result = build_status_result(_facts(state="releasing"))

    assert result.next_action is not None
    assert result.next_action.command == "ollija verify-production"


def test_unreachable_external_authority_is_unknown_never_passed() -> None:
    facts = _facts()
    facts = StatusFacts(
        authority=facts.authority,
        git=facts.git,
        lifecycle_state=facts.lifecycle_state,
        package_version=facts.package_version,
        checks=(CheckObservation("render", "unreachable", "probe failed"),),
    )

    result = build_status_result(facts)

    assert result.status == "ok"
    assert result.details["checks"][0]["status"] == "unreachable"
    assert "passed" not in json.dumps(result.details)
    assert any("render" in warning for warning in result.warnings)


def test_tool_probe_reports_missing_incompatible_and_auth_failure(tmp_path: Path) -> None:
    missing = probe_tool(
        "render",
        {"executable": str(tmp_path / "missing")},
        FakeRunner([]),
        cwd=tmp_path,
    )
    assert missing.status == "missing"

    incompatible_runner = FakeRunner(
        [CommandOutcome(0, "render v1.0.0", "")]
    )
    incompatible = probe_tool(
        "render",
        {
            "executable": "/bin/echo",
            "version_args": ["--version"],
            "minimum_version": "2.22.0",
        },
        incompatible_runner,
        cwd=tmp_path,
    )
    assert incompatible.status == "incompatible"

    auth_runner = FakeRunner(
        [
            CommandOutcome(0, "render v2.22.0", ""),
            CommandOutcome(1, "", "not logged in"),
        ]
    )
    unauthenticated = probe_tool(
        "render",
        {
            "executable": "/bin/echo",
            "version_args": ["--version"],
            "minimum_version": "2.22.0",
            "probe_args": ["whoami"],
        },
        auth_runner,
        cwd=tmp_path,
    )
    assert unauthenticated.status == "unreachable"


def test_status_recommends_doctor_when_git_is_unsafe() -> None:
    facts = _facts()
    unsafe_git = replace(facts.git, dirty_paths=("core/models.py",))
    result = build_status_result(
        StatusFacts(
            authority=facts.authority,
            git=unsafe_git,
            lifecycle_state="candidate",
            package_version=facts.package_version,
            checks=facts.checks,
        )
    )

    assert result.status == "blocked"
    assert result.next_action is not None
    assert result.next_action.command == "ollija doctor"
