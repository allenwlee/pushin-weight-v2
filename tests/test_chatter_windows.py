from datetime import UTC, datetime, timedelta
import json

import pytest

from monitor.editorial.chatter_windows import (
    apply_selection,
    decision_packet,
    selection_request,
)

BASE = datetime(2026, 11, 17, 9, 0, tzinfo=UTC)


def sample(minutes, *names, lag=1):
    slot = BASE + timedelta(minutes=minutes)
    return {
        "slot": slot.isoformat(),
        "observed_at": (slot + timedelta(minutes=lag)).isoformat(),
        "request_id": str(minutes),
        "headlines": [{"trend_name": n} for n in names],
    }


def votes(packet):
    return {
        "ranked_stories": [
            {
                "title": h["trend_name"],
                "headline_ids": [h["headline_id"]],
                "reason": "new public exchange",
                "qualifies": True,
                "prior_episode_id": None,
                "material_change": None,
            }
            for h in packet["headlines"]
        ]
    }


def test_freeze_deduplicates_and_excludes_unavailable_and_future_receipts():
    snap = [
        sample(-60, "expired"),
        sample(-45, "AI"),
        sample(-30, "ＡＩ", "AI"),
        sample(0, "late", lag=6),
        sample(15, "future"),
    ]
    packet = decision_packet(snap, BASE, {})
    assert [h["trend_name"] for h in packet["headlines"]] == ["ＡＩ"]
    headline = packet["headlines"][0]
    assert headline["snapshot_count"] == 2 and headline["consecutive"]
    assert [a["row"] for a in headline["appearances"]] == [1, 1]
    assert "expired" not in selection_request(packet)["user"]
    assert len(packet["missing_slots"]) == 2


def test_overflow_drains_without_model_even_after_window_rollover():
    p = decision_packet([sample(0, "one", "two", "three")], BASE, {})
    r = apply_selection(p, votes(p))
    assert [e["title"] for e in r["leads"]] == ["one", "two"]
    p2 = decision_packet([], BASE + timedelta(hours=1), r["history"])
    assert not p2["needs_ranking"]
    r2 = apply_selection(p2, None)
    assert [e["title"] for e in r2["leads"]] == ["three"]
    assert r2["leads"][0]["headlines"][0]["appearances"][0]["request_id"] == "0"


def test_repeat_evidence_triggers_once_and_exact_repeat_is_not_readmitted():
    o = sample(0, "A joke")
    p = decision_packet([o], BASE, {})
    h = apply_selection(p, votes(p))["history"]
    p = decision_packet([o, sample(15, "a JOKE")], BASE + timedelta(minutes=30), h)
    assert p["needs_ranking"]
    r = apply_selection(p, votes(p))
    assert not r["leads"]
    p = decision_packet(
        [sample(30, "a joke"), sample(45, "a joke")],
        BASE + timedelta(hours=1),
        r["history"],
    )
    assert not p["needs_ranking"]


def test_material_change_requires_prior_admission_and_fresh_wording():
    p = decision_packet([sample(0, "Founder leaves")], BASE, {})
    a = apply_selection(p, votes(p))["history"]
    p = decision_packet(
        [sample(30, "Founder returns")], BASE + timedelta(minutes=30), a
    )
    r = votes(p)
    g = r["ranked_stories"][0]
    g.update(
        prior_episode_id=a["admitted"][0]["episode_id"],
        material_change="return confirmed",
    )
    assert apply_selection(p, r)["leads"][0]["material_change"] == "return confirmed"
    g["prior_episode_id"] = "invented"
    with pytest.raises(ValueError):
        apply_selection(p, r)


def test_duplicate_response_ids_and_missing_rankings_fail_closed():
    p = decision_packet([sample(0, "one", "two")], BASE, {})
    r = votes(p)
    r["ranked_stories"][0]["headline_ids"] = [2]
    with pytest.raises(ValueError):
        apply_selection(p, r)
    with pytest.raises(ValueError):
        apply_selection(p, None)
    assert json.loads(selection_request(p)["user"])["prior_episodes"] == []


def test_exact_wording_fallback_preserves_explicit_prior_match_in_later_group():
    first = decision_packet([sample(0, "Original wording")], BASE, {})
    saved = apply_selection(first, votes(first))["history"]
    episode_id = saved["admitted"][0]["episode_id"]
    packet = decision_packet(
        [sample(30, "Original wording", "Reworded follow-up")],
        BASE + timedelta(minutes=30),
        saved,
    )
    reply = votes(packet)
    reply["ranked_stories"][1]["prior_episode_id"] = episode_id
    result = apply_selection(packet, reply)
    assert result["leads"] == []
    assert result["history"]["admitted"][0]["wordings"] == [
        "original wording", "reworded follow-up"
    ]


def test_two_old_aliases_cannot_occupy_both_slots_for_one_pending_episode():
    first = decision_packet([sample(0, "a", "b", "c", "alias c")], BASE, {})
    first_reply = votes(first)
    first_reply["ranked_stories"][2]["headline_ids"].append(4)
    first_reply["ranked_stories"].pop()
    history = apply_selection(first, first_reply)["history"]
    pending_id = history["pending"][0]["episode_id"]
    packet = decision_packet(
        [sample(30, "c", "alias c", "new", "a")],
        BASE + timedelta(minutes=30),
        history,
    )
    admitted = apply_selection(packet, votes(packet))["leads"]
    assert len(admitted) == 2
    assert admitted[0]["episode_id"] == pending_id
    assert admitted[1]["title"] == "new"
