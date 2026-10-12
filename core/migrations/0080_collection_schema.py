import hashlib
import json
import uuid
from copy import deepcopy
from typing import ClassVar

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    ).hexdigest()


def require_catalog_idle(apps, schema_editor):
    # Same lock as the catalog entry point, held until this atomic migration ends.
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_xact_lock(6842060924)")
        if not cursor.fetchone()[0]:
            raise RuntimeError("Stop the active HF catalog invocation before migrating")


def reset_sequence(schema_editor, model):
    from django.core.management.color import no_style

    for statement in schema_editor.connection.ops.sequence_reset_sql(
        no_style(), [model]
    ):
        schema_editor.execute(statement)


def sequence_position(schema_editor, model):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_sequence_last_value(pg_get_serial_sequence(%s, 'id')::regclass)",
            [model._meta.db_table],
        )
        return cursor.fetchone()[0] or 0


def merge_runs(apps, schema_editor):
    Run = apps.get_model("core", "CollectionRun")
    Old = apps.get_model("core", "HFModelCatalogRun")
    Scope = apps.get_model("core", "CollectionScopeRun")
    Source = apps.get_model("core", "DataSource")
    source, _ = Source.objects.get_or_create(
        pk="hf", defaults={"name": "Hugging Face", "source_type": "model_adoption"}
    )
    for old in Old.objects.order_by("pk").iterator(chunk_size=500):
        target = old.pk
        if Run.objects.filter(pk=target).exists():
            target = uuid.uuid5(
                uuid.NAMESPACE_URL, "pw:legacy-hf-catalog:" + str(old.pk)
            )
        if Run.objects.filter(pk=target).exists():
            raise RuntimeError("Catalog run identity collision requires reconciliation")
        if old.outcome not in {
            "pending",
            "running",
            "partial",
            "interrupted",
            "complete",
        }:
            raise RuntimeError("Unknown legacy catalog run outcome")
        status = "success" if old.outcome == "complete" else old.outcome
        if status == "success" and old.finished_at is None:
            raise RuntimeError(
                "Completed catalog run lacks its original completion timestamp"
            )
        Run.objects.create(
            id=target,
            batch_id=target,
            source=source,
            purpose="catalog",
            ingestion_key=digest(["catalog", "hf", str(old.pk)]),
            status=status,
            scope=old.scope,
            invocations=old.invocations,
            report=old.report,
            started_at=old.started_at,
            completed_at=old.finished_at,
            source_url="https://huggingface.co",
            request_count=sum(i.get("requests", 0) for i in old.invocations),
            source_metadata={
                "legacy_catalog": {"run_id": str(old.pk), "outcome": old.outcome}
            },
        )
        Run.objects.filter(pk=target).update(updated_at=old.updated_at)
        Scope.objects.filter(run_id=old.pk).update(run_id=target)


def restore_runs(apps, schema_editor):
    Run = apps.get_model("core", "CollectionRun")
    Old = apps.get_model("core", "HFModelCatalogRun")
    Scope = apps.get_model("core", "CollectionScopeRun")
    if Run.objects.filter(purpose="catalog").exclude(source_id="hf").exists():
        raise RuntimeError(
            "Other-source catalog history cannot be restored to the HF-only schema"
        )
    for run in Run.objects.filter(purpose="catalog", source_id="hf").iterator(
        chunk_size=500
    ):
        legacy = run.source_metadata.get("legacy_catalog", {})
        target = uuid.UUID(legacy.get("run_id", str(run.pk)))
        outcome = "complete" if run.status == "success" else run.status
        Old.objects.update_or_create(
            id=target,
            defaults={
                "scope": run.scope,
                "outcome": outcome,
                "invocations": run.invocations,
                "report": run.report,
                "finished_at": run.completed_at,
            },
        )
        Old.objects.filter(pk=target).update(
            started_at=run.started_at, updated_at=run.updated_at or run.started_at
        )
        Scope.objects.filter(run_id=run.pk).update(run_id=target)
        run.delete()


def update_product_pointers(apps, mapping):
    Product = apps.get_model("core", "Product")
    for product in Product.objects.exclude(hf_metadata={}).iterator(chunk_size=500):
        metadata = deepcopy(product.hf_metadata or {})
        changed = False
        for field in metadata.get("field_sources", {}).values():
            if not isinstance(field, dict):
                continue
            pointer = field.get("observation")
            if not isinstance(pointer, dict):
                continue
            replacement = mapping.get((str(pointer.get("run_id")), pointer.get("id")))
            if replacement:
                field["observation"] = {**pointer, **replacement}
                changed = True
        if changed:
            Product.objects.filter(pk=product.pk).update(hf_metadata=metadata)


def merge_observations(apps, schema_editor):
    Old = apps.get_model("core", "HFModelCatalogObservation")
    Observation = apps.get_model("core", "CollectionObservation")
    Run = apps.get_model("core", "CollectionRun")
    from django.db.models import Max

    next_id = (
        max(
            Observation.objects.aggregate(value=Max("id"))["value"] or 0,
            sequence_position(schema_editor, Observation),
        )
        + 1
    )
    mapping = {}
    for old in (
        Old.objects.select_related("namespace_run")
        .order_by("pk")
        .iterator(chunk_size=500)
    ):
        run = Run.objects.get(pk=old.namespace_run.run_id)
        legacy_run = run.source_metadata["legacy_catalog"]["run_id"]
        obs = Observation.objects.create(
            id=next_id,
            run=run,
            scope_run_id=old.namespace_run_id,
            resource_key=old.repo_key,
            source_identifier=old.repo_id,
            source_subject_kind="repository",
            observation_key=digest(
                ["catalog", str(run.pk), old.namespace_run.scope_key, old.repo_key]
            ),
            product_id=old.product_id,
            created_product=old.created_product,
            listing=old.listing,
            envelopes=old.envelopes,
            groups=old.groups,
            processing_outcome=old.outcome,
            observed_at=old.observed_at,
            source_metadata={
                "legacy_catalog": {"run_id": legacy_run, "observation_id": old.pk}
            },
        )
        Observation.objects.filter(pk=obs.pk).update(updated_at=old.updated_at)
        mapping[(legacy_run, old.pk)] = {"run_id": str(run.pk), "id": obs.pk}
        next_id += 1
    update_product_pointers(apps, mapping)
    for run in Run.objects.filter(purpose="catalog").iterator(chunk_size=500):
        Run.objects.filter(pk=run.pk).update(
            selected_count=run.observations.count(),
            success_count=run.observations.filter(
                processing_outcome="complete"
            ).count(),
        )
    # Never reuse previously consumed numeric IDs, including deleted-row gaps.
    if next_id > 1:
        with schema_editor.connection.cursor() as cursor:
            cursor.execute(
                "SELECT setval(pg_get_serial_sequence(%s, 'id'), %s, true)",
                [Observation._meta.db_table, next_id - 1],
            )


def restore_observations(apps, schema_editor):
    Old = apps.get_model("core", "HFModelCatalogObservation")
    Observation = apps.get_model("core", "CollectionObservation")
    mapping = {}
    rows = Observation.objects.filter(
        run__purpose="catalog", run__source_id="hf"
    ).select_related("run")
    reserved = {
        obs.source_metadata["legacy_catalog"]["observation_id"]
        for obs in rows
        if "legacy_catalog" in obs.source_metadata
    }
    next_id = max(reserved, default=0) + 1
    for obs in rows.order_by("pk").iterator(chunk_size=500):
        if (
            obs.scope_run_id is None
            or obs.source_subject_kind != "repository"
            or obs.mapping_id is not None
            or obs.values.exists()
        ):
            raise RuntimeError(
                "Catalog observation cannot be represented in the previous HF schema"
            )
        legacy = obs.source_metadata.get("legacy_catalog", {})
        old_id = legacy.get("observation_id")
        if old_id is None:
            old_id = next_id
            next_id += 1
        old_run = obs.run.source_metadata.get("legacy_catalog", {}).get(
            "run_id", str(obs.run_id)
        )
        Old.objects.create(
            id=old_id,
            namespace_run_id=obs.scope_run_id,
            repo_key=obs.resource_key,
            repo_id=obs.source_identifier,
            product_id=obs.product_id,
            created_product=obs.created_product,
            listing=obs.listing,
            envelopes=obs.envelopes,
            groups=obs.groups,
            outcome=obs.processing_outcome or "pending",
        )
        Old.objects.filter(pk=old_id).update(
            observed_at=obs.observed_at, updated_at=obs.updated_at or obs.observed_at
        )
        mapping[(str(obs.run_id), obs.pk)] = {"run_id": old_run, "id": old_id}
    update_product_pointers(apps, mapping)
    Observation.objects.filter(run__purpose="catalog", run__source_id="hf").delete()
    reset_sequence(schema_editor, Old)


class Migration(migrations.Migration):
    atomic = True
    dependencies: ClassVar[list] = [("core", "0079_original_content_physical_names")]
    operations: ClassVar[list] = [
        migrations.RunSQL(
            "SET LOCAL lock_timeout = '5s'", reverse_sql=migrations.RunSQL.noop
        ),
        migrations.RunPython(
            require_catalog_idle, reverse_code=migrations.RunPython.noop
        ),
        # Explicit db_table names already preserve all physical relationships.
        # Rename Python state together; rename tables only after history merges.
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RenameModel("MetricCollectionRun", "CollectionRun"),
                migrations.RenameModel("MetricObservation", "CollectionObservation"),
                migrations.RenameModel(
                    "HFModelCatalogNamespaceRun", "CollectionScopeRun"
                ),
            ]
        ),
        migrations.RemoveConstraint("collectionrun", "ck_run_terminal"),
        migrations.RemoveConstraint(
            "collectionscoperun", "uq_hf_catalog_run_namespace"
        ),
        migrations.RenameField("collectionscoperun", "namespace", "scope_key"),
        migrations.AddField(
            "collectionrun",
            "purpose",
            models.CharField(db_default="metric", default="metric", max_length=16),
        ),
        migrations.AddField(
            "collectionrun", "scope", models.JSONField(db_default={}, default=dict)
        ),
        migrations.AddField(
            "collectionrun",
            "invocations",
            models.JSONField(db_default=[], default=list),
        ),
        migrations.AddField(
            "collectionrun", "report", models.JSONField(db_default={}, default=dict)
        ),
        migrations.AddField(
            "collectionrun",
            "updated_at",
            models.DateTimeField(auto_now=True, null=True),
        ),
        migrations.AddField(
            "collectionscoperun",
            "scope_kind",
            models.CharField(default="namespace", max_length=32),
        ),
        migrations.AddField(
            "collectionobservation",
            "scope_run",
            models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="observations",
                to="core.collectionscoperun",
            ),
        ),
        migrations.AddField(
            "collectionobservation",
            "resource_key",
            models.CharField(max_length=256, null=True),
        ),
        migrations.AddField(
            "collectionobservation",
            "product",
            models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="core.product",
            ),
        ),
        migrations.AddField(
            "collectionobservation",
            "created_product",
            models.BooleanField(db_default=False, default=False),
        ),
        migrations.AddField(
            "collectionobservation",
            "listing",
            models.JSONField(db_default={}, default=dict),
        ),
        migrations.AddField(
            "collectionobservation",
            "envelopes",
            models.JSONField(db_default=[], default=list),
        ),
        migrations.AddField(
            "collectionobservation",
            "groups",
            models.JSONField(db_default={}, default=dict),
        ),
        migrations.AddField(
            "collectionobservation",
            "processing_outcome",
            models.CharField(max_length=64, null=True),
        ),
        migrations.AddField(
            "collectionobservation",
            "updated_at",
            models.DateTimeField(auto_now=True, null=True),
        ),
        migrations.AlterField(
            "collectionrun",
            "contract",
            models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to="core.metriccollectioncontract",
            ),
        ),
        migrations.AlterField(
            "collectionrun", "lease_expires_at", models.DateTimeField(null=True)
        ),
        migrations.AlterField(
            "collectionscoperun", "scope_key", models.CharField(max_length=256)
        ),
        migrations.AddConstraint(
            "collectionrun",
            models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        ("contract__isnull", False),
                        ("lease_expires_at__isnull", False),
                        ("purpose", "metric"),
                        models.Q(
                            models.Q(
                                ("completed_at__isnull", True), ("status", "running")
                            ),
                            models.Q(
                                ("completed_at__isnull", False),
                                (
                                    "status__in",
                                    ["success", "partial", "failed", "aborted"],
                                ),
                            ),
                            _connector="OR",
                        ),
                    ),
                    models.Q(
                        ("contract__isnull", True),
                        ("purpose", "catalog"),
                        models.Q(
                            models.Q(
                                ("completed_at__isnull", True),
                                (
                                    "status__in",
                                    ["pending", "running", "partial", "interrupted"],
                                ),
                            ),
                            models.Q(
                                ("completed_at__isnull", False),
                                ("status__in", ["success", "failed", "aborted"]),
                            ),
                            _connector="OR",
                        ),
                    ),
                    _connector="OR",
                ),
                name="ck_collection_run_lifecycle",
            ),
        ),
        migrations.AddConstraint(
            "collectionobservation",
            models.UniqueConstraint(
                fields=("scope_run", "resource_key"),
                name="uq_collection_scope_resource",
            ),
        ),
        migrations.AddConstraint(
            "collectionscoperun",
            models.UniqueConstraint(
                fields=("run", "scope_kind", "scope_key"),
                name="uq_collection_run_scope",
            ),
        ),
        migrations.AlterField(
            "collectionscoperun",
            "run",
            models.ForeignKey(
                "core.hfmodelcatalogrun",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="namespaces",
                db_constraint=False,
            ),
        ),
        migrations.RunPython(merge_runs, restore_runs),
        migrations.RunSQL(
            "SET CONSTRAINTS ALL IMMEDIATE", reverse_sql="SET CONSTRAINTS ALL IMMEDIATE"
        ),
        migrations.AlterField(
            "collectionscoperun",
            "run",
            models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="scopes",
                to="core.collectionrun",
            ),
        ),
        migrations.RunPython(merge_observations, restore_observations),
        migrations.RunSQL(
            "SET CONSTRAINTS ALL IMMEDIATE", reverse_sql="SET CONSTRAINTS ALL IMMEDIATE"
        ),
        migrations.DeleteModel("HFModelCatalogObservation"),
        migrations.DeleteModel("HFModelCatalogRun"),
        migrations.AlterModelTable("collectionrun", "collection_runs"),
        migrations.AlterModelTable("collectionobservation", "collection_observations"),
        migrations.AlterModelTable("collectionscoperun", "collection_scope_runs"),
        migrations.RunSQL(
            "CREATE VIEW metric_collection_runs AS SELECT * FROM collection_runs WHERE purpose = 'metric' WITH LOCAL CHECK OPTION; CREATE VIEW metric_observations AS SELECT * FROM collection_observations WHERE run_id IN (SELECT id FROM collection_runs WHERE purpose = 'metric') WITH LOCAL CHECK OPTION;",
            reverse_sql="DROP VIEW metric_observations; DROP VIEW metric_collection_runs;",
        ),
        migrations.RunSQL(
            migrations.RunSQL.noop, reverse_sql="SET LOCAL lock_timeout = '5s'"
        ),
        migrations.RunPython(
            migrations.RunPython.noop, reverse_code=require_catalog_idle
        ),
    ]
