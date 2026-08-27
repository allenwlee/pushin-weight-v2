from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from scripts.staging_refresh.cli import build_parser, run
from scripts.staging_refresh.policy import (
    DatabaseInspection,
    expected_confirmation,
    load_policy,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / "config" / "staging_refresh.yaml"


class FakeRuntime:
    def __init__(self, policy) -> None:
        self.policy = policy
        self.calls: list[str] = []
        self.source = DatabaseInspection(
            database=policy.source.database,
            role=policy.source.role,
            server_version=180000,
            tls=True,
            default_transaction_read_only=True,
            has_write_privileges=False,
            can_create_database=False,
            readable_tables=policy.relations.copied_tables,
            readable_sequences=policy.relations.sequences,
            base_tables=policy.relations.classified_tables,
            views=policy.relations.views,
            sequences=policy.relations.sequences,
        )
        self.target = DatabaseInspection(
            database=policy.target.database,
            role=policy.target.role,
            server_version=180000,
            tls=True,
            default_transaction_read_only=False,
            has_write_privileges=True,
            can_create_database=True,
            readable_tables=frozenset(),
            readable_sequences=frozenset(),
            base_tables=frozenset(),
            views=frozenset(),
            sequences=frozenset(),
        )
        self.failure: Exception | None = None

    def inspect_source(self, _url: str) -> DatabaseInspection:
        self.calls.append("inspect_source")
        if self.failure:
            raise self.failure
        return self.source

    def inspect_target(self, _url: str) -> DatabaseInspection:
        self.calls.append("inspect_target")
        return self.target

    def execute(self, action: str, *, recovery: str | None = None) -> dict[str, str]:
        self.calls.append(f"execute:{action}")
        return {"action": action, "recovery": recovery or ""}


@pytest.fixture
def policy():
    return load_policy(POLICY_PATH)


@pytest.fixture
def environment(policy) -> dict[str, str]:
    return {
        "RENDER_SERVICE_ID": policy.service.id,
        "RENDER_SERVICE_NAME": policy.service.name,
        policy.enable_environment: "true",
        policy.source.environment: (
            f"postgresql://{policy.source.role}:secret@{policy.source.host}:5432/"
            f"{policy.source.database}?sslmode=require"
        ),
        policy.target.environment: (
            f"postgresql://{policy.target.role}:secret@{policy.target.host}:5432/"
            f"{policy.target.database}"
        ),
    }


def test_help_exposes_the_explicit_lifecycle_only() -> None:
    help_text = build_parser().format_help()

    for command in ("preflight", "refresh", "verify", "rollback", "prune"):
        assert command in help_text
    assert "ollija" not in help_text.lower()


def test_preflight_passes_without_a_mutating_call(policy, environment) -> None:
    runtime = FakeRuntime(policy)
    output = io.StringIO()

    status = run(
        ["--policy", str(POLICY_PATH), "preflight"],
        environ=environment,
        runtime=runtime,
        stdout=output,
    )

    assert status == 0
    assert runtime.calls == ["inspect_source", "inspect_target"]
    assert json.loads(output.getvalue())["status"] == "authorized"


@pytest.mark.parametrize("command", ["refresh", "rollback", "prune"])
def test_production_service_rejects_mutation_before_database_access(
    command: str, policy, environment
) -> None:
    runtime = FakeRuntime(policy)
    environment["RENDER_SERVICE_ID"] = "srv-production"
    recovery = "pushinweight_staging_recovery_20260827t010203z"
    args = ["--policy", str(POLICY_PATH), command]
    if command in {"rollback", "prune"}:
        args.extend(["--recovery", recovery])
    args.extend(["--confirm", "irrelevant"])

    status = run(args, environ=environment, runtime=runtime, stdout=io.StringIO())

    assert status == 2
    assert runtime.calls == []


def test_refresh_executes_only_after_exact_confirmation(policy, environment) -> None:
    runtime = FakeRuntime(policy)
    confirmation = expected_confirmation(policy, "refresh")

    status = run(
        ["--policy", str(POLICY_PATH), "refresh", "--confirm", confirmation],
        environ=environment,
        runtime=runtime,
        stdout=io.StringIO(),
    )

    assert status == 0
    assert runtime.calls[-1] == "execute:refresh"


def test_url_bearing_runtime_failure_is_not_serialized(policy, environment) -> None:
    runtime = FakeRuntime(policy)
    secret_url = "postgresql://reader:super-secret@source.internal/database"
    runtime.failure = RuntimeError(secret_url)
    output = io.StringIO()

    status = run(
        ["--policy", str(POLICY_PATH), "preflight"],
        environ=environment,
        runtime=runtime,
        stdout=output,
    )

    assert status == 1
    assert "super-secret" not in output.getvalue()
    assert secret_url not in output.getvalue()
    assert json.loads(output.getvalue())["code"] == "runtime_error"
