import copy

import pytest

from core.measurement_taxonomy import configure_taxonomy, subject_id
from core.models import Brand, BrandCompany, Company, HFOrg, Product

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


def setup_spec():
    from core.benchmark_metric_identity import register_definitions

    register_definitions()
    # Test-only reviewed grants; real source rights are never inferred from these.
    from core.benchmark_attribution import USES
    from core.models import DataSource
    from tests.test_benchmark_use_policy import decision

    for source in DataSource.objects.all():
        policy = {use: decision() for use in USES}
        policy["datasets"] = {
            name: {use: decision() for use in USES}
            for name in (
                "cfahlgren1/hub-stats",
                "hfmlsoc/hub_weekly_snapshots",
                "lmarena-ai/leaderboard-dataset",
                "openrouter/rankings-daily",
                "opencode/model-daily",
            )
        }
        source.metadata["use_policy"] = policy
        source.save(update_fields=["metadata"])
    brand = Brand.objects.create(nickname="lab", display_name="Lab")
    company = Company.objects.create(nickname="lab", display_name="Lab")
    BrandCompany.objects.create(brand=brand, company=company)
    org = HFOrg.objects.create(namespace="lab", company=company, confirmed=True)
    product = Product.objects.create(
        repo_id="lab/Model",
        hf_org=org,
        brand=brand,
        type="llm-model",
        private=False,
        disabled=False,
    )
    taxonomy = configure_taxonomy(
        {
            "reviewed_by": "fixture",
            "subjects": [{"kind": "product", "key": str(product.product_key)}],
        }
    )
    spec = {
        "taxonomy_version": str(taxonomy.pk),
        "reviewed_by": "fixture",
        "mappings": [
            {
                "source": "hf",
                "external_identifier": "lab/Model",
                "identifier_scope": "model",
                "source_subject_kind": "repository",
                "subject_id": str(subject_id("product", product.product_key)),
                "evidence_url": "https://huggingface.co/lab/Model",
            }
        ],
        "source_configuration": {
            "hf": {"metrics": ["downloads", "downloads_all_time"]}
        },
        "methodology": {"aggregation": "fixed_cohort"},
    }
    return product, spec


def test_contract_is_reviewed_idempotent_and_frozen():
    from core.benchmark_metric_identity import configure_collection

    product, spec = setup_spec()
    contract = configure_collection(spec)
    assert configure_collection(copy.deepcopy(spec)).pk == contract.pk
    assert contract.mappings.get().subject.product_id == product.product_key
    product.display_name = "Renamed later"
    product.save()
    contract.refresh_from_db()
    assert "Renamed later" not in str(contract.catalog_snapshot)
    revised = copy.deepcopy(spec)
    revised["source_configuration"]["hf"]["poll_seconds"] = 43200
    assert configure_collection(revised).pk != contract.pk


@pytest.mark.parametrize("change", ["type", "private", "unconfirmed", "repo", "review"])
def test_unreviewed_or_incompatible_hf_mapping_rejected(change):
    from core.benchmark_metric_identity import configure_collection

    product, spec = setup_spec()
    if change == "type":
        product.type = None
        product.save()
    if change == "private":
        product.private = True
        product.save()
    if change == "unconfirmed":
        product.hf_org.confirmed = False
        product.hf_org.save()
    if change == "repo":
        spec["mappings"][0]["external_identifier"] = "other/Model"
    if change == "review":
        spec["reviewed_by"] = ""
    with pytest.raises(ValueError):
        configure_collection(spec)


def test_hf_namespace_bridge_preserves_identity_and_provenance():
    from core.benchmark_metric_identity import configure_hf_account
    from core.models import CompanyAccount

    product, _ = setup_spec()
    account = configure_hf_account(
        "lab", reviewed_by="fixture", evidence_url="https://huggingface.co/lab"
    )
    assert (
        configure_hf_account(
            "lab", reviewed_by="fixture", evidence_url="https://huggingface.co/lab"
        ).pk
        == account.pk
    )
    product.hf_org.refresh_from_db()
    assert product.hf_org.account_id == account.pk
    assert product.hf_org.confirmed is True
    assert CompanyAccount.objects.get(account=account).company_id == "lab"
