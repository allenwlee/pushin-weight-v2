"""Upgrade proof for canonical event occurrences and source evidence."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]

BEFORE = [("core", "0040_postbrandclassificationjudgment_and_more")]
AFTER = [("core", "0041_event_canonical_url_event_external_event_id_and_more")]


def test_migration_preserves_evidence_and_reconciles_only_exact_dated_occurrences():
    executor = MigrationExecutor(connection)
    try:
        executor.migrate(BEFORE)
        old_apps = executor.loader.project_state(BEFORE).apps
        Brand = old_apps.get_model("core", "Brand")
        Event = old_apps.get_model("core", "Event")
        Opportunity = old_apps.get_model("core", "Opportunity")
        Post = old_apps.get_model("core", "Post")

        brand = Brand.objects.create(nickname="qwen-migration", display_name="Qwen")
        now = timezone.now()
        posts = [
            Post.objects.create(tweet_id=f"legacy-event-{index}", text="source")
            for index in range(6)
        ]

        def event(index, *, title, start_value, source_url=None):
            return Event.objects.create(
                brand=brand,
                source_post=posts[index],
                source_url=source_url or f"https://x.com/qwen/status/{index}",
                title=title,
                organizer_name="Qwen" if index != 1 else "qwen",
                attendance_mode="online_live",
                start_value=start_value,
                start_precision="day" if start_value else "unknown",
                first_seen_at=now + timedelta(minutes=index),
                last_seen_at=now + timedelta(minutes=index),
                event_identity=str(index) * 64,
            )

        september = event(
            0,
            title="Qwen Cloud Hackathon",
            start_value="2026-09-20",
            source_url="https://events.qwen.example/cloud-hackathon",
        )
        duplicate = event(
            1,
            title="QWEN cloud-hackathon!",
            start_value="2026-09-20",
            source_url="https://events.qwen.example/cloud-hackathon/",
        )
        october = event(
            2,
            title="Qwen Cloud Hackathon",
            start_value="2026-10-20",
        )
        event(3, title="Qwen Cloud Hackathon", start_value=None)
        event(4, title="Qwen Cloud Hackathon", start_value=None)
        same_day_different_source = event(
            5,
            title="Qwen Cloud Hackathon",
            start_value="2026-09-20",
        )
        opportunity = Opportunity.objects.create(
            brand=brand,
            related_event=duplicate,
            source_post=posts[1],
            sponsor_name="Qwen",
            opportunity_type="contest",
            action_type="submit a project",
            benefit_type="prize",
            first_seen_at=now,
            last_seen_at=now,
            opportunity_identity="o" * 64,
        )

        executor = MigrationExecutor(connection)
        executor.migrate(AFTER)
        apps = executor.loader.project_state(AFTER).apps
        Event = apps.get_model("core", "Event")
        Evidence = apps.get_model("core", "EventEvidence")
        Opportunity = apps.get_model("core", "Opportunity")

        assert Event.objects.count() == 5
        assert Evidence.objects.count() == 6
        canonical = Event.objects.get(pk=september.pk)
        assert canonical.pk == september.pk
        assert canonical.normalized_title == "qwen cloud hackathon"
        assert canonical.canonical_url is None
        assert canonical.evidence.count() == 2
        assert canonical.last_seen_at == now + timedelta(minutes=1)
        assert (
            Opportunity.objects.get(pk=opportunity.pk).related_event_id == canonical.pk
        )
        assert Event.objects.get(pk=same_day_different_source.pk).evidence.count() == 1
        assert Event.objects.filter(start_value="2026-09-20").count() == 2
        assert Event.objects.get(pk=october.pk).evidence.count() == 1
        assert Event.objects.filter(start_value__isnull=True).count() == 2
    finally:
        MigrationExecutor(connection).migrate(
            MigrationExecutor(connection).loader.graph.leaf_nodes()
        )
