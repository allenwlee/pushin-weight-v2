"""Detach retired collection documents from the ORM before physical deletion.

The database keeps the 13 columns and old statistics index during this release
so already-running service images remain compatible. Temporary defaults satisfy
the old NOT NULL columns when the new ORM omits them on INSERT. A later guarded
migration removes the physical storage after every active image has advanced.
"""

from typing import ClassVar

from django.db import migrations


class Migration(migrations.Migration):

    dependencies: ClassVar[list] = [
        ('core', '0195_rg6_archive_import_scope_guard'),
    ]

    operations: ClassVar[list] = [migrations.SeparateDatabaseAndState(
        database_operations=[migrations.RunSQL(
            "SET LOCAL lock_timeout='2s'; SET LOCAL statement_timeout='30s'; "
            "ALTER TABLE collection_runs "
            "ALTER COLUMN request_params SET DEFAULT '{}'::jsonb, "
            "ALTER COLUMN source_metadata SET DEFAULT '{}'::jsonb; "
            "ALTER TABLE collection_scope_runs "
            "ALTER COLUMN ownership SET DEFAULT '{}'::jsonb, "
            "ALTER COLUMN cursor_history SET DEFAULT '[]'::jsonb, "
            "ALTER COLUMN envelopes SET DEFAULT '[]'::jsonb; "
            "ALTER TABLE collection_observations "
            "ALTER COLUMN dimensions SET DEFAULT '{}'::jsonb, "
            "ALTER COLUMN source_metadata SET DEFAULT '{}'::jsonb;",
            reverse_sql=migrations.RunSQL.noop,
        )],
        state_operations=[
        migrations.RemoveConstraint(
            model_name='collectionobservation',
            name='uq_source_statistics_snapshot',
        ),
        migrations.RemoveField(
            model_name='collectionobservation',
            name='dimensions',
        ),
        migrations.RemoveField(
            model_name='collectionobservation',
            name='envelopes',
        ),
        migrations.RemoveField(
            model_name='collectionobservation',
            name='groups',
        ),
        migrations.RemoveField(
            model_name='collectionobservation',
            name='listing',
        ),
        migrations.RemoveField(
            model_name='collectionobservation',
            name='source_metadata',
        ),
        migrations.RemoveField(
            model_name='collectionrun',
            name='invocations',
        ),
        migrations.RemoveField(
            model_name='collectionrun',
            name='raw_payload',
        ),
        migrations.RemoveField(
            model_name='collectionrun',
            name='report',
        ),
        migrations.RemoveField(
            model_name='collectionrun',
            name='request_params',
        ),
        migrations.RemoveField(
            model_name='collectionrun',
            name='source_metadata',
        ),
        migrations.RemoveField(
            model_name='collectionscoperun',
            name='cursor_history',
        ),
        migrations.RemoveField(
            model_name='collectionscoperun',
            name='envelopes',
        ),
        migrations.RemoveField(
            model_name='collectionscoperun',
            name='ownership',
        ),
        ],
    )]
