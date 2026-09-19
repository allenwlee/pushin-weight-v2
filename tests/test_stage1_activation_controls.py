"""Fail-closed activation controls for bounded Stage 1 lanes."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from core.discovery import plan_discovery_calls
from x_monitor.config import SynthesisConfig, load_config

REPO = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO / "config.yaml"
CONTROL_VALUES = {
    "X_MONITOR_DISCOVERY_JOBS_ENABLED": "False",
    "X_MONITOR_DISCOVERY_JOBS_PER_CYCLE_CALL_CEILING": "1",
    "X_MONITOR_DISCOVERY_JOBS_MAX_RESULTS": "20",
    "X_MONITOR_DISCOVERY_JOBS_MAX_PAGES": "1",
    "X_MONITOR_DISCOVERY_PERSONNEL_ENABLED": "False",
    "X_MONITOR_DISCOVERY_PERSONNEL_PER_CYCLE_CALL_CEILING": "1",
    "X_MONITOR_DISCOVERY_PERSONNEL_MAX_RESULTS": "20",
    "X_MONITOR_DISCOVERY_PERSONNEL_MAX_PAGES": "1",
    "X_MONITOR_TARGETED_EXTRACTION_ENABLED": "False",
    "X_MONITOR_TARGETED_EXTRACTION_MAX_CALLS_PER_CYCLE": "0",
    "X_MONITOR_SYNTHESIS_PREWARM_ENABLED": "False",
    "X_MONITOR_SYNTHESIS_PREWARM_PER_CYCLE": "0",
}


def _service_environment(blueprint_name: str, service_name: str) -> dict[str, str]:
    blueprint = yaml.safe_load((REPO / blueprint_name).read_text(encoding="utf-8"))
    service = next(item for item in blueprint["services"] if item["name"] == service_name)
    return {
        entry["key"]: entry.get("value")
        for entry in service["envVars"]
        if "key" in entry
    }


def test_checked_in_activation_controls_are_fail_closed() -> None:
    for blueprint_name, service_name in (
        ("render-staging.yaml", "pushinweight-staging-harvest"),
        ("render.yaml", "pushinweight-harvest"),
    ):
        environment = _service_environment(blueprint_name, service_name)
        assert {key: environment[key] for key in CONTROL_VALUES} == CONTROL_VALUES


def test_fail_closed_environment_loads_without_opening_a_lane(monkeypatch) -> None:
    for key, value in CONTROL_VALUES.items():
        monkeypatch.setenv(key, value)

    config = load_config(CONFIG_PATH)

    assert config.discovery.jobs.enabled is False
    assert config.discovery.personnel.enabled is False
    assert config.targeted_extraction.enabled is False
    assert config.targeted_extraction.max_calls_per_cycle == 0
    assert config.synthesis.prewarm_enabled is False
    assert config.synthesis.prewarm_per_cycle == 0


def test_bounded_activation_env_overrides_checked_in_disabled_lanes(monkeypatch) -> None:
    for key in CONTROL_VALUES:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "staging")
    monkeypatch.setenv("X_MONITOR_DISCOVERY_JOBS_ENABLED", "true")
    monkeypatch.setenv("X_MONITOR_DISCOVERY_PERSONNEL_ENABLED", "true")
    monkeypatch.setenv("X_MONITOR_TARGETED_EXTRACTION_ENABLED", "true")
    monkeypatch.setenv("X_MONITOR_TARGETED_EXTRACTION_MAX_CALLS_PER_CYCLE", "5")
    monkeypatch.setenv("X_MONITOR_SYNTHESIS_PREWARM_ENABLED", "true")
    monkeypatch.setenv("X_MONITOR_SYNTHESIS_PREWARM_PER_CYCLE", "5")

    config = load_config(CONFIG_PATH)

    assert config.discovery.jobs.enabled is True
    assert config.discovery.personnel.enabled is True
    assert config.targeted_extraction.enabled is True
    assert config.targeted_extraction.max_calls_per_cycle == 5
    assert config.synthesis.prewarm_enabled is True
    assert config.synthesis.prewarm_per_cycle == 5


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
def test_staging_discovery_activation_plans_one_capped_call_per_lane(monkeypatch) -> None:
    for key in CONTROL_VALUES:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "staging")
    monkeypatch.setenv("X_MONITOR_DISCOVERY_JOBS_ENABLED", "true")
    monkeypatch.setenv("X_MONITOR_DISCOVERY_PERSONNEL_ENABLED", "true")
    for lane in ("JOBS", "PERSONNEL"):
        monkeypatch.setenv(
            f"X_MONITOR_DISCOVERY_{lane}_PER_CYCLE_CALL_CEILING", "1"
        )
        monkeypatch.setenv(f"X_MONITOR_DISCOVERY_{lane}_MAX_RESULTS", "20")
        monkeypatch.setenv(f"X_MONITOR_DISCOVERY_{lane}_MAX_PAGES", "1")

    calls = plan_discovery_calls(load_config(CONFIG_PATH), list_id=42)

    assert [(call.discovery_lane, call.call_id) for call in calls] == [
        ("jobs", "JD_EN_ORG"),
        ("personnel", "PD_EN_ORG"),
    ]
    assert all(call.max_results == 20 and call.max_pages == 1 for call in calls)
    assert sum(
        max(
            int(call.max_results or 0) * int(call.credits_per_result or 0),
            int(call.minimum_credits_per_call or 0),
        )
        for call in calls
    ) <= 600


def test_production_rejects_any_truthy_temporary_activation(monkeypatch) -> None:
    for key in CONTROL_VALUES:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "production")
    monkeypatch.setenv("X_MONITOR_TARGETED_EXTRACTION_ENABLED", "true")
    monkeypatch.setenv("X_MONITOR_TARGETED_EXTRACTION_MAX_CALLS_PER_CYCLE", "5")

    with pytest.raises(ValueError, match="temporary Stage 1 activation requires"):
        load_config(CONFIG_PATH)


def test_enabled_targeted_extraction_requires_explicit_positive_cap(monkeypatch) -> None:
    for key in CONTROL_VALUES:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "staging")
    monkeypatch.setenv("X_MONITOR_TARGETED_EXTRACTION_ENABLED", "true")
    monkeypatch.setenv("X_MONITOR_TARGETED_EXTRACTION_MAX_CALLS_PER_CYCLE", "0")

    with pytest.raises(ValidationError, match="enabled targeted extraction requires a positive cap"):
        load_config(CONFIG_PATH)


def test_synthesis_prewarm_cap_must_fit_one_atomic_demand_batch() -> None:
    with pytest.raises(
        ValidationError,
        match="synthesis prewarm cap must not exceed demand batch limit",
    ):
        SynthesisConfig(
            prewarm_enabled=True,
            prewarm_per_cycle=10,
            demand_batch_limit=5,
        )
