"""One saved observation reaches the real Chatter article/media reader chain."""

import json
import subprocess
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock

import imageio_ffmpeg
import pytest

from core.models import (
    CollectionRequest,
    ContentPicture,
    Language,
    Locale,
    OriginalContent,
    OriginalContentCall,
    Post,
)
from monitor.editorial.chatter_chain import run_chatter, select_chatter
from monitor.editorial.chatter_trends import envelope_for
from monitor.editorial.config import load_editorial_config
from monitor.editorial.graphics_packages import claim_package, release_package
from monitor.editorial.graphics_pipeline import (
    advance_step,
    finalize_if_done,
    pending_action,
    review_step,
)
from monitor.editorial.graphics_reading import graphics_assets
from monitor.editorial.graphics_video import poll_video_job, submit_video_job
from monitor.editorial.readers import feed_payload
from monitor.original_content_readers import saved_edition
from tests.editorial_support import (
    editorial_storage as editorial_storage,  # noqa: PLC0414
)
from tests.test_chatter_chain import wire
from tests.test_chatter_discovery import selection
from tests.test_chatter_graphics_publication import media_transport
from tests.test_chatter_trends import discover, official_response, rank_wire, start
from tests.test_graphics_chatter_adapter import copy_result

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


def test_observation_to_rank_gather_select_copy_still_video_and_advisory(
    monkeypatch, editorial_storage, tmp_path, django_capture_on_commit_callbacks,
):
    monkeypatch.setenv("ORIGINAL_CONTENT_STORAGE", "shared")
    monkeypatch.setenv("OPENROUTER_API_KEY", "fixture-only")
    monkeypatch.setenv("XAI_API_KEY_PW", "fixture-only")
    for locale, language in (("en", "en"), ("ja", "ja"), ("zh-CN", "zh")):
        Language.objects.get_or_create(pk=language)
        Locale.objects.get_or_create(pk=locale, defaults={"language_id": language})
    cfg = load_editorial_config(Path(__file__).resolve().parents[1] / "config/editorial-chatter-staging.yaml")
    cfg = cfg.model_copy(update={
        "chatter": cfg.chatter.model_copy(update={"enabled": True}),
        "voices": {key: voice for key, voice in cfg.voices.items()
                   if not key.startswith("chatter:") or key == "chatter:en"},
        "locale_routes": {}, "public_enabled": True,
    })
    source_run = start(cfg)
    ranked, official, ranker = discover(
        source_run, cfg, official_response(1), Mock(return_value=rank_wire(1)),
    )
    assert ranked["status"] == "ranked"
    assert official.call_count == ranker.call_count == 1
    post = Post.objects.create(
        tweet_id="7611", lang="en", author_handle="reporter",
        text="Original headline 1: the maker confirms testing only, without a general release.",
        created_at=source_run.facts_as_of - timedelta(minutes=1),
    )
    queued, dispatches = [], []
    monkeypatch.setattr("monitor.editorial.graphics_dispatch.dispatch_creation",
                        lambda **values: dispatches.append(values) or True)
    no_rank_resend = Mock(side_effect=AssertionError("saved ranking must be reused"))
    with django_capture_on_commit_callbacks(execute=True):
        gathered = run_chatter(envelope_for(source_run), cfg=cfg, transport=no_rank_resend,
                               enqueue=lambda *values: queued.append(values))
        assert queued == []
    assert gathered["status"] == "discovered"
    assert queued == [("select", source_run.pk)]
    no_rank_resend.assert_not_called()

    def selector(_url, _key, body, **_kwargs):
        supplied = json.loads(body["input"][1]["content"])
        reply = selection(supplied["candidates"][0])
        reply["candidate_tags"][0].update(
            group_policy_ref=supplied["giant_group_policy"]["policy_ref"],
            group_evidence_post_ids=[post.pk],
        )
        return wire(reply)

    assert select_chatter(source_run.pk, cfg=cfg, transport=selector)["status"] == "selected"
    output = OriginalContent.objects.get(output_key="graphics-primary/v1")
    package = output.run
    assert len(dispatches) == 1
    assert CollectionRequest.objects.filter(attempt__run__content_run=source_run).count() == 1
    assert set(source_run.provider_calls.values_list("stage", flat=True)) == {"trends-ranking-v1", "selector:0"}

    transport, images = media_transport(copy_result(used=("F01",)))
    keys = {key: "fixture-only" for key in ("OPENAI_API_KEY", "OPENROUTER_API_KEY", "XAI_API_KEY_PW")}
    first = advance_step(package.pk, keys=keys, transport=transport)
    text = output.localized_texts.get(locale="en")
    assert first["stage"] == "C1" and first["text_id"] == text.pk
    assert not ContentPicture.objects.filter(run=package).exists()
    source_run.refresh_from_db()
    assert source_run.outcome["healthy_at"]
    assert feed_payload(cfg, source_locale="en", editorial_group="rest")["hero"]["id"] == str(text.public_id)
    assert list(text.sources.values_list("post_id", flat=True)) == [post.pk]
    for _ in range(5):
        advance_step(package.pk, keys=keys, transport=transport)
    assert len(images) == 1
    assert pending_action(package.pk)["action"] == "video"

    claim = claim_package(package.pk, owner="full-chain-video")
    assert claim is not None
    try:
        submitted = submit_video_job(package.pk, text.pk, owner=claim.owner, fence=claim.fence,
            api_key="fixture-only", transport=lambda *args, **kwargs: (200, b'{"request_id":"full-chain-video"}'))
    finally:
        release_package(package.pk, owner=claim.owner, fence=claim.fence)
    movie = tmp_path / "full-chain.mp4"
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-f", "lavfi", "-i",
        "color=c=red:s=32x32:r=5:d=5", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", "-y", str(movie)], check=True, capture_output=True)
    data = movie.read_bytes()
    polled = poll_video_job(submitted["job_id"], api_key="fixture-only",
        transport=lambda *args, **kwargs: (200, b'{"status":"done","video":{"url":"https://example.test/video"},"usage":{"cost_in_usd_ticks":1600000000}}'),
        fetch=lambda *args, **kwargs: (data, "https://example.test/video", "video/mp4"))
    assert polled["state"] == "completed"
    text.refresh_from_db()
    assets = graphics_assets(saved_edition(text))
    assert assets.still.text_id == assets.video.text_id == text.pk
    assert assets.video.provenance["decode_receipt"]["duration_ms"] == 5000

    def advisory(_url, _key, body, **_kwargs):
        message = body["messages"][1]["content"]
        message = message[0]["text"] if isinstance(message, list) else message
        supplied, _ = json.JSONDecoder().raw_decode(message.split("\n\nSUPPLIED INPUTS:\n", 1)[1])
        score = {"schema_version": "eic-scorecard/v1", "text_id": supplied["text_id"],
            "content_revision": supplied["content_revision"], "summary": "Offline fixture only.",
            "scores": {name: 4 for name in ("factual_support", "attribution_uncertainty", "headline_craft",
                "clarity_context", "image_claim_fit", "likeness", "lettering")},
            "findings": [], "reviewed_asset_refs": [], "not_reviewed": ["Offline fixture only."],
            "suggested_admin_follow_up": []}
        return 200, json.dumps({"model": body["model"], "usage": {"cost": "0.01"}, "choices": [
            {"finish_reason": "stop", "message": {"content": json.dumps(score)}}]}).encode()

    assert review_step(package.pk, keys=keys, transport=advisory)["state"] == "completed"
    assert pending_action(package.pk) is None
    assert finalize_if_done(package.pk)
    assert list(OriginalContentCall.objects.filter(run=package, stage__endswith=":C1")) == [text.producing_call]
    assert not source_run.provider_calls.filter(stage__startswith="writer:").exists()
    run_chatter(envelope_for(source_run), cfg=cfg, transport=no_rank_resend)
    no_rank_resend.assert_not_called()
    assert CollectionRequest.objects.filter(attempt__run__content_run=source_run).count() == 1
    assert OriginalContent.objects.filter(output_key="graphics-primary/v1").count() == 1
