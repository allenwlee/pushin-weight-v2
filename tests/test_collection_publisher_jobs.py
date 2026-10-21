"""Account enrollment inherits existing authority without widening company scope."""

import httpx
import pytest

from core.collection_jobs import register_job, set_job_state
from core.collection_publisher_jobs import enroll_confirmed_accounts, publisher_job_spec
from core.collection_scheduling import (
    dispatch_collection_roles,
    take_collection_authority,
)
from core.models import CollectionJob, Company, CompanyAccount, MetricValue
from tests.publisher_fixtures import hf_publisher
from tests.test_source_metric_projection import configured

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]
LIMITS = {"requests": 20, "bytes": 1000000, "seconds": 60, "items": 100}


def template(*, authority=True):
    contract, _, product, _ = configured()
    account = product.publisher_account
    company = account.companies.get(role_id="official").company
    job = register_job(
        **publisher_job_spec(
            job_key="publisher-template",
            account=account,
            budgets=LIMITS,
            options={"ingest_metadata": True},
            numeric_contract_id=contract.pk,
            routine_role="inventory",
        )
    )
    set_job_state(job.pk, "ready")
    if authority:
        take_collection_authority(job.pk)
    job.refresh_from_db()
    return job, company


def test_new_confirmed_account_gets_independent_job_and_native_metrics(settings):
    from core.model_inventory import execute_model_inventory
    from scripts.benchmark_download_collector.sources import Budget

    settings.BENCHMARK_COLLECTION_ENABLED = True
    original, company = template()
    account = hf_publisher(namespace="NewLab", company=company, confirmed=True).account
    created = enroll_confirmed_accounts("hf")
    assert len(created) == 1
    new = CollectionJob.objects.get(pk=created[0])
    assert new.owner_account_id == account.pk and new.origin_job_id == original.pk
    assert (
        new.definition
        == original.definition
        == {"version": 2, "options": {"ingest_metadata": True}}
    )
    assert new.schedule == original.schedule and new.budgets == original.budgets
    assert new.authority_enabled and new.state == "ready"
    assert new.numeric_contract_id != original.numeric_contract_id
    assert new.numeric_contract.mappings.get().publisher_account_id == account.pk
    assert enroll_confirmed_accounts("hf") == []
    third = hf_publisher(namespace="ThirdLab", company=company, confirmed=True).account
    later = enroll_confirmed_accounts("hf")
    assert (
        len(later) == 1
        and CollectionJob.objects.get(pk=later[0]).owner_account_id == third.pk
    )

    def respond(request):
        raw = {
            "id": "NewLab/Model",
            "author": "NewLab",
            "downloads": 2,
            "downloadsAllTime": 9,
            "likes": 3,
            "private": False,
        }
        if request.url.path == "/api/models":
            assert request.url.params["author"] == "NewLab"
            return httpx.Response(200, json=[raw])
        if request.url.path.endswith("/overview"):
            return httpx.Response(200, json={"name": "NewLab", "numFollowers": 1})
        return httpx.Response(200, json=raw)

    run = execute_model_inventory(
        new.pk, budget=Budget(httpx.Client(transport=httpx.MockTransport(respond)))
    )
    assert run.status == "success", run.report
    values = MetricValue.objects.filter(
        observation__run__job__contract=new.numeric_contract
    )
    assert values.count() >= 3
    assert set(values.values_list("observation__run__job__contract_id", flat=True)) == {
        new.numeric_contract_id
    }
    original.refresh_from_db()
    assert original.active_run_id is None and original.last_attempt_id is None
    assert not new.numeric_contract.source_configuration["hf"]["scheduling_enabled"]


def test_unconfirmed_conflicting_and_untracked_accounts_are_not_enrolled():
    original, company = template()
    hf_publisher(namespace="Unconfirmed", company=company, confirmed=False)
    joint = hf_publisher(namespace="Joint", company=company, confirmed=True).account
    other = Company.objects.create(nickname="other-company")
    hf_publisher(namespace="Other", company=other, confirmed=True)
    CompanyAccount.objects.create(
        account=joint, company=other, role_id="official", ownership_confirmed=True
    )
    assert enroll_confirmed_accounts("hf") == []
    assert CollectionJob.objects.count() == 1
    assert CollectionJob.objects.get(pk=original.pk).authority_enabled


def test_inspection_and_missing_authority_do_not_create_or_enable_jobs(settings):
    settings.BENCHMARK_COLLECTION_ENABLED = True
    original, company = template(authority=False)
    account = hf_publisher(
        namespace="PendingLab", company=company, confirmed=True
    ).account
    assert enroll_confirmed_accounts("hf") == []
    take_collection_authority(original.pk)
    dispatch_collection_roles(execute=False)
    assert not CollectionJob.objects.filter(owner_account=account).exists()
    source = original.source
    source.enabled = False
    source.save()
    assert enroll_confirmed_accounts("hf") == []
    source.refresh_from_db()
    assert not source.enabled


def test_existing_paused_account_job_is_preserved():
    _, company = template()
    account = hf_publisher(
        namespace="PausedLab", company=company, confirmed=True
    ).account
    paused = register_job(
        **publisher_job_spec(
            job_key="deliberately-paused",
            account=account,
            budgets=LIMITS,
            routine_role="inventory",
        )
    )
    assert enroll_confirmed_accounts("hf") == []
    paused.refresh_from_db()
    assert paused.state == "paused" and not paused.authority_enabled


def test_github_factory_registers_account_owned_instructions_and_separate_jobs():
    from core.github_catalog import register_github_job
    from tests.test_collection_identity import identities

    _, account, _, _ = identities()
    job = register_github_job(
        job_key="github-publisher", publisher_ids=[account.pk], budgets=LIMITS
    )
    assert job.instruction_version == 2 and job.owner_account_id == account.pk
    assert job.definition == {"version": 2, "options": {"github_role": "inventory"}}
    assert job.state == "paused" and not job.authority_enabled
    assert (
        register_github_job(
            job_key="github-publisher", publisher_ids=[account.pk], budgets=LIMITS
        ).pk
        == job.pk
    )
    with pytest.raises(ValueError, match="one GitHub account"):
        register_github_job(
            job_key="github-combined",
            publisher_ids=[account.pk, account.pk],
            budgets=LIMITS,
        )
    assert CollectionJob.objects.count() == 1
