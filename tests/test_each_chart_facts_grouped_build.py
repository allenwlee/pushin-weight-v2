"""The grouped saved build preserves the unchanged source's physical facts."""

from datetime import timedelta
from importlib import import_module
from time import perf_counter
from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.db import connection, transaction

from core.models import (
    GeopoliticalModeKey,
    MaterializationState,
    PostBrandClassificationState,
    PostBrandGeopoliticalMode,
    PostBrandSignal,
    PostTypeKey,
    PostUntrackedBrandPromotion,
)
from tests import test_each_chart_facts as source_fixtures

NOW = source_fixtures.NOW
fact_brand = source_fixtures.fact_brand
positive_fact_cohort = source_fixtures.positive_fact_cohort

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]
DATASET = "each.brand_post_facts.v1"
MIGRATION = "core.migrations.0232_each_facts_grouped_build"


def relation_columns(name):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT attname,atttypid,atttypmod,attcollation,attnotnull "
            "FROM pg_attribute WHERE attrelid=%s::regclass "
            "AND attnum>0 AND NOT attisdropped ORDER BY attnum",
            [name],
        )
        return cursor.fetchall()


def assert_physical_parity():
    """One statement/snapshot compares both directions with byte-sensitive text.

    Row JSON is transient query output, never a new stored column. It avoids
    nondeterministic FK collations folding uppercase values during EXCEPT, and
    retains NULLs, array order and duplicate array entries exactly.
    """
    columns = import_module("core.migrations.0228_each_chart_facts").COLUMNS
    with connection.cursor() as cursor:
        cursor.execute(f"""
            WITH expected AS (
                SELECT {columns} FROM each_brand_post_facts_source
                WHERE created_at < date_trunc('day',transaction_timestamp(),'UTC') - interval '1 day'
            ), actual AS (SELECT {columns} FROM each_brand_post_facts),
            missing AS (
                SELECT row_to_json(e)::text COLLATE "C" FROM expected e
                EXCEPT ALL SELECT row_to_json(a)::text COLLATE "C" FROM actual a
            ), extra AS (
                SELECT row_to_json(a)::text COLLATE "C" FROM actual a
                EXCEPT ALL SELECT row_to_json(e)::text COLLATE "C" FROM expected e
            )
            SELECT (SELECT count(*) FROM expected),(SELECT count(*) FROM actual),
                   (SELECT count(*) FROM missing),(SELECT count(*) FROM extra)
        """)
        expected, actual, missing, extra = cursor.fetchone()
    assert expected > 0
    assert (actual, missing, extra) == (expected, 0, 0)
    assert relation_columns("each_brand_post_facts") == relation_columns(
        "each_brand_post_facts_source"
    )
    return expected


def refresh(concurrent=False):
    start = perf_counter()
    with connection.cursor() as cursor:
        cursor.execute(
            "REFRESH MATERIALIZED VIEW "
            + ("CONCURRENTLY " if concurrent else "")
            + "each_brand_post_facts"
        )
    return perf_counter() - start


def test_grouped_initial_and_concurrent_build_keep_physical_rows(
    fact_brand,
    positive_fact_cohort,
    record_property,
):
    from core.models import AudienceTopicConcept, PostBrandAudienceTopic

    # Binary brand/sentiment ownership, mixed-case raw aliases and NULL/conflict
    # scalar slots must survive grouping under case-insensitive FK collations.
    PostTypeKey.objects.get_or_create(key="other")
    PostBrandSignal.objects.create(
        post_id="each-facts-5",
        brand_id=fact_brand.pk.upper(),
        post_type_id="other",
        sentiment_id="positive",
    )
    PostBrandClassificationState.objects.filter(
        post_id="each-facts-4", brand=fact_brand
    ).update(brand_id=fact_brand.pk.upper(), sentiment_id="POSITIVE")
    for key, version in (
        ("reporting", "custom:u18a:two"),
        ("framework", "stage1-taxonomy-v4"),
    ):
        GeopoliticalModeKey.objects.get_or_create(key=key)
        PostBrandGeopoliticalMode.objects.create(
            post_id="each-facts-5",
            brand=fact_brand,
            geopolitical_mode_id=key,
            taxonomy_version=version,
        )
    concept, _ = AudienceTopicConcept.objects.get_or_create(
        scheme_id="ai_audience_topics/v1", key="grouped:unknown"
    )
    PostBrandAudienceTopic.objects.create(
        post_id="each-facts-5",
        brand=fact_brand,
        concept=concept,
        scheme_id="ai_audience_topics/v1",
        scheme_revision=12,
    )
    PostUntrackedBrandPromotion.objects.update_or_create(
        post_id="each-facts-5",
        defaults={
            "promotion_keys": ["spam", "spam", "Spam", None, 7, {"general": True}]
        },
    )

    migration = import_module(MIGRATION)
    # Explicitly exercise the new build even when test execution reuses a
    # database whose earlier MV was recreated by another migration scenario.
    migration.forwards(None, SimpleNamespace(connection=connection))
    first = refresh()
    first_rows = assert_physical_parity()
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT legacy_sentiment_brand_ids,legacy_sentiment_values,promotion_keys FROM each_brand_post_facts WHERE brand_id=%s AND post_id='each-facts-5'",
            [fact_brand.pk],
        )
        brands, sentiments, promotions = cursor.fetchone()
    assert brands == sorted([fact_brand.pk, fact_brand.pk.upper()])
    assert sentiments == ["positive", None]
    assert promotions == ["Spam", "spam", "spam"]
    PostBrandClassificationState.objects.filter(
        post_id="each-facts-5", brand=fact_brand
    ).update(sentiment_id="negative")
    subsequent = refresh(concurrent=True)
    assert assert_physical_parity() == first_rows
    record_property("grouped_fixture_initial_seconds", first)
    record_property("grouped_fixture_concurrent_seconds", subsequent)
    record_property("grouped_fixture_physical_rows", first_rows)
    assert first < 90 and subsequent < 90


def acl_snapshot():
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT relowner FROM pg_class WHERE oid='each_brand_post_facts'::regclass"
        )
        owner = cursor.fetchone()[0]
        cursor.execute(
            "SELECT a.grantor,a.grantee,a.privilege_type,a.is_grantable FROM pg_class c CROSS JOIN LATERAL aclexplode(coalesce(c.relacl,acldefault('r',c.relowner))) a WHERE c.oid='each_brand_post_facts'::regclass ORDER BY 1,2,3,4"
        )
        table = cursor.fetchall()
        cursor.execute(
            "SELECT col.attname,a.grantor,a.grantee,a.privilege_type,a.is_grantable FROM pg_attribute col CROSS JOIN LATERAL aclexplode(col.attacl) a WHERE col.attrelid='each_brand_post_facts'::regclass AND col.attnum>0 AND NOT col.attisdropped ORDER BY 1,2,3,4,5"
        )
        return owner, table, cursor.fetchall()


def test_replacement_and_reverse_keep_access_triggers_and_unpublish_truthfully(
    fact_brand,
):
    migration = import_module(MIGRATION)
    reader = "each_grouped_read_" + uuid4().hex[:12]
    future = "each_grouped_default_" + uuid4().hex[:12]
    quote = connection.ops.quote_name
    with connection.cursor() as cursor:
        cursor.execute("CREATE ROLE " + quote(reader) + " NOLOGIN")
        cursor.execute("CREATE ROLE " + quote(future) + " NOLOGIN")
        cursor.execute(
            "GRANT SELECT ON each_brand_post_facts TO "
            + quote(reader)
            + " WITH GRANT OPTION"
        )
        cursor.execute(
            "GRANT SELECT (lang_detected) ON each_brand_post_facts TO "
            + quote(reader)
            + " WITH GRANT OPTION"
        )
        # New default grants must not leak onto a replacement of an older view.
        cursor.execute(
            "ALTER DEFAULT PRIVILEGES GRANT SELECT ON TABLES TO " + quote(future)
        )
        cursor.execute(
            "SELECT 'each_brand_post_facts_source'::regclass::oid,pg_get_viewdef('each_brand_post_facts_source'::regclass)"
        )
        source_before = cursor.fetchone()
        cursor.execute(
            "SELECT tgrelid,tgname,tgfoid FROM pg_trigger WHERE tgname LIKE 'each_facts_%' ORDER BY 1,2"
        )
        triggers = cursor.fetchall()
    access = acl_snapshot()
    columns = relation_columns("each_brand_post_facts")
    for direction in (migration.forwards, migration.backwards, migration.forwards):
        refresh()
        state = MaterializationState.objects.get(pk=DATASET)
        state.published_generation = state.source_generation
        state.cutoff = NOW.replace(hour=0) - timedelta(days=1)
        state.refreshed_at = NOW
        state.save(update_fields=["published_generation", "cutoff", "refreshed_at"])
        before = (state.source_generation, state.dirty_since)
        direction(None, SimpleNamespace(connection=connection))
        state.refresh_from_db()
        assert (state.source_generation, state.dirty_since) == before
        assert (state.published_generation, state.cutoff, state.refreshed_at) == (
            None,
            None,
            None,
        )
        assert acl_snapshot() == access
        assert relation_columns("each_brand_post_facts") == columns
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT relispopulated FROM pg_class WHERE oid='each_brand_post_facts'::regclass"
            )
            assert cursor.fetchone() == (False,)
            cursor.execute(
                "SELECT 'each_brand_post_facts_source'::regclass::oid,pg_get_viewdef('each_brand_post_facts_source'::regclass)"
            )
            assert cursor.fetchone() == source_before
            cursor.execute(
                "SELECT tgrelid,tgname,tgfoid FROM pg_trigger WHERE tgname LIKE 'each_facts_%' ORDER BY 1,2"
            )
            assert cursor.fetchall() == triggers
            cursor.execute(
                "SELECT has_table_privilege(%s,'each_brand_post_facts','SELECT')",
                [future],
            )
            assert cursor.fetchone() == (False,)
            cursor.execute(
                "SELECT indexname FROM pg_indexes WHERE tablename='each_brand_post_facts' ORDER BY indexname"
            )
            assert cursor.fetchall() == [
                ("each_brand_post_facts_key",),
                ("each_brand_post_facts_window",),
            ]
        refresh()
        assert_physical_parity()


def test_failed_replacement_rolls_back_relation_and_publication(fact_brand):
    migration = import_module(MIGRATION)
    refresh()
    publication = MaterializationState.objects.get(pk=DATASET)
    publication.published_generation = publication.source_generation
    publication.cutoff = NOW.replace(hour=0) - timedelta(days=1)
    publication.refreshed_at = NOW
    publication.save(update_fields=["published_generation", "cutoff", "refreshed_at"])
    before = MaterializationState.objects.get(pk=DATASET)
    state_before = {
        field.name: getattr(before, field.name) for field in before._meta.fields
    }
    access = acl_snapshot()
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT 'each_brand_post_facts'::regclass::oid,relispopulated FROM pg_class WHERE oid='each_brand_post_facts'::regclass"
        )
        relation_before = cursor.fetchone()
    from django.db import ProgrammingError

    with pytest.raises(ProgrammingError), transaction.atomic():
        migration.replace_saved_view(
            SimpleNamespace(connection=connection),
            "SELECT missing_frozen_column FROM posts",
        )
    assert acl_snapshot() == access
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT 'each_brand_post_facts'::regclass::oid,relispopulated FROM pg_class WHERE oid='each_brand_post_facts'::regclass"
        )
        assert cursor.fetchone() == relation_before
    before.refresh_from_db()
    assert {
        field.name: getattr(before, field.name) for field in before._meta.fields
    } == state_before
    assert_physical_parity()


def publication_snapshot():
    state = MaterializationState.objects.get(pk=DATASET)
    return {field.name: getattr(state, field.name) for field in state._meta.fields}


def relation_snapshot():
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT 'each_brand_post_facts'::regclass::oid,relispopulated FROM pg_class WHERE oid='each_brand_post_facts'::regclass"
        )
        return cursor.fetchone()


@pytest.mark.parametrize("delegated", ["table", "column"])
def test_delegated_grants_fail_before_drop_and_keep_original_publication(
    fact_brand, delegated
):
    migration = import_module(MIGRATION)
    intermediary = "each_grouped_intermediary_" + uuid4().hex[:10]
    downstream = "each_grouped_downstream_" + uuid4().hex[:10]
    quote = connection.ops.quote_name
    refresh()
    state = MaterializationState.objects.get(pk=DATASET)
    state.published_generation = state.source_generation
    state.cutoff = NOW.replace(hour=0) - timedelta(days=1)
    state.refreshed_at = NOW
    state.save(update_fields=["published_generation", "cutoff", "refreshed_at"])
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_user")
        original_user = cursor.fetchone()[0]
        cursor.execute("CREATE ROLE " + quote(intermediary) + " NOLOGIN")
        cursor.execute("CREATE ROLE " + quote(downstream) + " NOLOGIN")
        privilege = "SELECT" if delegated == "table" else "SELECT (lang_detected)"
        cursor.execute(
            f"GRANT {privilege} ON each_brand_post_facts TO {quote(intermediary)} WITH GRANT OPTION"
        )
        cursor.execute("SET LOCAL ROLE " + quote(intermediary))
        try:
            cursor.execute(
                f"GRANT {privilege} ON each_brand_post_facts TO {quote(downstream)}"
            )
        finally:
            cursor.execute("SET LOCAL ROLE " + quote(original_user))
    access = acl_snapshot()
    with connection.cursor() as cursor:
        cursor.execute("SELECT oid FROM pg_roles WHERE rolname=%s", [intermediary])
        intermediary_oid = cursor.fetchone()[0]
        cursor.execute("SELECT oid FROM pg_roles WHERE rolname=%s", [downstream])
        downstream_oid = cursor.fetchone()[0]
    delegated_grant = (intermediary_oid, downstream_oid, "SELECT", False)
    if delegated == "table":
        assert delegated_grant in access[1]
    else:
        assert ("lang_detected", *delegated_grant) in access[2]
    before_relation = relation_snapshot()
    before_publication = publication_snapshot()
    statements = []

    def capture(execute, sql, params, many, context):
        statements.append(sql)
        return execute(sql, params, many, context)

    with (
        connection.execute_wrapper(capture),
        pytest.raises(RuntimeError, match="cannot preserve existing grantors") as error,
    ):
        migration.forwards(None, SimpleNamespace(connection=connection))
    assert "current role=" in str(error.value) and "owner=" in str(error.value)
    assert intermediary in str(error.value)
    assert not any("DROP MATERIALIZED VIEW" in sql for sql in statements)
    assert relation_snapshot() == before_relation
    assert publication_snapshot() == before_publication
    assert acl_snapshot() == access
    assert before_publication["published_generation"] is not None
    assert_physical_parity()


def test_foreign_owner_fails_before_drop_and_retains_owner_and_rows(fact_brand):
    migration = import_module(MIGRATION)
    owner = "each_grouped_foreign_owner_" + uuid4().hex[:10]
    quote = connection.ops.quote_name
    refresh()
    with connection.cursor() as cursor:
        cursor.execute("CREATE ROLE " + quote(owner) + " NOLOGIN")
        cursor.execute(
            "ALTER MATERIALIZED VIEW each_brand_post_facts OWNER TO " + quote(owner)
        )
    access = acl_snapshot()
    before_relation = relation_snapshot()
    before_publication = publication_snapshot()
    statements = []

    def capture(execute, sql, params, many, context):
        statements.append(sql)
        return execute(sql, params, many, context)

    with (
        connection.execute_wrapper(capture),
        pytest.raises(
            RuntimeError, match="requires the migration role to own the view"
        ) as error,
    ):
        migration.forwards(None, SimpleNamespace(connection=connection))
    assert owner in str(error.value)
    assert not any("DROP MATERIALIZED VIEW" in sql for sql in statements)
    assert relation_snapshot() == before_relation
    assert publication_snapshot() == before_publication
    assert acl_snapshot() == access
    assert_physical_parity()
