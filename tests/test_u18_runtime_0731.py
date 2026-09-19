"""Selected DeepSeek 0731 transport is a closed two-role v4 contract."""

from __future__ import annotations

import json
import threading
import pytest


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
        role = "content" if "CONTENT ROLE:" in kwargs["system"] else "brand_interpretation"
        with self.lock:
            self.calls.append({"role": role, "request": kwargs, "payload": content})
        decisions = {}
        for slot in content["cases"].values():
            for decision_slot in slot["brand_decision_slots"]:
                decisions[decision_slot] = (
                    {
                        "outcome": "classified",
                        "post_types": ["hands_on_usage"],
                        "audience_topics": ["none"],
                    }
                    if role == "content"
                    else {
                        "product_labels": ["none"],
                        "sentiment": "neutral",
                        "geopolitical_modes": ["none"],
                        "china_national_stance": "none",
                        "us_national_stance": "none",
                    }
                )
        response = {"decisions": decisions}
        if role == "content":
            response["post_promotions"] = {post_slot: ["none"] for post_slot in content["cases"]}
            response["promoted_subjects"] = {post_slot: [] for post_slot in content["cases"]}
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


def test_selected_prompts_render_the_v4_fixed_slot_contract():
    from x_monitor.attribution import classify_batch_pragmatics_full
    from x_monitor.classifier_0731_prompts import BRAND_PROMPT, CONTENT_PROMPT

    assert "results_analysis" in CONTENT_PROMPT
    assert "news_reporting" in CONTENT_PROMPT
    assert "investigate_claim" in BRAND_PROMPT
    assert "general is an exclusive fallback" in CONTENT_PROMPT

    transport = FixedSlotTransport()
    classify_batch_pragmatics_full(_tweets(1), [], transport)
    prompts = {call["role"]: call["request"]["system"] for call in transport.calls}
    assert "D01, D02" in prompts["content"]
    assert "P01" in prompts["content"]
    assert "D01, D02" in prompts["brand_interpretation"]


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


def test_selected_runtime_maps_fixed_slots_to_v4_catalog_and_affiliations_for_both_roles():
    from x_monitor.attribution import (
        _two_role_selected_system_prompt,
        classify_batch_pragmatics_full,
    )

    content_system = _two_role_selected_system_prompt("content")
    brand_system = _two_role_selected_system_prompt("brand_interpretation")
    assert "results_analysis" in content_system
    assert "investigate_claim" in brand_system
    assert '"post_promotions"' not in content_system  # prose uses bare JSON key names

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
        assert set(call["payload"]) == {"tracked_brands", "cases"}
        assert set(call["payload"]["cases"]) == {f"P{number:02d}" for number in range(1, 21)}
        assert call["payload"]["cases"]["P01"]["brand_decision_slots"] == {
            "D01": "deepseek", "D02": "minimax",
        }
        assert call["payload"]["cases"]["P01"]["evidence"]["author_affiliations"] == [
            {"brand_id": "deepseek", "role": "official", "reviewed": True},
        ]
        assert "tweet_id" not in json.dumps(call["payload"])
        assert "input_context_fingerprint" not in json.dumps(call["payload"])
        assert "case_id_for_audit_only" not in json.dumps(call["payload"])
        assert list(call["payload"]["cases"]["P01"]["evidence"]) == [
            "created_at", "source_language", "source_text", "english_translation", "context", "author_affiliations",
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
            if "CONTENT ROLE:" in kwargs["system"]:
                response["decisions"].pop("D01")
                response["decisions"]["D99"] = {
                    "outcome": "classified", "post_types": ["hands_on_usage"], "audience_topics": ["none"],
                }
            return response

    transport = InvalidSlots()
    rows = classify_batch_pragmatics_full(_tweets(1), [], transport)
    assert len(transport.calls) == 2
    assert rows == [{"by_brand": {}, "unsanctioned_flags": [], "valid": False}]


def test_selected_runtime_makes_other_axes_unavailable_for_context_missing():
    from x_monitor.attribution import classify_batch_pragmatics_full

    class ConflictingRoles(FixedSlotTransport):
        def messages_create(self, **kwargs):
            response = super().messages_create(**kwargs)
            if "CONTENT ROLE:" in kwargs["system"]:
                response["decisions"] = {
                    slot: {"outcome": "context_missing", "post_types": [], "audience_topics": ["unavailable"]}
                    for slot in response["decisions"]
                }
            else:
                response["decisions"] = {
                    slot: {
                        "product_labels": ["testimonial"],
                        "sentiment": "positive",
                        "geopolitical_modes": ["none"],
                        "china_national_stance": "none",
                        "us_national_stance": "none",
                    }
                    for slot in response["decisions"]
                }
            return response

    rows = classify_batch_pragmatics_full(_tweets(1), [], ConflictingRoles())
    assert rows[0]["valid"] is True
    assert rows[0]["by_brand"]["minimax"] == {
        "outcome": "context_missing",
        "post_types": [],
        "audience_topics": [],
        "audience_topics_state": "unavailable",
        "product_labels": [],
        "sentiment": None,
        "geopolitical_modes": [],
        "geopolitical_modes_state": "unavailable",
        "china_national_stance": None,
        "us_national_stance": None,
    }


def test_selected_runtime_adds_nationalism_mode_implied_by_national_stance():
    """A stance answer deterministically entails the nationalism mode."""
    from x_monitor.attribution import classify_batch_pragmatics_full

    class OmittedImpliedMode(FixedSlotTransport):
        def messages_create(self, **kwargs):
            response = super().messages_create(**kwargs)
            if "CONTENT ROLE:" not in kwargs["system"]:
                response["decisions"]["D01"].update(
                    geopolitical_modes=["framework"],
                    china_national_stance="constructive_critical",
                )
            return response

    rows = classify_batch_pragmatics_full(_tweets(1), [], OmittedImpliedMode())

    assert rows[0]["valid"] is True
    assert rows[0]["by_brand"]["deepseek"]["geopolitical_modes"] == [
        "framework",
        "nationalism",
    ]
    assert (
        rows[0]["by_brand"]["deepseek"]["china_national_stance"]
        == "constructive_critical"
    )


def test_selected_runtime_unwraps_explicit_singleton_promotion_object():
    """The selected model sometimes wraps one promotion enum in an object."""
    from x_monitor.attribution import classify_batch_pragmatics_full

    class WrappedPromotion(FixedSlotTransport):
        def messages_create(self, **kwargs):
            response = super().messages_create(**kwargs)
            if "CONTENT ROLE:" in kwargs["system"]:
                response["post_promotions"]["P01"] = {"promotion": "none"}
            return response

    rows = classify_batch_pragmatics_full(_tweets(1), [], WrappedPromotion())

    assert rows[0]["valid"] is True
    assert rows[0]["untracked_brand_promotions"] == []


@pytest.mark.parametrize("fault", ["other_overlap", "unknown_type", "invalid_sentiment", "invalid_flag"])
def test_selected_runtime_isolates_invalid_values_to_the_entire_affected_post(fault):
    """One bad brand answer used to discard all twenty independent posts."""
    from x_monitor.attribution import classify_batch_pragmatics_full

    class InvalidValue(FixedSlotTransport):
        def messages_create(self, **kwargs):
            response = super().messages_create(**kwargs)
            content = "post_promotions" in response
            if content and fault == "other_overlap":
                response["decisions"]["D02"]["post_types"] = ["hands_on_usage", "other"]
            elif content and fault == "unknown_type":
                response["decisions"]["D02"]["post_types"] = ["invented_type"]
            elif not content and fault == "invalid_sentiment":
                response["decisions"]["D02"]["sentiment"] = "invented_sentiment"
            elif content and fault == "invalid_flag":
                response["post_promotions"]["P01"] = ["invented_flag"]
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
            if "post_promotions" in response:
                if fault == "missing_slot":
                    response["decisions"].pop("D02")
                elif fault == "extra_field":
                    response["decisions"]["D02"]["extra"] = True
                else:
                    response["post_promotions"]["P99"] = ["none"]
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
