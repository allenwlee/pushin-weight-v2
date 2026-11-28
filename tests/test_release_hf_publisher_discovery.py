"""Exercise an empty HF crosswalk through the scheduled release collector."""

from datetime import timedelta

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
    ("namespace", "returned_repo", "schedule_case"),
    [
        ("AminiTech", "AminiTech/Soma-1X-lite", "existing"),
        ("AminiTech", "AminiTech/Soma-1X-lite", "before-daily-slot"),
        ("AminiTech", "AminiTech/Soma-1X-lite", "offline-first"),
        ("UnrelatedOrg", None, "existing"),
        ("AminiTech", "OtherOrg/Soma-1X-lite", "existing"),
    ],
)
def test_scheduled_discovery_binds_only_verified_product_and_records_zero(
    settings, namespace, returned_repo, schedule_case, monkeypatch
):
    setup_spec()  # Install the existing metrics and the fixture's collection grants.
    models.DataSource.objects.filter(pk="hf").update(enabled=True)
    daily = schedule_case != "existing"
    if daily:
        # Staging's HF daily slot is 10 UTC. Launch the day after fixtures were
        # recorded so the release is visible at this simulated 08 UTC wake.
        launch = (timezone.now() + timedelta(days=1)).replace(
            hour=8, minute=0, second=0, microsecond=0
        )
        clock = [launch]
        monkeypatch.setattr(timezone, "now", lambda: clock[0])
        hf = models.DataSource.objects.get(pk="hf")
        hf.metadata["daily_collection_hour_utc"] = 10
        hf.save(update_fields=["metadata"])
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
        if (
            not calls
            and dossier.pk == announcement.event_dossier_source.event_dossier_id
        ):
            budget.remaining -= 2
        return False

    monkeypatch.setattr(
        "core.release_publisher_recovery.recover_release_publisher", recovered_at_source
    )
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
        if schedule_case == "offline-first":
            replay = collect_due_release_metrics(client=client, cutoff=now)
            assert replay["linked_jobs"] == 1 and replay["applied"] == 0
        first = collect_due_release_metrics(
            client=client, cutoff=None if daily else now
        )
        repeat = collect_due_release_metrics(client=client, cutoff=now)
        if daily:
            from core.collection_scheduling import due_job

            job = models.CollectionJob.objects.get(
                job_key__startswith="release-metric:", source_id="hf"
            )
            assert first["applied"] == 1
            slot = launch.replace(hour=10)
            assert job.last_success.scheduled_slot_at == slot
            assert job.next_due_at == slot + timedelta(days=1)
            from core.collection_state import BusyJob, claim_job

            with pytest.raises(BusyJob):
                claim_job(
                    job.pk,
                    typed=True,
                    expected_slot=slot.isoformat(),
                    initial_release_reading=True,
                )
            clock[0] = slot
            assert not due_job(job, now=clock[0])["due"]
            clock[0] = launch + timedelta(days=1)
            assert collect_due_release_metrics(client=client)["applied"] == 0
            clock[0] = slot + timedelta(days=1)
            assert collect_due_release_metrics(client=client)["applied"] == 1
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
    values = models.MetricValue.objects.filter(
        source_metric__metric_key="downloads",
        observation__mapping__subject__product=product,
    )
    assert values.count() == (2 if daily else 1)
    value = values.first()
    assert (
        value.integer_value == 0
        and value.observation.inputs.get().input_request.archive_id
    )


def test_publisher_profile_reuses_account_and_only_links_an_established_company():
    from core.release_provider_identity import bind_hf_publisher

    setup_spec()
    brand = models.Brand.objects.create(nickname="startlux", display_name="StartLux")
    source = "https://startlux.com/benchmark/"
    account = bind_hf_publisher(brand.pk, "startlux-models", source)
    assert account.normalized_identifier == "startlux-models"
    assert (
        models.BrandAccount.objects.get(brand=brand, account=account).role_id
        == "official"
    )
    assert not models.CompanyAccount.objects.filter(account=account).exists()
    company = models.Company.objects.create(nickname="startlux-labs")
    models.BrandCompany.objects.create(brand=brand, company=company)
    assert bind_hf_publisher(brand.pk, "STARTLUX-MODELS", source).pk == account.pk
    link = models.CompanyAccount.objects.get(account=account)
    assert link.company == company and link.ownership_confirmed
    other = models.Brand.objects.create(nickname="different", display_name="Different")
    assert bind_hf_publisher(other.pk, "startlux-models", source) is None
    assert not models.BrandAccount.objects.filter(brand=other, account=account).exists()

    models.BrandCompany.objects.create(brand=other, company=company)
    assert bind_hf_publisher(other.pk, "startlux-models", source).pk == account.pk
    assert models.CompanyAccount.objects.filter(account=account).count() == 1


@pytest.mark.parametrize(
    "case",
    [
        "confirmed",
        "wrong-handle",
        "ambiguous",
        "wrong-variant",
        "outage",
        "unsupported-owner",
    ],
)
def test_hf_discovery_without_a_url_requires_the_exact_product_and_issuer(case):
    from core.collection_budgets import invocation_budget
    from core.release_provider_identity import lookup_release_hf_model

    paths = []
    repo = "example-models/Agent-One"

    def respond(request):
        path = request.url.path
        paths.append(path)
        if path == "/api/models":
            if case == "outage":
                return httpx.Response(503)
            rows = [{"id": repo + "-GGUF" if case == "wrong-variant" else repo}]
            if case == "ambiguous":
                rows.append({"id": "OtherNamespace/Agent_One"})
            return httpx.Response(200, json=rows)
        if path.endswith("/socials"):
            return httpx.Response(
                200,
                json={
                    "org": "example-models",
                    "socialHandles": {
                        "twitter": "AnotherLab"
                        if case == "wrong-handle"
                        else "ExampleLab"
                    },
                },
            )
        assert path == "/api/models/" + repo
        return httpx.Response(
            200,
            json={
                "id": repo,
                "_id": "6b067d23d5ae3eca49eb4edc",
                "createdAt": "2026-11-25T06:16:03Z",
                "private": False,
            },
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        payload = lookup_release_hf_model(
            {
                "author_id": "987654",
                "author_handle": "ExampleLab",
                "text": "Introducing Agent One"
                if case == "unsupported-owner"
                else "Introducing Agent One https://huggingface.co/" + repo,
            },
            "Agent One",
            None,
            None,
            invocation_budget(client, requests=4, seconds=5),
        )
    assert bool(payload) == (case == "confirmed")
    assert ("/api/models/" + repo in paths) == (case == "confirmed")


def test_identity_confirmation_remains_enabled_without_chart_measurements(
    monkeypatch, settings
):
    import uuid
    from unittest.mock import Mock

    from core import release_chart_collection as collection

    settings.PRODUCT_RELEASE_BACKGROUND_ENABLED = True
    settings.BENCHMARK_COLLECTION_ENABLED = False
    # No eligible dossier or budget means no network demand or scheduler write.
    monkeypatch.setattr(
        collection, "_recent_publisher_findings", lambda now, **kwargs: [uuid.uuid4()]
    )
    monkeypatch.setattr(
        collection,
        "_release_page",
        Mock(side_effect=AssertionError("scanned metric jobs")),
    )
    with httpx.Client(
        transport=httpx.MockTransport(lambda r: pytest.fail("unexpected network"))
    ) as client:
        result = collection.collect_due_release_metrics(
            client=client, confirm_identities=True
        )
    assert (
        result["selected"] == 1
        and result["requests"] == 0
        and result["status"] == "identity_only"
    )
