from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

from .config import ProjectConfig
from .database import (
    _REQUIRED_TABLES,
    _SCRUB_TABLES,
    DatabaseFingerprint,
    DatabaseGuardError,
    PostgresRefreshBackend,
    RefreshError,
    _file_sha256,
    _hash_rows,
    _safe_child_environment,
    guard_refresh_target,
    safety_policy_from_config,
)


@dataclass(frozen=True, slots=True)
class HostedRefreshReport:
    source_database: str
    source_resource_id: str
    target_database: str
    target_resource_id: str
    target_marker_status: str
    refreshed_at: datetime
    source_schema_identity: str
    source_migration_identity: str
    row_counts: Mapping[str, int]
    scrubbed_rows: Mapping[str, int]
    dump_checksum: str
    dump_byte_size: int
    raw_artifact_removed: bool
    recovery_posture: str

    def to_receipt_payload(self) -> dict[str, Any]:
        return {
            "source_database": self.source_database,
            "source_resource_id": self.source_resource_id,
            "target_database": self.target_database,
            "target_resource_id": self.target_resource_id,
            "target_marker_status": self.target_marker_status,
            "refreshed_at": self.refreshed_at.astimezone(UTC).isoformat(),
            "source_schema_identity": self.source_schema_identity,
            "source_migration_identity": self.source_migration_identity,
            "row_counts": dict(self.row_counts),
            "scrubbed_rows": dict(self.scrubbed_rows),
            "dump_checksum": self.dump_checksum,
            "dump_byte_size": self.dump_byte_size,
            "raw_artifact_removed": self.raw_artifact_removed,
            "recovery_posture": self.recovery_posture,
        }


def guard_new_hosted_target(
    fingerprint: DatabaseFingerprint,
    *,
    expected_resource_id: str,
    policy,
    public_tables: set[str],
) -> None:
    reasons: list[str] = []
    if (
        fingerprint.resource_id in policy.production_resource_ids
        or fingerprint.database in policy.production_database_names
    ):
        reasons.append("target_is_production")
    if not expected_resource_id:
        reasons.append("hosted_resource_identity_missing")
    elif fingerprint.resource_id != expected_resource_id:
        reasons.append("hosted_resource_identity_mismatch")
    if fingerprint.environment != "staging":
        reasons.append("hosted_environment_invalid")
    if not fingerprint.database.startswith(policy.staging_name_prefix):
        reasons.append("target_name_invalid")
    if fingerprint.host in policy.local_hosts:
        reasons.append("hosted_target_is_local")
    if fingerprint.marker_environment is not None:
        reasons.append("hosted_target_already_marked")
    if public_tables:
        reasons.append("hosted_target_not_empty")
    if reasons:
        raise DatabaseGuardError(";".join(dict.fromkeys(reasons)))


class HostedStagingBootstrap:
    """Bootstrap a new, non-serving Render staging DB from scrubbed local data."""

    def __init__(
        self,
        *,
        config: ProjectConfig,
        target_database_url: str,
        target_resource_id: str,
    ) -> None:
        self.config = config
        self.policy = safety_policy_from_config(config)
        self._target_database_url = target_database_url
        self._target_resource_id = target_resource_id
        self._tmp_root = config.root / ".ollija" / "tmp"
        self._local = PostgresRefreshBackend(
            config=config,
            source_database_url="postgresql:///unused",
        )

    @staticmethod
    def _tables(connection: psycopg.Connection) -> set[str]:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public'"
            )
            return {str(row[0]) for row in cursor.fetchall()}

    def _target_fingerprint(
        self,
        connection: psycopg.Connection,
    ) -> DatabaseFingerprint:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT current_database(), session_user, "
                "COALESCE(inet_server_addr()::text, 'local_socket'), "
                "inet_server_port()"
            )
            database, role, host, port = cursor.fetchone()
            cursor.execute("SELECT to_regclass('public.ollija_environment_marker')")
            marker_exists = cursor.fetchone()[0] is not None
            marker_environment = None
            marker_status = None
            if marker_exists:
                cursor.execute(
                    "SELECT environment, status "
                    "FROM public.ollija_environment_marker WHERE singleton = TRUE"
                )
                row = cursor.fetchone()
                if row:
                    marker_environment, marker_status = str(row[0]), str(row[1])
        return DatabaseFingerprint(
            environment="staging",
            host=str(host),
            port=int(port or 5432),
            database=str(database),
            role=str(role),
            resource_id=self._target_resource_id,
            marker_environment=marker_environment,
            marker_status=marker_status,
        )

    def _target_libpq_environment(self) -> dict[str, str]:
        values = conninfo_to_dict(self._target_database_url)
        environment = _safe_child_environment({})
        for source_key, environment_key in {
            "host": "PGHOST",
            "hostaddr": "PGHOSTADDR",
            "port": "PGPORT",
            "dbname": "PGDATABASE",
            "user": "PGUSER",
            "password": "PGPASSWORD",
            "sslmode": "PGSSLMODE",
        }.items():
            value = values.get(source_key)
            if value:
                environment[environment_key] = str(value)
        return environment

    def _create_scrubbed_dump(self, source: DatabaseFingerprint) -> tuple[Path, str, int]:
        self._tmp_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._tmp_root.chmod(0o700)
        descriptor, raw_path = tempfile.mkstemp(
            prefix="scrubbed-staging-",
            suffix=".dump",
            dir=self._tmp_root,
        )
        os.close(descriptor)
        path = Path(raw_path)
        path.chmod(0o600)
        executable = shutil.which("pg_dump")
        if executable is None:
            path.unlink(missing_ok=True)
            raise RefreshError("pg_dump_unavailable")
        completed = subprocess.run(
            [
                executable,
                "--format=custom",
                "--no-owner",
                "--no-privileges",
                "--exclude-table=public.ollija_environment_marker",
                "--dbname",
                source.database,
                "--file",
                str(path),
            ],
            cwd=self.config.root,
            env=_safe_child_environment({"PGDATABASE": source.database}),
            text=True,
            capture_output=True,
            timeout=60 * 30,
            check=False,
        )
        if completed.returncode != 0:
            path.unlink(missing_ok=True)
            raise RefreshError("scrubbed_dump_failed")
        checksum = _file_sha256(path)
        return path, checksum, path.stat().st_size

    def _run_django(self, *args: str) -> None:
        python = self.config.root / ".venv" / "bin" / "python"
        environment = _safe_child_environment(
            {"DATABASE_URL": self._target_database_url}
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
            raise RefreshError("hosted_django_check_failed")

    @staticmethod
    def _scrub(connection: psycopg.Connection) -> dict[str, int]:
        tables = HostedStagingBootstrap._tables(connection)
        cleared: dict[str, int] = {}
        with connection.cursor() as cursor:
            for table in _SCRUB_TABLES:
                if table not in tables:
                    continue
                cursor.execute(
                    sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table))
                )
                cleared[table] = int(cursor.fetchone()[0])
            targets = [
                sql.Identifier(table) for table in _SCRUB_TABLES if table in tables
            ]
            if targets:
                cursor.execute(
                    sql.SQL("TRUNCATE TABLE {} RESTART IDENTITY CASCADE").format(
                        sql.SQL(", ").join(targets)
                    )
                )
            cursor.execute(
                "UPDATE django_site SET domain = %s, name = %s",
                (
                    "pushinweight-staging-web.onrender.com",
                    "PushinWeight staging",
                ),
            )
        return cleared

    @staticmethod
    def _counts(connection: psycopg.Connection) -> dict[str, int]:
        return PostgresRefreshBackend._row_counts(connection)

    def run(self) -> HostedRefreshReport:
        source = self._local.discover_active_local_database()
        guard_refresh_target(source, self.policy, allowed_statuses={"active"})
        with psycopg.connect(f"postgresql:///{source.database}") as connection:
            source_counts = self._counts(connection)
            schema_identity = _hash_rows(
                PostgresRefreshBackend._schema_rows(connection)
            )
            migration_identity = _hash_rows(
                PostgresRefreshBackend._migration_rows(connection)
            )

        with psycopg.connect(self._target_database_url) as connection:
            initial = self._target_fingerprint(connection)
            guard_new_hosted_target(
                initial,
                expected_resource_id=self._target_resource_id,
                policy=self.policy,
                public_tables=self._tables(connection),
            )
            with connection.cursor() as cursor:
                cursor.execute(
                    "CREATE TABLE public.ollija_environment_marker ("
                    "singleton boolean PRIMARY KEY DEFAULT TRUE CHECK (singleton), "
                    "environment text NOT NULL, status text NOT NULL, "
                    "source_resource_id text NOT NULL, "
                    "created_at timestamptz NOT NULL DEFAULT clock_timestamp(), "
                    "activated_at timestamptz)"
                )
                cursor.execute(
                    "INSERT INTO public.ollija_environment_marker "
                    "(singleton, environment, status, source_resource_id) "
                    "VALUES (TRUE, %s, 'building', %s)",
                    (self.policy.marker_environment, source.resource_id),
                )

        artifact: Path | None = None
        try:
            artifact, checksum, byte_size = self._create_scrubbed_dump(source)
            if _file_sha256(artifact) != checksum:
                raise RefreshError("hosted_dump_checksum_mismatch")
            with psycopg.connect(self._target_database_url) as connection:
                marked = self._target_fingerprint(connection)
            guard_refresh_target(marked, self.policy, allowed_statuses={"building"})
            executable = shutil.which("pg_restore")
            if executable is None:
                raise RefreshError("pg_restore_unavailable")
            restored = subprocess.run(
                [
                    executable,
                    "--exit-on-error",
                    "--no-owner",
                    "--no-privileges",
                    "--dbname",
                    marked.database,
                    str(artifact),
                ],
                cwd=self.config.root,
                env=self._target_libpq_environment(),
                text=True,
                capture_output=True,
                timeout=60 * 30,
                check=False,
            )
            if restored.returncode != 0:
                raise RefreshError("hosted_restore_failed")
            self._run_django("migrate", "--noinput")
            self._run_django("check")
            with psycopg.connect(self._target_database_url) as connection:
                scrubbed = self._scrub(connection)
            with psycopg.connect(self._target_database_url) as connection:
                tables = self._tables(connection)
                counts = self._counts(connection)
                with connection.cursor() as cursor:
                    zero = True
                    for table in _SCRUB_TABLES:
                        if table not in tables:
                            continue
                        cursor.execute(
                            sql.SQL("SELECT count(*) FROM {}").format(
                                sql.Identifier(table)
                            )
                        )
                        zero = zero and int(cursor.fetchone()[0]) == 0
                    if not _REQUIRED_TABLES.issubset(tables):
                        raise RefreshError("hosted_schema_invalid")
                    if counts != source_counts or not zero:
                        raise RefreshError("hosted_invariant_failed")
                    cursor.execute(
                        "UPDATE public.ollija_environment_marker "
                        "SET status = 'active', activated_at = clock_timestamp() "
                        "WHERE singleton = TRUE AND status = 'building'"
                    )
                    if cursor.rowcount != 1:
                        raise RefreshError("hosted_activation_failed")
            with psycopg.connect(self._target_database_url) as connection:
                active = self._target_fingerprint(connection)
            guard_refresh_target(active, self.policy, allowed_statuses={"active"})
            return HostedRefreshReport(
                source_database=source.database,
                source_resource_id=str(source.resource_id),
                target_database=active.database,
                target_resource_id=str(active.resource_id),
                target_marker_status=str(active.marker_status),
                refreshed_at=datetime.now(UTC),
                source_schema_identity=schema_identity,
                source_migration_identity=migration_identity,
                row_counts=counts,
                scrubbed_rows=scrubbed,
                dump_checksum=checksum,
                dump_byte_size=byte_size,
                raw_artifact_removed=True,
                recovery_posture="new_non_serving_hosted_database",
            )
        finally:
            if artifact is not None:
                artifact.unlink(missing_ok=True)
