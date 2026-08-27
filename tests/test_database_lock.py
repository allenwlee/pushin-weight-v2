from __future__ import annotations

from typing import Self

import psycopg
import pytest

from scripts.database_lock import (
    DatabaseLockError,
    acquire_cluster_lock,
    admin_connection_parameters,
)

Operation = tuple[str, tuple[int, ...]] | str


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

    def execute(self, statement: str, parameters: list[int]) -> None:
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


def test_fail_fast_lock_refuses_contention_and_closes_the_connection() -> None:
    operations: list[Operation] = []
    connect = FakeConnect(operations, try_lock=False)

    with pytest.raises(
        DatabaseLockError, match="cluster_lock_unavailable"
    ), acquire_cluster_lock(
        "postgresql://reader:secret@cluster.example/application",
        wait_seconds=0,
        connect=connect,
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
        ("SET statement_timeout = %s", (900_000,)),
        ("SELECT pg_advisory_lock(%s)", (8_675_309,)),
        ("SET statement_timeout = 0", ()),
        "critical",
        ("SELECT pg_advisory_unlock(%s)", (8_675_309,)),
        "close",
    ]


def test_waiting_lock_times_out_at_the_bounded_deadline_and_closes() -> None:
    operations: list[Operation] = []
    connect = FakeConnect(operations, timeout=True)

    with pytest.raises(
        DatabaseLockError, match="cluster_lock_timeout"
    ), acquire_cluster_lock(
        "postgresql://reader:secret@cluster.example/application",
        wait_seconds=900,
        connect=connect,
    ):
        raise AssertionError("unreachable")

    assert operations == [
        "connect",
        ("SET statement_timeout = %s", (900_000,)),
        ("SELECT pg_advisory_lock(%s)", (8_675_309,)),
        "close",
    ]


def test_critical_section_failure_still_releases_and_closes() -> None:
    operations: list[Operation] = []
    connect = FakeConnect(operations)

    with pytest.raises(RuntimeError, match="boom"), acquire_cluster_lock(
        "postgresql://reader:secret@cluster.example/application",
        wait_seconds=0,
        connect=connect,
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
