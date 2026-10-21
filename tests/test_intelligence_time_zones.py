"""Extracted timezone wording stays in owned evidence during writer cutover."""

from datetime import UTC, datetime

import pytest
from django.db import connection
from django.db.models.deletion import ProtectedError

from core.intelligence_readers import event_document, opportunity_document
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
        source_timezone_reference_id=(
            event_zone if TimeZone.objects.filter(pk=event_zone).exists() else None
        ),
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
        source_timezone_reference_id=(
            opportunity_zone
            if TimeZone.objects.filter(pk=opportunity_zone).exists()
            else None
        ),
        first_seen_at=NOW,
        last_seen_at=NOW,
        opportunity_identity=f"{index:064x}",
        content_hash="b" * 64,
        raw_payload={"source_timezone": opportunity_zone},
    )
    return event, opportunity


def test_reader_documents_preserve_exact_reported_zone_from_raw_evidence():
    TimeZone.objects.get_or_create(code="Asia/Tokyo")
    TimeZone.objects.get_or_create(code="UTC")
    event, opportunity = make_records(
        event_zone="Pacific Time", opportunity_zone="GMT+8"
    )
    assert event.source_timezone_reference_id is None
    assert opportunity.source_timezone_reference_id is None
    assert event_document(event.pk, as_of=NOW)["source_timezone"] == "Pacific Time"
    assert opportunity_document(opportunity.pk, as_of=NOW)["source_timezone"] == "GMT+8"
    assert "source_timezone" not in {field.name for field in Event._meta.fields}
    assert "source_timezone" not in {field.name for field in Opportunity._meta.fields}


def test_canonical_references_and_unmatched_reported_values_coexist():
    TimeZone.objects.get_or_create(code="Asia/Tokyo")
    TimeZone.objects.get_or_create(code="UTC")
    event, opportunity = make_records(event_zone="Asia/Tokyo", opportunity_zone="CST")
    assert event.source_timezone_reference_id == "Asia/Tokyo"
    assert opportunity.source_timezone_reference_id is None
    assert event_document(event.pk, as_of=NOW)["source_timezone"] == "Asia/Tokyo"
    assert opportunity_document(opportunity.pk, as_of=NOW)["source_timezone"] == "CST"
    with pytest.raises(ProtectedError):
        TimeZone.objects.get(pk="Asia/Tokyo").delete()


def test_replaced_columns_are_out_of_orm_state_but_remain_for_old_instances():
    assert "source_timezone" not in {field.name for field in Event._meta.fields}
    assert "source_timezone" not in {field.name for field in Opportunity._meta.fields}
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE table_schema=current_schema()
              AND table_name IN ('metrics', 'events', 'opportunities')
              AND column_name='source_timezone'
            """
        )
        assert len(cursor.fetchall()) == 3
