"""Build saved Each facts with grouped joins; keep the live source unchanged."""

from importlib import import_module
from typing import ClassVar

from django.db import migrations

# Frozen migration definitions only. The ordinary source view is the parity
# oracle and must not be rewritten when optimizing the rebuildable copy.
_ORIGINAL = import_module("core.migrations.0228_each_chart_facts")
ORIGINAL_SELECT = _ORIGINAL.VIEW_SQL.split(
    "CREATE MATERIALIZED VIEW each_brand_post_facts AS\n", 1
)[1].split("\nWITH NO DATA;", 1)[0]

GROUPED_SELECT = r"""
WITH post_types AS (
    SELECT g.post_id, g.brand_id,
        array_agg(DISTINCT g.post_type_key::text COLLATE "C"
                  ORDER BY g.post_type_key::text COLLATE "C") AS keys
    FROM posts_brands_signals g GROUP BY g.post_id, g.brand_id
), legacy_spelling AS (
    SELECT g.post_id, g.brand_id::text COLLATE "C" AS spelling,
        CASE WHEN count(DISTINCT nullif(g.sentiment::text, '') COLLATE "C")=1
             THEN min(nullif(g.sentiment::text, '') COLLATE "C") END AS sentiment
    FROM posts_brands_signals g
    GROUP BY g.post_id, g.brand_id::text COLLATE "C"
), legacy AS (
    SELECT post_id, spelling COLLATE case_insensitive AS brand_id,
        array_agg(spelling COLLATE "C" ORDER BY spelling COLLATE "C") AS brand_ids,
        array_agg(sentiment COLLATE "C" ORDER BY spelling COLLATE "C") AS sentiments
    FROM legacy_spelling GROUP BY post_id, spelling COLLATE case_insensitive
), labels AS (
    SELECT l.post_id, l.brand_id,
        array_agg(DISTINCT l.product_label_key::text COLLATE "C"
                  ORDER BY l.product_label_key::text COLLATE "C") AS keys
    FROM posts_brands_product_labels l GROUP BY l.post_id, l.brand_id
), audience AS (
    SELECT a.post_id, a.brand_id,
        array_agg(DISTINCT (a.scheme_revision::text || ':' || a.concept_id::text) COLLATE "C"
                  ORDER BY (a.scheme_revision::text || ':' || a.concept_id::text) COLLATE "C") AS edges
    FROM posts_brands_audience_topics a WHERE a.scheme_key='ai_audience_topics/v1'
    GROUP BY a.post_id, a.brand_id
), geo AS (
    SELECT g.post_id, g.brand_id,
        array_agg(g.taxonomy_version::text
                  ORDER BY g.taxonomy_version COLLATE "C",g.geopolitical_mode_key COLLATE "C") AS versions,
        array_agg(g.geopolitical_mode_key::text
                  ORDER BY g.taxonomy_version COLLATE "C",g.geopolitical_mode_key COLLATE "C") AS keys
    FROM posts_brands_geopolitical_modes g GROUP BY g.post_id, g.brand_id
), promotions AS (
    SELECT u.post_id,
        array_agg(item #>> '{}' ORDER BY (item #>> '{}') COLLATE "C") AS keys
    FROM posts_untracked_brand_promotions u
    CROSS JOIN LATERAL jsonb_array_elements(
        CASE WHEN jsonb_typeof(u.promotion_keys)='array'
             THEN u.promotion_keys ELSE '[]'::jsonb END
    ) item
    WHERE jsonb_typeof(item)='string' GROUP BY u.post_id
)
SELECT pb.brand_id, pb.post_id, p.created_at, p.lang_detected, p.lang,
    p.author_account_key, (s.post_id IS NOT NULL) AS state_present,
    s.brand_id::text AS state_brand_id,
    s.contract_version AS state_contract_version,
    s.taxonomy_version AS state_taxonomy_version,
    s.outcome AS state_outcome, s.sentiment::text AS state_sentiment,
    COALESCE(legacy.brand_ids, ARRAY[]::text[]) AS legacy_sentiment_brand_ids,
    COALESCE(legacy.sentiments, ARRAY[]::text[]) AS legacy_sentiment_values,
    COALESCE(post_types.keys, ARRAY[]::text[]) AS post_type_keys,
    COALESCE(labels.keys, ARRAY[]::text[]) AS product_label_keys,
    COALESCE(audience.edges, ARRAY[]::text[]) AS audience_topic_edges,
    COALESCE(geo.versions, ARRAY[]::text[]) AS geopolitical_mode_versions,
    COALESCE(geo.keys, ARRAY[]::text[]) AS geopolitical_mode_keys,
    COALESCE(promotions.keys, ARRAY[]::text[]) AS promotion_keys
FROM posts_brands pb JOIN posts p ON p.tweet_id=pb.post_id
LEFT JOIN posts_brands_classification_states s
    ON s.post_id=pb.post_id AND s.brand_id=pb.brand_id
LEFT JOIN post_types ON post_types.post_id=pb.post_id AND post_types.brand_id=pb.brand_id
LEFT JOIN legacy ON legacy.post_id=pb.post_id AND legacy.brand_id=pb.brand_id
LEFT JOIN labels ON labels.post_id=pb.post_id AND labels.brand_id=pb.brand_id
LEFT JOIN audience ON audience.post_id=pb.post_id AND audience.brand_id=pb.brand_id
LEFT JOIN geo ON geo.post_id=pb.post_id AND geo.brand_id=pb.brand_id
LEFT JOIN promotions ON promotions.post_id=pb.post_id
WHERE p.created_at < date_trunc('day', transaction_timestamp(), 'UTC') - interval '1 day'
"""


def replace_saved_view(schema_editor, select_sql):
    """Replace atomically, retaining access and explicitly withdrawing publication.

    No CASCADE and a short lock limit keep dependent objects/readers safe. A
    failure rolls the entire migration back, including the old view and state.
    Both directions create WITH NO DATA: only a later successful native refresh
    may publish the replacement. Historical invalidation generations stay intact.
    """
    db = schema_editor.connection
    quote = db.ops.quote_name
    with db.cursor() as cursor:
        cursor.execute("SET LOCAL lock_timeout = '2s'")
        cursor.execute(
            "SELECT pg_get_userbyid(relowner) "
            "FROM pg_class WHERE oid='each_brand_post_facts'::regclass"
        )
        owner = cursor.fetchone()[0]
        cursor.execute(
            "SELECT CASE WHEN a.grantee=0 THEN NULL ELSE pg_get_userbyid(a.grantee) END, "
            "a.privilege_type,a.is_grantable,pg_get_userbyid(a.grantor) FROM pg_class c "
            "CROSS JOIN LATERAL aclexplode(coalesce(c.relacl,acldefault('r',c.relowner))) a "
            "WHERE c.oid='each_brand_post_facts'::regclass"
        )
        table_grants = cursor.fetchall()
        cursor.execute(
            "SELECT col.attname, "
            "CASE WHEN a.grantee=0 THEN NULL ELSE pg_get_userbyid(a.grantee) END, "
            "a.privilege_type,a.is_grantable,pg_get_userbyid(a.grantor) FROM pg_attribute col "
            "CROSS JOIN LATERAL aclexplode(col.attacl) a "
            "WHERE col.attrelid='each_brand_post_facts'::regclass "
            "AND col.attnum>0 AND NOT col.attisdropped"
        )
        column_grants = cursor.fetchall()
        cursor.execute("SELECT current_user")
        migration_role = cursor.fetchone()[0]
        if owner != migration_role:
            raise RuntimeError(
                "Each facts rebuild requires the migration role to own the view; "
                f"current role={migration_role!r}, owner={owner!r}"
            )
        foreign_grantors = sorted(
            {
                row[-1]
                for row in (*table_grants, *column_grants)
                if row[-1] != migration_role
            }
        )
        if foreign_grantors:
            # Object GRANTED BY requires the current user. Changing roles or
            # rewriting a delegated grant chain would change access semantics.
            # Reject before DROP so an operator can choose the proper authority.
            raise RuntimeError(
                "Each facts rebuild cannot preserve existing grantors under "
                f"current role={migration_role!r}, owner={owner!r}; "
                f"existing grantors={foreign_grantors!r}"
            )
        cursor.execute("DROP MATERIALIZED VIEW each_brand_post_facts")
        cursor.execute(
            "CREATE MATERIALIZED VIEW each_brand_post_facts AS "
            + select_sql
            + " WITH NO DATA"
        )
        cursor.execute(
            "CREATE UNIQUE INDEX each_brand_post_facts_key "
            "ON each_brand_post_facts(brand_id,post_id)"
        )
        cursor.execute(
            "CREATE INDEX each_brand_post_facts_window "
            "ON each_brand_post_facts(brand_id,created_at)"
        )
        cursor.execute(
            "ALTER MATERIALIZED VIEW each_brand_post_facts OWNER TO " + quote(owner)
        )
        # Creation-time default privileges may have changed since the old view
        # was installed. Remove all new defaults, including unrelated roles,
        # before restoring the exact old privilege/grant-option/grantor tuples.
        cursor.execute(
            "SELECT DISTINCT a.grantee FROM pg_class c CROSS JOIN LATERAL "
            "aclexplode(coalesce(c.relacl,acldefault('r',c.relowner))) a "
            "WHERE c.oid='each_brand_post_facts'::regclass"
        )
        new_grantees = [row[0] for row in cursor.fetchall()]
        for grantee in new_grantees:
            if grantee == 0:
                target = "PUBLIC"
            else:
                cursor.execute("SELECT pg_get_userbyid(%s)", [grantee])
                target = quote(cursor.fetchone()[0])
            cursor.execute("REVOKE ALL ON each_brand_post_facts FROM " + target)
        for role, privilege, grantable, grantor in table_grants:
            target = "PUBLIC" if role is None else quote(role)
            cursor.execute(
                f"GRANT {privilege} ON each_brand_post_facts TO {target}"
                + (" WITH GRANT OPTION" if grantable else "")
                + " GRANTED BY "
                + quote(grantor)
            )
        for column, role, privilege, grantable, grantor in column_grants:
            target = "PUBLIC" if role is None else quote(role)
            cursor.execute(
                f"GRANT {privilege} ({quote(column)}) ON each_brand_post_facts TO {target}"
                + (" WITH GRANT OPTION" if grantable else "")
                + " GRANTED BY "
                + quote(grantor)
            )
        cursor.execute(
            "UPDATE materialization_state SET published_generation=NULL, "
            "cutoff=NULL,refreshed_at=NULL WHERE dataset_key='each.brand_post_facts.v1'"
        )


def forwards(apps, schema_editor):
    replace_saved_view(schema_editor, GROUPED_SELECT)


def backwards(apps, schema_editor):
    replace_saved_view(schema_editor, ORIGINAL_SELECT)


class Migration(migrations.Migration):
    dependencies: ClassVar[list] = [("core", "0231_merge_each_and_chatter")]
    operations: ClassVar[list] = [migrations.RunPython(forwards, backwards)]
