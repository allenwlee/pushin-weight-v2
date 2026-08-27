from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.staging_refresh.database import (
    RefreshError,
    SnapshotRestoreEngine,
    SourceCensus,
)
from scripts.staging_refresh.policy import load_policy

REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / "config" / "staging_refresh.yaml"


class FakeAdapter:
    def __init__(self, policy, events: list[str]) -> None:
        self.policy = policy
        self.events = events
        self.target_bytes = 100
        self.marker_valid = True
        self.census = SourceCensus(
            snapshot_id="00000003-0000001B-1",
            captured_at=datetime(2026, 8, 27, 1, 2, 3, tzinfo=UTC),
            database_bytes=100,
            schema_checksum="a" * 64,
            migration_checksum="b" * 64,
            row_counts={"posts": 12, "brands": 2},
            latest_timestamps={"posts.created_at": "2026-08-27T01:00:00+00:00"},
        )

    @contextmanager
    def exported_snapshot(self, _url: str) -> Iterator[SourceCensus]:
        self.events.append("snapshot:open")
        try:
            yield self.census
        finally:
            self.events.append("snapshot:close")

    def target_database_bytes(self, _url: str) -> int:
        self.events.append("target:size")
        return self.target_bytes

    def create_shadow(self, _url: str, name: str, marker: str) -> None:
        assert marker.startswith(self.policy.lifecycle.marker_prefix)
        self.events.append(f"shadow:create:{name}")

    def marker_matches(self, _url: str, name: str, marker: str) -> bool:
        self.events.append(f"shadow:marker:{name}")
        return self.marker_valid

    def drop_shadow(self, _url: str, name: str) -> None:
        self.events.append(f"shadow:drop:{name}")


class FakeRunner:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.commands: list[tuple[list[str], dict[str, str]]] = []
        self.fail: str | None = None
        self.interrupt_restore = False

    def __call__(self, command: list[str], **options: object):
        environment = options["env"]
        assert isinstance(environment, dict)
        self.commands.append((command, environment))
        executable = Path(command[0]).name
        self.events.append(f"command:{executable}")
        if command[1:] == ["--version"]:
            return SimpleNamespace(
                returncode=0,
                stdout=f"{executable} (PostgreSQL) 18.1\n",
                stderr="",
            )
        if executable == "pg_dump":
            if self.fail == "pg_dump":
                return SimpleNamespace(
                    returncode=1, stdout="", stderr="contains-password"
                )
            output = Path(command[command.index("--file") + 1])
            output.write_bytes(b"custom-format-dump")
        if executable == "pg_restore":
            if self.interrupt_restore:
                raise KeyboardInterrupt
            if self.fail == "pg_restore":
                return SimpleNamespace(
                    returncode=1, stdout="", stderr="contains-password"
                )
        return SimpleNamespace(returncode=0, stdout="", stderr="")


@contextmanager
def fake_lock(
    events: list[str], database_url: str, **_options: object
) -> Iterator[None]:
    label = "source" if "production" in database_url else "target"
    events.append(f"lock:{label}:acquire")
    try:
        yield
    finally:
        events.append(f"lock:{label}:release")


def _engine(tmp_path: Path, *, free: int = 10_000):
    policy = load_policy(POLICY_PATH)
    events: list[str] = []
    adapter = FakeAdapter(policy, events)
    runner = FakeRunner(events)
    source_url = (
        f"postgresql://{policy.source.role}:test@{policy.source.host}/"
        f"{policy.source.database}?sslmode=require"
    )
    target_url = (
        f"postgresql://{policy.target.role}:test@{policy.target.host}/"
        f"{policy.target.database}"
    )
    engine = SnapshotRestoreEngine(
        policy=policy,
        source_url=source_url,
        target_url=target_url,
        adapter=adapter,
        runner=runner,
        lock_factory=lambda url, **options: fake_lock(events, url, **options),
        executable_finder=lambda name: f"/usr/local/bin/{name}",
        disk_usage=lambda _path: SimpleNamespace(free=free),
        temporary_root=tmp_path,
        now=lambda: datetime(2026, 8, 27, 1, 2, 3, tzinfo=UTC),
    )
    return engine, adapter, runner, events


def test_snapshot_census_and_dump_use_one_exported_snapshot(tmp_path: Path) -> None:
    engine, _adapter, runner, events = _engine(tmp_path)

    artifact = engine.export_dump()
    with engine.target_lock():
        candidate = engine.restore_shadow(artifact)

    dump_command, source_environment = next(
        item
        for item in runner.commands
        if Path(item[0][0]).name == "pg_dump" and item[0][1:] != ["--version"]
    )
    restore_command, target_environment = next(
        item
        for item in runner.commands
        if Path(item[0][0]).name == "pg_restore" and item[0][1:] != ["--version"]
    )
    assert "--snapshot=00000003-0000001B-1" in dump_command
    assert "--format=custom" in dump_command
    assert all(
        f"--exclude-table-data=public.{table}" in dump_command
        for table in engine.policy.relations.excluded_tables
    )
    assert {"--exit-on-error", "--no-owner", "--no-privileges", "--jobs=1"} <= set(
        restore_command
    )
    assert candidate.name.startswith(engine.policy.lifecycle.shadow_prefix)
    assert artifact.checksum
    assert artifact.path.stat().st_mode & 0o777 == 0o600
    assert set(source_environment) <= engine.CHILD_ENVIRONMENT_ALLOWLIST
    assert set(target_environment) <= engine.CHILD_ENVIRONMENT_ALLOWLIST
    assert "snapshot:close" in events
    snapshot_open = events.index("snapshot:open")
    snapshot_close = events.index("snapshot:close")
    assert "command:pg_dump" in events[snapshot_open:snapshot_close]
    assert events.index("lock:target:acquire") < events.index(
        "shadow:create:" + candidate.name
    )


@pytest.mark.parametrize("failure", ["pg_dump", "pg_restore"])
def test_command_failure_is_secret_free_and_preserves_canonical(
    tmp_path: Path, failure: str
) -> None:
    engine, _adapter, runner, events = _engine(tmp_path)
    runner.fail = failure

    with pytest.raises(RefreshError) as exc_info:
        artifact = engine.export_dump()
        with engine.target_lock():
            engine.restore_shadow(artifact)

    assert "contains-password" not in str(exc_info.value)
    assert not any("pushinweight_staging:" in event for event in events)
    if failure == "pg_dump":
        assert not any(event.startswith("shadow:create") for event in events)
        assert list(tmp_path.glob("*.dump")) == []
    else:
        assert any(event.startswith("shadow:drop") for event in events)


def test_checksum_mismatch_fails_before_shadow_creation(tmp_path: Path) -> None:
    engine, _adapter, _runner, events = _engine(tmp_path)
    artifact = engine.export_dump()
    artifact.path.write_bytes(b"tampered")

    with (
        pytest.raises(RefreshError, match="dump_checksum_mismatch"),
        engine.target_lock(),
    ):
        engine.restore_shadow(artifact)

    assert not any(event.startswith("shadow:create") for event in events)


def test_restore_interruption_cleans_only_the_marked_shadow(tmp_path: Path) -> None:
    engine, adapter, runner, events = _engine(tmp_path)
    runner.interrupt_restore = True
    artifact = engine.export_dump()

    with pytest.raises(KeyboardInterrupt), engine.target_lock():
        engine.restore_shadow(artifact)

    assert any(event.startswith("shadow:marker") for event in events)
    assert any(event.startswith("shadow:drop") for event in events)
    adapter.marker_valid = False
    events.clear()

    with pytest.raises(RefreshError, match="shadow_cleanup_refused"):
        engine.cleanup_shadow("pushinweight_staging_shadow_20260827t010203z", "wrong")

    assert not any(event.startswith("shadow:drop") for event in events)


@pytest.mark.parametrize(
    ("version", "free", "error"),
    [
        ("17.7", 10_000, "postgres_client_version_unsupported"),
        ("18.1", 199, "local_space_insufficient"),
    ],
)
def test_tool_and_local_space_gates_precede_target_mutation(
    tmp_path: Path, version: str, free: int, error: str
) -> None:
    engine, _adapter, runner, events = _engine(tmp_path, free=free)
    original = runner.__call__

    def run(command: list[str], **options: object):
        result = original(command, **options)
        if command[1:] == ["--version"]:
            result.stdout = f"tool (PostgreSQL) {version}\n"
        return result

    engine.runner = run

    with pytest.raises(RefreshError, match=error):
        engine.export_dump()

    assert not any(event.startswith("shadow:create") for event in events)


def test_target_capacity_gate_precedes_shadow_creation(tmp_path: Path) -> None:
    engine, adapter, _runner, events = _engine(tmp_path)
    artifact = engine.export_dump()
    adapter.target_bytes = int(
        engine.policy.storage.target_disk_bytes
        * (1 - engine.policy.storage.required_reserve_ratio)
    )

    with (
        pytest.raises(RefreshError, match="target_capacity_insufficient"),
        engine.target_lock(),
    ):
        engine.restore_shadow(artifact)

    assert not any(event.startswith("shadow:create") for event in events)


def test_restore_requires_the_target_cluster_lock(tmp_path: Path) -> None:
    engine, _adapter, _runner, _events = _engine(tmp_path)
    artifact = engine.export_dump()

    with pytest.raises(RefreshError, match="target_lock_required"):
        engine.restore_shadow(artifact)


def test_cleanup_artifact_removes_only_the_owned_dump(tmp_path: Path) -> None:
    engine, _adapter, _runner, _events = _engine(tmp_path)
    artifact = engine.export_dump()
    unrelated = tmp_path / "unrelated.dump"
    unrelated.write_bytes(b"keep")

    engine.cleanup_artifact(artifact)

    assert not artifact.path.exists()
    assert unrelated.exists()


def test_stale_cleanup_removes_only_old_owned_artifacts(tmp_path: Path) -> None:
    engine, _adapter, _runner, _events = _engine(tmp_path)
    old_owned = tmp_path / "staging-refresh-old.dump"
    fresh_owned = tmp_path / "staging-refresh-fresh.dump"
    unrelated = tmp_path / "other.dump"
    for artifact in (old_owned, fresh_owned, unrelated):
        artifact.write_bytes(b"data")
    old_timestamp = datetime(2026, 8, 25, tzinfo=UTC).timestamp()
    old_owned.touch()
    old_owned.chmod(0o600)
    os.utime(old_owned, (old_timestamp, old_timestamp))

    engine.cleanup_stale_artifacts()

    assert not old_owned.exists()
    assert fresh_owned.exists()
    assert unrelated.exists()
