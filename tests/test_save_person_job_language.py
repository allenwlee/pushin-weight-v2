"""The fresh assessment is independent of historic cohort classifications."""

import pytest

from core.staff_assets.job_history_names import assess_fresh, load_lexicon


def test_fresh_name_signal_does_not_require_employer():
    person = {
        "native_id": "example",
        "handle": "hallo_sin",
        "names": ["成熟小老头"],
        "sources": [],
        "roles": [],
    }
    result = assess_fresh(person, load_lexicon())
    assert result["outcome"] == "assign"
    assert any(item["quote"] == "成熟小老头" for item in result["evidence"])


def test_real_command_fresh_assessment_ignores_old_assignment(
    tmp_path, django_db_blocker
):
    import json

    from django.core.management import call_command

    from tests.test_record_job_history import inventory, person

    source = tmp_path / "manifest.json"
    target = tmp_path / "inventory.json"
    output = tmp_path / "preview.html"
    row = person(names=["成熟小老头"], handle="hallo_sin")
    source.write_text(json.dumps({"schema": "record-job-history/v1", "people": [row]}))
    target.write_text(json.dumps(inventory()))
    with django_db_blocker.block():
        call_command(
            "save_person_job",
            str(source),
            inventory=str(target),
            output=str(output),
            fresh_language=True,
        )
    prepared = json.loads(output.with_suffix(".json").read_text())
    assert prepared["people"][0]["language_assessment"]["outcome"] == "assign"
    assert prepared["database_writes"] == 0


def test_scoped_history_keeps_other_employers_as_sourced_text():
    from core.staff_assets.job_history import prepare_job_history
    from tests.test_record_job_history import inventory, person

    row = person()
    row["sources"][0]["text"] += " Previously an Engineer at Acme."
    row["roles"].append(
        {
            "organization": "Acme",
            "status": "former",
            "affiliation_type": "employment",
            "title_raw": "Engineer",
            "source_keys": ["bio:0"],
        }
    )
    result = prepare_job_history([row], inventory(), selected_brands={"anthropic"})
    prepared = result["people"][0]
    assert len(prepared["affiliations"]) == 1
    assert "Acme" in prepared["biography_summaries"][0]["text"]
    assert (
        prepared["biography_summaries"][0]["source_reference"]
        == "https://x.com/testperson"
    )
    assert not any(
        a["table"] in {"brands", "companies", "brands_companies"}
        and "acme" in a["key"].lower()
        for a in result["record_actions"]
    )


def test_unresolved_identity_holds_biography_summary():
    from core.staff_assets.job_history import prepare_job_history
    from tests.test_record_job_history import inventory, person

    row = person(native_id=None)
    row["roles"][0]["organization"] = "Acme"
    result = prepare_job_history([row], inventory(), selected_brands={"anthropic"})
    assert result["people"][0]["biography_summaries"][0]["action"] == "hold"


def test_unknown_selected_brand_is_held_without_inventing_records():
    from core.staff_assets.job_history import prepare_job_history
    from tests.test_record_job_history import inventory, person

    row = person()
    row["roles"][0]["organization"] = "Google Brain"
    result = prepare_job_history(
        [row],
        inventory(),
        aliases={"googlebrain": {"brand_id": "google-brain", "company_id": "google"}},
        selected_brands={"google-brain"},
    )
    assert result["people"][0]["held_roles"][0]["organization"] == "Google Brain"
    assert not any(
        a["table"] in {"brands", "companies", "brands_companies"}
        for a in result["record_actions"]
    )


def test_fresh_proposal_respects_owner_exclusion():
    from core.staff_assets.job_history import prepare_job_history
    from tests.test_record_job_history import inventory, person

    row = person(names=["成熟小老头"])
    result = prepare_job_history(
        [row],
        inventory(),
        fresh_language=True,
        language_exclusions={"123": "owner decision"},
    )
    assert result["people"][0]["language_assessment"]["outcome"] == "assign"
    assert result["people"][0]["language_proposal"]["action"] == "excluded"
    assert "person_fields" not in result["people"][0]


def test_review_exclusions_reject_stale_evidence():
    import pytest

    from core.staff_assets.job_history_names import validate_review_exclusions
    from tests.test_record_job_history import person

    review = {
        "schema": "record-job-history-language-review/v1",
        "owner_exclusions": {
            "123": {
                "handle": "testperson",
                "evidence": "not in saved sources",
                "reason": "owner exclusion",
            }
        },
    }
    with pytest.raises(ValueError, match="evidence"):
        validate_review_exclusions(review, [person()])


def test_review_rejects_unknown_exclusion_fields():
    import pytest

    from core.staff_assets.job_history_names import validate_review_exclusions
    from tests.test_record_job_history import person

    review = {
        "schema": "record-job-history-language-review/v1",
        "owner_exclusions": {
            "123": {
                "handle": "testperson",
                "evidence": "Test Person",
                "reason": "owner exclusion",
                "unexpected": True,
            }
        },
    }
    with pytest.raises(ValueError, match="Invalid language-review exclusion"):
        validate_review_exclusions(review, [person()])


def test_missing_evidence_clock_is_visible_and_held():
    from core.staff_assets.job_history import prepare_job_history
    from tests.test_record_job_history import inventory, person

    row = person()
    row["sources"][0]["observations"] = [{"observed": None, "handle": "testperson"}]
    result = prepare_job_history([row], inventory(), selected_brands={"anthropic"})
    assert result["people"][0]["affiliations"][0]["action"] == "hold"
    assert result["people"][0]["sources"][0]["text"] == row["sources"][0]["text"]
    assert any("observation time" in issue for issue in result["people"][0]["issues"])


def test_saved_post_prepares_source_reference_without_database_access():
    from core.staff_assets.job_history import prepare_job_history
    from tests.test_record_job_history import inventory, person

    row = person()
    row["sources"].append(
        {
            "key": "post:0",
            "kind": "own_post",
            "text": "Joined Anthropic in July",
            "tweet_id": "222",
            "published_at": "2026-07-08T00:00:00Z",
            "observed_at": "2026-07-09T00:00:00Z",
        }
    )
    row["roles"][0]["source_keys"].append("post:0")
    result = prepare_job_history([row], inventory(), selected_brands={"anthropic"})
    post = next(a for a in result["record_actions"] if a["table"] == "posts")
    assert post["key"] == "222"
    evidence = result["people"][0]["affiliations"][0]["evidence"]
    assert (
        next(e for e in evidence if e["source_key"] == "post:0")["source_post_ref"]
        == "post:222"
    )
    assert result["database_writes"] == 0


def test_repeated_post_observations_share_one_proposed_post():
    from core.staff_assets.job_history import prepare_job_history
    from tests.test_record_job_history import inventory, person

    row = person()
    row["sources"].append(
        {
            "key": "post:0",
            "kind": "own_post",
            "text": "Joined Anthropic",
            "tweet_id": "222",
            "published_at": "2026-07-08T00:00:00Z",
            "observations": [
                {"observed": "2026-07-09T00:00:00Z"},
                {"observed": "2026-07-10T00:00:00Z"},
            ],
        }
    )
    result = prepare_job_history([row], inventory(), selected_brands={"anthropic"})
    posts = [a for a in result["record_actions"] if a["table"] == "posts"]
    assert len(posts) == 1
    assert len(posts[0]["observations"]) == 2


@pytest.mark.parametrize(
    "post_id,url",
    [
        ("not-numeric", "https://x.com/testperson/status/not-numeric"),
        ("222", "https://x.com/testperson/status/333"),
    ],
)
def test_invalid_or_mismatched_post_reference_is_held(post_id, url):
    from core.staff_assets.job_history import prepare_job_history
    from tests.test_record_job_history import inventory, person

    row = person()
    row["sources"].append(
        {
            "key": "post:0",
            "kind": "own_post",
            "text": "Joined Anthropic",
            "tweet_id": post_id,
            "url": url,
            "author_handle": "testperson",
            "published_at": "2026-07-08T00:00:00Z",
            "observed_at": "2026-07-09T00:00:00Z",
        }
    )
    result = prepare_job_history([row], inventory(), selected_brands={"anthropic"})
    post = next(a for a in result["record_actions"] if a["table"] == "posts")
    assert post["action"] == "hold"


def test_conflicting_post_source_holds_dependent_affiliation():
    from core.staff_assets.job_history import prepare_job_history
    from tests.test_record_job_history import inventory, person

    row = person()
    for key, body in [("post:0", "Joined Anthropic"), ("post:1", "Left Anthropic")]:
        row["sources"].append(
            {
                "key": key,
                "kind": "own_post",
                "text": body,
                "tweet_id": "222",
                "published_at": "2026-07-08T00:00:00Z",
                "observed_at": "2026-07-09T00:00:00Z",
            }
        )
        row["roles"][0]["source_keys"].append(key)
    result = prepare_job_history([row], inventory(), selected_brands={"anthropic"})
    assert (
        next(a for a in result["record_actions"] if a["table"] == "posts")["action"]
        == "hold"
    )
    assert result["people"][0]["affiliations"][0]["action"] == "hold"
    assert result["people"][0]["outcome"] == "unresolved"


def test_conflicting_post_source_holds_biography_summary():
    from core.staff_assets.job_history import prepare_job_history
    from tests.test_record_job_history import inventory, person

    row = person()
    row["roles"][0]["organization"] = "Acme"
    for key, body in [("post:0", "Worked at Acme"), ("post:1", "Never worked at Acme")]:
        row["sources"].append(
            {
                "key": key,
                "kind": "own_post",
                "text": body,
                "tweet_id": "222",
                "published_at": "2026-07-08T00:00:00Z",
                "observed_at": "2026-07-09T00:00:00Z",
            }
        )
    row["roles"][0]["source_keys"] = ["post:0"]
    result = prepare_job_history([row], inventory(), selected_brands={"anthropic"})
    assert result["people"][0]["biography_summaries"][0]["action"] == "hold"


def test_post_native_id_variants_keep_the_original_identity():
    from core.staff_assets.job_history import prepare_job_history
    from tests.test_record_job_history import inventory, person

    row = person()
    row["sources"].append(
        {
            "key": "post:0",
            "kind": "own_post",
            "text": "Joined Anthropic",
            "native_post_id": "333",
            "published_at": "2026-07-08T00:00:00Z",
            "observed_at": "2026-07-09T00:00:00Z",
        }
    )
    row["roles"][0]["source_keys"].append("post:0")
    result = prepare_job_history([row], inventory(), selected_brands={"anthropic"})
    assert (
        next(a for a in result["record_actions"] if a["table"] == "posts")["key"]
        == "333"
    )


def test_excluded_person_never_gets_fresh_language_write_proposal():
    from core.staff_assets.job_history import prepare_job_history
    from tests.test_record_job_history import inventory, person

    row = person(names=["成熟小老头"], outcome="excluded")
    result = prepare_job_history(
        [row], inventory(), fresh_language=True, language_exclusions={}
    )
    assert "person_fields" not in result["people"][0]


def test_command_rejects_incomplete_owner_review_packet(tmp_path, django_db_blocker):
    import json

    import pytest
    from django.core.management import call_command
    from django.core.management.base import CommandError

    from tests.test_record_job_history import inventory, person

    source = tmp_path / "manifest.json"
    target = tmp_path / "inventory.json"
    review = tmp_path / "review.json"
    source.write_text(
        json.dumps({"schema": "record-job-history/v1", "people": [person()]})
    )
    target.write_text(json.dumps(inventory()))
    review.write_text(
        json.dumps(
            {"schema": "record-job-history-language-review/v1", "owner_exclusions": {}}
        )
    )
    with django_db_blocker.block(), pytest.raises(CommandError, match="review"):
        call_command(
            "save_person_job",
            str(source),
            inventory=str(target),
            output=str(tmp_path / "preview.html"),
            fresh_language=True,
            language_review=str(review),
        )


def test_mismatched_post_author_is_held():
    from core.staff_assets.job_history import prepare_job_history
    from tests.test_record_job_history import inventory, person

    row = person()
    row["sources"].append(
        {
            "key": "post:0",
            "kind": "own_post",
            "text": "Joined Anthropic",
            "tweet_id": "222",
            "author_handle": "different",
            "published_at": "2026-07-08T00:00:00Z",
            "observed_at": "2026-07-09T00:00:00Z",
        }
    )
    row["roles"][0]["source_keys"].append("post:0")
    result = prepare_job_history([row], inventory(), selected_brands={"anthropic"})
    assert (
        next(a for a in result["record_actions"] if a["table"] == "posts")["action"]
        == "hold"
    )
    assert result["people"][0]["affiliations"][0]["action"] == "hold"


def test_language_review_rejects_duplicate_json_keys(tmp_path, django_db_blocker):
    import json

    import pytest
    from django.core.management import call_command
    from django.core.management.base import CommandError

    from tests.test_record_job_history import inventory, person

    source, target, review = (
        tmp_path / name for name in ("manifest.json", "inventory.json", "review.json")
    )
    source.write_text(
        json.dumps({"schema": "record-job-history/v1", "people": [person()]})
    )
    target.write_text(json.dumps(inventory()))
    review.write_text(
        '{"schema":"record-job-history-language-review/v1","owner_exclusions":{},"owner_exclusions":{}}'
    )
    with django_db_blocker.block(), pytest.raises(CommandError, match="duplicate"):
        call_command(
            "save_person_job",
            str(source),
            inventory=str(target),
            output=str(tmp_path / "preview.html"),
            fresh_language=True,
            language_review=str(review),
        )


def test_reviewed_disclosed_name_preserves_separate_observation():
    from core.staff_assets.job_history import prepare_job_history
    from tests.test_record_job_history import inventory, person

    row = person(names=["Ameliayu 余一"])
    audit = [
        {
            "native_id": "123",
            "handle": "testperson",
            "chinese_name": "余一",
            "category": "apparent_full_chinese_name",
            "evidence": [
                {
                    "name": "Ameliayu 余一",
                    "observed_at": "2026-10-01T00:00:00Z",
                    "handle": "testperson",
                    "kind": "account_bios",
                }
            ],
        }
    ]
    result = prepare_job_history([row], inventory(), audited_names=audit)
    names = [
        a
        for a in result["record_actions"]
        if a["table"] == "people_names" and a["fields"].get("full_name") == "余一"
    ]
    assert len(names) == 1
    assert result["people"][0]["reviewed_names"][0]["full_name"] == "余一"
    evidence = [
        a
        for a in result["record_actions"]
        if a["table"] == "people_name_evidence"
        and a["fields"].get("source_text") == "Ameliayu 余一"
        and a["fields"].get("name_id") == names[0]["key"]
    ]
    assert evidence[0]["fields"]["observed_at"] == "2026-10-01T00:00:00Z"


def test_reviewed_name_without_supporting_observation_is_held():
    from core.staff_assets.job_history import prepare_job_history
    from tests.test_record_job_history import inventory, person

    row = person(names=["Ameliayu 余一"])
    audit = [
        {
            "native_id": "123",
            "chinese_name": "余一",
            "category": "apparent_full_chinese_name",
            "evidence": [],
        }
    ]
    result = prepare_job_history([row], inventory(), audited_names=audit)
    name = next(
        a
        for a in result["record_actions"]
        if a["table"] == "people_names" and a["fields"].get("full_name") == "余一"
    )
    assert name["action"] == "hold"


def test_reviewed_name_reuses_identical_primary_name_proposal():
    from core.staff_assets.job_history import prepare_job_history
    from tests.test_record_job_history import inventory, person

    row = person(names=["余一"])
    audit = [
        {
            "native_id": "123",
            "chinese_name": "余一",
            "category": "apparent_full_chinese_name",
            "evidence": [
                {
                    "name": "余一",
                    "observed_at": "2026-10-01T00:00:00Z",
                    "handle": "testperson",
                    "kind": "account_bios",
                }
            ],
        }
    ]
    result = prepare_job_history([row], inventory(), audited_names=audit)
    assert (
        len(
            [
                a
                for a in result["record_actions"]
                if a["table"] == "people_names"
                and a["fields"].get("full_name") == "余一"
            ]
        )
        == 1
    )


def test_reviewed_name_cannot_attach_to_missing_person():
    import pytest

    from core.staff_assets.job_history import prepare_job_history
    from tests.test_record_job_history import inventory, person

    audit = [
        {
            "native_id": "999",
            "chinese_name": "余一",
            "category": "apparent_full_chinese_name",
            "evidence": [],
        }
    ]
    with pytest.raises(ValueError, match="identity absent"):
        prepare_job_history([person()], inventory(), audited_names=audit)


def test_biography_summary_reuses_identical_source_version():
    from core.staff_assets.job_history import prepare_job_history
    from tests.test_record_job_history import inventory, person

    row = person()
    row["roles"][0]["organization"] = "Acme"
    row["sources"][0]["observations"].append(
        {"observed": "2026-11-07T12:00:00Z", "handle": "testperson"}
    )
    result = prepare_job_history([row], inventory(), selected_brands={"anthropic"})
    summaries = result["people"][0]["biography_summaries"]
    assert len(summaries) == 1
    assert len(summaries[0]["observation_times"]) == 2
    assert (
        len([a for a in result["record_actions"] if a["table"] == "people_texts"]) == 1
    )


def test_scoped_preview_counts_raw_and_coalesced_roles():
    from core.staff_assets.job_history import prepare_job_history
    from tests.test_record_job_history import inventory, person

    row = person()
    row["roles"].append(
        {
            "organization": "Acme",
            "status": "former",
            "affiliation_type": "employment",
            "source_keys": ["bio:0"],
        }
    )
    result = prepare_job_history([row], inventory(), selected_brands={"anthropic"})
    assert result["role_counts"] == {
        "input": 2,
        "coalesced": 2,
        "structured": 1,
        "outside_scope": 1,
        "held": 1,
    }


def test_scoped_preview_reports_missing_profile_history_inventory():
    from core.staff_assets.job_history import prepare_job_history
    from tests.test_record_job_history import inventory, person

    result = prepare_job_history([person()], inventory(), selected_brands={"anthropic"})
    assert result["profile_history_inventory"] == "not_captured"


def test_saved_bio_gets_symbolic_profile_source_without_assuming_target_state():
    from core.staff_assets.job_history import prepare_job_history
    from tests.test_record_job_history import inventory, person

    result = prepare_job_history([person()], inventory(), selected_brands={"anthropic"})
    source = next(
        a for a in result["record_actions"] if a["table"] == "account_profile_snapshots"
    )
    role = result["people"][0]["affiliations"][0]
    assert source["action"] == "hold"
    assert role["evidence"][0]["source_profile_snapshot_ref"] == source["key"]
    assert role["action"] == "hold"
    assert result["database_writes"] == 0


def test_profile_sources_preserve_kinds_and_group_exact_replays():
    from core.staff_assets.job_history import prepare_job_history
    from tests.test_record_job_history import inventory, person

    row = person()
    row["sources"][0]["observations"] = [
        {
            "observed": "2026-11-06T12:00:00Z",
            "handle": "testperson",
            "kind": "account.profile_bio_text",
        },
        {
            "observed": "2026-11-06T12:00:00Z",
            "handle": "testperson",
            "kind": "snapshot.profile_bio_text",
        },
        {
            "observed": "2026-11-06T12:00:00Z",
            "handle": "testperson",
            "kind": "snapshot.profile_bio_text",
        },
    ]
    result = prepare_job_history([row], inventory(), selected_brands={"anthropic"})
    sources = [
        a for a in result["record_actions"] if a["table"] == "account_profile_snapshots"
    ]
    assert len(sources) == 2
    assert {a["fields"]["observation_kind"] for a in sources} == {
        "account.profile_bio_text",
        "snapshot.profile_bio_text",
    }
    assert sorted(a["occurrences"] for a in sources) == [1, 2]


def test_profile_source_identity_uses_stable_native_account():
    from copy import deepcopy

    from core.staff_assets.job_history import prepare_job_history
    from tests.test_record_job_history import inventory, person

    first = person()
    second = deepcopy(first)
    second["native_id"] = "456"
    result = prepare_job_history(
        [first, second], inventory(), selected_brands={"anthropic"}
    )
    refs = [
        a["key"]
        for a in result["record_actions"]
        if a["table"] == "account_profile_snapshots"
    ]
    assert len(refs) == len(set(refs)) == 2


def test_missing_name_clock_holds_names_without_losing_the_person():
    from core.staff_assets.job_history import prepare_job_history
    from tests.test_record_job_history import inventory, person

    row = person()
    row["name_source"]["observed_at"] = None
    result = prepare_job_history([row], inventory(), selected_brands={"anthropic"})
    assert result["people"][0]["names"] == ["Test Person"]
    assert all(
        a["action"] == "hold"
        for a in result["record_actions"]
        if a["table"]
        in {"people_names", "people_name_evidence", "person_name_selections"}
    )


def test_outside_scope_summary_keeps_each_source_own_fields():
    from core.staff_assets.job_history import prepare_job_history
    from tests.test_record_job_history import inventory, person

    row = person()
    row["sources"][0]["text"] = "Engineer at Acme"
    row["sources"].append(
        {
            "key": "post:0",
            "kind": "own_post",
            "text": "Acme Research team",
            "tweet_id": "222",
            "author_handle": "testperson",
            "published_at": "2026-07-08T00:00:00Z",
            "observed_at": "2026-07-09T00:00:00Z",
        }
    )
    row["roles"] = [
        {
            "organization": "Acme",
            "status": "unknown",
            "affiliation_type": "employment",
            "title_raw": "Engineer",
            "source_keys": ["bio:0"],
        },
        {
            "organization": "Acme",
            "status": "unknown",
            "affiliation_type": "employment",
            "team": "Research",
            "source_keys": ["post:0"],
        },
    ]
    result = prepare_job_history([row], inventory(), selected_brands={"anthropic"})
    summaries = result["people"][0]["biography_summaries"]
    bio = next(x for x in summaries if "/status/" not in x["source_reference"])
    post = next(x for x in summaries if "/status/" in x["source_reference"])
    assert "Engineer" in bio["text"] and "Research" not in bio["text"]
    assert "Research" in post["text"] and "Engineer" not in post["text"]


def test_structured_role_retains_field_specific_source_keys():
    from core.staff_assets.job_history import prepare_job_history
    from tests.test_record_job_history import inventory, person

    row = person()
    row["sources"][0]["text"] = "Engineer at Anthropic"
    row["sources"].append(
        {
            "key": "post:0",
            "kind": "own_post",
            "text": "Anthropic Research team",
            "tweet_id": "222",
            "author_handle": "testperson",
            "published_at": "2026-07-08T00:00:00Z",
            "observed_at": "2026-07-09T00:00:00Z",
        }
    )
    row["roles"] = [
        {
            "organization": "Anthropic",
            "status": "unknown",
            "affiliation_type": "employment",
            "title_raw": "Engineer",
            "source_keys": ["bio:0"],
        },
        {
            "organization": "Anthropic",
            "status": "unknown",
            "affiliation_type": "employment",
            "team": "Research",
            "source_keys": ["post:0"],
        },
    ]
    role = prepare_job_history([row], inventory(), selected_brands={"anthropic"})[
        "people"
    ][0]["affiliations"][0]
    assert role["field_sources"]["title_raw"][0]["source_keys"] == ["bio:0"]
    assert role["field_sources"]["team"][0]["source_keys"] == ["post:0"]
    assert role["field_sources"]["title_raw"][0]["supporting_span"] == "Engineer"
    assert role["field_sources"]["team"][0]["supporting_span"] == "Research"


def test_same_profile_url_different_saved_sources_stay_separate():
    from core.staff_assets.job_history import prepare_job_history
    from tests.test_record_job_history import inventory, person

    row = person()
    row["sources"][0]["text"] = "Engineer at Acme"
    row["sources"].append(
        {
            "key": "bio:1",
            "kind": "saved_bio",
            "text": "Researcher at Beta",
            "observations": [
                {"observed": "2026-11-06T12:00:00Z", "handle": "testperson"}
            ],
        }
    )
    row["roles"] = [
        {
            "organization": "Acme",
            "status": "unknown",
            "affiliation_type": "employment",
            "title_raw": "Engineer",
            "source_keys": ["bio:0"],
        },
        {
            "organization": "Beta",
            "status": "unknown",
            "affiliation_type": "employment",
            "title_raw": "Researcher",
            "source_keys": ["bio:1"],
        },
    ]
    summaries = prepare_job_history([row], inventory(), selected_brands={"anthropic"})[
        "people"
    ][0]["biography_summaries"]
    assert len(summaries) == 2
    assert all(not ("Acme" in x["text"] and "Beta" in x["text"]) for x in summaries)


def test_multi_source_summary_holds_unattributed_fields():
    from core.staff_assets.job_history import prepare_job_history
    from tests.test_record_job_history import inventory, person

    row = person()
    row["sources"][0]["text"] = "Worked at Acme"
    row["sources"].append(
        {
            "key": "post:0",
            "kind": "own_post",
            "text": "Engineer at Acme",
            "tweet_id": "222",
            "author_handle": "testperson",
            "published_at": "2026-07-08T00:00:00Z",
            "observed_at": "2026-07-09T00:00:00Z",
        }
    )
    row["roles"] = [
        {
            "organization": "Acme",
            "status": "unknown",
            "affiliation_type": "employment",
            "title_raw": "Engineer",
            "source_keys": ["bio:0", "post:0"],
        }
    ]
    result = prepare_job_history([row], inventory(), selected_brands={"anthropic"})
    bio = next(
        x
        for x in result["people"][0]["biography_summaries"]
        if "/status/" not in x["source_reference"]
    )
    assert bio["action"] == "hold"


def test_versioned_review_rejects_stale_source_and_unknown_keys():
    import hashlib

    import pytest

    from core.person_names import digest
    from core.staff_assets.job_history_names import validate_name_review
    from tests.test_record_job_history import person

    row = person()
    decision = {
        "native_id": "123",
        "source_key": "saved-name:0",
        "quote": "Test Person",
        "evidence_sha256": hashlib.sha256(b"Test Person").hexdigest(),
        "observed_at": row["name_source"]["observed_at"],
        "decision": "exclude",
        "reason": "owner decision",
        "supersedes": None,
    }
    review = {
        "schema": "record-job-history-name-review/v1",
        "source_digest": digest([row]),
        "rules_version": "save-person-job-fresh/v1",
        "reviewed_by": "owner",
        "reviewed_at": "2026-11-09T12:00:00+09:00",
        "decisions": [decision],
    }
    assert validate_name_review(review, [row]) == {"123": "owner decision"}
    bad = {**review, "extra": True}
    with pytest.raises(ValueError, match="review"):
        validate_name_review(bad, [row])
    decision["evidence_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="evidence"):
        validate_name_review(review, [row])


def test_versioned_review_rejects_duplicate_identity_and_stale_time():
    import hashlib

    import pytest

    from core.person_names import digest
    from core.staff_assets.job_history_names import validate_name_review
    from tests.test_record_job_history import person

    row = person()
    decision = {
        "native_id": "123",
        "source_key": "saved-name:0",
        "quote": "Test Person",
        "evidence_sha256": hashlib.sha256(b"Test Person").hexdigest(),
        "observed_at": row["name_source"]["observed_at"],
        "decision": "exclude",
        "reason": "owner decision",
        "supersedes": None,
    }
    review = {
        "schema": "record-job-history-name-review/v1",
        "source_digest": digest([row]),
        "rules_version": "save-person-job-fresh/v1",
        "reviewed_by": "owner",
        "reviewed_at": "2026-11-09T12:00:00+09:00",
        "decisions": [decision, dict(decision)],
    }
    with pytest.raises(ValueError, match="duplicate"):
        validate_name_review(review, [row])
    review["decisions"] = [{**decision, "observed_at": "2026-01-01T00:00:00Z"}]
    with pytest.raises(ValueError, match="observation time"):
        validate_name_review(review, [row])


def test_real_command_uses_versioned_manifest_review(tmp_path, django_db_blocker):
    import hashlib
    import json

    from django.core.management import call_command

    from core.person_names import digest
    from tests.test_record_job_history import inventory, person

    row = person(names=["成熟小老头"])
    decision = {
        "native_id": "123",
        "source_key": "saved-name:0",
        "quote": "成熟小老头",
        "evidence_sha256": hashlib.sha256("成熟小老头".encode()).hexdigest(),
        "observed_at": row["name_source"]["observed_at"],
        "decision": "exclude",
        "reason": "owner decision",
        "supersedes": None,
    }
    review = {
        "schema": "record-job-history-name-review/v1",
        "source_digest": digest([row]),
        "rules_version": "save-person-job-fresh/v1",
        "reviewed_by": "owner",
        "reviewed_at": "2026-11-09T12:00:00+09:00",
        "decisions": [decision],
    }
    source, target, output = (
        tmp_path / name for name in ("manifest.json", "inventory.json", "preview.html")
    )
    source.write_text(
        json.dumps(
            {"schema": "record-job-history/v1", "people": [row], "name_review": review}
        )
    )
    target.write_text(json.dumps(inventory()))
    with django_db_blocker.block():
        call_command(
            "save_person_job",
            str(source),
            inventory=str(target),
            output=str(output),
            fresh_language=True,
        )
    prepared = json.loads(output.with_suffix(".json").read_text())
    assert prepared["people"][0]["language_proposal"]["action"] == "excluded"


def test_manifest_rejects_duplicate_json_fields(tmp_path):
    import pytest

    from core.staff_assets.manifest import load_manifest

    manifest = tmp_path / "duplicate.json"
    manifest.write_text('{"schema":"record-job-history/v1","people":[],"people":[]}')
    with pytest.raises(ValueError, match="duplicate"):
        load_manifest(manifest)


def test_source_coverage_distinguishes_saved_evidence_from_search():
    from core.staff_assets.job_history import prepare_job_history
    from tests.test_record_job_history import inventory, person

    row = person()
    result = prepare_job_history([row], inventory(), selected_brands={"anthropic"})
    coverage = result["people"][0]["source_coverage"]
    assert coverage["saved_bios"] == 1
    assert coverage["own_posts"] == 0
    assert coverage["history_search"] == "not_run"
    assert coverage["source_completeness"] == "unknown"
