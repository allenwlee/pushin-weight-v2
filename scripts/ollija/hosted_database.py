from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote, urlsplit, urlunsplit

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from .config import ProjectConfig
from .database import (
    _REQUIRED_TABLES,
    _SCRUB_TABLES,
    DatabaseFingerprint,
    DatabaseGuardError,
    DatabaseSafetyPolicy,
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
    recovery_database: str | None

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
            "recovery_database": self.recovery_database,
        }


@dataclass(frozen=True, slots=True)
class HostedRefreshPlan:
    mode: Literal["bootstrap", "replace"]
    canonical_database: str
    load_database: str
    recovery_database: str | None


def _hosted_identity_reasons(
    fingerprint: DatabaseFingerprint,
    *,
    expected_resource_id: str,
    policy: DatabaseSafetyPolicy,
) -> list[str]:
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
    return reasons


def _bounded_database_name(canonical: str, label: str, suffix: str) -> str:
    tail = f"_{label}_{suffix}"
    if len(tail) >= 63:
        raise DatabaseGuardError("hosted_database_suffix_invalid")
    return f"{canonical[: 63 - len(tail)]}{tail}"


def build_hosted_refresh_plan(
    fingerprint: DatabaseFingerprint,
    *,
    expected_resource_id: str,
    policy: DatabaseSafetyPolicy,
    public_tables: set[str],
    suffix: str,
) -> HostedRefreshPlan:
    reasons = _hosted_identity_reasons(
        fingerprint,
        expected_resource_id=expected_resource_id,
        policy=policy,
    )
    if reasons:
        raise DatabaseGuardError(";".join(dict.fromkeys(reasons)))

    if (
        fingerprint.marker_environment is None
        and fingerprint.marker_status is None
        and not public_tables
    ):
        return HostedRefreshPlan(
            mode="bootstrap",
            canonical_database=fingerprint.database,
            load_database=fingerprint.database,
            recovery_database=None,
        )

    if fingerprint.marker_environment is None and public_tables:
        reasons.append("hosted_target_not_empty")
    elif fingerprint.marker_environment != policy.marker_environment:
        reasons.append("hosted_target_marker_invalid")
    if fingerprint.marker_status != "active":
        reasons.append("hosted_target_status_invalid")
    if not _REQUIRED_TABLES.issubset(public_tables):
        reasons.append("hosted_active_schema_invalid")
    if reasons:
        raise DatabaseGuardError(";".join(dict.fromkeys(reasons)))

    return HostedRefreshPlan(
        mode="replace",
        canonical_database=fingerprint.database,
        load_database=_bounded_database_name(
            fingerprint.database,
            "shadow",
            suffix,
        ),
        recovery_database=_bounded_database_name(
            fingerprint.database,
            "recovery",
            suffix,
        ),
    )


def guard_new_hosted_target(
    fingerprint: DatabaseFingerprint,
    *,
    expected_resource_id: str,
    policy: DatabaseSafetyPolicy,
    public_tables: set[str],
) -> None:
    reasons = _hosted_identity_reasons(
        fingerprint,
        expected_resource_id=expected_resource_id,
        policy=policy,
    )
    if fingerprint.marker_environment is not None:
        reasons.append("hosted_target_already_marked")
    if public_tables:
        reasons.append("hosted_target_not_empty")
    if reasons:
        raise DatabaseGuardError(";".join(dict.fromkeys(reasons)))


class HostedStagingRefresh:
    """Refresh Render staging through a validated, non-serving database."""

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

    def _database_url(self, database: str) -> str:
        return make_conninfo(self._target_database_url, dbname=database)

    def _django_database_url(self, database: str) -> str:
        parsed = urlsplit(self._target_database_url)
        if parsed.scheme not in {"postgres", "postgresql"} or not parsed.netloc:
            raise RefreshError("staging_database_url_invalid")
        return urlunsplit(
            (
                parsed.scheme,
                parsed.netloc,
                f"/{quote(database, safe='')}",
                parsed.query,
                parsed.fragment,
            )
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

    def _fingerprint(self, database: str) -> DatabaseFingerprint:
        with psycopg.connect(self._database_url(database)) as connection:
            return self._target_fingerprint(connection)

    def _target_libpq_environment(self, database: str) -> dict[str, str]:
        values = conninfo_to_dict(self._database_url(database))
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

    def _guard_admin(
        self,
        connection: psycopg.Connection,
        target: DatabaseFingerprint,
    ) -> None:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT current_database(), session_user, "
                "COALESCE(inet_server_addr()::text, 'local_socket'), "
                "inet_server_port(), rolcreatedb "
                "FROM pg_roles WHERE rolname = session_user"
            )
            database, role, host, port, can_create = cursor.fetchone()
        reasons: list[str] = []
        if str(database) != "postgres":
            reasons.append("hosted_admin_database_invalid")
        if str(role) != target.role:
            reasons.append("hosted_admin_role_mismatch")
        if str(host) != target.host or int(port or 5432) != target.port:
            reasons.append("hosted_admin_host_mismatch")
        if not can_create:
            reasons.append("hosted_admin_createdb_missing")
        if reasons:
            raise DatabaseGuardError(";".join(reasons))

    def _create_scrubbed_dump(
        self,
        source: DatabaseFingerprint,
    ) -> tuple[Path, str, int]:
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

    def _run_django(self, database: str, *args: str) -> None:
        python = self.config.root / ".venv" / "bin" / "python"
        environment = _safe_child_environment(
            {"DATABASE_URL": self._django_database_url(database)}
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
        tables = HostedStagingRefresh._tables(connection)
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

    def _create_marker(
        self,
        database: str,
        *,
        source_resource_id: str,
    ) -> None:
        with (
            psycopg.connect(self._database_url(database)) as connection,
            connection.cursor() as cursor,
        ):
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
                (self.policy.marker_environment, source_resource_id),
            )

    def _database_exists(
        self,
        connection: psycopg.Connection,
        database: str,
    ) -> bool:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (database,))
            return cursor.fetchone() is not None

    def _present_databases(
        self,
        connection: psycopg.Connection,
        databases: tuple[str, ...],
    ) -> set[str]:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT datname FROM pg_database WHERE datname = ANY(%s)",
                (list(databases),),
            )
            return {str(row[0]) for row in cursor.fetchall()}

    def _set_database_connections(
        self,
        database: str,
        *,
        allowed: bool,
        initial: DatabaseFingerprint,
    ) -> None:
        with psycopg.connect(
            self._database_url("postgres"),
            autocommit=True,
        ) as connection:
            self._guard_admin(connection, initial)
            if not self._database_exists(connection, database):
                raise RefreshError("hosted_database_missing_during_cutover")
            with connection.cursor() as cursor:
                cursor.execute(
                    sql.SQL("ALTER DATABASE {} WITH ALLOW_CONNECTIONS {}").format(
                        sql.Identifier(database),
                        sql.SQL("true" if allowed else "false"),
                    )
                )

    def _prepare_shadow(
        self,
        plan: HostedRefreshPlan,
        source: DatabaseFingerprint,
        initial: DatabaseFingerprint,
    ) -> None:
        if plan.recovery_database is None:
            raise RefreshError("hosted_recovery_database_missing")
        with psycopg.connect(
            self._database_url("postgres"),
            autocommit=True,
        ) as connection:
            self._guard_admin(connection, initial)
            with connection.cursor() as cursor:
                cursor.execute("SELECT datname FROM pg_database ORDER BY datname")
                stale_shadows = [
                    str(row[0])
                    for row in cursor.fetchall()
                    if str(row[0]).startswith(
                        f"{self.policy.staging_name_prefix}_shadow_"
                    )
                    and str(row[0]) != plan.load_database
                ]
        for database in stale_shadows:
            self._discard_shadow(database, initial)

        with psycopg.connect(
            self._database_url("postgres"),
            autocommit=True,
        ) as connection:
            self._guard_admin(connection, initial)
            for database in (plan.load_database, plan.recovery_database):
                if self._database_exists(connection, database):
                    raise RefreshError("hosted_refresh_database_already_exists")
            with connection.cursor() as cursor:
                cursor.execute(
                    sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(
                        sql.Identifier(plan.load_database)
                    )
                )
        try:
            self._create_marker(
                plan.load_database,
                source_resource_id=str(source.resource_id),
            )
        except BaseException:
            self._discard_shadow(plan.load_database, initial)
            raise

    def _discard_shadow(
        self,
        database: str,
        initial: DatabaseFingerprint,
    ) -> bool:
        if (
            database == initial.database
            or not database.startswith(self.policy.staging_name_prefix)
            or "_shadow_" not in database
        ):
            raise DatabaseGuardError("hosted_shadow_name_invalid")
        with psycopg.connect(
            self._database_url("postgres"),
            autocommit=True,
        ) as connection:
            self._guard_admin(connection, initial)
            if not self._database_exists(connection, database):
                return True
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_get_userbyid(datdba), datallowconn "
                    "FROM pg_database "
                    "WHERE datname = %s",
                    (database,),
                )
                database_row = cursor.fetchone()
                if database_row is None or str(database_row[0]) != initial.role:
                    raise DatabaseGuardError("hosted_shadow_owner_mismatch")
                connections_allowed = bool(database_row[1])

        if not connections_allowed:
            self._set_database_connections(database, allowed=True, initial=initial)

        fingerprint = self._fingerprint(database)
        if fingerprint.marker_environment is not None:
            if fingerprint.marker_environment != self.policy.marker_environment:
                raise DatabaseGuardError("hosted_shadow_marker_invalid")
            if fingerprint.marker_status not in {"active", "building", "failed"}:
                raise DatabaseGuardError("hosted_shadow_status_invalid")
            if fingerprint.marker_status != "failed":
                self._set_marker_status(
                    database,
                    expected=str(fingerprint.marker_status),
                    status="failed",
                )

        self._set_database_connections(database, allowed=False, initial=initial)
        with psycopg.connect(
            self._database_url("postgres"),
            autocommit=True,
        ) as connection:
            self._guard_admin(connection, initial)
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = %s AND usename = current_user "
                    "AND pid <> pg_backend_pid()",
                    (database,),
                )
                try:
                    cursor.execute(
                        sql.SQL("DROP DATABASE {}").format(sql.Identifier(database))
                    )
                except (psycopg.errors.InsufficientPrivilege, psycopg.errors.ObjectInUse):
                    return False
        return True

    def _restore(self, artifact: Path, database: str) -> None:
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
                database,
                str(artifact),
            ],
            cwd=self.config.root,
            env=self._target_libpq_environment(database),
            text=True,
            capture_output=True,
            timeout=60 * 30,
            check=False,
        )
        if restored.returncode != 0:
            raise RefreshError("hosted_restore_failed")

    def _set_marker_status(
        self,
        database: str,
        *,
        expected: str,
        status: str,
    ) -> None:
        with (
            psycopg.connect(self._database_url(database)) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                "UPDATE public.ollija_environment_marker "
                "SET status = %s, "
                "activated_at = CASE WHEN %s = 'active' "
                "THEN clock_timestamp() ELSE activated_at END "
                "WHERE singleton = TRUE AND status = %s",
                (status, status, expected),
            )
            if cursor.rowcount != 1:
                raise RefreshError("hosted_marker_transition_failed")

    def _activate_replacement(
        self,
        plan: HostedRefreshPlan,
        initial: DatabaseFingerprint,
    ) -> DatabaseFingerprint:
        recovery = plan.recovery_database
        if recovery is None:
            raise RefreshError("hosted_recovery_database_missing")
        with psycopg.connect(self._target_database_url) as connection:
            current = self._target_fingerprint(connection)
            current_tables = self._tables(connection)
        current_plan = build_hosted_refresh_plan(
            current,
            expected_resource_id=self._target_resource_id,
            policy=self.policy,
            public_tables=current_tables,
            suffix="revalidation",
        )
        if (
            current_plan.mode != "replace"
            or current.database != initial.database
            or current.role != initial.role
            or current.host != initial.host
        ):
            raise DatabaseGuardError("hosted_target_changed_before_cutover")

        self._set_marker_status(
            plan.load_database,
            expected="building",
            status="active",
        )
        cutover_error: BaseException | None = None
        try:
            self._set_database_connections(
                plan.canonical_database,
                allowed=False,
                initial=initial,
            )
            with psycopg.connect(
                self._database_url("postgres"),
                autocommit=True,
            ) as connection:
                self._guard_admin(connection, initial)
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                        "WHERE datname = %s AND pid <> pg_backend_pid()",
                        (plan.canonical_database,),
                    )
            with psycopg.connect(self._database_url("postgres")) as connection:
                self._guard_admin(connection, initial)
                with connection.cursor() as cursor:
                    cursor.execute(
                        sql.SQL("ALTER DATABASE {} RENAME TO {}").format(
                            sql.Identifier(plan.canonical_database),
                            sql.Identifier(recovery),
                        )
                    )
                    cursor.execute(
                        sql.SQL("ALTER DATABASE {} RENAME TO {}").format(
                            sql.Identifier(plan.load_database),
                            sql.Identifier(plan.canonical_database),
                        )
                    )
        except BaseException as exc:  # noqa: BLE001 - reconcile interrupted cutovers
            cutover_error = exc

        expected_before = {plan.canonical_database, plan.load_database}
        expected_after = {plan.canonical_database, recovery}
        with psycopg.connect(
            self._database_url("postgres"),
            autocommit=True,
        ) as connection:
            self._guard_admin(connection, initial)
            present = self._present_databases(
                connection,
                (
                    plan.canonical_database,
                    plan.load_database,
                    recovery,
                ),
            )
        if present == expected_before:
            self._set_database_connections(
                plan.canonical_database,
                allowed=True,
                initial=initial,
            )
            self._set_marker_status(
                plan.load_database,
                expected="active",
                status="building",
            )
            raise RefreshError("hosted_cutover_failed") from cutover_error
        if present != expected_after:
            raise RefreshError("hosted_cutover_state_unknown") from cutover_error

        self._set_database_connections(recovery, allowed=True, initial=initial)
        try:
            self._set_marker_status(recovery, expected="active", status="recovery")
        finally:
            self._set_database_connections(recovery, allowed=False, initial=initial)

        active = self._fingerprint(plan.canonical_database)
        guard_refresh_target(active, self.policy, allowed_statuses={"active"})
        return active

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
            plan = build_hosted_refresh_plan(
                initial,
                expected_resource_id=self._target_resource_id,
                policy=self.policy,
                public_tables=self._tables(connection),
                suffix=datetime.now(UTC).strftime("%Y%m%dt%H%M%S%fz"),
            )

        artifact: Path | None = None
        shadow_prepared = False
        try:
            artifact, checksum, byte_size = self._create_scrubbed_dump(source)
            if _file_sha256(artifact) != checksum:
                raise RefreshError("hosted_dump_checksum_mismatch")

            if plan.mode == "bootstrap":
                self._create_marker(
                    plan.load_database,
                    source_resource_id=str(source.resource_id),
                )
            else:
                self._prepare_shadow(plan, source, initial)
                shadow_prepared = True

            marked = self._fingerprint(plan.load_database)
            guard_refresh_target(marked, self.policy, allowed_statuses={"building"})
            self._restore(artifact, plan.load_database)
            self._run_django(plan.load_database, "migrate", "--noinput")
            self._run_django(plan.load_database, "check")
            with psycopg.connect(
                self._database_url(plan.load_database)
            ) as connection:
                scrubbed = self._scrub(connection)
            with psycopg.connect(
                self._database_url(plan.load_database)
            ) as connection:
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

            if plan.mode == "replace":
                active = self._activate_replacement(plan, initial)
                recovery_posture = "prior_hosted_binding_retained"
            else:
                self._set_marker_status(
                    plan.load_database,
                    expected="building",
                    status="active",
                )
                active = self._fingerprint(plan.canonical_database)
                guard_refresh_target(
                    active,
                    self.policy,
                    allowed_statuses={"active"},
                )
                recovery_posture = "new_non_serving_hosted_database"

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
                recovery_posture=recovery_posture,
                recovery_database=plan.recovery_database,
            )
        except BaseException as exc:
            if shadow_prepared:
                discarded = self._discard_shadow(plan.load_database, initial)
                if not discarded:
                    raise RefreshError(
                        "hosted_refresh_failed;hosted_shadow_retained_disabled"
                    ) from exc
            raise
        finally:
            if artifact is not None:
                artifact.unlink(missing_ok=True)
