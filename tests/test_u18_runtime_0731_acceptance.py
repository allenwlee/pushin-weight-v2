"""The selected-model acceptance run cannot silently expand paid work."""
import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from scripts.u18_runtime_0731_acceptance import FrozenTransport, verify_proven_requests
from x_monitor.openrouter import OpenRouterPermanentError
from x_monitor.provider_telemetry import ProviderResponse


class FakeClient:
    def __init__(self):
        self.calls = 0

    def build_request(self, **kwargs):
        return {"model": "frozen", "messages": kwargs["messages"]}

    def messages_create(self, **kwargs):
        self.calls += 1
        return ProviderResponse({"results": []}, usage={"cost_usd": 0.001})


def test_replication_rejects_prompt_drift_but_allows_declared_transport_changes():
    source = {"provider": {"only": ["DeepInfra"]}, "messages": [
        {"role": "system", "content": "Proven instructions"},
        {"role": "user", "content": json.dumps({"cases": {"P01": {
            "case_id_for_audit_only": "H123", "evidence": {"text": "source"}
        }}}, separators=(",", ":"))},
    ]}
    restored = json.loads(json.dumps(source))
    restored["provider"]["only"] = ["deepinfra/fp8"]
    restored["messages"][1]["content"] = '{"cases":{"P01":{"evidence":{"text":"source"}}}}'
    verify_proven_requests([restored], {"content": [source]})
    restored["messages"][0]["content"] = "Shortened instructions"
    with pytest.raises(ValueError, match="restored_r123_request_drift"):
        verify_proven_requests([restored], {"content": [source]})


def test_cycle_budget_wrapper_preserves_selected_request_profile():
    from monitor.cycle import _BoundedClassifierClient

    delegate = FakeClient()
    delegate.request_profile = "deepseek_0731"
    bounded = _BoundedClassifierClient(delegate, maximum_calls=6, pause_seconds=0)
    assert bounded.request_profile == "deepseek_0731"


def test_replication_permits_only_the_declared_shared_prompt_addition():
    source = {"provider": {"only": ["DeepInfra"]}, "messages": [
        {"role": "system", "content": "Proven instructions"},
        {"role": "user", "content": '{"cases":{}}'},
    ]}
    restored = json.loads(json.dumps(source))
    restored["provider"]["only"] = ["deepinfra/fp8"]
    addition = "\nShared brand-relevance rule."
    restored["messages"][0]["content"] += addition
    verify_proven_requests([restored], {"content": [source]}, prompt_addition=addition)
    restored["messages"][0]["content"] = "Shortened base" + addition
    with pytest.raises(ValueError, match="restored_r123_request_drift"):
        verify_proven_requests([restored], {"content": [source]}, prompt_addition=addition)


def test_only_exact_frozen_request_can_cross_provider_boundary(tmp_path):
    client = FakeClient()
    body = client.build_request(messages=[{"role": "user", "content": "source"}])
    transport = FrozenTransport(client, [body], tmp_path)
    with pytest.raises(OpenRouterPermanentError, match="not_frozen"):
        transport.messages_create(messages=[{"role": "user", "content": "changed"}])
    assert client.calls == 0
    transport.messages_create(messages=body["messages"])
    assert client.calls == 1
    with pytest.raises(OpenRouterPermanentError, match="already_attempted"):
        transport.messages_create(messages=body["messages"])
    assert client.calls == 1


def test_interrupted_transport_is_never_rebought(tmp_path):
    class Fails(FakeClient):
        def messages_create(self, **kwargs):
            self.calls += 1
            raise TimeoutError("interrupted")

    client = Fails()
    body = client.build_request(messages=[])
    transport = FrozenTransport(client, [body], tmp_path)
    with pytest.raises(OpenRouterPermanentError, match="transport_failed"):
        transport.messages_create(messages=[])
    restored = FrozenTransport(client, [body], tmp_path)
    with pytest.raises(OpenRouterPermanentError, match="already_attempted"):
        restored.messages_create(messages=[])
    assert client.calls == 1


def test_concurrent_duplicate_transport_has_one_entitlement(tmp_path):
    client = FakeClient()
    body = client.build_request(messages=[])
    transport = FrozenTransport(client, [body], tmp_path)

    def attempt():
        try:
            transport.messages_create(messages=[])
            return True
        except OpenRouterPermanentError:
            return False

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(attempt) for _ in range(2)]
        assert sum(future.result() for future in futures) == 1
    assert client.calls == 1


def test_billable_malformed_response_retains_usage(tmp_path):
    class Invalid(FakeClient):
        def messages_create(self, **kwargs):
            raise OpenRouterPermanentError("malformed", provider_usage={"cost_usd": 0.002})

    client = Invalid()
    transport = FrozenTransport(client, [client.build_request(messages=[])], tmp_path)
    with pytest.raises(OpenRouterPermanentError) as caught:
        transport.messages_create(messages=[])
    assert caught.value.provider_usage == {"cost_usd": 0.002}
    files = list(tmp_path.glob("*.measurement.json"))
    assert len(files) == 1
    assert json.loads(files[0].read_text())["usage"]["cost_usd"] == 0.002
