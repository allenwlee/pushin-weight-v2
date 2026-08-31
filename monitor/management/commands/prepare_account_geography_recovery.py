"""Create and restore-prove a narrow production Account geography snapshot."""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from psycopg import sql

from core.models import Account
from monitor.account_geography_recovery import (
    BACKUP_SCHEMA,
    GEOGRAPHY_COLUMNS,
    PRODUCTION_DATABASE_NAME,
    RESTORE_PROOF_TABLE,
    _build_geography_receipt,
    digest_relation,
)
from monitor.management.commands.reconcile_account_geography import (
    _geography_run_lock,
    _is_authorized_executor,
    _required_migrations_applied,
)


class Command(BaseCommand):
    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--confirm-database")

    def handle(self, **options):
        if not options["apply"]:
            self.stdout.write(
                json.dumps(
                    {
                        "mode": "dry_run",
                        "target": "production",
                        "account_count": Account.objects.count(),
                        "columns": list(GEOGRAPHY_COLUMNS),
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
            raise CommandError("geography snapshot is restricted to managed production")
        if not _required_migrations_applied():
            raise CommandError("required geography migrations are not applied")

        proof_sql = sql.Identifier("pg_temp", RESTORE_PROOF_TABLE)
        columns_sql = sql.SQL(", ").join(map(sql.Identifier, GEOGRAPHY_COLUMNS))

        with _geography_run_lock(), transaction.atomic():
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
                table_name = f"accounts_geo_{suffix}"
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
                    sql.SQL("CREATE TABLE {} AS SELECT {} FROM {}").format(
                        relation_sql,
                        columns_sql,
                        sql.Identifier(Account._meta.db_table),
                    )
                )
                cursor.execute(
                    sql.SQL("REVOKE ALL ON TABLE {} FROM PUBLIC").format(relation_sql)
                )

            snapshot_count, snapshot_digest = digest_relation(relation_sql)
            with connection.cursor() as cursor:
                cursor.execute(
                    sql.SQL(
                        "CREATE TEMP TABLE {} ON COMMIT DROP AS SELECT {} FROM {}"
                    ).format(
                        sql.Identifier(RESTORE_PROOF_TABLE),
                        columns_sql,
                        relation_sql,
                    )
                )
            restore_count, restore_digest = digest_relation(proof_sql)
            if snapshot_count != restore_count or snapshot_digest != restore_digest:
                raise CommandError("geography recovery restore proof does not match")
            if snapshot_count != account_count:
                raise CommandError("geography snapshot Account count changed")

            receipt, token = _build_geography_receipt(
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
                    "mode": "production_geography_snapshot_apply",
                    "snapshot_relation": relation,
                    "account_count": snapshot_count,
                    "columns": list(GEOGRAPHY_COLUMNS),
                    "row_digest": snapshot_digest,
                    "restore_proved": True,
                    "receipt_sha256": receipt["receipt_sha256"],
                    "recovery_receipt": token,
                },
                indent=2,
                sort_keys=True,
            )
        )
