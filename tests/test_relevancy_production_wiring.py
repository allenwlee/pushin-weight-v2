from __future__ import annotations

from contextlib import contextmanager
from io import StringIO

from django.core.management import call_command

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


def test_management_command_explicit_scheduled_mode_reaches_cycle_runner(monkeypatch):
    captured = {}

    @contextmanager
    def acquired_lock(**_kwargs):
        yield type("Lease", (), {"acquired": True, "contention": None})()

    class Runner:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def run(self):
            return {"status": "completed", "post_fetch": {}}

    monkeypatch.setattr("monitor.run_lock.harvest_writer_lock", acquired_lock)
    monkeypatch.setattr("monitor.cycle.CycleRunner", Runner)
    cfg = Config(
        enabled_models=["deepseek"],
        daily_ceiling=100,
        llm=LlmConfig(),
        harvest=HarvestConfig(),
    )
    monkeypatch.setattr("x_monitor.config.load_config", lambda _path: cfg)
    monkeypatch.setattr(
        "x_monitor.reattribute.build_anthropic_client_from_env",
        lambda _cfg: None,
    )
    monkeypatch.setattr(
        "x_monitor.relevancy.build_binary_relevancy_llm_call",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        "monitor.trend_narrative_dispatch.dispatch_harvest_completion",
        lambda *_args, **_kwargs: None,
    )

    call_command(
        "run_cycle",
        "--scheduled",
        "--json",
        stdout=StringIO(),
        stderr=StringIO(),
    )

    assert captured["cycle_kind"] == "scheduled"
