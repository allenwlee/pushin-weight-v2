"""Exercise an empty HF crosswalk through the scheduled release collector."""

import httpx
import pytest
from django.utils import timezone

from core import models
from core.event_dossiers import add_claim
from core.release_chart_collection import collect_due_release_metrics
from tests.product_factory import product_type_fields
from tests.test_benchmark_download_db_identity import setup_spec
from tests.test_release_chart_metric_collection import release_for

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


@pytest.mark.parametrize(
    ("namespace", "returned_repo"),
    [
        ("AminiTech", "AminiTech/Soma-1X-lite"),
        ("UnrelatedOrg", None),
        ("AminiTech", "OtherOrg/Soma-1X-lite"),
    ],
)
def test_scheduled_discovery_binds_only_verified_product_and_records_zero(
    settings, namespace, returned_repo, monkeypatch
):
    setup_spec()  # Install the existing metrics and the fixture's collection grants.
    models.DataSource.objects.filter(pk="hf").update(enabled=True)
    settings.BENCHMARK_COLLECTION_ENABLED = True
    brand = models.Brand.objects.create(nickname="amini", display_name="Amini")
    account = models.Account.objects.create(author_id="987654321", handle="AminiTech")
    role, _ = models.Role.objects.get_or_create(key="official")
    models.BrandAccount.objects.create(brand=brand, account=account, role=role)
    product = models.Product.objects.create(
        brand=brand,
        display_name="Soma-1X-lite",
        **product_type_fields(models.Product, "model-other"),
    )
    _, announcement = release_for(product)
    repo = namespace + "/Soma-1X-lite"
    add_claim(
        announcement.event_dossier_source_id,
        claim_kind="release_context",
        scope_key="official-hf-model:" + repo,
        reported_product_id=product.pk,
        assertion_text="Release repository",
        source_excerpt="https://huggingface.co/" + repo,
        extraction_version="pulse-publisher-source-v1",
    )
    # The upstream original-X and article fetches use the same invocation budget.
    # Exercise the two remaining physical HF fetches on the same wake.
    def recovered_at_source(dossier, *, client, now, budget):
        if not calls and dossier.pk == announcement.event_dossier_source.event_dossier_id:
            budget.remaining -= 2
        return False

    monkeypatch.setattr("core.release_publisher_recovery.recover_release_publisher", recovered_at_source)
    calls = []

    def respond(request):
        calls.append(str(request.url))
        assert namespace == "AminiTech"
        assert request.url.path == "/api/models/" + repo
        return httpx.Response(
            200,
            json={
                "id": returned_repo,
                "_id": "6b067d23d5ae3eca49eb4edc",
                "createdAt": "2026-11-25T06:16:03.000Z",
                "private": False,
                "downloads": 0,
                "likes": 6,
            },
        )

    now = timezone.now()
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        first = collect_due_release_metrics(client=client, cutoff=now)
        repeat = collect_due_release_metrics(client=client, cutoff=now)
    product.refresh_from_db()
    mappings = models.SourceSubjectMapping.objects.filter(
        source_id="hf", subject__product=product
    )
    if returned_repo != repo:
        assert bool(calls) == (namespace == "AminiTech")
        assert not mappings.exists() and not product.repo_id
        assert not models.MetricValue.objects.filter(
            observation__mapping__subject__product=product
        ).exists()
        return
    assert first["applied"] == 1 and repeat["applied"] == 0
    assert repeat["requests"] == 0
    assert product.repo_id == repo
    assert not models.CompanyAccount.objects.filter(
        account=product.publisher_account
    ).exists()
    assert product.publisher_account.normalized_identifier == "aminitech"
    assert mappings.filter(purpose="catalog", external_identifier=repo).count() == 1
    value = models.MetricValue.objects.get(
        source_metric__metric_key="downloads",
        observation__mapping__subject__product=product,
    )
    assert (
        value.integer_value == 0
        and value.observation.inputs.get().input_request.archive_id
    )
