"""Keep geography writes from reconstructing unrelated source payloads."""

import re
import time

from django.db import OperationalError, transaction

OWNERS = (
    ("accounts", "account_key", "location", "reported_profile_location", "profile_location_id", "freeform"),
    ("x_account_details", "account_key", "account_based_in", "reported_based_in", "", "based_in"),
    ("posts", "tweet_id", "author_location", "reported_author_location", "author_geolocation_id", "freeform"),
    ("account_profile_snapshots", "id", "location", "reported_location", "geolocation_id", "freeform"),
    ("people_brand_affiliations", "id", "location", "reported_location", "geolocation_id", "freeform"),
)


def trigger_matches(connection, table, name, function, event_type, *, columns=(), arguments=(), condition=None):
    """Avoid taking table DDL locks when a resumable setup is already exact."""
    with connection.cursor() as cursor:
        cursor.execute("""SELECT t.tgtype,t.tgenabled,t.tgargs,t.tgoldtable,t.tgnewtable,
            p.proname,p.pronamespace=c.relnamespace,
            ARRAY(SELECT a.attname FROM unnest(t.tgattr::smallint[]) WITH ORDINALITY v(num,pos)
                JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum=v.num ORDER BY v.pos),
            pg_get_triggerdef(t.oid),t.tgconstraint
            FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
            JOIN pg_proc p ON p.oid=t.tgfoid
            WHERE t.tgrelid=%s::regclass AND t.tgname=%s AND NOT t.tgisinternal""", [table, name])
        row = cursor.fetchone()
    if row is None:
        return False
    when = re.search(r" WHEN (.+) EXECUTE FUNCTION ", row[8])
    encoded_arguments = b"".join(value.encode() + b"\0" for value in arguments)
    return (
        row[:2] == (event_type, "O") and bytes(row[2]) == encoded_arguments
        and row[3:5] == (None, None) and row[5:7] == (function, True)
        and row[7] == list(columns) and not row[9]
        and (when.group(1) if when else None) == condition
    )


def prepare_post_index(connection, table, *, phase="initial"):
    """Drain old GIN maintenance work before acquiring source-row locks.

    GIN pending cleanup is physical index maintenance, not a source-data edit.
    Cleanup has a separate bounded allowance; ordinary mapping statements
    retain their 30-second limit and commit before periodic maintenance.
    """
    if table != "posts":
        return
    if connection.in_atomic_block:
        raise RuntimeError("Post index maintenance must run after source-row locks are released")
    for attempt in range(3):
        try:
            with transaction.atomic(using=connection.alias), connection.cursor() as cursor:
                cursor.execute("SET LOCAL lock_timeout='5s'; SET LOCAL statement_timeout='180s'")
                cursor.execute("SELECT gin_clean_pending_list('idx_posts_editorial_context'::regclass)")
                pages = cursor.fetchone()[0]
        except OperationalError as error:
            if getattr(error.__cause__, "sqlstate", None) != "55P03" or attempt == 2:
                raise
            # The failed maintenance transaction has rolled back. No source
            # rows are locked while another index maintainer finishes.
            print(f"RG4 posts: maintenance lock busy; retry={attempt + 1}/2", flush=True)
            time.sleep(attempt + 1)
        else:
            break
    print(f"RG4 posts: {phase} search-index pending pages cleaned={pages}", flush=True)


def finish_post_batch(connection, table, pending_rows, changed_rows=0, *, finish=False):
    """Bound queued index work, cleaning only after source writes commit.

    A cleanup can exceed the ordinary write timeout on a small database. It
    has its own allowance and never extends source-row lock ownership. If it
    fails, committed source batches survive and the next run cleans first.
    """
    if table != "posts":
        return 0
    pending_rows += changed_rows
    if pending_rows >= 500 or (finish and pending_rows):
        prepare_post_index(connection, table, phase="batch")
        return 0
    return pending_rows


def write_batch_options(cursor, table):
    cursor.execute("SET LOCAL lock_timeout='5s'; SET LOCAL statement_timeout='30s'")
    if table == "posts":
        # Explicit cleanup runs every 500 changed rows, outside their locks.
        # Leave headroom so ordinary 100-row writes do not trigger it inline.
        # This affects only this transaction, not index options/other writers.
        cursor.execute("SET LOCAL gin_pending_list_limit='64MB'")


def identity_triggers(schema_editor):
    """Keep native/generic identity checks on inserts and either identity update."""
    for table, native, generic, source in (
        ("posts", "author_id", "author_account_key", "x"),
        ("account_profile_snapshots", "author_id", "account_key", "any"),
    ):
        if trigger_matches(schema_editor.connection, table, "benchmark_account_link",
                "benchmark_account_link_compatibility", 23, columns=(native, generic),
                arguments=(native, generic, source)):
            continue
        schema_editor.execute(f'DROP TRIGGER benchmark_account_link ON "{table}"')
        schema_editor.execute(f"""CREATE TRIGGER benchmark_account_link
            BEFORE INSERT OR UPDATE OF "{native}","{generic}" ON "{table}"
            FOR EACH ROW EXECUTE FUNCTION benchmark_account_link_compatibility('{native}','{generic}','{source}')""")


def source_bridge_sql():
    """Direct field assignment retains unrelated toasted payloads unchanged."""
    incoming = []
    previous = []
    outgoing = []
    for table, _pk, old, new, field, context in OWNERS:
        incoming.append(f"WHEN '{table}' THEN old_value:=NEW.{old}; new_value:=NEW.{new};")
        previous.append(f"WHEN '{table}' THEN before_value:=OLD.{old}; before_new:=OLD.{new};")
        assignment = f"WHEN '{table}' THEN NEW.{old}:=chosen; NEW.{new}:=chosen;"
        if field:
            assignment += f" IF source_changed THEN NEW.{field}:=pw_geo_source_id(chosen,'{context}'); END IF;"
        outgoing.append(assignment)
    return f"""
CREATE OR REPLACE FUNCTION pw_geo_reported_bridge() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE before_value text; before_new text; old_value text; new_value text;
        chosen text; source_changed boolean;
BEGIN
  CASE TG_TABLE_NAME {' '.join(incoming)}
    ELSE RAISE EXCEPTION 'unsupported geography source owner'; END CASE;
  IF TG_OP='INSERT' THEN
    IF old_value IS NOT NULL AND new_value IS NOT NULL AND old_value IS DISTINCT FROM new_value THEN
      RAISE EXCEPTION 'conflicting location source representations' USING ERRCODE='23514';
    END IF;
    chosen:=COALESCE(new_value,old_value);
    source_changed:=chosen IS NOT NULL;
  ELSE
    CASE TG_TABLE_NAME {' '.join(previous)}
      ELSE RAISE EXCEPTION 'unsupported geography source owner'; END CASE;
    IF old_value IS DISTINCT FROM before_value AND new_value IS DISTINCT FROM before_new
       AND old_value IS DISTINCT FROM new_value THEN
      RAISE EXCEPTION 'conflicting location source representations' USING ERRCODE='23514';
    END IF;
    IF new_value IS DISTINCT FROM before_new THEN chosen:=new_value;
    ELSIF old_value IS DISTINCT FROM before_value THEN chosen:=old_value;
    ELSE chosen:=COALESCE(new_value,old_value); END IF;
    source_changed:=chosen IS DISTINCT FROM before_value;
  END IF;
  CASE TG_TABLE_NAME {' '.join(outgoing)}
    ELSE RAISE EXCEPTION 'unsupported geography source owner'; END CASE;
  RETURN NEW;
END $$;
"""


def reported_triggers(schema_editor):
    schema_editor.execute(source_bridge_sql())
    for table, _pk, old, new, field, context in OWNERS:
        if trigger_matches(schema_editor.connection, table, "pw_geo_reported_bridge",
                "pw_geo_reported_bridge", 23, columns=(old, new), arguments=(old, new, field, context)):
            continue
        args = ",".join("'" + part + "'" for part in (old, new, field, context))
        schema_editor.execute(f'DROP TRIGGER IF EXISTS pw_geo_reported_bridge ON "{table}"')
        schema_editor.execute(f"""CREATE TRIGGER pw_geo_reported_bridge
            BEFORE INSERT OR UPDATE OF "{old}","{new}" ON "{table}"
            FOR EACH ROW EXECUTE FUNCTION pw_geo_reported_bridge({args})""")


def install(apps, schema_editor):
    schema_editor.execute("SET LOCAL lock_timeout='5s'; SET LOCAL statement_timeout='30s'")
    # Acquire table locks in ingestion order: account, detail, post, snapshot.
    reported_triggers(schema_editor)
    identity_triggers(schema_editor)
