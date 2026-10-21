"""Shared identity records preserve namespaces and immutable provenance."""

import pytest
from django.apps import apps
from django.db import IntegrityError, connection, transaction
from django.db.models.deletion import ProtectedError

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


def definition(*, domain="workflow", digest="a" * 64, **overrides):
    values = {
        "definition_domain": domain,
        "definition_key": "fixture-workflow",
        "reported_version_token": "v1",
        "identity_sha256": digest,
        "provenance_state": "identity_only",
    }
    values.update(overrides)
    return apps.get_model("core", "DefinitionVersion").objects.create(**values)


def test_request_model_identity_includes_its_service_provider():
    Provider = apps.get_model("core", "ServiceProvider")
    Model = apps.get_model("core", "InferenceModel")
    first = Provider.objects.create(code="fixture-one")
    second = Provider.objects.create(code="fixture-two")
    native = "Publisher/Request-Alias:v1"
    one = Model.objects.create(service_provider=first, native_model_key=native)
    two = Model.objects.create(service_provider=second, native_model_key=native)
    assert one.pk != two.pk
    assert one.native_model_key == native
    with pytest.raises(IntegrityError), transaction.atomic():
        Model.objects.bulk_create(
            [Model(service_provider=first, native_model_key=native)]
        )
    with pytest.raises(ProtectedError):
        first.delete()
    with pytest.raises(IntegrityError, match="immutable"), transaction.atomic():
        Model.objects.filter(pk=one.pk).update(service_provider=second)


def test_stage_identity_belongs_to_one_workflow_definition_version():
    Stage = apps.get_model("core", "WorkflowStage")
    first = definition()
    second = definition(digest="b" * 64)
    stage = Stage.objects.create(workflow_version=first, stage_key="extract")
    assert Stage.objects.create(workflow_version=second, stage_key="extract").pk != stage.pk
    with pytest.raises(IntegrityError), transaction.atomic():
        Stage.objects.bulk_create(
            [Stage(workflow_version=first, stage_key="extract")]
        )
    policy = definition(domain="policy", digest="c" * 64)
    with pytest.raises(IntegrityError, match="workflow"), transaction.atomic():
        Stage.objects.bulk_create(
            [Stage(workflow_version=policy, stage_key="extract")]
        )
    with pytest.raises(IntegrityError, match="immutable"), transaction.atomic():
        Stage.objects.filter(pk=stage.pk).update(stage_key="different")


def test_definition_identity_and_available_provenance_are_immutable():
    Version = apps.get_model("core", "DefinitionVersion")
    row = definition()
    assert row.content_sha256 is None
    assert row.source_git_commit is None
    assert row.source_path is None
    assert row.evidence_archive_id is None
    with pytest.raises(IntegrityError, match="immutable"), transaction.atomic():
        Version.objects.filter(pk=row.pk).update(reported_version_token="v2")
    with pytest.raises(IntegrityError), transaction.atomic():
        definition(content_sha256="d" * 64, digest="e" * 64)
    with pytest.raises(IntegrityError), transaction.atomic():
        definition(domain="unregistered-domain", digest="f" * 64)
    with pytest.raises(IntegrityError), transaction.atomic():
        definition(digest="not-a-sha256")
    with pytest.raises(IntegrityError, match="immutable"), transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM definition_versions WHERE id=%s", [row.pk])


@pytest.mark.parametrize(
    "source_path,accepted",
    [
        ("core/prompts.py", True),
        ("core/workflow-v1.py", True),
        ("/private/prompts.py", False),
        ("../prompts.py", False),
        ("core/../prompts.py", False),
        ("core/prompts.py\n", False),
    ],
)
def test_source_pinned_definition_requires_a_relative_safe_locator(source_path, accepted):
    values = {
        "provenance_state": "source_pinned",
        "content_sha256": "b" * 64,
        "source_git_commit": "c" * 40,
        "source_path": source_path,
    }
    if accepted:
        assert definition(**values).source_path == source_path
    else:
        with pytest.raises(IntegrityError), transaction.atomic():
            definition(**values)
