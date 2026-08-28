from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from x_monitor.config import Config, load_config

REPO = Path(__file__).resolve().parent.parent


def _config(**harvest_overrides) -> Config:
    return Config(
        enabled_models=["minimax"],
        daily_ceiling=100,
        harvest=harvest_overrides,
    )


def test_harvest_runtime_defaults_pin_u9_contract():
    cfg = _config()

    assert cfg.harvest.run_deadline_seconds == 13 * 60
    assert cfg.harvest.next_slot_reserve_seconds == 2 * 60
    assert cfg.harvest.tip_sweep_target_seconds == 120
    assert cfg.harvest.relevancy_timeout_seconds == 30
    assert cfg.harvest.backlog.pending_per_call == 8
    assert cfg.harvest.backlog.quarantined_per_call == 4
    assert cfg.harvest.backlog.max_attempts == 8
    assert cfg.harvest.backlog.max_age_hours == 24
    assert cfg.harvest.backlog.replays_per_cycle == 2
    assert cfg.harvest.list_membership.page_size == 20
    assert cfg.harvest.list_membership.reconcile_interval_hours == 6
    assert cfg.harvest.enrichment.claim_per_cycle == 100
    assert cfg.harvest.enrichment.current_cycle_claim_per_cycle == 50
    assert cfg.harvest.enrichment.carryover_claim_per_cycle == 50
    assert cfg.harvest.enrichment.max_attempts == 8
    assert cfg.harvest.enrichment.max_age_hours == 24
    assert cfg.harvest.enrichment.claim_ttl_seconds == 660
    assert cfg.harvest.enrichment.request_timeout_seconds == 90
    assert cfg.harvest.enrichment.attempt_budget_seconds == 300
    assert cfg.harvest.enrichment.terminalization_reserve_seconds == 30
    assert cfg.harvest.enrichment.claim_safe_envelope_seconds == 630


def test_committed_yaml_pins_production_two_lane_envelope():
    enrichment = load_config(REPO / "config.yaml").harvest.enrichment

    assert (
        enrichment.claim_per_cycle,
        enrichment.current_cycle_claim_per_cycle,
        enrichment.carryover_claim_per_cycle,
    ) == (100, 50, 50)
    assert enrichment.claim_safe_envelope_seconds == 630


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"run_deadline_seconds": 0}, "run_deadline_seconds"),
        ({"next_slot_reserve_seconds": 0}, "next_slot_reserve_seconds"),
        ({"tip_sweep_target_seconds": 0}, "tip_sweep_target_seconds"),
        ({"relevancy_timeout_seconds": 0}, "relevancy_timeout_seconds"),
        (
            {"run_deadline_seconds": 800, "next_slot_reserve_seconds": 120},
            "next_slot_reserve_seconds",
        ),
        (
            {"run_deadline_seconds": 100, "tip_sweep_target_seconds": 120},
            "tip_sweep_target_seconds",
        ),
        (
            {"tip_sweep_target_seconds": 20, "relevancy_timeout_seconds": 30},
            "relevancy_timeout_seconds",
        ),
    ],
)
def test_harvest_runtime_rejects_nonpositive_or_impossible_budgets(
    overrides, field
):
    with pytest.raises(ValidationError) as exc_info:
        _config(**overrides)

    assert field in str(exc_info.value)


def test_config_creates_one_shareable_monotonic_deadline_contract():
    cfg = _config()
    clock_values = iter([100.0])

    deadline = cfg.harvest.start_deadline(monotonic=lambda: next(clock_values))

    assert deadline.started_at == 100.0
    assert deadline.deadline_at == 880.0
    assert deadline.tip_target_at == 220.0
    assert deadline.remaining(monotonic=lambda: 250.0) == 630.0
    assert deadline.can_start(30, monotonic=lambda: 850.0)
    assert not deadline.can_start(31, monotonic=lambda: 850.0)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("claim_per_cycle", 0),
        ("max_attempts", 0),
        ("max_age_hours", 0),
        ("claim_ttl_seconds", 0),
        ("request_timeout_seconds", 0),
        ("attempt_budget_seconds", 0),
        ("terminalization_reserve_seconds", 0),
    ],
)
def test_enrichment_runtime_rejects_unbounded_or_disabled_guards(field, value):
    with pytest.raises(ValidationError) as exc_info:
        _config(enrichment={field: value})

    assert field in str(exc_info.value)


def test_enrichment_claim_lease_covers_both_stage_budgets():
    with pytest.raises(ValidationError) as exc_info:
        _config(
            enrichment={
                "claim_ttl_seconds": 599,
                "attempt_budget_seconds": 300,
            }
        )

    assert "claim_ttl_seconds" in str(exc_info.value)


@pytest.mark.parametrize(
    "enrichment",
    [
        {
            "claim_per_cycle": 99,
            "current_cycle_claim_per_cycle": 50,
            "carryover_claim_per_cycle": 50,
        },
        {
            "claim_per_cycle": 5,
            "current_cycle_claim_per_cycle": 5,
            "carryover_claim_per_cycle": 1,
        },
    ],
)
def test_enrichment_lane_caps_must_fit_the_aggregate(enrichment):
    with pytest.raises(ValidationError) as exc_info:
        _config(enrichment=enrichment)

    assert "claim_per_cycle" in str(exc_info.value)


def test_enrichment_claim_lease_covers_terminalization_reserve():
    with pytest.raises(ValidationError) as exc_info:
        _config(
            enrichment={
                "claim_ttl_seconds": 629,
                "attempt_budget_seconds": 300,
                "terminalization_reserve_seconds": 30,
            }
        )

    assert "claim_ttl_seconds" in str(exc_info.value)
