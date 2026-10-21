"""Both deployed upgrade orders preserve source facts and derived publication."""

from datetime import timedelta

import pytest
from django.core.management import call_command
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder
from django.utils import timezone

from core.benchmark_metric_identity import configure_collection
from core.models import (
    HomeBrandTimeCount,
    MaterializationState,
)
from monitor.home_count_summary import refresh_home_counts
from tests.collection_fixtures import historical_fixture_models
from tests.test_benchmark_download_db_identity import setup_spec

GLOBAL = ("core", "0119_geography_label_locale_references")
HOME = ("core", "0094_shared_materialization_state")
MERGE = ("core", "0120_merge_homepage_shared_vocabulary")

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def test_integrated_graph_retains_the_operation_free_merge_migration():
    loader = MigrationExecutor(connection).loader
    migration = loader.get_migration(*MERGE)
    assert set(migration.dependencies) == {GLOBAL, HOME}
    assert migration.operations == []
    assert MERGE in loader.graph.nodes


@pytest.mark.usefixtures("isolated_migration_database")
@pytest.mark.parametrize("order", [(GLOBAL, HOME), (HOME, GLOBAL)])
def test_both_populated_upgrade_orders_preserve_originals_and_guards(order):
    base = ("core", "0092_measurement_window_index")
    executor = MigrationExecutor(connection)
    executor.migrate([base])
    old = executor.loader.project_state([base]).apps
    with historical_fixture_models(old):
        _, spec = setup_spec()
        configure_collection(spec)
    country = old.get_model("core", "Country").objects.create(code="XZ", m49_code="999")
    old.get_model("core", "CountryLabel").objects.create(
        country_id=country.pk, lang="zh-cn", label="保留原文"
    )
    brand = old.get_model("core", "Brand").objects.get(pk="lab")
    post = old.get_model("core", "Post").objects.create(
        tweet_id="merge-preservation", text="原文", created_at=timezone.now() - timedelta(days=2)
    )
    old.get_model("core", "PostBrand").objects.create(post=post, brand=brand)
    originals = {}
    for name in ("Post", "PostBrand", "CountryLabel", "SourceMetric", "MetricCollectionContract"):
        model = old.get_model("core", name)
        fields = [field.attname for field in model._meta.local_concrete_fields]
        originals[name] = (fields, list(model.objects.order_by("pk").values(*fields)))

    def assert_originals():
        for name, (fields, expected) in originals.items():
            actual = old.get_model("core", name).objects.order_by("pk").values(*fields)
            assert list(actual) == expected, name

    for branch in order:
        MigrationExecutor(connection).migrate([branch])
        assert_originals()
        assert branch in MigrationRecorder(connection).applied_migrations()
        if branch == GLOBAL:
            call_command("seed_shared_vocabulary", verbosity=0)
            global_labels = MigrationExecutor(connection).loader.project_state(
                [GLOBAL]
            ).apps.get_model("core", "CountryLabel")
            legacy_label = global_labels.objects.get(pk=(country.pk, "zh-cn"))
            assert legacy_label.lang == "zh-cn"
            # The shared catalogue seed alone does not perform the later
            # owner-context data mapping introduced with the RG1 cutover.
            assert legacy_label.locale_reference_id is None
        else:
            assert refresh_home_counts()["status"] == "refreshed"
            assert list(HomeBrandTimeCount.objects.values_list("brand_id", "post_count")) == [(brand.pk, 1)]

    publication = list(MaterializationState.objects.order_by("pk").values())
    counts = list(HomeBrandTimeCount.objects.order_by("pk").values())
    MigrationExecutor(connection).migrate([MERGE])
    assert_originals()
    applied = MigrationRecorder(connection).applied_migrations()
    assert {GLOBAL, HOME, MERGE} <= set(applied)
    assert list(MaterializationState.objects.order_by("pk").values()) == publication
    assert list(HomeBrandTimeCount.objects.order_by("pk").values()) == counts
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT relname,relkind FROM pg_class WHERE relname IN "
            "('materialization_state','home_brand_time_counts')"
        )
        assert dict(cursor.fetchall()) == {"materialization_state": "r", "home_brand_time_counts": "m"}
    legacy_country_label = MigrationExecutor(connection).loader.project_state(
        [GLOBAL]
    ).apps.get_model("core", "CountryLabel")
    with pytest.raises(IntegrityError), transaction.atomic():
        legacy_country_label.objects.filter(pk=(country.pk, "zh-cn")).update(
            locale_reference_id="en"
        )

    # Reversing only the empty merge must leave both histories and every row.
    MigrationExecutor(connection).migrate([GLOBAL, HOME])
    assert MERGE not in MigrationRecorder(connection).applied_migrations()
    assert_originals()
    assert list(MaterializationState.objects.order_by("pk").values()) == publication
    assert list(HomeBrandTimeCount.objects.order_by("pk").values()) == counts
    MigrationExecutor(connection).migrate([MERGE])
