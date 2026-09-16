"""Selected DeepSeek 0731 transport is a closed two-role v3 contract."""

from __future__ import annotations

import json
import threading
import pytest
from hashlib import sha256
from pathlib import Path


def _tweets(count: int) -> list[dict]:
    return [
        {
            "tweet_id": f"tweet-{index}",
            "text": f"visible source {index}",
            "context": [f"stored context {index}"],
            "brand_ids": ["deepseek", "minimax"],
            "source_language": "en",
            "affiliations": [
                {"brand_id": "deepseek", "role": "official", "reviewed": True},
            ],
        }
        for index in range(count)
    ]


class FixedSlotTransport:
    request_profile = "deepseek_0731"
    request_identity = "fake-selected-route"

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.lock = threading.Lock()

    def messages_create(self, **kwargs):
        content = json.loads(kwargs["messages"][0]["content"])
        role = "content" if "POST-LEVEL LEGACY UNSANCTIONED FLAGS" in kwargs["system"] else "brand_interpretation"
        with self.lock:
            self.calls.append({"role": role, "request": kwargs, "payload": content})
        decisions = {}
        for slot in content["cases"].values():
            for decision_slot in slot["brand_decision_slots"]:
                decisions[decision_slot] = (
                    {"outcome": "classified", "post_types": ["hands_on_usage"]}
                    if role == "content"
                    else {
                        "product_labels": [],
                        "sentiment": "neutral",
                        "china_nationalism": None,
                        "us_nationalism": None,
                    }
                )
        response = {"decisions": decisions}
        if role == "content":
            response["post_flags"] = {
                post_slot: [] for post_slot in content["cases"]
            }
        return response


def test_selected_profile_uses_tested_deepinfra_request_without_native_json_mode():
    from x_monitor.openrouter import OpenRouterChatCompletionsClient

    client = OpenRouterChatCompletionsClient(
        api_key="test-key",
        model="deepseek/deepseek-v4-flash-0731",
        provider="DeepInfra",
        endpoint_tag="deepinfra/fp8",
        quantizations=["fp8"],
        reasoning_enabled=False,
        request_profile="deepseek_0731",
    )
    request = client.build_request(
        model="deepseek/deepseek-v4-flash-0731",
        max_tokens=6000,
        temperature=1.0,
        top_p=1.0,
        seed=42,
        messages=[{"role": "user", "content": "{}"}],
    )

    assert client.request_profile == "deepseek_0731"
    assert request["provider"]["only"] == ["deepinfra/fp8"]
    assert request["provider"]["allow_fallbacks"] is False
    assert request["provider"]["quantizations"] == ["fp8"]
    assert request["temperature"] == 1.0
    assert request["top_p"] == 1.0
    assert request["seed"] == 42
    assert request["reasoning"] == {"enabled": False, "exclude": True}
    assert "response_format" not in request
    assert "deepseek_0731" in client.request_identity


def test_selected_prompts_match_the_successful_r123_request_fixture():
    fixture = json.loads((Path(__file__).parent / "fixtures" /
        "u18_0731_prior45_r123_prompt_manifest.json").read_text())
    from x_monitor.attribution import classify_batch_pragmatics_full
    from x_monitor.classifier_0731_prompts import BRAND_PROMPT, CONTENT_PROMPT

    shared_relevance_rule = """

SHARED TARGET-BRAND RELEVANCE: A visible statement about the target brand is usable even within a multi-brand roundup or parent-company report. A recommendation of the target is usable evidence; a bare name, handle, hashtag, or link is not. Apply the same evidence standard in both roles. Neutral reporting of target research is usable but is not praise.

FINAL CHECK: other must be the only post type when selected. No usable target evidence means context_missing with empty post_types and product_labels and null scalars. With usable evidence, sentiment is positive, negative, neutral, or mixed; nationalism is none when no national framing is present.
"""

    for role, prompt in (("content", CONTENT_PROMPT), ("brand", BRAND_PROMPT)):
        assert len(prompt.encode("utf-8")) == fixture[role]["utf8_bytes"]
        assert sha256(prompt.encode("utf-8")).hexdigest() == fixture[role]["sha256"]

    transport = FixedSlotTransport()
    classify_batch_pragmatics_full(_tweets(1), [], transport)
    prompts = {call["role"]: call["request"]["system"] for call in transport.calls}
    assert prompts == {
        "content": CONTENT_PROMPT + shared_relevance_rule,
        "brand_interpretation": BRAND_PROMPT + shared_relevance_rule,
    }


def test_selected_profile_rejects_a_route_or_sampling_drift():
    from x_monitor.openrouter import OpenRouterChatCompletionsClient, OpenRouterPermanentError

    client = OpenRouterChatCompletionsClient(
        api_key="test-key",
        model="deepseek/deepseek-v4-flash-0731",
        provider="DeepInfra",
        endpoint_tag="deepinfra/fp8",
        quantizations=["fp8"],
        reasoning_enabled=False,
        request_profile="deepseek_0731",
    )
    for kwargs in (
        {"temperature": 0.0, "top_p": 1.0, "seed": 42},
        {"temperature": 1.0, "top_p": 0.9, "seed": 42},
        {"temperature": 1.0, "top_p": 1.0, "seed": 7},
    ):
        try:
            client.build_request(max_tokens=1, messages=[], **kwargs)
        except OpenRouterPermanentError as error:
            assert str(error) == "openrouter_deepseek_0731_contract_mismatch"
        else:  # pragma: no cover - regression assertion
            raise AssertionError("selected request accepted a drift")


def test_factory_preserves_the_explicit_selected_profile_and_response_alias(monkeypatch):
    from x_monitor.config import LlmConfig
    from x_monitor.reattribute import build_classifier_client_from_env

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    cfg = type("Config", (), {"llm": LlmConfig(
        classifier_provider="openrouter",
        classifier_model="deepseek/deepseek-v4-flash-0731",
        classifier_openrouter_provider="DeepInfra",
        classifier_openrouter_response_provider="DeepInfra",
        classifier_openrouter_response_model="deepseek/deepseek-v4-flash-20260731",
        classifier_openrouter_endpoint_tag="deepinfra/fp8",
        classifier_openrouter_quantizations=["fp8"],
        classifier_openrouter_reasoning_enabled=False,
        classifier_openrouter_request_profile="deepseek_0731",
    )})()
    client = build_classifier_client_from_env(cfg)

    assert client.request_profile == "deepseek_0731"
    assert client.response_model == "deepseek/deepseek-v4-flash-20260731"


def test_selected_runtime_maps_fixed_slots_to_v3_ids_and_affiliations_for_both_roles():
    from x_monitor.attribution import (
        _two_role_selected_system_prompt,
        classify_batch_pragmatics_full,
    )

    content_system = _two_role_selected_system_prompt("content")
    brand_system = _two_role_selected_system_prompt("brand_interpretation")
    assert "Exact envelope" not in content_system + brand_system
    assert '"results"' not in content_system + brand_system
    assert '"post_flags"' in content_system
    assert '"post_flags"' not in brand_system

    transport = FixedSlotTransport()
    rows = classify_batch_pragmatics_full(_tweets(20), [], transport, max_tokens=6000)

    assert len(transport.calls) == 2
    assert {call["role"] for call in transport.calls} == {"content", "brand_interpretation"}
    assert all(row["valid"] is True for row in rows)
    assert all(set(row["by_brand"]) == {"deepseek", "minimax"} for row in rows)
    assert [rows[0]["classification_trace"][stage]["role_revision"] for stage in (
        "content", "brand_interpretation", "final"
    )] == [
        "stage1-content-0731-v4",
        "stage1-brand-interpretation-0731-v4",
        "stage1-two-role-merge-0731-v4",
    ]
    for call in transport.calls:
        request = call["request"]
        assert request["temperature"] == 1.0
        assert request["top_p"] == 1.0
        assert request["seed"] == 42
        assert request["thinking"] == {"type": "disabled"}
        assert set(call["payload"]) == {"cases"}
        assert set(call["payload"]["cases"]) == {f"P{number:02d}" for number in range(1, 21)}
        assert call["payload"]["cases"]["P01"]["brand_decision_slots"] == {
            "D01": "deepseek", "D02": "minimax",
        }
        assert call["payload"]["cases"]["P01"]["evidence"]["affiliations"] == [
            {"brand_id": "deepseek", "role": "official", "reviewed": True},
        ]
        assert "tweet_id" not in json.dumps(call["payload"])
        assert "input_context_fingerprint" not in json.dumps(call["payload"])
        assert "case_id_for_audit_only" not in json.dumps(call["payload"])
        assert list(call["payload"]["cases"]["P01"]["evidence"]) == [
            "source_language", "text", "context", "affiliations",
        ]


def test_selected_runtime_keeps_the_two_requests_per_20_post_batch_cap():
    from x_monitor.attribution import classify_batch_pragmatics_full

    transport = FixedSlotTransport()
    rows = classify_batch_pragmatics_full(_tweets(21), [], transport, max_workers=3)

    assert len(transport.calls) == 4
    assert all(row["valid"] is True for row in rows)
    assert sorted(len(call["payload"]["cases"]) for call in transport.calls) == [1, 1, 20, 20]
    assert [call["role"] for call in transport.calls].count("content") == 2
    assert [call["role"] for call in transport.calls].count("brand_interpretation") == 2


def test_selected_runtime_rejects_missing_duplicate_or_extra_slot_and_does_not_repair():
    from x_monitor.attribution import classify_batch_pragmatics_full

    class InvalidSlots(FixedSlotTransport):
        def messages_create(self, **kwargs):
            response = super().messages_create(**kwargs)
            if "POST-LEVEL LEGACY UNSANCTIONED FLAGS" in kwargs["system"]:
                response["decisions"].pop("D01")
                response["decisions"]["D99"] = {
                    "outcome": "classified", "post_types": ["hands_on_usage"],
                }
            return response

    transport = InvalidSlots()
    rows = classify_batch_pragmatics_full(_tweets(1), [], transport)
    assert len(transport.calls) == 2
    assert rows == [{"by_brand": {}, "unsanctioned_flags": [], "valid": False}]


def test_selected_runtime_rejects_conflicting_role_outputs_without_coercion():
    from x_monitor.attribution import classify_batch_pragmatics_full

    class ConflictingRoles(FixedSlotTransport):
        def messages_create(self, **kwargs):
            response = super().messages_create(**kwargs)
            if "POST-LEVEL LEGACY UNSANCTIONED FLAGS" in kwargs["system"]:
                response["decisions"] = {
                    slot: {"outcome": "context_missing", "post_types": []}
                    for slot in response["decisions"]
                }
            else:
                response["decisions"] = {
                    slot: {
                        "product_labels": ["testimonial"],
                        "sentiment": "positive",
                        "china_nationalism": None,
                        "us_nationalism": None,
                    }
                    for slot in response["decisions"]
                }
            return response

    rows = classify_batch_pragmatics_full(_tweets(1), [], ConflictingRoles())
    assert rows == [{"by_brand": {}, "unsanctioned_flags": [], "valid": False}]


@pytest.mark.parametrize("fault", ["other_overlap", "unknown_type", "invalid_sentiment", "invalid_flag"])
def test_selected_runtime_isolates_invalid_values_to_the_entire_affected_post(fault):
    """One bad brand answer used to discard all twenty independent posts."""
    from x_monitor.attribution import classify_batch_pragmatics_full

    class InvalidValue(FixedSlotTransport):
        def messages_create(self, **kwargs):
            response = super().messages_create(**kwargs)
            content = "post_flags" in response
            if content and fault == "other_overlap":
                response["decisions"]["D02"]["post_types"] = ["hands_on_usage", "other"]
            elif content and fault == "unknown_type":
                response["decisions"]["D02"]["post_types"] = ["invented_type"]
            elif not content and fault == "invalid_sentiment":
                response["decisions"]["D02"]["sentiment"] = "invented_sentiment"
            elif content and fault == "invalid_flag":
                response["post_flags"]["P01"] = ["invented_flag"]
            return response

    transport = InvalidValue()
    rows = classify_batch_pragmatics_full(_tweets(20), [], transport)
    assert len(transport.calls) == 2
    assert rows[0] == {"by_brand": {}, "unsanctioned_flags": [], "valid": False}
    assert all(row["valid"] and set(row["by_brand"]) == {"deepseek", "minimax"}
               for row in rows[1:])


@pytest.mark.parametrize("fault", ["missing_slot", "extra_field", "extra_post"])
def test_selected_runtime_still_rejects_entire_batch_for_envelope_drift(fault):
    from x_monitor.attribution import classify_batch_pragmatics_full

    class InvalidEnvelope(FixedSlotTransport):
        def messages_create(self, **kwargs):
            response = super().messages_create(**kwargs)
            if "post_flags" in response:
                if fault == "missing_slot":
                    response["decisions"].pop("D02")
                elif fault == "extra_field":
                    response["decisions"]["D02"]["extra"] = True
                else:
                    response["post_flags"]["P99"] = []
            return response

    transport = InvalidEnvelope()
    rows = classify_batch_pragmatics_full(_tweets(20), [], transport)
    assert len(transport.calls) == 2
    assert all(not row["valid"] for row in rows)


def test_selected_decoder_accepts_one_json_fence_and_retains_usage_on_terminal_shape_errors(monkeypatch, caplog):
    from x_monitor import openrouter
    from x_monitor.attribution import _call_signal_with_retry

    client = openrouter.OpenRouterChatCompletionsClient(
        api_key="test-key",
        model="deepseek/deepseek-v4-flash-0731",
        provider="DeepInfra",
        endpoint_tag="deepinfra/fp8",
        quantizations=["fp8"],
        reasoning_enabled=False,
        request_profile="deepseek_0731",
    )
    payload = {
        "id": "req-0731", "model": "deepseek/deepseek-v4-flash-0731",
        "openrouter_metadata": {"endpoints": {"available": [{
            "provider": "DeepInfra", "model": "deepseek/deepseek-v4-flash-0731", "selected": True,
        }]}},
        "choices": [{"finish_reason": "stop", "message": {"content": "```json\n{}\n```"}}],
        "usage": {"prompt_tokens": 9, "completion_tokens": 2, "total_tokens": 11, "cost": 0.01},
    }

    class Response:
        status = 200
        def read(self): return json.dumps(payload).encode()

    class Connection:
        def __init__(self, *args, **kwargs): pass
        def request(self, *args, **kwargs): pass
        def getresponse(self): return Response()
        def close(self): pass

    monkeypatch.setattr(openrouter.http.client, "HTTPSConnection", Connection)
    assert client.messages_create(
        model="deepseek/deepseek-v4-flash-0731", max_tokens=1,
        temperature=1.0, top_p=1.0, seed=42, messages=[],
    ) == {}

    payload["choices"][0]["finish_reason"] = "length"
    try:
        _call_signal_with_retry(
            client, "{}", model="deepseek/deepseek-v4-flash-0731", max_tokens=1,
            temperature=1.0, top_p=1.0, seed=42,
        )
    except openrouter.OpenRouterPermanentError as error:
        assert str(error) == "openrouter_response_incomplete"
        assert error.provider_usage["cost_usd"] == 0.01
    else:  # pragma: no cover - regression assertion
        raise AssertionError("non-stop selected response was accepted")
    terminal_event = [
        record.provider_transport_event for record in caplog.records
        if getattr(record, "provider_transport_event", {}).get("error_type")
        == "OpenRouterPermanentError"
    ][-1]
    assert terminal_event["usage_source"] == "provider"
    assert terminal_event["usage"]["cost_usd"] == 0.01

    payload["choices"][0]["finish_reason"] = "stop"
    payload["choices"][0]["message"]["content"] = '{"decisions":{"D01":{},"D01":{}}}'
    try:
        client.messages_create(
            model="deepseek/deepseek-v4-flash-0731", max_tokens=1,
            temperature=1.0, top_p=1.0, seed=42, messages=[],
        )
    except openrouter.OpenRouterPermanentError as error:
        assert str(error) == "openrouter_response_content_invalid"
        assert error.provider_usage["provider_request_id"] == "req-0731"
    else:  # pragma: no cover - regression assertion
        raise AssertionError("duplicate response key was accepted")
