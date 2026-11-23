"""Grok Responses uses the shared JSON transport and keeps compact evidence only."""

import json

import pytest

from core.models import OriginalContentCall
from monitor.editorial.config import Route
from monitor.editorial.providers import json_call
from tests.editorial_support import active_config
from tests.test_chatter_accounting import policy
from tests.test_original_content_consideration import consideration

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


def test_native_tool_input_preserves_query_identity_and_semantic_threshold():
    from monitor.editorial.providers import search_activity

    observed = search_activity(
        {
            "output": [
                {
                    "type": "custom_tool_call",
                    "call_id": "xs_fixture",
                    "name": "x_semantic_search",
                    "input": json.dumps(
                        {
                            "query": "new and continuing AI developments",
                            "limit": 10,
                            "min_score_threshold": 0.1,
                        }
                    ),
                }
            ]
        }
    )
    assert observed[0]["call_id"] == "xs_fixture"
    assert observed[0]["arguments"] == {
        "query": "new and continuing AI developments",
        "limit": 10,
        "min_score_threshold": 0.1,
    }
    assert observed[0]["results_visible"] is False


def test_native_search_agent_can_finish_before_json_validation():
    from datetime import UTC, datetime

    from monitor.editorial.chatter_discovery import semantic_request
    from monitor.editorial.providers import request_payload
    from tests.test_chatter_chain import chain_config

    cfg = chain_config()
    built = semantic_request(
        datetime(2026, 11, 4, 2, 10, tzinfo=UTC),
        {"subjects": [], "recent_searches": []},
        cfg,
    )
    body = request_payload(cfg.chatter.discovery, built)
    # Match the saved working agent form: search first, then return the requested JSON.
    assert body["max_turns"] == 2
    assert "text" not in body
    assert body["tools"] == [
        {"type": "x_search", "from_date": "2026-11-01", "to_date": "2026-11-05"}
    ]
    assert body["parallel_tool_calls"] is False
    selector = request_payload(cfg.chatter.selector, {"system": "Select", "user": "{}"})
    assert selector["text"]["format"]["type"] == "json_object"
    assert "tools" not in selector


def test_grok_responses_keeps_actual_tool_and_billing_counts_without_raw_envelope(
    monkeypatch,
):
    from monitor.editorial.chatter_accounting import call_once

    monkeypatch.setenv("XAI_API_KEY_PW", "fixture-only")
    route = Route(
        model="grok-4.7",
        endpoint="https://api.x.ai/v1/responses",
        key_env="XAI_API_KEY_PW",
        input_usd_per_million=2,
        output_usd_per_million=6,
        max_output_tokens=2048,
    )
    cfg = active_config().model_copy(update={"chatter": policy(20).chatter})
    run = consideration().run
    seen = []

    def transport(endpoint, key, body, **kwargs):
        seen.append(body)
        assert body["store"] is False and "messages" not in body
        assert body["max_turns"] == 1 and body["parallel_tool_calls"] is False
        return 200, json.dumps(
            {
                "id": "resp_fixture",
                "model": "grok-4.7",
                "status": "completed",
                "output": [
                    {"type": "reasoning", "encrypted_content": "never-save-this"},
                    {
                        "type": "custom_tool_call",
                        "id": "tool_1",
                        "name": "x_semantic_search",
                        "arguments": json.dumps(
                            {
                                "query": "AI people and consequential developments",
                                "limit": 10,
                            }
                        ),
                    },
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": '{"stories": []}'}],
                    },
                ],
                "usage": {
                    "input_tokens": 1000,
                    "output_tokens": 200,
                    "cost_in_usd_ticks": 123456789,
                    "server_side_tool_usage_details": {
                        "x_posts_fetched": 10,
                        "x_users_fetched": 0,
                        "x_search_calls": 1,
                    },
                },
            }
        ).encode()

    result = json_call(
        run,
        "discovery",
        route,
        {
            "system": "Discover supported stories.",
            "user": "A frozen current cutoff.",
            "reservation_usd": 3,
            "server_tools": {"tools": [{"type": "x_search"}], "max_turns": 1},
        },
        cfg,
        transport=transport,
        reservation=call_once,
    )
    assert len(seen) == 1 and result["data"] == {"stories": []}
    assert result["diagnostics"]["usage"]["x_posts_fetched"] == 10
    assert result["search_activity"][0]["name"] == "x_semantic_search"
    assert result["search_activity"][0]["results_visible"] is False
    call = OriginalContentCall.objects.get(run=run)
    assert str(call.actual_usd) == "0.012346"
    assert "never-save-this" not in json.dumps(call.response_payload)


def test_writer_call_stores_reconstructable_input_reference_instead_of_duplicate_evidence(
    monkeypatch,
):
    from monitor.editorial.chatter_accounting import call_once

    monkeypatch.setenv("OPENAI_API_KEY", "fixture-only")
    cfg = active_config().model_copy(update={"chatter": policy().chatter})
    route = cfg.writer_route("chatter", "en")
    monkeypatch.setenv(route.key_env, "fixture-only")
    run = consideration().run

    def transport(endpoint, key, body, **kwargs):
        return 200, json.dumps(
            {
                "model": route.model,
                "choices": [
                    {"finish_reason": "stop", "message": {"content": '{"saved": true}'}}
                ],
                "usage": {"prompt_tokens": 100, "completion_tokens": 20},
            }
        ).encode()

    reference = {"content_id": 123, "locale": "en", "builder": "chatter-v1"}
    json_call(
        run,
        "writer:en:123",
        route,
        {
            "system": "Write copy.",
            "user": "frozen-essential-source-passage",
            "input_reference": reference,
        },
        cfg,
        transport=transport,
        reservation=call_once,
    )
    call = OriginalContentCall.objects.get(run=run)
    assert call.request_packet["input_reference"] == reference
    assert "frozen-essential-source-passage" not in json.dumps(call.request_packet)
    assert (
        call.request_hash and call.request_packet["request_sha256"] == call.request_hash
    )
