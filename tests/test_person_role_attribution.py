"""A resolved identity and a job in the same source need a direct attribution."""

import pytest

from core.models import (
    Account,
    Brand,
    BrandAccount,
    Person,
    PersonBrandAffiliation,
    Role,
)
from core.person_names import record_name
from core.staff_assets.person_intake import create_or_update_person
from core.staff_assets.person_portrait_assessment import (
    PortraitAssessment,
    grounded_job_history,
    grounded_observation,
)

NAME = "Lin Shu"
ORG = "Qilin Lab"
TITLE = "design director"
URL = "https://news.example/staff"
WHEN = "2026-11-23T08:00:00+09:00"


def proposal(organization=ORG, title=TITLE):
    return {"organization": organization, "title": title, "status": "current"}


@pytest.mark.parametrize(
    "quote",
    [
        "Lin Shu interviewed Jane Li, design director of Qilin Lab.",
        "Lin Shu is not the design director of Qilin Lab.",
        "Lin Shu interviewed Qilin Lab design director Jane Li.",
        "Jane Li is the design director of Qilin Lab, Lin Shu said.",
        "Lin Shu, Qilin Lab design director Jane Li wants to meet.",
    ],
)
@pytest.mark.requires_postgres
@pytest.mark.django_db
def test_intake_leaves_account_and_jobs_unaffiliated(quote):
    Brand.objects.create(nickname="qilin-test", display_name=ORG)
    Role.objects.get_or_create(pk="staff")
    account = Account.x.create(author_id="55501", handle="linshu", display_name=NAME)
    result = create_or_update_person(
        NAME,
        {
            "identity_supported": True,
            "passage": quote,
            "source_url": URL,
            "observed_at": WHEN,
            "personal_account": {"native_id": account.author_id},
            "industry": True,
            "affiliation": proposal(),
        },
        needs={"jobs"},
        collect=False,
    )
    assert result["person_id"] and result["account_key"] == str(account.pk)
    assert result["affiliation"] is None
    assert "affiliation_unresolved" in result["gaps"]
    assert not BrandAccount.objects.filter(account=account).exists()
    assert not PersonBrandAffiliation.objects.filter(
        person_id=result["person_id"]
    ).exists()


@pytest.mark.parametrize(
    "url, expected", [("https://x.com/linshu", True), (URL, False)]
)
@pytest.mark.requires_postgres
@pytest.mark.django_db
def test_first_person_job_is_sourced_to_the_subjects_profile(url, expected):
    Brand.objects.create(nickname="qilin-test", display_name=ORG)
    Role.objects.get_or_create(pk="staff")
    account = Account.x.create(author_id="55501", handle="linshu", display_name=NAME)
    result = create_or_update_person(
        NAME,
        {
            "identity_supported": True,
            "passage": "I'm the design director at Qilin Lab.",
            "personal_account": {"native_id": account.author_id},
            "affiliation": proposal(),
            "source_url": url,
            "observed_at": WHEN,
        },
        collect=False,
    )
    assert bool(result["affiliation"]) == expected
    assert BrandAccount.objects.filter(account=account).exists() == expected


@pytest.mark.requires_postgres
@pytest.mark.django_db
def test_localized_collector_spelling_keeps_its_subject_bound_job():
    person = Person.objects.create()
    quote = "林书现任麒麟实验室首席科学家。"
    record_name(
        person,
        full_name="林书",
        language="und",
        source_kind="named_third_party",
        source_reference=URL,
        source_text=quote,
        collection_method="chinese_person_collector",
    )
    Brand.objects.create(nickname="qilin-test", display_name_zh_cn="麒麟实验室")
    result = create_or_update_person(
        NAME,
        {
            "person_id": str(person.pk),
            "name": "林书",
            "identity_supported": True,
            "passage": quote,
            "source_url": URL,
            "observed_at": WHEN,
            "industry": True,
            "affiliation": proposal("麒麟实验室", "首席科学家"),
        },
        needs={"jobs"},
        collect=False,
    )
    assert result["affiliation"]["title"] == "首席科学家"
    assert PersonBrandAffiliation.objects.get(person=person).title_raw == "首席科学家"


@pytest.mark.parametrize(
    "quote, prefix, expected",
    [
        ("Lin Shu interviewed Jane Li, design director of Qilin Lab.", "", False),
        ("Lin Shu was never the design director of Qilin Lab.", "", False),
        ("Lin Shu is the design director of Qilin Lab.", "It is false that ", False),
        ("Lin Shu is the design director of Qilin Lab.", "", True),
    ],
)
def test_portrait_and_job_history_ground_the_same_relationship(quote, prefix, expected):
    claim = proposal()
    reading = PortraitAssessment(
        identity="supported",
        identity_quote=NAME,
        image="absent",
        attribution_quote="",
        affiliation_quote=quote,
        organization=ORG,
        title=TITLE,
        affiliation_status="current",
        job_history=[{**claim, "quote": quote, "source_url": URL}],
    )
    page = {
        "title": NAME,
        "passage": prefix + quote,
        "source_url": URL,
        "observed_at": WHEN,
    }
    assert ("affiliation" in grounded_observation(reading, page, NAME)) == expected
    jobs = list(grounded_job_history(reading, [page], NAME))
    assert [row["affiliation"] for row in jobs] == ([claim] if expected else [])


@pytest.mark.parametrize(
    ("subject", "org", "title", "quote", "status"),
    [
        (
            NAME,
            ORG,
            TITLE,
            "Lin Shu（林书） is the design director at Qilin Lab.",
            "current",
        ),
        (
            "林书",
            "麒麟实验室",
            "首席科学家",
            "林书曾在麒麟实验室担任首席科学家。",
            "former",
        ),
        (
            "林书",
            "麒麟实验室",
            "首席科学家",
            "林书采访了麒麟实验室首席科学家李明。",
            None,
        ),
    ],
)
def test_bilingual_and_localized_roles_preserve_source_attribution(
    subject, org, title, quote, status
):
    from core.staff_assets.person_roles import sourced_role

    result = sourced_role(subject, org, quote, title)
    assert (result["status"] if result else None) == status
