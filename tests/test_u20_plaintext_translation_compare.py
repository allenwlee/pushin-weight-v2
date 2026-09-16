"""Focused safety contracts for the U20 plaintext translation harness."""
from __future__ import annotations

import json
import threading
from decimal import Decimal
from pathlib import Path

import pytest

from scripts import u20_plaintext_translation_compare as harness
from x_monitor.provider_telemetry import ProviderTextResponse


def _input_contract(path: Path) -> None:
    rows = []
    for language in ("en", "zh-cn", "ja"):
        for number in range(15):
            rows.append(
                {
                    "post_id": f"{language}-{number}",
                    "source_language": language,
                    "text": f"{language} source {number}",
                    "context": [],
                }
            )
    payload = {
        "schema": harness.INPUT_SCHEMA,
        "rows": rows,
        "rows_sha256": harness.digest(rows),
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _prepare(tmp_path: Path, monkeypatch) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    source = tmp_path / "input-contract.json"
    _input_contract(source)
    monkeypatch.setattr(harness, "INPUT_CONTRACT", source)
    directory = tmp_path / "run"
    harness.prepare(directory)
    return directory


def test_prepare_invokes_true_plaintext_caller_and_freezes_90_requests_per_arm(tmp_path, monkeypatch):
    directory = _prepare(tmp_path, monkeypatch)
    contract = json.loads((directory / "contract.json").read_text())
    requests = json.loads((directory / "requests.json").read_text())

    assert contract["limits"]["calls_per_arm"] == 90
    assert contract["limits"]["socket_idle_timeout_seconds"] == 180
    assert all(len(values) == 90 for values in requests.values())
    assert all(
        request["messages"][0]["content"].startswith(harness.LITERAL_TRANSLATION_PROMPT_VERSION + ". Translate one")
        for values in requests.values() for request in values
    )
    assert all(
        request["temperature"] == 1.0
        and request["top_p"] == 1.0
        and request["seed"] == 42
        for request in requests["0731"]
    )
    assert all(Decimal(value["reserved_cost_usd"]) <= harness.HARD_ARM_CAP for value in contract["bounds"].values())


def test_execution_refuses_changed_frozen_input_or_requests(tmp_path, monkeypatch):
    directory = _prepare(tmp_path, monkeypatch)
    source = harness.INPUT_CONTRACT
    payload = json.loads(source.read_text())
    payload["rows"][0]["text"] = "drift"
    source.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="input contract changed"):
        harness.load_execution(directory)


class _Delegate:
    def __init__(self, *, response: object | None = None, error: Exception | None = None) -> None:
        self.request_profile = "deepseek_0731"
        self.response = response or ProviderTextResponse('  "literal"\n```\n', {"input_tokens": 3, "output_tokens": 2, "cost_usd": 0.01})
        self.error = error
        self.calls: list[dict] = []

    def messages_create_text(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response


def test_transport_consumes_before_provider_refuses_replay_and_preserves_raw_formatting(tmp_path):
    request = {"model": "test", "max_tokens": 10, "messages": [{"role": "user", "content": "x"}]}
    delegate = _Delegate()
    transport = harness.FrozenPlaintextTransport(delegate, [request], tmp_path)

    assert transport.request_profile == "deepseek_0731"
    assert transport.messages_create_text(**request).text == '  "literal"\n```\n'
    with pytest.raises(harness.ConsumedRequestError, match="already_consumed"):
        transport.messages_create_text(**request)

    assert len(delegate.calls) == 1
    assert delegate.calls[0]["timeout"] == 180
    response = next((tmp_path / "responses").glob("*.json"))
    saved = json.loads(response.read_text())
    assert saved["raw_text"] == '  "literal"\n```\n'
    assert saved["raw_text_code_fence"] == '```text\n  "literal"\n```\n\n```'
    assert list((tmp_path / "consumed").glob("*.json"))


def test_transport_stores_error_usage_after_preconsumption(tmp_path):
    request = {"model": "test", "max_tokens": 10, "messages": []}
    error = RuntimeError("ambiguous provider failure")
    error.provider_usage = {"input_tokens": 7, "output_tokens": 3, "cost_usd": 0.02}  # type: ignore[attr-defined]
    delegate = _Delegate(error=error)
    transport = harness.FrozenPlaintextTransport(delegate, [request], tmp_path)

    with pytest.raises(RuntimeError, match="ambiguous"):
        transport.messages_create_text(**request)

    assert len(delegate.calls) == 1
    evidence = json.loads(next((tmp_path / "errors").glob("*.json")).read_text())
    assert evidence["usage"]["cost_usd"] == 0.02
    with pytest.raises(harness.ConsumedRequestError):
        transport.messages_create_text(**request)


def test_execute_uses_serial_real_caller_and_reports_explicit_provider_failure(tmp_path, monkeypatch):
    directory = _prepare(tmp_path, monkeypatch)
    active = 0
    peak = 0
    lock = threading.Lock()

    class Client(_Delegate):
        def messages_create_text(self, **kwargs):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            try:
                return super().messages_create_text(**kwargs)
            finally:
                with lock:
                    active -= 1

    client = Client()
    monkeypatch.setattr(
        harness,
        "price_preflight",
        lambda arm: {"cost_gate_ready": arm == "0731", "retrieval": "ok"},
    )
    monkeypatch.setattr(harness, "credential", lambda _arm: "fixture")
    monkeypatch.setattr(harness, "build_client", lambda _arm, _key: client)
    report = harness.run_arm(directory, "0731")

    assert len(client.calls) == 90
    assert peak == 1
    assert report["requests"]["received"] == 90
    assert report["failures"] == 0
    assert Decimal(report["summary"]["planning_reserved_cost_usd"]) <= Decimal("0.50")

    failed_directory = _prepare(tmp_path / "failed", monkeypatch)
    error = RuntimeError("provider down")
    error.provider_usage = {"input_tokens": 1, "output_tokens": 1, "cost_usd": 0.01}  # type: ignore[attr-defined]
    monkeypatch.setattr(harness, "build_client", lambda _arm, _key: Client(error=error))
    with pytest.raises(harness.ExecutionFailure, match="explicit failures"):
        harness.run_arm(failed_directory, "incumbent")
    result = json.loads((failed_directory / "arms" / "incumbent" / "result.json").read_text())
    assert result["requests"]["errors"] == 90
    assert result["failures"] == 45


def test_execute_refuses_unverified_price_preflight():
    with pytest.raises(ValueError, match="0731 price preflight"):
        harness.require_price_preflight("0731", {"cost_gate_ready": False})
    with pytest.raises(ValueError, match="incumbent price preflight"):
        harness.require_price_preflight("incumbent", {"retrieval": "unverified"})


def test_prepare_targeted_paragraph_probe_freezes_only_selected_source_rows(tmp_path, monkeypatch):
    source = tmp_path / "input-contract.json"
    _input_contract(source)
    data = json.loads(source.read_text())
    data["rows"][0]["text"] = "First paragraph.\n\nRepeated paragraph.\n\nRepeated paragraph."
    data["rows_sha256"] = harness.digest(data["rows"])
    source.write_text(json.dumps(data))
    monkeypatch.setattr(harness, "INPUT_CONTRACT", source)
    directory = tmp_path / "targeted"
    contract = harness.prepare(directory, paragraph_tracking=True, post_ids=["en-0"])
    assert contract["limits"]["calls_per_arm"] == 2
    assert contract["paragraph_tracking"] is True
    assert contract["literal_translation_prompt_version"] == "literal-translation-paragraphs-v7"
    assert [r["post_id"] for r in contract["rows"]] == ["en-0"]
    loaded, requests = harness.load_execution(directory)
    assert loaded == contract
    assert all(len(values) == 2 for values in requests.values())
    assert "Repeated paragraph." in requests["0731"][0]["messages"][0]["content"]
    with pytest.raises(ValueError, match="selection"):
        harness.prepare(tmp_path / "unknown", post_ids=["missing"])
