"""Pin the actual locale writer, provider, persistence and public reader path."""

import json
import re
from datetime import timedelta
from pathlib import Path

import pytest
from django.utils import timezone

from core.models import EditorialCall, EditorialEdition, EditorialHero, Post
from monitor.editorial import providers, service
from monitor.editorial.config import load_editorial_config
from monitor.editorial.voices import load_voice
from tests.editorial_support import grounded_reply

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.requires_postgres]

EXPECTED_ROUTES = {
    "en": ("gpt-6-sol", "medium"),
    "ja": ("gpt-6.1-sol", "high"),
    "zh-cn": ("gpt-6.1-sol", "high"),
}
HEADLINES = {"en": "MODEL CITIZEN", "ja": "新モデルが登場", "zh-cn": "新模型来了"}


def launch():
    cfg = load_editorial_config(Path("config/editorial-english-launch.yaml"))
    return cfg.model_copy(update={"pictures": {}, "pulse_limit": 0})


def captured_worker(monkeypatch, *, bad_model_locale=None, bad_copy_locale=None):
    cfg = launch()
    now = timezone.now()
    post = Post.objects.create(
        tweet_id="910001",
        text="A company releases a major model.",
        author_handle="SourceCompany",
        created_at=now - timedelta(minutes=2),
    )
    now = timezone.now()  # The closed cutoff must include this post's fetched_at.
    monkeypatch.setenv("OPENAI_API_KEY", "offline-test-key")
    monkeypatch.setenv("DEEPINFRA_API_KEY", "offline-test-key")
    captured = []

    def transport(endpoint, key, body, **kwargs):
        system = body["messages"][0]["content"]
        match = re.search(r"Write in (en|ja|zh-cn) directly", system)
        locale = match.group(1) if match else None
        captured.append(
            {
                "locale": locale,
                "endpoint": endpoint,
                "body": body,
                "timeout": kwargs["timeout"],
            }
        )
        if locale is None:
            data = {
                "events": [
                    {
                        "key": "multilingual-model-release",
                        "summary": post.text,
                        "post_ids": [post.tweet_id],
                        "occurred_at": post.created_at.isoformat(),
                        "chatter": True,
                        "pulse": False,
                        "importance": 90,
                        "reason": "A source announces a model release.",
                    }
                ]
            }
        else:
            actual_locale = "en" if locale == bad_copy_locale else locale
            data = {
                "headline": HEADLINES[actual_locale],
                "byline": {
                    "en": "The company announces its new model.",
                    "ja": "企業が新モデルを発表した。",
                    "zh-cn": "这家公司宣布推出新模型。",
                }[actual_locale],
                "article": {
                    "en": "The source company announces a model release.",
                    "ja": "発信元の企業がモデルの公開を発表した。",
                    "zh-cn": "消息来自发布模型的公司。",
                }[actual_locale],
                "locale": actual_locale,
                "post_ids": [post.tweet_id],
            }
        data = grounded_reply(body, data)
        served = (
            "wrong-served-model"
            if bad_model_locale is not None and locale == bad_model_locale
            else body["model"]
        )
        return 200, json.dumps(
            {
                "id": "offline-request-" + str(len(captured)),
                "service_tier": body.get("service_tier", "default"),
                "model": served,
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": json.dumps(data, ensure_ascii=False)},
                    }
                ],
                "usage": {
                    "prompt_tokens": 40,
                    "completion_tokens": 60,
                    "estimated_cost": 0.0001,
                },
            }
        ).encode()

    envelope = {
        "schema_version": 1,
        "completed_at": now.isoformat(),
        "source_cycle_id": "multilingual-fixture",
        "outcome": "completed",
        "dry_run": False,
    }
    outcome = service.run_editorial(
        envelope,
        cfg=cfg,
        call=lambda *args: providers.json_call(*args, transport=transport),
    )
    if outcome.get("error"):
        outcome["call_diagnostics"] = list(
            EditorialCall.objects.values("stage", "state", "error_code", "response")
        )
    return cfg, post, envelope, captured, outcome


@pytest.mark.parametrize("storage", ["legacy", "shared"])
def test_worker_routes_native_models_and_serves_independent_saved_locales(
    monkeypatch, client, storage
):
    monkeypatch.setenv("ORIGINAL_CONTENT_STORAGE", storage)
    cfg, post, envelope, captured, outcome = captured_worker(monkeypatch)
    assert outcome["published"] == 3, json.dumps(outcome)
    writes = {row["locale"]: row for row in captured if row["locale"]}
    assert set(writes) == set(EXPECTED_ROUTES)
    for locale, (model, effort) in EXPECTED_ROUTES.items():
        wire = writes[locale]
        if locale == "en":
            from monitor.editorial.writing import HEADLINE_ATTRIBUTION_RULE

            assert cfg.voices["chatter:en"] == "chatter-en-v3"
            assert HEADLINE_ATTRIBUTION_RULE in wire["body"]["messages"][0]["content"]
            assert "Write a catchy, punny, tongue-in-cheek print headline and supporting byline." in wire["body"]["messages"][0]["content"]
        else:
            assert "Preserve whose claim it is in every language and the headline." in wire["body"]["messages"][0]["content"]
        assert wire["endpoint"] == "https://api.openai.com/v1/chat/completions"
        assert wire["body"]["model"] == model
        assert wire["body"]["reasoning_effort"] == effort
        assert wire["timeout"] == (90 if locale == "en" else 300)
        assert wire["body"]["max_completion_tokens"] == (
            4096 if locale == "en" else 16384
        )
        assert wire["body"]["service_tier"] == "default"
        voice = load_voice(cfg.voices["chatter:" + locale])
        assert wire["body"]["messages"][0]["content"].startswith(
            voice.instructions + "\n"
        )
        saved = EditorialEdition.objects.get(track="chatter", locale=locale)
        assert saved.model == model and saved.voice["hash"] == voice.digest
        assert saved.evidence["cited_post_ids"] == [post.tweet_id]
        assert saved.evidence["source_check"]
        assert EditorialHero.objects.get(key="chatter:" + locale).edition_id == saved.pk
        monkeypatch.setattr(
            "monitor.editorial.views.load_editorial_config", lambda: cfg
        )
        response = client.get(
            "/api/v2/editorial-stories/", {"lang": locale}, secure=True
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["locale"] == locale and payload["requested_locale"] == locale
        assert payload["hero"]["headline"] == HEADLINES[locale]
        story = client.get(payload["hero"]["url"], secure=True)
        assert story.status_code == 200 and HEADLINES[locale] in story.content.decode()
        assert post.text not in story.content.decode()
    assert len(captured) == 4
    assert EditorialCall.objects.count() == 4
    again = service.run_editorial(
        envelope, cfg=cfg, call=lambda *args: pytest.fail("duplicate provider call")
    )
    assert again["status"] == "already_claimed"
    assert EditorialEdition.objects.count() == 3


@pytest.mark.parametrize("failure", ["served_model", "locale"])
def test_native_provider_or_locale_mismatch_is_held_without_fallback(
    monkeypatch, failure
):
    _, _, _, captured, outcome = captured_worker(
        monkeypatch,
        bad_model_locale="ja" if failure == "served_model" else None,
        bad_copy_locale="ja" if failure == "locale" else None,
    )
    assert outcome["published"] == 2, outcome
    assert set(EditorialEdition.objects.values_list("locale", flat=True)) == {
        "en",
        "zh-cn",
    }
    assert len([row for row in captured if row["locale"] == "ja"]) == 1
    assert outcome["holds"]


def test_loaded_profiles_resolve_exact_locked_strings_and_preserve_legacy_digest():
    from monitor.editorial.contracts import digest

    contract = json.loads(
        Path(
            "docs/analysis/2026-10-12-195333-g2-locked-editorial-prompt.json"
        ).read_text()
    )
    profiles = {
        "en|nypost": "chatter-en-v2",
        "ja|tospo": "chatter-ja-tospo-v2",
        "ja|rocket": "chatter-ja-rocket-v2",
        "zh-cn|metro": "chatter-zh-cn-metro-v2",
        "zh-cn|wemedia": "chatter-zh-cn-wemedia-v2",
    }
    for key, profile in profiles.items():
        locale = key.split("|", 1)[0]
        expected = (
            contract["instructions"][locale]
            + "\n"
            + contract["voices"][key]["task"][locale]
        )
        voice = load_voice(profile)
        assert voice.instructions == expected
        assert voice.locale == locale and voice.track == "chatter"
    old = json.loads(Path("config/editorial_voices/chatter-en-v1.json").read_text())
    assert load_voice(old["id"]).digest == digest(old)


@pytest.mark.parametrize(
    "mutation",
    [
        "escape",
        "missing",
        "unlocked",
        "unknown_voice",
        "wrong_locale",
        "empty",
        "inline",
    ],
)
def test_invalid_shared_prompt_is_rejected_before_any_provider_call(
    monkeypatch, tmp_path, settings, mutation
):
    source = Path(settings.BASE_DIR)
    profile = json.loads(
        (source / "config/editorial_voices/chatter-ja-tospo-v2.json").read_text()
    )
    contract = json.loads(
        (
            source / "config/editorial_prompts/editorial-judgment-headline-v1.json"
        ).read_text()
    )
    if mutation == "escape":
        profile["shared_prompt"] = "../editorial-judgment-headline-v1"
    elif mutation == "missing":
        profile["shared_prompt"] = "missing"
    elif mutation == "unlocked":
        contract["status"] = "draft"
    elif mutation == "unknown_voice":
        profile["publication_voice"] = "missing"
    elif mutation == "wrong_locale":
        contract["voices"]["ja|tospo"]["output_language"] = "en"
    elif mutation == "empty":
        contract["instructions"]["ja"] = " "
    else:
        profile["instructions"] = "Conflicting inline instruction"
    voices = tmp_path / "config/editorial_voices"
    prompts = tmp_path / "config/editorial_prompts"
    voices.mkdir(parents=True)
    prompts.mkdir(parents=True)
    (voices / "chatter-ja-tospo-v2.json").write_text(json.dumps(profile))
    (prompts / "editorial-judgment-headline-v1.json").write_text(json.dumps(contract))
    settings.BASE_DIR = tmp_path
    monkeypatch.setattr(
        providers,
        "json_call",
        lambda *args: pytest.fail("invalid profile made a paid call"),
    )
    with pytest.raises(ValueError):
        load_voice("chatter-ja-tospo-v2")
    assert EditorialCall.objects.count() == 0


def test_optional_media_cannot_take_slots_before_all_native_writers(monkeypatch):
    order = []

    def picture(event, packet, cfg, **kwargs):
        order.append(set(EditorialEdition.objects.values_list("locale", flat=True)))
        # Simulate an exhausted optional-media allowance without hiding text.
        from monitor.editorial.persistence import BudgetHeld

        raise BudgetHeld("optional media allowance exhausted")

    monkeypatch.setattr(service, "select_picture", picture)
    _, _, _, captured, outcome = captured_worker(monkeypatch)
    assert outcome["published"] == 3, outcome
    assert [row["locale"] for row in captured] == [None, "en", "ja", "zh-cn"]
    assert order == [{"en", "ja", "zh-cn"}] * 3
    assert len(outcome["holds"]) == 3
    assert all(hold["stage"] == "picture" for hold in outcome["holds"])


@pytest.mark.parametrize("storage", ["legacy", "shared"])
def test_native_worker_output_is_visible_in_real_story_browser(
    live_server, monkeypatch, settings, storage
):
    import os

    from playwright.sync_api import sync_playwright

    monkeypatch.setenv("ORIGINAL_CONTENT_STORAGE", storage)
    settings.SECURE_SSL_REDIRECT = False
    settings.ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]
    cfg, post, _, _, outcome = captured_worker(monkeypatch)
    assert outcome["published"] == 3, outcome
    monkeypatch.setattr("monitor.editorial.views.load_editorial_config", lambda: cfg)
    story_ids = dict(
        EditorialEdition.objects.filter(track="chatter").values_list(
            "locale", "story_id"
        )
    )
    with sync_playwright() as pw:
        executable = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE")
        browser = pw.chromium.launch(
            **({"executable_path": executable} if executable else {})
        )
        page = browser.new_page(extra_http_headers={"X-Forwarded-Proto": "https"})
        for width in (390, 1440):
            page.set_viewport_size({"width": width, "height": 900})
            for locale, headline in HEADLINES.items():
                response = page.goto(
                    f"{live_server.url}/stories/{story_ids[locale]}/?lang={locale}"
                )
                assert response.status == 200
                heading = page.locator("h1")
                assert heading.count() == 1 and heading.is_visible()
                assert heading.inner_text() == headline
                assert heading.bounding_box()["width"] > 0
                attribution = page.locator(".source-attribution")
                assert attribution.is_visible()
                assert attribution.locator("a").count() == 1
                assert post.tweet_id in attribution.locator("a").get_attribute("href")
                assert post.text not in page.locator("body").inner_text()
        browser.close()
