from __future__ import annotations

from monitor.management.commands.run_synthesis_worker import build_synthesis_client
from x_monitor.config import SynthesisConfig
from x_monitor.deepinfra import DeepInfraChatCompletionsClient


def test_synthesis_worker_builds_locked_direct_gemma_client(monkeypatch):
    monkeypatch.setenv("DEEPINFRA_API_KEY", "direct-key")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "wrong-provider-key")

    config = SynthesisConfig()
    client = build_synthesis_client(config)

    assert isinstance(client, DeepInfraChatCompletionsClient)
    assert client.api_key == "direct-key"
    assert client.model == "google/gemma-4-31B-it-turbo"
    assert client.request_profile == "gemma4_tagged"
    assert client._base_url == (
        "https://api.deepinfra.com/v1/openai/chat/completions"
    )


def test_synthesis_worker_does_not_fall_back_to_another_provider_key(monkeypatch):
    monkeypatch.delenv("DEEPINFRA_API_KEY", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "must-not-be-used")

    assert build_synthesis_client(SynthesisConfig()) is None
