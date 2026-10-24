"""Real PostgreSQL storage and writer contracts for derived homepage counts."""

import pytest
from django.db import connection
from django.utils import timezone

from core.models import Brand, MaterializationState, Post, PostBrand

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


@pytest.fixture(autouse=True)
def publication_state():
    # Transactional tests flush data, including the migration's initial row.
    # Each storage scenario starts from its explicit publication fixture.
    MaterializationState.objects.get_or_create(pk="home.brand_time_counts.v1")


@pytest.mark.parametrize("key", ["", "HOME.count.v1", "home.count", "home.count.v0", "home count.v1"])
def test_direct_writes_reject_unversioned_or_noncanonical_dataset_keys(key):
    from django.db import IntegrityError, transaction

    with pytest.raises(IntegrityError), transaction.atomic():
        MaterializationState.objects.create(dataset_key=key)


def test_home_counts_use_one_native_materialized_view_and_one_lifecycle_table():
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT relname, relkind FROM pg_class "
            "WHERE relnamespace = 'public'::regnamespace "
            "AND relname IN ('materialization_state', 'home_brand_time_counts')"
        )
        kinds = dict(cursor.fetchall())
    assert kinds == {
        "materialization_state": "r",
        "home_brand_time_counts": "m",
    }, "homepage counts require a rebuildable native view and distinct lifecycle state"


def test_staging_exporter_can_lock_publication_state_without_reading_or_writing():
    import importlib
    import uuid

    migration = importlib.import_module(
        "core.migrations.0094_shared_materialization_state"
    )
    grant = migration.GRANT_SQL
    role = "pw_counts_export_" + uuid.uuid4().hex[:12]
    with connection.cursor() as cursor:
        cursor.execute(f"CREATE ROLE {role} NOLOGIN")
        try:
            cursor.execute(grant.replace("staging_refresh_reader", role))
            cursor.execute(
                "SELECT has_table_privilege(%s, 'materialization_state', 'MAINTAIN'), "
                "has_table_privilege(%s, 'materialization_state', 'SELECT'), "
                "has_table_privilege(%s, 'materialization_state', 'INSERT')",
                [role, role, role],
            )
            assert cursor.fetchone() == (True, False, False)
        finally:
            cursor.execute(f"DROP OWNED BY {role}")
            cursor.execute(f"DROP ROLE {role}")


def test_history_writes_invalidate_but_metrics_and_empty_writes_do_not():
    from datetime import timedelta

    MaterializationState.objects.get_or_create(pk="home.brand_time_counts.v1")
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
        return MaterializationState.objects.get(
            pk="home.brand_time_counts.v1"
        ).source_generation

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
    # Post date corrections invalidate per changed row; relationship bulk
    # writes still invalidate once. The generation is a publication version.
    assert generation() == before + 1 + len(posts)


def test_actual_attribution_writer_invalidates_backfill_without_provider_calls():
    from datetime import timedelta

    from monitor.cycle import _persist_attribution
    from x_monitor.attribution import MentionRow

    MaterializationState.objects.get_or_create(pk="home.brand_time_counts.v1")
    brand = Brand.objects.create(nickname="writer-chain", display_name="Writer")
    post = Post.objects.create(
        tweet_id="writer-history", created_at=timezone.now() - timedelta(days=3)
    )
    before = MaterializationState.objects.get(
        pk="home.brand_time_counts.v1"
    ).source_generation
    mention = MentionRow(
        post_id=post.pk,
        brand_id=brand.pk,
        source="body_keyword",
        raw_token="Writer",
        mentioned_at="",
    )
    assert _persist_attribution(post, [], [mention]) == 1
    assert (
        MaterializationState.objects.get(
            pk="home.brand_time_counts.v1"
        ).source_generation
        == before + 1
    )
    assert _persist_attribution(post, [], [mention]) == 1
    assert (
        MaterializationState.objects.get(
            pk="home.brand_time_counts.v1"
        ).source_generation
        == before + 1
    )


def test_counter_changes_roll_back_with_source_transaction():
    from datetime import timedelta

    from django.db import transaction

    MaterializationState.objects.get_or_create(pk="home.brand_time_counts.v1")
    brand = Brand.objects.create(nickname="rollback-test")
    post = Post.objects.create(
        tweet_id="rollback-test", created_at=timezone.now() - timedelta(days=3)
    )
    before = MaterializationState.objects.get(
        pk="home.brand_time_counts.v1"
    ).source_generation
    with pytest.raises(ValueError), transaction.atomic():
        PostBrand.objects.create(post=post, brand=brand)
        raise ValueError("rollback source")
    assert (
        MaterializationState.objects.get(
            pk="home.brand_time_counts.v1"
        ).source_generation
        == before
    )
    assert not PostBrand.objects.filter(post=post).exists()


@pytest.mark.django_db(transaction=True)
def test_new_migration_can_reverse_and_reapply_without_losing_source_data(
    isolated_migration_database,
):
    from django.db.migrations.executor import MigrationExecutor

    before = ("core", "0092_measurement_window_index")
    target = ("core", "0094_shared_materialization_state")
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


@pytest.mark.django_db(transaction=True)
def test_shared_state_migration_preserves_publication_and_guards_other_datasets(
    isolated_migration_database,
):
    from datetime import timedelta

    from django.db.migrations.executor import MigrationExecutor

    old_target = ("core", "0093_homepage_count_materialization")
    new_target = ("core", "0094_shared_materialization_state")
    executor = MigrationExecutor(connection)
    executor.migrate([old_target])
    old_state = executor.loader.project_state([old_target]).apps.get_model(
        "core", "HomeCountSnapshot"
    )
    cutoff = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    values = {
        "source_generation": 17,
        "published_generation": 16,
        "dirty_since": cutoff - timedelta(days=3),
        "cutoff": cutoff,
        "refreshed_at": timezone.now(),
    }
    old_state.objects.update_or_create(pk=1, defaults=values)
    MigrationExecutor(connection).migrate([new_target])
    from core.models import MaterializationState

    row = MaterializationState.objects.get(pk="home.brand_time_counts.v1")
    assert {name: getattr(row, name) for name in values} == values
    other = MaterializationState.objects.create(dataset_key="test.preserved.v1")
    with pytest.raises(RuntimeError, match="other materialization state"):
        MigrationExecutor(connection).migrate([old_target])
    assert MaterializationState.objects.count() == 2
    other.delete()
    MigrationExecutor(connection).migrate([old_target])
    assert {
        name: getattr(old_state.objects.get(pk=1), name) for name in values
    } == values
    MigrationExecutor(connection).migrate([new_target])


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
    before = MaterializationState.objects.get(pk="home.brand_time_counts.v1")
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
    state = MaterializationState.objects.get(pk="home.brand_time_counts.v1")
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
    generation = MaterializationState.objects.get(
        pk="home.brand_time_counts.v1"
    ).source_generation
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
    assert (
        MaterializationState.objects.get(
            pk="home.brand_time_counts.v1"
        ).source_generation
        == generation
    )
