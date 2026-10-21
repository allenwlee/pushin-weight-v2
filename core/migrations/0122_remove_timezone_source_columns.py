"""Remove the retired timezone string columns after all old writers drain."""

from typing import ClassVar

from django.db import migrations

DROP_SQL = """
ALTER TABLE metrics DROP CONSTRAINT IF EXISTS ck_metric_source_timezone_ref;
ALTER TABLE events DROP CONSTRAINT IF EXISTS ck_events_source_timezone_ref;
ALTER TABLE opportunities DROP CONSTRAINT IF EXISTS ck_opportunities_source_timezone_ref;

DROP TRIGGER IF EXISTS sync_metric_source_timezone ON metrics;
DROP TRIGGER IF EXISTS sync_events_source_timezone ON events;
DROP TRIGGER IF EXISTS sync_opportunities_source_timezone ON opportunities;
DROP FUNCTION IF EXISTS sync_metric_source_timezone();
DROP FUNCTION IF EXISTS sync_intelligence_source_timezone();

ALTER TABLE metrics DROP COLUMN source_timezone;
ALTER TABLE events DROP COLUMN source_timezone;
ALTER TABLE opportunities DROP COLUMN source_timezone;
"""


class Migration(migrations.Migration):
    dependencies: ClassVar[list] = [
        ("core", "0121_timezone_source_writer_cutover"),
    ]

    operations: ClassVar[list] = [
        migrations.RunSQL("SET LOCAL lock_timeout='5s'", migrations.RunSQL.noop),
        migrations.RunSQL(DROP_SQL, reverse_sql=None),
    ]
