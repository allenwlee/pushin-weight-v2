"""Source-first role application never guesses identities or creates staff work."""

from datetime import timedelta

import pytest
from django.utils import timezone

from core.models import (
    Account,
    Brand,
    PersonAccount,
    PersonBrandAffiliation,
    PersonBrandAffiliationEvidence,
    Post,
    StaffCollectionWork,
)
from core.staff_assets.arrivals import catch_up
from core.staff_assets.job_history_apply import apply_sourced_role
from tests.person_factory import person_with_name

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def setup_source():
    Brand.objects.get_or_create(
        nickname="deepseek", defaults={"display_name": "DeepSeek"}
    )
    person = person_with_name("Saved source person")
    account = Account.objects.create(author_id="123456", handle="savedsource")
    now = timezone.now()
    PersonAccount.objects.create(
        person=person,
        account=account,
        resolution_status="confirmed",
        first_observed_at=now,
        last_observed_at=now,
    )
    fields = {
        "brand_id": "deepseek",
        "affiliation_type": "employment",
        "observed_organization_name": "DeepSeek",
        "status": "current",
        "start_date": "2026-08",
        "start_date_precision": "month",
        "end_date": None,
        "end_date_precision": "unknown",
        "review_status": "pending",
    }
    source = {
        "kind": "post",
        "account_key": str(account.pk),
        "post_id": "123456789",
        "url": "https://x.com/savedsource/status/123456789",
        "text": "Current role at DeepSeek since 2026-08",
        "published_at": (now - timedelta(days=1)).isoformat(),
        "observed_at": now.isoformat(),
    }
    return person, fields, source


def test_source_is_created_before_role_evidence_and_replay_is_idempotent():
    person, fields, source = setup_source()
    result = apply_sourced_role(
        person_id=person.pk, fields=fields, source=source, expected_action="create"
    )
    assert result["action"] == "create"
    evidence = PersonBrandAffiliationEvidence.objects.get(pk=result["evidence_id"])
    assert evidence.source_post_id == source["post_id"]
    assert evidence.observed_at == timezone.datetime.fromisoformat(
        source["observed_at"]
    )
    repeated = apply_sourced_role(
        person_id=person.pk, fields=fields, source=source, expected_action="create"
    )
    assert repeated["action"] != "hold", repeated
    assert repeated["role_id"] == result["role_id"]
    assert not repeated["evidence_created"]
    assert PersonBrandAffiliation.objects.filter(person=person).count() == 1
    catch_up(list_id="999999")
    assert not StaffCollectionWork.objects.filter(person=person).exists()


def test_unstated_status_is_held_while_source_supported_role_is_preserved():
    person, fields, source = setup_source()
    source["text"] = "Role at DeepSeek since 2026-08"
    result = apply_sourced_role(
        person_id=person.pk, fields=fields, source=source, expected_action="create"
    )
    assert result["action"] == "create"
    assert result["held_fields"] == {"status": "current"}
    role = PersonBrandAffiliation.objects.get(pk=result["role_id"])
    assert role.status == "unknown"
    assert role.evidence.get().evidence_text == source["text"]
    repeated = apply_sourced_role(
        person_id=person.pk, fields=fields, source=source, expected_action="create"
    )
    assert repeated["role_id"] == role.pk
    assert repeated["held_fields"] == {"status": "current"}
    assert PersonBrandAffiliation.objects.filter(person=person).count() == 1


def test_conflicting_existing_post_holds_without_writing_role():
    person, fields, source = setup_source()
    Post.objects.create(tweet_id=source["post_id"], text="conflicting source")
    result = apply_sourced_role(
        person_id=person.pk, fields=fields, source=source, expected_action="create"
    )
    assert result["action"] == "hold"
    assert not PersonBrandAffiliation.objects.filter(person=person).exists()


@pytest.mark.parametrize("organization", [None, "Mistral"])
def test_role_cannot_attach_an_unbound_organization_to_a_brand(organization):
    person, fields, source = setup_source()
    fields["observed_organization_name"] = organization
    source["text"] = "Current role at Mistral since 2026-08"
    result = apply_sourced_role(
        person_id=person.pk, fields=fields, source=source, expected_action="create"
    )
    assert result["action"] == "hold"
    assert not PersonBrandAffiliation.objects.filter(person=person).exists()
    assert not Post.objects.filter(pk=source["post_id"]).exists()


def test_ambiguous_brand_name_is_held():
    person, fields, source = setup_source()
    Brand.objects.create(nickname="another", display_name="DeepSeek")
    result = apply_sourced_role(
        person_id=person.pk, fields=fields, source=source, expected_action="create"
    )
    assert result["action"] == "hold"
    assert not Post.objects.filter(pk=source["post_id"]).exists()


def test_saved_bio_snapshot_creation_replays_and_holds_a_second_clock():
    from core.models import AccountProfileSnapshot
    from core.staff_assets.job_history_apply import apply_profile_action

    person, _, source = setup_source()
    account = person.account_links.get().account
    observed = source["observed_at"]
    person_packet = {
        "sources": [
            {
                "kind": "saved_bio",
                "text": source["text"],
                "observations": [
                    {
                        "kind": "account.profile_bio_text",
                        "handle": account.handle,
                        "observed": observed,
                    }
                ],
            }
        ]
    }
    action = {
        "action": "compare_or_create",
        "fields": {
            "account_key": str(account.pk),
            "source_reference": "https://x.com/savedsource",
            "saved_bio": source["text"],
            "observed_at": observed,
            "observed_handle": account.handle,
            "observation_kind": "account.profile_bio_text",
        },
    }
    first = apply_profile_action(
        person=person, account=account, person_packet=person_packet, action=action
    )
    assert first["action"] == "create", first
    assert (
        apply_profile_action(
            person=person, account=account, person_packet=person_packet, action=action
        )["action"]
        == "reuse"
    )
    later = (
        timezone.datetime.fromisoformat(observed) + timedelta(seconds=1)
    ).isoformat()
    action["fields"]["observed_at"] = later
    person_packet["sources"][0]["observations"][0]["observed"] = later
    assert (
        apply_profile_action(
            person=person, account=account, person_packet=person_packet, action=action
        )["action"]
        == "hold"
    )
    assert AccountProfileSnapshot.objects.filter(account=account).count() == 1


def test_historical_bio_is_captured_outside_existing_interval_but_not_inside():
    from core.models import AccountProfileSnapshot
    from core.profile_snapshots import (
        profile_observation_from_payload,
        record_profile_snapshot,
    )
    from core.staff_assets.job_history_apply import apply_profile_action

    person, _, source = setup_source()
    account = person.account_links.get().account
    now = timezone.datetime.fromisoformat(source["observed_at"])
    observation = profile_observation_from_payload(
        {
            "author_handle": account.handle,
            "author_profile_bio_text": "Newer profile",
            "_author_present_fields": ["author_handle", "author_profile_bio_text"],
        }
    )
    for when in (now, now + timedelta(hours=2)):
        record_profile_snapshot(
            account=account,
            observation=observation,
            observed_at=when,
            source_kind="post",
        )

    def attempt(when):
        observed = when.isoformat()
        packet = {
            "sources": [
                {
                    "kind": "saved_bio",
                    "text": source["text"],
                    "observations": [
                        {
                            "kind": "account.profile_bio_text",
                            "handle": account.handle,
                            "observed": observed,
                        }
                    ],
                }
            ]
        }
        action = {
            "action": "compare_or_create",
            "fields": {
                "account_key": str(account.pk),
                "source_reference": "https://x.com/savedsource",
                "saved_bio": source["text"],
                "observed_at": observed,
                "observed_handle": account.handle,
                "observation_kind": "account.profile_bio_text",
            },
        }
        return apply_profile_action(
            person=person, account=account, person_packet=packet, action=action
        )

    assert attempt(now + timedelta(hours=1))["action"] == "hold"
    captured = attempt(now - timedelta(hours=1))
    assert captured["action"] == "create", captured
    assert AccountProfileSnapshot.objects.filter(account=account).count() == 2
    account.refresh_from_db()
    assert account.description is None


def test_unsupported_date_is_held_before_creating_a_post():
    person, fields, source = setup_source()
    source["text"] = "Current role at DeepSeek since August"
    result = apply_sourced_role(
        person_id=person.pk, fields=fields, source=source, expected_action="create"
    )
    assert result["action"] == "hold"
    assert "start_date" in result["reason"]
    assert not Post.objects.filter(pk=source["post_id"]).exists()


def test_stale_prepared_role_rolls_back_new_source_post():
    person, fields, source = setup_source()
    result = apply_sourced_role(
        person_id=person.pk,
        fields=fields,
        source=source,
        expected_action="enrich",
        expected_id=99999,
    )
    assert result["action"] == "hold"
    assert not Post.objects.filter(pk=source["post_id"]).exists()


def test_day_precision_enriches_existing_role_and_keeps_both_sources():
    person, fields, first = setup_source()
    created = apply_sourced_role(
        person_id=person.pk, fields=fields, source=first, expected_action="create"
    )
    refined_fields = {
        **fields,
        "start_date": "2026-08-12",
        "start_date_precision": "day",
    }
    second = {
        **first,
        "post_id": "123456790",
        "url": "https://x.com/savedsource/status/123456790",
        "text": "Current role at DeepSeek since 2026-08-12",
    }
    refined = apply_sourced_role(
        person_id=person.pk,
        fields=refined_fields,
        source=second,
        expected_action="enrich",
        expected_id=created["role_id"],
    )
    assert refined["action"] == "enrich"
    role = PersonBrandAffiliation.objects.get(pk=created["role_id"])
    assert (role.start_date, role.start_date_precision) == ("2026-08-12", "day")
    assert set(role.evidence.values_list("source_post_id", flat=True)) == {
        "123456789",
        "123456790",
    }
    replay = apply_sourced_role(
        person_id=person.pk,
        fields=refined_fields,
        source=second,
        expected_action="enrich",
        expected_id=role.pk,
    )
    assert not replay["evidence_created"]
    assert role.evidence.count() == 2


def test_missing_selected_brand_requires_exact_source_support():
    person, fields, source = setup_source()
    fields = {**fields, "brand_id": "newlab", "observed_organization_name": "NewLab"}
    source["text"] = "Current role at NewLab since 2026-08"
    definition = {
        "table": "brands",
        "key": "newlab",
        "action": "create",
        "fields": {"nickname": "newlab", "display_name": "NewLab"},
    }
    result = apply_sourced_role(
        person_id=person.pk,
        fields=fields,
        source=source,
        expected_action="create",
        brand_definition=definition,
        selected_brands=["newlab"],
    )
    assert result["action"] == "create" and result["brand_created"] is True
    assert Brand.objects.filter(pk="newlab", display_name="NewLab").exists()


def test_missing_brand_outside_scope_does_not_create_source_or_brand():
    person, fields, source = setup_source()
    fields = {**fields, "brand_id": "newlab", "observed_organization_name": "NewLab"}
    source["text"] = "Current role at NewLab since 2026-08"
    definition = {
        "table": "brands",
        "key": "newlab",
        "action": "create",
        "fields": {"nickname": "newlab", "display_name": "NewLab"},
    }
    result = apply_sourced_role(
        person_id=person.pk,
        fields=fields,
        source=source,
        expected_action="create",
        brand_definition=definition,
        selected_brands=["deepseek"],
    )
    assert result["action"] == "hold"
    assert not Brand.objects.filter(pk="newlab").exists()
    assert not Post.objects.filter(pk=source["post_id"]).exists()


@pytest.mark.parametrize("proof", ["post", "profile", None, "conflict"])
def test_role_source_uses_proved_historical_handle_without_renaming(proof):
    from core.models import AccountProfileSnapshot
    from core.profile_snapshots import (
        profile_observation_from_payload,
        record_profile_snapshot,
    )

    person, fields, source = setup_source()
    account = person.account_links.get().account
    if proof in {"post", "conflict"}:
        Post.objects.create(tweet_id="historical-handle-proof", author=account,
            author_handle=account.handle, text="Earlier saved post")
    if proof == "profile":
        observation = profile_observation_from_payload({"author_handle": account.handle})
        record_profile_snapshot(account=account, observation=observation,
            observed_at=timezone.now(), source_kind="account")
        assert AccountProfileSnapshot.objects.filter(account=account).exists()
    account.handle = "newspelling"
    account.save(update_fields=["handle"])
    if proof == "conflict":
        Account.objects.create(author_id="999991", handle="savedsource")
    outcome = apply_sourced_role(person_id=person.pk, fields=fields, source=source, expected_action="create")
    account.refresh_from_db()
    assert account.handle == "newspelling"
    if proof in {"post", "profile"}:
        assert outcome["action"] == "create", outcome
        assert Post.objects.get(pk=source["post_id"]).author_handle == "savedsource"
    else:
        assert outcome["action"] == "hold"
        assert not PersonBrandAffiliation.objects.filter(person=person).exists()
        assert not Post.objects.filter(pk=source["post_id"]).exists()


def test_invalid_supporting_source_rolls_back_the_complete_role():
    person, fields, source = setup_source()
    fields.update(title_raw="Engineer", team="Research")
    source["text"] += " Engineer"
    additional = {**source, "post_id": "123456790", "text": "Research team at DeepSeek"}
    # This second source still names the first post's URL.
    outcome = apply_sourced_role(person_id=person.pk, fields=fields, source=source,
        supporting_sources=[additional], expected_action="create")
    assert outcome["action"] == "hold"
    assert not PersonBrandAffiliation.objects.filter(person=person).exists()
    assert not Post.objects.filter(pk=source["post_id"]).exists()


def test_source_only_enrichment_does_not_change_independent_collection_context():
    from core.staff_assets.intake import ingest_record
    from tests.test_staff_library import record

    person, fields, source = setup_source()
    data = record(person_id=str(person.pk))
    data["affiliations"][0].pop("title_raw")
    data["affiliations"][0].pop("location")
    ingest_record(data)
    role = PersonBrandAffiliation.objects.get(person=person)
    catch_up(list_id="999999")
    before = list(StaffCollectionWork.objects.filter(person=person).values_list("pk", "fingerprint", "state"))
    fields.update(title_raw="Engineer", team="Research")
    source["text"] += " Engineer in Research"
    outcome = apply_sourced_role(person_id=person.pk, fields=fields, source=source,
        expected_action="enrich", expected_id=role.pk)
    assert outcome["action"] == "enrich", outcome
    assert outcome["held_fields"] == {"title_raw": "Engineer"}
    role.refresh_from_db()
    assert role.title_raw in (None, "")
    assert role.team == "Research"
    catch_up(list_id="999999")
    assert list(StaffCollectionWork.objects.filter(person=person).values_list("pk", "fingerprint", "state")) == before
    assert role.evidence.filter(source_post_id=source["post_id"]).exists()
