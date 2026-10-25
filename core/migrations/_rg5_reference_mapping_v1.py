"""Frozen bounded reference bridge used only by the RG5 forward migrations."""

import hashlib

from django.db import transaction


def bridge_name(table, old):
    return "pw_rg5_ref_" + hashlib.sha256(f"{table}.{old}".encode()).hexdigest()[:12]


def install_and_map(
    connection,
    *,
    table,
    old,
    new,
    catalogue,
    pk="id",
    source_sql=None,
    owner_columns=(),
    gating=False,
    required=False,
    subject_kind_sql=None,
    immutable_trigger=None,
):
    """All identifiers/expressions come from frozen migration declarations."""
    name = bridge_name(table, old)
    constraint = name + "_fk"
    old_code = f"NEW.{old}"
    empty_is_null = source_sql and catalogue not in {
        "account_verification_types",
        "source_identifier_namespaces",
    }
    if empty_is_null:
        old_code = f"NULLIF(NEW.{old}, '')"
    if gating:
        old_code = f"CASE NEW.{old} WHEN 'False' THEN 'public' WHEN 'True' THEN 'gated' ELSE NEW.{old} END"
    legacy_code = "resolved_code"
    if table == "products" and gating:
        legacy_code = "CASE resolved_code WHEN 'public' THEN 'False' WHEN 'gated' THEN 'True' ELSE resolved_code END"
    source_declaration = "source_key text;" if source_sql else ""
    source_assignment = f"source_key := ({source_sql});" if source_sql else ""
    source_predicate = " AND data_source_id=source_key" if source_sql else ""
    if subject_kind_sql:
        source_declaration += " subject_kind_key text;"
        source_assignment += f" subject_kind_key := ({subject_kind_sql});"
        source_predicate += " AND subject_kind=subject_kind_key"
    source_guard = (
        """
    IF source_key IS NULL THEN
      RAISE EXCEPTION 'Reference owner has no source' USING ERRCODE='23514';
    END IF;
    """
        if source_sql
        else ""
    )
    register_code = (
        f"""
    INSERT INTO {catalogue}(data_source_id,code) VALUES(source_key,requested_code)
      ON CONFLICT(data_source_id,code) DO NOTHING;
    """
        if source_sql
        else ""
    )
    if subject_kind_sql:
        register_code = f"""
    INSERT INTO {catalogue}(data_source_id,subject_kind,code)
      VALUES(source_key,subject_kind_key,requested_code)
      ON CONFLICT(data_source_id,subject_kind,code) DO NOTHING;
    """
    trigger_columns = ",".join(dict.fromkeys((old, new, *owner_columns)))
    sql = f"""
CREATE OR REPLACE FUNCTION {name}() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE requested_code text; resolved_code text; resolved_id bigint; {source_declaration}
BEGIN
  {source_assignment}
  IF NEW.{old} IS NOT NULL OR NEW.{new} IS NOT NULL THEN {source_guard} END IF;
  IF (TG_OP='UPDATE' AND NEW.{old} IS DISTINCT FROM OLD.{old}
      AND NEW.{new} IS NOT DISTINCT FROM OLD.{new}) OR NEW.{new} IS NULL THEN
    requested_code := {old_code};
    IF TG_OP='UPDATE' AND NEW.{new} IS DISTINCT FROM OLD.{new}
        AND NEW.{old} IS NOT DISTINCT FROM OLD.{old} THEN
      requested_code := NULL;
      NEW.{old} := NULL;
    END IF;
    IF requested_code IS NULL THEN
      NEW.{new} := NULL;
    ELSE
      SELECT id INTO resolved_id FROM {catalogue} WHERE code=requested_code {source_predicate};
      IF resolved_id IS NULL THEN
        {register_code}
        SELECT id INTO resolved_id FROM {catalogue} WHERE code=requested_code {source_predicate};
      END IF;
      IF resolved_id IS NULL THEN
        RAISE EXCEPTION 'Unregistered {table}.{old}' USING ERRCODE='23514';
      END IF;
      NEW.{new} := resolved_id;
    END IF;
  ELSE
    SELECT code INTO resolved_code FROM {catalogue} WHERE id=NEW.{new} {source_predicate};
    IF resolved_code IS NULL THEN
      RAISE EXCEPTION 'Invalid or cross-source {table}.{new}' USING ERRCODE='23514';
    END IF;
    IF (TG_OP='INSERT' AND NEW.{old} IS NOT NULL
        OR TG_OP='UPDATE' AND NEW.{old} IS DISTINCT FROM OLD.{old})
        AND ({old_code}) IS DISTINCT FROM resolved_code THEN
      RAISE EXCEPTION 'Conflicting {table}.{old} representations' USING ERRCODE='23514';
    END IF;
    NEW.{old} := {legacy_code};
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER {name} BEFORE INSERT OR UPDATE OF {trigger_columns} ON {table}
  FOR EACH ROW EXECUTE FUNCTION {name}();
"""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT EXISTS (SELECT 1 FROM pg_trigger WHERE tgrelid=%s::regclass AND tgname=%s)",
            [table, name],
        )
        installed = cursor.fetchone()[0]
        if installed:
            cursor.execute(
                "SELECT t.tgenabled='O' AND t.tgtype=23 "
                "AND a.atttypid='bigint'::regtype "
                "AND c.contype='f' AND c.confrelid=%s::regclass "
                "AND c.conkey=ARRAY[a.attnum] AND c.condeferrable AND c.condeferred "
                "AND i.indisvalid AND i.indnkeyatts=1 AND i.indkey[0]=a.attnum "
                "FROM pg_trigger t "
                "JOIN pg_attribute a ON a.attrelid=t.tgrelid AND a.attname=%s "
                "JOIN pg_constraint c ON c.conrelid=t.tgrelid AND c.conname=%s "
                "JOIN pg_index i ON i.indrelid=t.tgrelid AND i.indexrelid=%s::regclass "
                "WHERE t.tgrelid=%s::regclass AND t.tgname=%s",
                [catalogue, new, constraint, name + "_idx", table, name],
            )
            if cursor.fetchone() != (True,):
                raise RuntimeError(f"Unsafe reference bridge resume: {table}.{old}")
    if not installed:
        with transaction.atomic(using=connection.alias), connection.cursor() as cursor:
            cursor.execute(
                "SET LOCAL lock_timeout='2s'; SET LOCAL statement_timeout='30s'"
            )
            if immutable_trigger:
                cursor.execute(f"LOCK TABLE {table} IN SHARE ROW EXCLUSIVE MODE")
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {new} bigint")
            cursor.execute(
                f"ALTER TABLE {table} ADD CONSTRAINT {constraint} FOREIGN KEY ({new}) REFERENCES {catalogue}(id) DEFERRABLE INITIALLY DEFERRED NOT VALID"
            )
            cursor.execute(f"CREATE INDEX {name}_idx ON {table}({new})")
            cursor.execute(sql)
    else:
        # Recreate only the function within the short setup transaction. The
        # validated trigger, reference and index remain installed during resume.
        with transaction.atomic(using=connection.alias), connection.cursor() as cursor:
            cursor.execute(
                "SET LOCAL lock_timeout='2s'; SET LOCAL statement_timeout='30s'"
            )
            cursor.execute(sql.split("CREATE TRIGGER", 1)[0])
    after = None
    while True:
        with transaction.atomic(using=connection.alias), connection.cursor() as cursor:
            cursor.execute(
                "SET LOCAL lock_timeout='2s'; SET LOCAL statement_timeout='30s'"
            )
            if immutable_trigger:
                cursor.execute(f"LOCK TABLE {table} IN SHARE ROW EXCLUSIVE MODE")
            cursor.execute(
                f"SELECT {pk} FROM {table} WHERE {new} IS NULL AND {old} IS NOT NULL "
                + (f"AND {old}<>'' " if empty_is_null else "")
                + (f"AND {pk}>%s " if after is not None else "")
                + f"ORDER BY {pk} LIMIT 500 FOR UPDATE",
                [after] if after is not None else [],
            )
            ids = [r[0] for r in cursor.fetchall()]
            if not ids:
                break
            # The bridge resolves exactly the locked original value. It never
            # replays a stale code over a reference corrected by a current writer.
            if immutable_trigger:
                cursor.execute(
                    f"ALTER TABLE {table} DISABLE TRIGGER {immutable_trigger}"
                )
            cursor.execute(f"UPDATE {table} SET {new}={new} WHERE {pk}=ANY(%s)", [ids])
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
            if immutable_trigger:
                cursor.execute(
                    f"ALTER TABLE {table} ENABLE TRIGGER {immutable_trigger}"
                )
            after = ids[-1]
        print(f"RG5 {table}.{old}: mapped {len(ids)} through {after}", flush=True)
    with transaction.atomic(using=connection.alias), connection.cursor() as cursor:
        cursor.execute("SET LOCAL lock_timeout='2s'; SET LOCAL statement_timeout='60s'")
        expected_code = old_code.replace("NEW.", "rg5_owner.")
        source_check = (
            (
                " OR c.data_source_id IS DISTINCT FROM ("
                + source_sql.replace("NEW.", "rg5_owner.")
                + ")"
            )
            if source_sql
            else ""
        )
        if subject_kind_sql:
            source_check += (
                " OR c.subject_kind IS DISTINCT FROM ("
                + subject_kind_sql.replace("NEW.", "rg5_owner.")
                + ")"
            )
        cursor.execute(
            f"SELECT count(*) FROM {table} rg5_owner LEFT JOIN {catalogue} c ON c.id=rg5_owner.{new} "
            f"WHERE c.code IS DISTINCT FROM ({expected_code}) "
            + (
                f"OR (rg5_owner.{new} IS NOT NULL AND (false {source_check}))"
                if source_sql
                else ""
            )
        )
        if cursor.fetchone()[0]:
            raise RuntimeError(f"Reference mapping mismatch: {table}.{old}")
        cursor.execute(f"ALTER TABLE {table} VALIDATE CONSTRAINT {constraint}")
        if required:
            cursor.execute(f"ALTER TABLE {table} ALTER COLUMN {new} SET NOT NULL")
