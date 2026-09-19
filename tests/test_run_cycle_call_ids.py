"""Regression net for bounded manual ``run_cycle --call-ids`` execution."""

from __future__ import annotations

import json
from contextlib import contextmanager
from io import StringIO
from types import SimpleNamespace

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from x_monitor.config import Config, DiscoveryLaneConfig, DiscoveryQueryConfig
from x_monitor.query_plan import PlannedCall


def _cfg() -> Config:
    cfg = Config(
        enabled_models=["deepseek"],
        daily_ceiling=100,
        x_monitor_list_id=42,
    )
    query = DiscoveryQueryConfig(
        query_id="JD_EN_ORG",
        language="en",
        query_family="organization",
        primary_terms=['"AI company"'],
        co_occurrence=["hiring"],
    )
    cfg.discovery.jobs = DiscoveryLaneConfig(
        enabled=False,
        query_pack_version="jobs-test-v1",
        queries=[query],
    )
    cfg.discovery.personnel = DiscoveryLaneConfig(
        enabled=False,
        query_pack_version="personnel-test-v1",
        queries=[
            DiscoveryQueryConfig(
                query_id="PD_EN_ORG",
                language="en",
                query_family="organization",
                primary_terms=["Anthropic"],
                co_occurrence=["joined"],
            )
        ],
    )
    return cfg


def _planned(call_id: str) -> PlannedCall:
    return PlannedCall(
        call_id=call_id,
        call_kind="brand_wide",
        brand_id="deepseek",
        bucket=None,
        query_string=f'("{call_id}")',
        query_length=len(call_id) + 4,
    )


@pytest.fixture
def command_runtime(monkeypatch):
    """Install a no-provider command runtime and return captured calls."""
    captured: dict[str, object] = {}
    cfg = _cfg()
    planned = [_planned("A"), _planned("JD_EN_ORG"), _planned("PD_EN_ORG")]

    monkeypatch.setattr("x_monitor.config.load_config", lambda _path: cfg)
    monkeypatch.setattr(
        "monitor.cycle.plan_calls_for_cycle", lambda _cfg: list(planned)
    )
    monkeypatch.setattr(
        "x_monitor.reattribute.build_relevancy_client_from_env",
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

    @contextmanager
    def writer_lock(**_kwargs):
        yield SimpleNamespace(acquired=True, contention=None)

    monkeypatch.setattr("monitor.run_lock.harvest_writer_lock", writer_lock)

    class Runner:
        def __init__(self, **kwargs):
            captured["runner_kwargs"] = kwargs

        def run(self):
            runner_kwargs = captured["runner_kwargs"]
            captured["executed_call_ids"] = [
                call.call_id
                for call in planned
                if call.call_id in set(runner_kwargs.get("_backfill_call_ids", []))
            ]
            return {
                "status": "completed",
                "post_fetch": {},
                "totals": {"n_calls_planned": len(captured["executed_call_ids"])},
            }

    monkeypatch.setattr("monitor.cycle.CycleRunner", Runner)
    return captured


def test_manual_call_ids_reach_real_command_caller_and_narrow_execution(
    command_runtime,
):
    stdout = StringIO()
    call_command(
        "run_cycle",
        "--call-ids",
        " JD_EN_ORG, pd_en_org ",
        "--json",
        stdout=stdout,
        stderr=StringIO(),
    )

    captured = command_runtime
    assert captured["runner_kwargs"]["cycle_kind"] == "manual"
    assert captured["runner_kwargs"]["_backfill_call_ids"] == [
        "JD_EN_ORG",
        "PD_EN_ORG",
    ]
    assert captured["executed_call_ids"] == ["JD_EN_ORG", "PD_EN_ORG"]
    assert json.loads(stdout.getvalue())["status"] == "completed"


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ("", "nonblank"),
        ("A, ", "nonblank"),
        ("A,a", "duplicates"),
        ("NOT_A_CALL", "unknown"),
        ("JD_EN_ORG", "not currently planned"),
    ],
)
def test_manual_call_ids_fail_closed_before_provider_construction(
    monkeypatch, raw, message
):
    cfg = _cfg()
    monkeypatch.setattr("x_monitor.config.load_config", lambda _path: cfg)
    monkeypatch.setattr(
        "monitor.cycle.plan_calls_for_cycle",
        lambda _cfg: [_planned("A")],
    )
    monkeypatch.setattr(
        "x_monitor.reattribute.build_relevancy_client_from_env",
        lambda _cfg: pytest.fail("provider constructed before call-id validation"),
    )
    with pytest.raises(CommandError, match=message):
        call_command(
            "run_cycle",
            "--call-ids",
            raw,
            "--dry-run",
            stdout=StringIO(),
            stderr=StringIO(),
        )


def test_invalid_manual_call_id_never_reserves_harvest_writer(monkeypatch):
    cfg = _cfg()
    monkeypatch.setattr("x_monitor.config.load_config", lambda _path: cfg)
    monkeypatch.setattr(
        "monitor.cycle.plan_calls_for_cycle",
        lambda _cfg: [_planned("A")],
    )

    @contextmanager
    def forbidden_writer_lock(**_kwargs):
        pytest.fail("invalid manual selector reserved the harvest writer")
        yield

    monkeypatch.setattr(
        "monitor.run_lock.harvest_writer_lock",
        forbidden_writer_lock,
    )
    with pytest.raises(CommandError, match="unknown"):
        call_command(
            "run_cycle",
            "--call-ids",
            "NOT_A_CALL",
            stdout=StringIO(),
            stderr=StringIO(),
        )


@pytest.mark.parametrize("flag", ["--scheduled", "--staging-acceptance", "--async"])
def test_manual_call_ids_reject_incompatible_modes(flag):
    args = ["run_cycle", "--call-ids", "A", flag]
    if flag == "--staging-acceptance":
        args.append("A")
    with pytest.raises(CommandError, match="manual-only"):
        call_command(*args, stdout=StringIO(), stderr=StringIO())
