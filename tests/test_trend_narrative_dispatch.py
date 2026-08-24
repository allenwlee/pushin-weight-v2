"""Post-harvest dispatch contracts for the shared trend narrative."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from django.db import transaction

from monitor.trend_narrative_dispatch import dispatch_harvest_completion
from x_monitor.config import HeadlineNarrativeConfig


def _stats(*, status: str = "completed") -> dict:
    return {
        "run_id": "cycle-a",
        "status": status,
        "finished_at": "2026-08-12T12:00:00+00:00",
        "totals": {"n_calls_planned": 7, "n_calls_run": 7},
    }


class _FakeTask:
    def __init__(self, *, error: Exception | None = None):
        self.calls: list[dict] = []
        self.error = error

    def apply_async(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return SimpleNamespace(id="headline-task-a")


def _config(
    monkeypatch,
    *,
    enqueue_enabled: bool = True,
    activation_state: str = "owner_override",
):
    config = HeadlineNarrativeConfig(
        enqueue_enabled=enqueue_enabled,
        activation_state=activation_state,
    )
    monkeypatch.setattr(
        "monitor.trend_narrative_dispatch.load_config",
        lambda _path: SimpleNamespace(headline_narrative=config),
    )
    return config


def test_eligible_completion_enqueues_one_expiring_headline_only_message(
    monkeypatch,
):
    config = _config(monkeypatch)
    task = _FakeTask()

    result = dispatch_harvest_completion(_stats(), dry_run=False, task=task)

    assert result.status == "enqueued"
    assert result.task_id == "headline-task-a"
    assert len(task.calls) == 1
    call = task.calls[0]
    assert call["queue"] == "trend-narratives"
    assert call["expires"] == config.task_expiry_seconds
    assert call["args"][0] == {
        "schema_version": 1,
        "source_cycle_id": "cycle-a",
        "completed_at": "2026-08-12T12:00:00+00:00",
        "outcome": "completed",
        "dry_run": False,
    }


@pytest.mark.parametrize("status", ["aborted", "error", "skipped", "running"])
def test_ineligible_outcomes_and_dry_runs_never_enqueue(monkeypatch, status):
    _config(monkeypatch)
    task = _FakeTask()

    outcome = dispatch_harvest_completion(
        _stats(status=status), dry_run=False, task=task
    )
    dry = dispatch_harvest_completion(_stats(), dry_run=True, task=task)

    assert outcome.status == "ineligible"
    assert dry.status == "ineligible"
    assert task.calls == []


def test_enqueue_control_off_and_broker_failure_are_isolated(monkeypatch):
    _config(monkeypatch, enqueue_enabled=False)
    off_task = _FakeTask()
    off = dispatch_harvest_completion(_stats(), dry_run=False, task=off_task)
    assert off.status == "disabled"
    assert off_task.calls == []

    _config(monkeypatch, enqueue_enabled=True)
    broken_task = _FakeTask(error=ConnectionError("broker down"))
    broken = dispatch_harvest_completion(
        _stats(), dry_run=False, task=broken_task
    )
    assert broken.status == "broker_error"
    assert len(broken_task.calls) == 1


def test_pending_activation_blocks_raw_enabled_enqueue(monkeypatch):
    config = _config(monkeypatch, activation_state="pending")
    task = _FakeTask()

    result = dispatch_harvest_completion(_stats(), dry_run=False, task=task)

    assert config.enqueue_enabled
    assert not config.enqueue_active
    assert result.status == "disabled"
    assert task.calls == []


@pytest.mark.django_db(transaction=True)
def test_atomic_dispatch_runs_only_after_commit(monkeypatch):
    _config(monkeypatch)
    task = _FakeTask()

    with transaction.atomic():
        result = dispatch_harvest_completion(_stats(), dry_run=False, task=task)
        assert result.status == "scheduled_after_commit"
        assert task.calls == []

    assert len(task.calls) == 1


@pytest.mark.django_db(transaction=True)
def test_rolled_back_harvest_never_dispatches(monkeypatch):
    _config(monkeypatch)
    task = _FakeTask()

    with (
        pytest.raises(RuntimeError, match="rollback fixture"),
        transaction.atomic(),
    ):
        dispatch_harvest_completion(_stats(), dry_run=False, task=task)
        raise RuntimeError("rollback fixture")

    assert task.calls == []


def test_both_live_harvest_entrypoints_call_the_isolated_dispatch(monkeypatch):
    import monitor.management.commands.run_cycle as command_module
    import monitor.tasks as tasks_module

    stats = _stats(status="degraded")
    stats["errors"] = []
    events: list[tuple[str, bool]] = []
    cfg = SimpleNamespace(
        llm=SimpleNamespace(relevancy_model="fixture"),
        harvest=SimpleNamespace(relevancy_timeout_seconds=1),
    )

    class Runner:
        def __init__(self, **_kwargs):
            pass

        def run(self):
            return dict(stats)

    monkeypatch.setattr("x_monitor.config.load_config", lambda _path: cfg)
    monkeypatch.setattr("monitor.cycle.CycleRunner", Runner)
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
        lambda payload, *, dry_run: events.append(
            (payload["run_id"], dry_run)
        ),
    )

    command = command_module.Command()
    command._handle(
        enqueue=False,
        dry_run=False,
        brands=None,
        limit_per_call=None,
        max_pages_per_call=None,
        skip_fetch=False,
        as_json=False,
    )
    tasks_module._execute_cycle(dry_run=False)

    assert events == [("cycle-a", False), ("cycle-a", False)]
