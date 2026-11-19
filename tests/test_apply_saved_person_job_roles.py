"""A partial role importer must fail closed and roll back each person's work."""

import json

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from core.models import PersonBrandAffiliation, Post
from core.person_names import digest
from tests.test_job_history_apply import setup_source
from tests.test_job_history_identity import prepared as prepared_identity

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def packet(person, fields, source):
    account_id = str(person.account_links.get().account_id)
    evidence = {
        "source_kind": "own_post",
        "source_post_ref": "post:" + source["post_id"],
        "native_post_id": source["post_id"],
        "source_url": source["url"],
        "evidence_text": source["text"],
        "published_at": source["published_at"],
        "observed_at": source["observed_at"],
    }
    result = {
        "schema": "record-job-history-preview/v1",
        "selected_brand_ids": ["deepseek"],
        "target": {
            "binding": {
                "database_name": "pushinweight_save_person_job",
                "database_host": "dpg-dbona93m8hqs73ef70mg-a",
            }
        },
        "people": [
            {
                "key": "one",
                "native_id": "123456",
                "handle": "savedsource",
                "names": ["Saved source person"],
                "name_source": {"observed_at": source["observed_at"]},
                "sources": [],
                "identity": {
                    "person_id": str(person.pk),
                    "person_action": "reuse",
                    "account_action": "reuse",
                    "account_key": account_id,
                },
                "affiliations": [
                    {
                        "local_id": "role:one",
                        "action": "create",
                        "fields": fields,
                        "evidence": [evidence],
                    }
                ],
            }
        ],
        "record_actions": [
            {
                "table": "posts",
                "key": source["post_id"],
                "action": "compare_or_create",
                "person_keys": ["one"],
                "observations": [source["observed_at"]],
                "fields": {
                    "native_post_id": source["post_id"],
                    "source_reference": source["url"],
                    "text": source["text"],
                    "published_at": source["published_at"],
                    "author_native_id": "123456",
                },
            }
        ],
    }
    result["payload_digest"] = digest(result)
    return result


def test_partial_role_application_is_explicit_and_replay_safe(tmp_path, monkeypatch):
    person, fields, source = setup_source()
    data = packet(person, fields, source)
    manifest, report = tmp_path / "packet.json", tmp_path / "report.json"
    manifest.write_text(json.dumps(data))
    monkeypatch.setattr(
        "core.management.commands.apply_saved_person_job_roles.verify_target",
        lambda *_: None,
    )
    kwargs = {
        "apply": True,
        "partial_saved_actions": True,
        "confirm_payload_digest": data["payload_digest"],
        "confirm_resource": "test",
        "output": str(report),
    }
    call_command("apply_saved_person_job_roles", str(manifest), **kwargs)
    assert json.loads(report.read_text())["people"][0]["created"] == 1
    assert json.loads(report.read_text())["complete"] is False
    call_command("apply_saved_person_job_roles", str(manifest), **kwargs)
    assert json.loads(report.read_text())["people"][0]["reused"] == 1
    assert PersonBrandAffiliation.objects.filter(person=person).count() == 1


def test_command_reports_status_held_when_role_source_does_not_state_it(
    tmp_path, monkeypatch
):
    person, fields, source = setup_source()
    source["text"] = "Role at DeepSeek since 2026-08"
    data = packet(person, fields, source)
    manifest, report = tmp_path / "packet.json", tmp_path / "report.json"
    manifest.write_text(json.dumps(data))
    monkeypatch.setattr(
        "core.management.commands.apply_saved_person_job_roles.verify_target",
        lambda *_: None,
    )
    call_command(
        "apply_saved_person_job_roles",
        str(manifest),
        apply=True,
        partial_saved_actions=True,
        confirm_payload_digest=data["payload_digest"],
        output=str(report),
    )
    row = json.loads(report.read_text())["people"][0]
    assert row["created"] == 1
    assert row["role_field_holds"][0]["fields"] == {"status": "current"}
    assert row["role_field_holds"][0]["source_reference"] == source["url"]
    assert PersonBrandAffiliation.objects.get(person=person).status == "unknown"


@pytest.mark.parametrize(
    "change", ["person", "id", "text", "url", "published", "observed", "author"]
)
def test_post_evidence_must_match_the_prepared_observation(change):
    from core.management.commands.apply_saved_person_job_roles import (
        post_action_matches,
    )

    person, fields, source = setup_source()
    data = packet(person, fields, source)
    item = data["people"][0]
    evidence = item["affiliations"][0]["evidence"][0]
    action = data["record_actions"][0]
    assert post_action_matches(item, evidence, action)
    if change == "person":
        action["person_keys"] = ["another-person"]
    elif change == "author":
        action["fields"]["author_native_id"] = "999"
    else:
        key = {
            "id": "native_post_id",
            "text": "evidence_text",
            "url": "source_url",
            "published": "published_at",
            "observed": "observed_at",
        }[change]
        evidence[key] = "different"
    assert not post_action_matches(item, evidence, action)


def test_person_failure_rolls_back_prior_sources_and_roles(tmp_path, monkeypatch):
    from django.db import DatabaseError

    from core.management.commands import apply_saved_person_job_roles as importer

    person, fields, source = setup_source()
    data = packet(person, fields, source)
    second = dict(data["people"][0]["affiliations"][0])
    second["local_id"] = "role:two"
    data["people"][0]["affiliations"].append(second)
    data["payload_digest"] = digest(
        {k: v for k, v in data.items() if k != "payload_digest"}
    )
    manifest, report = tmp_path / "packet.json", tmp_path / "report.json"
    manifest.write_text(json.dumps(data))
    monkeypatch.setattr(
        "core.management.commands.apply_saved_person_job_roles.verify_target",
        lambda *_: None,
    )
    original = importer.apply_sourced_role
    calls = []

    def fail_second(**kwargs):
        calls.append(1)
        if len(calls) == 2:
            raise DatabaseError("simulated writer failure")
        return original(**kwargs)

    monkeypatch.setattr(importer, "apply_sourced_role", fail_second)
    call_command(
        "apply_saved_person_job_roles",
        str(manifest),
        apply=True,
        partial_saved_actions=True,
        confirm_payload_digest=data["payload_digest"],
        output=str(report),
    )
    assert json.loads(report.read_text())["people"][0]["failed"] == 2
    assert not Post.objects.filter(pk=source["post_id"]).exists()
    assert not PersonBrandAffiliation.objects.filter(person=person).exists()


def test_unavailable_source_is_held_without_blocking_another_supported_role(
    tmp_path, monkeypatch
):
    person, fields, source = setup_source()
    data = packet(person, fields, source)
    second = dict(data["people"][0]["affiliations"][0])
    second["local_id"] = "role:two"
    second["evidence"] = [{**second["evidence"][0], "source_post_ref": "post:missing"}]
    data["people"][0]["affiliations"].append(second)
    data["payload_digest"] = digest(
        {k: v for k, v in data.items() if k != "payload_digest"}
    )
    manifest, report = tmp_path / "packet.json", tmp_path / "report.json"
    manifest.write_text(json.dumps(data))
    monkeypatch.setattr(
        "core.management.commands.apply_saved_person_job_roles.verify_target",
        lambda *_: None,
    )
    call_command(
        "apply_saved_person_job_roles",
        str(manifest),
        apply=True,
        partial_saved_actions=True,
        confirm_payload_digest=data["payload_digest"],
        output=str(report),
    )
    result = json.loads(report.read_text())["people"][0]
    assert result["created"] == 1 and result["held"] == 1
    assert result["evidence_held"] == 1 and result["role_holds"][0]["key"] == "role:two"


def test_packet_digest_is_required_before_any_write(tmp_path):
    person, fields, source = setup_source()
    data = packet(person, fields, source)
    manifest = tmp_path / "packet.json"
    manifest.write_text(json.dumps(data))
    with pytest.raises(CommandError, match="exact payload digest"):
        call_command(
            "apply_saved_person_job_roles",
            str(manifest),
            apply=True,
            partial_saved_actions=True,
            output=str(tmp_path / "report.json"),
        )
    assert not Post.objects.filter(pk=source["post_id"]).exists()


def test_guard_rejects_original_staging_even_with_task_resource_confirmation(
    monkeypatch,
):
    from core.management.commands.apply_saved_person_job_roles import (
        RESOURCE,
        verify_target,
    )

    monkeypatch.setenv("PUSHINWEIGHT_SAVE_PERSON_JOB_DB_RESOURCE", RESOURCE)
    payload = {
        "target": {
            "read_only": "on",
            "binding": {
                "database_name": "pushinweight_staging",
                "database_host": "dpg-d9vb8ds9v7es738lepsg-a",
            },
        }
    }
    with pytest.raises(CommandError, match="not bound"):
        verify_target(payload, RESOURCE)


def test_cohort_command_applies_and_replays_source_backed_new_identity(
    tmp_path, monkeypatch
):
    item, actions, provenance = prepared_identity()
    item["key"] = item["native_id"]
    item["affiliations"] = []
    for action in actions:
        action["person_key"] = item["key"]
    data = {
        "schema": "record-job-history-preview/v1",
        "selected_brand_ids": ["deepseek"],
        "people": [item],
        "record_actions": actions,
        "language_review_provenance": provenance,
    }
    data["payload_digest"] = digest(data)
    manifest, report = tmp_path / "packet.json", tmp_path / "report.json"
    manifest.write_text(json.dumps(data))
    monkeypatch.setattr(
        "core.management.commands.apply_saved_person_job_roles.verify_target",
        lambda *_: None,
    )
    kwargs = {
        "apply": True,
        "partial_saved_actions": True,
        "confirm_payload_digest": data["payload_digest"],
        "output": str(report),
    }
    call_command("apply_saved_person_job_roles", str(manifest), **kwargs)
    first = json.loads(report.read_text())["totals"]
    assert (
        first["accounts_created"],
        first["people_created"],
        first["names_created"],
        first["language_updated"],
        first["texts_created"],
    ) == (1, 1, 1, 1, 1)
    call_command("apply_saved_person_job_roles", str(manifest), **kwargs)
    second = json.loads(report.read_text())["totals"]
    assert (
        second["accounts_reused"],
        second["people_reused"],
        second["names_reused"],
        second["language_retained"],
        second["texts_reused"],
    ) == (1, 1, 1, 1, 1)


def test_exact_target_profile_source_can_back_role(tmp_path, monkeypatch):
    from django.utils.dateparse import parse_datetime

    from core.profile_snapshots import (
        profile_observation_from_payload,
        record_profile_snapshot,
    )

    person, fields, source = setup_source()
    account = person.account_links.get().account
    observation = profile_observation_from_payload(
        {
            "author_handle": account.handle,
            "author_profile_bio_text": source["text"],
            "_author_present_fields": ["author_handle", "author_profile_bio_text"],
        }
    )
    snapshot, _, _ = record_profile_snapshot(
        account=account,
        observation=observation,
        observed_at=parse_datetime(source["observed_at"]),
        source_kind="account",
    )
    data = packet(person, fields, source)
    data["people"][0]["affiliations"][0]["evidence"] = [
        {
            "source_kind": "saved_bio",
            "source_profile_snapshot_ref": "profile:test",
            "source_profile_snapshot_id": snapshot.pk,
            "source_url": "https://x.com/savedsource",
            "evidence_text": source["text"],
            "observed_at": source["observed_at"],
            "observed_handle": "savedsource",
            "observation_kind": "account.profile_bio_text",
        }
    ]
    data["record_actions"].append(
        {
            "table": "account_profile_snapshots",
            "key": "profile:test",
            "action": "reuse",
            "person_key": "one",
            "fields": {
                "target_snapshot_id": snapshot.pk,
                "account_key": str(account.pk),
                "source_reference": "https://x.com/savedsource",
                "saved_bio": source["text"],
                "observed_at": source["observed_at"],
                "observed_handle": "savedsource",
                "observation_kind": "account.profile_bio_text",
            },
        }
    )
    data["payload_digest"] = digest(
        {k: v for k, v in data.items() if k != "payload_digest"}
    )
    manifest, report = tmp_path / "packet.json", tmp_path / "report.json"
    manifest.write_text(json.dumps(data))
    monkeypatch.setattr(
        "core.management.commands.apply_saved_person_job_roles.verify_target",
        lambda *_: None,
    )
    call_command(
        "apply_saved_person_job_roles",
        str(manifest),
        apply=True,
        partial_saved_actions=True,
        confirm_payload_digest=data["payload_digest"],
        output=str(report),
    )
    result = json.loads(report.read_text())["people"][0]
    assert result["created"] == 1, result
    assert (
        PersonBrandAffiliation.objects.get(person=person)
        .evidence.get()
        .source_profile_snapshot_id
        == snapshot.pk
    )


def test_saved_bio_can_create_profile_and_back_role_atomically(tmp_path, monkeypatch):
    from core.models import AccountProfileSnapshot, StaffCollectionWork

    person, fields, source = setup_source()
    account = person.account_links.get().account
    data = packet(person, fields, source)
    item = data["people"][0]
    item["sources"] = [
        {
            "kind": "saved_bio",
            "text": source["text"],
            "observations": [
                {
                    "kind": "account.profile_bio_text",
                    "handle": account.handle,
                    "observed": source["observed_at"],
                }
            ],
        }
    ]
    evidence = {
        "source_kind": "saved_bio",
        "source_profile_snapshot_ref": "profile:test",
        "source_profile_snapshot_id": None,
        "source_url": "https://x.com/savedsource",
        "evidence_text": source["text"],
        "observed_at": source["observed_at"],
        "observed_handle": account.handle,
        "observation_kind": "account.profile_bio_text",
    }
    item["affiliations"][0]["evidence"] = [evidence]
    data["record_actions"].append(
        {
            "table": "account_profile_snapshots",
            "key": "profile:test",
            "action": "compare_or_create",
            "person_key": "one",
            "fields": {
                "account_key": str(account.pk),
                "source_reference": evidence["source_url"],
                "saved_bio": source["text"],
                "observed_at": source["observed_at"],
                "observed_handle": account.handle,
                "observation_kind": "account.profile_bio_text",
            },
        }
    )
    data["payload_digest"] = digest(
        {k: v for k, v in data.items() if k != "payload_digest"}
    )
    manifest, report = tmp_path / "packet.json", tmp_path / "report.json"
    manifest.write_text(json.dumps(data))
    monkeypatch.setattr(
        "core.management.commands.apply_saved_person_job_roles.verify_target",
        lambda *_: None,
    )
    kwargs = {
        "apply": True,
        "partial_saved_actions": True,
        "confirm_payload_digest": data["payload_digest"],
        "output": str(report),
    }
    call_command("apply_saved_person_job_roles", str(manifest), **kwargs)
    first = json.loads(report.read_text())["totals"]
    assert first["profiles_created"] == 1 and first["created"] == 1
    call_command("apply_saved_person_job_roles", str(manifest), **kwargs)
    second = json.loads(report.read_text())["totals"]
    assert second["profiles_reused"] == 1 and second["reused"] == 1
    assert AccountProfileSnapshot.objects.filter(account=account).count() == 1
    assert not StaffCollectionWork.objects.filter(person=person).exists()


def test_new_direct_account_person_can_save_own_post_role_without_enrollment(
    tmp_path, monkeypatch
):
    from core.models import Brand, StaffCollectionWork

    Brand.objects.get_or_create(
        nickname="deepseek", defaults={"display_name": "DeepSeek"}
    )
    item, actions, provenance = prepared_identity()
    item["key"] = item["native_id"]
    for action in actions:
        action["person_key"] = item["key"]
    observed = item["name_source"]["observed_at"]
    role_fields = {
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
    evidence = {
        "source_kind": "own_post",
        "source_post_ref": "post:9876543",
        "native_post_id": "9876543",
        "source_url": "https://x.com/savedwang/status/9876543",
        "evidence_text": "Current role at DeepSeek since 2026-08",
        "published_at": observed,
        "observed_at": observed,
    }
    item["affiliations"] = [
        {
            "local_id": "role:one",
            "action": "create",
            "fields": role_fields,
            "evidence": [evidence],
        }
    ]
    actions.append(
        {
            "table": "posts",
            "key": "9876543",
            "action": "compare_or_create",
            "person_keys": [item["key"]],
            "observations": [observed],
            "fields": {
                "native_post_id": "9876543",
                "source_reference": evidence["source_url"],
                "text": evidence["evidence_text"],
                "published_at": observed,
                "author_native_id": item["native_id"],
            },
        }
    )
    data = {
        "schema": "record-job-history-preview/v1",
        "selected_brand_ids": ["deepseek"],
        "people": [item],
        "record_actions": actions,
        "language_review_provenance": provenance,
    }
    data["payload_digest"] = digest(data)
    manifest, report = tmp_path / "packet.json", tmp_path / "report.json"
    manifest.write_text(json.dumps(data))
    monkeypatch.setattr(
        "core.management.commands.apply_saved_person_job_roles.verify_target",
        lambda *_: None,
    )
    kwargs = {
        "apply": True,
        "partial_saved_actions": True,
        "confirm_payload_digest": data["payload_digest"],
        "output": str(report),
    }
    call_command("apply_saved_person_job_roles", str(manifest), **kwargs)
    first = json.loads(report.read_text())["totals"]
    assert first["people_created"] == 1 and first["created"] == 1
    assert not StaffCollectionWork.objects.exists()
    call_command("apply_saved_person_job_roles", str(manifest), **kwargs)
    replay = json.loads(report.read_text())["totals"]
    assert replay["people_reused"] == 1 and replay["reused"] == 1
    assert not StaffCollectionWork.objects.exists()


def test_production_target_requires_separate_explicit_authorization(monkeypatch):
    from core.management.commands.apply_saved_person_job_roles import verify_target

    resource = "dpg-d9koekqjobas73fvjqng-a"
    monkeypatch.setenv("PUSHINWEIGHT_SAVE_PERSON_JOB_DB_RESOURCE", resource)
    monkeypatch.delenv("PUSHINWEIGHT_SAVE_PERSON_JOB_ALLOW_PRODUCTION", raising=False)
    payload = {"target": {"read_only": "on", "binding": {
        "database_name": "pushinweight_shadow", "database_host": resource,
        "resource": resource,
    }}}
    with pytest.raises(CommandError, match="Production application requires"):
        verify_target(payload, resource)


def test_production_confirmation_cannot_rebind_a_staging_packet(monkeypatch):
    from core.management.commands.apply_saved_person_job_roles import verify_target

    resource = "dpg-d9koekqjobas73fvjqng-a"
    monkeypatch.setenv("PUSHINWEIGHT_SAVE_PERSON_JOB_DB_RESOURCE", resource)
    monkeypatch.setenv("PUSHINWEIGHT_SAVE_PERSON_JOB_ALLOW_PRODUCTION", "1")
    payload = {"target": {"read_only": "on", "binding": {
        "database_name": "pushinweight_save_person_job",
        "database_host": "dpg-dbona93m8hqs73ef70mg-a",
        "resource": "dpg-dbona93m8hqs73ef70mg-a",
    }}}
    with pytest.raises(CommandError, match="not bound"):
        verify_target(payload, resource)


def test_production_guard_accepts_only_matching_confirmed_target(monkeypatch):
    from unittest.mock import MagicMock

    from core.management.commands import apply_saved_person_job_roles as command

    resource = command.PRODUCTION_RESOURCE
    monkeypatch.setenv("PUSHINWEIGHT_SAVE_PERSON_JOB_DB_RESOURCE", resource)
    monkeypatch.setenv("PUSHINWEIGHT_SAVE_PERSON_JOB_ALLOW_PRODUCTION", "1")
    monkeypatch.setitem(command.connection.settings_dict, "HOST", resource)
    cursor = MagicMock()
    cursor.__enter__.return_value.fetchone.return_value = ("pushinweight_shadow", "off")
    monkeypatch.setattr(command.connection, "cursor", lambda: cursor)
    schema = MagicMock()
    monkeypatch.setattr(command, "verify_import_schema", schema)
    command.verify_target({"target": {"read_only": "on", "binding": {
        "database_name": "pushinweight_shadow", "database_host": resource,
        "resource": resource,
    }}}, resource)
    schema.assert_called_once_with()


def test_import_schema_accepts_actual_branch_database():
    from core.management.commands.apply_saved_person_job_roles import (
        verify_import_schema,
    )

    verify_import_schema()


def test_import_schema_rejects_missing_columns(monkeypatch):
    from unittest.mock import MagicMock

    from core.management.commands import apply_saved_person_job_roles as command

    cursor = MagicMock()
    cursor.__enter__.return_value.fetchall.return_value = []
    monkeypatch.setattr(command.connection, "cursor", lambda: cursor)
    with pytest.raises(CommandError, match="Import schema is incompatible"):
        command.verify_import_schema()


def test_data_only_import_does_not_register_collection_callbacks(tmp_path, monkeypatch):
    from core.staff_assets import arrivals

    person, fields, source = setup_source()
    data = packet(person, fields, source)
    path = tmp_path / "packet.json"
    path.write_text(json.dumps(data))
    monkeypatch.setattr(
        "core.management.commands.apply_saved_person_job_roles.verify_target", lambda *_: None
    )
    registrations = []
    monkeypatch.setattr(arrivals, "register_person", registrations.append)
    call_command(
        "apply_saved_person_job_roles", str(path), apply=True,
        partial_saved_actions=True, confirm_payload_digest=data["payload_digest"],
        confirm_resource="test", output=str(tmp_path / "report.json"),
    )
    assert PersonBrandAffiliation.objects.filter(person=person).exists()
    assert registrations == []
    # The import must not leave ordinary writes suppressed in this process.
    role = PersonBrandAffiliation.objects.get(person=person)
    role.save()
    assert registrations == [person.pk]


def test_import_schema_checks_source_projection_columns(monkeypatch):
    from unittest.mock import MagicMock

    from core.management.commands import apply_saved_person_job_roles as command

    with command.connection.cursor() as cursor:
        cursor.execute(
            "SELECT table_name,column_name FROM information_schema.columns "
            "WHERE table_schema='public'"
        )
        columns = cursor.fetchall()
    required = ("account_profile_snapshots", "raw_profile_payload")
    assert required in columns
    cursor = MagicMock()
    cursor.__enter__.return_value.fetchall.return_value = [
        row for row in columns if row != required
    ]
    monkeypatch.setattr(command.connection, "cursor", lambda: cursor)
    with pytest.raises(CommandError, match="account_profile_snapshots.raw_profile_payload"):
        command.verify_import_schema()


def test_collection_registration_restored_after_person_database_error(monkeypatch):
    from types import SimpleNamespace

    from django.db import DatabaseError

    from core.management.commands import apply_saved_person_job_roles as command
    from core.staff_assets import arrivals

    def fail_identity(*args):
        raise DatabaseError("simulated database failure")

    monkeypatch.setattr(command, "apply_identity_records", fail_identity)
    result = command.process_person(
        {"native_id": "123", "identity": {"person_action": "create"}},
        {}, {}, [], None, ["deepseek"],
    )
    assert result["people_failed"] == 1
    registrations = []
    monkeypatch.setattr(arrivals, "register_person", registrations.append)
    arrivals.person_arrival(
        sender=PersonBrandAffiliation,
        instance=SimpleNamespace(
            person_id="normal-write",
            affiliation_type_reference=SimpleNamespace(code="employment"),
        ),
    )
    assert registrations == ["normal-write"]


def test_busy_shared_identity_lock_rolls_back_and_retries_cleanly():
    import psycopg
    from django.db import connection

    from core.management.commands.apply_saved_person_job_roles import process_person
    from core.models import Account, Person
    from core.staff_assets.job_history_identity import account_observation_person_ids

    item, actions, provenance = prepared_identity()
    item["key"] = item["native_id"]
    item["affiliations"] = []
    for action in actions:
        action["person_key"] = item["key"]
    # The production identity helper shares this database-local lock with staff work.
    with psycopg.connect(**connection.get_connection_params(), autocommit=True) as other:
        other.execute("SELECT pg_advisory_lock(71814001)")
        try:
            result = process_person(item, {}, {}, actions, provenance, ["deepseek"])
            assert result["people_failed"] == 1
            assert not Account.objects.filter(author_id=item["native_id"]).exists()
            assert not Person.objects.filter(
                pk=account_observation_person_ids(item["native_id"])[0]
            ).exists()
        finally:
            other.execute("SELECT pg_advisory_unlock(71814001)")
    retried = process_person(item, {}, {}, actions, provenance, ["deepseek"])
    assert retried["people_created"] == 1
    assert retried["names_created"] == 1


@pytest.mark.parametrize("second_status", ["Current", ""])
def test_coalesced_role_applies_complementary_sources_once(tmp_path, monkeypatch, second_status):
    from copy import deepcopy

    person, fields, source = setup_source()
    fields.update(title_raw="Engineer", team="Research")
    source["text"] = "Current Engineer at DeepSeek since 2026-08"
    data = packet(person, fields, source)
    second = deepcopy(data["people"][0]["affiliations"][0]["evidence"][0])
    second.update(
        native_post_id="123456790", source_post_ref="post:123456790",
        source_url="https://x.com/savedsource/status/123456790",
        evidence_text=f"{second_status} Research team at DeepSeek since 2026-08",
    )
    data["people"][0]["affiliations"][0]["evidence"].append(second)
    action = deepcopy(data["record_actions"][0])
    action.update(key="123456790")
    action["fields"].update(native_post_id="123456790", source_reference=second["source_url"], text=second["evidence_text"])
    data["record_actions"].append(action)
    data.pop("payload_digest")
    data["payload_digest"] = digest(data)
    manifest, report = tmp_path / "coalesced.json", tmp_path / "report.json"
    manifest.write_text(json.dumps(data))
    monkeypatch.setattr("core.management.commands.apply_saved_person_job_roles.verify_target", lambda *_: None)
    for _ in range(2):
        call_command("apply_saved_person_job_roles", str(manifest), apply=True,
            partial_saved_actions=True, confirm_payload_digest=data["payload_digest"], output=str(report))
        outcome = json.loads(report.read_text())["people"][0]
        assert outcome["held"] == 0, outcome
    role = PersonBrandAffiliation.objects.get(person=person)
    assert (role.title_raw, role.team, role.status) == ("Engineer", "Research", "current")
    assert role.evidence.count() == 2


def test_unwritable_receipt_stops_before_applying_first_person(tmp_path, monkeypatch):
    person, fields, source = setup_source()
    data = packet(person, fields, source)
    path = tmp_path / "packet.json"
    path.write_text(json.dumps(data))
    monkeypatch.setattr("core.management.commands.apply_saved_person_job_roles.verify_target", lambda *_: None)
    def fail(*_):
        raise OSError("Receipt destination unavailable")
    monkeypatch.setattr("core.management.commands.apply_saved_person_job_roles.write_report", fail)
    with pytest.raises(CommandError, match="destination unavailable"):
        call_command("apply_saved_person_job_roles", str(path), apply=True,
            partial_saved_actions=True, confirm_payload_digest=data["payload_digest"], output=str(tmp_path / "report.json"))
    assert not PersonBrandAffiliation.objects.filter(person=person).exists()
    assert not Post.objects.filter(pk=source["post_id"]).exists()
