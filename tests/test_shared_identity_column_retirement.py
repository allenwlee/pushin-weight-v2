"""The RG1 removal candidate drops legacy identity columns only after exact cutover."""

import pytest
from django.db import connection, transaction
from django.db.migrations.executor import MigrationExecutor

from core.benchmark_metric_identity import register_definitions
from core.collection_corrections import correct_attribution
from core.models import Actor, Country, CountryLabel, Region, RegionLabel, TimeZone
from tests.test_source_metric_projection import configured, evidence, project

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.requires_postgres]


@pytest.mark.usefixtures("isolated_migration_database")
def test_rg1_removal_drops_only_replaced_columns_and_switches_label_keys():
    cutover = ("core", "0126_remove_countrylabel_ck_country_label_locale_and_more")
    removal = ("core", "0127_remove_legacy_identity_columns")
    actor_requirement = ("core", "0128_require_correction_actor")
    MigrationExecutor(connection).migrate([cutover])

    contract, raw, _, _ = configured(mapped=True, product_type="llm-model")
    observation = project(contract, "hf", [evidence("hf", raw)]).observations.get()
    actor = Actor.objects.create(actor_kind="system", actor_key="rg1-retirement-test")
    correction = correct_attribution(
        observation,
        product=None,
        mapping=None,
        actor_identity=actor,
        reason="incorrect_product",
    )

    country = Country.objects.create(code="XZ", m49_code="999")
    region = Region.objects.create(
        key="rg1-retirement-test", source="fixture", level="region"
    )
    CountryLabel.objects.create(
        country=country, locale_reference_id="zh-Hans", label="示例"
    )
    RegionLabel.objects.create(region=region, locale_reference_id="ja", label="例")

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT table_name,column_name FROM information_schema.columns
            WHERE table_schema=current_schema() AND (
                (table_name='metrics' AND column_name IN ('unit','window_unit')) OR
                (table_name='collection_corrections' AND column_name='actor_identifier') OR
                (table_name IN ('country_labels','region_labels') AND column_name='lang')
            )
            """
        )
        assert len(cursor.fetchall()) == 5
        cursor.execute(
            "SELECT actor_identifier FROM collection_corrections WHERE id=%s",
            [correction.pk],
        )
        assert cursor.fetchone()[0] == "system:rg1-retirement-test"
        cursor.execute("SELECT lang FROM country_labels WHERE country_code='XZ'")
        assert cursor.fetchone()[0] == "zh-cn"

    MigrationExecutor(connection).migrate([removal])

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT table_name,column_name FROM information_schema.columns
            WHERE table_schema=current_schema() AND (
                (table_name='metrics' AND column_name IN ('unit','window_unit')) OR
                (table_name='collection_corrections' AND column_name='actor_identifier') OR
                (table_name IN ('country_labels','region_labels') AND column_name='lang')
            )
            """
        )
        assert cursor.fetchall() == []
        cursor.execute(
            """
            SELECT is_nullable FROM information_schema.columns
            WHERE table_schema=current_schema()
              AND table_name='collection_corrections' AND column_name='actor_id'
            """
        )
        assert cursor.fetchone()[0] == "YES"
        cursor.execute(
            """
            SELECT conrelid::regclass::text, conname, pg_get_constraintdef(oid)
            FROM pg_constraint
            WHERE conrelid IN ('country_labels'::regclass,'region_labels'::regclass)
              AND contype='p'
            """
        )
        assert set(cursor.fetchall()) == {
            (
                "country_labels",
                "country_labels_pkey",
                "PRIMARY KEY (country_code, locale_id)",
            ),
            (
                "region_labels",
                "region_labels_pkey",
                "PRIMARY KEY (region_key, locale_id)",
            ),
        }
        cursor.execute(
            """
            SELECT tgname FROM pg_trigger
            WHERE tgrelid IN ('metrics'::regclass,'collection_corrections'::regclass,
                              'country_labels'::regclass,'region_labels'::regclass)
              AND tgname IN ('sync_metric_units','sync_correction_actor_label',
                             'sync_country_label_locale','sync_region_label_locale')
              AND NOT tgisinternal
            """
        )
        assert cursor.fetchall() == []

    assert CountryLabel.objects.get(pk=("XZ", "zh-Hans")).label == "示例"
    assert RegionLabel.objects.get(pk=("rg1-retirement-test", "ja")).label == "例"
    correction.refresh_from_db()
    assert correction.actor_id == actor.pk

    MigrationExecutor(connection).migrate([actor_requirement])
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT is_nullable FROM information_schema.columns
            WHERE table_schema=current_schema()
              AND table_name='collection_corrections' AND column_name='actor_id'
            """
        )
        assert cursor.fetchone()[0] == "NO"


@pytest.mark.usefixtures("isolated_migration_database")
def test_actor_requirement_migration_refuses_null_rows():
    cutover = ("core", "0126_remove_countrylabel_ck_country_label_locale_and_more")
    removal = ("core", "0127_remove_legacy_identity_columns")
    actor_requirement = ("core", "0128_require_correction_actor")
    MigrationExecutor(connection).migrate([cutover])

    contract, raw, _, _ = configured(mapped=True, product_type="llm-model")
    observation = project(contract, "hf", [evidence("hf", raw)]).observations.get()
    actor = Actor.objects.create(actor_kind="system", actor_key="rg1-null-actor-test")
    correction = correct_attribution(
        observation,
        product=None,
        mapping=None,
        actor_identity=actor,
        reason="incorrect_product",
    )
    MigrationExecutor(connection).migrate([removal])

    with connection.cursor() as cursor:
        cursor.execute(
            "ALTER TABLE collection_corrections "
            "DISABLE TRIGGER collection_correction_guard"
        )
        cursor.execute(
            "UPDATE collection_corrections SET actor_id=NULL WHERE id=%s",
            [correction.pk],
        )
        cursor.execute(
            "ALTER TABLE collection_corrections "
            "ENABLE TRIGGER collection_correction_guard"
        )

    with pytest.raises(RuntimeError, match="without actor_id"), transaction.atomic():
        MigrationExecutor(connection).migrate([actor_requirement])

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT is_nullable FROM information_schema.columns
            WHERE table_schema=current_schema()
              AND table_name='collection_corrections' AND column_name='actor_id'
            """
        )
        assert cursor.fetchone()[0] == "YES"


@pytest.mark.usefixtures("isolated_migration_database")
def test_rg1_removal_blocks_when_a_legacy_value_disagrees_with_its_reference():
    cutover = ("core", "0126_remove_countrylabel_ck_country_label_locale_and_more")
    removal = ("core", "0127_remove_legacy_identity_columns")
    MigrationExecutor(connection).migrate([cutover])
    TimeZone.objects.get_or_create(pk="UTC")
    register_definitions()

    with connection.cursor() as cursor:
        cursor.execute("ALTER TABLE metrics DISABLE TRIGGER sync_metric_units")
        cursor.execute(
            "UPDATE metrics SET unit='unregistered-unit' WHERE id=(SELECT min(id) FROM metrics)"
        )

    with pytest.raises(RuntimeError, match="unresolved or inconsistent"), transaction.atomic():
        MigrationExecutor(connection).migrate([removal])

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT count(*) FROM information_schema.columns
            WHERE table_schema=current_schema() AND (
                (table_name='metrics' AND column_name IN ('unit','window_unit')) OR
                (table_name='collection_corrections' AND column_name='actor_identifier') OR
                (table_name IN ('country_labels','region_labels') AND column_name='lang')
            )
            """
        )
        assert cursor.fetchone()[0] == 5
