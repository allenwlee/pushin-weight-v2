from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import pytest

from scripts import u20_translation_synthesis_execute as execute
from scripts import u20_translation_synthesis_compare as compare


def _digest(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _prepared(tmp_path: Path, rows: list[dict] | None = None) -> tuple[Path, dict]:
    prepared = tmp_path / "prepared"
    prepared.mkdir()
    rows = rows or [
        {"post_id": "1", "text": "one", "context": []},
        {"post_id": "2", "text": "two", "context": []},
    ]
    # The existing preparation capture is provider-free, but it invokes both
    # production callers. This gives run_arm an exact frozen topology.
    requests = {
        "incumbent": compare.capture_requests(rows, "deepseek-v4-flash"),
        "0731": compare.capture_requests(rows, "deepseek/deepseek-v4-flash-0731"),
    }
    translation_count = len(requests["incumbent"]["translation"])
    synthesis_count = len(requests["incumbent"]["synthesis"])
    contract = {
        "schema": "u20-translation-synthesis-compare/v1",
        "rows": rows,
        "rows_sha256": _digest(rows),
        "requests_sha256": {arm: _digest(value) for arm, value in requests.items()},
        "requests_per_arm": {"literal_translation": translation_count, "synthesis": synthesis_count},
        "implementation_sha256": {},
        "source_corpus": "scripts/u20_translation_synthesis_execute.py",
        "source_sha256": hashlib.sha256(Path(execute.__file__).read_bytes()).hexdigest(),
        "models": {
            "incumbent": {"model": "deepseek-v4-flash", "base_url": "https://api.deepseek.com/anthropic"},
            "0731": {"model": "deepseek/deepseek-v4-flash-0731"},
        },
        "bounds": {
            "incumbent": {"input_bytes": 99999, "output_tokens": 20000,
                           "reserved_cost_usd": "0.02",
                           "roles": {"translation": {"requests": translation_count, "input_bytes": 1, "output_tokens": 2048},
                                     "synthesis": {"requests": synthesis_count, "input_bytes": 1, "output_tokens": 4000}}},
            "0731": {"input_bytes": 99999, "output_tokens": 20000,
                     "reserved_cost_usd": "0.02",
                     "roles": {"translation": {"requests": translation_count, "input_bytes": 1, "output_tokens": 2048},
                               "synthesis": {"requests": synthesis_count, "input_bytes": 1, "output_tokens": 4000}}},
        },
        "hard_cost_cap_usd_per_arm": "0.50",
    }
    (prepared / "contract.json").write_text(json.dumps(contract))
    (prepared / "requests.json").write_text(json.dumps(requests))
    return prepared, contract


def test_prepare_freezes_existing_artifact_and_rejects_later_request_tamper(tmp_path):
    prepared, _ = _prepared(tmp_path)
    execution = tmp_path / "execution"

    contract = execute.prepare_execution(prepared, execution)

    assert contract["prepared_requests_sha256"] == hashlib.sha256((prepared / "requests.json").read_bytes()).hexdigest()
    requests = json.loads((prepared / "requests.json").read_text())
    requests["incumbent"]["translation"][0]["max_tokens"] = 7
    (prepared / "requests.json").write_text(json.dumps(requests))
    with pytest.raises(ValueError, match="prepared requests changed"):
        execute.load_execution(execution)


def test_prepare_execution_keeps_literal_per_request_caps_for_20_20_5_capture(tmp_path):
    rows = [
        {"post_id": str(index), "text": f"source {index}", "context": []}
        for index in range(45)
    ]
    prepared, _ = _prepared(tmp_path, rows)
    execution = tmp_path / "execution"

    contract = execute.prepare_execution(prepared, execution)

    assert contract["limits"]["role_max_tokens"]["incumbent"]["translation"] == [8192, 32768]
    assert contract["limits"]["role_max_tokens"]["0731"]["translation"] == [8192, 32768]
    assert contract["limits"]["role_max_tokens"]["incumbent"]["synthesis"] == [4000]


class _Client:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []
        self.model = "deepseek-v4-flash"

    def messages_create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


def test_once_only_transport_persists_error_before_provider_and_never_retries(tmp_path):
    expected = {"model": "deepseek-v4-flash", "max_tokens": 3, "messages": []}
    client = _Client(error=TimeoutError("ambiguous"))
    transport = execute.FrozenTransport(
        client, "incumbent", "translation", [expected], tmp_path / "responses", tmp_path / "ledger.json",
        {"calls": 1, "input_bytes": 5000, "output_tokens": 3, "dollars": "0.35"},
    )

    assert transport.messages_create(**expected) == {}
    with pytest.raises(execute.ConsumedRequestError):
        transport.messages_create(**expected)

    assert len(client.calls) == 1
    measurement = next((tmp_path / "responses").glob("*.measurement.json"))
    assert json.loads(measurement.read_text())["status"] == "error"


def test_real_translator_marks_a_consumed_timeout_failed_without_retry_backoff(tmp_path):
    rows = [{"post_id": "1", "text": "one", "context": []}]
    expected = compare.capture_requests(rows, "deepseek-v4-flash")["translation"]
    client = _Client(error=TimeoutError("ambiguous"))
    transport = execute.FrozenTransport(
        client, "incumbent", "translation", expected, tmp_path / "responses", tmp_path / "ledger.json",
        {"calls": 1, "input_bytes": 10000, "output_tokens": 2048, "dollars": "0.35"},
        socket_idle_timeout_seconds=180,
    )
    cfg = SimpleNamespace(llm=SimpleNamespace(
        translator_model="deepseek-v4-flash", translator_base_url="https://api.deepseek.com/anthropic"
    ))

    started = __import__("time").monotonic()
    output = execute.translate_batch_literal([{"tweet_id": "1", "text": "one"}], transport, cfg=cfg)

    assert output[0]["translation_failed"] is True
    assert len(client.calls) == 1
    assert client.calls[0]["timeout"] == 180
    assert __import__("time").monotonic() - started < 1


def test_load_execution_fails_closed_for_a_directory_where_a_corpus_file_was_frozen(tmp_path):
    prepared, _ = _prepared(tmp_path)
    execution = tmp_path / "execution"
    execute.prepare_execution(prepared, execution)
    contract_path = execution / "execution-contract.json"
    contract = json.loads(contract_path.read_text())
    contract["prepared_source_hashes"]["corpus"] = "irrelevant"
    prepared_contract = json.loads((prepared / "contract.json").read_text())
    prepared_contract["source_corpus"] = "."
    (prepared / "contract.json").write_text(json.dumps(prepared_contract))
    contract["prepared_contract_sha256"] = hashlib.sha256((prepared / "contract.json").read_bytes()).hexdigest()
    contract_path.write_text(json.dumps(contract))

    with pytest.raises(ValueError, match="is not a file"):
        execute.load_execution(execution)


def test_model_arm_lock_rejects_an_overlapping_role_process_lock(tmp_path):
    with execute._model_arm_lock(tmp_path):
        with pytest.raises(execute.ConsumedRequestError, match="already running"):
            with execute._model_arm_lock(tmp_path):
                pass


def test_target_wrapper_adds_fixed_route_settings_and_rejects_parallel_duplicate(tmp_path):
    expected = {
        "model": "deepseek/deepseek-v4-flash-0731", "max_tokens": 3, "messages": [],
        "temperature": 1.0, "top_p": 1.0, "seed": 42,
    }
    client = _Client(response={"results": []})
    client.model = expected["model"]
    transport = execute.FrozenTransport(
        client, "0731", "translation", [expected], tmp_path / "responses", tmp_path / "ledger.json",
        {"calls": 1, "input_bytes": 5000, "output_tokens": 3, "dollars": "0.35"},
    )

    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: execute._capture(lambda: transport.messages_create(
            model=expected["model"], max_tokens=3, messages=[])), range(2)))

    assert sum(outcome["ok"] for outcome in outcomes) == 1
    assert len(client.calls) == 1
    assert {"temperature", "top_p", "seed"}.issubset(client.calls[0])


def test_true_callers_are_used_for_each_role(monkeypatch, tmp_path):
    prepared, _ = _prepared(tmp_path)
    execution = tmp_path / "execution"
    execute.prepare_execution(prepared, execution)
    calls = []

    monkeypatch.setattr(execute, "price_preflight", lambda model: {"cost_gate_ready": False})
    monkeypatch.setattr(execute, "credential", lambda model: "fixture")
    client = _Client(response={})
    monkeypatch.setattr(execute, "build_client", lambda model, key: client)

    execute.run_arm(execution, "incumbent", "translation")
    execute.run_arm(execution, "incumbent", "synthesis")

    assert len(client.calls) == 1 + len(compare.capture_requests(
        [{"post_id": "1", "text": "one", "context": []}, {"post_id": "2", "text": "two", "context": []},
    ], "deepseek-v4-flash")["synthesis"])
    assert client.calls[0]["max_tokens"] == 3277
    assert client.calls[0]["timeout"] == 180
    assert all(call["timeout"] == 60 for call in client.calls[1:])
    assert all(call["max_tokens"] == 4000 for call in client.calls[1:])
