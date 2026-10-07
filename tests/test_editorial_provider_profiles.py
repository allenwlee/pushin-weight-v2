"""Offline request/receipt checks using actual G2 builders and launch routes."""

import hashlib
import http.client
import json
from pathlib import Path

import pytest
from django.utils import timezone

from monitor.editorial import providers
from monitor.editorial.config import Route, load_editorial_config
from monitor.editorial.contracts import ProviderReplyError
from monitor.editorial.voices import load_voice
from monitor.editorial.writing import editor_request, writer_request
from tests.editorial_support import selection
from x_monitor.deepinfra import DeepInfraChatCompletionsClient, DeepInfraPermanentError


@pytest.fixture
def factual_setup():
    cfg = load_editorial_config(Path("config/editorial-english-launch.yaml"))
    packet = {
        "cutoff": timezone.now().isoformat(),
        "posts": [{"id": "1", "original_text": "A model release.", "images": []}],
        "context": [],
        "stories": [],
        "people": [],
    }
    return cfg, packet


def assert_closed(schema):
    if isinstance(schema, list):
        for value in schema:
            assert_closed(value)
    elif isinstance(schema, dict):
        assert "default" not in schema
        if schema.get("type") == "object":
            assert schema["additionalProperties"] is False
            assert schema["required"] == list(schema["properties"])
        for value in schema.values():
            assert_closed(value)


@pytest.mark.parametrize("key_env", ["DEEPINFRA_API_KEY", "OPENROUTER_API_KEY"])
def test_openai_route_rejects_another_provider_credential(factual_setup, key_env):
    cfg, _ = factual_setup
    with pytest.raises(ValueError, match="credential must match"):
        Route.model_validate({**cfg.routes["chatter"].model_dump(), "key_env": key_env})


def test_openai_missing_key_cannot_fall_back_or_reserve(monkeypatch, factual_setup):
    cfg, _ = factual_setup
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "other-provider-test-only")
    monkeypatch.setattr(providers, "call_once", lambda *args: pytest.fail("reserved"))
    with pytest.raises(ValueError, match="configured provider credential missing"):
        providers.json_call(
            None,
            "writer:chatter:en",
            cfg.routes["chatter"],
            {"system": "Return JSON", "user": "A source"},
            cfg,
            transport=lambda *args, **kwargs: pytest.fail("sent"),
        )


def test_openai_keeps_image_input_and_reasoning_allowance(factual_setup):
    cfg, packet = factual_setup
    req = writer_request(selection(), packet, load_voice("chatter-en-v1"), cfg)
    req["images"] = ["https://example.com/source.jpg"]
    req["visual_essential"] = True
    body = providers.request_payload(cfg.routes["chatter"], req)
    assert body["messages"][1]["content"] == [
        {"type": "text", "text": req["user"]},
        {"type": "image_url", "image_url": {"url": req["images"][0]}},
    ]
    assert body["max_completion_tokens"] == 4096
    assert body["reasoning_effort"] == "medium"
    assert body["service_tier"] == "default"
    assert not {"max_tokens", "provider", "reasoning"} & body.keys()


@pytest.mark.parametrize("stage,temperature", [("editor", 0.2), ("pulse", 0)])
def test_factual_wire_binds_g2_schema_and_baseline_without_lowering_allowance(
    factual_setup, stage, temperature
):
    cfg, packet = factual_setup
    req = (
        editor_request(packet, cfg)
        if stage == "editor"
        else writer_request(selection(), packet, load_voice("pulse-en-v1"), cfg)
    )
    body = providers.request_payload(cfg.routes[stage], req)
    assert body["max_tokens"] == 65536
    assert body["temperature"] == temperature
    assert body["top_p"] == 0.95 and body["seed"] == 42
    assert body["reasoning_effort"] == "none"
    assert body["service_tier"] == "priority"
    assert not {"provider", "thinking", "reasoning"} & body.keys()
    assert body["response_format"]["type"] == "json_schema"
    output = body["response_format"]["json_schema"]
    assert output["strict"] is True
    schema = output["schema"]
    assert schema == req["response_schema"]
    assert "output_schema" not in json.loads(req["user"])
    assert_closed(schema)
    assert schema["$defs"]["SourceClaim"]["properties"]["support"]["anyOf"][0][
        "properties"
    ]["post_id"]["enum"] == ["S001"]
    root = schema["$defs"]["Event"] if stage == "editor" else schema
    assert next(iter(root["properties"])) == "source_check"
    assert "post_ids" not in root["properties"]
    # One request must never mutate the next request's bound schema.
    schema["$defs"]["SourceClaim"]["properties"]["support"]["anyOf"][0]["properties"][
        "post_id"
    ]["enum"].append("foreign")
    assert req["response_schema"]["$defs"]["SourceClaim"]["properties"]["support"][
        "anyOf"
    ][0]["properties"]["post_id"]["enum"] == ["S001"]


@pytest.mark.parametrize(
    "change",
    [
        {"reasoning": "medium"},
        {"vision": True},
        {"model": "other"},
        {
            "endpoint": "https://openrouter.ai/api/v1/chat/completions",
            "key_env": "OPENROUTER_API_KEY",
        },
    ],
)
def test_factual_profile_cannot_silently_change_route_or_thinking(
    factual_setup, change
):
    cfg, _ = factual_setup
    with pytest.raises(ValueError, match="factual profile"):
        Route.model_validate({**cfg.routes["editor"].model_dump(), **change})


def test_missing_schema_and_profile_overrides_fail_before_send(factual_setup):
    cfg, _ = factual_setup
    with pytest.raises(DeepInfraPermanentError, match="schema_missing"):
        providers.request_payload(cfg.routes["editor"], {"system": "", "user": ""})
    client = DeepInfraChatCompletionsClient(
        api_key="test-only",
        model=cfg.routes["editor"].model,
        request_profile="editorial_editor_v1",
    )
    for options in (
        {"reasoning_effort": "medium"},
        {"provider": {"allow_fallbacks": True}},
    ):
        with pytest.raises(DeepInfraPermanentError):
            client.build_request(max_tokens=65536, messages=[], **options)


def reply(model):
    return {
        "model": model,
        "id": "g2-fake-response",
        "service_tier": "priority",
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 20,
            "estimated_cost": 0.001,
            "completion_tokens_details": {"reasoning_tokens": 0},
        },
        "choices": [
            {"finish_reason": "stop", "message": {"content": '{"events": []}'}}
        ],
    }


@pytest.mark.parametrize(
    "defect,code",
    [
        ("thinking", "deepinfra_headline_usage_invalid"),
        ("tier", "deepinfra_service_tier_mismatch"),
        ("usage", "deepinfra_headline_usage_invalid"),
        ("cost", "deepinfra_headline_usage_invalid"),
        ("tokens", "deepinfra_headline_usage_invalid"),
        ("id", "deepinfra_headline_usage_invalid"),
        ("model", "served_model_mismatch"),
        ("length", "incomplete_model_response"),
        ("content", "deepinfra_response_content_invalid"),
        ("duplicate", "deepinfra_response_content_invalid"),
        ("entries", "invalid_source_support"),
    ],
)
def test_factual_reply_rejected_with_safe_usage_and_request_identity(
    monkeypatch, factual_setup, defect, code
):
    cfg, packet = factual_setup
    route = cfg.routes["editor"]
    decoded = reply(route.model)
    if defect == "thinking":
        decoded["usage"]["completion_tokens_details"]["reasoning_tokens"] = 123
    elif defect == "tier":
        decoded["service_tier"] = "standard"
    elif defect == "usage":
        del decoded["usage"]
    elif defect == "cost":
        decoded["usage"]["estimated_cost"] = "NaN"
    elif defect == "tokens":
        decoded["usage"]["prompt_tokens"] = True
    elif defect == "id":
        del decoded["id"]
    elif defect == "model":
        decoded["model"] = "other"
    elif defect == "length":
        decoded["choices"][0]["finish_reason"] = "length"
    else:
        decoded["choices"][0]["message"]["content"] = {
            "content": "PRIVATE MODEL TEXT",
            "duplicate": '{"events": [], "events": []}',
            "entries": '{"events": [null]}',
        }[defect]
    monkeypatch.setenv("DEEPINFRA_API_KEY", "private-test-key")
    monkeypatch.setattr(
        providers, "call_once", lambda row, stage, kind, ceiling, cfg, send: send()
    )
    req = editor_request(packet, cfg)
    with pytest.raises(ProviderReplyError) as caught:
        providers.json_call(
            None,
            "editor",
            route,
            req,
            cfg,
            transport=lambda *args, **kwargs: (200, json.dumps(decoded)),
        )
    assert caught.value.code == code
    diagnostics = caught.value.diagnostics
    assert diagnostics["elapsed_seconds"] >= 0
    assert (
        diagnostics["request_sha256"]
        == hashlib.sha256(
            json.dumps(
                providers.request_payload(route, req), ensure_ascii=False
            ).encode()
        ).hexdigest()
    )
    saved = json.dumps(diagnostics)
    assert "PRIVATE MODEL TEXT" not in saved and "private-test-key" not in saved
    if defect == "thinking":
        assert diagnostics["usage"]["reasoning_tokens"] == 123


def test_success_records_usage_and_elapsed_time_without_another_send(
    monkeypatch, factual_setup
):
    cfg, packet = factual_setup
    route = cfg.routes["editor"]
    monkeypatch.setenv("DEEPINFRA_API_KEY", "private-test-key")
    monkeypatch.setattr(
        providers, "call_once", lambda row, stage, kind, ceiling, cfg, send: send()
    )
    calls = []

    def transport(endpoint, key, body, **kwargs):
        calls.append(body)
        assert kwargs["timeout"] == 300
        return 200, json.dumps(reply(route.model))

    result = providers.json_call(
        None, "editor", route, editor_request(packet, cfg), cfg, transport=transport
    )
    assert result["data"] == {"events": []} and len(calls) == 1
    assert result["usage"]["reasoning_tokens"] == 0
    assert result["diagnostics"]["provider_request_id"] == "g2-fake-response"
    assert result["diagnostics"]["elapsed_seconds"] >= 0


@pytest.mark.parametrize(
    "failure,code",
    [
        (TimeoutError("PRIVATE"), "provider_timeout"),
        (OSError("PRIVATE"), "provider_transport_failure"),
        (http.client.IncompleteRead(b"PRIVATE"), "provider_transport_failure"),
        (ValueError("PRIVATE response exceeds cap"), "provider_transport_invalid"),
    ],
)
def test_transport_failures_keep_safe_timing_without_guessed_phase(
    monkeypatch, factual_setup, failure, code
):
    cfg, packet = factual_setup
    monkeypatch.setenv("DEEPINFRA_API_KEY", "private-test-key")
    monkeypatch.setattr(
        providers, "call_once", lambda row, stage, kind, ceiling, cfg, send: send()
    )
    sends = []

    def transport(*args, **kwargs):
        sends.append(1)
        raise failure

    with pytest.raises(ProviderReplyError) as caught:
        providers.json_call(
            None,
            "editor",
            cfg.routes["editor"],
            editor_request(packet, cfg),
            cfg,
            transport=transport,
        )
    assert caught.value.code == code and sends == [1]
    diagnostics = caught.value.diagnostics
    assert diagnostics["elapsed_seconds"] >= 0
    assert "http_status" not in diagnostics and "phase" not in diagnostics
    assert "PRIVATE" not in json.dumps(diagnostics)
