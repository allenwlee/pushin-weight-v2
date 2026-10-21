"""Timezone writer cutover supports old and new versions during deployment."""

from datetime import UTC, datetime

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor

from core.models import Event, Opportunity, SourceMetric

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]

BASE = ("core", "0120_merge_homepage_shared_vocabulary")
WRITER_CUTOVER = ("core", "0121_timezone_source_writer_cutover")
PHYSICAL_DROP = ("core", "0122_remove_timezone_source_columns")
NOW = datetime(2026, 10, 21, 0, 0, tzinfo=UTC)


def _old_rows(apps):
    Brand = apps.get_model("core", "Brand")
    DataSource = apps.get_model("core", "DataSource")
    Event = apps.get_model("core", "Event")
    MetricType = apps.get_model("core", "MetricType")
    Opportunity = apps.get_model("core", "Opportunity")
    SourceMetric = apps.get_model("core", "SourceMetric")
    TimeZone = apps.get_model("core", "TimeZone")

    TimeZone.objects.bulk_create(
        [TimeZone(code=code) for code in ("UTC", "Asia/Tokyo", "US/Eastern")]
    )
    Brand.objects.create(nickname="timezone-migration-test")
    DataSource.objects.create(
        pk="timezone-test", name="Timezone test", source_type="benchmark"
    )
    MetricType.objects.create(pk="benchmark", name="Benchmark")
    metric = SourceMetric.objects.create(
        source_id="timezone-test",
        metric_type_id="benchmark",
        metric_key="legacy-zone",
        version=1,
        name="Legacy zone",
        unit="count",
        value_kind="integer",
        quantity_form="count",
        measurement_kind="state",
        source_timezone="UTC",
    )
    event = Event.objects.create(
        brand_id="timezone-migration-test",
        source_url="https://example.test/legacy-event",
        title="Legacy event",
        organizer_name="Test",
        source_timezone="Pacific Time",
        first_seen_at=NOW,
        last_seen_at=NOW,
        event_identity="1" * 64,
        content_hash="a" * 64,
        raw_payload={"source_timezone": "Pacific Time"},
    )
    opportunity = Opportunity.objects.create(
        brand_id="timezone-migration-test",
        source_url="https://example.test/legacy-opportunity",
        sponsor_name="Test",
        opportunity_type="contest",
        action_type="submit",
        benefit_type="prize",
        source_timezone="GMT+8",
        first_seen_at=NOW,
        last_seen_at=NOW,
        opportunity_identity="2" * 64,
        content_hash="b" * 64,
        raw_payload={"source_timezone": "GMT+8"},
    )
    return metric, event, opportunity


def _new_source_metric(model):
    return model.objects.create(
        source_id="timezone-test",
        metric_type_id="benchmark",
        metric_key="new-zone",
        version=1,
        name="New zone",
        unit="count",
        value_kind="integer",
        quantity_form="count",
        measurement_kind="state",
        source_timezone_reference_id="UTC",
    )


def _new_event_and_opportunity(event_model, opportunity_model):
    event = event_model.objects.create(
        brand_id="timezone-migration-test",
        source_url="https://example.test/new-event",
        title="New event",
        organizer_name="Test",
        source_timezone_reference_id="UTC",
        first_seen_at=NOW,
        last_seen_at=NOW,
        event_identity="3" * 64,
        content_hash="c" * 64,
        raw_payload={"source_timezone": "UTC"},
    )
    opportunity = opportunity_model.objects.create(
        brand_id="timezone-migration-test",
        related_event=event,
        source_url="https://example.test/new-opportunity",
        sponsor_name="Test",
        opportunity_type="contest",
        action_type="submit",
        benefit_type="prize",
        source_timezone_reference_id="UTC",
        first_seen_at=NOW,
        last_seen_at=NOW,
        opportunity_identity="4" * 64,
        content_hash="d" * 64,
        raw_payload={"source_timezone": "UTC"},
    )
    return event, opportunity


@pytest.mark.usefixtures("isolated_migration_database")
@pytest.mark.django_db(transaction=True)
def test_writer_cutover_is_compatible_until_old_application_instances_drain():
    executor = MigrationExecutor(connection)
    executor.migrate([BASE])
    old_apps = MigrationExecutor(connection).loader.project_state([BASE]).apps
    legacy_metric, legacy_event, legacy_opportunity = _old_rows(old_apps)

    executor = MigrationExecutor(connection)
    executor.migrate([WRITER_CUTOVER])
    cutover_apps = MigrationExecutor(connection).loader.project_state(
        [WRITER_CUTOVER]
    ).apps
    CutoverMetric = cutover_apps.get_model("core", "SourceMetric")
    CutoverEvent = cutover_apps.get_model("core", "Event")
    CutoverOpportunity = cutover_apps.get_model("core", "Opportunity")
    assert SourceMetric.objects.get(pk=legacy_metric.pk).source_timezone_reference_id == "UTC"

    # The old binary can still insert a reported value during a rolling deploy.
    OldMetric = old_apps.get_model("core", "SourceMetric")
    OldMetric.objects.filter(pk=legacy_metric.pk).update(source_timezone="US/Eastern")
    assert (
        SourceMetric.objects.get(pk=legacy_metric.pk).source_timezone_reference_id
        == "US/Eastern"
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        OldMetric.objects.filter(pk=legacy_metric.pk).update(
            source_timezone="Asia/Tokyo",
            source_timezone_reference_id="UTC",
        )
    OldEvent = old_apps.get_model("core", "Event")
    legacy_insert = OldEvent.objects.create(
        brand_id="timezone-migration-test",
        source_url="https://example.test/rolling-event",
        title="Rolling event",
        organizer_name="Test",
        source_timezone="Asia/Tokyo",
        first_seen_at=NOW,
        last_seen_at=NOW,
        event_identity="5" * 64,
        content_hash="e" * 64,
        raw_payload={"source_timezone": "Asia/Tokyo"},
    )
    assert (
        Event.objects.get(pk=legacy_insert.pk).source_timezone_reference_id
        == "Asia/Tokyo"
    )

    # New application writers use the FK only; the transitional trigger does not
    # mirror the FK back into the physical legacy columns.
    new_metric = _new_source_metric(CutoverMetric)
    new_event, new_opportunity = _new_event_and_opportunity(
        CutoverEvent, CutoverOpportunity
    )
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT source_timezone FROM metrics WHERE id=%s", [new_metric.pk]
        )
        assert cursor.fetchone() == (None,)
        cursor.execute("SELECT source_timezone FROM events WHERE id=%s", [new_event.pk])
        assert cursor.fetchone() == (None,)
        cursor.execute(
            "SELECT source_timezone FROM opportunities WHERE id=%s",
            [new_opportunity.pk],
        )
        assert cursor.fetchone() == (None,)

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT table_name
            FROM information_schema.columns
            WHERE table_schema=current_schema()
              AND table_name IN ('metrics', 'events', 'opportunities')
              AND column_name='source_timezone'
            """
        )
        assert len(cursor.fetchall()) == 3

    # Reversing the writer cutover restores the old ORM state and values.
    executor = MigrationExecutor(connection)
    executor.migrate([BASE])
    OldMetric = old_apps.get_model("core", "SourceMetric")
    OldEvent = old_apps.get_model("core", "Event")
    OldOpportunity = old_apps.get_model("core", "Opportunity")
    assert OldMetric.objects.get(pk=legacy_metric.pk).source_timezone == "US/Eastern"
    assert OldMetric.objects.get(pk=new_metric.pk).source_timezone == "UTC"
    assert OldEvent.objects.get(pk=legacy_event.pk).source_timezone == "Pacific Time"
    assert OldEvent.objects.get(pk=legacy_insert.pk).source_timezone == "Asia/Tokyo"
    assert (
        OldOpportunity.objects.get(pk=legacy_opportunity.pk).source_timezone == "GMT+8"
    )


@pytest.mark.usefixtures("isolated_migration_database")
@pytest.mark.django_db(transaction=True)
def test_physical_drop_removes_only_legacy_columns_after_writer_cutover():
    executor = MigrationExecutor(connection)
    executor.migrate([BASE])
    old_apps = MigrationExecutor(connection).loader.project_state([BASE]).apps
    _legacy_metric, legacy_event, legacy_opportunity = _old_rows(old_apps)

    executor = MigrationExecutor(connection)
    executor.migrate([WRITER_CUTOVER])
    cutover_apps = MigrationExecutor(connection).loader.project_state(
        [WRITER_CUTOVER]
    ).apps
    CutoverEvent = cutover_apps.get_model("core", "Event")
    CutoverOpportunity = cutover_apps.get_model("core", "Opportunity")
    new_event, new_opportunity = _new_event_and_opportunity(
        CutoverEvent, CutoverOpportunity
    )

    executor = MigrationExecutor(connection)
    executor.migrate([PHYSICAL_DROP])

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT table_name
            FROM information_schema.columns
            WHERE table_schema=current_schema()
              AND table_name IN ('metrics', 'events', 'opportunities')
              AND column_name='source_timezone'
            """
        )
        assert cursor.fetchall() == []
        cursor.execute(
            """
            SELECT table_name
            FROM information_schema.columns
            WHERE table_schema=current_schema()
              AND table_name IN ('metrics', 'events', 'opportunities')
              AND column_name='source_timezone_id'
            """
        )
        assert len(cursor.fetchall()) == 3
        cursor.execute(
            """
            SELECT tgname
            FROM pg_trigger
            WHERE tgrelid IN ('metrics'::regclass, 'events'::regclass,
                              'opportunities'::regclass)
              AND tgname IN ('sync_metric_source_timezone',
                             'sync_events_source_timezone',
                             'sync_opportunities_source_timezone')
              AND NOT tgisinternal
            """
        )
        assert cursor.fetchall() == []
        cursor.execute(
            """
            SELECT proname
            FROM pg_proc
            WHERE pronamespace=current_schema()::regnamespace
              AND proname IN ('sync_metric_source_timezone',
                              'sync_intelligence_source_timezone')
            """
        )
        assert cursor.fetchall() == []

    assert Event.objects.get(pk=legacy_event.pk).source_timezone_reference_id is None
    assert (
        Event.objects.get(pk=new_event.pk).source_timezone_reference_id == "UTC"
    )
    assert (
        Opportunity.objects.get(pk=legacy_opportunity.pk)
        .source_timezone_reference_id
        is None
    )
    assert (
        Opportunity.objects.get(pk=new_opportunity.pk).source_timezone_reference_id
        == "UTC"
    )
