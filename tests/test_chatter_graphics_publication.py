"""Personalized Chatter uses the saved Graphics edition while media is pending."""

import json
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from core.models import (
    Language,
    Locale,
    OriginalContent,
    OriginalContentCall,
    OriginalContentSelection,
)
from monitor.editorial.chatter_trends import TRENDS_SCOPE, workflow_version
from monitor.editorial.config import EditorialConfig
from monitor.editorial.graphics_pipeline import advance_step, pending_action
from monitor.original_content import featured_scope
from tests.editorial_support import (
    editorial_storage as editorial_storage,  # noqa: PLC0414
)
from tests.test_graphics_chatter_adapter import (
    copy_result,
    prepared,
)
from tests.test_graphics_chatter_adapter import (
    frozen_chatter as frozen_chatter,  # noqa: PLC0414
)

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


def personalized(row, source_locale="en", group="rest"):
    for code in ("en", "ja", "zh-CN"):
        Language.objects.get_or_create(pk=code.split("-")[0])
        Locale.objects.get_or_create(pk=code, defaults={"language_id": code.split("-")[0]})
    row.source_locale_id, row.editorial_group = source_locale, group
    row.save(update_fields=["source_locale", "editorial_group"])
    run = row.run
    cfg = EditorialConfig.model_validate(run.config_snapshot["editorial"])
    cfg = cfg.model_copy(update={"chatter": cfg.chatter.model_copy(update={"enabled": True}),
                                "voices": {key: value for key, value in cfg.voices.items() if not key.startswith("chatter:") or key == "chatter:en"}, "locale_routes": {}})
    run.scope_key, run.workflow_version = TRENDS_SCOPE, workflow_version()
    run.config_snapshot["editorial"] = cfg.model_dump(mode="json")
    run.save(update_fields=["scope_key", "workflow_version", "config_snapshot"])
    return cfg


def fake_copy(locale="en", used=("F01-Q",)):
    def transport(endpoint, key, body, **kwargs):
        assert "copy-proposals/v3" in body["messages"][1]["content"]
        return 200, json.dumps({"model": body["model"], "usage": {}, "choices": [
            {"finish_reason": "stop", "message": {"content": json.dumps(copy_result(locale, used))}}]}).encode()
    return transport


@pytest.mark.parametrize("source_locale,group", [(lang, group) for lang in ("en", "ja", "zh-CN") for group in ("giant", "rest")])
def test_personalized_handoff_c1_text_is_readable_before_any_graphics_call(frozen_chatter, monkeypatch, source_locale, group):
    from monitor.editorial.chatter_chain import (
        _incumbents,
        select_chatter,
        write_chatter,
    )
    from monitor.editorial.readers import feed_payload, find_saved_edition

    row, physical, _ = frozen_chatter
    cfg = personalized(row, source_locale, group)
    monkeypatch.setenv("ORIGINAL_CONTENT_STORAGE", "shared")
    sends = []
    monkeypatch.setattr("monitor.editorial.graphics_dispatch.dispatch_creation", lambda **kwargs: sends.append(kwargs) or True)
    queued = []
    from tests.test_chatter_chain import wire
    from tests.test_chatter_discovery import selection

    def selector(endpoint, key, body, **kwargs):
        payload = json.loads(body["input"][1]["content"])
        result = selection(payload["candidates"][0])
        target = f"{source_locale.casefold()}-{group}"
        tag = result["candidate_tags"][0]
        tag.update(dominant_source_language=source_locale.casefold(), editorial_group=group,
                   pool_ref=target, group_policy_ref=payload["giant_group_policy"]["policy_ref"],
                   group_evidence_post_ids=["98001"])
        lead = next(item.copy() for item in result["group_decisions"] if item["scope_ref"] == "en-rest")
        for item in result["group_decisions"]:
            if item["scope_ref"] == target:
                item.update({key: value for key, value in lead.items() if key != "scope_ref"})
            else:
                item.update(ranked_candidates=[], lead_action="none", lead_ref=None)
        return wire(result)

    monkeypatch.setenv("XAI_API_KEY_PW", "fixture")
    result = select_chatter(row.run_id, cfg=cfg, transport=selector, enqueue=lambda *args: queued.append(args))
    assert result["status"] == "selected", result
    assert not queued, "personalized lane must materialize Graphics rather than queue the legacy writer"
    package = OriginalContent.objects.get(output_key="graphics-primary/v1")
    assert (package.development_id, package.source_locale_id, package.editorial_group) == (row.development_id, source_locale, group)
    assert package.consideration_state is None
    row.run.refresh_from_db()
    assert not row.run.outcome.get("healthy_at")
    # A redelivered legacy task is also routed to the same package, never to the old writer.
    assert write_chatter(row.pk, "en", cfg=cfg)["status"] in {"queued", "pending_dispatch"}
    assert OriginalContent.objects.filter(output_key="graphics-primary/v1").count() == 1
    result = advance_step(package.run_id, keys={"OPENAI_API_KEY": "fixture-only"}, transport=fake_copy())
    text = package.localized_texts.get(locale="en")
    assert result["stage"] == "C1" and result["text_id"] == text.pk
    assert pending_action(package.run_id) == {"action": "advance"}
    assert not OriginalContentCall.objects.filter(run=package.run).exclude(stage__endswith=":C1").exists()
    assert not OriginalContentCall.objects.filter(run=row.run, stage__startswith="writer:").exists()
    scope = featured_scope("social-brief", "en", source_locale=source_locale, editorial_group=group)
    assert OriginalContentSelection.objects.get(scope_key=scope).text_id == text.pk
    assert feed_payload(cfg, track="chatter", locale="en", source_locale=source_locale, editorial_group=group)["hero"]["headline"] == "Testing Times"
    assert find_saved_edition(row.story_id, "chatter", locale="en", pinned=text.public_id).pk == text.public_id
    assert _incumbents()[f"{source_locale.casefold()}-{group}"].pk == row.pk
    assert list(text.sources.values_list("post_id", "snapshot_run_id")) == [("98001", physical.run_id)]
    row.run.refresh_from_db()
    assert row.run.outcome["writers"] == {f"{row.pk}:en": "published"}
    assert row.run.outcome["healthy_at"] and row.run.execution_state == "completed"
    assert not row.localized_texts.exists()
    assert OriginalContent.objects.filter(development=row.development, consideration_state__isnull=False).count() == 1


def test_trusted_chatter_graphics_uses_aggregate_trial_and_bypasses_routine_daily_stop(frozen_chatter, monkeypatch):
    from monitor.editorial.chatter_accounting import budget_scope, spent
    from monitor.editorial.graphics_packages import materialize_package

    row, _, _ = frozen_chatter
    cfg = personalized(row)
    monkeypatch.setenv("ORIGINAL_CONTENT_STORAGE", "shared")
    run, _ = materialize_package(prepared(row))
    outcome = advance_step(run.pk, keys={"OPENAI_API_KEY": "fixture-only"}, transport=fake_copy(), configured_daily_limit=0)
    assert outcome["state"] == "completed"
    call = OriginalContentCall.objects.get(run=run)
    assert call.budget_scope == budget_scope(cfg)
    assert spent(cfg) == call.reserved_usd + Decimal(str(cfg.chatter.trial.carry_usd))


def test_hourly_healthy_evaluation_has_three_hour_delay_window(frozen_chatter):
    from monitor.editorial.chatter_status import delay_status

    row, _, _ = frozen_chatter
    personalized(row)
    now = timezone.now()
    row.run.outcome = {"healthy_at": (now - timedelta(hours=2, minutes=59)).isoformat(), "phase": "complete", "selected": 0}
    row.run.save(update_fields=["outcome"])
    assert not delay_status(now)["delayed"]
    assert delay_status(now + timedelta(minutes=1))["delayed"]


def add_document(row, tmp_path):
    from core.event_dossiers import create_dossier, identity_key
    from core.models import CollectionObservation, EventDossierSource
    from monitor.editorial import chatter_history as history
    from tests.test_product_release_documents import captured_document

    receipt, _, options = captured_document(tmp_path)
    event = create_dossier(event_kind="product_release", identity_key=identity_key("test", "publication-doc"))
    document = EventDossierSource.objects.create(event_dossier=event,
        collection_observation=CollectionObservation.objects.get(pk=receipt["observation_id"]))
    source = {"kind": "dossier_source", "id": f"dossier-source:{document.pk}",
              "dossier_source_id": document.pk, "url": options["url"],
              "original_text": "The publisher confirms invitation-only access.",
              "created_at": None, "observed_at": row.run.facts_as_of.isoformat(),
              "author_handle": "document publisher"}
    history.freeze_sources(row.run, [source], fence=row.run.fence)
    history.attach_sources(row, [source["id"]], usage="background", fence=row.run.fence)
    return document, source


def test_actual_publisher_cites_only_used_background_document_without_fabricating_post(frozen_chatter, tmp_path, monkeypatch):
    from core.models import Post
    from monitor.editorial.graphics_packages import materialize_package
    from monitor.original_content import digest

    row, _, _ = frozen_chatter
    personalized(row)
    document, source = add_document(row, tmp_path)
    monkeypatch.setenv("ORIGINAL_CONTENT_STORAGE", "shared")
    run, output = materialize_package(prepared(row))
    outcome = advance_step(run.pk, keys={"OPENAI_API_KEY": "fixture-only"}, transport=fake_copy(used=("F03",)))
    assert outcome["text_id"] == output.localized_texts.get().pk
    assert list(output.localized_texts.get().sources.values_list("post_id", "dossier_source_id", "snapshot_run_id", "source_hash")) == [
        (None, document.pk, row.run_id, digest(run.snapshot["request"]["sources"][-1]))]
    assert not Post.objects.filter(pk=source["id"]).exists()


def media_transport(copy, *, first_image_status=200):
    import base64
    import io

    from PIL import Image

    discovery = {"schema_version": "graphics-discovery/v3", "queries": [], "preferred_sites": [],
        "reuse_asset_refs": [], "approaches": [{"candidate_id": label, "approach": "original_visual_concept",
        "reason": "Original idea.", "reference_target": None} for label in ("A", "B")]}
    design = {"schema_version": "graphics-treatments/v2", "source_gaps": [], "treatments": [
        {"candidate_id": label, "idea": "A graphic.", "why_it_bites": "A joke.", "input_asset_refs": [],
         "aspect_ratio": "1:1", "still_prompt": "Draw it.", "motion_prompt": "Move it."} for label in ("A", "B")]}
    outputs = iter([copy, discovery, design])
    data = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(data, format="PNG")
    images = []

    def transport(endpoint, key, body, **kwargs):
        if "/images/" in endpoint:
            images.append(body)
            if len(images) == 1 and first_image_status != 200:
                return first_image_status, b"{}"
            return 200, json.dumps({"data": [{"b64_json": base64.b64encode(data.getvalue()).decode()}],
                "usage": {"cost_in_usd_ticks": 600000000}}).encode()
        return 200, json.dumps({"model": body["model"], "usage": {"cost": "0.01"}, "choices": [
            {"finish_reason": "stop", "message": {"content": json.dumps(next(outputs))}}]}).encode()
    return transport, images


@pytest.mark.parametrize("image_status", [200, 400, 503])
def test_text_survives_pending_art_then_matching_still_or_one_definite_fallback(frozen_chatter, monkeypatch, editorial_storage, image_status):
    from core.models import ContentPicture
    from monitor.editorial.graphics_packages import (
        claim_package,
        materialize_package,
        release_package,
    )
    from monitor.editorial.graphics_pipeline import review_step
    from monitor.editorial.graphics_video import submit_video_job
    from monitor.editorial.readers import feed_payload, find_saved_edition

    row, _, _ = frozen_chatter
    cfg = personalized(row, "ja", "giant")
    monkeypatch.setenv("ORIGINAL_CONTENT_STORAGE", "shared")
    run, output = materialize_package(prepared(row))
    transport, images = media_transport(copy_result(), first_image_status=image_status)
    keys = {"OPENAI_API_KEY": "fixture", "OPENROUTER_API_KEY": "fixture", "XAI_API_KEY_PW": "fixture"}
    first = advance_step(run.pk, keys=keys, transport=transport)
    primary = output.localized_texts.get()
    assert first["text_id"] == primary.pk and not ContentPicture.objects.filter(run=run).exists()
    stages = [advance_step(run.pk, keys=keys, transport=transport)["stage"] for _ in range(4)]
    assert stages == ["G0", "source_lookup", "G1", "I-A"]
    assert pending_action(run.pk)["action"] in {"advance", "review"}
    if image_status == 400:
        assert advance_step(run.pk, keys=keys, transport=transport)["stage"] == "I-B"
        result = advance_step(run.pk, keys=keys, transport=transport)
        assert result["stage"] == "fallback"
        text = OriginalContentSelection.objects.get(scope_key="featured:social-brief:ja:giant:en").text
        assert text.headline == "Preview View" and text.pk != primary.pk
        assert (text.narrative.development_id, text.narrative.source_locale_id, text.narrative.editorial_group) == (row.development_id, "ja", "giant")
        assert len(images) == 2
    elif image_status == 503:
        assert pending_action(run.pk)["action"] == "review"
        assert advance_step(run.pk, keys=keys, transport=transport)["stage"] == "waiting"
        assert len(images) == 1
        text = primary
    else:
        result = advance_step(run.pk, keys=keys, transport=transport)
        assert result["next_action"] == "video"
        picture = ContentPicture.objects.get(run=run, provenance__role="still")
        assert picture.text_id == primary.pk
        assert len(images) == 1
        text = primary
    from monitor.editorial.graphics_status import graphics_status
    assert graphics_status(run.pk)["text_id"] == text.pk
    assert find_saved_edition(row.story_id, "chatter", locale="en", pinned=primary.public_id).pk == primary.public_id
    hero = feed_payload(cfg, source_locale="ja", editorial_group="giant")["hero"]
    assert hero["id"] == str(text.public_id)
    if image_status != 503:
        claim = claim_package(run.pk, owner="video-test")
        submission = submit_video_job(run.pk, text.pk, owner=claim.owner, fence=claim.fence,
            api_key="fixture", transport=lambda *args, **kwargs: (200, b'{"request_id":"saved-job"}'))
        release_package(run.pk, owner=claim.owner, fence=claim.fence)
        assert submission["state"] == "pending"
        assert ContentPicture.objects.get(pk=submission["job_id"]).text_id == text.pk
        assert review_step(run.pk, keys={})["state"] == "waiting_for_media"
        assert feed_payload(cfg, source_locale="ja", editorial_group="giant")["hero"]["id"] == str(text.public_id)
        if image_status == 400:
            from tests.test_chatter_pool_readers import published

            newer = published("giant", "98995")
            OriginalContentSelection.objects.filter(scope_key="featured:social-brief:ja:giant:en").update(text=newer)
            assert graphics_status(run.pk)["text_id"] == text.pk
            assert pending_action(run.pk)["action"] == "poll"


def test_pool_video_ownership_rejects_new_submission_after_pointer_changes(frozen_chatter, monkeypatch):
    from monitor.editorial.graphics_packages import materialize_package
    from monitor.editorial.graphics_video import _current
    from tests.test_chatter_pool_readers import published

    row, _, _ = frozen_chatter
    personalized(row, "ja", "giant")
    monkeypatch.setenv("ORIGINAL_CONTENT_STORAGE", "shared")
    run, output = materialize_package(prepared(row))
    advance_step(run.pk, keys={"OPENAI_API_KEY": "fixture"}, transport=fake_copy())
    primary = output.localized_texts.get()
    assert _current(primary)
    newer = published("giant", "98999")
    OriginalContentSelection.objects.filter(scope_key="featured:social-brief:ja:giant:en").update(text=newer)
    assert not _current(primary), "the current edition is determined within its source pool"


@pytest.mark.parametrize("cap", ["trial", "package"])
def test_trusted_origin_preserves_aggregate_trial_and_per_package_caps(frozen_chatter, monkeypatch, cap):
    from monitor.editorial.graphics_packages import materialize_package

    row, _, _ = frozen_chatter
    cfg = personalized(row)
    if cap == "trial":
        cfg = cfg.model_copy(update={"chatter": cfg.chatter.model_copy(update={
            "trial": cfg.chatter.trial.model_copy(update={"limit_usd": cfg.chatter.trial.carry_usd + 0.001})})})
        row.run.config_snapshot["editorial"] = cfg.model_dump(mode="json")
        row.run.save(update_fields=["config_snapshot"])
    request = prepared(row)
    if cap == "package":
        from monitor.editorial.graphics_entry import prepare_selected_story
        request = prepare_selected_story(content_id=row.pk, run_id=row.run_id, locale="en", per_story_usd="0.001")
    run, _ = materialize_package(request)
    result = advance_step(run.pk, keys={"OPENAI_API_KEY": "fixture"},
        transport=lambda *args, **kwargs: pytest.fail("a preserved cap must stop transport"), configured_daily_limit=0)
    assert result["state"] == "budget_or_capacity_unavailable"
    assert not OriginalContentCall.objects.filter(run=run).exists()


@pytest.mark.parametrize("forgery", ["flags", "binding"])
def test_caller_json_cannot_forge_the_trusted_origin_exception(forgery):
    from monitor.editorial.graphics_pipeline import advance_step
    from tests.test_graphics_pipeline import selected_run

    run, _ = selected_run()
    run.snapshot["request"]["budget_scope"] = "chatter"
    run.snapshot["request"]["chatter_origin"] = True
    run.save(update_fields=["snapshot"])
    if forgery == "binding":
        run.snapshot["request"]["chatter"] = {"schema_version": "graphics-chatter-source/v1",
            "source_content_id": run.snapshot["request"]["content_id"], "source_run_id": run.snapshot["request"]["run_id"]}
        run.save(update_fields=["snapshot"])
        with pytest.raises(ValueError, match="origin"):
            advance_step(run.pk, keys={"OPENROUTER_API_KEY": "fixture"},
                transport=lambda *args, **kwargs: pytest.fail("forged origin cannot dispatch"), configured_daily_limit=0)
    else:
        result = advance_step(run.pk, keys={"OPENROUTER_API_KEY": "fixture"},
            transport=lambda *args, **kwargs: pytest.fail("caller flags cannot bypass daily admission"), configured_daily_limit=0)
        assert result["state"] == "budget_or_capacity_unavailable"
    assert not OriginalContentCall.objects.filter(run=run).exists()


def test_chatter_actual_cost_and_unsent_refund_adjust_the_aggregate_once(frozen_chatter):
    from core.models import EditorialBudget
    from monitor.editorial.chatter_accounting import spent
    from monitor.editorial.graphics_packages import claim_package, materialize_package
    from monitor.editorial.persistence import (
        complete_graphics_call,
        fail_graphics_presend_call,
    )
    from monitor.original_content import digest
    from monitor.trend_narrative_lifecycle import (
        mark_trend_narrative_provider_call_sent,
    )
    from tests.test_graphics_accounting import reserve

    row, _, _ = frozen_chatter
    cfg = personalized(row)
    run, _ = materialize_package(prepared(row))
    claim_package(run.pk, owner="worker")
    call, may_send = reserve(run, configured_daily_limit=0)
    assert may_send and mark_trend_narrative_provider_call_sent(call.pk, owner="worker", fence=call.claim_fence, now=timezone.now())
    completion = {"owner": "worker", "fence": call.claim_fence, "response_hash": digest({"saved": True}),
        "response_payload": {"saved": True}, "actual_usd": "0.05"}
    assert complete_graphics_call(call.pk, **completion)
    assert complete_graphics_call(call.pk, **completion)
    assert spent(cfg) == Decimal("0.05") + Decimal(str(cfg.chatter.trial.carry_usd))
    unsent, _ = reserve(run, "G0", configured_daily_limit=0)
    assert fail_graphics_presend_call(unsent.pk, owner="worker", fence=unsent.claim_fence, error_code="pre_send:request_reconstruction")
    assert fail_graphics_presend_call(unsent.pk, owner="worker", fence=unsent.claim_fence, error_code="pre_send:request_reconstruction")
    assert spent(cfg) == Decimal("0.05") + Decimal(str(cfg.chatter.trial.carry_usd))
    assert not EditorialBudget.objects.exists()


def test_newer_pool_pointer_survives_late_primary_and_older_copy_remains_pinnable(frozen_chatter, monkeypatch):
    from monitor.editorial.graphics_packages import materialize_package
    from monitor.editorial.readers import find_saved_edition
    from tests.test_chatter_pool_readers import published

    row, _, _ = frozen_chatter
    personalized(row)
    monkeypatch.setenv("ORIGINAL_CONTENT_STORAGE", "shared")
    run, output = materialize_package(prepared(row))
    newer = published("rest", "98997")
    result = advance_step(run.pk, keys={"OPENAI_API_KEY": "fixture"}, transport=fake_copy())
    text = output.localized_texts.get()
    assert result["text_id"] == text.pk
    assert OriginalContentSelection.objects.get(scope_key="featured:social-brief:en:rest:en").text_id == newer.pk
    assert find_saved_edition(row.story_id, "chatter", locale="en", pinned=text.public_id).pk == text.public_id


@pytest.mark.django_db(transaction=True)
def test_c1_copy_reaches_real_anonymous_general_and_pinned_story_before_media(frozen_chatter, live_server, monkeypatch, settings):
    from playwright.sync_api import sync_playwright

    from core.models import ContentPicture
    from monitor.editorial.graphics_packages import materialize_package

    row, _, _ = frozen_chatter
    cfg = personalized(row, "ja", "giant")
    monkeypatch.setenv("ORIGINAL_CONTENT_STORAGE", "shared")
    settings.SECURE_SSL_REDIRECT = False
    settings.ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]
    monkeypatch.setattr("monitor.editorial.views.load_editorial_config", lambda: cfg)
    run, output = materialize_package(prepared(row))
    advance_step(run.pk, keys={"OPENAI_API_KEY": "fixture"}, transport=fake_copy())
    text = output.localized_texts.get()
    assert not ContentPicture.objects.filter(run=run).exists()
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 390, "height": 844},
            extra_http_headers={"X-Forwarded-Proto": "https"})
        for lang in ("en", "ja", "zh-cn"):
            response = page.goto(live_server.url + f"/general/?lang={lang}&source_lang=ja&group=giant&edition_lang=en", wait_until="networkidle")
            assert response.status == 200
            headline = page.locator("#chatter .editorial-headline a")
            assert headline.count() == 1 and headline.is_visible()
            assert headline.inner_text() == text.headline
            assert page.locator("#chatter .editorial-body").inner_text() == text.body
            assert page.locator('#chatter [name="source_lang"]').input_value() == "ja"
            assert page.locator('#chatter [name="group"]').input_value() == "giant"
        link = page.locator("#chatter .editorial-headline a").get_attribute("href")
        page.goto(live_server.url + link, wait_until="networkidle")
        assert page.locator("h1").inner_text() == text.headline
        assert text.body in page.locator("main").inner_text()
        assert page.locator('a[href="https://x.com/i/status/98001"]').count() == 1
        assert str(text.public_id) in page.url
        browser.close()
    assert OriginalContentCall.objects.filter(run=run).count() == 1


def test_late_decoded_video_attaches_to_its_older_pinned_edition_without_moving_pool_pointer(frozen_chatter, monkeypatch, editorial_storage, tmp_path):
    import subprocess

    import imageio_ffmpeg

    from core.models import ContentPicture
    from monitor.editorial.graphics_packages import (
        claim_package,
        materialize_package,
        release_package,
    )
    from monitor.editorial.graphics_reading import graphics_assets
    from monitor.editorial.graphics_video import poll_video_job, submit_video_job
    from monitor.original_content_readers import saved_edition
    from tests.test_chatter_pool_readers import published

    row, _, _ = frozen_chatter
    personalized(row)
    monkeypatch.setenv("ORIGINAL_CONTENT_STORAGE", "shared")
    run, output = materialize_package(prepared(row))
    transport, _ = media_transport(copy_result())
    keys = {"OPENAI_API_KEY": "fixture", "OPENROUTER_API_KEY": "fixture", "XAI_API_KEY_PW": "fixture"}
    for _ in range(6):
        advance_step(run.pk, keys=keys, transport=transport)
    output.refresh_from_db()
    primary = output.localized_texts.get()
    claim = claim_package(run.pk, owner="video-test")
    submitted = submit_video_job(run.pk, primary.pk, owner=claim.owner, fence=claim.fence,
        api_key="fixture", transport=lambda *args, **kwargs: (200, b'{"request_id":"late-saved-job"}'))
    release_package(run.pk, owner=claim.owner, fence=claim.fence)
    newer = published("rest", "98996")
    video = tmp_path / "late-video.mp4"
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-f", "lavfi", "-i",
        "color=c=red:s=32x32:r=5:d=5", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", "-y", str(video)], check=True, capture_output=True)
    data = video.read_bytes()
    polled = poll_video_job(submitted["job_id"], api_key="fixture",
        transport=lambda *args, **kwargs: (200, b'{"status":"done","video":{"url":"https://example.test/video"},"usage":{"cost_in_usd_ticks":1600000000}}'),
        fetch=lambda *args, **kwargs: (data, "https://example.test/video", "video/mp4"))
    assert polled["state"] == "completed"
    job = ContentPicture.objects.get(pk=submitted["job_id"])
    assert job.state == "complete" and job.text_id == primary.pk
    assert job.provenance["decode_receipt"]["duration_ms"] == 5000
    assert OriginalContentSelection.objects.get(scope_key="featured:social-brief:en:rest:en").text_id == newer.pk
    assets = graphics_assets(saved_edition(primary))
    assert assets.video.pk == job.pk and assets.still.text_id == primary.pk
    assert OriginalContentCall.objects.filter(run=run, stage__endswith=":V1").count() == 1


@pytest.mark.parametrize("with_cast,image_status", [(True, 200), (False, 200), (True, 400), (True, "changed_cast_bytes")])
def test_rolling_edition_owns_one_writer_pitch_and_its_video_inputs(
    frozen_chatter, monkeypatch, editorial_storage, tmp_path, with_cast, image_status,
):
    import base64
    import hashlib

    from monitor.editorial.chatter_trends import DECISION_SCOPE, ROLLING_LANE
    from monitor.editorial.graphics_contracts import WRITER_LED
    from monitor.editorial.graphics_generation import REFERENCE_VIDEO_MODEL, VIDEO_MODEL
    from monitor.editorial.graphics_packages import (
        claim_package,
        materialize_package,
        release_package,
    )
    from monitor.editorial.graphics_video import submit_video_job
    from tests.editorial_support import person_photo
    from tests.test_chatter_pool_readers import published

    row, _, _ = frozen_chatter
    personalized(row, "en", "giant")
    person, _, photo = person_photo("Source Maker", photo=with_cast)
    subject = "Source Maker announces a preview"
    if image_status == "changed_cast_bytes":
        from core.models import Account
        from tests.test_person_identity import link

        link(person, Account.objects.create(author_id="97222", handle="sourcemaker", normalized_handle="sourcemaker"), "confirmed")
        subject = "@sourcemaker announces a preview"
    row.selection.update(subject=subject, source_identities=[{
        "post_id": "98001", "person_links": [{"person_id": str(person.pk), "role": "mentioned",
                                             "resolution_status": "confirmed"}]}])
    row.save(update_fields=["selection"])
    row.run.config_snapshot["editorial"]["chatter"]["discovery_lane"] = ROLLING_LANE
    row.run.scope_key = DECISION_SCOPE
    row.run.save(update_fields=["scope_key", "config_snapshot"])
    monkeypatch.setenv("ORIGINAL_CONTENT_STORAGE", "shared")
    run, output = materialize_package(prepared(row))
    copy = copy_result()
    motion = "The winner springs over the counter. Hold the headline on the last beat."
    copy.update(schema_version=WRITER_LED, candidates=[
        {**copy["candidates"][0], "still_pitch": "An illustrated counter.", "motion_prompt": motion}])
    fake, images = media_transport(copy, first_image_status=image_status)
    keys = {k: "fixture" for k in ("OPENAI_API_KEY", "OPENROUTER_API_KEY", "XAI_API_KEY_PW")}
    sent = []

    def transport(endpoint, key, body, **kwargs):
        sent.append(body)
        if len(sent) == 2:
            fake(endpoint, key, body, **kwargs)  # legacy fixture's unused G0
            status, raw = fake(endpoint, key, body, **kwargs)
            result = json.loads(raw)
            message = result["choices"][0]["message"]
            design = json.loads(message["content"])
            design["treatments"] = design["treatments"][:1]
            message["content"] = json.dumps(design)
            return status, json.dumps(result).encode()
        return fake(endpoint, key, body, **kwargs)

    assert advance_step(run.pk, keys=keys, transport=transport)["stage"] == "C1"
    text = output.localized_texts.get()
    assert text.headline == copy["candidates"][0]["headline"]
    if image_status == "changed_cast_bytes":
        from django.core.files.storage import storages

        assert advance_step(run.pk, keys=keys, transport=transport)["stage"] == "source_lookup"
        with storages["staff_media"].open(photo.media.storage_name, "wb") as stream:
            stream.write(b"changed")
        blocked = advance_step(run.pk, keys=keys, transport=transport)
        assert blocked["stage"] == "G1" and blocked["state"] == "skipped"
        assert list(output.localized_texts.values_list("pk", flat=True)) == [text.pk]
        assert len(sent) == 1
        return
    assert [advance_step(run.pk, keys=keys, transport=transport)["stage"] for _ in range(3)] == [
        "source_lookup", "G1", "I-A"]
    assert len(images) == 1
    if image_status == 400:
        assert pending_action(run.pk)["action"] == "review"
        assert not run.provider_calls.filter(stage__endswith=":I-B").exists()
        return

    assert advance_step(run.pk, keys=keys, transport=transport)["next_action"] == "video"
    newer = published("giant", "98995")
    assert OriginalContentSelection.objects.get(scope_key="featured:social-brief:en:giant:en").text_id == newer.pk
    claim = claim_package(run.pk, owner="rolling-video")
    video = []
    try:
        result = submit_video_job(run.pk, text.pk, owner=claim.owner, fence=claim.fence, api_key="fixture",
            transport=lambda _url, _key, body, **_kw: (video.append(body) or 200, b'{"request_id":"rolling-clip"}'))
    finally:
        release_package(run.pk, owner=claim.owner, fence=claim.fence)
    assert result["state"] == "pending"
    assert video[0]["prompt"].endswith(motion) and video[0]["duration"] == 5 and video[0]["resolution"] == "720p"
    assert video[0]["model"] == (REFERENCE_VIDEO_MODEL if with_cast else VIDEO_MODEL)
    if with_cast:
        writer_input = sent[0]["messages"][-1]["content"][1]["image_url"]["url"]
        identity = video[0]["reference_images"][0]["url"]
        assert identity == writer_input == images[0]["images"][0]["url"]
        assert hashlib.sha256(base64.b64decode(identity.split(",")[1])).hexdigest() == photo.media_id
        assert video[0]["image"]["url"] != identity
    else:
        assert "reference_images" not in video[0]
    assert not run.provider_calls.filter(stage__endswith=":G0").exists()
    import subprocess

    import imageio_ffmpeg

    from monitor.editorial.graphics_reading import graphics_assets
    from monitor.editorial.graphics_video import poll_video_job
    from monitor.editorial.readers import find_saved_edition

    movie = tmp_path / "archive.mp4"
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-f", "lavfi", "-i",
        "color=c=red:s=32x32:r=5:d=5", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-y", str(movie)],
        check=True, capture_output=True)
    polled = poll_video_job(result["job_id"], api_key="fixture",
        transport=lambda *_args, **_kw: (200, b'{"status":"done","video":{"url":"https://example.test/movie"}}'),
        fetch=lambda *_args, **_kw: (movie.read_bytes(), "https://example.test/movie", "video/mp4"))
    assert polled["state"] == "completed"
    edition = find_saved_edition(row.story_id, "chatter", locale="en", pinned=text.public_id)
    assets = graphics_assets(edition)
    assert assets.video.text_id == assets.still.text_id == text.pk
    assert assets.video.provenance["decode_receipt"]["input_still_sha256"] == assets.still.generated_sha256
