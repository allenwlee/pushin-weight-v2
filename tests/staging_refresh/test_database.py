from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.staging_refresh.database import (
    CandidateCensus,
    CandidateProcessor,
    RefreshError,
    ScrubReport,
    SnapshotRestoreEngine,
    SourceCensus,
    scrub_candidate_data,
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
            row_counts={
                "accounts": 5,
                "brands": 2,
                "posts": 12,
                "posts_brands": 10,
                "products": 3,
            },
            latest_timestamps={"posts.created_at": "2026-08-27T01:00:00+00:00"},
            translation_counts={
                "posts.text_en": 10,
                "posts.text_zh_cn": 10,
                "brands.display_name_en": 2,
                "brands.display_name_zh_cn": 2,
            },
            classification_counts={
                table: 1 for table in policy.validation.classification_tables
            },
            terminal_narrative_count=4,
            current_narrative_count=4,
        )
        self.candidate_census = CandidateCensus(
            base_tables=policy.relations.classified_tables,
            views=policy.relations.views,
            sequences=policy.relations.sequences,
            columns=policy.validation.required_columns,
            row_counts=self.census.row_counts,
            latest_timestamps=self.census.latest_timestamps,
            translation_counts=self.census.translation_counts,
            classification_counts=self.census.classification_counts,
            scrubbed_counts={table: 0 for table in policy.scrub.truncate_tables},
            terminal_narrative_count=4,
            current_narrative_count=4,
            duplicate_current_windows=(),
            invalid_foreign_keys=(),
            view_valid=True,
            site_domain=policy.scrub.site_domain,
            site_name=policy.scrub.site_name,
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

    def scrub_candidate(self, _url: str, name: str) -> ScrubReport:
        self.events.append(f"candidate:scrub:{name}")
        return ScrubReport(
            cleared_rows={table: 1 for table in self.policy.scrub.truncate_tables},
            removed_narratives=3,
            retained_narratives=4,
            site_rows=1,
        )

    def inspect_candidate(self, _url: str, name: str) -> CandidateCensus:
        self.events.append(f"candidate:inspect:{name}")
        return self.candidate_census

    def mark_validated(
        self,
        _url: str,
        name: str,
        marker: str,
        evidence: dict[str, object],
    ) -> str:
        assert evidence["validation"] == "passed"
        self.events.append(f"candidate:validated:{name}")
        return marker.replace('"state":"building"', '"state":"validated"')


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
        if (
            executable == "python"
            and command[-2:] == ["migrate", "--check"]
            and self.fail == "django_migrate_check"
        ):
            return SimpleNamespace(returncode=1, stdout="", stderr="pending")
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


def test_candidate_runs_migrations_scrub_and_full_validation_before_marking(
    tmp_path: Path,
) -> None:
    engine, adapter, runner, events = _engine(tmp_path)
    artifact = engine.export_dump()
    with engine.target_lock():
        candidate = engine.restore_shadow(artifact)
        result = CandidateProcessor(
            policy=engine.policy,
            target_url=engine.target_url,
            adapter=adapter,
            runner=runner,
            python="/usr/local/bin/python",
        ).process(candidate)

    django_commands = [
        command[1:]
        for command, _environment in runner.commands
        if Path(command[0]).name == "python"
    ]
    assert django_commands == [
        ["manage.py", "migrate", "--noinput"],
        ["manage.py", "check", "--deploy"],
        ["manage.py", "migrate", "--check"],
    ]
    assert events.index(f"candidate:scrub:{candidate.name}") < events.index(
        f"candidate:inspect:{candidate.name}"
    )
    assert events[-2] == f"candidate:validated:{candidate.name}"
    assert result.candidate.marker != candidate.marker
    assert result.scrub.removed_narratives == 3


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ("missing_migration", "candidate_migrations_pending"),
        ("invalid_view", "candidate_view_invalid"),
        ("stale_timestamp", "candidate_latest_timestamp_mismatch:posts.created_at"),
        ("count_drift", "candidate_count_mismatch:posts"),
        ("orphan", "candidate_foreign_key_invalid:fk_orphan"),
        ("translation", "candidate_translation_mismatch:posts.text_en"),
        ("duplicate_current", "candidate_current_narrative_duplicate:1"),
        ("sensitive", "candidate_scrub_incomplete:auth_user"),
    ],
)
def test_candidate_validation_blocks_every_unsafe_shape(
    tmp_path: Path, change: str, code: str
) -> None:
    engine, adapter, runner, events = _engine(tmp_path)
    artifact = engine.export_dump()
    with engine.target_lock():
        candidate = engine.restore_shadow(artifact)
        census = adapter.candidate_census
        if change == "missing_migration":
            runner.fail = "django_migrate_check"
        elif change == "invalid_view":
            census = replace(census, view_valid=False)
        elif change == "stale_timestamp":
            census = replace(
                census,
                latest_timestamps={"posts.created_at": "2026-08-26T01:00:00+00:00"},
            )
        elif change == "count_drift":
            census = replace(census, row_counts={**census.row_counts, "posts": 11})
        elif change == "orphan":
            census = replace(census, invalid_foreign_keys=("fk_orphan",))
        elif change == "translation":
            census = replace(
                census,
                translation_counts={**census.translation_counts, "posts.text_en": 9},
            )
        elif change == "duplicate_current":
            census = replace(census, duplicate_current_windows=(1,))
        elif change == "sensitive":
            census = replace(
                census,
                scrubbed_counts={**census.scrubbed_counts, "auth_user": 1},
            )
        adapter.candidate_census = census

        with pytest.raises(RefreshError, match=code):
            CandidateProcessor(
                policy=engine.policy,
                target_url=engine.target_url,
                adapter=adapter,
                runner=runner,
                python="/usr/local/bin/python",
            ).process(candidate)

    assert not any(event.startswith("candidate:validated") for event in events)


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
def test_database_scrub_removes_private_and_transient_state_but_keeps_history() -> None:
    from django.contrib.auth import get_user_model
    from django.contrib.sites.models import Site
    from django.db import connection, transaction

    from core.models import TrendNarrative

    policy = load_policy(POLICY_PATH)
    now = datetime(2026, 8, 27, 1, 0, tzinfo=UTC)
    get_user_model().objects.create_user(username="private", password="test")
    transient = TrendNarrative.objects.create(
        source_cycle_id="transient",
        window_days=1,
        status="checked",
        facts_as_of=now,
    )
    published = TrendNarrative.objects.create(
        source_cycle_id="published",
        window_days=7,
        status="published",
        facts_as_of=now,
        is_current=True,
        primary_brand_key="brand",
        primary_brand_name_en="Brand",
        primary_brand_name_zh_hans="品牌",
        body_en="Published body",
        body_zh_hans="已发布内容",
        output_hash="output-hash",
        call_slot_consumed=True,
        claim_owner="worker",
        claim_fence=1,
        claimed_at=now,
        claim_expires_at=now.replace(hour=2),
        transport_started_at=now,
        transport_completed_at=now,
        generated_at=now,
        published_at=now,
    )

    with transaction.atomic(), connection.cursor() as cursor:
        report = scrub_candidate_data(cursor, policy)

    assert report.removed_narratives == 1
    assert not TrendNarrative.objects.filter(pk=transient.pk).exists()
    assert TrendNarrative.objects.filter(pk=published.pk, status="published").exists()
    assert get_user_model().objects.count() == 0
    site = Site.objects.get(pk=1)
    assert site.domain == policy.scrub.site_domain
    with connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM trend_narrative_versions")
        assert cursor.fetchone()[0] == 1


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
def test_database_scrub_failure_rolls_back_every_destructive_statement() -> None:
    from django.contrib.auth import get_user_model
    from django.db import DatabaseError, connection, transaction

    policy = load_policy(POLICY_PATH)
    get_user_model().objects.create_user(username="must-survive", password="test")
    with connection.cursor() as cursor:
        cursor.execute(
            "CREATE FUNCTION staging_refresh_test_reject_site() RETURNS trigger "
            "LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'reject site'; END $$"
        )
        cursor.execute(
            "CREATE TRIGGER staging_refresh_test_reject_site "
            "BEFORE UPDATE ON django_site FOR EACH STATEMENT "
            "EXECUTE FUNCTION staging_refresh_test_reject_site()"
        )
    try:
        with (
            pytest.raises(DatabaseError, match="reject site"),
            transaction.atomic(),
            connection.cursor() as cursor,
        ):
            scrub_candidate_data(cursor, policy)

        assert get_user_model().objects.filter(username="must-survive").exists()
    finally:
        with connection.cursor() as cursor:
            cursor.execute(
                "DROP TRIGGER IF EXISTS staging_refresh_test_reject_site ON django_site"
            )
            cursor.execute("DROP FUNCTION IF EXISTS staging_refresh_test_reject_site()")
