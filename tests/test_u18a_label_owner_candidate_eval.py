"""Provider-free proof of the bounded label-owner candidate harness."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import u18a_label_owner_candidate_eval as evaluation
from x_monitor.deepinfra import DeepInfraPermanentError, DeepInfraRetryableError


class FakeSelectedClient:
    model = evaluation.MODEL
    request_profile = evaluation.PROFILE

    def __init__(self, responses):
        self.responses = list(responses)
        self.sent = 0

    def build_request(self, **kwargs):
        return {"model": self.model, "max_tokens": kwargs["max_tokens"], "messages": kwargs["messages"]}

    def messages_create(self, **_kwargs):
        self.sent += 1
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return SimpleNamespace(provider_usage=response)


def _usage(*, cost="0.01", input_tokens=50, output_tokens=10):
    return {
        "provider": "DeepInfra", "model": evaluation.MODEL,
        "provider_request_id": "fake-provider-request",
        "input_tokens": input_tokens, "output_tokens": output_tokens,
        "cost_usd": cost,
    }


def _call(budget, request_hash):
    kwargs = {"max_tokens": 100, "messages": [{"role": "user", "content": "frozen input"}]}
    assert evaluation._digest(budget.delegate.build_request(**kwargs)) == request_hash
    return budget.messages_create(**kwargs)


def test_prepare_freezes_twenty_actual_selected_requests_without_provider(tmp_path):
    path = tmp_path / "contract"
    contract = evaluation.prepare(path)
    assert contract["route"] == {
        "provider": "DeepInfra", "model": evaluation.MODEL,
        "request_profile": "deepseek_0731",
    }
    assert contract["baseline_reservation"]["logical_requests"] == 20
    assert contract["caps"]["physical_requests"] == 39
    assert contract["baseline_reservation"]["input_tokens"] <= 250_000
    assert contract["baseline_reservation"]["output_tokens"] <= 100_000
    assert float(contract["baseline_reservation"]["cost_usd"]) <= 10
    assert len(contract["cases"]) == 10
    assert all(len(case["request_hashes"]) == 2 for case in contract["cases"])
    assert json.loads((path / "contract.json").read_text()) == contract
    with pytest.raises(FileExistsError):
        evaluation.prepare(path)


def test_run_live_requires_explicit_flag_before_client_construction(tmp_path, monkeypatch):
    path = tmp_path / "contract"
    evaluation.prepare(path)
    from x_monitor import reattribute

    def forbidden_client(_cfg):
        raise AssertionError("credentialed client constructed without live flag")

    monkeypatch.setattr(reattribute, "build_classifier_client_from_env", forbidden_client)
    with pytest.raises(ValueError, match="requires --execute-live"):
        evaluation.run_live(path)
    assert not (path / "live-run").exists()


@pytest.mark.parametrize("missing_field", [None, "cost_usd"])
def test_missing_usage_fails_closed_before_another_request(tmp_path, missing_field):
    reported_usage = _usage() if missing_field else None
    if reported_usage is not None:
        reported_usage.pop(missing_field)
    delegate = FakeSelectedClient([reported_usage, _usage()])
    budget = evaluation.BudgetTransport(delegate, tmp_path / "attempts")
    request = delegate.build_request(max_tokens=100, messages=[{"role": "user", "content": "frozen input"}])
    identity = evaluation._digest(request)
    budget.start_case("test", [identity])
    with pytest.raises(DeepInfraPermanentError, match="missing provider (cost )?usage"):
        _call(budget, identity)
    with pytest.raises(DeepInfraPermanentError):
        _call(budget, identity)
    assert delegate.sent == 1
    assert budget.uncertain_usage
    assert budget.physical_attempts == 1
    assert (tmp_path / "attempts/attempt-001.started.json").exists()
    assert (tmp_path / "attempts/attempt-001.result.json").exists()


def test_one_transport_retry_is_ceiling_even_if_classifier_would_retry_again(tmp_path):
    first = DeepInfraRetryableError("retryable_with_usage")
    first.provider_usage = _usage()
    second = DeepInfraRetryableError("retryable_with_usage")
    second.provider_usage = _usage()
    delegate = FakeSelectedClient([first, second, _usage()])
    budget = evaluation.BudgetTransport(delegate, tmp_path / "attempts")
    request = delegate.build_request(max_tokens=100, messages=[{"role": "user", "content": "frozen input"}])
    identity = evaluation._digest(request)
    budget.start_case("test", [identity])
    with pytest.raises(DeepInfraRetryableError):
        _call(budget, identity)
    with pytest.raises(DeepInfraPermanentError, match="retry_ceiling_reached"):
        _call(budget, identity)
    with pytest.raises(DeepInfraPermanentError):
        _call(budget, identity)
    assert delegate.sent == 2
    assert budget.logical_requests == 1
    assert budget.physical_attempts == 2
    assert not budget.uncertain_usage


def test_unmetered_transport_error_aborts_without_retry(tmp_path):
    delegate = FakeSelectedClient([DeepInfraRetryableError("timeout"), _usage()])
    budget = evaluation.BudgetTransport(delegate, tmp_path / "attempts")
    request = delegate.build_request(max_tokens=100, messages=[{"role": "user", "content": "frozen input"}])
    identity = evaluation._digest(request)
    budget.start_case("test", [identity])
    with pytest.raises(DeepInfraPermanentError, match="missing_provider_usage_on_error"):
        _call(budget, identity)
    assert delegate.sent == 1
    assert budget.uncertain_usage
    assert budget.blocked_reason == "missing_provider_usage_on_error"


def test_output_ceiling_blocks_before_any_provider_attempt(tmp_path, monkeypatch):
    delegate = FakeSelectedClient([_usage()])
    budget = evaluation.BudgetTransport(delegate, tmp_path / "attempts")
    request = delegate.build_request(max_tokens=100, messages=[{"role": "user", "content": "frozen input"}])
    identity = evaluation._digest(request)
    budget.start_case("test", [identity])
    monkeypatch.setattr(evaluation, "MAX_OUTPUT_TOKENS", 99)
    with pytest.raises(DeepInfraPermanentError, match="evaluation_ceiling_reached"):
        _call(budget, identity)
    assert delegate.sent == 0
    assert budget.physical_attempts == 0


def test_physical_call_ceiling_counts_retries_before_provider_attempt(tmp_path, monkeypatch):
    delegate = FakeSelectedClient([_usage()])
    budget = evaluation.BudgetTransport(delegate, tmp_path / "attempts")
    request = delegate.build_request(max_tokens=100, messages=[{"role": "user", "content": "frozen input"}])
    identity = evaluation._digest(request)
    budget.start_case("test", [identity])
    monkeypatch.setattr(evaluation, "MAX_PHYSICAL_REQUESTS", 0)
    with pytest.raises(DeepInfraPermanentError, match="evaluation_ceiling_reached"):
        _call(budget, identity)
    assert delegate.sent == 0
    assert budget.physical_attempts == 0


def test_full_result_and_ownership_boundary_are_reported_separately():
    fixture = evaluation._read_json(evaluation.FIXTURE)
    case = next(case for case in fixture["cases"] if case["case_id"] == "token_machine_deepseek_win")
    actual = json.loads(json.dumps(case["expected"]))
    actual["promoted_subjects"][0]["evidence"] = "Free AI tokens every day"
    comparison = evaluation._compare(case["expected"], {"valid": True, **actual}, "deepseek")
    assert comparison["ownership_boundary_match"] is True
    assert comparison["full_result_match"] is False
    assert comparison["ownership"]["tracked_advertising_actual"] is False
