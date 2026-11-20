"""Protect a reused frozen source's physical run without duplicating source text."""

from typing import ClassVar

import django.db.models.deletion
from django.contrib.postgres.operations import AddIndexConcurrently
from django.db import migrations, models


class Migration(migrations.Migration):
    atomic = False
    dependencies: ClassVar[list[tuple[str, str]]] = [
        ("core", "0223_chatter_collection_operation")
    ]
    operations: ClassVar[list] = [
        migrations.RunSQL("SET lock_timeout = '5s'", "RESET lock_timeout"),
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.AddField(
                    model_name="originalcontentsource",
                    name="snapshot_run",
                    field=models.ForeignKey(
                        "core.originalcontentrun",
                        null=True,
                        db_index=False,
                        db_constraint=False,
                        related_name="frozen_source_uses",
                        on_delete=django.db.models.deletion.PROTECT,
                    ),
                ),
                migrations.RunSQL(
                    'ALTER TABLE "original_content_sources" ADD CONSTRAINT "fk_chatter_source_snapshot" '
                    'FOREIGN KEY ("snapshot_run_id") REFERENCES "original_content_runs" ("id") '
                    "DEFERRABLE INITIALLY DEFERRED NOT VALID",
                    'ALTER TABLE "original_content_sources" DROP CONSTRAINT "fk_chatter_source_snapshot"',
                ),
                migrations.RunSQL(
                    'ALTER TABLE "original_content_sources" VALIDATE CONSTRAINT "fk_chatter_source_snapshot"',
                    migrations.RunSQL.noop,
                ),
            ],
            state_operations=[
                migrations.AddField(
                    model_name="originalcontentsource",
                    name="snapshot_run",
                    field=models.ForeignKey(
                        "core.originalcontentrun",
                        null=True,
                        db_index=False,
                        related_name="frozen_source_uses",
                        on_delete=django.db.models.deletion.PROTECT,
                    ),
                )
            ],
        ),
        AddIndexConcurrently(
            model_name="originalcontentsource",
            index=models.Index(
                fields=["snapshot_run"],
                condition=models.Q(snapshot_run__isnull=False),
                name="idx_oc_source_snapshot",
            ),
        ),
        migrations.RunSQL("RESET lock_timeout", "SET lock_timeout = '5s'"),
    ]
