from __future__ import annotations

import json
from io import StringIO
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

import monitor.management.commands.evaluate_trend_headlines as command_module


def _manifest(tmp_path: Path) -> Path:
    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps(
            {
                "run_id": "command-test",
                "model": "deepseek-v4-pro",
                "max_calls": 28,
                "input_token_budget": 20_000_000,
                "dollar_budget": "100",
                "input_dollars_per_million_tokens": "1",
                "output_dollars_per_million_tokens": "2",
                "pricing_checked_at": "2026-08-14T00:00:00Z",
                "context_window_tokens": 300000,
                "concurrency": 1,
            }
        ),
        encoding="utf-8",
    )
    return path


def test_dry_run_reports_preflight_without_provider_transport(tmp_path, monkeypatch):
    output = StringIO()
    monkeypatch.setattr(
        command_module,
        "run_synthetic_evaluation",
        lambda *_args, **_kwargs: pytest.fail("dry-run attempted provider transport"),
    )

    call_command(
        "evaluate_trend_headlines",
        dry_run=True,
        manifest=_manifest(tmp_path),
        stdout=output,
    )

    payload = json.loads(output.getvalue())
    assert payload["transport_enabled"] is False
    assert payload["manifest"]["model"] == "deepseek-v4-pro"
    assert payload["concurrency"] == 1
    assert payload["planned_call_count"] == 28


def test_execute_is_explicit_and_writes_machine_and_editorial_artifacts(
    tmp_path, monkeypatch
):
    output = StringIO()
    captured = {}

    def fake_run(manifest, scenarios, config, **kwargs):
        captured.update(
            model=config.model,
            concurrency=manifest.concurrency,
            scenario_count=len(scenarios),
            cancellation_path=kwargs["cancellation_path"],
        )
        return {
            "artifact_schema_version": 1,
            "manifest": manifest.as_json(),
            "execution": {
                "concurrency": 1,
                "calls_used": 0,
                "accounted_input_tokens": 0,
                "accounted_cost_dollars": "0.000000",
                "stop_reason": "completed",
            },
            "results": [],
        }

    monkeypatch.setattr(command_module, "run_synthetic_evaluation", fake_run)
    cancel = tmp_path / "cancel"
    call_command(
        "evaluate_trend_headlines",
        execute=True,
        manifest=_manifest(tmp_path),
        output_dir=tmp_path / "artifacts",
        cancel_file=cancel,
        stdout=output,
    )

    payload = json.loads(output.getvalue())
    assert captured == {
        "model": "deepseek-v4-pro",
        "concurrency": 1,
        "scenario_count": 16,
        "cancellation_path": cancel,
    }
    assert Path(payload["json"]).exists()
    assert Path(payload["markdown"]).exists()
    assert json.loads(Path(payload["json"]).read_text())["results"] == []


def test_manifest_is_required_before_execute_or_dry_run():
    with pytest.raises(CommandError, match="evaluation_manifest_required"):
        call_command("evaluate_trend_headlines", dry_run=True)

    with pytest.raises(CommandError, match="evaluation_manifest_required"):
        call_command("evaluate_trend_headlines", execute=True)


def test_calibration_uses_no_provider_and_writes_a_read_only_artifact(
    tmp_path, monkeypatch
):
    output = StringIO()
    captured = {}

    def fake_calibration(**kwargs):
        captured.update(kwargs)
        return {
            "calibration_schema_version": 1,
            "read_only": True,
            "config_written": False,
            "groups": [],
        }

    monkeypatch.setattr(
        command_module,
        "calibrate_historical_materiality",
        fake_calibration,
    )
    monkeypatch.setattr(
        command_module,
        "run_synthetic_evaluation",
        lambda *_args, **_kwargs: pytest.fail(
            "calibration attempted provider transport"
        ),
    )

    call_command(
        "evaluate_trend_headlines",
        calibrate=True,
        as_of="2026-08-14T00:00:00Z",
        anchor_count=3,
        anchor_step_days=7,
        minimum_samples=5,
        windows="7,30",
        output_dir=tmp_path,
        stdout=output,
    )

    paths = json.loads(output.getvalue())
    artifact = json.loads(Path(paths["json"]).read_text())
    assert len(captured["anchors"]) == 3
    assert captured["windows"] == (7, 30)
    assert captured["minimum_samples"] == 5
    assert artifact["calibration"]["read_only"] is True
    assert artifact["execution"]["calls_used"] == 0


def test_calibration_rejects_unbounded_anchor_count_before_query(tmp_path, monkeypatch):
    monkeypatch.setattr(
        command_module,
        "calibrate_historical_materiality",
        lambda **_kwargs: pytest.fail("invalid calibration reached database loader"),
    )

    with pytest.raises(CommandError, match="calibration_anchor_bound_invalid"):
        call_command(
            "evaluate_trend_headlines",
            calibrate=True,
            anchor_count=65,
            output_dir=tmp_path,
        )
