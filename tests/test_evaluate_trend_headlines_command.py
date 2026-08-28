"""Operator command contracts for finite per-brand evaluation."""

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
                "reviewer": "codex:command-test",
                "model": "deepseek-v4-pro",
                "max_calls": 17,
                "input_token_budget": 2_000_000,
                "output_token_budget": 200_000,
                "dollar_budget": "10",
                "input_dollars_per_million_tokens": "0.50",
                "output_dollars_per_million_tokens": "2.00",
                "pricing_version": "test-v1",
                "pricing_checked_at": "2026-08-27T00:00:00+00:00",
                "context_window_tokens": 500_000,
                "brand_cap": 25,
                "concurrency": 1,
            }
        ),
        encoding="utf-8",
    )
    return path


def test_synthetic_dry_run_reports_exact_v3_graph_without_transport(
    tmp_path, monkeypatch
):
    output = StringIO()
    monkeypatch.setattr(
        command_module,
        "run_per_brand_evaluation",
        lambda *_args, **_kwargs: pytest.fail("dry-run attempted transport"),
    )

    call_command(
        "evaluate_trend_headlines",
        dry_run=True,
        synthetic=True,
        manifest=_manifest(tmp_path),
        stdout=output,
    )

    payload = json.loads(output.getvalue())
    assert payload["planned_call_count"] == 17
    assert payload["transport_enabled"] is False
    assert payload["publication_enabled"] is False
    assert payload["manifest"]["reviewer"] == "codex:command-test"


def test_execute_is_explicit_and_writes_machine_and_editorial_artifacts(
    tmp_path, monkeypatch
):
    output = StringIO()
    captured = {}

    def fake_run(manifest, snapshots, config, **kwargs):
        captured.update(
            reviewer=manifest.reviewer,
            snapshot_sizes=[len(snapshot["dossiers"]) for snapshot in snapshots],
            model=config.model,
            include_controls=kwargs["include_calibration_controls"],
        )
        return {
            "artifact_schema_version": 2,
            "manifest": manifest.as_json(),
            "publication_enabled": False,
            "execution": {
                "calls_used": 0,
                "accounted_cost_dollars": "0.000000",
                "stop_reason": "completed",
            },
            "activation_assessment": {"complete": True},
            "brand_outcomes": [],
            "critic_calibration": {},
        }

    monkeypatch.setattr(command_module, "run_per_brand_evaluation", fake_run)
    call_command(
        "evaluate_trend_headlines",
        execute=True,
        synthetic=True,
        manifest=_manifest(tmp_path),
        output_dir=tmp_path / "artifacts",
        stdout=output,
    )

    payload = json.loads(output.getvalue())
    assert captured == {
        "reviewer": "codex:command-test",
        "snapshot_sizes": [1, 3, 5],
        "model": "deepseek-v4-pro",
        "include_controls": True,
    }
    assert Path(payload["json"]).exists()
    assert Path(payload["markdown"]).exists()


def test_omitted_dataset_preserves_the_bounded_synthetic_default(tmp_path):
    output = StringIO()
    call_command(
        "evaluate_trend_headlines",
        dry_run=True,
        manifest=_manifest(tmp_path),
        stdout=output,
    )
    assert json.loads(output.getvalue())["planned_call_count"] == 17


def test_manifest_is_required_before_preflight_or_execute(tmp_path):
    with pytest.raises(CommandError, match="evaluation_manifest_required"):
        call_command("evaluate_trend_headlines", execute=True, synthetic=True)


def test_real_mode_uses_bounded_read_only_snapshot_builder(tmp_path, monkeypatch):
    output = StringIO()
    captured = {}

    def fake_snapshots(windows, *, as_of, manifest):
        captured.update(windows=windows, as_of=as_of, brand_cap=manifest.brand_cap)
        return []

    monkeypatch.setattr(
        command_module, "build_real_evaluation_snapshots", fake_snapshots
    )

    call_command(
        "evaluate_trend_headlines",
        dry_run=True,
        real=True,
        windows="1,7",
        as_of="2026-08-27T00:00:00+00:00",
        manifest=_manifest(tmp_path),
        stdout=output,
    )

    assert captured["windows"] == (1, 7)
    assert captured["brand_cap"] == 25
    assert captured["as_of"].isoformat() == "2026-08-27T00:00:00+00:00"
    assert json.loads(output.getvalue())["planned_call_count"] == 0


def test_calibration_remains_provider_free_and_writes_read_only_artifact(
    tmp_path, monkeypatch
):
    output = StringIO()
    monkeypatch.setattr(
        command_module,
        "calibrate_historical_materiality",
        lambda **_kwargs: {
            "read_only": True,
            "config_written": False,
            "groups": [],
        },
    )
    monkeypatch.setattr(
        command_module,
        "run_per_brand_evaluation",
        lambda *_args, **_kwargs: pytest.fail("calibration attempted transport"),
    )

    call_command(
        "evaluate_trend_headlines",
        calibrate=True,
        as_of="2026-08-27T00:00:00+00:00",
        anchor_count=3,
        windows="7,30",
        output_dir=tmp_path,
        stdout=output,
    )

    paths = json.loads(output.getvalue())
    artifact = json.loads(Path(paths["json"]).read_text())
    assert artifact["calibration"]["read_only"] is True
    assert artifact["publication_enabled"] is False
    assert artifact["execution"]["calls_used"] == 0
