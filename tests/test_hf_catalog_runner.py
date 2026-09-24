import httpx
import pytest
from django.db import connection

from core.hf_catalog import execute_catalog, resolve_scope
from core.hf_metadata_client import HFMetadataClient
from core.models import Brand, BrandCompany, Company, HFModelCatalogRun, HFOrg, Product

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def scope(brands=("lab",)):
    company = Company.objects.create(nickname="lab")
    for name in brands:
        brand = Brand.objects.create(nickname=name)
        BrandCompany.objects.create(brand=brand, company=company)
    HFOrg.objects.create(namespace="lab", company=company, confirmed=True)
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
    assert Product.objects.filter(brand__isnull=True).count() == 2
    identities = list(Product.objects.values_list("id", "repo_id"))
    again = execute_catalog(scope=manifest, hf=api())
    assert again["imported"] == 0 and again["updated"] == 2
    assert list(Product.objects.values_list("id", "repo_id")) == identities
    assert HFModelCatalogRun.objects.count() == 2


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
    HFOrg.objects.update(confirmed=False)
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
    run = HFModelCatalogRun.objects.get()
    assert run.namespaces.get().cursor is None
    assert run.namespaces.get().observations.count() == 0
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
        assert HFModelCatalogRun.objects.count() == 0


def test_failed_detail_does_not_hide_terminal_listing_or_erase_product():
    def fail_detail(request):
        if request.url.params.get("blobs"):
            return httpx.Response(403)

    result = execute_catalog(scope=scope(), hf=api(fail_detail))
    assert result["enumeration_complete"] and not result["enrichment_complete"]
    assert Product.objects.count() == 2
    run = HFModelCatalogRun.objects.get()
    assert run.namespaces.get().observations.first().groups == {
        "listing": "ok",
        "detail": "forbidden",
        "expanded": "ok",
    }
    assert execute_catalog(run_id=run.pk, hf=api())["complete"]


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

    def expired(request):
        if request.url.params.get("cursor") == "expired":
            return httpx.Response(400, json={"error": "invalid cursor"})

    resumed = execute_catalog(run_id=first["run_id"], hf=api(expired))
    assert resumed["complete"]
    assert Product.objects.count() == 2
    assert resumed["unique_models"] == 2


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
    HFOrg.objects.create(namespace="blocked", company_id="lab", confirmed=True)
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
