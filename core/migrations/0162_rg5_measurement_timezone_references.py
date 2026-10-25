"""Bounded timezone mapping; physical deletion follows the application cutover."""

import django.db.models.deletion
from django.db import migrations, models, transaction

# ruff: noqa: RUF012
DOMAINS = (
    ("metric_values", "source_timezone", "source_timezone_id"),
    ("collection_corrections", "before_source_timezone", "before_source_timezone_id"),
    ("collection_corrections", "after_source_timezone", "after_source_timezone_id"),
)


def bridge_sql(table, old, new):
    # Attribution corrections have no timing state. Timing corrections serialize
    # their absent canonical timezone as the original explicit "unknown" token.
    fallback = (
        "'unknown'"
        if table == "metric_values"
        else (
            f"CASE WHEN NEW.{old.removesuffix('source_timezone')}temporal_status IS NULL "
            "THEN NULL ELSE 'unknown' END"
        )
    )
    return f"""
CREATE FUNCTION pw_rg5_{old}_bridge() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP='UPDATE' AND NEW.{old} IS DISTINCT FROM OLD.{old}
      AND NEW.{new} IS NOT DISTINCT FROM OLD.{new} THEN
    NEW.{new} := nullif(NEW.{old},'unknown');
  ELSIF TG_OP='UPDATE' AND NEW.{new} IS DISTINCT FROM OLD.{new} THEN
    IF NEW.{old} IS DISTINCT FROM OLD.{old}
       AND nullif(NEW.{old},'unknown') IS DISTINCT FROM NEW.{new} THEN
      RAISE EXCEPTION 'Conflicting timezone representations' USING ERRCODE='23514';
    END IF;
    NEW.{old} := coalesce(NEW.{new},{fallback});
  ELSIF NEW.{new} IS NULL THEN
    NEW.{new} := nullif(NEW.{old},'unknown');
    NEW.{old} := coalesce(NEW.{old},{fallback});
  ELSE
    IF NEW.{old} IS NOT NULL AND nullif(NEW.{old},'unknown') IS DISTINCT FROM NEW.{new} THEN
      RAISE EXCEPTION 'Conflicting timezone representations' USING ERRCODE='23514';
    END IF;
    NEW.{old} := NEW.{new};
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER pw_rg5_{old}_bridge BEFORE INSERT OR UPDATE OF {old},{new}
ON {table} FOR EACH ROW EXECUTE FUNCTION pw_rg5_{old}_bridge();
"""


def expand_and_map(apps, schema_editor):
    connection = schema_editor.connection
    for table, old, new in DOMAINS:
        constraint = f"fk_rg5_{table}_{new}"
        trigger = f"pw_rg5_{old}_bridge"
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT EXISTS (SELECT 1 FROM pg_trigger WHERE tgrelid=%s::regclass "
                "AND tgname=%s AND NOT tgisinternal)",
                [table, trigger],
            )
            installed = cursor.fetchone()[0]
            if installed:
                cursor.execute(
                    "SELECT t.tgenabled='O' AND t.tgtype=23 "
                    "AND a.atttypid='varchar'::regtype AND a.atttypmod=68 "
                    "AND c.contype='f' AND c.confrelid='time_zones'::regclass "
                    "AND c.conkey=ARRAY[a.attnum] AND c.condeferrable AND c.condeferred "
                    "FROM pg_trigger t "
                    "JOIN pg_attribute a ON a.attrelid=t.tgrelid AND a.attname=%s "
                    "JOIN pg_constraint c ON c.conrelid=t.tgrelid AND c.conname=%s "
                    "WHERE t.tgrelid=%s::regclass AND t.tgname=%s",
                    [new, constraint, table, trigger],
                )
                if cursor.fetchone() != (True,):
                    raise RuntimeError(f"Unsafe timezone bridge resume: {table}.{old}")
        if not installed:
            # One short atomic setup; retries reuse an already installed bridge.
            with (
                transaction.atomic(using=connection.alias),
                connection.cursor() as cursor,
            ):
                cursor.execute(
                    "SET LOCAL lock_timeout='2s'; SET LOCAL statement_timeout='30s'"
                )
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {new} varchar(64)")
                cursor.execute(
                    f"ALTER TABLE {table} ADD CONSTRAINT {constraint} FOREIGN KEY ({new}) "
                    "REFERENCES time_zones(code) DEFERRABLE INITIALLY DEFERRED NOT VALID"
                )
                cursor.execute(bridge_sql(table, old, new))
        after = None
        while True:
            with (
                transaction.atomic(using=connection.alias),
                connection.cursor() as cursor,
            ):
                cursor.execute(
                    "SET LOCAL lock_timeout='2s'; SET LOCAL statement_timeout='30s'"
                )
                if table == "collection_corrections":
                    # History refuses every UPDATE. Suspend only under its table
                    # lock; both success and rollback restore the guard.
                    cursor.execute(f"LOCK TABLE {table} IN SHARE ROW EXCLUSIVE MODE")
                cursor.execute(
                    f"SELECT id FROM {table} WHERE {new} IS NULL AND {old} IS NOT NULL "
                    f"AND {old}<>'unknown' "
                    + ("AND id>%s " if after is not None else "")
                    + "ORDER BY id LIMIT 500 FOR UPDATE",
                    [after] if after is not None else [],
                )
                ids = [r[0] for r in cursor.fetchall()]
                if not ids:
                    break
                if table == "collection_corrections":
                    cursor.execute(
                        f"ALTER TABLE {table} DISABLE TRIGGER collection_correction_guard"
                    )
                cursor.execute(
                    f"UPDATE {table} SET {new}={old} WHERE id=ANY(%s)", [ids]
                )
                cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
                if table == "collection_corrections":
                    cursor.execute(
                        f"ALTER TABLE {table} ENABLE TRIGGER collection_correction_guard"
                    )
                after = ids[-1]
            print(f"RG5 {table}.{old}: mapped {len(ids)} through {after}", flush=True)
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT count(*) FROM {table} WHERE {new} IS DISTINCT FROM nullif({old},'unknown')"
            )
            if cursor.fetchone()[0]:
                raise RuntimeError(f"Timezone mapping mismatch: {table}.{old}")
        with transaction.atomic(using=connection.alias), connection.cursor() as cursor:
            cursor.execute(
                "SET LOCAL lock_timeout='2s'; SET LOCAL statement_timeout='60s'"
            )
            cursor.execute(f"ALTER TABLE {table} VALIDATE CONSTRAINT {constraint}")


class Migration(migrations.Migration):
    atomic = False
    dependencies = [("core", "0161_rg5_vocabularies_expand")]
    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[migrations.RunPython(expand_and_map)],
            state_operations=[
                migrations.RemoveField(
                    model_name="metricvalue", name="source_timezone"
                ),
                migrations.RemoveField(
                    model_name="collectioncorrection", name="before_source_timezone"
                ),
                migrations.RemoveField(
                    model_name="collectioncorrection", name="after_source_timezone"
                ),
                migrations.AddField(
                    model_name="metricvalue",
                    name="source_timezone_reference",
                    field=models.ForeignKey(
                        db_column="source_timezone_id",
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        to="core.timezone",
                    ),
                ),
                migrations.AddField(
                    model_name="collectioncorrection",
                    name="before_source_timezone_reference",
                    field=models.ForeignKey(
                        db_column="before_source_timezone_id",
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="corrections_before",
                        to="core.timezone",
                    ),
                ),
                migrations.AddField(
                    model_name="collectioncorrection",
                    name="after_source_timezone_reference",
                    field=models.ForeignKey(
                        db_column="after_source_timezone_id",
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="corrections_after",
                        to="core.timezone",
                    ),
                ),
            ],
        ),
    ]
