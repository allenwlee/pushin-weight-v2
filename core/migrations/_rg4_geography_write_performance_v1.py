"""Keep geography writes from reconstructing unrelated source payloads."""

from django.db import transaction

OWNERS = (
    ("accounts", "account_key", "location", "reported_profile_location", "profile_location_id", "freeform"),
    ("x_account_details", "account_key", "account_based_in", "reported_based_in", "", "based_in"),
    ("posts", "tweet_id", "author_location", "reported_author_location", "author_geolocation_id", "freeform"),
    ("account_profile_snapshots", "id", "location", "reported_location", "geolocation_id", "freeform"),
    ("people_brand_affiliations", "id", "location", "reported_location", "geolocation_id", "freeform"),
)


def prepare_post_index(connection, table):
    """Drain old GIN maintenance work before acquiring source-row locks.

    GIN pending cleanup is physical index maintenance, not a source-data edit.
    Its initial backlog has a separate bounded allowance; ordinary mapping
    statements retain their 30-second limit and smaller pending-list threshold.
    """
    if table != "posts":
        return
    with transaction.atomic(using=connection.alias), connection.cursor() as cursor:
        cursor.execute("SET LOCAL lock_timeout='5s'; SET LOCAL statement_timeout='180s'")
        cursor.execute("SELECT gin_clean_pending_list('idx_posts_editorial_context'::regclass)")
        pages = cursor.fetchone()[0]
    print(f"RG4 posts: initial search-index pending pages cleaned={pages}", flush=True)


def write_batch_options(cursor, table):
    cursor.execute("SET LOCAL lock_timeout='5s'; SET LOCAL statement_timeout='30s'")
    if table == "posts":
        # A full default 4MB cleanup exceeds the staging statement budget.
        # Keep its work small without changing the index or any other session.
        cursor.execute("SET LOCAL gin_pending_list_limit='64kB'")


def identity_triggers(schema_editor):
    """Keep native/generic identity checks on inserts and either identity update."""
    for table, native, generic, source in (
        ("posts", "author_id", "author_account_key", "x"),
        ("account_profile_snapshots", "author_id", "account_key", "any"),
    ):
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
