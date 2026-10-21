"""Shared zone references must not rewrite extracted evidence or reader output."""

import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from io import StringIO
from threading import Event as ThreadEvent

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, connection, transaction
from django.db.models.deletion import ProtectedError

from core.intelligence_readers import event_document, opportunity_document
from core.intelligence_time_zones import OWNERS, map_intelligence_time_zones
from core.models import Brand, Event, Opportunity, TimeZone

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]

NOW = datetime(2026, 10, 21, 0, 0, tzinfo=UTC)


def make_records(*, event_zone="Asia/Tokyo", opportunity_zone="UTC", index=0):
    brand, _ = Brand.objects.get_or_create(
        nickname="zone-fixture", defaults={"display_name": "Zone fixture"}
    )
    event = Event.objects.create(
        brand=brand,
        source_url="https://example.test/event",
        title="Workshop",
        organizer_name="Fixture",
        start_value="2026-10",
        start_precision="month",
        source_timezone=event_zone,
        first_seen_at=NOW,
        last_seen_at=NOW,
        event_identity=f"{index:064x}",
        content_hash="a" * 64,
        raw_payload={"source_timezone": event_zone, "source_schedule_text": "October"},
    )
    opportunity = Opportunity.objects.create(
        brand=brand,
        related_event=event,
        source_url="https://example.test/opportunity",
        sponsor_name="Fixture",
        opportunity_type="contest",
        action_type="submit",
        benefit_type="prize",
        close_value="2026-10-25",
        close_precision="day",
        source_timezone=opportunity_zone,
        first_seen_at=NOW,
        last_seen_at=NOW,
        opportunity_identity=f"{index:064x}",
        content_hash="b" * 64,
        raw_payload={"source_timezone": opportunity_zone},
    )
    return event, opportunity


def test_reader_documents_dates_and_source_evidence_characterization():
    event, opportunity = make_records()
    before = (
        event_document(event.pk, as_of=NOW),
        opportunity_document(opportunity.pk, as_of=NOW),
    )
    fields = (
        Event.objects.values().get(pk=event.pk),
        Opportunity.objects.values().get(pk=opportunity.pk),
    )
    call_command("seed_shared_vocabulary", catalogue=["time_zones"])
    assert (
        event_document(event.pk, as_of=NOW),
        opportunity_document(opportunity.pk, as_of=NOW),
    ) == before
    assert (
        Event.objects.values().get(pk=event.pk),
        Opportunity.objects.values().get(pk=opportunity.pk),
    ) == fields


def test_mapping_preserves_every_original_field_and_complete_reader_documents():
    event, opportunity = make_records()
    documents = (
        event_document(event.pk, as_of=NOW),
        opportunity_document(opportunity.pk, as_of=NOW),
    )
    before = [
        Event.objects.values().get(pk=event.pk),
        Opportunity.objects.values().get(pk=opportunity.pk),
    ]
    TimeZone.objects.bulk_create([TimeZone(code="Asia/Tokyo"), TimeZone(code="UTC")])
    for owner in OWNERS:
        assert map_intelligence_time_zones(owner=owner, apply=True)["updated"] == 1
    after = [
        Event.objects.values().get(pk=event.pk),
        Opportunity.objects.values().get(pk=opportunity.pk),
    ]
    for old, new in zip(before, after, strict=True):
        assert old.pop("source_timezone_reference_id") is None
        assert new.pop("source_timezone_reference_id") == new["source_timezone"]
    assert after == before
    assert (
        event_document(event.pk, as_of=NOW),
        opportunity_document(opportunity.pk, as_of=NOW),
    ) == documents


@pytest.mark.parametrize("owner", OWNERS)
def test_bounded_late_mapping_resumes_idempotently_without_resolving_offsets(owner):
    zones = ["UTC", "US/Eastern", "UTC+8", "CST", "", None]
    for index, zone in enumerate(zones):
        make_records(event_zone=zone, opportunity_zone=zone, index=index)
    TimeZone.objects.bulk_create([TimeZone(code="UTC"), TimeZone(code="US/Eastern")])
    first = map_intelligence_time_zones(
        owner=owner, apply=True, batch_size=1, max_batches=1
    )
    assert first["updated"] == 1 and first["remaining_resolvable"] == 1
    second = map_intelligence_time_zones(
        owner=owner,
        apply=True,
        after_id=first["after_id"],
        batch_size=1,
        max_batches=1,
    )
    assert second["updated"] == 1 and second["remaining_resolvable"] == 0
    assert second["unmatched_count"] == second["absent_count"] == 2
    assert map_intelligence_time_zones(owner=owner, apply=True)["updated"] == 0
    rows = OWNERS[owner].objects.order_by("pk")
    assert list(rows.values_list("source_timezone", flat=True)) == zones
    assert list(rows.values_list("source_timezone_reference_id", flat=True)) == [
        "UTC",
        "US/Eastern",
        None,
        None,
        None,
        None,
    ]


@pytest.mark.parametrize("owner", OWNERS)
def test_preview_and_invalid_controls_never_write(owner):
    make_records(event_zone="UTC", opportunity_zone="UTC")
    TimeZone.objects.create(code="UTC")
    output = StringIO()
    call_command("map_intelligence_time_zones", owner=owner, stdout=output)
    result = json.loads(output.getvalue())
    assert result["updated"] == 0 and result["apply"] is False
    assert result["examined"] == result["remaining_resolvable"] == 1
    for options in [
        {"batch_size": 0},
        {"max_batches": 10001},
        {"after_id": -1},
        {"owner": "metrics"},
        {"apply": True, "dry_run": True},
    ]:
        arguments = {"owner": owner, **options}
        with pytest.raises(CommandError):
            call_command("map_intelligence_time_zones", **arguments)
    assert (
        not OWNERS[owner]
        .objects.filter(source_timezone_reference__isnull=False)
        .exists()
    )


@pytest.mark.parametrize("owner", OWNERS)
def test_old_raw_updates_resolve_clear_and_protect_exact_references(owner):
    TimeZone.objects.bulk_create([TimeZone(code="UTC"), TimeZone(code="US/Eastern")])
    make_records(event_zone="UTC", opportunity_zone="UTC")
    row = OWNERS[owner].objects.get()
    assert row.source_timezone_reference_id == "UTC"
    for zone, reference in [
        ("US/Eastern", "US/Eastern"),
        ("UTC+8", None),
        ("CST", None),
        (None, None),
        ("", None),
        ("UTC", "UTC"),
    ]:
        with connection.cursor() as c:
            c.execute(
                f"UPDATE {owner} SET source_timezone=%s WHERE id=%s", [zone, row.pk]
            )
        row.refresh_from_db()
        assert (
            row.source_timezone == zone
            and row.source_timezone_reference_id == reference
        )
    with pytest.raises(ProtectedError):
        TimeZone.objects.get(pk="UTC").delete()


@pytest.mark.parametrize("owner", OWNERS)
@pytest.mark.parametrize(
    "raw,reference",
    [
        ("UTC", "US/Eastern"),
        ("UTC", "Missing/Zone"),
        (None, "UTC"),
        ("", "UTC"),
        ("UTC+8", "UTC"),
    ],
)
def test_raw_sql_rejects_contradictory_or_absent_reported_zone(owner, raw, reference):
    TimeZone.objects.bulk_create([TimeZone(code="UTC"), TimeZone(code="US/Eastern")])
    make_records(event_zone=raw, opportunity_zone=raw)
    row = OWNERS[owner].objects.get()
    with (
        pytest.raises(IntegrityError, match="timezone reference"),
        transaction.atomic(),
        connection.cursor() as c,
    ):
        c.execute(
            f"UPDATE {owner} SET source_timezone_id=%s WHERE id=%s", [reference, row.pk]
        )


@pytest.mark.parametrize("owner", OWNERS)
@pytest.mark.django_db(transaction=True)
def test_mapper_rechecks_a_reported_zone_after_a_concurrent_old_writer(owner):
    from django.db import connections

    make_records(event_zone="UTC", opportunity_zone="UTC")
    TimeZone.objects.create(code="UTC")
    row = OWNERS[owner].objects.get()
    started = ThreadEvent()
    backend = []

    def map_one():
        try:
            with connections["default"].cursor() as c:
                c.execute("SELECT pg_backend_pid()")
                backend.append(c.fetchone()[0])
            started.set()
            return map_intelligence_time_zones(
                owner=owner, apply=True, batch_size=1, max_batches=1
            )
        finally:
            connections["default"].close()

    with ThreadPoolExecutor(max_workers=1) as pool:
        with transaction.atomic(), connection.cursor() as c:
            c.execute(f"SELECT id FROM {owner} WHERE id=%s FOR UPDATE", [row.pk])
            future = pool.submit(map_one)
            assert started.wait(5)
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                c.execute(
                    "SELECT wait_event_type FROM pg_stat_activity WHERE pid=%s",
                    [backend[0]],
                )
                if c.fetchone() == ("Lock",):
                    break
                time.sleep(0.01)
            else:
                pytest.fail("Mapper did not reach the expected row-lock wait")
            c.execute(
                f"UPDATE {owner} SET source_timezone='UTC+8' WHERE id=%s", [row.pk]
            )
        result = future.result(timeout=10)
    row.refresh_from_db()
    assert result["updated"] == 0
    assert row.source_timezone == "UTC+8" and row.source_timezone_reference_id is None


@pytest.mark.usefixtures("isolated_migration_database")
@pytest.mark.django_db(transaction=True)
def test_populated_migration_reverse_preserves_all_source_fields_and_old_writers():
    from django.db.migrations.executor import MigrationExecutor

    from tests.collection_fixtures import historical_fixture_models

    base = ("core", "0117_metric_unit_references")
    target = ("core", "0118_intelligence_timezone_references")
    MigrationExecutor(connection).migrate([base])
    old = MigrationExecutor(connection).loader.project_state([base]).apps
    old.get_model("core", "TimeZone").objects.create(code="UTC")
    with historical_fixture_models(old):
        make_records(event_zone="UTC", opportunity_zone="UTC+8")
    originals = {}
    for name in ("Event", "Opportunity"):
        originals[name] = list(
            old.get_model("core", name).objects.order_by("pk").values()
        )
    MigrationExecutor(connection).migrate([target])
    for name, model in [("Event", Event), ("Opportunity", Opportunity)]:
        rows = list(model.objects.order_by("pk").values())
        for row in rows:
            assert row.pop("source_timezone_reference_id") == (
                "UTC" if row["source_timezone"] == "UTC" else None
            )
        assert rows == originals[name]
        fields = originals[name][0].copy()
        fields.pop("id")
        fields[f"{name.lower()}_identity"] = "a" * 64
        fields["source_timezone"] = "UTC"
        legacy = old.get_model("core", name).objects.create(**fields)
        assert model.objects.get(pk=legacy.pk).source_timezone_reference_id == "UTC"
        old.get_model("core", name).objects.filter(pk=legacy.pk).update(
            source_timezone=None
        )
        assert model.objects.get(pk=legacy.pk).source_timezone_reference_id is None
    MigrationExecutor(connection).migrate([base])
    for name in ("Event", "Opportunity"):
        assert (
            list(
                old.get_model("core", name)
                .objects.exclude(**{f"{name.lower()}_identity": "a" * 64})
                .order_by("pk")
                .values()
            )
            == originals[name]
        )
    MigrationExecutor(connection).migrate([target])
