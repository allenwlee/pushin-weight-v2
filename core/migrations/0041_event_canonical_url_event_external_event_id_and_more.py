from __future__ import annotations

import hashlib
import re
import unicodedata
from urllib.parse import urlparse

import django.db.models.deletion
from django.db import migrations, models


def _title(value):
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return " ".join(re.findall(r"[\w]+", text, flags=re.UNICODE))


def _url(value):
    if not value:
        return None
    parsed = urlparse(value)
    if not parsed.scheme or not parsed.netloc:
        return value
    return parsed._replace(
        scheme=parsed.scheme.casefold(),
        netloc=parsed.netloc.casefold(),
        path=parsed.path.rstrip("/") or "/",
        fragment="",
    ).geturl()


def _backfill(apps, schema_editor):
    alias = schema_editor.connection.alias
    Event = apps.get_model("core", "Event")
    Evidence = apps.get_model("core", "EventEvidence")
    Opportunity = apps.get_model("core", "Opportunity")
    events = list(Event.objects.using(alias).all().order_by("id"))
    for event in events:
        updates = {}
        if not event.normalized_title:
            updates["normalized_title"] = _title(event.title)
        if updates:
            Event.objects.using(alias).filter(pk=event.pk).update(**updates)
        if not event.source_post_id and not event.source_url:
            continue
        evidence_hash = hashlib.sha256(f"legacy-event:{event.pk}".encode()).hexdigest()
        Evidence.objects.using(alias).get_or_create(
            event_id=event.pk,
            source_post_id=event.source_post_id,
            evidence_hash=evidence_hash,
            defaults={
                "source_url": event.source_url,
                "observed_title": event.title,
                "observed_organizer_name": event.organizer_name,
                "observed_start_value": event.start_value,
                "observed_start_precision": event.start_precision,
                "observed_end_value": event.end_value,
                "observed_end_precision": event.end_precision,
                "observed_at": event.last_seen_at,
                "extraction_version": event.extraction_version,
                "extraction_confidence": event.extraction_confidence,
                "raw_payload": event.raw_payload,
            },
        )

    canonical_by_occurrence = {}
    for event in events:
        if event.start_value is None and event.end_value is None:
            continue
        source_anchor = (
            ("url", _url(event.source_url))
            if event.source_url
            else ("post", event.source_post_id)
            if event.source_post_id
            else None
        )
        if source_anchor is None:
            continue
        key = (
            event.brand_id,
            _title(event.title),
            _title(event.organizer_name),
            event.start_value,
            event.start_precision,
            event.end_value,
            event.end_precision,
            source_anchor,
        )
        canonical = canonical_by_occurrence.setdefault(key, event)
        if canonical.pk == event.pk:
            continue
        Evidence.objects.using(alias).filter(event_id=event.pk).update(
            event_id=canonical.pk
        )
        Opportunity.objects.using(alias).filter(related_event_id=event.pk).update(
            related_event_id=canonical.pk
        )
        Event.objects.using(alias).filter(pk=canonical.pk).update(
            first_seen_at=min(canonical.first_seen_at, event.first_seen_at),
            last_seen_at=max(canonical.last_seen_at, event.last_seen_at),
        )
        canonical.first_seen_at = min(canonical.first_seen_at, event.first_seen_at)
        canonical.last_seen_at = max(canonical.last_seen_at, event.last_seen_at)
        Event.objects.using(alias).filter(pk=event.pk).delete()


class Migration(migrations.Migration):
    dependencies = [("core", "0040_postbrandclassificationjudgment_and_more")]
    operations = [
        migrations.AddField(
            model_name="event",
            name="canonical_url",
            field=models.URLField(blank=True, max_length=2048, null=True),
        ),
        migrations.AddField(
            model_name="event",
            name="external_event_source",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="event",
            name="external_event_id",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="event",
            name="normalized_title",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="event",
            name="source_post",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="extracted_events",
                to="core.post",
            ),
        ),
        migrations.CreateModel(
            name="EventEvidence",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("source_url", models.URLField(blank=True, max_length=2048, null=True)),
                ("observed_title", models.TextField()),
                ("observed_organizer_name", models.TextField(blank=True, default="")),
                (
                    "observed_start_value",
                    models.CharField(blank=True, max_length=64, null=True),
                ),
                (
                    "observed_start_precision",
                    models.CharField(
                        choices=[
                            ("datetime", "Date and time"),
                            ("day", "Day"),
                            ("month", "Month"),
                            ("year", "Year"),
                            ("unknown", "Unknown"),
                        ],
                        default="unknown",
                        max_length=16,
                    ),
                ),
                (
                    "observed_end_value",
                    models.CharField(blank=True, max_length=64, null=True),
                ),
                (
                    "observed_end_precision",
                    models.CharField(
                        choices=[
                            ("datetime", "Date and time"),
                            ("day", "Day"),
                            ("month", "Month"),
                            ("year", "Year"),
                            ("unknown", "Unknown"),
                        ],
                        default="unknown",
                        max_length=16,
                    ),
                ),
                ("observed_at", models.DateTimeField()),
                ("extraction_version", models.TextField(blank=True, null=True)),
                ("extraction_confidence", models.FloatField(blank=True, null=True)),
                ("raw_payload", models.JSONField(blank=True, null=True)),
                ("evidence_hash", models.CharField(max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "event",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="evidence",
                        to="core.event",
                    ),
                ),
                (
                    "source_post",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="event_evidence",
                        to="core.post",
                    ),
                ),
            ],
            options={
                "db_table": "event_evidence",
                "ordering": ["event_id", "observed_at", "id"],
            },
        ),
        migrations.AddConstraint(
            model_name="eventevidence",
            constraint=models.UniqueConstraint(
                fields=("event", "source_post", "evidence_hash"),
                name="uq_event_evidence_observation",
            ),
        ),
        migrations.AddConstraint(
            model_name="eventevidence",
            constraint=models.CheckConstraint(
                condition=models.Q(source_post__isnull=False)
                | (models.Q(source_url__isnull=False) & ~models.Q(source_url="")),
                name="ck_event_evidence_has_source",
            ),
        ),
        migrations.AddConstraint(
            model_name="eventevidence",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        ("observed_start_precision", "unknown"),
                        ("observed_start_value__isnull", True),
                    ),
                    models.Q(
                        ("observed_start_precision", "day"),
                        ("observed_start_value__regex", "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"),
                    ),
                    models.Q(
                        ("observed_start_precision", "month"),
                        ("observed_start_value__regex", "^[0-9]{4}-[0-9]{2}$"),
                    ),
                    models.Q(
                        ("observed_start_precision", "year"),
                        ("observed_start_value__regex", "^[0-9]{4}$"),
                    ),
                    models.Q(
                        ("observed_start_precision", "datetime"),
                        (
                            "observed_start_value__regex",
                            "^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}(:[0-9]{2}(\\.[0-9]+)?)?(Z|[+-][0-9]{2}:[0-9]{2})$",
                        ),
                    ),
                    _connector="OR",
                ),
                name="ck_event_evidence_start_precision",
            ),
        ),
        migrations.AddConstraint(
            model_name="eventevidence",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        ("observed_end_precision", "unknown"),
                        ("observed_end_value__isnull", True),
                    ),
                    models.Q(
                        ("observed_end_precision", "day"),
                        ("observed_end_value__regex", "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"),
                    ),
                    models.Q(
                        ("observed_end_precision", "month"),
                        ("observed_end_value__regex", "^[0-9]{4}-[0-9]{2}$"),
                    ),
                    models.Q(
                        ("observed_end_precision", "year"),
                        ("observed_end_value__regex", "^[0-9]{4}$"),
                    ),
                    models.Q(
                        ("observed_end_precision", "datetime"),
                        (
                            "observed_end_value__regex",
                            "^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}(:[0-9]{2}(\\.[0-9]+)?)?(Z|[+-][0-9]{2}:[0-9]{2})$",
                        ),
                    ),
                    _connector="OR",
                ),
                name="ck_event_evidence_end_precision",
            ),
        ),
        migrations.RunPython(_backfill, migrations.RunPython.noop),
    ]
