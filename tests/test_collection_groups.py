"""Metadata outcomes retain their original grain without invented requests."""

import pytest

from core.collection_groups import observation_group_outcomes, record_observation_group
from core.collection_storage_migration import project_observation_groups_batch
from core.models import CollectionObservation, CollectionRequest, CollectionScopeRun
from tests.test_collection_relational_storage import execution

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


def observations():
    run, _, scope = execution()
    return [
        CollectionObservation.objects.create(
            run=run, scope_run=scope, source_identifier=f"lab/model{index}",
            source_subject_kind="repository", observation_key=str(index) * 64,
            groups=groups,
        )
        for index, groups in enumerate([
            {"listing": "ok", "detail": "forbidden", "expanded": "partial_expansion"},
            {"detail": "old_unknown_outcome"},
        ], start=1)
    ]


def test_group_copy_preserves_partial_unknown_and_identity_without_fake_requests():
    first, second = observations()
    original = list(CollectionObservation.objects.order_by("pk").values())
    request_count = CollectionRequest.objects.count()
    with pytest.raises(ValueError, match="not projected"):
        project_observation_groups_batch(batch_size=1, verify_only=True)
    assert not first.resource_scopes.exists()
    copied = project_observation_groups_batch(batch_size=1)
    assert (copied.last_id, copied.scanned, copied.updated) == (first.pk, 1, 1)
    assert project_observation_groups_batch(batch_size=1).updated == 0
    assert project_observation_groups_batch(after_id=first.pk).updated == 1
    assert project_observation_groups_batch(verify_only=True).updated == 0
    assert list(CollectionObservation.objects.order_by("pk").values()) == original
    assert CollectionRequest.objects.count() == request_count
    expanded = first.resource_scopes.get(phase="expanded")
    assert expanded.parent_scope_id == first.scope_run_id
    assert (expanded.execution_state, expanded.coverage_state) == ("completed", "partial")
    assert not expanded.enumeration_complete
    unknown = second.resource_scopes.get()
    assert (unknown.execution_state, unknown.coverage_state) == ("unknown", "unknown")
    CollectionObservation.objects.filter(pk=first.pk).update(groups={})
    first.refresh_from_db()
    assert observation_group_outcomes(first) == original[0]["groups"]
    assert project_observation_groups_batch().updated == 0


def test_group_copy_refuses_conflicts_and_malformed_legacy_atomically():
    first, second = observations()
    second.groups = {"x" * 33: "ok"}
    second.save(update_fields=["groups"])
    with pytest.raises(ValueError, match="invalid resource group"):
        project_observation_groups_batch()
    assert not CollectionScopeRun.objects.filter(scope_kind="resource_group").exists()
    second.groups = {}
    second.save(update_fields=["groups"])
    project_observation_groups_batch()
    first.resource_scopes.filter(phase="detail").update(outcome="ok")
    with pytest.raises(ValueError, match="differs from legacy"):
        project_observation_groups_batch()


def test_live_group_update_preserves_other_typed_groups_and_refuses_foreign_owner():
    first, second = observations()
    project_observation_groups_batch()
    first.groups = {}
    record_observation_group(first, "detail", "ok")
    assert observation_group_outcomes(first) == {
        "listing": "ok", "detail": "ok", "expanded": "partial_expansion",
    }
    first.resource_scopes.filter(phase="detail").update(resource_observation=second)
    with pytest.raises(ValueError, match="ownership mismatch"):
        record_observation_group(first, "detail", "ok")
