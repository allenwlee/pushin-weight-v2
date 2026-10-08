from copy import deepcopy

import pytest
from django.utils import timezone

from core.models import Post
from monitor.editorial.config import EditorialConfig
from monitor.editorial.context import _collect_story_packet, story_packet
from monitor.editorial.evidence import (
    _collect_packet,
    build_packet,
    post_evidence,
    trim_packet,
)
from monitor.packet_maker import evidence_identity
from tests.test_editorial_context import selected, stored

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


def test_editorial_adapters_preserve_sources_coverage_and_months_old_meme():
    now = timezone.now()
    anchor = stored(
        "1",
        "Mistral Large 4 is Le Chonk. Available by API, weights coming later.",
        now,
        0,
    )
    stored("2", "Le Chonk revives the old Le Chaton Fat joke.", now, 1)
    stored("3", "Le Chaton Fat was a Mistral meme nickname.", now, 90)
    stored("4", "Mistral unrelated generic update.", now, 90)
    stored("5", "Le Chaton Fat was a Mistral meme nickname.", now, -1)
    cfg = EditorialConfig()
    baseline = trim_packet(_collect_packet(now, cfg), cfg.max_packet_bytes)
    assert build_packet(now, cfg) == baseline
    event = selected(now, ["1"])
    packet = {
        "posts": [post_evidence(anchor)],
        "context": [],
        "cutoff": now.isoformat(),
    }
    old = _collect_story_packet(event, deepcopy(packet), cfg)
    prepared = story_packet(event, packet, cfg)
    assert prepared == old
    assert "3" in {source["id"] for source in prepared["context"]}
    assert {source["id"] for source in prepared["context"]}.isdisjoint({"4", "5"})


def test_source_and_profile_changes_invalidate_unchanged_evidence():
    now = timezone.now()
    post = stored("1", "An original passage", now, 0)
    packet = {"posts": [post_evidence(post)]}
    baseline = evidence_identity(packet, {"classification": "v3"})
    assert evidence_identity(packet, {"classification": "v4"}) != baseline
    Post.objects.filter(pk="1").update(like_count=42)
    post.refresh_from_db()
    assert (
        evidence_identity({"posts": [post_evidence(post)]}, {"classification": "v3"})
        != baseline
    )
