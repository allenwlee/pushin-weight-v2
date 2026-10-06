import json
from datetime import timedelta

import pytest
from django.utils import timezone

from core.models import (
    EditorialCall,
    EditorialEdition,
    EditorialHero,
    EditorialPicture,
    Post,
    PostBrand,
)
from monitor.editorial import providers, service
from monitor.editorial.media import start_derivative
from tests.editorial_support import (  # noqa: F401
    active_config,
    editorial_storage,
    person_photo,
)

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.requires_postgres,
    pytest.mark.usefixtures("editorial_storage"),
]


def test_source_to_paid_reservation_to_two_editions_picture_and_reader(
    monkeypatch, client
):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-only")
    monkeypatch.setenv("PUSHINWEIGHT_MINIMAX_API_KEY", "project-test-only")
    person, _, _ = person_photo("blue", "founder")
    post = Post.objects.create(
        tweet_id="555",
        text="DeepSeek announces a new release.",
        created_at=timezone.now() - timedelta(minutes=5),
    )
    PostBrand.objects.create(post=post, brand_id="deepseek")
    calls = []

    def transport(endpoint, key, body, **kwargs):
        calls.append(body)
        if "minimax.io" in endpoint:
            return 200, b'{"task_id":"fixture-video"}'
        if "editor-in-chief" in body["messages"][0]["content"]:
            data = {
                "events": [
                    {
                        "key": "deepseek-new-release",
                        "summary": post.text,
                        "post_ids": ["555"],
                        "brand_keys": ["deepseek"],
                        "occurred_at": post.created_at.isoformat(),
                        "chatter": True,
                        "pulse": True,
                        "importance": 90,
                        "reason": "A substantive release",
                        "subject_kind": "model_release",
                    }
                ]
            }
        else:
            funny = "New York Post" in body["messages"][0]["content"]
            data = {
                "headline": "MODEL BEHAVIOR"
                if funny
                else "DeepSeek announces a new release",
                "byline": "A new release for developers.",
                "article": "DeepSeek announced a new release. The source does not provide additional detail.",
                "locale": "en",
                "post_ids": ["555"],
            }
        return 200, json.dumps(
            {
                "model": body["model"],
                "choices": [
                    {"finish_reason": "stop", "message": {"content": json.dumps(data)}}
                ],
                "usage": {"prompt_tokens": 100, "completion_tokens": 50},
            }
        ).encode()

    monkeypatch.setattr(providers, "https_request", transport)
    monkeypatch.setattr(
        service,
        "start_derivative",
        lambda row, assessment, cfg: start_derivative(
            row, assessment, cfg, transport=transport
        ),
    )
    monkeypatch.setattr("monitor.editorial.dispatch.dispatch_poll", lambda _: None)
    cfg = active_config(public_enabled=True, assessment_calls=5)
    result = service.run_editorial(
        {
            "schema_version": 1,
            "completed_at": timezone.now().isoformat(),
            "source_cycle_id": "fixture",
            "outcome": "completed",
            "dry_run": False,
        },
        cfg=cfg,
    )
    assert result["published"] == 2, result
    assert EditorialCall.objects.count() == 4
    assert len(calls) == 4
    assert (
        EditorialHero.objects.get(key="chatter:en").edition.headline == "MODEL BEHAVIOR"
    )
    picture = EditorialPicture.objects.get()
    assert picture.state == "pending" and picture.person_media.person_id == person.pk
    assert picture.provider_task_id == "fixture-video"
    assert "data:image" not in json.dumps(
        list(EditorialCall.objects.values_list("response", flat=True))
    )
    monkeypatch.setattr("monitor.editorial.views.load_editorial_config", lambda: cfg)
    response = client.get("/api/v2/editorial-stories/?lang=en", secure=True)
    item = response.json()["hero"]
    assert item["asset"]["type"] == "image"
    assert client.get(item["url"], secure=True).status_code == 200
    assert client.get(item["asset"]["url"], secure=True).status_code == 200
    monkeypatch.setattr(
        "monitor.editorial.views.load_editorial_config",
        lambda: cfg.model_copy(update={"pictures": {"chatter": "off"}}),
    )
    assert client.get(item["asset"]["url"], secure=True).status_code == 404
    assert client.get(item["url"], secure=True).status_code == 200
    assert EditorialEdition.objects.count() == 2
    assert len(calls) == 4  # GET requests never invoke providers.


def test_disable_during_writer_prevents_publication(monkeypatch):
    Post.objects.create(
        tweet_id="44",
        text="A major release",
        created_at=timezone.now() - timedelta(minutes=2),
    )
    cfg = active_config(pictures={})
    live = [cfg]

    def call(row, stage, route, request, cfg):
        if stage.startswith("editor"):
            data = {
                "events": [
                    {
                        "key": "release",
                        "summary": "A major release",
                        "post_ids": ["44"],
                        "occurred_at": row.cutoff.isoformat(),
                        "chatter": True,
                        "pulse": False,
                        "importance": 90,
                        "reason": "A release",
                    }
                ]
            }
        else:
            live[0] = cfg.model_copy(update={"enabled": False})
            data = {
                "headline": "Headline",
                "byline": "Byline",
                "article": "Article",
                "locale": "en",
                "post_ids": ["44"],
            }
        return {"data": data, "model": "test"}

    service.run_editorial(
        {
            "schema_version": 1,
            "completed_at": timezone.now().isoformat(),
            "source_cycle_id": "fixture",
            "outcome": "completed",
            "dry_run": False,
        },
        cfg=cfg,
        call=call,
        policy_reader=lambda: live[0],
    )
    assert not EditorialEdition.objects.exists()
