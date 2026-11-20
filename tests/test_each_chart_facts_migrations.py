"""Native storage and online invalidation contracts for Each chart facts."""

from datetime import timedelta
from importlib import import_module
from types import SimpleNamespace

import pytest
from django.db import ProgrammingError, connection, transaction
from django.utils import timezone

from core.classification_contract import CONTRACT_VERSION, TAXONOMY_VERSION
from core.models import (
    Brand,
    MaterializationState,
    Post,
    PostBrand,
    PostBrandClassificationState,
    SentimentKey,
)
from tests.test_geolocation_access import serving_login

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]
KEY = "each.brand_post_facts.v1"


@pytest.fixture(autouse=True)
def each_state():
    MaterializationState.objects.get_or_create(pk=KEY)


def read_state(key=KEY):
    with connection.cursor() as c:
        c.execute(
            "SELECT source_generation,dirty_since,ctid::text FROM materialization_state WHERE dataset_key=%s",
            [key],
        )
        return c.fetchone()


def test_relations_indexes_and_safe_serving_allowlist():
    from core.geolocation_access import SERVING_VIEWS

    with connection.cursor() as c:
        c.execute(
            "SELECT relname,relkind FROM pg_class WHERE relnamespace='public'::regnamespace AND relname IN ('each_brand_post_facts','each_brand_post_facts_source')"
        )
        assert dict(c.fetchall()) == {
            "each_brand_post_facts": "m",
            "each_brand_post_facts_source": "v",
        }
        c.execute(
            "SELECT indexname,indexdef FROM pg_indexes WHERE tablename='each_brand_post_facts'"
        )
        indexes = dict(c.fetchall())
        assert "UNIQUE" in indexes["each_brand_post_facts_key"]
        assert "(brand_id, created_at)" in indexes["each_brand_post_facts_window"]
        c.execute(
            "SELECT DISTINCT origin.relname,a.attname FROM pg_rewrite r JOIN pg_depend d ON d.objid=r.oid AND d.classid='pg_rewrite'::regclass JOIN pg_class origin ON origin.oid=d.refobjid JOIN pg_attribute a ON a.attrelid=origin.oid AND a.attnum=d.refobjsubid WHERE r.ev_class='each_brand_post_facts_source'::regclass AND d.refobjsubid>0"
        )
        assert ("posts", "author_location") not in c.fetchall()
    assert {"each_brand_post_facts", "each_brand_post_facts_source"} <= SERVING_VIEWS


def test_reverse_and_reapply_native_storage():
    migration = import_module("core.migrations.0235_each_chart_facts")
    with connection.cursor() as c:
        c.execute(migration.REVERSE_SQL)
        c.execute(
            "SELECT to_regclass('each_brand_post_facts'),to_regclass('each_brand_post_facts_source')"
        )
        assert c.fetchone() == (None, None)
        c.execute(migration.VIEW_SQL + migration.TRIGGER_SQL)
        c.execute(
            "SELECT relispopulated FROM pg_class WHERE oid='each_brand_post_facts'::regclass"
        )
        assert c.fetchone() == (False,)
    assert read_state()[0] == 0


@pytest.mark.parametrize("age", [0, 1, 3])
def test_recent_posts_never_touch_state_and_history_invalidates(age):
    brand = Brand.objects.create(nickname="each-trigger-age", display_name="Trigger")
    at = timezone.now().replace(hour=12, minute=0, second=0, microsecond=0) - timedelta(
        days=age
    )
    post = Post.objects.create(tweet_id="each-trigger-age", created_at=at, lang="en")
    before = read_state()
    PostBrand.objects.create(post=post, brand=brand)
    after = read_state()
    if age < 2:
        assert after == before
    else:
        assert after[0] == before[0] + 1
        assert after[1] == at
    before = read_state()
    Post.objects.filter(pk=post.pk).update(lang="ja")
    after = read_state()
    assert after == before if age < 2 else after[0] == before[0] + 1
    # Unprojected text/weight changes do not run an Each invalidation trigger.
    before = read_state()
    Post.objects.filter(pk=post.pk).update(text="unrelated")
    PostBrand.objects.filter(post=post, brand=brand).update(weight=0.3)
    assert read_state() == before


def test_classification_projection_and_binary_case_changes_invalidate_only_each():
    brand = Brand.objects.create(nickname="each-trigger-state", display_name="Trigger")
    post = Post.objects.create(
        tweet_id="each-trigger-state", created_at=timezone.now() - timedelta(days=5)
    )
    PostBrand.objects.create(post=post, brand=brand)
    SentimentKey.objects.get_or_create(key="positive")
    state = PostBrandClassificationState.objects.create(
        post=post,
        brand=brand,
        contract_version=CONTRACT_VERSION,
        taxonomy_version=TAXONOMY_VERSION,
        prompt_version="test",
        model="test",
        input_context_fingerprint="a" * 64,
        outcome="classified",
        sentiment_id="positive",
    )
    home = read_state("home.brand_time_counts.v1")
    before = read_state()
    PostBrandClassificationState.objects.filter(pk=state.pk).update(
        classified_at=timezone.now(), model="changed"
    )
    assert read_state() == before
    PostBrandClassificationState.objects.filter(pk=state.pk).update(
        brand_id=brand.pk.upper()
    )
    assert read_state()[0] == before[0] + 1
    assert read_state("home.brand_time_counts.v1") == home
    with connection.cursor() as c:
        c.execute(
            "SELECT state_brand_id FROM each_brand_post_facts_source WHERE post_id=%s",
            [post.pk],
        )
        assert c.fetchone()[0] == brand.pk.upper()


def test_brand_identity_and_truncate_use_global_sentinel():
    brand = Brand.objects.create(nickname="each-trigger-case", display_name="Trigger")
    Brand.objects.filter(pk=brand.pk).update(nickname=brand.pk.upper())
    assert read_state()[1].year == 1
    with connection.cursor() as c:
        c.execute("TRUNCATE posts_brands_classification_states")
    assert read_state()[1].year == 1


def test_trigger_columns_match_actual_model_columns_and_are_invoker_rights():
    from django.apps import apps

    migration = import_module("core.migrations.0235_each_chart_facts")
    models = {model._meta.db_table: model for model in apps.get_models() if model._meta.managed}
    for table, fields in migration.UPDATE_COLUMNS.items():
        actual = {field.column for field in models[table]._meta.local_concrete_fields}
        required = {column for column, _binary in fields}
        assert required <= actual
        with connection.cursor() as cursor:
            physical = {column.name for column in connection.introspection.get_table_description(cursor, table)}
        assert required <= physical
    with connection.cursor() as cursor:
        cursor.execute("SELECT proname,prosecdef FROM pg_proc WHERE proname IN ('each_facts_invalidate','each_facts_brand_identity')")
        assert dict(cursor.fetchall()) == {"each_facts_invalidate": False, "each_facts_brand_identity": False}


@pytest.mark.parametrize("table", [
    "posts_brands", "posts_brands_classification_states", "posts_brands_signals",
    "posts_brands_product_labels", "posts_brands_audience_topics",
    "posts_brands_geopolitical_modes", "posts_untracked_brand_promotions",
])
def test_each_edge_insert_projection_update_and_delete_invalidate_one_row(table):
    from core.models import (
        AudienceTopicConcept, AudienceTopicScheme, GeopoliticalModeKey,
        PostBrandAudienceTopic, PostBrandGeopoliticalMode, PostBrandProductLabel,
        PostBrandSignal, PostTypeKey, PostUntrackedBrandPromotion, ProductLabelKey,
    )

    brand = Brand.objects.create(nickname="each-edge-trigger")
    at = timezone.now() - timedelta(days=5)
    post = Post.objects.create(tweet_id="each-edge-trigger", created_at=at)
    SentimentKey.objects.get_or_create(key="positive")
    SentimentKey.objects.get_or_create(key="negative")
    PostTypeKey.objects.get_or_create(key="other")
    ProductLabelKey.objects.get_or_create(key="bug")
    scheme, _ = AudienceTopicScheme.objects.get_or_create(key="ai_audience_topics/v1", defaults={"manifest_hash": "a" * 64})
    concept, _ = AudienceTopicConcept.objects.get_or_create(scheme=scheme, key="local_inference")
    GeopoliticalModeKey.objects.get_or_create(key="reporting")
    specs = {
        "posts_brands": (PostBrand, {}, {"brand_id": brand.pk.upper()}),
        "posts_brands_classification_states": (PostBrandClassificationState, {
            "contract_version": CONTRACT_VERSION, "taxonomy_version": TAXONOMY_VERSION,
            "prompt_version": "test", "model": "test", "input_context_fingerprint": "a" * 64,
            "outcome": "classified", "sentiment_id": "positive",
        }, {"sentiment_id": "negative"}),
        "posts_brands_signals": (PostBrandSignal, {"post_type_id": "other", "sentiment_id": "positive"}, {"sentiment_id": "negative"}),
        "posts_brands_product_labels": (PostBrandProductLabel, {"product_label_id": "bug"}, {"brand_id": brand.pk.upper()}),
        "posts_brands_audience_topics": (PostBrandAudienceTopic, {"concept": concept, "scheme": scheme, "scheme_revision": 1}, {"scheme_revision": 2}),
        "posts_brands_geopolitical_modes": (PostBrandGeopoliticalMode, {"geopolitical_mode_id": "reporting", "taxonomy_version": TAXONOMY_VERSION}, {"taxonomy_version": "custom:version"}),
        "posts_untracked_brand_promotions": (PostUntrackedBrandPromotion, {"promotion_keys": []}, {"promotion_keys": ["spam"]}),
    }
    model, defaults, changes = specs[table]
    values = {"post": post, **defaults}
    if table != "posts_untracked_brand_promotions":
        values["brand"] = brand
    before = read_state()
    row = model.objects.create(**values)
    assert read_state()[:2] == (before[0] + 1, at)
    if any(field.name == "evidence" for field in model._meta.fields):
        before = read_state()
        model.objects.filter(pk=row.pk).update(evidence={"source": "unprojected"})
        assert read_state() == before
    before = read_state()
    model.objects.filter(pk=row.pk).update(**changes)
    assert read_state()[:2] == (before[0] + 1, at)
    before = read_state()
    model.objects.filter(post=post).delete()
    assert read_state()[:2] == (before[0] + 1, at)


@pytest.mark.parametrize("age", [0, 1, 5])
def test_real_publish_call_chain_has_exact_historical_row_invalidation(age):
    from core.models import PostBrandProductLabel, PostBrandSignal, PostEnrichmentState, PostTypeKey, ProductLabelKey
    from monitor.cycle import _publish_stage1_classification

    brand = Brand.objects.create(nickname="each-real-publish")
    at = timezone.now().replace(hour=12, minute=0, second=0, microsecond=0) - timedelta(days=age)
    post = Post.objects.create(tweet_id="each-real-publish", text="A fixture", created_at=at)
    PostBrand.objects.create(post=post, brand=brand)
    PostEnrichmentState.objects.create(post=post, claim_run_id="each-real-publish", claim_expires_at=timezone.now() + timedelta(minutes=5))
    for key in ("positive", "negative"):
        SentimentKey.objects.get_or_create(key=key)
    PostTypeKey.objects.get_or_create(key="hands_on_usage")
    ProductLabelKey.objects.get_or_create(key="bug")
    classification = {
        "outcome": "classified", "post_types": ["hands_on_usage"], "product_labels": ["bug"],
        "sentiment": "positive", "china_nationalism": None, "us_nationalism": None,
    }
    for sentiment, historical_delta in (("positive", 3), ("positive", 4), ("negative", 5)):
        classification["sentiment"] = sentiment
        before = read_state()
        _publish_stage1_classification(
            post_id=post.pk, result={"valid": True, "unsanctioned_flags": [], "by_brand": {brand.pk: classification}},
            tweet={"text": post.text, "context": []}, model="fixture", run_id="each-real-publish",
        )
        assert PostBrandClassificationState.objects.get(post=post, brand=brand).sentiment_id == sentiment
        assert PostBrandSignal.objects.filter(post=post).count() == 1
        assert PostBrandProductLabel.objects.filter(post=post).count() == 1
        after = read_state()
        if age < 2:
            assert after == before
        else:
            assert after[:2] == (before[0] + historical_delta, at)


def storage_snapshot():
    with connection.cursor() as cursor:
        cursor.execute("SELECT c.oid,c.relname,c.relowner,c.relacl::text FROM pg_class c WHERE c.relname IN ('each_brand_post_facts','each_brand_post_facts_source','idx_posts_created_cover') ORDER BY c.relname")
        relations = cursor.fetchall()
        cursor.execute("SELECT tgrelid,tgname,tgfoid FROM pg_trigger WHERE tgname LIKE 'each_facts_%' ORDER BY 1,2")
        triggers = cursor.fetchall()
        cursor.execute("SELECT attname,attacl::text FROM pg_attribute WHERE attrelid='each_brand_post_facts'::regclass AND attnum>0 ORDER BY attnum")
        columns = cursor.fetchall()
    return relations, triggers, columns, MaterializationState.objects.filter(pk=KEY).values().get()


def test_fresh_create_refuses_existing_objects_without_changing_grants_or_publication():
    from uuid import uuid4

    migration = import_module("core.migrations.0235_each_chart_facts")
    role = "each_existing_grants_" + uuid4().hex[:12]
    with connection.cursor() as cursor:
        cursor.execute("CREATE ROLE " + connection.ops.quote_name(role) + " NOLOGIN")
        cursor.execute("GRANT SELECT ON each_brand_post_facts TO " + connection.ops.quote_name(role) + " WITH GRANT OPTION")
        cursor.execute("GRANT SELECT (lang_detected) ON each_brand_post_facts TO " + connection.ops.quote_name(role) + " WITH GRANT OPTION")
    before = storage_snapshot()
    with pytest.raises(ProgrammingError):
        migration.create_storage(None, SimpleNamespace(connection=connection))
    assert storage_snapshot() == before


def test_failed_fresh_create_rolls_back_all_each_objects_and_state(monkeypatch):
    migration = import_module("core.migrations.0235_each_chart_facts")
    editor = SimpleNamespace(connection=connection)
    with connection.cursor() as cursor:
        cursor.execute("SELECT 'idx_posts_created_cover'::regclass::oid")
        home_index = cursor.fetchone()
    migration.drop_storage(None, editor)
    original = migration.TRIGGER_SQL
    monkeypatch.setattr(migration, "TRIGGER_SQL", original + "SELECT missing_frozen_column FROM posts;")
    with pytest.raises(ProgrammingError):
        migration.create_storage(None, editor)
    assert not MaterializationState.objects.filter(pk=KEY).exists()
    with connection.cursor() as cursor:
        cursor.execute("SELECT to_regclass('each_brand_post_facts'),to_regclass('each_brand_post_facts_source')")
        assert cursor.fetchone() == (None, None)
        cursor.execute("SELECT count(*) FROM pg_trigger WHERE tgname LIKE 'each_facts_%'")
        assert cursor.fetchone() == (0,)
        cursor.execute("SELECT 'idx_posts_created_cover'::regclass::oid")
        assert cursor.fetchone() == home_index
    monkeypatch.setattr(migration, "TRIGGER_SQL", original)
    migration.create_storage(None, editor)
    assert read_state()[:2] == (0, None)


def test_missing_parent_in_a_deferred_delete_uses_global_sentinel():
    brand = Brand.objects.create(nickname="each-deferred-cascade")
    post = Post.objects.create(tweet_id="each-deferred-cascade", created_at=timezone.now() - timedelta(days=5))
    PostBrand.objects.create(post=post, brand=brand)
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("DELETE FROM posts WHERE tweet_id=%s", [post.pk])
        cursor.execute("DELETE FROM posts_brands WHERE post_id=%s", [post.pk])
    assert read_state()[1].year == 1


@pytest.mark.django_db(transaction=True)
def test_real_serving_login_requires_both_view_grants_and_cannot_read_location_sources(serving_login):
    from unittest.mock import patch

    import psycopg
    from psycopg import sql

    from core.geolocation_access import serving_grants_ready

    serving, role, _owner, _report = serving_login
    with connection.cursor() as cursor:
        cursor.execute("REFRESH MATERIALIZED VIEW each_brand_post_facts")
    with serving.cursor() as cursor:
        cursor.execute("SELECT brand_id,post_id,created_at FROM each_brand_post_facts LIMIT 0")
        cursor.execute("SELECT brand_id,post_id,created_at FROM each_brand_post_facts_source LIMIT 0")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cursor.execute("SELECT reported_author_location FROM posts LIMIT 0")
    for relation in ("each_brand_post_facts", "each_brand_post_facts_source"):
        with connection.cursor() as cursor:
            cursor.execute(sql.SQL("REVOKE SELECT ON {} FROM {}").format(sql.Identifier(relation), sql.Identifier(role)))
        with patch.object(connection, "connection", serving):
            assert not serving_grants_ready(connection)
        with connection.cursor() as cursor:
            cursor.execute(sql.SQL("GRANT SELECT ON {} TO {}").format(sql.Identifier(relation), sql.Identifier(role)))
        with patch.object(connection, "connection", serving):
            assert serving_grants_ready(connection)
