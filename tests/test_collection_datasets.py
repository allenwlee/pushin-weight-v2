"""Dataset identity follows measurement source while preserving exact origins."""

import pytest
from django.db import IntegrityError, transaction

from core.collection_datasets import dataset_code, resolve_dataset
from core.collection_state import checkpoint_scope, claim_job
from core.models import (
    CollectionJob,
    CollectionObservation,
    CollectionRun,
    DataSource,
    SourceDataset,
)
from tests.test_collection_jobs import ready

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


def test_dataset_identity_is_source_qualified_and_sql_enforced():
    job = ready()
    other = DataSource.objects.create(id="arena", name="Arena", source_type="benchmark")
    first = resolve_dataset(job.source_id, {"dataset_id": "publisher/archive"})
    second = resolve_dataset(other.pk, {"dataset_id": "publisher/archive"})
    assert first.pk != second.pk
    assert resolve_dataset(job.source_id, {"dataset_id": first.code}).pk == first.pk
    with pytest.raises(IntegrityError), transaction.atomic():
        SourceDataset.objects.create(source=job.source, code=first.code)
    with pytest.raises(IntegrityError, match="immutable"), transaction.atomic():
        SourceDataset.objects.filter(pk=first.pk).update(code="rewritten")
    claim = claim_job(job.pk)
    scope = checkpoint_scope(
        claim, scope_kind="archive_snapshot", scope_key="snapshot",
        ownership={"dataset_id": first.code},
    )
    assert scope.source_dataset_id == first.pk
    observation = CollectionObservation.objects.create(
        run_id=claim.run_id, scope_run=scope, source_identifier="publisher/archive",
        source_subject_kind="aggregate", observation_key="d" * 64,
    )
    for query in (
        CollectionRun.objects.filter(pk=claim.run_id),
        type(scope).objects.filter(pk=scope.pk),
        CollectionObservation.objects.filter(pk=observation.pk),
    ):
        with pytest.raises(IntegrityError, match="measurement source"), transaction.atomic():
            query.update(source_dataset=second)
    other_job = CollectionJob.objects.create(
        job_key="different-source-job", source=other, purpose=job.purpose,
        operation=job.operation, mode=job.mode, definition=job.definition,
        definition_sha256=job.definition_sha256,
    )
    with pytest.raises(IntegrityError, match="measurement source"), transaction.atomic():
        CollectionRun.objects.filter(pk=claim.run_id).update(job=other_job)


def test_archive_scope_keeps_dataset_on_its_captured_observation():
    job = ready()
    claim = claim_job(job.pk)

    def write(run, scope):
        CollectionObservation.objects.create(
            run=run, scope_run=scope, source_identifier="publisher/archive",
            source_subject_kind="aggregate", observation_key="c" * 64,
        )

    scope = checkpoint_scope(
        claim, scope_kind="archive_snapshot", scope_key="snapshot",
        ownership={"dataset_id": "publisher/archive"}, write=write,
    )
    assert scope.observations.get().source_dataset_id == scope.source_dataset_id


@pytest.mark.parametrize("metadata", [
    {"dataset_id": ""}, {"dataset_id": 42}, {"dataset_id": "a" * 257},
    {"dataset_id": "one", "publication_provenance": {"dataset_id": "two"}},
])
def test_bad_dataset_coordinate_does_not_create_an_identity(metadata):
    with pytest.raises(ValueError, match="dataset"):
        resolve_dataset("hf", metadata)
    assert not SourceDataset.objects.exists()


def test_publication_dataset_does_not_reclassify_the_host_as_source():
    DataSource.objects.create(id="arena", name="Arena", source_type="benchmark")
    metadata = {
        "publication_provenance": {"dataset_id": "lmarena-ai/leaderboard-dataset"},
        "source_url": "https://huggingface.co/datasets/lmarena-ai/leaderboard-dataset",
    }
    assert dataset_code(metadata) == "lmarena-ai/leaderboard-dataset"
    assert resolve_dataset("arena", metadata).source_id == "arena"


def test_dataset_copy_handles_every_owner_and_archive_only_run_metadata():
    from core.collection_capture import archive_legacy
    from core.collection_storage_migration import project_source_datasets_batch
    from core.models import CollectionScopeRun

    job = ready()
    claim = claim_job(job.pk)
    run = CollectionRun.objects.get(pk=claim.run_id)
    run.source_metadata_archive = archive_legacy({"dataset_id": "publisher/archive"})
    run.save(update_fields=["source_metadata_archive"])
    scope = CollectionScopeRun.objects.create(
        run=run, scope_key="archive", ownership={"dataset_id": "publisher/archive"},
    )
    observation = CollectionObservation.objects.create(
        run=run, scope_run=scope, source_identifier="repo", source_subject_kind="repository",
        source_metadata={"publication_provenance": {"dataset_id": "publisher/archive"}},
        observation_key="b" * 64,
    )
    for kind, owner in (("run", run), ("scope", scope), ("observation", observation)):
        with pytest.raises(ValueError, match="not projected"):
            project_source_datasets_batch(kind, verify_only=True)
        assert owner.source_dataset_id is None
        assert project_source_datasets_batch(kind, batch_size=1).updated == 1
        owner.refresh_from_db()
        assert owner.source_dataset.code == "publisher/archive"
        assert project_source_datasets_batch(kind).updated == 0
        assert project_source_datasets_batch(kind, verify_only=True).updated == 0
        assert project_source_datasets_batch(kind, after_id=owner.pk).scanned == 0
    assert SourceDataset.objects.count() == 1
    other = resolve_dataset(job.source_id, {"dataset_id": "different"})
    CollectionObservation.objects.filter(pk=observation.pk).update(source_dataset=other)
    with pytest.raises(ValueError, match="differs"):
        project_source_datasets_batch("observation")


def test_dataset_verification_does_not_create_missing_identities():
    from core.collection_storage_migration import project_source_datasets_batch

    job = ready()
    claim = claim_job(job.pk)
    CollectionRun.objects.filter(pk=claim.run_id).update(
        source_metadata={"dataset_id": "publisher/archive"},
    )
    with pytest.raises(ValueError, match="not projected"):
        project_source_datasets_batch("run", verify_only=True)
    assert not SourceDataset.objects.exists()
