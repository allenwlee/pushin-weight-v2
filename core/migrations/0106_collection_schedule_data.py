"""Copy dispatch settings while keeping the preceding reader's compatibility map."""

import uuid
from typing import ClassVar

from django.db import migrations


def forward(apps, schema_editor):
    Source = apps.get_model("core", "DataSource")
    Job = apps.get_model("core", "CollectionJob")
    alias = schema_editor.connection.alias
    for source in Source.objects.using(alias).all().iterator():
        metadata = dict(source.metadata)
        roles = metadata.get("collection_role_authorities", {})
        metrics = metadata.get("collection_job_authorities", {})
        limits = metadata.get("collection_role_dispatch_budget", None)
        if not isinstance(roles, dict) or not isinstance(metrics, dict):
            raise TypeError(f"Invalid existing collection authority: {source.pk}")
        # A replay also closes removals/takeovers made by the previous image
        # after an earlier copy. V2 authorities have no legacy map projection.
        for job in (
            Job.objects.using(alias)
            .select_for_update(nowait=True)
            .filter(source=source, instruction_version=1, authority_enabled=True)
            .order_by("pk")
        ):
            expected = (
                metrics.get(str(job.contract_id))
                if job.purpose == "metric"
                else roles.get(job.routine_role)
                if job.purpose == "catalog" and job.owner_account_id is None
                else str(job.pk)
            )
            if expected != str(job.pk):
                Job.objects.using(alias).filter(pk=job.pk).update(authority_enabled=False)
        for role, identifier in roles.items():
            job = Job.objects.using(alias).get(
                pk=uuid.UUID(identifier),
                source=source,
                purpose="catalog",
                mode="recurring",
            )
            scope = job.definition.get("scope", {})
            if job.instruction_version == 1 and scope.get("routine_role") != role:
                raise ValueError(
                    f"Collection role identity mismatch: {source.pk}/{role}"
                )
            Job.objects.using(alias).filter(pk=job.pk).update(
                routine_role=role, authority_enabled=job.state != "cancelled"
            )
        for contract, identifier in metrics.items():
            job = Job.objects.using(alias).get(
                pk=uuid.UUID(identifier),
                source=source,
                purpose="metric",
                contract_id=uuid.UUID(contract),
                mode="recurring",
            )
            Job.objects.using(alias).filter(pk=job.pk).update(authority_enabled=True)
        fields = []
        if limits is not None:
            ceilings = {"requests": 10000, "bytes": 33554432, "seconds": 3600}
            if (
                not isinstance(limits, dict)
                or set(limits) != set(ceilings)
                or any(
                    type(limits[k]) is not int or not 0 < limits[k] <= ceilings[k]
                    for k in ceilings
                )
            ):
                raise ValueError(
                    f"Invalid existing source dispatch budget: {source.pk}"
                )
            for key, value in limits.items():
                name = "dispatch_max_" + key
                setattr(source, name, value)
                fields.append(name)
        if fields:
            source.save(using=alias, update_fields=fields)


def reverse(apps, schema_editor):
    Source = apps.get_model("core", "DataSource")
    Job = apps.get_model("core", "CollectionJob")
    alias = schema_editor.connection.alias
    for source in Source.objects.using(alias).all().iterator():
        roles, metrics = {}, {}
        for job in Job.objects.using(alias).filter(
            source=source, authority_enabled=True, instruction_version=1
        ):
            if job.purpose == "metric":
                metrics[str(job.contract_id)] = str(job.pk)
            elif job.purpose == "catalog" and job.owner_account_id is None:
                roles[job.routine_role] = str(job.pk)
        # Account-partitioned authorities cannot be represented by the old map;
        # their jobs remain stored and inactive to the old dispatcher.
        source.metadata = {
            **source.metadata,
            "collection_role_authorities": roles,
            "collection_job_authorities": metrics,
            "collection_role_dispatch_budget": {
                "requests": source.dispatch_max_requests,
                "bytes": source.dispatch_max_bytes,
                "seconds": source.dispatch_max_seconds,
            },
        }
        source.save(using=alias, update_fields=["metadata"])


class Migration(migrations.Migration):
    dependencies: ClassVar[list] = [("core", "0105_collection_schedule_ownership")]
    operations: ClassVar[list] = [migrations.RunPython(forward, reverse)]
