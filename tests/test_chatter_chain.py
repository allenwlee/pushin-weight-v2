"""The real stage functions connect discovery, direct source receipts and publication."""

import json
from datetime import timedelta
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest
from django.utils import timezone

from core.models import (
    CollectionRequest,
    OriginalContent,
    OriginalContentCall,
    OriginalContentRun,
)
from monitor.editorial.config import ChatterTrial, ChatterWorkflow, Route
from monitor.editorial.readers import feed_payload
from tests.editorial_support import active_config, grounded_reply, senior_approval
from tests.test_chatter_discovery import selection

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


def test_failed_search_attempt_is_briefed_without_counting_a_fresh_story():
    from monitor.editorial.chatter_chain import _history
    from monitor.editorial.chatter_history import SCOPE, WORKFLOW
    from tests.test_original_content_consideration import consideration, producer

    content = consideration()
    run = content.run
    run.scope_key = SCOPE
    run.discovery_state = "failed"
    run.save(update_fields=["scope_key", "discovery_state"])
    call = producer(content, "en")
    call.workflow_key, call.stage = WORKFLOW, "discovery"
    call.response_payload = {
        "data": {"stories": [17], "keyword_query": ""},
        "search_activity": [],
    }
    call.save(update_fields=["workflow_key", "stage", "response_payload"])
    candidates, _, brief = _history(timezone.now() + timedelta(seconds=1))
    assert candidates == {} and brief["subjects"] == []
    assert len(brief["recent_searches"]) == 1
    assert brief["recent_searches"][0]["discovery_state"] == "failed"
    assert brief["recent_searches"][0]["tool_activity"] == []
    assert brief["recent_searches"][0]["stories"] == []


def chain_config():
    route = Route(
        model="grok-4.7",
        endpoint="https://api.x.ai/v1/responses",
        key_env="XAI_API_KEY_PW",
        input_usd_per_million=2,
        output_usd_per_million=6,
        max_output_tokens=8192,
        timeout_seconds=300,
    )
    return active_config(pictures={}).model_copy(
        update={
            "chatter": ChatterWorkflow(
                enabled=True,
                discovery=route,
                selector=route,
                trial=ChatterTrial(scope="chatter-test", limit_usd=20, carry_usd=0),
            )
        }
    )


def wire(data, model="grok-4.7", *, search=False):
    return 200, json.dumps(
        {
            "id": "fixture",
            "model": model,
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": json.dumps(data)}],
                }
            ],
            "usage": {
                "input_tokens": 1000,
                "output_tokens": 200,
                "cost_in_usd_ticks": 100000000,
                "server_side_tool_usage_details": {
                    "x_search_calls": int(search),
                    "x_posts_fetched": 10 if search else 0,
                },
            },
        }
    ).encode()


def test_discovery_to_pool_publication_uses_real_storage_and_no_duplicate_send(
    monkeypatch,
):
    from monitor.editorial import chatter_chain

    real_failure = chatter_chain._failure

    def unexpected_failure(run, stage, exc):
        raise exc

    monkeypatch.setattr("monitor.editorial.chatter_chain._failure", unexpected_failure)
    from monitor.editorial.chatter_chain import (
        reconstruct_selection_request,
        reconstruct_writer_request,
        review_chatter,
        run_chatter,
        select_chatter,
        write_chatter,
    )

    for name in (
        "XAI_API_KEY_PW",
        "OPENROUTER_API_KEY",
        "TWITTERAPI_IO_ON_DEMAND_API_KEY",
    ):
        monkeypatch.setenv(name, "fixture-only")
    monkeypatch.setenv("ORIGINAL_CONTENT_STORAGE", "shared")
    from core.models import Language, Locale

    for code in ("en", "ja", "zh-CN"):
        Language.objects.get_or_create(pk=code.split("-")[0])
        Locale.objects.get_or_create(
            pk=code, defaults={"language_id": code.split("-")[0]}
        )
    cfg, now = chain_config(), timezone.now()
    cfg = cfg.model_copy(
        update={"voices": {**cfg.voices, "chatter:ja": "chatter-ja-tospo-v2"}}
    )
    calls, queued = [], []
    story = {
        "story_ref": "S1",
        "subject": "A small lab announces a model",
        "angle": "Unverified semantic notes are not writing evidence.",
        "reader_appeal": "A substantive new development.",
        "keyword_query": '"small lab"',
        "prior_development_id": None,
        "primary_posts": [
            {
                "url": "https://x.com/lab/status/123",
                "author_handle": "lab",
                "text": "unverified text",
                "created_at": None,
            }
        ],
        "discussion_posts": [],
        "gaps": [],
    }

    def transport(endpoint, key, body, **kwargs):
        calls.append(body)
        if "messages" in body and "reviews" in json.loads(
            body["messages"][1]["content"]
        ):
            payload = json.loads(body["messages"][1]["content"])
            data = {
                "reviews": [
                    {
                        "text_id": row["text_id"],
                        "review": {**senior_approval(), "verdict": "hold"},
                    }
                    for row in payload["reviews"]
                ]
            }
            return 200, json.dumps(
                {
                    "model": body["model"],
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {"content": json.dumps(data)},
                        }
                    ],
                    "usage": {"prompt_tokens": 100, "completion_tokens": 100},
                }
            ).encode()
        if "input" in body:
            payload = json.loads(body["input"][1]["content"])
            if "activity_window" in payload:
                return wire(
                    {
                        "stories": [story],
                        "keyword_query": '"small lab"',
                        "search_notes": [],
                        "history_requests": [],
                    },
                    search=True,
                )
            candidates = payload["candidates"]
            chosen = next(row for row in candidates if "123" in row["post_ids"])
            result = selection(chosen)
            result["candidate_tags"][0]["group_policy_ref"] = payload[
                "giant_group_policy"
            ]["policy_ref"]
            rest = next(
                row
                for row in result["group_decisions"]
                if row["scope_ref"] == "en-rest"
            )
            rest["incumbent_ref"] = payload["incumbents"].get("en-rest")
            if rest["incumbent_ref"]:
                rest["lead_action"] = "keep"
            for candidate in candidates:
                if candidate["candidate_ref"] == chosen["candidate_ref"]:
                    continue
                tag = {
                    **result["candidate_tags"][0],
                    "candidate_ref": candidate["candidate_ref"],
                    "language_evidence_ref": "language:" + candidate["candidate_ref"],
                    "group_evidence_post_ids": candidate["post_ids"],
                }
                result["candidate_tags"].append(tag)
                rest["ranked_candidates"].append(
                    {
                        "candidate_ref": candidate["candidate_ref"],
                        "rank": len(rest["ranked_candidates"]) + 1,
                        "outcome": "passed_over",
                        "reason": "The other development has stronger supported reader appeal.",
                        "measurement_refs": [],
                        "history_refs": [],
                        "asset_refs": [],
                    }
                )
            return wire(result)
        assert "Unverified semantic notes" not in body["messages"][1]["content"]
        data = grounded_reply(
            body,
            {
                "headline": "MODEL BEHAVIOR",
                "byline": "A source announces a model.",
                "article": "A company announced a model.",
                "locale": "en",
            },
        )
        return 200, json.dumps(
            {
                "model": body["model"],
                "choices": [
                    {"finish_reason": "stop", "message": {"content": json.dumps(data)}}
                ],
                "usage": {"prompt_tokens": 100, "completion_tokens": 100},
            }
        ).encode()

    def get(url, params, timeout=None, **kwargs):
        identity = "124" if "advanced_search" in url else "123"
        data = {
            "tweets": [
                {
                    "id": identity,
                    "text": "A company announced a model.",
                    "lang": "en",
                    "createdAt": (now - timedelta(minutes=1)).isoformat(),
                    "likeCount": 10,
                    "author": {"id": "42", "userName": "lab"},
                }
            ],
            "has_next_page": False,
        }
        response = Mock(status_code=200)
        response.json.return_value = data
        response.content = json.dumps(data).encode()
        return response

    envelope = {
        "schema_version": 1,
        "source_cycle_id": str(uuid4()),
        "cycle_started_at": now.isoformat(),
        "cutoff": now.isoformat(),
        "dry_run": False,
        "credential_purpose": "on-demand",
    }
    with patch(
        "x_monitor.x_client.XClient._get_bounded", side_effect=get
    ) as source_get:
        result = run_chatter(
            envelope,
            cfg=cfg,
            transport=transport,
            enqueue=lambda *args: queued.append(args),
        )
        assert result["status"] == "discovered", result
        assert source_get.call_count == 2
    assert queued == [("select", result["run_id"])]
    selected = select_chatter(
        result["run_id"],
        cfg=cfg,
        transport=transport,
        enqueue=lambda *args: queued.append(args),
    )
    assert selected["selected"] == 1
    content = OriginalContent.objects.get(
        run_id=result["run_id"], consideration_state="selected"
    )
    assert OriginalContent.objects.filter(
        run=content.run, consideration_state="passed_over"
    ).exists()
    published = write_chatter(
        content.pk, "en", cfg=cfg, transport=transport, enqueue=lambda *args: None
    )
    assert published["status"] == "published", published
    feed = feed_payload(cfg, source_locale="en", editorial_group="rest")
    assert (
        feed["hero"]["headline"] == "MODEL BEHAVIOR"
        and feed["hero"]["source_count"] == 1
    )
    assert (
        CollectionRequest.objects.filter(
            scope_run__run__content_run=content.run
        ).count()
        == 3
    )
    from monitor.editorial.chatter_history import read_sources

    assert read_sources(content)[0]["counters"]["replies"] is None
    assert OriginalContentCall.objects.filter(run=content.run).count() == 3
    before = len(calls)
    assert (
        run_chatter(envelope, cfg=cfg, transport=transport, enqueue=lambda *args: None)[
            "status"
        ]
        == "already_discovered"
    )
    assert (
        write_chatter(
            content.pk, "en", cfg=cfg, transport=transport, enqueue=lambda *args: None
        )["status"]
        == "already_published"
    )
    assert len(calls) == before
    monkeypatch.setattr(chatter_chain, "_failure", real_failure)
    failure = write_chatter(
        content.pk,
        "ja",
        cfg=cfg,
        transport=lambda *args, **kwargs: (503, b"{}"),
        enqueue=lambda *args: None,
    )
    assert failure["status"] == "held"
    assert (
        feed_payload(cfg, source_locale="en", editorial_group="rest")["hero"][
            "headline"
        ]
        == "MODEL BEHAVIOR"
    )
    assert (
        reconstruct_writer_request(
            content.run.provider_calls.get(stage=f"writer:{content.pk}:en")
        )["model"]
        == cfg.writer_route("chatter", "en").model
    )
    selector_call = content.run.provider_calls.get(stage="selector:0")
    assert "A company announced a model." not in json.dumps(
        selector_call.request_packet
    )
    assert (
        reconstruct_selection_request(selector_call)["model"]
        == cfg.chatter.selector.model
    )
    assert (
        review_chatter(content.run_id, cfg=cfg, transport=transport)["status"]
        == "reviewed"
    )
    assert (
        feed_payload(cfg, source_locale="en", editorial_group="rest")["hero"][
            "headline"
        ]
        == "MODEL BEHAVIOR"
    )
    run = OriginalContentRun.objects.get(pk=result["run_id"])
    assert (
        run.outcome["healthy_at"]
        and run.cycle_started_at == now
        and run.execution_state == "completed"
    )
    later = now + timedelta(minutes=15)
    monkeypatch.setattr(chatter_chain, "_failure", unexpected_failure)
    next_envelope = {
        **envelope,
        "source_cycle_id": str(uuid4()),
        "cycle_started_at": later.isoformat(),
        "cutoff": later.isoformat(),
    }
    with (
        patch("django.utils.timezone.now", return_value=later),
        patch("x_monitor.x_client.XClient._get_bounded", side_effect=get),
    ):
        second = run_chatter(
            next_envelope, cfg=cfg, transport=transport, enqueue=lambda *args: None
        )
        assert second["status"] == "discovered", second
        kept = select_chatter(
            second["run_id"], cfg=cfg, transport=transport, enqueue=lambda *args: None
        )
        assert kept["selected"] == 0
        current = OriginalContent.objects.get(
            run_id=second["run_id"], development=content.development
        )
        assert (
            current.consideration_state == "kept"
            and not current.localized_texts.exists()
        )
        from monitor.editorial.chatter_history import appearance_history

        assert (
            appearance_history(current.development, later)["consecutive_lower_bound"]
            == 2
        )
