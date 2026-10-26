from uuid import uuid4

import httpx
import pytest
from django.db import connection

from core.hf_catalog import execute_catalog, resolve_catalog_run, resolve_scope
from core.hf_metadata_client import HFMetadataClient
from core.measurement_taxonomy import digest
from core.models import (
    Brand,
    BrandCompany,
    CollectionObservationInput,
    CollectionRequest,
    CollectionRun,
    Company,
    Product,
)
from core.publisher_accounts import publisher_links
from tests.collection_fixtures import with_database_models
from tests.publisher_fixtures import hf_publisher

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


@with_database_models
def scope(brands=("lab",)):
    company = Company.objects.create(nickname="lab")
    for name in brands:
        brand = Brand.objects.create(nickname=name)
        BrandCompany.objects.create(brand=brand, company=company)
    hf_publisher(namespace="lab", company=company, confirmed=True)
    return resolve_scope(brands=list(brands), companies=[], rules=[])


def api(handler=None, budget=50):
    def respond(request):
        if handler:
            response = handler(request)
            if response is not None:
                return response
        if "overview" in request.url.path:
            return httpx.Response(200, json={"name": "lab"})
        if request.url.path == "/api/models":
            return httpx.Response(
                200, json=[{"id": "lab/model"}, {"id": "lab/model-GGUF"}]
            )
        return httpx.Response(
            200,
            json={
                "id": request.url.path.removeprefix("/api/models/"),
                "sha": "abc",
                "downloadsAllTime": 4_000_000_000,
                "siblings": [{"rfilename": "w", "size": 32}],
            },
        )

    return HFMetadataClient(
        httpx.Client(transport=httpx.MockTransport(respond)),
        max_requests=budget,
        max_seconds=60,
        sleep=lambda _: None,
    )


def test_full_walk_enrichment_refresh_identity_and_ambiguous_brand():
    manifest = scope(("first", "second"))
    result = execute_catalog(scope=manifest, hf=api())
    assert result["enumeration_complete"] and result["enrichment_complete"]
    assert not result["complete"]  # attribution remains unresolved
    assert result["unique_models"] == result["imported"] == 2
    assert result["requests"] == 6
    saved = CollectionRun.objects.get(pk=result["run_id"])
    legacy_id = uuid4()
    saved.ingestion_key = digest(["catalog", "hf", str(legacy_id)])
    saved.source_metadata = {}
    saved.save(update_fields=["ingestion_key", "source_metadata"])
    assert resolve_catalog_run(legacy_id).pk == saved.pk
    assert resolve_catalog_run(saved.pk).pk == saved.pk
    assert saved.job_id is not None
    assert saved.job.source_id == saved.source_id == "hf"
    assert saved.job.definition["scope"] == saved.scope == manifest
    assert saved.request_count == 6
    assert saved.invocations == []
    assert saved.attempts.get().response_byte_limit is not None
    requests = CollectionRequest.objects.filter(attempt__run=saved)
    assert requests.count() == saved.attempts.get().actual_requests == 6
    assert requests.filter(transport_outcome="received", archive__isnull=False).count() == 6
    assert not requests.exclude(scope_run__run=saved).exists()
    assert CollectionObservationInput.objects.filter(
        observation__run=saved, input_request__in=requests,
    ).count() == 6
    assert saved.selected_count == saved.success_count == 2
    assert Product.objects.filter(brand__isnull=True).count() == 2
    identities = list(Product.objects.values_list("id", "repo_id"))
    again = execute_catalog(scope=manifest, hf=api())
    assert again["imported"] == 0 and again["updated"] == 2
    assert list(Product.objects.values_list("id", "repo_id")) == identities
    assert CollectionRun.objects.count() == 2
    assert CollectionRun.objects.get(pk=again["run_id"]).job_id == saved.job_id


def test_different_direct_catalog_bounds_have_different_immutable_jobs():
    manifest = scope()
    first = execute_catalog(scope=manifest, hf=api(budget=2))
    second = execute_catalog(scope=manifest, hf=api(budget=3))
    assert CollectionRun.objects.get(pk=first["run_id"]).job_id != (
        CollectionRun.objects.get(pk=second["run_id"]).job_id
    )


def test_request_cap_commits_discovery_before_pending_enrichment_and_resumes():
    result = execute_catalog(scope=scope(), hf=api(budget=2))
    assert Product.objects.count() == 2
    assert result["enumeration_complete"]
    assert not result["enrichment_complete"]
    resumed = execute_catalog(run_id=result["run_id"], hf=api())
    assert resumed["complete"]
    assert resumed["requests"] == 4
    assert resumed["cumulative_requests"] == 6
    assert resumed["imported"] == 2
    run = CollectionRun.objects.get(pk=result["run_id"])
    assert list(run.attempts.order_by("ordinal").values_list("actual_requests", flat=True)) == [2, 4]


def test_resumed_projection_reuses_loaded_job_instead_of_fetching_per_model(monkeypatch):
    from django.test.utils import CaptureQueriesContext

    from core import hf_catalog

    first = execute_catalog(scope=scope(), hf=api(budget=2))
    persist = hf_catalog.persist_product
    job_reads = []

    def measured_projection(*args, **kwargs):
        with CaptureQueriesContext(connection) as queries:
            result = persist(*args, **kwargs)
        job_reads.extend(
            query["sql"]
            for query in queries
            if 'FROM "collection_jobs"' in query["sql"]
        )
        return result

    monkeypatch.setattr(hf_catalog, "persist_product", measured_projection)
    resumed = execute_catalog(run_id=first["run_id"], hf=api())
    assert resumed["complete"] and resumed["unique_models"] == 2
    assert resumed["requests"] == 4
    assert not job_reads


def test_slow_http_response_records_partial_time_cap_with_finalization_lease(
    monkeypatch,
):
    from datetime import timedelta

    from django.utils import timezone

    elapsed = [0.0]
    started = timezone.now()
    monkeypatch.setattr(
        timezone, "now", lambda: started + timedelta(seconds=elapsed[0])
    )

    def slow_response(request):
        elapsed[0] = 61.0
        return httpx.Response(200, json={"name": "lab"})

    hf = HFMetadataClient(
        httpx.Client(transport=httpx.MockTransport(slow_response)),
        max_requests=5,
        max_seconds=60,
        clock=lambda: elapsed[0],
    )
    report = execute_catalog(scope=scope(), hf=hf)
    assert report["stop_reason"] == "time_cap"
    run = CollectionRun.objects.get(pk=report["run_id"])
    attempt = run.attempts.get()
    assert run.status == attempt.outcome == "partial"
    from core.collection_capture import run_report_document

    assert run_report_document(run) == report
    assert run.scopes.get().outcome == "time_cap"
    assert run.request_count == 1
    assert run.lease_expires_at == started + timedelta(seconds=120)
    assert run.job.definition["budgets"]["seconds"] == 60
    assert attempt.effective_seconds == 60
    assert attempt.response_byte_limit == hf.max_bytes
    assert run.invocations == []


@pytest.mark.usefixtures("isolated_migration_database")
def test_archived_partial_catalog_reuses_pages_without_rewriting_unknown_budgets():
    import copy

    from django.db.migrations.executor import MigrationExecutor

    from tests.test_run_job_normalization import previous_catalog_module

    target = [("core", "0088_archive_run_instructions")]
    executor = MigrationExecutor(connection)
    executor.migrate(target)
    historical = executor.loader.project_state(target).apps
    previous = previous_catalog_module(historical)
    first = previous.execute_catalog(scope=scope(), hf=api(budget=2))
    run = historical.get_model("core", "CollectionRun").objects.get(pk=first["run_id"])
    scopes = list(run.scopes.order_by("pk").values_list("pk", flat=True))
    observations = list(run.observations.order_by("pk").values_list("pk", flat=True))
    target = [("core", "0090_remove_run_instruction_columns")]
    executor = MigrationExecutor(connection)
    executor.migrate(target)
    historical_0090 = executor.loader.project_state(target).apps
    ArchivedRun = historical_0090.get_model("core", "CollectionRun")
    archived_run = ArchivedRun.objects.get(pk=run.pk)
    archive_id = archived_run.job_id
    definition = copy.deepcopy(archived_run.job.definition)
    assert definition["budgets"] is None
    assert definition["schedule"] is None

    # Resume with the current reader only after upgrading its complete schema.
    executor = MigrationExecutor(connection)
    executor.migrate(executor.loader.graph.leaf_nodes())
    run = CollectionRun.objects.get(pk=run.pk)

    def no_saved_pages(request):
        assert request.url.path.startswith("/api/models/lab/")

    resumed = execute_catalog(run_id=run.pk, hf=api(no_saved_pages, budget=7))
    run.refresh_from_db()
    assert resumed["complete"] and resumed["requests"] == 4
    assert run.job_id == archive_id
    assert run.job.definition == definition
    assert list(run.scopes.order_by("pk").values_list("pk", flat=True)) == scopes
    assert list(run.observations.order_by("pk").values_list("pk", flat=True)) == observations
    latest_attempt = run.attempts.order_by("-ordinal").first()
    assert latest_attempt.reserved_requests == 7
    assert latest_attempt.effective_seconds == 60


def test_short_page_next_link_is_followed_and_repeated_cursor_is_partial():
    def pages(request):
        if request.url.path == "/api/models":
            return httpx.Response(
                200,
                json=[{"id": "lab/model"}],
                headers={
                    "link": '<https://huggingface.co/api/models?cursor=next>; rel="next"'
                },
            )

    result = execute_catalog(scope=scope(), hf=api(pages))
    assert not result["enumeration_complete"]
    assert result["namespaces"][0]["outcome"] == "repeated_cursor"
    assert result["unique_models"] == 1
    assert result["namespaces"][0]["raw_count"] == 2
    run = CollectionRun.objects.get(pk=result["run_id"])
    assert run.scopes.get(scope_kind="namespace").recorded_cursors == ["next"]


def test_ownership_conflict_is_quarantined_without_reassignment():
    manifest = scope()
    other = Brand.objects.create(nickname="other")
    product = Product.objects.create(repo_id="lab/model", brand=other, raw={"kept": 1})
    result = execute_catalog(scope=manifest, hf=api())
    assert result["conflicts"] == 1
    assert not result["complete"]
    product.refresh_from_db()
    assert product.brand_id == "other" and product.raw == {"kept": 1}


def test_namespace_404_does_not_become_empty_success():
    result = execute_catalog(scope=scope(), hf=api(lambda r: httpx.Response(404)))
    assert result["requests"] == 2
    assert not result["enumeration_complete"]
    assert Product.objects.count() == 0


def test_changed_ownership_blocks_resume_before_network():
    result = execute_catalog(scope=scope(), hf=api(budget=1))
    publisher_links(source="hf").update(ownership_confirmed=False)
    with pytest.raises(ValueError, match="scope changed"):
        execute_catalog(
            run_id=result["run_id"], hf=api(lambda r: pytest.fail("network"))
        )


def test_page_failure_rolls_back_products_and_checkpoint(monkeypatch):
    import core.hf_catalog as catalog

    original = catalog.persist_product
    count = [0]

    def fail_second(*args, **kwargs):
        count[0] += 1
        if count[0] == 2:
            raise RuntimeError("simulated crash")
        return original(*args, **kwargs)

    monkeypatch.setattr(catalog, "persist_product", fail_second)
    with pytest.raises(RuntimeError, match="simulated crash"):
        execute_catalog(scope=scope(), hf=api())
    assert Product.objects.count() == 0
    run = CollectionRun.objects.get()
    assert run.scopes.get().cursor is None
    assert run.scopes.get().observations.count() == 0
    monkeypatch.setattr(catalog, "persist_product", original)
    assert execute_catalog(run_id=run.pk, hf=api())["complete"]


def test_lock_contention_sends_no_http_or_writes():
    import psycopg

    from core.hf_catalog import CATALOG_LOCK

    manifest = scope()
    params = connection.get_connection_params()
    with psycopg.connect(**params) as other:
        other.execute("SELECT pg_advisory_lock(%s)", (CATALOG_LOCK,))
        with pytest.raises(ValueError, match="already running"):
            execute_catalog(scope=manifest, hf=api(lambda r: pytest.fail("network")))
        assert CollectionRun.objects.count() == 0


def test_failed_detail_does_not_hide_terminal_listing_or_erase_product():
    from core.collection_groups import observation_group_outcomes

    def fail_detail(request):
        if request.url.params.get("blobs"):
            return httpx.Response(403)

    result = execute_catalog(scope=scope(), hf=api(fail_detail))
    assert result["enumeration_complete"] and not result["enrichment_complete"]
    assert Product.objects.count() == 2
    run = CollectionRun.objects.get()
    listing = run.scopes.get(scope_kind="namespace").observations.first()
    assert observation_group_outcomes(listing) == {
        "listing": "ok",
        "detail": "forbidden",
        "expanded": "ok",
    }
    assert execute_catalog(run_id=run.pk, hf=api())["complete"]


def test_typed_group_resume_preserves_report_and_does_not_repeat_successful_expansion():
    from core.hf_catalog import catalog_report

    def fail_detail(request):
        if request.url.params.get("blobs"):
            return httpx.Response(403)

    result = execute_catalog(scope=scope(), hf=api(fail_detail))
    run = CollectionRun.objects.get(pk=result["run_id"])
    expected = catalog_report(run)["group_outcomes"]
    run.observations.update(groups={})
    assert catalog_report(run)["group_outcomes"] == expected
    resumed = execute_catalog(run_id=run.pk, hf=api())
    assert resumed["complete"]
    assert resumed["requests"] == 2
    assert len(resumed["namespaces"]) == 1


def test_invalid_saved_cursor_restarts_namespace_and_deduplicates():
    def first_page(request):
        if request.url.path == "/api/models":
            return httpx.Response(
                200,
                json=[{"id": "lab/model"}],
                headers={
                    "link": '<https://huggingface.co/api/models?cursor=expired>; rel="next"'
                },
            )

    first = execute_catalog(scope=scope(), hf=api(first_page, budget=2))
    run = CollectionRun.objects.get(pk=first["run_id"])
    assert run.scopes.get(scope_kind="namespace").recorded_cursors == ["expired"]
    run.scopes.update(cursor_history=[])

    def expired(request):
        if request.url.params.get("cursor") == "expired":
            return httpx.Response(400, json={"error": "invalid cursor"})

    resumed = execute_catalog(run_id=first["run_id"], hf=api(expired))
    assert resumed["complete"]
    assert Product.objects.count() == 2
    assert resumed["unique_models"] == 2
    assert run.scopes.get(scope_kind="namespace").recorded_cursors == []


def test_model_cap_leaves_exact_continuation_and_resumes_pending():
    def capped(request):
        if request.url.path == "/api/models":
            if request.url.params.get("cursor"):
                return httpx.Response(200, json=[{"id": "lab/model-GGUF"}])
            assert request.url.params["limit"] == "1"
            return httpx.Response(
                200,
                json=[{"id": "lab/model"}],
                headers={
                    "link": '<https://huggingface.co/api/models?cursor=next>; rel="next"'
                },
            )

    first = execute_catalog(scope=scope(), hf=api(capped), max_models=1)
    assert not first["complete"]
    assert Product.objects.count() == 1
    assert first["namespaces"][0]["next_cursor"] == "next"
    assert execute_catalog(run_id=first["run_id"], hf=api(capped), max_models=1)[
        "complete"
    ]


def test_invalid_typed_field_is_recorded_and_does_not_abort_other_models():
    def malformed(request):
        if request.url.path == "/api/models/lab/model":
            return httpx.Response(
                200, json={"id": "lab/model", "downloads": "not-a-number"}
            )

    result = execute_catalog(scope=scope(), hf=api(malformed))
    assert result["enumeration_complete"] and not result["complete"]
    assert result["group_outcomes"]["detail"]["projection_error"] == 1
    assert Product.objects.count() == 2
    assert (
        Product.objects.get(repo_id="lab/model-GGUF").downloads_all_time
        == 4_000_000_000
    )


def test_one_inaccessible_namespace_does_not_suppress_another():
    scope()
    hf_publisher(namespace="blocked", company_id="lab", confirmed=True)
    manifest = resolve_scope(brands=["lab"], companies=[], rules=[])
    result = execute_catalog(
        scope=manifest,
        hf=api(
            lambda request: (
                httpx.Response(403) if "/blocked/" in request.url.path else None
            )
        ),
    )
    assert not result["complete"]
    assert result["namespaces"][0]["outcome"] == "forbidden"
    assert result["namespaces"][1]["enumeration_complete"]
    assert Product.objects.count() == 2


@pytest.mark.parametrize("replacement", ["expired", "replaced"])
def test_stale_direct_catalog_cannot_checkpoint_or_overwrite_final_report(replacement):
    import uuid
    from datetime import timedelta

    from django.utils import timezone

    from core.collection_state import StaleClaim

    manifest = scope()

    def lose_ownership(request):
        run = CollectionRun.objects.get()
        changes = {"report": {"successor": "preserve"}}
        if replacement == "expired":
            changes["lease_expires_at"] = timezone.now() - timedelta(seconds=1)
        else:
            changes["lease_token"] = uuid.uuid4()
        CollectionRun.objects.filter(pk=run.pk).update(**changes)
        return httpx.Response(200, json={"name": "lab"})

    client = api(lose_ownership)
    with pytest.raises(StaleClaim):
        execute_catalog(scope=manifest, hf=client)
    run = CollectionRun.objects.get()
    assert run.report == {"successor": "preserve"}
    assert run.scopes.get().envelopes == []
    assert not run.observations.exists()
    assert not Product.objects.exists()
    assert client.on_attempt is None
