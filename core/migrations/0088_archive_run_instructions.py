"""Retain legacy columns while recovering only actually stored instructions.

Old processes may still write jobless rows during this compatible rollout.
The same bounded operation is exposed by normalize_collection_run_jobs for
the post-rollout catch-up before making job mandatory in a later release.
"""

import hashlib
import json
import uuid
from typing import ClassVar

from django.db import migrations, transaction

BATCH_SIZE = 100


def _digest(value):
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()


def archive_run_instructions(
    apps, schema_editor, *, run_id=None, purposes=None, compatible_build=False
):
    alias = schema_editor.connection.alias
    Run = apps.get_model("core", "CollectionRun")
    Job = apps.get_model("core", "CollectionJob")
    after = None
    while True:
        with transaction.atomic(using=alias):
            with schema_editor.connection.cursor() as cursor:
                cursor.execute("SET LOCAL lock_timeout = '5s'")
            rows = (
                Run.objects.using(alias).select_for_update(of=("self",)).order_by("pk")
            )
            if run_id is not None:
                rows = rows.filter(pk=run_id)
            if purposes is not None:
                rows = rows.filter(purpose__in=purposes)
            if after is not None:
                rows = rows.filter(pk__gt=after)
            batch = list(
                rows.select_related("job").only(
                    "id",
                    "job_id",
                    "source_id",
                    "purpose",
                    "contract_id",
                    "scope",
                    "status",
                    "job__source_id",
                    "job__purpose",
                    "job__contract_id",
                    "job__definition",
                )[:BATCH_SIZE]
            )
            if not batch:
                break
            for run in batch:
                if run.job_id:
                    if not (
                        run.source_id == run.job.source_id
                        and run.purpose == run.job.purpose
                        and run.contract_id == run.job.contract_id
                        and run.scope == run.job.definition.get("scope")
                    ):
                        raise ValueError(
                            f"collection run instruction mismatch: {run.pk}"
                        )
                    continue
                # An old process can explicitly resume any catalog row, even a
                # successful one. Leave non-metric work for strict catch-up;
                # snapshot refresh also discards catalog/content runtime rows.
                if compatible_build and (
                    run.purpose != "metric" or run.status == "running"
                ):
                    continue
                if run.status == "running":
                    raise ValueError(
                        f"jobless running collection run must finish before archival: {run.pk}"
                    )
                identity = uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"pushinweight:archived-collection-run:v1:{run.pk}",
                )
                key = f"archive:run:{run.pk}"
                definition = {
                    "version": 1,
                    "scope": run.scope,
                    "schedule": None,
                    "budgets": None,
                    "historical_instructions": "unknown_beyond_stored_fields",
                    "execution": {"driver": "none", "executable": False},
                    "archived_run_id": str(run.pk),
                }
                values = {
                    "job_key": key,
                    "source_id": run.source_id,
                    "purpose": run.purpose,
                    "contract_id": run.contract_id,
                    "operation": "archived_run",
                    "mode": "historical",
                    "definition": definition,
                    "state": "completed",
                    "definition_sha256": _digest(
                        {
                            "source": run.source_id,
                            "purpose": run.purpose,
                            "contract": str(run.contract_id)
                            if run.contract_id
                            else None,
                            "operation": "archived_run",
                            "mode": "historical",
                            "definition": definition,
                        }
                    ),
                }
                # Check both namespaces, rather than assigning somebody else's job
                # on a deterministic UUID or unique-key collision.
                if (
                    Job.objects.using(alias)
                    .filter(job_key=key)
                    .exclude(pk=identity)
                    .exists()
                ):
                    raise ValueError(f"archival job key collision: {run.pk}")
                job, _ = Job.objects.using(alias).get_or_create(
                    pk=identity, defaults=values
                )
                if any(
                    getattr(job, name) != value for name, value in values.items()
                ) or any(
                    getattr(job, name) is not None
                    for name in (
                        "active_run_id",
                        "last_attempt_id",
                        "last_success_id",
                        "next_due_at",
                        "next_retry_at",
                    )
                ):
                    raise ValueError(f"archival job identity collision: {run.pk}")
                Run.objects.using(alias).filter(pk=run.pk, job__isnull=True).update(
                    job=job
                )
            after = batch[-1].pk


def archive_inactive_run_instructions(apps, schema_editor):
    archive_run_instructions(apps, schema_editor, compatible_build=True)


class Migration(migrations.Migration):
    atomic = False
    dependencies: ClassVar[list] = [("core", "0087_source_statistics_snapshot")]
    operations: ClassVar[list] = [
        migrations.RunPython(
            archive_inactive_run_instructions, migrations.RunPython.noop
        )
    ]
