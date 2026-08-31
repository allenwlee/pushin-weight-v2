"""Create and restore-prove the production Account recovery snapshot."""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any
from uuid import UUID

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from psycopg import sql

from core.models import Account
from monitor.management.commands.backfill_account_based_in import (
    PRODUCTION_DATABASE_NAME,
    _is_authorized_executor,
    _production_run_lock,
    _required_migrations_applied,
)

BACKUP_SCHEMA = "account_user_about_backup"
RESTORE_PROOF_TABLE = "account_user_about_restore_proof"
STORAGE_POLICY = "render-postgres-encrypted-at-rest"
RESTORE_PROOF_POLICY = "temporary-relation-count-and-digest-match"


def _json_default(value: Any) -> str:
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    if isinstance(value, (Decimal, UUID)):
        return str(value)
    raise TypeError(f"unsupported digest value type: {type(value).__name__}")


def _digest_relation(relation_sql: sql.Composable) -> tuple[int, str]:
    digest = hashlib.sha256()
    row_count = 0
    with connection.cursor() as cursor:
        cursor.execute(
            sql.SQL("SELECT * FROM {} ORDER BY author_id").format(relation_sql)
        )
        while rows := cursor.fetchmany(1_000):
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


def _build_receipt(
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
        "database": PRODUCTION_DATABASE_NAME,
        "created_at": created_at.isoformat(),
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


class Command(BaseCommand):
    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--confirm-database")

    def handle(self, **options):
        if not options["apply"]:
            account_count = Account.objects.count()
            self.stdout.write(
                json.dumps(
                    {
                        "mode": "dry_run",
                        "target": "production",
                        "account_count": account_count,
                        "writes": 0,
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return

        if options["confirm_database"] != PRODUCTION_DATABASE_NAME:
            raise CommandError(
                f"apply requires --confirm-database {PRODUCTION_DATABASE_NAME}"
            )
        if not _is_authorized_executor("production"):
            raise CommandError(
                "recovery snapshot is restricted to the managed production environment"
            )
        if not _required_migrations_applied():
            raise CommandError("required User About migrations are not applied")

        proof_sql = sql.Identifier("pg_temp", RESTORE_PROOF_TABLE)

        with _production_run_lock(), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
                cursor.execute(
                    sql.SQL("SELECT statement_timestamp(), count(*) FROM {}").format(
                        sql.Identifier(Account._meta.db_table)
                    )
                )
                created_at, account_count = cursor.fetchone()
                account_count = int(account_count)
                suffix = created_at.strftime("%Y%m%dt%H%M%Sz").lower()
                table_name = f"accounts_{suffix}"
                relation = f"{BACKUP_SCHEMA}.{table_name}"
                relation_sql = sql.Identifier(BACKUP_SCHEMA, table_name)
                cursor.execute(
                    sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(
                        sql.Identifier(BACKUP_SCHEMA)
                    )
                )
                cursor.execute(
                    sql.SQL("REVOKE ALL ON SCHEMA {} FROM PUBLIC").format(
                        sql.Identifier(BACKUP_SCHEMA)
                    )
                )
                cursor.execute(
                    sql.SQL("CREATE TABLE {} AS SELECT * FROM {}").format(
                        relation_sql,
                        sql.Identifier(Account._meta.db_table),
                    )
                )
                cursor.execute(
                    sql.SQL("REVOKE ALL ON TABLE {} FROM PUBLIC").format(relation_sql)
                )

            snapshot_count, snapshot_digest = _digest_relation(relation_sql)
            with connection.cursor() as cursor:
                cursor.execute(
                    sql.SQL(
                        "CREATE TEMP TABLE {} ON COMMIT DROP AS SELECT * FROM {}"
                    ).format(
                        sql.Identifier(RESTORE_PROOF_TABLE),
                        relation_sql,
                    )
                )
            restore_count, restore_digest = _digest_relation(proof_sql)
            if snapshot_count != restore_count or snapshot_digest != restore_digest:
                raise CommandError("recovery snapshot restore proof does not match")
            if snapshot_count != account_count:
                raise CommandError(
                    "recovery snapshot Account count changed during preflight"
                )

            receipt, token = _build_receipt(
                created_at=created_at,
                snapshot_relation=relation,
                snapshot_account_count=snapshot_count,
                snapshot_row_digest=snapshot_digest,
                restore_account_count=restore_count,
                restore_row_digest=restore_digest,
            )

        self.stdout.write(
            json.dumps(
                {
                    "mode": "production_snapshot_apply",
                    "snapshot_relation": relation,
                    "account_count": snapshot_count,
                    "row_digest": snapshot_digest,
                    "restore_proved": True,
                    "receipt_sha256": receipt["receipt_sha256"],
                    "recovery_receipt": token,
                },
                indent=2,
                sort_keys=True,
            )
        )
