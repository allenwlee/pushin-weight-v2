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


@pytest.mark.parametrize("manual_scope", [False, True])
def test_late_decoded_video_attaches_to_its_older_pinned_edition_without_moving_pool_pointer(frozen_chatter, monkeypatch, editorial_storage, tmp_path, manual_scope):
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
    if manual_scope:
        row.run.scope_key = "chatter-retroactive-example"
        row.run.save(update_fields=["scope_key"])
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
    person_photo("Source Maker", photo=False)
    subject = "Source Maker announces a preview"
    if image_status == "changed_cast_bytes":
        from core.models import Account
        from tests.test_person_identity import link

        link(person, Account.objects.create(author_id="97222", handle="sourcemaker", normalized_handle="sourcemaker"), "confirmed")
        subject = "@sourcemaker announces a preview"
    row.selection.update(subject=subject, person_ids=[str(person.pk)], source_identities=[{
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

    if not with_cast:
        first = advance_step(run.pk, keys=keys, transport=transport)
        assert first["state"] == "awaiting_portrait" and not sent
        # The missing portrait cannot block publication once its first deadline passes.
        later = timezone.now() + timedelta(seconds=21)
        monkeypatch.setattr(timezone, "now", lambda: later)
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


def test_same_event_lookup_finds_old_editions_across_disjoint_sources_and_story_ids(frozen_chatter):
    from uuid import uuid4

    from core.models import OriginalContentText
    from monitor.editorial.chatter_coverage import previous_coverage
    from tests.test_original_content_consideration import consideration

    row, _, sources = frozen_chatter
    row.selection = {"people": ["Jensen Huang"], "subject": "Nvidia board reinstates Jensen Huang"}
    earlier = row.run.facts_as_of - timedelta(days=2)
    for title, angle in [
        ("HUANG IN THERE!", "Jensen Huang was reinstated by the Nvidia board."),
        ("PARDON MY FRENCH, MENSCH!", "Jensen Huang sparred with Arthur Mensch at GTC."),
    ]:
        old = consideration(consideration_state="selected", selection={"subject": angle},
                            status="approved", published_at=earlier, verified_at=earlier)
        OriginalContentText.objects.create(narrative=old, public_id=uuid4(), locale="en",
                                          headline=title, secondary=angle, body=angle)
    coverage = previous_coverage(row, sources)
    assert {edition["headline"] for edition in coverage["editions"]} == {
        "HUANG IN THERE!", "PARDON MY FRENCH, MENSCH!"}
    assert all(edition["story_id"] != str(row.development_id) for edition in coverage["editions"])


@pytest.mark.parametrize("scenario", ["recap", "recap_passed", "recap_kept", "first_different_event", "followup", "same_headline",
                                       "resume_same_headline", "cited_but_missing"])
def test_rolling_selector_and_writer_replay_jensen(frozen_chatter, monkeypatch, scenario):
    from datetime import datetime
    from pathlib import Path
    from uuid import UUID

    from core.models import EventDossier, EventDossierClaim, OriginalContentText, Post
    from monitor.editorial import chatter_history, graphics_pipeline
    from monitor.editorial.chatter_chain import (
        reconcile_chatter_graphics,
        select_chatter,
    )
    from monitor.editorial.chatter_inputs import reconstruct_selection_request
    from monitor.editorial.chatter_trends import DECISION_SCOPE, ROLLING_LANE
    from monitor.editorial.graphics_contracts import WRITER_LED
    from monitor.editorial.graphics_packages import materialize_package
    from monitor.editorial.readers import find_saved_edition
    from tests.test_chatter_chain import wire
    from tests.test_chatter_discovery import selection
    from tests.test_original_content_consideration import consideration

    fixture = json.loads((Path(__file__).parent / "fixtures/chatter_jensen_continuation.json").read_text())
    row, _, _ = frozen_chatter
    cfg = personalized(row)
    cfg = cfg.model_copy(update={"chatter": cfg.chatter.model_copy(update={"discovery_lane": ROLLING_LANE})})
    run = row.run
    run.scope_key, run.workflow_version = DECISION_SCOPE, workflow_version(ROLLING_LANE)
    run.config_snapshot["editorial"] = cfg.model_dump(mode="json")
    cutoff = datetime.fromisoformat("2026-11-25T04:32:00+00:00")
    run.facts_as_of = cutoff
    recap = scenario.startswith("recap")
    run.outcome = {"event_coverage_version": 1, "incumbent_refs": {"en-rest": str(row.development_id)} if scenario == "recap_kept" else {}}
    run.save(update_fields=["scope_key", "workflow_version", "config_snapshot", "outcome", "facts_as_of"])
    old = []
    for edition in fixture["prior"]:
        when = datetime.fromisoformat(edition["published"])
        # An older filing used another story ID. Both pinned URLs must survive.
        parent = consideration(consideration_state="selected", selection={"subject": edition["secondary"]},
            status="approved", published_at=when, verified_at=when)
        original = OriginalContentText.objects.create(narrative=parent, locale="en", headline=edition["headline"],
            secondary=edition["secondary"], body=edition["body"], public_id=UUID(edition["public_id"]))
        old.append(original)
    different = scenario == "first_different_event"
    if recap:
        subject = fixture["meme_pitch"]
        item = fixture["recap"]
        passage = item["text"].split("\n")[-1].removeprefix("- ")
    elif different:
        subject = "Jensen Huang and Arthur Mensch trade barbs at GTC"
        item = {"source_id": "2125048000000000000", "speaker": "reporter", "created_at": cutoff.isoformat(),
                "text": "At the GTC panel Jensen Huang asked Arthur Mensch about his answer in French."}
        passage = item["text"]
    else:
        subject = "Employees cheer Jensen Huang at Nvidia headquarters"
        reaction = fixture["reaction"]
        item = {"source_id": reaction["id"], "speaker": reaction["handle"], "text": reaction["text"],
                "created_at": reaction["created_at"]}
        passage = item["text"].split("\n")[0]
    post = Post.objects.create(tweet_id=item["source_id"], text=item["text"], created_at=datetime.fromisoformat(item["created_at"]),
                               author_handle=item["speaker"], lang="en")
    if recap:
        from core.event_dossiers import create_dossier, identity_key
        from core.models import EventDossierSource
        release = create_dossier(event_kind="product_release", identity_key=identity_key("test", "GLM-5.4"),
                                 first_seen_at=cutoff - timedelta(hours=1))
        EventDossierSource.objects.create(event_dossier=release, post=post, linked_at=cutoff - timedelta(minutes=5))
    source = chatter_history.project_post(post)
    if recap:
        source["source_language"] = "und"  # Source-language grounding is still required.
    chatter_history.freeze_sources(run, [source], fence=run.fence)
    chatter_history.attach_sources(row, [post.pk], fence=run.fence)
    row.selection = {"subject": subject, "people": ["Jensen Huang"], "angle": subject, "episode_id": "this-event"}
    row.save(update_fields=["selection"])
    transports = []
    def selector(endpoint, key, body, **kwargs):
        transports.append(body)
        payload = json.loads(body["input"][1]["content"])
        candidate, = payload["candidates"]
        assert "What can we tell a reader" in body["input"][0]["content"]
        editions = candidate["event_history"]["editions"]
        assert {e["headline"] for e in editions} == {t.headline for t in old}
        if recap:
            assert [d["dossier_id"] for d in candidate["event_history"]["dossiers"]] == [str(release.pk)]
        reply = selection(candidate)
        reply["candidate_tags"][0].update(group_policy_ref=payload["giant_group_policy"]["policy_ref"],
                                           group_evidence_post_ids=[post.pk])
        evidence = {"source_id": post.pk, "excerpt": passage}
        assignment = {"reader_gets": "CNN-News18 reports cheers and Huang's promise to be a better CEO.",
                      "support": evidence, "source_detail": "better CEO", "detail_words": {"en": ["cheer", "apolog", "better CEO"]}}
        if recap:  # A real citation cannot make this market estimate evidence of a meme.
            assignment.update(reader_gets="A new AI meme about Huang is spreading.", source_detail="meme",
                              detail_words={"en": ["meme", "parody"]})
        if scenario in {"recap_passed", "recap_kept"}:
            group = next(g for g in reply["group_decisions"] if g["scope_ref"] == "en-rest")
            group["ranked_candidates"][0]["outcome"] = "passed_over"
            incumbent = candidate["candidate_ref"] if scenario == "recap_kept" else None
            group.update(lead_action="keep" if incumbent else "none", incumbent_ref=incumbent, lead_ref=incumbent)
        reply["event_comparisons"] = [{"candidate_ref": candidate["candidate_ref"],
            "kind": "human_interest" if different else "personnel_change", "participants": ["Jensen Huang", "Nvidia"],
            "action": "GTC panel exchange" if different else "reinstate CEO", "occasion": "2026-11-23",
            "same_editions": [] if different else [e["edition_id"] for e in editions],
            "same_dossier": None, "passages": [evidence], "assignment": None if different else assignment}]
        return wire(reply, cfg.chatter.selector.model)

    monkeypatch.setenv("ORIGINAL_CONTENT_STORAGE", "shared")
    monkeypatch.setenv(cfg.chatter.selector.key_env, "fixture-only")
    dispatches = []
    monkeypatch.setattr("monitor.editorial.graphics_dispatch.dispatch_creation", lambda **kw: dispatches.append(kw) or True)
    monkeypatch.setattr(graphics_pipeline, "prepare_person_cast", lambda _saved, _selection, started, **_kw:
                        {"subjects": [], "gaps": [], "started_at": started.isoformat()})
    selected = select_chatter(run.pk, cfg=cfg, transport=selector, enqueue=lambda *args: None)
    assert selected.get("selected") == (0 if recap else 1), selected
    run.refresh_from_db()
    assert len(transports) == 1 and reconstruct_selection_request(run.provider_calls.get(stage="selector:0")) == transports[0]
    if recap:
        assert not dispatches and not OriginalContent.objects.filter(output_key="graphics-primary/v1").exists()
        claim = EventDossierClaim.objects.get(source_excerpt=passage)
        assert claim.effective_at == post.created_at and item["speaker"] in claim.assertion_text
        assert run.outcome["covered_episode_ids"] == ["this-event"]
        assert claim.event_dossier_source.event_dossier_id != release.pk
        assert not release.sources.get().claims.exists()
        assert claim.event_dossier_source.event_dossier.current_review is None
        assert claim.event_dossier_source.event_dossier.editorial_development.pk == old[0].narrative.development_id
        return
    package = OriginalContent.objects.get(output_key="graphics-primary/v1")
    assert package.run.snapshot["request"]["handoff"]["poster_treatment"] == "original-artwork/v1"
    sent = []
    def writer(endpoint, key, body, **kwargs):
        sent.append(body)
        message = body["messages"][1]["content"]
        if different:
            assert "You're writing the next" not in message
            fact_id, title, byline, article = "F03", "PARDON MY FRENCH, MENSCH!", "A question in French.", passage
        else:
            assert message.startswith("You're writing the next Chatter piece")
            assert "HUANG IN THERE!" in message and "RETURN OF THE JENSEN?" in message and passage in message
            handoff = json.JSONDecoder().raw_decode(message.split("\n\nSUPPLIED INPUTS:\n")[1])[0]
            lead = handoff["fact_items"][0]
            assert lead["supporting_passage"] == passage and lead["speaker"] == "CNNnews18"
            assert all(f["edition_role"] == "background" for f in handoff["fact_items"][1:])
            fact_id = lead["fact_id"]
            positive = fixture["positive_copy"]
            title = "  huang IN there?" if "same_headline" in scenario else positive["headline"]
            byline, article = positive["byline"], positive["article"]
            if scenario == "cited_but_missing":
                byline, article = old[0].secondary, old[0].body
        response = copy_result(used=[fact_id])
        response.update(schema_version=WRITER_LED, article=article, candidates=[{
            **response["candidates"][0], "headline": title, "byline": byline, "still_pitch": "One scene.",
            "motion_prompt": "One movement."}])
        return 200, json.dumps({"model": body["model"], "usage": {}, "choices": [
            {"finish_reason": "stop", "message": {"content": json.dumps(response)}}]}).encode()

    if scenario == "resume_same_headline":
        with monkeypatch.context() as paused:
            def interruption(*_args):
                raise RuntimeError("worker interrupted after C1")
            paused.setattr(graphics_pipeline, "_publish_chatter_copy", interruption)
            with pytest.raises(RuntimeError, match="interrupted"):
                advance_step(package.run_id, keys={"OPENAI_API_KEY": "fixture"}, transport=writer)
    result = advance_step(package.run_id, keys={"OPENAI_API_KEY": "fixture"}, transport=writer)
    row.refresh_from_db()
    run.refresh_from_db()
    assert all("article" not in prior and "cited_passages" not in prior for prior in row.selection["event_coverage"]["prior"])
    assert len(sent) == 1
    assert list(package.run.provider_calls.values_list("stage", flat=True)) == [f"gfx:{package.run_id}:C1"]
    if scenario in {"followup", "first_different_event"}:
        edition = package.localized_texts.get()
        package.refresh_from_db()
        assert result["text_id"] == edition.pk
        assert package.development.event_dossier.event_kind_reference.code == ("human_interest" if different else "personnel_change")
        assert find_saved_edition(package.story_id, "chatter", locale="en", pinned=edition.public_id).pk == edition.public_id
        assert package.story_id == (row.story_id if different else old[0].narrative.story_id)
        assert materialize_package(prepared(row))[0].pk == package.run_id
        assert edition.sources.get().post_id == post.pk
    else:
        assert result["state"] == "repeat" and not package.localized_texts.exists()
        assert pending_action(package.run_id) is None and run.outcome["writers"][f"{row.pk}:en"] == "repeat"
        assert reconcile_chatter_graphics(run)
    for original in old:
        assert find_saved_edition(original.narrative.story_id, "chatter", locale="en", pinned=original.public_id).pk == original.public_id
    assert EventDossier.objects.count() == 1


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("same_episode", [True, False])
def test_two_workers_publishing_first_chatter_event_converge(frozen_chatter, monkeypatch, same_episode):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from django.db import connections

    from core.event_dossiers import identity_key
    from core.models import EventDossier, OriginalContentText, Post
    from monitor.editorial import chatter_history
    from monitor.editorial.graphics_packages import materialize_package
    from tests.test_original_content_consideration import consideration

    first, _, sources = frozen_chatter
    personalized(first)
    second = consideration(consideration_state="selected")
    second.run.config_snapshot = first.run.config_snapshot
    second.run.scope_key, second.run.workflow_version = first.run.scope_key, first.run.workflow_version
    second.run.save(update_fields=["config_snapshot", "scope_key", "workflow_version"])
    text = "A second source reports the same panel exchange."
    post = Post.objects.create(tweet_id="98003", text=text, created_at=second.run.facts_as_of, author_handle="other")
    chatter_history.freeze_sources(second.run, [chatter_history.project_post(post)], fence=second.run.fence)
    chatter_history.attach_sources(second, [post.pk], fence=second.run.fence)
    episode = "ranked-gtc-panel-episode"
    packages = []
    for row, identity, excerpt in [(first, "98001", sources[0]["original_text"]), (second, post.pk, text)]:
        row.selection = {**row.selection, "episode_id": episode if same_episode or row == first else "other-event", "people": ["Jensen Huang"],
                         "event_coverage": {"kind": "human_interest",
            "identity": identity_key("test", "GTC audience Q&A" if row == first else "conference panel exchange"),
            "same_dossier": None, "prior": [], "assignment": None, "passages": [{"source_id": identity, "excerpt": excerpt}]}}
        row.save(update_fields=["selection"])
        packages.append(materialize_package(prepared(row))[0].pk)
    monkeypatch.setenv("ORIGINAL_CONTENT_STORAGE", "shared")
    both_sent = Barrier(2)
    def publish(package_id):
        try:
            def writer(endpoint, key, body, **kw):
                both_sent.wait(timeout=10)
                copy = copy_result(used=["F01"])
                # Different words for the same first admission must still converge.
                copy["candidates"][0]["headline"] += str(package_id)
                return 200, json.dumps({"model": body["model"], "usage": {}, "choices": [
                    {"finish_reason": "stop", "message": {"content": json.dumps(copy)}}]}).encode()
            return advance_step(package_id, keys={"OPENAI_API_KEY": "fixture"}, transport=writer)
        finally:
            connections.close_all()
    with ThreadPoolExecutor(max_workers=2) as threads:
        results = list(threads.map(publish, packages))
    assert sorted(result["state"] for result in results) == ["completed", "repeat" if same_episode else "reconsider"]
    winner = first if results[0]["state"] == "completed" else second
    event = EventDossier.objects.get(identity_key=identity_key("chatter-episode-v1", winner.selection["episode_id"]))
    if not same_episode:
        deferred = second if winner == first else first
        deferred.run.refresh_from_db()
        assert deferred.run.outcome["writers"][f"{deferred.pk}:en"] == "reconsider"
        assert not deferred.run.outcome.get("covered_episode_ids")
        assert event.sources.count() == 1 and EventDossier.objects.count() == 1
        return
    assert event.sources.count() == 2
    assert OriginalContentText.objects.filter(narrative__development__event_dossier=event).count() == 1
    assert event.current_review is None
    # A third selector made its decision before publication, but its C1 has not
    # been sent. The same guard records its distinct evidence without a writer.
    third = consideration(consideration_state="selected")
    third.run.config_snapshot = first.run.config_snapshot
    third.run.scope_key, third.run.workflow_version = first.run.scope_key, first.run.workflow_version
    third.run.save(update_fields=["config_snapshot", "scope_key", "workflow_version"])
    another = Post.objects.create(tweet_id="98004", text="Another account describes the same exchange.",
                                  created_at=third.run.facts_as_of, author_handle="witness")
    chatter_history.freeze_sources(third.run, [chatter_history.project_post(another)], fence=third.run.fence)
    chatter_history.attach_sources(third, [another.pk], fence=third.run.fence)
    third.selection = {"episode_id": episode, "people": ["Jensen Huang"], "event_coverage": {**second.selection["event_coverage"],
                                          "passages": [{"source_id": another.pk, "excerpt": another.text}]}}
    third.save(update_fields=["selection"])
    late, _ = materialize_package(prepared(third))
    assert advance_step(late.pk, keys={}, transport=lambda *_: pytest.fail("writer sent"))["state"] == "repeat"
    assert not late.provider_calls.exists() and event.sources.count() == 3


def test_cross_event_roundup_document_reuses_observation_for_its_own_new_claim(frozen_chatter, tmp_path):
    from core.event_dossiers import identity_key
    from monitor.editorial.chatter_coverage import record_event
    from monitor.editorial.chatter_history import read_sources

    row, _, _ = frozen_chatter
    original, _ = add_document(row, tmp_path)
    document = next(source for source in read_sources(row) if source["kind"] == "dossier_source")
    coverage = {"prior": [], "same_dossier": None, "identity": identity_key("test", "second event"),
                "kind": "human_interest", "passages": [{"source_id": document["id"], "excerpt": document["original_text"]}]}
    event = record_event(row, coverage, [document]).event_dossier
    assert event.pk != original.event_dossier_id
    attached = event.sources.get()
    assert attached.collection_observation_id == original.collection_observation_id
    assert attached.claims.get().source_excerpt == document["original_text"]
    assert not original.claims.exists()


def test_matched_dossier_merged_after_selection_uses_canonical_target(frozen_chatter):
    from core.event_dossiers import create_dossier, identity_key
    from core.models import EditorialStory, EventDossier
    from monitor.editorial.chatter_coverage import record_event
    from monitor.editorial.chatter_history import read_sources

    row, _, _ = frozen_chatter
    original, target = [create_dossier(event_kind="human_interest", identity_key=identity_key("test", key))
                        for key in ("old subject link", "canonical event")]
    row.development.event_dossier = original
    row.development.save(update_fields=["event_dossier"])
    canonical = EditorialStory.objects.create(event_dossier=target, development_key="canonical")
    EventDossier.objects.filter(pk=original.pk).update(merged_into=target)
    support = read_sources(row, usage="consideration")
    coverage = {"prior": [{"story_id": str(row.development_id), "published": "2026-11-24", "edition_id": "older"}],
                "same_dossier": str(original.pk), "identity": identity_key("test", "frozen event"), "kind": "human_interest",
                "passages": [{"source_id": support[0]["id"], "excerpt": support[0]["original_text"]}]}
    assert record_event(row, coverage, support) == canonical
    assert target.sources.get().claims.count() == 1 and not original.sources.exists()
    row.development.refresh_from_db()
    assert row.development.event_dossier_id == original.pk
