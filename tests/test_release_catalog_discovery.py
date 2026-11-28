"""Public catalog discovery through the scheduled release worker."""

import httpx
import pytest
from django.core.cache import cache

from core import models
from tests.test_pulse_glm54_replay import replay_announcement

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def test_confirmation_finds_listing_without_measurements_and_reuses_it(
    settings, monkeypatch
):
    from core.release_chart_collection import collect_due_release_metrics

    release = replay_announcement()
    settings.BENCHMARK_COLLECTION_ENABLED = False
    settings.PRODUCT_RELEASE_BACKGROUND_ENABLED = True
    cache.clear()
    monkeypatch.setattr(
        "core.release_publisher_recovery.recover_release_publisher",
        lambda *a, **kw: False,
    )
    from core import release_catalog_discovery as discovery

    requested = []

    def listed(fetch, matches, owns):
        assert matches("GLM-5.4") and not matches("GLM-5.4-Flash")
        assert owns("Zhipu GLM") and not owns("Other Lab")
        fetch("https://openrouter.ai/api/v1/models")
        return [
            ("z-ai/glm-5.4", "catalog_id", "https://openrouter.ai/z-ai/glm-5.4", {})
        ]

    monkeypatch.setattr(discovery, "CATALOGS", {"openrouter": listed})

    def response(req):
        requested.append(str(req.url))
        return httpx.Response(200, json={"data": []})

    with httpx.Client(transport=httpx.MockTransport(response)) as client:
        for _ in range(2):
            result = collect_due_release_metrics(
                client=client, dossier_ids=[release.dossier_id], confirm_identities=True
            )
            assert result["status"] == "identity_only"
    mappings = models.SourceSubjectMapping.objects.filter(
        subject__product_id=release.product_key
    )
    assert list(
        mappings.values_list(
            "purpose", "source_id", "external_identifier", "identifier_scope__code"
        )
    ) == [("catalog", "openrouter", "z-ai/glm-5.4", "catalog_id")]
    assert requested == ["https://openrouter.ai/api/v1/models"]


def test_provider_failure_and_variant_collision_preserve_sibling_result():
    from django.utils import timezone

    from core import release_catalog_discovery as discovery
    from core.collection_budgets import invocation_budget

    release = replay_announcement()

    def failed(*args):
        raise ValueError("provider offline")

    def ambiguous(*args):
        return [
            (i, "model_id", "https://opencode.ai/data/lab/" + i, {})
            for i in ("one", "two")
        ]

    def exact(*args):
        return [
            (
                "glm-5.4",
                "arena_model_name",
                "https://huggingface.co/datasets/lmarena-ai/leaderboard-dataset",
                {},
            )
        ]

    with httpx.Client(
        transport=httpx.MockTransport(lambda r: pytest.fail("unexpected HTTP"))
    ) as client:
        result = discovery.discover_release_catalogs(
            release,
            invocation_budget(client),
            now=timezone.now(),
            catalogs={"openrouter": failed, "opencode": ambiguous, "arena": exact},
        )
    assert result == {
        "openrouter": "deferred",
        "opencode": "ambiguous",
        "arena": "mapped",
    }
    assert list(
        models.SourceSubjectMapping.objects.filter(purpose="catalog").values_list(
            "source_id", flat=True
        )
    ) == ["arena"]


def test_match_keys_preserve_numeric_boundaries_and_model_suffixes():
    from core.release_catalog_discovery import model_name_key

    assert model_name_key("GLM‑5.4") == model_name_key("glm 5.4")
    assert model_name_key("Model-1-2") != model_name_key("Model-12")
    assert model_name_key("GLM-5.4-Flash") != model_name_key("GLM-5.4")


@pytest.mark.parametrize("reverse", [False, True])
def test_two_sibling_products_cannot_claim_same_provider_identity(reverse):
    from django.utils import timezone

    from core.collection_budgets import invocation_budget
    from core.release_catalog_discovery import discover_release_catalogs
    from core.release_chart_handoff import resolve_catalog_release
    from tests.product_factory import product_type_fields
    from tests.test_release_chart_metric_collection import release_for

    company = models.Company.objects.create(nickname="studio")
    releases = []
    for i in (1, 2):
        brand = models.Brand.objects.create(nickname=f"studio-{i}")
        models.BrandCompany.objects.create(brand=brand, company=company)
        org = models.Account.x.create(author_id=str(9856700 + i), handle=f"studio_{i}")
        role, _ = models.Role.objects.get_or_create(pk="official")
        models.BrandAccount.objects.create(brand=brand, account=org, role=role)
        row = models.Product.objects.create(
            brand=brand,
            display_name="Model One",
            **product_type_fields(models.Product, "model-llm"),
        )
        event, _ = release_for(row, key=f"duplicate-model-{i}")
        releases.append(resolve_catalog_release(event.pk))

    def found(_fetch, matches, owns):
        assert matches("Model-One") and owns("Studio")
        return [
            (
                "studio/model-one",
                "catalog_id",
                "https://openrouter.ai/studio/model-one",
                {},
            )
        ]

    with httpx.Client() as client:
        for release in releases[:: -1 if reverse else 1]:
            result = discover_release_catalogs(
                release,
                invocation_budget(client),
                now=timezone.now(),
                catalogs={"openrouter": found},
            )
            assert result["openrouter"] == "ambiguous"
    assert not models.SourceSubjectMapping.objects.filter(
        external_identifier="studio/model-one"
    ).exists()


def test_conflicting_company_account_cannot_supply_provider_issuer():
    from django.utils import timezone

    from core.collection_budgets import invocation_budget
    from core.release_catalog_discovery import discover_release_catalogs

    release = replay_announcement()
    company = models.Company.objects.create(nickname="glm-owner")
    other = models.Company.objects.create(nickname="unrelated")
    models.BrandCompany.objects.create(brand_id=release.brand_id, company=company)
    wrong = models.Account.x.create(author_id="9856721", handle="wrongpublisher")
    models.BrandAccount.objects.create(
        brand_id=release.brand_id, account=wrong, role_id="official"
    )
    models.CompanyAccount.objects.create(
        company=other, account=wrong, role_id="official", ownership_confirmed=True
    )

    def listing(_fetch, matches, owns):
        assert matches("GLM-5.4") and owns("Zhipu GLM")
        if owns("wrongpublisher"):
            return [
                (
                    "wrongpublisher/glm-5.4",
                    "catalog_id",
                    "https://openrouter.ai/wrongpublisher/glm-5.4",
                    {},
                )
            ]
        return []

    with httpx.Client() as client:
        result = discover_release_catalogs(
            release,
            invocation_budget(client),
            now=timezone.now(),
            catalogs={"openrouter": listing},
        )
    assert result == {"openrouter": "no_verified_match"}
    assert not models.SourceSubjectMapping.objects.filter(
        external_identifier="wrongpublisher/glm-5.4"
    ).exists()
