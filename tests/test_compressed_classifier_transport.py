"""Exercise physical-call accounting through the application's real wrapper."""

import json
from decimal import Decimal
from types import SimpleNamespace

import pytest

from tests.test_compressed_classifier import answers, case, extraction


@pytest.mark.parametrize(("options", "expected_max_tokens"), [({}, 65_536), ({"max_tokens": 6000}, 6000)])
def test_selected_batch_entry_uses_two_accounted_calls_and_versioned_trace(options, expected_max_tokens):
    from monitor.cycle import _BoundedClassifierClient
    from x_monitor.attribution import BrandRow, classify_batch_pragmatics_full
    from x_monitor.compressed_classifier import make_extraction_request

    class Client:
        request_profile = "compressed8_pulse_v1"
        request_identity = "synthetic-combined"
        model = "deepseek-ai/DeepSeek-V4-Flash-0731"
        release_channels = ("api", "weights")

        def messages_create(self, **kwargs):
            if kwargs["model"].startswith("deepseek"):
                return extraction()
            return answers(json.loads(kwargs["messages"][0]["content"]))

    dispatches = []
    client = _BoundedClassifierClient(Client(), maximum_calls=6, pause_seconds=0, before_dispatch=lambda request: dispatches.append(dict(request)))
    sample = case()
    tweet = {"tweet_id": sample["case_id"], "text": sample["state"]["source_text"],
             "brand_ids": ["qwen"], "tracked_brand_catalog": sample["state"]["tracked_brands"]}
    result = classify_batch_pragmatics_full([tweet], [BrandRow("qwen", "Qwen", "#000", False)], client, max_workers=1, **options)[0]
    assert result["valid"]
    assert client.calls == len(dispatches) == 2
    assert [row["model"] for row in dispatches] == [Client.model, "jev-1.14.0"]
    assert dispatches[0]["max_tokens"] == expected_max_tokens
    assert make_extraction_request(sample, release_channels=Client.release_channels, **options)["max_tokens"] == expected_max_tokens
    assert all(row["_batch_context"]["post_ids"] == [sample["case_id"]] for row in dispatches)
    assert result["classification_trace"]["final"]["prompt_version"] == "compressed8-pulse-merge-v4"
    assert result["release_findings"][0]["observed_name"] == "Qwen4"


@pytest.mark.parametrize("failures, valid, attempts", [(1, True, 2), (3, False, 3)])
def test_batch_retries_only_failed_jev_stage_and_accounts_for_every_attempt(monkeypatch, failures, valid, attempts):
    from monitor.cycle import _BoundedClassifierClient
    from x_monitor import attribution
    from x_monitor.jev_classifier import CompressedClassifierClient, JevClassifierClient, JevRetryableError

    extraction_calls, jev_requests, dispatches, outcomes, errors, sleeps = [], [], [], [], [], []
    monkeypatch.setattr(attribution.time, "sleep", sleeps.append)

    def extract(**kwargs):
        extraction_calls.append(kwargs)
        return extraction()

    def classify(request, timeout):
        jev_requests.append(request)
        if len(jev_requests) <= failures:
            raise TimeoutError("synthetic Jev timeout")
        return {**answers(request), "usage": {"input_tokens": 100, "output_tokens": 10}}

    delegate = CompressedClassifierClient(
        extraction=SimpleNamespace(_base_url="https://api.deepinfra.com/v1/openai", messages_create=extract),
        classification=JevClassifierClient(api_key="fixture-key", transport=classify),
    )
    client = _BoundedClassifierClient(delegate, maximum_calls=6, pause_seconds=0,
                                     before_dispatch=lambda request: dispatches.append(dict(request)),
                                     after_call=outcomes.append)
    sample = case()
    tweet = {"tweet_id": sample["case_id"], "text": sample["state"]["source_text"],
             "brand_ids": ["qwen"], "tracked_brand_catalog": sample["state"]["tracked_brands"]}
    result, = attribution.classify_batch_pragmatics_full(
        [tweet], [attribution.BrandRow("qwen", "Qwen", "#000", False)], client, max_workers=1,
        on_batch_error=lambda tweets, error: errors.append(error),
    )
    assert result["valid"] is valid
    assert len(extraction_calls) == 1
    assert len(jev_requests) == attempts
    assert all(request == jev_requests[0] for request in jev_requests)
    assert client.calls == len(dispatches) == len(outcomes) == 1 + attempts
    assert client.remaining_calls == 6 - client.calls  # Unused reservations are released even on exhaustion.
    assert [row["model"] for row in dispatches] == [delegate.model, *(["jev-1.14.0"] * attempts)]
    assert [row["_batch_context"]["role"] for row in dispatches] == ["extraction", *(["classification"] * attempts)]
    assert all(row["_batch_context"]["post_ids"] == [sample["case_id"]] for row in dispatches)
    assert sum(isinstance(outcome, JevRetryableError) for outcome in outcomes) == failures
    assert sleeps == [1.0, 2.0][:attempts - 1]
    if valid:
        assert errors == []
        assert outcomes[-1].provider_usage["input_tokens"] == 100
        assert result["release_findings"][0]["observed_name"] == "Qwen4"
    else:
        assert len(errors) == 1 and isinstance(errors[0], JevRetryableError)
        assert result["by_brand"] == {}
        assert "release_findings" not in result


def test_jev_transport_reports_tokens_and_estimated_cost_without_implicit_retry():
    from x_monitor.jev_classifier import JevClassifierClient

    calls = []
    request = {"model": "jev-1.14.0", "state": {"text": "hello"}, "questions": {"q": {"type": "noul"}}}
    document = {"model": "jev-1.14.0", "answers": {"q": {"type": "noul", "noul": 0.9}},
                "usage": {"input_tokens": 100, "output_tokens": 10}}
    client = JevClassifierClient(api_key="fixture-key", transport=lambda req, timeout: calls.append((req, timeout)) or document)
    response = client.messages_create(model="jev-1.14.0", messages=[{"role": "user", "content": json.dumps(request)}], max_tokens=1, timeout=17)
    assert calls == [(request, 17)]
    assert response.provider_usage["input_tokens"] == 100
    assert response.provider_usage["output_tokens"] == 10
    assert Decimal(str(response.provider_usage["cost_usd"])) == Decimal("0.0000042")
    assert "fixture-key" not in repr(client)


def test_wrong_jev_model_retains_usage_on_error():
    from x_monitor.jev_classifier import JevClassifierClient, JevPermanentError

    document = {"model": "wrong-model", "answers": {}, "usage": {"input_tokens": 100, "output_tokens": 10}}
    client = JevClassifierClient(api_key="fixture-key", transport=lambda req, timeout: document)
    request = {"model": "jev-1.14.0", "state": "hello", "questions": {"q": {"type": "noul"}}}
    with pytest.raises(JevPermanentError) as error:
        client.messages_create(model="jev-1.14.0", messages=[{"role": "user", "content": json.dumps(request)}], max_tokens=1)
    assert error.value.provider_usage["input_tokens"] == 100


def test_jev_budget_bound_is_explicit_and_missing_shape_is_rejected():
    from monitor.enrichment_budget import request_cost_bound
    from x_monitor.attribution import LLMCallBudgetExhausted

    request = {"model": "jev-1.14.0", "max_tokens": 1,
               "messages": [{"role": "user", "content": json.dumps({"model": "jev-1.14.0", "state": "source", "questions": {"q": {"type": "noul"}}})}]}
    assert request_cost_bound(request) == Decimal("0.002753")
    with pytest.raises(LLMCallBudgetExhausted):
        request_cost_bound({"model": "jev-1.14.0"})


def test_combined_factory_needs_both_credentials_without_falling_back(monkeypatch):
    from x_monitor.config import Config
    from x_monitor.reattribute import build_classifier_client_from_env

    cfg = Config(enabled_models=["deepseek"], daily_ceiling=100)
    cfg.llm.classifier_pipeline = "compressed8_pulse_v1"
    cfg.llm.classifier_provider = "deepinfra"
    cfg.llm.classifier_model = "deepseek-ai/DeepSeek-V4-Flash-0731"
    cfg.llm.classifier_base_url = "https://api.deepinfra.com/v1/openai"
    cfg.llm.classifier_deepinfra_request_profile = "deepseek_0731"
    monkeypatch.setenv("DEEPINFRA_API_KEY", "fixture-key")
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    assert build_classifier_client_from_env(cfg) is None
    monkeypatch.setenv("TYPESAFE_API_KEY", "fixture-jev-key")
    client = build_classifier_client_from_env(cfg)
    assert client.request_profile == "compressed8_pulse_v1"
    assert "fixture-jev-key" not in repr(client)
