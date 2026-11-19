"""Bind profile evidence only to exact target-side source observations."""

from copy import deepcopy

from core.profile_snapshots import profile_observation_from_payload
from core.staff_assets.job_history import (
    _can_create_target_profile,
    _match_target_profile,
    prepare_job_history,
)
from tests.test_record_job_history import inventory, person


def target():
    observation = profile_observation_from_payload(
        {
            "author_profile_bio_text": "Research at DeepSeek",
            "_author_present_fields": ["author_profile_bio_text"],
        }
    )
    action = {
        "fields": {
            "account_key": "target-account",
            "observed_at": "2026-08-01T00:00:00+00:00",
            "observed_handle": "researcher",
            "observation_kind": "account.profile_bio_text",
            "source_reference": "https://x.com/researcher",
            "saved_bio": "Research at DeepSeek",
        }
    }
    row = {
        "id": 42,
        "account_key": "target-account",
        "first_observed_at": "2026-08-01T00:00:00+00:00",
        "last_observed_at": "2026-08-01T00:00:00+00:00",
        "first_source_post_id": None,
        "first_source_kind": "account",
        "profile_hash": observation.profile_hash,
        "profile_data": observation.profile_data,
        "present_fields": list(observation.present_fields),
        "handle": "researcher",
    }
    return action, row


def test_exact_target_source_clock_and_hash_reuses_target_identity():
    action, row = target()
    assert _match_target_profile(action, [row]) == 42


def test_wrong_hash_account_source_or_ambiguous_duplicate_is_held():
    action, row = target()
    for key, wrong in [
        ("profile_hash", "bad"),
        ("account_key", "other"),
        ("first_source_kind", "post"),
        ("first_source_post_id", "123"),
        ("handle", "other"),
    ]:
        changed = {**row, key: wrong}
        assert _match_target_profile(action, [changed]) is None
    assert _match_target_profile(action, [row, deepcopy(row)]) is None


def test_conflicting_compressed_window_is_held_even_with_exact_match():
    action, row = target()
    conflict = {
        **row,
        "id": 43,
        "profile_hash": "different",
        "first_observed_at": "2026-07-31T00:00:00+00:00",
        "last_observed_at": "2026-08-02T00:00:00+00:00",
    }
    assert _match_target_profile(action, [row, conflict]) is None


def test_interior_time_does_not_claim_unrecorded_observation():
    action, row = target()
    row["last_observed_at"] = "2026-08-03T00:00:00+00:00"
    action["fields"]["observed_at"] = "2026-08-02T00:00:00+00:00"
    assert _match_target_profile(action, [row]) is None


def test_new_profile_proposal_stays_outside_known_compressed_intervals():
    action, row = target()
    row["first_observed_at"] = "2026-08-03T00:00:00+00:00"
    row["last_observed_at"] = "2026-08-05T00:00:00+00:00"
    assert _can_create_target_profile(action, [row])
    action["fields"]["observed_at"] = "2026-08-04T00:00:00+00:00"
    assert not _can_create_target_profile(action, [row])
    row["last_observed_at"] = "bad"
    assert not _can_create_target_profile(action, [row])


def test_real_preparation_requires_complete_inventory_before_binding_snapshot():
    state = inventory()
    state["accounts"] = [
        {"account_key": "target-account", "author_id": "123", "handle": "testperson"}
    ]
    state["people"] = [{"id": "target-person"}]
    state["person_accounts"] = [
        {
            "account_key": "target-account",
            "person_id": "target-person",
            "resolution_status": "confirmed",
        }
    ]
    source_person = person()
    source = source_person["sources"][0]
    source["observations"][0]["kind"] = "account.profile_bio_text"
    observed = source["observations"][0]["observed"]
    obs = profile_observation_from_payload(
        {
            "author_handle": "testperson",
            "author_profile_bio_text": source["text"],
            "_author_present_fields": ["author_handle", "author_profile_bio_text"],
        }
    )
    state["profile_snapshots"] = [
        {
            "id": 42,
            "account_key": "target-account",
            "first_observed_at": observed,
            "last_observed_at": observed,
            "first_source_post_id": None,
            "first_source_kind": "account",
            "profile_hash": obs.profile_hash,
            "profile_data": obs.profile_data,
            "present_fields": list(obs.present_fields),
            "handle": "testperson",
        }
    ]
    partial = prepare_job_history([source_person], state, selected_brands={"anthropic"})
    assert (
        next(
            a
            for a in partial["record_actions"]
            if a["table"] == "account_profile_snapshots"
        )["action"]
        == "hold"
    )
    state["profile_snapshots_complete"] = True
    complete = prepare_job_history(
        [source_person], state, selected_brands={"anthropic"}
    )
    profile = next(
        a
        for a in complete["record_actions"]
        if a["table"] == "account_profile_snapshots"
    )
    assert (
        profile["action"] == "reuse" and profile["fields"]["target_snapshot_id"] == 42
    )
    assert (
        complete["people"][0]["affiliations"][0]["evidence"][0][
            "source_profile_snapshot_id"
        ]
        == 42
    )
