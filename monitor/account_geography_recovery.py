"""Receipt and digest primitives for narrow Account geography recovery."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from django.core.management.base import CommandError
from django.db import connection
from django.utils import timezone
from psycopg import sql

from core.models import Account

PRODUCTION_DATABASE_NAME = "pushinweight_shadow"
BACKUP_SCHEMA = "account_geography_backup"
RESTORE_PROOF_TABLE = "account_geography_restore_proof"
STORAGE_POLICY = "render-postgres-encrypted-at-rest"
RESTORE_PROOF_POLICY = "temporary-relation-count-and-digest-match"
RECEIPT_MAX_AGE = timedelta(hours=24)
GEOGRAPHY_COLUMNS = (
    "author_id",
    "account_based_in",
    "country_code",
    "based_in_region_key",
    "account_based_in_fetched_at",
    "first_seen_at",
)
_MODEL_GEOGRAPHY_FIELDS = (
    "author_id",
    "account_based_in",
    "country_id",
    "based_in_region_id",
    "account_based_in_fetched_at",
    "first_seen_at",
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_RELATION = re.compile(r"account_geography_backup\.accounts_geo_[0-9]{8}t[0-9]{6}z")


@dataclass(frozen=True, slots=True)
class GeographyRecoveryReceipt:
    receipt_sha256: str
    created_at: datetime
    snapshot_account_count: int
    row_digest: str
    storage: str
    snapshot_relation: str
    columns: tuple[str, ...]


def _json_default(value: Any) -> str:
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    if isinstance(value, (Decimal, UUID)):
        return str(value)
    raise TypeError(f"unsupported digest value type: {type(value).__name__}")


def digest_rows(rows: Iterable[tuple]) -> tuple[int, str]:
    digest = hashlib.sha256()
    row_count = 0
    for row in rows:
        encoded = json.dumps(
            row,
            default=_json_default,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode()
        digest.update(encoded)
        digest.update(b"\n")
        row_count += 1
    return row_count, digest.hexdigest()


def digest_relation(relation_sql: sql.Composable) -> tuple[int, str]:
    columns_sql = sql.SQL(", ").join(map(sql.Identifier, GEOGRAPHY_COLUMNS))
    with connection.cursor() as cursor:
        cursor.execute(
            sql.SQL("SELECT {} FROM {} ORDER BY author_id").format(
                columns_sql,
                relation_sql,
            )
        )

        def rows():
            while batch := cursor.fetchmany(1_000):
                yield from batch

        return digest_rows(rows())


def digest_account_queryset(queryset) -> tuple[int, str]:
    rows = queryset.order_by("author_id").values_list(*_MODEL_GEOGRAPHY_FIELDS)
    return digest_rows(rows.iterator(chunk_size=1_000))


def _build_geography_receipt(
    *,
    created_at: datetime,
    snapshot_relation: str,
    snapshot_account_count: int,
    snapshot_row_digest: str,
    restore_account_count: int,
    restore_row_digest: str,
) -> tuple[dict[str, Any], str]:
    payload = {
        "schema_version": 1,
        "scope": "account_geography",
        "database": PRODUCTION_DATABASE_NAME,
        "created_at": created_at.isoformat(),
        "columns": list(GEOGRAPHY_COLUMNS),
        "snapshot_account_count": snapshot_account_count,
        "snapshot_row_digest": snapshot_row_digest,
        "restore_account_count": restore_account_count,
        "restore_row_digest": restore_row_digest,
        "storage": STORAGE_POLICY,
        "snapshot_relation": snapshot_relation,
        "restore_proof": RESTORE_PROOF_POLICY,
    }
    canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    payload["receipt_sha256"] = hashlib.sha256(canonical).hexdigest()
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    token = base64.urlsafe_b64encode(encoded).decode().rstrip("=")
    return payload, token


def parse_geography_recovery_receipt(
    encoded: str | None,
) -> GeographyRecoveryReceipt:
    if not encoded:
        raise CommandError("production apply requires a geography recovery receipt")
    try:
        padded = encoded + "=" * (-len(encoded) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode()))
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CommandError("geography recovery receipt is invalid") from exc
    if not isinstance(payload, dict):
        raise CommandError("geography recovery receipt is invalid")

    expected_keys = {
        "schema_version",
        "scope",
        "database",
        "created_at",
        "columns",
        "snapshot_account_count",
        "snapshot_row_digest",
        "restore_account_count",
        "restore_row_digest",
        "storage",
        "snapshot_relation",
        "restore_proof",
        "receipt_sha256",
    }
    if (
        set(payload) != expected_keys
        or payload.get("schema_version") != 1
        or payload.get("scope") != "account_geography"
    ):
        raise CommandError("geography recovery receipt is invalid")

    receipt_sha256 = payload["receipt_sha256"]
    unsigned = {key: value for key, value in payload.items() if key != "receipt_sha256"}
    canonical = json.dumps(unsigned, separators=(",", ":"), sort_keys=True).encode()
    expected_sha256 = hashlib.sha256(canonical).hexdigest()
    if not isinstance(receipt_sha256, str) or not hmac.compare_digest(
        receipt_sha256,
        expected_sha256,
    ):
        raise CommandError("geography recovery receipt digest does not match")
    if payload["database"] != PRODUCTION_DATABASE_NAME:
        raise CommandError("geography recovery receipt database does not match")
    if payload["columns"] != list(GEOGRAPHY_COLUMNS):
        raise CommandError("geography recovery receipt columns do not match")

    snapshot_digest = payload["snapshot_row_digest"]
    if (
        not isinstance(snapshot_digest, str)
        or not _SHA256.fullmatch(snapshot_digest)
        or payload["restore_row_digest"] != snapshot_digest
    ):
        raise CommandError("geography recovery receipt restore digest does not match")
    snapshot_count = payload["snapshot_account_count"]
    if (
        type(snapshot_count) is not int
        or snapshot_count <= 0
        or payload["restore_account_count"] != snapshot_count
    ):
        raise CommandError("geography recovery receipt restore count does not match")
    if payload["storage"] != STORAGE_POLICY:
        raise CommandError("geography recovery receipt storage is not approved")
    if not isinstance(payload["snapshot_relation"], str) or not _RELATION.fullmatch(
        payload["snapshot_relation"]
    ):
        raise CommandError("geography recovery receipt relation is invalid")
    if payload["restore_proof"] != RESTORE_PROOF_POLICY:
        raise CommandError("geography recovery receipt restore proof is invalid")

    try:
        created_at = datetime.fromisoformat(str(payload["created_at"]))
    except ValueError as exc:
        raise CommandError("geography recovery receipt timestamp is invalid") from exc
    if timezone.is_naive(created_at):
        raise CommandError("geography recovery receipt timestamp is invalid")
    age = timezone.now() - created_at
    if age < -timedelta(minutes=5) or age > RECEIPT_MAX_AGE:
        raise CommandError("geography recovery receipt is stale")

    return GeographyRecoveryReceipt(
        receipt_sha256=receipt_sha256,
        created_at=created_at,
        snapshot_account_count=snapshot_count,
        row_digest=snapshot_digest,
        storage=payload["storage"],
        snapshot_relation=payload["snapshot_relation"],
        columns=tuple(payload["columns"]),
    )


def verify_geography_recovery_snapshot(
    receipt: GeographyRecoveryReceipt,
):
    schema_name, table_name = receipt.snapshot_relation.split(".", 1)
    relation_sql = sql.Identifier(schema_name, table_name)
    with connection.cursor() as cursor:
        cursor.execute("SELECT to_regclass(%s)", [receipt.snapshot_relation])
        if cursor.fetchone()[0] is None:
            raise CommandError("geography recovery snapshot relation is unavailable")

    snapshot_count, snapshot_digest = digest_relation(relation_sql)
    if (
        snapshot_count != receipt.snapshot_account_count
        or snapshot_digest != receipt.row_digest
    ):
        raise CommandError("geography recovery snapshot does not match its receipt")

    queryset = Account.objects.filter(first_seen_at__lte=receipt.created_at)
    current_count, current_digest = digest_account_queryset(queryset)
    if (
        current_count != receipt.snapshot_account_count
        or current_digest != receipt.row_digest
    ):
        raise CommandError("current Account geography does not match recovery snapshot")
    return queryset
