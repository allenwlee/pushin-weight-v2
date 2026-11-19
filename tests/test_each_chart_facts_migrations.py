"""Native storage and online invalidation contracts for Each chart facts."""

from datetime import timedelta
from importlib import import_module

import pytest
from django.db import connection
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
    migration = import_module("core.migrations.0228_each_chart_facts")
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
