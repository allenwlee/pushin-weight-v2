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
    grounded_reply,
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
        data = grounded_reply(body, data)
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
    assert item["source_count"] == 1
    assert [source["url"] for source in item["sources"]] == [
        "https://x.com/i/status/555"
    ]
    assert EditorialEdition.objects.get(pk=item["id"]).evidence["attribution"] == {
        "post_count": 1,
        "posts": [{"id": "555", "url": "https://x.com/i/status/555"}],
    }
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


def test_launch_profile_sends_current_deepseek_allowance_through_real_editor(
    monkeypatch,
):
    from decimal import Decimal

    from core.models import EditorialBudget
    from monitor.editorial.config import load_editorial_config

    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-only")
    monkeypatch.setenv("DEEPINFRA_API_KEY", "deepinfra-test-only")
    monkeypatch.setenv("EDITORIAL_CONFIG_PATH", "config/editorial-english-launch.yaml")
    cfg = load_editorial_config()
    post = Post.objects.create(
        tweet_id="2106428676351090999",
        text="A major model release.",
        created_at=timezone.now() - timedelta(minutes=1),
    )
    requests = []

    def transport(endpoint, key, body, **kwargs):
        if body["model"] == "deepseek-ai/DeepSeek-V4-Flash-0731":
            assert endpoint == "https://api.deepinfra.com/v1/openai/chat/completions"
            assert key == "deepinfra-test-only"
            assert body["reasoning_effort"] == "none"
            assert body["service_tier"] == "priority"
            assert body["response_format"]["json_schema"]["strict"] is True
            assert kwargs["timeout"] == 300
            assert "provider" not in body and "reasoning" not in body
        else:
            assert body["model"] == "gpt-6-sol"
            assert endpoint == "https://api.openai.com/v1/chat/completions"
            assert key == "openai-test-only"
            assert body["reasoning_effort"] == "medium"
            assert body["max_completion_tokens"] == 4096
            assert body["service_tier"] == "default"
            assert not {"max_tokens", "provider", "reasoning"} & body.keys()
        requests.append(body)
        if body["model"] == cfg.routes["editor"].model:
            assert EditorialCall.objects.filter(
                state="sent", reserved_usd__gte=Decimal("0.131072")
            ).exists()
        if "editor-in-chief" in body["messages"][0]["content"]:
            data = {
                "events": [
                    {
                        "key": "current-allowance-release",
                        "summary": post.text,
                        "post_ids": [post.pk],
                        "occurred_at": post.created_at.isoformat(),
                        "chatter": True,
                        "pulse": True,
                        "importance": 90,
                        "reason": "A substantive release",
                    }
                ]
            }
        else:
            data = {
                "headline": "A release",
                "byline": "A new model for developers.",
                "article": post.text,
                "locale": "en",
                "post_ids": [post.pk],
            }
        data = grounded_reply(body, data)
        return 200, json.dumps(
            {
                "model": body["model"],
                "id": "g2-test-response",
                "service_tier": "priority",
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 50,
                    "estimated_cost": 0.001,
                    "completion_tokens_details": {"reasoning_tokens": 0},
                },
                "choices": [
                    {"finish_reason": "stop", "message": {"content": json.dumps(data)}}
                ],
            }
        ).encode()

    monkeypatch.setattr(providers, "https_request", transport)
    result = service.run_editorial(
        {
            "schema_version": 1,
            "completed_at": timezone.now().isoformat(),
            "source_cycle_id": "current-output-allowance",
            "outcome": "completed",
            "dry_run": False,
        },
        cfg=cfg,
    )
    assert result["published"] == 2, result
    assert [
        request.get("max_tokens", request.get("max_completion_tokens"))
        for request in requests
    ] == [65536, 4096, 65536]
    from monitor.headline_grounding import SOURCE_READING_RULES

    for request in requests:
        assert SOURCE_READING_RULES in request["messages"][0]["content"]
        content = request["messages"][1]["content"]
        if isinstance(content, list):
            content = content[0]["text"]
        evidence = json.loads(content)["evidence"]
        first = evidence["posts"][0] if isinstance(evidence, dict) else evidence[0]
        assert first["id"] == "S001" and first["source_spans"]
    assert all(
        edition.selection["source_check"][0]["post_id"] == post.pk
        for edition in EditorialEdition.objects.all()
    )
    for edition in EditorialEdition.objects.all():
        assert edition.evidence["source_check"][0]["source_field"] == "original_text"
        assert edition.evidence["supported_copy"] == {
            field: getattr(edition, field)
            for field in ("headline", "byline", "article")
        }
    # Both factual calls reserve the full enlarged allowance before sending.
    factual_calls = EditorialCall.objects.exclude(stage__startswith="writer:chatter")
    assert factual_calls.count() == 2
    assert all(call.reserved_usd >= Decimal("0.131072") for call in factual_calls)
    assert EditorialBudget.objects.get().reserved_usd <= Decimal(5)


@pytest.mark.parametrize(
    "defect", ["missing_check", "foreign_passage", "foreign_brand"]
)
def test_real_provider_chain_blocks_unsupported_selection_before_writing(
    monkeypatch, defect
):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-only")
    post = Post.objects.create(
        tweet_id="grounding-guard",
        text="A source announces a release.",
        created_at=timezone.now() - timedelta(minutes=1),
    )
    sends = []

    def transport(endpoint, key, body, **kwargs):
        sends.append(body)
        data = grounded_reply(
            body,
            {
                "events": [
                    {
                        "key": "guarded-release",
                        "summary": post.text,
                        "post_ids": [post.pk],
                        "occurred_at": post.created_at.isoformat(),
                        "chatter": True,
                        "pulse": True,
                        "importance": 80,
                        "reason": "A release",
                    }
                ]
            },
        )
        if defect == "missing_check":
            data["events"][0].pop("source_check")
        elif defect == "foreign_passage":
            data["events"][0]["source_check"][0]["support"]["span_ids"] = [
                "s:another-post"
            ]
        else:
            data["events"][0]["source_check"][0]["support"]["brand_keys"] = ["qwen"]
        return 200, json.dumps(
            {
                "model": body["model"],
                "choices": [
                    {"finish_reason": "stop", "message": {"content": json.dumps(data)}}
                ],
            }
        ).encode()

    monkeypatch.setattr(providers, "https_request", transport)
    envelope = {
        "schema_version": 1,
        "completed_at": timezone.now().isoformat(),
        "source_cycle_id": "grounding-guard",
        "outcome": "completed",
        "dry_run": False,
    }
    cfg = active_config(pictures={})
    result = service.run_editorial(envelope, cfg=cfg)
    assert result["status"] == "held" and result["published"] == 0
    assert len(sends) == 1 and not EditorialEdition.objects.exists()
    assert EditorialCall.objects.get().reserved_usd > 0
    assert service.run_editorial(envelope, cfg=cfg)["status"] == "already_claimed"
    assert len(sends) == 1  # A blocked source check cannot trigger a paid retry.


def test_context_is_frozen_for_both_tracks_but_only_cited_posts_are_attributed(
    monkeypatch,
):
    from core.models import EditorialAssessment
    from tests.test_editorial_context import stored

    now = timezone.now()
    stored(
        "101",
        "Mistral Large 4 is Le Chonk. Available by API, weights coming later.",
        now,
        0,
    )
    stored("102", "Le Chonk revives the old Le Chaton Fat joke.", now, 2)
    stored("103", "The fictional Le Chaton Fat fooled people.", now, 90)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-only")
    writer_inputs = []

    def transport(endpoint, key, body, **kwargs):
        if "editor-in-chief" in body["messages"][0]["content"]:
            data = {
                "events": [
                    {
                        "key": "chonk",
                        "summary": "A model release",
                        "post_ids": ["101"],
                        "occurred_at": now.isoformat(),
                        "chatter": True,
                        "pulse": True,
                        "importance": 90,
                        "reason": "A substantive release",
                    }
                ]
            }
        else:
            content = body["messages"][1]["content"]
            if isinstance(content, list):
                content = content[0]["text"]
            writer_inputs.append(json.loads(content))
            data = {
                "headline": "CAT NEWS",
                "byline": "A cat-themed model release.",
                "article": "The release recalls an older fictional cat model.",
                "locale": "en",
                "post_ids": ["101", "103"],
            }
        grounded = grounded_reply(body, data)
        if "events" not in grounded:
            source = next(
                p
                for p in writer_inputs[-1]["evidence"]
                if any("fictional" in span["text"] for span in p["source_spans"])
            )
            span = source["source_spans"][0]
            grounded["source_check"].append(
                {
                    "support": {
                        "post_id": source["id"],
                        "source_field": span["source_field"],
                        "span_ids": [span["span_id"]],
                        "brand_keys": [],
                    },
                    "action": "recalls",
                    "target": "a fictional model",
                    "status": "source_report",
                    "number_ownership": "none",
                }
            )
        return 200, json.dumps(
            {
                "model": body["model"],
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": json.dumps(grounded)},
                    }
                ],
                "usage": {"prompt_tokens": 100, "completion_tokens": 50},
            }
        ).encode()

    monkeypatch.setattr(providers, "https_request", transport)
    result = service.run_editorial(
        {
            "schema_version": 1,
            "completed_at": (now + timedelta(seconds=1)).isoformat(),
            "source_cycle_id": "context",
            "outcome": "completed",
            "dry_run": False,
        },
        cfg=active_config(pictures={}),
    )
    assert result["published"] == 2, result
    assert len(writer_inputs) == 2
    assert writer_inputs[0]["evidence"] == writer_inputs[1]["evidence"]
    assert len(writer_inputs[0]["evidence"]) == 3
    frozen = EditorialAssessment.objects.get().packet["story_packets"]["chonk"]
    assert set(frozen["story_context"]["included_ids"]) == {"102", "103"}
    for edition in EditorialEdition.objects.all():
        assert edition.evidence["attribution"]["post_count"] == 2
        assert {p["url"] for p in edition.evidence["attribution"]["posts"]} == {
            "https://x.com/i/status/101",
            "https://x.com/i/status/103",
        }
        assert edition.selection["post_ids"] == ["101"]
        assert {claim["post_id"] for claim in edition.evidence["source_check"]} == {
            "101",
            "103",
        }
