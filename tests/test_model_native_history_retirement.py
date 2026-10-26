"""Native history selects typed owners and exact captured provider objects."""

from datetime import UTC, datetime

import httpx
import pytest

from core.collection_capture import observation_object_documents, read_document
from core.collection_state import claim_job
from core.model_history_collection import execute_model_history, history_report
from core.model_native_history import _hf_checkpoint, validate_typed_scope
from core.models import CollectionObservation, CollectionScopeRun, DataSource, Product
from scripts.benchmark_download_collector.sources import Budget
from tests.product_factory import product_type_fields
from tests.test_hf_catalog_runner import scope
from tests.test_model_history_collection import history_job

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


@pytest.fixture
def native_job():
    scope()
    product = Product.objects.create(
        brand_id="lab", repo_id="lab/model", **product_type_fields(Product, "llm-model")
    )
    source = DataSource.objects.get(pk="hf")
    source.enabled, source.adapter_key = True, "hf-catalog-v1"
    source.save()
    return history_job(
        source,
        product.brand,
        product,
        creation={
            "at": "2026-09-01T00:00:00Z",
            "source": "hf",
            "native_identifier": "lab/model",
        },
    )


def run_native(job, *, commits=None, requests=20, head_identifier="lab/model"):
    rows = (
        commits
        if commits is not None
        else [
            {"id": "b" * 40, "date": "2026-09-03T04:00:00Z"},
            {"id": "c" * 40, "date": "2026-09-04T05:00:00Z"},
        ]
    )
    seen = []

    def respond(request):
        seen.append(request)
        if request.url.path == "/api/models/lab/model":
            return httpx.Response(
                200, json={"id": head_identifier, "private": False, "sha": "a" * 40}
            )
        if "/commits/" in request.url.path:
            return httpx.Response(200, json=rows)
        assert "/tree/" in request.url.path
        return httpx.Response(
            200, json=[{"type": "file", "path": "config.json", "size": 5}]
        )

    run = execute_model_history(
        job.pk,
        budget=Budget(
            httpx.Client(transport=httpx.MockTransport(respond)),
            max_requests=requests,
            max_bytes=1000000,
            sleep=lambda _: None,
        ),
    )
    return run, seen


def test_hf_history_uses_exact_rows_and_preserves_duplicate_receipt_and_cutoff(
    native_job,
):
    earlier = {"id": "b" * 40, "date": "2026-09-03T04:00:00Z"}
    rows = [earlier, earlier, {"id": "c" * 40, "date": "2026-09-13T00:00:00Z"}]
    run, seen = run_native(native_job, commits=rows)
    assert run.status == "success" and len(seen) == 3
    assert seen[-1].url.path.endswith("/tree/" + "b" * 40)
    commits = run.scopes.get(scope_key="lab/model:commits")
    assert commits.raw_count == 3 and commits.observations.count() == 2
    request = commits.requests.get()
    assert request.request_revision == "a" * 40 and request.request_group == "commits"
    assert read_document(request.archive) == rows
    for observation in run.observations.exclude(observation_kind="coverage"):
        raw, dimensions, metadata = observation_object_documents(observation)
        assert raw and dimensions["kind"] == observation.observation_kind
        assert metadata["historical_public_visibility_proven"] is False
        edge = observation.inputs.get(input_role="hf_native_object")
        assert edge.input_request.scope_run_id == observation.scope_run_id
        assert edge.input_request.attempt.run_id == run.pk
        assert observation.observed_at == edge.input_request.received_at
        assert (
            observation.resource_snapshot.publisher_account.normalized_identifier
            == "lab"
        )
        assert (
            observation.listing
            == observation.dimensions
            == observation.source_metadata
            == {}
        )
        assert observation.envelopes == [] and observation.groups == {}
    assert all(
        s.ownership == {} and s.envelopes == [] and s.cursor_history == []
        for s in run.scopes.all()
    )
    assert run.report == {} and run.attempts.get().actual_requests == 3
    assert history_report(run)["physical_accounting_complete"] is True


@pytest.mark.parametrize(
    "damage", ["ordinal", "hash", "request_revision", "parent_revision", "endpoint"]
)
def test_hf_native_selected_response_refuses_damaged_input(native_job, damage):
    run, _ = run_native(native_job)
    observation = run.observations.get(
        observation_kind="hf_commits",
        source_record_at=datetime(2026, 9, 3, 4, tzinfo=UTC),
    )
    edge = observation.inputs.get(input_role="hf_native_object")
    if damage == "ordinal":
        edge.row_locator = "1"
        edge.save(update_fields=["row_locator"])
    elif damage == "hash":
        edge.input_sha256 = "0" * 64
        edge.save(update_fields=["input_sha256"])
    elif damage in {"request_revision", "endpoint"}:
        request = edge.input_request
        field = "request_revision" if damage == "request_revision" else "endpoint_url"
        setattr(
            request,
            field,
            "d" * 40
            if field == "request_revision"
            else "https://huggingface.co/api/models/lab/other/commits/" + "a" * 40,
        )
        request.save(update_fields=[field])
    else:
        parent = observation.scope_run.resource_observation.resource_snapshot
        parent.revision = "d" * 40
        parent.save(update_fields=["revision"])
    with pytest.raises(ValueError, match="changed"):
        observation_object_documents(observation)


def test_native_hf_retains_provider_spelling_with_frozen_case_insensitive_identity(
    native_job,
):
    run, _ = run_native(native_job, head_identifier="Lab/Model")
    assert run.status == "success"
    head = run.observations.get(observation_kind="hf_metadata")
    assert head.source_identifier == "lab/model"
    assert observation_object_documents(head)[0]["id"] == "Lab/Model"


def test_unknown_commit_time_does_not_fabricate_cutoff_eligibility(native_job):
    run, seen = run_native(
        native_job,
        commits=[
            {"id": "b" * 40, "date": "2026-09-03"},
            {"id": "c" * 40, "date": "invalid"},
        ],
    )
    assert run.status == "success" and len(seen) == 2
    tree = run.scopes.get(scope_key="lab/model:tree")
    assert tree.outcome == "history_unavailable" and tree.enumeration_complete
    assert tree.error_code == "no_qualified_commit_at_cutoff"
    assert tree.resource_observation_id is None and tree.requested_revision is None
    assert not tree.requests.exists()
    dated = run.observations.get(
        observation_kind="hf_commits", source_record_date="2026-09-03"
    )
    assert dated.source_record_at is None
    assert not run.observations.filter(
        observation_kind="hf_commits", source_record_at__isnull=False
    ).exists()


def test_native_scope_rejects_unselected_repository_and_legacy_resume(native_job):
    claim = claim_job(native_job.pk, typed=True)
    run = native_job.runs.get(pk=claim.run_id)
    owner = {"repository_id": "lab/other", "namespace": "lab", "company_id": "lab"}
    with pytest.raises(ValueError, match="frozen model selection"):
        validate_typed_scope(
            native_job, run, "hf_history_head", "lab/other", owner, None
        )
    CollectionScopeRun.objects.create(
        run=run,
        scope_kind="hf_history_head",
        scope_key="lab/model",
        ownership={},
        envelopes=[{"revision": "a" * 40}],
    )
    with pytest.raises(ValueError, match="requires typed migration"):
        _hf_checkpoint(
            claim, scope_kind="hf_history_head", scope_key="lab/model", ownership={}
        )
    assert not run.attempts.get().requests.exists()


def test_native_history_resume_ignores_poisoned_retiring_documents(native_job):
    run, _ = run_native(native_job, requests=1)
    assert run.status == "partial"
    original = run.observations.get(observation_kind="hf_metadata")
    observed_at = original.observed_at
    CollectionObservation.objects.filter(pk=original.pk).update(
        listing={"id": "unselected/wrong", "sha": "d" * 40},
        dimensions={"kind": "wrong"},
        source_metadata={"revision": "d" * 40},
    )
    run.scopes.update(
        ownership={"repository_id": "wrong"}, envelopes=[{"revision": "d" * 40}]
    )
    resumed, seen = run_native(native_job)
    assert resumed.pk == run.pk and resumed.status == "success"
    assert len(seen) == 2 and seen[0].url.path.endswith("/commits/" + "a" * 40)
    original.refresh_from_db()
    assert original.observed_at == observed_at
    assert observation_object_documents(original)[0]["sha"] == "a" * 40


def test_github_native_capture_has_typed_parent_and_frozen_mapping_validation():
    from core.collection_identity import review_github_mapping
    from tests.test_collection_identity import identities
    from tests.test_github_catalog import responses

    brand, account, subject, repository = identities()
    source = account.data_source
    source.enabled, source.adapter_key = True, "github-catalog-v1"
    source.save()
    mapping = review_github_mapping(
        subject=subject,
        repo=repository,
        role="dedicated_model",
        version_selector=None,
        evidence_url="https://github.com/publisher/family",
        reviewed_by="test",
    )
    pin = {
        "mapping_id": str(mapping.pk),
        "mapping_hash": mapping.mapping_hash,
        "source": "github",
        "native_identifier": "123",
        "identifier_scope": "repository_id",
    }
    job = history_job(source, brand, subject.product, pins=[pin])
    seen = []
    fallback = responses(repository, seen)

    def respond(request):
        if request.url.path == "/repos/publisher/family":
            seen.append(str(request.url))
            return httpx.Response(200, json=repository)
        return fallback(request)

    run = execute_model_history(
        job.pk,
        budget=Budget(
            httpx.Client(transport=httpx.MockTransport(respond)),
            max_requests=30,
            max_bytes=1000000,
        ),
    )
    assert run.status == "success" and run.attempts.get().actual_requests == len(seen)
    assert run.observations.exclude(observation_kind="coverage").exists()
    for observation in run.observations.exclude(observation_kind="coverage"):
        assert observation.projection_kind == "github-catalog-object-v1"
        assert observation_object_documents(observation)[0]
        assert (
            observation.listing
            == observation.dimensions
            == observation.source_metadata
            == {}
        )
        assert (
            observation.inputs.get(
                input_role="github_source_object"
            ).input_request.scope_run_id
            == observation.scope_run_id
        )
    assert all(
        scope.ownership == {} and scope.envelopes == [] for scope in run.scopes.all()
    )
    tree = run.scopes.get(scope_kind="repository_tree")
    parent = tree.resource_observation
    assert parent.observation_kind == "commits"
    owner = {
        "repository_id": 123,
        "revision": parent.resource_snapshot.revision,
        "tree_revision": parent.resource_snapshot.tree_revision,
    }
    validate_typed_scope(job, run, tree.scope_kind, tree.scope_key, owner, parent)
    with pytest.raises(ValueError, match="coordinate changed"):
        validate_typed_scope(
            job,
            run,
            tree.scope_kind,
            tree.scope_key,
            {**owner, "revision": "a" * 40},
            parent,
        )
    mapping.mapping_hash = "0" * 64
    mapping.save(update_fields=["mapping_hash"])
    with pytest.raises(ValueError, match="reviewed GitHub mapping changed"):
        validate_typed_scope(job, run, tree.scope_kind, tree.scope_key, owner, parent)
