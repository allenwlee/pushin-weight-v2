from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import model_task_experiment as experiment


def _input(path: Path) -> None:
    path.write_text(json.dumps({"rows": [{"post_id": "p1", "text": "hola", "source_language": "other"}]}), encoding="utf-8")


def test_prepare_exercises_actual_literal_caller_and_pins_profile(tmp_path: Path):
    source, directory = tmp_path / "rows.json", tmp_path / "trial"
    _input(source)
    contract = experiment.prepare(source, directory, "qwen_translation_v1")
    assert contract["requests"]
    request = contract["requests"][0]
    assert request["model"] == "qwen/qwen3.7-flash"
    assert request["provider"]["only"] == ["alibaba"]
    assert request["provider"]["allow_fallbacks"] is False


def test_prepare_exercises_actual_synthesis_caller(tmp_path: Path):
    source, directory = tmp_path / "rows.json", tmp_path / "trial"
    _input(source)
    contract = experiment.prepare(source, directory, "gemini_flex_commentary_v1")
    assert len(contract["requests"]) == 1
    assert contract["requests"][0]["service_tier"] == "flex"
    assert contract["requests"][0]["response_format"]["type"] == "json_schema"


def test_run_consumes_once_and_reports_missing_delivery_separately(tmp_path: Path):
    source, directory, responses = tmp_path / "rows.json", tmp_path / "trial", tmp_path / "responses.json"
    _input(source); contract = experiment.prepare(source, directory, "qwen_translation_v1")
    responses.write_text(json.dumps({}), encoding="utf-8")
    first = experiment.run(directory, responses)
    assert first["delivery"] == {"missing_outputs": len(contract["requests"]), "complete": False}
    assert first["quality_gate"]["status"].startswith("not_assessed")
    assert experiment.run(directory, responses) == first


def test_run_rejects_changed_frozen_contract_and_attempt_limit(tmp_path: Path):
    source, directory, responses = tmp_path / "rows.json", tmp_path / "trial", tmp_path / "responses.json"
    _input(source); experiment.prepare(source, directory, "qwen_translation_v1")
    responses.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="attempt exceeds"):
        experiment.run(directory, responses, attempt=4)
    contract = json.loads((directory / "contract.json").read_text()); contract["requests"].append({})
    (directory / "contract.json").write_text(json.dumps(contract), encoding="utf-8")
    with pytest.raises(ValueError, match="frozen contract"):
        experiment.run(directory, responses)


def test_only_gemini_commentary_gets_the_owner_authorized_fourth_profile_limit():
    assert experiment.attempt_limit("google/gemini-2.5-flash-lite", "commentary") == 4
    assert experiment.attempt_limit("google/gemini-2.5-flash-lite", "translation") == 3
    assert experiment.attempt_limit("openai/gpt-5.6-luna", "commentary") == 3


def test_run_rejects_response_for_an_unfrozen_request(tmp_path: Path):
    source, directory, responses = tmp_path / "rows.json", tmp_path / "trial", tmp_path / "responses.json"
    _input(source); experiment.prepare(source, directory, "gemini_flex_commentary_v1")
    responses.write_text(json.dumps({"not-a-request": {}}), encoding="utf-8")
    with pytest.raises(ValueError, match="not in frozen"):
        experiment.run(directory, responses)


def test_undefined_detection_branch_and_mutable_budget_are_rejected(tmp_path):
    source = tmp_path / "rows.json"
    source.write_text(json.dumps({"rows": [{"post_id": "p1", "text": "hello"}]}))
    with pytest.raises(ValueError, match="source_language"):
        experiment.prepare(source, tmp_path / "invalid", "qwen_translation_v1")
    _input(source)
    directory = tmp_path / "trial"
    contract = experiment.prepare(source, directory, "qwen_translation_v1")
    contract["reserved_cost_usd"] = 0
    experiment.write(directory / "contract.json", contract)
    with pytest.raises(ValueError, match="frozen contract"):
        experiment.live(directory)
    assert not (directory / "attempt-1.live").exists()


def test_marker_normalization_only_changes_framing_of_complete_ordered_blocks():
    prompt = "SOURCE:\n[[PW0:001]]\nHello\n[[PW0:002]]\nWorld\n[[PW0:END]]"
    response = "[[PW0:001]] 你好\n[[PW0:002]]  \n世界\n[[PW0:END]]"
    assert experiment.normalize_marker_lines(response, prompt) == "[[PW0:001]]\n你好\n[[PW0:002]]\n世界\n[[PW0:END]]"
    missing = "[[PW0:001]] 你好\n[[PW0:END]]"
    assert experiment.normalize_marker_lines(missing, prompt) == missing


@pytest.mark.parametrize("profile_key,provider,model", [("qwen_translation_v1", "Alibaba", "qwen/qwen3.7-flash"), ("gemini_flex_commentary_v1", "Google AI Studio", "google/gemini-2.5-flash-lite")])
def test_live_real_callers_validate_route_and_consume_once(tmp_path, monkeypatch, profile_key, provider, model):
    source, directory = tmp_path / "rows.json", tmp_path / "trial"
    source.write_text(json.dumps({"rows": [{"post_id": "p1", "text": "Hello world", "source_language": "en", "context": [{"provenance": "stored_quote", "text": "Hi"}]}]}))
    contract = experiment.prepare(source, directory, profile_key)
    monkeypatch.setattr(experiment, "credential", lambda _: "fake")
    sent = []
    def fake_send(client, wire, *, timeout):
        assert "timeout" not in wire
        assert (directory / "attempt-1.live" / "started.json").exists()
        assert list((directory / "attempt-1.live" / "requests").glob("*.json"))
        sent.append(wire)
        if profile_key.endswith("commentary_v1"):
            assert "stored_quote" in wire["messages"][0]["content"]
            content = json.dumps({"post_id": "p1", "commentary_en": "A greeting.", "commentary_zh_cn": "一句问候。", "commentary_ja": "挨拶です。"})
        else:
            content = "你好世界" if len(sent) == 1 else "こんにちは世界"
        return {"model": model, "provider": provider, "service_tier": "flex" if "gemini" in profile_key else None, "openrouter_metadata": {"endpoints": {"available": [{"selected": True, "provider": provider, "model": model}]}}, "choices": [{"finish_reason": "stop", "message": {"content": content}}], "usage": {"prompt_tokens": 20, "completion_tokens": 10}}
    monkeypatch.setattr(experiment.OpenRouterChatCompletionsClient, "_send_request", fake_send)
    report = experiment.live(directory)
    assert len(sent) == len(contract["requests"])
    assert not report["errors"]["transport"] and not report["errors"]["structural"]
    assert report["semantic"] == "unassessed"
    with pytest.raises(ValueError, match="already started"):
        experiment.live(directory)
    assert len(sent) == len(contract["requests"])


def test_structured_translation_preserves_real_caller_paragraphs(tmp_path, monkeypatch):
    source, directory = tmp_path / "source.json", tmp_path / "trial"
    source.write_text(json.dumps({"rows": [{"post_id": "p1", "text": "Hello\n\nWorld", "source_language": "en"}]}))
    experiment.prepare(source, directory, "qwen_translation_v5")
    monkeypatch.setattr(experiment, "credential", lambda _: "fake")

    def send(client, wire, *, timeout):
        data = json.loads(wire["messages"][1]["content"])
        assert data["source_lines"] == ["Hello", "World"]
        assert wire["messages"][0]["role"] == "system"
        lines = ["你好", "世界"] if data["target_language"] == "Simplified Chinese" else ["こんにちは", "世界"]
        content = json.dumps({"source_reading": "A greeting to the world.", "lines": lines})
        return {"model": "qwen/qwen3.7-flash", "provider": "Alibaba", "openrouter_metadata": {"endpoints": {"available": [{"selected": True, "provider": "Alibaba", "model": "qwen/qwen3.7-flash"}]}}, "choices": [{"finish_reason": "stop", "message": {"content": content}}], "usage": {"prompt_tokens": 30, "completion_tokens": 20}}

    monkeypatch.setattr(experiment.OpenRouterChatCompletionsClient, "_send_request", send)
    report = experiment.live(directory, attempt=5)
    assert report["rows"]["p1"]["text_zh_cn"] == "你好\n\n世界"
    assert report["rows"]["p1"]["text_ja"] == "こんにちは\n\n世界"
    assert report["rows"]["p1"]["text_en"] == "Hello\n\nWorld"
    assert not report["errors"]["structural"]


def test_single_request_profile_limits_real_transport_concurrency(tmp_path, monkeypatch):
    import threading
    import time
    source, directory = tmp_path / 'sources.json', tmp_path / 'trial'
    source.write_text(json.dumps({'rows': [
        {'post_id': f'p{i}', 'text': f'Hello {i}', 'source_language': 'en'} for i in range(3)
    ]}))
    contract = experiment.prepare(source, directory, 'qwen235_translation_v2')
    assert contract['limits']['max_concurrency'] == 1
    monkeypatch.setattr(experiment, 'credential', lambda _: 'fake')
    guard = threading.Lock()
    running = peak = 0

    def send(client, wire, *, timeout):
        nonlocal running, peak
        with guard:
            running += 1
            peak = max(peak, running)
        time.sleep(0.02)
        data = json.loads(wire['messages'][1]['content'])
        line = '你好' if data['target_language'] == 'Simplified Chinese' else 'こんにちは'
        with guard:
            running -= 1
        return {'model': 'qwen/qwen3-235b-a22b-2507', 'provider': 'GMICloud',
                'openrouter_metadata': {'endpoints': {'available': [{'selected': True, 'provider': 'GMICloud', 'model': 'qwen/qwen3-235b-a22b-2507'}]}},
                'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps({'lines': [line]})}}],
                'usage': {'prompt_tokens': 20, 'completion_tokens': 10}}

    monkeypatch.setattr(experiment.OpenRouterChatCompletionsClient, '_send_request', send)
    report = experiment.live(directory)
    assert peak == 1
    assert report['request_count'] == 6
    assert not report['errors']['transport'] and not report['errors']['structural']


def test_qwen_v3_enforces_four_second_send_start_spacing_with_fake_clock(tmp_path, monkeypatch):
    source, directory = tmp_path / 'sources.json', tmp_path / 'trial'
    source.write_text(json.dumps({'rows': [
        {'post_id': f'p{i}', 'text': 'OpenCode Go [[PQ0:001]] may be cheaper.', 'source_language': 'en'} for i in range(2)
    ]}))
    contract = experiment.prepare(source, directory, 'qwen235_translation_v3')
    assert contract['limits']['max_concurrency'] == 1
    assert contract['limits']['min_request_interval_seconds'] == 4
    monkeypatch.setattr(experiment, 'credential', lambda _: 'fake')
    now, starts, sleeps = [100.0], [], []
    original_transport = experiment.FrozenLiveTransport

    def fake_sleep(seconds):
        sleeps.append(seconds)
        now[0] += seconds

    def transport_factory(*args):
        return original_transport(*args, clock=lambda: now[0], sleep=fake_sleep)

    monkeypatch.setattr(experiment, 'FrozenLiveTransport', transport_factory)

    def send(client, wire, *, timeout):
        starts.append(now[0])
        data = json.loads(wire['messages'][1]['content'])
        assert data['source_lines'] == ['OpenCode Go [[PQ0:001]] may be cheaper.']
        line = 'OpenCode Go [[PQ0:001]] 更便宜。' if data['target_language'] == 'Simplified Chinese' else 'OpenCode Go [[PQ0:001]] はもっと安いかもしれない。'
        now[0] += 0.25
        return {'model': 'qwen/qwen3-235b-a22b-2507', 'provider': 'GMICloud',
                'openrouter_metadata': {'endpoints': {'available': [{'selected': True, 'provider': 'GMICloud', 'model': 'qwen/qwen3-235b-a22b-2507'}]}},
                'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps({'lines': [line]})}}],
                'usage': {'prompt_tokens': 20, 'completion_tokens': 10}}

    monkeypatch.setattr(experiment.OpenRouterChatCompletionsClient, '_send_request', send)
    report = experiment.live(directory)
    assert starts == [100.0, 104.0, 108.0, 112.0]
    assert sleeps == [3.75, 3.75, 3.75]
    assert [item['pacing_wait_ms'] for item in report['raw_responses'].values()] == [0, 3750, 3750, 3750]
    assert not report['errors']['transport'] and not report['errors']['structural']
