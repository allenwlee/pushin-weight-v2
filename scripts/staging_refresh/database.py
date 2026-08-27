from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import quote, urlsplit, urlunsplit

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

from scripts.database_lock import acquire_cluster_lock, admin_connection_parameters

from .policy import DatabaseInspection, RefreshPolicy


class RefreshError(RuntimeError):
    """A secret-free failure before staging activation."""


@dataclass(frozen=True, slots=True)
class SourceCensus:
    snapshot_id: str
    captured_at: datetime
    database_bytes: int
    schema_checksum: str
    migration_checksum: str
    row_counts: Mapping[str, int]
    latest_timestamps: Mapping[str, str | None]
    translation_counts: Mapping[str, int]
    classification_counts: Mapping[str, int]
    terminal_narrative_count: int
    current_narrative_count: int


@dataclass(frozen=True, slots=True)
class DumpArtifact:
    path: Path
    checksum: str
    byte_size: int
    source: SourceCensus


@dataclass(frozen=True, slots=True)
class ShadowCandidate:
    name: str
    marker: str
    artifact: DumpArtifact


@dataclass(frozen=True, slots=True)
class ScrubReport:
    cleared_rows: Mapping[str, int]
    removed_narratives: int
    retained_narratives: int
    site_rows: int


@dataclass(frozen=True, slots=True)
class CandidateCensus:
    base_tables: frozenset[str]
    views: frozenset[str]
    sequences: frozenset[str]
    columns: Mapping[str, frozenset[str]]
    row_counts: Mapping[str, int]
    latest_timestamps: Mapping[str, str | None]
    translation_counts: Mapping[str, int]
    classification_counts: Mapping[str, int]
    scrubbed_counts: Mapping[str, int]
    terminal_narrative_count: int
    current_narrative_count: int
    duplicate_current_windows: tuple[int, ...]
    invalid_foreign_keys: tuple[str, ...]
    view_valid: bool
    site_domain: str
    site_name: str


@dataclass(frozen=True, slots=True)
class CandidateResult:
    candidate: ShadowCandidate
    scrub: ScrubReport
    census: CandidateCensus


class SnapshotAdapter(Protocol):
    def exported_snapshot(self, database_url: str) -> Any: ...

    def target_database_bytes(self, database_url: str) -> int: ...

    def create_shadow(self, database_url: str, name: str, marker: str) -> None: ...

    def marker_matches(self, database_url: str, name: str, marker: str) -> bool: ...

    def drop_shadow(self, database_url: str, name: str) -> None: ...

    def scrub_candidate(self, database_url: str, name: str) -> ScrubReport: ...

    def inspect_candidate(self, database_url: str, name: str) -> CandidateCensus: ...

    def mark_validated(
        self,
        database_url: str,
        name: str,
        marker: str,
        evidence: dict[str, object],
    ) -> str: ...


class CommandResult(Protocol):
    returncode: int
    stdout: str
    stderr: str


def _hash_rows(rows: list[tuple[object, ...]]) -> str:
    payload = json.dumps(rows, default=str, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _libpq_environment(
    database_url: str,
    *,
    database: str | None = None,
    require_tls: bool,
) -> dict[str, str]:
    try:
        values = conninfo_to_dict(database_url)
    except Exception as exc:
        raise RefreshError("connection_url_invalid") from exc
    environment = {
        key: os.environ[key]
        for key in ("PATH", "LANG", "LC_ALL", "TZ", "SYSTEMROOT")
        if key in os.environ
    }
    for source_key, child_key in {
        "host": "PGHOST",
        "hostaddr": "PGHOSTADDR",
        "port": "PGPORT",
        "dbname": "PGDATABASE",
        "user": "PGUSER",
        "password": "PGPASSWORD",
        "sslmode": "PGSSLMODE",
    }.items():
        value = values.get(source_key)
        if value is not None:
            environment[child_key] = str(value)
    if database:
        environment["PGDATABASE"] = database
    if require_tls:
        environment["PGSSLMODE"] = "require"
    environment["PGAPPNAME"] = "staging-data-refresh"
    return environment


def _table_count(cursor: Any, table: str) -> int:
    cursor.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table)))
    return int(cursor.fetchone()[0])


def _translation_counts(cursor: Any, policy: RefreshPolicy) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table, columns in policy.validation.translation_columns.items():
        for column in columns:
            cursor.execute(
                sql.SQL(
                    "SELECT count(*) FROM {} WHERE NULLIF(BTRIM({}), '') IS NOT NULL"
                ).format(sql.Identifier(table), sql.Identifier(column))
            )
            counts[f"{table}.{column}"] = int(cursor.fetchone()[0])
    return counts


def scrub_candidate_data(cursor: Any, policy: RefreshPolicy) -> ScrubReport:
    """Scrub one already-restored non-serving database inside its transaction."""

    cleared = {
        table: _table_count(cursor, table)
        for table in sorted(policy.scrub.truncate_tables)
    }
    targets = [sql.Identifier(table) for table in sorted(policy.scrub.truncate_tables)]
    cursor.execute(
        sql.SQL("TRUNCATE TABLE {} RESTART IDENTITY CASCADE").format(
            sql.SQL(", ").join(targets)
        )
    )
    cursor.execute(
        "DELETE FROM trend_narratives WHERE NOT (status = ANY(%s))",
        [list(policy.scrub.retained_narrative_statuses)],
    )
    removed_narratives = int(cursor.rowcount)
    cursor.execute(
        "UPDATE django_site SET domain = %s, name = %s",
        [policy.scrub.site_domain, policy.scrub.site_name],
    )
    site_rows = int(cursor.rowcount)
    retained_narratives = _table_count(cursor, "trend_narratives")
    return ScrubReport(
        cleared_rows=cleared,
        removed_narratives=removed_narratives,
        retained_narratives=retained_narratives,
        site_rows=site_rows,
    )


class PsycopgSnapshotAdapter:
    def __init__(
        self,
        policy: RefreshPolicy,
        *,
        connect: Callable[..., Any] = psycopg.connect,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.policy = policy
        self.connect = connect
        self.now = now or (lambda: datetime.now(UTC))

    @contextmanager
    def exported_snapshot(self, database_url: str) -> Iterator[SourceCensus]:
        with (
            self.connect(database_url, autocommit=True) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                "BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
            )
            cursor.execute("SELECT pg_export_snapshot()")
            snapshot_id = str(cursor.fetchone()[0])
            cursor.execute("SELECT pg_database_size(current_database())")
            database_bytes = int(cursor.fetchone()[0])
            cursor.execute(
                "SELECT table_name, column_name, data_type, is_nullable, "
                "COALESCE(column_default, '') FROM information_schema.columns "
                "WHERE table_schema = 'public' ORDER BY table_name, ordinal_position"
            )
            schema_checksum = _hash_rows(list(cursor.fetchall()))
            cursor.execute(
                "SELECT app, name, applied FROM django_migrations ORDER BY app, name"
            )
            migration_checksum = _hash_rows(list(cursor.fetchall()))
            row_counts: dict[str, int] = {}
            for table in self.policy.validation.exact_count_tables:
                cursor.execute(
                    sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table))
                )
                row_counts[table] = int(cursor.fetchone()[0])
            latest: dict[str, str | None] = {}
            table = self.policy.validation.latest_timestamp_table
            column = self.policy.validation.latest_timestamp_column
            cursor.execute(
                sql.SQL("SELECT max({}) FROM {}").format(
                    sql.Identifier(column),
                    sql.Identifier(table),
                )
            )
            value = cursor.fetchone()[0]
            latest[f"{table}.{column}"] = value.isoformat() if value else None
            translation_counts = _translation_counts(cursor, self.policy)
            classification_counts = {
                table: _table_count(cursor, table)
                for table in self.policy.validation.classification_tables
            }
            cursor.execute(
                "SELECT count(*) FROM trend_narratives WHERE status = ANY(%s)",
                [list(self.policy.scrub.retained_narrative_statuses)],
            )
            terminal_narrative_count = int(cursor.fetchone()[0])
            cursor.execute(
                "SELECT count(*) FROM trend_narratives "
                "WHERE status = 'published' AND is_current"
            )
            current_narrative_count = int(cursor.fetchone()[0])
            census = SourceCensus(
                snapshot_id=snapshot_id,
                captured_at=self.now().astimezone(UTC),
                database_bytes=database_bytes,
                schema_checksum=schema_checksum,
                migration_checksum=migration_checksum,
                row_counts=row_counts,
                latest_timestamps=latest,
                translation_counts=translation_counts,
                classification_counts=classification_counts,
                terminal_narrative_count=terminal_narrative_count,
                current_narrative_count=current_narrative_count,
            )
            try:
                yield census
            finally:
                cursor.execute("ROLLBACK")

    def target_database_bytes(self, database_url: str) -> int:
        parameters = admin_connection_parameters(database_url)
        with self.connect(**parameters) as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT COALESCE(sum(pg_database_size(datname)), 0) FROM pg_database"
            )
            return int(cursor.fetchone()[0])

    def create_shadow(self, database_url: str, name: str, marker: str) -> None:
        parameters = admin_connection_parameters(database_url)
        with (
            self.connect(**parameters, autocommit=True) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", [name])
            if cursor.fetchone() is not None:
                raise RefreshError("shadow_database_already_exists")
            cursor.execute(
                sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(
                    sql.Identifier(name)
                )
            )
            cursor.execute(
                sql.SQL("COMMENT ON DATABASE {} IS %s").format(sql.Identifier(name)),
                [marker],
            )

    def marker_matches(self, database_url: str, name: str, marker: str) -> bool:
        parameters = admin_connection_parameters(database_url)
        with self.connect(**parameters) as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT obj_description(oid, 'pg_database') FROM pg_database WHERE datname = %s",
                [name],
            )
            row = cursor.fetchone()
            return bool(row and row[0] == marker)

    def drop_shadow(self, database_url: str, name: str) -> None:
        parameters = admin_connection_parameters(database_url)
        with (
            self.connect(**parameters, autocommit=True) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                sql.SQL("ALTER DATABASE {} WITH ALLOW_CONNECTIONS false").format(
                    sql.Identifier(name)
                )
            )
            cursor.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                [name],
            )
            cursor.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))

    def _candidate_parameters(self, database_url: str, name: str) -> dict[str, str]:
        try:
            parameters = {
                key: str(value)
                for key, value in conninfo_to_dict(database_url).items()
                if value is not None
            }
        except Exception as exc:
            raise RefreshError("target_url_invalid") from exc
        parameters["dbname"] = name
        return parameters

    def scrub_candidate(self, database_url: str, name: str) -> ScrubReport:
        parameters = self._candidate_parameters(database_url, name)
        with self.connect(**parameters) as connection, connection.cursor() as cursor:
            return scrub_candidate_data(cursor, self.policy)

    def inspect_candidate(self, database_url: str, name: str) -> CandidateCensus:
        parameters = self._candidate_parameters(database_url, name)
        with self.connect(**parameters) as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT c.relname, c.relkind FROM pg_class c "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'S', 'v')"
            )
            relations = list(cursor.fetchall())
            base_tables = frozenset(
                str(row[0]) for row in relations if row[1] in {"r", "p"}
            )
            views = frozenset(str(row[0]) for row in relations if row[1] == "v")
            sequences = frozenset(str(row[0]) for row in relations if row[1] == "S")
            cursor.execute(
                "SELECT table_name, column_name FROM information_schema.columns "
                "WHERE table_schema = 'public'"
            )
            columns: dict[str, set[str]] = {}
            for table, column in cursor.fetchall():
                columns.setdefault(str(table), set()).add(str(column))
            row_counts = {
                table: _table_count(cursor, table)
                for table in self.policy.validation.exact_count_tables
            }
            table = self.policy.validation.latest_timestamp_table
            column = self.policy.validation.latest_timestamp_column
            cursor.execute(
                sql.SQL("SELECT max({}) FROM {}").format(
                    sql.Identifier(column), sql.Identifier(table)
                )
            )
            latest_value = cursor.fetchone()[0]
            latest = {
                f"{table}.{column}": (
                    latest_value.isoformat() if latest_value else None
                )
            }
            translations = _translation_counts(cursor, self.policy)
            classifications = {
                table: _table_count(cursor, table)
                for table in self.policy.validation.classification_tables
            }
            scrubbed = {
                table: _table_count(cursor, table)
                for table in sorted(self.policy.scrub.truncate_tables)
            }
            cursor.execute(
                "SELECT count(*) FROM trend_narratives WHERE status = ANY(%s)",
                [list(self.policy.scrub.retained_narrative_statuses)],
            )
            terminal_count = int(cursor.fetchone()[0])
            cursor.execute(
                "SELECT count(*) FROM trend_narratives "
                "WHERE status = 'published' AND is_current"
            )
            current_count = int(cursor.fetchone()[0])
            cursor.execute(
                "SELECT window_days FROM trend_narratives WHERE is_current "
                "GROUP BY window_days HAVING count(*) > 1 ORDER BY window_days"
            )
            duplicates = tuple(int(row[0]) for row in cursor.fetchall())
            cursor.execute(
                "SELECT conname FROM pg_constraint c "
                "JOIN pg_namespace n ON n.oid = c.connamespace "
                "WHERE n.nspname = 'public' AND c.contype = 'f' "
                "AND NOT c.convalidated ORDER BY conname"
            )
            invalid_foreign_keys = tuple(str(row[0]) for row in cursor.fetchall())
            cursor.execute("SELECT 1 FROM trend_narrative_versions LIMIT 0")
            cursor.execute("SELECT domain, name FROM django_site WHERE id = 1")
            site_row = cursor.fetchone()
            return CandidateCensus(
                base_tables=base_tables,
                views=views,
                sequences=sequences,
                columns={table: frozenset(values) for table, values in columns.items()},
                row_counts=row_counts,
                latest_timestamps=latest,
                translation_counts=translations,
                classification_counts=classifications,
                scrubbed_counts=scrubbed,
                terminal_narrative_count=terminal_count,
                current_narrative_count=current_count,
                duplicate_current_windows=duplicates,
                invalid_foreign_keys=invalid_foreign_keys,
                view_valid=True,
                site_domain=str(site_row[0]) if site_row else "",
                site_name=str(site_row[1]) if site_row else "",
            )

    def mark_validated(
        self,
        database_url: str,
        name: str,
        marker: str,
        evidence: dict[str, object],
    ) -> str:
        prefix = f"{self.policy.lifecycle.marker_prefix}:"
        if not marker.startswith(prefix):
            raise RefreshError("candidate_marker_invalid")
        try:
            payload = json.loads(marker.removeprefix(prefix))
        except (TypeError, json.JSONDecodeError) as exc:
            raise RefreshError("candidate_marker_invalid") from exc
        if not isinstance(payload, dict) or payload.get("state") != "building":
            raise RefreshError("candidate_marker_invalid")
        payload["state"] = "validated"
        payload["validated_at"] = self.now().astimezone(UTC).isoformat()
        payload["evidence"] = evidence
        validated = prefix + json.dumps(payload, sort_keys=True, separators=(",", ":"))
        parameters = admin_connection_parameters(database_url)
        with (
            self.connect(**parameters, autocommit=True) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                "SELECT obj_description(oid, 'pg_database') "
                "FROM pg_database WHERE datname = %s",
                [name],
            )
            row = cursor.fetchone()
            if not row or row[0] != marker:
                raise RefreshError("candidate_marker_changed")
            cursor.execute(
                sql.SQL("COMMENT ON DATABASE {} IS %s").format(sql.Identifier(name)),
                [validated],
            )
        return validated


class SnapshotRestoreEngine:
    CHILD_ENVIRONMENT_ALLOWLIST = frozenset(
        {
            "PATH",
            "LANG",
            "LC_ALL",
            "TZ",
            "SYSTEMROOT",
            "PGHOST",
            "PGHOSTADDR",
            "PGPORT",
            "PGDATABASE",
            "PGUSER",
            "PGPASSWORD",
            "PGSSLMODE",
            "PGAPPNAME",
        }
    )
    _ARTIFACT_PREFIX = "staging-refresh-"
    _ARTIFACT_SUFFIX = ".dump"

    def __init__(
        self,
        *,
        policy: RefreshPolicy,
        source_url: str,
        target_url: str,
        adapter: SnapshotAdapter | None = None,
        runner: Callable[..., CommandResult] = subprocess.run,
        lock_factory: Callable[..., Any] = acquire_cluster_lock,
        executable_finder: Callable[[str], str | None] = shutil.which,
        disk_usage: Callable[[Path], Any] = shutil.disk_usage,
        temporary_root: Path | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.policy = policy
        self.source_url = source_url
        self.target_url = target_url
        self.now = now or (lambda: datetime.now(UTC))
        self.adapter = adapter or PsycopgSnapshotAdapter(policy, now=self.now)
        self.runner = runner
        self.lock_factory = lock_factory
        self.executable_finder = executable_finder
        self.disk_usage = disk_usage
        self.temporary_root = temporary_root or (
            policy.path.parents[1] / ".staging-refresh"
        )
        self._target_lock_depth = 0
        self._executables: dict[str, str] = {}

    @property
    def project_root(self) -> Path:
        return self.policy.path.parents[1]

    def _run(
        self, command: list[str], *, environment: Mapping[str, str]
    ) -> CommandResult:
        try:
            return self.runner(
                command,
                cwd=self.project_root,
                env=dict(environment),
                text=True,
                capture_output=True,
                timeout=60 * 30,
                check=False,
            )
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            raise RefreshError("subprocess_failed") from exc

    def _verify_clients(self) -> None:
        for name in ("pg_dump", "pg_restore"):
            executable = self.executable_finder(name)
            if not executable:
                raise RefreshError(f"{name}_unavailable")
            result = self._run([executable, "--version"], environment={})
            match = re.search(r"PostgreSQL\)\s+(\d+)", result.stdout)
            if result.returncode != 0 or not match:
                raise RefreshError("postgres_client_version_unknown")
            if int(match.group(1)) < 18:
                raise RefreshError("postgres_client_version_unsupported")
            self._executables[name] = executable

    def _prepare_temporary_root(self) -> None:
        self.temporary_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.temporary_root.chmod(0o700)

    def cleanup_stale_artifacts(self) -> None:
        if not self.temporary_root.exists():
            return
        cutoff = self.now().timestamp() - timedelta(hours=24).total_seconds()
        for artifact in self.temporary_root.glob(
            f"{self._ARTIFACT_PREFIX}*{self._ARTIFACT_SUFFIX}"
        ):
            if artifact.is_file() and artifact.stat().st_mtime < cutoff:
                artifact.unlink()

    def _new_artifact_path(self) -> Path:
        self._prepare_temporary_root()
        descriptor, value = tempfile.mkstemp(
            prefix=self._ARTIFACT_PREFIX,
            suffix=self._ARTIFACT_SUFFIX,
            dir=self.temporary_root,
        )
        os.close(descriptor)
        path = Path(value)
        path.chmod(0o600)
        return path

    def _guard_local_space(self, source_bytes: int) -> None:
        self._prepare_temporary_root()
        required = int(source_bytes * self.policy.storage.local_free_space_multiplier)
        if int(self.disk_usage(self.temporary_root).free) < required:
            raise RefreshError("local_space_insufficient")

    def export_dump(self) -> DumpArtifact:
        self.cleanup_stale_artifacts()
        self._verify_clients()
        environment = _libpq_environment(self.source_url, require_tls=True)
        artifact_path: Path | None = None
        try:
            with (
                self.lock_factory(
                    self.source_url,
                    wait_seconds=0,
                    lock_id=self.policy.lifecycle.cluster_lock_id,
                ),
                self.adapter.exported_snapshot(self.source_url) as census,
            ):
                self._guard_local_space(census.database_bytes)
                artifact_path = self._new_artifact_path()
                command = [
                    self._executables["pg_dump"],
                    "--format=custom",
                    "--no-owner",
                    "--no-privileges",
                    f"--snapshot={census.snapshot_id}",
                    *(
                        f"--exclude-table-data=public.{table}"
                        for table in sorted(self.policy.relations.excluded_tables)
                    ),
                    "--file",
                    str(artifact_path),
                ]
                result = self._run(command, environment=environment)
                if result.returncode != 0:
                    raise RefreshError("pg_dump_failed")
                mode = stat.S_IMODE(artifact_path.stat().st_mode)
                if mode != 0o600:
                    raise RefreshError("dump_permissions_invalid")
                checksum = _file_sha256(artifact_path)
                byte_size = artifact_path.stat().st_size
                if byte_size <= 0:
                    raise RefreshError("dump_empty")
                return DumpArtifact(
                    path=artifact_path,
                    checksum=checksum,
                    byte_size=byte_size,
                    source=census,
                )
        except BaseException:
            if artifact_path is not None and artifact_path.exists():
                artifact_path.unlink()
            raise

    @contextmanager
    def target_lock(self) -> Iterator[None]:
        with self.lock_factory(
            self.target_url,
            wait_seconds=0,
            lock_id=self.policy.lifecycle.cluster_lock_id,
        ):
            self._target_lock_depth += 1
            try:
                yield
            finally:
                self._target_lock_depth -= 1

    def _guard_target_capacity(self, source_bytes: int) -> None:
        current = self.adapter.target_database_bytes(self.target_url)
        usable = int(
            self.policy.storage.target_disk_bytes
            * (1 - self.policy.storage.required_reserve_ratio)
        )
        if current + source_bytes > usable:
            raise RefreshError("target_capacity_insufficient")

    def _shadow_name(self) -> str:
        suffix = self.now().astimezone(UTC).strftime("%Y%m%dt%H%M%Sz").lower()
        name = f"{self.policy.lifecycle.shadow_prefix}{suffix}"
        if len(name) > 63:
            raise RefreshError("shadow_name_too_long")
        return name

    def _shadow_marker(self, name: str, artifact: DumpArtifact) -> str:
        payload = {
            "created_at": self.now().astimezone(UTC).isoformat(),
            "database": name,
            "source_resource_id": self.policy.source.resource_id,
            "state": "building",
            "checksum": artifact.checksum,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return f"{self.policy.lifecycle.marker_prefix}:{encoded}"

    def restore_shadow(self, artifact: DumpArtifact) -> ShadowCandidate:
        if self._target_lock_depth <= 0:
            raise RefreshError("target_lock_required")
        if (
            not self._owned_artifact(artifact.path)
            or _file_sha256(artifact.path) != artifact.checksum
        ):
            raise RefreshError("dump_checksum_mismatch")
        self._guard_target_capacity(artifact.source.database_bytes)
        name = self._shadow_name()
        marker = self._shadow_marker(name, artifact)
        created = False
        try:
            self.adapter.create_shadow(self.target_url, name, marker)
            created = True
            environment = _libpq_environment(
                self.target_url,
                database=name,
                require_tls=False,
            )
            command = [
                self._executables["pg_restore"],
                "--exit-on-error",
                "--no-owner",
                "--no-privileges",
                "--jobs=1",
                "--dbname",
                name,
                str(artifact.path),
            ]
            result = self._run(command, environment=environment)
            if result.returncode != 0:
                raise RefreshError("pg_restore_failed")
            return ShadowCandidate(name=name, marker=marker, artifact=artifact)
        except BaseException:
            if created:
                self.cleanup_shadow(name, marker)
            raise

    def cleanup_shadow(self, name: str, marker: str) -> None:
        if (
            self._target_lock_depth <= 0
            or not name.startswith(self.policy.lifecycle.shadow_prefix)
            or name == self.policy.target.database
        ):
            raise RefreshError("shadow_cleanup_refused")
        if not self.adapter.marker_matches(self.target_url, name, marker):
            raise RefreshError("shadow_cleanup_refused")
        self.adapter.drop_shadow(self.target_url, name)

    def _owned_artifact(self, path: Path) -> bool:
        try:
            resolved = path.resolve(strict=False)
            root = self.temporary_root.resolve(strict=False)
        except OSError:
            return False
        return (
            resolved.parent == root
            and resolved.name.startswith(self._ARTIFACT_PREFIX)
            and resolved.name.endswith(self._ARTIFACT_SUFFIX)
        )

    def cleanup_artifact(self, artifact: DumpArtifact) -> None:
        if not self._owned_artifact(artifact.path):
            raise RefreshError("artifact_cleanup_refused")
        artifact.path.unlink(missing_ok=True)


def _django_database_url(database_url: str, database: str) -> str:
    try:
        parsed = urlsplit(database_url)
        if parsed.scheme not in {"postgres", "postgresql"} or not parsed.netloc:
            raise ValueError
    except ValueError as exc:
        raise RefreshError("target_url_invalid") from exc
    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            f"/{quote(database, safe='')}",
            parsed.query,
            "",
        )
    )


class CandidateProcessor:
    """Migrate, scrub, validate, and mark one non-serving shadow database."""

    def __init__(
        self,
        *,
        policy: RefreshPolicy,
        target_url: str,
        adapter: SnapshotAdapter,
        runner: Callable[..., CommandResult] = subprocess.run,
        python: str = sys.executable,
    ) -> None:
        self.policy = policy
        self.target_url = target_url
        self.adapter = adapter
        self.runner = runner
        self.python = python

    @property
    def project_root(self) -> Path:
        return self.policy.path.parents[1]

    def _django_environment(self, database: str) -> dict[str, str]:
        environment = {
            key: os.environ[key]
            for key in ("PATH", "LANG", "LC_ALL", "TZ", "SYSTEMROOT")
            if key in os.environ
        }
        environment.update(
            {
                "DATABASE_URL": _django_database_url(self.target_url, database),
                "DJANGO_SETTINGS_MODULE": "project.settings",
                "DEBUG": "False",
                "OLLIJA_STAGING_MODE": "False",
                "XMONITOR_DRY_RUN": "True",
                "X_MONITOR_HEADLINE_SERVING_ENABLED": "False",
                "X_MONITOR_HEADLINE_ENQUEUE_ENABLED": "False",
                "X_MONITOR_HEADLINE_PROVIDER_CALLS_ENABLED": "False",
            }
        )
        return environment

    def _run_django(self, database: str, *arguments: str) -> None:
        command = [self.python, "manage.py", *arguments]
        try:
            result = self.runner(
                command,
                cwd=self.project_root,
                env=self._django_environment(database),
                text=True,
                capture_output=True,
                timeout=60 * 30,
                check=False,
            )
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            raise RefreshError("candidate_django_command_failed") from exc
        if result.returncode != 0:
            if arguments == ("migrate", "--check"):
                raise RefreshError("candidate_migrations_pending")
            if arguments and arguments[0] == "migrate":
                raise RefreshError("candidate_migration_failed")
            raise RefreshError("candidate_django_check_failed")

    def _validate(self, candidate: ShadowCandidate, census: CandidateCensus) -> None:
        source = candidate.artifact.source
        if census.base_tables != self.policy.relations.classified_tables:
            raise RefreshError("candidate_table_policy_mismatch")
        if census.views != self.policy.relations.views or not census.view_valid:
            raise RefreshError("candidate_view_invalid")
        if census.sequences != self.policy.relations.sequences:
            raise RefreshError("candidate_sequence_policy_mismatch")
        for table, required in self.policy.validation.required_columns.items():
            missing = required - census.columns.get(table, frozenset())
            if missing:
                raise RefreshError(f"candidate_column_missing:{table}.{min(missing)}")
        for table, expected in source.row_counts.items():
            if census.row_counts.get(table) != expected:
                raise RefreshError(f"candidate_count_mismatch:{table}")
        for table in self.policy.validation.required_nonempty_tables:
            if census.row_counts.get(table, 0) <= 0:
                raise RefreshError(f"candidate_required_table_empty:{table}")
        for key, expected in source.translation_counts.items():
            if census.translation_counts.get(key) != expected:
                raise RefreshError(f"candidate_translation_mismatch:{key}")
        for table, expected in source.classification_counts.items():
            if census.classification_counts.get(table) != expected:
                raise RefreshError(f"candidate_classification_mismatch:{table}")
        for key, expected in source.latest_timestamps.items():
            actual = census.latest_timestamps.get(key)
            if actual is None or expected is None:
                if actual != expected:
                    raise RefreshError(f"candidate_latest_timestamp_mismatch:{key}")
                continue
            difference = abs(
                (
                    datetime.fromisoformat(actual) - datetime.fromisoformat(expected)
                ).total_seconds()
            )
            if difference > self.policy.validation.maximum_latest_timestamp_lag_seconds:
                raise RefreshError(f"candidate_latest_timestamp_mismatch:{key}")
        incomplete = [
            table for table, count in census.scrubbed_counts.items() if count != 0
        ]
        if incomplete:
            raise RefreshError(f"candidate_scrub_incomplete:{min(incomplete)}")
        if census.terminal_narrative_count != source.terminal_narrative_count:
            raise RefreshError("candidate_terminal_narrative_mismatch")
        if census.current_narrative_count != source.current_narrative_count:
            raise RefreshError("candidate_current_narrative_mismatch")
        if census.duplicate_current_windows:
            raise RefreshError(
                "candidate_current_narrative_duplicate:"
                f"{census.duplicate_current_windows[0]}"
            )
        if census.invalid_foreign_keys:
            raise RefreshError(
                f"candidate_foreign_key_invalid:{census.invalid_foreign_keys[0]}"
            )
        if census.site_domain != self.policy.scrub.site_domain:
            raise RefreshError("candidate_site_invalid")
        if census.site_name != self.policy.scrub.site_name:
            raise RefreshError("candidate_site_invalid")

    def process(self, candidate: ShadowCandidate) -> CandidateResult:
        self._run_django(candidate.name, "migrate", "--noinput")
        self._run_django(candidate.name, "check", "--deploy")
        self._run_django(candidate.name, "migrate", "--check")
        scrub = self.adapter.scrub_candidate(self.target_url, candidate.name)
        census = self.adapter.inspect_candidate(self.target_url, candidate.name)
        self._validate(candidate, census)
        evidence: dict[str, object] = {
            "validation": "passed",
            "row_counts": dict(census.row_counts),
            "scrubbed_counts": dict(census.scrubbed_counts),
            "terminal_narratives": census.terminal_narrative_count,
        }
        marker = self.adapter.mark_validated(
            self.target_url,
            candidate.name,
            candidate.marker,
            evidence,
        )
        return CandidateResult(
            candidate=replace(candidate, marker=marker),
            scrub=scrub,
            census=census,
        )


class PostgresRuntime:
    """PostgreSQL inspection boundary and lifecycle command runtime."""

    def __init__(
        self,
        policy: RefreshPolicy,
        *,
        source_url: str | None = None,
        target_url: str | None = None,
    ) -> None:
        self.policy = policy
        self.source_url = source_url
        self.target_url = target_url
        self.engine = (
            SnapshotRestoreEngine(
                policy=policy,
                source_url=source_url,
                target_url=target_url,
            )
            if source_url and target_url
            else None
        )
        if self.engine is not None:
            self.engine.cleanup_stale_artifacts()

    @staticmethod
    def _inspect(url: str) -> DatabaseInspection:
        with psycopg.connect(url) as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT current_database(), session_user, "
                "current_setting('server_version_num')::integer, "
                "current_setting('default_transaction_read_only')::boolean, "
                "r.rolcreatedb, "
                "r.rolsuper OR r.rolcreaterole OR r.rolreplication OR r.rolbypassrls "
                "FROM pg_roles r WHERE r.rolname = session_user"
            )
            database, role, version, read_only, can_create, elevated = cursor.fetchone()
            cursor.execute(
                "SELECT EXISTS ("
                "SELECT 1 FROM pg_stat_ssl WHERE pid = pg_backend_pid() AND ssl"
                ")"
            )
            tls = bool(cursor.fetchone()[0])
            cursor.execute(
                "SELECT c.relname, c.relkind, "
                "CASE WHEN c.relkind IN ('r', 'p') THEN "
                "has_table_privilege(current_user, c.oid, 'SELECT') ELSE FALSE END, "
                "CASE WHEN c.relkind = 'S' THEN "
                "has_sequence_privilege(current_user, c.oid, 'SELECT') ELSE FALSE END, "
                "CASE WHEN c.relkind IN ('r', 'p') THEN "
                "has_table_privilege(current_user, c.oid, 'INSERT,UPDATE,DELETE,TRUNCATE') "
                "ELSE FALSE END "
                "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'S', 'v')"
            )
            rows: list[tuple[Any, ...]] = cursor.fetchall()
            cursor.execute(
                "SELECT has_schema_privilege(current_user, 'public', 'CREATE')"
            )
            schema_write = bool(cursor.fetchone()[0])

        base_tables = frozenset(str(row[0]) for row in rows if row[1] in {"r", "p"})
        views = frozenset(str(row[0]) for row in rows if row[1] == "v")
        sequences = frozenset(str(row[0]) for row in rows if row[1] == "S")
        readable_tables = frozenset(
            str(row[0]) for row in rows if row[1] in {"r", "p"} and row[2]
        )
        readable_sequences = frozenset(
            str(row[0]) for row in rows if row[1] == "S" and row[3]
        )
        table_write = any(bool(row[4]) for row in rows)
        return DatabaseInspection(
            database=str(database),
            role=str(role),
            server_version=int(version),
            tls=tls,
            default_transaction_read_only=bool(read_only),
            has_write_privileges=bool(elevated) or schema_write or table_write,
            can_create_database=bool(can_create),
            readable_tables=readable_tables,
            readable_sequences=readable_sequences,
            base_tables=base_tables,
            views=views,
            sequences=sequences,
        )

    def inspect_source(self, url: str) -> DatabaseInspection:
        return self._inspect(url)

    def inspect_target(self, url: str) -> DatabaseInspection:
        return self._inspect(url)

    def execute(self, action: str, *, recovery: str | None = None) -> dict[str, str]:
        raise RuntimeError("lifecycle_not_implemented")
