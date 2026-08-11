from __future__ import annotations

from monitor import tasks
from x_monitor.config import Config, HarvestConfig, LlmConfig


def test_scheduled_entrypoint_threads_configured_model_and_timeout(monkeypatch):
    cfg = Config(
        enabled_models=["deepseek"],
        daily_ceiling=100,
        llm=LlmConfig(relevancy_model="configured-relevance-model"),
        harvest=HarvestConfig(relevancy_timeout_seconds=17),
    )
    captured = {}

    monkeypatch.setattr(tasks, "load_config", lambda path: cfg)
    monkeypatch.setattr(
        "x_monitor.reattribute.build_anthropic_client_from_env",
        lambda config: object(),
    )

    def build_call(**kwargs):
        captured.update(kwargs)
        return "bounded-call"

    monkeypatch.setattr(
        "x_monitor.relevancy.build_binary_relevancy_llm_call", build_call
    )

    class Runner:
        def __init__(self, **kwargs):
            captured["runner_kwargs"] = kwargs

        def run(self):
            return {"status": "completed"}

    monkeypatch.setattr("monitor.cycle.CycleRunner", Runner)
    assert tasks._execute_cycle(dry_run=True)["status"] == "completed"
    assert captured["model"] == "configured-relevance-model"
    assert captured["timeout_seconds"] == 17
    assert captured["runner_kwargs"]["_relevancy_llm_call"] == "bounded-call"
