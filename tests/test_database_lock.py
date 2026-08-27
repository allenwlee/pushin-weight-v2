from __future__ import annotations

import os
from getpass import getuser
from typing import Self

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from scripts.database_lock import (
    DatabaseLockError,
    acquire_cluster_lock,
    acquire_harvest_coordination_lock,
    admin_connection_parameters,
    harvest_coordination_lock_keys,
)

Operation = tuple[str, tuple[object, ...]] | str


class FakeCursor:
    def __init__(
        self,
        operations: list[Operation],
        *,
        try_lock: bool = True,
        timeout: bool = False,
    ) -> None:
        self.operations = operations
        self.try_lock = try_lock
        self.timeout = timeout
        self.last_statement = ""

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, statement: str, parameters: list[object]) -> None:
        self.last_statement = statement
        self.operations.append((statement, tuple(parameters)))
        if self.timeout and "pg_advisory_lock" in statement:
            raise psycopg.errors.QueryCanceled()

    def fetchone(self) -> tuple[bool]:
        assert "pg_try_advisory_lock" in self.last_statement
        return (self.try_lock,)


class FakeConnection:
    def __init__(
        self,
        operations: list[Operation],
        *,
        try_lock: bool = True,
        timeout: bool = False,
    ) -> None:
        self.operations = operations
        self.try_lock = try_lock
        self.timeout = timeout

    def __enter__(self) -> Self:
        self.operations.append("connect")
        return self

    def __exit__(self, *_args: object) -> None:
        self.operations.append("close")

    def cursor(self) -> FakeCursor:
        return FakeCursor(
            self.operations,
            try_lock=self.try_lock,
            timeout=self.timeout,
        )


class FakeConnect:
    def __init__(
        self,
        operations: list[Operation],
        *,
        try_lock: bool = True,
        timeout: bool = False,
    ) -> None:
        self.operations = operations
        self.try_lock = try_lock
        self.timeout = timeout
        self.parameters: dict[str, object] = {}

    def __call__(self, **parameters: object) -> FakeConnection:
        self.parameters = parameters
        return FakeConnection(
            self.operations,
            try_lock=self.try_lock,
            timeout=self.timeout,
        )


def test_admin_connection_keeps_the_cluster_and_replaces_only_the_database() -> None:
    parameters = admin_connection_parameters(
        "postgresql://reader:secret@cluster.example:5432/application?sslmode=require"
    )

    assert parameters["host"] == "cluster.example"
    assert parameters["user"] == "reader"
    assert parameters["dbname"] == "postgres"
    assert parameters["sslmode"] == "require"


def test_harvest_coordination_lock_uses_admin_database_and_environment_keys() -> None:
    operations: list[Operation] = []
    connect = FakeConnect(operations)
    keys = harvest_coordination_lock_keys("staging")

    with acquire_harvest_coordination_lock(
        "postgresql://reader:secret@cluster.example/application",
        environment="staging",
        connect=connect,
    ):
        operations.append("critical")

    assert connect.parameters["dbname"] == "postgres"
    assert operations == [
        "connect",
        ("SELECT pg_try_advisory_lock(%s, %s)", keys),
        "critical",
        ("SELECT pg_advisory_unlock(%s, %s)", keys),
        "close",
    ]


def test_harvest_coordination_lock_refuses_concurrent_work() -> None:
    operations: list[Operation] = []
    connect = FakeConnect(operations, try_lock=False)

    with (
        pytest.raises(DatabaseLockError, match="^harvest_lock_unavailable$"),
        acquire_harvest_coordination_lock(
            "postgresql://reader:secret@cluster.example/application",
            environment="staging",
            connect=connect,
        ),
    ):
        raise AssertionError("unreachable")


def test_fail_fast_lock_refuses_contention_and_closes_the_connection() -> None:
    operations: list[Operation] = []
    connect = FakeConnect(operations, try_lock=False)

    with (
        pytest.raises(DatabaseLockError, match="cluster_lock_unavailable"),
        acquire_cluster_lock(
            "postgresql://reader:secret@cluster.example/application",
            wait_seconds=0,
            connect=connect,
        ),
    ):
        raise AssertionError("unreachable")

    assert operations == [
        "connect",
        ("SELECT pg_try_advisory_lock(%s)", (8_675_309,)),
        "close",
    ]


def test_waiting_lock_releases_after_success_in_reverse_order() -> None:
    operations: list[Operation] = []
    connect = FakeConnect(operations)

    with acquire_cluster_lock(
        "postgresql://reader:secret@cluster.example/application",
        wait_seconds=900,
        connect=connect,
    ):
        operations.append("critical")

    assert operations == [
        "connect",
        ("SELECT set_config('statement_timeout', %s, false)", ("900000",)),
        ("SELECT pg_advisory_lock(%s)", (8_675_309,)),
        ("SELECT set_config('statement_timeout', '0', false)", ()),
        "critical",
        ("SELECT pg_advisory_unlock(%s)", (8_675_309,)),
        "close",
    ]


@pytest.mark.requires_postgres
def test_waiting_lock_timeout_sql_executes_against_postgres() -> None:
    parameters = conninfo_to_dict(os.environ["DATABASE_URL"])
    parameters.setdefault("host", "localhost")
    parameters.setdefault("user", getuser())
    database_url = make_conninfo(**parameters)

    with acquire_cluster_lock(database_url, wait_seconds=1):
        pass


@pytest.mark.requires_postgres
def test_harvest_coordination_contention_executes_against_postgres() -> None:
    parameters = conninfo_to_dict(os.environ["DATABASE_URL"])
    parameters.setdefault("host", "localhost")
    parameters.setdefault("user", getuser())
    database_url = make_conninfo(**parameters)

    with (
        acquire_harvest_coordination_lock(database_url, environment="staging"),
        pytest.raises(DatabaseLockError, match="^harvest_lock_unavailable$"),
        acquire_harvest_coordination_lock(database_url, environment="staging"),
    ):
        raise AssertionError("unreachable")


def test_waiting_lock_times_out_at_the_bounded_deadline_and_closes() -> None:
    operations: list[Operation] = []
    connect = FakeConnect(operations, timeout=True)

    with (
        pytest.raises(DatabaseLockError, match="cluster_lock_timeout"),
        acquire_cluster_lock(
            "postgresql://reader:secret@cluster.example/application",
            wait_seconds=900,
            connect=connect,
        ),
    ):
        raise AssertionError("unreachable")

    assert operations == [
        "connect",
        ("SELECT set_config('statement_timeout', %s, false)", ("900000",)),
        ("SELECT pg_advisory_lock(%s)", (8_675_309,)),
        "close",
    ]


def test_critical_section_failure_still_releases_and_closes() -> None:
    operations: list[Operation] = []
    connect = FakeConnect(operations)

    with (
        pytest.raises(RuntimeError, match="boom"),
        acquire_cluster_lock(
            "postgresql://reader:secret@cluster.example/application",
            wait_seconds=0,
            connect=connect,
        ),
    ):
        operations.append("critical")
        raise RuntimeError("boom")

    assert operations[-3:] == [
        "critical",
        ("SELECT pg_advisory_unlock(%s)", (8_675_309,)),
        "close",
    ]


def test_invalid_connection_never_exposes_the_url() -> None:
    secret_url = "not-a-database-url-with-super-secret"

    with pytest.raises(DatabaseLockError) as exc_info:
        admin_connection_parameters(secret_url)

    assert secret_url not in str(exc_info.value)
