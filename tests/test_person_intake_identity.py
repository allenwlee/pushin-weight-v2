"""Exercise online preview and data-only apply through their real database entry points."""

import json
from functools import partial
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from core.models import (
    Account,
    Brand,
    BrandAccount,
    BrandCompany,
    Company,
    CompanyAccount,
    Person,
    PersonAccount,
    PersonBrandAffiliation,
    PersonName,
    Post,
    Product,
    ProductType,
    Role,
    StaffCollectionWork,
    StaffIntake,
)
from core.person_names import record_legacy_display_name
from core.staff_assets.arrivals import catch_up, without_collection_registration
from core.staff_assets.person_intake import create_or_update_person

reconcile = partial(create_or_update_person, collect=False)

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


@pytest.fixture
def arthur():
    brand, _ = Brand.objects.get_or_create(
        pk="mistral", defaults={"display_name": "Mistral"}
    )
    company, _ = Company.objects.get_or_create(pk="mistral-ai")
    BrandCompany.objects.create(brand=brand, company=company)
    Product.objects.create(
        brand=brand, product_type=ProductType.objects.get(code="model-llm")
    )
    Role.objects.get_or_create(pk="staff")
    account = Account.x.create(
        author_id="30521",
        handle="arthurm",
        display_name="Arthur Mensch",
        description="CEO of Mistral",
    )
    return account, {
        "passage": "Reporter Wong met Arthur Mensch, CEO of Mistral, to ask about Google.",
        "source_id": "story-142",
        "source_url": "https://press.example/142",
        "observed_at": timezone.now().isoformat(),
    }


def test_portrait_only_preview_apply_replay_from_passage(arthur, tmp_path):
    account, packet = arthur
    source = tmp_path / "observation.json"
    source.write_text(json.dumps(packet))

    def command(**kwargs):
        stdout = StringIO()
        call_command(
            "create_or_update_person",
            subject="Arthur Mensch",
            evidence=str(source),
            stdout=stdout,
            **kwargs,
        )
        return json.loads(stdout.getvalue())

    before = command()
    assert {row["table"] for row in before["proposed_changes"]} == {
        "people",
        "people_accounts",
        "brands_accounts",
        "companies_accounts",
    }
    assert not Person.objects.exists() and not StaffIntake.objects.exists()
    result, replay = command(apply=True), command(apply=True)
    assert before["person_id"] == result["person_id"] == replay["person_id"]
    assert result["account_key"] == str(account.pk)
    assert result["gaps"] == [] and result["industry"] is True and not result["jobs"]
    assert PersonAccount.objects.get().resolution_status == "pending"
    assert (
        BrandAccount.objects.get().brand_id == "mistral"
        and CompanyAccount.objects.get().company_id == "mistral-ai"
    )
    assert (
        StaffIntake.objects.get(source_key__startswith="person-intake:").payload[
            "person_intake"
        ]
        == packet
    )
    assert (
        PersonName.objects.get().evidence.get().source_reference == packet["source_url"]
    )
    assert (
        not StaffCollectionWork.objects.exists()
        and not PersonBrandAffiliation.objects.exists()
    )


def test_known_person_through_merge_company_only_and_conflicting_role(arthur):
    account, packet = arthur
    person = Person.objects.create()
    retired = Person.objects.create(merged_into=person)
    PersonAccount.objects.create(
        person=person,
        account=account,
        resolution_status="confirmed",
        first_observed_at=timezone.now(),
        last_observed_at=timezone.now(),
    )
    brand = Brand.objects.create(pk="second")
    BrandCompany.objects.create(brand=brand, company_id="mistral-ai")
    Role.objects.get_or_create(pk="executive")
    with without_collection_registration():
        CompanyAccount.objects.create(
            company_id="mistral-ai",
            account=account,
            role_id="executive",
            ownership_confirmed=True,
        )
    packet.update(
        person_id=str(retired.pk),
        affiliation={"company_id": "mistral-ai", "organization": "Mistral-AI"},
        passage="Mistral-AI CEO Arthur Mensch visited the lab.",
    )
    result = reconcile("Arthur Mensch", packet)
    assert result["person_id"] == str(person.pk) and result["account_key"] == str(
        account.pk
    )
    assert not BrandAccount.objects.exists()
    assert "companies_accounts_role_conflict" in result["gaps"]
    assert CompanyAccount.objects.get().ownership_confirmed is True
    assert CompanyAccount.objects.get().role_id == "executive"


def test_reporter_former_employer_and_namesakes_are_preserved(arthur):
    account, packet = arthur
    reporter = Account.x.create(
        author_id="30522", handle="reporter", display_name="W. Reporter"
    )
    people = [Person.objects.create() for _ in range(2)]
    for p in people:
        record_legacy_display_name(p, "Alex Doe")
    packet.update(
        author_id=reporter.author_id,
        author_handle=reporter.handle,
        passage="Alex Doe visited a Mistral event.",
    )
    unresolved = reconcile("Alex Doe", packet)
    assert unresolved["person_id"] is None and set(
        unresolved["candidate_person_ids"]
    ) == {str(p.pk) for p in people}
    assert (
        "identity_unresolved" in unresolved["gaps"]
        and not PersonAccount.objects.exists()
    )
    packet.update(
        passage="Arthur Mensch, former CEO of Mistral, was interviewed.",
        personal_account={"handle": account.handle},
    )
    result = reconcile("Arthur Mensch", packet)
    assert result["person_id"] and result["account_key"] == str(account.pk)
    assert not BrandAccount.objects.exists() and not CompanyAccount.objects.exists()


def test_renamed_and_reassigned_handle(arthur):
    account, packet = arthur
    Post.objects.create(
        tweet_id="31000",
        author=account,
        author_handle="oldarthur",
        created_at=timezone.now(),
        text="Earlier post",
    )
    packet["personal_account"] = {"handle": "oldarthur"}
    result = reconcile("Arthur Mensch", packet)
    assert result["account_key"] == str(account.pk)
    Account.x.create(author_id="30523", handle="oldarthur")
    result = reconcile("Arthur Mensch", packet)
    assert result["person_id"] is None and "account_handle_ambiguous" in result["gaps"]
    packet["personal_account"]["native_id"] = account.author_id
    assert "account_handle_conflict" in reconcile("Arthur Mensch", packet)["gaps"]


def test_bound_source_late_enrichment_and_independently_requested_jobs(arthur):
    account, packet = arthur
    first = dict(
        packet,
        passage="A verified portrait caption identifies Arthur Mensch.",
        identity_supported=True,
    )
    initial = reconcile("Arthur Mensch", first)
    assert (
        initial["person_id"]
        and initial["account_key"] is None
        and initial["industry"] is None
    )
    packet.update(
        person_id=initial["person_id"],
        personal_account={"native_id": account.author_id},
        passage="Arthur Mensch, CEO of Mistral since 2021, leads research.",
        affiliation={
            "organization": "Mistral",
            "start_date": "2021",
            "start_date_precision": "year",
            "job_function": "research",
        },
        china_reason="His sourced biography documents study in Beijing.",
        facematch=False,
    )
    result = reconcile("Arthur Mensch", packet, needs={"jobs"})
    assert (
        result["jobs"]
        and result["china"]
        and not result["facematch"]
        and not result["gaps"]
    )
    assert result["person_id"] == initial["person_id"]
    role = PersonBrandAffiliation.objects.get()
    assert (
        role.title_raw,
        role.job_function,
        role.status,
        role.start_date,
        role.start_date_precision,
    ) == ("CEO", "research", "current", "2021", "year")
    assert (
        role.evidence.get().evidence_text == packet["passage"] and role.end_date is None
    )
    reconcile("Arthur Mensch", packet, needs={"jobs"})
    assert PersonBrandAffiliation.objects.count() == role.evidence.count() == 1
    assert not StaffCollectionWork.objects.exists()


@pytest.mark.parametrize(
    ("industry", "research"), [(False, False), (None, False), (True, True)]
)
def test_route_uncertainty_and_sourced_decisions_are_independent(industry, research):
    packet = {
        "passage": "A sourced profile identifies Pat Adams.",
        "source_url": "https://example.com/profile",
        "observed_at": timezone.now().isoformat(),
        "identity_supported": True,
        "industry": industry,
        "china_reason": "An attributed interview in Chinese.",
        "facematch": True,
    }
    result = reconcile("Pat Adams", packet, needs={"jobs", "portrait"})
    assert (
        result["industry"] is industry
        and result["jobs"] is research
        and result["china"] is research
    )
    assert result["facematch"] and Person.objects.get().ethnicity is None
    assert not StaffCollectionWork.objects.exists()


def test_curated_cast_identity_and_namesake_must_match_independently():
    from core.models import PersonMedia, StaffMediaObject

    def person_with_cast(name, org, key):
        person = Person.objects.create()
        record_legacy_display_name(person, name)
        sha = key * 64
        obj = StaffMediaObject.objects.create(
            sha256=sha,
            storage_name="cast/" + sha,
            media_type="image/jpeg",
            byte_size=50,
        )
        PersonMedia.objects.create(
            person=person,
            media=obj,
            fingerprint=sha,
            observed_at=timezone.now(),
            source_kind="saved_g2_cast",
            source_url="https://example.com/" + key,
            availability="available",
            evidence={
                "schema": "g2-cast-image/v1",
                "source_person_key": name.lower().replace(" ", "-"),
                "source_role": "identity-still",
                "identity_resolution": {
                    "state": "verified",
                    "method": "corroborated_name_context",
                    "person_id": str(person.pk),
                    "source_name": name,
                    "source_context_term": org,
                    "evidence": [f"{name}, founder of {org}"],
                },
            },
        )
        return person

    palmer = person_with_cast("Palmer Luckey", "Anduril", "a")
    jensen = person_with_cast("Jensen Huang", "Nvidia", "b")
    namesake = Person.objects.create()
    record_legacy_display_name(namesake, "Jensen Huang")
    packet = {
        "passage": "Palmer Luckey showed reporters the new system.",
        "source_url": "https://press.example/news",
        "observed_at": timezone.now().isoformat(),
    }
    assert reconcile("Palmer Luckey", packet)["person_id"] == str(palmer.pk)
    packet["passage"] = "Jensen Huang greeted the audience."
    assert reconcile("Jensen Huang", packet)["person_id"] is None
    packet["passage"] = "Nvidia CEO Jensen Huang greeted the audience."
    assert reconcile("Jensen Huang", packet)["person_id"] == str(jensen.pk)


def test_single_subject_collection_requires_apply_and_delegates_to_worker(
    arthur, tmp_path, monkeypatch
):
    from django.core.management.base import CommandError

    account, packet = arthur
    evidence = tmp_path / "source.json"
    evidence.write_text(json.dumps(packet))
    with pytest.raises(CommandError, match="requires --apply"):
        call_command(
            "create_or_update_person",
            subject="Arthur Mensch",
            evidence=str(evidence),
            collect=True,
        )
    calls = []

    def collect(identity, subject, evidence, needs):
        calls.append((subject, evidence, needs, bool(identity["person_id"])))
        return {"work_id": 42}

    monkeypatch.setattr(
        "core.staff_assets.person_research.collect_missing", collect
    )
    result = StringIO()
    call_command(
        "create_or_update_person",
        subject="Arthur Mensch",
        evidence=str(evidence),
        collect=True,
        apply=True,
        stdout=result,
    )
    assert calls == [("Arthur Mensch", packet, {"portrait"}, True)] and json.loads(
        result.getvalue()
    ) == {"work_id": 42}
    assert PersonAccount.objects.filter(account=account).exists()


def test_foreground_subject_role_can_establish_industry_without_caller_switch():
    packet = {
        "passage": "U.S. President Donald Trump discussed artificial intelligence.",
        "source_id": "story:1",
        "observed_at": timezone.now().isoformat(),
        "china_reason": "An earlier article was in Chinese.",
    }
    trump = reconcile("Donald Trump", packet, needs={"jobs", "portrait"})
    assert trump["person_id"] and trump["industry"] is False
    assert not any(trump[key] for key in ("china", "jobs", "facematch"))
    packet.update(
        passage="AI researcher Pat Adams spoke to the audience.", source_id="story:2"
    )
    researcher = reconcile("Pat Adams", packet, needs={"jobs"})
    assert (
        researcher["person_id"]
        and researcher["industry"]
        and researcher["china"]
        and researcher["jobs"]
    )
    packet.update(
        passage="The AI researcher interviewed Dana Long.", source_id="story:3"
    )
    assert reconcile("Dana Long", packet)["industry"] is None


def test_former_brand_prefix_and_rejected_account_do_not_make_staff(arthur):
    account, packet = arthur
    packet.update(
        passage="Former Mistral CEO Arthur Mensch was interviewed.",
        personal_account={"native_id": account.author_id},
    )
    result = reconcile("Arthur Mensch", packet)
    assert (
        result["affiliation"]["status"] == "former"
        and not BrandAccount.objects.exists()
    )
    PersonAccount.objects.filter(person_id=result["person_id"]).update(
        resolution_status="rejected"
    )
    assert reconcile("Arthur Mensch", packet)["person_id"] is None
    assert not BrandAccount.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_data_only_edges_survive_catch_up_and_independent_enrollment_still_runs(arthur):
    account, packet = arthur
    outcome = reconcile("Arthur Mensch", packet)
    catch_up(list_id="987654")
    assert not StaffCollectionWork.objects.exists()
    assert not StaffIntake.objects.filter(
        source_key="x-account:" + account.author_id
    ).exists()
    # A different, independently assigned staff edge remains an enrollment source.
    other = Brand.objects.create(pk="independent-lab")
    with without_collection_registration():
        BrandAccount.objects.create(brand=other, account=account, role_id="staff")
    catch_up(list_id="987654")
    assert StaffIntake.objects.filter(
        source_key="x-account:" + account.author_id, person_id=outcome["person_id"]
    ).exists()
    assert StaffCollectionWork.objects.filter(person_id=outcome["person_id"]).exists()


@pytest.mark.django_db(transaction=True)
def test_concurrent_personal_account_reconciliation_creates_one_set_of_edges(arthur):
    from concurrent.futures import ThreadPoolExecutor

    from django.db import connections

    account, packet = arthur

    def reconcile_story(source):
        try:
            return reconcile("Arthur Mensch", dict(packet, source_url=source))[
                "person_id"
            ]
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as threads:
        people = list(
            threads.map(
                reconcile_story, ["https://press.example/1", "https://press.example/2"]
            )
        )
    assert (
        len(set(people)) == PersonAccount.objects.filter(account=account).count() == 1
    )
    assert (
        BrandAccount.objects.filter(account=account).count()
        == CompanyAccount.objects.filter(account=account).count()
        == 1
    )
    assert (
        StaffIntake.objects.filter(
            source_key__startswith="person-intake-links:"
        ).count()
        == 1
    )


def test_namesake_resolution_has_a_bounded_query_count(record_property):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    people = Person.objects.bulk_create([Person() for _ in range(26)])
    for person in people:
        record_legacy_display_name(person, "Jensen Huang")
    alias, survivor = people[:2]
    Person.objects.filter(pk=alias.pk).update(merged_into=survivor)
    from core.person_names import record_name

    source = "https://example.com/reported-profile"
    record_name(
        alias,
        full_name="Jensen Huang",
        language="und",
        source_kind="named_third_party",
        source_reference=source,
        source_text="Jensen Huang visited.",
        collection_method="saved_profile",
    )
    packet = {
        "passage": "Jensen Huang visited the campus.",
        "source_url": source,
        "observed_at": timezone.now().isoformat(),
    }
    with CaptureQueriesContext(connection) as queries:
        result = reconcile("Jensen Huang", packet, apply=False)
    assert (
        result["person_id"] == str(survivor.pk)
        and len(result["candidate_person_ids"]) == 25
    )
    record_property("sql_queries", len(queries))
    assert len(queries) <= 26, len(queries)
