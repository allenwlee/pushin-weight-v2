"""Explicit execution-location binding for copied, immutable backfill jobs.

The operator supplies a checksummed copy receipt. Nothing reads it implicitly
from the environment, and ordinary/scheduled processes retain strict identity
checks. The binding is process-wide so enrichment worker threads see it too.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from contextlib import contextmanager
from pathlib import Path

from django.db import connection

from core.measurement_taxonomy import digest, require

FORMAT = "x-backfill-database-relocation/v1"
_binding = None
_lock = threading.Lock()


def identity():
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_database(),session_user")
        name, user = cursor.fetchone()
    return {"name": name, "user": user, "host": connection.settings_dict["HOST"]}


def _identity_matches(actual, expected):
    return (
        actual["name"] == expected["name"]
        and actual["user"] == expected["user"]
        and actual["host"] in expected["hosts"]
    )


def validate_receipt(value):
    require(
        isinstance(value, dict)
        and set(value)
        == {
            "format",
            "source",
            "destination",
            "verified",
            "snapshot_sha256",
            "definitions",
            "scopes",
            "manifests",
        },
        "relocation receipt fields invalid",
    )
    require(
        value["format"] == FORMAT and value["verified"] is True,
        "verified relocation receipt required",
    )
    for name in ("source", "destination"):
        row = value[name]
        require(
            isinstance(row, dict) and set(row) == {"name", "user", "hosts"},
            "relocation identity fields invalid",
        )
        require(
            all(isinstance(row[k], str) and row[k] for k in ("name", "user")),
            "relocation identity required",
        )
        require(
            isinstance(row["hosts"], list)
            and 1 <= len(row["hosts"]) <= 2
            and all(
                isinstance(h, str) and h and re.fullmatch(r"[A-Za-z0-9.:-]+", h)
                for h in row["hosts"]
            ),
            "relocation hosts invalid",
        )
    require(
        not set(value["source"]["hosts"]) & set(value["destination"]["hosts"]),
        "relocation source and destination must differ",
    )
    for key in ("definitions", "scopes", "manifests"):
        require(
            isinstance(value[key], list)
            and len(value[key]) <= 10000
            and (key == "manifests" or bool(value[key])),
            "relocation allowlist invalid",
        )
    hashes = [
        value["snapshot_sha256"],
        *value["definitions"],
        *value["scopes"],
        *value["manifests"],
    ]
    require(
        all(isinstance(v, str) and re.fullmatch(r"[a-f0-9]{64}", v) for v in hashes),
        "relocation hashes invalid",
    )
    return value


def _checked_binding():
    if _binding is None:
        return None
    require(
        os.environ.get("X_MONITOR_DEPLOYMENT_ENVIRONMENT") == "backfill",
        "relocation requires dedicated backfill environment",
    )
    require(
        _identity_matches(identity(), _binding["destination"]),
        "relocation destination changed",
    )
    return _binding


def copy_verified(snapshot_sha256):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT shobj_description(oid,'pg_database') FROM pg_database WHERE datname=current_database()"
        )
        return cursor.fetchone()[0] == "x-backfill-copy/v1:" + snapshot_sha256


@contextmanager
def relocated_database(path, sha256):
    global _binding
    require(
        bool(path) == bool(sha256), "relocation path and checksum required together"
    )
    if path is None:
        yield
        return
    require(_lock.acquire(blocking=False), "relocation context already active")
    try:
        require(
            Path(path).stat().st_size <= 2 * 1024 * 1024, "relocation receipt too large"
        )
        body = Path(path).read_bytes()
        require(
            hashlib.sha256(body).hexdigest() == sha256,
            "relocation receipt checksum mismatch",
        )
        value = validate_receipt(json.loads(body))
        _binding = {**value, "receipt_sha256": sha256}
        _checked_binding()
        require(
            copy_verified(value["snapshot_sha256"]),
            "relocation copy verification missing",
        )
        yield
    finally:
        _binding = None
        _lock.release()


def scope_relocated(scope):
    bound = _checked_binding()
    return bool(
        bound
        and scope.get("database") == {k: bound["source"][k] for k in ("name", "user")}
        and digest(scope) in bound["scopes"]
        and (
            not scope.get("staging_host")
            or scope["staging_host"] in bound["source"]["hosts"]
        )
    )


def job_database_matches(job, actual=None):
    actual = actual or identity()
    if job.scope.get("database") == {k: actual[k] for k in ("name", "user")}:
        return True
    if (job.source_id, job.purpose, job.operation, job.mode) != (
        "x",
        "content",
        "x_backfill",
        "historical",
    ):
        return False
    if (
        not scope_relocated(job.scope)
        or job.definition_sha256 not in _binding["definitions"]
    ):
        return False
    from core.collection_jobs import validate_job

    validate_job(job)
    return True


def campaign_database_matches(frozen, actual):
    if frozen["database"] == {k: actual[k] for k in ("name", "user")}:
        return True
    bound = _checked_binding()
    return bool(
        bound
        and frozen["database"] == {k: bound["source"][k] for k in ("name", "user")}
        and digest(frozen) in bound["manifests"]
    )


def relocation_audit():
    bound = _checked_binding()
    return (
        {
            k: bound[k]
            for k in ("receipt_sha256", "snapshot_sha256", "source", "destination")
        }
        if bound
        else None
    )
