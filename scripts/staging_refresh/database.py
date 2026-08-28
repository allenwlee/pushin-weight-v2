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
import time
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

from scripts.database_lock import (
    acquire_cluster_lock,
    acquire_harvest_coordination_lock,
    admin_connection_parameters,
)

from .policy import DatabaseInspection, RefreshPolicy, expected_confirmation
from .receipt import (
    DatabaseComment,
    Receipt,
    ReceiptError,
    decode_database_comment,
    encode_database_comment,
)


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


@dataclass(frozen=True, slots=True)
class DatabaseState:
    name: str
    allow_connections: bool
    comment: str | None


@dataclass(frozen=True, slots=True)
class QuiescenceInspection:
    worker_nodes: tuple[str, ...]
    queue_depth: int
    unacked_count: int
    unacked_index_count: int = 0
    namespace_keys: tuple[str, ...] = ()
    envelope_present: bool = False


def inspect_staging_quiescence(
    policy: RefreshPolicy,
    broker_url: str | None,
    *,
    redis_factory=None,
    celery_factory=None,
) -> QuiescenceInspection:
    """Inspect the owned staging broker without exposing its connection URL."""

    if not broker_url:
        raise RefreshError("staging_broker_url_missing")
    if redis_factory is None:
        import redis

        redis_factory = redis.Redis.from_url
    if celery_factory is None:
        from celery import Celery

        celery_factory = Celery

    try:
        client = redis_factory(
            broker_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        client.ping()
        queue_depth = int(client.llen(policy.quiescence.queue_name))
        unacked_count = int(client.hlen(policy.quiescence.unacked_key))
        unacked_index_count = int(client.zcard(policy.quiescence.unacked_index_key))
        namespace_keys = tuple(
            sorted(
                str(key)
                for key in client.scan_iter(
                    match=policy.quiescence.queue_namespace_pattern
                )
                if str(key) != policy.quiescence.queue_name
            )
        )
        envelope_present = bool(client.exists(policy.quiescence.envelope_key))
    except Exception as exc:
        raise RefreshError("staging_broker_state_unavailable") from exc

    try:
        app = celery_factory("staging-refresh-quiescence", broker=broker_url)
        inspector = app.control.inspect(
            timeout=policy.quiescence.worker_probe_timeout_seconds
        )
        responses = inspector.ping() or {}
        worker_nodes = tuple(sorted(str(name) for name in responses))
    except Exception as exc:
        raise RefreshError("staging_worker_state_unavailable") from exc

    return QuiescenceInspection(
        worker_nodes=worker_nodes,
        queue_depth=queue_depth,
        unacked_count=unacked_count,
        unacked_index_count=unacked_index_count,
        namespace_keys=namespace_keys,
        envelope_present=envelope_present,
    )


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

    def database_state(self, database_url: str, name: str) -> DatabaseState | None: ...

    def database_states(
        self, database_url: str, prefix: str
    ) -> tuple[DatabaseState, ...]: ...

    def set_allow_connections(
        self, database_url: str, name: str, allowed: bool
    ) -> None: ...

    def terminate_connections(self, database_url: str, name: str) -> None: ...

    def rename_database(self, database_url: str, old: str, new: str) -> None: ...

    def write_receipt_comments(
        self,
        database_url: str,
        active_name: str,
        active_comment: str,
        recovery_name: str,
        recovery_comment: str,
    ) -> None: ...

    def drop_recovery(self, database_url: str, name: str) -> None: ...


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
        "DELETE FROM trend_narrative_subjects "
        "WHERE trend_narrative_id IN ("
        "SELECT id FROM trend_narratives WHERE NOT (status = ANY(%s))"
        ")",
        [list(policy.scrub.retained_narrative_statuses)],
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
                sql.SQL("COMMENT ON DATABASE {} IS {}").format(
                    sql.Identifier(name), sql.Literal(marker)
                )
            )

    def marker_matches(self, database_url: str, name: str, marker: str) -> bool:
        parameters = admin_connection_parameters(database_url)
        with self.connect(**parameters) as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT shobj_description(oid, 'pg_database') "
                "FROM pg_database WHERE datname = %s",
                [name],
            )
            row = cursor.fetchone()
            return bool(row and row[0] == marker)

    def drop_shadow(self, database_url: str, name: str) -> None:
        self.set_allow_connections(database_url, name, False)
        self.terminate_connections(database_url, name)
        self._administration(
            database_url,
            sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)),
        )

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
                "SELECT shobj_description(oid, 'pg_database') "
                "FROM pg_database WHERE datname = %s",
                [name],
            )
            row = cursor.fetchone()
            if not row or row[0] != marker:
                raise RefreshError("candidate_marker_changed")
            cursor.execute(
                sql.SQL("COMMENT ON DATABASE {} IS {}").format(
                    sql.Identifier(name), sql.Literal(validated)
                )
            )
        return validated

    def database_state(self, database_url: str, name: str) -> DatabaseState | None:
        parameters = admin_connection_parameters(database_url)
        with self.connect(**parameters) as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT datname, datallowconn, "
                "shobj_description(oid, 'pg_database') "
                "FROM pg_database WHERE datname = %s",
                [name],
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return DatabaseState(
            name=str(row[0]), allow_connections=bool(row[1]), comment=row[2]
        )

    def database_states(
        self, database_url: str, prefix: str
    ) -> tuple[DatabaseState, ...]:
        parameters = admin_connection_parameters(database_url)
        with self.connect(**parameters) as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT datname, datallowconn, "
                "shobj_description(oid, 'pg_database') "
                "FROM pg_database WHERE starts_with(datname, %s) ORDER BY datname",
                [prefix],
            )
            rows = cursor.fetchall()
        return tuple(
            DatabaseState(
                name=str(row[0]), allow_connections=bool(row[1]), comment=row[2]
            )
            for row in rows
        )

    def _administration(self, database_url: str, statement: Any) -> None:
        parameters = admin_connection_parameters(database_url)
        timeout = str(
            self.policy.lifecycle.administration_statement_timeout_seconds * 1000
        )
        with (
            self.connect(**parameters, autocommit=True) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                "SELECT set_config('statement_timeout', %s, false)", [timeout]
            )
            cursor.execute(statement)

    def set_allow_connections(
        self, database_url: str, name: str, allowed: bool
    ) -> None:
        self._administration(
            database_url,
            sql.SQL("ALTER DATABASE {} WITH ALLOW_CONNECTIONS {}").format(
                sql.Identifier(name), sql.SQL("true" if allowed else "false")
            ),
        )

    def terminate_connections(self, database_url: str, name: str) -> None:
        parameters = admin_connection_parameters(database_url)
        timeout = str(
            self.policy.lifecycle.administration_statement_timeout_seconds * 1000
        )
        with (
            self.connect(**parameters, autocommit=True) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                "SELECT set_config('statement_timeout', %s, false)", [timeout]
            )
            cursor.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid() "
                "AND usename = current_user",
                [name],
            )
            deadline = (
                time.monotonic()
                + self.policy.lifecycle.administration_statement_timeout_seconds
            )
            while True:
                cursor.execute(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE datname = %s AND pid <> pg_backend_pid()",
                    [name],
                )
                if int(cursor.fetchone()[0]) == 0:
                    return
                if time.monotonic() >= deadline:
                    raise RefreshError("database_connections_remain")
                time.sleep(0.1)

    def rename_database(self, database_url: str, old: str, new: str) -> None:
        self._administration(
            database_url,
            sql.SQL("ALTER DATABASE {} RENAME TO {}").format(
                sql.Identifier(old), sql.Identifier(new)
            ),
        )

    def write_receipt_comments(
        self,
        database_url: str,
        active_name: str,
        active_comment: str,
        recovery_name: str,
        recovery_comment: str,
    ) -> None:
        parameters = admin_connection_parameters(database_url)
        timeout = str(
            self.policy.lifecycle.administration_statement_timeout_seconds * 1000
        )
        with self.connect(**parameters) as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT set_config('statement_timeout', %s, true)", [timeout]
            )
            cursor.execute(
                sql.SQL("COMMENT ON DATABASE {} IS {}").format(
                    sql.Identifier(active_name), sql.Literal(active_comment)
                )
            )
            cursor.execute(
                sql.SQL("COMMENT ON DATABASE {} IS {}").format(
                    sql.Identifier(recovery_name), sql.Literal(recovery_comment)
                )
            )

    def drop_recovery(self, database_url: str, name: str) -> None:
        self.drop_shadow(database_url, name)


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

    def preflight(self) -> SourceCensus:
        self.cleanup_stale_artifacts()
        self._verify_clients()
        with (
            self.lock_factory(
                self.source_url,
                wait_seconds=0,
                lock_id=self.policy.lifecycle.cluster_lock_id,
            ),
            self.adapter.exported_snapshot(self.source_url) as census,
        ):
            self._guard_local_space(census.database_bytes)
        with self.target_lock():
            self._guard_target_capacity(census.database_bytes)
        return census

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

    def validate(self, candidate: ShadowCandidate, census: CandidateCensus) -> None:
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
        self.validate(candidate, census)
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


class LifecycleManager:
    """Guard canonical/recovery database name transitions and durable receipts."""

    def __init__(
        self,
        *,
        policy: RefreshPolicy,
        target_url: str,
        adapter: SnapshotAdapter,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.policy = policy
        self.target_url = target_url
        self.adapter = adapter
        self.now = now or (lambda: datetime.now(UTC))

    @property
    def canonical(self) -> str:
        return self.policy.target.database

    def _recovery_name(self) -> str:
        suffix = self.now().astimezone(UTC).strftime("%Y%m%dt%H%M%Sz").lower()
        name = f"{self.policy.lifecycle.recovery_prefix}{suffix}"
        if len(name) > 63:
            raise RefreshError("recovery_name_too_long")
        return name

    def _state(self, name: str, *, missing: str) -> DatabaseState:
        state = self.adapter.database_state(self.target_url, name)
        if state is None:
            raise RefreshError(missing)
        return state

    def _receipt(
        self,
        *,
        action: str,
        recovery: str,
        result: CandidateResult | None = None,
        prior: Receipt | None = None,
        census: CandidateCensus | None = None,
    ) -> Receipt:
        if result is not None:
            source = result.candidate.artifact.source
            payload: dict[str, object] = {
                "version": 1,
                "action": action,
                "completed_at": self.now().astimezone(UTC).isoformat(),
                "source_resource_id": self.policy.source.resource_id,
                "source_database": self.policy.source.database,
                "target_resource_id": self.policy.target.resource_id,
                "canonical_database": self.canonical,
                "recovery_database": recovery,
                "snapshot_at": source.captured_at.astimezone(UTC).isoformat(),
                "dump_checksum": result.candidate.artifact.checksum,
                "dump_bytes": result.candidate.artifact.byte_size,
                "source_counts": dict(source.row_counts),
                "candidate_counts": dict(result.census.row_counts),
                "translation_counts": dict(result.census.translation_counts),
                "classification_counts": dict(result.census.classification_counts),
                "scrubbed_rows": dict(result.scrub.cleared_rows),
                "latest_timestamps": dict(result.census.latest_timestamps),
                "terminal_narrative_count": result.census.terminal_narrative_count,
                "current_narrative_count": result.census.current_narrative_count,
                "rollback_confirmation": expected_confirmation(
                    self.policy, "rollback", recovery=recovery
                ),
            }
        elif prior is not None:
            payload = prior.to_payload()
            payload.update(
                {
                    "action": action,
                    "completed_at": self.now().astimezone(UTC).isoformat(),
                    "recovery_database": recovery,
                    "rollback_confirmation": expected_confirmation(
                        self.policy, "rollback", recovery=recovery
                    ),
                }
            )
            if census is not None:
                payload["candidate_counts"] = dict(census.row_counts)
                payload["translation_counts"] = dict(census.translation_counts)
                payload["classification_counts"] = dict(census.classification_counts)
                payload["latest_timestamps"] = dict(census.latest_timestamps)
                payload["terminal_narrative_count"] = census.terminal_narrative_count
                payload["current_narrative_count"] = census.current_narrative_count
        else:  # pragma: no cover - internal call contract
            raise RefreshError("receipt_input_missing")
        try:
            return Receipt.from_payload(payload)
        except ReceiptError as exc:
            raise RefreshError("receipt_invalid") from exc

    def _write_receipt(self, receipt: Receipt) -> None:
        self.adapter.write_receipt_comments(
            self.target_url,
            self.canonical,
            encode_database_comment(
                marker_prefix=self.policy.lifecycle.marker_prefix,
                state="active",
                database=self.canonical,
                receipt=receipt,
            ),
            receipt.recovery_database,
            encode_database_comment(
                marker_prefix=self.policy.lifecycle.marker_prefix,
                state="recovery",
                database=receipt.recovery_database,
                receipt=receipt,
            ),
        )

    def _diagnostic(self, *names: str) -> str:
        values = []
        for name in names:
            state = self.adapter.database_state(self.target_url, name)
            if state is None:
                values.append(f"{name}=absent")
            else:
                enabled = "enabled" if state.allow_connections else "disabled"
                values.append(f"{name}={enabled}")
        return ";".join(values)

    def _repair_swap(
        self,
        *,
        incoming: str,
        displaced: str,
        failure_code: str,
    ) -> None:
        try:
            canonical = self.adapter.database_state(self.target_url, self.canonical)
            incoming_state = self.adapter.database_state(self.target_url, incoming)
            displaced_state = self.adapter.database_state(self.target_url, displaced)

            if canonical is not None and incoming_state is None and displaced_state:
                self.adapter.set_allow_connections(
                    self.target_url, self.canonical, False
                )
                self.adapter.terminate_connections(self.target_url, self.canonical)
                self.adapter.rename_database(self.target_url, self.canonical, incoming)
                canonical = None
            if canonical is None and displaced_state is not None:
                self.adapter.rename_database(self.target_url, displaced, self.canonical)

            canonical = self.adapter.database_state(self.target_url, self.canonical)
            incoming_state = self.adapter.database_state(self.target_url, incoming)
            displaced_state = self.adapter.database_state(self.target_url, displaced)
            if (
                canonical is None
                or incoming_state is None
                or displaced_state is not None
            ):
                raise RefreshError("repair_state_invalid")
            if incoming_state.allow_connections:
                self.adapter.set_allow_connections(self.target_url, incoming, False)
                self.adapter.terminate_connections(self.target_url, incoming)
            self.adapter.set_allow_connections(self.target_url, self.canonical, True)
        except BaseException as exc:
            detail = self._diagnostic(self.canonical, incoming, displaced)
            raise RefreshError(
                f"{failure_code}_manual_recovery_required:{detail}"
            ) from exc
        raise RefreshError(f"{failure_code}_failed_repaired")

    def _swap(
        self,
        *,
        incoming: str,
        displaced: str,
        prepare_receipt: Callable[[], Receipt],
        failure_code: str,
    ) -> Receipt:
        try:
            self.adapter.set_allow_connections(self.target_url, incoming, False)
            self.adapter.terminate_connections(self.target_url, incoming)
            self.adapter.set_allow_connections(self.target_url, self.canonical, False)
            self.adapter.terminate_connections(self.target_url, self.canonical)
            self.adapter.rename_database(self.target_url, self.canonical, displaced)
            self.adapter.rename_database(self.target_url, incoming, self.canonical)
            self.adapter.set_allow_connections(self.target_url, self.canonical, True)
            receipt = prepare_receipt()
            self._write_receipt(receipt)
        except BaseException:  # noqa: BLE001 - every cutover failure must reconcile
            self._repair_swap(
                incoming=incoming,
                displaced=displaced,
                failure_code=failure_code,
            )
        return receipt

    def activate(self, result: CandidateResult) -> Receipt:
        candidate = result.candidate
        canonical = self._state(self.canonical, missing="canonical_database_missing")
        candidate_state = self._state(
            candidate.name, missing="candidate_database_missing"
        )
        recovery = self._recovery_name()
        if not canonical.allow_connections:
            raise RefreshError("canonical_database_disabled")
        if (
            not candidate.name.startswith(self.policy.lifecycle.shadow_prefix)
            or candidate.name == self.canonical
        ):
            raise RefreshError("candidate_name_invalid")
        if candidate_state.comment != candidate.marker:
            raise RefreshError("candidate_marker_changed")
        marker_prefix = f"{self.policy.lifecycle.marker_prefix}:"
        if not candidate.marker.startswith(marker_prefix):
            raise RefreshError("candidate_marker_invalid")
        try:
            marker = json.loads(candidate.marker.removeprefix(marker_prefix))
        except (TypeError, json.JSONDecodeError) as exc:
            raise RefreshError("candidate_marker_invalid") from exc
        if (
            not isinstance(marker, dict)
            or marker.get("state") != "validated"
            or marker.get("database") != candidate.name
            or marker.get("checksum") != candidate.artifact.checksum
        ):
            raise RefreshError("candidate_marker_invalid")
        if self.adapter.database_state(self.target_url, recovery) is not None:
            raise RefreshError("recovery_database_already_exists")

        receipt = self._receipt(action="refresh", recovery=recovery, result=result)

        def prepare_receipt() -> Receipt:
            census = self.adapter.inspect_candidate(self.target_url, self.canonical)
            CandidateProcessor(
                policy=self.policy,
                target_url=self.target_url,
                adapter=self.adapter,
            ).validate(candidate, census)
            return receipt

        return self._swap(
            incoming=candidate.name,
            displaced=recovery,
            prepare_receipt=prepare_receipt,
            failure_code="activation",
        )

    def _decode_state(
        self, state: DatabaseState, *, expected_state: str, invalid: str
    ) -> DatabaseComment:
        try:
            record = decode_database_comment(
                state.comment,
                marker_prefix=self.policy.lifecycle.marker_prefix,
            )
        except ReceiptError as exc:
            raise RefreshError(invalid) from exc
        if record.state != expected_state or record.database != state.name:
            raise RefreshError(invalid)
        receipt = record.receipt
        if (
            receipt.source_resource_id != self.policy.source.resource_id
            or receipt.source_database != self.policy.source.database
            or receipt.target_resource_id != self.policy.target.resource_id
            or receipt.canonical_database != self.canonical
        ):
            raise RefreshError("receipt_identity_mismatch")
        return record

    def _verify_shape(self, census: CandidateCensus) -> None:
        if census.base_tables != self.policy.relations.classified_tables:
            raise RefreshError("active_table_policy_mismatch")
        if census.views != self.policy.relations.views or not census.view_valid:
            raise RefreshError("active_view_invalid")
        if census.sequences != self.policy.relations.sequences:
            raise RefreshError("active_sequence_policy_mismatch")
        for table, required in self.policy.validation.required_columns.items():
            if required - census.columns.get(table, frozenset()):
                raise RefreshError(f"active_column_missing:{table}")
        for table in self.policy.validation.required_nonempty_tables:
            if census.row_counts.get(table, 0) <= 0:
                raise RefreshError(f"active_required_table_empty:{table}")
        if census.duplicate_current_windows or census.invalid_foreign_keys:
            raise RefreshError("active_relational_invariant_invalid")
        if (
            census.site_domain != self.policy.scrub.site_domain
            or census.site_name != self.policy.scrub.site_name
        ):
            raise RefreshError("active_site_invalid")

    def _verify_census(self, receipt: Receipt, census: CandidateCensus) -> None:
        self._verify_shape(census)
        if dict(census.row_counts) != dict(receipt.candidate_counts):
            raise RefreshError("active_count_mismatch")
        if dict(census.latest_timestamps) != dict(receipt.latest_timestamps):
            raise RefreshError("active_latest_timestamp_mismatch")
        if dict(census.translation_counts) != dict(receipt.translation_counts):
            raise RefreshError("active_translation_mismatch")
        if dict(census.classification_counts) != dict(receipt.classification_counts):
            raise RefreshError("active_classification_mismatch")
        if census.terminal_narrative_count != receipt.terminal_narrative_count:
            raise RefreshError("active_terminal_narrative_mismatch")
        if census.current_narrative_count != receipt.current_narrative_count:
            raise RefreshError("active_current_narrative_mismatch")
        if receipt.action == "refresh" and any(census.scrubbed_counts.values()):
            raise RefreshError("active_scrub_incomplete")

    def verify(self) -> Receipt:
        canonical = self._state(self.canonical, missing="canonical_database_missing")
        if not canonical.allow_connections:
            raise RefreshError("canonical_database_disabled")
        active = self._decode_state(
            canonical, expected_state="active", invalid="active_marker_invalid"
        )
        receipt = active.receipt
        if receipt.canonical_database != self.canonical:
            raise RefreshError("active_receipt_invalid")
        recovery = self._state(
            receipt.recovery_database, missing="recovery_database_missing"
        )
        if recovery.allow_connections:
            raise RefreshError("recovery_database_enabled")
        recovery_record = self._decode_state(
            recovery, expected_state="recovery", invalid="recovery_marker_invalid"
        )
        if recovery_record.receipt != receipt:
            raise RefreshError("receipt_pair_mismatch")
        census = self.adapter.inspect_candidate(self.target_url, self.canonical)
        self._verify_census(receipt, census)
        return receipt

    def rollback(self, recovery: str) -> Receipt:
        expected_confirmation(self.policy, "rollback", recovery=recovery)
        canonical = self._state(self.canonical, missing="canonical_database_missing")
        recovery_state = self._state(recovery, missing="recovery_database_missing")
        if not canonical.allow_connections:
            raise RefreshError("canonical_database_disabled")
        if recovery_state.allow_connections:
            raise RefreshError("recovery_database_enabled")
        active = self._decode_state(
            canonical, expected_state="active", invalid="active_marker_invalid"
        )
        marked_recovery = self._decode_state(
            recovery_state,
            expected_state="recovery",
            invalid="recovery_marker_invalid",
        )
        if (
            active.receipt != marked_recovery.receipt
            or active.receipt.recovery_database != recovery
        ):
            raise RefreshError("recovery_receipt_mismatch")
        displaced = self._recovery_name()
        if displaced == recovery:
            raise RefreshError("recovery_name_collision")
        if self.adapter.database_state(self.target_url, displaced) is not None:
            raise RefreshError("recovery_database_already_exists")

        def prepare_receipt() -> Receipt:
            census = self.adapter.inspect_candidate(self.target_url, self.canonical)
            self._verify_shape(census)
            return self._receipt(
                action="rollback",
                recovery=displaced,
                prior=active.receipt,
                census=census,
            )

        return self._swap(
            incoming=recovery,
            displaced=displaced,
            prepare_receipt=prepare_receipt,
            failure_code="rollback",
        )

    def prune(self, recovery: str) -> str:
        expected_confirmation(self.policy, "prune", recovery=recovery)
        state = self._state(recovery, missing="recovery_database_missing")
        if state.allow_connections:
            raise RefreshError("recovery_database_enabled")
        record = self._decode_state(
            state, expected_state="recovery", invalid="recovery_marker_invalid"
        )
        if record.receipt.recovery_database != recovery:
            raise RefreshError("recovery_receipt_mismatch")

        marked: list[str] = []
        for candidate in self.adapter.database_states(
            self.target_url, self.policy.lifecycle.recovery_prefix
        ):
            if candidate.allow_connections:
                continue
            try:
                candidate_record = self._decode_state(
                    candidate,
                    expected_state="recovery",
                    invalid="recovery_marker_invalid",
                )
            except RefreshError:
                continue
            if candidate_record.receipt.recovery_database == candidate.name:
                marked.append(candidate.name)
        retained = set(sorted(marked)[-self.policy.lifecycle.retained_recoveries :])
        if (
            recovery in retained
            or len(marked) <= self.policy.lifecycle.retained_recoveries
        ):
            raise RefreshError("recovery_retained")
        self.adapter.drop_recovery(self.target_url, recovery)
        return recovery


class PostgresRuntime:
    """PostgreSQL inspection boundary and lifecycle command runtime."""

    def __init__(
        self,
        policy: RefreshPolicy,
        *,
        source_url: str | None = None,
        target_url: str | None = None,
        adapter: SnapshotAdapter | None = None,
        engine: SnapshotRestoreEngine | None = None,
        runner: Callable[..., CommandResult] = subprocess.run,
        lock_factory: Callable[..., Any] = acquire_cluster_lock,
        harvest_lock_factory: Callable[..., Any] = acquire_harvest_coordination_lock,
        now: Callable[[], datetime] | None = None,
        broker_url: str | None = None,
        quiescence_guard: Callable[[], QuiescenceInspection] | None = None,
    ) -> None:
        self.policy = policy
        self.source_url = source_url
        self.target_url = target_url
        self.now = now or (lambda: datetime.now(UTC))
        if engine is not None and adapter is not None and engine.adapter is not adapter:
            raise ValueError("engine_adapter_mismatch")
        self.adapter = (
            adapter
            or (engine.adapter if engine is not None else None)
            or PsycopgSnapshotAdapter(policy, now=self.now)
        )
        self.runner = runner
        self.lock_factory = lock_factory
        self.harvest_lock_factory = harvest_lock_factory
        self.quiescence_guard = quiescence_guard or (
            lambda: inspect_staging_quiescence(policy, broker_url)
        )
        self.engine = engine or (
            SnapshotRestoreEngine(
                policy=policy,
                source_url=source_url,
                target_url=target_url,
                adapter=self.adapter,
                runner=runner,
                lock_factory=lock_factory,
                now=self.now,
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
                "ELSE FALSE END, "
                "CASE WHEN c.relkind IN ('r', 'p') THEN "
                "has_table_privilege(current_user, c.oid, 'MAINTAIN') ELSE FALSE END "
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
        maintainable_tables = frozenset(
            str(row[0]) for row in rows if row[1] in {"r", "p"} and row[5]
        )
        # PostgreSQL 18 MAINTAIN permits the schema locks pg_dump needs but no
        # row writes, so it is intentionally reported separately from DML.
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
            maintainable_tables=maintainable_tables,
            readable_sequences=readable_sequences,
            base_tables=base_tables,
            views=views,
            sequences=sequences,
        )

    def inspect_source(self, url: str) -> DatabaseInspection:
        return self._inspect(url)

    def inspect_target(self, url: str) -> DatabaseInspection:
        return self._inspect(url)

    def _lifecycle(self) -> LifecycleManager:
        if not self.target_url:
            raise RefreshError("target_url_missing")
        return LifecycleManager(
            policy=self.policy,
            target_url=self.target_url,
            adapter=self.adapter,
            now=self.now,
        )

    @contextmanager
    def _target_lock(self) -> Iterator[None]:
        if not self.target_url:
            raise RefreshError("target_url_missing")
        with self.lock_factory(
            self.target_url,
            wait_seconds=0,
            lock_id=self.policy.lifecycle.cluster_lock_id,
        ):
            yield

    @contextmanager
    def _harvest_lock(self) -> Iterator[None]:
        if not self.target_url:
            raise RefreshError("target_url_missing")
        with self.harvest_lock_factory(
            self.target_url,
            environment=self.policy.quiescence.harvest_environment,
        ):
            yield

    def _refresh(self) -> Receipt:
        with self._harvest_lock():
            self._require_quiescence()
            if self.engine is None:
                raise RefreshError("refresh_urls_missing")
            artifact = self.engine.export_dump()
            try:
                with self.engine.target_lock():
                    candidate = self.engine.restore_shadow(artifact)
                    try:
                        result = CandidateProcessor(
                            policy=self.policy,
                            target_url=self.engine.target_url,
                            adapter=self.engine.adapter,
                            runner=self.runner,
                        ).process(candidate)
                    except BaseException:
                        self.engine.cleanup_shadow(candidate.name, candidate.marker)
                        raise
                    self._require_quiescence()
                    return LifecycleManager(
                        policy=self.policy,
                        target_url=self.engine.target_url,
                        adapter=self.engine.adapter,
                        now=self.now,
                    ).activate(result)
            finally:
                self.engine.cleanup_artifact(artifact)

    def _require_quiescence(self) -> QuiescenceInspection:
        inspection = self.quiescence_guard()
        if inspection.worker_nodes:
            raise RefreshError(
                f"staging_headline_worker_active:{inspection.worker_nodes[0]}"
            )
        if (
            inspection.queue_depth
            or inspection.unacked_count
            or inspection.unacked_index_count
            or inspection.namespace_keys
        ):
            raise RefreshError("staging_headline_queue_not_empty")
        if inspection.envelope_present:
            raise RefreshError("staging_headline_envelope_present")
        return inspection

    def execute(self, action: str, *, recovery: str | None = None) -> dict[str, object]:
        if action == "preflight":
            with self._harvest_lock():
                self._require_quiescence()
                if self.engine is None:
                    raise RefreshError("refresh_urls_missing")
                census = self.engine.preflight()
            return {
                "action": "preflight",
                "source_database_bytes": census.database_bytes,
                "source_snapshot_at": census.captured_at.astimezone(UTC).isoformat(),
            }
        if action == "refresh":
            return self._refresh().to_payload()
        if action == "verify":
            return self._lifecycle().verify().to_payload()
        if action == "rollback":
            if recovery is None:
                raise RefreshError("recovery_name_missing")
            with self._harvest_lock(), self._target_lock():
                self._require_quiescence()
                return self._lifecycle().rollback(recovery).to_payload()
        if action == "prune":
            if recovery is None:
                raise RefreshError("recovery_name_missing")
            with self._harvest_lock(), self._target_lock():
                self._require_quiescence()
                pruned = self._lifecycle().prune(recovery)
            return {"action": "prune", "recovery_database": pruned}
        raise RefreshError("action_invalid")
