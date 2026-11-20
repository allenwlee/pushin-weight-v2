"""Saved-source preparation must be useful without allowing an import."""

from copy import deepcopy

import pytest

from core.staff_assets.job_history import prepare_job_history


def inventory():
    return {
        "database": "staging-fixture",
        "captured_at": "2026-11-07T09:00:00+09:00",
        "read_only": "on",
        "accounts": [],
        "people": [],
        "person_accounts": [],
        "names": [],
        "affiliations": [],
        "evidence": [],
        "brands": [{"nickname": "anthropic", "display_name": "Anthropic"}],
        "companies": [{"nickname": "anthropic"}],
        "company_labels": [{"company_id": "anthropic", "label": "Anthropic"}],
        "brand_companies": [{"brand_id": "anthropic", "company_id": "anthropic"}],
    }


def person(**changes):
    return {
        "native_id": "123",
        "handle": "testperson",
        "names": ["Test Person"],
        "name_source": {
            "source_kind": "saved_account_name",
            "observed_at": "2026-11-06T12:00:00Z",
        },
        "outcome": "supported",
        "note": "",
        "discovery_brands": ["anthropic"],
        "sources": [
            {
                "key": "bio:0",
                "kind": "saved_bio",
                "text": "Claude Code @anthropicai. Previously OpenAI, left August 2026.",
                "observations": [
                    {"observed": "2026-11-06T12:00:00Z", "handle": "testperson"}
                ],
            }
        ],
        "roles": [
            {
                "organization": "Anthropic",
                "status": "current",
                "affiliation_type": "employment",
                "team": "Claude Code",
                "title_raw": None,
                "source_keys": ["bio:0"],
            }
        ],
        **changes,
    }


def test_preview_preserves_fields_and_existing_chain_without_writes(django_db_blocker):
    source, state = person(), inventory()
    original = deepcopy((source, state))
    with django_db_blocker.block():
        result = prepare_job_history([source], state)
    assert (source, state) == original
    row = result["people"][0]
    assert row["identity"]["person_action"] == "create"
    role = row["affiliations"][0]
    assert role["fields"]["team"] == "Claude Code"
    assert role["fields"]["title_raw"] is None
    assert role["chain"]["brand_id"] == "anthropic"
    assert role["chain"]["company_ids"] == ["anthropic"]
    assert "company_id" not in role["fields"]
    assert "technical_involvement" not in role["fields"]
    assert role["evidence"][0]["evidence_text"] == source["sources"][0]["text"]
    assert result["database_writes"] == 0


def test_missing_chain_records_are_shared_not_duplicated():
    state = inventory()
    row = person()
    row["roles"][0]["organization"] = "Example Lab"
    second = deepcopy(row)
    second.update(native_id="456", handle="second")
    result = prepare_job_history([row, second], state)
    creates = [a for a in result["record_actions"] if a["action"] == "create"]
    for table in ("brands", "companies", "brands_companies"):
        assert sum(a["table"] == table for a in creates) == 1


def test_handle_owned_by_another_native_identity_is_held():
    state = inventory()
    state["accounts"].append({"account_key": "other-account", "author_id": "456", "handle": "testperson"})
    result = prepare_job_history([person()], state)
    identity = result["people"][0]["identity"]
    assert identity["account_action"] == "hold"
    assert identity["person_action"] == "hold"
    assert any("different stored X identity" in issue for issue in result["people"][0]["issues"])


def test_single_source_summary_holds_unsupported_date():
    row = person()
    row["sources"][0]["text"] = "I joined OtherCorp in June."
    row["roles"][0].update(organization="OtherCorp", team=None, status="unknown", start_date="2026-06", start_date_precision="month")
    result = prepare_job_history([row], inventory(), selected_brands=["anthropic"])
    summaries = result["people"][0]["biography_summaries"]
    assert summaries and all(summary["action"] == "hold" for summary in summaries)


def test_parent_company_does_not_imply_model_team():
    state = inventory()
    state["brands"].append({"nickname": "qwen", "display_name": "Qwen"})
    state["companies"].append({"nickname": "alibaba"})
    state["brand_companies"].append({"brand_id": "qwen", "company_id": "alibaba"})
    row = person()
    row["roles"][0].update(organization="Alibaba", team=None)
    role = prepare_job_history([row], state)["people"][0]["affiliations"][0]
    assert role["chain"]["brand_id"] != "qwen"
    assert role["chain"]["company_ids"] == ["alibaba"]
    assert role["fields"]["team"] is None


def test_multiple_company_links_are_visible_and_held():
    state = inventory()
    state["companies"].append({"nickname": "other"})
    state["brand_companies"].append({"brand_id": "anthropic", "company_id": "other"})
    row = prepare_job_history([person()], state)["people"][0]
    assert row["affiliations"][0]["chain"]["company_ids"] == ["anthropic", "other"]
    assert row["outcome"] == "unresolved"


@pytest.mark.parametrize(
    "value,precision", [("2026-02-30", "day"), ("20260800", "month"), (None, "month")]
)
def test_bad_dates_are_rejected(value, precision):
    row = person()
    row["roles"][0].update(end_date=value, end_date_precision=precision)
    with pytest.raises(ValueError):
        prepare_job_history([row], inventory())


def test_month_precision_and_source_times_remain_separate():
    row = person()
    row["roles"][0].update(
        status="former", end_date="2026-08", end_date_precision="month"
    )
    role = prepare_job_history([row], inventory())["people"][0]["affiliations"][0]
    assert role["fields"]["end_date"] == "2026-08"
    assert role["end_display"] == "20260800"
    assert role["evidence"][0]["observed_at"] == "2026-11-06T12:00:00+00:00"


@pytest.mark.parametrize(
    "change", ["unknown_field", "foreign_source", "duplicate_identity"]
)
def test_invalid_inputs_fail_before_rendering(change):
    rows = [person()]
    if change == "unknown_field":
        rows[0]["roles"][0]["company_id"] = "anthropic"
    elif change == "foreign_source":
        rows[0]["roles"][0]["source_keys"] = ["other-person:0"]
    else:
        rows.append(person(handle="renamed"))
    with pytest.raises(ValueError):
        prepare_job_history(rows, inventory())


def test_missing_native_identity_is_preserved_and_held():
    result = prepare_job_history([person(native_id=None)], inventory())
    assert len(result["people"]) == 1
    assert result["people"][0]["outcome"] == "unresolved"
    assert result["people"][0]["identity"]["account_action"] == "resolve"


def test_two_sources_share_role_but_preserve_observation_times():
    row = person()
    source = deepcopy(row["sources"][0])
    source["key"] = "bio:1"
    source["observations"][0]["observed"] = "2026-11-05T12:00:00Z"
    row["sources"].append(source)
    role = deepcopy(row["roles"][0])
    role["source_keys"] = ["bio:1"]
    row["roles"].append(role)
    result = prepare_job_history([row], inventory())
    roles = result["people"][0]["affiliations"]
    assert len(roles) == 1
    assert len(roles[0]["evidence"]) == 2
    assert (
        result["payload_digest"]
        == prepare_job_history([row], inventory())["payload_digest"]
    )


def test_shared_manifest_route_and_real_command_do_not_connect(
    tmp_path, django_db_blocker
):
    import json

    from django.core.management import call_command

    from core.staff_assets.manifest import import_manifest

    manifest = {"schema": "record-job-history/v1", "people": [person()]}
    source = tmp_path / "manifest.json"
    target = tmp_path / "inventory.json"
    output = tmp_path / "preview.html"
    source.write_text(json.dumps(manifest))
    target.write_text(json.dumps(inventory()))
    with django_db_blocker.block():
        with pytest.raises(ValueError, match="preview-only"):
            import_manifest(manifest, apply=True, inventory=inventory())
        call_command(
            "record_job_history", str(source), inventory=str(target), output=str(output)
        )
    prepared = json.loads(output.with_suffix(".json").read_text())
    assert prepared["payload_digest"] in output.read_text()
    assert "Claude Code" in output.read_text()
    assert "Claude Code" in output.with_suffix(".csv").read_text()
    assert prepared["database_writes"] == 0



def test_save_person_job_command_preserves_legacy_preview(tmp_path, django_db_blocker):
    import json

    from django.core.management import call_command

    source = tmp_path / "manifest.json"
    target = tmp_path / "inventory.json"
    source.write_text(json.dumps({"schema": "record-job-history/v1", "people": [person()]}))
    target.write_text(json.dumps(inventory()))
    with django_db_blocker.block():
        for command in ("record_job_history", "save_person_job"):
            call_command(command, str(source), inventory=str(target), output=str(tmp_path / f"{command}.html"))
    old = json.loads((tmp_path / "record_job_history.json").read_text())
    new = json.loads((tmp_path / "save_person_job.json").read_text())
    assert new == old


def test_existing_manifest_preview_contract_is_unchanged(
    monkeypatch, django_db_blocker
):
    from core.staff_assets import manifest

    monkeypatch.setattr(manifest, "resolve_person", lambda record: (None, None))
    old = {
        "schema": "staff-intake/v1",
        "people": [
            {
                "source_key": "old:1",
                "display_name": "Existing caller",
                "eligibility": "staff",
                "observed_at": "2026-11-06T12:00:00Z",
                "affiliations": [
                    {
                        "brand_id": "anthropic",
                        "source_url": "https://example.com/bio",
                        "evidence_text": "Works at Anthropic",
                    }
                ],
            }
        ],
    }
    with django_db_blocker.block():
        result = manifest.import_manifest(old)
    assert result == {
        "applied": False,
        "counts": {"create": 1},
        "records": [{"source_key": "old:1", "action": "create", "person_id": None}],
        "source_outcomes": [],
    }


def test_contract_role_remains_contractor():
    row = person()
    row["roles"][0].update(affiliation_type="contractor", employment_type="contract")
    role = prepare_job_history([row], inventory())["people"][0]["affiliations"][0]
    assert role["fields"]["affiliation_type"] == "contractor"
    assert role["fields"]["employment_type"] == "contract"


def test_existing_account_observation_identity_is_reused_without_promoting_link():
    from core.person_identity import account_observation_person_ids

    state = inventory()
    pk = str(account_observation_person_ids("123")[0])
    state["accounts"] = [
        {"account_key": "account:1", "author_id": "123", "handle": "testperson"}
    ]
    state["people"] = [{"id": pk, "merged_into_id": None}]
    state["person_accounts"] = [
        {"account_key": "account:1", "person_id": pk, "resolution_status": "pending"}
    ]
    identity = prepare_job_history([person()], state)["people"][0]["identity"]
    assert identity["person_action"] == "reuse"
    assert identity["person_id"] == pk
    assert state["person_accounts"][0]["resolution_status"] == "pending"


def test_html_escapes_source_text_and_csv_does_not_execute_formulae():
    from core.staff_assets.job_history_preview import render_csv, render_html

    row = person()
    row["sources"][0]["text"] = '<script>alert("source")</script>'
    row["names"] = ["=FORMULA()"]
    result = prepare_job_history([row], inventory())
    html = render_html(result)
    assert '<script>alert("source")</script>' not in html
    assert "&lt;script&gt;" in html
    assert "'=FORMULA()" in render_csv(result)


def test_displayed_name_is_the_prepared_name_not_an_unapplied_profile_override():
    from core.staff_assets.job_history_preview import render_html

    row = person()
    row["name_source"] = {
        "source_kind": "saved_account_name",
        "observed_at": "2026-11-06T12:00:00Z",
    }
    result = prepare_job_history([row], inventory())
    html = render_html(
        result, profiles={"testperson": {"name": "Unprepared different name"}}
    )
    assert "Unprepared different name" not in html
    assert "Test Person" in html
    name_actions = [a for a in result["record_actions"] if a["table"] == "people_names"]
    assert name_actions[0]["fields"]["full_name"] == "Test Person"


@pytest.mark.parametrize(
    "changed",
    [
        {"affiliation_type": "other"},
        {"affiliation_type": "contractor"},
        {"review_status": "rejected"},
        {"superseded_at": "2026-11-06T12:00:00Z"},
    ],
)
def test_existing_nonmatching_or_retired_claim_is_never_enriched(changed):
    from core.person_identity import account_observation_person_ids

    row, state = person(), inventory()
    pk = str(account_observation_person_ids("123")[0])
    state["people"] = [{"id": pk, "merged_into_id": None}]
    state["affiliations"] = [
        {
            "id": 1,
            "person_id": pk,
            "brand_id": "anthropic",
            "affiliation_type": "employment",
            "status": "current",
            "team": "Claude Code",
            "review_status": "pending",
            **changed,
        }
    ]
    prepared = prepare_job_history([row], state)["people"][0]
    role = prepared["affiliations"][0]
    assert role["existing_id"] is None
    assert role["action"] not in {"enrich", "add_evidence"}
    assert prepared["existing_affiliations"][0]["id"] == 1


def test_existing_person_does_not_imply_existing_account_link():
    from core.person_identity import account_observation_person_ids

    state = inventory()
    state["people"] = [{"id": str(account_observation_person_ids("123")[0])}]
    state["accounts"] = [
        {"account_key": "account:1", "author_id": "123", "handle": "testperson"}
    ]
    identity = prepare_job_history([person()], state)["people"][0]["identity"]
    assert identity["person_action"] == "reuse"
    assert identity["person_account_action"] == "create"


@pytest.mark.parametrize(
    "bad",
    [
        "name_string",
        "empty_evidence",
        "missing_observation",
        "missing_name_observation",
        "integer_identity",
    ],
)
def test_malformed_identity_names_and_evidence_are_rejected(bad):
    row = person()
    if bad == "name_string":
        row["names"] = "Test Person"
    elif bad == "empty_evidence":
        row["sources"][0]["text"] = "  "
    elif bad == "missing_observation":
        row["sources"][0]["observations"] = []
    elif bad == "missing_name_observation":
        row["name_source"]["observed_at"] = None
    else:
        row["native_id"] = 123
    with pytest.raises(ValueError):
        prepare_job_history([row], inventory())


@pytest.mark.parametrize("url", ["javascript:alert(1)", "data:text/html,hello"])
def test_untrusted_source_urls_render_as_text_not_executable_anchors(url):
    from core.staff_assets.job_history_preview import render_html

    row = person()
    row["sources"][0]["url"] = url
    result = prepare_job_history([row], inventory())
    result["people"][0]["existing_affiliations"] = [
        {"id": 1, "evidence": [{"source_url": url, "evidence_text": "Saved text"}]}
    ]
    html = render_html(result)
    assert 'href="' + url not in html
    assert url in html


def test_same_role_with_more_detail_is_one_affiliation_with_both_sources():
    row = person()
    row["roles"][0]["title_raw"] = "Engineer"
    second = deepcopy(row["roles"][0])
    second.update(team=None, source_keys=["bio:1"])
    row["roles"].append(second)
    source = deepcopy(row["sources"][0])
    source.update(key="bio:1", text="Engineer at Anthropic")
    row["sources"].append(source)
    roles = prepare_job_history([row], inventory())["people"][0]["affiliations"]
    assert len(roles) == 1
    assert roles[0]["fields"]["team"] == "Claude Code"
    assert roles[0]["source_keys"] == ["bio:0", "bio:1"]
    assert len(roles[0]["evidence"]) == 2


def test_undated_role_does_not_bridge_two_distinct_employment_spells():
    row = person()
    row["roles"][0].update(status="former", title_raw="Engineer")
    for year in ("2020", "2025"):
        role = deepcopy(row["roles"][0])
        role.update(start_date=year, start_date_precision="year")
        row["roles"].append(role)
    result = prepare_job_history([row], inventory())["people"][0]
    assert len(result["affiliations"]) == 3
    assert result["outcome"] == "unresolved"


def test_unused_source_retains_visible_link_and_observation_time():
    from core.staff_assets.job_history_preview import render_html

    row = person(roles=[], outcome="unresolved")
    html = render_html(prepare_job_history([row], inventory()))
    assert "Other saved evidence" in html
    assert "2026-11-06 21:00 JST" in html
    assert 'href="https://x.com/testperson"' in html


def test_low_certainty_present_keeps_null_end_date_and_existing_review_note():
    from core.staff_assets.job_history_preview import render_html

    row = person()
    baseline = prepare_job_history([row], inventory())
    row["roles"][0]["review_note"] = "Continuing employment assumed; certainty: low."
    result = prepare_job_history([row], inventory())
    role = result["people"][0]["affiliations"][0]
    assert role["fields"]["status"] == "current"
    assert role["fields"]["end_date"] is None
    assert role["fields"]["end_date_precision"] == "unknown"
    assert role["fields"]["confidence"] is None
    assert role["fields"]["review_note"] == row["roles"][0]["review_note"]
    assert role["local_id"] == baseline["people"][0]["affiliations"][0]["local_id"]
    assert "Present (low certainty)" in render_html(result)


def language_assignment(native_ids=None):
    from core.person_names import digest

    members = native_ids or ["123"]
    return {
        "schema": "record-job-history-primary-language/v1",
        "value": "zh-Hans",
        "origin": "owner_override",
        "decision_id": "owner-language-test",
        "authorized_by": "Allen",
        "authorized_at": "2026-11-08T22:00:00+09:00",
        "instruction": "Assign this selected cohort to zh-Hans; uncertainty accepted.",
        "evidence_reference": "saved-reviewed-cohort.json",
        "evidence_sha256": "a" * 64,
        "expected_count": len(members),
        "native_ids": members,
        "cohort_digest": digest(sorted(members)),
    }


def test_language_override_targets_native_id_and_preserves_other_records(django_db_blocker):
    selected = person(handle="renamed_handle", roles=[], outcome="unresolved")
    other = person(native_id="456", handle="other")
    people, state, decision = [selected, other], inventory(), language_assignment()
    original = deepcopy((people, state, decision))
    with django_db_blocker.block():
        baseline = prepare_job_history(people, state)
        result = prepare_job_history(people, state, primary_language_assignment=decision)
        assert result == prepare_job_history(people, state, primary_language_assignment=decision)
    assert (people, state, decision) == original
    assert result["people"][0]["person_fields"] == {"primary_language": "zh-Hans"}
    assert result["people"][0]["outcome"] == "unresolved"
    assert result["people"][1] == baseline["people"][1]
    assert result["affiliation_count"] == baseline["affiliation_count"]
    assert result["primary_language_assignment_count"] == 1
    assert result["primary_language_assignment"] == decision
    assert result["payload_digest"] != baseline["payload_digest"]
    assert [a for a in result["record_actions"] if a["table"] != "people"] == [
        a for a in baseline["record_actions"] if a["table"] != "people"
    ]
    action = next(a for a in result["record_actions"] if a["table"] == "people" and a["person_key"] == "123")
    assert action["action"] == "create"
    assert action["fields"] == {"primary_language": "zh-Hans"}
    assert result["database_writes"] == 0 and result["apply_available"] is False


@pytest.mark.parametrize("prior,expected", [(None, "update"), ("en", "update"), ("zh-Hans", "retain")])
def test_language_override_reuses_person_and_discloses_existing_value(prior, expected):
    from core.person_identity import account_observation_person_ids

    state = inventory()
    pk = str(account_observation_person_ids("123")[0])
    state["people"] = [{"id": pk, "primary_language": prior}]
    result = prepare_job_history([person()], state, primary_language_assignment=language_assignment())
    p = result["people"][0]
    assert p["identity"]["person_action"] == "reuse"
    assert p["primary_language_assignment"]["previous_value"] == prior
    assert p["primary_language_assignment"]["previous_value_known"] is True
    action = next(a for a in result["record_actions"] if a["table"] == "people")
    assert action["key"] == pk and action["action"] == expected
    assert action["fields"] == {"primary_language": "zh-Hans"}


def test_language_override_does_not_bypass_an_identity_conflict():
    state = inventory()
    state["accounts"] = [{"account_key": "account:1", "author_id": "123", "handle": "testperson"}]
    state["person_accounts"] = [{"account_key": "account:1", "person_id": "unconfirmed", "resolution_status": "pending"}]
    result = prepare_job_history([person()], state, primary_language_assignment=language_assignment())
    assert result["people"][0]["person_fields"] == {"primary_language": "zh-Hans"}
    action = next(a for a in result["record_actions"] if a["table"] == "people")
    assert action["action"] == "hold"


@pytest.mark.parametrize("change", [
    {"native_ids": ["123", "123"], "expected_count": 2},
    {"native_ids": [123]},
    {"expected_count": True},
    {"expected_count": 2},
    {"value": "en"},
    {"origin": "inference"},
    {"authorized_by": ""},
    {"authorized_at": "2026-11-08"},
    {"instruction": ""},
    {"cohort_digest": "b" * 64},
    {"evidence_sha256": "invalid"},
    {"unrecognized_field": True},
])
def test_invalid_language_decision_is_rejected(change):
    decision = {**language_assignment(), **change}
    with pytest.raises((ValueError, TypeError)):
        prepare_job_history([person()], inventory(), primary_language_assignment=decision)


def test_language_override_rejects_absent_native_identity_even_if_handle_matches():
    with pytest.raises(ValueError, match="identities absent"):
        prepare_job_history([person(native_id="456")], inventory(), primary_language_assignment=language_assignment())


def test_language_override_real_command_exports_exact_assignments(tmp_path, django_db_blocker):
    import csv
    import json

    from django.core.management import call_command

    from core.staff_assets.manifest import import_manifest, load_manifest

    decision = language_assignment()
    manifest = {
        "schema": "record-job-history/v1",
        "people": [person(), person(native_id="456", handle="other")],
        "primary_language_assignment": decision,
    }
    source, target, output = (tmp_path / n for n in ("manifest.json", "inventory.json", "preview.html"))
    source.write_text(json.dumps(manifest))
    target.write_text(json.dumps(inventory()))
    with django_db_blocker.block():
        with pytest.raises(ValueError, match="preview-only"):
            import_manifest(load_manifest(source), apply=True, inventory=inventory())
        call_command("record_job_history", str(source), inventory=str(target), output=str(output))
    result = json.loads(output.with_suffix(".json").read_text())
    assert result["primary_language_assignment"] == decision
    assert result["primary_language_assignment_count"] == 1
    assert result["database_writes"] == 0
    html = output.read_text()
    assert html.count('class="primary-language"') == 1
    assert "people.primary_language: Unset → zh-Hans" in html
    assert "Owner override" in html and decision["instruction"] in html
    rows = list(csv.DictReader(output.with_suffix(".csv").open()))
    assert rows[0]["primary_language"] == "zh-Hans"
    assert rows[0]["primary_language_origin"] == "owner_override"
    assert rows[1]["primary_language"] == ""
