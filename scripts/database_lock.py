from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any, Protocol, Self

import psycopg
from psycopg.conninfo import conninfo_to_dict

CLUSTER_LOCK_ID = 8_675_309


class DatabaseLockError(RuntimeError):
    """A secret-free cluster-lock failure that can be retried safely."""


class Cursor(Protocol):
    def __enter__(self) -> Self: ...

    def __exit__(self, *_args: object) -> None: ...

    def execute(self, statement: str, parameters: list[object]) -> None: ...

    def fetchone(self) -> tuple[object, ...]: ...


class Connection(Protocol):
    def __enter__(self) -> Self: ...

    def __exit__(self, *_args: object) -> None: ...

    def cursor(self) -> Cursor: ...


def admin_connection_parameters(database_url: str) -> dict[str, str]:
    """Return the same cluster credentials scoped to its administration DB."""

    try:
        parameters = {
            key: str(value)
            for key, value in conninfo_to_dict(database_url).items()
            if value is not None
        }
    except Exception as exc:
        raise DatabaseLockError("database_url_invalid") from exc
    if not parameters.get("host") or not parameters.get("user"):
        raise DatabaseLockError("database_url_invalid")
    parameters["dbname"] = "postgres"
    return parameters


def harvest_coordination_lock_keys(environment: str) -> tuple[int, int]:
    """Return stable signed PostgreSQL keys for one environment's harvest gate."""

    if not environment or "\n" in environment or "\r" in environment:
        raise DatabaseLockError("harvest_lock_environment_invalid")
    digest = hashlib.sha256(
        f"pushinweight:harvest-coordination:{environment}".encode()
    ).digest()
    unsigned = (
        int.from_bytes(digest[:4], "big"),
        int.from_bytes(digest[4:8], "big"),
    )
    return tuple(value - 2**32 if value >= 2**31 else value for value in unsigned)


@contextmanager
def acquire_harvest_coordination_lock(
    database_url: str,
    *,
    environment: str,
    connect: Callable[..., Connection] = psycopg.connect,
) -> Iterator[None]:
    """Exclude staging harvest and refresh across active-database swaps.

    Both callers connect to the cluster administration database. The lock
    therefore survives termination and renaming of the serving staging
    database during activation.
    """

    parameters: dict[str, Any] = admin_connection_parameters(database_url)
    keys = harvest_coordination_lock_keys(environment)
    try:
        connection = connect(**parameters, autocommit=True)
    except Exception as exc:
        raise DatabaseLockError("harvest_lock_connection_failed") from exc

    acquired = False
    with connection:
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_try_advisory_lock(%s, %s)", list(keys))
                row = cursor.fetchone()
                acquired = bool(row and row[0])
                if not acquired:
                    raise DatabaseLockError("harvest_lock_unavailable")
        except DatabaseLockError:
            raise
        except Exception as exc:
            raise DatabaseLockError("harvest_lock_acquire_failed") from exc

        try:
            yield
        finally:
            if acquired:
                try:
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT pg_advisory_unlock(%s, %s)", list(keys))
                except Exception as exc:
                    raise DatabaseLockError("harvest_lock_release_failed") from exc


@contextmanager
def acquire_cluster_lock(
    database_url: str,
    *,
    wait_seconds: int,
    lock_id: int = CLUSTER_LOCK_ID,
    connect: Callable[..., Connection] = psycopg.connect,
) -> Iterator[None]:
    """Own the shared cluster lifecycle lock on the cluster's `postgres` DB."""

    if wait_seconds < 0:
        raise DatabaseLockError("cluster_lock_wait_invalid")
    parameters: dict[str, Any] = admin_connection_parameters(database_url)
    try:
        connection = connect(**parameters, autocommit=True)
    except Exception as exc:
        raise DatabaseLockError("cluster_connection_failed") from exc

    acquired = False
    with connection:
        try:
            with connection.cursor() as cursor:
                if wait_seconds == 0:
                    cursor.execute("SELECT pg_try_advisory_lock(%s)", [lock_id])
                    row = cursor.fetchone()
                    acquired = bool(row and row[0])
                    if not acquired:
                        raise DatabaseLockError("cluster_lock_unavailable")
                else:
                    cursor.execute(
                        "SELECT set_config('statement_timeout', %s, false)",
                        [str(wait_seconds * 1000)],
                    )
                    try:
                        cursor.execute("SELECT pg_advisory_lock(%s)", [lock_id])
                    except psycopg.errors.QueryCanceled as exc:
                        raise DatabaseLockError("cluster_lock_timeout") from exc
                    acquired = True
                    cursor.execute(
                        "SELECT set_config('statement_timeout', '0', false)", []
                    )
        except DatabaseLockError:
            raise
        except Exception as exc:
            raise DatabaseLockError("cluster_lock_acquire_failed") from exc

        try:
            yield
        finally:
            if acquired:
                try:
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT pg_advisory_unlock(%s)", [lock_id])
                except Exception as exc:
                    raise DatabaseLockError("cluster_lock_release_failed") from exc
