"""Reconcile account links introduced on the independently deployed company branch."""

import json
import uuid
from typing import ClassVar

import django.db.models.deletion
from django.db import migrations, models
from django.db.migrations.exceptions import IrreversibleError

LINKS = (
    ("official_company_account_states", True),
    ("official_company_list_intents", False),
)


def forward(apps, schema_editor):
    q = schema_editor.quote_name
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SET LOCAL lock_timeout = '5s'")
        cursor.execute("SELECT pg_try_advisory_xact_lock(72620666)")
        if not cursor.fetchone()[0]:
            raise RuntimeError("account migration lock busy")
        for table, unique in LINKS:
            cursor.execute(
                "SELECT atttypid::regtype::text FROM pg_attribute "
                "WHERE attrelid=%s::regclass AND attname='account_id'",
                [table],
            )
            column_type = cursor.fetchone()[0]
            if column_type not in {"text", "uuid"}:
                raise RuntimeError(f"unsupported account link type: {table}")
            cursor.execute(f"ALTER TABLE {q(table)} ADD COLUMN account_key uuid")
            join = "account_key" if column_type == "uuid" else "author_id"
            cursor.execute(
                f"UPDATE {q(table)} t SET account_key=a.account_key "
                f"FROM accounts a WHERE t.account_id=a.{join} AND a.data_source_id='x'"
            )
            cursor.execute(f"SELECT count(*) FROM {q(table)} WHERE account_key IS NULL")
            if cursor.fetchone()[0]:
                raise RuntimeError(f"unmapped company account links: {table}")
            cursor.execute(
                "SELECT conname FROM pg_constraint WHERE conrelid=%s::regclass "
                "AND confrelid='accounts'::regclass AND contype='f'",
                [table],
            )
            for (name,) in cursor.fetchall():
                cursor.execute(f"ALTER TABLE {q(table)} DROP CONSTRAINT {q(name)}")
            if column_type == "uuid":
                cursor.execute(
                    f"ALTER TABLE {q(table)} ALTER COLUMN account_id TYPE text "
                    "USING account_id::text"
                )
                cursor.execute(
                    f"UPDATE {q(table)} t SET account_id=a.author_id "
                    "FROM accounts a WHERE t.account_key=a.account_key"
                )
            cursor.execute(
                f"ALTER TABLE {q(table)} ALTER COLUMN account_id DROP NOT NULL, "
                "ALTER COLUMN account_key SET NOT NULL"
            )
            cursor.execute(
                f"ALTER TABLE {q(table)} ADD CONSTRAINT {q(table + '_native_account_fk')} "
                "FOREIGN KEY(account_id) REFERENCES accounts(author_id) DEFERRABLE INITIALLY DEFERRED, "
                f"ADD CONSTRAINT {q(table + '_generic_account_fk')} "
                "FOREIGN KEY(account_key) REFERENCES accounts(account_key) DEFERRABLE INITIALLY DEFERRED"
            )
            if unique:
                cursor.execute(
                    f"ALTER TABLE {q(table)} ADD CONSTRAINT {q(table + '_generic_account_unique')} "
                    "UNIQUE(account_key)"
                )
            else:
                cursor.execute(
                    f"ALTER TABLE {q(table)} DROP CONSTRAINT uq_official_co_list_intent, "
                    "ADD CONSTRAINT uq_official_co_list_intent UNIQUE(list_id,account_key), "
                    "ADD CONSTRAINT compat_official_co_list_intent UNIQUE(list_id,account_id)"
                )
                cursor.execute(
                    f"CREATE INDEX {q(table + '_generic_account_idx')} ON {q(table)}(account_key)"
                )
            cursor.execute(
                f"CREATE TRIGGER benchmark_account_link BEFORE INSERT OR UPDATE ON {q(table)} "
                "FOR EACH ROW EXECUTE FUNCTION "
                "benchmark_account_link_compatibility('account_id','account_key','x')"
            )
        cursor.execute(
            "SELECT cursor FROM official_company_scans WHERE key='account-observations' FOR UPDATE"
        )
        row = cursor.fetchone()
        if row and row[0]:
            checkpoint = json.loads(row[0])
            previous = checkpoint.get("pk")
            if previous is not None:
                try:
                    uuid.UUID(str(previous))
                except ValueError:
                    cursor.execute(
                        "SELECT account_key FROM accounts WHERE author_id=%s AND data_source_id='x'",
                        [str(previous)],
                    )
                    account = cursor.fetchone()
                    if not account:
                        raise RuntimeError(
                            "unmapped company account observation checkpoint"
                        )
                    checkpoint.update(
                        pk=str(account[0]), legacy_native_pk=str(previous)
                    )
                    cursor.execute(
                        "UPDATE official_company_scans SET cursor=%s WHERE key='account-observations'",
                        [json.dumps(checkpoint)],
                    )


def reverse(apps, schema_editor):
    raise IrreversibleError(
        "Preserve account links; use reviewed forward repair or database restore."
    )


class Migration(migrations.Migration):
    dependencies: ClassVar[list] = [("core", "0073_rename_metrics")]
    operations: ClassVar[list] = [
        migrations.SeparateDatabaseAndState(
            database_operations=[migrations.RunPython(forward, reverse)],
            state_operations=[
                migrations.RenameField(
                    "officialcompanyaccountstate", "account", "native_account_id"
                ),
                migrations.AlterField(
                    "officialcompanyaccountstate",
                    "native_account_id",
                    models.TextField(db_column="account_id", null=True, editable=False),
                ),
                migrations.AddField(
                    "officialcompanyaccountstate",
                    "account",
                    models.OneToOneField(
                        to="core.account",
                        db_column="account_key",
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="official_company_state",
                    ),
                ),
                migrations.RemoveConstraint(
                    "officialcompanylistintent", "uq_official_co_list_intent"
                ),
                migrations.RenameField(
                    "officialcompanylistintent", "account", "native_account_id"
                ),
                migrations.AlterField(
                    "officialcompanylistintent",
                    "native_account_id",
                    models.TextField(db_column="account_id", null=True, editable=False),
                ),
                migrations.AddField(
                    "officialcompanylistintent",
                    "account",
                    models.ForeignKey(
                        to="core.account",
                        db_column="account_key",
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="official_list_intents",
                    ),
                ),
                migrations.AddConstraint(
                    "officialcompanylistintent",
                    models.UniqueConstraint(
                        fields=("list_id", "account"), name="uq_official_co_list_intent"
                    ),
                ),
            ],
        ),
    ]
