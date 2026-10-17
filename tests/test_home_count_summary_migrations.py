"""Real PostgreSQL storage and writer contracts for derived homepage counts."""

import pytest
from django.db import connection
from django.utils import timezone

from core.models import Brand, HomeCountSnapshot, Post, PostBrand

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


def test_home_counts_use_one_native_materialized_view_and_one_lifecycle_table():
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT relname, relkind FROM pg_class "
            "WHERE relnamespace = 'public'::regnamespace "
            "AND relname IN ('home_count_snapshot', 'home_brand_time_counts')"
        )
        kinds = dict(cursor.fetchall())
    assert kinds == {
        "home_count_snapshot": "r",
        "home_brand_time_counts": "m",
    }, "homepage counts require a rebuildable native view and distinct lifecycle state"


def test_staging_exporter_can_lock_publication_state_without_reading_or_writing():
    import importlib
    import uuid

    migration = importlib.import_module(
        "core.migrations.0093_homepage_count_materialization"
    )
    grant = "DO $grant$" + migration.VIEW_SQL.split("DO $grant$", 1)[1]
    role = "pw_counts_export_" + uuid.uuid4().hex[:12]
    with connection.cursor() as cursor:
        cursor.execute(f"CREATE ROLE {role} NOLOGIN")
        try:
            cursor.execute(grant.replace("staging_refresh_reader", role))
            cursor.execute(
                "SELECT has_table_privilege(%s, 'home_count_snapshot', 'MAINTAIN'), "
                "has_table_privilege(%s, 'home_count_snapshot', 'SELECT'), "
                "has_table_privilege(%s, 'home_count_snapshot', 'INSERT')",
                [role, role, role],
            )
            assert cursor.fetchone() == (True, False, False)
        finally:
            cursor.execute(f"DROP OWNED BY {role}")
            cursor.execute(f"DROP ROLE {role}")


def test_bulk_history_writes_invalidate_once_but_metrics_and_empty_writes_do_not():
    from datetime import timedelta

    HomeCountSnapshot.objects.get_or_create(pk=1)
    brand = Brand.objects.create(nickname="history-trigger", display_name="History")
    posts = Post.objects.bulk_create(
        [
            Post(
                tweet_id=f"history-{index}",
                created_at=timezone.now() - timedelta(days=2),
            )
            for index in range(4)
        ]
    )

    def generation():
        return HomeCountSnapshot.objects.get(pk=1).source_generation

    before = generation()
    PostBrand.objects.bulk_create([PostBrand(post=post, brand=brand) for post in posts])
    assert generation() == before + 1
    Post.objects.filter(pk__in=[post.pk for post in posts]).update(
        text="unrelated edit"
    )
    Post.objects.filter(pk="does-not-exist").update(created_at=timezone.now())
    assert generation() == before + 1
    Post.objects.filter(pk__in=[post.pk for post in posts]).update(
        created_at=timezone.now()
    )
    assert generation() == before + 2


def test_actual_attribution_writer_invalidates_backfill_without_provider_calls():
    from datetime import timedelta

    from monitor.cycle import _persist_attribution
    from x_monitor.attribution import MentionRow

    HomeCountSnapshot.objects.get_or_create(pk=1)
    brand = Brand.objects.create(nickname="writer-chain", display_name="Writer")
    post = Post.objects.create(
        tweet_id="writer-history", created_at=timezone.now() - timedelta(days=3)
    )
    before = HomeCountSnapshot.objects.get(pk=1).source_generation
    mention = MentionRow(
        post_id=post.pk,
        brand_id=brand.pk,
        source="body_keyword",
        raw_token="Writer",
        mentioned_at="",
    )
    assert _persist_attribution(post, [], [mention]) == 1
    assert HomeCountSnapshot.objects.get(pk=1).source_generation == before + 1
    assert _persist_attribution(post, [], [mention]) == 1
    assert HomeCountSnapshot.objects.get(pk=1).source_generation == before + 1


def test_counter_changes_roll_back_with_source_transaction():
    from datetime import timedelta

    from django.db import transaction

    HomeCountSnapshot.objects.get_or_create(pk=1)
    brand = Brand.objects.create(nickname="rollback-test")
    post = Post.objects.create(
        tweet_id="rollback-test", created_at=timezone.now() - timedelta(days=3)
    )
    before = HomeCountSnapshot.objects.get(pk=1).source_generation
    with pytest.raises(ValueError), transaction.atomic():
        PostBrand.objects.create(post=post, brand=brand)
        raise ValueError("rollback source")
    assert HomeCountSnapshot.objects.get(pk=1).source_generation == before
    assert not PostBrand.objects.filter(post=post).exists()


@pytest.mark.django_db(transaction=True)
def test_new_migration_can_reverse_and_reapply_without_losing_source_data(
    isolated_migration_database,
):
    from django.db.migrations.executor import MigrationExecutor

    before = ("core", "0092_measurement_window_index")
    target = ("core", "0093_homepage_count_materialization")
    executor = MigrationExecutor(connection)
    executor.migrate([before])
    brand = Brand.objects.create(nickname="migration-count-test")
    post = Post.objects.create(
        tweet_id="migration-count-test", created_at=timezone.now()
    )
    PostBrand.objects.create(post=post, brand=brand)
    for destination in (target, before, target):
        executor = MigrationExecutor(connection)
        executor.migrate([destination])
        assert PostBrand.objects.filter(post_id=post.pk, brand_id=brand.pk).count() == 1
    state = executor.loader.project_state([target]).apps.get_model(
        "core", "HomeBrandTimeCount"
    )
    for name in state._meta.pk.field_names:
        assert state._meta.get_field(name) is not None
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT indisvalid, indisready FROM pg_index WHERE indexrelid = 'home_brand_time_counts_key'::regclass"
        )
        assert cursor.fetchone() == (True, True)


@pytest.mark.parametrize(
    "change",
    [
        "delete_link",
        "reattribute",
        "null_time",
        "legacy",
        "promotion",
        "delete_post",
        "truncate",
        "canonical_identity",
    ],
)
def test_count_relevant_database_changes_invalidate_published_history(change):
    from datetime import timedelta

    from core.models import PostUnsanctionedFlag, PostUntrackedBrandPromotion
    from monitor.home_count_summary import refresh_home_counts

    brand = Brand.objects.create(nickname="dirty-test")
    other = Brand.objects.create(nickname="dirty-other")
    post = Post.objects.create(
        tweet_id="dirty-test", created_at=timezone.now() - timedelta(days=2)
    )
    PostBrand.objects.create(post=post, brand=brand)
    assert refresh_home_counts()["status"] == "refreshed"
    before = HomeCountSnapshot.objects.get(pk=1)
    if change == "delete_link":
        PostBrand.objects.filter(post=post).delete()
    elif change == "reattribute":
        PostBrand.objects.filter(post=post).update(brand=other)
    elif change == "null_time":
        Post.objects.filter(pk=post.pk).update(created_at=None)
    elif change == "legacy":
        PostUnsanctionedFlag.objects.create(post=post, flags="[]")
    elif change == "promotion":
        PostUntrackedBrandPromotion.objects.create(post=post)
    elif change == "delete_post":
        post.delete()
    elif change == "truncate":
        with connection.cursor() as cursor:
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
            cursor.execute("TRUNCATE posts_brands CASCADE")
    else:
        Brand.objects.filter(pk=brand.pk).update(nickname=brand.pk.upper())
    state = HomeCountSnapshot.objects.get(pk=1)
    assert state.source_generation > before.published_generation
    assert state.dirty_since < state.cutoff


def test_weight_noops_and_eligibility_detail_edits_keep_closed_day_counts_valid():
    from datetime import timedelta

    from core.models import PostUnsanctionedFlag, PostUntrackedBrandPromotion
    from monitor.home_count_summary import refresh_home_counts

    brand = Brand.objects.create(nickname="noop-test")
    post = Post.objects.create(
        tweet_id="noop-test", created_at=timezone.now() - timedelta(days=2)
    )
    PostBrand.objects.create(post=post, brand=brand)
    PostUnsanctionedFlag.objects.create(post=post, flags="[]")
    PostUntrackedBrandPromotion.objects.create(post=post)
    assert refresh_home_counts()["status"] == "refreshed"
    generation = HomeCountSnapshot.objects.get(pk=1).source_generation
    PostBrand.objects.filter(post=post).update(weight=0.5)
    PostBrand.objects.filter(post=post).update(brand_id=brand.pk.upper())
    Post.objects.filter(pk=post.pk).update(created_at=post.created_at, like_count=9)
    PostUnsanctionedFlag.objects.filter(post=post).update(flags='["changed"]')
    PostUntrackedBrandPromotion.objects.filter(post=post).update(
        promotion_keys=["changed"]
    )
    PostBrand.objects.bulk_create(
        [PostBrand(post=post, brand=brand)], ignore_conflicts=True
    )
    assert HomeCountSnapshot.objects.get(pk=1).source_generation == generation
