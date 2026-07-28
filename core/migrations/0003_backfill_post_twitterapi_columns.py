"""Backfill posts TwitterAPI columns from posts.raw.

Originally U2 of the posts.raw denormalization plan. The full backfill
in this migration ran all 50 UPDATE statements inside a single
transaction. On Render's free-tier Postgres (1GB disk), the WAL +
dead tuples accumulated over the 50 full-table scans exceeded the
available disk and crashed with:
  django.db.utils.OperationalError: could not extend file ...
That crash corrupted shared memory and forced Postgres to restart;
the entire transaction rolled back, leaving typed columns NULL.

The real backfill was moved to migration 0006_chunked_backfill.py,
which runs the same updates in committed chunks to avoid OOM on prod.
This migration is now a no-op so historical migration history stays
intact (0003 is referenced by older docs) but does no work.
"""

from django.db import migrations


def _backfill_columns(apps, schema_editor):
    """No-op; real backfill lives in 0006_chunked_backfill."""
    pass


def _backfill_reverse(apps, schema_editor):
    """Forward-only migration; no reverse."""
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0002_add_post_twitterapi_columns"),
    ]

    operations = [
        migrations.RunPython(_backfill_columns, _backfill_reverse),
    ]