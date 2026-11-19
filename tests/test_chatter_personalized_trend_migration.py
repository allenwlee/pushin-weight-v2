"""Rehearse the narrow provenance change with saved legacy records."""

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor

from core.models import OriginalContent
from tests.test_original_content_consideration import consideration

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.requires_postgres]
BASE = ("core", "0228_merge_staging_chatter_translation")
TARGET = ("core", "0229_chatter_personalized_trend_appearance")


def layout():
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT table_name, column_name, data_type, is_nullable "
            "FROM information_schema.columns WHERE table_schema = current_schema() "
            "ORDER BY table_name, ordinal_position"
        )
        return cursor.fetchall()


def appearance_constraint():
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT conname, convalidated, pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conrelid = 'original_content'::regclass "
            "AND conname LIKE 'ck_oc_appearance_kind%' ORDER BY conname"
        )
        (constraint,) = cursor.fetchall()
        assert constraint[:2] == ("ck_oc_appearance_kind", True)
        return constraint[2]


def test_personalized_trend_migration_preserves_legacy_records_and_schema():
    assert connection.settings_dict["NAME"].startswith("test_")
    executor = MigrationExecutor(connection)
    assert executor.loader.get_migration(*TARGET).dependencies == [BASE]
    executor.migrate([BASE])
    try:
        rows = [consideration(appearance_kind=kind) for kind in (
            "semantic_shortlist", "memory_only", "keyword_only", "release", None,
        )]
        ids = [row.pk for row in rows]
        saved = list(OriginalContent.objects.filter(pk__in=ids).order_by("pk").values())
        before_layout = layout()
        MigrationExecutor(connection).migrate([TARGET])
        assert layout() == before_layout
        assert list(OriginalContent.objects.filter(pk__in=ids).order_by("pk").values()) == saved
        assert "personalized_trend" in appearance_constraint()
        personalized = consideration(appearance_kind="personalized_trend")
        with pytest.raises(IntegrityError), transaction.atomic():
            OriginalContent.objects.filter(pk=personalized.pk).update(appearance_kind="personalized_trends")

        # Refuse a lossy reversal, retaining the current validated guard and data.
        with pytest.raises(IntegrityError):
            MigrationExecutor(connection).migrate([BASE])
        assert "personalized_trend" in appearance_constraint()
        personalized.refresh_from_db()
        assert personalized.appearance_kind == "personalized_trend"
        personalized.delete()

        MigrationExecutor(connection).migrate([BASE])
        assert "personalized_trend" not in appearance_constraint()
        with pytest.raises(IntegrityError), transaction.atomic():
            OriginalContent.objects.filter(pk=rows[0].pk).update(appearance_kind="personalized_trend")
        assert list(OriginalContent.objects.filter(pk__in=ids).order_by("pk").values()) == saved
        assert layout() == before_layout
    finally:
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
