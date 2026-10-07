import json
from datetime import timedelta

import pytest
from django.utils import timezone

from core.models import Post
from monitor.editorial.config import EditorialConfig
from monitor.editorial.context import story_packet
from monitor.editorial.contracts import Event
from monitor.editorial.evidence import packet_bytes, post_evidence, trim_packet
from monitor.editorial.voices import load_voice
from monitor.editorial.writing import validate_copy, writer_request


def selected(now, ids):
    return Event(
        key="ajax",
        summary="A local agent",
        post_ids=ids,
        occurred_at=now,
        chatter=True,
        pulse=False,
        importance=70,
        reason="A development",
    )


def stored(pk, text, now, days):
    post = Post.objects.create(
        tweet_id=pk, text=text, created_at=now - timedelta(days=days)
    )
    Post.objects.filter(pk=pk).update(fetched_at=now - timedelta(minutes=1))
    return post


@pytest.mark.django_db
@pytest.mark.requires_postgres
def test_story_recall_recovers_months_old_history_without_name_collision_or_late_fetch():
    now = timezone.now()
    anchor = stored(
        "1",
        "PewDiePie announced Ajax, a local agent for his Odysseus workspace.",
        now,
        0,
    )
    recent = stored(
        "2",
        "PewDiePie uses Ajax for his Odysseus workspace, called ProjectAtlas.",
        now,
        2,
    )
    stored("3", "Ajax football fans win the game.", now, 2)
    stored("4", "PewDiePie experiments with Ajax in his Odysseus workspace.", now, 95)
    stored("5", "ProjectAtlas was the name of this local agent workspace.", now, 140)
    stored("6", "PewDiePie experiments with Ajax in his Odysseus workspace.", now, 181)
    stored("7", "PewDiePie experiments with Ajax in his Odysseus workspace.", now, 90)
    Post.objects.filter(pk="7").update(fetched_at=now + timedelta(hours=1))
    stored("8", "PewDiePie announced Ajax.", now, -1)
    stored("9", "ProjectAtlas: PewDiePie's local agent workspace.", now, 3)
    packet = {
        "posts": [post_evidence(anchor)],
        "context": [],
        "cutoff": now.isoformat(),
    }
    event = selected(now, ["1"])
    cfg = EditorialConfig()
    result = story_packet(event, packet, cfg)
    ids = {p["id"] for p in result["context"]}
    assert {recent.pk, "4", "5", "9"} <= ids
    assert ids.isdisjoint({"3", "6", "7", "8"})
    assert "projectatlas" in result["story_context"]["history_terms"]
    assert result["story_context"]["query_timeout"] is False
    assert result["story_context"]["evidence_bytes"] <= cfg.max_story_bytes
    request = writer_request(event, result, load_voice("chatter-en-v1"), cfg)
    assert "4" in request["source_ids"].values()
    assert len(json.loads(request["user"])["event"]["post_ids"]) == 1
    assert event.post_ids == ["1"]
    raw = {
        "headline": "Headline",
        "byline": "Byline",
        "article": "Article",
        "locale": "en",
        "post_ids": ["1", "4"],
    }
    assert validate_copy(raw, event, "en", packet=result).post_ids == ["1", "4"]
    with pytest.raises(ValueError, match="source mismatch"):
        validate_copy({**raw, "post_ids": ["1", "3"]}, event, "en", packet=result)
    with pytest.raises(ValueError, match="selected story"):
        validate_copy({**raw, "post_ids": ["4"]}, event, "en", packet=result)


def test_trim_preserves_background_and_reports_loss_in_utf8_bytes():
    rows = [{"id": str(n), "original_text": "界" * 300} for n in range(12)]
    packet = {
        "posts": rows[:8],
        "context": rows[8:],
        "coverage": {"sampled": False},
        "headline_leads": [],
        "people": [],
        "stories": [],
        "chart_context": [],
    }
    result = trim_packet(packet, 4000)
    assert packet_bytes(result) <= 4000
    assert result["posts"] and result["context"]
    assert result["coverage"]["context_trimmed"] == 3


@pytest.mark.django_db
@pytest.mark.requires_postgres
def test_story_byte_budget_keeps_anchors_and_records_excluded_context():
    now = timezone.now()
    anchor = stored("1", "PewDiePie Ajax Odysseus workspace", now, 0)
    for i in range(2, 9):
        stored(str(i), "PewDiePie Ajax Odysseus workspace " + "界" * 1500, now, i)
    packet = {
        "posts": [post_evidence(anchor)],
        "context": [],
        "cutoff": now.isoformat(),
    }
    result = story_packet(
        selected(now, ["1"]), packet, EditorialConfig(max_story_bytes=4000)
    )
    assert result["posts"][0]["id"] == "1"
    assert result["context"] == []
    assert result["story_context"]["recent_candidates"] > 1
    assert result["story_context"]["evidence_bytes"] <= 4000


@pytest.mark.django_db
@pytest.mark.requires_postgres
def test_query_timeout_preserves_anchors_and_records_partial_recall(monkeypatch):
    from monitor.editorial import context

    now = timezone.now()
    anchor = stored("1", "PewDiePie Ajax Odysseus workspace", now, 0)
    monkeypatch.setattr(context, "retrieve", lambda *args, **kwargs: ([], True))
    packet = {
        "posts": [post_evidence(anchor)],
        "context": [],
        "cutoff": now.isoformat(),
    }
    result = story_packet(selected(now, ["1"]), packet, EditorialConfig())
    assert result["story_context"]["query_timeout"] is True
    assert result["posts"][0]["id"] == "1"


@pytest.mark.django_db
@pytest.mark.requires_postgres
def test_chonk_bridge_discovers_chaton_history_and_manual_entry_matches_automatic():
    now = timezone.now()
    anchor = stored(
        "1",
        "Mistral Large 4 is Le Chonk. Available by API, weights coming later.",
        now,
        0,
    )
    stored("2", "Le Chonk revives the old Le Chaton Fat joke.", now, 1)
    stored(
        "3", "Remember the fictional Le Chaton Fat? That cat fooled people.", now, 90
    )
    stored("4", "Mistral Large 3 was released by API.", now, 90)
    event = selected(now, ["1"])
    packet = {
        "posts": [post_evidence(anchor)],
        "context": [],
        "cutoff": now.isoformat(),
    }
    auto = story_packet(event, packet, EditorialConfig())
    manual = story_packet(event, {**packet, "posts": []}, EditorialConfig())
    assert [p["id"] for p in auto["context"]] == [p["id"] for p in manual["context"]]
    assert {p["id"] for p in auto["context"]} == {"2", "3"}
    bridge = next(
        p
        for p in auto["story_context"]["alias_bridges"]
        if p["term"] == "le chaton fat"
    )
    assert bridge["post_id"] == "2"
    assert (
        Post.objects.get(pk="2").text[bridge["start"] : bridge["end"]]
        == "Le Chaton Fat"
    )


@pytest.mark.django_db
@pytest.mark.requires_postgres
def test_unnamed_teaser_requires_direct_link_not_just_same_team():
    now = timezone.now()
    teaser = stored("1", "We hope to ship this weekend; timing is tentative.", now, 6)
    stored("2", "Another product should ship this weekend.", now, 6)
    anchor = stored("3", "GLM 5.2 is available today.", now, 0)
    Post.objects.filter(pk=anchor.pk).update(in_reply_to_id=teaser.pk)
    anchor.refresh_from_db()
    event = selected(now, ["3"])
    packet = {"posts": [], "context": [], "cutoff": now.isoformat()}
    result = story_packet(event, packet, EditorialConfig())
    assert [p["id"] for p in result["context"]] == ["1"]
    assert result["story_context"]["linked_ids"] == ["1"]
    assert "tentative" in result["context"][0]["original_text"]
    Post.objects.filter(pk="3").update(fetched_at=now + timedelta(hours=1))
    with pytest.raises(ValueError, match="missing selected"):
        story_packet(event, packet, EditorialConfig())


def test_distinctive_seeds_never_include_url_fragments():
    from monitor.editorial.context import names

    assert "zhr3nxmovo" not in names(
        [{"original_text": "PewDiePie Ajax https://t.co/ZHR3NXmoVO"}]
    )


def test_phrase_seeds_keep_names_and_versions_without_sentence_fillers():
    from monitor.editorial.context import names

    terms = names([{"original_text": "Meet Mistral Large 4. LE CHATON FAT IS REAL."}])
    assert "mistral large 4" in terms
    assert "meet mistral large 4" not in terms
    assert "le chaton fat" in terms
    assert "le chaton fat is" not in terms


@pytest.mark.django_db
@pytest.mark.requires_postgres
def test_token_address_promotion_does_not_become_model_background():
    now = timezone.now()
    anchor = stored("1", "PewDiePie Ajax Odysseus workspace", now, 0)
    stored(
        "2",
        "PewDiePie Ajax Odysseus workspace. CA：H9qKeikv2EuifXaMCWSFQSUvNHUu2dre9R3Gmz62mvjw",
        now,
        2,
    )
    stored("3", "PewDiePie Ajax runs locally in Odysseus workspace", now, 2)
    result = story_packet(
        selected(now, ["1"]),
        {"posts": [post_evidence(anchor)], "context": [], "cutoff": now.isoformat()},
        EditorialConfig(),
    )
    assert [p["id"] for p in result["context"]] == ["3"]
