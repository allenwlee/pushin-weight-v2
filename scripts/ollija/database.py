from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

from .config import ProjectConfig


class DatabaseGuardError(ValueError):
    """A database identity does not satisfy the fail-closed refresh policy."""


class RefreshError(RuntimeError):
    """A refresh stopped before activation."""


@dataclass(frozen=True, slots=True)
class DatabaseFingerprint:
    environment: str
    host: str
    port: int
    database: str
    role: str
    resource_id: str | None
    marker_environment: str | None = None
    marker_status: str | None = None
    default_transaction_read_only: bool = False


@dataclass(frozen=True, slots=True)
class DatabaseSafetyPolicy:
    production_resource_ids: frozenset[str]
    production_database_names: frozenset[str]
    staging_name_prefix: str
    marker_environment: str
    source_readonly_role: str
    local_resource_id: str
    local_hosts: frozenset[str]


def _strings(value: object, *, field: str) -> frozenset[str]:
    if not isinstance(value, list) or not value or not all(
        isinstance(item, str) and item for item in value
    ):
        raise DatabaseGuardError(f"database_policy_invalid:{field}")
    return frozenset(value)


def safety_policy_from_config(config: ProjectConfig) -> DatabaseSafetyPolicy:
    safety = config.database_safety
    local = config.environments.get("local")
    if not isinstance(local, Mapping):
        raise DatabaseGuardError("database_policy_invalid:environments.local")

    prefix = safety.get("staging_name_prefix")
    marker = safety.get("marker_environment")
    source_role = safety.get("source_readonly_role", "ollija_dump")
    local_resource_id = local.get("database_resource_id", "local:fuchitalee")
    local_hosts = safety.get(
        "local_hosts",
        ["local_socket", "localhost", "127.0.0.1", "::1"],
    )
    string_values = {
        "staging_name_prefix": prefix,
        "marker_environment": marker,
        "source_readonly_role": source_role,
        "local_resource_id": local_resource_id,
    }
    invalid = [
        key
        for key, value in string_values.items()
        if not isinstance(value, str) or not value
    ]
    if invalid:
        raise DatabaseGuardError(
            "database_policy_invalid:" + ",".join(sorted(invalid))
        )

    return DatabaseSafetyPolicy(
        production_resource_ids=_strings(
            safety.get("production_resource_ids"),
            field="production_resource_ids",
        ),
        production_database_names=_strings(
            safety.get("production_database_names"),
            field="production_database_names",
        ),
        staging_name_prefix=prefix,
        marker_environment=marker,
        source_readonly_role=source_role,
        local_resource_id=local_resource_id,
        local_hosts=_strings(local_hosts, field="local_hosts"),
    )


def guard_refresh_source(
    fingerprint: DatabaseFingerprint,
    policy: DatabaseSafetyPolicy,
) -> None:
    reasons: list[str] = []
    if fingerprint.environment != "production":
        reasons.append("source_environment_invalid")
    if not fingerprint.resource_id:
        reasons.append("source_resource_ambiguous")
    elif fingerprint.resource_id not in policy.production_resource_ids:
        reasons.append("source_resource_unknown")
    if fingerprint.database not in policy.production_database_names:
        reasons.append("source_database_unknown")
    if fingerprint.role != policy.source_readonly_role:
        reasons.append("source_role_not_dedicated")
    if not fingerprint.default_transaction_read_only:
        reasons.append("source_not_read_only")
    if reasons:
        raise DatabaseGuardError(";".join(reasons))


def guard_refresh_target(
    fingerprint: DatabaseFingerprint,
    policy: DatabaseSafetyPolicy,
    *,
    allowed_statuses: set[str],
) -> None:
    reasons: list[str] = []
    if (
        fingerprint.resource_id in policy.production_resource_ids
        or fingerprint.database in policy.production_database_names
    ):
        reasons.append("target_is_production")
    if not fingerprint.resource_id:
        reasons.append("target_resource_ambiguous")
    if fingerprint.environment not in {"local", "staging"}:
        reasons.append("target_environment_invalid")
    if not fingerprint.database.startswith(policy.staging_name_prefix):
        reasons.append("target_name_invalid")
    if fingerprint.environment == "local":
        if fingerprint.resource_id != policy.local_resource_id:
            reasons.append("target_local_resource_invalid")
        if fingerprint.host not in policy.local_hosts:
            reasons.append("target_local_host_invalid")
    if fingerprint.marker_environment != policy.marker_environment:
        reasons.append("target_marker_missing")
    if fingerprint.marker_status not in allowed_statuses:
        reasons.append("target_marker_status_invalid")
    if reasons:
        raise DatabaseGuardError(";".join(dict.fromkeys(reasons)))


@dataclass(frozen=True, slots=True)
class DatabaseSnapshot:
    fingerprint: DatabaseFingerprint
    captured_at: datetime
    schema_identity: str
    migration_identity: str
    row_counts: Mapping[str, int]


@dataclass(frozen=True, slots=True)
class DumpArtifact:
    identifier: str
    local_path: Path
    expected_checksum: str
    actual_checksum: str
    byte_size: int


@dataclass(frozen=True, slots=True)
class MigrationReport:
    applied: tuple[str, ...]
    database_affecting: bool
    candidate_compatible: bool
    live_code_compatible: bool
    recovery_posture: str | None


@dataclass(frozen=True, slots=True)
class ScrubReport:
    cleared_rows: Mapping[str, int]
    preserved_tables: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ValidationReport:
    schema_valid: bool
    invariants_passed: bool
    row_counts: Mapping[str, int]


@dataclass(frozen=True, slots=True)
class RefreshReport:
    source: DatabaseFingerprint
    target: DatabaseFingerprint
    snapshot_at: datetime
    snapshot_age_seconds: int
    source_schema_identity: str
    source_migration_identity: str
    row_counts: Mapping[str, int]
    scrubbed_rows: Mapping[str, int]
    preserved_tables: tuple[str, ...]
    dump_checksum: str
    dump_byte_size: int
    migrations_applied: tuple[str, ...]
    database_affecting: bool
    live_code_compatible: bool
    recovery_posture: str
    raw_artifact_removed: bool

    def to_receipt_payload(self) -> dict[str, Any]:
        return {
            "source_resource_id": self.source.resource_id,
            "source_database": self.source.database,
            "source_role": self.source.role,
            "target_resource_id": self.target.resource_id,
            "target_database": self.target.database,
            "target_marker_status": self.target.marker_status,
            "snapshot_at": self.snapshot_at.astimezone(UTC).isoformat(),
            "snapshot_age_seconds": self.snapshot_age_seconds,
            "source_schema_identity": self.source_schema_identity,
            "source_migration_identity": self.source_migration_identity,
            "row_counts": dict(self.row_counts),
            "scrubbed_rows": dict(self.scrubbed_rows),
            "preserved_tables": list(self.preserved_tables),
            "dump_checksum": self.dump_checksum,
            "dump_byte_size": self.dump_byte_size,
            "migrations_applied": list(self.migrations_applied),
            "database_affecting": self.database_affecting,
            "live_code_compatible": self.live_code_compatible,
            "recovery_posture": self.recovery_posture,
            "raw_artifact_removed": self.raw_artifact_removed,
        }


class RefreshBackend(Protocol):
    def inspect_source(self) -> DatabaseSnapshot: ...

    def create_dump(self, source: DatabaseSnapshot) -> DumpArtifact: ...

    def verify_dump(self, artifact: DumpArtifact) -> bool: ...

    def prepare_shadow(self, source: DatabaseSnapshot) -> DatabaseFingerprint: ...

    def restore_dump(
        self,
        artifact: DumpArtifact,
        target: DatabaseFingerprint,
    ) -> None: ...

    def migrate(self, target: DatabaseFingerprint) -> MigrationReport: ...

    def scrub(self, target: DatabaseFingerprint) -> ScrubReport: ...

    def validate(
        self,
        target: DatabaseFingerprint,
        source: DatabaseSnapshot,
    ) -> ValidationReport: ...

    def activate(
        self,
        target: DatabaseFingerprint,
        *,
        recovery_posture: str,
    ) -> DatabaseFingerprint: ...

    def discard_shadow(self, target: DatabaseFingerprint) -> None: ...

    def cleanup_dump(self, artifact: DumpArtifact) -> None: ...


class RefreshPipeline:
    def __init__(
        self,
        *,
        backend: RefreshBackend,
        policy: DatabaseSafetyPolicy,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.backend = backend
        self.policy = policy
        self.now = now or (lambda: datetime.now(UTC))

    def run(self) -> RefreshReport:
        artifact: DumpArtifact | None = None
        target: DatabaseFingerprint | None = None
        activated: DatabaseFingerprint | None = None
        source = self.backend.inspect_source()
        guard_refresh_source(source.fingerprint, self.policy)

        try:
            artifact = self.backend.create_dump(source)
            if not self.backend.verify_dump(artifact):
                raise RefreshError("dump_checksum_mismatch")

            target = self.backend.prepare_shadow(source)
            guard_refresh_target(target, self.policy, allowed_statuses={"building"})
            self.backend.restore_dump(artifact, target)
            migration = self.backend.migrate(target)
            self._guard_migration(migration)
            scrub = self.backend.scrub(target)
            validation = self.backend.validate(target, source)
            self._guard_validation(validation, source)
            recovery_posture = migration.recovery_posture or ""
            activated = self.backend.activate(
                target,
                recovery_posture=recovery_posture,
            )
            guard_refresh_target(
                activated,
                self.policy,
                allowed_statuses={"active"},
            )
        except (DatabaseGuardError, RefreshError):
            if target is not None and activated is None:
                self.backend.discard_shadow(target)
            raise
        except Exception as exc:
            if target is not None and activated is None:
                self.backend.discard_shadow(target)
            raise RefreshError(f"refresh_failed:{type(exc).__name__}") from exc
        finally:
            if artifact is not None:
                self.backend.cleanup_dump(artifact)

        if artifact is None or activated is None:
            raise RefreshError("refresh_incomplete")
        captured_at = source.captured_at.astimezone(UTC)
        age = max(0, int((self.now().astimezone(UTC) - captured_at).total_seconds()))
        return RefreshReport(
            source=source.fingerprint,
            target=activated,
            snapshot_at=captured_at,
            snapshot_age_seconds=age,
            source_schema_identity=source.schema_identity,
            source_migration_identity=source.migration_identity,
            row_counts=dict(validation.row_counts),
            scrubbed_rows=dict(scrub.cleared_rows),
            preserved_tables=scrub.preserved_tables,
            dump_checksum=artifact.actual_checksum,
            dump_byte_size=artifact.byte_size,
            migrations_applied=migration.applied,
            database_affecting=migration.database_affecting,
            live_code_compatible=migration.live_code_compatible,
            recovery_posture=recovery_posture,
            raw_artifact_removed=True,
        )

    @staticmethod
    def _guard_migration(report: MigrationReport) -> None:
        if not report.candidate_compatible:
            raise RefreshError("candidate_schema_incompatible")
        if report.database_affecting and not report.live_code_compatible:
            raise RefreshError("live_code_incompatible")
        if report.database_affecting and not report.recovery_posture:
            raise RefreshError("recovery_posture_missing")

    @staticmethod
    def _guard_validation(
        report: ValidationReport,
        source: DatabaseSnapshot,
    ) -> None:
        if not report.schema_valid:
            raise RefreshError("refresh_schema_invalid")
        if not report.invariants_passed:
            raise RefreshError("refresh_invariant_failed")
        for table, expected in source.row_counts.items():
            if report.row_counts.get(table) != expected:
                raise RefreshError(f"refresh_row_count_mismatch:{table}")


_PRESERVED_TABLES = ("posts", "brands", "trend_narratives")
_SCRUB_TABLES = (
    "django_session",
    "auth_user",
    "account_emailaddress",
    "account_emailconfirmation",
    "socialaccount_socialaccount",
    "socialaccount_socialtoken",
    "socialaccount_socialapp",
    "socialaccount_socialapp_sites",
    "call_state",
    "harvest_backlog_windows",
    "post_enrichment_states",
    "twitter_list_sync_state",
    "_applied_config_snapshot",
)
_REQUIRED_TABLES = frozenset(
    {
        "django_migrations",
        "django_site",
        "posts",
        "brands",
        "trend_narratives",
    }
)


def _hash_rows(rows: list[tuple[object, ...]]) -> str:
    encoded = json.dumps(rows, default=str, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_child_environment(overrides: Mapping[str, str]) -> dict[str, str]:
    environment = dict(os.environ)
    for key in (
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_BASE_URL",
        "CELERY_BROKER_URL",
        "CELERY_RESULT_BACKEND",
        "DEEPSEEK_API_KEY",
        "GOOGLE_CLIENT_ID",
        "GOOGLE_CLIENT_SECRET",
        "OLLIJA_STAGING_GOOGLE_CLIENT_ID",
        "OLLIJA_STAGING_GOOGLE_CLIENT_SECRET",
        "TWITTERAPI_IO_API_KEY",
        "X_MONITOR_HEADLINE_API_KEY",
    ):
        environment.pop(key, None)
    environment.update(overrides)
    environment.update(
        {
            "XMONITOR_DRY_RUN": "True",
            "X_MONITOR_HEADLINE_SERVING_ENABLED": "False",
            "X_MONITOR_HEADLINE_ENQUEUE_ENABLED": "False",
            "X_MONITOR_HEADLINE_PROVIDER_CALLS_ENABLED": "False",
        }
    )
    return environment


class PostgresRefreshBackend:
    """Local production-derived refresh implementation.

    Connection secrets remain in libpq environment variables inherited only by
    child processes. Public methods return fingerprints and aggregate metadata,
    never connection strings or provider values.
    """

    def __init__(
        self,
        *,
        config: ProjectConfig,
        source_database_url: str,
        admin_database_url: str = "postgresql:///postgres",
    ) -> None:
        self.config = config
        self.policy = safety_policy_from_config(config)
        self._source_database_url = source_database_url
        self._admin_database_url = admin_database_url
        self._tmp_root = config.root / ".ollija" / "tmp"
        self._source_snapshot_connection: psycopg.Connection | None = None
        self._source_snapshot_id: str | None = None

    @staticmethod
    def _local_database_url(database: str) -> str:
        return f"postgresql:///{database}"

    @staticmethod
    def _marker(connection: psycopg.Connection) -> tuple[str | None, str | None]:
        with connection.cursor() as cursor:
            cursor.execute("SELECT to_regclass('public.ollija_environment_marker')")
            if cursor.fetchone()[0] is None:
                return None, None
            cursor.execute(
                "SELECT environment, status "
                "FROM public.ollija_environment_marker WHERE singleton = TRUE"
            )
            row = cursor.fetchone()
        return (str(row[0]), str(row[1])) if row else (None, None)

    def _source_fingerprint(
        self,
        connection: psycopg.Connection,
    ) -> DatabaseFingerprint:
        production = self.config.environments.get("production")
        resource_id = (
            production.get("database_resource_id")
            if isinstance(production, Mapping)
            else None
        )
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT current_database(), session_user, "
                "COALESCE(inet_server_addr()::text, 'local_socket'), "
                "inet_server_port(), current_setting('default_transaction_read_only')"
            )
            database, role, host, port, read_only = cursor.fetchone()
        marker_environment, marker_status = self._marker(connection)
        return DatabaseFingerprint(
            environment="production",
            host=str(host),
            port=int(port or 5432),
            database=str(database),
            role=str(role),
            resource_id=str(resource_id) if resource_id else None,
            marker_environment=marker_environment,
            marker_status=marker_status,
            default_transaction_read_only=str(read_only).lower() == "on",
        )

    def _local_fingerprint(self, database: str) -> DatabaseFingerprint:
        with psycopg.connect(self._local_database_url(database)) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT current_database(), session_user, "
                    "COALESCE(inet_server_addr()::text, 'local_socket'), "
                    "inet_server_port()"
                )
                actual_database, role, host, port = cursor.fetchone()
            marker_environment, marker_status = self._marker(connection)
        return DatabaseFingerprint(
            environment="local",
            host=str(host),
            port=int(port or 5432),
            database=str(actual_database),
            role=str(role),
            resource_id=self.policy.local_resource_id,
            marker_environment=marker_environment,
            marker_status=marker_status,
        )

    @staticmethod
    def _schema_rows(connection: psycopg.Connection) -> list[tuple[object, ...]]:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT table_name, column_name, data_type, is_nullable, "
                "COALESCE(column_default, '') "
                "FROM information_schema.columns "
                "WHERE table_schema = 'public' "
                "ORDER BY table_name, ordinal_position"
            )
            return list(cursor.fetchall())

    @staticmethod
    def _migration_rows(connection: psycopg.Connection) -> list[tuple[object, ...]]:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT app, name, applied FROM django_migrations "
                "ORDER BY app, name"
            )
            return list(cursor.fetchall())

    @staticmethod
    def _row_counts(
        connection: psycopg.Connection,
        tables: tuple[str, ...] = _PRESERVED_TABLES,
    ) -> dict[str, int]:
        counts: dict[str, int] = {}
        with connection.cursor() as cursor:
            for table in tables:
                cursor.execute(
                    sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table))
                )
                counts[table] = int(cursor.fetchone()[0])
        return counts

    def inspect_source(self) -> DatabaseSnapshot:
        if self._source_snapshot_connection is not None:
            raise RefreshError("source_snapshot_already_open")
        connection = psycopg.connect(self._source_database_url)
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
                )
                cursor.execute("SELECT pg_export_snapshot()")
                snapshot_id = str(cursor.fetchone()[0])
            fingerprint = self._source_fingerprint(connection)
            guard_refresh_source(fingerprint, self.policy)
            with connection.cursor() as cursor:
                cursor.execute("SELECT clock_timestamp()")
                captured_at = cursor.fetchone()[0]
            schema_rows = self._schema_rows(connection)
            migration_rows = self._migration_rows(connection)
            row_counts = self._row_counts(connection)
        except BaseException:
            connection.close()
            raise
        self._source_snapshot_connection = connection
        self._source_snapshot_id = snapshot_id
        return DatabaseSnapshot(
            fingerprint=fingerprint,
            captured_at=captured_at,
            schema_identity=_hash_rows(schema_rows),
            migration_identity=_hash_rows(migration_rows),
            row_counts=row_counts,
        )

    def _source_libpq_environment(self) -> dict[str, str]:
        values = conninfo_to_dict(self._source_database_url)
        environment = _safe_child_environment({})
        mapping = {
            "host": "PGHOST",
            "hostaddr": "PGHOSTADDR",
            "port": "PGPORT",
            "dbname": "PGDATABASE",
            "user": "PGUSER",
            "password": "PGPASSWORD",
            "sslmode": "PGSSLMODE",
        }
        for source_key, environment_key in mapping.items():
            value = values.get(source_key)
            if value:
                environment[environment_key] = str(value)
        return environment

    def create_dump(self, source: DatabaseSnapshot) -> DumpArtifact:
        if (
            self._source_snapshot_connection is None
            or self._source_snapshot_id is None
        ):
            raise RefreshError("source_snapshot_missing")
        path: Path | None = None
        try:
            self._tmp_root.mkdir(parents=True, exist_ok=True, mode=0o700)
            self._tmp_root.chmod(0o700)
            descriptor, raw_path = tempfile.mkstemp(
                prefix="production-snapshot-",
                suffix=".dump",
                dir=self._tmp_root,
            )
            os.close(descriptor)
            path = Path(raw_path)
            path.chmod(0o600)
            executable = shutil.which("pg_dump")
            if executable is None:
                raise RefreshError("pg_dump_unavailable")
            completed = subprocess.run(
                [
                    executable,
                    "--format=custom",
                    "--no-owner",
                    "--no-privileges",
                    "--snapshot",
                    self._source_snapshot_id,
                    "--file",
                    str(path),
                ],
                cwd=self.config.root,
                env=self._source_libpq_environment(),
                text=True,
                capture_output=True,
                timeout=60 * 30,
                check=False,
            )
            if completed.returncode != 0:
                raise RefreshError("production_dump_failed")
            path.chmod(0o600)
            checksum = _file_sha256(path)
            return DumpArtifact(
                identifier=checksum[:20],
                local_path=path,
                expected_checksum=checksum,
                actual_checksum=checksum,
                byte_size=path.stat().st_size,
            )
        except BaseException:
            if path is not None:
                path.unlink(missing_ok=True)
            raise
        finally:
            self._source_snapshot_connection.close()
            self._source_snapshot_connection = None
            self._source_snapshot_id = None

    def verify_dump(self, artifact: DumpArtifact) -> bool:
        return (
            artifact.local_path.is_file()
            and artifact.local_path.stat().st_size == artifact.byte_size
            and _file_sha256(artifact.local_path) == artifact.expected_checksum
        )

    def _guard_local_admin(self, connection: psycopg.Connection) -> None:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT current_database(), "
                "COALESCE(inet_server_addr()::text, 'local_socket')"
            )
            database, host = cursor.fetchone()
        if database in self.policy.production_database_names:
            raise DatabaseGuardError("admin_database_is_production")
        if str(host) not in self.policy.local_hosts:
            raise DatabaseGuardError("admin_host_not_local")

    def prepare_shadow(self, source: DatabaseSnapshot) -> DatabaseFingerprint:
        suffix = datetime.now(UTC).strftime("%Y%m%dt%H%M%S%fz")
        database = f"{self.policy.staging_name_prefix}_shadow_{suffix}"[:63]
        with psycopg.connect(
            self._admin_database_url,
            autocommit=True,
        ) as connection:
            self._guard_local_admin(connection)
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (database,))
                if cursor.fetchone():
                    raise RefreshError("shadow_database_already_exists")
                cursor.execute(
                    sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database))
                )

        try:
            with (
                psycopg.connect(self._local_database_url(database)) as connection,
                connection.cursor() as cursor,
            ):
                cursor.execute(
                    "CREATE TABLE public.ollija_environment_marker ("
                    "singleton boolean PRIMARY KEY DEFAULT TRUE "
                    "CHECK (singleton), "
                    "environment text NOT NULL, "
                    "status text NOT NULL, "
                    "source_resource_id text NOT NULL, "
                    "created_at timestamptz NOT NULL DEFAULT clock_timestamp(), "
                    "activated_at timestamptz)"
                )
                cursor.execute(
                    "INSERT INTO public.ollija_environment_marker "
                    "(singleton, environment, status, source_resource_id) "
                    "VALUES (TRUE, %s, 'building', %s)",
                    (self.policy.marker_environment, source.fingerprint.resource_id),
                )
        except Exception:
            self._drop_named_database(database)
            raise

        fingerprint = self._local_fingerprint(database)
        guard_refresh_target(fingerprint, self.policy, allowed_statuses={"building"})
        return fingerprint

    def restore_dump(
        self,
        artifact: DumpArtifact,
        target: DatabaseFingerprint,
    ) -> None:
        current = self._local_fingerprint(target.database)
        guard_refresh_target(current, self.policy, allowed_statuses={"building"})
        executable = shutil.which("pg_restore")
        if executable is None:
            raise RefreshError("pg_restore_unavailable")
        completed = subprocess.run(
            [
                executable,
                "--exit-on-error",
                "--no-owner",
                "--no-privileges",
                "--dbname",
                target.database,
                str(artifact.local_path),
            ],
            cwd=self.config.root,
            env=_safe_child_environment({"PGDATABASE": target.database}),
            text=True,
            capture_output=True,
            timeout=60 * 30,
            check=False,
        )
        if completed.returncode != 0:
            raise RefreshError("shadow_restore_failed")

    def _candidate_is_database_affecting(self) -> bool:
        completed = subprocess.run(
            [
                "git",
                "diff",
                "--name-only",
                f"origin/{self.config.git.production_branch}...HEAD",
            ],
            cwd=self.config.root,
            text=True,
            capture_output=True,
            timeout=15,
            check=False,
        )
        if completed.returncode != 0:
            raise RefreshError("database_impact_unknown")
        paths = completed.stdout.splitlines()
        return any(
            path == "core/models.py"
            or path.startswith("core/migrations/")
            or path in {"scripts/ollija/database.py", ".ollija/project.yaml"}
            for path in paths
        )

    def _run_django(self, database: str, *args: str) -> None:
        python = self.config.canonical_virtualenv / "bin" / "python"
        if not python.is_file():
            raise RefreshError("project_python_unavailable")
        environment = _safe_child_environment(
            {"DATABASE_URL": self._local_database_url(database)}
        )
        completed = subprocess.run(
            [str(python), "manage.py", *args],
            cwd=self.config.root,
            env=environment,
            text=True,
            capture_output=True,
            timeout=60 * 10,
            check=False,
        )
        if completed.returncode != 0:
            raise RefreshError("django_database_check_failed")

    def _verify_live_code(self, database: str) -> bool:
        self._tmp_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        archive_root = Path(
            tempfile.mkdtemp(prefix="live-code-", dir=self._tmp_root)
        )
        archive_root.chmod(0o700)
        archive_path = archive_root / "source.tar"
        checkout = archive_root / "checkout"
        checkout.mkdir(mode=0o700)
        try:
            archive = subprocess.run(
                [
                    "git",
                    "archive",
                    "--format=tar",
                    f"--output={archive_path}",
                    f"origin/{self.config.git.production_branch}",
                ],
                cwd=self.config.root,
                text=True,
                capture_output=True,
                timeout=60,
                check=False,
            )
            if archive.returncode != 0:
                return False
            extracted = subprocess.run(
                ["tar", "-xf", str(archive_path), "-C", str(checkout)],
                cwd=self.config.root,
                text=True,
                capture_output=True,
                timeout=60,
                check=False,
            )
            if extracted.returncode != 0:
                return False
            python = self.config.canonical_virtualenv / "bin" / "python"
            environment = _safe_child_environment(
                {"DATABASE_URL": self._local_database_url(database)}
            )
            commands = (
                [str(python), "manage.py", "check"],
                [
                    str(python),
                    "manage.py",
                    "shell",
                    "-c",
                    (
                        "from core.models import Brand, Post; "
                        "Brand.objects.values_list('pk', flat=True).first(); "
                        "Post.objects.values_list('pk', flat=True).first()"
                    ),
                ],
            )
            for command in commands:
                completed = subprocess.run(
                    command,
                    cwd=checkout,
                    env=environment,
                    text=True,
                    capture_output=True,
                    timeout=60 * 5,
                    check=False,
                )
                if completed.returncode != 0:
                    return False
            return True
        finally:
            shutil.rmtree(archive_root, ignore_errors=True)

    def migrate(self, target: DatabaseFingerprint) -> MigrationReport:
        current = self._local_fingerprint(target.database)
        guard_refresh_target(current, self.policy, allowed_statuses={"building"})
        with psycopg.connect(self._local_database_url(target.database)) as connection:
            before = self._migration_rows(connection)
        self._run_django(target.database, "migrate", "--noinput")
        self._run_django(target.database, "check")
        with psycopg.connect(self._local_database_url(target.database)) as connection:
            after = self._migration_rows(connection)
        before_names = {(str(app), str(name)) for app, name, _applied in before}
        applied = tuple(
            f"{app}.{name}"
            for app, name, _applied in after
            if (str(app), str(name)) not in before_names
        )
        database_affecting = self._candidate_is_database_affecting()
        live_code_compatible = (
            self._verify_live_code(target.database) if database_affecting else True
        )
        return MigrationReport(
            applied=applied,
            database_affecting=database_affecting,
            candidate_compatible=True,
            live_code_compatible=live_code_compatible,
            recovery_posture="prior_local_binding_retained",
        )

    @staticmethod
    def _existing_tables(connection: psycopg.Connection) -> set[str]:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public'"
            )
            return {str(row[0]) for row in cursor.fetchall()}

    def scrub(self, target: DatabaseFingerprint) -> ScrubReport:
        current = self._local_fingerprint(target.database)
        guard_refresh_target(current, self.policy, allowed_statuses={"building"})
        cleared: dict[str, int] = {}
        with psycopg.connect(self._local_database_url(target.database)) as connection:
            tables = self._existing_tables(connection)
            with connection.cursor() as cursor:
                for table in _SCRUB_TABLES:
                    if table not in tables:
                        continue
                    cursor.execute(
                        sql.SQL("SELECT count(*) FROM {}").format(
                            sql.Identifier(table)
                        )
                    )
                    cleared[table] = int(cursor.fetchone()[0])
                scrub_targets = [
                    sql.Identifier(table)
                    for table in _SCRUB_TABLES
                    if table in tables
                ]
                if scrub_targets:
                    cursor.execute(
                        sql.SQL(
                            "TRUNCATE TABLE {} RESTART IDENTITY CASCADE"
                        ).format(sql.SQL(", ").join(scrub_targets))
                    )
                cursor.execute(
                    "UPDATE django_site SET domain = %s, name = %s",
                    ("fuchitalee.tailnet", "PushinWeight staging"),
                )
        return ScrubReport(
            cleared_rows=cleared,
            preserved_tables=_PRESERVED_TABLES,
        )

    def validate(
        self,
        target: DatabaseFingerprint,
        source: DatabaseSnapshot,
    ) -> ValidationReport:
        current = self._local_fingerprint(target.database)
        guard_refresh_target(current, self.policy, allowed_statuses={"building"})
        with psycopg.connect(self._local_database_url(target.database)) as connection:
            tables = self._existing_tables(connection)
            counts = self._row_counts(connection)
            with connection.cursor() as cursor:
                scrubbed_zero = True
                for table in _SCRUB_TABLES:
                    if table not in tables:
                        continue
                    cursor.execute(
                        sql.SQL("SELECT count(*) FROM {}").format(
                            sql.Identifier(table)
                        )
                    )
                    scrubbed_zero = scrubbed_zero and int(cursor.fetchone()[0]) == 0
        counts_match = all(
            counts.get(table) == expected
            for table, expected in source.row_counts.items()
        )
        return ValidationReport(
            schema_valid=_REQUIRED_TABLES.issubset(tables),
            invariants_passed=scrubbed_zero and counts_match,
            row_counts=counts,
        )

    def _active_local_databases(self) -> tuple[str, ...]:
        names: list[str] = []
        with psycopg.connect(self._admin_database_url) as connection:
            self._guard_local_admin(connection)
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT datname FROM pg_database "
                    "WHERE datallowconn AND datname LIKE %s ORDER BY datname",
                    (f"{self.policy.staging_name_prefix}%",),
                )
                candidates = [str(row[0]) for row in cursor.fetchall()]
        for database in candidates:
            try:
                fingerprint = self._local_fingerprint(database)
            except psycopg.Error:
                continue
            if (
                fingerprint.marker_environment == self.policy.marker_environment
                and fingerprint.marker_status == "active"
            ):
                names.append(database)
        return tuple(names)

    def activate(
        self,
        target: DatabaseFingerprint,
        *,
        recovery_posture: str,
    ) -> DatabaseFingerprint:
        if recovery_posture != "prior_local_binding_retained":
            raise RefreshError("recovery_posture_invalid")
        current = self._local_fingerprint(target.database)
        guard_refresh_target(current, self.policy, allowed_statuses={"building"})
        previous = tuple(
            database
            for database in self._active_local_databases()
            if database != target.database
        )
        for database in previous:
            guard_refresh_target(
                self._local_fingerprint(database),
                self.policy,
                allowed_statuses={"active"},
            )
        with (
            psycopg.connect(self._local_database_url(target.database)) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                "UPDATE public.ollija_environment_marker "
                "SET status = 'active', activated_at = clock_timestamp() "
                "WHERE singleton = TRUE AND status = 'building'"
            )
            if cursor.rowcount != 1:
                raise RefreshError("shadow_activation_failed")
        try:
            for database in previous:
                with (
                    psycopg.connect(self._local_database_url(database)) as connection,
                    connection.cursor() as cursor,
                ):
                    cursor.execute(
                        "UPDATE public.ollija_environment_marker "
                        "SET status = 'recovery' WHERE singleton = TRUE"
                    )
        except BaseException:
            for database in previous:
                with (
                    psycopg.connect(self._local_database_url(database)) as connection,
                    connection.cursor() as cursor,
                ):
                    cursor.execute(
                        "UPDATE public.ollija_environment_marker "
                        "SET status = 'active' WHERE singleton = TRUE"
                    )
            with (
                psycopg.connect(
                    self._local_database_url(target.database)
                ) as connection,
                connection.cursor() as cursor,
            ):
                cursor.execute(
                    "UPDATE public.ollija_environment_marker "
                    "SET status = 'building', activated_at = NULL "
                    "WHERE singleton = TRUE"
                )
            raise
        return self._local_fingerprint(target.database)

    def _drop_named_database(self, database: str) -> None:
        with psycopg.connect(
            self._admin_database_url,
            autocommit=True,
        ) as connection:
            self._guard_local_admin(connection)
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = %s AND pid <> pg_backend_pid()",
                    (database,),
                )
                cursor.execute(
                    sql.SQL("DROP DATABASE IF EXISTS {}").format(
                        sql.Identifier(database)
                    )
                )

    def discard_shadow(self, target: DatabaseFingerprint) -> None:
        current = self._local_fingerprint(target.database)
        guard_refresh_target(
            current,
            self.policy,
            allowed_statuses={"building", "ready"},
        )
        self._drop_named_database(target.database)

    def cleanup_dump(self, artifact: DumpArtifact) -> None:
        artifact.local_path.unlink(missing_ok=True)

    def discover_active_local_database(self) -> DatabaseFingerprint:
        active = self._active_local_databases()
        if len(active) != 1:
            raise RefreshError(f"active_local_database_count:{len(active)}")
        fingerprint = self._local_fingerprint(active[0])
        guard_refresh_target(
            fingerprint,
            self.policy,
            allowed_statuses={"active"},
        )
        return fingerprint
